/*
 * Resultado de comparar las seis estrategias para un objetivo, un clima y
 * unas restricciones. Lo usan «Comparar», «¿Qué pasaría si…?» y «Evidencia».
 *
 * Grilla del PRD v0.9: lluvia −30 %…+30 % en pasos de 10 (7) × temperatura
 * −2…+4 °C en pasos de 1 (7) = 49 celdas. 100 corridas por celda; las 6 que
 * coinciden con un escenario con nombre usan 500.
 *
 * CASO ILUSTRATIVO. El paquete real traerá la grilla precalculada (puntajes
 * por corrida) y el motor la ordenará. Mientras no existan, este archivo
 * FABRICA resultados a partir de puntajes medianos escritos a mano y de un
 * efecto lineal de la lluvia y el calor. No es agronomía ni el motor: solo
 * sirve para construir y probar las pantallas, con la misma forma que
 * devolverá el motor. Se borra entero.
 */
import {
  CRITERIA,
  OBJECTIVE_WEIGHTS,
  STRATEGIES,
  type Criterion,
  type Objective,
  type StrategyId,
} from './comparison.ts';
import { fixesNitrogen } from './crops.ts';

export const RAIN_STEPS = [-30, -20, -10, 0, 10, 20, 30] as const;
export const TEMP_STEPS = [-2, -1, 0, 1, 2, 3, 4] as const;

export type NamedScenario = 'normal' | 'dry' | 'veryDry' | 'wet' | 'hot' | 'dryHot';

/** Los seis escenarios con nombre del PRD (lluvia %, temperatura °C). */
export const NAMED: Record<NamedScenario, [number, number]> = {
  normal: [0, 0],
  dry: [-10, 0],
  veryDry: [-20, 0],
  wet: [10, 0],
  hot: [0, 2],
  dryHot: [-10, 2],
};

export function namedScenario(rain: number, temp: number): NamedScenario | null {
  const hit = (Object.keys(NAMED) as NamedScenario[]).find((k) => NAMED[k][0] === rain && NAMED[k][1] === temp);
  return hit ?? null;
}

/** Puntaje 0–100 por criterio; `null` = sin dato (falta un parámetro del cultivo). */
export type Scores = Record<Criterion, number | null>;
type Numbers = Record<Criterion, number>;

/*
 * Criterios sin dato. Garbanzo y trigo no tienen rendimiento ni precio con
 * fuente: su ingreso no se calcula. Se declara; no se inventa.
 */
export const NO_DATA: Partial<Record<StrategyId, readonly Criterion[]>> = {
  E4: ['income'],
  E5: ['income'],
};

/** Puntos de suelo que suma una leguminosa. Sorgo y trigo no los reciben. */
export const NITROGEN_BONUS = 10;

export function nitrogenBonus(id: StrategyId): number {
  return fixesNitrogen(id) ? NITROGEN_BONUS : 0;
}

/* Puntaje mediano de cada criterio en el escenario normal, ANTES del nitrógeno. Ejemplo.
   El ingreso de E4 y E5 es sin dato (NO_DATA): su 0 es un relleno que nunca se lee. */
const BASE: Record<StrategyId, Numbers> = {
  E0: { water: 50, soil: 30, erosion: 25, climate: 45, income: 55 },
  E1: { water: 50, soil: 70, erosion: 80, climate: 50, income: 45 },
  E2: { water: 45, soil: 50, erosion: 45, climate: 50, income: 80 },
  E3: { water: 72, soil: 45, erosion: 45, climate: 72, income: 55 },
  E4: { water: 48, soil: 45, erosion: 40, climate: 35, income: 0 },
  E5: { water: 42, soil: 38, erosion: 42, climate: 30, income: 0 },
};

/* Cambio por cada +10 % de lluvia. La cobertura (E1) depende mucho del agua;
   el sorgo (E3) casi no cambia. */
const PER_RAIN: Record<StrategyId, Numbers> = {
  E0: { water: 4, soil: 0, erosion: -3, climate: 3, income: 2 },
  E1: { water: 6, soil: 9.5, erosion: 8, climate: 4, income: 2 },
  E2: { water: 4, soil: 4, erosion: -2, climate: 3, income: 3 },
  E3: { water: 2, soil: 0, erosion: -2, climate: 1.5, income: 1 },
  E4: { water: 4, soil: 2, erosion: -2, climate: 3, income: 0 },
  E5: { water: 4, soil: 0, erosion: -2, climate: 3, income: 0 },
};

/* Cambio por cada +1 °C. El sorgo tolera mejor el calor. */
const PER_DEGREE: Record<StrategyId, Numbers> = {
  E0: { water: -3, soil: 0, erosion: 0, climate: -4, income: -2 },
  E1: { water: -3, soil: -2, erosion: -1, climate: -3, income: -1.5 },
  E2: { water: -3.5, soil: 0, erosion: 0, climate: -4, income: -3 },
  E3: { water: -1.5, soil: 0, erosion: 0, climate: -1.5, income: -1 },
  E4: { water: -3.5, soil: 0, erosion: 0, climate: -5, income: 0 },
  E5: { water: -4, soil: 0, erosion: 0, climate: -6, income: 0 },
};

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function scoresAt(id: StrategyId, rain: number, temp: number): Scores {
  const r = rain / 10;
  const out = {} as Scores;
  for (const c of CRITERIA) {
    if (NO_DATA[id]?.includes(c)) {
      out[c] = null;
      continue;
    }
    const bonus = c === 'soil' ? nitrogenBonus(id) : 0;
    out[c] = clamp(BASE[id][c] + bonus + r * PER_RAIN[id][c] + temp * PER_DEGREE[id][c], 0, 100);
  }
  return out;
}

