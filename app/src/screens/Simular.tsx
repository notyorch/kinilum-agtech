import { Badge } from '../ds/components';
import { Slider } from '../ds/primitives';
import { robustnessOf, type StrategyId } from '../data/comparison';
import { RAIN_STEPS, TEMP_STEPS, firstShare, type ScenarioResult } from '../data/scenarios';
import { t } from '../i18n/es';
import { strategyText } from '../i18n/strategies';
import { useAppState } from '../shell/state';
import { useFlip } from '../shell/useFlip';
import { Bar, Card, DashedNote, ScreenHead } from './parts';

const signed = (v: number, unit: string) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)} ${unit}`;
const first = <T,>(xs: readonly T[]) => xs[0]!;
const last = <T,>(xs: readonly T[]) => xs[xs.length - 1]!;

/** Puntos de diferencia (de 100) a partir de los cuales decimos que aguanta más o menos. */
const NOTICEABLE = 3;

export function Simular() {
  const x = t.simular;
  const { selected, setSelected, rain, setRain, temp, setTemp, declaration, resultAt } = useAppState();
  const normal = resultAt(0, 0);
  const r = resultAt(rain, temp);

  const name = (id: StrategyId) => strategyText(id, declaration.beanVariant).short;
  const ids = [...r.order, ...r.unranked, ...r.excluded];
  const register = useFlip(ids.join());

  const topChanged = r.order[0] !== normal.order[0];
  const tie = r.order.length > 1 && robustnessOf(firstShare(r), r.marginMedian) === 'indistinguishable';

  const place = (res: ScenarioResult) => x.place(res.order.indexOf(selected) + 1, res.order.length);
  const before = normal.totals[selected];
  const after = r.totals[selected];
  const competes = r.order.includes(selected) && before !== null && after !== null;
  const d = competes ? after - before : 0;
  const verdict = !competes ? x.verdict.out : d < -NOTICEABLE ? x.verdict.less : d > NOTICEABLE ? x.verdict.more : x.verdict.same;

  return (
    <div className="kn-screen">
      <ScreenHead title={x.title} intro={x.intro} />

      <Card label={x.rain} aside={<span className="kn-reading">{signed(rain, '%')}</span>}>
        <Slider
          label={x.rain}
          value={rain}
          onChange={setRain}
          min={first(RAIN_STEPS)}
          max={last(RAIN_STEPS)}
          step={10}
          valueText={x.rainText(rain)}
        />
        <div className="kn-ticks">
          <span>{x.rainMin}</span>
          <span>{x.rainMid}</span>
          <span>{x.rainMax}</span>
        </div>
      </Card>

      <Card label={x.heat} aside={<span className="kn-reading">{signed(temp, '°C')}</span>}>
        <Slider
          label={x.heat}
          value={temp}
          onChange={setTemp}
          min={first(TEMP_STEPS)}
          max={last(TEMP_STEPS)}
          step={1}
          valueText={x.heatText(temp)}
        />
        {/* El cero no queda al centro: va de −2 a +4. */}
        <div className="kn-ticks kn-ticks--temp">
          <span>{x.heatMin}</span>
          <span>{x.heatMid}</span>
          <span>{x.heatMax}</span>
        </div>
      </Card>

      <Card
        label={x.result(name(selected))}
        title={verdict}
        aside={r.named && <Badge tone="neutral">{t.scenarios[r.named]}</Badge>}
      >
        {competes && (
          <>
            <Bar label={x.normal} value={before / 100} tone="brand" valueText={place(normal)} />
            <Bar label={x.changed} value={after / 100} valueText={place(r)} />
          </>
        )}
      </Card>

      <section className="kn-rank" aria-label={x.orderTitle}>
        <h2 className="kn-rank__title">{x.orderTitle}</h2>
        {topChanged && r.movedBy && <p className="kn-card__text">{x.movedBy(t.criteria[r.movedBy].toLowerCase())}</p>}
        {tie && <p className="kn-card__text">{x.tieNote}</p>}
        <ol className="kn-rank__list">
          {ids.map((id) => {
            const pos = r.order.indexOf(id);
            const total = r.totals[id];
            return (
              <li key={id} ref={register(id)}>
                <button
                  type="button"
                  className="kn-rank__row"
                  aria-pressed={selected === id}
                  data-muted={pos < 0 || undefined}
                  onClick={() => setSelected(id)}
                >
                  <span className="kn-rank__pos">{pos < 0 ? '–' : pos + 1}</span>
                  <span className="kn-rank__name">{name(id)}</span>
                  {pos < 0 ? (
                    <span className="kn-rank__tag">
                      {r.excluded.includes(id) ? t.comparar.excluded : t.comparar.unranked}
                    </span>
                  ) : (
                    <span className="kn-rank__meter" aria-hidden="true">
                      <span
                        className={pos === 0 ? 'kn-bar__fill--brand' : 'kn-bar__fill--ink'}
                        style={{ width: `${Math.round(total ?? 0)}%` }}
                      />
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ol>
        <p className="kn-hint">{x.orderHint}</p>
      </section>

      <DashedNote title={x.note} />
    </div>
  );
}
