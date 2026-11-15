// Pruebas del paquete en el celular: guardar, releer y no decir «listo» de más. Sin navegador: caché, almacenamiento y red falsos.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PACKAGE_CACHE, PACKAGE_FORMAT, applyUpdate, readSaved, start } from '../src/offline/packageStore.ts';
import { readinessOf } from '../src/offline/readiness.ts';

const BASE = 'https://kinilum.test/packages/';
const ID = 'yuc-demo-001';
const OLD = `${ID}.2026-11-14.json`;
const NEW = `${ID}.2026-11-15.json`;

const pkg = (date, extra = {}) => JSON.stringify({ package_format: PACKAGE_FORMAT, parcel_id: ID, generated_at: date, ...extra });

function world({ files, index, online = true, corruptOnRead = false, putFails = false } = {}) {
  const store = new Map();
  const ls = new Map();
  const calls = [];
  const cache = {
    async put(url, res) {
      if (putFails) throw new Error('disco lleno');
      store.set(url, await res.text());
    },
    async match(url) {
      return store.has(url) ? new Response(corruptOnRead ? store.get(url) + ' ' : store.get(url)) : undefined;
    },
    async delete(url) {
      return store.delete(url);
    },
  };
  const w = {
    store,
    ls,
    calls,
    online,
    files,
    index,
    deps: {
      base: BASE,
      caches: { open: async (name) => (assert.equal(name, PACKAGE_CACHE), cache) },
      storage: { getItem: (k) => ls.get(k) ?? null, setItem: (k, v) => void ls.set(k, v), removeItem: (k) => void ls.delete(k) },
      fetch: async (url, init) => {
        calls.push({ url, cache: init?.cache });
        if (!w.online) throw new TypeError('Failed to fetch');
        if (url === `${BASE}index.json`) return new Response(JSON.stringify({ parcels: { [ID]: { file: w.index.file, generated_at: w.index.date } } }));
        const name = url.slice(BASE.length);
        return name in w.files ? new Response(w.files[name]) : new Response('no', { status: 404 });
      },
    },
  };
  return w;
}

test('primera vez con señal: baja, guarda, relee y recién entonces queda listo', async () => {
  const w = world({ files: { [OLD]: pkg('2026-11-14') }, index: { file: OLD, date: '2026-11-14' } });
  const seen = [];
  const s = await start(w.deps, ID, (x) => seen.push(x.kind));
  assert.deepEqual(seen, ['downloading']);
  assert.equal(s.kind, 'ready');
  assert.equal(s.current.file, OLD);
  assert.equal(s.update, null);
  assert.ok(w.store.has(`${BASE}${OLD}`), 'quedó en la Cache API');
  assert.deepEqual(JSON.parse(w.ls.get(`kinilum.package.${ID}`)), { file: OLD, generated_at: '2026-11-14' });
});

test('el índice y el paquete se piden siempre a la red, nunca de la caché del navegador', async () => {
  const w = world({ files: { [OLD]: pkg('2026-11-14') }, index: { file: OLD, date: '2026-11-14' } });
  await start(w.deps, ID);
  assert.ok(w.calls.length >= 2 && w.calls.every((c) => c.cache === 'no-store'));
});

test('primera vez sin señal: hace falta señal una vez y nunca dice listo', async () => {
  const w = world({ files: {}, index: { file: OLD, date: '2026-11-14' }, online: false });
  const s = await start(w.deps, ID);
  assert.equal(s.kind, 'needs-signal');
  assert.equal(readinessOf(s, 'ready'), 'needs-signal');
});

test('después de guardado, sin señal sigue listo con lo guardado', async () => {
  const w = world({ files: { [OLD]: pkg('2026-11-14') }, index: { file: OLD, date: '2026-11-14' } });
  await start(w.deps, ID);
  w.online = false;
  const s = await start(w.deps, ID);
  assert.equal(s.kind, 'ready');
  assert.equal(s.viaNetwork, false);
  assert.equal(s.current.file, OLD);
});

test('si lo guardado no se lee igual, no se da por guardado', async () => {
  const w = world({ files: { [OLD]: pkg('2026-11-14') }, index: { file: OLD, date: '2026-11-14' }, corruptOnRead: true });
  const s = await start(w.deps, ID);
  assert.equal(s.kind, 'failed');
  assert.equal(w.ls.get(`kinilum.package.${ID}`), undefined, 'sin puntero: no hay nada que dar por bueno');
});

test('si no se puede escribir en la caché (disco lleno, modo privado) no dice listo', async () => {
  const w = world({ files: { [OLD]: pkg('2026-11-14') }, index: { file: OLD, date: '2026-11-14' }, putFails: true });
  const s = await start(w.deps, ID);
  assert.equal(s.kind, 'failed');
  assert.equal(readinessOf(s, 'ready'), 'failed');
});

