# Tekken 5: Dark Resurrection Online — native Windows-Version

Tekken 5: Dark Resurrection (PS3, PlayStation-Network-Version), das nativ unter
Windows läuft. Es wird rekompiliert, nicht emuliert. Online gespielt wird über
die eigene Lobby des Launchers, wie bei Tekken 6 Native Online.

English: [../README.md](../README.md)

<!-- RELEASE LINE: the version and date in the next two lines change with every release, when it is tagged
(docs/RELEASING.md "Cutting a release", step 2); the same lines are in README.md. -->
**Release 1.1.4 (2026-10-21).** Lade
`T5DR-Online-1.1.4.zip` von https://github.com/TheWishin/T5DROnline/releases

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

## Stand (2026-10-21)

Getestet auf einem Entwicklungs-PC (Windows 11, Ryzen 9 mit 16 Kernen, RTX 3090).
Online wurde zwischen zwei echten PCs über das Internet getestet
(AMD/60 Hz gegen Intel/240 Hz).

| Bereich | Stand |
|---|---|
| Start | Funktioniert. Startet, öffnet das Fenster, erreicht Titel, Menüs, Charakterwahl und Kämpfe. |
| Menüs, Kämpfe | 60 fps, auch wenn andere Programme den PC auslasten. Das Spiel wartet nicht mehr aktiv auf seine Frames: etwa 30 % weniger CPU bei 8 Kernen / 16 Threads. Seit 1.1.3 brauchen die eigene Arbeit des Spiels und das Übersetzen seiner Zeichenbefehle etwa ein Viertel weniger Prozessorzeit pro Kampf-Frame, und ein PC, der knapp zu langsam für 60 fps ist, schafft in Kämpfen 45-55 statt 30-45 fps (gemessen mit gebremsten Test-Spielen; echte schwache PCs sind noch nicht gemessen). Seit 1.1.4 sparen zwei Änderungen am Code des Spiels weiter Prozessorzeit pro Frame (4 Kerne unter Last): Register bleiben zwischen Aufrufen im Prozessor (Haupt-Thread ~7 %, Zeichen-Thread ~18 % weniger), und Schreibzugriffe auf den Speicher sind billiger (5-7 % und 15-25 % weniger). Außerdem geht ein fertiges Bild an die Grafikkarte, während das Spiel schon sein nächstes rechnet: auf einem gebremsten 4-Kern-Test-PC kommt ein verspätetes Bild etwa 1 ms früher. |
| Laptops, Handhelds | **Stromsparen** (Launcher-Einstellungen; Auto schaltet es ein bei Akku, Energiesparplan, mobilem Prozessor oder integrierter Grafik): weniger Hilfs-Threads, kein aktives Warten, online dasselbe Spiel. Noch nicht auf einem echten Laptop oder Handheld ausprobiert. Seit 1.1.4 starten Geräte mit integrierter Grafik außerdem mit der Internen Auflösung Auto, und der Reiter Offline spielen sagt, wenn der Prozessor deutlich unter seinem normalen Takt lief (und schlägt den Windows-Energiemodus Beste Leistung vor). |
| Spielmodi | Arcade, Ghost, Versus (zwei Spieler an einem PC), Survival und Practice laufen. Gallery und das Online-Menü des Spiels brauchen die Server von Namco und Sony (abgeschaltet) und sagen das. |
| Kämpfer, Stages | Alle Kämpfer und Stages werden richtig dargestellt, auch Gesichter, Bodenschatten und Figuren im Hintergrund. Stage-Unschärfe und das Leuchten der Sonne sehen bei jeder internen Auflösung aus wie auf der PS3, wenn Settings -> Stage blur / glow auf An steht (Aus, scharf und ohne Leuchten, ist seit 1.1.4 der Standard). |
| Freischaltungen, Kostüme | Offline, in den Launcher-Einstellungen -> Unlocks (alles anfangs aus): alle Stages ohne die Kämpfe, die sie sonst kosten, Jinpachi und das Zufallsfeld in der Charakterwahl ohne Arcade-Durchspielen und alle Customize-Items für 0 Fight Money (dein Spielstand wird vorher gesichert). Online-Spiele haben einen eigenen frischen Spielstand, auf beiden PCs derselbe; nur dein eigenes Kostüm kommt aus deinem Spielstand, und beide Spieler sehen beide Kostüme (1.1.3). Beide PCs prüfen das Kostüm gegen die Tabellen des Item-Shops im Spiel und nehmen sonst das Standard-Kostüm (1.1.4). |
| Anzeige | Fenster in jeder Größe, randloses Vollbild (Alt+Enter oder F11). **Interne Auflösung** von Lowest (0,5x) über Native (720p) bis 1080p, 1440p und 4K, oder Auto (die Stufe des Bildschirms, mit integrierter Grafik höchstens 1080p) (Launcher-Einstellungen, `PS3_INTERNAL_RES`); jede Stufe in Kämpfen, Menüs, Videos und Charakterwahl geprüft. Weniger Arbeit für die Grafikkarte ab 1080p (1.1.3). Mit integrierter Grafik ist Auto der Standard (1.1.4). |
| Musik, Soundeffekte, Videos | Funktionieren. |
| Steuerung | Tastatur, Xbox-Controller (XInput), DualShock 4 und DualSense über USB und Bluetooth (direkt gelesen, ohne Steam), Arcade-Sticks und Hitboxen (DirectInput), zwei Spieler an einem PC, Knöpfe im Launcher einstellbar (Settings -> Set up controllers) oder in der `controls.ini`. Kurze Taps gehen nie verloren. Von einem Menschen ausprobiert: Xbox-Pad und Arcade-Stick, alle Eingaben kamen an, flüssig. **Set up controllers** fand von 1.1.0 bis 1.1.3 gar keinen Controller; es funktioniert wieder (1.1.4). |
| Trainings-Werkzeuge | Im Practice-Modus: eine Eingabe-Anzeige (die letzten Eingaben jedes Spielers, jede mit der Zahl der Frames, die sie gehalten wurde) und Framedaten nach jedem Schlagabtausch (Startup und wer zuerst wieder handeln kann: `+3`, `-12`), scharf über das Bild gezeichnet, bei jeder Auflösung. Launcher: Settings -> Trainings-Anzeige (Aus / Eingaben / Eingaben + Framedaten, auch in den anderen Offline-Modi, online nur die eigenen Eingaben), F2 schaltet sie im Spiel um. Siehe [TRAINING.md](TRAINING.md) (englisch). |
| Speichern | Funktioniert. Die Uhr im Spiel zeigt das echte Datum. |
| Lange Sitzungen | Der alte Speicherfehler (weißes Bild nach ein paar Besuchen des Titels) ist behoben. |
| Online-Spiel | Funktioniert auf einem PC und über den öffentlichen Lobby-Server. Rollback-Netcode: 1 Frame Input-Delay bis ~60 ms Ping, darüber 2 (Settings -> Online input delay; Ranked: immer 2), getestet bei 0/50/150 ms Ping mit Paketverlust. Zwischen zwei echten PCs über das Internet gespielt (18.10.2026). Quick- und Ranked-Suche nehmen zuerst Gegner mit niedrigem Ping (geschätzt über den nächsten Relay-Server) und erweitern die Suche, während du wartest. Viele abgebrochene Matches hintereinander machen das offene Spiel nicht mehr kaputt. Einen Online-Kampf kann niemand pausieren. Matches kommen auch zustande, wenn eine Firewall das Spiel blockiert: über das Relay, wenn sonst nichts durchkommt (1.1.3); dort spielt das Spiel wie ein direktes Match bei gleichem Ping, weil der Launcher die Pakete des Spiels sofort weitergibt (1.1.4). |
| Charakterwahl online | Quick-Matches, Räume und Einladungen von Freunden bieten für beide Spieler auch Jinpachi (obere Reihe, rechts außen) und das Zufallsfeld des Spiels (obere Reihe, links außen); Ranked-Matches und Turnier-Sets nicht. Mokujin und das Zufallsfeld würfeln in jedem Match neu (1.1.4). |
| Intros, Wiederholung | Online werden die Intros der Kämpfer (etwa 7 s) und die Wiederholung nach einer Runde (etwa 9 s) übersprungen, sobald beide Spieler Start gedrückt haben; ein Spieler allein überspringt nichts, und Start pausiert einen Online-Kampf weiterhin nie (1.1.4). |
| Freunde, Einladungen | Mit Konto fügst du auf der Seite **Freunde** im Online-Reiter Freunde mit ihrem Namen hinzu und siehst, wer online ist, sucht oder im Match ist. **Einladen** zu einem lockeren Match oder in deinen Raum: ein Klick auf Annehmen startet es. |
| Räume | Lobby-Räume für 2 oder Community-Räume für bis zu 8, die sich abwechseln (der Sieger bleibt, oder jeder der Reihe nach); offen, mit Passwort oder Einladungscode, oder versteckt (1.1.3). Freunde, die das Passwort eines Raums kennen, kommen immer hinein, auch wenn Fremde es gerade zu erraten versuchen; der Host sieht, wie viele falsche Passwörter kamen, und kann diese Netzwerke abweisen (1.1.4). |
| Turniere | Mit Konto im Online-Reiter bei Turnieren mitspielen (Turnier-Hosts legen sie an; für einen der 20 Host-Plätze eine DM an wishin): Single oder Double Elimination, Sets bis 2 oder 3 Siege, bis zu 64 Spieler; der Server ruft jedes Set auf, und das Spiel startet von selbst (1.1.3). |
| Hinweise | Wartest du in einem anderen Fenster? Wenn ein Match gefunden wird, jemand deinem Raum beitritt, du in einem Raum dran bist, ein Freund dich einlädt, ein Turnier-Set bereit ist oder dein Gegner ein Rematch will, spielt der Launcher einen kurzen Ton und seine Taskleisten-Schaltfläche blinkt, bis du zurück bist (Settings -> Ton und Taskleistenblinken; anfangs an; 1.1.4). |
| Replays | Jedes Online-Match wird gespeichert (ein paar KB). Der Reiter **Replays** spielt es im Spiel noch einmal ab und prüft, dass es mit dem Live-Match identisch ist. |
| Zuschauen | **Zuschauen** beim Match eines Freundes, eines Raums oder einem Turnier-Set, live im eigenen Spiel, ein paar Sekunden dahinter und Bild für Bild geprüft; nur wenn beide Spieler es erlauben (Settings -> Spectators) (1.1.3). Das Zuschauen bei einem Raum geht auch zwischen einem Match und seinem Rematch, und bei einem vollen Match haben Freunde und Raummitglieder Vorrang (1.1.4). |
| Launcher | Englisch und sechs Übersetzungen: Deutsch, Español, 한국어, 日本語, Português (Brasil), Français, ohne abgeschnittene Texte bei 100 % und 150 % Anzeige-Skalierung. Der Einstellungen-Reiter scrollt. Neben jedem Namen im Online-Reiter steht das Rang-Schild des Spiels selbst, nach BUILD GAME aus deiner eigenen Kopie gelesen, und das Fenster wird mehr als doppelt so schnell neu gezeichnet (1.1.4). Aktualisiert sich selbst. |
| Bauen aus deiner Kopie | Funktioniert auf dem Entwicklungs-PC. Ein stehengebliebener Hilfsprozess hält das Bauen nicht mehr bei "Translate code" an; eine Datei, die beim Kompilieren scheitert, bekommt einen zweiten Versuch (1.1.3). |

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
6. Reiter **Play offline**: Gib einen Namen ein (freiwillig) und klicke auf **PLAY OFFLINE** (Arcade, Versus,
   Practice ... an diesem PC). Für Matches über das Internet nimm den Reiter **Play online**.

