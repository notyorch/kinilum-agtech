/*
 * Componentes del sistema de diseño kinilum, portados 1:1 de
 * project/components/bundle.js (artifact "kinilum") a TSX tipado.
 * Estilos: ./components.css (copia de bundle.css). No cambies el aspecto
 * aquí: cambia el sistema de diseño y vuelve a copiar.
 *
 * Única diferencia con el bundle: los textos por defecto ("estimado",
 * "Confianza alta", etiquetas de StrategyCard) también se pueden pasar
 * por props, para que salgan de los archivos de idioma.
 */
import { Fragment, type ButtonHTMLAttributes, type ReactNode } from 'react';

const cx = (...c: Array<string | false | null | undefined>) => c.filter(Boolean).join(' ');

type GlyphKind = 'positive' | 'risk' | 'info' | 'unknown' | 'note';

/** Glifos geométricos de 1.5px: el estado nunca depende solo del color. */
export function Glyph({ kind, size = 12 }: { kind: GlyphKind; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 12 12',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.5,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    className: 'kn-glyph',
  };
  switch (kind) {
    case 'positive':
      return <svg {...common}><path d="M2.5 6.2 5 8.5 9.5 3.5" /></svg>;
    case 'risk':
      return <svg {...common}><path d="M6 1.8 10.6 10H1.4Z" /><path d="M6 5v2" /><path d="M6 8.6v.01" /></svg>;
    case 'info':
      return <svg {...common}><circle cx={6} cy={6} r={4.5} /><path d="M6 5.5v3" /><path d="M6 3.6v.01" /></svg>;
    case 'unknown':
      return <svg {...common}><circle cx={6} cy={6} r={4.5} strokeDasharray="2 2" /></svg>;
    case 'note':
      return <svg {...common}><rect x={1.5} y={1.5} width={9} height={9} rx={2} /><path d="M4 4.5h4M4 7h2.5" /></svg>;
  }
}

/* Button ------------------------------------------------------------------ */

/** Acción. `primary` (ink sólido) una vez por vista; `secondary` por defecto; `ghost` para acciones terciarias. */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'md' | 'sm';
}
export function Button({ variant = 'secondary', size = 'md', className, children, ...rest }: ButtonProps) {
  return (
    <button type="button" {...rest} className={cx('kn-btn', `kn-btn-${variant}`, `kn-btn-${size}`, className)}>
      {children}
    </button>
  );
}

/* Badge ------------------------------------------------------------------- */

export type BadgeTone = 'neutral' | 'positive' | 'risk' | 'info' | 'unknown';
const BADGE_GLYPH: Partial<Record<BadgeTone, GlyphKind>> = { positive: 'positive', risk: 'risk', info: 'info', unknown: 'unknown' };

/** Estado en una o dos palabras. Cada tono trae su ícono: el color nunca va solo. */
export interface BadgeProps {
  tone?: BadgeTone;
  /** Relleno sólido; solo para `positive` o `risk` de severidad alta. */
  strong?: boolean;
  /** `false` quita el ícono (solo en `neutral` tiene sentido). */
  icon?: boolean;
  children?: ReactNode;
  className?: string;
}
export function Badge({ tone = 'neutral', strong, icon, children, className }: BadgeProps) {
  const g = icon === false ? undefined : BADGE_GLYPH[tone];
  return (
    <span className={cx('kn-badge', `kn-badge-${tone}`, strong && 'kn-badge-strong', className)}>
      {g ? <Glyph kind={g} /> : null}
      {children}
    </span>
  );
}

/* SourceTag --------------------------------------------------------------- */

/** De dónde sale un dato: fuente + resolución. Borde punteado si el valor es estimado. */
export interface SourceTagProps {
  /** Nombre corto de la fuente: "SMAP", "GPM IMERG", "Muestreo de suelo". */
  source: string;
  /** Resolución o fecha: "9 km", "30 m", "2025-08". */
  resolution?: string;
  /** El valor es modelado o interpolado, no medido. */
  estimated?: boolean;
  /** Texto del segmento punteado; por defecto "estimado". */
  estimatedLabel?: string;
  title?: string;
  className?: string;
}
export function SourceTag({ source, resolution, estimated, estimatedLabel = 'estimado', title, className }: SourceTagProps) {
  return (
    <span className={cx('kn-src', estimated && 'kn-src-est', className)} title={title}>
      <span className="kn-src-name">{source}</span>
      {resolution ? <span className="kn-src-res">{resolution}</span> : null}
      {estimated ? <span className="kn-src-res">{estimatedLabel}</span> : null}
    </span>
  );
}

/* Confidence -------------------------------------------------------------- */

export type ConfidenceLevel = 'high' | 'medium' | 'low';
const LEVELS: Record<ConfidenceLevel, number> = { high: 3, medium: 2, low: 1 };
const LEVEL_ES: Record<ConfidenceLevel, string> = { high: 'alta', medium: 'media', low: 'baja' };

