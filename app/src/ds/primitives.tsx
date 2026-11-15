/*
 * Controles interactivos de kinilum sobre Radix Primitives (sin estilos,
 * accesibles: teclado, ARIA, foco). Radix pone el comportamiento; el aspecto
 * sale solo de los tokens, en ./primitives.css.
 *
 * Regla: las pantallas importan de aquí, nunca de @radix-ui directamente.
 * Así, si algún día cambiamos de librería, solo cambia este archivo.
 */
import * as Collapsible from '@radix-ui/react-collapsible';
import * as RadixSlider from '@radix-ui/react-slider';
import * as ToggleGroup from '@radix-ui/react-toggle-group';
import type { ReactNode } from 'react';
import { Glyph } from './components';

const cx = (...c: Array<string | false | null | undefined>) => c.filter(Boolean).join(' ');

/* SegmentedControl ---------------------------------------------------------- */

export interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  /** Texto para lectores de pantalla si `label` no basta (p. ej. "ES"). */
  ariaLabel?: string;
  lang?: string;
}

/**
 * Elegir una opción entre pocas. Siempre hay una elegida (no se puede
 * desmarcar).
 * - `segmented`: botones unidos, relleno ink en la elegida. Para ajustes cortos (ES | EN).
 * - `chips`: fichas separadas que se acomodan en varias líneas; la elegida en
 *   brand-soft con check, para que el color no cargue el significado solo.
 *   Para decisiones del agricultor (su objetivo).
 */
export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  label,
  variant = 'segmented',
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: SegmentedOption<T>[];
  /** Nombre accesible del grupo. */
  label: string;
  variant?: 'segmented' | 'chips';
  className?: string;
}) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      onValueChange={(v) => {
        if (v) onChange(v as T);
      }}
      aria-label={label}
      className={cx('kn-toggle', `kn-toggle-${variant}`, className)}
    >
      {options.map((o) => (
        <ToggleGroup.Item key={o.value} value={o.value} aria-label={o.ariaLabel} lang={o.lang} className="kn-toggle-item">
          {variant === 'chips' ? (
            <span className="kn-toggle-check" aria-hidden="true">
              <Glyph kind="positive" />
            </span>
          ) : null}
          {o.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}

/* MultiToggle --------------------------------------------------------------- */

/**
 * Elegir varias opciones (o ninguna), con el mismo aspecto de fichas: la
 * elegida en brand-soft con check. Para listas cortas que declara el agricultor.
 */
export function MultiToggle<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T[];
  onChange: (v: T[]) => void;
  options: SegmentedOption<T>[];
  label: string;
  className?: string;
}) {
  return (
    <ToggleGroup.Root
      type="multiple"
      value={value}
      onValueChange={(v) => onChange(v as T[])}
      aria-label={label}
      className={cx('kn-toggle', 'kn-toggle-chips', className)}
    >
      {options.map((o) => (
        <ToggleGroup.Item key={o.value} value={o.value} aria-label={o.ariaLabel} className="kn-toggle-item">
          <span className="kn-toggle-check" aria-hidden="true">
            <Glyph kind="positive" />
          </span>
          {o.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}

/* Disclosure ---------------------------------------------------------------- */

/** Mostrar u ocultar la capa técnica ("Cómo comparamos", detalles de método). */
export function Disclosure({
  summary,
  children,
  defaultOpen = false,
  className,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  return (
    <Collapsible.Root defaultOpen={defaultOpen} className={cx('kn-disclosure', className)}>
      <Collapsible.Trigger className="kn-disclosure-trigger">
        <svg className="kn-disclosure-chevron" width={12} height={12} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4.5 2.5 8 6l-3.5 3.5" />
        </svg>
        <span>{summary}</span>
      </Collapsible.Trigger>
      <Collapsible.Content className="kn-disclosure-content">{children}</Collapsible.Content>
    </Collapsible.Root>
  );
}

/* Slider -------------------------------------------------------------------- */

/**
 * Valor en pasos (lluvia −30 %…+30 %, temperatura −2…+4 °C). `onCommit` se
 * llama al soltar: el cálculo no corre en cada píxel (PRD: sin tirones).
 */
export function Slider({
  value,
  onChange,
  onCommit,
  min,
  max,
  step,
  label,
  valueText,
  className,
}: {
  value: number;
  onChange: (v: number) => void;
  onCommit?: (v: number) => void;
  min: number;
  max: number;
  step: number;
  /** Nombre accesible. */
  label: string;
  /** Texto del valor para lectores de pantalla ("20 % menos lluvia"). */
  valueText?: string;
  className?: string;
}) {
  return (
    <RadixSlider.Root
      className={cx('kn-slider', className)}
      value={[value]}
      min={min}
      max={max}
      step={step}
      onValueChange={([v]) => v !== undefined && onChange(v)}
      onValueCommit={([v]) => v !== undefined && onCommit?.(v)}
    >
      <RadixSlider.Track className="kn-slider-track">
        <RadixSlider.Range className="kn-slider-range" />
      </RadixSlider.Track>
      <RadixSlider.Thumb className="kn-slider-thumb" aria-label={label} aria-valuetext={valueText} />
    </RadixSlider.Root>
  );
}
