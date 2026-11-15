import { t } from '../i18n/es';
import { ScreenHead, SourceTag, UnknownBadge } from './parts';

export function Evidencia() {
  const e = t.evidencia;
  return (
    <div className="kn-screen">
      <ScreenHead title={e.title} intro={e.intro} />
      <ul className="kn-list">
        {e.sources.map((s) => (
          <li key={s.name}>
            <SourceTag name={s.name} res={s.res} />
            <span className="kn-list__text">{s.text}</span>
            <UnknownBadge>{e.notConnected}</UnknownBadge>
          </li>
        ))}
      </ul>
    </div>
  );
}
