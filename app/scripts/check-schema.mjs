#!/usr/bin/env node
/*
 * Validación de los paquetes contra shared/schema/ (ARQUITECTURA-DEV §4.4:
 * «un dato sin support_level o sin p10/p90 no sale del pipeline»).
 *
 *   npm run check:schema          valida public/packages/ (índice y paquetes) + autoprueba
 *   node scripts/check-schema.mjs <archivo.json>   valida un paquete suelto
 *
 * Lo que el esquema JSON no puede decir lo revisan las comprobaciones de abajo
 * («semánticas»). pipeline/package/validate.py hace las mismas: si cambia una,
 * cambie la otra.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import Ajv from 'ajv';

const SCHEMA_DIR = fileURLToPath(new URL('../../shared/schema/', import.meta.url));
const PACKAGES_DIR = fileURLToPath(new URL('../public/packages/', import.meta.url));
const MAX_PACKAGE_BYTES = 500 * 1024;

const readJson = (p) => JSON.parse(readFileSync(p, 'utf8'));

const ajv = new Ajv({ allErrors: true, strict: true, allowUnionTypes: true });
// El valor del contrato primero: el paquete lo referencia por nombre de archivo.
ajv.addSchema(readJson(join(SCHEMA_DIR, 'contract-value.schema.json')));
const validatePackage = ajv.compile(readJson(join(SCHEMA_DIR, 'parcel-package.schema.json')));
const validateIndex = ajv.compile(readJson(join(SCHEMA_DIR, 'package-index.schema.json')));

const errText = (errors) => (errors ?? []).map((e) => `${e.instancePath || '/'} ${e.message}`).slice(0, 8).join('; ');

/* Comprobaciones que el esquema JSON no expresa ------------------------------ */

export const NAMED = {
  normal: [0, 0],
  dry: [-10, 0],
  veryDry: [-20, 0],
  wet: [10, 0],
  hot: [0, 2],
  dryHot: [-10, 2],
};
const STRATEGIES = ['E0', 'E1', 'E2', 'E3', 'E4', 'E5'];
const CRITERIA = ['water', 'soil', 'erosion', 'climate', 'income'];
/** Cultivo del catálogo que trae cada estrategia (pipeline/simulate/scenarios.py: ROTATION_CROP). */
const ROTATION_CROP = { E2: 'frijol', E3: 'sorgo', E4: 'garbanzo', E5: 'trigo' };
/** Byte de un criterio declarado sin dato (pipeline/simulate/encode.py: NO_DATA). */
const NO_DATA = 255;

