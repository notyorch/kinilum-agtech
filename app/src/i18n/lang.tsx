import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { en } from './en';
import { es, setStrings } from './es';
import { setStrategyStrings } from './strategies';

export type Lang = 'es' | 'en';
export const LANGS: readonly Lang[] = ['es', 'en'];
const KEY = 'kinilum.lang';

function stored(): Lang | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === 'es' || v === 'en' ? v : null;
  } catch {
    return null; // sin almacenamiento (modo privado): la app sigue en español
  }
}

/** Pone los textos del idioma, antes de que nada se dibuje. */
function apply(lang: Lang): void {
  setStrings(lang === 'en' ? en : es);
  setStrategyStrings(lang);
  document.documentElement.lang = lang;
}

let initial: Lang = stored() ?? 'es';
apply(initial);

interface LangState {
  lang: Lang;
  setLang: (l: Lang) => void;
}

const Ctx = createContext<LangState | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initial);
  const setLang = useCallback((next: Lang) => {
    apply(next);
    initial = next;
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* se usa en esta sesión y ya */
    }
    setLangState(next);
  }, []);
  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLang(): LangState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useLang fuera de LangProvider');
  return ctx;
}
