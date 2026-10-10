'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

require('../src/core/curves.js');
require('../src/core/model.js');
require('../src/data/default.js');
require('../src/core/calc.js');
const W = globalThis.Waechter;
const { interpolate, expCost } = W.Curves;
const { analyze, primeCost } = W.Calc;
const M = W.Model;

const fresh = () => JSON.parse(JSON.stringify(W.defaultData));
const close = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} ≉ ${b}`);
const el = (data, id) => data.elements.find((e) => e.id === id);
const seal = (parts, extra) => ({ size: 1, carrier: 'body', parts, ...extra });
const e = (id, params) => ({ kind: 'element', id, params });

test('Kostenkurven treffen die Beispielwerte des Autors', () => {
  const d = fresh();
  const cost = (id, params) => primeCost(el(d, id), params).cost;
  close(cost('feuer', { temp: 500 }), 120);
  close(cost('feuer', { temp: 1000 }), 180);
  close(cost('feuer', { temp: 5000 }), 1950);
  close(cost('licht', { lux: 1000 }), 25);
  close(cost('licht', { lux: 10000 }), 100);
  close(cost('licht', { lux: 100000 }), 5000);
  close(cost('wasser', { speed: 0 }), 2);
  close(cost('wasser', { speed: 2 }), 20);
  close(cost('wasser', { speed: 10 }), 100);
  close(cost('luft', { pressure: 1 }), 30);
  close(cost('luft', { pressure: 100 }), 1000);
  close(cost('mystic', { jqm: 777 }), 777);
  close(cost('natura', {}), 10);
});

test('Erde: jedes weitere Kilo kostet das 1,125-Fache; Dunkel startet bei 50', () => {
  const d = fresh();
  close(primeCost(el(d, 'erde'), { mass: 1 }).cost, 1.25);
  close(primeCost(el(d, 'erde'), { mass: 2 }).cost, 1.25 + 1.25 * 1.125);
  close(expCost(1.25, 1.125, 3, true), 1.25 + 1.25 * 1.125 + 1.25 * 1.125 ** 2);
  close(primeCost(el(d, 'dunkel'), { amount: 1 }).cost, 50);
  close(primeCost(el(d, 'dunkel'), { amount: 2 }).cost, 97);
});

test('Kurven zwischen den Punkten sind monoton und werden fortgesetzt', () => {
  const pts = [[500, 120], [1000, 180], [5000, 1950]];
  assert.ok(interpolate(pts, 750) > 120 && interpolate(pts, 750) < 180);
  assert.ok(interpolate(pts, 10000) > 1950);
  assert.ok(interpolate(pts, 250) < 120);
  assert.ok(interpolate([[0, 2], [2, 20]], 1) > 2);
});

test('Rezepte: Eis aus Wasser + Luft in beiden Reihenfolgen, Verschachtelung', () => {
  const d = fresh();
  const idx = M.buildIndex(d);
  assert.equal(M.lookupRecipe(idx, ['wasser', 'luft']).id, 'eis');
  assert.equal(M.lookupRecipe(idx, ['luft', 'wasser']).id, 'eis');
  assert.equal(M.lookupRecipe(idx, ['wasser', 'feuer']), null);
  // Obsidian/Stein: Reihenfolge zählt
  d.elements.push({ id: 'obsidian', name: 'Obsidian', kind: 'derived', recipe: { ingredients: ['lava', 'wasser'], ordered: true } });
  d.elements.push({ id: 'stein', name: 'Stein', kind: 'derived', recipe: { ingredients: ['wasser', 'lava'], ordered: true } });
  const idx2 = M.buildIndex(d);
  assert.equal(M.lookupRecipe(idx2, ['lava', 'wasser']).id, 'obsidian');
  assert.equal(M.lookupRecipe(idx2, ['wasser', 'lava']).id, 'stein');
  const tree = M.expand(idx2, 'obsidian');
  assert.deepEqual(M.primeCounts(tree), { feuer: 1, erde: 1, wasser: 1 });
  assert.equal(tree.levels, 2);
});

test('Kreisrezepte werden erkannt', () => {
  const d = fresh();
  el(d, 'eis').recipe.ingredients = ['lava', 'luft'];
  el(d, 'lava').recipe.ingredients = ['eis', 'erde'];
  assert.ok(M.validate(d).some((p) => p.level === 'error' && /Kreisrezept/.test(p.text)));
});

test('Standarddaten sind gültig', () => {
  assert.deepEqual(M.validate(fresh()).filter((p) => p.level === 'error'), []);
});

test('Typ zählt Teile der obersten Ebene: Eis + Feuer + Wasser = Typ 3', () => {
  const r = analyze(fresh(), seal([e('eis'), e('feuer'), e('wasser')]));
  assert.equal(r.typ, 3);
  assert.deepEqual(r.primes, { wasser: 2, luft: 1, feuer: 1 });
});

test('Typ 8: 5 Elemente + große und 2 kleine Batterien', () => {
  const parts = [e('feuer'), e('erde'), e('licht'), e('dunkel'), e('natura'),
    { kind: 'battery', ref: 'battery_large' }, { kind: 'battery', ref: 'battery_small' }, { kind: 'battery', ref: 'battery_small' }];
  assert.equal(analyze(fresh(), seal(parts)).typ, 8);
});

test('Gegensätze entstehen aus der Zerlegung: Eis + Lava = 3', () => {
  const r = analyze(fresh(), seal([e('eis'), e('lava')]));
  assert.deepEqual(r.oppositions.map((o) => o.text).sort(), [
    'Luft löscht Feuer', 'Wasser ist ineffizient gegen Erde', 'Wasser löscht Feuer',
  ]);
});

test('Feuer + Wasser ist deutlich komplexer als Feuer + Erde', () => {
  const d = fresh();
  const fw = analyze(d, seal([e('feuer'), e('wasser')]));
  const fe = analyze(d, seal([e('feuer'), e('erde')]));
  assert.equal(fe.oppositions.length, 0);
  assert.ok(fw.complexity.total > fe.complexity.total * 2);
  assert.ok(fw.creation > fe.creation * 2);
});

test('Verwoben: Nutzung billiger, Erschaffung teurer als nebeneinander', () => {
  const d = fresh();
  const fused = analyze(d, seal([e('eis')]));
  const apart = analyze(d, seal([e('wasser'), e('luft')]));
  assert.equal(fused.typ, 1);
  assert.equal(apart.typ, 2);
  assert.ok(fused.usage.total < apart.usage.total);
  assert.ok(fused.creation > apart.creation);
});

test('Größe: doppelt so groß = Erschaffung 1,25–2,5-mal billiger, Nutzung 1,1-mal', () => {
  const d = fresh();
  const parts = [e('feuer'), e('wasser'), e('luft')];
  const one = analyze(d, seal(parts, { size: 1 }));
  const two = analyze(d, seal(parts, { size: 2 }));
  const half = analyze(d, seal(parts, { size: 0.5 }));
  const ratio = one.creation / two.creation;
  assert.ok(ratio >= 1.25 && ratio <= 2.5, String(ratio));
  assert.ok(half.creation > one.creation);
  close(one.usage.total / two.usage.total, 1.1);
  // einfaches Siegel spart mehr als komplexes
  const simple = analyze(d, seal([e('erde')], { size: 1 })).creation / analyze(d, seal([e('erde')], { size: 2 })).creation;
  const complex = analyze(d, seal([e('eis'), e('lava'), e('licht'), e('dunkel')], { size: 1 })).creation /
    analyze(d, seal([e('eis'), e('lava'), e('licht'), e('dunkel')], { size: 2 })).creation;
  assert.ok(simple > complex);
});

test('Siegel im Siegel spart weniger durch Größe', () => {
  const d = fresh();
  const inner = seal([e('feuer'), e('erde')]);
  const plain = seal([e('feuer'), e('erde')]);
  const nested = seal([{ kind: 'seal', spec: inner }]);
  const gain = (sp) => analyze(d, { ...sp, size: 1 }).creation / analyze(d, { ...sp, size: 2 }).creation;
  assert.ok(gain(plain) > gain(nested));
  assert.equal(analyze(d, nested).nestDepth, 1);
});

test('Gegenstand: Batterie Pflicht, ohne Generator nur 40–60 % Wirkungsgrad', () => {
  const d = fresh();
  const noBattery = analyze(d, seal([e('feuer')], { carrier: 'object' }));
  assert.ok(noBattery.warnings.some((w) => w.level === 'error'));
  const withBattery = [e('feuer'), { kind: 'battery', ref: 'battery_small' }];
  const plain = analyze(d, seal(withBattery, { carrier: 'object' }));
  const high = analyze(d, seal(withBattery, { carrier: 'object', density: 'high' }));
  const withGen = analyze(d, seal(withBattery.concat({ kind: 'generator', ref: 'generator', source: 'body', level: 'regen' }), { carrier: 'object' }));
  close(plain.usage.efficiency, 0.425);
  close(high.usage.efficiency, 0.6);
  close(withGen.usage.efficiency, 1);
  assert.ok(plain.usage.total > high.usage.total && high.usage.total > withGen.usage.total);
});

test('Generatorquellen: Dauerleistung, Vorrat, Flächenskalierung', () => {
  const d = fresh();
  const gen = (source, level, amount) => ({ kind: 'generator', ref: 'generator', source, level, amount });
  const body = analyze(d, seal([gen('body', 'limit')]));
  close(body.generators.rate, 5);
  const blood = analyze(d, seal([gen('blood', 'ml', 3)]));
  close(blood.generators.stores[0].total, 3000);
  const crystal = analyze(d, seal([gen('crystal', 'standard', 1)]));
  close(crystal.generators.stores[0].total, 300000);
  const sunSmall = analyze(d, seal([gen('sunlight', 'clear')], { size: 1 }));
  const sunBig = analyze(d, seal([gen('sunlight', 'clear')], { size: 2 }));
  close(sunBig.generators.rate / sunSmall.generators.rate, 4);
  // Bewegung ist nicht flächenabhängig
  close(analyze(d, seal([gen('motion', 'run')], { size: 2 })).generators.rate, 8);
});

test('Analyse ist deterministisch und ändert die Daten nicht', () => {
  const d = fresh();
  const before = JSON.stringify(d);
  const sp = seal([e('eis'), e('lava'), e('licht')]);
  assert.equal(JSON.stringify(analyze(d, sp)), JSON.stringify(analyze(d, sp)));
  assert.equal(JSON.stringify(d), before);
});
