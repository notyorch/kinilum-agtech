// El paquete de la parcela en el celular: se baja, se guarda en la Cache API y se VUELVE A LEER antes de decir «listo».
// Sin React ni `window`: todo lo que toca el navegador entra por `Deps`, así las pruebas corren con Node.
//
// El paquete NO va en el precache del service worker (ese solo guarda la app): lo maneja este archivo, para que
// «listo» signifique «lo guardé y lo leí de vuelta», no «lo pedí».

export const PACKAGE_FORMAT = 'kinilum-package/2';
export const PACKAGE_CACHE = 'kinilum-packages-v1';
const FILE_RE = /^[A-Za-z0-9_-]{1,64}\.\d{4}-\d{2}-\d{2}(\.r[2-9]\d*)?\.json$/; // igual que shared/schema/package-index

export interface PackageRef {
  file: string;
  generatedAt: string;
}

export type PackageStatus =
  | { kind: 'checking' }
  | { kind: 'downloading' }
  /** Guardado y releído. `update`: hay uno más nuevo que NO se aplica sin que el usuario acepte. */
  | { kind: 'ready'; current: PackageRef; update: PackageRef | null; viaNetwork: boolean }
  /** No hay paquete guardado y no hay señal: hace falta conectarse una sola vez. */
  | { kind: 'needs-signal' }
  /** El paquete tiene un formato que esta versión de la app no conoce. */
  | { kind: 'unsupported' }
  | { kind: 'failed' };

export interface Deps {
  fetch: typeof fetch;
  caches: Pick<CacheStorage, 'open'>;
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
  /** URL absoluta de la carpeta `packages/`, con diagonal final. */
  base: string;
}

/**
 * Una «Cache API» en memoria, para los navegadores que no la tienen (una página `http` que no es localhost, por ejemplo
 * por Tailscale, no es un contexto seguro). Los datos se bajan, se releen y se ven, pero **no sobreviven a recargar la
 * página**: por eso la app no dice «Listo para usar sin señal» con este respaldo.
 */
export function memoryCaches(): Deps['caches'] {
  const files = new Map<string, string>();
  const cache = {
    async match(url: string) {
      const text = files.get(url);
      return text === undefined ? undefined : new Response(text);
    },
    async put(url: string, res: Response) {
      files.set(url, await res.text());
    },
    async delete(url: string) {
      return files.delete(url);
    },
  };
  return { open: async () => cache as unknown as Cache };
}

class Unsupported extends Error {}
class Network extends Error {}
class Unverified extends Error {}

const pointerKey = (id: string) => `kinilum.package.${id}`;

/** Un paquete válido para esta app: JSON, formato conocido, de esta parcela. Devuelve su referencia. */
export function inspect(text: string, id: string, file: string): PackageRef {
  let pkg: unknown;
  try {
    pkg = JSON.parse(text);
  } catch {
    throw new Unverified('no es JSON');
  }
  const p = pkg as { package_format?: unknown; parcel_id?: unknown; generated_at?: unknown };
  if (p?.package_format !== PACKAGE_FORMAT) throw new Unsupported(String(p?.package_format));
  if (p.parcel_id !== id || typeof p.generated_at !== 'string') throw new Unverified('no es de esta parcela');
  return { file, generatedAt: p.generated_at };
}

async function readIndex(d: Deps, id: string): Promise<PackageRef> {
  let res: Response;
  try {
    res = await d.fetch(`${d.base}index.json`, { cache: 'no-store' }); // el índice NUNCA sale de caché
  } catch {
    throw new Network('sin señal');
  }
  if (!res.ok) throw new Network(`índice: HTTP ${res.status}`);
  const entry = (await res.json())?.parcels?.[id];
  if (!entry || !FILE_RE.test(entry.file ?? '') || typeof entry.generated_at !== 'string') throw new Unverified('índice sin esta parcela');
  return { file: entry.file, generatedAt: entry.generated_at };
}

/** Lo guardado: el puntero, el archivo en la Cache API y su contenido. `null` si algo falla (no se da por bueno). */
export async function readSaved(d: Deps, id: string): Promise<PackageRef | null> {
  const raw = d.storage.getItem(pointerKey(id));
  if (!raw) return null;
  let ref: { file?: unknown };
  try {
    ref = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof ref.file !== 'string' || !FILE_RE.test(ref.file)) return null;
  const cache = await d.caches.open(PACKAGE_CACHE);
  const hit = await cache.match(`${d.base}${ref.file}`);
  if (!hit) return null;
  try {
    return inspect(await hit.text(), id, ref.file);
  } catch (e) {
    if (e instanceof Unsupported) {
      // Un formato que no conocemos: se descarta para volver a bajarlo, no se usa a medias.
      await cache.delete(`${d.base}${ref.file}`);
      d.storage.removeItem(pointerKey(id));
    }
    return null;
  }
}

