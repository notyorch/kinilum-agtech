import { Button } from '../ds/components';
import { MultiToggle, SegmentedControl } from '../ds/primitives';
import { CROP_IDS } from '../data/crops';
import type { Machinery } from '../data/restrictions';
import { t } from '../i18n/es';
import { useAppState } from '../shell/state';
import { Card, DashedNote, DataSource, Metric, ScreenHead } from './parts';

export function MiParcela() {
  const p = t.parcela;
  const d = t.declaration;
  const { go, declaration, setDeclaration } = useAppState();
  const cropOptions = CROP_IDS.map((c) => ({ value: c, label: d.crops[c] }));
  const machineryOptions = (['manual', 'hired'] satisfies Machinery[]).map((m) => ({ value: m, label: d.machineryOptions[m] }));
  return (
    <div className="kn-screen">
      <ScreenHead title={p.title} />

      <Card title={p.name} aside={<span className="kn-area">{p.area}</span>}>
        <p className="kn-card__text">{p.crop}</p>
      </Card>

      <Card label={p.bare.label}>
        <Metric value={p.bare.value} unit={p.bare.unit} />
        <p className="kn-card__text">{p.bare.detail}</p>
        <DataSource source="HLS" resolution="30 m" scale="parcela" />
      </Card>

      <Card label={p.rain.label}>
        <Metric value={p.rain.value} unit={p.rain.unit} />
        <p className="kn-card__text">{p.rain.detail}</p>
        <DataSource source="IMERG" resolution="11 km" scale="zona" />
      </Card>

      <Card label={p.soil.label} title={p.soil.value}>
        <p className="kn-card__text">{p.soil.detail}</p>
        <DataSource source="SoilGrids" resolution="250 m" estimated scale="entorno" />
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
