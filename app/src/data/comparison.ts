/*
 * Lo que las pantallas necesitan del motor de decisión: estrategias,
 * criterios, objetivos y robustez. Aquí no hay cálculo: no es el motor.
 *
 * Los imports de src/data llevan la extensión .ts para que las pruebas
 * (app/tests) puedan cargar estos módulos con Node, sin compilar.
 */

/** E0 actual · E1 cobertura · E2 frijol regional · E3 sorgo · E4 garbanzo · E5 trigo. */
export const STRATEGIES = ['E0', 'E1', 'E2', 'E3', 'E4', 'E5'] as const;
export type StrategyId = (typeof STRATEGIES)[number];

/** Los cinco criterios que puntúa el simulador (0–100). */
export const CRITERIA = ['water', 'soil', 'erosion', 'climate', 'income'] as const;
export type Criterion = (typeof CRITERIA)[number];

export const OBJECTIVES = ['water', 'soil', 'income', 'risk', 'balanced'] as const;
export type Objective = (typeof OBJECTIVES)[number];

/** Pesos iniciales del PRD v0.9 (a calibrar con técnicos). Cada fila suma 1. */
export const OBJECTIVE_WEIGHTS: Record<Objective, Record<Criterion, number>> = {
  water: { water: 0.45, soil: 0.1, erosion: 0.1, climate: 0.25, income: 0.1 },
  soil: { water: 0.1, soil: 0.45, erosion: 0.25, climate: 0.1, income: 0.1 },
  income: { water: 0.1, soil: 0.1, erosion: 0.05, climate: 0.2, income: 0.55 },
  risk: { water: 0.25, soil: 0.1, erosion: 0.1, climate: 0.45, income: 0.1 },
  balanced: { water: 0.2, soil: 0.2, erosion: 0.2, climate: 0.2, income: 0.2 },
};

export type Robustness = 'high' | 'medium' | 'indistinguishable';

/** Umbrales iniciales del PRD v0.9 (a calibrar). */
export function robustnessOf(firstShare: number, marginMedian: number): Robustness {
  if (firstShare < 0.5 || marginMedian < 5) return 'indistinguishable';
  if (firstShare >= 0.7 && marginMedian >= 10) return 'high';
  return 'medium';
}

/** "9 de cada 10": redondeo a décimos, como pide el PRD. */
export function outOfTen(count: number, runs: number): number {
  // Nunca «10 de cada 10»: la simulación repite pocos años reales y decir 10 sonaría a certeza.
  return Math.min(9, Math.round((count / runs) * 10));
}

/** Certeza de lo que dice cada tarjeta (componente Confidence), no robustez. Ejemplo. */
export const exampleCertainty: Record<StrategyId, 'high' | 'medium' | 'low'> = {
  E0: 'high',
  E1: 'medium',
  E2: 'low',
  E3: 'medium',
  E4: 'low',
  E5: 'low',
};