/** El contenido del paquete guardado (ya verificado por `readSaved`), o `null` si no hay uno bueno. */
export async function readPackageData(d: Deps, id: string): Promise<unknown | null> {
  const saved = await readSaved(d, id);
  if (!saved) return null;
  const hit = await (await d.caches.open(PACKAGE_CACHE)).match(`${d.base}${saved.file}`);
  return hit ? JSON.parse(await hit.text()) : null;
}

/** Baja, guarda y RELEE un paquete. Solo si la relectura coincide byte a byte con lo descargado se da por guardado. */
async function saveVerified(d: Deps, id: string, ref: PackageRef): Promise<PackageRef> {
  const url = `${d.base}${ref.file}`;
  let res: Response;
  try {
    res = await d.fetch(url, { cache: 'no-store' });
  } catch {
    throw new Network('sin señal');
  }
  if (!res.ok) throw new Network(`paquete: HTTP ${res.status}`);
  const text = await res.text();
  inspect(text, id, ref.file); // antes de guardar: que lo entendamos
  const cache = await d.caches.open(PACKAGE_CACHE);
  await cache.put(url, new Response(text, { headers: { 'content-type': 'application/json' } }));
  const back = await cache.match(url);
  if (!back) throw new Unverified('no quedó guardado');
  const again = await back.text();
  if (again !== text) throw new Unverified('lo guardado no coincide con lo descargado');
  return inspect(again, id, ref.file);
}

function classify(e: unknown): PackageStatus {
  if (e instanceof Unsupported) return { kind: 'unsupported' };
  if (e instanceof Network) return { kind: 'needs-signal' };
  return { kind: 'failed' };
}

/** Qué hay en este celular y qué hay en la red. Baja el primero si falta; el nuevo solo se avisa. */
export async function start(d: Deps, id: string, onStatus: (s: PackageStatus) => void = () => {}): Promise<PackageStatus> {
  const saved = await readSaved(d, id).catch(() => null);
  let remote: PackageRef | null = null;
  try {
    remote = await readIndex(d, id);
  } catch (e) {
    if (e instanceof Unverified) return saved ? ready(saved, null, false) : { kind: 'failed' };
    // sin señal: lo guardado sirve; si no hay nada, hace falta señal una vez
    return saved ? ready(saved, null, false) : { kind: 'needs-signal' };
  }
  if (saved && saved.file === remote.file) return ready(saved, null, true);
  if (saved) return ready(saved, remote, true); // hay uno más nuevo: se avisa, no se cambia solo
  onStatus({ kind: 'downloading' });
  try {
    const ok = await saveVerified(d, id, remote);
    d.storage.setItem(pointerKey(id), JSON.stringify({ file: ok.file, generated_at: ok.generatedAt }));
    return ready(ok, null, true);
  } catch (e) {
    return classify(e);
  }
}

/** El usuario aceptó los datos nuevos: se baja y verifica el nuevo antes de soltar el viejo. */
export async function applyUpdate(d: Deps, id: string, next: PackageRef): Promise<PackageStatus> {
  const before = d.storage.getItem(pointerKey(id));
  try {
    const ok = await saveVerified(d, id, next);
    d.storage.setItem(pointerKey(id), JSON.stringify({ file: ok.file, generated_at: ok.generatedAt }));
    if (before) {
      const old = (JSON.parse(before) as { file?: string }).file;
      if (old && old !== ok.file && FILE_RE.test(old)) await (await d.caches.open(PACKAGE_CACHE)).delete(`${d.base}${old}`);
    }
    return ready(ok, null, true);
  } catch (e) {
    const saved = await readSaved(d, id).catch(() => null);
    return saved && !(e instanceof Unsupported) ? ready(saved, next, false) : classify(e); // lo anterior sigue sirviendo
  }
}

const ready = (current: PackageRef, update: PackageRef | null, viaNetwork: boolean): PackageStatus => ({ kind: 'ready', current, update, viaNetwork });