test('un formato que la app no conoce se rechaza y no se guarda', async () => {
  const w = world({ files: { [OLD]: JSON.stringify({ package_format: 'kinilum-package/9', parcel_id: ID, generated_at: '2026-11-14' }) }, index: { file: OLD, date: '2026-11-14' } });
  const s = await start(w.deps, ID);
  assert.equal(s.kind, 'unsupported');
  assert.equal(w.store.size, 0);
  assert.equal(readinessOf(s, 'ready'), 'unsupported');
});

test('un paquete guardado con un formato que ya no conocemos se descarta y se vuelve a bajar', async () => {
  const w = world({ files: { [OLD]: pkg('2026-11-14') }, index: { file: OLD, date: '2026-11-14' } });
  w.store.set(`${BASE}${OLD}`, JSON.stringify({ package_format: 'kinilum-package/1', parcel_id: ID, generated_at: '2026-11-14' }));
  w.ls.set(`kinilum.package.${ID}`, JSON.stringify({ file: OLD, generated_at: '2026-11-14' }));
  assert.equal(await readSaved(w.deps, ID), null);
  assert.equal(w.store.size, 0);
  const s = await start(w.deps, ID);
  assert.equal(s.kind, 'ready');
  assert.equal(JSON.parse(w.store.get(`${BASE}${OLD}`)).package_format, PACKAGE_FORMAT);
});

test('un paquete de otra parcela no se acepta', async () => {
  const w = world({ files: { [OLD]: JSON.stringify({ package_format: PACKAGE_FORMAT, parcel_id: 'otra', generated_at: '2026-11-14' }) }, index: { file: OLD, date: '2026-11-14' } });
  assert.equal((await start(w.deps, ID)).kind, 'failed');
});

test('hay datos nuevos: se avisa y NO se cambia nada hasta que el usuario acepte', async () => {
  const w = world({ files: { [OLD]: pkg('2026-11-14'), [NEW]: pkg('2026-11-15') }, index: { file: OLD, date: '2026-11-14' } });
  await start(w.deps, ID);
  w.index = { file: NEW, date: '2026-11-15' };
  const s = await start(w.deps, ID);
  assert.equal(s.kind, 'ready');
  assert.equal(s.current.file, OLD);
  assert.equal(s.update?.file, NEW);
  assert.ok(!w.store.has(`${BASE}${NEW}`), 'lo nuevo todavía no se bajó');
  assert.equal(JSON.parse(w.ls.get(`kinilum.package.${ID}`)).file, OLD);

  const after = await applyUpdate(w.deps, ID, s.update);
  assert.equal(after.kind, 'ready');
  assert.equal(after.current.file, NEW);
  assert.equal(after.update, null);
  assert.ok(w.store.has(`${BASE}${NEW}`) && !w.store.has(`${BASE}${OLD}`), 'se suelta el viejo solo después de verificar el nuevo');
});

test('si falla la descarga de lo nuevo, lo anterior sigue sirviendo', async () => {
  const w = world({ files: { [OLD]: pkg('2026-11-14') }, index: { file: OLD, date: '2026-11-14' } });
  await start(w.deps, ID);
  w.online = false;
  const s = await applyUpdate(w.deps, ID, { file: NEW, generatedAt: '2026-11-15' });
  assert.equal(s.kind, 'ready');
  assert.equal(s.current.file, OLD);
  assert.ok(s.update, 'el aviso sigue ahí para reintentar');
});

test('el índice que nombra un archivo raro se rechaza (no se pide cualquier ruta)', async () => {
  const w = world({ files: {}, index: { file: '../../etc/passwd', date: '2026-11-14' } });
  assert.equal((await start(w.deps, ID)).kind, 'failed');
  assert.ok(w.calls.every((c) => c.url === `${BASE}index.json`));
});

test('«listo para usar sin señal» exige paquete Y aplicación guardados', () => {
  const ready = { kind: 'ready', current: { file: OLD, generatedAt: '2026-11-14' }, update: null, viaNetwork: true };
  assert.equal(readinessOf(ready, 'ready'), 'ready');
  assert.equal(readinessOf(ready, 'installing'), 'saving');
  assert.equal(readinessOf(ready, 'unsupported'), 'shell-missing');
  assert.equal(readinessOf(ready, 'failed'), 'shell-missing', 'datos guardados pero la app no: no es «listo»');
  assert.equal(readinessOf({ kind: 'failed' }, 'ready'), 'failed');
  assert.equal(readinessOf(ready, 'dev'), 'dev');
  assert.equal(readinessOf({ kind: 'checking' }, 'ready'), 'saving');
  assert.equal(readinessOf({ kind: 'downloading' }, 'ready'), 'saving');
});
