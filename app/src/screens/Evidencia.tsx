import { Badge, SourceTag } from '../ds/components';
import { STRATEGIES, type StrategyId } from '../data/comparison';
import { RULES } from '../data/restrictions';
import { t } from '../i18n/es';
import { s, strategyText } from '../i18n/strategies';
import { useAppState } from '../shell/state';
import { Card, DashedNote, ScreenHead } from './parts';

const COLS = 25;
const CELL = 12; // 10 px de celda + 2 px de separación: la grilla de la marca

/** Un cuadro por temporada simulada: lleno de verde las que la dejan primera. */
function RunsGrid({ yes, runs }: { yes: number; runs: number }) {
  const rows = Math.ceil(runs / COLS);
  return (
    <svg className="kn-runsgrid" viewBox={`0 0 ${COLS * CELL - 2} ${rows * CELL - 2}`} aria-hidden="true">
      {Array.from({ length: runs }, (_, i) => (
        <rect
          key={i}
          x={(i % COLS) * CELL}
          y={Math.floor(i / COLS) * CELL}
          width={CELL - 2}
          height={CELL - 2}
          rx={2}
          className={i < yes ? 'is-yes' : 'is-no'}
        />
      ))}
    </svg>
  );
}

export function Evidencia() {
  const e = t.evidencia;
  const { objective, selected, declaration, resultAt } = useAppState();
  const r = resultAt(0, 0);

  const name = (id: StrategyId) => strategyText(id, declaration.beanVariant).short;
  const competes = r.order.includes(selected);
  const yes = r.firstCount[selected];
  const others = STRATEGIES.filter((id) => id !== selected && r.firstCount[id] > 0).sort(
    (a, b) => r.firstCount[b] - r.firstCount[a],
  );
  const variant = s.variants[declaration.beanVariant];

  return (
    <div className="kn-screen">
      <ScreenHead title={e.title} intro={e.intro} />

      <Card label={e.kicker(name(selected), t.objectives[objective].lower)}>
        {competes ? (
          <>
            <p className="kn-runs-figure">
              <span className="kn-runs-figure__yes">{yes}</span> {e.outOf} {r.runs}
            </p>
            <p className="kn-card__text">{e.runsText}</p>
            <RunsGrid yes={yes} runs={r.runs} />
            <div className="kn-runs-legend">
              <span>
                <i className="is-yes" /> {e.yes} · {yes}
              </span>
              <span>
                <i className="is-no" /> {e.no} · {r.runs - yes}
              </span>
            </div>
          </>
        ) : (
          <p className="kn-card__text">{e.notCompeting}</p>
        )}
      </Card>

      <Card title={e.othersTitle}>
        {others.length ? (
          <ul className="kn-rows">
            {others.map((id) => (
              <li key={id}>
                <span>{name(id)}</span>
                <span className="kn-rows__n">{r.firstCount[id]}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="kn-card__text">{e.othersNone}</p>
        )}
      </Card>

      <Card label={e.variantTitle} title={variant.label} aside={<Badge tone="unknown">{e.toValidate}</Badge>}>
        <p className="kn-card__text">
          {variant.label}, {variant.what}. {s.variantChosenBy[declaration.beanVariantChosenBy]}
        </p>
        <p className="kn-card__text">{e.variantOthers}</p>
      </Card>

      <Card title={e.rulesTitle}>
        <p className="kn-card__text">{e.rulesIntro}</p>
        <ul className="kn-rules">
          {RULES.map((rule) => (
            <li key={rule.id}>
              <span>{s.rules[rule.id]}</span>
              {rule.evidence === 'a_validar' && <Badge tone="unknown">{e.toValidate}</Badge>}
            </li>
          ))}
          <li>
            <span>{s.rules.nitrogen}</span>
            <Badge tone="unknown">{e.toValidate}</Badge>
          </li>
        </ul>
      </Card>

      <Card title={e.methodTitle}>
        <p className="kn-card__text">{e.method}</p>
        <div className="kn-tags">
          <SourceTag source="NASA POWER" resolution="~50 km" estimated estimatedLabel={t.estimated} />
          <SourceTag source="GPM IMERG" resolution="11 km" />
          <SourceTag source="HLS" resolution="30 m" />
        </div>
      </Card>

      <DashedNote title={e.noteTitle}>{e.note}</DashedNote>
      <p className="kn-hint">{t.app.closing}</p>
    </div>
  );
}
