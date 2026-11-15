// Pruebas de los datos de la app: `npm test` (Node carga los .ts sin compilar).
// Comprueban que el espejo de la app dice lo mismo que el catálogo de cultivos
// y que las reglas del producto se cumplen con las seis estrategias.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { parse } from 'yaml';

import { CRITERIA, OBJECTIVES, STRATEGIES } from '../src/data/comparison.ts';
import { BEAN_VARIANTS, CROPS, CROP_IDS, DEFAULT_BEAN_VARIANT, RULES_VERSION } from '../src/data/crops.ts';
import { PARCEL, RULES, excludedSet, flagsFor, reasonsFor } from '../src/data/restrictions.ts';
import {
  NAMED,
  RAIN_STEPS,
  TEMP_STEPS,
  namedScenario,
  nitrogenBonus,
  scenarioResult,
  scoresAt,
  total,
} from '../src/data/scenarios.ts';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const catalog = parse(read('../../pipeline/rules/crops.v2.yaml'));
const parcel = parse(read('../../pipeline/parcels/sin-demo-001.yaml'));
const index = JSON.parse(read('../public/packages/index.json'));
const published = JSON.parse(read(`../public/packages/${index.parcels['sin-demo-001'].file}`));
const es = JSON.parse(read('../src/i18n/strategies.es.json'));
const en = JSON.parse(read('../src/i18n/strategies.en.json'));

const sorted = (xs) => [...xs].sort();

/* ---- El espejo de la app y el catálogo dicen lo mismo ------------------- */

test('crops.ts es el espejo de pipeline/rules/crops.v2.yaml', () => {
  assert.equal(catalog.rules_version, RULES_VERSION);
  assert.deepEqual(sorted(Object.keys(catalog.cultivos)), sorted(CROP_IDS));
  for (const id of CROP_IDS) {
    const c = catalog.cultivos[id];
    assert.deepEqual(
      CROPS[id],
      {
        tipo: c.tipo,
        estrategia: c.estrategia,
        fijaNitrogeno: c.fija_nitrogeno,
        exigeMaquinaria: c.exige_maquinaria,
        requiereVenta: c.requiere_venta,
        cicloDias: c.ciclo_dias,
        estadoEvidencia: c.estado_evidencia,
      },
      id,
    );
  }
});

test('las reglas de la app son las del catálogo', () => {
  assert.deepEqual(sorted(catalog.reglas.map((r) => r.id)), sorted(RULES.map((r) => r.catalogId)));
  for (const rule of RULES) {
    const c = catalog.reglas.find((r) => r.id === rule.catalogId);
    const crops = rule.effect === 'exclude' ? c.excluye : c.marca_poco_viable;
    assert.deepEqual(sorted(crops), sorted(rule.crops), rule.catalogId);
    assert.equal(c.estado_evidencia, rule.evidence, rule.catalogId);
  }
});

test('la declaración de la app es la del paquete publicado y la de la parcela', () => {
  const { restrictions, rotation } = published;
  // Paquete publicado (lo arma pipeline/package/build.py)…
  assert.deepEqual(PARCEL, {
    soil: restrictions.soil,
    extremeHeat: restrictions.extreme_heat,
    machinery: restrictions.machinery,
    accepted: restrictions.cultivos_aceptados,
    market: restrictions.market,
    beanVariant: rotation.E2.variant,
    beanVariantChosenBy: rotation.E2.variant_chosen_by,
  });
  assert.equal(rotation.rules_version, RULES_VERSION);
  // …que sale de lo que declara el técnico en pipeline/parcels/sin-demo-001.yaml.
  assert.equal(parcel.frijol_variante, PARCEL.beanVariant);
  assert.deepEqual(parcel.cultivos_aceptados, PARCEL.accepted);
  assert.deepEqual(parcel.market, PARCEL.market);
  assert.equal(parcel.illustrative, true);
  assert.equal(published.illustrative, true);
});

test('las estrategias de la app traen el cultivo que dice el paquete', () => {
  for (const id of CROP_IDS) assert.equal(published.rotation[CROPS[id].estrategia].rotation_crop, id);
});

