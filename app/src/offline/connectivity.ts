// «Con señal / Sin señal». `navigator.onLine` solo dice si hay una red, no si el sitio responde: por eso, además,
// se prueba pidiendo el índice de paquetes (que el service worker nunca atiende, así que va a la red de verdad).

const PROBE_MS = 4000;
const EVERY_MS = 60_000;

export async function probe(fetcher: typeof fetch = fetch, onLine: boolean = navigator.onLine): Promise<boolean> {
  if (!onLine) return false;
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), PROBE_MS);
  try {
    const res = await fetcher(new URL(`packages/index.json?probe=${Date.now()}`, document.baseURI).href, { method: 'HEAD', cache: 'no-store', signal: ctl.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** Revisa al abrir, al volver a la pestaña, con los eventos online/offline y cada minuto mientras esté a la vista. */
export function watchConnectivity(onChange: (online: boolean) => void): () => void {
  let alive = true;
  const check = () => void probe().then((ok) => alive && onChange(ok));
  const visible = () => document.visibilityState === 'visible' && check();
  const goOffline = () => onChange(false);
  const timer = window.setInterval(visible, EVERY_MS);
  window.addEventListener('online', check);
  window.addEventListener('offline', goOffline);
  document.addEventListener('visibilitychange', visible);
  check();
  return () => {
    alive = false;
    window.clearInterval(timer);
    window.removeEventListener('online', check);
    window.removeEventListener('offline', goOffline);
    document.removeEventListener('visibilitychange', visible);
  };
}
