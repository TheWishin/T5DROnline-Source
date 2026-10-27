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
    # ---- launcher/controls_edit.py
    "Removed {sources} from your buttons: that is L2 / R2 at rest on a PlayStation pad, so the game held them all the time. Save to keep this.":
        "{sources} aus deinen Tasten entfernt: Das ist L2 / R2 in Ruhe auf einem PlayStation-Pad, deshalb hat das Spiel sie die ganze Zeit gedrückt gehalten. Speichere, um das zu behalten.",
    "Attack buttons": "Angriffstasten",
    "Several buttons with one press (macros)": "Mehrere Tasten mit einem Druck (Makros)",
    "Start, Select and the other buttons": "Start, Select und die anderen Tasten",
    "Directions": "Richtungen",
    "1 (Left Punch)": "1 (Linker Schlag)",
    "2 (Right Punch)": "2 (Rechter Schlag)",
    "3 (Left Kick)": "3 (Linker Tritt)",
    "4 (Right Kick)": "4 (Rechter Tritt)",
    "Select": "Select",
    "Start / pause": "Start / Pause",
    "Down": "Runter",
    "Left": "Links",
    "Up": "Hoch",
    "Right": "Rechts",
    "PlayStation pad, default": "PlayStation-Pad, Standard",
    "Xbox pad, default": "Xbox-Pad, Standard",
    "X Y A B are 1 2 3 4; bumpers and triggers are L1 R1 L2 R2.":
        "X Y A B sind 1 2 3 4; Schultertasten und Trigger sind L1 R1 L2 R2.",
    "Square Triangle Cross Circle are 1 2 3 4 (DualShock 4, DualSense and most "
    "PS3/PS4-mode sticks).":
        "Quadrat Dreieck Kreuz Kreis sind 1 2 3 4 (DualShock 4, DualSense und die meisten "
        "Sticks im PS3/PS4-Modus).",
    "Switch pad, default": "Switch-Pad, Standard",
    "Y X B A are 1 2 3 4 (Switch Pro controller, sticks in Switch mode).":
        "Y X B A sind 1 2 3 4 (Switch-Pro-Controller, Sticks im Switch-Modus).",
    "Xbox-style pad (generic)": "Xbox-ähnliches Pad (allgemein)",
    "A B X Y buttons and LB RB, for Xbox-like pads that Windows does not give to XInput.":
        "A-B-X-Y-Tasten und LB RB, für Xbox-ähnliche Pads, die Windows nicht an XInput gibt.",
    "8-button stick (Vewlix layout)": "8-Tasten-Stick (Vewlix-Layout)",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: X Y RB LB over A B RT LT.":
        "Obere Reihe 1 2 [1+2] [1+3], untere Reihe 3 4 [3+4] [2+4]: X Y RB LB über A B RT "
        "LT.",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: B1 B4 B6 B5 over B2 B3 B8 B7.":
        "Obere Reihe 1 2 [1+2] [1+3], untere Reihe 3 4 [3+4] [2+4]: B1 B4 B6 B5 über B2 B3 "
        "B8 B7.",
    "6-button stick (Noir / Sega Astro)": "6-Tasten-Stick (Noir / Sega Astro)",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: X Y RB over A B RT. LB and LT stay L1 and "
    "L2.":
        "Obere Reihe 1 2 [1+2], untere Reihe 3 4 [3+4]: X Y RB über A B RT. LB und LT "
        "bleiben L1 und L2.",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: B1 B4 B6 over B2 B3 B8. B5 and B7 stay L1 "
    "and L2.":
        "Obere Reihe 1 2 [1+2], untere Reihe 3 4 [3+4]: B1 B4 B6 über B2 B3 B8. B5 und B7 "
        "bleiben L1 und L2.",
    "Hitbox": "Hitbox",
    "The 8-button layout above. Directions come from the d-pad or the left stick, which "
    "is read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "Das 8-Tasten-Layout von oben. Die Richtungen kommen vom Steuerkreuz oder vom linken "
        "Stick, der als 8-Wege-Steuerkreuz gelesen wird; links+rechts (hoch+runter) zugleich "
        "heben sich auf.",
    "The 8-button layout above. Directions come from the hat or the left stick, which is "
    "read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "Das 8-Tasten-Layout von oben. Die Richtungen kommen vom Hat oder vom linken Stick, "
        "der als 8-Wege-Steuerkreuz gelesen wird; links+rechts (hoch+runter) zugleich heben "
        "sich auf.",
    "The file has {n} settings; the game reads at most {max}.":
        "Die Datei hat {n} Einstellungen; das Spiel liest höchstens {max}.",
    "The file has {n} sections; the game reads at most {max}.":
        "Die Datei hat {n} Abschnitte; das Spiel liest höchstens {max}.",
    "Changed lines of {sections} that would have overridden this ({what}).":
        "Geänderte Zeilen aus {sections}, die das überschrieben hätten ({what}).",
    "Lines of your file in other sections still change some buttons.":
        "Zeilen deiner Datei in anderen Abschnitten ändern weiterhin einige Tasten.",
    "Other lines in your file ({sections}) still change this layout.":
        "Andere Zeilen deiner Datei ({sections}) ändern dieses Layout weiterhin.",
    "{n} lines removed.": "{n} Zeilen entfernt.",
    # ---- launcher/controls_ui.py
    "DirectInput controller": "DirectInput-Controller",
    "Xbox pad (XInput)": "Xbox-Pad (XInput)",
    "PlayStation pad, read directly": "PlayStation-Pad, direkt gelesen",
    "Arrows move; A S on top are 1 2, Z X below are 3 4. Q W are L1 R1, 1 2 are L2 R2, Enter is Start, Tab is Select.": "Pfeiltasten bewegen; A S oben sind 1 2, Z X darunter 3 4. Q W sind L1 R1, 1 2 sind L2 R2, Enter ist Start, Tab ist Select.",
    "Arrows move; number pad 4 5 are 1 2, 1 2 are 3 4, 6 is 1+2, 3 is 3+4 (Num Lock on).": "Pfeiltasten bewegen; Ziffernblock 4 5 sind 1 2, 1 2 sind 3 4, 6 ist 1+2, 3 ist 3+4 (Num-Taste an).",
    "Esc (leaves the game)": "Esc (verlässt das Spiel)",
    "F11 (fullscreen)": "F11 (Vollbild)",
    "F2 (training overlay)": "F2 (Trainingsanzeige)",
    "Keyboard, second player": "Tastatur, zweiter Spieler",
    "Keyboard: WASD and U I J K": "Tastatur: WASD und U I J K",
    "Keyboard: arrows and A S Z X": "Tastatur: Pfeiltasten und A S Z X",
    "Keyboard: arrows and number pad": "Tastatur: Pfeiltasten und Ziffernblock",
    'Keyboard: pick a game button, then Set selected (or double-click it) and press the key. Esc stops. The game reads the keyboard while its window has the focus.': 'Tastatur: wähle eine Spieltaste, dann "Ausgewählte einstellen" (oder Doppelklick) und drücke die Taste. Esc bricht ab. Das Spiel liest die Tastatur, solange sein Fenster den Fokus hat.',
    "Press only that one key. Esc stops.": "Drücke nur diese eine Taste. Esc bricht ab.",
    "Press the key for {button}...": "Drücke die Taste für {button}...",
    "The keyboard ([{section}] in controls.ini)": "Die Tastatur ([{section}] in der controls.ini)",
    "W A S D move; U I are 1 2, J K are 3 4, O is 1+2, L is 3+4. Y P are L1 R1, H and ; are L2 R2, Enter is Start, Backspace is Select.": "W A S D bewegen; U I sind 1 2, J K sind 3 4, O ist 1+2, L ist 3+4. Y P sind L1 R1, H und ; sind L2 R2, Enter ist Start, Rücktaste ist Select.",
    "{key} is the game's own key; press another one.": '{key} ist eine Taste des Spiels selbst; drücke eine andere.',
    "{source} is also {other} for the second keyboard player.": "{source} ist für den zweiten Tastatur-Spieler auch {other}.",
    "Controls - T5DR Online": "Steuerung - T5DR Online",
    "Press a button on a controller to pick it, then set its buttons. The game reads the "
    "file when it starts.":
        "Drücke eine Taste an einem Controller, um ihn auszuwählen, und stelle dann seine "
        "Tasten ein. Das Spiel liest die Datei beim Start.",
    "Controllers": "Controller",
    "Player": "Spieler",
    "Controller": "Controller",
    "Pressed now": "Gerade gedrückt",
    "Move through this window with the controller": "Dieses Fenster mit dem Controller bedienen",
    "Buttons": "Tasten",
    "Game button": "Spieltaste",
    "Controller button": "Controller-Taste",
    "Set up all buttons": "Alle Tasten einstellen",
    "Set up directions": "Richtungen einstellen",
    "Set selected": "Ausgewählte einstellen",
    "Clear": "Löschen",
    "Layout": "Layout",
    "Use this layout": "Dieses Layout benutzen",
    "Reset to defaults": "Auf Standard zurücksetzen",
    "Your changes apply to": "Deine Änderungen gelten für",
    "Player and directions": "Spieler und Richtungen",
    "Automatic": "Automatisch",
    "Player 1": "Spieler 1",
    "Player 2": "Spieler 2",
    "8-way d-pad": "8-Wege-Steuerkreuz",
    "Analog stick": "Analogstick",
    "Both cancel (neutral)": "Beide heben sich auf (neutral)",
    "Up wins (Up+Down is Up)": "Hoch gewinnt (Hoch+Runter = Hoch)",
    "Last direction wins": "Die letzte Richtung gewinnt",
    "Pass both through": "Beide durchlassen",
    "This controller is": "Dieser Controller ist",
    "Left stick": "Linker Stick",
    "Opposite directions": "Gegenrichtungen",
    "Left stick, 8-way d-pad: a hitbox or stick in left-stick mode sends the direction "
    "as a stick; the game then reads it as d-pad presses. Left+Right (or Up+Down) at "
    "once happens on keyboards and hitboxes; the game cannot take both. Stick and "
    "opposite directions belong to the player's port.":
        "Linker Stick, 8-Wege-Steuerkreuz: Eine Hitbox oder ein Stick im Linker-Stick-Modus "
        "sendet die Richtung als Stick; das Spiel liest sie dann als Steuerkreuz-Drücke. "
        "Links+Rechts (oder Hoch+Runter) zugleich kommt auf Tastaturen und Hitboxen vor; das "
        "Spiel kann nicht beides nehmen. Stick und gegenüberliegende Richtungen gehören zum "
        "Port des Spielers.",
    "Skip": "Überspringen",
    "Stop": "Stopp",
    "Save": "Speichern",
    "Revert": "Verwerfen",
    "Close": "Schließen",
    "no controller": "kein Controller",
    "Controllers cannot be read on this PC.": "Controller lassen sich auf diesem PC nicht lesen.",
    "No controller found. Plug one in; it shows up here by itself.":
        "Kein Controller gefunden. Stecke einen an; er erscheint hier von selbst.",
    "switched off in [general]": "in [general] ausgeschaltet",
    "no free player port": "kein freier Spieler-Port",
    "No controller chosen": "Kein Controller ausgewählt",
    "This controller model ({vid}:{pid})": "Dieses Controller-Modell ({vid}:{pid})",
    "This controller model (no USB ID)": "Dieses Controller-Modell (ohne USB-ID)",
    "All DirectInput controllers": "Alle DirectInput-Controller",
    "All Xbox pads (XInput)": "Alle Xbox-Pads (XInput)",
    "Only the controller on player {n}'s port": "Nur der Controller am Port von Spieler {n}",
    "no player": "kein Spieler",
    "player {n}": "Spieler {n}",
    "yours": "deins",
    "Your own layout": "Dein eigenes Layout",
    "Player {n}": "Spieler {n}",
    "Buttons you set yourself, or a mix. Pick a layout to start from it.":
        "Tasten, die du selbst eingestellt hast, oder eine Mischung. Wähle ein Layout, um "
        "davon auszugehen.",
    "On the controller: {up} / {down} choose a button, {accept} sets it, {clear} clears "
    "it, {save} saves, {back} closes. The game reads the file when it starts.":
        "Am Controller: {up} / {down} wählt eine Taste, {accept} stellt sie ein, {clear} "
        "löscht sie, {save} speichert, {back} schließt. Das Spiel liest die Datei beim "
        "Start.",
    "(no game button)": "(keine Spieltaste)",
    "Press a button on a controller first, or pick one in the list.":
        "Drücke zuerst eine Taste an einem Controller, oder wähle einen in der Liste.",
    "Press the button for {button}...": "Drücke die Taste für {button}...",
    "Press only that one button on the controller.": "Drücke am Controller nur diese eine Taste.",
    "{n} of {total}.": "{n} von {total}.",
    "Wait a few seconds to skip it.": "Warte ein paar Sekunden, um sie zu überspringen.",
    "That was several buttons at once ({sources}). Press one button only.":
        "Das waren mehrere Tasten auf einmal ({sources}). Drücke nur eine Taste.",
    "{button}: skipped.": "{button}: übersprungen.",
    "{button} = {source}.": "{button} = {source}.",
    "{source} was {other}; that one has no button now.": "{source} war {other}; das hat jetzt keine Taste mehr.",
    "Stopped.": "Gestoppt.",
    "{button}: cleared.": "{button}: gelöscht.",
    "Layout: {name}.": "Layout: {name}.",
    "Pick a layout in the list first.": "Wähle zuerst ein Layout in der Liste.",
    "Put {name} back to the default buttons? Your comments and other settings in "
    "controls.ini stay.":
        "{name} auf die Standardtasten zurücksetzen? Deine Kommentare und anderen "
        "Einstellungen in controls.ini bleiben.",
    "The part of the file that is for all {kind} controllers has button lines too. Reset "
    "those as well?":
        "Der Teil der Datei für alle Controller vom Typ {kind} hat auch Tastenzeilen. Diese "
        "ebenfalls zurücksetzen?",
    "Reset to the defaults. Save to keep it.": "Auf Standard zurückgesetzt. Speichere, um es zu behalten.",
    "{name} is {player}. Save to keep it.": "{name} ist {player}. Speichere, um es zu behalten.",
    "controls.ini changed": "controls.ini geändert",
    "controls.ini was changed by something else since this screen opened. Overwrite it "
    "with your settings? (The old file is kept as controls.ini.bak.)":
        "controls.ini wurde seit dem Öffnen dieses Fensters von etwas anderem geändert. Mit "
        "deinen Einstellungen überschreiben? (Die alte Datei bleibt als controls.ini.bak "
        "erhalten.)",
    "Could not save: {error}": "Speichern nicht möglich: {error}",
    "Saved {path}. The game reads it when it starts.": "{path} gespeichert. Das Spiel liest sie beim Start.",
    "The game that is running keeps its old buttons until you start it again.":
        "Das laufende Spiel behält seine alten Tasten, bis du es neu startest.",
    "Changes undone.": "Änderungen verworfen.",
    "There are unsaved changes. Save them first, or close with the mouse.":
        "Es gibt ungespeicherte Änderungen. Speichere sie zuerst, oder schließe mit der "
        "Maus.",
    "Controls": "Steuerung",
    "Save the changes to controls.ini?": "Die Änderungen in controls.ini speichern?",
    # ---- launcher/core.py
    "Auto (laptops, handhelds, integrated graphics)": "Auto (Laptops, Handhelds, integrierte Grafik)",
    "On": "An",
    "a mobile processor": "ein Laptop-Prozessor",
    "battery saver is on": "der Stromsparmodus von Windows ist an",
    "the Power saver power plan is on": "der Energiesparplan \"Energiesparmodus\" ist aktiv",
    "this PC has a battery (laptop or handheld)": "dieser PC hat einen Akku (Laptop oder Handheld)",
    "Inputs": "Eingaben",
    "Inputs + frame data": "Eingaben + Framedaten",
    "Auto (Windows language)": "Auto (Sprache von Windows)",
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
    "Build the game once (about 2 minutes): this version of the launcher changes the "
    "game code. Click BUILD GAME. Your unpacked game and saves are kept; only the code "
    "is translated and compiled again.":
        "Baue das Spiel einmal (etwa 2 Minuten): Diese Version des Launchers ändert den "
        "Spielcode. Klicke auf BUILD GAME. Dein entpacktes Spiel und deine Spielstände "
        "bleiben erhalten; nur der Code wird neu übersetzt und kompiliert.",
    "Ready: {title_id} v{version}, program SHA-1 {sha}... verified, built {when}.":
        "Bereit: {title_id} v{version}, Programm-SHA-1 {sha}... geprüft, gebaut {when}.",
    "Check & decrypt": "Prüfen & entschlüsseln",
    "Key data": "Schlüsseldaten",
    "Recompiler": "Recompiler",
    "Unpack": "Entpacken",
    "Compile": "Kompilieren",
    "Game files": "Spieldateien",
    "Sound core": "Soundkern",
    "Shaders": "Shader",
    "Translate code": "Code übersetzen",
    "The translation step has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, close other programs, press Cancel and then BUILD GAME again; build.log "
    "has the details.":
        "Der Schritt „Code übersetzen“ hat seit {minutes} Minuten nichts ausgegeben. Auf einem langsamen oder "
        "ausgelasteten PC kann er noch arbeiten. Wenn sich nichts tut, schließe andere Programme, klicke auf "
        "Abbrechen und dann wieder auf BUILD GAME; build.log hat die Details.",
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
    "Lowest (0.5x)": "Am niedrigsten (0,5x)",
    "Lower (0.75x)": "Niedriger (0,75x)",
    "Native (720p)": "Nativ (720p)",
    "1080p (1.5x)": "1080p (1,5x)",
    "1440p (2x)": "1440p (2x)",
    "4K (3x)": "4K (3x)",
    "The 3D scene at half size (a quarter of its pixels); HUD and text stay sharp. "
    "For integrated graphics and old laptops.":
        "Die 3D-Szene in halber Größe (ein Viertel ihrer Pixel); HUD und Text bleiben scharf. "
        "Für integrierte Grafik und alte Laptops.",
    "The 3D scene at 3/4 size (about half of its pixels); HUD and text stay sharp. "
    "For weak graphics cards.":
        "Die 3D-Szene in 3/4 Größe (etwa die Hälfte ihrer Pixel); HUD und Text bleiben scharf. "
        "Für schwache Grafikkarten.",
    "The PS3's 1280 x 720. Light on any graphics card; the picture is scaled to your window.":
        "Die 1280 x 720 der PS3. Leicht für jede Grafikkarte; das Bild wird auf dein Fenster skaliert.",
    "1920 x 1080: 2.25x the pixels of Native. Sharp on Full HD screens. "
    "If fights drop below 60 fps, go one step down.":
        "1920 x 1080: 2,25-mal die Pixel von Nativ. Scharf auf Full-HD-Bildschirmen. "
        "Fallen Kämpfe unter 60 fps, geh eine Stufe zurück.",
    "2560 x 1440: 4x the pixels of Native. For strong graphics cards. "
    "If fights drop below 60 fps, go one step down.":
        "2560 x 1440: 4-mal die Pixel von Nativ. Für starke Grafikkarten. "
        "Fallen Kämpfe unter 60 fps, geh eine Stufe zurück.",
    "3840 x 2160: 9x the pixels of Native. For very strong graphics cards "
    "(an RTX 3090 needs 1-2 ms of a 16.7 ms frame). If fights drop below 60 fps, go one step down.":
        "3840 x 2160: 9-mal die Pixel von Nativ. Für sehr starke Grafikkarten "
        "(eine RTX 3090 braucht 1-2 ms von 16,7 ms pro Bild). Fallen Kämpfe unter 60 fps, "
        "geh eine Stufe zurück.",
    "Auto (by ping)": "Auto (nach Ping)",
    "Window, 1280 x 720 (native; larger with Windows display scaling)":
        "Fenster, 1280 x 720 (nativ; größer mit der Windows-Skalierung)",
    "Window, 1920 x 1080": "Fenster, 1920 x 1080",
    "Window, 2560 x 1440": "Fenster, 2560 x 1440",
    "Maximized window": "Maximiertes Fenster",
    "Borderless fullscreen (Alt+Enter or F11 switches in the game)":
        "Randloses Vollbild (Alt+Enter oder F11 schaltet im Spiel um)",
    # ---- launcher/online.py
    "Online play": "Online spielen",
    "The lobby files (lobby/t5lobby) are missing from this copy of the launcher, so "
    "online play is not available.\n\n({reason})":
        "Die Lobby-Dateien (lobby/t5lobby) fehlen in dieser Kopie des Launchers, darum ist "
        "Online-Spiel nicht möglich.\n\n({reason})",
    # ---- launcher/problem_report_ui.py
    "Before the zip is made, your Windows user name in file paths becomes <user>, "
    "internet IP addresses become <ip> (addresses of your own network stay), lobby player "
    "names (yours and your opponents') become <player>, and passwords, tokens and match keys "
    "are left out. Your game files, keys, .pkg and .rap are never included. Nothing is "
    "uploaded: you send the zip yourself.":
        "Bevor die Zip-Datei entsteht, wird dein Windows-Benutzername in Dateipfaden zu "
        "<user>, Internet-IP-Adressen werden zu <ip> (Adressen deines eigenen Netzwerks "
        "bleiben), Spielernamen aus der Lobby (deiner und die deiner Gegner) werden zu "
        "<player>, und Passwörter, Tokens und Match-Schlüssel werden weggelassen. Deine "
        "Spieldateien, Schlüssel, .pkg und .rap sind nie dabei. Es wird nichts hochgeladen: "
        "Du schickst die Zip-Datei selbst.",
    "{count} bytes": "{count} Bytes",
    "Report a problem": "Problem melden",
    "This makes one zip file on your Desktop with the logs and settings that help to "
    "find the problem. Send the zip to the person who gave you the game, or attach it to "
    "an issue.":
        "Das erstellt eine Zip-Datei auf deinem Desktop mit den Logs und Einstellungen, die "
        "helfen, das Problem zu finden. Schicke die Zip-Datei an die Person, von der du das "
        "Spiel hast, oder hänge sie an ein Issue.",
    "What happened? (optional)": "Was ist passiert? (freiwillig)",
    "What goes into the zip": "Was in die Zip-Datei kommt",
    "Nothing found yet: no game log, no build log.": "Noch nichts gefunden: kein Spiel-Log, kein Build-Log.",
    "Could not look at the files: {error}": "Die Dateien lassen sich nicht ansehen: {error}",
    "Save report on the Desktop": "Bericht auf dem Desktop speichern",
    "Cancel": "Abbrechen",
    "About {size} before it is packed (a zip is smaller).":
        "Etwa {size}, bevor gepackt wird (eine Zip-Datei ist kleiner).",
    "About {size}; the limit is {limit}, so the biggest logs are shortened in the "
    "middle.":
        "Etwa {size}; das Limit ist {limit}, darum werden die größten Logs in der Mitte "
        "gekürzt.",
    "Making the report...": "Erstelle den Bericht...",
    "The report could not be made: {error}": "Der Bericht konnte nicht erstellt werden: {error}",
    "Report saved": "Bericht gespeichert",
    "{size}. Its folder is open.": "{size}. Der Ordner ist geöffnet.",
    "Send this zip to the person who gave you the game, or attach it to an issue at "
    "{url}.":
        "Schicke diese Zip-Datei an die Person, von der du das Spiel hast, oder hänge sie an "
        "ein Issue auf {url}.",
    "Send this zip to the person who gave you the game.":
        "Schicke diese Zip-Datei an die Person, von der du das Spiel hast.",
    "(shortened in the middle)": "(in der Mitte gekürzt)",
    "{name}   left out: {reason}": "{name}   weggelassen: {reason}",
    "Removed from the text files: {user} user or PC names, {ip} IP addresses, {secret} "
    "passwords, tokens or keys, {email} e-mail addresses.":
        "Aus den Textdateien entfernt: {user} Benutzer- oder PC-Namen, {ip} IP-Adressen, "
        "{secret} Passwörter, Tokens oder Schlüssel, {email} E-Mail-Adressen.",
    "Open folder": "Ordner öffnen",
    # ---- launcher/t5dr_launcher.pyw
    "Discord": "Discord",
    "Show what I play in my Discord status (Rich Presence)":
        "In meinem Discord-Status zeigen, was ich spiele (Rich Presence)",
    "\"In lobby\", \"Searching ranked\" or your match (fighters, ranked set score) with a timer, through the "
    "Discord app on this PC. Without Discord running nothing happens.":
        "„In der Lobby“, „Sucht ein Ranked-Match“ oder dein Match (Kämpfer, Stand im Ranked-Set) mit Zeit, über die "
        "Discord-App auf diesem PC. Läuft Discord nicht, passiert nichts.",
    "Power saving (laptops, handhelds)": "Stromsparen (Laptops, Handhelds)",
    "No busy waiting and fewer worker threads: the processor stays cooler and keeps its speed, so the game "
    "holds 60 fps longer. The game itself is the same, online too.":
        "Kein aktives Warten und weniger Arbeits-Threads: Der Prozessor bleibt kühler und behält seinen Takt, "
        "so hält das Spiel die 60 fps länger. Das Spiel selbst bleibt gleich, auch online.",
    "On for this PC.": "An für diesen PC.",
    "Off.": "Aus.",
    "Auto: on for this PC -- {reason}.": "Auto: an für diesen PC -- {reason}.",
    "Auto: off for this PC (no battery, no mobile processor); the game turns it on by itself if it runs on "
    "integrated graphics.":
        "Auto: aus für diesen PC (kein Akku, kein Laptop-Prozessor); läuft das Spiel auf integrierter Grafik, "
        "schaltet es das Stromsparen selbst ein.",
    "Power saving is on.": "Stromsparen ist an.",
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
    "Back": "Back",
    "SELECT": "SELECT",
    "Tab": "Tab",
    "Esc": "Esc",
    "Quit the game": "Spiel beenden",
    "A / B": "A / B",
    "Cross / Circle": "Kreuz / Kreis",
    "Mouse": "Maus",
    "Online tab: accept / decline": "Online-Reiter: annehmen / ablehnen",
    "native Windows build  ·  launcher {version}": "native Windows-Version  ·  Launcher {version}",
    "Build": "Bauen",
    "Play offline": "Offline spielen",
    "Settings": "Einstellungen",
    "Play online": "Online spielen",
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
    "Redo every step": "Alle Schritte neu machen",
    "Skip warm-up": "Aufwärmen überspringen",
    "Skipping…": "Überspringe…",
    "Keep the PC responsive (slower)": "PC bedienbar halten (langsamer)",
    "Open build.log": "build.log öffnen",
    "Report a problem...": "Problem melden...",
    "Check my problem": "Mein Problem prüfen",
    "Check my problem...": "Mein Problem prüfen...",
    "Looking…": "Suche…",
    "No known problem found.": "Kein bekanntes Problem gefunden.",
    "If something still goes wrong, \"Report a problem...\" makes one zip with your logs to send to whoever helps you.":
        "Wenn trotzdem etwas schiefgeht, macht „Problem melden...“ eine ZIP-Datei mit deinen Logs, die du an deine Hilfe schicken kannst.",
    "Problem": "Problem",
    "Note": "Hinweis",
    "Help": "Hilfe",
    "The launcher looks in this PC's logs and settings for the problems other players had, and says how to fix them. Nothing is changed and nothing is sent.":
        "Der Launcher sucht in den Logs und Einstellungen dieses PCs nach den Problemen, die andere Spieler hatten, und sagt, wie man sie behebt. Nichts wird geändert und nichts wird gesendet.",
    "Your game package is version {version}": "Dein Spielpaket ist Version {version}",
    "The port works only with version {supported} of the game: TEKKEN 5 DARK RESURRECTION ONLINE, US PSN (NPUB30009), a .pkg of {size} bytes, with its license {rap}. Version {version} cannot be used, whatever the license. Choose the {supported} package on the Build tab and press BUILD GAME.":
        "Der Port funktioniert nur mit Version {supported} des Spiels: TEKKEN 5 DARK RESURRECTION ONLINE, US-PSN (NPUB30009), eine .pkg mit {size} Bytes, mit ihrer Lizenz {rap}. Version {version} geht mit keiner Lizenz. Wähle im Tab „Bauen“ das Paket {supported} und drücke BUILD GAME.",
    "build.log: the package says version {version}.": "build.log: Das Paket nennt Version {version}.",
    "Unpacking the game ran out of memory": "Beim Entpacken des Spiels war der Speicher voll",
    "Close other programs (browser, games, launchers) and press BUILD GAME again; since 1.1.5 the launcher unpacks the game in small pieces. If it fails again, check that Windows has a page file (System > About > Advanced system settings > Performance > Virtual memory: automatic).":
        "Schließe andere Programme (Browser, Spiele, Launcher) und drücke noch einmal BUILD GAME; seit 1.1.5 entpackt der Launcher das Spiel in kleinen Stücken. Klappt es wieder nicht, prüfe, ob Windows eine Auslagerungsdatei hat (System > Info > Erweiterte Systemeinstellungen > Leistung > Virtueller Arbeitsspeicher: automatisch).",
    "build.log: the computer ran out of memory while the game data was unpacked.":
        "build.log: Beim Entpacken der Spieldaten ging dem Computer der Speicher aus.",
    "The game package looks damaged or incomplete": "Das Spielpaket scheint beschädigt oder unvollständig",
    "Download the package again (it must be {size} bytes), choose it on the Build tab, tick \"Redo every step\" and press BUILD GAME.":
        "Lade das Paket noch einmal herunter (es muss {size} Bytes haben), wähle es im Tab „Bauen“, setze den Haken bei „Alle Schritte neu machen“ und drücke BUILD GAME.",
    "build.log: the package could not be read to the end or not decrypted.":
        "build.log: Das Paket ließ sich nicht bis zum Ende lesen oder nicht entschlüsseln.",
    "The game says its data is damaged": "Das Spiel meldet beschädigte Daten",
    "On the Build tab tick \"Redo every step\" and press BUILD GAME: it unpacks the game again. If the message comes back, download the package again (it must be {size} bytes).":
        "Setze im Tab „Bauen“ den Haken bei „Alle Schritte neu machen“ und drücke BUILD GAME: Das Spiel wird neu entpackt. Kommt die Meldung wieder, lade das Paket noch einmal herunter (es muss {size} Bytes haben).",
    "Game log: the game showed the message \"{message}\".": "Spiel-Log: Das Spiel zeigte die Meldung „{message}“.",
    "Your graphics card is an older model": "Deine Grafikkarte ist ein älteres Modell",
    "{gpu} is a Direct3D 12 card of the oldest kind (resource binding tier 1: GeForce cards with a Fermi chip, among them some GT 730 models, and older Intel graphics). The game's graphics take several times longer on it than on later cards, whatever the processor: fights can stay below 30 frames per second, and a lower Internal resolution helps only a little. Later cards (a GT 730 with a Kepler chip, GTX 750, Radeon HD 7000 and newer) run the game at full speed.":
        "{gpu} ist eine Direct3D-12-Karte der ältesten Art (Resource Binding Tier 1: GeForce-Karten mit Fermi-Chip, darunter manche GT 730, und ältere Intel-Grafik). Die Grafik des Spiels braucht darauf ein Mehrfaches der Zeit späterer Karten, egal welcher Prozessor: Kämpfe können unter 30 Bildern pro Sekunde bleiben, und eine kleinere interne Auflösung hilft nur wenig. Spätere Karten (eine GT 730 mit Kepler-Chip, GTX 750, Radeon HD 7000 und neuer) schaffen das Spiel mit voller Geschwindigkeit.",
    "Game log: {gpu}, resource binding tier {tier}.": "Spiel-Log: {gpu}, Resource Binding Tier {tier}.",
    "Your processor has {cores} cores": "Dein Prozessor hat {cores} Kerne",
    "The game is made for 4 cores; on {cores} it can stay below 60 frames per second in fights (an i3-3240 reached about 20). Close other programs while you play, keep Windows' power plan on Balanced or High performance, and see \"Low frame rate\" in the help.":
        "Das Spiel ist für 4 Kerne gemacht; mit {cores} kann es in Kämpfen unter 60 Bildern pro Sekunde bleiben (ein i3-3240 kam auf etwa 20). Schließe beim Spielen andere Programme, lass den Energiesparplan von Windows auf „Ausbalanciert“ oder „Höchstleistung“ und sieh unter „Low frame rate“ in der Hilfe nach.",
    "This PC: {cores} cores, {logical} logical processors.":
        "Dieser PC: {cores} Kerne, {logical} logische Prozessoren.",
    "The launcher runs under Wine or Proton": "Der Launcher läuft unter Wine oder Proton",
    "That works, with a few known differences: since 1.1.5 the launcher sets the safe graphics defaults for Wine by itself. A dark blue or black game window (sound playing) means the Proton build does not suit the game: try another one (Proton Experimental, proton-cachyos-slr). See \"Linux and Steam Deck\" in the help.":
        "Das funktioniert, mit ein paar bekannten Unterschieden: Seit 1.1.5 setzt der Launcher die sicheren Grafik-Voreinstellungen für Wine selbst. Ein dunkelblaues oder schwarzes Spielfenster (mit Ton) heißt, dass die Proton-Version nicht zum Spiel passt: Probiere eine andere (Proton Experimental, proton-cachyos-slr). Siehe „Linux and Steam Deck“ in der Hilfe.",
    "This PC: {wine}.": "Dieser PC: {wine}.",
    "Windows Firewall blocks the game": "Die Windows-Firewall blockiert das Spiel",
    "Online matches then often go through a relay (more lag) or do not connect. Open Windows Security > Firewall & network protection > Allow an app through firewall, and allow t5dr.exe (in {folder}) for private and public networks; or remove the block rule for it there.":
        "Online-Matches laufen dann oft über ein Relay (mehr Verzögerung) oder kommen nicht zustande. Öffne Windows-Sicherheit > Firewall- & Netzwerkschutz > Zugriff von App durch Firewall zulassen und erlaube t5dr.exe (in {folder}) für private und öffentliche Netzwerke, oder entferne dort die Blockier-Regel dafür.",
    "Windows Firewall: a block rule or \"Block all incoming connections\" for t5dr.exe.":
        "Windows-Firewall: eine Blockier-Regel oder „Alle eingehenden Verbindungen blockieren“ für t5dr.exe.",
    "Checking the build…": "Prüfe den Build…",
    "Your name (shown in the game)": "Dein Name (im Spiel sichtbar)",
    "PLAY OFFLINE": "OFFLINE SPIELEN",
    "Arcade, Versus, Practice and the other modes on this PC. To play against people over the "
    "internet, use the":
        "Arcade, Versus, Training und die anderen Modi auf diesem PC. Um über das Internet "
        "gegen andere zu spielen, nutze den",
    "Online tab": "Online-Reiter",
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
    "The picture is scaled to the window; how sharp it is depends on Internal resolution. "
    "You can also drag the window's edges. Alt+Enter or F11 switches borderless fullscreen "
    "in the game.":
        "Das Bild wird auf das Fenster skaliert; wie scharf es ist, hängt von der internen "
        "Auflösung ab. Du kannst auch an den Rändern des Fensters ziehen. Alt+Enter oder F11 "
        "schaltet im Spiel auf randloses Vollbild um.",
    "Unlocks": "Freischaltungen",
    "Unlock all stages (the Tekken 5 stages, without clearing Arcade)":
        "Alle Stages freischalten (die Tekken-5-Stages, ohne den Arcade-Modus durchzuspielen)",
    "Unlock Jinpachi and Random select (without clearing Arcade)":
        "Jinpachi und die Random-Auswahl freischalten (ohne den Arcade-Modus durchzuspielen)",
    "Unlock all customization items (free in the item shop)":
        "Alle Customize-Items freischalten (gratis im Item-Shop)",
    "Offline only (Arcade, VS, Practice and the rest). Your save is not changed; items you take for free "
    "stay yours (the save is backed up first, in save-backups). Online, both players always get the "
    "same stages; Jinpachi and Random are there in casual matches and rooms, not in ranked.":
        "Nur offline (Arcade, VS, Practice und der Rest). Dein Spielstand wird nicht verändert; Items, die "
        "du dir gratis nimmst, bleiben dir (der Spielstand wird vorher gesichert, in save-backups). Online "
        "bekommen beide Spieler immer dieselben Stages; Jinpachi und Random gibt es in Casual-Matches und "
        "Räumen, nicht in Ranked.",
    "Sound and start": "Ton und Start",
    "Mute sound": "Ton aus",
    "Sound and taskbar flash when a match is found or someone joins my room": "Ton und Taskleistenblinken, wenn ein Match gefunden wird oder jemand meinem Raum beitritt",
    "Start minimized, without taking focus (for testing)": "Minimiert starten, ohne den Fokus zu nehmen (zum Testen)",
    "Advanced: extra settings, one NAME=VALUE per line":
        "Erweitert: zusätzliche Einstellungen, eine pro Zeile als NAME=WERT",
    "Internal resolution": "Interne Auflösung",
    "VSync": "VSync",
    "On (smooth, default)": "An (flüssig, Standard)",
    "Off (lowest latency, may tear)": "Aus (geringste Verzögerung, Bild kann reißen)",
    "The game always runs at 60 fps, like on the PS3.": "Das Spiel läuft immer mit 60 fps, wie auf der PS3.",
    "Stage blur / glow": "Stage-Unschärfe / Leuchten",
    "Off (default)": "Aus (Standard)",
    "Off": "Aus",
    "Some stages blur the picture (the misty swamp) or let the sun glow. Off shows them sharp, "
    "without the glow. Only your picture changes: online, both players can choose differently.":
        "Manche Stages machen das Bild unscharf (der neblige Sumpf) oder lassen die Sonne leuchten. "
        "Aus zeigt sie scharf, ohne das Leuchten. Nur dein Bild ändert sich: Online können beide "
        "Spieler verschieden wählen.",
    "Training overlay": "Trainings-Anzeige",
    "Also in the other offline modes (Arcade, Versus, ...)": "Auch in den anderen Offline-Modi (Arcade, Versus, ...)",
    "Practice tools": "Trainingswerkzeuge",
    "SELECT combos in Practice (offline only)": "SELECT-Kombinationen im Practice-Modus (nur offline)",
    "Dummy:": "Dummy:",
    "As set in the game's Practice menu": "Wie im Practice-Menü des Spiels eingestellt",
    "Blocks after the first hit": "Blockt nach dem ersten Treffer",
    "Crouches": "Duckt sich",
    "Walks forward and back": "Geht vor und zurück",
    "Sidesteps": "Macht Seitschritte",
    "In Practice, hold SELECT and press: 3 round start; f+3 / b+3 the dummy against the wall in front "
    "of / behind you; df+3 / db+3 you against the wall in front of / behind you. 1 records the dummy "
    "(you play it), 2 plays the recording once, 4 in a loop; tap up / down for slot 1-5, forward / "
    "back for what the dummy does.":
        "Im Practice-Modus SELECT halten und drücken: 3 Rundenstart; f+3 / b+3 der Dummy an der Wand vor "
        "/ hinter dir; df+3 / db+3 du an der Wand vor / hinter dir. 1 nimmt den Dummy auf (du steuerst "
        "ihn), 2 spielt die Aufnahme einmal ab, 4 in Schleife; oben / unten tippen für Platz 1-5, vor / "
        "zurück für das, was der Dummy tut.",
    "Also online (only your own inputs, no frame data)": "Auch online (nur deine eigenen Eingaben, keine Framedaten)",
    "In Practice: your last inputs with how many frames each was held, and after each exchange the "
    "startup of the move and who can act first (+3, -12). F2 in the game switches it.":
        "Im Practice-Modus: deine letzten Eingaben, jede mit der Zahl der Frames, die sie gehalten wurde, "
        "und nach jedem Schlagabtausch der Startup des Moves und wer zuerst wieder handeln kann (+3, -12). "
        "F2 im Spiel schaltet sie um.",
    "Your screen: {width} x {height}. In fullscreen, {step} matches it.":
        "Dein Bildschirm: {width} x {height}. Im Vollbild passt {step} dazu.",
    "Online input delay": "Online-Input-Delay",
    "Frames. Auto: 1 up to about 60 ms ping, 2 above. 0/1/2 count only when your "
    "opponent picked the same, otherwise Auto. Ranked matches always use 2.":
        "Frames. Auto: 1 bis etwa 60 ms Ping, darüber 2. 0/1/2 gelten nur, wenn dein Gegner "
        "dasselbe gewählt hat, sonst Auto. Ranked-Matches nutzen immer 2.",
    "Open the game's port on my router during online matches (UPnP / NAT-PMP / PCP)":
        "Den Port des Spiels während Online-Matches am Router öffnen (UPnP / NAT-PMP / PCP)",
    "Helps the direct connection when your opponent's router is strict. The port is open only while "
    "you play and is closed again afterwards.":
        "Hilft bei der direkten Verbindung, wenn der Router deines Gegners streng ist. Der Port ist nur "
        "offen, während du spielst, und wird danach wieder geschlossen.",
    "Set up controllers…": "Controller einstellen…",
    "Pick a pad, stick or hitbox, press the buttons you want for 1 2 3 4 and the rest, "
    "or start from a layout.":
        "Wähle ein Pad, einen Stick oder eine Hitbox, drücke die Tasten, die du für 1 2 3 4 "
        "und den Rest willst, oder starte von einem Layout.",
    "(needs the lobby files, which are missing)": "(braucht die Lobby-Dateien, die fehlen)",
    "Action (Tekken default)": "Aktion (Tekken-Standard)",
    "PS3 button": "PS3-Taste",
    "Keyboard": "Tastatur",
    "Xbox controller": "Xbox-Controller",
    "Keyboard and the first XInput controller both drive player 1 (they are combined). "
    "The keyboard only counts while the game window has focus. The game's own Options menu can change "
    "the button layout for offline play; online games use the launcher's buttons only.":
        "Tastatur und der erste XInput-Controller steuern beide Spieler 1 (sie werden "
        "zusammengelegt). Die Tastatur gilt nur, solange das Spielfenster den Fokus hat. Das "
        "Options-Menü des Spiels kann die Tastenbelegung für das Spielen offline ändern; online "
        "gelten nur die Tasten aus dem Launcher.",
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
    "Click Report a problem.": "Klicke auf „Problem melden...“.",
    "The game closed.": "Das Spiel wurde geschlossen.",
    "A build is running. Stop it and quit?": "Das Bauen läuft noch. Stoppen und beenden?",
    # ---- launcher/updater.py
    "Check for updates": "Nach Updates suchen",
    "Updated from {old} to {new}.": "Von {old} auf {new} aktualisiert.",
    "the new version": "die neue Version",
    "The update to {version} failed and could not be undone completely: {error}.\n\nThe "
    "old program files are in\n{folder}\nYour game, saves and settings (the native "
    "folder) were not touched. Download the zip from the releases page and extract it "
    "over this folder.":
        "Das Update auf {version} ist fehlgeschlagen und konnte nicht ganz rückgängig "
        "gemacht werden: {error}.\n\nDie alten Programmdateien liegen in\n{folder}\nDein "
        "Spiel, deine Spielstände und Einstellungen (der Ordner native) wurden nicht "
        "angefasst. Lade die Zip-Datei von der Releases-Seite herunter und entpacke sie über "
        "diesen Ordner.",
    "The update to {version} did not work: {error}.\n\nNothing was changed; this is "
    "still version {current}. Try again later, or download the zip from the releases "
    "page.":
        "Das Update auf {version} hat nicht geklappt: {error}.\n\nEs wurde nichts geändert; "
        "das ist weiterhin Version {current}. Versuche es später noch einmal, oder lade die "
        "Zip-Datei von der Releases-Seite herunter.",
    "Update": "Update",
    "Updates": "Updates",
    "This is a development checkout (no release.json and bundled Python), so it does not "
    "update itself. Use git, or a release zip from\n{page}":
        "Das ist ein Entwickler-Checkout (ohne release.json und ohne mitgeliefertes Python), "
        "darum aktualisiert er sich nicht selbst. Nimm Git oder eine Release-Zip von\n{page}",
    "Update to {version}…": "Auf {version} aktualisieren…",
    "Could not check for updates.\n\n{problem}": "Die Suche nach Updates hat nicht geklappt.\n\n{problem}",
    "Version {version} is available: click 'Update to {version}' at the top.":
        "Version {version} ist da: Klicke oben auf „Auf {version} aktualisieren“.",
    "You have the newest version ({version}).": "Du hast die neueste Version ({version}).",
    "Update available": "Update verfügbar",
    "T5DR Online {version} is available": "T5DR Online {version} ist da",
    "Download: {size}, published {date}.": "Download: {size}, veröffentlicht {date}.",
    "Download: {size}.": "Download: {size}.",
    "You have {version}.": "Du hast {version}.",
    "The launcher downloads it, checks it, replaces its program files and starts again. "
    "Your game, saves and settings (the native folder) stay as they are.":
        "Der Launcher lädt es herunter, prüft es, ersetzt seine Programmdateien und startet "
        "neu. Dein Spiel, deine Spielstände und Einstellungen (der Ordner native) bleiben, "
        "wie sie sind.",
    "After this update the game is built once more (about 2 minutes): the Play tab "
    "offers BUILD GAME. Only the code is rebuilt; the unpacked game and saves are kept.":
        "Nach diesem Update wird das Spiel noch einmal gebaut (etwa 2 Minuten): Der Reiter "
        "Spielen bietet BUILD GAME an. Nur der Code wird neu gebaut; das entpackte Spiel und "
        "deine Spielstände bleiben erhalten.",
    "The game itself does not need to be built again.": "Das Spiel selbst muss nicht neu gebaut werden.",
    "If this update changes the game code, the Play tab asks you to build the game once "
    "(about 2 minutes).":
        "Ändert dieses Update den Spielcode, bittet dich der Reiter Spielen, das Spiel "
        "einmal zu bauen (etwa 2 Minuten).",
    "(no release notes)": "(keine Release-Notes)",
    "Update now": "Jetzt aktualisieren",
    "Later": "Später",
    "Release page": "Release-Seite",
    "Cancelling…": "Breche ab…",
    "Downloading…": "Lade herunter…",
    "Unexpected error: {error}": "Unerwarteter Fehler: {error}",
    "Downloading… {done} of {total}": "Lade herunter… {done} von {total}",
    "Downloading… {done}": "Lade herunter… {done}",
    "Checking the download (SHA-256)…": "Prüfe den Download (SHA-256)…",
    "Unpacking… {percent}%": "Entpacke… {percent}%",
    "Preparing the restart…": "Bereite den Neustart vor…",
    "Try again": "Noch einmal versuchen",
    "Could not start the update step: {error}": "Der Update-Schritt konnte nicht gestartet werden: {error}",
    "Installing {version}: the launcher restarts in a few seconds…":
        "Installiere {version}: Der Launcher startet in ein paar Sekunden neu…",
    "Updating to {version}…": "Aktualisiere auf {version}…",
    # ---- lobby/t5lobby/client.py
    "Contacting the lobby server over UDP...": "Verbinde mit dem Lobby-Server über UDP...",
    "UDP to the lobby server is blocked (firewall?)": "UDP zum Lobby-Server ist blockiert (Firewall?)",
    "Connecting to your opponent...": "Verbinde mit deinem Gegner...",
    "Measuring the connection...": "Messe die Verbindung...",
    "Direct connection not possible; using the lobby server's relay...":
        "Direkte Verbindung nicht möglich; nutze das Relay des Lobby-Servers...",
    "Direct connection found: the match no longer goes through the lobby server.":
        "Direkte Verbindung gefunden: Das Match läuft nicht mehr über den Lobby-Server.",
    "The direct connection was lost; back on the lobby server's relay.":
        "Die direkte Verbindung ist abgerissen; es geht wieder über das Relay des Lobby-Servers.",
    "Direct connection not possible; using the relay server {name}...":
        "Direkte Verbindung nicht möglich; nutze den Relay-Server {name}...",
    "Direct connection found: the match no longer goes through the relay server {name}.":
        "Direkte Verbindung gefunden: Das Match läuft nicht mehr über den Relay-Server {name}.",
    "The direct connection was lost; back on the relay server {name}.":
        "Die direkte Verbindung ist abgerissen; es geht wieder über den Relay-Server {name}.",
    # ---- lobby/t5lobby/dialogs.py
    "No": "Nein",
    "Yes": "Ja",
    "OK": "OK",
    # ---- lobby/t5lobby/fighters.py
    "Random": "Zufall",
    "Western Gate": "Western Gate",
    "Autumn Temple": "Autumn Temple",
    "Meteor Shower": "Meteor Shower",
    "Ghetto Pit": "Ghetto Pit",
    "City Lights": "City Lights",
    "Great Plains": "Great Plains",
    "Galleon": "Galleon",
    "All Hollow's Eve": "All Hollow's Eve",
    "Winter Palace": "Winter Palace",
    "Festival": "Festival",
    "Aurora Australis": "Aurora Australis",
    "Heaven's Gate": "Heaven's Gate",
    "Space Colony": "Space Colony",
    "Pool Party": "Pool Party",
    "Playroom": "Playroom",
    "Wolves' Den": "Wolves' Den",
    "Industrial Complex": "Industrial Complex",
    "Ominous Mist": "Ominous Mist",
    "Dragon's Nest": "Dragon's Nest",
    "Burning Temple": "Burning Temple",
    "Waterfall": "Waterfall",
    "Urban Jungle": "Urban Jungle",
    "City at Sunset": "City at Sunset",
    "Moonlit Wilderness": "Moonlit Wilderness",
    "Pirate's Cove": "Pirate's Cove",
    "Secret Garden": "Secret Garden",
    "Cathedral": "Cathedral",
    "Acid Rain": "Acid Rain",
    "Polar Paradise": "Polar Paradise",
    "Hell's Gate": "Hell's Gate",
    "Final Frontier": "Final Frontier",
    "Poolside": "Poolside",
    "Final Stage": "Final Stage",
    "Stage {number}": "Stage {number}",
    "Tekken 5 stage {number}": "Tekken-5-Stage {number}",
    # ---- lobby/t5lobby/handover.py
    "direct connection": "direkte Verbindung",
    "local network": "lokales Netzwerk",
    "through the lobby server": "über den Lobby-Server",
    "through the relay server {name}": "über den Relay-Server {name}",
    "{name} -- {how}, ping {ms} ms, input delay {delay}": "{name} -- {how}, Ping {ms} ms, Input-Delay {delay}",
    # ---- lobby/t5lobby/i18n_known.py
    "login timeout": "Zeitlimit beim Anmelden",
    "idle timeout": "Zeitlimit: zu lange nichts getan",
    "banned from this server": "von diesem Server gesperrt",
    "too many connections": "zu viele Verbindungen",
    "server full": "Server voll",
    "slow down": "Nicht so schnell",
    "bad request": "Ungültige Anfrage",
    "the server is busy; try again in a few seconds": "Der Server ist gerade ausgelastet; versuch es in ein paar Sekunden noch einmal",
    "the chat is busy; try again in a moment": "Der Chat ist gerade ausgelastet; versuch es gleich noch einmal",
    "that name looks too much like the account {other}": "Der Name ist dem Konto {other} zu ähnlich",
    "that name looks too much like {name}, who is online": "Der Name ist zu ähnlich wie {name} (gerade online)",
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
    "too many password changes; wait a minute": "zu viele Passwortänderungen; warte eine Minute",
    "too many requests for new codes; wait a minute": "zu viele Anfragen nach neuen Codes; warte eine Minute",
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
    "the ranked set goes on by itself": "Das Ranked-Set geht von selbst weiter",
    "you are in a ranked set ({mine}-{theirs}); leave it first (that counts as a loss)":
        "Du bist in einem Ranked-Set ({mine}-{theirs}); verlass es zuerst (das zählt als Niederlage)",
    "that player is in a ranked set": "Dieser Spieler ist gerade in einem Ranked-Set",
    "you are not in a ranked set": "Du bist in keinem Ranked-Set",
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
    "guests cannot have friends; create an account (free)":
        "Gäste können keine Freunde haben; erstelle ein (kostenloses) Konto",
    "there is no account with that name": "Es gibt kein Konto mit diesem Namen",
    "you cannot add yourself": "Du kannst dich nicht selbst hinzufügen",
    "you blocked that player; unblock them first":
        "Du hast diesen Spieler blockiert; hebe die Blockierung zuerst auf",
    "your friends list is full ({max})": "Deine Freundesliste ist voll ({max})",
    "your last invite to that friend ended a moment ago; try again in {seconds} s":
        "Deine letzte Einladung an diesen Freund ist gerade erst zu Ende; versuch es in {seconds} s wieder",
    "your last challenge to that player ended a moment ago; try again in {seconds} s":
        "Deine letzte Herausforderung an diesen Spieler ist gerade erst zu Ende; versuch es in {seconds} s wieder",
    "too many friend requests from this internet address today; try again tomorrow":
        "Zu viele Freundschaftsanfragen von dieser Internetadresse heute; versuche es morgen wieder",
    "you can send {count} friend requests a day; try again tomorrow":
        "Du kannst {count} Freundschaftsanfragen am Tag senden; versuche es morgen wieder",
    "{count} of your friend requests are waiting for an answer; cancel some first":
        "{count} deiner Freundschaftsanfragen warten auf eine Antwort; ziehe zuerst ein paar zurück",
    "{name} declined your last request; you can ask again in {days} day(s)":
        "{name} hat deine letzte Anfrage abgelehnt; du kannst in {days} Tag(en) wieder anfragen",
    "that player has too many friend requests waiting": "Bei diesem Spieler warten zu viele Freundschaftsanfragen",
    "that player's friends list is full": "Die Freundesliste dieses Spielers ist voll",
    "no friend request from that player": "Keine Freundschaftsanfrage von diesem Spieler",
    "no friend request to that player": "Keine Freundschaftsanfrage an diesen Spieler",
    "that player is not on your friends list": "Dieser Spieler ist nicht in deiner Freundesliste",
    "that friend is not online": "Dieser Freund ist nicht online",
    "that friend's launcher is too old for invites (it needs 1.1.2 or newer)":
        "Der Launcher dieses Freundes ist zu alt für Einladungen (er braucht 1.1.2 oder neuer)",
    "create a room first, then invite": "Erstelle zuerst einen Raum, dann lade ein",
    "that friend is busy right now": "Dieser Freund ist gerade beschäftigt",
    "one invite at a time": "Immer nur eine Einladung",
    "wait a moment before inviting again": "Warte einen Moment, bevor du wieder einlädst",
    "that player has invites pending": "Dieser Spieler hat noch offene Einladungen",
    "that invite is over": "Diese Einladung ist vorbei",
    "the invite is no longer possible": "Die Einladung ist nicht mehr möglich",
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
    "the server sent a malformed match id": "Der Server hat eine ungültige Match-ID geschickt",
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
    # 1.1.5: the package's version, read before the build (tools/build_game.py, launcher/core.py)
    "This package is version {version} of the game (program content ID {id}). The port supports only version "
    "{supported}: {game}, content ID {cid}, {size} bytes. This version cannot be used, whatever the license "
    "(.rap).":
        "Dieses Paket ist Version {version} des Spiels (Content-ID des Programms {id}). Der Port unterstützt nur "
        "Version {supported}: {game}, Content-ID {cid}, {size} Bytes. Diese Version lässt sich nicht verwenden, "
        "mit keiner Lizenz (.rap).",
    "{id}  ({size} bytes) -- version {version} of the game. The port supports only version {supported}; the "
    "build will refuse this package.":
        "{id}  ({size} Bytes) -- Version {version} des Spiels. Der Port unterstützt nur Version {supported}; das "
        "Bauen wird dieses Paket ablehnen.",
    "{id}  ({size} bytes) -- its program has content ID {program}, not the supported one ({supported}). The "
    "build will most likely refuse it.":
        "{id}  ({size} Bytes) -- sein Programm hat die Content-ID {program}, nicht die unterstützte "
        "({supported}). Das Bauen wird es wahrscheinlich ablehnen.",
    # 1.1.5: the game's own message boxes (launcher/core.py dialog_info, dialog_message)
    "The game shows: \"{text}\" {advice}": "Das Spiel zeigt: „{text}“ {advice}",
    "Your built game data is probably damaged. Open the Build tab, tick \"Redo every step\" and press BUILD "
    "GAME. If the message comes back, download the package again: it must be exactly {size} bytes.":
        "Deine gebauten Spieldaten sind wahrscheinlich beschädigt. Öffne den Reiter Bauen, setz den Haken bei "
        "„Alle Schritte neu machen“ und drück BUILD GAME. Kommt die Meldung wieder, lade das Paket neu herunter: "
        "Es muss genau {size} Bytes groß sein.",
    "The game could not write its save, so progress may be lost. Check that the disk is not full and that no "
    "antivirus blocks the folder native\\gamedata.":
        "Das Spiel konnte seinen Spielstand nicht schreiben, Fortschritt kann verloren gehen. Prüf, ob die "
        "Festplatte voll ist und ob ein Virenschutz den Ordner native\\gamedata sperrt.",
    "The game could not read its save. If it happens every time, click Report a problem.":
        "Das Spiel konnte seinen Spielstand nicht lesen. Passiert das jedes Mal, klicke auf „Problem melden...“.",
    "If the game does not go on, click Report a problem.":
        "Geht das Spiel nicht weiter, klicke auf „Problem melden...“.",
    # 1.1.5: the launcher's --search ranked|casual (lobby/t5lobby/tk_tab.py search_on_start)
    "Build the game first (Build tab); then the search starts by itself next time.":
        "Bau zuerst das Spiel (Reiter Bauen); beim nächsten Mal startet die Suche dann von selbst.",
    "Log in to start the search. Tick \"Remember me\" when you log in with your account: next time --search "
    "logs in and starts searching by itself.":
        "Melde dich an, um die Suche zu starten. Setz beim Anmelden mit deinem Konto den Haken bei „Angemeldet "
        "bleiben“: Beim nächsten Mal meldet --search dich an und startet die Suche von selbst.",
    "Ranked matches need an account: log in with your name and password.":
        "Ranked-Matches brauchen ein Konto: Melde dich mit Name und Passwort an.",
    # 1.1.5: a build step that prints nothing for long (launcher/core.py step_quiet_hint)
    "The step \"{title}\" has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, press Cancel and then BUILD GAME again; build.log has the details.":
        "Der Schritt „{title}“ hat seit {minutes} Minuten nichts ausgegeben. Auf einem langsamen oder "
        "ausgelasteten PC kann er noch arbeiten. Wenn sich nichts tut, klicke auf Abbrechen und dann wieder auf "
        "BUILD GAME; build.log hat die Details.",
    "Last program started: {tool}.": "Zuletzt gestartetes Programm: {tool}.",
    "The license (.rap) does not belong to this package. Use the .rap whose name matches "
    "the package's content ID ({id}).":
        "Die Lizenz (.rap) gehört nicht zu diesem Paket. Nimm die .rap, deren Name zur "
        "Content-ID des Pakets passt ({id}).",
    "Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press BUILD GAME "
    "again; if it fails again, check that the package is {size} bytes.":
        "Das Entschlüsseln des Spielprogramms ist fehlgeschlagen (siehe Log oben). Setz den Haken bei "
        "\"Alle Schritte neu machen\" und drück noch einmal BUILD GAME; klappt es wieder nicht, prüf, "
        "ob das Paket {size} Bytes groß ist.",
    "The package is {size} bytes, the supported one is {supported} bytes: the download is incomplete or it is "
    "a different file. Download it again.":
        "Das Paket ist {size} Bytes groß, das unterstützte {supported} Bytes: Der Download ist unvollständig "
        "oder es ist eine andere Datei. Lade es noch einmal herunter.",
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
    "CMake and Ninja were not found. On macOS: brew install cmake ninja sdl2 glslang spirv-cross":
        "CMake und Ninja wurden nicht gefunden. Unter macOS: brew install cmake ninja sdl2 glslang "
        "spirv-cross",
    "glslang and spirv-cross were not found; the game's shaders need them. "
    "On macOS: brew install glslang spirv-cross":
        "glslang und spirv-cross wurden nicht gefunden; die Shader des Spiels brauchen sie. "
        "Unter macOS: brew install glslang spirv-cross",
    "Building the game is supported on Windows and macOS only.":
        "Das Spiel lässt sich nur unter Windows und macOS bauen.",
    "This Python refuses pip install (PEP 668; Homebrew's does). Use a virtual environment: python3 -m venv .venv && .venv/bin/pip install pycryptodome, then run the tools with .venv/bin/python.":
        "Dieses Python verweigert pip install (PEP 668; das von Homebrew tut das). Verwende eine virtuelle Umgebung: python3 -m venv .venv && .venv/bin/pip install pycryptodome, und starte die Tools dann mit .venv/bin/python.",
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
    "System information and the settings you use": "Systeminformationen und die Einstellungen, die du nutzt",
    "What happened (what you wrote)": "Was passiert ist (was du geschrieben hast)",
    "Launcher log": "Launcher-Log",
    "Game log (the newest one)": "Spiel-Log (das neueste)",
    "Game log (the newest {count})": "Spiel-Log (die neuesten {count})",
    "Build log": "Build-Log",
    "Build log (the last build went fine)": "Build-Log (der letzte Build lief gut)",
    "Online: the files of the last match": "Online: die Dateien des letzten Matches",
    "controls.ini (your button settings)": "controls.ini (deine Tastenbelegung)",
    "Desync dumps (game state numbers, binary)": "Desync-Dumps (Zahlen des Spielzustands, binär)",
    "The last replay (the inputs of the last online session, without names)":
        "Das letzte Replay (die Eingaben der letzten Online-Sitzung, ohne Namen)",
    "could not be cleaned of private data": "ließ sich nicht von privaten Daten säubern",
    "no room left in the size limit": "kein Platz mehr im Größenlimit",
    "could not be read": "ließ sich nicht lesen",
    "The launcher cannot write next to its folder or into it, so it cannot update "
    "itself. Download the zip from the releases page instead.":
        "Der Launcher kann neben seinem Ordner und in ihm nicht schreiben, darum kann er "
        "sich nicht selbst aktualisieren. Lade stattdessen die Zip-Datei von der "
        "Releases-Seite herunter.",
    "Refused to download from {host}: not this project's GitHub releases.":
        "Download von {host} abgelehnt: Das sind nicht die GitHub-Releases dieses Projekts.",
    "The download came from {host}. Nothing was changed.": "Der Download kam von {host}. Es wurde nichts geändert.",
    "GitHub did not return a published release.": "GitHub hat kein veröffentlichtes Release geliefert.",
    "The latest release has an unexpected version ({tag}).":
        "Das neueste Release hat eine unerwartete Version ({tag}).",
    "Release {version} has no {name} with SHA256SUMS yet.": "Release {version} hat noch kein {name} mit SHA256SUMS.",
    "The downloaded release does not say it is version {version}. Nothing was changed.":
        "Das heruntergeladene Release sagt nicht, dass es Version {version} ist. Es wurde "
        "nichts geändert.",
    "The downloaded release has no launcher. Nothing was changed.":
        "Dem heruntergeladenen Release fehlt der Launcher. Es wurde nichts geändert.",
    "This folder has no python\\pythonw.exe, so the launcher cannot update itself (a "
    "development checkout?). Download the zip from the releases page instead.":
        "In diesem Ordner fehlt python\\pythonw.exe, darum kann sich der Launcher nicht "
        "selbst aktualisieren (ein Entwickler-Checkout?). Lade stattdessen die Zip-Datei von "
        "der Releases-Seite herunter.",
    "The download was sent to {host}, which is not GitHub's storage for this project. "
    "Nothing was changed.":
        "Der Download wurde an {host} geschickt, das nicht der GitHub-Speicher dieses "
        "Projekts ist. Es wurde nichts geändert.",
    "Release {version}: {name} is not on this project's GitHub releases.":
        "Release {version}: {name} gibt es nicht in den GitHub-Releases dieses Projekts.",
    "Release {version}: {name} is still being uploaded.": "Release {version}: {name} wird noch hochgeladen.",
    "The download stopped early ({done} of {total} bytes). Try again.":
        "Der Download ist zu früh abgebrochen ({done} von {total} Bytes). Versuche es noch "
        "einmal.",
    "The download is not a readable zip ({error}). Nothing was changed.":
        "Der Download ist keine lesbare Zip-Datei ({error}). Es wurde nichts geändert.",
    "The download unpacks to far more than a release should. Nothing was changed.":
        "Der Download enthält viel mehr Daten, als ein Release haben sollte. Es wurde nichts "
        "geändert.",
    "Not enough free disk space: the update needs about {need} MB next to the folder, "
    "{free} MB are free.":
        "Nicht genug freier Speicherplatz: Das Update braucht etwa {need} MB neben dem "
        "Ordner, frei sind {free} MB.",
    "SHA256SUMS of release {version} has no line for {name}. Nothing was changed.":
        "In SHA256SUMS von Release {version} steht keine Zeile für {name}. Es wurde nichts "
        "geändert.",
    "SHA256SUMS and GitHub disagree about the download's checksum. Nothing was changed.":
        "SHA256SUMS und GitHub sind sich über die Prüfsumme des Downloads nicht einig. Es "
        "wurde nichts geändert.",
    "The download is damaged or not the published file: its SHA-256 is {got}..., "
    "SHA256SUMS says {want}.... Nothing was changed.":
        "Der Download ist beschädigt oder nicht die veröffentlichte Datei: Seine SHA-256 ist "
        "{got}..., SHA256SUMS sagt {want}.... Es wurde nichts geändert.",
    "The downloaded release has no python\\pythonw.exe. Nothing was changed.":
        "Dem heruntergeladenen Release fehlt python\\pythonw.exe. Es wurde nichts geändert.",
    "The download is far bigger than a release should be. Nothing was changed.":
        "Der Download ist viel größer, als ein Release sein sollte. Es wurde nichts "
        "geändert.",
    "The download contains an unexpected path ({name}: {why}). Nothing was changed.":
        "Der Download enthält einen unerwarteten Pfad ({name}: {why}). Es wurde nichts "
        "geändert.",
    "The download contains an unexpected path ({name}). Nothing was changed.":
        "Der Download enthält einen unerwarteten Pfad ({name}). Es wurde nichts geändert.",
    "Cancelled.": "Abgebrochen.",
    "Could not download or unpack the update ({error}). Nothing was changed.":
        "Das Update konnte nicht heruntergeladen oder entpackt werden ({error}). Es wurde "
        "nichts geändert.",
    "The download is damaged ({error}). Nothing was changed.":
        "Der Download ist beschädigt ({error}). Es wurde nichts geändert.",
    "the new release contains {names} (the player's files)": "das neue Release enthält {names} (Dateien des Spielers)",
    "release.json does not say {version} after the swap": "release.json nennt nach dem Tausch nicht {version}",
    "launcher\\t5dr_launcher.pyw is missing after the swap": "launcher\\t5dr_launcher.pyw fehlt nach dem Tausch",
    "python\\pythonw.exe is missing after the swap": "python\\pythonw.exe fehlt nach dem Tausch",
    "the update plan is incomplete": "der Update-Plan ist unvollständig",
    "the launcher did not close": "der Launcher wurde nicht geschlossen",
    "programs from the folder were still running ({names}); close them and try again":
        "Programme aus dem Ordner liefen noch ({names}); schließe sie und versuche es noch "
        "einmal",
    "the new launcher {version} did not start": "der neue Launcher {version} ist nicht gestartet",
    "could not replace the program files: {error}": "die Programmdateien konnten nicht ersetzt werden: {error}",
    "unexpected error: {error}": "unerwarteter Fehler: {error}",
    "GitHub asks to wait with update checks until {time}.":
        "GitHub bittet, mit der Update-Suche bis {time} zu warten.",
    "GitHub limits update checks right now. Try again later.":
        "GitHub begrenzt gerade die Update-Suchen. Versuche es später noch einmal.",
    "GitHub answered with error {code}. Try again later.":
        "GitHub hat mit Fehler {code} geantwortet. Versuche es später noch einmal.",
    "No connection to GitHub. Check the internet connection and try again.":
        "Keine Verbindung zu GitHub. Prüfe die Internetverbindung und versuche es noch "
        "einmal.",
    "A build is running. Update when it is finished.": "Das Bauen läuft noch. Aktualisiere, wenn es fertig ist.",
    "The game is running. Close it first, then update.": "Das Spiel läuft. Schließe es zuerst, dann aktualisiere.",
    "'Host for friends' is running. Stop hosting first, then update.":
        "„Für Freunde hosten“ läuft. Beende zuerst das Hosten, dann aktualisiere.",
    "An online match was found. Update after the match.":
        "Ein Online-Match wurde gefunden. Aktualisiere nach dem Match.",
    "An online match is running. Update after the match.": "Ein Online-Match läuft. Aktualisiere nach dem Match.",
    "You are searching for or playing an online match. Update afterwards.":
        "Du suchst ein Online-Match oder spielst gerade eins. Aktualisiere danach.",
    "Other programs from this folder are still running ({names}): another launcher "
    "window, the game or a lobby server. Close them, then update.":
        "Andere Programme aus diesem Ordner laufen noch ({names}): ein anderes "
        "Launcher-Fenster, das Spiel oder ein Lobby-Server. Schließe sie, dann aktualisiere.",
    "not a plain relative path": "kein einfacher relativer Pfad",
    "'.', '..' or an empty part": "„.“, „..“ oder ein leerer Teil",
    "outside the folder {folder}": "außerhalb des Ordners {folder}",
    "named like the player's own files": "heißt wie die eigenen Dateien des Spielers",
    "a name Windows does not keep as written": "ein Name, den Windows nicht so speichert, wie er geschrieben ist",
    "Release {version} is a test version; it is not installed automatically.":
        "Release {version} ist eine Testversion; sie wird nicht automatisch installiert.",
    "Release {version} is not signed with the project's release key (no SHA256SUMS.sig). It was not made by "
    "the project's release process; nothing was changed.":
        "Release {version} ist nicht mit dem Release-Schlüssel des Projekts signiert (keine SHA256SUMS.sig). Es "
        "stammt nicht aus dem Release-Ablauf des Projekts; es wurde nichts geändert.",
    "Release {version} failed the signature check ({error}). It was not made by the project's release "
    "process; nothing was changed.":
        "Release {version} hat die Signaturprüfung nicht bestanden ({error}). Es stammt nicht aus dem "
        "Release-Ablauf des Projekts; es wurde nichts geändert.",
    "idle": "frei",
    "room": "im Raum",
    "queue": "in der Suche",
    "match": "im Match",
    "playing": "im Spiel",
    # ---- lobby/t5lobby/discord_rpc.py
    "In lobby": "In der Lobby",
    "Searching ranked": "Sucht ein Ranked-Match",
    "Searching quick match": "Sucht ein Quick Match",
    "Ranked, Set {mine}-{theirs}": "Ranked-Set {mine}-{theirs}",
    "Ranked": "Ranked",
    "Casual": "Casual",
    "In match: {mine} vs {theirs} ({what})": "Im Match: {mine} vs {theirs} ({what})",
    "In match ({what})": "Im Match ({what})",
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
    "This match lagged: the games waited {secs} s for each other's inputs.":
        "Dieses Match hat gelaggt: Die Spiele haben {secs} s auf die Eingaben des anderen gewartet.",
    "A wired connection and no uploads during matches help.":
        "Ein LAN-Kabel statt WLAN und keine Uploads während der Matches helfen.",
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "Dein Gegner hat das Spiel geschlossen.",
    "The connection to your opponent's game was lost.": "Die Verbindung zum Spiel deines Gegners ist abgebrochen.",
    "Your opponent's game stopped responding.": "Das Spiel deines Gegners reagiert nicht mehr.",
    "Your opponent's game did not get to the fight.": "Das Spiel deines Gegners hat es nicht bis zum Kampf geschafft.",
    "Your opponent's game was restarted; the match cannot go on.":
        "Das Spiel deines Gegners wurde neu gestartet; das Match kann nicht weitergehen.",
    "Loading the fight took too long on this PC (slow disk or a busy PC?); the match was stopped.":
        "Das Laden des Kampfs hat auf diesem PC zu lange gedauert (langsame Festplatte oder ausgelasteter "
        "PC?); das Match wurde abgebrochen.",
    "Loading the fight took too long on your opponent's PC; the match was stopped.":
        "Das Laden des Kampfs hat auf dem PC deines Gegners zu lange gedauert; das Match wurde abgebrochen.",
    "Your opponent's game could not be reached (firewall or router?).":
        "Das Spiel deines Gegners war nicht erreichbar (Firewall oder Router?).",
    "Your opponent's game is a different build.": "Das Spiel deines Gegners ist ein anderer Build.",
    "Your opponent's game is in another match.": "Das Spiel deines Gegners ist in einem anderen Match.",
    "The game could not open its network port (another program uses it?).":
        "Das Spiel konnte seinen Netzwerk-Port nicht öffnen (nutzt ihn ein anderes "
        "Programm?).",
    "You closed the game during the match: it counts as a loss.":
        "Du hast das Spiel während des Matches geschlossen: Das zählt als Niederlage.",
    "The game could not get back to character select and closed itself; it starts again for your next match.":
        "Das Spiel kam nicht zur Charakterauswahl zurück und hat sich beendet; zu deinem nächsten Match startet es neu.",
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
    "{wins}W {losses}L": "{wins}W {losses}L",
    "{draws}D": "{draws}D",
    "{rank} (placement {done}/{total})": "{rank} (Platzierung {done}/{total})",
    # ---- lobby/t5lobby/sets.py
    "a game was too short to count": "ein Spiel war zu kurz, um zu zählen",
    "a fight ended without a winner": "ein Kampf endete ohne Sieger",
    "too many games without a winner": "zu viele Spiele ohne Sieger",
    "left after the lag check": "nach dem Lag-Check verlassen",
    "the lobby server restarted": "der Lobby-Server wurde neu gestartet",
    "a player left right away": "ein Spieler ist sofort gegangen",
    "the next game could not start": "das nächste Spiel konnte nicht starten",
    "a player left before a game counted": "ein Spieler ist gegangen, bevor ein Spiel gezählt hat",
    "a player lost the lobby connection": "ein Spieler hat die Verbindung zur Lobby verloren",
    "set won": "Set gewonnen",
    "set lost": "Set verloren",
    "Set {mine}-{theirs}": "Set {mine}-{theirs}",
    "game {number} of {best}": "Spiel {number} von {best}",
    "game {number} of {best} again (no winner)": "Spiel {number} von {best} noch einmal (kein Sieger)",
    "starts in {seconds} s": "startet in {seconds} s",
    "The set does not count ({why}); no rating change": "Das Set zählt nicht ({why}); keine Wertungsänderung",
    "The set does not count; no rating change": "Das Set zählt nicht; keine Wertungsänderung",
    "You won the set (your opponent left it)": "Du hast das Set gewonnen (dein Gegner hat es verlassen)",
    "You won the set": "Du hast das Set gewonnen",
    "You lost the set (you left it)": "Du hast das Set verloren (du hast es verlassen)",
    "You lost the set": "Du hast das Set verloren",
    "You won the set {mine}-{theirs}": "Du hast das Set {mine}-{theirs} gewonnen",
    "You lost the set {mine}-{theirs}": "Du hast das Set {mine}-{theirs} verloren",
    "set game {number}": "Set-Spiel {number}",
    # ---- lobby/t5lobby/tk_tour.py, tour_text.py (tournaments)
    "A set is played like a casual set with the in-game select; results come from the games. Players who do not accept a called set in time are out.": "Ein Set läuft wie ein lockeres Set mit der Auswahl im Spiel; die Ergebnisse kommen aus den Spielen. Wer ein aufgerufenes Set nicht rechtzeitig annimmt, scheidet aus.",
    "Accepted. Waiting for {name}...": "Angenommen. Warte auf {name}...",
    "Bracket": "Turnierbaum",
    "CALLED": "AUFGERUFEN",
    "Cancel tournament": "Turnier absagen",
    "Cancel {name}? Nobody can play it any more.": "{name} absagen? Dann kann es niemand mehr spielen.",
    "Cancelled": "Abgesagt",
    "Champion: {name}": "Sieger: {name}",
    "Check in": "Einchecken",
    "Check-in": "Check-in",
    "Check-in 10 minutes before": "Check-in 10 Minuten vorher",
    "Check-in 15 minutes before": "Check-in 15 Minuten vorher",
    "Check-in 30 minutes before": "Check-in 30 Minuten vorher",
    "Check-in 5 minutes before": "Check-in 5 Minuten vorher",
    "Check-in 60 minutes before": "Check-in 60 Minuten vorher",
    "Check-in for {name} is open: check in on the Tournaments page, or you are not in the bracket.": "Der Check-in für {name} ist offen: checke auf der Seite Turniere ein, sonst bist du nicht im Turnierbaum.",
    "Checked in.": "Eingecheckt.",
    "Click a set in the bracket.": "Klicke ein Set im Turnierbaum an.",
    "Create": "Anlegen",
    "Create tournament": "Turnier anlegen",
    "Create...": "Anlegen...",
    "Disqualify": "Disqualifizieren",
    "Disqualify which player (name)?": "Welchen Spieler disqualifizieren (Name)?",
    "Disqualify...": "Disqualifizieren...",
    "Double elimination": "Double Elimination",
    "Final": "Finale",
    "Finished": "Beendet",
    "First to 2 games (best of 3)": "Wer zuerst 2 Spiele gewinnt (Best of 3)",
    "First to 3 games (best of 5)": "Wer zuerst 3 Spiele gewinnt (Best of 5)",
    "Format": "Format",
    "Grand final": "Grand Final",
    "Grand final reset": "Grand Final (Reset)",
    "LIVE": "LIVE",
    "Leave the tournament set": "Turnier-Set verlassen",
    "Leave this tournament set?\n\nYou lose the set.": "Dieses Turnier-Set verlassen?\n\nDu verlierst das Set.",
    "Losers final": "Losers-Finale",
    "Losers round {number}": "Losers-Runde {number}",
    "Losers semi-final": "Losers-Halbfinale",
    "NEEDS THE ORGANIZER": "BRAUCHT DEN ORGANISATOR",
    "No check-in": "Kein Check-in",
    "No tournament selected": "Kein Turnier ausgewählt",
    "Only tournament hosts can create tournaments. Ask the server's owner for a host slot.":
        "Nur Turnier-Hosts können Turniere anlegen. Frag den Betreiber des Servers nach einem Host-Platz.",
    "Pick a tournament to see its bracket.": "Wähle ein Turnier, um seinen Turnierbaum zu sehen.",
    "Pick one in the list, or create one.": "Wähle eins in der Liste oder lege eins an.",
    "Players": "Spieler",
    "Players at most": "Höchstens Spieler",
    "Players: {list}": "Spieler: {list}",
    "Quarter-final": "Viertelfinale",
    "Random seeding": "Zufällige Setzliste",
    "Report a result": "Ergebnis eintragen",
    "Reset set": "Set zurücksetzen",
    "Reset set {set}? It is played again from 0-0.": "Set {set} zurücksetzen? Es wird ab 0-0 neu gespielt.",
    "Round {number}": "Runde {number}",
    "Running": "Läuft",
    "Seeded by rating": "Setzliste nach Wertung",
    "Seeding": "Setzliste",
    "Semi-final": "Halbfinale",
    "Sets": "Sets",
    "Side 1 wins": "Seite 1 gewinnt",
    "Side 2 wins": "Seite 2 gewinnt",
    "Sign up": "Anmelden",
    "Sign-up": "Anmeldung",
    "Single elimination": "Single Elimination",
    "Start now": "Jetzt starten",
    "Start {name} now, with the players who are in?": "{name} jetzt starten, mit den Spielern, die dabei sind?",
    "Starts": "Startet",
    "TOURNAMENT": "TURNIER",
    "TOURNAMENT SET · BEST OF {best}": "TURNIER-SET · BEST OF {best}",
    "The bracket is drawn when the tournament starts.": "Der Turnierbaum entsteht, wenn das Turnier startet.",
    "The name needs 3 characters or more.": "Der Name braucht 3 Zeichen oder mehr.",
    "The organizer decided your tournament set.": "Der Organisator hat dein Turnier-Set entschieden.",
    "The organizer reset your tournament set; it is called again.": "Der Organisator hat dein Turnier-Set zurückgesetzt; es wird neu aufgerufen.",
    "The set goes on at {mine}-{theirs}.": "Das Set geht bei {mine}-{theirs} weiter.",
    "The set has no result; the tournament calls it again or its organizer decides": "Das Set hat kein Ergebnis; das Turnier ruft es neu auf oder sein Organisator entscheidet",
    "The set is called again.": "Das Set wird neu aufgerufen.",
    "The tournament was cancelled.": "Das Turnier wurde abgesagt.",
    "The tournament {name} has started: you are seed {seed} of {players}. Your sets are called here.": "Das Turnier {name} hat begonnen: du bist Nummer {seed} von {players} in der Setzliste. Deine Sets werden hier aufgerufen.",
    "The tournament {name} is over: {champion} won it.": "Das Turnier {name} ist vorbei: {champion} hat gewonnen.",
    "The tournament {name} is over: {champion} won it. You finished {place}.": "Das Turnier {name} ist vorbei: {champion} hat gewonnen. Du bist auf {place}.",
    "The tournament {name} was cancelled by its organizer.": "Das Turnier {name} wurde von seinem Organisator abgesagt.",
    "The tournament {name} was cancelled: not enough players.": "Das Turnier {name} wurde abgesagt: zu wenige Spieler.",
    "This tournament had no bracket.": "Dieses Turnier hatte keinen Turnierbaum.",
    "This tournament is for another build of the game.": "Dieses Turnier ist für einen anderen Build des Spiels.",
    "Tournament": "Turnier",
    "Tournament set": "Turnier-Set",
    "Tournament set vs {name}": "Turnier-Set gegen {name}",
    "Tournament {name} created.": "Turnier {name} angelegt.",
    "Tournament {name}: set {set} needs you ({why}). Report the result or reset it.": "Turnier {name}: Set {set} braucht dich ({why}). Trag das Ergebnis ein oder setze es zurück.",
    "Tournament {name}: {code}": "Turnier {name}: {code}",
    "Tournaments": "Turniere",
    "Winners final": "Winners-Finale",
    "Winners round {number}": "Winners-Runde {number}",
    "Winners semi-final": "Winners-Halbfinale",
    "Withdraw": "Zurückziehen",
    "Withdraw from {name}? You are out of the tournament.": "Von {name} zurückziehen? Dann bist du aus dem Turnier raus.",
    "Write the start time as HH:MM, e.g. 20:30.": "Schreib die Startzeit als HH:MM, z. B. 20:30.",
    "You are checked in.": "Du bist eingecheckt.",
    "You are in. Your next set is called here when its players are known.": "Du bist dabei. Dein nächstes Set wird hier aufgerufen, sobald seine Spieler feststehen.",
    "You are out of {name}.": "Du bist aus {name} ausgeschieden.",
    "You are out of {name}: {place}.": "Du bist aus {name} ausgeschieden: {place}.",
    "You are out of {name}: {why}.": "Du bist aus {name} raus: {why}.",
    "You are out: {why}.": "Du bist raus: {why}.",
    "You are signed up.": "Du bist angemeldet.",
    "You are signed up. Check in now, or you are not in the bracket.": "Du bist angemeldet. Checke jetzt ein, sonst bist du nicht im Turnierbaum.",
    "You did not check in for {name}; the tournament started without you.": "Du hast für {name} nicht eingecheckt; das Turnier hat ohne dich begonnen.",
    "You finished {place}.": "Du bist auf {place}.",
    "You left the tournament.": "Du hast das Turnier verlassen.",
    "You won the tournament {name}!": "Du hast das Turnier {name} gewonnen!",
    "Your next set: {set}.": "Dein nächstes Set: {set}.",
    "Your opponent did not show up: you win the set.": "Dein Gegner ist nicht gekommen: du gewinnst das Set.",
    "Your opponent is out of the tournament: you win the set.": "Dein Gegner ist aus dem Turnier raus: du gewinnst das Set.",
    "Your tournament set has no result; the organizer decides how it goes on.": "Dein Turnier-Set hat kein Ergebnis; der Organisator entscheidet, wie es weitergeht.",
    "Your tournament set is ready": "Dein Turnier-Set ist bereit",
    "accept within {seconds} s": "annehmen innerhalb von {seconds} s",
    "accepted -- waiting for {name}...": "angenommen -- warte auf {name}...",
    "best of {best}": "Best of {best}",
    "bye": "Freilos",
    "check-in from {time}": "Check-in ab {time}",
    "decided by the organizer": "vom Organisator entschieden",
    "did not show up": "nicht gekommen",
    "disqualified": "disqualifiziert",
    "disqualified by the organizer": "vom Organisator disqualifiziert",
    "ended {time}": "beendet {time}",
    "in 1 hour": "in 1 Stunde",
    "in 10 minutes": "in 10 Minuten",
    "in 12 hours": "in 12 Stunden",
    "in 15 minutes": "in 15 Minuten",
    "in 2 hours": "in 2 Stunden",
    "in 24 hours": "in 24 Stunden",
    "in 3 hours": "in 3 Stunden",
    "in 30 minutes": "in 30 Minuten",
    "in 5 minutes": "in 5 Minuten",
    "in 6 hours": "in 6 Stunden",
    "no-show": "nicht gekommen",
    "nobody": "niemand",
    "none yet": "noch keine",
    "not needed": "nicht nötig",
    "or at (HH:MM)": "oder um (HH:MM)",
    "organizer {name}": "Organisator {name}",
    "place {place}": "Platz {place}",
    "rated": "gewertet",
    "results disputed": "Ergebnisse umstritten",
    "started {time}": "gestartet {time}",
    "starts {time}": "startet {time}",
    "waiting": "offen",
    "withdrew": "zurückgezogen",
    "{format}, best of {best}": "{format}, Best of {best}",
    "{name} has accepted.": "{name} hat angenommen.",
    "{name} is not online yet.": "{name} ist noch nicht online.",
    "{name} wins": "{name} gewinnt",
    "{name} wins set {set}?": "{name} gewinnt Set {set}?",
    "{name}'s tournament": "Turnier von {name}",
    "{players} of {max} players": "{players} von {max} Spielern",
    "The organizer decided the set.": "Der Organisator hat das Set entschieden.",
    # ---- lobby/t5lobby/i18n_known.py: lobby/t5lobby/server/tournaments.py
    "tournaments need an account": "Turniere brauchen ein Konto",
    "no such tournament": "Dieses Turnier gibt es nicht",
    "only the server's organizers can create tournaments here": "Hier können nur die Organisatoren des Servers Turniere anlegen",
    "a tournament name is 3-40 characters": "Ein Turniername hat 3 bis 40 Zeichen",
    "the format is single or double elimination": "Das Format ist Single oder Double Elimination",
    "a set is first to 2 or first to 3 games": "Ein Set geht auf 2 oder 3 gewonnene Spiele",
    "the player limit is 8, 16, 32 or 64": "Die Spielergrenze ist 8, 16, 32 oder 64",
    "the check-in window is 0, 5, 10, 15, 30 or 60 minutes": "Der Check-in dauert 0, 5, 10, 15, 30 oder 60 Minuten",
    "seeding is random or by rating": "Die Setzliste ist zufällig oder nach Wertung",
    "that start time has passed": "Diese Startzeit ist schon vorbei",
    "a tournament starts within {days} days": "Ein Turnier startet innerhalb von {days} Tagen",
    "this server has as many tournaments as it takes; try again later": "Dieser Server hat schon so viele Turniere, wie er annimmt; versuch es später noch einmal",
    "you already run {count} tournaments; finish or cancel one first": "Du leitest schon {count} Turniere; beende oder sage erst eins ab",
    "update the launcher to play in tournaments": "Aktualisiere den Launcher, um bei Turnieren mitzuspielen",
    "sign-up for that tournament is closed": "Die Anmeldung für dieses Turnier ist geschlossen",
    "that tournament is played with another build of the game": "Dieses Turnier wird mit einem anderen Build des Spiels gespielt",
    "that tournament is full": "Dieses Turnier ist voll",
    "you are not in that tournament": "Du bist nicht in diesem Turnier",
    "that tournament is over": "Dieses Turnier ist vorbei",
    "check-in is not open": "Der Check-in ist nicht offen",
    "that tournament is not running": "Dieses Turnier läuft nicht",
    "that set is not yours to play": "Dieses Set ist nicht deins",
    "that set is not waiting for you": "Dieses Set wartet nicht auf dich",
    "only the organizer can do that": "Das kann nur der Organisator",
    "that tournament name is not allowed here":
        "Dieser Turniername ist hier nicht erlaubt",
    "this internet address runs as many tournaments as one organizer may; finish or cancel one first":
        "Von dieser Internetadresse laufen schon so viele Turniere, wie ein Organisator haben darf; beende oder sage erst eins ab",
    "the organizer took you off this tournament":
        "Der Organisator hat dich aus diesem Turnier genommen",
    "you play in that set yourself: a server tournament admin decides it (or cancel the tournament)":
        "Du spielst dieses Set selbst: Ein Turnier-Admin des Servers entscheidet es (oder sage das Turnier ab)",
    "that tournament has started already": "Dieses Turnier hat schon begonnen",
    "a tournament needs at least 2 players": "Ein Turnier braucht mindestens 2 Spieler",
    "no such player in that tournament": "Diesen Spieler gibt es in diesem Turnier nicht",
    "that player is out already": "Dieser Spieler ist schon ausgeschieden",
    "no such set": "Dieses Set gibt es nicht",
    "that set is decided; override it instead": "Dieses Set ist entschieden; überschreibe es stattdessen",
    "only a played set can be overridden": "Nur ein gespieltes Set kann überschrieben werden",
    "that set has not been played": "Dieses Set wurde noch nicht gespielt",
    "that set was a walkover": "Dieses Set war ein Freilos",
    "set {set} was already played from this result; reset it first": "Set {set} wurde mit diesem Ergebnis schon gespielt; setze erst das zurück",
    "finish your match first, then accept the tournament set": "Beende erst dein Match, dann nimm das Turnier-Set an",
    "finish your set first, then accept the tournament set": "Beende erst dein Set, dann nimm das Turnier-Set an",
    "you are in a tournament set; finish it first": "Du spielst ein Turnier-Set; beende es erst",
    "that player is playing a tournament set": "Dieser Spieler spielt gerade ein Turnier-Set",
    "your tournament set is ready; accept it first": "Dein Turnier-Set ist bereit; nimm es zuerst an",
    "that player has a tournament set to play": "Dieser Spieler muss ein Turnier-Set spielen",
    # ---- lobby/t5lobby/theme.py
    "Good connection": "Gute Verbindung",
    "Laggy connection": "Verbindung mit Lag",
    "OK connection": "Ordentliche Verbindung",
    "Ping not known yet": "Ping noch nicht bekannt",
    "sec": "Sek.",
    # ---- lobby/t5lobby/tk_tab.py
    "Leave set (counts as a loss)": "Set verlassen (zählt als Niederlage)",
    "Leave the ranked set": "Ranked-Set verlassen",
    "Leave this ranked set?\n\nLeaving a ranked set counts as losing it.":
        "Dieses Ranked-Set verlassen?\n\nWer ein Ranked-Set verlässt, hat es verloren.",
    "Rematch? (a new set)": "Rematch? (ein neues Set)",
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
    "the two games went out of sync": "die Spiele liefen nicht mehr synchron",
    "too short to count": "zu kurz zum Zählen",
    "a game crashed": "ein Spiel ist abgestürzt",
    "the reports disagreed": "die Meldungen passten nicht zusammen",
    "left right away": "sofort verlassen",
    "a player left": "ein Spieler ist gegangen",
    "a player lost the connection": "ein Spieler hat die Verbindung verloren",
    "a player did not report": "ein Spieler hat nichts gemeldet",
    "the connection between the games failed": "die Verbindung der Spiele brach ab",
    "both players left": "beide Spieler sind gegangen",
    "no result in time": "kein Ergebnis rechtzeitig",
    "repeated crashes count as losses": "wiederholte Abstürze sind Niederlagen",
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
    "via the relay server {name}": "über den Relay-Server {name}",
    "Lobby error: {error}": "Lobby-Fehler: {error}",
    "guest": "Gast",
    "Not connected. Ranked needs an account; guests play casual matches.":
        "Nicht verbunden. Ranked braucht ein Konto; Gäste spielen Casual-Matches.",
    "Passwords are only sent to servers on this PC / your network, or over an encrypted "
    "(TLS) connection.":
        "Passwörter gehen nur an Server auf diesem PC oder in deinem Netzwerk, oder über "
        "eine verschlüsselte (TLS-)Verbindung.",
    "Double-click a player in the lobby or the leaderboard.":
        "Doppelklick auf einen Spieler in der Lobby oder der Rangliste.",
    "{name} (guest, casual matches only)": "{name} (Gast, nur Casual-Matches)",
    "{record} this session": "{record} in dieser Sitzung",
    "rating {rating}": "Wertung {rating}",
    "main {character}": "Main {character}",
    "server ping {ms} ms": "Server-Ping {ms} ms",
    "encrypted": "verschlüsselt",
    "[Server: {notice}]": "[Server: {notice}]",
    "Server notice: {notice}": "Server-Hinweis: {notice}",
    "The game is not built.": "Das Spiel ist nicht gebaut.",
    "This Mac build has no online play. For a test match: tools/build_game.py --macos-online (docs/MACOS_ONLINE_TEST.md).":
        "Dieser Mac-Build hat kein Online-Spiel. Für ein Testmatch: tools/build_game.py --macos-online (docs/MACOS_ONLINE_TEST.md).",
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
    "Log out": "Abmelden",
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
    "Save recovery codes": "Wiederherstellungs-Codes speichern",
    "T5DR Online recovery codes for {name} on {server}":
        "T5DR Online Wiederherstellungs-Codes für {name} auf {server}",
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
    "Played {games}: {wins} won, {losses} lost, win rate {rate} %": "Gespielt {games}: {wins} gewonnen, {losses} verloren, Siegquote {rate} %",
    "Ranked {games}, {rate} % won": "Ranked {games}, {rate} % gewonnen",
    "Casual {games}, {rate} % won": "Casual {games}, {rate} % gewonnen",
    "Stats": "Statistik",
    "Community stats": "Community-Statistik",
    "Accounts": "Konten",
    "Matches": "Matches",
    "Ranked matches": "Ranked-Matches",
    "Last 24 hours": "Letzte 24 Stunden",
    "{matches} matches, {players} players": "{matches} Matches, {players} Spieler",
    "as of {when}": "Stand {when}",
    "All": "Alle",
    "Fighter": "Kämpfer",
    "Wins": "Siege",
    "Win rate": "Siegquote",
    "Picked": "Gewählt",
    "No numbers yet.": "Noch keine Zahlen.",
    "This lobby server has no stats page yet (it comes with server 1.1.5).":
        "Dieser Lobby-Server hat noch keine Statistik (sie kommt mit Server 1.1.5).",
    "Win rate per match; a mirror match counts as one win and one loss. Grey: fewer than {count} matches, not much to go on yet. Click a column to sort.":
        "Siegquote pro Match; ein Spiegelmatch zählt als ein Sieg und eine Niederlage. Grau: weniger als {count} Matches, noch wenig aussagekräftig. Zum Sortieren auf eine Spalte klicken.",
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
    "Lost the connection to the lobby server.": "Verbindung zum Lobby-Server verloren.",
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
    "other version": "andere Version",
    "ranked": "ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "Suche... ({ranked} in der Ranked-Suche, {quick} bei Quick Match)",
    "ping about {ms} ms (estimated; measured directly once you both accept)":
        "Ping etwa {ms} ms (geschätzt; direkt gemessen, sobald ihr beide annehmt)",
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
    "Next game": "Nächstes Spiel",
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
    "Host for friends": "Für Freunde hosten",
    "The lobby server stopped (exit code {code}); see its log in {folder}.":
        "Der Lobby-Server wurde beendet (Exit-Code {code}); sein Log liegt in {folder}.",
    "Stopped hosting.": "Hosten beendet.",
    # in-game character select (branch ingame-select)
    "Pick your fighter in the game ({secs} s; Select = random; no pick = the character set here).":
        "Wähle deinen Kämpfer im Spiel ({secs} s; Select = zufällig; ohne Wahl der hier eingestellte Charakter).",
    "Waiting for your opponent to pick...": "Warte auf die Wahl deines Gegners...",
    "Ranked match (accounts) or Quick match; then pick your fighter in the game (Select = random). The character here is used when you do not pick in time.":
        "Ranked Match (Konten) oder Quick Match; dann wählst du deinen Kämpfer im Spiel (Select = zufällig). Der Charakter hier gilt, wenn du nicht rechtzeitig wählst.",
    "pick your fighter in the game ({secs} s)": "Kämpfer im Spiel wählen ({secs} s)",
    "(locked for this ranked set)": "(fest für dieses Ranked-Set)",
    "Pick your fighter in the game": "Wähle deinen Kämpfer im Spiel",
    "Your opponent is picking": "Dein Gegner wählt",
    # ---- lobby/t5lobby/tk_views.py
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
    "Check the server address and your internet connection, then try again.":
        "Prüfe die Server-Adresse und deine Internetverbindung und versuche es dann noch "
        "einmal.",
    "Check your internet connection, then try again.":
        "Prüfe deine Internetverbindung und versuche es dann noch einmal.",
    "The server is slow or gone; try again in a minute.":
        "Der Server ist langsam oder weg; versuche es in einer Minute noch einmal.",
    "Log in again.": "Melde dich noch einmal an.",
    "Ask whoever runs the server for its current fingerprint (\"Server certificate...\").":
        "Frage den Betreiber des Servers nach dem aktuellen Fingerabdruck "
        "(„Server-Zertifikat...“).",
    "Check the spelling, or use \"Forgot password...\".":
        "Prüfe die Schreibweise, oder nutze „Passwort vergessen...“.",
    "Check the name and the code; each code works once.": "Prüfe den Namen und den Code; jeder Code gilt nur einmal.",
    "Pick another name, or wait a minute if that was you.":
        "Nimm einen anderen Namen, oder warte eine Minute, falls du das warst.",
    "Log in with that account's password, or pick another name.":
        "Melde dich mit dem Passwort dieses Kontos an, oder nimm einen anderen Namen.",
    "Pick another name.": "Nimm einen anderen Namen.",
    "Update the game to the release this server asks for.":
        "Aktualisiere das Spiel auf das Release, das dieser Server verlangt.",
    "You both need the same release of the game.": "Ihr braucht beide dasselbe Release des Spiels.",
    "Update the launcher to the newest release.": "Aktualisiere den Launcher auf das neueste Release.",
    "Create an account (free) to play ranked.": "Erstelle ein (kostenloses) Konto, um Ranked zu spielen.",
    "Pick another room or create your own.": "Wähle einen anderen Raum oder erstelle einen eigenen.",
    "Log in with your password.": "Melde dich mit deinem Passwort an.",
    "Build the game on the Build tab first.": "Baue das Spiel zuerst im Reiter Bauen.",
    "Allow T5DR Online through the Windows firewall, then search again.":
        "Erlaube T5DR Online in der Windows-Firewall und suche dann noch einmal.",
    "Try again; if it keeps failing, check your firewall or router.":
        "Versuche es noch einmal; klappt es weiter nicht, prüfe deine Firewall oder deinen "
        "Router.",
    "Log in again; your settings are kept.": "Melde dich noch einmal an; deine Einstellungen bleiben erhalten.",
    "Type the same password twice.": "Gib zweimal dasselbe Passwort ein.",
    "Find a new opponent.": "Suche einen neuen Gegner.",
    "Check the Play offline tab: does the game start there?":
        "Sieh im Reiter Offline spielen nach: Startet das Spiel dort?",
    "Against other players over the internet. Log in or play as a guest; the game starts "
    "by itself, straight into the fight, and the result comes back here.":
        "Gegen andere Spieler über das Internet. Melde dich an oder spiele als Gast; das "
        "Spiel startet von selbst, direkt im Kampf, und das Ergebnis kommt hierher zurück.",
    "Server": "Server",
    "Server certificate...": "Server-Zertifikat...",
    "Name": "Name",
    "Log in": "Anmelden",
    "Password": "Passwort",
    "Password again": "Passwort noch einmal",
    "Name: 2 to 16 letters, digits, spaces or _-.[]()!?":
        "Name: 2 bis 16 Buchstaben, Ziffern, Leerzeichen oder _-.[]()!?",
    "Password: 6 to 128 characters": "Passwort: 6 bis 128 Zeichen",
    "Both passwords the same": "Beide Passwörter gleich",
    "You get recovery codes once: the only way back in if you forget the password":
        "Du bekommst die Wiederherstellungs-Codes einmal: der einzige Weg zurück, wenn du "
        "das Passwort vergisst",
    "Remember me": "Angemeldet bleiben",
    "Forgot password...": "Passwort vergessen...",
    "Casual matches with the name above, no account and no password. Ranked matches, the "
    "leaderboard and your match history need an account.":
        "Casual-Matches mit dem Namen oben, ohne Konto und ohne Passwort. Ranked-Matches, "
        "die Rangliste und dein Match-Verlauf brauchen ein Konto.",
    "Play as guest": "Als Gast spielen",
    "Runs a lobby on this PC. Your friends type the address it shows into their Server "
    "box.":
        "Startet eine Lobby auf diesem PC. Deine Freunde tragen die Adresse, die sie zeigt, "
        "in ihr Server-Feld ein.",
    "Open router ports (UPnP)": "Router-Ports öffnen (UPnP)",
    "How it works": "So geht es",
    "Quick match (casual) or Ranked match (account).": "Quick Match (Casual) oder Ranked-Match (mit Konto).",
    "An opponent is found: accept within 15 seconds.": "Ein Gegner wird gefunden: Nimm innerhalb von 15 Sekunden an.",
    "The game opens straight into the fight.": "Das Spiel öffnet sich direkt im Kampf.",
    "The result comes back here: rematch or next game.":
        "Das Ergebnis kommt hierher zurück: Rematch oder nächstes Spiel.",
    "With a controller: A accepts, B declines.": "Mit Controller: A nimmt an, B lehnt ab.",
    "Online nobody can pause the fight: Start does not open the pause menu.":
        "Online kann niemand den Kampf pausieren: Start öffnet kein Pausenmenü.",
    "Intros and the replay after a round are skipped once both players have pressed Start.":
        "Intros und die Wiederholung nach einer Runde werden übersprungen, sobald beide Spieler Start gedrückt haben.",
    "Lobby": "Lobby",
    "Leaderboard": "Rangliste",
    "Profile": "Profil",
    "My profile": "Mein Profil",
    "Find an opponent online": "Gegner online finden",
    "Character": "Charakter",
    "Choose your fighter": "Wähle deinen Kämpfer",
    "{star} your main: {character}": "{star} dein Main: {character}",
    "Arrow keys move, Enter picks, Esc closes. With a controller: Cross / A picks, Circle / B closes.":
        "Pfeiltasten bewegen, Enter wählt, Esc schließt. Mit Controller: Kreuz / A wählt, Kreis / B schließt.",
    "Locked for this ranked set": "Für dieses Ranked-Set gesperrt",
    "Ranked match": "Ranked-Match",
    "Quick match": "Quick Match",
    "Casual: the lowest ping first": "Casual: der niedrigste Ping zuerst",
    "Strict (ranked: +-150 rating)": "Streng (Ranked: +-150 Wertung)",
    "Searching": "Suche",
    "Looking for an opponent": "Suche einen Gegner",
    "Searching for": "Suche seit",
    "Stop searching": "Suche beenden",
    "In match": "Im Match",
    "CASUAL": "CASUAL",
    "Input delay": "Input-Delay",
    "Connection": "Verbindung",
    "Players online": "Spieler online",
    "Challenge": "Herausfordern",
    "Rooms": "Räume",
    "Create room": "Raum erstellen",
    "Join room": "Raum beitreten",
    "Leave room": "Raum verlassen",
    "Chat": "Chat",
    "Send": "Senden",
    "Refresh": "Aktualisieren",
    "Order: rating minus twice its uncertainty (a few matches are needed to climb). '?' "
    "= provisional.":
        "Reihenfolge: Wertung minus das Doppelte der Unsicherheit (ein paar Matches sind "
        "nötig, um aufzusteigen). „?“ = vorläufig.",
    "Your account": "Dein Konto",
    "Blocked players...": "Blockierte Spieler...",
    "Change password...": "Passwort ändern...",
    "New recovery codes...": "Neue Wiederherstellungs-Codes...",
    "Dismiss": "Ausblenden",
    "Use a controller here": "Controller hier benutzen",
    "none open": "keiner offen",
    "Nobody else is online right now. Ranked match and Quick match keep looking until someone comes.":
        "Gerade ist sonst niemand online. Ranked-Match und Quick Match suchen weiter, bis jemand kommt.",
    "No rooms open. Create one: friends can join it and play in turn.":
        "Keine Räume offen. Mach einen auf: Freunde können beitreten und abwechselnd spielen.",
    "Nobody has a ranked result yet. Win a ranked set to be the first.":
        "Noch hat niemand ein Ranked-Ergebnis. Gewinn ein Ranked-Set und sei der Erste.",
    "In your room “{name}”. Waiting for a second player...":
        "In deinem Raum „{name}“. Warte auf einen zweiten Spieler...",
    "In the room “{name}”. The match starts when you are both ready.":
        "Im Raum „{name}“. Das Match startet, wenn ihr beide bereit seid.",
    "Hosting. Friends type this as their Server:\n{share}":
        "Du hostest. Deine Freunde tragen das als ihren Server ein:\n{share}",
    "Same network: {lan}": "Im selben Netzwerk: {lan}",
    "Guest · casual matches": "Gast · Casual-Matches",
    "Rating {rating}  ·  {record}": "Wertung {rating}  ·  {record}",
    "Main: {character}": "Main: {character}",
    "Server ping {ms} ms": "Server-Ping {ms} ms",
    "Create an account to play ranked": "Erstelle ein Konto, um Ranked zu spielen",
    "Rated: close to your rank, good connection": "Gewertet: nah an deinem Rang, gute Verbindung",
    "Similar rank and a good connection, strict: within 150 rating points (this can take "
    "a while).":
        "Ähnlicher Rang und gute Verbindung, streng: innerhalb von 150 Wertungspunkten (das "
        "kann dauern).",
    "Similar rank and a good connection.": "Ähnlicher Rang und gute Verbindung.",
    "The opponent with the lowest ping first.": "Zuerst der Gegner mit dem niedrigsten Ping.",
    "{ranked} in the ranked queue  ·  {quick} in quick match":
        "{ranked} in der Ranked-Suche  ·  {quick} bei Quick Match",
    "Character select": "Charakterwahl",
    "Stage select": "Stage-Wahl",
    "Match over": "Match vorbei",
    "Waiting for the next match": "Warte auf das nächste Match",
    "Your game is running": "Dein Spiel läuft",
    "Starting the game...": "Das Spiel startet...",
    "Waiting for the game...": "Warte auf das Spiel...",
    "vs your opponent": "gegen deinen Gegner",
    "vs {name}": "gegen {name}",
    "{count} frame  ({ms} ms)": "{count} Frame  ({ms} ms)",
    "{count} frames  ({ms} ms)": "{count} Frames  ({ms} ms)",
    "Direct": "Direkt",
    "Local network": "Lokales Netzwerk",
    "Relay (lobby server)": "Relay (Lobby-Server)",
    "Relay ({name})": "Relay ({name})",
    "Guest": "Gast",
    "{rank}  ·  rating {rating}": "{rank}  ·  Wertung {rating}",
    "SET · GAME {game}": "SET · SPIEL {game}",
    "Opponent hidden": "Gegner verborgen",
    "Name and side are shown once you both accept.": "Name und Seite werden gezeigt, sobald ihr beide annehmt.",
    "(estimated before you connect)": "(geschätzt, bevor ihr verbunden seid)",
    "(measured in your last match together)": "(gemessen in eurem letzten Match)",
    "ping {ms} ms (measured in your last match together)": "Ping {ms} ms (gemessen in eurem letzten Match)",
    "probably a direct connection": "wahrscheinlich eine direkte Verbindung",
    "probably over the local network": "wahrscheinlich über das lokale Netzwerk",
    "probably through a relay server": "wahrscheinlich über einen Relay-Server",
    "Accepted. Waiting for your opponent...": "Angenommen. Warte auf deinen Gegner...",
    "Match ready": "Match bereit",
    "Connecting the two games...": "Verbinde die beiden Spiele...",
    "wants to play you. Accept to start the match.": "will gegen dich spielen. Nimm an, um das Match zu starten.",
    "YOU WIN": "SIEG",
    "YOU LOSE": "NIEDERLAGE",
    "DRAW": "UNENTSCHIEDEN",
    "MATCH OVER": "MATCH VORBEI",
    "NO CONTEST": "KEINE WERTUNG",
    "Casual match": "Casual-Match",
    "ROUNDS  (P1 – P2)": "RUNDEN  (P1 – P2)",
    "ROUNDS  (YOU – THEM)": "RUNDEN  (DU – GEGNER)",
    "GAMES  (YOU – THEM)": "SPIELE  (DU – GEGNER)",
    "SET WON": "SET GEWONNEN",
    "The game waits here for your next match: Rematch, Next game or Leave.":
        "Das Spiel wartet hier auf dein nächstes Match: Rematch, Nächstes Spiel oder Verlassen.",
    "SET LOST": "SET VERLOREN",
    "Ranked set": "Ranked-Set",
    "Ranked set vs {name}": "Ranked-Set gegen {name}",
    "RANKED SET · BEST OF {best}": "RANKED-SET · BEST OF {best}",
    "Game {number} of {best} starts in": "Spiel {number} von {best} startet in",
    "Game {number} of {best} again (no winner), starts in":
        "Spiel {number} von {best} noch einmal (kein Sieger), startet in",
    "Rating {rating}": "Wertung {rating}",
    "PROMOTED": "AUFGESTIEGEN",
    "DEMOTED": "ABGESTIEGEN",
    "PLACED": "EINGESTUFT",
    "Placement match {done} of {total}": "Platzierungsmatch {done} von {total}",
    "Lag check": "Lag-Check",
    "Rematch offered. Waiting for {opp}...": "Rematch angeboten. Warte auf {opp}...",
    "Back to the lobby": "Zurück zur Lobby",
    "New recovery codes": "Neue Wiederherstellungs-Codes",
    "Your account is ready": "Dein Konto ist fertig",
    "These codes are the only way back into your account if you forget the password "
    "(there is no e-mail). Each code works once. Write them down or save them somewhere "
    "safe -- they are not shown again.":
        "Diese Codes sind der einzige Weg zurück in dein Konto, wenn du das Passwort "
        "vergisst (es gibt keine E-Mail). Jeder Code gilt nur einmal. Schreibe sie auf oder "
        "speichere sie an einem sicheren Ort -- sie werden nicht noch einmal angezeigt.",
    "Save to a file...": "In Datei speichern...",
    "I have saved them": "Ich habe sie gespeichert",
    # ---- friends (tk_tab.py, tk_views.py)
    "Request": "Anfrage",
    "Friends": "Freunde",
    "Invite to a match": "Zum Match einladen",
    "Invite to my room": "In den Raum einladen",
    "Invite in {seconds} s": "Einladen in {seconds} s",
    "Remove": "Entfernen",
    "Invite a friend who is online: one click on their side starts a casual match, or brings them into your room.":
        "Lade einen Freund ein, der online ist: Ein Klick auf seiner Seite startet ein Casual-Match oder holt ihn "
        "in deinen Raum.",
    "Add a friend": "Freund hinzufügen",
    "Send request": "Anfrage senden",
    "Their account name. They become your friend when they accept.":
        "Sein Kontoname. Ihr seid Freunde, sobald er annimmt.",
    "Requests": "Anfragen",
    "Take back": "Zurückziehen",
    "Invite from a friend": "Einladung von einem Freund",
    "invites you to the room “{room}”. Accept to join it; the match starts at once.":
        "lädt dich in den Raum „{room}“ ein. Nimm an, um beizutreten; das Match startet sofort.",
    "invites you to a casual match. Accept to start it.":
        "lädt dich zu einem Casual-Match ein. Nimm an, um es zu starten.",
    "Check the spelling: friends are added by their account name.":
        "Prüfe die Schreibweise: Freunde werden mit ihrem Kontonamen hinzugefügt.",
    "in a match": "im Match",
    "offline": "offline",
    "older launcher: no invites": "älterer Launcher: keine Einladungen",
    "Friends ({count})": "Freunde ({count})",
    "offline, last seen {when}": "offline, zuletzt gesehen {when}",
    "Friends need an account. Log in with one to add friends and invite them.":
        "Freunde brauchen ein Konto. Melde dich mit einem an, um Freunde hinzuzufügen und einzuladen.",
    "This lobby server has no friends list (it needs version 1.1.2 or newer).":
        "Dieser Lobby-Server hat keine Freundesliste (dafür braucht er Version 1.1.2 oder neuer).",
    "wants to be your friend": "möchte dein Freund sein",
    "asked: waiting for an answer": "wartet auf Antwort",
    "{online} online · {count} of {max}": "{online} online · {count} von {max}",
    "Your friends see when you are online. Invite one who is online to play.":
        "Deine Freunde sehen, wann du online bist. Lade einen ein, der online ist, um zu spielen.",
    "No friends yet. Add one by account name: they become your friend when they accept.":
        "Noch keine Freunde. Füge einen mit seinem Kontonamen hinzu: Ihr seid Freunde, sobald er annimmt.",
    "Cancel the invite": "Einladung zurückziehen",
    "You and {name} are friends now.": "Du und {name} seid jetzt Freunde.",
    "Friend request sent to {name}. They become your friend when they accept.":
        "Freundschaftsanfrage an {name} gesendet. Ihr seid Freunde, sobald sie angenommen ist.",
    "Request from {name} declined.": "Anfrage von {name} abgelehnt.",
    "Request to {name} taken back.": "Anfrage an {name} zurückgezogen.",
    "Remove friend": "Freund entfernen",
    "Remove {name} from your friends?\n\nYou can ask again later; they have to accept again.":
        "{name} aus deinen Freunden entfernen?\n\nDu kannst später wieder anfragen; die Anfrage muss dann wieder "
        "angenommen werden.",
    "{name} is no longer your friend.": "{name} ist nicht mehr dein Freund.",
    "Select a friend in the list first.": "Wähle zuerst einen Freund in der Liste.",
    "Invite sent to {name}; waiting for an answer ({seconds} s)...":
        "Einladung an {name} gesendet; warte auf eine Antwort ({seconds} s)...",
    "{name} ({rank}) invites you to the room “{room}”": "{name} ({rank}) lädt dich in den Raum „{room}“ ein",
    "{name} ({rank}) invites you to a casual match": "{name} ({rank}) lädt dich zu einem Casual-Match ein",
    "The invite from {name} ran out.": "Die Einladung von {name} ist abgelaufen.",
    "The invite from {name} ended.": "Die Einladung von {name} ist beendet.",
    "{name} declined your invite.": "{name} hat deine Einladung abgelehnt.",
    "{name} did not answer your invite.": "{name} hat auf deine Einladung nicht geantwortet.",
    "The invite to {name} ended.": "Die Einladung an {name} ist beendet.",
    "{name} wants to be your friend: see the Friends tab.":
        "{name} möchte dein Freund sein: siehe den Reiter Freunde.",
    "{name} accepted your friend request.": "{name} hat deine Freundschaftsanfrage angenommen.",
    "{name} declined your friend request.": "{name} hat deine Freundschaftsanfrage abgelehnt.",

    # ---- launcher/replays_ui.py, launcher/t5dr_launcher.pyw (Replays tab)
    "Replays": "Replays",
    "Every online match is saved here. Watch plays it back in the game exactly as it was played: the same "
    "inputs frame by frame, checked against the live match while it plays.":
        "Jedes Online-Match wird hier gespeichert. Ansehen spielt es im Spiel genau so ab, wie es gespielt "
        "wurde: dieselben Eingaben Bild für Bild, während des Abspielens mit dem Live-Match verglichen.",
    "Date": "Datum",
    "Fighters": "Kämpfer",
    "Netcode": "Netcode",
    "WATCH": "ANSEHEN",
    "Stop replay": "Replay stoppen",
    "Delete": "Löschen",
    "Open replays folder": "Replay-Ordner öffnen",
    "While a replay plays: START (Enter) pauses and goes on, SELECT (Tab) ends the replay. A "
    "rematch is played after the matches before it in the same session: it starts from what they "
    "left.":
        "Während ein Replay läuft: START (Enter) pausiert und geht weiter, SELECT (Tab) beendet das "
        "Replay. Ein Rematch wird nach den Matches davor in derselben Sitzung abgespielt: es beginnt dort, "
        "wo sie aufgehört haben.",
    "Save online matches as replays": "Online-Matches als Replays speichern",
    "Watch replay": "Replay ansehen",
    "{count} of these matches have a replay on this PC ({mark}). Select one to watch it.":
        "{count} dieser Matches haben ein Replay auf diesem PC ({mark}). Wähle eins, um es anzusehen.",
    "None of these matches has a replay on this PC (replays are saved on the PC that played, while \"Save online matches as replays\" is on).":
        "Keins dieser Matches hat ein Replay auf diesem PC (Replays werden auf dem PC gespeichert, der gespielt hat, solange „Online-Matches als Replays speichern“ an ist).",
    "No replay of this match on this PC.": "Kein Replay dieses Matches auf diesem PC.",
    "{fighters}, saved on this PC.": "{fighters}, auf diesem PC gespeichert.",
    "This replay is no longer on this PC.": "Dieses Replay ist nicht mehr auf diesem PC.",
    "Keep the players' names in replays": "Die Namen der Spieler in Replays behalten",
    "Rollback": "Rollback",
    "Lockstep": "Lockstep",
    "(name not saved)": "(Name nicht gespeichert)",
    "{matches} match(es) in {files} file(s) in {folder}": "{matches} Match(es) in {files} Datei(en) in {folder}",
    "No replays yet. Play an online match: it is saved here.":
        "Noch keine Replays. Spiel ein Online-Match: es wird hier gespeichert.",
    "not finished": "nicht beendet",
    "won {mine}-{theirs}": "gewonnen {mine}-{theirs}",
    "lost {mine}-{theirs}": "verloren {mine}-{theirs}",
    "Close the running game first (Stop game on the Play tab).":
        "Schließ zuerst das laufende Spiel (Spiel stoppen im Tab Offline spielen).",
    "Build the game first (Build tab).": "Bau zuerst das Spiel (Tab Build).",
    "This replay cannot be played: {why}": "Dieses Replay lässt sich nicht abspielen: {why}",
    "Recorded with another version of the game: it may not play back the same.":
        "Mit einer anderen Version des Spiels aufgenommen: es läuft vielleicht nicht gleich ab.",
    "Playing {fighters} ({when})...": "Spiele {fighters} ab ({when})...",
    "The replay ended before the end of the match.": "Das Replay endete vor dem Ende des Matches.",
    "Replay over: identical to the live match ({checks} checks, same result).":
        "Replay zu Ende: identisch mit dem Live-Match ({checks} Prüfungen, gleiches Ergebnis).",
    "Replay over, but it went a different way from frame {frame} on (the game or its version differs from "
    "the one that played it).":
        "Replay zu Ende, aber ab Bild {frame} lief es anders (das Spiel oder seine Version ist nicht die, mit "
        "der gespielt wurde).",
    "Replay over.": "Replay zu Ende.",
    "Delete this replay file? It holds {n} match(es) against the same opponent.":
        "Diese Replay-Datei löschen? Sie enthält {n} Match(es) gegen denselben Gegner.",
    # ---- lobby/t5lobby/tk_spectate.py, server/spectating.py, launcher Settings (spectating live matches)
    "Spectators":
        "Zuschauer",
    "Friends and room visitors may watch my online matches":
        "Freunde und Raumbesucher dürfen meine Online-Matches ansehen",
    "Also my ranked matches":
        "Auch meine Ranked-Matches",
    "They see the match a few seconds late, in their own game. Only when both players allow it; a "
    "ranked match only when both allow ranked too.":
        "Sie sehen das Match ein paar Sekunden später, in ihrem eigenen Spiel. Nur wenn beide Spieler es "
        "erlauben; ein Ranked-Match nur, wenn beide auch Ranked erlauben.",
    "Watch":
        "Zuschauen",
    "Spectating":
        "Zuschauen",
    "Stop watching":
        "Nicht mehr zuschauen",
    "Watching":
        "Du schaust zu",
    "Waiting for the match data...":
        "Warte auf die Matchdaten...",
    "About {seconds} s behind the live match.":
        "Etwa {seconds} s hinter dem Live-Match.",
    "It plays from the start of the players' session, a few seconds behind.":
        "Es läuft ab dem Beginn der Session der Spieler, ein paar Sekunden zurück.",
    "Watching {p1} vs {p2}.":
        "Du schaust {p1} vs {p2} zu.",
    "Spectators watching your match: {count}":
        "Zuschauer bei deinem Match: {count}",
    "The live match is over.":
        "Das Live-Match ist vorbei.",
    "The players turned spectators off.":
        "Die Spieler haben Zuschauer ausgeschaltet.",
    "The match data stopped coming.":
        "Die Matchdaten kommen nicht mehr an.",
    "This session is too long to watch from its start.":
        "Diese Session ist zu lang, um sie von Anfang an anzusehen.",
    "Your own match is starting.":
        "Dein eigenes Match beginnt.",
    "The match data was damaged.":
        "Die Matchdaten waren beschädigt.",
    "You stopped watching.":
        "Du schaust nicht mehr zu.",
    "A friend of the players took your place: the match has as many spectators as it can take.":
        "Ein Freund der Spieler hat deinen Platz bekommen: Das Match hat so viele Zuschauer, wie es aufnehmen kann.",
    "this launcher cannot watch matches; update it":
        "Dieser Launcher kann keine Matches ansehen; aktualisiere ihn",
    "that match is not being played right now":
        "Dieses Match wird gerade nicht gespielt",
    "you are playing in that match":
        "Du spielst in diesem Match",
    "you are in a match yourself":
        "Du bist selbst in einem Match",
    "only friends of a player can watch this match":
        "Nur Freunde eines Spielers können dieses Match ansehen",
    "the players do not allow spectators":
        "Die Spieler erlauben keine Zuschauer",
    "neither player can send the match right now":
        "Gerade kann keiner der Spieler das Match senden",
    "this match cannot be watched any more":
        "Dieses Match kann nicht mehr angesehen werden",
    "this match has {count} spectators already":
        "Dieses Match hat schon {count} Zuschauer",
    "the server cannot show more matches right now":
        "Der Server kann gerade keine weiteren Matches zeigen",
    "too many matches are watched from your network; stop watching one first":
        "Aus deinem Netz werden schon zu viele Matches angeschaut; hör erst bei einem auf",
    "the places for guests at this match are taken; log in with an account to watch":
        "Die Plätze für Gäste bei diesem Match sind belegt; melde dich mit einem Konto an, um zuzuschauen",
    "the server cannot show guests more matches right now; log in with an account to watch":
        "Der Server kann Gästen gerade keine weiteren Matches zeigen; melde dich mit einem Konto an, um zuzuschauen",
    # firewall hint on the Online tab (t5lobby.fwcheck, tk_tab.fw_hint_text)
    "Firewall":
        "Firewall",
    "How to fix":
        "So behebst du es",
    "Windows Firewall blocks {program} on this network. Matches still connect, but some only "
    "through a relay, with more lag.":
        "Die Windows-Firewall blockiert {program} in diesem Netzwerk. Matches kommen trotzdem "
        "zustande, manche aber nur über ein Relay, mit mehr Lag.",
    "A firewall seems to block T5DR Online's network traffic on this PC.":
        "Eine Firewall scheint den Netzwerkverkehr von T5DR Online auf diesem PC zu blockieren.",
    # patch 0063 (igpu-4k-stall): Internal resolution Auto, integrated-graphics and GPU-bound hints
    "Auto (matches the screen)":
        "Auto (passend zum Bildschirm)",
    "The game picks the step that matches your screen when it starts, at most 1080p on integrated graphics (they share the processor's memory and power).":
        "Das Spiel wählt beim Start die Stufe, die zu deinem Bildschirm passt, mit integrierter Grafik höchstens 1080p (sie teilt sich Speicher und Strom mit dem Prozessor).",
    "On this PC: {step}.":
        "Auf diesem PC: {step}.",
    "{step} on integrated graphics: a busy built-in GPU slows the processor too (they share its power and memory). For 60 fps choose Auto in Settings -> Internal resolution: {better} here.":
        "{step} mit integrierter Grafik: eine ausgelastete eingebaute GPU bremst auch den Prozessor (sie teilen sich Strom und Speicher). Für 60 fps wähle Auto unter Einstellungen -> Interne Auflösung: hier {better}.",
    "Auto is the default on integrated graphics.":
        "Mit integrierter Grafik ist Auto der Standard.",
    "Your processor ran at {ghz} GHz ({percent} % of its normal speed): set Windows power mode to Best performance.":
        "Dein Prozessor lief mit {ghz} GHz ({percent} % seiner normalen Geschwindigkeit): stell den Energiemodus von Windows auf Beste Leistung.",
    "Extra settings below set {setting}: that wins over this choice.":
        "Die zusätzlichen Einstellungen unten setzen {setting}: das gilt statt dieser Auswahl.",
    "Fights were slower than 60 fps because of the graphics (GPU-bound): choose a lower Internal resolution in Settings.":
        "Kämpfe liefen langsamer als 60 fps wegen der Grafik (GPU-limitiert): wähle in den Einstellungen eine niedrigere interne Auflösung.",
    "Fights were slower than 60 fps: the integrated graphics were busy and slowed the processor too. A lower Internal resolution in Settings helps.":
        "Kämpfe liefen langsamer als 60 fps: die integrierte Grafik war ausgelastet und hat auch den Prozessor gebremst. Eine niedrigere interne Auflösung in den Einstellungen hilft.",
    "Fights were slower than 60 fps because of the graphics card: it is too slow for this game. Internal resolution Lowest helps a little at most.":
        "Kämpfe liefen langsamer als 60 fps wegen der Grafikkarte: sie ist zu langsam für das Spiel. Die interne Auflösung Niedrigste hilft höchstens ein wenig.",
    "Fights were slower than 60 fps because of the processor: close other programs while you play. A lower Internal resolution does not help.":
        "Kämpfe liefen langsamer als 60 fps wegen des Prozessors: schließe beim Spielen andere Programme. Eine niedrigere interne Auflösung hilft nicht.",
    # ---- private and community rooms (lobby/t5lobby/tk_rooms.py; the server's messages: i18n_known.py)
    "private rooms need a newer launcher; update it": "Private Räume brauchen einen neueren Launcher; aktualisiere ihn",
    "only the room's host can do that": "Das kann nur der Gastgeber des Raums",
    "too many wrong room passwords; try again in {seconds} s":
        "Zu viele falsche Raum-Passwörter; versuche es in {seconds} s wieder",
    "wrong room password": "Falsches Raum-Passwort",
    "the room's password changed; try again": "Das Passwort des Raums hat sich geändert; versuche es noch einmal",
    "no room has that invite code": "Kein Raum hat diesen Einladungscode",
    "rooms hold 2 to {count} players": "In einen Raum passen 2 bis {count} Spieler",
    "room passwords are 4-64 characters, no space at either end":
        "Raum-Passwörter haben 4-64 Zeichen, ohne Leerzeichen am Anfang oder Ende",
    "private and community rooms are casual (unranked)": "Private und Community-Räume sind casual (nicht ranked)",
    "you are in that room": "Du bist in diesem Raum",
    "the room's host removed you from this room": "Der Gastgeber hat dich aus diesem Raum entfernt",
    "the room's host turned away password guesses from your network; ask the host for an invite":
        "Der Gastgeber des Raums hat Passwort-Versuche aus deinem Netz abgewiesen; bitte ihn um eine Einladung",
    "only a room with a password counts wrong guesses": "Nur ein Raum mit Passwort zählt falsche Versuche",
    "that player is not in your room": "Dieser Spieler ist nicht in deinem Raum",
    "you cannot remove yourself; leave the room instead":
        "Du kannst dich nicht selbst entfernen; verlasse den Raum stattdessen",
    "you can remove that player after their match": "Du kannst diesen Spieler nach seinem Match entfernen",
    "only rooms for 3 or more players take turns": "Nur Räume für 3 oder mehr Spieler wechseln sich ab",
    "you sit out in the room; press Back in line to play again":
        "Du setzt im Raum aus; drücke Wieder anstellen, um wieder zu spielen",
    "the room picks the next match by itself": "Der Raum wählt das nächste Match selbst",
    "the room's host removed that player from this room": "Der Gastgeber hat diesen Spieler aus diesem Raum entfernt",
    "only the room's players can watch its match": "Nur die Spieler des Raums können sein Match zuschauen",
    "Anybody": "Alle",
    "Back in line": "Wieder anstellen",
    "Back in line: you play when it is your turn.": "Wieder angestellt: Du spielst, wenn du dran bist.",
    "Copy invite code": "Einladungscode kopieren",
    "Create a room": "Raum erstellen",
    "Everyone in turn": "Alle der Reihe nach",
    "Hide the room from the room list": "Raum in der Raumliste verstecken",
    "In the room “{name}”: {count}/{size} players, taking turns.":
        "Im Raum „{name}“: {count}/{size} Spieler, ihr wechselt euch ab.",
    "Invite code": "Einladungscode",
    "Line: {names}": "Reihe: {names}",
    "New invite code": "Neuer Einladungscode",
    "Next: {p1} vs {p2} in {seconds} s": "Als Nächstes: {p1} gegen {p2} in {seconds} s",
    "No room selected. Join a room with its invite code (XXXX-XXXX-XXXX):":
        "Kein Raum gewählt. Tritt einem Raum mit seinem Einladungscode bei (XXXX-XXXX-XXXX):",
    "Password (4-64 characters):": "Passwort (4-64 Zeichen):",
    "Players in the room:": "Spieler im Raum:",
    "Players:": "Spieler:",
    "Playing: {p1} vs {p2}": "Es spielen: {p1} gegen {p2}",
    "Private (invite code)": "Privat (Einladungscode)",
    "Private (password)": "Privat (Passwort)",
    "Remove player": "Spieler entfernen",
    "Remove {name} from the room? They cannot come back into it.":
        "{name} aus dem Raum entfernen? Er kann nicht wieder hinein.",
    "Removed {name} from the room.": "{name} wurde aus dem Raum entfernt.",
    "Wrong passwords in the last 10 minutes: {count} (networks: {networks})":
        "Falsche Passwörter in den letzten 10 Minuten: {count} (Netze: {networks})",
    "Turn away the guessers": "Passwort-Rater abweisen",
    "Networks turned away: {count}. They cannot try passwords on this room any more.":
        "Abgewiesene Netze: {count}. Von dort kann niemand mehr Passwörter für diesen Raum ausprobieren.",
    "Room created.": "Raum erstellt.",
    "Room created. Press Copy invite code to see the code you can share.":
        "Raum erstellt. Drücke Einladungscode kopieren, um den Code zum Weitergeben zu sehen.",
    "Room name (optional):": "Name des Raums (optional):",
    "Room password": "Raum-Passwort",
    "Room passwords are 4-64 characters, with no space at the start or end.":
        "Raum-Passwörter haben 4-64 Zeichen, ohne Leerzeichen am Anfang oder Ende.",
    "Room settings": "Raum-Einstellungen",
    "Room settings saved.": "Raum-Einstellungen gespeichert.",
    "Room settings...": "Raum-Einstellungen...",
    "Sit out": "Aussetzen",
    "The invite code is in the field next to the button: select it and press Ctrl+C to copy it.":
        "Der Einladungscode steht im Feld neben dem Knopf: markiere ihn und drücke Strg+C, um ihn zu kopieren.",
    "The room's invite code (XXXX-XXXX-XXXX):": "Einladungscode des Raums (XXXX-XXXX-XXXX):",
    "Turns (3 or more players):": "Reihenfolge (ab 3 Spielern):",
    "Who can join:": "Wer beitreten kann:",
    "Winner stays": "Gewinner bleibt",
    "You sit out: your turns are skipped until you press Back in line.":
        "Du setzt aus: Deine Runden werden übersprungen, bis du Wieder anstellen drückst.",
    "Your room: {name}": "Dein Raum: {name}",
    "hidden": "versteckt",
    "invites you to the private room “{room}”. Accept to join it without its password.":
        "lädt dich in den privaten Raum „{room}“ ein. Nimm an, um ohne sein Passwort hineinzukommen.",
    "private": "privat",
    "private (invite code)": "privat (Einladungscode)",
    "private (password)": "privat (Passwort)",
    "{count}/{size} players": "{count}/{size} Spieler",
    "{name} (host)": "{name} (Gastgeber)",
    "{name} (sitting out)": "{name} (setzt aus)",
    "{name} ({rank}) invites you to the private room “{room}”":
        "{name} ({rank}) lädt dich in den privaten Raum „{room}“ ein",
    "“{room}” is private. Its password:": "„{room}“ ist privat. Sein Passwort:",
    "this server has no private rooms": "Dieser Server hat keine privaten Räume",
    # training rooms and the health handicap (1.1.5)
    "My health (casual)": "Meine Gesundheit (locker)",
    "TRAINING OVER": "TRAINING VORBEI",
    "TRAINING: endless health, nothing counted; hold SELECT for 1 s to pick again": "TRAINING: endlose Gesundheit, nichts zählt; SELECT 1 s halten, um neu zu wählen",
    "Training fight over -- nothing is counted": "Trainingskampf vorbei -- nichts wird gezählt",
    "Training room: endless health, nothing counted": "Trainingsraum: endlose Gesundheit, nichts zählt",
    "Training vs {name}": "Training gegen {name}",
    "health: you {you} %, opponent {opponent} %": "Gesundheit: du {you} %, Gegner {opponent} %",
    "training": "Training",
    "training: endless health, nothing counted": "Training: endlose Gesundheit, nichts zählt",
    "{percent} %": "{percent} %",
    "training rooms need a newer launcher; update it": "Trainingsräume brauchen einen neueren Launcher; aktualisiere ihn",
    "training rooms are casual (unranked)": "Trainingsräume sind locker (ohne Wertung)",
    "the health handicap needs a newer launcher; update it": "Das Gesundheits-Handicap braucht einen neueren Launcher; aktualisiere ihn",
    "life is 30 to 100 in steps of 10": "Die Gesundheit ist 30 bis 100 in Zehnerschritten",
    "this server has no training rooms": "Dieser Server hat keine Trainingsräume",
    "this server has no health handicap": "Dieser Server hat kein Gesundheits-Handicap",
    # Settings -> Graphics (patch 0079)
    "Graphics (weak graphics cards)":
        "Grafik (schwache Grafikkarten)",
    "Shadows":
        "Schatten",
    "Effects":
        "Effekte",
    "On (default)":
        "An (Standard)",
    "Off: no shadows of the fighters and the stage. Saves graphics work and some processor time.":
        "Aus: keine Schatten der Kämpfer und der Stage. Spart "
        "Grafikarbeit und etwas Prozessorzeit.",
    "Off: no hit sparks or other hit effects (also the EWGF lightning), flames, smoke, mist, glows or "
    "waterfalls. Saves graphics work (the most on misty stages) and some processor time.":
        "Aus: keine Treffer-Funken und keine anderen "
        "Treffer-Effekte (auch der EWGF-Blitz fehlt), keine "
        "Flammen, kein Rauch, Nebel, Leuchten und keine "
        "Wasserfälle. Spart Grafikarbeit (am "
        "meisten auf nebligen Stages) und etwas Prozessorzeit.",
    "Lowest (old graphics cards)":
        "Am niedrigsten (alte Grafikkarten)",
    "Default":
        "Standard",
    "Lowest: Internal resolution Lowest; stage blur / glow and shadows off. Effects stay on: the hit effects show what happens in a fight. Default puts them back. Only your picture changes: online, both players can choose differently.":
        "Am niedrigsten: Interne Auflösung „Am niedrigsten“; Stage-Unschärfe / Leuchten und Schatten aus. Die Effekte bleiben an: Die Treffer-Effekte zeigen, was im Kampf passiert. „Standard“ stellt sie wieder her. Nur dein Bild ändert sich: Online kann jeder Spieler selbst wählen.",
    # ---- lobby/t5lobby/tk_casual.py
    "Any side": "Seite egal",
    "P1 (left)": "P1 (links)",
    "P2 (right)": "P2 (rechts)",
    "Challenges, invites, rooms:": "Herausforderungen, Einladungen, Räume:",
    "Random stage": "Zufällige Stage",
    "wants to be P{n} on {stage}": "will P{n} sein, auf {stage}",
    "wants to be P{n}": "will P{n} sein",
    "wants to play on {stage}": "will auf {stage} spielen",
    "You both wanted P{n}: a coin flip made you P{m}.": "Ihr wolltet beide P{n}: Der Münzwurf macht dich zu P{m}.",
    "Your opponent wanted another stage: a coin flip chose {stage}.":
        "Dein Gegner wollte eine andere Stage: Der Münzwurf hat {stage} gewählt.",
    "P{n} on {stage}": "P{n} auf {stage}",
    "Rematch: swap sides": "Rematch: Seiten tauschen",
    "with the sides swapped": "mit getauschten Seiten",
    # the fold button right of the Online tab's lists (tk_views.toggle_top)
    "Hide": "Ausblenden",
    "Show": "Einblenden",
}
