/*
 * Datenmodell: Elemente, Rezepte, Verschachtelung.
 *
 * Urelemente (kind 'prime') sind fest. Alles andere (kind 'derived') entsteht
 * aus einem Rezept: geordnete Zutatenliste, optional "Reihenfolge egal".
 * Rezepte dürfen auf abgeleitete Elemente verweisen (beliebig tief).
 */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});

  function slug(name) {
    return (
      String(name)
        .toLowerCase()
        .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '') || 'element'
    );
  }

  function recipeKey(ingredients, ordered) {
    return ordered ? 'o:' + ingredients.join('>') : 'u:' + ingredients.slice().sort().join('+');
  }

  function buildIndex(data) {
    const byId = new Map();
    data.elements.forEach((e) => byId.set(e.id, e));
    const recipes = new Map();
    data.elements.forEach((e) => {
      if (e.kind === 'derived' && e.recipe) recipes.set(recipeKey(e.recipe.ingredients, !!e.recipe.ordered), e);
    });
    return { data, byId, recipes };
  }

  // Welches Element entsteht aus genau dieser Zutatenfolge? (null = keines)
  function lookupRecipe(index, ingredients) {
    return (
      index.recipes.get('o:' + ingredients.join('>')) ||
      index.recipes.get('u:' + ingredients.slice().sort().join('+')) ||
      null
    );
  }

  // Zerlegt ein Element in seinen Rezeptbaum. Wirft bei Kreisrezepten.
  function expand(index, id, stack) {
    stack = stack || [];
    const el = index.byId.get(id);
    if (!el) throw new Error('Unbekanntes Element: ' + id);
    if (stack.includes(id)) throw new Error('Kreisrezept: ' + stack.concat(id).join(' → '));
    if (el.kind === 'prime') return { id, el, children: [], levels: 0 };
    const ings = (el.recipe && el.recipe.ingredients) || [];
    const children = ings.map((c) => expand(index, c, stack.concat(id)));
    return { id, el, children, levels: 1 + Math.max(0, ...children.map((c) => c.levels)) };
  }

  // Urelement-Anzahl im Baum: Eis -> { wasser: 1, luft: 1 }
  function primeCounts(node, acc) {
    acc = acc || {};
    if (!node.children.length) acc[node.id] = (acc[node.id] || 0) + 1;
    else node.children.forEach((c) => primeCounts(c, acc));
    return acc;
  }

  function validate(data) {
    const problems = [];
    const err = (text) => problems.push({ level: 'error', text });
    const warn = (text) => problems.push({ level: 'warn', text });
    const index = buildIndex(data);
    const seen = new Set();
    data.elements.forEach((e) => {
      if (seen.has(e.id)) err(`Doppelte Element-ID: ${e.id}`);
      seen.add(e.id);
    });
    const keys = new Map();
    data.elements.forEach((e) => {
      if (e.kind === 'derived') {
        const ings = (e.recipe && e.recipe.ingredients) || [];
        if (ings.length < 2) err(`${e.name}: Rezept braucht mindestens zwei Zutaten.`);
        ings.forEach((i) => { if (!index.byId.has(i)) err(`${e.name}: unbekannte Zutat "${i}".`); });
        const k = recipeKey(ings, !!(e.recipe && e.recipe.ordered));
        if (keys.has(k)) warn(`${e.name} und ${keys.get(k)} haben dasselbe Rezept.`);
        keys.set(k, e.name);
        try { expand(index, e.id); } catch (x) { err(x.message); }
      } else if (!e.cost) {
        warn(`${e.name}: kein Kostenmodell definiert.`);
      }
    });
    (data.oppositions || []).forEach((o) => {
      const a = index.byId.get(o.from), b = index.byId.get(o.to);
      if (!a || !b) err(`Gegensatz mit unbekanntem Element: ${o.from} → ${o.to}`);
      else if (a.kind !== 'prime' || b.kind !== 'prime') err(`Gegensätze gelten nur für Urelemente: ${a.name} → ${b.name}`);
    });
    return problems;
  }

  W.Model = { slug, recipeKey, buildIndex, lookupRecipe, expand, primeCounts, validate };
  if (typeof module === 'object' && module.exports) module.exports = W.Model;
})(typeof globalThis !== 'undefined' ? globalThis : this);