/** Devuelve la lista de problemas (vacía = bien). Supone que el esquema ya pasó. */
export function semanticProblems(pkg) {
  const out = [];

  for (const [key, v] of Object.entries(pkg.values)) {
    if (v.value !== null && !(v.p10 <= v.value && v.value <= v.p90)) {
      out.push(`values.${key}: debe cumplirse p10 ≤ value ≤ p90 (${v.p10}, ${v.value}, ${v.p90})`);
    }
  }
  for (const [i, p] of pkg.rain_this_season.projected.entries()) {
    if (!(p.lo <= p.y && p.y <= p.hi)) out.push(`rain_this_season.projected[${i}]: debe cumplirse lo ≤ y ≤ hi`);
  }
  for (const s of pkg.seasons) {
    if (!(s.deficit.p10 <= s.deficit.p50 && s.deficit.p50 <= s.deficit.p90)) out.push(`seasons ${s.year}: deficit debe cumplir p10 ≤ p50 ≤ p90`);
  }

  // Privacidad (ARQUITECTURA-DEV §5.3): a lo más 2 decimales (≈ 1 km) en el punto de referencia.
  for (const n of pkg.reference_point ?? []) {
    if (Math.abs(n * 100 - Math.round(n * 100)) > 1e-9) out.push(`reference_point: ${n} tiene más de 2 decimales (ubicaría la parcela)`);
  }
  if (/"(polygon|geometry|coordinates|lat|lon|lng|latitude|longitude)"\s*:/.test(JSON.stringify(pkg))) {
    out.push('el paquete lleva un campo de polígono o coordenadas: no se publica');
  }

  const m = pkg.map_30m;
  if (m) {
    const cols = m.mask[0].length;
    if (m.mask.some((row) => row.length !== cols)) out.push('map_30m.mask: todas las filas deben medir lo mismo');
    const clean = m.mask.join('').split('c').length - 1;
    if (clean !== pkg.clean_pixels) out.push(`clean_pixels (${pkg.clean_pixels}) no coincide con los cuadros «c» de la máscara (${clean})`);
    for (const [name, layer] of Object.entries(m.layers)) {
      const ok = layer.values.length === m.mask.length && layer.values.every((row) => row.length === cols);
      if (!ok) out.push(`map_30m.layers.${name}: las dimensiones no coinciden con la máscara`);
    }
  }

  const rotation = pkg.rotation;
  if (rotation) {
    for (const [strategy, crop] of Object.entries(ROTATION_CROP)) {
      if (rotation[strategy].rotation_crop !== crop) out.push(`rotation.${strategy}: rotation_crop debe ser ${crop}, no ${rotation[strategy].rotation_crop}`);
    }
  }

  const sim = pkg.simulation;
  if (sim) {
    if (rotation && sim.rules_version !== rotation.rules_version) out.push('simulation.rules_version no coincide con rotation.rules_version');
    // (estrategia, criterio) declarados sin dato: sus bytes valen 255 en todas las corridas.
    const declared = new Set(
      Object.entries(sim.no_data ?? {}).flatMap(([s, criteria]) => criteria.map((c) => STRATEGIES.indexOf(s) * CRITERIA.length + CRITERIA.indexOf(c))),
    );
    const seen = new Set();
    for (const [i, c] of sim.cells.entries()) {
      const key = `${c.rain}/${c.temp}`;
      if (seen.has(key)) out.push(`simulation.cells[${i}]: celda repetida (${key})`);
      seen.add(key);
      const named = Object.entries(NAMED).find(([, [r, t]]) => r === c.rain && t === c.temp)?.[0];
      if (named !== c.scenario) out.push(`simulation.cells[${i}] (${key}): scenario debe ser ${named ?? 'ausente'}, no ${c.scenario ?? 'ausente'}`);
      if (c.runs !== (named ? 500 : 100)) out.push(`simulation.cells[${i}] (${key}): runs debe ser ${named ? 500 : 100}`);
      const bytes = Buffer.from(c.scores, 'base64');
      const rows = STRATEGIES.length * CRITERIA.length;
      if (bytes.length !== rows * c.runs) {
        out.push(`simulation.cells[${i}] (${key}): scores mide ${bytes.length} bytes y debe medir ${rows * c.runs}`);
      } else {
        for (let row = 0; row < rows; row++) {
          const chunk = bytes.subarray(row * c.runs, (row + 1) * c.runs);
          if (declared.has(row)) {
            if (chunk.some((b) => b !== NO_DATA)) {
              out.push(`simulation.cells[${i}] (${key}): un criterio declarado en no_data debe valer ${NO_DATA} en todas las corridas`);
              break;
            }
          } else if (chunk.some((b) => b > 100)) {
            out.push(`simulation.cells[${i}] (${key}): hay puntajes mayores que 100`);
            break;
          }
        }
      }
    }
    if (seen.size !== 49) out.push(`simulation.cells: faltan celdas de la grilla (${seen.size} de 49)`);
  }
  return out;
}

/** Esquema + comprobaciones semánticas + tamaño de un paquete ya leído. */
export function packageProblems(pkg, bytes) {
  if (!validatePackage(pkg)) return [`esquema: ${errText(validatePackage.errors)}`];
  const out = semanticProblems(pkg);
  if (bytes !== undefined && bytes >= MAX_PACKAGE_BYTES) out.push(`pesa ${(bytes / 1024).toFixed(1)} KB (límite 500 KB)`);
  return out;
}

