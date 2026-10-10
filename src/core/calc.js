/*
 * Berechnung eines Siegels aus den Daten (Elemente, Rezepte, Gegensätze, Einstellungen).
 *
 * spec = {
 *   size: 1,                      // relativ zur Normalgröße (2 = doppelt so groß)
 *   carrier: 'body' | 'object',
 *   density: 'normal' | 'high',   // Energiedichte (nur Gegenstand ohne Generator)
 *   parts: [
 *     { kind: 'element',   id: 'eis', params: { wasser: { speed: 2 } } },
 *     { kind: 'battery',   ref: 'battery_small' },
 *     { kind: 'generator', ref: 'generator', source: 'body', level: 'regen', amount: 1 },
 *     { kind: 'seal',      spec: { ... } }          // Siegel im Siegel
 *   ]
 * }
 *
 * Typ = Anzahl der Teile der obersten Ebene. Ein verwobenes Element
 * (Eis = Wasser + Luft) zählt als EIN Teil, weil man seine Bestandteile
 * nicht einzeln herausbekommt.
 */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});
  const { interpolate, expCost } = W.Curves;
  const M = W.Model;

  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const hasValue = (v) => v !== undefined && v !== null && v !== '' && Number.isFinite(Number(v));
  const valueOf = (def, params) => (params && hasValue(params[def.id]) ? Number(params[def.id]) : def.default);

  function factorMult(f, v) {
    if (f.mode === 'points') {
      const r = interpolate(f.points, f.ref);
      return r > 0 ? interpolate(f.points, v) / r : 1;
    }
    return f.ref > 0 ? v / f.ref : 1;
  }

  // Nutzungskosten (jqm je Aktivierung) eines Urelements mit seinen Parametern
  function primeCost(el, params) {
    const c = el.cost;
    if (!c) return { cost: 0, details: [] };
    switch (c.model) {
      case 'curve': {
        const x = valueOf(c.main, params);
        let cost = interpolate(c.main.points, x);
        const details = [{ label: c.main.label, value: x, unit: c.main.unit }];
        (c.factors || []).forEach((f) => {
          const v = valueOf(f, params);
          cost *= factorMult(f, v);
          details.push({ label: f.label, value: v, unit: f.unit });
        });
        return { cost, details };
      }
      case 'exp': {
        const n = valueOf(c.param, params);
        return { cost: expCost(c.start, c.factor, n, !!c.cumulative), details: [{ label: c.param.label, value: n, unit: c.param.unit }] };
      }
      case 'catalog': {
        const wanted = params && params[c.param.id];
        const e = c.entries.find((x) => x.id === (wanted || c.default)) || c.entries[0];
        return { cost: e ? e.cost : 0, details: [{ label: c.param.label, value: e ? e.name : '–', unit: '' }] };
      }
      case 'direct': {
        const v = valueOf(c.param, params);
        return { cost: v, details: [{ label: c.param.label, value: v, unit: c.param.unit }] };
      }
      default:
        return { cost: 0, details: [] };
    }
  }

  // Nutzung eines Rezeptbaums. Jede Verwebung (derived) senkt die Nutzung.
  function nodeUsage(node, paramsByPrime, s) {
    if (!node.children.length) {
      const r = primeCost(node.el, paramsByPrime[node.id]);
      return { cost: r.cost, lines: [{ id: node.id, name: node.el.name, cost: r.cost, details: r.details }] };
    }
    const kids = node.children.map((c) => nodeUsage(c, paramsByPrime, s));
    const f = s.fuseUsage;
    return {
      cost: kids.reduce((a, k) => a + k.cost, 0) * f,
      lines: kids.flatMap((k) => k.lines).map((l) => ({ ...l, cost: l.cost * f })),
    };
  }

  // Komplexität: jede Verwebung erhöht sie (mehr Erschaffungsaufwand)
  function nodeComplexity(node, s) {
    if (!node.children.length) return node.el.complexity != null ? node.el.complexity : s.primeComplexity;
    return node.children.reduce((a, c) => a + nodeComplexity(c, s), 0) * s.fuseCreation;
  }

  function analyze(data, spec, depth) {
    depth = depth || 0;
    const s = data.settings;
    const index = M.buildIndex(data);
    const warnings = [];
    const warn = (level, text) => warnings.push({ level, text });
    const noted = new Set();
    const note = (key, level, text) => { if (!noted.has(key)) { noted.add(key); warn(level, text); } };

    const size = Math.max(Number(spec.size) || 1, 1e-6);
    const carrier = spec.carrier === 'object' ? 'object' : 'body';
    const parts = [];
    const primes = {};
    const generators = { rate: 0, stores: [] };
    let partsComplexity = 0;
    let effectsSum = 0;
    let nestDepth = 0;
    let hasBattery = false;
    let hasGenerator = false;

    (spec.parts || []).forEach((part) => {
      if (part.kind === 'element') {
        let tree;
        try { tree = M.expand(index, part.id); } catch (e) { warn('error', e.message); return; }
        const usage = nodeUsage(tree, part.params || {}, s);
        const complexity = nodeComplexity(tree, s);
        const counts = M.primeCounts(tree);
        Object.keys(counts).forEach((id) => {
          primes[id] = (primes[id] || 0) + counts[id];
          const el = index.byId.get(id);
          const c = el.cost || {};
          (c.factors || []).filter((f) => f.assumed).forEach((f) =>
            note(`f:${id}:${f.id}`, 'info', `${el.name}: ${f.label} ist eine Annahme (${f.mode === 'linear' ? 'linear' : 'Kurve'}), bitte im Editor prüfen.`));
          if (c.gaps && c.gaps.length)
            note(`g:${id}`, 'info', `${el.name}: ${c.gaps.join(', ')} noch nicht definiert (Referenz: ${c.reference || 'siehe Editor'}).`);
          if (c.param && c.param.assumed)
            note(`p:${id}`, 'info', `${el.name}: Einheit "${c.param.unit}" ist eine Annahme.`);
        });
        partsComplexity += complexity;
        effectsSum += usage.cost;
        parts.push({ kind: 'element', id: part.id, name: tree.el.name, levels: tree.levels, complexity, usage: usage.cost, lines: usage.lines });
      } else if (part.kind === 'battery' || part.kind === 'generator') {
        const def = data.components.find((c) => c.id === part.ref);
        if (!def) { warn('error', `Unbekanntes Bauteil: ${part.ref}`); return; }
        partsComplexity += def.complexity;
        const out = { kind: part.kind, ref: def.id, name: def.name, complexity: def.complexity };
        if (part.kind === 'battery') {
          hasBattery = true;
          if (def.capacity == null) note(`cap:${def.id}`, 'info', `${def.name}: Kapazität nicht definiert.`);
        } else {
          hasGenerator = true;
          const src = data.sources.find((x) => x.id === part.source);
          const lvl = src && src.levels.find((l) => l.id === part.level);
          if (!src || !lvl) warn('warn', 'Generator ohne gültige Quelle.');
          else if (src.kind === 'rate') {
            const rate = lvl.value * (src.areaScaling ? Math.pow(size, s.areaExponent) : 1);
            generators.rate += rate;
            out.source = `${src.name}: ${lvl.name}`;
            out.rate = rate;
          } else {
            const amount = hasValue(part.amount) ? Number(part.amount) : 1;
            generators.stores.push({ name: src.name, level: lvl.name, amount, total: lvl.value * amount, unit: src.consumes || '×' });
            out.source = `${src.name}: ${lvl.name}`;
            out.total = lvl.value * amount;
          }
        }
        parts.push(out);
      } else if (part.kind === 'seal') {
        const sub = analyze(data, part.spec || {}, depth + 1);
        const complexity = sub.complexity.total * s.nestingPenalty;
        partsComplexity += complexity;
        effectsSum += sub.usage.effects;
        nestDepth = Math.max(nestDepth, 1 + sub.nestDepth);
        sub.warnings.filter((w) => w.level === 'error').forEach((w) => warn('error', `Verschachteltes Siegel: ${w.text}`));
        parts.push({ kind: 'seal', name: sub.typLabel, complexity, usage: sub.usage.effects, sub });
      } else {
        warn('error', `Unbekannte Teileart: ${part.kind}`);
      }
    });

    // Gegensätze: alle Elemente in Urelemente zerlegen, jede Beziehung zählt einzeln
    const kinds = new Map((data.oppositionKinds || []).map((k) => [k.id, k]));
    const oppositions = [];
    (data.oppositions || []).forEach((o) => {
      if (primes[o.from] && primes[o.to]) {
        const kind = kinds.get(o.kind) || { name: o.kind, weight: 1 };
        oppositions.push({
          from: o.from, to: o.to, kind: o.kind,
          text: `${index.byId.get(o.from).name} ${kind.name} ${index.byId.get(o.to).name}`,
          weight: kind.weight,
        });
      }
    });
    const oppositionComplexity = oppositions.reduce((a, o) => a + o.weight * s.oppositionComplexity, 0);
    const total = partsComplexity + oppositionComplexity;

    // Größe: je größer, desto billiger die Erschaffung; komplexe/verschachtelte Siegel sparen weniger
    const t = clamp((total - s.complexityMin) / (s.complexityMax - s.complexityMin) + s.nestPenalty * nestDepth, 0, 1);
    const perDoubling = s.sizeSimple + t * (s.sizeComplex - s.sizeSimple);
    const doublings = Math.log2(size);
    const sizeMultiplier = Math.pow(perDoubling, -doublings);
    const creation = s.creationPerComplexity * total * sizeMultiplier;
    const usageSizeFactor = Math.pow(s.usagePerDoubling, -doublings);

    // Gegenstand: Batterie Pflicht, ohne Generator geht Energie über die Luft verloren
    let efficiency = 1;
    if (carrier === 'object') {
      if (!hasBattery) warn('error', 'Auf Gegenständen ist immer eine Batterie nötig.');
      if (!hasGenerator) {
        efficiency = spec.density === 'high' ? s.transferHigh : s.transferNormal;
        warn('info', `Kein Generator: Transfer über Luft nur ${Math.round(efficiency * 100)} % effizient (ein Generator wird empfohlen).`);
      }
    }
    const usage = (effectsSum * usageSizeFactor) / efficiency;

    return {
      typ: parts.length,
      typLabel: `Typ ${parts.length}`,
      parts,
      primes,
      oppositions,
      complexity: { parts: partsComplexity, oppositions: oppositionComplexity, total },
      size: { value: size, perDoubling, sizeMultiplier, usageFactor: usageSizeFactor },
      creation,
      usage: { effects: effectsSum, total: usage, efficiency },
      generators,
      nestDepth,
      warnings,
    };
  }

  W.Calc = { analyze, primeCost, nodeUsage, nodeComplexity };
  if (typeof module === 'object' && module.exports) module.exports = W.Calc;
})(typeof globalThis !== 'undefined' ? globalThis : this);
