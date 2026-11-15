import { SegmentedControl } from '../ds/primitives';
import { LANGS, useLang, type Lang } from '../i18n/lang';
import { OfflineCard } from '../offline/Offline';
import { t } from '../i18n/es';
import { THEME_PREFS, useTheme } from '../shell/theme';
import { Card, ScreenHead } from './parts';

export function Ajustes() {
  const a = t.ajustes;
  const { pref, setPref } = useTheme();
  const { lang, setLang } = useLang();
  const names: Record<Lang, string> = { es: 'Español', en: 'English' };
  return (
    <div className="kn-screen">
      <ScreenHead title={a.title} intro={t.app.closing} />
      <Card title={a.theme}>
        <SegmentedControl
          className="kn-fill"
          label={a.theme}
          value={pref}
          onChange={setPref}
          options={THEME_PREFS.map((p) => ({ value: p, label: a.themes[p] }))}
        />
      </Card>
      <Card title={a.language}>
        <SegmentedControl
          className="kn-fill"
          label={a.language}
          value={lang}
          onChange={setLang}
          options={LANGS.map((l) => ({ value: l, label: names[l], lang: l }))}
        />
      </Card>
      <OfflineCard />
      <Card title={a.about}>
        <p className="kn-card__text">{a.aboutText}</p>
        <p className="kn-meta">{a.version}</p>
      </Card>
    </div>
  );
}
