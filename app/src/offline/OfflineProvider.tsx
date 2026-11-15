import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react';
import { watchConnectivity } from './connectivity';
import type { ParcelPackage } from '../data/schema.gen.ts';
import { applyUpdate, memoryCaches, readPackageData, start, type Deps, type PackageStatus } from './packageStore.ts';
import { readinessOf, type OfflineReadiness } from './readiness.ts';
import { applyShellUpdate, registerShell, shellSnapshot, subscribeShell } from './shell';

/** Hoy solo existe la parcela de ejemplo; cuando haya más, el id saldrá de la ruta. */
export const PARCEL_ID = 'sin-demo-001';

interface OfflineState {
  online: boolean;
  readiness: OfflineReadiness;
  /** Fecha de generación del paquete guardado (AAAA-MM-DD), si hay uno. */
  dataDate: string | null;
  /** El paquete guardado y releído, o `null` si todavía no hay uno bueno. Las pantallas leen de aquí, no de un espejo. */
  data: ParcelPackage | null;
  newData: boolean;
  newApp: boolean;
  useNewData: () => void;
  updateApp: () => void;
}

const Ctx = createContext<OfflineState | null>(null);

/** Sin Cache API (página `http` fuera de localhost) los datos viven en memoria: se ven, pero no se guardan. */
const PERSISTENT = typeof window.caches !== 'undefined';
const MEMORY = memoryCaches();

const realDeps = (): Deps => ({
  fetch: window.fetch.bind(window),
  caches: PERSISTENT ? window.caches : MEMORY,
  storage: window.localStorage,
  base: new URL('packages/', document.baseURI).href,
});

export function OfflineProvider({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(() => navigator.onLine);
  const [pkg, setPkg] = useState<PackageStatus>({ kind: 'checking' });
  const shell = useSyncExternalStore(subscribeShell, shellSnapshot);
  const [data, setData] = useState<ParcelPackage | null>(null);

  useEffect(() => {
    registerShell();
    return watchConnectivity(setOnline);
  }, []);

  const load = useCallback(() => {
    if (import.meta.env.DEV) window.localStorage.removeItem(`kinilum.package.${PARCEL_ID}`); // en desarrollo el paquete siempre se baja de nuevo
    // Un fallo inesperado del almacenamiento (modo privado, disco lleno) no debe romper la app: se dice «no pudimos guardar».
    start(realDeps(), PARCEL_ID, setPkg).then(setPkg, () => setPkg({ kind: 'failed' }));
  }, []);
  useEffect(load, [load]);
  // Primera vez sin señal: en cuanto vuelva la señal, se intenta de nuevo.
  useEffect(() => {
    if (online && (pkg.kind === 'needs-signal' || pkg.kind === 'failed')) load();
  }, [online, pkg.kind, load]);

  const savedFile = pkg.kind === 'ready' ? pkg.current.file : null;
  useEffect(() => {
    if (!savedFile) return;
    let alive = true;
    readPackageData(realDeps(), PARCEL_ID).then((d) => alive && setData(d as ParcelPackage | null), () => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [savedFile]);

  const useNewData = useCallback(() => {
    if (pkg.kind !== 'ready' || !pkg.update) return;
    setPkg({ kind: 'downloading' });
    applyUpdate(realDeps(), PARCEL_ID, pkg.update).then(setPkg, () => setPkg({ kind: 'failed' }));
  }, [pkg]);

  const value = useMemo<OfflineState>(
    () => ({
      online,
      readiness: readinessOf(pkg, shell.state, PERSISTENT),
      dataDate: pkg.kind === 'ready' ? pkg.current.generatedAt : null,
      data,
      newData: pkg.kind === 'ready' && !!pkg.update,
      newApp: shell.update,
      useNewData,
      updateApp: applyShellUpdate,
    }),
    [online, pkg, shell, data, useNewData],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useOffline(): OfflineState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useOffline fuera de OfflineProvider');
  return ctx;
}
