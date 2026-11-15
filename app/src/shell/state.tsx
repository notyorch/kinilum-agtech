import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import type { Objective, StrategyId } from '../data/comparison';
import { PARCEL, excludedSet, type Declaration } from '../data/restrictions';
import { scenarioResult, type ScenarioResult } from '../data/scenarios';
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
  go: (s: SectionId) => void;
}

const Ctx = createContext<AppState | null>(null);

const INITIAL_OBJECTIVE: Objective = 'water';
const topOf = (o: Objective, d: Declaration): StrategyId => scenarioResult(o, 0, 0, excludedSet(d)).order[0] ?? 'E0';

export function AppStateProvider({ go, children }: { go: (s: SectionId) => void; children: ReactNode }) {
  const [objective, setObjectiveRaw] = useState<Objective>(INITIAL_OBJECTIVE);
  const [declaration, setDeclaration] = useState<Declaration>(PARCEL);
  const [selected, setSelected] = useState<StrategyId>(() => topOf(INITIAL_OBJECTIVE, PARCEL));
  const [rain, setRain] = useState(0);
  const [temp, setTemp] = useState(0);

  const setObjective = useCallback(
    (o: Objective) => {
      setObjectiveRaw(o);
      setSelected(topOf(o, declaration));
    },
    [declaration],
  );

  const resultAt = useCallback(
    (r: number, t: number) => scenarioResult(objective, r, t, excludedSet(declaration)),
    [objective, declaration],
  );

  const value = useMemo(
    () => ({ objective, setObjective, selected, setSelected, rain, setRain, temp, setTemp, declaration, setDeclaration, resultAt, go }),
    [objective, setObjective, selected, rain, temp, declaration, resultAt, go],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAppState fuera de AppStateProvider');
  return ctx;
}
