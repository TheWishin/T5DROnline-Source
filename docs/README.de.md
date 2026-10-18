# Tekken 5: Dark Resurrection Online — native Windows-Version

Tekken 5: Dark Resurrection (PS3, PlayStation-Network-Version), das nativ unter
Windows läuft. Es wird rekompiliert, nicht emuliert. Online-Spiel mit Freunden
ist in Arbeit.

English: [../README.md](../README.md)

**Release 1.0.0 (2026-10-18).** Lade
`T5DR-Online-1.0.0.zip` von https://github.com/TheWishin/T5DROnline/releases

**Offline ist spielbereit:** alle Modi, 60 fps, Xbox-Pad und Arcade-Stick getestet.
**Online funktioniert:** getestet zwischen den PCs von zwei Spielern über das
Internet (direkte Verbindung, 26 ms Ping, 60 fps). Beendet Matches bitte normal,
nicht mit Alt+F4.

**Test-Version. Rechne mit Fehlern.** Bitte melde sie (siehe "Fehler melden").

## Was ist das?

- Das Programm des PS3-Spiels wird vorab in C++ übersetzt (statische
  Rekompilierung) und zu einem normalen Windows-Programm kompiliert. Es läuft
  kein Emulator.
- Das Prinzip ist dasselbe wie bei
  [Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online).
  Dieses Repository und seine Releases enthalten **keinen Teil des Spiels**.
- Du baust das Spiel auf deinem eigenen PC aus **deiner eigenen Kopie**: dem
  PSN-Paket (`.pkg`) und der Lizenz (`.rap`) aus deinem eigenen Konto. Der
  Launcher macht das für dich.
- Online-Spiel mit Freunden funktioniert wie bei Tekken 6 Native Online: Im
  Online-Reiter des Launchers anmelden (oder als Gast spielen), Gegner finden,
  und das Spiel startet direkt im Kampf. Siehe "Online".

## Stand (2026-10-17)

Getestet auf einem Entwicklungs-PC (Windows 11, Ryzen 9 mit 16 Kernen, RTX 3090).
Online wurde zwischen zwei echten PCs über das Internet getestet
(AMD/60 Hz gegen Intel/240 Hz).

| Bereich | Stand |
|---|---|
| Start | Funktioniert. Startet, öffnet das Fenster, erreicht Titel, Menüs, Charakterwahl und Kämpfe. |
| Menüs, Kämpfe | 60 fps, auch wenn andere Programme den PC auslasten. Schwächere PCs sind noch nicht gemessen. |
| Spielmodi | Arcade, Ghost, Versus (zwei Spieler an einem PC), Survival und Practice laufen. Gallery und das Online-Menü des Spiels brauchen die Server von Namco und Sony (abgeschaltet) und sagen das. |
| Kämpfer, Stages | Alle Kämpfer und Stages werden richtig dargestellt, auch Gesichter, Bodenschatten und Figuren im Hintergrund. |
| Anzeige | Fenster in jeder Größe, randloses Vollbild (Alt+Enter oder F11). **Interne Auflösung** von Lowest (0,5x) über Native (720p) bis 1080p, 1440p und 4K (Launcher-Einstellungen, `PS3_INTERNAL_RES`); jede Stufe in Kämpfen, Menüs, Videos und Charakterwahl geprüft. |
| Musik, Soundeffekte, Videos | Funktionieren. |
| Steuerung | Tastatur, Xbox-Controller (XInput), PlayStation-Pads, Arcade-Sticks und Hitboxen (DirectInput), zwei Spieler an einem PC, Knöpfe im Launcher einstellbar (Settings -> Set up controllers) oder in der `controls.ini`. Kurze Taps gehen nie verloren. Von einem Menschen ausprobiert: Xbox-Pad und Arcade-Stick, alle Eingaben kamen an, flüssig. |
| Speichern | Funktioniert. Die Uhr im Spiel zeigt das echte Datum. |
| Lange Sitzungen | Der alte Speicherfehler (weißes Bild nach ein paar Besuchen des Titels) ist behoben. |
| Online-Spiel | Funktioniert auf einem PC und über den öffentlichen Lobby-Server. Rollback-Netcode: 1 Frame Input-Delay bis ~60 ms Ping, darüber 2 (Settings -> Online input delay; Ranked: immer 2), getestet bei 0/50/150 ms Ping mit Paketverlust. Zwischen zwei echten PCs über das Internet gespielt (18.10.2026). |
| Bauen aus deiner Kopie | Funktioniert auf dem Entwicklungs-PC. |

