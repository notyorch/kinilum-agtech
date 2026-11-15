import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react';
import { watchConnectivity } from './connectivity';
import { applyUpdate, start, type Deps, type PackageStatus } from './packageStore.ts';
import { readinessOf, type OfflineReadiness } from './readiness.ts';
import { applyShellUpdate, registerShell, shellSnapshot, subscribeShell } from './shell';

/** Hoy solo existe la parcela de ejemplo; cuando haya más, el id saldrá de la ruta. */
export const PARCEL_ID = 'yuc-demo-001';

interface OfflineState {
  online: boolean;
  readiness: OfflineReadiness;
  /** Fecha de generación del paquete guardado (AAAA-MM-DD), si hay uno. */
  dataDate: string | null;
  newData: boolean;
  newApp: boolean;
  useNewData: () => void;
  updateApp: () => void;
}

const Ctx = createContext<OfflineState | null>(null);

const realDeps = (): Deps => ({
  fetch: window.fetch.bind(window),
  caches: window.caches,
  storage: window.localStorage,
  base: new URL('packages/', document.baseURI).href,
});

export function OfflineProvider({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(() => navigator.onLine);
  const [pkg, setPkg] = useState<PackageStatus>({ kind: 'checking' });
  const shell = useSyncExternalStore(subscribeShell, shellSnapshot);

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

  const useNewData = useCallback(() => {
    if (pkg.kind !== 'ready' || !pkg.update) return;
    setPkg({ kind: 'downloading' });
    applyUpdate(realDeps(), PARCEL_ID, pkg.update).then(setPkg, () => setPkg({ kind: 'failed' }));
  }, [pkg]);

  const value = useMemo<OfflineState>(
    () => ({
      online,
      readiness: readinessOf(pkg, shell.state),
      dataDate: pkg.kind === 'ready' ? pkg.current.generatedAt : null,
      newData: pkg.kind === 'ready' && !!pkg.update,
      newApp: shell.update,
      useNewData,
      updateApp: applyShellUpdate,
    }),
    [online, pkg, shell, useNewData],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useOffline(): OfflineState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useOffline fuera de OfflineProvider');
  return ctx;
}
