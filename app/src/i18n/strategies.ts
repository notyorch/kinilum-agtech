// Textos de las estrategias, las variantes de frijol y las reglas de cultivo.
// Viven en strategies.es.json y strategies.en.json, con las mismas claves.
// La app todavía no tiene selector de idioma: hoy usa el español.
import type { StrategyId } from '../data/comparison';
import type { BeanVariant, CropId } from '../data/crops';
import type { Reason } from '../data/restrictions';
import es from './strategies.es.json';

export const s = es;

export interface StrategyText {
  name: string;
  short: string;
  summary: string;
  why: string;
  evidence: { source: string; resolution: string; estimated: boolean; detail: string }[];
  benefits: string[];
  missing: string[];
  risks: string[];
}

/** Las cinco respuestas de una estrategia. En E2, con los textos de la variante de frijol elegida. */
export function strategyText(id: StrategyId, variant: BeanVariant): StrategyText {
  const base = s.strategies[id];
  return id === 'E2' ? { ...base, ...s.variants[variant].E2 } : base;
}

const fill = (text: string, crop: CropId) => text.replace('{crop}', s.crops[crop]);

/** La razón de una regla rota, con el nombre del cultivo. */
export function reasonText(r: Reason): string {
  return fill(s.reasons[r.rule], r.crop);
}