## Voraussetzungen

- Windows 10 oder 11, 64 Bit.
- Eine Grafikkarte mit DirectX 12 und eine 64-Bit-CPU mit SSE4.1 (praktisch jeder
  PC der letzten 10+ Jahre).
- Arbeitsspeicher: Das Spiel brauchte auf dem Entwicklungs-PC etwa 1,2 GB. Kleine
  PCs haben wir nicht getestet. 8 GB oder mehr sind eine sichere Schätzung.
- Etwa 1,5 GB freier Speicherplatz. Nach dem Bauen belegt es etwa 1,1 GB, dazu
  die 90 MB der Zip-Datei.
- Eine Internetverbindung beim ersten Bauen. Etwa 50 KB öffentliche Schlüsseldaten
  (zwei Textdateien) werden von github.com geladen. Es wird nichts über dich oder
  dein Spiel gesendet.
- **Deine eigene Kopie** des Spiels, genau diese:
  **TEKKEN 5 DARK RESURRECTION ONLINE, US-PSN, `NPUB30009`, Version 01.00**.
  - das Paket: `.pkg`, 619.430.240 Bytes
  - die Lizenz: `.rap` (16 Bytes), benannt
    `UP0700-NPUB30009_00-UPDATE0000010000.rap`
  - **Andere Versionen werden abgelehnt** (Disc-Kopien, andere Regionen, andere
    Versionen). Die Portierung ist an genau dieses Programm gebunden.

Du brauchst **kein** Visual Studio, kein Git und kein Python. Die Zip-Datei bringt
ihr eigenes Python und ihren eigenen Compiler mit (clang-cl und lld-link aus
LLVM). Die Laufzeit des Spiels ist vorkompiliert. Dein PC übersetzt und kompiliert
nur den Code aus deiner Kopie.

## Installieren und erstes Bauen

1. Lade die Zip-Datei (`T5DR-Online-<Version>.zip`, etwa 90 MB) von der
   Releases-Seite: https://github.com/TheWishin/T5DROnline/releases
2. Entpacke **alles** in einen eigenen Ordner, zum Beispiel `C:\T5DR`. Nicht nach
   Programme (Program Files). Nicht direkt aus dem Zip-Fenster heraus.
3. Starte `T5DR Online.exe`. Windows warnt eventuell einmal (SmartScreen: die
   Datei ist nicht signiert). Klicke auf "Weitere Informationen", dann auf
   "Trotzdem ausführen".
4. Reiter **Build**: Wähle deine `.pkg` und deine `.rap`. Der Launcher sucht auch
   in Downloads, Desktop und Dokumente. Beide Zeilen sollten ein grünes Häkchen
   bekommen.
5. Klicke auf **BUILD GAME**. Der Launcher:
   - prüft deine Kopie (eine falsche Version oder falsche `.rap` wird innerhalb
     von Sekunden abgelehnt),
   - entpackt sie in den Ordner `native`,
   - übersetzt den Code des Spiels und kompiliert ihn auf deinem PC.

   Dauer: etwa 90 Sekunden auf dem Entwicklungs-PC (16 Kerne). Auf einem
   normalen PC erwarten wir ein paar Minuten (Schätzung, nicht gemessen).
   **Cancel** ist ungefährlich: BUILD GAME macht dort weiter, wo es aufgehört hat.
6. Reiter **Play**: Gib einen Namen ein (freiwillig) und klicke auf **PLAY**.

Alles, was das Bauen erzeugt, bleibt im Ordner `native` neben dem Launcher. Das
sind Spieldaten. Gib sie nicht weiter. Zum Deinstallieren löschst du den ganzen
Ordner.

## Sprache des Launchers

Der Launcher spricht Deutsch oder Englisch. Unter **Einstellungen** -> **Sprache**
stellst du ein: **Auto** nimmt die Sprache von Windows, dazu **Deutsch** und
**English**. Eine Änderung gilt, wenn der Launcher neu startet (der Knopf **Jetzt
neu starten** macht das). Das Spiel selbst bleibt englisch.