/* ---- Variantes del frijol regional -------------------------------------- */

test('la variante de frijol es un perfil completo y el frijol negro es la variante por defecto de Sinaloa', () => {
  const { variantes, variante_por_defecto } = catalog.cultivos.frijol;
  assert.deepEqual(sorted(Object.keys(variantes)), sorted(BEAN_VARIANTS));
  assert.equal(variante_por_defecto, DEFAULT_BEAN_VARIANT);
  assert.equal(DEFAULT_BEAN_VARIANT, 'negro');
  const params = ['kc_por_etapa', 'profundidad_raiz_m', 'ventana_siembra', 'ciclo_dias', 'umbral_calor_c', 'rendimiento_t_ha', 'precio_mxn_t'];
  for (const v of BEAN_VARIANTS) {
    for (const p of params) assert.ok(p in variantes[v], `${v}.${p}`);
    assert.equal(variantes[v].estado_evidencia, 'a_validar');
  }
});

test('el nombre de E2 sale de la variante de frijol elegida', () => {
  const names = BEAN_VARIANTS.map((v) => es.variants[v].E2.name);
  assert.equal(new Set(names).size, BEAN_VARIANTS.length);
  assert.match(es.variants.negro.E2.name, /frijol negro/);
});

/* ---- Nitrógeno ---------------------------------------------------------- */

test('sorgo y trigo no reciben bonificación de nitrógeno; frijol y garbanzo sí', () => {
  assert.equal(nitrogenBonus('E3'), 0);
  assert.equal(nitrogenBonus('E5'), 0);
  assert.equal(nitrogenBonus('E0'), 0);
  assert.ok(nitrogenBonus('E2') > 0);
  assert.ok(nitrogenBonus('E4') > 0);
  for (const id of ['E3', 'E5']) {
    for (const lang of [es, en]) {
      for (const benefit of lang.strategies[id].benefits) assert.doesNotMatch(benefit, /nitr[óo]gen/i, `${id}: ${benefit}`);
    }
  }
});

/* ---- Seis estrategias en la grilla de escenarios ------------------------ */

test('cada estrategia tiene sus 49 celdas y ninguna se oculta', () => {
  assert.equal(STRATEGIES.length, 6);
  let cells = 0;
  for (const rain of RAIN_STEPS) {
    for (const temp of TEMP_STEPS) {
      cells += 1;
      for (const objective of OBJECTIVES) {
        const r = scenarioResult(objective, rain, temp, excludedSet(PARCEL));
        assert.deepEqual(sorted([...r.order, ...r.unranked, ...r.excluded]), sorted(STRATEGIES));
        assert.equal(r.runs, namedScenario(rain, temp) ? 500 : 100);
        assert.equal(Object.values(r.firstCount).reduce((a, b) => a + b, 0), r.order.length ? r.runs : 0);
        for (const id of STRATEGIES) {
          for (const c of CRITERIA) {
            const v = r.scores[id][c];
            assert.ok(v === null || (v >= 0 && v <= 100), `${id}.${c} = ${v}`);
          }
        }
      }
    }
  }
  assert.equal(cells, 49);
  assert.equal(Object.keys(NAMED).length, 6);
});

/* ---- Sin dato: se declara, no se inventa y no falla --------------------- */

test('un criterio sin parámetros queda «sin dato» y la comparación no falla', () => {
  for (const id of ['E4', 'E5']) {
    const s = scoresAt(id, 0, 0);
    assert.equal(s.income, null);
    // Con poco peso en el criterio que falta, se ordena con los demás.
    assert.equal(typeof total(s, 'water'), 'number');
    // Si lo que falta pesa demasiado en el objetivo, no se ordena.
    assert.equal(total(s, 'income'), null);
  }
  const everything = scenarioResult('income', 0, 0);
  assert.deepEqual(sorted(everything.unranked), ['E4', 'E5']);
  const nothing = { water: null, soil: null, erosion: null, climate: null, income: null };
  assert.equal(total(nothing, 'balanced'), null);
});

/* ---- Restricciones ------------------------------------------------------ */