/* Autoprueba: el esquema acepta lo bueno y rechaza lo malo ----------------------- */

/** Bloque `simulation` sintético (bytes pseudoaleatorios fijos): solo prueba la forma, NO es un resultado. */
export function syntheticSimulation() {
  let seed = 7;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) % 101);
  const cells = [];
  for (const rain of [-30, -20, -10, 0, 10, 20, 30]) {
    for (const temp of [-2, -1, 0, 1, 2, 3, 4]) {
      const scenario = Object.entries(NAMED).find(([, [r, t]]) => r === rain && t === temp)?.[0];
      const runs = scenario ? 500 : 100;
      const bytes = Buffer.alloc(STRATEGIES.length * CRITERIA.length * runs);
      for (let i = 0; i < bytes.length; i++) bytes[i] = rnd();
      // El ingreso de E4 y E5 va declarado sin dato: 255 en todas las corridas.
      for (const s of [4, 5]) bytes.fill(NO_DATA, (s * CRITERIA.length + 4) * runs, (s * CRITERIA.length + 5) * runs);
      cells.push({ ...(scenario ? { scenario } : {}), rain, temp, runs, scores: bytes.toString('base64') });
    }
  }
  return {
    strategies: STRATEGIES,
    criteria: CRITERIA,
    rules_version: 'crops.v1',
    no_data: { E4: ['income'], E5: ['income'] },
    cells,
  };
}

function selfTest(base) {
  const results = [];
  const expect = (cond, msg) => results.push([cond, msg]);
  const clone = () => structuredClone(base);

  const good = clone();
  expect(packageProblems(good).length === 0, 'autoprueba: el paquete de ejemplo pasa');

  const withSim = clone();
  withSim.simulation = syntheticSimulation();
  const simOk = packageProblems(withSim, Buffer.byteLength(JSON.stringify(withSim)));
  expect(simOk.length === 0, `autoprueba: un bloque simulation bien formado pasa${simOk.length ? ` (${simOk[0]})` : ''}`);
  console.log(`  info  simulation sintético: ${(Buffer.byteLength(JSON.stringify(withSim)) / 1024).toFixed(0)} KB en total (límite 500 KB)`);

  const noSupport = clone();
  delete noSupport.values.rain.support_level;
  expect(packageProblems(noSupport).length > 0, 'autoprueba: sin support_level se rechaza');

  const noRange = clone();
  delete noRange.values.rain.p10;
  expect(packageProblems(noRange).length > 0, 'autoprueba: sin p10 se rechaza');

  const nullWithRange = clone();
  nullWithRange.values.moisture.p10 = 0.2;
  expect(packageProblems(nullWithRange).length > 0, 'autoprueba: value nulo con rango se rechaza');

  const unordered = clone();
  unordered.values.rain.p10 = 950;
  expect(packageProblems(unordered).some((p) => p.includes('p10 ≤ value')), 'autoprueba: p10 > value se rechaza');

  const badPoint = clone();
  badPoint.reference_point = [-89.62345, 20.97123];
  expect(packageProblems(badPoint).some((p) => p.includes('decimales')), 'autoprueba: punto con más de 2 decimales se rechaza');

  const leaks = clone();
  leaks.polygon = [[1, 2]];
  expect(packageProblems(leaks).length > 0, 'autoprueba: un campo «polygon» se rechaza');

  const over100 = clone();
  over100.simulation = syntheticSimulation();
  const bytes = Buffer.from(over100.simulation.cells[0].scores, 'base64');
  bytes[0] = 101;
  over100.simulation.cells[0].scores = bytes.toString('base64');
  expect(packageProblems(over100).some((p) => p.includes('mayores que 100')), 'autoprueba: un puntaje de 101 se rechaza');

  const undeclared = clone();
  undeclared.simulation = syntheticSimulation();
  delete undeclared.simulation.no_data;
  expect(packageProblems(undeclared).some((p) => p.includes('mayores que 100')), 'autoprueba: un 255 que no está declarado en no_data se rechaza');

  const filled = clone();
  filled.simulation = syntheticSimulation();
  filled.simulation.no_data.E3 = ['income'];
  expect(packageProblems(filled).some((p) => p.includes('no_data')), 'autoprueba: un criterio declarado sin dato pero con puntajes se rechaza');

  const wrongCrop = clone();
  wrongCrop.rotation = { ...wrongCrop.rotation, E4: { rotation_crop: 'trigo' } };
  expect(packageProblems(wrongCrop).some((p) => p.includes('rotation.E4')), 'autoprueba: una estrategia con el cultivo de otra se rechaza');

  const oldCrops = clone();
  oldCrops.restrictions = { ...oldCrops.restrictions, market: ['bean'] };
  expect(packageProblems(oldCrops).length > 0, 'autoprueba: un cultivo fuera del catálogo se rechaza');

  const short = clone();
  short.simulation = syntheticSimulation();
  short.simulation.cells[1].scores = Buffer.alloc(10).toString('base64');
  expect(packageProblems(short).some((p) => p.includes('bytes')), 'autoprueba: scores de otro largo se rechaza');

  return results;
}

