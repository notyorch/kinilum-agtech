/*
 * Espejo de pipeline/rules/crops.v2.yaml: los cuatro cultivos de rotación y
 * las variantes del frijol regional. La fuente de verdad es el catálogo; la
 * prueba app/tests/data.test.mjs falla si este archivo deja de coincidir.
 *
 * `null` = por definir con el técnico. Nunca se rellena con un valor inventado.
 */
import type { StrategyId } from './comparison.ts';

export const RULES_VERSION = 'crops.v2';

export const CROP_IDS = ['frijol', 'garbanzo', 'sorgo', 'trigo'] as const;
export type CropId = (typeof CROP_IDS)[number];

export type EvidenceState = 'a_validar' | 'validado';

export interface CropProfile {
  tipo: 'leguminosa' | 'cereal';
  estrategia: StrategyId;
  fijaNitrogeno: boolean;
  exigeMaquinaria: boolean | null;
  requiereVenta: boolean | null;
  cicloDias: number | null;
  estadoEvidencia: EvidenceState;
}

export const CROPS: Record<CropId, CropProfile> = {
  frijol: { tipo: 'leguminosa', estrategia: 'E2', fijaNitrogeno: true, exigeMaquinaria: false, requiereVenta: true, cicloDias: null, estadoEvidencia: 'a_validar' },
  garbanzo: { tipo: 'leguminosa', estrategia: 'E4', fijaNitrogeno: true, exigeMaquinaria: null, requiereVenta: null, cicloDias: null, estadoEvidencia: 'a_validar' },
  sorgo: { tipo: 'cereal', estrategia: 'E3', fijaNitrogeno: false, exigeMaquinaria: true, requiereVenta: true, cicloDias: null, estadoEvidencia: 'a_validar' },
  trigo: { tipo: 'cereal', estrategia: 'E5', fijaNitrogeno: false, exigeMaquinaria: null, requiereVenta: null, cicloDias: null, estadoEvidencia: 'a_validar' },
};

/** Variantes del frijol (E2). Hoy solo frijol negro; las demás se agregan con el técnico. La elige el técnico en la configuración de la parcela. */
export const BEAN_VARIANTS = ['negro'] as const;
export type BeanVariant = (typeof BEAN_VARIANTS)[number];
export const DEFAULT_BEAN_VARIANT: BeanVariant = 'negro';

/** Qué trae cada estrategia además del maíz. E1 es una leguminosa de cobertura, fuera del catálogo. */
export const ROTATION: Record<StrategyId, CropId | 'cover' | null> = {
  E0: null,
  E1: 'cover',
  E2: 'frijol',
  E3: 'sorgo',
  E4: 'garbanzo',
  E5: 'trigo',
};

/** El cultivo del catálogo que trae la estrategia, si trae uno. */
export function cropOf(id: StrategyId): CropId | null {
  const c = ROTATION[id];
  return c === null || c === 'cover' ? null : c;
}

/** Solo las leguminosas suman nitrógeno: cobertura, frijol y garbanzo. Sorgo y trigo, no. */
export function fixesNitrogen(id: StrategyId): boolean {
  const c = ROTATION[id];
  if (c === null) return false;
  return c === 'cover' ? true : CROPS[c].fijaNitrogeno;
}
