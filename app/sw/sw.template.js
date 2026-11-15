// Service worker de kinilum. NO se edita en dist/: `scripts/build-sw.mjs` copia esta plantilla y le pone la versión y
// la lista de archivos de la app (el «shell»). Guarda solo la app; el paquete de la parcela lo guarda la propia app en
// la Cache API (`kinilum-packages-v1`), por eso aquí no se toca nada de `packages/`.
const VERSION = '__VERSION__';
const SHELL_CACHE = `kinilum-shell-${VERSION}`;
const PRECACHE = __PRECACHE__;
const SCOPE = self.registration.scope;
const at = (path) => new URL(path, SCOPE).href;

self.addEventListener('install', (event) => {
  // La primera vez no hay nada que proteger: se activa de inmediato. Si ya había una versión, espera a que el usuario acepte.
  if (!self.registration.active) self.skipWaiting();
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(PRECACHE.map((p) => new Request(at(p), { cache: 'reload' })))));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) {
        if (name.startsWith('kinilum-shell-') && name !== SHELL_CACHE) await caches.delete(name); // el paquete (kinilum-packages-*) no se toca
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || !url.href.startsWith(SCOPE)) return;
  if (url.href.slice(SCOPE.length).startsWith('packages/')) return; // índice y paquete: de la red o de la Cache API de la app, nunca de aquí
  if (req.mode === 'navigate') {
    event.respondWith(caches.match(at('index.html'), { cacheName: SHELL_CACHE }).then((hit) => hit || fetch(req)));
    return;
  }
  event.respondWith(caches.open(SHELL_CACHE).then((cache) => cache.match(req, { ignoreSearch: true })).then((hit) => hit || fetch(req)));
});
