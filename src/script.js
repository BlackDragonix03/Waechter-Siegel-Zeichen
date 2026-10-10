/*
 * Schaftschrift der Wächter (Entwurf, kombinierbar).
 *
 * Prinzip: Jeder Buchstabe sitzt auf demselben senkrechten Schaft (x = 0.3).
 * Zweige links und rechts machen ihn unverwechselbar. Übereinander gesetzt
 * verbinden sich die Schäfte zu einer durchgehenden Linie: ein Wort wird EIN
 * Symbol (eine Art Binderune) und passt in einen Siegelkreis.
 *
 * Systematik, damit die Schrift lesbar bleibt:
 *  - Vokale tragen einen Ring auf dem Schaft.
 *  - Umlaute = Grundbuchstabe + zwei Punkte an den Seiten.
 *  - Jeder Buchstabe hat eine eigene, deterministisch erzeugte Zweigkombination;
 *    zwei Buchstaben unterscheiden sich immer in mindestens zwei Zweigen.
 *  - Gleicher Schriftschlüssel -> immer dasselbe Alphabet.
 */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});
  const { createRng } = W.Prng;

  const BASE = 'abcdefghijklmnopqrstuvwxyzß0123456789'.split('');
  const UMLAUTS = { 'ä': 'a', 'ö': 'o', 'ü': 'u' };
  const VOWELS = new Set(['a', 'e', 'i', 'o', 'u']);
  const STEM_X = 0.3;
  const SIDE_X = [0.0, 0.6];          // links, rechts
  const YS = [0, 0.25, 0.5, 0.75, 1]; // Knotenhöhen im Band
  const CELL = { w: 0.6, h: 1 };
  const MAX_ROWS = 4;                 // Buchstaben je Säule

  /* ---------- Text -> Wörter ---------- */

  function mapChar(ch) {
    if (/[a-z0-9]/.test(ch) || ch === 'ä' || ch === 'ö' || ch === 'ü' || ch === 'ß') return ch;
    if (ch === 'æ') return 'ae';
    if (ch === 'œ') return 'oe';
    if (ch === 'ø') return 'o';
    const d = ch.normalize('NFD').replace(/[̀-ͯ]/g, '');
    return /^[a-z0-9]$/.test(d) ? d : ''; // alles andere trennt Wörter
  }

  function parseText(text) {
    const words = [];
    let cur = '';
    for (const ch of String(text || '').normalize('NFC').toLowerCase()) {
      const m = mapChar(ch);
      if (m) cur += m;
      else if (cur) { words.push(cur); cur = ''; }
    }
    if (cur) words.push(cur);
    return { words, letters: words.reduce((n, w) => n + w.length, 0) };
  }

  /* ---------- Glyph-Erzeugung ---------- */

  // Ein Zweig: Schaftknoten y0 -> Seitenknoten (side, y1), gerade oder gebogen
  function makeBranch(rng) {
    const side = rng.int(0, 1);
    const y0 = rng.int(0, 4);
    const y1 = rng.int(0, 4);
    const curved = rng.next() < 0.45;
    const bulge = curved ? rng.sign() : 0;
    return { side, y0, y1, curved, bulge };
  }
  const branchSig = (b) => `${b.side}${b.y0}${b.y1}${b.curved ? (b.bulge > 0 ? 'p' : 'm') : 'l'}`;

  function genSig(key, ch, attempt) {
    const rng = createRng(`${key}|schaft|${ch}|${attempt}`);
    const vowel = VOWELS.has(ch);
    const count = vowel ? rng.int(1, 2) : rng.int(2, 3);
    const branches = [];
    const seen = new Set();
    let guard = 0;
    while (branches.length < count && guard++ < 40) {
      const b = makeBranch(rng);
      if (b.y0 === b.y1 && b.curved) continue;                 // flacher Bogen sieht nach nichts aus
      if (b.y0 === b.y1 && b.y0 % 4 === 0) continue;            // Zweig am Rand parallel zum Band
      const s = branchSig(b);
      if (seen.has(s)) continue;
      seen.add(s);
      branches.push(b);
    }
    return { branches, vowel, sigSet: new Set(branches.map(branchSig).concat(vowel ? ['ring'] : [])) };
  }

  const distance = (a, b) => {
    let d = 0;
    a.forEach((x) => { if (!b.has(x)) d++; });
    b.forEach((x) => { if (!a.has(x)) d++; });
    return d;
  };

  function toPrimitives(g, key, ch) {
    const rng = createRng(`${key}|form|${ch}`);
    const prim = [{ t: 'L', p: [[STEM_X, 0], [STEM_X, 1]] }]; // durchgehender Schaft
    g.branches.forEach((b) => {
      const jx = rng.range(-0.012, 0.012);
      const a = [STEM_X, YS[b.y0]];
      const e = [SIDE_X[b.side] + jx, YS[b.y1]];
      if (!b.curved) prim.push({ t: 'L', p: [a, e] });
      else {
        const mx = (a[0] + e[0]) / 2, my = (a[1] + e[1]) / 2;
        const nx = -(e[1] - a[1]), ny = e[0] - a[0];
        const nl = Math.hypot(nx, ny) || 1;
        const off = b.bulge * 0.2;
        prim.push({ t: 'Q', p: [a, [mx + (nx / nl) * off, my + (ny / nl) * off], e] });
      }
    });
    if (g.vowel) prim.push({ t: 'O', c: [STEM_X, 0.5], r: 0.11, fill: false });
    return prim;
  }

  const cache = {};

  function buildAlphabet(key) {
    if (cache[key]) return cache[key];
    const glyphs = {};
    const taken = [];
    BASE.forEach((ch) => {
      let best = null;
      for (let attempt = 0; attempt < 400; attempt++) {
        const g = genSig(key, ch, attempt);
        const minD = taken.length ? Math.min(...taken.map((t) => distance(g.sigSet, t))) : 9;
        if (!best || minD > best.minD) best = { g, minD };
        if (minD >= 2) break;
      }
      taken.push(best.g.sigSet);
      glyphs[ch] = { ch, prim: toPrimitives(best.g, key, ch), minDistance: best.minD };
    });
    Object.keys(UMLAUTS).forEach((u) => {
      const base = glyphs[UMLAUTS[u]];
      glyphs[u] = {
        ch: u,
        prim: base.prim.concat([
          { t: 'O', c: [0.06, 0.5], r: 0.04, fill: true },
          { t: 'O', c: [0.54, 0.5], r: 0.04, fill: true },
        ]),
      };
    });
    const order = BASE.slice(0, 26).concat(['ä', 'ö', 'ü', 'ß'], BASE.slice(27));
    return (cache[key] = { key, glyphs, order });
  }

  /* ---------- Layout: Wort -> ein Symbol ---------- */

  const f1 = (v) => (Math.round(v * 100) / 100).toString();

  // Setzt die Buchstaben eines Wortes als Säulen auf einen gemeinsamen Schaft.
  function layoutWord(word, alphabet, cx, cy, boxW, boxH) {
    const chars = Array.from(word).filter((c) => alphabet.glyphs[c]);
    const n = chars.length;
    const gapX = 0.5;
    let best = null;
    for (let rows = 1; rows <= Math.min(n, MAX_ROWS); rows++) {
      const cols = Math.ceil(n / rows);
      const totalW = cols * CELL.w + (cols - 1) * gapX;
      const totalH = rows * CELL.h;
      const scale = Math.min(boxW / totalW, boxH / totalH);
      if (!best || scale > best.scale + 1e-9) best = { rows, cols, scale, totalW, totalH };
    }
    let d = '';
    const dots = [], rings = [];
    if (!best) return { d, dots, rings, scale: 1, strokeWidth: 1.5 };
    const { rows, cols, scale, totalW, totalH } = best;
    chars.forEach((ch, i) => {
      const c = Math.floor(i / rows), r = i % rows;
      const inCol = c < cols - 1 ? rows : n - (cols - 1) * rows;
      const ox = -totalW / 2 + c * (CELL.w + gapX);
      const oy = -(inCol * CELL.h) / 2 + r * CELL.h; // letzte Säule mittig
      const X = (x) => cx + (ox + x) * scale;
      const Y = (y) => cy + (oy + y) * scale;
      alphabet.glyphs[ch].prim.forEach((p) => {
        if (p.t === 'L') d += `M${f1(X(p.p[0][0]))} ${f1(Y(p.p[0][1]))}L${f1(X(p.p[1][0]))} ${f1(Y(p.p[1][1]))}`;
        else if (p.t === 'Q') d += `M${f1(X(p.p[0][0]))} ${f1(Y(p.p[0][1]))}Q${f1(X(p.p[1][0]))} ${f1(Y(p.p[1][1]))} ${f1(X(p.p[2][0]))} ${f1(Y(p.p[2][1]))}`;
        else if (p.fill) dots.push({ cx: X(p.c[0]), cy: Y(p.c[1]), r: Math.max(p.r * scale, 0.9) });
        else rings.push({ cx: X(p.c[0]), cy: Y(p.c[1]), r: p.r * scale });
      });
    });
    return { d, dots, rings, scale, strokeWidth: Math.min(2.6, Math.max(1.1, scale * 0.07)) };
  }

  function layoutToSvg(l, color) {
    let s = `<path d="${l.d}" fill="none" stroke="${color}" stroke-width="${f1(l.strokeWidth)}" stroke-linecap="round" stroke-linejoin="round"/>`;
    l.rings.forEach((r) => { s += `<circle cx="${f1(r.cx)}" cy="${f1(r.cy)}" r="${f1(r.r)}" fill="none" stroke="${color}" stroke-width="${f1(l.strokeWidth)}"/>`; });
    l.dots.forEach((r) => { s += `<circle cx="${f1(r.cx)}" cy="${f1(r.cy)}" r="${f1(r.r)}" fill="${color}"/>`; });
    return s;
  }

  /* ---------- Vorschau: Textzeile und Alphabet ---------- */

  function renderText(words, key, opts) {
    const o = Object.assign({ width: 760, glyph: 34, ink: '#1d1812', paper: '#f3ead7', label: '#6d604b' }, opts);
    const alphabet = buildAlphabet(key);
    const rowH = o.glyph * 1.3 + 36;
    let x = 14, y = 14, rows = 1;
    let body = '';
    words.forEach((w) => {
      const wW = Array.from(w).length * (o.glyph * 0.6 + o.glyph * 0.3);
      if (x + wW > o.width - 14 && x > 14) { x = 14; y += rowH; rows++; }
      let cx = x;
      Array.from(w).forEach((ch) => {
        body += layoutToSvg(layoutWord(ch, alphabet, cx + o.glyph * 0.3, y + o.glyph * 0.65, o.glyph * 0.6, o.glyph * 1.2), o.ink);
        cx += o.glyph * 0.9;
      });
      body += `<text x="${f1(x)}" y="${f1(y + o.glyph * 1.3 + 16)}" font-size="12" fill="${o.label}" font-family="Georgia, serif">${w}</text>`;
      x += wW + o.glyph * 0.7;
    });
    const h = rows * rowH + 10;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${o.width} ${h}" width="100%" role="img" aria-label="Text in Wächterschrift"><rect width="${o.width}" height="${h}" fill="${o.paper}"/>${body}</svg>`;
  }

  function renderAlphabet(key, opts) {
    const o = Object.assign({ cols: 10, glyph: 40, ink: '#1d1812', paper: '#f3ead7', label: '#6d604b' }, opts);
    const alphabet = buildAlphabet(key);
    const cellW = o.glyph * 1.5, cellH = o.glyph * 1.3 + 40;
    const rows = Math.ceil(alphabet.order.length / o.cols);
    const width = cellW * o.cols + 20, height = cellH * rows + 20;
    let body = '';
    alphabet.order.forEach((ch, i) => {
      const cx = 10 + (i % o.cols) * cellW + cellW / 2;
      const cy = 10 + Math.floor(i / o.cols) * cellH + o.glyph * 0.7;
      body += layoutToSvg(layoutWord(ch, alphabet, cx, cy, o.glyph * 0.6, o.glyph * 1.2), o.ink);
      body += `<text x="${f1(cx)}" y="${f1(cy + o.glyph * 0.6 + 22)}" font-size="14" text-anchor="middle" fill="${o.label}" font-family="Georgia, serif">${ch.toUpperCase()}</text>`;
    });
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="100%" role="img" aria-label="Alphabet der Wächter"><rect width="${width}" height="${height}" fill="${o.paper}"/>${body}</svg>`;
  }

  W.Script = { parseText, buildAlphabet, layoutWord, layoutToSvg, renderText, renderAlphabet };
  if (typeof module === 'object' && module.exports) module.exports = W.Script;
})(typeof globalThis !== 'undefined' ? globalThis : this);
