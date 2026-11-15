/*
 * «Con menos agua de riego»: qué parte de lo que pide cada estrategia alcanzaría a cubrir si las presas dan menos agua.
 *
 * Sale de `water_mm` de cada celda del paquete (lo que el simulador calculó que pide cada estrategia, en mm por ciclo).
 * El agua disponible se mide frente a lo que hoy pide el maíz solo en clima normal: 100 % es esa agua; 60 % es el 60 %.
 * Es cuánta agua PIDE cada opción, no cuánto rendiría con menos agua: el rendimiento con recorte todavía no se calcula.
 */
import { STRATEGIES, type StrategyId } from './comparison.ts';
import type { Simulation } from './schema.gen.ts';

export const SUPPLY_STEPS = [100, 90, 80, 70, 60, 50, 40] as const;

/** Parte de lo que pide la estrategia que el agua disponible cubre, de 0 a 1: en un año muy seco, en uno típico y en uno húmedo. */
export interface Coverage {
  low: number;
  mid: number;
  high: number;
}

const cellAt = (sim: Simulation, rain: number, temp: number) => sim.cells.find((c) => c.rain === rain && c.temp === temp);

/** Mm por ciclo que hoy pide el maíz solo (mediana, clima normal): la vara de «100 % del agua». */
export function referenceMm(sim: Simulation): number | null {
  return cellAt(sim, 0, 0)?.water_mm?.E0?.[1] ?? null;
}

export function coverageAt(sim: Simulation, rain: number, temp: number, supplyPct: number): Record<StrategyId, Coverage | null> {
  const ref = referenceMm(sim);
  const water = cellAt(sim, rain, temp)?.water_mm;
  const available = ref === null ? 0 : (ref * supplyPct) / 100;
  const share = (need: number) => (need <= 0 ? 1 : Math.min(1, available / need));
  return Object.fromEntries(
    STRATEGIES.map((id) => {
      const need = water?.[id];
      const [p10, p50, p90] = need ?? [];
      return [id, ref === null || p10 === undefined || p50 === undefined || p90 === undefined ? null : { low: share(p90), mid: share(p50), high: share(p10) }];
    }),
  ) as Record<StrategyId, Coverage | null>;
}
