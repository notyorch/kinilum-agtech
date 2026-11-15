import { t } from '../i18n/es';
import { Card, ScreenHead, Skeleton, UnknownBadge } from './parts';

// Grilla de ejemplo, fija: opacidad del verde por celda; null = sin dato.
const CELLS: (number | null)[] = [
  0.3, 0.45, 0.6, 0.55, 0.4, null, null, 0.2,
  0.4, 0.7, 0.85, 0.8, 0.6, 0.35, null, 0.25,
  0.5, 0.8, 1, 0.95, 0.75, 0.5, 0.3, 0.3,
  0.45, 0.75, 0.9, 0.85, 0.7, 0.45, 0.35, 0.4,
  0.3, 0.55, 0.65, 0.6, 0.5, null, 0.45, 0.5,
  0.2, 0.35, 0.45, null, null, null, 0.55, 0.6,
];

export function MiParcela() {
  const p = t.parcela;
  return (
    <div className="kn-screen">
      <ScreenHead
        title={p.title}
        intro={p.intro}
        kicker={<span className="kn-badge kn-badge--info">{t.app.illustrative}</span>}
      />
      <Card title="yuc-demo-001">
        <div className="kn-grid" aria-hidden="true">
          {CELLS.map((o, i) =>
            o === null ? (
              <span key={i} className="kn-grid__cell kn-grid__cell--empty" />
            ) : (
              <span key={i} className="kn-grid__cell" style={{ opacity: o }} />
            ),
          )}
        </div>
        <div className="kn-legend">
          <span>
            <i className="kn-legend__swatch" /> {p.measured}
          </span>
          <span>
            <i className="kn-legend__swatch kn-legend__swatch--empty" /> {p.noData}
          </span>
        </div>
        <p className="kn-card__text">{p.gridCaption}</p>
      </Card>
      {p.cards.map((c) => (
        <Card key={c.title} title={c.title} aside={<UnknownBadge>{t.app.pending}</UnknownBadge>}>
          <p className="kn-card__text">{c.text}</p>
          <Skeleton />
        </Card>
      ))}
    </div>
  );
}
