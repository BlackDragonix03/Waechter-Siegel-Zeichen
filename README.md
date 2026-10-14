# Wächter-Siegelwerkstatt

Werkzeug für die Fantasy-Rasse der Wächter: Elemente, Rezepte, Gegensätze und
Energie der Siegelmagie. Schrift und gezeichnetes Siegel folgen später.

## Benutzen

`index.html` im Browser öffnen, ohne Installation und ohne Server. Alle Änderungen
werden automatisch im Browser gespeichert. Unter **Daten** kannst du alles als
Datei exportieren (Backup, oder zum Ablegen im Repo) und wieder importieren.

Tests: `npm test` (Node 20 oder neuer, keine Abhängigkeiten).

## Pakete: Windows-Exe und Android-APK

GitHub baut beide Pakete automatisch (`.github/workflows/build.yml`, Reiter **Actions**,
Lauf öffnen, unten **Artefakte**). Auch von Hand startbar über **Run workflow**.

- **Windows:** `Waechter-Siegelwerkstatt-0.1.0.exe`, eine einzelne Datei ohne Installation
  (Electron, `desktop/`). Unsigniert: Windows zeigt beim ersten Start eventuell eine
  SmartScreen-Warnung („Weitere Informationen“, „Trotzdem ausführen“).
- **Android:** `Waechter-Siegelwerkstatt-debug.apk` (Capacitor, `android/`). Mit einem
  Debug-Schlüssel signiert, per Seitenladen installierbar (Installation aus unbekannten
  Quellen erlauben). Fürs Veröffentlichen im Play Store braucht es einen eigenen Schlüssel.
  Bilder werden dort über den Teilen-Dialog gespeichert.

### Selbst bauen unter Windows (Doppelklick)

- **`build-windows-exe.bat`**: baut die Exe nach `release\`. Braucht nur Node.js 20 oder neuer.
  Wenn „Cannot create symbolic link“ erscheint: als Administrator starten oder den
  Windows-Entwicklermodus einschalten.
- **`build-android-apk.bat`**: baut die APK nach `release\`. Braucht Node.js, **JDK 17**
  (nicht neuer) und das **Android-SDK** (Android Studio installieren, `ANDROID_HOME` setzen).
  Fehlende Teile meldet die Datei mit einer Anleitung.

Beide laden beim ersten Start einige hundert MB aus dem Internet. Auf der Windows-Seite sind
die Dateien nicht getestet worden, nur der Ablauf ist geprüft.

Lokal testen: `cd desktop && npm install && npm start` startet die Desktop-App.

## NetGuard: Netzwerk-Scanner (eigenständiges Werkzeug)

Im Ordner `netguard/` liegt ein eigenständiges Programm zum Scannen des Netzwerks mit zoombarer
Topologie, Geräteliste (Name, IP, MAC, Hersteller, Ports, Router-Zugang), gespeicherten Scans
mit Vergleich, Diagnose mit Lösungsvorschlägen sowie Live-Überwachung und Router-Abfrage.
Windows-Exe bauen: **`build-netguard-exe.bat`** (braucht nur Python 3.10+). Details in
`netguard/README.md`.

## Siegel entschlüsseln

Im Bereich **Entschlüsseln** legst du ein Siegel ab (Datei wählen, hineinziehen oder mit Strg+V
einfügen). Das Tool sagt, was es ist: Typ, Teile mit Rezepten, Urelemente, Gegensätze,
Komplexität, Kosten, getragene Kristalle samt Warnung, die Inschrift und die Wörter in den
Kreisen, jeweils im Klartext und in der Schrift, dazu eine Schrifttafel der verwendeten Zeichen.

- **Was gelesen wird:** SVG und PNG, die die Werkstatt gespeichert hat. Der Export bettet alle
  Angaben ein, auch die damals gültigen Regeln. Die Erklärung gilt also, auch wenn du die
  Regeln später geändert hast. Aus der ID wird das Siegel nachgebaut und verglichen:
  Veränderungen fallen auf.
- **SVG ohne Angaben:** Dann liest das Tool die Zeichen im Inschriftring, zählt Bänder und
  Kreise und nennt die Inschrift. Der Ring ist ein Kreis, der Anfang des Textes ist dann
  eventuell nicht erkennbar.
- **Was nicht geht:** Screenshots, Fotos, JPEG und mit anderen Programmen neu gespeicherte PNG.
  Ein Bild wird nie anhand seiner Pixel erkannt. Dafür bräuchte das Siegel einen sichtbaren
  Datenring, der auch Screenshots übersteht. Das wäre ein eigener Schritt.

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
