// Español e inglés dicen lo mismo: mismas claves, nada sin traducir y la misma voz (frases cortas, sin exclamaciones).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { en } from '../src/i18n/en.ts';
import { es } from '../src/i18n/es.ts';

const flat = (x, path = '') =>
  x && typeof x === 'object' ? Object.entries(x).flatMap(([k, v]) => flat(v, `${path}.${k}`)) : [[path, x]];

const esFlat = new Map(flat(es));
const enFlat = new Map(flat(en));

// Lo que se escribe igual en los dos idiomas (marca, unidades, símbolos).
const SAME = new Set(['.app.name', '.simular.rainMin', '.simular.rainMid', '.simular.rainMax', '.simular.heatMin', '.simular.heatMid', '.simular.heatMax', '.parcela.rain.unit', '.simular.waterMin', '.simular.waterMax']);

test('en.ts trae exactamente las mismas claves que es.ts', () => {
  assert.deepEqual([...enFlat.keys()].sort(), [...esFlat.keys()].sort());
});

test('los tipos de cada clave coinciden (texto con texto, función con función)', () => {
  for (const [k, v] of esFlat) assert.equal(typeof enFlat.get(k), typeof v, k);
});

test('ningún texto del inglés quedó en español', () => {
  for (const [k, v] of enFlat) {
    if (typeof v !== 'string') continue;
    if (!SAME.has(k)) assert.notEqual(v, esFlat.get(k), `sin traducir: ${k}`);
    assert.doesNotMatch(v, /[áéíóúñ¿¡]/i, `${k}: ${v}`);
  }
});

test('las funciones de texto devuelven frases distintas en cada idioma', () => {
  assert.notEqual(en.comparar.firstIn(3), es.comparar.firstIn(3));
  assert.match(en.comparar.firstIn(3), /3 out of 10/);
  assert.match(en.simular.rainText(-10), /10 % less rain/);
  assert.match(en.simular.heatText(2), /2 degrees warmer/);
  assert.match(en.simular.heatText(1), /1 degree warmer/);
  assert.match(en.comparar.excludedNote(1), /^One option is/);
  assert.match(en.comparar.excludedNote(2), /^2 options are/);
  assert.match(en.parcela.rain.detail(900, 1100), /between 900 and 1100 mm/);
});

test('el inglés conserva la voz: sin exclamaciones ni emoji, frases de 20 palabras o menos, kinilum en minúsculas', () => {
  const texts = [...enFlat.values()].filter((v) => typeof v === 'string');
  // También las frases que arman las funciones.
  texts.push(en.comparar.firstIn(4), en.comparar.excludedNote(2), en.simular.movedBy('water'), en.parcela.soil.measured(80), en.parcela.rain.detail(900, 1100));
  for (const text of texts) {
    assert.doesNotMatch(text, /!/, text);
    assert.doesNotMatch(text, /\p{Extended_Pictographic}/u, text);
    assert.doesNotMatch(text, /Kinilum|KINILUM/, text);
    for (const sentence of text.split(/(?<=[.:])\s+/)) {
      const words = sentence.split(/\s+/).filter((w) => /\p{L}|\d/u.test(w)).length;
      assert.ok(words <= 20, `${words} words: ${sentence}`);
    }
  }
});