Diese Anleitung nennt die Knöpfe oft englisch, so wie sie im englischen Launcher
heißen. Im deutschen Launcher heißen sie:

| Englisch | Deutsch |
|---|---|
| Build, Play, Settings (Reiter) | Bauen, Spielen, Einstellungen |
| Cancel | Abbrechen |
| Stop game | Spiel stoppen |
| Open saves folder | Speicherordner öffnen |
| Check for updates, Update now | Nach Updates suchen, Jetzt aktualisieren |
| Report a problem | Problem melden |
| Host for friends | Für Freunde hosten |
| Online input delay | Online-Input-Delay |
| Advanced: extra settings | Erweitert: zusätzliche Einstellungen |
| Mute sound | Ton aus |

**BUILD GAME**, **PLAY**, **Quick Match** und **Ranked-Match** heißen in beiden
Sprachen gleich.

## Spielen

- Das Spiel öffnet ein eigenes Fenster. Es zeichnet in 1280 x 720 und skaliert auf
  das Fenster. Unter **Settings** gibt es Fenstergrößen, maximiert, randlos
  (experimentell: noch nicht mit dem echten Spielfenster getestet) und Stumm.
- **Esc** beendet das Spiel. Der Knopf **Stop game** auch. In einem
  Online-Match zweimal Esc drücken: Wer dort das Spiel schließt (Esc, Alt+F4,
  das X des Fensters), verliert das Match.
- Zwei Spieler an einem PC: Schließe ein zweites Pad an, wähle dann Versus.
- Tipps für jetzt:
  - Gehe so selten wie möglich zum Titelbildschirm zurück (Speicherfehler).
  - Lass das Spiel nicht im Leerlauf am Titel stehen.
  - Benutze nicht den Menüpunkt **Online** des Spiels (siehe "Online").

## Steuerung

Tastatur (Standard) und Xbox-Controller:

| Aktion | Tastatur | Xbox-Pad |
|---|---|---|
| Bewegen, Menüs | Pfeiltasten | Steuerkreuz, linker Stick |
| Linker Schlag (1) | A | X |
| Rechter Schlag (2) | S | Y |
| Linker Tritt (3) | Z | A |
| Rechter Tritt (4) | X | B |
| L1 / R1 | Q / W | LB / RB |
| L2 / R2 | 1 / 2 | LT / RT |
| Start | Enter | Start |
| Select | Tab | Back |
| Spiel beenden | Esc | |

- Die Tastatur geht nur, solange das Spielfenster den Fokus hat. Pads gehen auch
  ohne Fokus.
- Tastatur und das erste Pad steuern beide Spieler 1.
- PlayStation-Pads (DualShock 4, DualSense), Arcade-Sticks und Hitboxen werden
  über DirectInput gelesen. Du musst nichts installieren. Ein Arcade-Stick wurde
  mit echter Hardware getestet: alle Eingaben kamen an.
- Pads kannst du im laufenden Spiel ein- und ausstecken.
- **Pad, Arcade-Stick oder Hitbox: die Knöpfe stellst du im Launcher ein.**
  Öffne **Settings** und klicke **Set up controllers...** (Controller
  einrichten). Das Fenster zeigt die Controller, die Windows sieht, eine Zeile
  pro Spieler, und die Zeile leuchtet, wenn du einen Knopf drückst (sie nennt
  auch den Spielknopf dazu). Wähle einen Controller (oder drücke einfach einen
  Knopf darauf) und klicke **Set up all buttons** (alle Knöpfe einrichten): Es
  fragt "Press the button for 1 (Left Punch)..." (Drücke den Knopf für ...) und
  macht weiter mit 2, 3, 4, 1+2, 3+4, 1+3, 2+4, 1+2+3+4, Start und Select.
  **Skip** (Überspringen) lässt einen Knopf, wie er ist, **Clear** (Löschen)
  gibt ihm keinen Knopf. **Set selected** (Ausgewählten setzen) stellt eine
  Zeile ein, auch die anderen Makros (1+4, 2+3, 1+2+3 usw.), **Set up
  directions** (Richtungen einrichten) ist für Sticks, die ihre Richtungen als
  Knöpfe senden. **Layout** (Belegung) startet mit einer fertigen Belegung:
  Xbox, PlayStation, Switch, Arcade-Stick mit 8 Knöpfen (Vewlix), 6 Knöpfen
  (Noir / Sega Astro) oder Hitbox. Bei einer Hitbox wählst du auch, was
  passiert, wenn links und rechts zugleich gedrückt werden (SOCD), und ob der
  linke Stick als Steuerkreuz zählt. **Save** (Speichern) schreibt
  `native\controls.ini`; das Spiel liest sie beim Start. **Reset to defaults**
  (auf Standard zurücksetzen) stellt den Controller auf die Standardknöpfe
  zurück. Deine Kommentare und übrigen Einstellungen in der Datei bleiben
  erhalten. Mit dem Controller selbst: Oben / Unten wählen einen Knopf, Kreuz
  setzt ihn, Dreieck löscht ihn, Start speichert, Kreis schließt (die Knöpfe
  des Controllers, wie deine `controls.ini` sie hat). Das geht nur, solange
  dieses Fenster vorne ist; nimm das Häkchen bei "Move through this window with
  the controller" weg, wenn du Knöpfe nur testen willst.
