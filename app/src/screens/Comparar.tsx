import { Badge, Button, StrategyCard } from '../ds/components';
import { SegmentedControl } from '../ds/primitives';
import {
  CRITERIA,
  OBJECTIVES,
  OBJECTIVE_WEIGHTS,
  exampleCertainty,
  outOfTen,
  robustnessOf,
  type Criterion,
  type StrategyId,
} from '../data/comparison';
import { flagsFor, reasonsFor } from '../data/restrictions';
import { firstShare } from '../data/scenarios';
import { t } from '../i18n/es';
import { reasonText, s, strategyText } from '../i18n/strategies';
import { useAppState } from '../shell/state';
import { useFlip } from '../shell/useFlip';
import { Bar, DashedNote, ScreenHead } from './parts';

export function Comparar() {
  const c = t.comparar;
  const { objective, setObjective, selected, setSelected, declaration, resultAt, go } = useAppState();
  const r = resultAt(0, 0);

  const tie = r.order.length > 1 && robustnessOf(firstShare(r), r.marginMedian) === 'indistinguishable';
  const best = tie ? null : r.order[0];
  // Las que compiten, luego las que no tienen datos y al final las excluidas: ninguna se oculta.
  const ids = [...r.order, ...r.unranked, ...r.excluded];
  const register = useFlip(ids.join());

  // El criterio que más pesa en el objetivo va resaltado; en «Equilibrado» pesan igual.
  const weights = OBJECTIVE_WEIGHTS[objective];
  const top = Math.max(...CRITERIA.map((k) => weights[k]));
  const emphasis = (k: Criterion) => objective !== 'balanced' && weights[k] === top;

  const badgeFor = (id: StrategyId) => {
    if (r.excluded.includes(id)) return <Badge tone="neutral">{c.excluded}</Badge>;
    if (r.unranked.includes(id)) return <Badge tone="unknown">{c.unranked}</Badge>;
    if (tie && r.order.indexOf(id) < 2) return <Badge tone="unknown">{c.tie}</Badge>;
    if (id === best) return <Badge tone="positive">{t.objectives[objective].best}</Badge>;
    return null;
  };

  return (
    <div className="kn-screen">
      <ScreenHead title={c.title} intro={c.intro} />
      <DashedNote title={c.exampleTitle}>{c.exampleNote}</DashedNote>

      <div className="kn-field">
        <p className="kn-field__label">{c.objective}</p>
        <SegmentedControl
          variant="chips"
          label={c.objective}
          value={objective}
          onChange={setObjective}
          options={OBJECTIVES.map((o) => ({ value: o, label: t.objectives[o].chip }))}
        />
      </div>

      {tie && (
        <p className="kn-card__text">
          {c.tieNote} {r.separatingData && c.separating[r.separatingData]}
        </p>
      )}
      <p className="kn-hint">{c.hint}</p>

      <div className="kn-options" role="radiogroup" aria-label={c.title}>
        {ids.map((id) => {
          const text = strategyText(id, declaration.beanVariant);
          const excluded = r.excluded.includes(id);
          const reasons = reasonsFor(id, declaration);
          const flags = flagsFor(id, declaration);
          const level = exampleCertainty[id];
          return (
            <div key={id} ref={register(id)} className="kn-option-wrap">
              <button
                type="button"
                role="radio"
                aria-checked={selected === id}
                className="kn-option"
                data-muted={excluded || undefined}
                onClick={() => setSelected(id)}
              >
                <span className="kn-option__top">
                  <span className="kn-option__name">{text.name}</span>
                  {badgeFor(id)}
                </span>

                {excluded ? (
                  <span className="kn-option__notes">
                    {reasons.map((reason) => (
                      <span key={reason.rule}>{reasonText(reason)}</span>
                    ))}
                  </span>
                ) : (
                  <span className="kn-option__bars">
                    {CRITERIA.map((k) => {
                      const v = r.scores[id][k];
                      return (
                        <Bar
                          key={k}
                          compact
                          label={t.criteria[k]}
                          value={v === null ? null : v / 100}
                          tone={id === best ? 'brand' : 'ink'}
                          emphasis={emphasis(k)}
                          valueText={c.barValue(Math.round((v ?? 0) / 10))}
                        />
                      );
                    })}
                  </span>
                )}

                {id === best && <span className="kn-option__note">{c.firstIn(outOfTen(r.firstCount[id], r.runs))}</span>}
                {r.unranked.includes(id) && (
                  <span className="kn-option__note">{c.unrankedNote(t.objectives[objective].lower)}</span>
                )}
                {flags.map((flag) => (
                  <span key={flag.rule} className="kn-option__flag">
                    <Badge tone="risk">{c.lowViability}</Badge>
                    <span>{reasonText(flag)}</span>
                  </span>
                ))}
              </button>

              {selected === id && (
                <StrategyCard
                  name={text.name}
                  summary={text.summary}
                  current={id === 'E0'}
                  selected
                  confidence={level}
                  confidenceLabel={t.confidence[level]}
                  why={text.why}
                  evidence={text.evidence}
                  benefits={text.benefits}
                  missing={text.missing}
                  risks={text.risks}
                  footer={t.app.closing}
                  labels={s.labels}
                  estimatedLabel={t.estimated}
                />
              )}
            </div>
          );
        })}
      </div>

      {r.excluded.length > 0 && <p className="kn-hint">{c.excludedNote(r.excluded.length)}</p>}

      <Button variant="secondary" className="kn-cta" onClick={() => go('evidencia')}>
        {c.evidence}
      </Button>
    </div>
  );
}
