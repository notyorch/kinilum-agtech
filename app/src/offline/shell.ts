// El service worker: registro, estado y aviso de versión nueva. Solo corre en el build (no en `npm run dev`).

export type ShellState =
  | 'dev' //          npm run dev: no hay service worker
  | 'unsupported' //  el navegador no lo permite (por ejemplo, sin HTTPS)
  | 'installing'
  | 'ready' //        la app quedó guardada y se releyó de la caché
  | 'failed';

export interface ShellSnapshot {
  state: ShellState;
  /** Hay una versión nueva ya descargada, esperando a que el usuario acepte. */
  update: boolean;
}

type Listener = (s: ShellSnapshot) => void;

let snap: ShellSnapshot = { state: import.meta.env.DEV ? 'dev' : 'installing', update: false };
let registration: ServiceWorkerRegistration | null = null;
let reloadOnTakeover = false;
const listeners = new Set<Listener>();

const set = (next: Partial<ShellSnapshot>) => {
  snap = { ...snap, ...next };
  listeners.forEach((l) => l(snap));
};

export const shellSnapshot = () => snap;
export function subscribeShell(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** «Listo» solo si el worker está activo Y el index.html se lee de vuelta de la caché de la app. */
async function verifyShell(): Promise<boolean> {
  try {
    const hit = await caches.match(new URL('index.html', document.baseURI).href, { ignoreSearch: true });
    return !!hit;
  } catch {
    return false;
  }
}

async function onActive(reg: ServiceWorkerRegistration) {
  set({ state: (await verifyShell()) ? 'ready' : 'failed', update: !!reg.waiting });
}

function watch(worker: ServiceWorker, reg: ServiceWorkerRegistration) {
  worker.addEventListener('statechange', () => {
    if (worker.state === 'activated') void onActive(reg);
    // Una versión nueva descargada mientras la anterior controla la página: espera la decisión del usuario.
    if (worker.state === 'installed' && navigator.serviceWorker.controller) set({ update: true });
    if (worker.state === 'redundant' && !reg.active) set({ state: 'failed' });
  });
}

export function registerShell(): void {
  if (import.meta.env.DEV) return;
  if (!('serviceWorker' in navigator) || !('caches' in window)) return set({ state: 'unsupported' });
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (reloadOnTakeover) window.location.reload(); // solo cuando el usuario aceptó: la primera vez no recarga
  });
  navigator.serviceWorker
    .register('./sw.js', { updateViaCache: 'none' })
    .then((reg) => {
      registration = reg;
      if (reg.installing) watch(reg.installing, reg);
      reg.addEventListener('updatefound', () => reg.installing && watch(reg.installing, reg));
      if (reg.active && !reg.installing) void onActive(reg);
      else if (reg.waiting && navigator.serviceWorker.controller) set({ update: true });
      document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && void reg.update().catch(() => {}));
    })
    .catch(() => set({ state: 'failed' }));
}

/** El usuario aceptó la versión nueva: se activa y la página se vuelve a abrir. */
export function applyShellUpdate(): void {
  if (!registration?.waiting) return;
  reloadOnTakeover = true;
  registration.waiting.postMessage({ type: 'SKIP_WAITING' });
}
