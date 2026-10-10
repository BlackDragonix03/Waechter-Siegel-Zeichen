/* Kostenkurven: rechnen zwischen vom Autor gesetzten Stützpunkten. */
(function (global) {
  'use strict';
  const W = (global.Waechter = global.Waechter || {});

  function cleanPoints(points) {
    const byX = new Map();
    (points || []).forEach((p) => {
      if (Number.isFinite(p[0]) && Number.isFinite(p[1])) byX.set(p[0], p[1]);
    });
    return Array.from(byX.entries()).sort((a, b) => a[0] - b[0]);
  }

  /*
   * Interpoliert y(x) zwischen Stützpunkten [[x, y], ...].
   * - Alle Werte > 0: Rechnung in log-log (Potenzgesetz zwischen den Punkten),
   *   passend zu "verdoppelt sich die Temperatur -> Preis wächst um Faktor n".
   * - Sonst (z. B. Geschwindigkeit 0): linear.
   * Außerhalb der Punkte wird die Steigung des Randsegments fortgesetzt.
   */
  function interpolate(points, x) {
    const pts = cleanPoints(points);
    if (!pts.length) return NaN;
    if (pts.length === 1) return pts[0][1];
    const useLog = x > 0 && pts.every((p) => p[0] > 0 && p[1] > 0);
    const f = useLog ? Math.log : (v) => v;
    const g = useLog ? Math.exp : (v) => v;
    let i = 0;
    while (i < pts.length - 2 && x > pts[i + 1][0]) i++;
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    const t = (f(x) - f(x0)) / (f(x1) - f(x0));
    return Math.max(0, g(f(y0) + t * (f(y1) - f(y0))));
  }

  /*
   * Exponentielle Kosten.
   * cumulative = true : n Einheiten kosten die Summe start * factor^i (i = 0..n-1),
   *                     d. h. jede weitere Einheit ist factor-mal so teuer (Erde).
   * cumulative = false: Gesamtpreis = start * factor^(n-1) (Dunkel).
   */
  function expCost(start, factor, n, cumulative) {
    if (cumulative) {
      if (n <= 0) return 0;
      if (Math.abs(factor - 1) < 1e-9) return start * n;
      return (start * (Math.pow(factor, n) - 1)) / (factor - 1);
    }
    return start * Math.pow(factor, n - 1);
  }

  W.Curves = { interpolate, expCost, cleanPoints };
  if (typeof module === 'object' && module.exports) module.exports = W.Curves;
})(typeof globalThis !== 'undefined' ? globalThis : this);
