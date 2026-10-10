/*
 * Siegelbild (SVG) aus einem Siegel der Rechner-Daten.
 *
 * Aufbau (außen -> innen), alles aus den Daten abgeleitet:
 *  - Rahmen mit Teilstrichen
 *  - Inschriftring: Wörter in Wächterschrift, rundum wiederholt
 *  - ein Musterband je Element (Flammen, Wellen, Ziegel, ...); verwobene Elemente
 *    wechseln die Muster ihrer Urelemente im Band ab
 *  - ein Flechtband je Gegensatz (zwei gegenläufige Wellen in den Farben beider Seiten)
 *  - Bahnen (Spiralen) im Inneren; Gegensätze bringen gegenläufige Bahnen
 *  - Kern mit Rosette
 *  - Sternpolygon durch die Teile: Typ N = N-zählige Symmetrie, ein Kreis je Teil
 *
 * Gleiche Anforderungen -> immer dasselbe Bild (Zufall nur aus dem Siegelschlüssel).
 * Mehr Elemente und Gegensätze -> mehr Bänder, mehr Bahnen, größeres Siegel.
 */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});
  const { createRng, seedId } = W.Prng;
  const M = W.Model;
  const S = W.Script;
  const TAU = Math.PI * 2;
  const KEY = (W.Lore && W.Lore.alphabetKey) || 'waechter';
  const INSCRIPTION_GLYPH = 17; // Höhe der Buchstaben im Inschriftring (der Entschlüssler gleicht damit ab)

  const n1 = (v) => { const r = Math.round(v * 10) / 10; return Object.is(r, -0) ? '0' : String(r); };
  const pt = (r, a) => [r * Math.cos(a), r * Math.sin(a)];
  const mv = (p) => `${n1(p[0])} ${n1(p[1])}`;
  const polyD = (pts, closed) => 'M' + pts.map(mv).join('L') + (closed ? 'Z' : '');
  const gcd = (a, b) => (b ? gcd(b, a % b) : a);

  function smoothD(pts, closed) {
    const n = pts.length;
    if (n < 2) return '';
    const at = (i) => (closed ? pts[(i + n) % n] : pts[Math.max(0, Math.min(n - 1, i))]);
    let d = 'M' + mv(pts[0]);
    for (let i = 0; i < (closed ? n : n - 1); i++) {
      const p0 = at(i - 1), p1 = at(i), p2 = at(i + 1), p3 = at(i + 2);
      d += `C${n1(p1[0] + (p2[0] - p0[0]) / 6)} ${n1(p1[1] + (p2[1] - p0[1]) / 6)} ${n1(p2[0] - (p3[0] - p1[0]) / 6)} ${n1(p2[1] - (p3[1] - p1[1]) / 6)} ${mv(p2)}`;
    }
    return closed ? d + 'Z' : d;
  }

  /* ---------- Aussehen der Elemente ---------- */

  const LOOKS = {
    erde:   { lane: 'step',  pattern: 'block' },
    feuer:  { lane: 'flame', pattern: 'tri' },
    wasser: { lane: 'wave',  pattern: 'scallop' },
    luft:   { lane: 'curl',  pattern: 'ring' },
    licht:  { lane: 'ray',   pattern: 'ray' },
    dunkel: { lane: 'veil',  pattern: 'moon' },
    mystic: { lane: 'spark', pattern: 'star' },
    natura: { lane: 'vine',  pattern: 'leaf' },
  };
  const LANE_CYCLE = ['smooth', 'wave', 'flame', 'curl', 'step', 'veil'];
  const PATTERN_CYCLE = ['tri', 'scallop', 'block', 'ring', 'ray', 'moon', 'star', 'leaf'];

  function lookOf(el, fallbackIndex) {
    if (el && el.look) return el.look;
    if (el && LOOKS[el.id]) return LOOKS[el.id];
    return { lane: LANE_CYCLE[fallbackIndex % LANE_CYCLE.length], pattern: PATTERN_CYCLE[fallbackIndex % PATTERN_CYCLE.length] };
  }

  const THEMES = {
    ink:   { label: 'Tinte',          paper: '#f3ead7', ink: '#1d1812', colors: false },
    color: { label: 'Elementfarben',  paper: '#f3ead7', ink: '#1d1812', colors: true },
    glow:  { label: 'Leuchtend',      paper: '#0e0c14', ink: '#efe3c6', colors: true, lighten: true, glow: true },
  };

  // Farben stammen aus Daten (auch aus eingebetteten Daten fremder Dateien): nur #rrggbb, sonst Grau
  const safeColor = (c) => (/^#[0-9a-fA-F]{6}$/.test(String(c)) ? String(c) : '#888888');

  function lighten(hex, amount) {
    const v = parseInt(hex.slice(1), 16);
    const c = [(v >> 16) & 255, (v >> 8) & 255, v & 255].map((x) => Math.round(x + (255 - x) * amount));
    return '#' + c.map((x) => x.toString(16).padStart(2, '0')).join('');
  }

  /* ---------- Bahnen ---------- */

  function tri(x) { return 2 * Math.abs(2 * (x - Math.floor(x + 0.5))) - 1; } // Dreieckswelle [-1, 1]

  // Mittellinie einer Bahn als Punktfolge, je nach Stil verformt.
  function laneLines(style, rng, o) {
    const ph = rng.range(0, TAU);
    if (style === 'step') {
      const steps = rng.int(7, 10);
      const pts = [pt(o.r0, o.th0)];
      let prevTh = o.th0;
      for (let k = 1; k <= steps; k++) {
        const t = k / steps;
        const r = o.r0 + (o.r1 - o.r0) * t;
        const th = o.th0 + o.spin * Math.pow(t, 0.85);
        pts.push(pt(r, prevTh));
        for (let j = 1; j <= 3; j++) pts.push(pt(r, prevTh + ((th - prevTh) * j) / 3));
        prevTh = th;
      }
      return { lines: [pts], smooth: false, dash: [10, 20], gap: [3, 7] };
    }
    const N = 72;
    const spin = style === 'ray' ? o.spin * 0.1 : o.spin;
    const base = [];
    for (let i = 0; i <= N; i++) {
      const t = i / N;
      base.push(pt(o.r0 + (o.r1 - o.r0) * t, o.th0 + spin * Math.pow(t, 0.85)));
    }
    const cum = [0];
    for (let i = 1; i <= N; i++) cum.push(cum[i - 1] + Math.hypot(base[i][0] - base[i - 1][0], base[i][1] - base[i - 1][1]));
    const shift = (fn) => base.map((p, i) => {
      const a = base[Math.max(0, i - 1)], b = base[Math.min(N, i + 1)];
      let tx = b[0] - a[0], ty = b[1] - a[1];
      const l = Math.hypot(tx, ty) || 1;
      tx /= l; ty /= l;
      const [al, ac] = fn(cum[i], i / N);
      return [p[0] + tx * al - ty * ac, p[1] + ty * al + tx * ac];
    });
    switch (style) {
      case 'wave':  return { lines: [shift((s, t) => [0, 3.4 * Math.sin((TAU * s) / 17 + ph) * (0.5 + 0.5 * t)])], smooth: true, dash: [10, 28], gap: [3, 8] };
      case 'flame': return { lines: [shift((s, t) => [0, 3 * tri(s / 9 + ph / TAU) * (0.35 + 0.9 * t)])], smooth: false, dash: [6, 14], gap: [3, 6] };
      case 'curl':  return { lines: [shift((s) => [2.7 * Math.sin((TAU * s) / 9.5 + ph), 2.7 * Math.cos((TAU * s) / 9.5 + ph)])], smooth: true, dash: [18, 34], gap: [5, 10] };
      case 'vine':  return { lines: [shift((s) => [1.8 * Math.sin((TAU * s) / 14 + ph), 1.8 * Math.cos((TAU * s) / 14 + ph)])], smooth: true, dash: [16, 30], gap: [4, 9] };
      case 'ray':   return { lines: [shift(() => [0, 0])], smooth: true, dash: [5, 7], gap: [4, 6] };
      case 'veil':  return { lines: [shift((s) => [0, 1.9 + 1.2 * Math.sin((TAU * s) / 22 + ph)]), shift((s) => [0, -1.9 - 1.2 * Math.sin((TAU * s) / 22 + ph)])], smooth: true, dash: [18, 40], gap: [6, 12] };
      case 'spark': return { lines: [shift((s) => [0, 1.2 * Math.sin((TAU * s) / 30 + ph)])], smooth: true, dash: [2.5, 7], gap: [4, 9] };
      default:      return { lines: [shift((s) => [0, 1.1 * Math.sin((TAU * s) / 30 + ph)])], smooth: true, dash: [7, 24], gap: [3, 9] };
    }
  }

  function dashed(pts, rng, dash, gap) {
    const cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    const total = cum[cum.length - 1];
    const at = (s) => {
      let i = 1;
      while (i < pts.length - 1 && cum[i] < s) i++;
      const t = (s - cum[i - 1]) / ((cum[i] - cum[i - 1]) || 1);
      return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t];
    };
    const out = [];
    let s = rng.range(0, gap[1] * 0.6);
    while (s < total) {
      const e = Math.min(total, s + rng.range(dash[0], dash[1]));
      if (e - s > 1.2) {
        const seg = [at(s)];
        for (let i = 1; i < pts.length - 1; i++) if (cum[i] > s && cum[i] < e) seg.push(pts[i]);
        seg.push(at(e));
        out.push(seg);
      }
      s = e + rng.range(gap[0], gap[1]);
    }
    return out;
  }

  /* ---------- Musterbänder ---------- */

  // Ein Feld des Bandes (Winkel a, Breite step); liefert Pfade und Punkte
  function slot(type, i, a, step, rIn, rOut) {
    const rm = (rIn + rOut) / 2;
    const hh = (rOut - rIn) / 2 - 1.5;
    const paths = [], dots = [];
    switch (type) {
      case 'tri': {
        const b1 = pt(rIn + 1.5, a - step * 0.42), b2 = pt(rIn + 1.5, a + step * 0.42);
        paths.push(polyD([b1, pt(rOut - 1.5 - (i % 2 ? hh * 0.5 : 0), a), b2], false));
        paths.push(polyD([pt(rIn + 1.5 + hh * 0.35, a - step * 0.2), pt(rm + hh * 0.1, a), pt(rIn + 1.5 + hh * 0.35, a + step * 0.2)], false));
        break;
      }
      case 'scallop': {
        const c = pt(rIn + 1.5 + hh * 2.1, a);
        paths.push(`M${mv(pt(rIn + 1.5, a - step * 0.5))}Q${mv(c)} ${mv(pt(rIn + 1.5, a + step * 0.5))}`);
        const c2 = pt(rIn + 1.5 + hh * 1.1, a);
        paths.push(`M${mv(pt(rIn + 1.5, a - step * 0.3))}Q${mv(c2)} ${mv(pt(rIn + 1.5, a + step * 0.3))}`);
        break;
      }
      case 'block': {
        const w = step * 0.4;
        const r0 = rIn + 2, r1 = rOut - 2;
        paths.push(polyD([pt(r0, a - w), pt(r1, a - w), pt(r1, a + w), pt(r0, a + w)], true));
        if (i % 2) paths.push(polyD([pt(rm - hh * 0.5, a - w * 0.5), pt(rm + hh * 0.5, a - w * 0.5), pt(rm + hh * 0.5, a + w * 0.5), pt(rm - hh * 0.5, a + w * 0.5)], true));
        break;
      }
      case 'ring': {
        const c = pt(rm, a);
        paths.push(`M${n1(c[0] - hh * 0.62)} ${n1(c[1])}a${n1(hh * 0.62)} ${n1(hh * 0.62)} 0 1 0 ${n1(hh * 1.24)} 0a${n1(hh * 0.62)} ${n1(hh * 0.62)} 0 1 0 ${n1(-hh * 1.24)} 0`);
        dots.push({ c, r: 1.2 });
        break;
      }
      case 'ray': {
        const tip = i % 2 ? rm : rOut - 1.5;
        paths.push(polyD([pt(rIn + 1.5, a), pt(tip, a)], false));
        dots.push({ c: pt(tip + 1.8, a), r: 1.1 });
        break;
      }
      case 'moon': {
        const top = pt(rm + hh * 0.95, a), bot = pt(rm - hh * 0.95, a);
        paths.push(`M${mv(bot)}A${n1(hh)} ${n1(hh)} 0 0 1 ${mv(top)}A${n1(hh * 1.7)} ${n1(hh * 1.7)} 0 0 0 ${mv(bot)}Z`);
        dots.push({ c: pt(rm, a + step * 0.5), r: 1 });
        break;
      }
      case 'star': {
        if (i % 2) { dots.push({ c: pt(rm, a), r: 1.5 }); break; }
        const pts = [];
        for (let k = 0; k < 8; k++) {
          const ang = (k * TAU) / 8;
          const rr = k % 2 === 0 ? (k % 4 === 0 ? hh * 0.98 : hh * 0.62) : hh * 0.22;
          // radiale Spitze zeigt nach außen: lokale x-Achse = radial
          const lx = Math.cos(ang) * rr, ly = Math.sin(ang) * rr;
          const c = pt(rm, a);
          pts.push([c[0] + lx * Math.cos(a) - ly * Math.sin(a), c[1] + lx * Math.sin(a) + ly * Math.cos(a)]);
        }
        paths.push(polyD(pts, true));
        break;
      }
      case 'leaf': {
        const dir = i % 2 ? -1 : 1;
        const b = pt(rIn + 1.5, a - dir * step * 0.22), t = pt(rOut - 1.5, a + dir * step * 0.22);
        const mx = (b[0] + t[0]) / 2, my = (b[1] + t[1]) / 2;
        const nx = -(t[1] - b[1]), ny = t[0] - b[0];
        const nl = Math.hypot(nx, ny) || 1;
        const o = hh * 0.55;
        paths.push(`M${mv(b)}Q${n1(mx + (nx / nl) * o)} ${n1(my + (ny / nl) * o)} ${mv(t)}Q${n1(mx - (nx / nl) * o)} ${n1(my - (ny / nl) * o)} ${mv(b)}Z`);
        paths.push(polyD([b, t], false));
        break;
      }
      default:
        dots.push({ c: pt(rm, a), r: 1.4 });
    }
    return { paths, dots };
  }

  const PITCH = { tri: 9, scallop: 11, block: 8, ring: 10, ray: 6.5, moon: 11, star: 9, leaf: 9, dots: 7 };

  // Anzahl der Felder: Vielfaches der Symmetrie V, damit alles ausgerichtet bleibt
  function slotCount(r, pitch, V, motifs) {
    const unit = V * motifs;
    return Math.max(unit * 2, unit * Math.round((TAU * r) / pitch / unit));
  }

  /* ---------- Siegel zusammenstellen ---------- */

  function effectiveParams(data, idx, id, params) {
    const out = [];
    let tree;
    try { tree = M.expand(idx, id); } catch (e) { return out; }
    Object.keys(M.primeCounts(tree)).sort().forEach((pid) => {
      const el = idx.byId.get(pid);
      const c = el && el.cost;
      if (!c) return;
      const defs = c.model === 'curve' ? [c.main].concat(c.factors || []) : [c.param];
      defs.forEach((def) => {
        const given = params && params[pid] && params[pid][def.id];
        const v = given !== undefined && given !== '' && Number.isFinite(Number(given)) ? Number(given) : (c.model === 'catalog' ? (given || c.default) : def.default);
        out.push(`${pid}.${def.id}=${v}`);
      });
    });
    return out;
  }

  // Teile des Siegels in kanonischer Reihenfolge; Reihenfolge der Eingabe ist egal.
  function canonicalParts(data, spec) {
    const idx = M.buildIndex(data);
    const parts = [];
    (spec.parts || []).forEach((p) => {
      if (p.kind === 'element') {
        let tree;
        try { tree = M.expand(idx, p.id); } catch (e) { return; }
        const primes = [];
        (function walk(n) { if (!n.children.length) { if (!primes.includes(n.id)) primes.push(n.id); } else n.children.forEach(walk); })(tree);
        parts.push({
          kind: 'element', name: tree.el.name, primes, fused: tree.levels > 0, place: tree.el.place || 'outer',
          key: `e:${p.id}:${effectiveParams(data, idx, p.id, p.params).join(',')}`,
        });
      } else if (p.kind === 'battery' || p.kind === 'generator') {
        const def = data.components.find((c) => c.id === p.ref);
        if (!def) return;
        parts.push({
          kind: p.kind, name: def.name, primes: [], fused: false, place: def.place || 'inner',
          key: p.kind === 'battery' ? `b:${p.ref}` : `g:${p.ref}:${p.source}:${p.level}:${p.amount == null ? 1 : p.amount}`,
        });
      } else if (p.kind === 'seal') {
        const sub = canonicalParts(data, p.spec || {});
        parts.push({ kind: 'seal', name: 'Siegel', primes: [], fused: false, place: 'inner', key: `s:[${sub.map((x) => x.key).join('|')}]` });
      }
    });
    return parts.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  }

  function blobPts(rng, r, k, jitter) {
    const pts = [];
    for (let i = 0; i < k; i++) {
      const a = (i / k) * TAU + rng.range(-0.12, 0.12);
      pts.push(pt(r * (1 + rng.range(-jitter, jitter)), a));
    }
    return pts;
  }

  function build(data, spec, opts) {
    // placement: 'auto' = jedes Teil nach seiner Definition (innen oder außen), 'inner'/'outer' = alle gleich
    opts = Object.assign({ theme: 'ink', label: '', placement: 'auto' }, opts || {});
    const theme = THEMES[opts.theme] || THEMES.ink;
    const parts = canonicalParts(data, spec);
    if (!parts.length) return { empty: true, svg: '', meta: {} };
    const idx = M.buildIndex(data);
    const analysis = W.Calc.analyze(data, spec);

    const labelWords = S.parseText(opts.label).words;
    const seedText = `v1|${parts.map((p) => p.key).join('|')}|${labelWords.join(' ')}`;
    const rng = createRng(seedText);
    const alphabet = S.buildAlphabet(KEY);

    const V = parts.length >= 3 ? parts.length : 4;
    const color = (id) => {
      if (!theme.colors) return theme.ink;
      const c = safeColor((idx.byId.get(id) || {}).color);
      return theme.lighten ? lighten(c, 0.35) : c;
    };

    // Elemente (Urelemente in Reihenfolge des Auftretens) und ihr Aussehen
    const primeOrder = [];
    parts.forEach((p) => p.primes.forEach((id) => { if (!primeOrder.includes(id)) primeOrder.push(id); }));
    const primeEls = data.elements.filter((e) => e.kind === 'prime');
    const looks = {};
    primeOrder.forEach((id) => { const el = idx.byId.get(id); looks[id] = lookOf(el, Math.max(0, primeEls.indexOf(el))); });

    // Bänder: je Element ein Musterband, je Gegensatz ein Flechtband
    const bands = [];
    parts.filter((p) => p.kind === 'element').forEach((p) => bands.push({ type: 'pattern', motifs: p.primes, fused: p.fused }));
    if (!bands.length) bands.push({ type: 'pattern', motifs: [null], fused: false });
    analysis.oppositions.forEach((o) => bands.push({ type: 'braid', a: o.from, b: o.to }));

    const H = { frame: 10, inscr: 27, pattern: 16, braid: 15, gap: 3.5, core: 14, laneMin: 52 + 10 * Math.min(primeOrder.length, 6) };
    const bandsH = bands.reduce((a, b) => a + (b.type === 'braid' ? H.braid : H.pattern) + H.gap, 0);

    // Kreise der Teile: Größe nach Wortlänge und Siegelgröße, Platz innen oder außen nach Definition
    const placeOf = (p) => (opts.placement === 'inner' || opts.placement === 'outer' ? opts.placement : p.place);
    const hasInner = parts.some((p) => placeOf(p) === 'inner');
    const sizeFactor = hasInner
      ? 1 + Math.min(0.8, (bandsH + H.inscr) / 260)
      : Math.min(1.7, Math.max(1, (H.core + H.laneMin + bandsH + H.inscr + H.frame + 8) / 150));
    const sats = parts.map((p) => {
      const word = p.name.toLowerCase().replace(/[^a-zäöüß0-9]/g, '');
      const len = Array.from(word).length;
      return { part: p, word, place: placeOf(p), rs: Math.min(40, Math.max(24, 18 + 4.4 * Math.sqrt(len))) * sizeFactor };
    });
    const maxOf = (list) => (list.length ? Math.max(...list.map((x) => x.rs)) : 0);
    const maxRsIn = maxOf(sats.filter((x) => x.place === 'inner'));
    const maxRsOut = maxOf(sats.filter((x) => x.place === 'outer'));
    const maxRs = Math.max(maxRsIn, maxRsOut);
    // Innen: Kreise sitzen auf einem Ring um den Kern; der Bahnenbereich muss sie fassen
    const rho = Math.max((V * maxRsIn * 1.25) / Math.PI, maxRsIn * 1.9, H.core + maxRsIn + 6);
    const laneNeed = hasInner ? Math.max(H.laneMin, rho + maxRsIn + 8) : H.laneMin;
    const needBands = H.core + laneNeed + bandsH + H.inscr + H.frame + 8;
    const needSat = maxRsOut ? (V * maxRsOut * 1.2) / Math.PI : 0;
    const R = Math.max(needBands, needSat, 120);

    const out = [];
    const sw = { frame: 2.4, thin: 1.2, band: 1.5, lane: 2, glyph: 2 };
    const group = (attrs, inner) => out.push(`<g ${attrs}>${inner}</g>`);
    const strokeAttr = (c, w, extra, fill) => `fill="${fill || 'none'}" stroke="${c}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"${extra || ''}`;
    const circleD = (r) => `M${n1(-r)} 0a${n1(r)} ${n1(r)} 0 1 0 ${n1(2 * r)} 0a${n1(r)} ${n1(r)} 0 1 0 ${n1(-2 * r)} 0`;
    const a0 = rng.range(0, TAU);

    // Positionen: Teile gleichmäßig auf die Ecken verteilen (2 Teile bei V=4 liegen sich gegenüber)
    const slotOf = sats.map((_, j) => Math.floor((j * V) / sats.length));
    sats.forEach((sat, j) => {
      sat.vertex = slotOf[j];
      sat.angle = a0 + (sat.vertex / V) * TAU;
      sat.c = pt(sat.place === 'inner' ? rho : R, sat.angle);
    });
    // Die Umgebung reagiert: um jedes Zeichen bleibt eine Fläche frei (Bahnen, Muster und Schrift weichen aus)
    const holes = sats.map((sat) => ({ c: sat.c, r: sat.rs * 1.16 + 3 }));
    const inHole = (q, margin) => holes.some((h) => Math.hypot(q[0] - h.c[0], q[1] - h.c[1]) < h.r + (margin || 0));

    // Radien von außen nach innen
    let r = R;
    const frameOut = r, frameIn = r - 7;
    r = frameIn - 3;
    const inscrOut = r, inscrIn = r - H.inscr;
    r = inscrIn - H.gap;
    const bandRadii = bands.map((b) => {
      const h = b.type === 'braid' ? H.braid : H.pattern;
      const o = { out: r, in: r - h };
      r = o.in - H.gap;
      return o;
    });
    const laneOut = r - 4;

    /* --- Bahnen (innen) --- */
    {
      const lanesRng = rng.fork('lanes');
      const complexity = analysis.complexity.total;
      const rl = (H.core + laneOut) / 2;
      const m = Math.max(1, Math.ceil((rl * TAU) / 17 / V));
      let count = V * m;
      while (count > 44 && count > V) count -= V;
      void complexity;
      const styles = primeOrder.length ? primeOrder.map((id) => ({ id, style: looks[id].lane })) : [{ id: null, style: 'smooth' }];
      const spinDir = lanesRng.sign();
      const spin = spinDir * lanesRng.range(0.9, 1.5);
      const body = [];
      const addLane = (st, th0, sp, r0, r1, colorId) => {
        const g = laneLines(st, lanesRng, { th0, spin: sp, r0, r1 });
        let d = '';
        g.lines.forEach((pts) => dashed(pts, lanesRng, g.dash, g.gap)
          .filter((seg) => !seg.some((q) => inHole(q, 1.5)))
          .forEach((seg) => { d += g.smooth ? smoothD(seg, false) : polyD(seg, false); }));
        body.push(`<path d="${d}" ${strokeAttr(colorId ? color(colorId) : theme.ink, sw.lane)}/>`);
      };
      for (let i = 0; i < count; i++) {
        const s = styles[i % styles.length];
        const r0 = H.core + (i % 2 ? 12 : 0) + lanesRng.range(0, 3);
        const r1 = laneOut - lanesRng.range(0, 6);
        addLane(s.style, a0 + (i / count) * TAU + lanesRng.range(-0.05, 0.05), spin * lanesRng.range(0.92, 1.08), r0, r1, s.id);
      }
      // Gegensätze: gegenläufige Bahnen in den Farben beider Seiten
      analysis.oppositions.forEach((o, k) => {
        const n = Math.min(V, 8);
        for (let i = 0; i < n; i++) {
          const sideId = i % 2 ? o.to : o.from;
          addLane(looks[sideId] ? looks[sideId].lane : 'smooth', a0 + ((i + 0.5) / n) * TAU + k * 0.3, -spin * lanesRng.range(0.9, 1.1), H.core + 10, laneOut - 2, sideId);
        }
      });
      group('id="bahnen"', body.join(''));
    }

    /* --- Bänder --- */
    bands.forEach((b, bi) => {
      const rr = bandRadii[bi];
      const bandRng = rng.fork('band' + bi);
      const body = [];
      body.push(`<path d="${circleD(rr.out)}" ${strokeAttr(theme.ink, sw.thin)}/>`);
      body.push(`<path d="${circleD(rr.in)}" ${strokeAttr(theme.ink, sw.thin)}/>`);
      if (b.type === 'pattern') {
        const motifs = b.motifs.map((id) => (id ? looks[id].pattern : PATTERN_CYCLE[bandRng.int(0, PATTERN_CYCLE.length - 1)]));
        const pitch = Math.max(...motifs.map((t) => PITCH[t] || 8));
        const n = slotCount((rr.in + rr.out) / 2, pitch, V, motifs.length);
        const step = TAU / n;
        const items = b.motifs.map(() => ({ d: '', dots: '' }));
        for (let i = 0; i < n; i++) {
          const mi = i % motifs.length;
          if (inHole(pt((rr.in + rr.out) / 2, a0 + i * step), 3)) continue;
          const sl = slot(motifs[mi], Math.floor(i / motifs.length), a0 + i * step, step, rr.in, rr.out);
          items[mi].d += sl.paths.join('');
          sl.dots.forEach((d) => { items[mi].dots += `<circle cx="${n1(d.c[0])}" cy="${n1(d.c[1])}" r="${d.r}"/>`; });
        }
        items.forEach((it, mi) => {
          const c = b.motifs[mi] ? color(b.motifs[mi]) : theme.ink;
          body.push(`<path d="${it.d}" ${strokeAttr(c, sw.band)}/><g fill="${c}">${it.dots}</g>`);
        });
      } else {
        const k = V * 3;
        const rm = (rr.in + rr.out) / 2, amp = (rr.out - rr.in) / 2 - 2;
        const wave = (sgn) => {
          const pts = [];
          for (let i = 0; i <= 360; i++) { const th = (i / 360) * TAU; pts.push(pt(rm + sgn * amp * Math.sin(k * (th - a0)), th)); }
          return smoothD(pts, true);
        };
        body.push(`<path d="${wave(1)}" ${strokeAttr(color(b.a), 1.9)}/>`);
        body.push(`<path d="${wave(-1)}" ${strokeAttr(color(b.b), 1.9)}/>`);
        let dots = '';
        for (let i = 0; i < k * 2; i++) { const c = pt(rm, a0 + (i * Math.PI) / k); dots += `<circle cx="${n1(c[0])}" cy="${n1(c[1])}" r="1.5"/>`; }
        body.push(`<g fill="${theme.ink}">${dots}</g>`);
      }
      group(`id="band${bi}"`, body.join(''));
    });

    /* --- Inschrift --- */
    {
      const rm = (inscrOut + inscrIn) / 2;
      const words = labelWords.length ? labelWords : S.parseText(parts.map((p) => p.name).join(' ')).words;
      const tokens = [];
      words.forEach((w) => { Array.from(w).forEach((ch) => tokens.push(ch)); tokens.push('·'); });
      const gh = INSCRIPTION_GLYPH;
      const pitch = gh * 0.6 + 7;
      const circ = TAU * rm;
      let seq = tokens;
      const maxTokens = Math.floor(circ / (gh * 0.6 + 4));
      if (seq.length > maxTokens) seq = seq.slice(0, maxTokens);
      const reps = Math.max(1, Math.floor(circ / pitch / seq.length));
      const total = reps * seq.length;
      const body = [];
      body.push(`<path d="${circleD(inscrOut)}" ${strokeAttr(theme.ink, sw.thin)}/>`);
      body.push(`<path d="${circleD(inscrIn)}" ${strokeAttr(theme.ink, sw.thin)}/>`);
      for (let i = 0; i < total; i++) {
        const tk = seq[i % seq.length];
        const a = a0 + (i / total) * TAU;
        const c = pt(rm, a);
        if (inHole(c, 4)) continue;
        const tf = `translate(${n1(c[0])} ${n1(c[1])}) rotate(${n1((a * 180) / Math.PI + 90)})`;
        if (tk === '·') body.push(`<g transform="${tf}"><path d="M0 -3L2.4 0L0 3L-2.4 0Z" fill="${theme.ink}"/></g>`);
        else body.push(`<g transform="${tf}">${S.layoutToSvg(S.layoutWord(tk, alphabet, 0, 0, gh * 0.6, gh), theme.ink)}</g>`);
      }
      group('id="inschrift"', body.join(''));
    }

    /* --- Rahmen --- */
    {
      const body = [`<path d="${circleD(frameOut)}" ${strokeAttr(theme.ink, sw.frame)}/>`, `<path d="${circleD(frameIn)}" ${strokeAttr(theme.ink, sw.thin)}/>`];
      let ticks = '';
      const tn = V * Math.max(6, Math.round((TAU * frameOut) / 6 / V));
      for (let i = 0; i < tn; i++) { const a = a0 + (i / tn) * TAU; ticks += `M${mv(pt(frameIn + 1, a))}L${mv(pt(frameOut - 1, a))}`; }
      body.push(`<path d="${ticks}" ${strokeAttr(theme.ink, 0.8)}/>`);
      group('id="rahmen"', body.join(''));
    }

    /* --- Kern --- */
    {
      const body = [];
      const petals = Math.max(3, primeOrder.length);
      let d = '';
      for (let i = 0; i < petals; i++) {
        const a = a0 + (i / petals) * TAU;
        const tip = pt(H.core * 0.95, a), l = pt(H.core * 0.45, a - 0.5), rgt = pt(H.core * 0.45, a + 0.5);
        d += `M${mv(pt(2, a))}Q${mv(l)} ${mv(tip)}Q${mv(rgt)} ${mv(pt(2, a))}Z`;
      }
      body.push(`<path d="${d}" ${strokeAttr(theme.ink, 1.4)}/>`);
      body.push(`<path d="${circleD(H.core + 1.5)}" ${strokeAttr(theme.ink, 1.6)}/>`);
      body.push(`<path d="${circleD(2.2)}" fill="${theme.ink}"/>`);
      group('id="kern"', body.join(''));
    }

    /* --- Sternpolygone durch die Teile --- */
    const starR = hasInner ? rho : (H.core + laneOut) * 0.62;
    {
      const k = V % 2 ? Math.floor((V - 1) / 2) : Math.max(1, V / 2 - 1);
      let step = k;
      while (gcd(V, step) > 1 && step > 1) step--; // möglichst ein zusammenhängender Stern
      const g = gcd(V, step);
      const star = (rad, offset, w) => {
        let d = '';
        for (let s = 0; s < g; s++) {
          const pts = [];
          for (let v = s, c = 0; c < V / g; c++, v = (v + step) % V) pts.push(pt(rad, offset + (v / V) * TAU));
          d += polyD(pts, true);
        }
        return `<path d="${d}" ${strokeAttr(theme.ink, w, ' opacity="0.9"')}/>`;
      };
      group('id="stern"', star(starR, a0, 1.5) + star(starR * 0.55, a0 + Math.PI / V, 1));
    }

    /* --- Kreise der Teile --- */
    {
      const satRng = rng.fork('sats');
      const body = [];
      for (let i = 0; i < V; i++) {
        const a = a0 + (i / V) * TAU;
        const sat = sats[slotOf.indexOf(i)];
        // Knoten auf dem inneren Stern; bei außen liegenden Zeichen markiert er den Anschluss
        const node = `<g transform="translate(${mv(pt(starR, a))})"><path d="M0 -5L5 0L0 5L-5 0Z" ${strokeAttr(theme.ink, 1.4, '', theme.paper)}/><circle r="1.4" fill="${theme.ink}"/></g>`;
        if (!sat) { body.push(node); continue; }
        if (sat.place === 'outer') body.push(node);
        const c = sat.c;
        const { rs, part } = sat;
        let outline, decor = '';
        if (part.kind === 'battery') {
          const pts = [[-rs * 0.95, -rs * 0.8], [rs * 0.95, -rs * 0.8], [rs * 0.95, rs * 0.8], [-rs * 0.95, rs * 0.8]].map((p) => [p[0] + satRng.range(-1.2, 1.2), p[1] + satRng.range(-1.2, 1.2)]);
          outline = polyD(pts, true);
          decor = `<path d="${polyD(pts.map((p) => [p[0] * 0.86, p[1] * 0.86]), true)}" ${strokeAttr(theme.ink, 1)}/>`;
        } else if (part.kind === 'generator' || part.kind === 'seal') {
          const pts = Array.from({ length: 6 }, (_, j) => pt(rs * 1.02, (j / 6) * TAU + Math.PI / 6 + satRng.range(-0.04, 0.04)));
          outline = polyD(pts, true);
          decor = `<path d="${polyD(pts.map((p) => [p[0] * 0.86, p[1] * 0.86]), true)}" ${strokeAttr(theme.ink, 1)}/>`;
        } else {
          outline = smoothD(blobPts(satRng, rs, 10, 0.06), true);
          if (part.fused) decor = `<path d="${smoothD(blobPts(satRng, rs * 0.88, 10, 0.05), true)}" ${strokeAttr(theme.ink, 1)}/>`;
          const m = part.primes.length;
          if (theme.colors && m) {
            part.primes.forEach((id, j) => {
              const a1 = (j / m) * TAU - Math.PI / 2 + 0.12, a2 = ((j + 1) / m) * TAU - Math.PI / 2 - 0.12;
              const rr = rs * 0.8;
              const p1 = pt(rr, a1), p2 = pt(rr, a2);
              decor += `<path d="M${mv(p1)}A${n1(rr)} ${n1(rr)} 0 ${a2 - a1 > Math.PI ? 1 : 0} 1 ${mv(p2)}" ${strokeAttr(color(id), 2.4)}/>`;
            });
          }
        }
        const word = S.layoutWord(sat.word, alphabet, 0, 0, rs * 1.15, rs * 1.15);
        body.push(`<g transform="translate(${mv(c)})"><circle r="${n1(rs * 1.16 + 3)}" ${strokeAttr(theme.ink, 0.8, ' stroke-opacity="0.6"', theme.paper)}/><path d="${outline}" ${strokeAttr(theme.ink, 2.2, '', theme.paper)}/>${decor}${S.layoutToSvg(word, theme.ink)}</g>`);
      }
      group('id="teile"', body.join(''));
    }

    const extent = (maxRsOut ? R + maxRsOut : R) + 12;
    const E = Math.ceil(extent);
    const glow = theme.glow
      ? '<defs><filter id="gl" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
      : '';
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${-E} ${-E} ${2 * E} ${2 * E}" width="${2 * E}" height="${2 * E}" role="img" aria-label="Wächter-Siegel"><title>Siegel ${seedId(seedText)}</title>${glow}<rect x="${-E}" y="${-E}" width="${2 * E}" height="${2 * E}" fill="${theme.paper}"/><g${theme.glow ? ' filter="url(#gl)"' : ''}>${out.join('')}</g></svg>`;

    return {
      empty: false,
      svg,
      meta: {
        id: seedId(seedText),
        radius: R,
        extent: E,
        symmetry: V,
        parts: parts.length,
        bands: bands.length,
        braids: analysis.oppositions.length,
        inside: sats.filter((x) => x.place === 'inner').length,
        outside: sats.filter((x) => x.place === 'outer').length,
        analysis,
      },
    };
  }

  W.Seal = { build, canonicalParts, THEMES, SCRIPT_KEY: KEY, INSCRIPTION_GLYPH };
  if (typeof module === 'object' && module.exports) module.exports = W.Seal;
})(typeof globalThis !== 'undefined' ? globalThis : this);