- Die Tastatur und alles andere stellst du in der `controls.ini` ein. Die
  dokumentierte Vorlage mit allen Standardwerten ist [controls.ini](controls.ini).
  Lege deine Datei als `native\controls.ini` ab und starte das Spiel neu.
  Beispiele (aus der Vorlage):
  - `[keys1]` / `preset = tekken` — WASD zum Bewegen, U I J K für die Knöpfe.
  - Zwei Spieler an einer Tastatur: `[keys1] preset = tekken` und
    `[keys2] preset = numpad`.
  - `1+2 = O` — eine Taste für zwei Knöpfe.
- Das Options-Menü des Spiels kann die Knopfbelegung auch ändern.
- Eine Test-Zip von vor dem Abend des 2026-10-16 kennt nur Tastatur und
  Xbox-Pads. `controls.ini` und DirectInput kamen später.

## Online

1. Starte den Launcher und öffne den Reiter **Online**. Der öffentliche Server
   "T5DR Online" ist schon ausgewählt.
2. Klicke **Als Gast spielen** oder **Anmelden**. Für Ranked brauchst du ein
   Konto: Lege es im Reiter an und bewahre die Wiederherstellungs-Codes auf.
3. Suche ein **Quick**- oder **Ranked**-Match, oder öffne einen Lobby-Raum für
   einen Freund. Wird ein Gegner gefunden, siehst du den Ping und nimmst
   innerhalb von 15 Sekunden an.
4. Das Spiel zeigt seine eigene Charakterauswahl. Wähle deinen Kämpfer mit
   Pad, Stick oder Tastatur innerhalb von 30 Sekunden: Die Taste, mit der du
   bestätigst, wählt das Kostüm, **Select** (Tab auf der Tastatur, Back am
   Xbox-Pad) wählt zufällig. Wählst du nichts, bekommst du den Charakter aus
   dem Launcher. Haben beide gewählt, startet der Kampf: wer zuerst 3 Runden
   gewinnt. Der Name unter deinem Kämpfer zählt die Sekunden herunter;
   "PICKING..." beim Gegner heißt, du wartest auf seine Wahl.
5. Danach **Rematch** oder **Next game**. Ein Rematch führt wieder zur
   Charakterauswahl. In einem Ranked-Set bleiben die Kämpfer des ersten Spiels
   für alle Rematches. Das Spiel bleibt zwischen den Matches offen.

Gut zu wissen:

- Die beiden PCs schicken sich die Controller-Eingaben direkt zu. Lassen die
  Router das nicht zu, leitet der Lobby-Server sie weiter. Bei einer direkten
  Verbindung erfährt jeder PC die IP-Adresse des anderen.
- Kabel ist besser als WLAN.
- Beim ersten Mal fragt die Windows-Firewall, ob das Spiel und Python ins Netz
  dürfen. Erlaube es für **private Netzwerke**.
