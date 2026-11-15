import { t } from '../i18n/es';
import { THEME_PREFS, useTheme } from '../shell/theme';
import { Card, ScreenHead } from './parts';

export function Ajustes() {
  const a = t.ajustes;
  const { pref, setPref } = useTheme();
  return (
    <div className="kn-screen">
      <ScreenHead title={a.title} intro={t.app.closing} />
      <Card title={a.theme}>
        <div className="kn-segmented" role="radiogroup" aria-label={a.theme}>
          {THEME_PREFS.map((p) => (
            <button key={p} type="button" role="radio" aria-checked={pref === p} onClick={() => setPref(p)}>
              {a.themes[p]}
            </button>
          ))}
        </div>
      </Card>
      <Card title={a.about}>
        <p className="kn-card__text">{a.aboutText}</p>
        <p className="kn-meta">{a.version}</p>
      </Card>
    </div>
  );
}
