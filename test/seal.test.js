'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

for (const f of ['prng', 'core/curves', 'core/model', 'data/default', 'core/calc', 'script', 'seal']) require(`../src/${f}.js`);
const W = globalThis.Waechter;
const fresh = () => JSON.parse(JSON.stringify(W.defaultData));
const e = (id, params) => ({ kind: 'element', id, params: params || {} });
const bat = { kind: 'battery', ref: 'battery_small' };
const build = (parts, extra, opts) => W.Seal.build(fresh(), { size: 1, carrier: 'body', parts, ...extra }, opts);

test('Gleiche Anforderungen ergeben immer dasselbe Bild', () => {
  const a = build([e('feuer'), e('wasser'), bat]);
  const b = build([e('feuer'), e('wasser'), bat]);
  assert.equal(a.svg, b.svg);
  assert.equal(a.meta.id, b.meta.id);
});

test('Reihenfolge der Teile, Größe und Träger ändern das Bild nicht', () => {
  const base = build([e('feuer'), e('wasser'), bat]).svg;
  assert.equal(build([bat, e('wasser'), e('feuer')]).svg, base);
  assert.equal(build([e('feuer'), e('wasser'), bat], { size: 4 }).svg, base);
  assert.equal(build([e('feuer'), e('wasser'), bat], { carrier: 'object' }).svg, base);
});

test('Ausdrücklich gesetzte Standardwerte ändern das Bild nicht', () => {
  assert.equal(build([e('feuer', { feuer: { temp: 500, duration: 1 } })]).svg, build([e('feuer')]).svg);
});

test('Andere Anforderungen ergeben ein anderes Bild', () => {
  const ids = new Set();
  const variants = [
    [e('feuer')], [e('wasser')], [e('feuer'), e('wasser')], [e('feuer'), e('erde')], [e('eis')], [e('wasser'), e('luft')],
    [e('feuer', { feuer: { temp: 1000 } })], [e('feuer'), bat], [e('feuer'), { kind: 'battery', ref: 'battery_large' }],
  ];
  variants.forEach((p) => ids.add(build(p).svg));
  assert.equal(ids.size, variants.length);
  assert.notEqual(build([e('feuer')], {}, { label: 'Ka' }).svg, build([e('feuer')], {}, { label: 'Ro' }).svg);
});

test('Verwoben (Eis) sieht anders aus als nebeneinander (Wasser, Luft)', () => {
  assert.notEqual(build([e('eis')]).svg, build([e('wasser'), e('luft')]).svg);
  assert.equal(build([e('eis')]).meta.parts, 1);
  assert.equal(build([e('wasser'), e('luft')]).meta.parts, 2);
});

test('Mehr Elemente und Gegensätze: mehr Bänder und größeres Siegel', () => {
  const one = build([e('feuer')]);
  const two = build([e('feuer'), e('erde')]);
  const opp = build([e('feuer'), e('wasser')]);
  const many = build([e('eis'), e('lava'), e('licht'), e('natura')]);
  assert.ok(two.meta.radius > one.meta.radius);
  assert.ok(many.meta.radius > two.meta.radius);
  assert.equal(opp.meta.braids, 1);
  assert.equal(two.meta.braids, 0);
  assert.equal(many.meta.braids, 3 - 0); // Eis + Lava ergibt drei Gegensätze, Licht/Natura keine
  assert.ok(opp.meta.bands > two.meta.bands);
  assert.ok(opp.meta.radius > two.meta.radius, 'Gegensatz macht das Siegel größer als eine ruhige Kombination');
});

test('Typ bestimmt die Symmetrie, jedes Teil bekommt einen Kreis', () => {
  const r = build([e('feuer'), e('wasser'), e('erde'), e('luft'), e('licht')]);
  assert.equal(r.meta.symmetry, 5);
  assert.equal((r.svg.match(/<g id="teile">/g) || []).length, 1);
});

