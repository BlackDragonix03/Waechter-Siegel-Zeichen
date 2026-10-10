/*
 * Startdaten der Wächter-Welt. Alles hier ist im Editor änderbar.
 *
 * Kennzeichnung:
 *   - Werte vom Autor genannt: ohne Markierung.
 *   - Annahmen von Claude: stehen in meta.assumed (Einstellungen) bzw. haben
 *     assumed:true (Faktoren, Quellen). Im Editor als "Annahme" gekennzeichnet;
 *     eine Änderung bestätigt den Wert.
 */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});

  W.defaultData = {
    version: 1,
    energyUnit: 'jqm',

    settings: {
      // Verwoben (z. B. Eis statt Wasser + Luft): Nutzung billiger, Erschaffung teurer
      fuseUsage: 0.8,
      fuseCreation: 1.3,
      // Erschaffung des Siegels: jqm je Komplexitätspunkt
      creationPerComplexity: 25,
      primeComplexity: 1,
      // Zuschlag je Gegensatz-Beziehung (mal Gewicht der Art)
      oppositionComplexity: 5,
      // Siegel im Siegel: Komplexität * Faktor je Ebene
      nestingPenalty: 1.25,
      // Doppelte Größe -> Erschaffung so viel billiger (einfach ... komplex)
      sizeSimple: 2.5,
      sizeComplex: 1.25,
      complexityMin: 2,
      complexityMax: 40,
      nestPenalty: 0.15,
      // Doppelte Größe -> Nutzungskosten und Hitze so viel geringer
      usagePerDoubling: 1.1,
      // Wirkungsgrad bei Gegenständen ohne Generator (Transfer über Luft)
      transferNormal: 0.425,
      transferHigh: 0.6,
      // Leistung flächenabhängiger Quellen wächst mit Größe^Exponent
      areaExponent: 2,
    },
    meta: {
      assumed: [
        'fuseUsage', 'fuseCreation', 'creationPerComplexity', 'primeComplexity',
        'oppositionComplexity', 'nestingPenalty', 'complexityMin', 'complexityMax',
        'nestPenalty', 'usagePerDoubling',
      ],
    },

    elements: [
      {
        id: 'erde', name: 'Erde', kind: 'prime', color: '#8a6a3b',
        cost: {
          model: 'exp', start: 1.25, factor: 1.125, cumulative: true,
          param: { id: 'mass', label: 'Masse', unit: 'kg', default: 1 },
          reference: '1 kg = 1,25 jqm, jedes weitere kg kostet das 1,125-Fache des vorherigen',
        },
      },
      {
        id: 'feuer', name: 'Feuer', kind: 'prime', color: '#c4411f',
        cost: {
          model: 'curve',
          main: { id: 'temp', label: 'Temperatur', unit: '°C', default: 500, points: [[500, 120], [1000, 180], [5000, 1950]] },
          factors: [{ id: 'duration', label: 'Dauer', unit: 's', ref: 1, default: 1, mode: 'linear', assumed: true }],
          reference: '500 °C für 1 s = 120 jqm',
        },
      },
      {
        id: 'wasser', name: 'Wasser', kind: 'prime', color: '#2f74b5',
        cost: {
          model: 'curve',
          main: { id: 'speed', label: 'Geschwindigkeit', unit: 'm/s', default: 2, points: [[0, 2], [2, 20], [10, 100]] },
          factors: [{ id: 'volume', label: 'Volumen', unit: 'l', ref: 1, default: 1, mode: 'linear', assumed: true }],
          gaps: ['Temperatur'],
          reference: '1 l, 20 °C: ruhend 2 jqm, 2 m/s 20 jqm, 10 m/s 100 jqm',
        },
      },
      {
        id: 'luft', name: 'Luft', kind: 'prime', color: '#7fb7be',
        cost: {
          model: 'curve',
          main: { id: 'pressure', label: 'Druck', unit: 'bar', default: 1, points: [[1, 30], [100, 1000]] },
          factors: [],
          gaps: ['Geschwindigkeit', 'Temperatur'],
          reference: '10 m/s, 20 °C: 1 bar = 30 jqm, 100 bar = 1000 jqm (Luftbombe)',
        },
      },
      {
        id: 'licht', name: 'Licht', kind: 'prime', color: '#e2b93b',
        cost: {
          model: 'curve',
          main: { id: 'lux', label: 'Helligkeit', unit: 'lux', default: 1000, points: [[1000, 25], [10000, 100], [100000, 5000]] },
          factors: [{ id: 'duration', label: 'Dauer', unit: 's', ref: 1, default: 1, mode: 'linear', assumed: true }],
          reference: '1000 lux für 1 s = 25 jqm',
        },
      },
      {
        id: 'dunkel', name: 'Dunkel', kind: 'prime', color: '#4b3f66',
        cost: {
          model: 'exp', start: 50, factor: 1.94, cumulative: false,
          param: { id: 'amount', label: 'Menge', unit: 'Einheit', default: 1, assumed: true },
          reference: 'Start 50 jqm, Faktor 1,94; Wächter können Dunkel kaum nutzen, daher so schnell so teuer',
        },
      },
      {
        id: 'mystic', name: 'Mystic', kind: 'prime', color: '#a24bc4',
        cost: {
          model: 'direct',
          param: { id: 'jqm', label: 'Energie', unit: 'jqm', default: 100 },
          reference: 'Mystic ist jqm selbst, daher 1:1',
        },
      },
      {
        id: 'natura', name: 'Natura', kind: 'prime', color: '#3f8f4f',
        cost: {
          model: 'catalog',
          param: { id: 'entry', label: 'Eintrag' },
          default: 'wurzeln',
          entries: [{ id: 'wurzeln', name: 'Wurzeln', cost: 10 }],
          reference: 'Kosten hängen von der Definition ab (Wurzeln, Bäume, ...)',
        },
      },
      { id: 'eis', name: 'Eis', kind: 'derived', recipe: { ingredients: ['wasser', 'luft'], ordered: false } },
      { id: 'lava', name: 'Lava', kind: 'derived', recipe: { ingredients: ['feuer', 'erde'], ordered: false } },
    ],

    oppositionKinds: [
      { id: 'loescht', name: 'löscht', weight: 1 },
      { id: 'zerstoert', name: 'zerstört', weight: 1 },
      { id: 'ineffizient', name: 'ist ineffizient gegen', weight: 1 },
    ],
    // "von" wirkt gegen "nach"; nur Urelemente. Beziehungen zählen einzeln.
    oppositions: [
      { from: 'wasser', to: 'feuer', kind: 'loescht' },
      { from: 'luft', to: 'feuer', kind: 'loescht' },
      { from: 'wasser', to: 'erde', kind: 'ineffizient' },
    ],

    components: [
      { id: 'battery_small', name: 'Kleine Batterie', kind: 'battery', complexity: 1.5, capacity: null, assumed: true },
      { id: 'battery_large', name: 'Große Batterie', kind: 'battery', complexity: 2.5, capacity: null, assumed: true },
      { id: 'generator', name: 'Generator', kind: 'generator', complexity: 4, assumed: true },
    ],

    // kind 'rate': Dauerleistung jqm/s; 'store': einmaliger Vorrat in jqm
    sources: [
      {
        id: 'blood', name: 'Blut', kind: 'store', unit: 'jqm je ml', consumes: 'ml',
        levels: [{ id: 'ml', name: '1 ml', value: 1000 }],
      },
      {
        id: 'environment', name: 'Umgebung', kind: 'rate', unit: 'jqm/s',
        levels: [
          { id: 'low', name: 'gering', value: 10 },
          { id: 'normal', name: 'normal', value: 20 },
          { id: 'high', name: 'hoch', value: 50 },
          { id: 'extreme', name: 'extrem', value: 1000 },
        ],
      },
      {
        id: 'body', name: 'Körperkraft', kind: 'rate', unit: 'jqm/s',
        levels: [
          { id: 'regen', name: 'regenerativ', value: 1 },
          { id: 'limit', name: 'grenzwertig', value: 5 },
          { id: 'exhaust', name: 'erschöpfend', value: 10, note: 'über 2 h' },
        ],
      },
      {
        id: 'sunlight', name: 'Sonnenlicht', kind: 'rate', unit: 'jqm/s', areaScaling: true,
        levels: [
          { id: 'night', name: 'Nacht', value: 0 },
          { id: 'overcast', name: 'bedeckt', value: 5 },
          { id: 'clear', name: 'klar', value: 20 },
          { id: 'peak', name: 'Hochgebirge oder Wüste mittags', value: 50 },
        ],
      },
      {
        id: 'thermal', name: 'Temperaturgefälle', kind: 'rate', unit: 'jqm/s', areaScaling: true,
        levels: [
          { id: 'k10', name: '10 K Unterschied', value: 2 },
          { id: 'k50', name: '50 K Unterschied', value: 12 },
          { id: 'k200', name: '200 K Unterschied', value: 60 },
        ],
      },
      {
        id: 'wind', name: 'Wind', kind: 'rate', unit: 'jqm/s', areaScaling: true, assumed: true,
        note: 'Nur Sturm = 30 jqm/s stammt aus dem ersten Entwurf; Brise und Wind sind geschätzt.',
        levels: [
          { id: 'breeze', name: 'Brise', value: 5 },
          { id: 'wind', name: 'Wind', value: 15 },
          { id: 'storm', name: 'Sturm', value: 30 },
        ],
      },
      {
        id: 'motion', name: 'Bewegung', kind: 'rate', unit: 'jqm/s',
        levels: [
          { id: 'walk', name: 'Gehen', value: 2 },
          { id: 'run', name: 'Laufen', value: 8 },
          { id: 'strike', name: 'Schwerthieb', value: 30 },
        ],
      },
      {
        // Wird am Körper getragen; der Körper leitet zum Siegel (kein Generator-Bauteil).
        id: 'crystal', name: 'Energiekristall', kind: 'store', placement: 'carried', unit: 'jqm', consumes: 'Kristall',
        rechargeable: false,
        note: 'Entsteht aus Energie und löst sich bei Verbrauch auf. Gibt seine gesamte Energie in unter einer Nanosekunde ab. Ohne Präparation nahezu unzerstörbar.',
        hazard: 'Ein präparierter Kristall explodiert beim Brechen. 300.000 jqm könnten einen Krater von 150 km erzeugen.',
        levels: [{ id: 'standard', name: 'Standard (5 × 2 × 2 cm)', value: 300000 }],
      },
    ],
  };
  if (typeof module === 'object' && module.exports) module.exports = W.defaultData;
})(typeof globalThis !== 'undefined' ? globalThis : this);
