// El resultado que sale de las corridas del paquete publicado: mismo formato que el ejemplo, y lo que no tiene dato no se ordena.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { OBJECTIVES, STRATEGIES } from '../src/data/comparison.ts';
import { PARCEL, excludedSet } from '../src/data/restrictions.ts';
import { RAIN_STEPS, TEMP_STEPS, namedScenario, scenarioResult } from '../src/data/scenarios.ts';
import { scenarioResultFromSimulation } from '../src/data/simulation.ts';

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'));
const index = read('../public/packages/index.json');
const published = read(`../public/packages/${index.parcels['sin-demo-001'].file}`);
const sim = published.simulation;
const none = new Set();

test('el paquete publicado trae las 49 celdas y cada una se puede leer', () => {
  assert.equal(sim.cells.length, 49);
  for (const rain of RAIN_STEPS) {
    for (const temp of TEMP_STEPS) {
      const r = scenarioResultFromSimulation(sim, 'water', rain, temp, none);
      assert.equal(r.runs, namedScenario(rain, temp) ? 500 : 100); // las 6 con nombre llevan 500 corridas y las demás, 100
    }
  }
});

test('tiene la misma forma que el resultado de ejemplo', () => {
  const real = scenarioResultFromSimulation(sim, 'water', 0, 0, none);
  const example = scenarioResult('water', 0, 0, none);
  assert.deepEqual(Object.keys(real).sort(), Object.keys(example).sort().filter((k) => k !== 'separatingData' || 'separatingData' in real));
});

test('ahorrar agua: el frijol pide menos riego y el sorgo, más; E1 no se ordena porque no tiene datos', () => {
  const r = scenarioResultFromSimulation(sim, 'water', 0, 0, none);
  assert.equal(r.order[0], 'E2');
  assert.equal(r.order.at(-1), 'E3');
  assert.deepEqual([...r.order].sort(), ['E0', 'E2', 'E3', 'E4', 'E5']);
  assert.deepEqual(r.unranked, ['E1']);
  assert.equal(Object.values(r.firstCount).reduce((a, b) => a + b, 0), r.runs);
  assert.equal(r.scores.E1.water, null);
  assert.equal(r.scores.E0.soil, null); // suelo, erosión y clima: sin dato en todas
  for (const id of ['E0', 'E2', 'E3', 'E4', 'E5']) {
    assert.ok(r.scores[id].water >= 0 && r.scores[id].water <= 100, id);
    assert.ok(r.scores[id].income >= 0 && r.scores[id].income <= 100, id);
  }
});

test('ingreso: el maíz solo da más ingreso bruto que las rotaciones', () => {
  const r = scenarioResultFromSimulation(sim, 'income', 0, 0, none);
  assert.equal(r.order[0], 'E0');
  assert.ok(r.scores.E0.income > r.scores.E2.income);
});

test('los objetivos que dependen de criterios sin dato no ordenan a nadie: se dice, no se inventa', () => {
  for (const o of ['soil', 'risk', 'balanced']) {
    const r = scenarioResultFromSimulation(sim, o, 0, 0, none);
    assert.deepEqual(r.order, [], o);
    assert.equal(r.unranked.length, 6, o);
  }
});

test('las excluidas por restricciones siguen visibles y no compiten', () => {
  const r = scenarioResultFromSimulation(sim, 'water', 0, 0, excludedSet(PARCEL));
  assert.deepEqual([...r.excluded].sort(), ['E4', 'E5']);
  assert.ok(!r.order.includes('E4') && !r.order.includes('E5'));
  assert.deepEqual([...r.order, ...r.unranked, ...r.excluded].sort(), [...STRATEGIES].sort());
});

test('en todos los objetivos las seis estrategias quedan repartidas y nunca desaparece una', () => {
  for (const o of OBJECTIVES) {
    for (const [rain, temp] of [[0, 0], [-20, 0], [-10, 2], [30, 4]]) {
      const r = scenarioResultFromSimulation(sim, o, rain, temp, excludedSet(PARCEL));
      assert.deepEqual([...r.order, ...r.unranked, ...r.excluded].sort(), [...STRATEGIES].sort(), `${o} ${rain} ${temp}`);
    }
  }
});

test('el paquete declara qué no se calculó', () => {
  assert.deepEqual(sim.no_data.E1.sort(), ['climate', 'erosion', 'income', 'soil', 'water']);
  for (const id of ['E0', 'E2', 'E3', 'E4', 'E5']) assert.deepEqual(sim.no_data[id].sort(), ['climate', 'erosion', 'soil']);
  assert.match(sim.generator, /simulate\.run/);
  assert.equal(sim.rules_version, published.rotation.rules_version);
});

/* ---- Con menos agua de riego -------------------------------------------- */
import { SUPPLY_STEPS, coverageAt, referenceMm } from '../src/data/irrigation.ts';

test('el agua de referencia es lo que hoy pide el maíz solo: un valor creíble, cerca de los 446 mm netos del INIFAP', () => {
  const ref = referenceMm(sim);
  assert.ok(ref > 380 && ref < 500, `${ref}`);
});

test('con toda el agua que hoy pide el maíz, el maíz cubre lo que pide y las rotaciones que piden menos también', () => {
  const c = coverageAt(sim, 0, 0, 100);
  assert.equal(c.E0.mid, 1);
  assert.equal(c.E2.mid, 1);
  assert.equal(c.E1, null); // sin dato: no aparece con un número
});

test('con menos agua, cubren menos, y el frijol cubre más que el maíz solo; el sorgo, menos', () => {
  const full = coverageAt(sim, 0, 0, 100);
  const cut = coverageAt(sim, 0, 0, 60);
  assert.ok(cut.E0.mid < 1 && Math.abs(cut.E0.mid - 0.6) < 0.001);
  assert.ok(cut.E2.mid > cut.E0.mid && cut.E3.mid < cut.E0.mid);
  for (const id of ['E0', 'E2', 'E3', 'E4', 'E5']) {
    assert.ok(cut[id].mid <= full[id].mid, id);
    assert.ok(cut[id].low <= cut[id].mid && cut[id].mid <= cut[id].high, id); // año muy seco ≤ típico ≤ húmedo
    assert.ok(cut[id].low >= 0 && cut[id].high <= 1, id);
  }
});

test('el recorte se puede combinar con el clima: los 7 pasos y las 49 celdas se pueden leer', () => {
  for (const pct of SUPPLY_STEPS) {
    for (const rain of RAIN_STEPS) for (const temp of TEMP_STEPS) assert.ok(coverageAt(sim, rain, temp, pct).E0, `${pct} ${rain} ${temp}`);
  }
});

test('un paquete sin water_mm no inventa cobertura', () => {
  const old = { ...sim, cells: sim.cells.map(({ water_mm, ...rest }) => rest) };
  assert.equal(referenceMm(old), null);
  assert.ok(Object.values(coverageAt(old, 0, 0, 60)).every((v) => v === null));
});
