#!/usr/bin/env node
/*
 * Revisión del modo avión sobre dist/ (después de `build-sw`). Falla el build si:
 *   - algún JS, CSS, fuente o imagen de dist/ queda fuera del precache de sw.js (esa pantalla no abriría sin señal);
 *   - sw.js conserva marcas sin reemplazar o el precache incluye algo de packages/;
 *   - el paquete publicado pesa más de 500 KB, lleva polígono o coordenadas, o su nombre no lleva parcela y fecha;
 *   - el índice apunta a un archivo que no existe.
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { shellFiles } from './build-sw.mjs';

const DIST = fileURLToPath(new URL('../dist/', import.meta.url));
const MAX_PACKAGE_BYTES = 500 * 1024;
const NAME_RE = /^[A-Za-z0-9_-]{1,64}\.\d{4}-\d{2}-\d{2}(\.r[2-9]\d*)?\.json$/;
const GEO_KEY = /^(polygon|coordinates|geometry|latitude|longitude|lat|lon|lng)$/i;

const geoKeys = (node, path = '') =>
  node && typeof node === 'object'
    ? Object.entries(node).flatMap(([k, v]) => [...(GEO_KEY.test(k) ? [`${path}/${k}`] : []), ...geoKeys(v, `${path}/${k}`)])
    : [];

export function check(dist = DIST) {
  const errors = [];
  const swPath = join(dist, 'sw.js');
  if (!existsSync(swPath)) return ['falta dist/sw.js: corra `node scripts/build-sw.mjs`'];
  const sw = readFileSync(swPath, 'utf8');
  if (sw.includes('__VERSION__') || sw.includes('__PRECACHE__')) errors.push('sw.js conserva marcas sin reemplazar');
  const precache = JSON.parse(/const PRECACHE = (\[[\s\S]*?\]);/.exec(sw)?.[1] ?? 'null');
  if (!Array.isArray(precache)) return [...errors, 'sw.js no trae la lista PRECACHE'];
  for (const f of shellFiles(dist)) if (!precache.includes(f)) errors.push(`fuera del precache: ${f}`);
  for (const f of precache) {
    if (f.startsWith('packages/')) errors.push(`el paquete no va en el precache: ${f}`);
    if (!existsSync(join(dist, f))) errors.push(`el precache nombra un archivo que no existe: ${f}`);
  }
  if (!precache.includes('index.html')) errors.push('index.html no está en el precache');
  if (!precache.some((f) => f.endsWith('.js'))) errors.push('el precache no trae ningún JS');

  const pkgDir = join(dist, 'packages');
  const index = JSON.parse(readFileSync(join(pkgDir, 'index.json'), 'utf8'));
  for (const [id, { file }] of Object.entries(index.parcels ?? {})) {
    if (!NAME_RE.test(file) || !file.startsWith(`${id}.`)) errors.push(`${file}: el nombre debe llevar la parcela y la fecha`);
    const p = join(pkgDir, file);
    if (!existsSync(p)) {
      errors.push(`${id}: el índice apunta a ${file}, que no existe`);
      continue;
    }
    const bytes = readFileSync(p);
    if (bytes.length > MAX_PACKAGE_BYTES) errors.push(`${file}: pesa ${bytes.length} bytes, el tope es ${MAX_PACKAGE_BYTES}`);
    const geo = geoKeys(JSON.parse(bytes.toString('utf8')));
    if (geo.length) errors.push(`${file}: lleva polígono o coordenadas (${geo.slice(0, 3).join(', ')})`);
  }
  for (const f of readdirSync(pkgDir)) if (f !== 'index.json' && !NAME_RE.test(f)) errors.push(`packages/${f}: nombre sin parcela y fecha`);
  return errors;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const errors = check();
  if (errors.length) {
    console.error(`check-offline: ${errors.length} problema(s)\n- ${errors.join('\n- ')}`);
    process.exit(1);
  }
  console.log('check-offline: el precache cubre dist/ y el paquete cumple el tope y la privacidad');
}
