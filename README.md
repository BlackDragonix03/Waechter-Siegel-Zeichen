# Wächter-Siegelwerkstatt

Werkzeug für die Fantasy-Rasse der Wächter: Elemente, Rezepte, Gegensätze und
Energie der Siegelmagie. Schrift und gezeichnetes Siegel folgen später.

## Benutzen

`index.html` im Browser öffnen, ohne Installation und ohne Server. Alle Änderungen
werden automatisch im Browser gespeichert. Unter **Daten** kannst du alles als
Datei exportieren (Backup, oder zum Ablegen im Repo) und wieder importieren.

Tests: `npm test` (Node 20 oder neuer, keine Abhängigkeiten).

## Regeln der Welt, wie sie im Tool stecken

- **Urelemente:** Erde, Feuer, Wasser, Luft, Licht, Dunkel, Mystic, Natura.
- **Rezepte:** Abgeleitete Elemente (Eis = Wasser + Luft, Lava = Feuer + Erde) entstehen
  aus zwei oder mehr Zutaten und können sich beliebig verschachteln. Bei „Reihenfolge
  zählt“ ergeben Lava → Wasser und Wasser → Lava verschiedene Ergebnisse.
- **Typ:** Anzahl der Teile der obersten Ebene. Ein verwobenes Element (Eis) zählt als
  ein Teil. Eis + Feuer + Wasser ist Typ 3.
- **Gegensätze:** Nur zwischen Urelementen. Jedes Element wird in Urelemente zerlegt,
  jede Beziehung mit beiden Seiten im Siegel zählt einzeln. Eis + Lava ergibt drei
  Gegensätze. Das macht ein Siegel deutlich komplexer.
- **Kosten (jqm):** Jedes Urelement hat eine Kostenkurve aus deinen Beispielwerten
  (Stützpunkte, Potenzgesetz zwischen den Punkten), exponentiell (Erde, Dunkel),
  Katalog (Natura) oder direkt 1:1 (Mystic).
- **Verwoben vs. nebeneinander:** Verwoben ist in der Nutzung billiger, in der
  Erschaffung teurer.
- **Größe:** Doppelt so groß heißt Erschaffung 1,25 bis 2,5 Mal billiger (komplexe und
  verschachtelte Siegel sparen weniger) und Nutzung und Hitze 1,1 Mal geringer.
- **Träger:** Gegenstände brauchen immer eine Batterie. Ohne Generator geht Energie
  über die Luft verloren (40 bis 60 % Wirkungsgrad).
- **Generatorquellen:** Blut, Umgebung, Körperkraft, Sonnenlicht, Temperaturgefälle,
  Wind (Leistung wächst mit der Fläche) und Bewegung. **Energiekristalle** werden am
  Körper getragen, der Körper leitet zum Siegel. Sie sind kein Siegelteil, nicht
  aufladbar, lösen sich beim Verbrauch auf und können explodieren.

## Annahmen von Claude

Alles, was nicht von dir kam, ist im Editor mit **Annahme** markiert; eine Änderung
bestätigt den Wert. Aktuell sind das: Verwebungsfaktoren (0,8 und 1,3), Erschaffungsaufwand
je Komplexitätspunkt (25 jqm), Zuschlag je Gegensatz (5), Komplexität von Bauteilen,
Verschachtelungsfaktoren, „je Verdopplung“ beim Nutzungsfaktor 1,1, der lineare Verlauf
von Dauer (Feuer, Licht) und Volumen (Wasser) sowie die Stufen Brise und Wind.

## Noch offen

- Die Schrift und die Zeichnung des Siegels.
- Hitze und Überlastung (zu kleiner Generator, zu dicht gepackte Siegel).
- Siegel im Siegel in der Oberfläche (der Rechenkern kann es schon).
- Kapazität der Batterien, Temperatur bei Wasser, Geschwindigkeit und Temperatur bei Luft.

`src/prng.js`, `src/lore.js` und `src/script.js` sind früher Vorrat für die
Schrift und das Siegelbild und werden noch nicht verwendet.