/* Programa ---------------------------------------------------------------------- */

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const results = [];
  const check = (cond, msg) => results.push([cond, msg]);
  const arg = process.argv[2];

  if (arg) {
    const text = readFileSync(arg, 'utf8');
    const problems = packageProblems(JSON.parse(text), Buffer.byteLength(text));
    for (const p of problems) console.log(`  FALLA ${p}`);
    console.log(problems.length ? `\n${arg}: ${problems.length} problema(s).` : `  ok    ${arg}`);
    process.exit(problems.length ? 1 : 0);
  }

  const indexPath = join(PACKAGES_DIR, 'index.json');
  check(existsSync(indexPath), 'public/packages/index.json existe');
  let example = null;
  if (existsSync(indexPath)) {
    const index = readJson(indexPath);
    check(validateIndex(index), `índice: cumple el esquema${validateIndex.errors ? ` (${errText(validateIndex.errors)})` : ''}`);
    const listed = new Set(Object.values(index.parcels ?? {}).map((e) => e.file));
    for (const [id, entry] of Object.entries(index.parcels ?? {})) {
      const p = join(PACKAGES_DIR, entry.file);
      if (!existsSync(p)) {
        check(false, `${id}: falta ${entry.file}`);
        continue;
      }
      const text = readFileSync(p, 'utf8');
      const pkg = JSON.parse(text);
      const problems = packageProblems(pkg, Buffer.byteLength(text));
      check(problems.length === 0, `${id}: ${entry.file} cumple el esquema${problems.length ? ` — ${problems.join(' | ')}` : ''}`);
      check(pkg.parcel_id === id && pkg.generated_at === entry.generated_at, `${id}: parcel_id y generated_at coinciden con el índice`);
      example ??= pkg;
    }
    // Un paquete publicado que nadie apunta es un paquete viejo que se coló en dist/.
    const orphans = readdirSync(PACKAGES_DIR).filter((f) => f.endsWith('.json') && f !== 'index.json' && !listed.has(f) && statSync(join(PACKAGES_DIR, f)).isFile());
    check(orphans.length === 0, orphans.length ? `paquetes que el índice no menciona: ${orphans.join(', ')}` : 'ningún paquete huérfano en public/packages/');
  }
  if (example) for (const [ok, msg] of selfTest(example)) check(ok, msg);

  const failed = results.filter(([ok]) => !ok);
  for (const [ok, msg] of results) console.log(`${ok ? '  ok   ' : '  FALLA'} ${msg}`);
  console.log(failed.length ? `\n${failed.length} revisión(es) del esquema fallaron.` : `\nEsquema en regla (${results.length} revisiones).`);
  process.exit(failed.length ? 1 : 0);
}
