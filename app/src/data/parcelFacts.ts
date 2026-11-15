/*
 * Lo que «Mi parcela» muestra, sacado del paquete guardado (los datos que leyó el pipeline), no de un texto escrito
 * a mano. Funciones puras: las prueba tests/facts.test.mjs con Node.
 *
 * Una fuente sin valor (`value: null`) sale «sin dato»: nunca se rellena con un número.
 */
import type { ContractValue, ParcelPackage } from './schema.gen.ts';

export interface Range {
  value: number;
  low: number;
  high: number;
}

/** El valor y su rango p10–p90, o `null` si el paquete no trae dato. */
export function rangeOf(v: ContractValue | undefined): Range | null {
  if (!v || v.value === null || v.p10 === null || v.p90 === null) return null;
  return { value: v.value, low: v.p10, high: v.p90 };
}

/** Meses a partir de días, al medio mes más cercano («3 y medio»). */
export function monthsFromDays(days: number): number {
  return Math.round(days / 15.2) / 2;
}

/** Un número redondeado a la decena, para decir «unos 950» y no «948.08». */
export function roundTo(n: number, step: number): number {
  return Math.round(n / step) * step;
}

export interface ParcelFacts {
  areaHa: number | null;
  /** Meses al año sin plantas verdes: un MÍNIMO (los meses con nubes no se cuentan). */
  bareMonths: Range | null;
  rainMm: Range | null;
  /** Profundidad de raíz en cm; `null` cuando nadie la ha medido. */
  rootDepthCm: Range | null;
}

export function factsFrom(pkg: ParcelPackage | null): ParcelFacts {
  if (!pkg) return { areaHa: null, bareMonths: null, rainMm: null, rootDepthCm: null };
  const bare = rangeOf(pkg.values.bare);
  return {
    areaHa: pkg.area_ha,
    bareMonths: bare && { value: monthsFromDays(bare.value), low: monthsFromDays(bare.low), high: monthsFromDays(bare.high) },
    rainMm: rangeOf(pkg.values.rain),
    rootDepthCm: rangeOf(pkg.values.soil),
  };
}
