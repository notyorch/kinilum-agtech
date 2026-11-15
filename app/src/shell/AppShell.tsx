import { useCallback, useEffect, useState, type AnimationEvent, type CSSProperties, type ReactNode } from 'react';
import { t } from '../i18n/es';
import { ChartIcon, DocIcon, GearIcon, PinIcon, SparkIcon } from './icons';
import { TabBar, type TabItem } from './TabBar';
import { useTheme } from './theme';
import { AppStateProvider } from './state';
import { Badge } from '../ds/components';
import { SignalBadge, UpdateNotices } from '../offline/Offline';
import { MiParcela } from '../screens/MiParcela';
import { Comparar } from '../screens/Comparar';
import { Simular } from '../screens/Simular';
import { Evidencia } from '../screens/Evidencia';
import { Ajustes } from '../screens/Ajustes';
import './shell.css';

export type SectionId = 'parcela' | 'comparar' | 'simular' | 'evidencia' | 'ajustes';

const TABS: readonly TabItem<SectionId>[] = [
  { id: 'parcela', label: t.tabs.parcela, Icon: PinIcon },
  { id: 'comparar', label: t.tabs.comparar, Icon: ChartIcon },
  { id: 'simular', label: t.tabs.simular, Icon: SparkIcon },
  { id: 'evidencia', label: t.tabs.evidencia, Icon: DocIcon },
  { id: 'ajustes', label: t.tabs.ajustes, Icon: GearIcon },
];

const SCREENS: Record<SectionId, () => ReactNode> = {
  parcela: () => <MiParcela />,
  comparar: () => <Comparar />,
  simular: () => <Simular />,
  evidencia: () => <Evidencia />,
  ajustes: () => <Ajustes />,
};

const order = (id: SectionId) => TABS.findIndex((tab) => tab.id === id);

/** La sección vive en el hash (#/ajustes) para que recargar no la pierda. */
function readHash(): SectionId {
  const id = window.location.hash.replace(/^#\/?/, '');
  return TABS.some((tab) => tab.id === id) ? (id as SectionId) : 'parcela';
}

interface View {
  current: SectionId;
  /** La sección que sale, mientras dura su animación. */
  leaving: SectionId | null;
  /** 1: la nueva entra por la derecha; -1: por la izquierda. */
  dir: 1 | -1;
}

function Lockup() {
  const { theme } = useTheme();
  return (
    <span className="kn-lockup" role="img" aria-label={t.app.name}>
      <img src={`./brand/lockup-on-${theme}.svg`} alt="" width={2000} height={2000} />
    </span>
  );
}

export function AppShell() {
  const [view, setView] = useState<View>(() => ({ current: readHash(), leaving: null, dir: 1 }));

  const go = useCallback((id: SectionId) => {
    setView((v) =>
      id === v.current ? v : { current: id, leaving: v.current, dir: order(id) > order(v.current) ? 1 : -1 },
    );
    window.history.replaceState(null, '', `#/${id}`);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, []);

  useEffect(() => {
    const sync = () => go(readHash());
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, [go]);

  // Si la animación de salida no llega a terminar (pestaña en segundo plano,
  // animaciones apagadas), la sección anterior se retira igual.
  useEffect(() => {
    if (!view.leaving) return;
    const id = window.setTimeout(() => setView((v) => ({ ...v, leaving: null })), 400);
    return () => window.clearTimeout(id);
  }, [view.leaving, view.current]);

  const onLeft = (e: AnimationEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) setView((v) => ({ ...v, leaving: null }));
  };

  return (
    <AppStateProvider go={go}>
      <div className="kn-app">
        <header className="kn-topbar">
          <Lockup />
          <span className="kn-topbar__badges">
            <Badge tone="unknown">{t.app.illustrative}</Badge>
            <SignalBadge />
          </span>
        </header>
        <UpdateNotices />

        <main id="kn-main" className="kn-stage" role="tabpanel" aria-labelledby={`tab-${view.current}`}>
          {view.leaving && (
            <div
              key={`out-${view.leaving}`}
              className="kn-scene is-leaving"
              style={{ '--dir': view.dir } as CSSProperties}
              onAnimationEnd={onLeft}
              aria-hidden="true"
            >
              {SCREENS[view.leaving]()}
            </div>
          )}
          <div key={view.current} className="kn-scene is-entering" style={{ '--dir': view.dir } as CSSProperties}>
            {SCREENS[view.current]()}
          </div>
        </main>

        <TabBar items={TABS} active={view.current} onChange={go} label={t.app.nav} />
      </div>
    </AppStateProvider>
  );
}
