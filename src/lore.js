/*
 * Welt-Konfiguration der Wächter.
 * Alles, was "Lore" ist (Elemente, Wachstumsregeln, Schriftschlüssel), steht
 * hier an EINER Stelle, damit es später anhand deiner Dokumente angepasst
 * werden kann, ohne den Zeichencode anzufassen.
 *
 * ACHTUNG: Änderungen hier ändern die erzeugten Siegel/Glyphen.
 */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});

  // style = Charakter der Bahnen, pattern = Musterring des Elements
  const elements = [
    { id: 'feuer',    name: 'Feuer',    style: 'flame',  pattern: 'tri',     color: '#b3361b' },
    { id: 'wasser',   name: 'Wasser',   style: 'wave',   pattern: 'scallop', color: '#1f5f8b' },
    { id: 'erde',     name: 'Erde',     style: 'step',   pattern: 'block',   color: '#6b4f2a' },
    { id: 'luft',     name: 'Luft',     style: 'curl',   pattern: 'ring',    color: '#4f8a8f' },
    { id: 'licht',    name: 'Licht',    style: 'ray',    pattern: 'ray',     color: '#b8932a' },
    { id: 'schatten', name: 'Schatten', style: 'veil',   pattern: 'moon',    color: '#4a3d63' },
  ];
  const elementById = {};
  elements.forEach((e) => { elementById[e.id] = e; });

  W.Lore = {
    // Schlüssel der Schrift: ändert das komplette Alphabet.
    alphabetKey: 'waechter',
    maxWords: 24,
    elements,
    elementById,
    // Wie schnell wächst ein Siegel mit den Anforderungen?
    complexity: {
      baseRadius: 95,          // Siegelradius ohne Elemente (Einheiten)
      sizePerElement: 0.22,    // +22 % Radius je Element
      baseLanes: 5,            // Bahnen ohne Elemente
      lanesPerElement: 3,      // zusätzliche Bahnen je Element
      lanesPerPair: 1,         // zusätzliche Bahnen je Elementpaar (Feuer+Wasser ...)
      lettersPerExtraLane: 10, // +1 Bahn je 10 Buchstaben
      maxLanes: 30,
    },
  };
  if (typeof module === 'object' && module.exports) module.exports = W.Lore;
})(typeof globalThis !== 'undefined' ? globalThis : this);
