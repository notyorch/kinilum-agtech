#!/usr/bin/env node
/*
 * Después de `vite build`: arma dist/sw.js a partir de sw/sw.template.js.
 *   - PRECACHE: todos los archivos de dist/ menos sw.js, mapas y packages/ (el paquete NO va en el precache).
 *   - VERSION: huella del contenido de esos archivos; si cambia algo de la app cambia el service worker.
 * Sin dependencias: ni plugin de PWA ni Workbox.
 */
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const DIST = fileURLToPath(new URL('../dist/', import.meta.url));
const TEMPLATE = fileURLToPath(new URL('../sw/sw.template.js', import.meta.url));

export function shellFiles(dist) {
  const out = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) walk(p);
      else out.push(relative(dist, p).split(sep).join('/'));
    }
  };
  walk(dist);
  return out.filter((f) => f !== 'sw.js' && !f.endsWith('.map') && !f.startsWith('packages/'));
}

export function build(dist = DIST) {
  const files = shellFiles(dist);
  const hash = createHash('sha256');
  for (const f of files) hash.update(f).update(readFileSync(join(dist, f)));
  const version = hash.digest('hex').slice(0, 12);
  const sw = readFileSync(TEMPLATE, 'utf8').replace('__VERSION__', version).replace('__PRECACHE__', JSON.stringify(files, null, 2));
  writeFileSync(join(dist, 'sw.js'), sw);
  return { version, files };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { version, files } = build();
  console.log(`sw.js: versión ${version}, ${files.length} archivos en el precache`);
}