/** Qué tan respaldada está una afirmación. Tres barras; las vacías son punteadas. */
export interface ConfidenceProps {
  level?: ConfidenceLevel;
  /** Texto visible; por defecto "Confianza alta|media|baja". `""` muestra solo las barras. */
  label?: string;
  className?: string;
}
export function Confidence({ level = 'medium', label, className }: ConfidenceProps) {
  const n = LEVELS[level];
  const text = label ?? `Confianza ${LEVEL_ES[level]}`;
  return (
    <span className={cx('kn-conf', `kn-conf-${level}`, className)} role="img" aria-label={text}>
      <span className="kn-conf-bars" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} className={cx('kn-conf-bar', i <= n ? 'is-on' : 'is-off')} />
        ))}
      </span>
      {text ? <span className="kn-conf-label" aria-hidden="true">{text}</span> : null}
    </span>
  );
}

/* Callout ----------------------------------------------------------------- */

/** Nota en contexto: humildad, método o riesgo. */
export interface CalloutProps {
  tone?: 'note' | 'info' | 'risk';
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}
export function Callout({ tone = 'note', title, children, className }: CalloutProps) {
  return (
    <div className={cx('kn-callout', `kn-callout-${tone}`, className)} role={tone === 'risk' ? 'alert' : 'note'}>
      <span className="kn-callout-icon">
        <Glyph kind={tone === 'risk' ? 'risk' : tone === 'info' ? 'info' : 'note'} size={16} />
      </span>
      <div className="kn-callout-body">
        {title ? <div className="kn-callout-title">{title}</div> : null}
        {children ? <div className="kn-callout-text">{children}</div> : null}
      </div>
    </div>
  );
}

/* StrategyCard ------------------------------------------------------------ */

export interface Evidence {
  source: string;
  resolution?: string;
  estimated?: boolean;
  detail: ReactNode;
}
type StrategyLabelKey = 'why' | 'evidence' | 'benefits' | 'missing' | 'risks' | 'current';
const STRATEGY_LABELS: Record<StrategyLabelKey, string> = {
  why: 'Por qué se sugiere',
  evidence: 'Evidencia',
  benefits: 'Beneficios',
  missing: 'Qué no sabemos',
  risks: 'Revisar con un experto local',
  current: 'Actual',
};

/** Una estrategia de rotación con sus cinco respuestas obligatorias. */
export interface StrategyCardProps {
  name: ReactNode;
  summary?: ReactNode;
  kicker?: ReactNode;
  /** Marca la rotación que el agricultor usa hoy. */
  current?: boolean;
  selected?: boolean;
  confidence?: ConfidenceLevel;
  /** Texto de Confidence (para otro idioma). */
  confidenceLabel?: string;
  why?: ReactNode;
  evidence?: Evidence[];
  benefits?: ReactNode[];
  missing?: ReactNode[];
  risks?: ReactNode[];
  footer?: ReactNode;
  /** Sobrescribe las etiquetas de fila (para otro idioma). */
  labels?: Partial<Record<StrategyLabelKey, string>>;
  /** Texto "estimado" de los SourceTag de evidencia. */
  estimatedLabel?: string;
  className?: string;
}

function Section<T>(label: string, kind: string, items: T[] | undefined, render: (item: T) => ReactNode) {
  if (!items || !items.length) return null;
  return (
    <div className={`kn-sc-row kn-sc-${kind}`}>
      <div className="kn-sc-label">{label}</div>
      <ul className="kn-sc-list">
        {items.map((it, i) => (
          <li key={i}>{render(it)}</li>
        ))}
      </ul>
    </div>
  );
}

export function StrategyCard(p: StrategyCardProps) {
  const labels = { ...STRATEGY_LABELS, ...p.labels };
  return (
    <article className={cx('kn-sc', p.selected && 'is-selected', p.className)}>
      <header className="kn-sc-head">
        <div className="kn-sc-titles">
          <div className="kn-sc-kicker">
            {p.current ? <Badge tone="neutral">{labels.current}</Badge> : null}
            {p.kicker ? <span>{p.kicker}</span> : null}
          </div>
          <h3 className="kn-sc-name">{p.name}</h3>
          {p.summary ? <p className="kn-sc-summary">{p.summary}</p> : null}
        </div>
        {p.confidence ? <Confidence level={p.confidence} label={p.confidenceLabel} /> : null}
      </header>
      <div className="kn-sc-rows">
        {p.why ? (
          <div className="kn-sc-row kn-sc-why">
            <div className="kn-sc-label">{labels.why}</div>
            <p className="kn-sc-text">{p.why}</p>
          </div>
        ) : null}
        {Section(labels.evidence, 'evidence', p.evidence, (e) => (
          <Fragment>
            <SourceTag source={e.source} resolution={e.resolution} estimated={e.estimated} estimatedLabel={p.estimatedLabel} />
            <span className="kn-sc-ev">{e.detail}</span>
          </Fragment>
        ))}
        {Section(labels.benefits, 'benefits', p.benefits, (b) => (
          <Fragment><Glyph kind="positive" /><span>{b}</span></Fragment>
        ))}
        {Section(labels.missing, 'missing', p.missing, (m) => (
          <Fragment><Glyph kind="unknown" /><span>{m}</span></Fragment>
        ))}
        {Section(labels.risks, 'risks', p.risks, (r) => (
          <Fragment><Glyph kind="risk" /><span>{r}</span></Fragment>
        ))}
      </div>
      {p.footer ? <footer className="kn-sc-foot">{p.footer}</footer> : null}
    </article>
  );
}
