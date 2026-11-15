#!/usr/bin/env node
/*
 * Genera los tipos de TypeScript desde shared/schema/ (una sola fuente de verdad
 * para el contrato: ARQUITECTURA-DEV §13.1).
 *
 *   npm run gen:schema        escribe src/data/schema.gen.ts
 *   npm run check:schema-gen  falla si el archivo generado no coincide con el esquema
 *
 * No edite schema.gen.ts a mano: cámbielo en shared/schema/ (con la aprobación de Jorge).
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { compile, compileFromFile } from 'json-schema-to-typescript';

const schemaDir = fileURLToPath(new URL('../../shared/schema/', import.meta.url));
const out = fileURLToPath(new URL('../src/data/schema.gen.ts', import.meta.url));
const checkOnly = process.argv.includes('--check');

const banner = `/* eslint-disable */
/*
 * GENERADO por scripts/gen-schema-types.mjs desde shared/schema/. NO lo edite a mano:
 * cambie el esquema (requiere la aprobación de Jorge) y corra \`npm run gen:schema\`.
 */`;

const read = (name) => JSON.parse(readFileSync(`${schemaDir}${name}`, 'utf8'));

/*
 * Un solo esquema para los tipos: el paquete con ContractValue incrustado. Dos cosas se
 * quitan SOLO para generar tipos (el esquema de validación queda intacto):
 *   - `allOf` con if/then (valor nulo ⇒ rango nulo): TypeScript no lo expresa y ensucia el tipo;
 *     lo hace cumplir la validación (ajv y jsonschema), no el tipo.
 *   - las referencias entre archivos, que se vuelven locales.
 */
function bundle() {
  const pkg = read('parcel-package.schema.json');
  const cv = read('contract-value.schema.json');
  const { definitions: cvDefs, $schema: _s, $id: _i, ...cvBody } = cv;
  delete cvBody.allOf;
  const text = JSON.stringify({ ...pkg, definitions: { ...pkg.definitions, ...cvDefs, ContractValue: cvBody } })
    .replaceAll('"contract-value.schema.json#/definitions/', '"#/definitions/')
    .replaceAll('"contract-value.schema.json"', '"#/definitions/ContractValue"');
  const out = JSON.parse(text);
  delete out.$id;
  // Junto a un $ref, una descripción haría que el generador copie el tipo en vez de reutilizarlo.
  const strip = (node) => {
    if (Array.isArray(node)) return node.forEach(strip);
    if (!node || typeof node !== 'object') return;
    if (typeof node.$ref === 'string') for (const k of Object.keys(node)) if (k !== '$ref') delete node[k];
    Object.values(node).forEach(strip);
  };
  strip(out);
  return out;
}

const ts = await compile(bundle(), 'ParcelPackage', {
  cwd: schemaDir,
  bannerComment: banner,
  additionalProperties: false,
  ignoreMinAndMaxItems: true,
  format: true,
  style: { singleQuote: true, semi: true, printWidth: 110 },
});
const indexTs = await compileFromFile(`${schemaDir}package-index.schema.json`, {
  cwd: schemaDir,
  bannerComment: '',
  additionalProperties: false,
  ignoreMinAndMaxItems: true,
  format: true,
  style: { singleQuote: true, semi: true, printWidth: 110 },
});
const text = `${ts.trimEnd()}\n\n${indexTs.trim()}\n`;

if (checkOnly) {
  let current = '';
  try {
    current = readFileSync(out, 'utf8');
  } catch {
    /* no existe */
  }
  if (current.replace(/\r\n/g, '\n') !== text) {
    console.error('src/data/schema.gen.ts no coincide con shared/schema/. Corra `npm run gen:schema`.');
    process.exit(1);
  }
  console.log('  ok    schema.gen.ts coincide con shared/schema/');
} else {
  writeFileSync(out, text);
  console.log(`Escrito ${out}`);
}