Alles, was das Bauen erzeugt, bleibt im Ordner `native` neben dem Launcher. Das
sind Spieldaten. Gib sie nicht weiter. Zum Deinstallieren löschst du den ganzen
Ordner.

## Sprache des Launchers

Der Launcher spricht Deutsch, Englisch, Spanisch, Koreanisch, Japanisch,
brasilianisches Portugiesisch und Französisch. Unter **Einstellungen** ->
**Sprache** stellst du ein: **Auto** nimmt die Sprache von Windows (Englisch, wenn
Windows eine andere Sprache hat), dazu jede Sprache unter ihrem eigenen Namen:
**English**, **Deutsch**, **Español**, **한국어**, **日本語**, **Português (Brasil)**,
**Français**. Eine Änderung gilt, wenn der Launcher neu startet (der Knopf **Jetzt
neu starten** macht das). Das Spiel selbst bleibt englisch. Die spanischen,
koreanischen, japanischen, portugiesischen und französischen Texte sind mit
maschineller Hilfe übersetzt: Klingt etwas falsch, sag uns Bescheid --
Korrekturen sind willkommen.

Diese Anleitung nennt die Knöpfe oft englisch, so wie sie im englischen Launcher
heißen. Im deutschen Launcher heißen sie:

| Englisch | Deutsch |
|---|---|
| Build, Play offline, Play online, Settings (Reiter) | Bauen, Offline spielen, Online spielen, Einstellungen |
| PLAY OFFLINE | OFFLINE SPIELEN |
| Cancel | Abbrechen |
| Stop game | Spiel stoppen |
| Open saves folder | Speicherordner öffnen |
| Check for updates, Update now | Nach Updates suchen, Jetzt aktualisieren |
| Report a problem | Problem melden |
| Host for friends | Für Freunde hosten |
| Online input delay | Online-Input-Delay |
| Advanced: extra settings | Erweitert: zusätzliche Einstellungen |
| Mute sound | Ton aus |
| Stage blur / glow | Stage-Unschärfe / Leuchten |
| Power saving (laptops, handhelds) | Stromsparen (Laptops, Handhelds) |
| Unlocks, Unlock all stages, Unlock Jinpachi and Random select, Unlock all customization items | Freischaltungen, Alle Stages freischalten, Jinpachi und die Random-Auswahl freischalten, Alle Customize-Items freischalten |

