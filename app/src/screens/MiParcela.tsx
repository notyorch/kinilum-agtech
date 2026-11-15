import { Button } from '../ds/components';
import { MultiToggle, SegmentedControl } from '../ds/primitives';
import { CROP_IDS } from '../data/crops';
import { factsFrom, roundTo } from '../data/parcelFacts';
import type { Machinery } from '../data/restrictions';
import { t } from '../i18n/es';
import { useOffline } from '../offline/OfflineProvider';
import { useAppState } from '../shell/state';
import { Card, DashedNote, DataSource, Metric, ScreenHead } from './parts';

export function MiParcela() {
  const p = t.parcela;
  const d = t.declaration;
  const { go, declaration, setDeclaration } = useAppState();
  const { data } = useOffline();
  const facts = factsFrom(data);
  const cropOptions = CROP_IDS.map((c) => ({ value: c, label: d.crops[c] }));
  const machineryOptions = (['manual', 'hired'] satisfies Machinery[]).map((m) => ({ value: m, label: d.machineryOptions[m] }));
  return (
    <div className="kn-screen">
      <ScreenHead title={p.title} />

      <Card title={p.name} aside={facts.areaHa !== null && <span className="kn-area">{p.area(facts.areaHa)}</span>}>
        <p className="kn-card__text">{p.crop}</p>
        {!data && <p className="kn-card__text">{p.waiting}</p>}
      </Card>

      <Card label={p.bare.label}>
        {facts.bareMonths ? (
          <>
            <Metric value={`${p.bare.atLeast} ${facts.bareMonths.value}`} unit={p.bare.unit} />
            <p className="kn-card__text">{p.bare.detail}</p>
          </>
        ) : (
          <>
            <Metric value={t.noData} />
            <p className="kn-card__text">{p.bare.none}</p>
          </>
        )}
        <DataSource source="HLS" resolution="30 m" scale="parcela" />
      </Card>

      <Card label={p.rain.label}>
        {facts.rainMm ? (
          <>
            <Metric value={String(roundTo(facts.rainMm.value, 10))} unit={p.rain.unit} />
            <p className="kn-card__text">{p.rain.detail(roundTo(facts.rainMm.low, 10), roundTo(facts.rainMm.high, 10))}</p>
          </>
        ) : (
          <>
            <Metric value={t.noData} />
            <p className="kn-card__text">{p.rain.none}</p>
          </>
        )}
        <DataSource source="IMERG" resolution="11 km" scale="zona" estimated />
      </Card>

      <Card label={p.soil.label} title={facts.rootDepthCm ? undefined : p.soil.value}>
        {facts.rootDepthCm ? <Metric value={String(Math.round(facts.rootDepthCm.value))} unit="cm" /> : null}
        <p className="kn-card__text">{facts.rootDepthCm ? p.soil.measured(Math.round(facts.rootDepthCm.value)) : p.soil.detail}</p>
        <DataSource source={p.soil.source} resolution={p.soil.sourceDetail} scale="parcela" />
      </Card>

      <DashedNote title={t.app.unknownTitle}>{p.unknown}</DashedNote>

      <Card title={d.title}>
        <p className="kn-card__text">{d.intro}</p>
        <div className="kn-field">
          <p className="kn-field__label">{d.machinery}</p>
          <SegmentedControl
            className="kn-fill"
            label={d.machinery}
            value={declaration.machinery}
            onChange={(machinery) => setDeclaration({ ...declaration, machinery })}
            options={machineryOptions}
          />
        </div>
        <div className="kn-field">
          <p className="kn-field__label">{d.accepted}</p>
          <MultiToggle
            label={d.accepted}
            value={declaration.accepted}
            onChange={(accepted) => setDeclaration({ ...declaration, accepted })}
            options={cropOptions}
          />
        </div>
        <div className="kn-field">
          <p className="kn-field__label">{d.market}</p>
          <MultiToggle
            label={d.market}
            value={declaration.market}
            onChange={(market) => setDeclaration({ ...declaration, market })}
            options={cropOptions}
          />
        </div>
      </Card>

      <Button variant="primary" className="kn-cta" onClick={() => go('comparar')}>
        {p.cta}
      </Button>
    </div>
  );
}
