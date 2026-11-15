import { t } from '../i18n/es';
import { Card, ScreenHead, Skeleton, UnknownBadge } from './parts';

export function Comparar() {
  const c = t.comparar;
  return (
    <div className="kn-screen">
      <ScreenHead title={c.title} intro={c.intro} />
      {c.strategies.map((s) => (
        <Card key={s.name} title={s.name} aside={<UnknownBadge>{c.notComputed}</UnknownBadge>}>
          <p className="kn-card__text">{s.note}</p>
          <Skeleton lines={3} />
        </Card>
      ))}
      <p className="kn-closing">{t.app.closing}</p>
    </div>
  );
}