- Netcode: Rollback wie bei Tekken 6 Native Online. Das Input-Delay folgt dem
  Ping: 1 Frame bis etwa 60 ms, darüber 2. **Settings -> Online input delay**
  kann es auf 0, 1 oder 2 Frames festlegen; das gilt nur, wenn der Gegner
  dasselbe gewählt hat, sonst Auto. Ranked-Matches nutzen immer 2. Ruckelt ein
  Match auf einem langsamen PC, kann ein Spieler auf Delay-Netcode umschalten:
  Settings -> "Advanced: extra settings" -> `T5_RB_MODE=off`.
- Ranked nutzt eine Glicko-2-Wertung mit den Rang-Namen aus Tekken 5. Verlassen
  oder Verbindungsabbruch zählt als Niederlage. Ein Desync macht das Match
  ungültig.
- Mehr in [ONLINE.md](ONLINE.md) und [RANKED.md](RANKED.md) (auf Englisch).

Der Menüpunkt **Online** des Spiels braucht Sonys Server, die es nicht mehr
gibt: nach dem Nutzungsbedingungs-Bildschirm meldet das Spiel "A network error
occurred" und kehrt zum Titel zurück.

Du kannst einen eigenen Server betreiben: auf einem kleinen Linux-VPS, mit
Docker, auf einem Mac oder mit **Host for friends** im Launcher. Siehe
[HOSTING.md](HOSTING.md) (auf Englisch).

## Aktualisieren

Der Launcher bietet neue Versionen an; klicke auf **Update**.

- Beim Start (höchstens einmal pro Stunde) und mit **Check for updates** oben
  fragt der Launcher GitHub nach dem neuesten veröffentlichten Release. Er zeigt
  die Version, was neu ist und die Downloadgröße.
- **Update now** lädt das Zip (etwa 90 MB), prüft es gegen die veröffentlichte
  SHA-256-Prüfsumme, ersetzt die Programmdateien und startet den Launcher neu.
  Das dauert ein paar Sekunden plus den Download.
- Dein Ordner `native` (entpacktes Spiel, Speicherstände, Logs) und deine
  Einstellungen bleiben, wie sie sind.
- Wenn die neue Version den Spielcode ändert, steht im Reiter Play **Build the
  game once (about 2 minutes)**. Klicke auf **BUILD GAME**. Nur der Code wird neu
  gebaut.
- Der Launcher aktualisiert nie, solange das Spiel, ein Build oder ein
  Online-Match (oder eine Suche) läuft. Geht etwas schief, legt er die alten
  Dateien zurück und sagt, warum.

Von Hand (Versionen 1.0.0 und älter, die sich noch nicht selbst aktualisieren,
oder wenn das Update immer wieder scheitert):

1. Entpacke das neue Release in einen **neuen** Ordner.
2. Kopiere deinen alten Ordner `native` hinein. So bleiben das entpackte Spiel
   und deine Speicherstände erhalten.
3. Starte den Launcher. Wenn die neue Version den Spielcode ändert, sagt dir das
   der Reiter Play. Klicke dann nochmal auf **BUILD GAME**. Nur der Code wird neu
   gebaut.

## Fehler melden

**Probleme? Klicke auf "Report a problem"** (Reiter Play; auch im Reiter Build und
im Reiter Online nach einem Match). Der Launcher macht EINE Zip-Datei auf deinem
Desktop und öffnet den Ordner. Schicke das Zip der Person, die dir das Spiel
gegeben hat, oder hänge es an ein Issue unter
https://github.com/TheWishin/T5DROnline/issues. Im Fenster kannst du ein paar
Worte dazu schreiben, was passiert ist.

Im Zip sind die neuesten Spiel-Logs, `build.log` wenn das Bauen das Problem war,
das Log des Launchers, die Dateien deines letzten Online-Matches, deine
`controls.ini`, Desync-Dumps (falls es welche gibt) und `system.txt`:
Windows-Version, Prozessor, Grafikkarte samt Treiber, Arbeitsspeicher, Bildschirme
(Bildwiederholrate, Skalierung), Release-Version und Build-ID und deine
Einstellungen. Das Fenster zeigt alles an, bevor es speichert. Es wird nichts
hochgeladen: du schickst das Zip selbst.