**BUILD GAME**, **Quick Match** und **Ranked-Match** heißen in beiden
Sprachen gleich.

## Spielen

- Das Spiel öffnet ein eigenes Fenster und skaliert sein Bild auf das Fenster.
  Unter **Settings** gibt es Fenstergrößen, maximiert, randloses Vollbild und
  Stumm. Der Einstellungen-Reiter ist höher als das Fenster: scrolle ihn mit
  dem Mausrad oder der Bildlaufleiste.
- **Settings** -> **Internal resolution** (interne Auflösung) stellt ein, wie
  scharf das Bild ist, wie bei einem Emulator: Native ist das 1280 x 720 der
  PS3; 1080p, 1440p und 4K zeichnen das Spiel größer (scharf auf großen
  Bildschirmen, mehr Arbeit für die Grafikkarte: der Launcher nennt die Stufe,
  die zu deinem Bildschirm passt); Lower und Lowest zeichnen die 3D-Szene
  kleiner für schwache Grafikkarten (Laptops, integrierte Grafik), das HUD
  bleibt scharf. **Auto** nimmt die Stufe, die zu deinem Bildschirm passt,
  mit integrierter Grafik höchstens 1080p (sie teilt sich Speicher und Strom
  mit dem Prozessor, ein größeres Bild bremst dort das ganze Spiel). Seit
  1.1.4 ist Auto mit integrierter Grafik der Standard (ab dem zweiten Spiel:
  der Launcher liest es aus dem Log des ersten); eine Stufe, die du wählst,
  bleibt, und über der Stufe von Auto sagen die Einstellungen und der
  Reiter Offline spielen, dass sie auch den Prozessor bremst. Es ändert nur
  das Bild, der andere Spieler online braucht also nicht dieselbe
  Einstellung. Fallen Kämpfe unter 60 fps, geh eine Stufe
  herunter. Mehr in [TROUBLESHOOTING.md](TROUBLESHOOTING.md#low-frame-rate)
  (englisch).
- **Settings** -> **VSync**: An (flüssig, Standard) oder Aus (geringste
  Verzögerung, das Bild kann reißen). Das Spiel läuft immer mit 60 fps, wie
  auf der PS3, deshalb gibt es keine Einstellung für die Bildrate. Online kann
  jeder Spieler selbst wählen.
- **Settings** -> **Stage blur / glow** (Stage-Unschärfe / Leuchten): Manche
  Stages machen das ganze Bild weich (der neblige Sumpf und drei weitere) oder
  lassen die Sonne leuchten (der Schrottplatz). Aus (seit 1.1.4 der Standard,
  einmalig auch für Spieler älterer Versionen) zeigt diese Stages scharf, ohne
  das Leuchten; An sieht aus wie auf der PS3, bei jeder internen Auflösung. Online kann jeder Spieler selbst wählen.
- **Settings** -> **Power saving (laptops, handhelds)** (Stromsparen): Auto
  (Standard) schaltet es ein bei Akkubetrieb, Stromsparmodus oder dem
  Energiesparplan, einem mobilen Prozessor oder integrierter Grafik; mit An und
  Aus entscheidest du selbst. Das Spiel nutzt dann weniger Hilfs-Threads und
  wartet nie aktiv, so bleibt der Prozessor kühler und hält seinen Takt; im
  Fenstertitel steht "power saving". Das Spiel selbst ist dasselbe, online
  braucht der andere Spieler also nicht dieselbe Einstellung. Noch nicht auf
  einem echten Laptop oder Handheld ausprobiert; siehe
  [TROUBLESHOOTING.md](TROUBLESHOOTING.md#game-speeds-up-or-slows-down-on-a-laptop-or-handheld)
  (englisch).
- **Settings** -> **Trainings-Anzeige**: Im Practice-Modus zeigt das Spiel deine
  letzten Eingaben (Richtungen als Pfeile, 1 2 3 4 für die Knöpfe, jede mit der
  Zahl der Frames, die sie gehalten wurde) und nach jedem Schlagabtausch den
  Startup des Moves (`i10`) und wer zuerst wieder handeln kann (`GEBLOCKT +3`,
  `TREFFER -12`). Aus / Eingaben / Eingaben + Framedaten; auf Wunsch auch in
  den anderen Offline-Modi und online (dort nur deine eigenen Eingaben). **F2**
  im Spiel schaltet sie um. Sie liest das Spiel nur und ändert nie ein Match.
  Mehr in [TRAINING.md](TRAINING.md) (englisch).
- **Settings** -> **Unlocks** (Freischaltungen, für das Spiel offline; alles
  ist anfangs aus):
  - **Alle Stages freischalten**: Die Tekken-5-Stages (die alten, sonst nach
    etwa 50 Kämpfen verdient, ein paar Arcade-Durchgängen) gibt es in Arcade,
    VS, Practice und den anderen Modi, ohne den Arcade-Modus durchzuspielen. Dein Spielstand wird
    nicht verändert: Ausgeschaltet ist das Spiel wie vorher.
  - **Jinpachi und die Random-Auswahl freischalten**: Die Charakterauswahl hat
    Jinpachi (obere Reihe, rechts außen) und das Zufallsfeld (obere Reihe, links
    außen), ohne den Arcade-Modus durchzuspielen. Dein Spielstand wird nicht
    verändert. Online brauchst du es nicht: Casual-Matches und Räume haben
    immer beide, Ranked nie.
  - **Alle Customize-Items freischalten**: Alles im **ITEM SHOP & EQUIP** (nach
    der Kämpferwahl in Arcade, Ghost oder Survival) kostet 0 Fight Money. Was du
    dir nimmst, bleibt in deinem Spielstand wie ein gekauftes Item, auch nach
    dem Ausschalten; der Launcher sichert deinen Spielstand vor dem ersten Spiel
    damit einmal (im Ordner `save-backups` im Spielordner; zum Rückgängigmachen
    zurückkopieren).
  - Online wird die Stage-Freischaltung nicht benutzt: Dort haben beide Spieler
    immer dieselben Stages zur Wahl (die Stage wählt die Lobby). Was du im
    Item-Shop genommen und angezogen hast, zeigt sich online aber als dein
    eigenes Kostüm (ab 1.1.3; siehe "Online").
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
- Tastatur und das erste Pad steuern beide Spieler 1. Online ist der Controller,
  den du drückst, dein Spieler, egal an welchem Port (ein in der `controls.ini`
  festgelegtes `[port1] device` bleibt der einzige).
- PlayStation-Pads (DualShock 4, DualSense) liest das Spiel direkt, über USB und
  Bluetooth, auch nachdem Steam oder DS4Windows sie benutzt haben (Steam ist nicht
  nötig; startet Steam das Spiel mit Steam Input, nimmt das Spiel das virtuelle
  Pad von Steam). Arcade-Sticks und Hitboxen werden über DirectInput gelesen. Du
  musst nichts installieren. Ein Arcade-Stick wurde mit echter Hardware getestet:
  alle Eingaben kamen an.
- Pads kannst du im laufenden Spiel ein- und ausstecken.
- **Pad, Arcade-Stick, Hitbox oder Tastatur: die Knöpfe stellst du im Launcher ein.**
  Öffne **Settings** und klicke **Set up controllers...** (Controller
  einrichten). Das Fenster zeigt die Controller, die Windows sieht, und die
  Tastatur, eine Zeile pro Spieler, und die Zeile leuchtet, wenn du einen Knopf
  drückst (sie nennt auch den Spielknopf dazu). Wähle einen Controller (oder
  drücke einfach einen Knopf darauf; die Tastatur: klicke ihre Zeile) und klicke
  **Set up all buttons** (alle Knöpfe einrichten): Es fragt "Press the button for
  1 (Left Punch)..." (Drücke den Knopf für ...) und macht weiter mit 2, 3, 4,
  1+2, 3+4, 1+3, 2+4, 1+2+3+4, L1, R1, L2, R2, L3, R3, Start und Select -- jeder
  Knopf des PS3-Pads und jede Tekken-Kombination kann eine eigene Taste oder
  einen eigenen Knopf haben, auch online.
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
- Alles andere stellst du in der `controls.ini` ein. Die
  dokumentierte Vorlage mit allen Standardwerten ist [controls.ini](controls.ini).
  Lege deine Datei als `native\controls.ini` ab und starte das Spiel neu.
  Beispiele (aus der Vorlage):
  - `[keys1]` / `preset = tekken` — WASD zum Bewegen, U I J K für die Knöpfe.
  - Zwei Spieler an einer Tastatur: `[keys1] preset = tekken` und
    `[keys2] preset = numpad`.
  - `1+2 = O` — eine Taste für zwei Knöpfe.
- Das Options-Menü des Spiels kann die Knopfbelegung auch ändern, nur für das
  Spielen offline (Online-Spiele haben einen eigenen frischen Spielstand, siehe "Online").
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
   Xbox-Pad) wählt zufällig. In Quick-Matches, Räumen und Einladungen hat die
   obere Reihe für beide auch **Jinpachi** (rechts außen) und das
   **Zufallsfeld** des Spiels (links außen); Ranked-Matches und Turniere haben
   beides nicht. Mokujins kopierter Kämpfer und das Zufallsfeld werden in
   jedem Match neu gezogen (auf beiden PCs gleich). Wählst du nichts,
   bekommst du den Charakter aus dem Launcher. Haben beide gewählt, startet der Kampf: wer zuerst 3 Runden
   gewinnt. Der Name unter deinem Kämpfer zählt die Sekunden herunter;
   "PICKING..." beim Gegner heißt, du wartest auf seine Wahl.
5. Danach **Rematch** oder **Next game**. Ein Rematch führt wieder zur
   Charakterauswahl. In einem Ranked-Set bleiben die Kämpfer des ersten Spiels
   für alle Rematches. Das Spiel bleibt zwischen den Matches offen.

Gut zu wissen:

- Die beiden PCs schicken sich die Controller-Eingaben direkt zu. Lassen die
  Router das nicht zu, leitet ein Relay-Server sie weiter (die Lobby nimmt den,
  der für euch beide am nächsten liegt). Bei einer direkten Verbindung erfährt
  jeder PC die IP-Adresse des anderen.
- Quick- und Ranked-Suche suchen zuerst einen Gegner mit niedrigem Ping und
  erweitern die Suche, während du wartest: jeder Ping nach 30 Sekunden (Quick)
  oder 60 Sekunden (Ranked). Der Ping, den ein gefundenes Match zeigt, rechnet
  den nächsten Relay-Server mit ein.
- Kabel ist besser als WLAN.
- Beim ersten Mal fragt die Windows-Firewall, ob das Spiel und Python ins Netz
  dürfen. Erlaube es für **private Netzwerke**. Auf Abbrechen geklickt? Matches
  kommen trotzdem zustande, manche nur über das Relay; der Online-Tab zeigt dann
  eine Firewall-Zeile mit **So behebst du es**.
- Netcode: Rollback wie bei Tekken 6 Native Online. Das Input-Delay folgt dem
  Ping: 1 Frame bis etwa 60 ms, darüber 2. **Settings -> Online input delay**
  kann es auf 0, 1 oder 2 Frames festlegen; das gilt nur, wenn der Gegner
  dasselbe gewählt hat, sonst Auto. Ranked-Matches nutzen immer 2. Ruckelt ein
  Match auf einem langsamen PC, kann ein Spieler auf Delay-Netcode umschalten:
  Settings -> "Advanced: extra settings" -> `T5_RB_MODE=off`.
- Online-Spiele haben einen eigenen Spielstand (`gamedata-online` im
  Spielordner), auf beiden PCs derselbe frische: Was du in den **OPTIONS** des
  Spiels einstellst (Tastenbelegung, Rundenzeit, Schwierigkeit) und deine
  Freischaltungen gelten nur offline, damit beide Spieler immer dasselbe Spiel
  spielen. Stell deine Tasten im Launcher ein (Settings -> Set up
  controllers); die gelten auch online. Dein eigener Spielstand wird beim
  Online-Spielen nie angefasst. Nur dein eigenes Kostüm wird daraus gelesen
  (siehe unten).
- Einen Online-Kampf kann niemand pausieren (ab 1.1.2): **Start** öffnet dort
  für keinen der beiden Spieler das Pausenmenü. Das Replay nach einer Runde
  überspringt Start weiterhin. Wer ein Match abbrechen will, schließt das Spiel
  (zweimal Esc): Das zählt wie bisher als Niederlage.
- Ranked nutzt eine Glicko-2-Wertung mit den Rang-Namen aus Tekken 5 und, ab
  1.1.4, den Rang-Schildern des Spiels selbst (Beginner, 9th kyu ... Tekken
  Lord) neben jedem Namen. Der Launcher liest die Schilder nach BUILD GAME aus
  deinem entpackten Spiel (im Download sind sie nicht); bis dahin zeigt er ein
  Text-Abzeichen in der Farbe des Schilds. Verlassen oder Verbindungsabbruch
  zählt als Niederlage. Ein Desync macht das Match ungültig.
- **Freunde** (mit Konto, ab 1.1.2): Füge auf der Seite **Freunde** im
  Online-Reiter einen Freund mit seinem Kontonamen hinzu. Hat er angenommen,
  siehst du, wann er online ist, sucht oder im Match ist. **Zu einem Match
  einladen** (oder in deinen Raum) fragt ihn; ein Klick auf **Annehmen** auf
  seiner Seite startet es. Wer einen Spieler blockiert, beendet die
  Freundschaft.
- **Deine eigenen Kostüme online** (ab 1.1.3): was du offline im Item-Shop
  gekauft und angezogen hast, sehen du und dein Gegner auch im Online-Match.
- **Turniere** (mit Konto, ab 1.1.3): Die Seite **Turniere** im Online-Reiter
  zeigt die Turniere des Servers. **Anmelden** (und **Einchecken**, wenn das
  Turnier danach fragt); ist dein Set dran, zeigt der Reiter „Dein Turnier-Set
  ist bereit“: **Annehmen** innerhalb von 5 Minuten, dann startet das Spiel von
  selbst. Sets gehen über Best of 3 oder 5 und laufen wie lockere Sets mit der
  Auswahl im Spiel; der Turnierbaum (Single oder Double Elimination) füllt sich
  von selbst. Turnier-Hosts legen Turniere mit **Anlegen...** an. Es gibt 20
  Host-Plätze: Wer Turniere ausrichten will, schreibt **wishin** eine DM.
  Mehr in [TOURNAMENTS.md](TOURNAMENTS.md) (auf Englisch).
- **Private Räume und Community-Räume** (ab 1.1.3): **Raum erstellen** fragt,
  wie viele Spieler (2 bis 8) und wer beitreten darf: alle, mit Passwort oder
  mit Einladungscode; der Raum lässt sich auch in der Raumliste verstecken.
  Andere wählen ihn aus und drücken **Raum beitreten** (das fragt nach dem
  Passwort), oder sie geben den Einladungscode bei **Raum beitreten** ein, ohne
  einen Raum auszuwählen. Den Code teilst du mit **Einladungscode kopieren**: Er
  erscheint im Feld neben dem Knopf, dort drückst du Strg+C. In einem Raum für 3
  oder mehr wechselt ihr euch ab, ein Match nach dem anderen, nach **Gewinner
  bleibt** oder **Alle der Reihe nach**; **Aussetzen** überspringt deine Runden.
  Der Gastgeber kann in **Raum-Einstellungen...** das Passwort ändern und einen
  Spieler entfernen. Einen Freund, den du in deinen Raum einlädst, fragt
  niemand nach dem Passwort. Die Matches eines privaten Raums können nur seine
  Spieler zuschauen. Diese Räume sind casual. Mehr in [ONLINE.md](ONLINE.md)
  „Rooms“ (auf Englisch).
- Mehr in [ONLINE.md](ONLINE.md) und [RANKED.md](RANKED.md) (auf Englisch).

### Zuschauen

Ein Freund im Match, das Match eines Raums oder ein Turnier-Set lässt sich live
ansehen: **Zuschauen** auf der Freunde-Seite (unter der Liste), in der Raumliste
oder über dem Turnierbaum (vorher das Set anklicken).
Dein Spiel zeigt das Match ein paar Sekunden später, genau so, wie es gespielt
wird (dieselben Eingaben, beim Abspielen geprüft). Wann immer du dazukommst,
läuft die Session der Spieler von ihrem Anfang an (ein Rematch hängt von den
Matches davor ab). Settings -> Zuschauer: „Freunde und Raumbesucher dürfen meine
Online-Matches ansehen“ (an) und „Auch meine Ranked-Matches“ (aus); ein Match
wird nur angesehen, wenn beide Spieler es erlauben. Die eigenen Kostüme beider
Spieler sehen auch die Zuschauer. Mehr in [SPECTATE.md](SPECTATE.md) (auf Englisch).

### Replays

Jedes Online-Match wird als Replay gespeichert (ein paar KB, in
`native\replays`). Der Reiter **Replays** zeigt sie mit Datum, Kämpfern,
Ergebnis und Gegner; **Ansehen** spielt das Match im Spiel noch einmal ab,
genau so, wie es war: dieselben Eingaben Bild für Bild, während des Abspielens
mit dem Live-Match verglichen (am Ende steht im Reiter "identisch mit dem
Live-Match"). Während es läuft, pausiert **START** (Enter), **SELECT** (Tab)
beendet es. Ein Rematch wird nach den Matches davor in derselben Sitzung
gezeigt (ein Rematch beginnt dort, wo das Match davor aufgehört hat). Im Reiter kannst du die Aufnahme ausschalten oder die Namen der Spieler
weglassen. Ein Replay läuft nur mit der Spielversion, die es aufgenommen hat.
Mehr in [REPLAYS.md](REPLAYS.md) (auf Englisch).

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
- Wenn die neue Version den Spielcode ändert, steht im Reiter Play offline **Build the
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
   der Reiter Play offline. Klicke dann nochmal auf **BUILD GAME**. Nur der Code wird neu
   gebaut.

## Fehler melden

**Probleme? Klicke auf "Report a problem"** (Reiter Play offline; auch im Reiter Build und
im Reiter Play online nach einem Match). Der Launcher macht EINE Zip-Datei auf deinem
Desktop und öffnet den Ordner. Schicke das Zip der Person, die dir das Spiel
gegeben hat, oder hänge es an ein Issue unter
https://github.com/TheWishin/T5DROnline/issues. Im Fenster kannst du ein paar
Worte dazu schreiben, was passiert ist.

Im Zip sind die neuesten Spiel-Logs, `build.log` wenn das Bauen das Problem war,
das Log des Launchers, die Dateien deines letzten Online-Matches, dein neuestes
Replay (nur Eingaben, ohne die Namen der Spieler), deine
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
- **DualShock 4 / DualSense geht nur über Steam**: Ab 1.1.1 liest das Spiel diese
  Pads selbst, auch über Bluetooth, nachdem Steam sie umgeschaltet hat. Bei 1.1.0
  und älter: Pad ausschalten (PS-Taste 10 Sekunden halten) und ohne laufendes
  Steam wieder einschalten, oder ein USB-Kabel nehmen.
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

**Wo sind meine Speicherstände?** In `native\gamedata`. Im Reiter Play offline gibt es den
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
