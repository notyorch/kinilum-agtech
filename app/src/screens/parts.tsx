// Piezas comunes de las pantallas del shell. Clases y valores salen de tokens.css.
import type { ReactNode } from 'react';
import './screens.css';

export function ScreenHead({ title, intro, kicker }: { title: string; intro: string; kicker?: ReactNode }) {
  return (
    <div className="kn-head">
      {kicker && <div className="kn-head__kicker">{kicker}</div>}
      <h1 className="kn-head__title">{title}</h1>
      <p className="kn-head__intro">{intro}</p>
    </div>
  );
}

export function Card({ title, children, aside }: { title: string; children?: ReactNode; aside?: ReactNode }) {
  return (
    <section className="kn-card">
      <div className="kn-card__top">
        <h2 className="kn-card__title">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Estado sin dato: borde punteado, porque nada aquí está medido todavía. */
export function UnknownBadge({ children }: { children: ReactNode }) {
  return (
    <span className="kn-badge kn-badge--unknown">
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        <circle cx="6" cy="6" r="4.25" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2" />
      </svg>
      {children}
    </span>
  );
}

export function SourceTag({ name, res }: { name: string; res: string }) {
  return (
    <span className="kn-src">
      <span className="kn-src__name">{name}</span>
      <span className="kn-src__res">{res}</span>
    </span>
  );
}

/** Líneas grises en lugar del contenido que todavía no existe. */
export function Skeleton({ lines = 2 }: { lines?: number }) {
  return (
    <div className="kn-skel" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} style={{ width: `${88 - i * 22}%` }} />
      ))}
    </div>
  );
}
