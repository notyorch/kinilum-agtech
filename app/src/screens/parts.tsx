// Piezas comunes de las pantallas. Lo que el sistema de diseño ya trae
// (Badge, SourceTag, Confidence, Callout, StrategyCard) sale de ../ds.
import type { ReactNode } from 'react';
import { Glyph, SourceTag } from '../ds/components';
import { t } from '../i18n/es';
import './screens.css';

export function ScreenHead({ title, intro }: { title: string; intro?: string }) {
  return (
    <div className="kn-head">
      <h1 className="kn-head__title">{title}</h1>
      {intro && <p className="kn-head__intro">{intro}</p>}
    </div>
  );
}

export function Card({
  label,
  title,
  aside,
  selected,
  children,
}: {
  /** Texto chico arriba (qué mide la tarjeta). */
  label?: ReactNode;
  title?: ReactNode;
  aside?: ReactNode;
  selected?: boolean;
  children?: ReactNode;
}) {
  return (
    <section className="kn-card" data-selected={selected || undefined}>
      {(label || title || aside) && (
        <div className="kn-card__top">
          <div className="kn-card__titles">
            {label && <p className="kn-card__label">{label}</p>}
            {title && <h2 className="kn-card__title">{title}</h2>}
          </div>
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

/** Una medición: cifra grande en Geist Mono con su unidad. */
export function Metric({ value, unit }: { value: string; unit?: string }) {
  return (
    <p className="kn-metric">
      {value}
      {unit && <span className="kn-metric__unit">{unit}</span>}
    </p>
  );
}

/** Fuente, resolución y a qué escala corresponde el dato (parcela, zona, entorno). */
export function DataSource({
  source,
  resolution,
  estimated,
  scale,
}: {
  source: string;
  resolution: string;
  estimated?: boolean;
  scale: keyof typeof t.scale;
}) {
  return (
    <div className="kn-datasrc">
      <SourceTag source={source} resolution={resolution} estimated={estimated} estimatedLabel={t.estimated} />
      <span>{t.scale[scale]}</span>
    </div>
  );
}

/**
 * Lo supuesto o lo que falta va punteado (medido = sólido, supuesto = punteado),
 * con su ícono para que el borde no cargue el significado solo.
 */
export function DashedNote({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="kn-dashed" role="note">
      <span className="kn-dashed__icon">
        <Glyph kind="unknown" size={16} />
      </span>
      <p className="kn-dashed__text">
        <strong>{title}</strong> {children}
      </p>
    </div>
  );
}

/**
 * Barra horizontal 0–1. Más larga es mejor. `null` = sin dato: diagonales y
 * la palabra, nunca una barra vacía que parezca un cero.
 * `compact` pone la etiqueta a la izquierda, para listas largas.
 */
export function Bar({
  label,
  value,
  tone = 'ink',
  emphasis,
  valueText,
  compact,
}: {
  label: string;
  value: number | null;
  tone?: 'ink' | 'brand';
  /** El criterio que más pesa en lo que eligió el agricultor: etiqueta resaltada. */
  emphasis?: boolean;
  /** Texto del valor; visible salvo en `compact`, donde solo lo lee el lector de pantalla. */
  valueText: string;
  compact?: boolean;
}) {
  const text = value === null ? t.noData : valueText;
  return (
    <span className="kn-bar" data-emphasis={emphasis || undefined} data-compact={compact || undefined}>
      <span className="kn-bar__head">
        <span className="kn-bar__label">{label}</span>
        {(!compact || value === null) && <span className="kn-bar__value">{text}</span>}
      </span>
      <span className="kn-bar__track" data-nodata={value === null || undefined} role="img" aria-label={`${label}: ${text}`}>
        {value !== null && (
          <span className={`kn-bar__fill kn-bar__fill--${tone}`} style={{ width: `${Math.round(value * 100)}%` }} />
        )}
      </span>
    </span>
  );
}
