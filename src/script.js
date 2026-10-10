/*
 * Die Schrift der Wächter.
 *
 * Jeder Buchstabe bekommt ein festes Glyph, erzeugt aus dem Schriftschlüssel
 * (Lore.alphabetKey). Gleicher Schlüssel -> immer dasselbe Alphabet.
 *
 * Regeln der Schrift (damit sie wie ein System wirkt, nicht wie Zufall):
 *  - Glyphen leben auf einem 3x5-Knotenraster (Breite 0.6, Höhe 1).
 *  - Fast alle haben eine tragende Linie (Schaft), davon zweigen Striche ab.
 *  - Vokale tragen einen RING an einem Strichende.
 *  - Umlaute = Grundbuchstabe + zwei Punkte darüber.
 *  - Ein Wort wird zu EINEM Symbol: die Glyphen werden in ein Feld gesetzt.
 */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});
  const { createRng } = W.Prng;

  const BASE = 'abcdefghijklmnopqrstuvwxyzß0123456789'.split('');
  const UMLAUTS = { 'ä': 'a', 'ö': 'o', 'ü': 'u' };
  const VOWELS = new Set(['a', 'e', 'i', 'o', 'u']);
  const XS = [0, 0.3, 0.6];
  const YS = [0, 0.25, 0.5, 0.75, 1];
  const CELL = { w: 0.6, h: 1.2, top: -0.2 }; // Umlautpunkte liegen über y=0

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

  function genBase(key, ch, attempt) {
    const rng = createRng(`${key}|glyph|${ch}|${attempt}`);
    const jn = () => rng.range(-0.022, 0.022);
    const N = XS.map((x) => YS.map((y) => [x + jn(), y + jn()]));
    const at = (n) => N[n[0]][n[1]];
    const prim = [];
    const sig = [];
    const conn = []; // Knoten (xi, yi), an denen Striche ansetzen dürfen
    const vowel = VOWELS.has(ch);

    // Schaft
    const sp = rng.next();
    if (sp < 0.62) {
      const y0 = rng.pick([0, 0, 1]);
      const y1 = rng.pick([4, 4, 3]);
      prim.push({ t: 'L', p: [at([1, y0]), at([1, y1])] });
      for (let y = y0; y <= y1; y++) conn.push([1, y]);
      sig.push(`S|${y0}-${y1}`);
    } else if (sp < 0.82) {
      const bulge = rng.sign() * rng.range(0.22, 0.32);
      const a = at([1, 0]), b = at([1, 4]);
      prim.push({ t: 'Q', p: [a, [0.3 + bulge, 0.5], b] });
      conn.push([1, 0], [1, 4], [1, 2]);
      sig.push(`B|${bulge > 0 ? '+' : '-'}`);
    } else {
      prim.push({ t: 'L', p: [at([0, 1]), at([0, 3])] });
      prim.push({ t: 'L', p: [at([2, 0]), at([2, 2])] });
      conn.push([0, 1], [0, 3], [2, 0], [2, 2]);
      sig.push('D');
    }

    // Abzweigende Striche
    const count = vowel ? rng.int(1, 3) : rng.int(2, 4);
    const used = new Set();
    for (let k = 0; k < count; k++) {
      for (let tries = 0; tries < 14; tries++) {
        const s = rng.pick(conn);
        const e = [rng.int(0, 2), rng.int(0, 4)];
        if (s[0] === e[0] && s[1] === e[1]) continue;
        const d = Math.hypot(XS[e[0]] - XS[s[0]], YS[e[1]] - YS[s[1]]);
        if (d < 0.29) continue;
        const id = `${s}-${e}`;
        if (used.has(id)) continue;
        used.add(id);
        const a = at(s), b = at(e);
        if (rng.next() < 0.62) {
          prim.push({ t: 'L', p: [a, b] });
          sig.push(`L|${id}`);
        } else {
          const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
          const nx = -(b[1] - a[1]), ny = b[0] - a[0];
          const nl = Math.hypot(nx, ny) || 1;
          const off = rng.sign() * rng.range(0.12, 0.26);
          prim.push({ t: 'Q', p: [a, [mx + (nx / nl) * off, my + (ny / nl) * off], b] });
          sig.push(`Q|${id}|${off > 0 ? '+' : '-'}`);
        }
        conn.push(e);
        break;
      }
    }

    // Vokal-Ring bzw. gelegentlicher Punkt bei Konsonanten
    if (vowel) {
      const c = rng.pick(conn);
      prim.push({ t: 'O', c: at(c), r: 0.1, fill: false });
      sig.push(`R|${c}`);
    } else if (rng.next() < 0.3) {
      const corners = [[0, 0], [2, 0], [0, 4], [2, 4]].filter(
        (c) => !conn.some((q) => q[0] === c[0] && q[1] === c[1])
      );
      if (corners.length) {
        const c = rng.pick(corners);
        const p = at(c);
        // Punkt leicht zur Mitte gerückt, damit er nicht am Rand klebt
        prim.push({ t: 'O', c: [p[0] + (c[0] === 0 ? 0.07 : -0.07), p[1] + (c[1] === 0 ? 0.07 : -0.07)], r: 0.04, fill: true });
        sig.push(`P|${c}`);
      }
    }
    return { prim, sig: sig.join(';') };
  }

  const cache = {};

  function buildAlphabet(key) {
    if (cache[key]) return cache[key];
    const glyphs = {};
    const seen = new Set();
    BASE.forEach((ch) => {
      let g;
      for (let attempt = 0; attempt < 60; attempt++) {
        g = genBase(key, ch, attempt);
        if (!seen.has(g.sig)) break;
      }
      seen.add(g.sig);
      glyphs[ch] = { ch, prim: g.prim };
    });
    Object.keys(UMLAUTS).forEach((u) => {
      const base = glyphs[UMLAUTS[u]];
      glyphs[u] = {
        ch: u,
        prim: base.prim.concat([
          { t: 'O', c: [0.16, -0.12], r: 0.04, fill: true },
          { t: 'O', c: [0.44, -0.12], r: 0.04, fill: true },
        ]),
      };
    });
    const order = BASE.slice(0, 26).concat(['ä', 'ö', 'ü', 'ß'], BASE.slice(27));
    return (cache[key] = { key, glyphs, order });
  }

  /* ---------- Layout: Wort -> ein Symbol ---------- */

  const f1 = (v) => (Math.round(v * 100) / 100).toString();

  // Setzt die Glyphen eines Wortes in ein Feld (boxW x boxH) um (cx, cy).
  function layoutWord(word, alphabet, cx, cy, boxW, boxH) {
    const chars = Array.from(word);
    const n = chars.length;
    const gx = 0.3, gy = 0.25;
    let best = null;
    for (let cols = 1; cols <= n; cols++) {
      const rows = Math.ceil(n / cols);
      const totalW = cols * CELL.w + (cols - 1) * gx;
      const totalH = rows * CELL.h + (rows - 1) * gy;
      const scale = Math.min(boxW / totalW, boxH / totalH);
      if (!best || scale > best.scale + 1e-9) best = { cols, rows, scale, totalW, totalH };
    }
    const { cols, rows, scale, totalW, totalH } = best;
    let d = '';
    const dots = [];
    const rings = [];
    chars.forEach((ch, i) => {
      const g = alphabet.glyphs[ch];
      if (!g) return;
      const r = Math.floor(i / cols), c = i % cols;
      const inRow = r < rows - 1 ? cols : n - (rows - 1) * cols;
      const rowW = inRow * CELL.w + (inRow - 1) * gx;
      const ox = -totalW / 2 + (totalW - rowW) / 2 + c * (CELL.w + gx);
      const oy = -totalH / 2 + r * (CELL.h + gy) - CELL.top;
      const X = (x) => cx + (ox + x) * scale;
      const Y = (y) => cy + (oy + y) * scale;
      g.prim.forEach((p) => {
        if (p.t === 'L') d += `M${f1(X(p.p[0][0]))} ${f1(Y(p.p[0][1]))}L${f1(X(p.p[1][0]))} ${f1(Y(p.p[1][1]))}`;
        else if (p.t === 'Q') d += `M${f1(X(p.p[0][0]))} ${f1(Y(p.p[0][1]))}Q${f1(X(p.p[1][0]))} ${f1(Y(p.p[1][1]))} ${f1(X(p.p[2][0]))} ${f1(Y(p.p[2][1]))}`;
        else if (p.fill) dots.push({ cx: X(p.c[0]), cy: Y(p.c[1]), r: Math.max(p.r * scale, 0.9) });
        else rings.push({ cx: X(p.c[0]), cy: Y(p.c[1]), r: p.r * scale });
      });
    });
    return { d, dots, rings, scale, strokeWidth: Math.min(2.4, Math.max(1.1, scale * 0.085)) };
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
    const rowH = o.glyph * 1.2 + 36;
    let x = 14, y = 14, rows = 1;
    let body = '';
    words.forEach((w) => {
      const wW = Array.from(w).length * (o.glyph * 0.6 + o.glyph * 0.3);
      if (x + wW > o.width - 14 && x > 14) { x = 14; y += rowH; rows++; }
      let cx = x;
      Array.from(w).forEach((ch) => {
        const l = layoutWord(ch, alphabet, cx + o.glyph * 0.3, y + o.glyph * 0.62, o.glyph * 0.6, o.glyph * 1.2);
        body += layoutToSvg(l, o.ink);
        cx += o.glyph * 0.9;
      });
      body += `<text x="${f1(x)}" y="${f1(y + o.glyph * 1.2 + 16)}" font-size="12" fill="${o.label}" font-family="Georgia, serif">${w}</text>`;
      x += wW + o.glyph * 0.7;
    });
    const h = rows * rowH + 10;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${o.width} ${h}" width="100%" role="img" aria-label="Text in Wächterschrift"><rect width="${o.width}" height="${h}" fill="${o.paper}"/>${body}</svg>`;
  }

  function renderAlphabet(key, opts) {
    const o = Object.assign({ cols: 10, glyph: 40, ink: '#1d1812', paper: '#f3ead7', label: '#6d604b' }, opts);
    const alphabet = buildAlphabet(key);
    const cellW = o.glyph * 1.5, cellH = o.glyph * 1.2 + 40;
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
