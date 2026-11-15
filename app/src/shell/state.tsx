import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Objective, StrategyId } from '../data/comparison';
import { PARCEL, excludedSet, type Declaration } from '../data/restrictions';
import { scenarioResult, type ScenarioResult } from '../data/scenarios';
import { scenarioResultFromSimulation } from '../data/simulation';
import type { Simulation } from '../data/schema.gen';
import { useOffline } from '../offline/OfflineProvider';
import type { SectionId } from './AppShell';

/** Lo que el agricultor elige en una pantalla y las demás necesitan ver. */
interface AppState {
  objective: Objective;
  setObjective: (o: Objective) => void;
  /** La estrategia que está mirando; al cambiar de objetivo vuelve a la primera. */
  selected: StrategyId;
  setSelected: (id: StrategyId) => void;
  /** Ajustes de «¿Qué pasaría si…?»: % de lluvia y °C, sobre la grilla de escenarios. */
  rain: number;
  setRain: (v: number) => void;
  temp: number;
  setTemp: (v: number) => void;
  /** Lo declarado: parte de lo que puso el técnico y el agricultor lo ajusta. */
  declaration: Declaration;
  setDeclaration: (d: Declaration) => void;
  /** Resultado para el objetivo y lo declarado, con el clima que se pida. */
  resultAt: (rain: number, temp: number) => ScenarioResult;
  /** true: el orden sale de las corridas del paquete (datos reales); false: es el ejemplo escrito a mano. */
  simulated: boolean;
  /** El bloque `simulation` del paquete, si lo hay (de ahí salen el orden y el agua que pide cada opción). */
  simulation: Simulation | undefined;
  go: (s: SectionId) => void;
}

const Ctx = createContext<AppState | null>(null);

const INITIAL_OBJECTIVE: Objective = 'water';
/** El resultado para un objetivo y un clima: de la simulación del paquete si la hay, y si no, el ejemplo. */
const resultFor = (sim: Simulation | undefined, o: Objective, r: number, t: number, d: Declaration): ScenarioResult =>
  sim ? scenarioResultFromSimulation(sim, o, r, t, excludedSet(d)) : scenarioResult(o, r, t, excludedSet(d));

const topOf = (o: Objective, d: Declaration, sim?: Simulation): StrategyId => resultFor(sim, o, 0, 0, d).order[0] ?? 'E0';

export function AppStateProvider({ go, children }: { go: (s: SectionId) => void; children: ReactNode }) {
  const sim = useOffline().data?.simulation;
  const [objective, setObjectiveRaw] = useState<Objective>(INITIAL_OBJECTIVE);
  const [declaration, setDeclaration] = useState<Declaration>(PARCEL);
  const [selected, setSelected] = useState<StrategyId>(() => topOf(INITIAL_OBJECTIVE, PARCEL));
  const [rain, setRain] = useState(0);
  const [temp, setTemp] = useState(0);

  const setObjective = useCallback(
    (o: Objective) => {
      setObjectiveRaw(o);
      setSelected(topOf(o, declaration, sim));
    },
    [declaration, sim],
  );

  // Cuando llegan las corridas del paquete, la estrategia mirada vuelve a la primera del orden real.
  useEffect(() => {
    setSelected(topOf(objective, declaration, sim));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sim]);

  const resultAt = useCallback(
    (r: number, t: number) => resultFor(sim, objective, r, t, declaration),
    [objective, declaration, sim],
  );

  const value = useMemo(
    () => ({ objective, setObjective, selected, setSelected, rain, setRain, temp, setTemp, declaration, setDeclaration, resultAt, simulated: !!sim, simulation: sim, go }),
    [objective, setObjective, selected, rain, temp, declaration, resultAt, sim, go],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAppState fuera de AppStateProvider');
  return ctx;
}
