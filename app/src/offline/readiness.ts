import type { PackageStatus } from './packageStore.ts';
import type { ShellState } from './shell.ts';

export type OfflineReadiness = 'dev' | 'ready' | 'saving' | 'needs-signal' | 'shell-missing' | 'memory' | 'unsupported' | 'failed';

/** «Listo para usar sin señal» exige las DOS cosas: el paquete guardado y releído, y la app guardada y releída. */
/** `persistent`: el navegador tiene Cache API (datos que sobreviven a recargar). Sin ella, los datos solo viven en memoria. */
export function readinessOf(pkg: PackageStatus, shell: ShellState, persistent = true): OfflineReadiness {
  if (shell === 'dev') return 'dev';
  if (pkg.kind === 'unsupported') return 'unsupported';
  if (pkg.kind === 'failed') return 'failed';
  if (pkg.kind === 'needs-signal') return 'needs-signal';
  if (pkg.kind !== 'ready' || shell === 'installing') return 'saving';
  if (!persistent) return 'memory'; // los datos se ven, pero no quedaron guardados
  return shell === 'ready' ? 'ready' : 'shell-missing'; // 'unsupported' o 'failed': los datos están, la app no quedó guardada
}
