'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const zlib = require('node:zlib');

for (const f of ['prng', 'core/curves', 'core/model', 'data/default', 'core/calc', 'script', 'seal', 'decode']) require(`../src/${f}.js`);
const W = globalThis.Waechter;
const D = W.Decode;
const fresh = () => JSON.parse(JSON.stringify(W.defaultData));
const e = (id, params) => ({ kind: 'element', id, params: params || {} });
const bat = { kind: 'battery', ref: 'battery_small' };
const crystal = { kind: 'carried', source: 'crystal', level: 'standard', amount: 1 };

function sealWith(parts, options, extra) {
  const data = fresh();
  const spec = { size: 2, carrier: 'object', parts, ...extra };
  const opts = { theme: 'color', label: '', placement: 'auto', ...options };
  const r = W.Seal.build(data, spec, opts);
  return { data, spec, opts, r, payload: D.makePayload(data, spec, opts, r.meta.id) };
}

// kleines gültiges PNG (1×1) für die Chunk-Tests
function tinyPng() {
  const chunk = (type, data) => {
    const b = Buffer.alloc(12 + data.length);
    b.writeUInt32BE(data.length, 0);
    b.write(type, 4, 'latin1');
    data.copy(b, 8);
    b.writeUInt32BE(D.crc32(b, 4, 8 + data.length), 8 + data.length);
    return b;
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(1, 0); ihdr.writeUInt32BE(1, 4); ihdr[8] = 8; ihdr[9] = 6;
  const idat = zlib.deflateSync(Buffer.from([0, 255, 0, 0, 255]));
  return new Uint8Array(Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', idat), chunk('IEND', Buffer.alloc(0))]));
}

test('SVG: Nutzlast wird eingebettet und unverändert wieder gelesen', () => {
  const { r, payload } = sealWith([e('eis'), e('lava'), bat], { label: 'Kaelen & Söhne <1>' });
  const svg = D.embedInSvg(r.svg, payload);
  assert.deepEqual(D.extractFromSvg(svg), payload);
  assert.equal(D.stripSvgMetadata(svg), r.svg, 'ohne Metadaten bleibt das Bild bitgleich');
  // Sonderzeichen in der Nutzlast dürfen das XML nicht brechen
  assert.ok(!/<metadata[^>]*>[^<]*[<>][^<]*<\/metadata>/.test(svg.replace(/&lt;|&gt;|&amp;/g, '')));
  const read = D.readSealFile(new TextEncoder().encode(svg));
  assert.equal(read.type, 'svg');
  assert.deepEqual(read.payload, payload);
});

test('Erklärung: Typ, Teile, Urelemente, Gegensätze, Texte', () => {
  const { payload } = sealWith([e('eis'), e('lava'), bat, crystal], { label: 'Kaelen Wächter' });
  const x = D.explain(payload);
  assert.equal(x.typ, 3);
  assert.equal(x.idMatches, true);
  assert.deepEqual(x.parts.map((p) => p.name).sort(), ['Eis', 'Kleine Batterie', 'Lava']);
  assert.deepEqual(x.parts.find((p) => p.name === 'Eis').recipe, 'Eis = Wasser + Luft');
  assert.equal(x.parts.find((p) => p.name === 'Lava').recipe, 'Lava = Feuer + Erde');
  assert.deepEqual(x.primes.map((p) => p.name).sort(), ['Erde', 'Feuer', 'Luft', 'Wasser']);
  assert.deepEqual(x.oppositions.slice().sort(), ['Luft löscht Feuer', 'Wasser ist ineffizient gegen Erde', 'Wasser löscht Feuer']);
  assert.deepEqual(x.inscription, { words: ['kaelen', 'wächter'], fromLabel: true });
  assert.deepEqual(x.circles.slice().sort(), ['eis', 'kleinebatterie', 'lava']);
  assert.deepEqual(x.circleNames.slice().sort(), ['Eis', 'Kleine Batterie', 'Lava']);
  assert.equal(x.carrier, 'Gegenstand');
  assert.equal(x.size, 2);
  assert.equal(x.carried.length, 1);
  assert.equal(x.carried[0].total, 300000);
  assert.match(x.carried[0].hazard, /150 km/);
  assert.ok(x.creation > 0 && x.usage.total > 0);
});

test('Ohne Inschrift stehen die Namen der Teile im Ring', () => {
  const x = D.explain(sealWith([e('feuer'), e('wasser')], { label: '' }).payload);
  assert.equal(x.inscription.fromLabel, false);
  assert.deepEqual(x.inscription.words.slice().sort(), ['feuer', 'wasser']);
});

test('Verschachtelte Rezepte werden lesbar erklärt (Reihenfolge zählt)', () => {
  const data = fresh();
  data.elements.push({ id: 'obsidian', name: 'Obsidian', kind: 'derived', recipe: { ingredients: ['lava', 'wasser'], ordered: true } });
  const spec = { size: 1, carrier: 'body', parts: [e('obsidian')] };
  const opts = { theme: 'ink', label: '', placement: 'auto' };
  const payload = D.makePayload(data, spec, opts, W.Seal.build(data, spec, opts).meta.id);
  const x = D.explain(payload);
  assert.equal(x.parts[0].recipe, 'Obsidian = Lava (Feuer + Erde) → Wasser');
  assert.equal(x.typ, 1);
  assert.equal(x.oppositions.length, 2); // Feuer und Erde gegen Wasser: löscht, ineffizient
});

test('Veränderte Angaben fallen auf: Siegel-ID passt nicht mehr', () => {
  const { payload } = sealWith([e('feuer'), e('wasser'), bat]);
  const forged = JSON.parse(JSON.stringify(payload));
  forged.spec.parts.pop();
  assert.equal(D.explain(forged).idMatches, false);
  const edited = JSON.parse(JSON.stringify(payload));
  edited.options.label = 'andere Worte';
  assert.equal(D.explain(edited).idMatches, false);
});

test('Erklärung hängt nur von den eingebetteten Regeln ab, nicht von späteren Änderungen', () => {
  const { payload } = sealWith([e('eis'), bat]);
  const before = JSON.stringify(D.explain(payload).parts);
  W.defaultData.elements.find((x) => x.id === 'eis').name = 'Frost';
  try {
    assert.equal(JSON.stringify(D.explain(payload).parts), before);
  } finally {
    W.defaultData.elements.find((x) => x.id === 'eis').name = 'Eis';
  }
});

test('PNG: Nutzlast wird als gültiger iTXt-Block eingebettet und gelesen', () => {
  const png = tinyPng();
  assert.equal(D.extractFromPng(png), null);
  const { payload } = sealWith([e('licht'), bat], { label: 'Ka' });
  const out = D.embedInPng(png, payload);
  assert.ok(out.length > png.length);
  assert.deepEqual(D.extractFromPng(out), payload);
  // Chunk-Struktur: IHDR zuerst, alle Prüfsummen stimmen, IEND am Ende
  let pos = 8; const types = [];
  while (pos < out.length) {
    const len = new DataView(out.buffer, out.byteOffset).getUint32(pos);
    const type = String.fromCharCode(...out.slice(pos + 4, pos + 8));
    const crc = new DataView(out.buffer, out.byteOffset).getUint32(pos + 8 + len);
    assert.equal(D.crc32(out, pos + 4, pos + 8 + len), crc, `CRC von ${type}`);
    types.push(type); pos += 12 + len;
  }
  assert.deepEqual(types, ['IHDR', 'iTXt', 'IDAT', 'IEND']);
  assert.equal(pos, out.length);
  const read = D.readSealFile(out);
  assert.equal(read.type, 'png');
  assert.deepEqual(read.payload, payload);
});

test('Nicht lesbare Dateien: PNG ohne Daten, fremde Dateien, kaputte Daten', () => {
  assert.deepEqual(D.readSealFile(tinyPng()), { type: 'png', payload: null, error: null });
  assert.equal(D.readSealFile(new TextEncoder().encode('Hallo Welt')).type, 'unknown');
  assert.equal(D.readSealFile(new Uint8Array([1, 2, 3])).type, 'unknown');
  const broken = '<svg xmlns="http://www.w3.org/2000/svg"><metadata id="waechter-siegel">{kaputt</metadata></svg>';
  const r = D.readSealFile(new TextEncoder().encode(broken));
  assert.equal(r.payload, null);
  assert.match(r.error, /beschädigt/);
  assert.throws(() => D.explain({ format: 'waechter-siegel', spec: { parts: [] } }), /unvollständig/);
  assert.throws(() => D.explain({ format: 'anderes' }), /keine Siegeldatei/);
});

// Der Ring ist ein Kreis: bei Lücken ist nur die Reihenfolge der Wörter im Kreis erkennbar, nicht der Start
const rotations = (words) => words.map((_, i) => words.slice(i).concat(words.slice(0, i)).join(' '));

test('Ersatzlösung: SVG ohne Daten wird über die Schriftzeichen gelesen', () => {
  // Zeichen innen: der Inschriftring ist lückenlos, Text und Reihenfolge sind exakt
  const inner = sealWith([e('feuer'), e('wasser'), bat], { label: 'Kaelen Wächter', placement: 'inner' }).r;
  const a = D.decodeFromSvgStructure(inner.svg);
  assert.deepEqual(a.inscription.words, ['kaelen', 'wächter']);
  assert.equal(a.inscription.startUnknown, false);
  assert.equal(a.inscription.unknown, 0);
  assert.ok(a.inscription.repeats >= 1);
  assert.equal(a.id, inner.meta.id);
  assert.equal(a.bands, inner.meta.bands);
  assert.equal(a.circles, inner.meta.parts);
  // Farben dürfen sich ändern, die Zeichen werden trotzdem erkannt
  assert.deepEqual(D.decodeFromSvgStructure(inner.svg.replace(/#1d1812/g, '#336699')).inscription.words, ['kaelen', 'wächter']);

  // Zeichen am Rand: der Ring lässt Zeichen aus, Lücken werden aus den Wiederholungen gefüllt
  const outer = sealWith([e('feuer'), e('wasser'), bat], { label: 'Kaelen Wächter', placement: 'outer' }).r;
  const b = D.decodeFromSvgStructure(outer.svg);
  assert.ok(rotations(['kaelen', 'wächter']).includes(b.inscription.words.join(' ')), b.inscription.words.join(' '));
  assert.equal(b.inscription.unknown, 0, 'alle Lücken ließen sich füllen');

  // Ohne eigene Inschrift stehen die Namen der Teile im Ring
  const plain = sealWith([e('feuer'), e('wasser')], { label: '', placement: 'inner' }).r;
  assert.deepEqual(D.decodeFromSvgStructure(plain.svg).inscription.words.slice().sort(), ['feuer', 'wasser']);

  // Anschlussknoten (außen liegende Zeichen, leere Ecken bei Typ 1 und 2) zählen nicht als Kreise
  for (const [parts, placement] of [[[e('feuer'), e('wasser'), bat], 'outer'], [[e('feuer'), bat], 'auto'], [[e('eis')], 'auto'], [[e('feuer'), e('licht'), e('erde'), bat], 'auto']]) {
    const r = sealWith(parts, { label: 'x', placement }).r;
    assert.equal(D.decodeFromSvgStructure(r.svg).circles, r.meta.parts, `${parts.length} Teile, ${placement}`);
  }

  // Alle Zeichen des Alphabets werden unterschieden
  const text = 'abcdefghijklmnopqrstuvwxyzäöüß0123456789';
  const all = sealWith([e('feuer')], { label: text, placement: 'inner' }).r;
  assert.equal(D.decodeFromSvgStructure(all.svg).inscription.words.join(''), text);
});

test('Sicherheit: Farben aus fremden Daten dürfen kein Markup einschleusen', () => {
  const data = fresh();
  data.elements.find((x) => x.id === 'feuer').color = '#fff" onload="alert(1)';
  data.elements.find((x) => x.id === 'wasser').color = '"><script>alert(1)</script>';
  const spec = { size: 1, carrier: 'body', parts: [e('feuer'), e('wasser')] };
  for (const theme of ['ink', 'color', 'glow']) {
    const svg = W.Seal.build(data, spec, { theme, label: '' }).svg;
    assert.ok(!/<script|onload=|alert\(/.test(svg), theme);
  }
});
