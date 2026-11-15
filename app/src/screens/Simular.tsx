import { t } from '../i18n/es';
import { Card, ScreenHead, Skeleton, UnknownBadge } from './parts';

export function Simular() {
  const s = t.simular;
  return (
    <div className="kn-screen">
      <ScreenHead title={s.title} intro={s.intro} />
      {s.controls.map((c) => (
        <Card key={c.title} title={c.title} aside={<UnknownBadge>{t.app.pending}</UnknownBadge>}>
          <p className="kn-card__text">{c.text}</p>
          <Skeleton lines={1} />
        </Card>
      ))}
    </div>
  );
}