/** Si los criterios sin dato pesan esto o más en el objetivo, la estrategia no se ordena. */
export const MAX_MISSING_WEIGHT = 0.5;

/**
 * Puntaje ponderado (0–100). Un criterio sin dato se deja fuera y los demás
 * pesos se reparten; si falta demasiado, devuelve `null`: no se puede ordenar.
 */
export function total(s: Scores, o: Objective): number | null {
  let sum = 0;
  let used = 0;
  for (const c of CRITERIA) {
    const v = s[c];
    if (v === null) continue;
    sum += OBJECTIVE_WEIGHTS[o][c] * v;
    used += OBJECTIVE_WEIGHTS[o][c];
  }
  if (1 - used >= MAX_MISSING_WEIGHT - 1e-9) return null;
  return sum / used;
}

/** El criterio que más pesa en una diferencia entre dos estrategias; ignora los sin dato. */
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

export interface ScenarioResult {
  objective: Objective;
  rain: number;
  temp: number;
  named: NamedScenario | null;
  runs: number;
  /** Las que compiten, de mayor a menor puntaje ponderado. */
  order: StrategyId[];
  /** Compatibles, pero sin datos suficientes para este objetivo. No compiten; siguen visibles. */
  unranked: StrategyId[];
  /** Fuera por restricciones. No compiten; siguen visibles con su razón. */
  excluded: StrategyId[];
  /** Veces que cada estrategia quedó primera, de `runs`. */
  firstCount: Record<StrategyId, number>;
  /** Diferencia de puntaje entre la 1.ª y la 2.ª. */
  marginMedian: number;
  /** Criterio que más explica la diferencia entre la 1.ª y la 2.ª. */
  driver: Criterion | null;
  /** Solo si no podemos distinguir: el dato que separaría a las dos primeras. */
  separatingData?: 'soilDepth' | 'localPrice';
  scores: Record<StrategyId, Scores>;
  totals: Record<StrategyId, number | null>;
  normalTotals: Record<StrategyId, number | null>;
  /** Si el primer lugar cambió frente a lo normal: el criterio que más lo movió. */
  movedBy: Criterion | null;
}

const byStrategy = <T,>(f: (id: StrategyId) => T) =>
  Object.fromEntries(STRATEGIES.map((id) => [id, f(id)])) as Record<StrategyId, T>;

/**
 * Las estrategias excluidas no entran al orden ni al conteo (WHERE); tampoco
 * las que no tienen datos para el objetivo. Compiten las demás.
 */
export function scenarioResult(
  objective: Objective,
  rain: number,
  temp: number,
  excluded: ReadonlySet<StrategyId> = new Set(),
): ScenarioResult {
  const named = namedScenario(rain, temp);
  const runs = named ? 500 : 100;
  const scores = byStrategy((id) => scoresAt(id, rain, temp));
  const normal = byStrategy((id) => scoresAt(id, 0, 0));
  const totals = byStrategy((id) => total(scores[id], objective));
  const normalTotals = byStrategy((id) => total(normal[id], objective));

  const out = STRATEGIES.filter((id) => excluded.has(id));
  const compatible = STRATEGIES.filter((id) => !excluded.has(id));
  const unranked = compatible.filter((id) => totals[id] === null);
  const score = (id: StrategyId) => totals[id] ?? 0;
  const order = compatible.filter((id) => totals[id] !== null).sort((a, b) => score(b) - score(a));

  const firstCount = byStrategy(() => 0);
  const shared = { objective, rain, temp, named, runs, order, unranked, excluded: out, scores, totals, normalTotals };

  const first = order[0];
  const second = order[1];
  // Con una sola opción en competencia (o ninguna) no hay nada que comparar.
  if (!first || !second) {
    if (first) firstCount[first] = runs;
    return { ...shared, firstCount, marginMedian: 0, driver: null, movedBy: null };
  }

  const margin = score(first) - score(second);
  // Tope en 0.94: un ejemplo nunca debe decir «10 de cada 10» (sonaría a certeza).
  const share = margin < 5 ? 0.4 + margin * 0.02 : clamp(0.55 + (margin - 5) * 0.03, 0.55, 0.94);
  const others = order.slice(1);
  const splits = [0.7, 0.2, 0.1].slice(0, others.length);
  const splitSum = splits.reduce((a, b) => a + b, 0);
  others.forEach((id, i) => {
    firstCount[id] = Math.round((1 - share) * ((splits[i] ?? 0) / splitSum) * runs);
  });
  firstCount[first] = runs - others.reduce((acc, id) => acc + firstCount[id], 0);

  const tie = margin < 5 || share < 0.5;
  const neutral = rain === 0 && temp === 0;
  // Primera en lo normal, entre las mismas que compiten.
  const oldTop = [...order].sort((a, b) => (normalTotals[b] ?? 0) - (normalTotals[a] ?? 0))[0]!;
  // Qué criterio cambió más la distancia entre A y B frente a lo normal.
  const movedBetween = (a: StrategyId, b: StrategyId) =>
    heaviest(objective, (c) => minus(minus(scores[a][c], scores[b][c]), minus(normal[a][c], normal[b][c])));
  const movedBy = neutral ? null : first !== oldTop ? movedBetween(first, oldTop) : tie ? movedBetween(first, second) : null;

  return {
    ...shared,
    firstCount,
    marginMedian: Math.round(margin),
    driver: heaviest(objective, (c) => minus(scores[first][c], scores[second][c])),
    separatingData: tie ? (first === 'E2' || second === 'E2' ? 'localPrice' : 'soilDepth') : undefined,
    movedBy,
  };
}

/** Robustez de la primera frente a la segunda (umbrales del PRD v0.9). */
export function firstShare(r: ScenarioResult): number {
  const first = r.order[0];
  return first ? r.firstCount[first] / r.runs : 0;
}