test('Beide Platzierungen und alle Stile liefern gültiges SVG ohne NaN', () => {
  const parts = [e('eis'), e('lava'), e('dunkel'), e('mystic'), bat, { kind: 'generator', ref: 'generator', source: 'body', level: 'regen' }];
  for (const placement of ['inner', 'outer']) {
    for (const theme of ['ink', 'color', 'glow']) {
      const r = build(parts, {}, { placement, theme, label: 'Wächter' });
      assert.match(r.svg, /^<svg [^>]*viewBox="/);
      assert.ok(r.svg.endsWith('</svg>'));
      assert.ok(!/NaN|undefined|Infinity/.test(r.svg), `${placement}/${theme}`);
    }
  }
});

test('Leeres Siegel liefert kein Bild', () => {
  assert.equal(build([]).empty, true);
});

// Browser lesen SVG als HTML großzügig, Bild-Export und Editoren (Inkscape) prüfen es als XML.
function wellFormed(svg) {
  const stack = [];
  for (const m of svg.matchAll(/<(\/?)([a-zA-Z][\w:-]*)((?:\s+[\w:-]+="[^"]*")*)\s*(\/?)>/g)) {
    const [, close, name, attrs, self] = m;
    if (close) { if (stack.pop() !== name) return `Schließendes </${name}> ohne Gegenstück`; continue; }
    const seen = new Set();
    for (const a of attrs.matchAll(/\s([\w:-]+)="/g)) {
      if (seen.has(a[1])) return `doppeltes Attribut ${a[1]} in <${name}>`;
      seen.add(a[1]);
    }
    if (!self) stack.push(name);
  }
  const rest = svg.replace(/<(\/?)([a-zA-Z][\w:-]*)((?:\s+[\w:-]+="[^"]*")*)\s*(\/?)>/g, '').replace(/<title>[^<]*<\/title>/, '');
  if (/[<>]/.test(rest.replace(/<\/?title>/g, ''))) return 'unerkannte Tags im SVG';
  return stack.length ? `ungeschlossen: ${stack.join(',')}` : null;
}

test('SVG ist wohlgeformtes XML (keine doppelten Attribute, Tags balanciert)', () => {
  const parts = [e('eis'), e('lava'), e('dunkel'), e('mystic'), e('natura'), bat, { kind: 'battery', ref: 'battery_large' },
    { kind: 'generator', ref: 'generator', source: 'body', level: 'regen' }];
  for (const placement of ['inner', 'outer', 'auto']) {
    for (const theme of ['ink', 'color', 'glow']) {
      assert.equal(wellFormed(build(parts, {}, { placement, theme, label: 'Wächter' }).svg), null, `${placement}/${theme}`);
    }
  }
  assert.equal(wellFormed('<svg><g fill="a" fill="b"/></svg>'), 'doppeltes Attribut fill in <g>');
});

test('Platz je Teil: manche Zeichen innen, manche außen, die Umgebung weicht aus', () => {
  const data = fresh();
  data.elements.find((x) => x.id === 'licht').place = 'inner';
  const parts = [e('feuer'), e('licht'), bat];
  const mixed = W.Seal.build(data, { size: 1, carrier: 'body', parts }, { placement: 'auto' });
  assert.equal(mixed.meta.inside, 2);   // Licht und Batterie
  assert.equal(mixed.meta.outside, 1);  // Feuer
  const allIn = W.Seal.build(data, { size: 1, carrier: 'body', parts }, { placement: 'inner' });
  const allOut = W.Seal.build(data, { size: 1, carrier: 'body', parts }, { placement: 'outer' });
  assert.equal(allIn.meta.outside, 0);
  assert.equal(allOut.meta.inside, 0);
  assert.notEqual(mixed.svg, allIn.svg);
  assert.notEqual(mixed.svg, allOut.svg);
  // außen liegende Zeichen vergrößern die Zeichenfläche, rein innen liegende nicht
  assert.ok(allOut.meta.extent - allOut.meta.radius > allIn.meta.extent - allIn.meta.radius);
  assert.equal(wellFormed(mixed.svg), null);
});