Bevor das Zip entsteht, wird dein Windows-Benutzername in Dateipfaden zu `<user>`,
IP-Adressen aus dem Internet werden zu `<ip>` (Adressen deines eigenen Netzes
bleiben), und Passwörter, Tokens und Match-Schlüssel werden weggelassen. Das Zip
ist höchstens 20 MB groß; ein größeres Log behält seinen Anfang und sein Ende.
Deine Spieldateien, Schlüssel, `.pkg` und `.rap` sind nie darin.

Wenn der Launcher selbst nicht startet, schicke von Hand `native\build.log`
(Probleme beim Bauen) oder die neueste Datei in `native\logs\` (Probleme im Spiel),
dazu deine Windows-Version, Grafikkarte und was du kurz vorher getan hast. Diese
Dateien enthalten Ordnerpfade mit deinem Windows-Benutzernamen. Schau vorher hinein,
bevor du sie öffentlich postest.

Mehr Hilfe: [TROUBLESHOOTING.md](TROUBLESHOOTING.md) (auf Englisch). Die
wichtigsten Fälle in Kürze:

- **"This copy is a different version of the game"**: Deine Kopie ist nicht
  NPUB30009 Version 01.00. Es gibt nur diese eine.
- **"The license (.rap) does not belong to this package"**: Nimm die `.rap`, deren
  Name zur Content-ID `UP0700-NPUB30009_00-UPDATE0000010000` passt.
- **Windows warnt vor `T5DR Online.exe`**: Die Datei ist nicht signiert. "Weitere
  Informationen", dann "Trotzdem ausführen".
- **Kein Ton**: Stelle in Windows das richtige Standard-Wiedergabegerät ein und
  starte das Spiel neu. Prüfe, dass "Mute sound" in den Settings aus ist.
- **Controller doppelt oder gar nicht erkannt**: DS4Windows oder Steam Input
  erzeugen ein zweites, virtuelles Pad. Verstecke eines von beiden.
- **Weißer Bildschirm nach etwa 3 Minuten**: Bekannter Speicherfehler. Neu starten.

## Häufige Fragen

**Brauche ich eine PS3 oder RPCS3?** Nein. Du brauchst die `.pkg` und `.rap` deines
eigenen Kaufs. RPCS3 wird nicht benutzt und nicht installiert.

**Kann ich eine Disc-Kopie, die EU-/JP-Version oder eine andere Version nehmen?**
Nein. Nur NPUB30009 Version 01.00. Alles andere lehnt der Builder ab.

**Woher bekomme ich das Spiel?** Aus deinem eigenen PlayStation-Network-Konto. Wir
liefern weder Paket noch Lizenz und können nicht dabei helfen, sie zu beschaffen.

**Läuft es unter Linux oder macOS?** Nein. Nur Windows führt einen rekompilierten
Titel heute aus.

**Warum braucht das Bauen Internet?** Einmalig, um etwa 50 KB öffentliche
Schlüsseldaten von github.com zu laden (siehe Danksagung).

**Warum warnt Windows vor dem Launcher?** `T5DR Online.exe` ist ein winziges,
nicht signiertes Startprogramm. Eine Code-Signatur ist noch nicht eingerichtet.

**Wo sind meine Speicherstände?** In `native\gamedata`. Im Reiter Play gibt es den
Knopf **Open saves folder**. Sichere den Ordner, bevor du experimentierst.

**Kommt der PSN-Onlinemodus zurück?** Nein. Die Server gibt es nicht mehr.
Online-Spiel wird unsere eigene Lobby benutzen.

**Wie deinstalliere ich?** Lösche den Ordner.

## Danksagung

- **[ps3recomp](https://github.com/sp00nznet/ps3recomp)** von Ned Heller
  (sp00nznet) und Mitwirkenden (MIT). Es übersetzt den PS3-Code und liefert die
  Laufzeitbibliotheken: D3D12-Grafik, WASAPI-Ton, XInput-Pads. Wir bauen gegen
  den **Branch von NoahBPeterson** `infamous/upstream-sync`
  (https://github.com/NoahBPeterson/ps3recomp), festgelegt auf Commit `f17bcd3`,
  plus unsere Patches in `patches/ps3recomp/`.
- **[Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online)** von
  Ekspym. Die Vorlage dafür, wie dieses Projekt funktioniert: ein Launcher zum
  Selberbauen, eine Lobby und Rollback-Netcode.
- **RPCS3** — wir starten und installieren es nie. Wir haben seinen Open-Source-Code
  als Vorlage für die Entschlüsselung von PS3-Paket und -Lizenz (NPDRM) benutzt.
  Das Bauen lädt außerdem zwei öffentliche Textdateien aus seinem Repository
  (`rpcs3/Crypto/key_vault.h` und `key_vault.cpp`), um die öffentlichen
  Schlüsseltabellen daraus zu lesen.
- Der ATRAC3plus-Musikdecoder stammt aus FFmpeg, über PPSSPPs `at3_standalone`
  (LGPL-2.1 oder neuer), so wie ps3recomp ihn mitliefert.
- Videos werden mit Windows Media Foundation dekodiert.
- Die Release-Zip enthält außerdem Python (PSF-Lizenz) und LLVM clang-cl / lld-link
  (Apache-2.0 mit LLVM-Ausnahme). Die Lizenztexte liegen in `LICENSES\`.
- Das Spiel selbst ist das Werk von Bandai Namco und dem ursprünglichen
  Tekken-Team.
- Entwickelt mit Hilfe von Claude (Anthropic), einem KI-Assistenten.

## Rechtliches

In diesem Repository und in den Releases steckt kein Sony- oder Namco-Code, es
stecken keine Schlüssel und keine Spieldaten darin. Du musst das Spiel besitzen.
Das Programm des Spiels, seine Daten, der übersetzte Code, die Schlüssel und deine
`.pkg` / `.rap` bleiben auf deinem eigenen PC. Git ignoriert sie, und die CI des
Projekts führt eine Prüfung aus, die bei allem Spiel-Abgeleiteten fehlschlägt.

Das ist ein Fan-Projekt. Es steht in keiner Verbindung zu Bandai Namco
Entertainment oder Sony Interactive Entertainment und wird nicht von ihnen
unterstützt. Tekken ist eine Marke von Bandai Namco. Die Regeln zum Entschlüsseln
und Umwandeln von Spielen, die du besitzt, sind von Land zu Land verschieden. Du
bist selbst dafür verantwortlich, deine einzuhalten. Das ist keine Rechtsberatung.

Der eigene Code und die Doku dieses Projekts stehen unter der MIT-Lizenz
(`LICENSE`). Quellcode: https://github.com/TheWishin/T5DROnline-Source ps3recomp steht ebenfalls unter der MIT-Lizenz. Die Lizenz gilt für
nichts vom Spiel.

## Aus dem Quellcode bauen

Die meisten Spieler nehmen die Release-Zip. Entwickler bauen so.

Du brauchst Windows 10/11, die Visual Studio 2022 Build Tools (MSVC x64, Windows
SDK, CMake + Ninja, clang-cl), Python 3.10+ und Git. Der Reiter Build im Launcher
kann die Visual-Studio-Teile für dich installieren (winget, mit deiner
Zustimmung).

```
python tools/build_game.py --pkg <deine.pkg> --rap <deine.rap>
python tools/run_game.py [--log DATEI] [NAME=WERT ...]
```

`build_game.py` holt ps3recomp beim festgelegten Commit, wendet
`patches/ps3recomp/*.patch` in Namensreihenfolge an und entpackt, entschlüsselt,
übersetzt und kompiliert dann. Jeder Schritt wird übersprungen, wenn sein Ergebnis
schon da ist. `--out ORDNER` legt alle Ausgaben unter ORDNER ab.

Zum Weiterlesen (alles auf Englisch):

- Der Ordner `docs/` — wie die einzelnen Teile funktionieren: Grafik, Netplay,
  Rollback, Lobby, Hosting, Releases.
- [RELEASE.md](RELEASE.md) — der Launcher, die Zip und wie sie gepackt wird
  (`tools/package_release.py`).
- [ONLINE.md](ONLINE.md) — die Lobby: Protokoll, NAT, eigener Server.
- [CI.md](CI.md) — Continuous Integration und die Prüfung auf Spieldaten
  (`python tools/check_no_game_data.py`, bevor du committest).
- [controls.ini](controls.ini) — alle Steuerungs-Einstellungen.
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Lösungen für Spieler.
- [../CHANGELOG.md](../CHANGELOG.md) — was wann dazukam.

**Committe niemals etwas Spiel-Abgeleitetes.** Das Repository ist öffentlich.
