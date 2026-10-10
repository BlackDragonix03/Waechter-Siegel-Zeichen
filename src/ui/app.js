/* Editor und Rechner der Wächter-Siegelwerkstatt (Oberfläche). */
(function () {
  'use strict';
  const W = window.Waechter;
  const M = W.Model;
  const KEY = 'waechter.data.v1';
  const SPEC_KEY = 'waechter.spec.v1';

  /* ---------- Zustand ---------- */

  const clone = (o) => JSON.parse(JSON.stringify(o));
  const defaultSpec = () => ({ size: 1, carrier: 'body', density: 'normal', parts: [] });

  function load(key, fallback) {
    try {
      const v = localStorage.getItem(key);
      if (v) return JSON.parse(v);
    } catch (e) { /* Speicher nicht verfügbar */ }
    return fallback();
  }
  let data = load(KEY, () => clone(W.defaultData));
  if (!data || !Array.isArray(data.elements) || data.version !== W.defaultData.version) data = clone(W.defaultData);
  let spec = load(SPEC_KEY, defaultSpec);
  if (!spec || !Array.isArray(spec.parts)) spec = defaultSpec();

  const TABS = [
    ['calc', 'Siegel-Rechner'],
    ['elements', 'Elemente'],
    ['recipes', 'Rezepte'],
    ['opposites', 'Gegensätze'],
    ['parts', 'Bauteile & Quellen'],
    ['settings', 'Einstellungen'],
    ['data', 'Daten'],
  ];
  let tab = (location.hash || '#calc').slice(1);
  if (!TABS.some((t) => t[0] === tab)) tab = 'calc';
  const openIds = new Set();

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(data));
      localStorage.setItem(SPEC_KEY, JSON.stringify(spec));
    } catch (e) { /* ignorieren */ }
  }
  function commit() { save(); render(); }

  /* ---------- Bausteine ---------- */

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    let value;
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'value') value = v;
      else if (k === 'checked') el.checked = !!v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    kids.flat(Infinity).forEach((c) => {
      if (c == null || c === false) return;
      el.append(c instanceof Node ? c : String(c));
    });
    if (value !== undefined) el.value = value;
    return el;
  }

  const nf = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 });
  const fmt = (n) => (Number.isFinite(n) ? nf.format(n >= 1000 ? Math.round(n) : Math.round(n * 100) / 100) : '–');

  function numInput(value, onChange, attrs) {
    const i = h('input', Object.assign({ type: 'number', step: 'any' }, attrs || {}));
    i.value = value == null ? '' : value;
    i.addEventListener('change', () => {
      const v = parseFloat(String(i.value).replace(',', '.'));
      if (Number.isFinite(v)) onChange(v); else i.value = value == null ? '' : value;
    });
    return i;
  }
  const textInput = (value, onChange, attrs) =>
    h('input', Object.assign({ type: 'text', value: value == null ? '' : value, onchange: (e) => onChange(e.target.value) }, attrs || {}));
  const checkbox = (checked, onChange) => h('input', { type: 'checkbox', checked, onchange: (e) => onChange(e.target.checked) });
  function select(options, value, onChange) {
    return h('select', { value, onchange: (e) => onChange(e.target.value) },
      options.map((o) => h('option', { value: o[0] }, o[1])));
  }
  const btn = (label, onClick, cls) => h('button', { class: 'btn ' + (cls || ''), type: 'button', onclick: onClick }, label);
  const field = (label, ...ctrl) => h('label', {}, label, ...ctrl);
  const assumedChip = (on) => (on ? h('span', { class: 'chip assumed', title: 'Annahme von Claude – bitte prüfen. Eine Änderung bestätigt den Wert.' }, 'Annahme') : null);

  // Wert setzen; eine Änderung bestätigt eine Annahme
  function edit(obj, key, v) {
    obj[key] = v;
    delete obj.assumed;
    commit();
  }

  function colorOf(el, depth) {
    depth = depth || 0;
    if (!el) return '#888';
    if (el.color) return el.color;
    if (el.recipe && depth < 8) {
      const first = data.elements.find((e) => e.id === el.recipe.ingredients[0]);
      return colorOf(first, depth + 1);
    }
    return '#888';
  }
  const dot = (el) => h('span', { class: 'dot', style: `background:${colorOf(el)}` });

  /* ---------- Siegel-Rechner ---------- */

  function renderCalc() {
    const idx = M.buildIndex(data);
    const res = W.Calc.analyze(data, spec);
    return h('div', { class: 'cols' },
      h('div', { class: 'col' }, controlsCard(), ...spec.parts.map((p, i) => partCard(p, i, idx)), addCard()),
      h('div', { class: 'col' }, resultCard(res)));
  }

  function controlsCard() {
    const label = h('b', {}, `×${fmt(spec.size)}`);
    const range = h('input', { type: 'range', min: -4, max: 4, step: 0.05, value: Math.log2(spec.size) });
    range.addEventListener('input', () => { label.textContent = `×${fmt(Math.pow(2, range.value))}`; });
    range.addEventListener('change', () => { spec.size = Math.round(Math.pow(2, range.value) * 1000) / 1000; commit(); });
    return h('div', { class: 'card' },
      h('h3', {}, 'Siegel'),
      h('div', { class: 'row' }, 'Größe', range, label, h('span', { class: 'muted' }, '(1 = Normalgröße)')),
      h('div', { class: 'row' },
        field('Träger ', select([['body', 'Körper'], ['object', 'Gegenstand']], spec.carrier, (v) => { spec.carrier = v; commit(); })),
        spec.carrier === 'object'
          ? field('Energiedichte ', select([['normal', 'normal'], ['high', 'hoch']], spec.density, (v) => { spec.density = v; commit(); }))
          : null,
        btn('Leeren', () => { spec.parts = []; commit(); }, 'danger')));
  }

  function removeBtn(i) { return btn('×', () => { spec.parts.splice(i, 1); commit(); }, 'x danger'); }

  function setParam(part, primeId, paramId, v) {
    part.params = part.params || {};
    (part.params[primeId] = part.params[primeId] || {})[paramId] = v;
    commit();
  }

  function paramRows(part, prime) {
    const c = prime.cost;
    if (!c) return [];
    const cur = (def) => (part.params && part.params[prime.id] && part.params[prime.id][def.id]);
    const row = (def) => h('label', { class: 'pf' }, h('span', {}, `${prime.name}: ${def.label}`),
      numInput(cur(def) != null ? cur(def) : def.default, (v) => setParam(part, prime.id, def.id, v)), h('em', { class: 'muted' }, def.unit));
    if (c.model === 'curve') return [row(c.main)].concat((c.factors || []).map(row));
    if (c.model === 'exp' || c.model === 'direct') return [row(c.param)];
    if (c.model === 'catalog') {
      return [h('label', { class: 'pf' }, h('span', {}, `${prime.name}: ${c.param.label}`),
        select(c.entries.map((e) => [e.id, e.name]), cur(c.param) || c.default || (c.entries[0] && c.entries[0].id),
          (v) => setParam(part, prime.id, c.param.id, v)))];
    }
    return [];
  }

  function partCard(part, i, idx) {
    if (part.kind === 'element') {
      const el = idx.byId.get(part.id);
      let tree;
      try { tree = M.expand(idx, part.id); } catch (e) { return h('div', { class: 'card part err' }, e.message, removeBtn(i)); }
      const usage = W.Calc.nodeUsage(tree, part.params || {}, data.settings);
      const primeIds = Object.keys(M.primeCounts(tree));
      return h('div', { class: 'card part' },
        h('div', { class: 'head' }, dot(el), el.name,
          tree.levels ? h('span', { class: 'chip' }, `verwoben, Ebene ${tree.levels}`) : null,
          h('span', { class: 'sp' }), h('span', { class: 'muted' }, `${fmt(usage.cost)} jqm`), removeBtn(i)),
        ...primeIds.flatMap((id) => paramRows(part, idx.byId.get(id))));
    }
    if (part.kind === 'battery' || part.kind === 'generator') {
      const def = data.components.find((c) => c.id === part.ref);
      const body = [];
      if (part.kind === 'generator') {
        const genSources = data.sources.filter((s) => s.placement !== 'carried');
        const src = genSources.find((s) => s.id === part.source) || genSources[0];
        if (!part.source) part.source = src.id;
        const lvl = src.levels.find((l) => l.id === part.level) || src.levels[0];
        part.level = lvl.id;
        body.push(h('div', { class: 'row' },
          field('Quelle ', select(genSources.map((s) => [s.id, s.name]), src.id, (v) => {
            part.source = v; part.level = data.sources.find((s) => s.id === v).levels[0].id; commit();
          })),
          field('Stufe ', select(src.levels.map((l) => [l.id, `${l.name} (${fmt(l.value)} ${src.unit})`]), lvl.id, (v) => { part.level = v; commit(); })),
          src.kind === 'store' ? field('Menge ', numInput(part.amount != null ? part.amount : 1, (v) => { part.amount = v; commit(); })) : null,
          assumedChip(src.assumed)));
        if (src.note) body.push(h('div', { class: 'hint' }, src.note));
      }
      return h('div', { class: 'card part' },
        h('div', { class: 'head' }, def ? def.name : `Unbekannt: ${part.ref}`, h('span', { class: 'chip' }, part.kind === 'battery' ? 'Batterie' : 'Generator'),
          h('span', { class: 'sp' }), removeBtn(i)), ...body);
    }
    if (part.kind === 'carried') {
      const carriedSources = data.sources.filter((s) => s.placement === 'carried');
      const src = carriedSources.find((s) => s.id === part.source) || carriedSources[0];
      if (!src) return h('div', { class: 'card part err' }, 'Keine getragene Quelle definiert.', removeBtn(i));
      part.source = src.id;
      const lvl = src.levels.find((l) => l.id === part.level) || src.levels[0];
      part.level = lvl.id;
      return h('div', { class: 'card part' },
        h('div', { class: 'head' }, src.name, h('span', { class: 'chip' }, 'am Körper getragen'), h('span', { class: 'sp' }), removeBtn(i)),
        h('div', { class: 'row' },
          field('Stufe ', select(src.levels.map((l) => [l.id, `${l.name} (${fmt(l.value)} jqm)`]), lvl.id, (v) => { part.level = v; commit(); })),
          field('Anzahl ', numInput(part.amount != null ? part.amount : 1, (v) => { part.amount = v; commit(); }))),
        h('div', { class: 'hint' }, 'Der Körper leitet die Energie zum Siegel; der Kristall ist kein Teil des Siegels.'),
        src.note ? h('div', { class: 'hint' }, src.note) : null);
    }
    return h('div', { class: 'card part err' }, `Unbekannte Teileart: ${part.kind}`, removeBtn(i));
  }

  function addCard() {
    const elSel = select(
      [['', '– Element wählen –']].concat(data.elements.map((e) => [e.id, `${e.name}${e.kind === 'derived' ? ' (verwoben)' : ''}`])), '', () => {});
    const compSel = select([['', '– Bauteil wählen –']].concat(data.components.map((c) => [c.id, c.name])), '', () => {});
    return h('div', { class: 'card' },
      h('h3', {}, 'Hinzufügen'),
      h('div', { class: 'row' }, elSel, btn('Element', () => {
        if (!elSel.value) return;
        spec.parts.push({ kind: 'element', id: elSel.value, params: {} }); commit();
      }, 'primary')),
      h('div', { class: 'row' }, compSel, btn('Bauteil', () => {
        const def = data.components.find((c) => c.id === compSel.value);
        if (!def) return;
        spec.parts.push(def.kind === 'generator'
          ? { kind: 'generator', ref: def.id, source: data.sources[0].id, level: data.sources[0].levels[0].id, amount: 1 }
          : { kind: 'battery', ref: def.id });
        commit();
      }, 'primary')),
      h('div', { class: 'row' }, btn('Kristall am Körper tragen', () => {
        const src = data.sources.find((x) => x.placement === 'carried');
        if (!src) { alert('Keine getragene Quelle definiert (Tab „Bauteile & Quellen“).'); return; }
        spec.parts.push({ kind: 'carried', source: src.id, level: src.levels[0].id, amount: 1 }); commit();
      }, 'primary')),
      h('p', { class: 'hint' }, 'Wasser und Luft einzeln sind Typ 2, Eis (verwoben) ist Typ 1: In der Nutzung billiger, in der Erschaffung teurer.'));
  }

  function resultCard(r) {
    const counts = Object.keys(r.primes).map((id) => {
      const el = data.elements.find((e) => e.id === id);
      return h('span', { class: 'chip' }, dot(el), ` ${el.name}${r.primes[id] > 1 ? ' ×' + r.primes[id] : ''}`);
    });
    const lines = r.parts.flatMap((p) => p.lines || []);
    const gen = r.generators;
    return h('div', { class: 'card' },
      h('div', { class: 'big' }, r.typLabel),
      h('div', { class: 'hint' }, 'Zählt die Teile der obersten Ebene; ein verwobenes Element ist ein Teil.'),
      h('div', { class: 'row' }, h('span', { class: 'muted' }, 'Urelemente:'), counts.length ? counts : h('span', { class: 'muted' }, 'keine')),
      h('h3', {}, 'Gegensätze'),
      r.oppositions.length
        ? h('ul', { class: 'clean' }, r.oppositions.map((o) => h('li', {}, o.text)))
        : h('div', { class: 'muted' }, 'keine'),
      h('div', { class: 'stats' },
        stat('Komplexität', fmt(r.complexity.total), `Teile ${fmt(r.complexity.parts)} + Gegensätze ${fmt(r.complexity.oppositions)}`),
        stat('Erschaffung', `${fmt(r.creation)} jqm`, `Größe ×${fmt(r.size.value)}: ${fmt(r.size.sizeMultiplier)}× Aufwand (je Verdopplung ${fmt(r.size.perDoubling)}× billiger)`),
        stat('Nutzung', `${fmt(r.usage.total)} jqm`, `je Aktivierung, Größenfaktor ${fmt(r.size.usageFactor)}, Wirkungsgrad ${Math.round(r.usage.efficiency * 100)} %`),
        stat('Generator', gen.rate ? `${fmt(gen.rate)} jqm/s` : '–', gen.stores.length ? gen.stores.map((s) => `${s.name}: ${fmt(s.total)} jqm`).join(', ') : 'Dauerleistung'),
        r.carried.length ? stat('Getragen', `${fmt(r.carried.reduce((a, c) => a + c.total, 0))} jqm`, r.carried.map((c) => `${c.amount}× ${c.name}, nicht aufladbar`).join(', ')) : null),
      lines.length
        ? h('table', {}, h('tr', {}, h('th', {}, 'Wirkung'), h('th', {}, 'Parameter'), h('th', {}, 'jqm')),
          lines.map((l) => h('tr', {}, h('td', {}, l.name), h('td', {}, l.details.map((d) => `${d.label} ${d.value}${d.unit ? ' ' + d.unit : ''}`).join(', ')), h('td', {}, fmt(l.cost)))))
        : null,
      r.warnings.length ? h('h3', {}, 'Hinweise') : null,
      r.warnings.map((w) => h('div', { class: 'msg ' + w.level }, w.text)));
  }
  const stat = (label, value, sub) => h('div', { class: 'stat' }, h('span', {}, label), h('b', {}, value), h('span', {}, sub));

  /* ---------- Elemente ---------- */

  const defaultCost = (model) => ({
    curve: { model: 'curve', main: { id: 'value', label: 'Wert', unit: '', default: 1, points: [[1, 10], [10, 100]] }, factors: [], reference: '' },
    exp: { model: 'exp', start: 1, factor: 1.1, cumulative: true, param: { id: 'amount', label: 'Menge', unit: '', default: 1 } },
    catalog: { model: 'catalog', param: { id: 'entry', label: 'Eintrag' }, default: '', entries: [] },
    direct: { model: 'direct', param: { id: 'jqm', label: 'Energie', unit: 'jqm', default: 100 } },
  }[model]);

  function pointsEditor(points, xl, yl) {
    const t = h('table', { class: 'pts' }, h('tr', {}, h('th', {}, xl), h('th', {}, yl), h('th', {})));
    points.forEach((p, i) => t.append(h('tr', {},
      h('td', {}, numInput(p[0], (v) => { p[0] = v; commit(); })),
      h('td', {}, numInput(p[1], (v) => { p[1] = v; commit(); })),
      h('td', {}, btn('×', () => { points.splice(i, 1); commit(); }, 'x danger')))));
    return h('div', {}, t, btn('+ Stützpunkt', () => {
      const last = points[points.length - 1] || [1, 1];
      points.push([last[0] * 2, last[1] * 2]); commit();
    }));
  }

  function paramDef(def, title) {
    return h('div', { class: 'row' }, h('b', {}, title),
      field('Name ', textInput(def.label, (v) => edit(def, 'label', v), { style: 'min-width:100px' })),
      field('Einheit ', textInput(def.unit, (v) => edit(def, 'unit', v), { style: 'min-width:60px;width:80px' })),
      def.default !== undefined ? field('Standard ', numInput(def.default, (v) => edit(def, 'default', v))) : null,
      assumedChip(def.assumed));
  }

  function costEditor(el) {
    const c = el.cost;
    const out = [h('div', { class: 'row' }, field('Kostenmodell ', select(
      [['curve', 'Kurve (Stützpunkte)'], ['exp', 'Exponentiell'], ['catalog', 'Katalog'], ['direct', 'Direkt 1:1']],
      c ? c.model : 'direct', (v) => { el.cost = defaultCost(v); commit(); })))];
    if (!c) return out;
    if (c.model === 'curve') {
      out.push(paramDef(c.main, 'Hauptwert'));
      out.push(pointsEditor(c.main.points, `${c.main.label} (${c.main.unit})`, 'Kosten (jqm)'));
      out.push(h('div', { class: 'hint' }, 'Zwischen den Punkten rechnet das Tool als Potenzgesetz (log-log), bei Nullwerten linear; außerhalb wird die letzte Steigung fortgesetzt.'));
      (c.factors || []).forEach((f, i) => {
        out.push(h('div', { class: 'row' }, h('b', {}, `Faktor ${i + 1}`),
          field('Name ', textInput(f.label, (v) => edit(f, 'label', v), { style: 'min-width:90px;width:110px' })),
          field('Einheit ', textInput(f.unit, (v) => edit(f, 'unit', v), { style: 'min-width:50px;width:70px' })),
          field('Bezug ', numInput(f.ref, (v) => edit(f, 'ref', v))),
          field('Standard ', numInput(f.default, (v) => edit(f, 'default', v))),
          field('Verlauf ', select([['linear', 'linear (doppelt = doppelt)'], ['points', 'Kurve']], f.mode, (v) => {
            f.mode = v; if (v === 'points' && !f.points) f.points = [[f.ref, 1], [f.ref * 2, 2]]; delete f.assumed; commit();
          })),
          assumedChip(f.assumed),
          btn('×', () => { c.factors.splice(i, 1); commit(); }, 'x danger')));
        if (f.mode === 'points') out.push(pointsEditor(f.points, `${f.label} (${f.unit})`, 'Faktor'));
      });
      out.push(btn('+ weiterer Faktor (z. B. Dauer)', () => {
        c.factors = c.factors || [];
        c.factors.push({ id: 'f' + (c.factors.length + 1), label: 'Dauer', unit: 's', ref: 1, default: 1, mode: 'linear' });
        commit();
      }));
    } else if (c.model === 'exp') {
      out.push(paramDef(c.param, 'Wert'));
      out.push(h('div', { class: 'row' },
        field('Start (jqm) ', numInput(c.start, (v) => edit(c, 'start', v))),
        field('Faktor ', numInput(c.factor, (v) => edit(c, 'factor', v))),
        field('Jede weitere Einheit teurer (Summe) ', checkbox(!!c.cumulative, (v) => edit(c, 'cumulative', v)))));
      out.push(h('div', { class: 'hint' }, c.cumulative
        ? 'n Einheiten kosten die Summe: Start, Start·Faktor, Start·Faktor², …'
        : 'Gesamtpreis = Start · Faktor^(Menge − 1)'));
    } else if (c.model === 'catalog') {
      out.push(h('div', { class: 'hint' }, 'Feste Einträge mit eigenem Preis, z. B. Wurzeln = 10 jqm.'));
      c.entries.forEach((e, i) => out.push(h('div', { class: 'row' },
        field('Name ', textInput(e.name, (v) => { e.name = v; commit(); })),
        field('Kosten (jqm) ', numInput(e.cost, (v) => { e.cost = v; commit(); })),
        btn('×', () => { c.entries.splice(i, 1); commit(); }, 'x danger'))));
      out.push(btn('+ Eintrag', () => {
        const name = 'Neuer Eintrag';
        let id = M.slug(name), n = 2;
        while (c.entries.some((e) => e.id === id)) id = M.slug(name) + '_' + n++;
        c.entries.push({ id, name, cost: 10 }); if (!c.default) c.default = id; commit();
      }));
    } else if (c.model === 'direct') {
      out.push(paramDef(c.param, 'Wert'));
      out.push(h('div', { class: 'hint' }, 'Die Kosten entsprechen dem eingegebenen Wert (1:1).'));
    }
    out.push(h('label', { class: 'pf' }, h('span', {}, 'Notiz / Referenz'),
      textInput(c.reference || '', (v) => { c.reference = v; commit(); }, { style: 'flex:1;min-width:260px' })));
    return out;
  }

  function elementCard(el) {
    const d = h('details', { class: 'card', open: openIds.has(el.id) },
      h('summary', {}, dot(el), el.name, h('span', { class: 'chip' }, el.kind === 'prime' ? 'Urelement' : 'abgeleitet')));
    d.addEventListener('toggle', () => { if (d.open) openIds.add(el.id); else openIds.delete(el.id); });
    d.append(h('div', { class: 'row' },
      field('Name ', textInput(el.name, (v) => { el.name = v; commit(); })),
      el.kind === 'prime' ? field('Farbe ', h('input', { type: 'color', value: el.color || '#888888', onchange: (e) => { el.color = e.target.value; commit(); } })) : null,
      el.kind === 'prime' ? field('Komplexität ', numInput(el.complexity, (v) => { el.complexity = v; commit(); }, { placeholder: 'Standard' })) : null));
    if (el.kind === 'prime') d.append(...costEditor(el));
    else {
      const names = el.recipe.ingredients.map((i) => (data.elements.find((e) => e.id === i) || { name: i }).name);
      d.append(h('div', {}, `Rezept: ${names.join(el.recipe.ordered ? ' → ' : ' + ')}`, h('span', { class: 'hint' }, ' (im Tab „Rezepte“ bearbeiten)')));
    }
    return d;
  }

  function renderElements() {
    return h('div', { class: 'stack' },
      h('p', { class: 'hint' }, 'Urelemente: Erde, Feuer, Wasser, Luft, Licht, Dunkel, Mystic, Natura. Die Kosten geben an, wie viel jqm eine Aktivierung kostet.'),
      data.elements.map(elementCard));
  }

  /* ---------- Rezepte ---------- */

  function dependents(id) {
    const out = [];
    data.elements.forEach((e) => { if (e.kind === 'derived' && e.recipe.ingredients.includes(id)) out.push(`Rezept von ${e.name}`); });
    (function scan(s, where) {
      s.parts.forEach((p) => {
        if (p.kind === 'element' && p.id === id) out.push(`${where}: Teil im Siegel`);
        if (p.kind === 'seal') scan(p.spec, 'verschachteltes Siegel');
      });
    })(spec, 'Rechner');
    return out;
  }

  function recipeCard(el, idx) {
    const r = el.recipe;
    const opts = data.elements.filter((e) => e.id !== el.id).map((e) => [e.id, e.name]);
    let summary = '';
    try {
      const c = M.primeCounts(M.expand(idx, el.id));
      summary = 'Urelemente: ' + Object.keys(c).map((id) => `${idx.byId.get(id).name}${c[id] > 1 ? ' ×' + c[id] : ''}`).join(', ');
    } catch (e) { summary = e.message; }
    return h('div', { class: 'card' },
      h('div', { class: 'row' }, dot(el), field('Name ', textInput(el.name, (v) => { el.name = v; commit(); })),
        field('Reihenfolge zählt ', checkbox(!!r.ordered, (v) => { r.ordered = v; commit(); })),
        btn('Löschen', () => {
          const deps = dependents(el.id);
          if (deps.length) { alert(`„${el.name}“ wird noch verwendet:\n- ${deps.join('\n- ')}`); return; }
          data.elements.splice(data.elements.indexOf(el), 1); commit();
        }, 'danger')),
      h('div', { class: 'row' }, r.ingredients.map((ing, i) => [
        i ? h('span', { class: 'muted' }, r.ordered ? '→' : '+') : null,
        select(opts, ing, (v) => { r.ingredients[i] = v; commit(); }),
        r.ingredients.length > 2 ? btn('×', () => { r.ingredients.splice(i, 1); commit(); }, 'x danger') : null,
      ]), btn('+ Zutat', () => { r.ingredients.push(opts[0][0]); commit(); })),
      h('div', { class: 'hint' }, summary));
  }

  function renderRecipes() {
    const idx = M.buildIndex(data);
    const derived = data.elements.filter((e) => e.kind === 'derived');
    const nameIn = h('input', { type: 'text', placeholder: 'Name, z. B. Obsidian' });
    const all = data.elements.map((e) => [e.id, e.name]);
    const test = ['', '', ''].map(() => select([['', '–']].concat(all), '', () => showTest()));
    const out = h('div', { class: 'msg info' }, 'Wähle Zutaten in Reihenfolge.');
    function showTest() {
      const ings = test.map((s) => s.value).filter(Boolean);
      if (ings.length < 2) { out.textContent = 'Wähle mindestens zwei Zutaten.'; return; }
      const found = M.lookupRecipe(idx, ings);
      out.textContent = found ? `→ ${found.name}` : 'Kein Rezept für diese Kombination.';
    }
    return h('div', { class: 'stack' },
      h('p', { class: 'hint' }, 'Abgeleitete Elemente entstehen aus Zutaten, auch aus anderen abgeleiteten (verschachtelt). Bei „Reihenfolge zählt“ ergeben Lava → Wasser und Wasser → Lava verschiedene Ergebnisse.'),
      derived.map((e) => recipeCard(e, idx)),
      h('div', { class: 'card' }, h('h3', {}, 'Neues Element'),
        h('div', { class: 'row' }, nameIn, btn('Anlegen', () => {
          const name = nameIn.value.trim();
          if (!name) return;
          let id = M.slug(name), n = 2;
          while (data.elements.some((e) => e.id === id)) id = M.slug(name) + '_' + n++;
          const primes = data.elements.filter((e) => e.kind === 'prime');
          data.elements.push({ id, name, kind: 'derived', recipe: { ingredients: [primes[0].id, primes[1].id], ordered: false } });
          openIds.add(id); commit();
        }, 'primary'))),
      h('div', { class: 'card' }, h('h3', {}, 'Kombinations-Test'),
        h('div', { class: 'row' }, test), out));
  }

  /* ---------- Gegensätze ---------- */

  function renderOpposites() {
    const primes = data.elements.filter((e) => e.kind === 'prime').map((e) => [e.id, e.name]);
    const kinds = data.oppositionKinds.map((k) => [k.id, k.name]);
    return h('div', { class: 'stack' },
      h('p', { class: 'hint' }, 'Gegensätze gelten nur für Urelemente. Im Siegel wird jedes Element in Urelemente zerlegt; jede Beziehung, deren beide Seiten vorkommen, zählt einzeln und erhöht die Komplexität.'),
      h('div', { class: 'card' }, h('h3', {}, 'Arten'),
        data.oppositionKinds.map((k) => h('div', { class: 'row' },
          field('Bezeichnung ', textInput(k.name, (v) => { k.name = v; commit(); })),
          field('Gewicht ', numInput(k.weight, (v) => { k.weight = v; commit(); })))),
        btn('+ Art', () => {
          data.oppositionKinds.push({ id: 'art' + (data.oppositionKinds.length + 1), name: 'neue Art', weight: 1 }); commit();
        })),
      h('div', { class: 'card' }, h('h3', {}, 'Beziehungen'),
        data.oppositions.map((o, i) => h('div', { class: 'row' },
          select(primes, o.from, (v) => { o.from = v; commit(); }),
          select(kinds, o.kind, (v) => { o.kind = v; commit(); }),
          select(primes, o.to, (v) => { o.to = v; commit(); }),
          btn('×', () => { data.oppositions.splice(i, 1); commit(); }, 'x danger'))),
        btn('+ Beziehung', () => {
          data.oppositions.push({ from: primes[0][0], to: primes[1][0], kind: kinds[0][0] }); commit();
        })));
  }

  /* ---------- Bauteile & Quellen ---------- */

  function renderParts() {
    return h('div', { class: 'stack' },
      h('div', { class: 'card' }, h('h3', {}, 'Bauteile'),
        h('p', { class: 'hint' }, 'Bauteile belegen Platz im Siegel und erhöhen die Komplexität. Ein Generator ist ein Siegel im Siegel.'),
        data.components.map((c) => h('div', { class: 'row' },
          field('Name ', textInput(c.name, (v) => edit(c, 'name', v))),
          h('span', { class: 'chip' }, c.kind === 'battery' ? 'Batterie' : 'Generator'),
          field('Komplexität ', numInput(c.complexity, (v) => edit(c, 'complexity', v))),
          c.kind === 'battery' ? field('Kapazität (jqm) ', numInput(c.capacity, (v) => edit(c, 'capacity', v), { placeholder: 'offen' })) : null,
          assumedChip(c.assumed))),
        h('div', { class: 'row' },
          btn('+ Batterie', () => { data.components.push({ id: 'battery_' + Date.now().toString(36), name: 'Neue Batterie', kind: 'battery', complexity: 2, capacity: null, assumed: true }); commit(); }),
          btn('+ Generator', () => { data.components.push({ id: 'generator_' + Date.now().toString(36), name: 'Neuer Generator', kind: 'generator', complexity: 4, assumed: true }); commit(); }))),
      h('h3', {}, 'Generatorquellen'),
      data.sources.map(sourceCard),
      btn('+ Quelle', () => {
        data.sources.push({ id: 'src_' + Date.now().toString(36), name: 'Neue Quelle', kind: 'rate', unit: 'jqm/s', levels: [{ id: 'l1', name: 'Stufe 1', value: 1 }] });
        commit();
      }));
  }

  function sourceCard(src) {
    const key = 'src:' + src.id;
    const d = h('details', { class: 'card', open: openIds.has(key) },
      h('summary', {}, src.name, h('span', { class: 'chip' }, src.kind === 'rate' ? 'Dauerleistung' : 'Vorrat'), assumedChip(src.assumed)));
    d.addEventListener('toggle', () => { if (d.open) openIds.add(key); else openIds.delete(key); });
    d.append(h('div', { class: 'row' },
      field('Name ', textInput(src.name, (v) => edit(src, 'name', v))),
      field('Art ', select([['rate', 'Dauerleistung (jqm/s)'], ['store', 'Vorrat (einmalig)']], src.kind, (v) => edit(src, 'kind', v))),
      field('Einheit ', textInput(src.unit, (v) => edit(src, 'unit', v), { style: 'min-width:80px;width:100px' })),
      field('Platz ', select([['generator', 'im Generator'], ['carried', 'am Körper getragen']], src.placement || 'generator', (v) => edit(src, 'placement', v))),
      src.kind === 'rate' ? field('Leistung wächst mit der Fläche ', checkbox(!!src.areaScaling, (v) => edit(src, 'areaScaling', v))) : null,
      src.kind === 'store' ? field('Aufladbar ', checkbox(!!src.rechargeable, (v) => edit(src, 'rechargeable', v))) : null));
    d.append(h('label', { class: 'pf' }, h('span', {}, 'Gefahrenhinweis'),
      textInput(src.hazard || '', (v) => { src.hazard = v; commit(); }, { style: 'flex:1;min-width:260px' })));
    if (src.note) d.append(h('div', { class: 'hint' }, src.note));
    src.levels.forEach((l, i) => d.append(h('div', { class: 'row' },
      field('Stufe ', textInput(l.name, (v) => { l.name = v; commit(); })),
      field('Wert ', numInput(l.value, (v) => { l.value = v; delete src.assumed; commit(); })),
      field('Notiz ', textInput(l.note || '', (v) => { l.note = v; commit(); }, { style: 'min-width:100px;width:140px' })),
      btn('×', () => { src.levels.splice(i, 1); commit(); }, 'x danger'))));
    d.append(btn('+ Stufe', () => { src.levels.push({ id: 'l' + (src.levels.length + 1) + '_' + Date.now().toString(36), name: 'Neue Stufe', value: 1 }); commit(); }));
    return d;
  }

  /* ---------- Einstellungen ---------- */

  const SETTINGS = [
    ['Verwobene Elemente', [
      ['fuseUsage', 'Nutzungsfaktor je Verwebung', 'Eis kostet in der Nutzung weniger als Wasser + Luft (< 1).'],
      ['fuseCreation', 'Erschaffungsfaktor je Verwebung', 'Eis ist in der Erschaffung aufwendiger (> 1).'],
    ]],
    ['Komplexität und Erschaffung', [
      ['creationPerComplexity', 'Erschaffung: jqm je Komplexitätspunkt', 'Absolute Höhe der Erschaffungskosten.'],
      ['primeComplexity', 'Komplexität je Urelement', ''],
      ['oppositionComplexity', 'Zuschlag je Gegensatz', 'Mal Gewicht der Art. Macht Feuer + Wasser deutlich komplexer.'],
      ['nestingPenalty', 'Siegel im Siegel: Faktor je Ebene', ''],
    ]],
    ['Größe', [
      ['sizeSimple', 'Doppelte Größe, einfaches Siegel: Erschaffung so viel billiger', 'Dein Wert 2,5.'],
      ['sizeComplex', 'Doppelte Größe, komplexes Siegel: Erschaffung so viel billiger', 'Dein Wert 1,25.'],
      ['complexityMin', 'Komplexität „einfach“', ''],
      ['complexityMax', 'Komplexität „komplex“', ''],
      ['nestPenalty', 'Verschachtelung verschiebt Richtung „komplex“', 'Siegel im Siegel sparen durch Größe weniger.'],
      ['usagePerDoubling', 'Doppelte Größe: Nutzung und Hitze so viel geringer', 'Dein Wert 1,1 (angenommen: je Verdopplung).'],
      ['areaExponent', 'Flächenquellen wachsen mit Größe^', '2 = Fläche.'],
    ]],
    ['Gegenstände', [
      ['transferNormal', 'Wirkungsgrad ohne Generator (normal)', '40–45 %.'],
      ['transferHigh', 'Wirkungsgrad ohne Generator (hohe Dichte)', 'bis 60 %.'],
    ]],
  ];

  function renderSettings() {
    const s = data.settings;
    const assumed = data.meta.assumed;
    return h('div', { class: 'stack' },
      h('p', { class: 'hint' }, 'Werte mit „Annahme“ stammen nicht von dir, sondern von Claude. Eine Änderung bestätigt sie.'),
      SETTINGS.map(([title, rows]) => h('div', { class: 'card' }, h('h3', {}, title),
        rows.map(([key, label, hint]) => h('div', { class: 'row' },
          h('label', { class: 'pf' }, h('span', { style: 'min-width:340px' }, label),
            numInput(s[key], (v) => { s[key] = v; const i = assumed.indexOf(key); if (i >= 0) assumed.splice(i, 1); commit(); }),
            assumedChip(assumed.includes(key)),
            h('em', { class: 'muted' }, hint)))))));
  }

  /* ---------- Daten ---------- */

  function download(name, text) {
    const a = h('a', { href: URL.createObjectURL(new Blob([text], { type: 'application/json' })), download: name });
    document.body.append(a); a.click(); a.remove();
  }

  function renderData() {
    const problems = M.validate(data);
    const file = h('input', { type: 'file', accept: 'application/json,.json', onchange: (e) => {
      const f = e.target.files[0];
      if (!f) return;
      f.text().then((t) => {
        try {
          const parsed = JSON.parse(t);
          if (!Array.isArray(parsed.elements) || !parsed.settings) throw new Error('Keine gültige Datei.');
          data = parsed; commit();
        } catch (x) { alert('Import fehlgeschlagen: ' + x.message); }
      });
    } });
    return h('div', { class: 'stack' },
      h('div', { class: 'card' }, h('h3', {}, 'Speichern und Laden'),
        h('p', { class: 'hint' }, 'Alles wird automatisch im Browser gespeichert. Für ein Backup oder zum Ablegen im Repo exportierst du die Daten als Datei.'),
        h('div', { class: 'row' },
          btn('Daten exportieren', () => download('waechter-daten.json', JSON.stringify(data, null, 2)), 'primary'),
          field('Importieren ', file),
          btn('Auf Standard zurücksetzen', () => {
            if (confirm('Alle Änderungen verwerfen und die Startdaten laden?')) { data = clone(W.defaultData); spec = defaultSpec(); commit(); }
          }, 'danger'))),
      h('div', { class: 'card' }, h('h3', {}, 'Prüfung der Daten'),
        problems.length ? problems.map((p) => h('div', { class: 'msg ' + p.level }, p.text)) : h('div', { class: 'ok' }, 'Keine Probleme gefunden.')));
  }

  /* ---------- Rahmen ---------- */

  const views = { calc: renderCalc, elements: renderElements, recipes: renderRecipes, opposites: renderOpposites, parts: renderParts, settings: renderSettings, data: renderData };

  // Das Entfernen eines fokussierten Felds löst "change" aus und damit ein weiteres
  // render(). Deshalb: Fokus zuerst abgeben und verschachtelte Aufrufe zusammenfassen.
  let rendering = false;
  let rerender = false;
  function render() {
    if (rendering) { rerender = true; return; }
    rendering = true;
    try {
      const y = window.scrollY;
      const active = document.activeElement;
      if (active && active !== document.body && typeof active.blur === 'function') active.blur();
      const nav = document.getElementById('tabs');
      nav.replaceChildren(...TABS.map(([id, label]) => h('button', { class: id === tab ? 'on' : '', onclick: () => { tab = id; location.hash = id; render(); window.scrollTo(0, 0); } }, label)));
      const main = document.getElementById('main');
      main.replaceChildren(views[tab]());
      window.scrollTo(0, y);
    } finally {
      rendering = false;
    }
    if (rerender) { rerender = false; render(); }
  }

  render();
})();
