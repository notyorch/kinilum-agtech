/*
 * Restricciones: filtros, no pesos. «Restricciones = WHERE, objetivo = pesos
 * del ORDER BY» (PRD v0.9).
 *
 * Una estrategia que no cumple una restricción NO se oculta: aparece como
 * «no compatible con lo que nos dijo», con su razón, al final de la lista.
 *
 * REGLAS DE EJEMPLO, todas a validar con el técnico. Son el espejo de la
 * sección `reglas` de pipeline/rules/crops.v1.yaml; la prueba
 * app/tests/data.test.mjs falla si dejan de coincidir.
 */
import { STRATEGIES, type StrategyId } from './comparison.ts';
import { cropOf, type BeanVariant, type CropId, type EvidenceState } from './crops.ts';

export type Machinery = 'manual' | 'hired';
export type Soil = 'tsekel' | 'kankab' | 'undeclared';

/** Lo que declaran el técnico (en la parcela) y el agricultor (en su celular). */
export interface Declaration {
  soil: Soil;
  extremeHeat: boolean;
  machinery: Machinery;
  /** Además del maíz, qué cultivos de rotación acepta sembrar. */
  accepted: CropId[];
  /** Para qué cultivos tiene dónde vender. */
  market: CropId[];
  /** Variante del frijol regional que se simula en E2, y quién la eligió. */
  beanVariant: BeanVariant;
  beanVariantChosenBy: 'technician' | 'team';
}

/**
 * Espejo de `restrictions` y `rotation` del paquete publicado (public/packages), que arma
 * pipeline/package/build.py desde pipeline/parcels/yuc-demo-001.yaml. Caso ilustrativo.
 */
export const PARCEL: Declaration = {
  soil: 'tsekel',
  extremeHeat: true,
  machinery: 'hired',
  accepted: ['frijol', 'garbanzo', 'sorgo', 'trigo'],
  market: ['frijol', 'sorgo'],
  beanVariant: 'xpelon',
  beanVariantChosenBy: 'team',
};

export type RuleId = 'notAccepted' | 'noMarket' | 'noMachinery' | 'heatThinSoil';

export interface Rule {
  id: RuleId;
  /** `id` de la regla en el catálogo. */
  catalogId: string;
  crops: readonly CropId[];
  /** `exclude` saca la estrategia del orden; `lowViability` solo la marca. */
  effect: 'exclude' | 'lowViability';
  evidence: EvidenceState;
}

export const RULES: readonly Rule[] = [
  { id: 'notAccepted', catalogId: 'no_aceptado', crops: ['frijol', 'garbanzo', 'sorgo', 'trigo'], effect: 'exclude', evidence: 'a_validar' },
  { id: 'noMarket', catalogId: 'sin_venta', crops: ['frijol', 'garbanzo', 'sorgo', 'trigo'], effect: 'exclude', evidence: 'a_validar' },
  { id: 'noMachinery', catalogId: 'sin_maquinaria', crops: ['sorgo', 'trigo'], effect: 'exclude', evidence: 'a_validar' },
  { id: 'heatThinSoil', catalogId: 'calor_extremo_suelo_delgado', crops: ['garbanzo', 'trigo'], effect: 'lowViability', evidence: 'a_validar' },
];

/** Cuándo se dispara cada regla. Ninguna depende del objetivo (eso es un peso, no un filtro). */
const BROKEN: Record<RuleId, (crop: CropId, d: Declaration) => boolean> = {
  notAccepted: (crop, d) => !d.accepted.includes(crop),
  noMarket: (crop, d) => !d.market.includes(crop),
  noMachinery: (_crop, d) => d.machinery === 'manual',
  heatThinSoil: (_crop, d) => d.extremeHeat && d.soil === 'tsekel',
};

export interface Reason {
  rule: RuleId;
  crop: CropId;
}

function broken(id: StrategyId, d: Declaration, effect: Rule['effect']): Reason[] {
  const crop = cropOf(id);
  if (!crop) return [];
  return RULES.filter((r) => r.effect === effect && r.crops.includes(crop) && BROKEN[r.id](crop, d)).map((r) => ({
    rule: r.id,
    crop,
  }));
}

/** Por qué una estrategia no es compatible con lo declarado. Vacío = compite. */
export function reasonsFor(id: StrategyId, d: Declaration): Reason[] {
  return broken(id, d, 'exclude');
}

/** Avisos «poco viable»: la estrategia sigue compitiendo, con la razón a la vista. */
export function flagsFor(id: StrategyId, d: Declaration): Reason[] {
  return broken(id, d, 'lowViability');
}

export function excludedSet(d: Declaration): Set<StrategyId> {
  return new Set(STRATEGIES.filter((id) => reasonsFor(id, d).length > 0));
}
