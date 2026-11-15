/*
 * El resultado de comparar las seis estrategias, calculado a partir del bloque `simulation` del paquete: los puntajes por
 * corrida que deja `pipeline/simulate/run.py`. Devuelve la MISMA forma que `scenarioResult` (el ejemplo escrito a mano),
 * así que las pantallas no cambian.
 *
 * Cada corrida es un año real de lluvia y temperatura de la zona, igual para las seis estrategias. Aquí se cuenta cuántas
 * veces queda primera cada una con el objetivo elegido, se saca el margen mediano y se declara qué criterio explica la
 * diferencia. Los criterios sin dato (255) se dejan fuera y los demás pesos se reparten; si falta demasiado peso, esa
 * estrategia no se ordena para ese objetivo.
 */
import { CRITERIA, OBJECTIVE_WEIGHTS, STRATEGIES, robustnessOf, type Criterion, type Objective, type StrategyId } from './comparison.ts';
import { MAX_MISSING_WEIGHT, namedScenario, type ScenarioResult, type Scores } from './scenarios.ts';
import type { Simulation } from './schema.gen.ts';

const NO_DATA = 255;

interface Cell {
  runs: number;
  bytes: Uint8Array;
}

const decoded = new WeakMap<Simulation, Map<string, Cell>>();

function decode(sim: Simulation): Map<string, Cell> {
  let map = decoded.get(sim);
  if (map) return map;
  map = new Map();
  for (const c of sim.cells) {
    const raw = atob(c.scores);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
    map.set(`${c.rain}|${c.temp}`, { runs: c.runs, bytes });
  }
  decoded.set(sim, map);
  return map;
}

const at = (cell: Cell, s: number, c: number, r: number) => cell.bytes[(s * CRITERIA.length + c) * cell.runs + r]!;

const median = (xs: number[]): number => {
  const a = [...xs].sort((x, y) => x - y);
  const m = a.length >> 1;
  return a.length % 2 ? a[m]! : (a[m - 1]! + a[m]!) / 2;
};

/** Puntaje mediano de cada criterio; `null` donde está declarado sin dato. */
function medianScores(cell: Cell, s: number): Scores {
  const out = {} as Scores;
  CRITERIA.forEach((crit, c) => {
    if (at(cell, s, c, 0) === NO_DATA) {
      out[crit] = null;
      return;
    }
    out[crit] = median(Array.from({ length: cell.runs }, (_, r) => at(cell, s, c, r)));
  });
  return out;
}

/** Puntaje ponderado de una corrida; `null` si a la estrategia le falta demasiado peso para este objetivo. */
function runTotal(cell: Cell, s: number, o: Objective, r: number): number | null {
  let sum = 0;
  let used = 0;
  CRITERIA.forEach((crit, c) => {
    const v = at(cell, s, c, r);
    if (v === NO_DATA) return;
    sum += OBJECTIVE_WEIGHTS[o][crit] * v;
    used += OBJECTIVE_WEIGHTS[o][crit];
  });
  if (1 - used >= MAX_MISSING_WEIGHT - 1e-9) return null;
  return sum / used;
}

const byStrategy = <T,>(f: (id: StrategyId, s: number) => T) =>
  Object.fromEntries(STRATEGIES.map((id, s) => [id, f(id, s)])) as Record<StrategyId, T>;

function heaviest(o: Objective, diff: (c: Criterion) => number | null): Criterion | null {
  let best: Criterion | null = null;
  let max = -1;
  for (const c of CRITERIA) {
    const d = diff(c);
    if (d === null) continue;
    const v = Math.abs(OBJECTIVE_WEIGHTS[o][c] * d);
    if (v > max) [max, best] = [v, c];
  }
  return best;
}

const minus = (a: number | null, b: number | null) => (a === null || b === null ? null : a - b);

function cellOf(sim: Simulation, rain: number, temp: number): Cell {
  const cell = decode(sim).get(`${rain}|${temp}`);
  if (!cell) throw new Error(`el paquete no trae la celda de lluvia ${rain} y temperatura ${temp}`);
  return cell;
}

function medianTotals(cell: Cell, o: Objective): Record<StrategyId, number | null> {
  return byStrategy((_id, s) => {
    const t = Array.from({ length: cell.runs }, (_, r) => runTotal(cell, s, o, r));
    return t.some((x) => x === null) ? null : median(t as number[]);
  });
}

export function scenarioResultFromSimulation(
  sim: Simulation,
  objective: Objective,
  rain: number,
  temp: number,
  excluded: ReadonlySet<StrategyId> = new Set(),
): ScenarioResult {
  const cell = cellOf(sim, rain, temp);
  const normalCell = cellOf(sim, 0, 0);
  const runs = cell.runs;
  const named = namedScenario(rain, temp);
  const scores = byStrategy((_id, s) => medianScores(cell, s));
  const normal = byStrategy((_id, s) => medianScores(normalCell, s));
  const totals = medianTotals(cell, objective);
  const normalTotals = medianTotals(normalCell, objective);

  const out = STRATEGIES.filter((id) => excluded.has(id));
  const compatible = STRATEGIES.filter((id) => !excluded.has(id));
  const unranked = compatible.filter((id) => totals[id] === null);
  const order = compatible.filter((id) => totals[id] !== null).sort((a, b) => (totals[b] ?? 0) - (totals[a] ?? 0));
  const firstCount = byStrategy(() => 0);
  const shared = { objective, rain, temp, named, runs, order, unranked, excluded: out, scores, totals, normalTotals };

  const first = order[0];
  const second = order[1];
  if (!first || !second) {
    if (first) firstCount[first] = runs;
    return { ...shared, firstCount, marginMedian: 0, driver: null, movedBy: null };
  }

  // Cuántas veces queda primera cada una: la corrida i es el mismo año para todas.
  for (let r = 0; r < runs; r += 1) {
    let best: StrategyId | null = null;
    let bestScore = -Infinity;
    for (const id of order) {
      const t = runTotal(cell, STRATEGIES.indexOf(id), objective, r) as number;
      if (t > bestScore) [bestScore, best] = [t, id];
    }
    if (best) firstCount[best] += 1;
  }
  const iFirst = STRATEGIES.indexOf(first);
  const iSecond = STRATEGIES.indexOf(second);
  const margin = median(Array.from({ length: runs }, (_, r) => (runTotal(cell, iFirst, objective, r) as number) - (runTotal(cell, iSecond, objective, r) as number)));
  const marginMedian = Math.round(margin);
  const tie = robustnessOf(firstCount[first] / runs, marginMedian) === 'indistinguishable';
  const neutral = rain === 0 && temp === 0;
  const oldTop = [...order].sort((a, b) => (normalTotals[b] ?? 0) - (normalTotals[a] ?? 0))[0]!;
  const movedBetween = (a: StrategyId, b: StrategyId) =>
    heaviest(objective, (c) => minus(minus(scores[a][c], scores[b][c]), minus(normal[a][c], normal[b][c])));
  const movedBy = neutral ? null : first !== oldTop ? movedBetween(first, oldTop) : tie ? movedBetween(first, second) : null;

  return {
    ...shared,
    firstCount,
    marginMedian,
    driver: heaviest(objective, (c) => minus(scores[first][c], scores[second][c])),
    separatingData: tie ? (first === 'E2' || second === 'E2' ? 'localPrice' : 'soilDepth') : undefined,
    movedBy,
  };
}
