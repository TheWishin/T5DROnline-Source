"""German texts for the launcher and the Online tab (t5lobby/i18n.py).

English text -> German text. The English text is the key, exactly as written in t("...") / N_("..."); the
German one keeps the same {placeholders}. Written in plain du-form German, like docs/README.de.md; names
players know from the game and the lobby (Quick Match, Ranked, BUILD GAME, Rematch, Lobby, Input-Delay,
Ping) stay as they are. A text whose German is the English word (Start, Online, Tab, ...) is listed too:
tests/test_i18n.py wants an entry for every text, so a missing one cannot hide.

Grouped by the file that uses the text. python tools/i18n_extract.py --skeleton prints entries for new
texts to paste into the right group.
"""

MESSAGES = {
    # ---- launcher/core.py
    "Auto (Windows language)": "Auto (Sprache von Windows)",
    "Deutsch": "Deutsch",
    "English": "English",
    "No package chosen.": "Kein Paket gewählt.",
    "File not found.": "Datei nicht gefunden.",
    "Cannot read the file: {error}": "Die Datei lässt sich nicht lesen: {error}",
    "This is not a PS3 package (.pkg).": "Das ist kein PS3-Paket (.pkg).",
    "{id}  ({size} bytes) -- the supported version": "{id}  ({size} Bytes) -- die unterstützte Version",
    "{id}  ({size} bytes) -- Tekken 5 DR, but not the supported package ({supported}). "
    "The build will most likely refuse it.":
        "{id}  ({size} Bytes) -- Tekken 5 DR, aber nicht das unterstützte Paket "
        "({supported}). Das Bauen wird es wahrscheinlich ablehnen.",
    "{id}  ({size} bytes) -- not Tekken 5 DR Online ({title_id}).":
        "{id}  ({size} Bytes) -- nicht Tekken 5 DR Online ({title_id}).",
    "No license chosen.": "Keine Lizenz gewählt.",
    "Not a PS3 license: a .rap file is exactly 16 bytes.":
        "Das ist keine PS3-Lizenz: Eine .rap-Datei ist genau 16 Bytes groß.",
    "{name} -- matches the supported package": "{name} -- passt zum unterstützten Paket",
    "{name} -- matches the package": "{name} -- passt zum Paket",
    "{name} -- the name does not match the package's content ID; it may be the wrong "
    "license.":
        "{name} -- der Name passt nicht zur Content-ID des Pakets. Vielleicht ist das die "
        "falsche Lizenz.",
    "The output folder": "Der Ausgabeordner",
    "This folder": "Dieser Ordner",
    "{label} has a long path ({bytes} bytes). Windows allows only {max} characters for a "
    "file path, and the build writes files about {room} characters deeper. Move the "
    "folder to a short path, for example {example}.":
        "{label} hat einen langen Pfad ({bytes} Bytes). Windows erlaubt für einen Dateipfad "
        "nur {max} Zeichen, und beim Bauen entstehen Dateien etwa {room} Zeichen tiefer. "
        "Verschiebe den Ordner an einen kurzen Pfad, zum Beispiel {example}.",
    "This folder is inside OneDrive. OneDrive would upload about 1 GB of game data and "
    "can lock files while the game is built. Move the folder out of OneDrive, for "
    "example to {example}.":
        "Dieser Ordner liegt in OneDrive. OneDrive würde etwa 1 GB Spieldaten hochladen und "
        "kann Dateien sperren, während das Spiel gebaut wird. Verschiebe den Ordner aus "
        "OneDrive heraus, zum Beispiel nach {example}.",
    "This folder is in Program Files, where Windows does not let programs write. Move it "
    "to a folder of your own, for example {example}.":
        "Dieser Ordner liegt in Programme (Program Files), wo Windows keine Programme "
        "schreiben lässt. Verschiebe ihn in einen eigenen Ordner, zum Beispiel {example}.",
    "Windows does not let the launcher write into this folder. Move it to a folder of "
    "your own, for example {example}.":
        "Windows lässt den Launcher in diesen Ordner nicht schreiben. Verschiebe ihn in "
        "einen eigenen Ordner, zum Beispiel {example}.",
    "This folder is on a network share. Building and playing from there is slow and was "
    "not tested; copy it to a local drive.":
        "Dieser Ordner liegt auf einer Netzwerkfreigabe. Bauen und Spielen von dort ist "
        "langsam und wurde nicht getestet. Kopiere ihn auf ein lokales Laufwerk.",
    "The game is not built yet. Open the Build tab, choose your .pkg and .rap, press "
    "BUILD GAME.":
        "Das Spiel ist noch nicht gebaut. Öffne den Reiter Bauen, wähle deine .pkg und .rap "
        "und klicke auf BUILD GAME.",
    "t5dr.exe is there but the game data is missing. Build again.":
        "t5dr.exe ist da, aber die Spieldaten fehlen. Baue noch einmal.",
    "The decrypted program has SHA-1 {sha}..., not the supported version. Build again "
    "from the supported package.":
        "Das entschlüsselte Programm hat die SHA-1 {sha}... und ist nicht die unterstützte "
        "Version. Baue noch einmal mit dem unterstützten Paket.",
    "This version of the launcher changes the game code. Build again (your game data is "
    "kept; only the code is translated and compiled again).":
        "Diese Version des Launchers ändert den Spielcode. Baue noch einmal (deine "
        "Spieldaten bleiben erhalten, nur der Code wird neu übersetzt und kompiliert).",
    "Ready: {title_id} v{version}, program SHA-1 {sha}... verified, built {when}.":
        "Bereit: {title_id} v{version}, Programm-SHA-1 {sha}... geprüft, gebaut {when}.",
    "Check & decrypt": "Prüfen & entschlüsseln",
    "Key data": "Schlüsseldaten",
    "Recompiler": "Recompiler",
    "Unpack": "Entpacken",
    "Compile": "Kompilieren",
    "Game files": "Spieldateien",
    "Sound core": "Soundkern",
    "Translate code": "Code übersetzen",
    "The graphics card stopped working for the game (the driver crashed, was reset or "
    "updated). Start the game again. If it happens again, update the graphics driver.":
        "Die Grafikkarte hat für das Spiel nicht mehr funktioniert (der Treiber ist "
        "abgestürzt, wurde zurückgesetzt oder aktualisiert). Starte das Spiel noch einmal. "
        "Passiert es wieder, aktualisiere den Grafiktreiber.",
    "This PC's graphics card or driver cannot run Direct3D 12. Install the newest "
    "graphics driver from AMD, Intel or NVIDIA.":
        "Die Grafikkarte oder der Treiber dieses PCs kann Direct3D 12 nicht. Installiere den "
        "neuesten Grafiktreiber von AMD, Intel oder NVIDIA.",
    "This processor is too old for the game: it lacks the SSE4.1 instructions "
    "(processors from about 2008 on have them).":
        "Dieser Prozessor ist zu alt für das Spiel: Ihm fehlen die SSE4.1-Befehle "
        "(Prozessoren ab etwa 2008 haben sie).",
    "The game was built on a PC with a newer processor (AVX2). Press BUILD GAME to build "
    "it again for this PC; your saves are kept.":
        "Das Spiel wurde auf einem PC mit einem neueren Prozessor (AVX2) gebaut. Klicke auf "
        "BUILD GAME, um es für diesen PC neu zu bauen. Deine Spielstände bleiben erhalten.",
    "t5dr_game.dll could not be loaded (missing or blocked). Press BUILD GAME again, and "
    "look in the antivirus quarantine.":
        "t5dr_game.dll konnte nicht geladen werden (fehlt oder ist blockiert). Klicke noch "
        "einmal auf BUILD GAME und sieh in der Quarantäne deines Virenscanners nach.",
    "The game could not get back to character select after the last match and closed "
    "itself. It starts again for your next match.":
        "Das Spiel kam nach dem letzten Match nicht zurück zur Charakterwahl und hat sich "
        "selbst beendet. Es startet für dein nächstes Match wieder.",
    "The game stopped after a crash (exit code {code}). The game log has the details.":
        "Das Spiel wurde nach einem Absturz beendet (Exit-Code {code}). Das Spiel-Log hat "
        "die Details.",
    "The game stopped (exit code {code}). The game log has the details.":
        "Das Spiel wurde beendet (Exit-Code {code}). Das Spiel-Log hat die Details.",
    "t5dr.exe is not built yet": "t5dr.exe ist noch nicht gebaut",
    "Original": "Original",
    "Lower": "Niedriger",
    "Lowest": "Am niedrigsten",
    "Auto (by ping)": "Auto (nach Ping)",
    "Window, 1280 x 720 (native; larger with Windows display scaling)":
        "Fenster, 1280 x 720 (nativ; größer mit der Windows-Skalierung)",
    "Window, 1920 x 1080": "Fenster, 1920 x 1080",
    "Window, 2560 x 1440": "Fenster, 2560 x 1440",
    "Maximized window": "Maximiertes Fenster",
    "Borderless fullscreen (experimental)": "Randloses Vollbild (experimentell)",
    # ---- launcher/online.py
    "Online play": "Online spielen",
    "The lobby files (lobby/t5lobby) are missing from this copy of the launcher, so "
    "online play is not available.\n\n({reason})":
        "Die Lobby-Dateien (lobby/t5lobby) fehlen in dieser Kopie des Launchers, darum ist "
        "Online-Spiel nicht möglich.\n\n({reason})",
    # ---- launcher/t5dr_launcher.pyw
    "A": "A",
    "Left punch (1)": "Linker Schlag (1)",
    "Square": "Quadrat",
    "X": "X",
    "Right punch (2)": "Rechter Schlag (2)",
    "S": "S",
    "Triangle": "Dreieck",
    "Y": "Y",
    "Cross": "Kreuz",
    "Left kick (3)": "Linker Tritt (3)",
    "Z": "Z",
    "B": "B",
    "Circle": "Kreis",
    "Right kick (4)": "Rechter Tritt (4)",
    "Arrow keys": "Pfeiltasten",
    "D-pad, left stick": "Steuerkreuz, linker Stick",
    "Move / menus": "Bewegen, Menüs",
    "L1 / R1": "L1 / R1",
    "LB / RB": "LB / RB",
    "Q / W": "Q / W",
    "1 / 2": "1 / 2",
    "L2 / R2": "L2 / R2",
    "LT / RT": "LT / RT",
    "Enter": "Enter",
    "START": "START",
    "Start": "Start",
    "Start / pause": "Start / Pause",
    "Back": "Back",
    "SELECT": "SELECT",
    "Select": "Select",
    "Tab": "Tab",
    "Esc": "Esc",
    "Quit the game": "Spiel beenden",
    "A / B": "A / B",
    "Cross / Circle": "Kreuz / Kreis",
    "Mouse": "Maus",
    "Online tab: accept / decline": "Online-Reiter: annehmen / ablehnen",
    "native Windows build  ·  launcher {version}": "native Windows-Version  ·  Launcher {version}",
    "Build": "Bauen",
    "Play": "Spielen",
    "Settings": "Einstellungen",
    "Online": "Online",
    "Output: {folder}": "Ausgabe: {folder}",
    "Your game": "Dein Spiel",
    "Package (.pkg)": "Paket (.pkg)",
    "License (.rap)": "Lizenz (.rap)",
    "Browse…": "Durchsuchen…",
    "Supported: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version "
    "01.00 -- the package file and the license (.rap) from your own account. Nothing "
    "leaves this PC.":
        "Unterstützt wird: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 "
        "Version 01.00 -- die Paketdatei und die Lizenz (.rap) aus deinem eigenen Konto. "
        "Nichts verlässt diesen PC.",
    "Build tools on this PC": "Build-Tools auf diesem PC",
    "Needed": "Nötig",
    "Found": "Gefunden",
    "Checking…": "Prüfe…",
    "Details": "Details",
    "Check again": "Noch einmal prüfen",
    "Install missing…": "Fehlendes installieren…",
    "Press BUILD GAME. It takes a few minutes; the game data stays in this folder.":
        "Klicke auf BUILD GAME. Das dauert ein paar Minuten. Die Spieldaten bleiben in "
        "diesem Ordner.",
    "BUILD GAME": "BUILD GAME",
    "Cancel": "Abbrechen",
    "Redo every step": "Alle Schritte neu machen",
    "Keep the PC responsive (slower)": "PC bedienbar halten (langsamer)",
    "Open build.log": "build.log öffnen",
    "Checking the build…": "Prüfe den Build…",
    "Your name (shown in the game)": "Dein Name (im Spiel sichtbar)",
    "PLAY": "PLAY",
    "Stop game": "Spiel stoppen",
    "Open newest game log": "Neuestes Spiel-Log öffnen",
    "Open saves folder": "Speicherordner öffnen",
    "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers "
    "both work; see Settings for the keys. Esc closes the game. START skips the intro "
    "movie.":
        "Das Spiel öffnet ein eigenes Fenster (DirectX 12). Tastatur und Xbox-Controller "
        "funktionieren beide; die Tasten stehen unter Einstellungen. Esc beendet das Spiel. "
        "START überspringt das Intro-Video.",
    "Display": "Anzeige",
    "The game renders at 1280 x 720 and is scaled to the window. You can also drag the "
    "window's edges. The runtime has no exclusive fullscreen yet.":
        "Das Spiel rendert in 1280 x 720 und wird auf das Fenster skaliert. Du kannst auch "
        "an den Rändern des Fensters ziehen. Exklusives Vollbild gibt es noch nicht.",
    "Sound and start": "Ton und Start",
    "Mute sound": "Ton aus",
    "Start minimized, without taking focus (for testing)": "Minimiert starten, ohne den Fokus zu nehmen (zum Testen)",
    "Advanced: extra settings, one NAME=VALUE per line":
        "Erweitert: zusätzliche Einstellungen, eine pro Zeile als NAME=WERT",
    "3D resolution": "3D-Auflösung",
    "for weak graphics cards": "für schwache Grafikkarten",
    "Online input delay": "Online-Input-Delay",
    "Frames. Auto: 1 up to about 60 ms ping, 2 above. 0/1/2 count only when your "
    "opponent picked the same, otherwise Auto. Ranked matches always use 2.":
        "Frames. Auto: 1 bis etwa 60 ms Ping, darüber 2. 0/1/2 gelten nur, wenn dein Gegner "
        "dasselbe gewählt hat, sonst Auto. Ranked-Matches nutzen immer 2.",
    "Controls": "Steuerung",
    "Action (Tekken default)": "Aktion (Tekken-Standard)",
    "PS3 button": "PS3-Taste",
    "Keyboard": "Tastatur",
    "Xbox controller": "Xbox-Controller",
    "Keyboard and the first XInput controller both drive player 1 (they are combined). "
    "The keyboard only counts while the game window has focus. Button layout inside the "
    "game can be changed in its own Options menu.":
        "Tastatur und der erste XInput-Controller steuern beide Spieler 1 (sie werden "
        "zusammengelegt). Die Tastatur gilt nur, solange das Spielfenster den Fokus hat. Die "
        "Tastenbelegung im Spiel änderst du im Options-Menü des Spiels.",
    "In this window, on the Online tab, a controller or arcade stick works without mouse "
    "or keyboard: Cross / A accepts a match or rematch and starts a search, Circle / B "
    "declines, leaves or stops the search. It only counts while this window is in front, "
    "and only after the button was let go for a moment. Which stick button is Cross "
    "follows your controls.ini.":
        "In diesem Fenster geht der Online-Reiter auch mit Controller oder Arcade-Stick, "
        "ohne Maus und Tastatur: Kreuz / A nimmt ein Match oder Rematch an und startet eine "
        "Suche, Kreis / B lehnt ab, verlässt oder beendet die Suche. Das gilt nur, solange "
        "dieses Fenster vorne ist, und erst, nachdem du den Knopf kurz losgelassen hast. "
        "Welcher Stick-Knopf Kreuz ist, richtet sich nach deiner controls.ini.",
    "Language": "Sprache",
    "Restart now": "Jetzt neu starten",
    "The language changes when the launcher starts again.": "Die Sprache ändert sich, wenn der Launcher neu startet.",
    "A build is running. Stop it first, or restart the launcher by hand when it is done.":
        "Das Bauen läuft noch. Brich es zuerst ab, oder starte den Launcher selbst neu, wenn "
        "es fertig ist.",
    "Close the game first.": "Schließe zuerst das Spiel.",
    "Choose your Tekken 5 DR Online package": "Wähle dein Paket für Tekken 5 DR Online",
    "All files": "Alle Dateien",
    "PS3 package": "PS3-Paket",
    "Choose your license (.rap)": "Wähle deine Lizenz (.rap)",
    "PS3 license": "PS3-Lizenz",
    "Checking build tools…": "Prüfe die Build-Tools…",
    "missing": "fehlt",
    "ok": "ok",
    "Missing: {names}": "Es fehlt: {names}",
    "Everything the build needs is installed.": "Alles, was das Bauen braucht, ist installiert.",
    "All build tools found.": "Alle Build-Tools gefunden.",
    "{count} build tool(s) missing -- click 'Install missing…'.":
        "{count} Build-Tool(s) fehlen -- klicke auf „Fehlendes installieren…“.",
    "Hide details": "Details ausblenden",
    "Microsoft Visual Studio 2022 Build Tools: the C++ compiler parts only (MSVC x64, "
    "Windows SDK, CMake, Clang). Download about 2.5 GB, about 7 GB on disk, 10-20 "
    "minutes. You accept Microsoft's license terms for the Build Tools "
    "(visualstudio.microsoft.com/license-terms).":
        "Microsoft Visual Studio 2022 Build Tools: nur die C++-Compiler-Teile (MSVC x64, "
        "Windows SDK, CMake, Clang). Download etwa 2,5 GB, etwa 7 GB auf der Festplatte, "
        "10-20 Minuten. Du akzeptierst Microsofts Lizenzbedingungen für die Build Tools "
        "(visualstudio.microsoft.com/license-terms).",
    "Git for Windows (about 70 MB download).": "Git für Windows (etwa 70 MB Download).",
    "Install build tools": "Build-Tools installieren",
    "The build needs these free tools from their makers, installed with Windows' own "
    "installer (winget):\n\n{tools}\n\nWindows will ask for administrator permission. A "
    "console window shows the progress.\n\nInstall now?":
        "Das Bauen braucht diese kostenlosen Tools von ihren Herstellern. Sie werden mit dem "
        "Installer von Windows (winget) installiert:\n\n{tools}\n\nWindows fragt nach "
        "Administratorrechten. Ein Konsolenfenster zeigt den Fortschritt.\n\nJetzt "
        "installieren?",
    "Could not start the installer:\n{error}\n\nIs winget (App Installer) available? On "
    "Windows 10 install 'App Installer' from the Microsoft Store.":
        "Der Installer konnte nicht gestartet werden:\n{error}\n\nIst winget (App-Installer) "
        "vorhanden? Unter Windows 10 installierst du den „App-Installer“ aus dem Microsoft "
        "Store.",
    "Install failed": "Installation fehlgeschlagen",
    "Installer running in its own window…": "Der Installer läuft in einem eigenen Fenster…",
    "Could not start the build: {error}": "Das Bauen konnte nicht gestartet werden: {error}",
    "Building…": "Baue…",
    "Step {n} of {total}: {title}  —  {elapsed}": "Schritt {n} von {total}: {title}  —  {elapsed}",
    "Done in {elapsed}. Open the Play tab.": "Fertig in {elapsed}. Öffne den Reiter Spielen.",
    "Build finished.": "Bauen abgeschlossen.",
    "Cancelled. BUILD GAME continues where it stopped.":
        "Abgebrochen. BUILD GAME macht dort weiter, wo es aufgehört hat.",
    "The build stopped. The message below says why; build.log has the details.":
        "Das Bauen wurde gestoppt. Die Meldung unten sagt warum; build.log hat die Details.",
    "The build failed. See the log above and build.log.":
        "Das Bauen ist fehlgeschlagen. Sieh ins Log oben und in build.log.",
    "Build stopped.": "Bauen gestoppt.",
    "Could not start the game:\n{error}": "Das Spiel konnte nicht gestartet werden:\n{error}",
    "Game started (process {pid}). Log: {log}": "Spiel gestartet (Prozess {pid}). Log: {log}",
    "starting…": "startet…",
    "Running — {elapsed} — {fps}": "Läuft — {elapsed} — {fps}",
    "The game closed.": "Das Spiel wurde geschlossen.",
    "A build is running. Stop it and quit?": "Das Bauen läuft noch. Stoppen und beenden?",
    # ---- lobby/t5lobby/client.py
    "Contacting the lobby server over UDP...": "Verbinde mit dem Lobby-Server über UDP...",
    "UDP to the lobby server is blocked (firewall?)": "UDP zum Lobby-Server ist blockiert (Firewall?)",
    "Connecting to your opponent...": "Verbinde mit deinem Gegner...",
    "Measuring the connection...": "Messe die Verbindung...",
    "Direct connection not possible; using the lobby server's relay...":
        "Direkte Verbindung nicht möglich; nutze das Relay des Lobby-Servers...",
    # ---- lobby/t5lobby/dialogs.py
    "No": "Nein",
    "Yes": "Ja",
    "OK": "OK",
    # ---- lobby/t5lobby/fighters.py
    "Random": "Zufall",
    # ---- lobby/t5lobby/handover.py
    "direct connection": "direkte Verbindung",
    "local network": "lokales Netzwerk",
    "through the lobby server": "über den Lobby-Server",
    "{name} -- {how}, ping {ms} ms, input delay {delay}": "{name} -- {how}, Ping {ms} ms, Input-Delay {delay}",
    # ---- lobby/t5lobby/i18n_known.py
    "login timeout": "Zeitlimit beim Anmelden",
    "idle timeout": "Zeitlimit: zu lange nichts getan",
    "banned from this server": "von diesem Server gesperrt",
    "too many connections": "zu viele Verbindungen",
    "server full": "Server voll",
    "slow down": "Nicht so schnell",
    "flooding: disconnected": "zu viele Nachrichten: Verbindung getrennt",
    "this server speaks lobby protocol {version}; update the launcher":
        "Dieser Server nutzt das Lobby-Protokoll {version}; aktualisiere den Launcher",
    "build {build} is not accepted by this server; update the launcher and rebuild the "
    "game":
        "Dieser Server akzeptiert den Build {build} nicht; aktualisiere den Launcher und "
        "baue das Spiel neu",
    "already logged in": "schon angemeldet",
    "this server has no accounts": "Dieser Server hat keine Konten",
    "this server has no guest logins": "Dieser Server erlaubt keine Gäste",
    "too many failed logins; wait a few minutes": "zu viele fehlgeschlagene Anmeldungen; warte ein paar Minuten",
    "too many failed attempts; wait a few minutes": "zu viele fehlgeschlagene Versuche; warte ein paar Minuten",
    "too many new accounts from this address": "zu viele neue Konten von dieser Adresse",
    "the saved login has expired; log in with your password":
        "Die gespeicherte Anmeldung ist abgelaufen; melde dich mit deinem Passwort an",
    "session expired; log in again": "Sitzung abgelaufen; melde dich neu an",
    "names are 2-16 letters, digits, spaces or _-.[]()!?":
        "Namen haben 2-16 Zeichen: Buchstaben, Ziffern, Leerzeichen oder _-.[]()!?",
    "that name is reserved": "Dieser Name ist reserviert",
    "that name is not allowed here": "Dieser Name ist hier nicht erlaubt",
    "that name belongs to an account": "Dieser Name gehört zu einem Konto",
    "that name is taken": "Dieser Name ist schon vergeben",
    "someone with that name is online": "Jemand mit diesem Namen ist online",
    "wrong name or password": "Name oder Passwort falsch",
    "wrong password": "Passwort falsch",
    "the current password is wrong": "Das aktuelle Passwort ist falsch",
    "passwords are 6-128 characters": "Passwörter haben 6-128 Zeichen",
    "guests have no password": "Gäste haben kein Passwort",
    "guests have no account": "Gäste haben kein Konto",
    "wrong name or recovery code (each code works once)":
        "Name oder Wiederherstellungs-Code falsch (jeder Code gilt nur einmal)",
    "logged in from another place": "an einem anderen Ort angemeldet",
    "this account is banned for good": "Dieses Konto ist für immer gesperrt",
    "this account is banned for good: {reason}": "Dieses Konto ist für immer gesperrt: {reason}",
    "this account is banned until {time}": "Dieses Konto ist bis {time} gesperrt",
    "this account is banned until {time}: {reason}": "Dieses Konto ist bis {time} gesperrt: {reason}",
    "you are {status}": "Das geht gerade nicht (Status: {status})",
    "ranked needs an account": "Ranked braucht ein Konto",
    "ranked matches come from the ranked queue on this server":
        "Ranked-Matches kommen auf diesem Server aus der Ranked-Suche",
    "your character is locked until this ranked set ends":
        "Dein Charakter ist gesperrt, bis dieses Ranked-Set vorbei ist",
    "finish your running match with the same game build first":
        "Beende zuerst dein laufendes Match mit demselben Spiel-Build",
    "this PC ran its last match at {fps} fps; ranked needs at least {min_fps} (both "
    "games run at the slower PC's speed). Close other programs or lower the resolution "
    "scale, then play a casual match to measure again":
        "Dieser PC hat sein letztes Match mit {fps} fps gespielt; Ranked braucht mindestens "
        "{min_fps} (beide Spiele laufen mit der Geschwindigkeit des langsameren PCs). "
        "Schließe andere Programme oder senke die 3D-Auflösung und spiele dann ein "
        "Casual-Match, um neu zu messen",
    "chat: slow down": "Chat: nicht so schnell",
    "history is kept for accounts only": "Der Verlauf wird nur für Konten gespeichert",
    "no such player": "Diesen Spieler gibt es nicht",
    "no such room": "Diesen Raum gibt es nicht",
    "room is full": "Der Raum ist voll",
    "you cannot join this room": "Du kannst diesem Raum nicht beitreten",
    "not in a room": "Du bist in keinem Raum",
    "no opponent in the room": "Kein Gegner im Raum",
    "that player runs a different build of the game": "Dieser Spieler hat einen anderen Build des Spiels",
    "finish the match first": "Beende zuerst das Match",
    "finish or leave the running match first": "Beende oder verlasse zuerst das laufende Match",
    "that match is over; find a new opponent": "Dieses Match ist vorbei; suche einen neuen Gegner",
    "your opponent is no longer available": "Dein Gegner ist nicht mehr da",
    "that player is not available": "Dieser Spieler ist nicht verfügbar",
    "busy": "beschäftigt",
    "one challenge at a time": "Immer nur eine Herausforderung",
    "that player has challenges pending": "Dieser Spieler hat noch offene Herausforderungen",
    "no such challenge": "Diese Herausforderung gibt es nicht",
    "challenge no longer possible": "Die Herausforderung ist nicht mehr möglich",
    "no such match": "Dieses Match gibt es nicht",
    "match is {state}": "Das Match ist {state}",
    "you cannot block yourself": "Du kannst dich nicht selbst blockieren",
    "the block list is full ({max})": "Die Blockliste ist voll ({max})",
    "that player is not on your block list": "Dieser Spieler steht nicht auf deiner Blockliste",
    "you are not in a set": "Du bist in keinem Set",
    "no such finished match": "Dieses beendete Match gibt es nicht",
    "{name} is back in the lobby": "{name} ist zurück in der Lobby",
    "{name} lost the lobby connection; waiting {seconds} s for them to return":
        "{name} hat die Verbindung zur Lobby verloren; warte {seconds} s auf die Rückkehr",
    "your PC ran its last match at {fps} fps": "dein PC hat sein letztes Match mit {fps} fps gespielt",
    "your opponent's PC ran its last match at {fps} fps":
        "der PC deines Gegners hat sein letztes Match mit {fps} fps gespielt",
    "{name}'s PC ran its last match at {fps} fps": "der PC von {name} hat sein letztes Match mit {fps} fps gespielt",
    "{parts} -- this match runs at the slower PC's speed":
        "{parts} -- dieses Match läuft mit der Geschwindigkeit des langsameren PCs",
    "you two played {count} ranked matches in the last 24 hours; this one is unranked "
    "(limit {max})":
        "Ihr habt in den letzten 24 Stunden {count} Ranked-Matches gegeneinander gespielt; "
        "dieses zählt nicht für Ranked (Limit {max})",
    "your PC's UDP packets did not reach the lobby server; check the firewall":
        "Die UDP-Pakete deines PCs kommen nicht beim Lobby-Server an; prüfe die Firewall",
    "your opponent reported the result; please report yours":
        "Dein Gegner hat das Ergebnis gemeldet; melde bitte auch deins",
    "opponent runs a different build": "Der Gegner hat einen anderen Build",
    "not connected to the lobby": "nicht mit der Lobby verbunden",
    "the lobby server did not answer": "Der Lobby-Server hat nicht geantwortet",
    "no answer to {type}": "Keine Antwort auf {type}",
    "cannot reach {host}:{port} ({error})": "{host}:{port} ist nicht erreichbar ({error})",
    "the server's certificate does not match the pinned one":
        "Das Zertifikat des Servers passt nicht zum festgelegten",
    "this server has no encryption (TLS): a password would cross the internet readable. "
    "Play as a guest, or ask the server's host to set up TLS and give you its "
    "fingerprint.":
        "Dieser Server hat keine Verschlüsselung (TLS): Ein Passwort würde lesbar durchs "
        "Internet gehen. Spiele als Gast, oder bitte den Betreiber des Servers, TLS "
        "einzurichten und dir den Fingerabdruck zu geben.",
    "connection closed": "Verbindung geschlossen",
    "message too long": "Nachricht zu lang",
    "closed": "geschlossen",
    "Choose your game package (.pkg) first.": "Wähle zuerst dein Spielpaket (.pkg).",
    "The package file does not exist: {file}": "Die Paketdatei gibt es nicht: {file}",
    "{file} is not a PS3 package (.pkg).": "{file} ist kein PS3-Paket (.pkg).",
    "Choose your license file (.rap) first.": "Wähle zuerst deine Lizenzdatei (.rap).",
    "{file} is not a PS3 license: a .rap file is exactly 16 bytes.":
        "{file} ist keine PS3-Lizenz: Eine .rap-Datei ist genau 16 Bytes groß.",
    "This package has no USRDIR/EBOOT.BIN -- it is not a game package (an add-on or "
    "theme?). The port needs {game}.":
        "Dieses Paket enthält keine USRDIR/EBOOT.BIN -- es ist kein Spielpaket (ein Add-on "
        "oder Theme?). Die Portierung braucht {game}.",
    "This package is \"{title}\" ({id}). The port needs {game}.":
        "Dieses Paket ist „{title}“ ({id}). Die Portierung braucht {game}.",
    "This copy is a different version of the game: \"{title}\" version {version}, content "
    "ID {id} (program SHA-1 {sha}...). The port supports only {game}, content ID "
    "{supported}.":
        "Diese Kopie ist eine andere Version des Spiels: „{title}“ Version {version}, "
        "Content-ID {id} (Programm-SHA-1 {sha}...). Die Portierung unterstützt nur {game}, "
        "Content-ID {supported}.",
    "The license (.rap) does not belong to this package. Use the .rap whose name matches "
    "the package's content ID ({id}).":
        "Die Lizenz (.rap) gehört nicht zu diesem Paket. Nimm die .rap, deren Name zur "
        "Content-ID des Pakets passt ({id}).",
    "Decrypting the game program failed (see the log above). Is the package complete? "
    "Its size should be 619,430,240 bytes.":
        "Das Entschlüsseln des Spielprogramms ist fehlgeschlagen (siehe Log oben). Ist das "
        "Paket vollständig? Es sollte 619.430.240 Bytes groß sein.",
    "The ps3recomp copy in this folder does not match this version of the port. Download "
    "the release again and extract it into an empty folder.":
        "Die ps3recomp-Kopie in diesem Ordner passt nicht zu dieser Version der Portierung. "
        "Lade das Release noch einmal herunter und entpacke es in einen leeren Ordner.",
    "Git is needed to download ps3recomp (the recompiler). Install Git, or use a release "
    "zip, which already contains it.":
        "Git wird gebraucht, um ps3recomp (den Recompiler) herunterzuladen. Installiere Git, "
        "oder nimm eine Release-Zip, die ihn schon enthält.",
    "This package's Python is missing pycryptodome. Download the release again.":
        "Im Python dieses Pakets fehlt pycryptodome. Lade das Release noch einmal herunter.",
    "Could not download the public PS3 key data from github.com (needed once, a few KB). "
    "Check the internet connection and press BUILD GAME again.":
        "Die öffentlichen PS3-Schlüsseldaten konnten nicht von github.com geladen werden "
        "(einmalig nötig, ein paar KB). Prüfe die Internetverbindung und klicke noch einmal "
        "auf BUILD GAME.",
    "The C++ build tools (Visual Studio 2022 Build Tools, x64 C++ toolset) are not "
    "installed. Open the launcher's Build tab and click Install next to them.":
        "Die C++-Build-Tools (Visual Studio 2022 Build Tools, x64-C++-Toolset) sind nicht "
        "installiert. Öffne im Launcher den Reiter Bauen und klicke auf „Fehlendes "
        "installieren…“.",
    "clang-cl.exe and lld-link.exe were not found in toolchain\\llvm\\bin. Download the "
    "release again.":
        "clang-cl.exe und lld-link.exe wurden in toolchain\\llvm\\bin nicht gefunden. Lade das "
        "Release noch einmal herunter.",
    "The Windows SDK is missing (needed for Direct3D 12). Install it with the C++ build "
    "tools.":
        "Das Windows SDK fehlt (für Direct3D 12 nötig). Installiere es mit den "
        "C++-Build-Tools.",
    "clang-cl (LLVM 16 or newer) was not found. Install LLVM or the Visual Studio "
    "component 'C++ Clang tools for Windows'.":
        "clang-cl (LLVM 16 oder neuer) wurde nicht gefunden. Installiere LLVM oder die "
        "Visual-Studio-Komponente „C++ Clang tools for Windows“.",
    "CMake and Ninja were not found. Install the Visual Studio component 'C++ CMake "
    "tools for Windows'.":
        "CMake und Ninja wurden nicht gefunden. Installiere die Visual-Studio-Komponente "
        "„C++ CMake tools for Windows“.",
    "expected 1 SPU image, found {count}": "1 SPU-Image erwartet, {count} gefunden",
    "step '{step}' failed: a tool exited with code {code} -- the lines above say why.":
        "Schritt „{step}“ ist fehlgeschlagen: Ein Tool endete mit Code {code} -- die Zeilen "
        "darüber sagen warum.",
    "cancelled": "abgebrochen",
    "step '{step}' could not read or write a file: {reason} ({file}). The folder path is "
    "too long for Windows: move the folder to a short path such as C:\\Games\\T5DR.":
        "Schritt „{step}“ konnte keine Datei lesen oder schreiben: {reason} ({file}). Der "
        "Ordnerpfad ist für Windows zu lang: Verschiebe den Ordner an einen kurzen Pfad wie "
        "C:\\Games\\T5DR.",
    "step '{step}' could not read or write a file: {reason} ({file}). Is the disk full, "
    "or does another program (antivirus, OneDrive) hold the file?":
        "Schritt „{step}“ konnte keine Datei lesen oder schreiben: {reason} ({file}). Ist "
        "die Festplatte voll, oder hält ein anderes Programm (Virenscanner, OneDrive) die "
        "Datei fest?",
    "Python 3.10+": "Python 3.10+",
    "pycryptodome (Python AES)": "pycryptodome (Python AES)",
    "ps3recomp source": "ps3recomp-Quellcode",
    "Game runtime (t5dr.exe)": "Spiel-Runtime (t5dr.exe)",
    "clang-cl + lld-link": "clang-cl + lld-link",
    "C++ build tools (MSVC x64)": "C++-Build-Tools (MSVC x64)",
    "Windows SDK (Direct3D 12)": "Windows SDK (Direct3D 12)",
    "clang-cl 16+ (LLVM)": "clang-cl 16+ (LLVM)",
    "CMake + Ninja": "CMake + Ninja",
    "{version} at {path}": "{version} in {path}",
    "installed": "installiert",
    "missing -- pip install pycryptodome": "fehlt -- pip install pycryptodome",
    "included in this package": "im Paket enthalten",
    "git checkout in deps/": "Git-Checkout in deps/",
    "not present -- will be downloaded with Git": "nicht da -- wird mit Git heruntergeladen",
    "not present and Git is missing": "nicht da, und Git fehlt",
    "precompiled, included in this package": "vorkompiliert, im Paket enthalten",
    "missing from toolchain\\llvm -- download the release again":
        "fehlt in toolchain\\llvm -- lade das Release noch einmal herunter",
    "not found": "nicht gefunden",
    "missing {tools}": "fehlt: {tools}",
    "idle": "frei",
    "room": "im Raum",
    "queue": "in der Suche",
    "match": "im Match",
    "playing": "im Spiel",
    # ---- lobby/t5lobby/lag.py
    "Ping {ping} ms should mean about {frames} frames behind.":
        "Bei {ping} ms Ping sind etwa {frames} Frames Rückstand normal.",
    "The games did not report how it went, so there is nothing to compare.":
        "Die Spiele haben nicht gemeldet, wie es lief, darum gibt es nichts zu vergleichen.",
    "It was {observed}.": "Es waren {observed}.",
    "That is what the ping explains.": "Das erklärt der Ping.",
    "That is more than the ping explains.": "Das ist mehr, als der Ping erklärt.",
    "Both PCs ran below full speed.": "Beide PCs liefen unter voller Geschwindigkeit.",
    "Your PC was the slow one ({fps} fps).": "Dein PC war der langsame ({fps} fps).",
    "Your PC was the slow one.": "Dein PC war der langsame.",
    "Your opponent's PC was the slow one ({fps} fps).": "Der PC deines Gegners war der langsame ({fps} fps).",
    "Your opponent's PC was the slow one.": "Der PC deines Gegners war der langsame.",
    "Both PCs kept up, so the connection stalled now and then (jitter or lost packets).":
        "Beide PCs kamen mit, die Verbindung hat also zwischendurch gestockt (Jitter oder "
        "verlorene Pakete).",
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "Dein Gegner hat das Spiel geschlossen.",
    "The connection to your opponent's game was lost.": "Die Verbindung zum Spiel deines Gegners ist abgebrochen.",
    "Your opponent's game stopped responding.": "Das Spiel deines Gegners reagiert nicht mehr.",
    "Your opponent's game did not get to the fight.": "Das Spiel deines Gegners hat es nicht bis zum Kampf geschafft.",
    "Your opponent's game was restarted; the match cannot go on.":
        "Das Spiel deines Gegners wurde neu gestartet; das Match kann nicht weitergehen.",
    "Your opponent's game could not be reached (firewall or router?).":
        "Das Spiel deines Gegners war nicht erreichbar (Firewall oder Router?).",
    "Your opponent's game is a different build.": "Das Spiel deines Gegners ist ein anderer Build.",
    "Your opponent's game is in another match.": "Das Spiel deines Gegners ist in einem anderen Match.",
    "The game could not open its network port (another program uses it?).":
        "Das Spiel konnte seinen Netzwerk-Port nicht öffnen (nutzt ihn ein anderes "
        "Programm?).",
    "You closed the game during the match: it counts as a loss.":
        "Du hast das Spiel während des Matches geschlossen: Das zählt als Niederlage.",
    "Your opponent does not want a rematch.": "Dein Gegner will kein Rematch.",
    "The game is not running any more; leaving the rematch.":
        "Das Spiel läuft nicht mehr; das Rematch wird verlassen.",
    "Rematch against {name}: same connection, the game stays open.":
        "Rematch gegen {name}: dieselbe Verbindung, das Spiel bleibt offen.",
    "The game could not start; leaving the match.": "Das Spiel konnte nicht starten; das Match wird verlassen.",
    "Playing against {summary}": "Du spielst gegen {summary}",
    "The game did not answer its control channel; it is restarted for every opponent "
    "from now on.":
        "Das Spiel hat auf seinem Steuerkanal nicht geantwortet; ab jetzt wird es für jeden "
        "Gegner neu gestartet.",
    "Character select...": "Charakterwahl...",
    "The game is starting...": "Das Spiel startet...",
    "Fight!": "Fight!",
    "Loading the fight...": "Lade den Kampf...",
    "Stage select...": "Stage-Wahl...",
    "At character select, waiting for the next match.": "In der Charakterwahl, warte auf das nächste Match.",
    "Match over.": "Match vorbei.",
    "Ignored a result the game wrote for an earlier match.":
        "Ein Ergebnis, das das Spiel für ein früheres Match geschrieben hat, wurde "
        "ignoriert.",
    "The match could not be finished ({reason}).": "Das Match konnte nicht beendet werden ({reason}).",
    "The match could not be played ({reason}).": "Das Match konnte nicht gespielt werden ({reason}).",
    "The game stopped unexpectedly; the match does not count (repeated crashes do).":
        "Das Spiel wurde unerwartet beendet; das Match zählt nicht (wiederholte Abstürze "
        "schon).",
    "Result sent (the games went out of sync on {frames} frames); waiting for the "
    "lobby...":
        "Ergebnis gesendet (die Spiele waren in {frames} Frames nicht mehr synchron); warte "
        "auf die Lobby...",
    "Result sent; waiting for the lobby...": "Ergebnis gesendet; warte auf die Lobby...",
    "Lobby: {message}": "Lobby: {message}",
    # ---- lobby/t5lobby/padnav.py
    "(+{count} more)": "(+{count} weitere)",
    # ---- lobby/t5lobby/ranks.py
    "{rank} (placement {done}/{total})": "{rank} (Platzierung {done}/{total})",
    # ---- lobby/t5lobby/tk_tab.py
    "in a room": "in einem Raum",
    "in lobby": "in der Lobby",
    "matching": "im Match-Aufbau",
    "searching": "sucht",
    "full": "voll",
    "open": "offen",
    "Result confirmed": "Ergebnis bestätigt",
    "Result recorded (your opponent did not report)": "Ergebnis gespeichert (dein Gegner hat nichts gemeldet)",
    "Match decided by forfeit": "Match durch Aufgabe entschieden",
    "Result decided by the games' state": "Ergebnis nach dem Stand der Spiele entschieden",
    "You and your opponent reported different results -- not counted":
        "Du und dein Gegner habt verschiedene Ergebnisse gemeldet -- zählt nicht",
    "No result": "Kein Ergebnis",
    "confirmed": "bestätigt",
    "forfeit": "Aufgabe",
    "one-sided": "einseitig",
    "disputed": "strittig",
    "resolved": "entschieden",
    "void": "ungültig",
    "draw": "Remis",
    "loss": "Niederlage",
    "win": "Sieg",
    "the two games went out of sync": "die beiden Spiele waren nicht mehr synchron",
    "too short to count": "zu kurz zum Zählen",
    "a game crashed": "ein Spiel ist abgestürzt",
    "the reports disagreed": "die Meldungen passten nicht zusammen",
    "left right away": "sofort verlassen",
    "a player left": "ein Spieler ist gegangen",
    "a player lost the connection": "ein Spieler hat die Verbindung verloren",
    "a player did not report": "ein Spieler hat nichts gemeldet",
    "the connection between the games failed": "die Verbindung zwischen den Spielen ist ausgefallen",
    "both players left": "beide Spieler sind gegangen",
    "no result in time": "kein Ergebnis rechtzeitig",
    "repeated crashes count as losses": "wiederholte Abstürze zählen als Niederlagen",
    "repeated early quits": "wiederholtes frühes Beenden",
    "repeated missing reports": "wiederholt fehlende Meldungen",
    "scores differed": "die Spielstände waren verschieden",
    "the fight ended without a winner": "der Kampf endete ohne Sieger",
    "Match declined.": "Match abgelehnt.",
    "Nobody accepted in time.": "Niemand hat rechtzeitig angenommen.",
    "Your opponent left.": "Dein Gegner ist gegangen.",
    "No UDP connection to the lobby server (firewall?).": "Keine UDP-Verbindung zum Lobby-Server (Firewall?).",
    "Could not connect the two PCs, not even through the relay.":
        "Die beiden PCs konnten nicht verbunden werden, auch nicht über das Relay.",
    "The lobby server's relay is full; try again in a moment.":
        "Das Relay des Lobby-Servers ist voll; versuche es gleich noch einmal.",
    "Challenge cancelled.": "Herausforderung zurückgezogen.",
    "Challenge declined.": "Herausforderung abgelehnt.",
    "Challenge expired.": "Herausforderung abgelaufen.",
    "direct": "direkt",
    "via the lobby server's relay": "über das Relay des Lobby-Servers",
    "Player": "Spieler",
    "Rank": "Rang",
    "Rating": "Wertung",
    "Record": "Bilanz",
    "Main": "Main",
    "Ping": "Ping",
    "Room": "Raum",
    "Status": "Status",
    "Owner": "Ersteller",
    "Place": "Platz",
    "State": "Zustand",
    "When": "Wann",
    "Characters": "Charaktere",
    "Opponent": "Gegner",
    "Result": "Ergebnis",
    "Score": "Runden",
    "{wins}W {losses}L": "{wins}W {losses}L",
    "{draws}D": "{draws}D",
    "Lobby error: {error}": "Lobby-Fehler: {error}",
    "guest": "Gast",
    "Account": "Konto",
    "Server": "Server",
    "Name": "Name",
    "Password": "Passwort",
    "Remember me": "Angemeldet bleiben",
    "Log in": "Anmelden",
    "Play as guest": "Als Gast spielen",
    "Forgot password...": "Passwort vergessen...",
    "Server certificate...": "Server-Zertifikat...",
    "Host for friends": "Für Freunde hosten",
    "Open router ports (UPnP)": "Router-Ports öffnen (UPnP)",
    "Not connected. Ranked needs an account; guests play casual matches.":
        "Nicht verbunden. Ranked braucht ein Konto; Gäste spielen Casual-Matches.",
    "Log out": "Abmelden",
    "Change password...": "Passwort ändern...",
    "New recovery codes...": "Neue Wiederherstellungs-Codes...",
    "My profile": "Mein Profil",
    "Blocked players...": "Blockierte Spieler...",
    "Passwords are only sent to servers on this PC / your network, or over an encrypted "
    "(TLS) connection.":
        "Passwörter gehen nur an Server auf diesem PC oder in deinem Netzwerk, oder über "
        "eine verschlüsselte (TLS-)Verbindung.",
    "Character": "Charakter",
    "Strict (ranked: +-150 rating)": "Streng (Ranked: +-150 Wertung)",
    "Ranked match": "Ranked-Match",
    "Quick match": "Quick Match",
    "Stop searching": "Suche beenden",
    "Create room": "Raum erstellen",
    "Join room": "Raum beitreten",
    "Leave room": "Raum verlassen",
    "Challenge": "Herausfordern",
    "Lobby": "Lobby",
    "Leaderboard": "Rangliste",
    "Profile": "Profil",
    "Chat": "Chat",
    "Refresh": "Aktualisieren",
    "Order: rating minus twice its uncertainty (a few matches are needed to climb). '?' "
    "= provisional.":
        "Reihenfolge: Wertung minus das Doppelte der Unsicherheit (ein paar Matches sind "
        "nötig, um aufzusteigen). „?“ = vorläufig.",
    "Double-click a player in the lobby or the leaderboard.":
        "Doppelklick auf einen Spieler in der Lobby oder der Rangliste.",
    "Use a controller here": "Controller hier benutzen",
    "{name} (guest, casual matches only)": "{name} (Gast, nur Casual-Matches)",
    "{record} this session": "{record} in dieser Sitzung",
    "rating {rating}": "Wertung {rating}",
    "main {character}": "Main {character}",
    "server ping {ms} ms": "Server-Ping {ms} ms",
    "encrypted": "verschlüsselt",
    "[Server: {notice}]": "[Server: {notice}]",
    "Server notice: {notice}": "Server-Hinweis: {notice}",
    "The game is not built.": "Das Spiel ist nicht gebaut.",
    "Cannot read the build's identity: {error}": "Die Kennung des Builds lässt sich nicht lesen: {error}",
    "Enter a password (6 characters or more), or play as a guest.":
        "Gib ein Passwort ein (6 Zeichen oder mehr), oder spiele als Gast.",
    "Connecting to {server}...": "Verbinde mit {server}...",
    "Pick a character, then Ranked match (accounts) or Quick match.":
        "Wähle einen Charakter, dann Ranked-Match (mit Konto) oder Quick Match.",
    "Encrypted connection (TLS).": "Verschlüsselte Verbindung (TLS).",
    "(logged in with your saved login)": "(mit deiner gespeicherten Anmeldung angemeldet)",
    "In the lobby.": "In der Lobby.",
    "Your saved login has expired; log in with your password.":
        "Deine gespeicherte Anmeldung ist abgelaufen; melde dich mit deinem Passwort an.",
    "Create account": "Konto erstellen",
    "Type the password again:": "Gib das Passwort noch einmal ein:",
    "The two passwords differ.": "Die beiden Passwörter sind verschieden.",
    "Closing the running game for the online match...": "Schließe das laufende Spiel für das Online-Match...",
    "Also forget the saved login on this PC?\n\n(No = you are logged in automatically "
    "next time.)":
        "Auch die gespeicherte Anmeldung auf diesem PC vergessen?\n\n(Nein = du wirst beim "
        "nächsten Mal automatisch angemeldet.)",
    "Not connected.": "Nicht verbunden.",
    "Change password": "Passwort ändern",
    "Current password:": "Aktuelles Passwort:",
    "New password (6 characters or more):": "Neues Passwort (6 Zeichen oder mehr):",
    "New password again:": "Neues Passwort noch einmal:",
    "The two new passwords differ.": "Die beiden neuen Passwörter sind verschieden.",
    "Password changed. Saved logins on other PCs have ended.":
        "Passwort geändert. Gespeicherte Anmeldungen auf anderen PCs sind beendet.",
    "Recovery codes": "Wiederherstellungs-Codes",
    "Your password (the old codes stop working):": "Dein Passwort (die alten Codes gelten dann nicht mehr):",
    "Your account is ready.": "Dein Konto ist fertig.",
    "These codes are the only way back into your account if you forget the password "
    "(there is no e-mail). Each code works once. Write them down or save them somewhere "
    "safe -- they are not shown again.":
        "Diese Codes sind der einzige Weg zurück in dein Konto, wenn du das Passwort "
        "vergisst (es gibt keine E-Mail). Jeder Code gilt nur einmal. Schreibe sie auf oder "
        "speichere sie an einem sicheren Ort -- sie werden nicht noch einmal angezeigt.",
    "Save recovery codes": "Wiederherstellungs-Codes speichern",
    "T5DR Online recovery codes for {name} on {server}":
        "T5DR Online Wiederherstellungs-Codes für {name} auf {server}",
    "Save to a file...": "In Datei speichern...",
    "I have saved them": "Ich habe sie gespeichert",
    "Forgot password": "Passwort vergessen",
    "Account name:": "Kontoname:",
    "One of your recovery codes (XXXX-XXXX-XXXX):": "Einer deiner Wiederherstellungs-Codes (XXXX-XXXX-XXXX):",
    "Password reset. {count} recovery code(s) left. Log in with the new password.":
        "Passwort zurückgesetzt. Noch {count} Wiederherstellungs-Code(s) übrig. Melde dich "
        "mit dem neuen Passwort an.",
    "Server certificate": "Server-Zertifikat",
    "For a server with its own (self-signed) certificate: its SHA-256 fingerprint, from "
    "whoever runs it.\nEmpty = no pinning (use tls://host:port for a server with a "
    "normal certificate).":
        "Für einen Server mit eigenem (selbst signiertem) Zertifikat: sein "
        "SHA-256-Fingerabdruck, von dem, der ihn betreibt.\nLeer = kein Pinning (nimm "
        "tls://host:port für einen Server mit normalem Zertifikat).",
    "Searching for an opponent...": "Suche einen Gegner...",
    "Searching for an opponent (ranked: similar rank and a good connection, strict: "
    "within 150 rating points -- this can take a while)...":
        "Suche einen Gegner (Ranked: ähnlicher Rang und gute Verbindung, streng: innerhalb "
        "von 150 Wertungspunkten -- das kann dauern)...",
    "Searching for an opponent (ranked: similar rank and a good connection)...":
        "Suche einen Gegner (Ranked: ähnlicher Rang und gute Verbindung)...",
    "Select a room first.": "Wähle zuerst einen Raum.",
    "Select an opponent in the list first.": "Wähle zuerst in der Liste einen Gegner.",
    "Challenge sent.": "Herausforderung gesendet.",
    "Blocked players": "Blockierte Spieler",
    "You are never matched with these players (ranked, quick matches, rooms, challenges, "
    "rematches). They are not told. Accounts stay blocked; a guest is blocked until you "
    "log out.":
        "Du wirst mit diesen Spielern nie zusammengebracht (Ranked, Quick Match, Räume, "
        "Herausforderungen, Rematches). Sie erfahren es nicht. Konten bleiben blockiert; ein "
        "Gast ist blockiert, bis du dich abmeldest.",
    "Unblocked {name}.": "{name} ist nicht mehr blockiert.",
    "Unblock": "Freigeben",
    "Close": "Schließen",
    "Block player": "Spieler blockieren",
    "Block {name}?\n\nYou will not be matched with them again. They are not told. You "
    "can unblock them under \"Blocked players...\".":
        "{name} blockieren?\n\nDu wirst nicht mehr mit diesem Spieler zusammengebracht. Er "
        "erfährt es nicht. Du kannst die Sperre unter „Blockierte Spieler...“ aufheben.",
    "Blocked {name}. You will not be matched again.": "{name} blockiert. Ihr werdet nicht mehr zusammengebracht.",
    "you": "du",
    "{name} -- {rank}": "{name} -- {rank}",
    "Rating {rating} +/- {rd}": "Wertung {rating} +/- {rd}",
    "(provisional)": "(vorläufig)",
    "#{place} on the leaderboard": "Platz {place} in der Rangliste",
    "Record {record}": "Bilanz {record}",
    "ranked matches {count}": "Ranked-Matches {count}",
    "highest rank {rank}": "höchster Rang {rank}",
    "Characters: {list}": "Charaktere: {list}",
    "Matches without result caused in the last 24 h: {count}":
        "Durch dich verursachte Matches ohne Ergebnis in den letzten 24 h: {count}",
    "Recovery codes left: {count}": "Übrige Wiederherstellungs-Codes: {count}",
    "{you} vs {opponent}": "{you} vs {opponent}",
    "casual": "Casual",
    "Opponent: {name} ({rank}, {rating})": "Gegner: {name} ({rank}, {rating})",
    "RANKED": "RANKED",
    "rematch": "Rematch",
    "{name} ({rank}) challenges you": "{name} ({rank}) fordert dich heraus",
    "Accept": "Annehmen",
    "Decline": "Ablehnen",
    "Challenge {state}.": "Herausforderung {state}.",
    "connecting...": "verbinde...",
    "Your opponent accepted.": "Dein Gegner hat angenommen.",
    "Match cancelled ({reason}).": "Match abgebrochen ({reason}).",
    "Ranked match vs {name}": "Ranked-Match gegen {name}",
    "Casual match vs {name}": "Casual-Match gegen {name}",
    "{p1} vs {p2}": "{p1} vs {p2}",
    "ping {ms} ms ({how}), input delay {frames} frames ({delay_ms} ms)":
        "Ping {ms} ms ({how}), Input-Delay {frames} Frames ({delay_ms} ms)",
    "Lost the lobby connection -- reconnecting (your match goes on)...":
        "Verbindung zur Lobby verloren -- verbinde neu (dein Match läuft weiter)...",
    "Reconnected to the lobby.": "Wieder mit der Lobby verbunden.",
    "Lost the lobby connection: {reason}": "Verbindung zur Lobby verloren: {reason}",
    "Removed from the lobby: {reason}": "Aus der Lobby entfernt: {reason}",
    "The game closed. How did the match against {opponent} end?":
        "Das Spiel wurde geschlossen. Wie ist das Match gegen {opponent} ausgegangen?",
    "I won": "Ich habe gewonnen",
    "I lost": "Ich habe verloren",
    "Draw": "Unentschieden",
    "I quit": "Ich habe aufgegeben",
    "{opponent} wants a rematch": "{opponent} will ein Rematch",
    "Rematch": "Rematch",
    "No thanks": "Nein danke",
    "Result sent; waiting for your opponent's report...": "Ergebnis gesendet; warte auf die Meldung deines Gegners...",
    "Rematch offered; waiting for your opponent...": "Rematch angeboten; warte auf deinen Gegner...",
    "(other version)": "(andere Version)",
    "ranked": "ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "Suche... ({ranked} in der Ranked-Suche, {quick} bei Quick Match)",
    "ping about {ms} ms (through the server; measured directly once you both accept)":
        "Ping etwa {ms} ms (über den Server; direkt gemessen, sobald ihr beide annehmt)",
    "ping not known yet": "Ping noch nicht bekannt",
    "Opponent found": "Gegner gefunden",
    "accept within {seconds} s?": "innerhalb von {seconds} s annehmen?",
    "waiting for the opponent...": "warte auf den Gegner...",
    "Lag check: {text}": "Lag-Check: {text}",
    "You left after the lag check. No penalty, no rating change.":
        "Du bist nach dem Lag-Check gegangen. Keine Strafe, keine Änderung der Wertung.",
    "Your opponent left after the lag check. No penalty for anyone.":
        "Dein Gegner ist nach dem Lag-Check gegangen. Für keinen von euch gibt es eine "
        "Strafe.",
    "Your opponent left. The set is over.": "Dein Gegner ist gegangen. Das Set ist vorbei.",
    "Rematch {name}": "Rematch mit {name}",
    "Leave": "Verlassen",
    "Block {name}": "{name} blockieren",
    "Leave: too laggy": "Verlassen: zu laggy",
    "You lost.": "Du hast verloren.",
    "You won.": "Du hast gewonnen.",
    "rating {rating} ({delta})": "Wertung {rating} ({delta})",
    "PROMOTED to {rank}!": "AUFGESTIEGEN zu {rank}!",
    "demoted to {rank}": "abgestiegen zu {rank}",
    "placed at {rank}": "eingestuft als {rank}",
    "placement {done}/{total}": "Platzierung {done}/{total}",
    "your opponent": "dein Gegner",
    "Rematch?": "Rematch?",
    "Controller off.": "Controller aus.",
    "No controller found.": "Kein Controller gefunden.",
    "Controller: {summary}": "Controller: {summary}",
    "Cannot start the lobby server: {error}": "Der Lobby-Server lässt sich nicht starten: {error}",
    "Stop hosting": "Hosten beenden",
    "Starting a lobby server on this PC and asking the router to forward its ports...":
        "Starte einen Lobby-Server auf diesem PC und bitte den Router, seine Ports "
        "weiterzuleiten...",
    "Starting a lobby server on this PC...": "Starte einen Lobby-Server auf diesem PC...",
    "<your public IP>": "<deine öffentliche IP>",
    "Hosting. Friends paste this as their Server (copied to the clipboard):\n  {share}":
        "Du hostest. Deine Freunde tragen das als ihren Server ein (in die Zwischenablage "
        "kopiert):\n  {share}",
    "\n  same network: {lan}": "\n  im selben Netzwerk: {lan}",
    "\n  Forward TCP+UDP 7781 and UDP 7782 on your router (or tick 'Open router ports').":
        "\n  Leite TCP+UDP 7781 und UDP 7782 an deinem Router weiter (oder setze den Haken "
        "bei „Router-Ports öffnen“).",
    "Hosting a lobby on this PC. Log in to join it yourself.":
        "Eine Lobby läuft auf diesem PC. Melde dich an, um selbst beizutreten.",
    "Hosting failed: {message}": "Hosten fehlgeschlagen: {message}",
    "The lobby server stopped (exit code {code}); see its log in {folder}.":
        "Der Lobby-Server wurde beendet (Exit-Code {code}); sein Log liegt in {folder}.",
    "Stopped hosting.": "Hosten beendet.",
}
