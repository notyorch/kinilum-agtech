// El service worker real (la plantilla con su lista de archivos) corrido contra un entorno simulado: sin navegador.
// No reemplaza probarlo en un navegador con service worker: comprueba la lógica de caché y qué NO toca.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const SCOPE = 'https://kinilum.test/app/';
const FILES = ['index.html', 'assets/index-abc.js', 'assets/index-abc.css', 'brand/lockup-on-dark.svg'];

function boot({ active = null, existing = {} } = {}) {
  const src = readFileSync(new URL('../sw/sw.template.js', import.meta.url), 'utf8').replace('__VERSION__', 'v1').replace('__PRECACHE__', JSON.stringify(FILES));
  const handlers = {};
  const store = new Map(Object.entries(existing).map(([k, v]) => [k, new Map(Object.entries(v))]));
  const log = { skipWaiting: 0, claim: 0, network: [], added: [] };
  const mk = (name) => {
    if (!store.has(name)) store.set(name, new Map());
    const m = store.get(name);
    return {
      async addAll(reqs) {
        for (const r of reqs) {
          log.added.push({ url: r.url, cache: r.cache });
          m.set(r.url.split('?')[0], 'cached:' + r.url);
        }
      },
      async match(req, opts) {
        const url = (typeof req === 'string' ? req : req.url);
        const key = opts?.ignoreSearch ? url.split('?')[0] : url;
        return m.has(key) ? { body: m.get(key) } : undefined;
      },
    };
  };
  const caches = {
    open: async (n) => mk(n),
    keys: async () => [...store.keys()],
    delete: async (n) => store.delete(n),
    match: async (url, opts) => {
      const c = opts?.cacheName ? [opts.cacheName] : [...store.keys()];
      for (const n of c) {
        const hit = store.get(n)?.get(typeof url === 'string' ? url : url.url);
        if (hit) return { body: hit };
      }
    },
  };
  const self = {
    registration: { scope: SCOPE, active },
    location: new URL(SCOPE),
    clients: { claim: async () => void log.claim++ },
    skipWaiting: () => void log.skipWaiting++,
    addEventListener: (type, fn) => (handlers[type] = fn),
  };
  const ctx = vm.createContext({
    self,
    caches,
    URL,
    Request: class Request {
      constructor(url, init) {
        this.url = url;
        this.cache = init?.cache;
      }
    },
    fetch: async (req) => (log.network.push(req.url ?? req), { body: 'network' }),
  });
  vm.runInContext(src, ctx);
  const fire = async (type, ev) => {
    let p;
    handlers[type]({ ...ev, waitUntil: (x) => (p = x), respondWith: (x) => (ev.responded = x) });
    await p;
  };
  return { store, log, handlers, fire };
}

/** Dispara un `fetch` y devuelve la respuesta del worker (o `undefined` si no lo atendió). */
const dispatch = async (sw, req) => {
  let responded;
  sw.handlers.fetch({ request: req, respondWith: (p) => (responded = p) });
  return responded === undefined ? undefined : await responded;
};

const request = (path, init = {}) => ({ method: 'GET', mode: 'cors', url: new URL(path, SCOPE).href, ...init });

test('instalar guarda todo el shell, saltándose la caché HTTP, y la primera vez se activa sin esperar', async () => {
  const sw = boot();
  await sw.fire('install', {});
  assert.deepEqual(sw.log.added.map((a) => a.url), FILES.map((f) => SCOPE + f));
  assert.ok(sw.log.added.every((a) => a.cache === 'reload'));
  assert.equal(sw.log.skipWaiting, 1);
});

test('si ya había una versión, la nueva espera: no se activa sola', async () => {
  const sw = boot({ active: {} });
  await sw.fire('install', {});
  assert.equal(sw.log.skipWaiting, 0);
  sw.handlers.message({ data: { type: 'SKIP_WAITING' } });
  assert.equal(sw.log.skipWaiting, 1, 'solo cuando el usuario acepta');
  sw.handlers.message({ data: { type: 'otra-cosa' } });
  assert.equal(sw.log.skipWaiting, 1);
});

test('activar borra los shells viejos pero NUNCA el paquete de la parcela', async () => {
  const sw = boot({ existing: { 'kinilum-shell-v0': { a: 1 }, 'kinilum-shell-v1': { b: 1 }, 'kinilum-packages-v1': { p: 'paquete' }, 'otra-app': { x: 1 } } });
  await sw.fire('activate', {});
  assert.deepEqual([...sw.store.keys()].sort(), ['kinilum-packages-v1', 'kinilum-shell-v1', 'otra-app']);
  assert.equal(sw.log.claim, 1);
});

test('una navegación sale del index.html guardado, también sin señal y con cualquier ruta o parámetro', async () => {
  const sw = boot();
  await sw.fire('install', {});
  for (const path of ['', 'index.html', '?utm=1']) {
    assert.equal((await dispatch(sw, request(path, { mode: 'navigate' }))).body, `cached:${SCOPE}index.html`);
  }
  assert.deepEqual(sw.log.network, []);
});

test('los archivos de la app salen de la caché primero y, si faltan, de la red', async () => {
  const sw = boot();
  await sw.fire('install', {});
  assert.equal((await dispatch(sw, request('assets/index-abc.js?v=2'))).body, `cached:${SCOPE}assets/index-abc.js`);
  assert.equal((await dispatch(sw, request('assets/otro.js'))).body, 'network');
});

test('el índice y el paquete de la parcela NO los atiende el service worker', async () => {
  const sw = boot();
  await sw.fire('install', {});
  for (const path of ['packages/index.json', 'packages/index.json?probe=1', 'packages/yuc-demo-001.2026-11-14.json']) {
    assert.equal(await dispatch(sw, request(path)), undefined, path);
  }
});

test('no toca lo que no es suyo: POST, otros orígenes y rutas fuera del alcance', async () => {
  const sw = boot();
  await sw.fire('install', {});
  for (const req of [request('assets/index-abc.js', { method: 'POST' }), { method: 'GET', mode: 'cors', url: 'https://otro.test/app/assets/index-abc.js' }, { method: 'GET', mode: 'cors', url: 'https://kinilum.test/otra/x.js' }]) {
    assert.equal(await dispatch(sw, req), undefined, req.url);
  }
});

test('el service worker publicado (dist/sw.js) lleva la misma lógica y una versión real', () => {
  let built;
  try {
    built = readFileSync(new URL('../dist/sw.js', import.meta.url), 'utf8');
  } catch {
    return; // sin build todavía: `npm run build` lo genera y check-offline lo revisa
  }
  assert.match(built, /const VERSION = '[0-9a-f]{12}';/);
  assert.ok(!built.includes('__PRECACHE__'));
});