test('en el caso ilustrativo, garbanzo y trigo quedan excluidos por no tener dónde vender, con su razón, nunca ocultos', () => {
  const r = scenarioResult('water', 0, 0, excludedSet(PARCEL));
  assert.deepEqual(sorted(r.excluded), ['E4', 'E5']);
  for (const id of ['E4', 'E5']) {
    assert.deepEqual(reasonsFor(id, PARCEL).map((x) => x.rule), ['noMarket']);
    assert.deepEqual(flagsFor(id, PARCEL), []); // la regla de calor y suelo delgado no aplica a Guasave y se quitó
  }
});

test('sin maquinaria salen sorgo y trigo; sin dónde vender salen los cuatro cultivos', () => {
  const everywhere = { ...PARCEL, market: [...CROP_IDS] };
  assert.deepEqual(sorted(excludedSet({ ...everywhere, machinery: 'manual' })), ['E3', 'E5']);
  assert.deepEqual(sorted(excludedSet({ ...PARCEL, market: [] })), ['E2', 'E3', 'E4', 'E5']);
  assert.deepEqual(sorted(excludedSet({ ...everywhere, accepted: [] })), ['E2', 'E3', 'E4', 'E5']);
  assert.equal(excludedSet(everywhere).size, 0);
  // Ya no hay reglas de «poco viable»: la de calor y suelo delgado no aplica a Guasave.
  for (const id of STRATEGIES) assert.deepEqual(flagsFor(id, PARCEL), []);
});

test('todas las reglas de cultivo siguen «a validar» mientras no tengan fuente', () => {
  for (const rule of catalog.reglas) {
    if (rule.fuente === null) assert.equal(rule.estado_evidencia, 'a_validar', rule.id);
  }
  for (const rule of RULES) assert.ok(es.rules[rule.id], rule.id);
});

/* ---- Textos ------------------------------------------------------------- */

const keysOf = (x, path = '') =>
  x && typeof x === 'object'
    ? Object.entries(x).flatMap(([k, v]) => keysOf(v, `${path}/${k}`))
    : [path];

const strings = (x) => (typeof x === 'string' ? [x] : x && typeof x === 'object' ? Object.values(x).flatMap(strings) : []);

test('strategies.es.json y strategies.en.json tienen las mismas claves', () => {
  assert.deepEqual(keysOf(es), keysOf(en));
  assert.deepEqual(sorted(Object.keys(es.strategies)), sorted(STRATEGIES));
});

test('E4 y E5 no dicen que el cultivo es poco común (en Sinaloa se siembran) y sí que faltan sus fechas y ciclo locales', () => {
  for (const id of ['E4', 'E5']) {
    for (const lang of [es, en]) {
      assert.doesNotMatch(lang.strategies[id].missing.join(' '), /poco común|uncommon/i);
    }
    assert.match(es.strategies[id].missing[0], /fechas de siembra y su ciclo/);
    assert.match(es.strategies[id].missing[0], /del municipio, no de su parcela/);
    assert.match(en.strategies[id].missing[0], /sowing dates and cycle/);
  }
});

test('ningún texto nombra una fuente que todavía no está integrada, ni un lugar o suelo de Yucatán', () => {
  const all = [...strings(es.strategies), ...strings(en.strategies)].join('\n');
  assert.doesNotMatch(all, /MODIS|ECOSTRESS|GRACE|SRTM|SIAP/, 'fuentes sin integrar');
  assert.doesNotMatch(all, /Yucat|tsek|k.ankab|milpa|caliza|limestone|xpel/i);
});

test('los textos en español pasan la lectura de «doña Rosa»', () => {
  const { _nota, ...texts } = es;
  for (const text of strings(texts)) {
    assert.doesNotMatch(text, /[!¡]/, text);
    assert.doesNotMatch(text, /\p{Extended_Pictographic}/u, text);
    for (const sentence of text.split(/(?<=[.:])\s+/)) {
      const words = sentence.split(/\s+/).filter((w) => /\p{L}|\d/u.test(w)).length;
      assert.ok(words <= 20, `${words} palabras: ${sentence}`);
    }
  }
});
