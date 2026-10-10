/*
 * Entschlüsseler: liest ein exportiertes Siegel (SVG oder PNG) und erklärt, was es ist.
 *
 * Der Export bettet die vollständigen Angaben ins Bild ein (Teile, Werte, Inschrift und die
 * damals gültigen Regeln). Daraus lässt sich ein Siegel exakt erklären, auch wenn sich die
 * Regeln später geändert haben. Ein SVG ohne diese Daten wird über die Schriftzeichen im
 * Inschriftring gelesen (Anzahl der Bänder und Kreise, Inschrift im Klartext).
 *
 * Grenzen: Screenshots, Fotos, JPEG und mit anderen Programmen neu gespeicherte PNG tragen
 * die Daten nicht mehr. Bilder werden nie anhand ihrer Pixel erkannt.
 */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});
  const M = W.Model;
  const S = W.Script;

  const FORMAT = 'waechter-siegel';
  const PNG_KEY = 'WaechterSiegel';

  const escXml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const unescXml = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
  const clone = (o) => JSON.parse(JSON.stringify(o));

  /* ---------- Nutzlast ---------- */

  // Alles, was nötig ist, um das Siegel später zu erklären und nachzubauen
  function makePayload(data, spec, options, id) {
    return {
      format: FORMAT,
      version: 1,
      id,
      spec: clone(spec),
      options: { theme: options.theme, label: options.label || '', placement: options.placement || 'auto' },
      data: clone(data),
    };
  }

  function checkPayload(p) {
    if (!p || p.format !== FORMAT) throw new Error('Das ist keine Siegeldatei der Werkstatt.');
    const d = p.data;
    const ok = p.spec && Array.isArray(p.spec.parts) && d && Array.isArray(d.elements) && Array.isArray(d.components) &&
      Array.isArray(d.sources) && Array.isArray(d.oppositions) && d.settings && typeof d.settings === 'object';
    if (!ok) throw new Error('Die eingebetteten Daten sind unvollständig oder beschädigt.');
    return p;
  }

  /* ---------- SVG ---------- */

  function embedInSvg(svg, payload) {
    const meta = `<metadata id="${FORMAT}">${escXml(JSON.stringify(payload))}</metadata>`;
    return svg.replace(/<svg\b[^>]*>/, (m) => m + meta);
  }

  function stripSvgMetadata(svg) {
    return svg.replace(/<metadata id="waechter-siegel">[\s\S]*?<\/metadata>/, '');
  }

  function extractFromSvg(text) {
    const m = /<metadata id="waechter-siegel">([\s\S]*?)<\/metadata>/.exec(text);
    if (!m) return null;
    try { return JSON.parse(unescXml(m[1])); } catch (e) { return { error: 'Die eingebetteten Daten sind beschädigt.' }; }
  }

  /* ---------- PNG ---------- */

  let crcTable = null;
  function crc32(bytes, start, end) {
    if (!crcTable) {
      crcTable = new Uint32Array(256);
      for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        crcTable[n] = c >>> 0;
      }
    }
    let c = 0xffffffff;
    for (let i = start; i < end; i++) c = crcTable[(c ^ bytes[i]) & 255] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  const PNG_SIG = [137, 80, 78, 71, 13, 10, 26, 10];
  const isPng = (b) => b.length > 33 && PNG_SIG.every((v, i) => b[i] === v);
  const u32 = (b, o) => ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;

  // Fügt die Nutzlast als iTXt-Block (UTF-8, unkomprimiert) direkt hinter dem Kopfblock ein
  function embedInPng(bytes, payload) {
    if (!isPng(bytes) || u32(bytes, 8) !== 13 || String.fromCharCode(...bytes.slice(12, 16)) !== 'IHDR') throw new Error('Keine gültige PNG-Datei.');
    const enc = new TextEncoder();
    const key = enc.encode(PNG_KEY);
    const text = enc.encode(JSON.stringify(payload));
    const data = new Uint8Array(key.length + 5 + text.length); // Schlüsselwort, 0, Flag, Methode, 0 (Sprache), 0 (Titel), Text
    data.set(key, 0);
    data.set(text, key.length + 5);
    const chunk = new Uint8Array(12 + data.length);
    const view = new DataView(chunk.buffer);
    view.setUint32(0, data.length);
    chunk.set(enc.encode('iTXt'), 4);
    chunk.set(data, 8);
    view.setUint32(8 + data.length, crc32(chunk, 4, 8 + data.length));
    const at = 33; // 8 Signatur + 25 IHDR-Block
    const out = new Uint8Array(bytes.length + chunk.length);
    out.set(bytes.slice(0, at), 0);
    out.set(chunk, at);
    out.set(bytes.slice(at), at + chunk.length);
    return out;
  }

  function extractFromPng(bytes) {
    if (!isPng(bytes)) return null;
    let pos = 8;
    while (pos + 12 <= bytes.length) {
      const len = u32(bytes, pos);
      const type = String.fromCharCode(...bytes.slice(pos + 4, pos + 8));
      const start = pos + 8;
      const end = start + len;
      if (end + 4 > bytes.length) break;
      if (type === 'iTXt' || type === 'tEXt') {
        const zero = bytes.indexOf(0, start);
        const key = String.fromCharCode(...bytes.slice(start, zero));
        if (key === PNG_KEY) {
          let text;
          if (type === 'iTXt') {
            if (bytes[zero + 1] === 1) return { error: 'Komprimierte Daten werden nicht unterstützt.' };
            let p = zero + 3;                  // hinter Flag und Methode
            p = bytes.indexOf(0, p) + 1;       // Sprachkennung überspringen
            p = bytes.indexOf(0, p) + 1;       // übersetztes Schlüsselwort überspringen
            text = new TextDecoder().decode(bytes.slice(p, end));
          } else {
            text = String.fromCharCode(...bytes.slice(zero + 1, end));
          }
          try { return JSON.parse(text); } catch (e) { return { error: 'Die eingebetteten Daten sind beschädigt.' }; }
        }
      }
      if (type === 'IEND') break;
      pos = end + 4;
    }
    return null;
  }

  /* ---------- Datei lesen ---------- */

  // bytes: Uint8Array. Liefert { type, payload, error, svgText }.
  function readSealFile(bytes) {
    if (isPng(bytes)) {
      const payload = extractFromPng(bytes);
      return { type: 'png', payload: payload && !payload.error ? payload : null, error: payload && payload.error ? payload.error : null };
    }
    const text = new TextDecoder().decode(bytes);
    if (/<svg\b/.test(text)) {
      const payload = extractFromSvg(text);
      return { type: 'svg', svgText: text, payload: payload && !payload.error ? payload : null, error: payload && payload.error ? payload.error : null };
    }
    return { type: 'unknown', payload: null, error: null };
  }

  /* ---------- Erklärung ---------- */

  // Eis = Wasser + Luft; verschachtelt: Obsidian = Lava (Feuer + Erde) → Wasser
  function recipeText(idx, id, top) {
    const el = idx.byId.get(id);
    if (!el) return id;
    if (el.kind === 'prime') return el.name;
    const sep = el.recipe.ordered ? ' → ' : ' + ';
    const inner = el.recipe.ingredients.map((i) => recipeText(idx, i, false)).join(sep);
    return top ? `${el.name} = ${inner}` : `${el.name} (${inner})`;
  }

  const cleanWord = (name) => name.toLowerCase().replace(/[^a-zäöüß0-9]/g, '');

  function explain(payload) {
    checkPayload(payload);
    const { data, spec } = payload;
    const idx = M.buildIndex(data);
    const analysis = W.Calc.analyze(data, spec);
    const options = payload.options || {};
    const rebuilt = W.Seal.build(data, spec, options);
    const canon = W.Seal.canonicalParts(data, spec);
    const parts = canon.map((p) => {
      const entry = { kind: p.kind, name: p.name, place: p.place, fused: p.fused, primes: p.primes.map((id) => (idx.byId.get(id) || { name: id }).name) };
      if (p.kind === 'element') {
        const id = (p.key.split(':')[1] || '');
        entry.recipe = recipeText(idx, id, true);
      }
      return entry;
    });
    const carried = (spec.parts || []).filter((p) => p.kind === 'carried').map((p) => {
      const src = data.sources.find((s) => s.id === p.source);
      const lvl = src && src.levels.find((l) => l.id === p.level);
      return src && lvl ? { name: src.name, level: lvl.name, amount: p.amount == null ? 1 : p.amount, total: lvl.value * (p.amount == null ? 1 : p.amount), hazard: src.hazard || '' } : null;
    }).filter(Boolean);
    const labelWords = S.parseText(options.label || '').words;
    const nameWords = canon.map((p) => cleanWord(p.name)).filter(Boolean);
    return {
      id: payload.id,
      rebuiltId: rebuilt.empty ? null : rebuilt.meta.id,
      idMatches: !rebuilt.empty && rebuilt.meta.id === payload.id,
      rebuiltSvg: rebuilt.svg,
      typ: analysis.typ,
      parts,
      carried,
      primes: Object.keys(analysis.primes).map((id) => ({ name: (idx.byId.get(id) || { name: id }).name, count: analysis.primes[id] })),
      oppositions: analysis.oppositions.map((o) => o.text),
      complexity: analysis.complexity,
      size: spec.size || 1,
      carrier: spec.carrier === 'object' ? 'Gegenstand' : 'Körper',
      creation: analysis.creation,
      usage: analysis.usage,
      warnings: analysis.warnings,
      inscription: { words: labelWords.length ? labelWords : S.parseText(nameWords.join(' ')).words, fromLabel: labelWords.length > 0 },
      circles: nameWords,
      circleNames: canon.map((p) => p.name),
      options,
    };
  }

  /* ---------- Ersatzlösung: SVG ohne eingebettete Daten ---------- */

  // Inhalt einer <g id="...">-Gruppe samt verschachtelter Gruppen
  function groupInner(svg, id) {
    const start = svg.indexOf(`<g id="${id}">`);
    if (start < 0) return null;
    const re = /<g\b|<\/g>/g;
    re.lastIndex = start;
    let depth = 0;
    let m;
    while ((m = re.exec(svg))) {
      depth += m[0] === '</g>' ? -1 : 1;
      if (depth === 0) return svg.slice(start + `<g id="${id}">`.length, m.index);
    }
    return null;
  }

  const normColors = (m) => m.replace(/(stroke|fill)="#[0-9a-fA-F]{3,8}"/g, '$1="#"');

  // Liest die Inschrift aus den Zeichen: jedes Zeichen wird mit dem Alphabet verglichen
  function decodeFromSvgStructure(svg) {
    const alphabet = S.buildAlphabet(W.Seal.SCRIPT_KEY);
    const gh = W.Seal.INSCRIPTION_GLYPH;
    const table = new Map();
    alphabet.order.forEach((ch) => table.set(normColors(S.layoutToSvg(S.layoutWord(ch, alphabet, 0, 0, gh * 0.6, gh), '#000')), ch));
    table.set(normColors('<path d="M0 -3L2.4 0L0 3L-2.4 0Z" fill="#000"/>'), '·');

    const out = { inscription: null, id: null, bands: (svg.match(/<g id="band\d+">/g) || []).length, circles: 0 };
    const idm = /<title>Siegel ([A-Z0-9-]+)<\/title>/.exec(svg);
    if (idm) out.id = idm[1];
    const teile = groupInner(svg, 'teile');
    // Kreise tragen einen Freihaltering; die kleinen Anschlussknoten auf dem Stern gehören nicht dazu
    if (teile) out.circles = (teile.match(/<g transform="translate\([^)]*\)"><circle r=/g) || []).length;

    const ring = groupInner(svg, 'inschrift');
    if (ring) {
      // Zeichen mit ihrem Winkel einlesen. Neben Kreisen lässt der Ring Zeichen aus,
      // deshalb werden die Plätze aus den Winkeln rekonstruiert und Lücken aus den Wiederholungen gefüllt.
      const re = /<g transform="translate\((-?[\d.]+) (-?[\d.]+)\) rotate\((-?[\d.]+)\)">([\s\S]*?)<\/g>/g;
      const toks = [];
      let m;
      while ((m = re.exec(ring))) toks.push({ deg: parseFloat(m[3]) - 90, ch: table.get(normColors(m[4])) || '?' });
      let unknown = toks.filter((t) => t.ch === '?').length;
      if (toks.length) {
        let step = Infinity;
        for (let k = 1; k < toks.length; k++) { const d = toks[k].deg - toks[k - 1].deg; if (d > 0.01) step = Math.min(step, d); }
        const N = Number.isFinite(step) ? Math.max(1, Math.round(360 / step)) : 1;
        const slots = new Array(N).fill(null);
        toks.forEach((t) => { slots[((Math.round((t.deg - toks[0].deg) / (360 / N)) % N) + N) % N] = t.ch; });
        // kleinste Wiederholungseinheit, in der sich bekannte Zeichen nicht widersprechen
        let unit = slots.slice();
        for (let p = 1; p <= N; p++) {
          if (N % p) continue;
          const u = new Array(p).fill(null);
          let ok = true;
          for (let i = 0; i < N && ok; i++) {
            if (slots[i] == null) continue;
            if (u[i % p] == null) u[i % p] = slots[i]; else if (u[i % p] !== slots[i]) ok = false;
          }
          if (ok) { unit = u; break; }
        }
        const gaps = unit.filter((c) => c == null).length;
        let text = unit.map((c) => (c == null ? '?' : c)).join('');
        // Der Ring ist ein Kreis: beginnt das Lesen mitten im Wort (Zeichen am Start fehlen), ist der
        // Startpunkt nicht erkennbar. Dann bei einem Wortanfang beginnen (hinter einem Trenner).
        let startUnknown = gaps > 0;
        const cut = text.indexOf('·');
        if (!text.endsWith('·') && cut >= 0 && cut < text.length - 1) {
          text = text.slice(cut + 1) + text.slice(0, cut + 1);
          startUnknown = true;
        }
        out.inscription = { words: text.split('·').filter(Boolean), repeats: N / unit.length, unknown: unknown + gaps, startUnknown };
      } else {
        out.inscription = { words: [], repeats: 0, unknown: 0, startUnknown: false };
      }
    }
    return out;
  }

  W.Decode = {
    FORMAT, makePayload, checkPayload, embedInSvg, stripSvgMetadata, extractFromSvg,
    embedInPng, extractFromPng, readSealFile, explain, decodeFromSvgStructure, crc32,
  };
  if (typeof module === 'object' && module.exports) module.exports = W.Decode;
})(typeof globalThis !== 'undefined' ? globalThis : this);
