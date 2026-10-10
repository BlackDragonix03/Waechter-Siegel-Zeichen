/* Deterministischer Zufall: gleicher Text -> immer gleiche Zahlenfolge. */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});

  // cyrb128: String -> vier 32-Bit-Werte
  function hash128(str) {
    let h1 = 1779033703, h2 = 3144134277, h3 = 1013904242, h4 = 2773480762;
    for (let i = 0, k; i < str.length; i++) {
      k = str.charCodeAt(i);
      h1 = h2 ^ Math.imul(h1 ^ k, 597399067);
      h2 = h3 ^ Math.imul(h2 ^ k, 2869860233);
      h3 = h4 ^ Math.imul(h3 ^ k, 951274213);
      h4 = h1 ^ Math.imul(h4 ^ k, 2716044179);
    }
    h1 = Math.imul(h3 ^ (h1 >>> 18), 597399067);
    h2 = Math.imul(h4 ^ (h2 >>> 22), 2869860233);
    h3 = Math.imul(h1 ^ (h3 >>> 17), 951274213);
    h4 = Math.imul(h2 ^ (h4 >>> 19), 2716044179);
    h1 ^= h2 ^ h3 ^ h4; h2 ^= h1; h3 ^= h1; h4 ^= h1;
    return [h1 >>> 0, h2 >>> 0, h3 >>> 0, h4 >>> 0];
  }

  // sfc32: schneller PRNG mit 128 Bit Zustand
  function sfc32(a, b, c, d) {
    return function () {
      a >>>= 0; b >>>= 0; c >>>= 0; d >>>= 0;
      let t = (a + b) | 0;
      a = b ^ (b >>> 9);
      b = (c + (c << 3)) | 0;
      c = (c << 21) | (c >>> 11);
      d = (d + 1) | 0;
      t = (t + d) | 0;
      c = (c + t) | 0;
      return (t >>> 0) / 4294967296;
    };
  }

  function createRng(seed) {
    const seedStr = String(seed);
    const h = hash128(seedStr);
    const f = sfc32(h[0], h[1], h[2], h[3]);
    for (let i = 0; i < 15; i++) f();
    return {
      seed: seedStr,
      next: f,
      range: (a, b) => a + (b - a) * f(),
      int: (a, b) => a + Math.floor(f() * (b - a + 1)),
      chance: (p) => f() < p,
      sign: () => (f() < 0.5 ? -1 : 1),
      pick: (arr) => arr[Math.floor(f() * arr.length)],
      shuffle: (arr) => {
        const a = arr.slice();
        for (let i = a.length - 1; i > 0; i--) {
          const j = Math.floor(f() * (i + 1));
          [a[i], a[j]] = [a[j], a[i]];
        }
        return a;
      },
      // Unabhängiger Unterstrom: neue Features verändern bestehende Teile nicht.
      fork: (label) => createRng(seedStr + '/' + label),
    };
  }

  // Kurze, gut lesbare Kennung, z. B. "7K3F-92QA"
  function seedId(str) {
    const h = hash128(String(str));
    const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let out = '';
    for (let i = 0; i < 8; i++) {
      out += abc[((i < 4 ? h[0] : h[1]) >>> ((i % 4) * 5)) & 31];
      if (i === 3) out += '-';
    }
    return out;
  }

  W.Prng = { hash128, createRng, seedId };
  if (typeof module === 'object' && module.exports) module.exports = W.Prng;
})(typeof globalThis !== 'undefined' ? globalThis : this);
