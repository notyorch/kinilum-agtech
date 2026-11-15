import type { PackageStatus } from './packageStore.ts';
import type { ShellState } from './shell.ts';

export type OfflineReadiness = 'dev' | 'ready' | 'saving' | 'needs-signal' | 'shell-missing' | 'unsupported' | 'failed';

/** «Listo para usar sin señal» exige las DOS cosas: el paquete guardado y releído, y la app guardada y releída. */
export function readinessOf(pkg: PackageStatus, shell: ShellState): OfflineReadiness {
  if (shell === 'dev') return 'dev';
  if (pkg.kind === 'unsupported') return 'unsupported';
  if (pkg.kind === 'failed') return 'failed';
  if (pkg.kind === 'needs-signal') return 'needs-signal';
  if (pkg.kind !== 'ready' || shell === 'installing') return 'saving';
  return shell === 'ready' ? 'ready' : 'shell-missing'; // 'unsupported' o 'failed': los datos están, la app no quedó guardada
}
