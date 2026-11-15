import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type Theme = 'dark' | 'light';
/** Lo que elige la persona: un tema fijo o seguir al dispositivo. */
export type ThemePref = 'system' | 'light' | 'dark';
export const THEME_PREFS: ThemePref[] = ['system', 'light', 'dark'];

const KEY = 'kinilum.theme';
const THEME_COLOR: Record<Theme, string> = { dark: '#000000', light: '#ffffff' }; // = token surface
const DARK_QUERY = '(prefers-color-scheme: dark)';

/** Sin preferencia guardada: sigue al dispositivo. */
function readPref(): ThemePref {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark' || saved === 'system') return saved;
  } catch {
    /* sin almacenamiento: sigue al dispositivo */
  }
  return 'system';
}

interface ThemeCtx {
  pref: ThemePref;
  setPref: (p: ThemePref) => void;
  /** El tema que se ve ahora (resuelve «dispositivo»). */
  theme: Theme;
}

const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPref] = useState<ThemePref>(readPref);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(DARK_QUERY).matches);

  useEffect(() => {
    const mq = window.matchMedia(DARK_QUERY);
    const sync = () => setSystemDark(mq.matches);
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  const theme: Theme = pref === 'system' ? (systemDark ? 'dark' : 'light') : pref;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme]);
  }, [theme]);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, pref);
    } catch {
      /* sin almacenamiento: la preferencia dura la sesión */
    }
  }, [pref]);

  const value = useMemo(() => ({ pref, setPref, theme }), [pref, theme]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useTheme fuera de ThemeProvider');
  return ctx;
}
