"""French texts for the launcher and the Online tab (t5lobby/i18n.py).

English text -> French text. The English text is the key, exactly as written in t("...") / N_("...");
the French one keeps the same {placeholders}. Friendly French in the tu-form, short and the way players
talk ("manette", "match", "salon"). Names players know from the game and the lobby stay as they are:
Quick Match, Ranked, BUILD GAME, Rematch, Rollback, lobby, input delay, ping, the character and rank names.

Machine-assisted translation: corrections from players are welcome (docs/ONLINE.md "Languages").
Same keys and groups as i18n_de.py; tests/test_i18n.py and tools/i18n_extract.py check every catalog.
"""

MESSAGES = {
    # ---- launcher/controls_edit.py
    "Removed {sources} from your buttons: that is L2 / R2 at rest on a PlayStation pad, so the game held them all the time. Save to keep this.":
        "{sources} retiré de tes boutons : c'est L2 / R2 au repos sur une manette PlayStation, donc le jeu les gardait enfoncés en permanence. Enregistre pour garder ce changement.",
    "Attack buttons": "Boutons d'attaque",
    "Several buttons with one press (macros)": "Plusieurs boutons en un appui (macros)",
    "Start, Select and the other buttons": "Start, Select et les autres boutons",
    "Directions": "Directions",
    "1 (Left Punch)": "1 (Poing gauche)",
    "2 (Right Punch)": "2 (Poing droit)",
    "3 (Left Kick)": "3 (Pied gauche)",
    "4 (Right Kick)": "4 (Pied droit)",
    "Select": "Select",
    "Start / pause": "Start / pause",
    "Down": "Bas",
    "Left": "Gauche",
    "Up": "Haut",
    "Right": "Droite",
    "PlayStation pad, default": "Manette PlayStation, par défaut",
    "Xbox pad, default": "Manette Xbox, par défaut",
    "X Y A B are 1 2 3 4; bumpers and triggers are L1 R1 L2 R2.":
        "X Y A B sont 1 2 3 4 ; bumpers et gâchettes sont L1 R1 L2 R2.",
    "Square Triangle Cross Circle are 1 2 3 4 (DualShock 4, DualSense and most "
    "PS3/PS4-mode sticks).":
        "Carré Triangle Croix Rond sont 1 2 3 4 (DualShock 4, DualSense et la plupart des sticks en mode PS3/PS4).",
    "Switch pad, default": "Manette Switch, par défaut",
    "Y X B A are 1 2 3 4 (Switch Pro controller, sticks in Switch mode).":
        "Y X B A sont 1 2 3 4 (manette Switch Pro, sticks en mode Switch).",
    "Xbox-style pad (generic)": "Manette type Xbox (générique)",
    "A B X Y buttons and LB RB, for Xbox-like pads that Windows does not give to XInput.":
        "Boutons A B X Y et LB RB, pour les manettes type Xbox que Windows ne confie pas à XInput.",
    "8-button stick (Vewlix layout)": "Stick 8 boutons (disposition Vewlix)",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: X Y RB LB over A B RT LT.":
        "Rangée du haut 1 2 [1+2] [1+3], du bas 3 4 [3+4] [2+4] : X Y RB LB au-dessus de A B RT LT.",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: B1 B4 B6 B5 over B2 B3 B8 B7.":
        "Rangée du haut 1 2 [1+2] [1+3], du bas 3 4 [3+4] [2+4] : B1 B4 B6 B5 au-dessus de B2 B3 B8 B7.",
    "6-button stick (Noir / Sega Astro)": "Stick 6 boutons (Noir / Sega Astro)",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: X Y RB over A B RT. LB and LT stay L1 and "
    "L2.":
        "Rangée du haut 1 2 [1+2], du bas 3 4 [3+4] : X Y RB au-dessus de A B RT. LB et LT restent L1 et L2.",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: B1 B4 B6 over B2 B3 B8. B5 and B7 stay L1 "
    "and L2.":
        "Rangée du haut 1 2 [1+2], du bas 3 4 [3+4] : B1 B4 B6 au-dessus de B2 B3 B8. B5 et B7 restent L1 et L2.",
    "Hitbox": "Hitbox",
    "The 8-button layout above. Directions come from the d-pad or the left stick, which "
    "is read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "La disposition 8 boutons ci-dessus. Les directions viennent de la croix ou du stick gauche, lu comme une "
        "croix 8 directions ; gauche+droite (haut+bas) en même temps s'annulent.",
    "The 8-button layout above. Directions come from the hat or the left stick, which is "
    "read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "La disposition 8 boutons ci-dessus. Les directions viennent du hat ou du stick gauche, lu comme une croix 8 "
        "directions ; gauche+droite (haut+bas) en même temps s'annulent.",
    "The file has {n} settings; the game reads at most {max}.":
        "Le fichier contient {n} réglages ; le jeu en lit au plus {max}.",
    "The file has {n} sections; the game reads at most {max}.":
        "Le fichier contient {n} sections ; le jeu en lit au plus {max}.",
    "Changed lines of {sections} that would have overridden this ({what}).":
        "Lignes modifiées de {sections} qui auraient remplacé ceci ({what}).",
    "Lines of your file in other sections still change some buttons.":
        "Des lignes de ton fichier dans d'autres sections changent encore certains boutons.",
    "Other lines in your file ({sections}) still change this layout.":
        "D'autres lignes de ton fichier ({sections}) changent encore cette disposition.",
    "{n} lines removed.": "{n} lignes supprimées.",
    # ---- launcher/controls_ui.py
    "DirectInput controller": "Manette DirectInput",
    "Xbox pad (XInput)": "Manette Xbox (XInput)",
    "PlayStation pad, read directly": "Manette PlayStation, lue directement",
    "Arrows move; A S on top are 1 2, Z X below are 3 4. Q W are L1 R1, 1 2 are L2 R2, Enter is Start, Tab is Select.": "Les flèches déplacent ; A S en haut sont 1 2, Z X en dessous 3 4. Q W sont L1 R1, 1 2 sont L2 R2, Entrée est Start, Tab est Select.",
    "Arrows move; number pad 4 5 are 1 2, 1 2 are 3 4, 6 is 1+2, 3 is 3+4 (Num Lock on).": "Les flèches déplacent ; pavé numérique 4 5 sont 1 2, 1 2 sont 3 4, 6 est 1+2, 3 est 3+4 (Verr Num actif).",
    "Esc (leaves the game)": "Échap (quitte le jeu)",
    "F11 (fullscreen)": "F11 (plein écran)",
    'F2 (training overlay)': "F2 (affichage d'entraînement)",
    "Keyboard, second player": "Clavier, second joueur",
    "Keyboard: WASD and U I J K": "Clavier : WASD et U I J K",
    "Keyboard: arrows and A S Z X": "Clavier : flèches et A S Z X",
    "Keyboard: arrows and number pad": "Clavier : flèches et pavé numérique",
    "Keyboard: pick a game button, then Set selected (or double-click it) and press the key. Esc stops. The game reads the keyboard while its window has the focus.": "Clavier : choisis un bouton du jeu, puis « Régler la sélection » (ou double-clic) et appuie sur la touche. Échap arrête. Le jeu lit le clavier tant que sa fenêtre a le focus.",
    "Press only that one key. Esc stops.": "Appuie sur cette seule touche. Échap arrête.",
    "Press the key for {button}...": "Appuie sur la touche pour {button}...",
    "The keyboard ([{section}] in controls.ini)": "Le clavier ([{section}] dans controls.ini)",
    "W A S D move; U I are 1 2, J K are 3 4, O is 1+2, L is 3+4. Y P are L1 R1, H and ; are L2 R2, Enter is Start, Backspace is Select.": "W A S D déplacent ; U I sont 1 2, J K sont 3 4, O est 1+2, L est 3+4. Y P sont L1 R1, H et ; sont L2 R2, Entrée est Start, Retour arrière est Select.",
    "{key} is the game's own key; press another one.": '{key} est une touche du jeu lui-même ; appuie sur une autre.',
    "{source} is also {other} for the second keyboard player.": "{source} est aussi {other} pour le second joueur au clavier.",
    "Controls - T5DR Online": "Commandes - T5DR Online",
    "Press a button on a controller to pick it, then set its buttons. The game reads the "
    "file when it starts.":
        "Appuie sur un bouton d'une manette pour la choisir, puis règle ses boutons. Le jeu lit le fichier au "
        "démarrage.",
    "Controllers": "Manettes",
    "Player": "Joueur",
    "Controller": "Manette",
    "Pressed now": "Appuyé",
    "Move through this window with the controller": "Naviguer dans cette fenêtre à la manette",
    "Buttons": "Boutons",
    "Game button": "Bouton du jeu",
    "Controller button": "Bouton de la manette",
    "Set up all buttons": "Régler tous les boutons",
    "Set up directions": "Régler les directions",
    "Set selected": "Régler la sélection",
    "Clear": "Effacer",
    "Layout": "Disposition",
    "Use this layout": "Utiliser cette disposition",
    "Reset to defaults": "Rétablir par défaut",
    "Your changes apply to": "Tes changements s'appliquent à",
    "Player and directions": "Joueur et directions",
    "Automatic": "Automatique",
    "Player 1": "Joueur 1",
    "Player 2": "Joueur 2",
    "8-way d-pad": "Croix 8 directions",
    "Analog stick": "Stick analogique",
    "Both cancel (neutral)": "Les deux s'annulent (neutre)",
    "Up wins (Up+Down is Up)": "Haut l'emporte (Haut+Bas = Haut)",
    "Last direction wins": "La dernière direction l'emporte",
    "Pass both through": "Laisser passer les deux",
    "This controller is": "Cette manette est",
    "Left stick": "Stick gauche",
    "Opposite directions": "Directions opposées",
    "Left stick, 8-way d-pad: a hitbox or stick in left-stick mode sends the direction "
    "as a stick; the game then reads it as d-pad presses. Left+Right (or Up+Down) at "
    "once happens on keyboards and hitboxes; the game cannot take both. Stick and "
    "opposite directions belong to the player's port.":
        "Stick gauche, croix 8 directions : un hitbox ou un stick en mode stick gauche envoie la direction comme un "
        "stick ; le jeu la lit comme des appuis sur la croix. Gauche+Droite (ou Haut+Bas) en même temps arrive sur "
        "les claviers et hitboxes ; le jeu ne peut pas prendre les deux. Stick et directions opposées dépendent du "
        "port du joueur.",
    "Skip": "Passer",
    "Stop": "Arrêter",
    "Save": "Enregistrer",
    "Revert": "Rétablir",
    "Close": "Fermer",
    "no controller": "aucune manette",
    "Controllers cannot be read on this PC.": "Impossible de lire les manettes sur ce PC.",
    "No controller found. Plug one in; it shows up here by itself.":
        "Aucune manette trouvée. Branches-en une ; elle apparaîtra ici toute seule.",
    "switched off in [general]": "désactivé dans [general]",
    "no free player port": "aucun port joueur libre",
    "No controller chosen": "Aucune manette choisie",
    "This controller model ({vid}:{pid})": "Ce modèle de manette ({vid}:{pid})",
    "This controller model (no USB ID)": "Ce modèle de manette (sans ID USB)",
    "All DirectInput controllers": "Toutes les manettes DirectInput",
    "All Xbox pads (XInput)": "Toutes les manettes Xbox (XInput)",
    "Only the controller on player {n}'s port": "Seulement la manette sur le port du joueur {n}",
    "no player": "aucun joueur",
    "player {n}": "joueur {n}",
    "yours": "perso",
    "Your own layout": "Ta propre disposition",
    "Player {n}": "Joueur {n}",
    "Buttons you set yourself, or a mix. Pick a layout to start from it.":
        "Des boutons réglés par toi, ou un mélange. Choisis une disposition pour partir de celle-ci.",
    "On the controller: {up} / {down} choose a button, {accept} sets it, {clear} clears "
    "it, {save} saves, {back} closes. The game reads the file when it starts.":
        "À la manette : {up} / {down} choisissent un bouton, {accept} le règle, {clear} l'efface, {save} enregistre, "
        "{back} ferme. Le jeu lit le fichier au démarrage.",
    "(no game button)": "(aucun bouton du jeu)",
    "Press a button on a controller first, or pick one in the list.":
        "Appuie d'abord sur un bouton d'une manette, ou choisis-en une dans la liste.",
    "Press the button for {button}...": "Appuie sur le bouton pour {button}...",
    "Press only that one button on the controller.": "Appuie uniquement sur ce bouton de la manette.",
    "{n} of {total}.": "{n} sur {total}.",
    "Wait a few seconds to skip it.": "Attends quelques secondes pour le passer.",
    "That was several buttons at once ({sources}). Press one button only.":
        "C'était plusieurs boutons à la fois ({sources}). Appuie sur un seul.",
    "{button}: skipped.": "{button} : passé.",
    "{button} = {source}.": "{button} = {source}.",
    "{source} was {other}; that one has no button now.": "{source} était {other} ; celui-ci n'a plus de bouton.",
    "Stopped.": "Arrêté.",
    "{button}: cleared.": "{button} : effacé.",
    "Layout: {name}.": "Disposition : {name}.",
    "Pick a layout in the list first.": "Choisis d'abord une disposition dans la liste.",
    "Put {name} back to the default buttons? Your comments and other settings in "
    "controls.ini stay.":
        "Remettre {name} sur les boutons par défaut ? Tes commentaires et autres réglages dans controls.ini restent.",
    "The part of the file that is for all {kind} controllers has button lines too. Reset "
    "those as well?":
        "La partie du fichier pour toutes les manettes {kind} contient aussi des lignes de boutons. Les remettre par "
        "défaut aussi ?",
    "Reset to the defaults. Save to keep it.": "Remis par défaut. Enregistre pour le garder.",
    "{name} is {player}. Save to keep it.": "{name} est {player}. Enregistre pour le garder.",
    "controls.ini changed": "controls.ini a changé",
    "controls.ini was changed by something else since this screen opened. Overwrite it "
    "with your settings? (The old file is kept as controls.ini.bak.)":
        "controls.ini a été modifié par autre chose depuis l'ouverture de cet écran. L'écraser avec tes réglages ? "
        "(L'ancien fichier est gardé sous controls.ini.bak.)",
    "Could not save: {error}": "Impossible d'enregistrer : {error}",
    "Saved {path}. The game reads it when it starts.": "{path} enregistré. Le jeu le lit au démarrage.",
    "The game that is running keeps its old buttons until you start it again.":
        "Le jeu en cours garde ses anciens boutons jusqu'à ce que tu le relances.",
    "Changes undone.": "Changements annulés.",
    "There are unsaved changes. Save them first, or close with the mouse.":
        "Il y a des changements non enregistrés. Enregistre-les d'abord, ou ferme avec la souris.",
    "Controls": "Commandes",
    "Save the changes to controls.ini?": "Enregistrer les changements dans controls.ini ?",
    # ---- launcher/core.py
    "Auto (laptops, handhelds, integrated graphics)": "Auto (portables, handhelds, puce graphique intégrée)",
    "On": "Activé",
    "a mobile processor": "un processeur mobile",
    "battery saver is on": "l'économiseur de batterie de Windows est activé",
    "the Power saver power plan is on": "le mode de gestion « Économie d'énergie » est actif",
    "this PC has a battery (laptop or handheld)": "ce PC a une batterie (portable ou handheld)",
    "Inputs": "Inputs",
    "Inputs + frame data": "Inputs + données de frames",
    "Auto (Windows language)": "Auto (langue de Windows)",
    "No package chosen.": "Aucun paquet choisi.",
    "File not found.": "Fichier introuvable.",
    "Cannot read the file: {error}": "Impossible de lire le fichier : {error}",
    "This is not a PS3 package (.pkg).": "Ce n'est pas un paquet PS3 (.pkg).",
    "{id}  ({size} bytes) -- the supported version": "{id}  ({size} octets) -- la version prise en charge",
    "{id}  ({size} bytes) -- Tekken 5 DR, but not the supported package ({supported}). "
    "The build will most likely refuse it.":
        "{id}  ({size} octets) -- Tekken 5 DR, mais pas le paquet pris en charge ({supported}). La compilation le "
        "refusera très probablement.",
    "{id}  ({size} bytes) -- not Tekken 5 DR Online ({title_id}).":
        "{id}  ({size} octets) -- pas Tekken 5 DR Online ({title_id}).",
    "No license chosen.": "Aucune licence choisie.",
    "Not a PS3 license: a .rap file is exactly 16 bytes.":
        "Ce n'est pas une licence PS3 : un fichier .rap fait exactement 16 octets.",
    "{name} -- matches the supported package": "{name} -- correspond au paquet pris en charge",
    "{name} -- matches the package": "{name} -- correspond au paquet",
    "{name} -- the name does not match the package's content ID; it may be the wrong "
    "license.":
        "{name} -- le nom ne correspond pas au content ID du paquet ; ce n'est peut-être pas la bonne licence.",
    "The output folder": "Le dossier de sortie",
    "This folder": "Ce dossier",
    "{label} has a long path ({bytes} bytes). Windows allows only {max} characters for a "
    "file path, and the build writes files about {room} characters deeper. Move the "
    "folder to a short path, for example {example}.":
        "{label} a un chemin long ({bytes} octets). Windows n'autorise que {max} caractères pour un chemin de "
        "fichier, et la compilation écrit des fichiers environ {room} caractères plus loin. Déplace le dossier vers "
        "un chemin court, par exemple {example}.",
    "This folder is inside OneDrive. OneDrive would upload about 1 GB of game data and "
    "can lock files while the game is built. Move the folder out of OneDrive, for "
    "example to {example}.":
        "Ce dossier est dans OneDrive. OneDrive enverrait environ 1 Go de données du jeu et peut verrouiller des "
        "fichiers pendant la compilation. Sors le dossier de OneDrive, par exemple vers {example}.",
    "This folder is in Program Files, where Windows does not let programs write. Move it "
    "to a folder of your own, for example {example}.":
        "Ce dossier est dans Program Files (Programmes), où Windows n'autorise pas les programmes à écrire. "
        "Déplace-le dans un dossier à toi, par exemple {example}.",
    "Windows does not let the launcher write into this folder. Move it to a folder of "
    "your own, for example {example}.":
        "Windows n'autorise pas le launcher à écrire dans ce dossier. Déplace-le dans un dossier à toi, par exemple "
        "{example}.",
    "This folder is on a network share. Building and playing from there is slow and was "
    "not tested; copy it to a local drive.":
        "Ce dossier est sur un partage réseau. Compiler et jouer depuis là est lent et n'a pas été testé ; copie-le "
        "sur un disque local.",
    "The game is not built yet. Open the Build tab, choose your .pkg and .rap, press "
    "BUILD GAME.":
        "Le jeu n'est pas encore compilé. Ouvre l'onglet Compiler, choisis ton .pkg et ton .rap, puis appuie sur "
        "BUILD GAME.",
    "t5dr.exe is there but the game data is missing. Build again.":
        "t5dr.exe est là, mais les données du jeu manquent. Recompile.",
    "The decrypted program has SHA-1 {sha}..., not the supported version. Build again "
    "from the supported package.":
        "Le programme déchiffré a le SHA-1 {sha}..., ce n'est pas la version prise en charge. Recompile à partir du "
        "paquet pris en charge.",
    "Build the game once (about 2 minutes): this version of the launcher changes the "
    "game code. Click BUILD GAME. Your unpacked game and saves are kept; only the code "
    "is translated and compiled again.":
        "Compile le jeu une fois (environ 2 minutes) : cette version du launcher change le code du jeu. Clique sur "
        "BUILD GAME. Ton jeu décompressé et tes sauvegardes sont conservés ; seul le code est retraduit et "
        "recompilé.",
    "Ready: {title_id} v{version}, program SHA-1 {sha}... verified, built {when}.":
        "Prêt : {title_id} v{version}, SHA-1 du programme {sha}... vérifié, compilé {when}.",
    "Check & decrypt": "Vérifier et déchiffrer",
    "Key data": "Données de clés",
    "Recompiler": "Recompilateur",
    "Unpack": "Extraire",
    "Compile": "Compiler",
    "Game files": "Fichiers du jeu",
    "Sound core": "Moteur audio",
    "Translate code": "Traduire le code",
    "The translation step has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, close other programs, press Cancel and then BUILD GAME again; build.log "
    "has the details.":
        "L'étape « Traduire le code » n'a rien affiché depuis {minutes} minutes. Sur un PC lent ou très occupé, elle "
        "peut encore travailler. Si rien ne change, ferme les autres programmes, clique sur Annuler puis à nouveau "
        "sur BUILD GAME ; build.log contient les détails.",
    "The graphics card stopped working for the game (the driver crashed, was reset or "
    "updated). Start the game again. If it happens again, update the graphics driver.":
        "La carte graphique a cessé de fonctionner pour le jeu (le pilote a planté, a été réinitialisé ou mis à "
        "jour). Relance le jeu. Si ça se reproduit, mets à jour le pilote graphique.",
    "This PC's graphics card or driver cannot run Direct3D 12. Install the newest "
    "graphics driver from AMD, Intel or NVIDIA.":
        "La carte graphique ou le pilote de ce PC ne gère pas Direct3D 12. Installe le dernier pilote graphique "
        "d'AMD, Intel ou NVIDIA.",
    "This processor is too old for the game: it lacks the SSE4.1 instructions "
    "(processors from about 2008 on have them).":
        "Ce processeur est trop ancien pour le jeu : il lui manque les instructions SSE4.1 (les processeurs depuis "
        "2008 environ les ont).",
    "The game was built on a PC with a newer processor (AVX2). Press BUILD GAME to build "
    "it again for this PC; your saves are kept.":
        "Le jeu a été compilé sur un PC avec un processeur plus récent (AVX2). Appuie sur BUILD GAME pour le "
        "recompiler pour ce PC ; tes sauvegardes sont conservées.",
    "t5dr_game.dll could not be loaded (missing or blocked). Press BUILD GAME again, and "
    "look in the antivirus quarantine.":
        "Impossible de charger t5dr_game.dll (absent ou bloqué). Appuie à nouveau sur BUILD GAME et regarde dans la "
        "quarantaine de l'antivirus.",
    "The game could not get back to character select after the last match and closed "
    "itself. It starts again for your next match.":
        "Le jeu n'a pas pu revenir à la sélection des personnages après le dernier match et s'est fermé. Il "
        "redémarre pour ton prochain match.",
    "The game stopped after a crash (exit code {code}). The game log has the details.":
        "Le jeu s'est arrêté après un plantage (code de sortie {code}). Le journal du jeu contient les détails.",
    "The game stopped (exit code {code}). The game log has the details.":
        "Le jeu s'est arrêté (code de sortie {code}). Le journal du jeu contient les détails.",
    "t5dr.exe is not built yet": "t5dr.exe n'est pas encore compilé",
    "Lowest (0.5x)": "Minimale (0,5x)",
    "Lower (0.75x)": "Basse (0,75x)",
    "Native (720p)": "Native (720p)",
    "1080p (1.5x)": "1080p (1,5x)",
    "1440p (2x)": "1440p (2x)",
    "4K (3x)": "4K (3x)",
    "The 3D scene at half size (a quarter of its pixels); HUD and text stay sharp. "
    "For integrated graphics and old laptops.":
        "La scène 3D à moitié de sa taille (un quart de ses pixels) ; le HUD et le texte restent nets. Pour les "
        "puces graphiques intégrées et les vieux portables.",
    "The 3D scene at 3/4 size (about half of its pixels); HUD and text stay sharp. "
    "For weak graphics cards.":
        "La scène 3D aux 3/4 de sa taille (environ la moitié de ses pixels) ; le HUD et le texte restent nets. Pour "
        "les cartes graphiques modestes.",
    "The PS3's 1280 x 720. Light on any graphics card; the picture is scaled to your window.":
        "Le 1280 x 720 de la PS3. Léger pour toute carte graphique ; l'image est mise à l'échelle de ta fenêtre.",
    "1920 x 1080: 2.25x the pixels of Native. Sharp on Full HD screens. "
    "If fights drop below 60 fps, go one step down.":
        "1920 x 1080 : 2,25x les pixels de Native. Net sur les écrans Full HD. Si les combats passent sous 60 fps, "
        "descends d'un cran.",
    "2560 x 1440: 4x the pixels of Native. For strong graphics cards. "
    "If fights drop below 60 fps, go one step down.":
        "2560 x 1440 : 4x les pixels de Native. Pour les cartes graphiques puissantes. Si les combats passent sous "
        "60 fps, descends d'un cran.",
    "3840 x 2160: 9x the pixels of Native. For very strong graphics cards "
    "(an RTX 3090 needs 1-2 ms of a 16.7 ms frame). If fights drop below 60 fps, go one step down.":
        "3840 x 2160 : 9x les pixels de Native. Pour les cartes graphiques très puissantes (une RTX 3090 utilise 1-2 "
        "ms d'une image de 16,7 ms). Si les combats passent sous 60 fps, descends d'un cran.",
    "Auto (by ping)": "Auto (selon le ping)",
    "Window, 1280 x 720 (native; larger with Windows display scaling)":
        "Fenêtre, 1280 x 720 (native ; plus grande avec la mise à l'échelle de Windows)",
    "Window, 1920 x 1080": "Fenêtre, 1920 x 1080",
    "Window, 2560 x 1440": "Fenêtre, 2560 x 1440",
    "Maximized window": "Fenêtre agrandie",
    "Borderless fullscreen (Alt+Enter or F11 switches in the game)":
        "Plein écran sans bordure (Alt+Entrée ou F11 bascule en jeu)",
    # ---- launcher/online.py
    "Online play": "Jeu en ligne",
    "The lobby files (lobby/t5lobby) are missing from this copy of the launcher, so "
    "online play is not available.\n\n({reason})":
        "Les fichiers du lobby (lobby/t5lobby) manquent dans cette copie du launcher, le jeu en ligne n'est donc pas "
        "disponible.\n\n({reason})",
    # ---- launcher/problem_report_ui.py
    "Before the zip is made, your Windows user name in file paths becomes <user>, "
    "internet IP addresses become <ip> (addresses of your own network stay), lobby player "
    "names (yours and your opponents') become <player>, and passwords, tokens and match keys "
    "are left out. Your game files, keys, .pkg and .rap are never included. Nothing is "
    "uploaded: you send the zip yourself.":
        "Avant de créer le zip, ton nom d'utilisateur Windows dans les chemins devient <user>, les adresses IP "
        "internet deviennent <ip> (celles de ton propre réseau restent), les noms des joueurs du lobby (le tien et "
        "ceux de tes adversaires) deviennent <player>, et les mots de passe, tokens et clés de match sont retirés. "
        "Tes fichiers du jeu, clés, .pkg et .rap ne sont jamais inclus. Rien n'est envoyé : c'est toi qui envoies le "
        "zip.",
    "{count} bytes": "{count} octets",
    "Report a problem": "Signaler un problème",
    "This makes one zip file on your Desktop with the logs and settings that help to "
    "find the problem. Send the zip to the person who gave you the game, or attach it to "
    "an issue.":
        "Cela crée un fichier zip sur ton Bureau avec les journaux et réglages qui aident à trouver le problème. "
        "Envoie le zip à la personne qui t'a donné le jeu, ou joins-le à une issue.",
    "What happened? (optional)": "Que s'est-il passé ? (facultatif)",
    "What goes into the zip": "Ce qui va dans le zip",
    "Nothing found yet: no game log, no build log.":
        "Rien trouvé pour l'instant : aucun journal du jeu, aucun journal de compilation.",
    "Could not look at the files: {error}": "Impossible d'examiner les fichiers : {error}",
    "Save report on the Desktop": "Enregistrer le rapport sur le Bureau",
    "Cancel": "Annuler",
    "About {size} before it is packed (a zip is smaller).": "Environ {size} avant compression (le zip est plus petit).",
    "About {size}; the limit is {limit}, so the biggest logs are shortened in the "
    "middle.":
        "Environ {size} ; la limite est de {limit}, donc les plus gros journaux sont raccourcis au milieu.",
    "Making the report...": "Création du rapport...",
    "The report could not be made: {error}": "Impossible de créer le rapport : {error}",
    "Report saved": "Rapport enregistré",
    "{size}. Its folder is open.": "{size}. Son dossier est ouvert.",
    "Send this zip to the person who gave you the game, or attach it to an issue at "
    "{url}.":
        "Envoie ce zip à la personne qui t'a donné le jeu, ou joins-le à une issue sur {url}.",
    "Send this zip to the person who gave you the game.": "Envoie ce zip à la personne qui t'a donné le jeu.",
    "(shortened in the middle)": "(raccourci au milieu)",
    "{name}   left out: {reason}": "{name}   retiré : {reason}",
    "Removed from the text files: {user} user or PC names, {ip} IP addresses, {secret} "
    "passwords, tokens or keys, {email} e-mail addresses.":
        "Retiré des fichiers texte : {user} noms d'utilisateur ou de PC, {ip} adresses IP, {secret} mots de passe, "
        "tokens ou clés, {email} adresses e-mail.",
    "Open folder": "Ouvrir le dossier",
    # ---- launcher/t5dr_launcher.pyw
    "Discord": "Discord",
    "Show what I play in my Discord status (Rich Presence)":
        "Afficher ce que je joue dans mon statut Discord (Rich Presence)",
    "\"In lobby\", \"Searching ranked\" or your match (fighters, ranked set score) with a timer, through the "
    "Discord app on this PC. Without Discord running nothing happens.":
        "« Dans le lobby », « Recherche Ranked » ou ton match (personnages, score du set Ranked) avec un chrono, via "
        "l'appli Discord de ce PC. Sans Discord lancé, rien ne se passe.",
    "Power saving (laptops, handhelds)": "Économie d'énergie (portables, handhelds)",
    "No busy waiting and fewer worker threads: the processor stays cooler and keeps its speed, so the game "
    "holds 60 fps longer. The game itself is the same, online too.":
        "Pas d'attente active et moins de threads de travail : le processeur chauffe moins et garde sa vitesse, donc "
        "le jeu tient les 60 fps plus longtemps. Le jeu lui-même est identique, en ligne aussi.",
    "On for this PC.": "Activé sur ce PC.",
    "Off.": "Désactivé.",
    "Auto: on for this PC -- {reason}.": "Auto : activé sur ce PC -- {reason}.",
    "Auto: off for this PC (no battery, no mobile processor); the game turns it on by itself if it runs on "
    "integrated graphics.":
        "Auto : désactivé sur ce PC (pas de batterie, pas de processeur mobile) ; le jeu l'active tout seul s'il "
        "tourne sur une puce graphique intégrée.",
    "Power saving is on.": "L'économie d'énergie est activée.",
    "A": "A",
    "Left punch (1)": "Poing gauche (1)",
    "Square": "Carré",
    "X": "X",
    "Right punch (2)": "Poing droit (2)",
    "S": "S",
    "Triangle": "Triangle",
    "Y": "Y",
    "Cross": "Croix",
    "Left kick (3)": "Pied gauche (3)",
    "Z": "Z",
    "B": "B",
    "Circle": "Rond",
    "Right kick (4)": "Pied droit (4)",
    "Arrow keys": "Flèches",
    "D-pad, left stick": "Croix, stick gauche",
    "Move / menus": "Déplacement / menus",
    "L1 / R1": "L1 / R1",
    "LB / RB": "LB / RB",
    "Q / W": "Q / W",
    "1 / 2": "1 / 2",
    "L2 / R2": "L2 / R2",
    "LT / RT": "LT / RT",
    "Enter": "Entrée",
    "START": "START",
    "Start": "Start",
    "Back": "Back",
    "SELECT": "SELECT",
    "Tab": "Tab",
    "Esc": "Échap",
    "Quit the game": "Quitter le jeu",
    "A / B": "A / B",
    "Cross / Circle": "Croix / Rond",
    "Mouse": "Souris",
    "Online tab: accept / decline": "Onglet En ligne : accepter / refuser",
    "native Windows build  ·  launcher {version}": "version Windows native  ·  launcher {version}",
    "Build": "Compiler",
    "Play offline": "Jouer hors ligne",
    "Settings": "Paramètres",
    "Play online": "Jouer en ligne",
    "Output: {folder}": "Sortie : {folder}",
    "Your game": "Ton jeu",
    "Package (.pkg)": "Paquet (.pkg)",
    "License (.rap)": "Licence (.rap)",
    "Browse…": "Parcourir…",
    "Supported: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version "
    "01.00 -- the package file and the license (.rap) from your own account. Nothing "
    "leaves this PC.":
        "Pris en charge : Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version 01.00 -- le fichier du "
        "paquet et la licence (.rap) de ton propre compte. Rien ne quitte ce PC.",
    "Build tools on this PC": "Outils de compilation sur ce PC",
    "Needed": "Requis",
    "Found": "Trouvé",
    "Checking…": "Vérification…",
    "Details": "Détails",
    "Check again": "Revérifier",
    "Install missing…": "Installer ce qui manque…",
    "Press BUILD GAME. It takes a few minutes; the game data stays in this folder.":
        "Appuie sur BUILD GAME. Ça prend quelques minutes ; les données du jeu restent dans ce dossier.",
    "BUILD GAME": "BUILD GAME",
    "Redo every step": "Refaire toutes les étapes",
    "Keep the PC responsive (slower)": "Garder le PC réactif (plus lent)",
    "Open build.log": "Ouvrir build.log",
    "Report a problem...": "Signaler un problème...",
    "Checking the build…": "Vérification de la compilation…",
    "Your name (shown in the game)": "Ton nom (affiché dans le jeu)",
    "PLAY OFFLINE": "JOUER HORS LIGNE",
    "Arcade, Versus, Practice and the other modes on this PC. To play against people over the "
    "internet, use the":
        "Arcade, Versus, Practice et les autres modes sur ce PC. Pour jouer contre d'autres joueurs sur internet :",
    "Online tab": "onglet En ligne",
    "Stop game": "Arrêter le jeu",
    "Open newest game log": "Ouvrir le dernier journal du jeu",
    "Open saves folder": "Ouvrir le dossier des sauvegardes",
    "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers "
    "both work; see Settings for the keys. Esc closes the game. START skips the intro "
    "movie.":
        "Le jeu s'ouvre dans sa propre fenêtre (DirectX 12). Le clavier et les manettes type Xbox fonctionnent ; les "
        "touches sont dans Paramètres. Échap ferme le jeu. START passe la vidéo d'intro.",
    "Display": "Affichage",
    "The picture is scaled to the window; how sharp it is depends on Internal resolution. "
    "You can also drag the window's edges. Alt+Enter or F11 switches borderless fullscreen "
    "in the game.":
        "L'image est mise à l'échelle de la fenêtre ; sa netteté dépend de la Résolution interne. Tu peux aussi "
        "tirer les bords de la fenêtre. Alt+Entrée ou F11 bascule en plein écran sans bordure en jeu.",
    "Unlocks": "Déblocages",
    "Unlock all stages (the Tekken 5 stages, without clearing Arcade)":
        "Débloquer tous les stages (ceux de Tekken 5, sans finir le mode Arcade)",
    "Unlock Jinpachi and Random select (without clearing Arcade)":
        "Débloquer Jinpachi et la sélection Random (sans finir le mode Arcade)",
    "Unlock all customization items (free in the item shop)":
        "Débloquer tous les objets de personnalisation (gratuits dans l'ITEM SHOP)",
    "Offline only (Arcade, VS, Practice and the rest). Your save is not changed; items you take for free "
    "stay yours (the save is backed up first, in save-backups). Online, both players always get the "
    "same stages; Jinpachi and Random are there in casual matches and rooms, not in ranked.":
        "Hors ligne seulement (Arcade, VS, Practice et le reste). Ta sauvegarde n'est pas modifiée ; les "
        "objets que tu prends gratuitement restent à toi (la sauvegarde est d'abord copiée, dans "
        "save-backups). En ligne, les deux joueurs ont toujours les mêmes stages ; Jinpachi et Random sont "
        "là dans les matchs amicaux et les salons, pas en Ranked.",
    "Sound and start": "Son et démarrage",
    "Mute sound": "Couper le son",
    "Sound and taskbar flash when a match is found or someone joins my room": "Son et clignotement dans la barre des tâches quand un match est trouvé ou que quelqu'un rejoint mon salon",
    "Start minimized, without taking focus (for testing)": "Démarrer réduit, sans prendre le focus (pour les tests)",
    "Advanced: extra settings, one NAME=VALUE per line": "Avancé : réglages supplémentaires, un NOM=VALEUR par ligne",
    "Internal resolution": "Résolution interne",
    "VSync": "VSync",
    "On (smooth, default)": "Activée (fluide, par défaut)",
    "Off (lowest latency, may tear)": "Désactivée (latence minimale, déchirures possibles)",
    "The game always runs at 60 fps, like on the PS3.": "Le jeu tourne toujours à 60 fps, comme sur PS3.",
    "Stage blur / glow": "Flou / halo des stages",
    "Off (default)": "Désactivé (par défaut)",
    "Off": "Désactivé",
    "Some stages blur the picture (the misty swamp) or let the sun glow. Off shows them sharp, "
    "without the glow. Only your picture changes: online, both players can choose differently.":
        "Certains stages floutent l'image (le marais brumeux) ou font briller le soleil. Désactivé les montre nets, "
        "sans le halo. Seule ton image change : en ligne, chaque joueur peut choisir différemment.",
    "Training overlay": "Overlay d'entraînement",
    "Also in the other offline modes (Arcade, Versus, ...)":
        "Aussi dans les autres modes hors ligne (Arcade, Versus, ...)",
    "Also online (only your own inputs, no frame data)":
        "Aussi en ligne (seulement tes inputs, sans données de frames)",
    "In Practice: your last inputs with how many frames each was held, and after each exchange the "
    "startup of the move and who can act first (+3, -12). F2 in the game switches it.":
        "En Practice : tes derniers inputs avec le nombre de frames où chacun a été tenu, et après chaque échange le "
        "startup du coup et qui peut agir en premier (+3, -12). F2 en jeu l'active ou le désactive.",
    "Your screen: {width} x {height}. In fullscreen, {step} matches it.":
        "Ton écran : {width} x {height}. En plein écran, {step} lui correspond.",
    "Online input delay": "Input delay en ligne",
    "Frames. Auto: 1 up to about 60 ms ping, 2 above. 0/1/2 count only when your "
    "opponent picked the same, otherwise Auto. Ranked matches always use 2.":
        "Frames. Auto : 1 jusqu'à environ 60 ms de ping, 2 au-delà. 0/1/2 ne comptent que si ton adversaire a choisi "
        "pareil, sinon Auto. Les matchs Ranked utilisent toujours 2.",
    "Open the game's port on my router during online matches (UPnP / NAT-PMP / PCP)":
        "Ouvrir le port du jeu sur mon routeur pendant les matchs en ligne (UPnP / NAT-PMP / PCP)",
    "Helps the direct connection when your opponent's router is strict. The port is open only while "
    "you play and is closed again afterwards.":
        "Aide la connexion directe quand le routeur de ton adversaire est strict. Le port n'est ouvert que pendant "
        "que tu joues et se referme ensuite.",
    "Set up controllers…": "Régler les manettes…",
    "Pick a pad, stick or hitbox, press the buttons you want for 1 2 3 4 and the rest, "
    "or start from a layout.":
        "Choisis une manette, un stick ou un hitbox, appuie sur les boutons voulus pour 1 2 3 4 et le reste, ou pars "
        "d'une disposition.",
    "(needs the lobby files, which are missing)": "(nécessite les fichiers du lobby, qui manquent)",
    "Action (Tekken default)": "Action (par défaut dans Tekken)",
    "PS3 button": "Bouton PS3",
    "Keyboard": "Clavier",
    "Xbox controller": "Manette Xbox",
    "Keyboard and the first XInput controller both drive player 1 (they are combined). "
    "The keyboard only counts while the game window has focus. The game's own Options menu can change "
    "the button layout for offline play; online games use the launcher's buttons only.":
        "Le clavier et la première manette XInput contrôlent tous deux le joueur 1 (ils sont combinés). Le clavier "
        "ne compte que quand la fenêtre du jeu a le focus. Le menu Options du jeu peut changer la disposition des "
        "boutons pour jouer hors ligne ; en ligne, seuls les boutons du launcher comptent.",
    "In this window, on the Online tab, a controller or arcade stick works without mouse "
    "or keyboard: Cross / A accepts a match or rematch and starts a search, Circle / B "
    "declines, leaves or stops the search. It only counts while this window is in front, "
    "and only after the button was let go for a moment. Which stick button is Cross "
    "follows your controls.ini.":
        "Dans cette fenêtre, sur l'onglet En ligne, une manette ou un stick arcade marche sans souris ni clavier : "
        "Croix / A accepte un match ou un Rematch et lance une recherche, Rond / B refuse, quitte ou arrête la "
        "recherche. Ça ne compte que quand cette fenêtre est au premier plan, et seulement après avoir relâché le "
        "bouton un instant. Le bouton du stick qui fait Croix suit ton controls.ini.",
    "Language": "Langue",
    "Restart now": "Redémarrer maintenant",
    "The language changes when the launcher starts again.": "La langue change au prochain démarrage du launcher.",
    "A build is running. Stop it first, or restart the launcher by hand when it is done.":
        "Une compilation est en cours. Arrête-la d'abord, ou relance le launcher toi-même quand elle sera finie.",
    "Close the game first.": "Ferme d'abord le jeu.",
    "Choose your Tekken 5 DR Online package": "Choisis ton paquet Tekken 5 DR Online",
    "All files": "Tous les fichiers",
    "PS3 package": "Paquet PS3",
    "Choose your license (.rap)": "Choisis ta licence (.rap)",
    "PS3 license": "Licence PS3",
    "Checking build tools…": "Vérification des outils de compilation…",
    "missing": "manquant",
    "ok": "ok",
    "Missing: {names}": "Manquant : {names}",
    "Everything the build needs is installed.": "Tout ce dont la compilation a besoin est installé.",
    "All build tools found.": "Tous les outils de compilation sont là.",
    "{count} build tool(s) missing -- click 'Install missing…'.":
        "{count} outil(s) de compilation manquant(s) -- clique sur « Installer ce qui manque… ».",
    "Hide details": "Masquer les détails",
    "Microsoft Visual Studio 2022 Build Tools: the C++ compiler parts only (MSVC x64, "
    "Windows SDK, CMake, Clang). Download about 2.5 GB, about 7 GB on disk, 10-20 "
    "minutes. You accept Microsoft's license terms for the Build Tools "
    "(visualstudio.microsoft.com/license-terms).":
        "Microsoft Visual Studio 2022 Build Tools : uniquement les parties du compilateur C++ (MSVC x64, Windows "
        "SDK, CMake, Clang). Téléchargement d'environ 2,5 Go, environ 7 Go sur le disque, 10-20 minutes. Tu acceptes "
        "les conditions de licence de Microsoft pour les Build Tools (visualstudio.microsoft.com/license-terms).",
    "Git for Windows (about 70 MB download).": "Git for Windows (téléchargement d'environ 70 Mo).",
    "Install build tools": "Installer les outils de compilation",
    "The build needs these free tools from their makers, installed with Windows' own "
    "installer (winget):\n\n{tools}\n\nWindows will ask for administrator permission. A "
    "console window shows the progress.\n\nInstall now?":
        "La compilation a besoin de ces outils gratuits de leurs éditeurs, installés avec l'installateur de Windows "
        "(winget) :\n\n{tools}\n\nWindows va demander l'autorisation administrateur. Une fenêtre de console affiche "
        "la progression.\n\nInstaller maintenant ?",
    "Could not start the installer:\n{error}\n\nIs winget (App Installer) available? On "
    "Windows 10 install 'App Installer' from the Microsoft Store.":
        "Impossible de lancer l'installateur :\n{error}\n\nwinget (Programme d'installation d'application) est-il "
        "disponible ? Sous Windows 10, installe « Programme d'installation d'application » depuis le Microsoft "
        "Store.",
    "Install failed": "Échec de l'installation",
    "Installer running in its own window…": "L'installateur tourne dans sa propre fenêtre…",
    "Could not start the build: {error}": "Impossible de lancer la compilation : {error}",
    "Building…": "Compilation…",
    "Step {n} of {total}: {title}  —  {elapsed}": "Étape {n} sur {total} : {title}  —  {elapsed}",
    "Done in {elapsed}. Open the Play tab.": "Terminé en {elapsed}. Ouvre l'onglet Jouer hors ligne.",
    "Build finished.": "Compilation terminée.",
    "Cancelled. BUILD GAME continues where it stopped.": "Annulé. BUILD GAME reprend là où il s'est arrêté.",
    "The build stopped. The message below says why; build.log has the details.":
        "La compilation s'est arrêtée. Le message ci-dessous dit pourquoi ; build.log contient les détails.",
    "The build failed. See the log above and build.log.":
        "La compilation a échoué. Regarde le journal ci-dessus et build.log.",
    "Build stopped.": "Compilation arrêtée.",
    "Could not start the game:\n{error}": "Impossible de lancer le jeu :\n{error}",
    "Game started (process {pid}). Log: {log}": "Jeu lancé (processus {pid}). Journal : {log}",
    "starting…": "démarrage…",
    "Running — {elapsed} — {fps}": "En cours — {elapsed} — {fps}",
    "Click Report a problem.": "Clique sur « Signaler un problème... ».",
    "The game closed.": "Le jeu s'est fermé.",
    "A build is running. Stop it and quit?": "Une compilation est en cours. L'arrêter et quitter ?",
    # ---- launcher/updater.py
    "Check for updates": "Rechercher des mises à jour",
    "Updated from {old} to {new}.": "Mis à jour de {old} vers {new}.",
    "the new version": "la nouvelle version",
    "The update to {version} failed and could not be undone completely: {error}.\n\nThe "
    "old program files are in\n{folder}\nYour game, saves and settings (the native "
    "folder) were not touched. Download the zip from the releases page and extract it "
    "over this folder.":
        "La mise à jour vers {version} a échoué et n'a pas pu être entièrement annulée : {error}.\n\nLes anciens "
        "fichiers du programme sont dans\n{folder}\nTon jeu, tes sauvegardes et tes réglages (le dossier native) "
        "n'ont pas été touchés. Télécharge le zip depuis la page des releases et extrais-le par-dessus ce dossier.",
    "The update to {version} did not work: {error}.\n\nNothing was changed; this is "
    "still version {current}. Try again later, or download the zip from the releases "
    "page.":
        "La mise à jour vers {version} n'a pas marché : {error}.\n\nRien n'a été changé ; c'est toujours la version "
        "{current}. Réessaie plus tard, ou télécharge le zip depuis la page des releases.",
    "Update": "Mise à jour",
    "Updates": "Mises à jour",
    "This is a development checkout (no release.json and bundled Python), so it does not "
    "update itself. Use git, or a release zip from\n{page}":
        "Ceci est une copie de développement (sans release.json ni Python fourni), elle ne se met donc pas à jour "
        "toute seule. Utilise git, ou un zip de release depuis\n{page}",
    "Update to {version}…": "Mettre à jour vers {version}…",
    "Could not check for updates.\n\n{problem}": "Impossible de rechercher les mises à jour.\n\n{problem}",
    "Version {version} is available: click 'Update to {version}' at the top.":
        "La version {version} est disponible : clique sur « Mettre à jour vers {version} » en haut.",
    "You have the newest version ({version}).": "Tu as la dernière version ({version}).",
    "Update available": "Mise à jour disponible",
    "T5DR Online {version} is available": "T5DR Online {version} est disponible",
    "Download: {size}, published {date}.": "Téléchargement : {size}, publié le {date}.",
    "Download: {size}.": "Téléchargement : {size}.",
    "You have {version}.": "Tu as la {version}.",
    "The launcher downloads it, checks it, replaces its program files and starts again. "
    "Your game, saves and settings (the native folder) stay as they are.":
        "Le launcher la télécharge, la vérifie, remplace ses fichiers et redémarre. Ton jeu, tes sauvegardes et tes "
        "réglages (le dossier native) restent tels quels.",
    "After this update the game is built once more (about 2 minutes): the Play tab "
    "offers BUILD GAME. Only the code is rebuilt; the unpacked game and saves are kept.":
        "Après cette mise à jour, le jeu est recompilé une fois (environ 2 minutes) : l'onglet Jouer hors ligne "
        "propose BUILD GAME. Seul le code est recompilé ; le jeu décompressé et les sauvegardes sont conservés.",
    "The game itself does not need to be built again.": "Le jeu lui-même n'a pas besoin d'être recompilé.",
    "If this update changes the game code, the Play tab asks you to build the game once "
    "(about 2 minutes).":
        "Si cette mise à jour change le code du jeu, l'onglet Jouer hors ligne te demande de le compiler une fois "
        "(environ 2 minutes).",
    "(no release notes)": "(pas de notes de version)",
    "Update now": "Mettre à jour",
    "Later": "Plus tard",
    "Release page": "Page de la version",
    "Cancelling…": "Annulation…",
    "Downloading…": "Téléchargement…",
    "Unexpected error: {error}": "Erreur inattendue : {error}",
    "Downloading… {done} of {total}": "Téléchargement… {done} sur {total}",
    "Downloading… {done}": "Téléchargement… {done}",
    "Checking the download (SHA-256)…": "Vérification du téléchargement (SHA-256)…",
    "Unpacking… {percent}%": "Décompression… {percent} %",
    "Preparing the restart…": "Préparation du redémarrage…",
    "Try again": "Réessayer",
    "Could not start the update step: {error}": "Impossible de lancer l'étape de mise à jour : {error}",
    "Installing {version}: the launcher restarts in a few seconds…":
        "Installation de {version} : le launcher redémarre dans quelques secondes…",
    "Updating to {version}…": "Mise à jour vers {version}…",
    # ---- lobby/t5lobby/client.py
    "Contacting the lobby server over UDP...": "Contact du serveur du lobby en UDP...",
    "UDP to the lobby server is blocked (firewall?)": "L'UDP vers le serveur du lobby est bloqué (pare-feu ?)",
    "Connecting to your opponent...": "Connexion à ton adversaire...",
    "Measuring the connection...": "Mesure de la connexion...",
    "Direct connection not possible; using the lobby server's relay...":
        "Connexion directe impossible ; passage par le relais du serveur du lobby...",
    "Direct connection found: the match no longer goes through the lobby server.":
        "Connexion directe trouvée : le match ne passe plus par le serveur du lobby.",
    "The direct connection was lost; back on the lobby server's relay.":
        "La connexion directe a été perdue ; retour sur le relais du serveur du lobby.",
    "Direct connection not possible; using the relay server {name}...":
        "Connexion directe impossible ; passage par le serveur relais {name}...",
    "Direct connection found: the match no longer goes through the relay server {name}.":
        "Connexion directe trouvée : le match ne passe plus par le serveur relais {name}.",
    "The direct connection was lost; back on the relay server {name}.":
        "La connexion directe a été perdue ; retour sur le serveur relais {name}.",
    # ---- lobby/t5lobby/dialogs.py
    "No": "Non",
    "Yes": "Oui",
    "OK": "OK",
    # ---- lobby/t5lobby/fighters.py
    "Random": "Aléatoire",
    # ---- lobby/t5lobby/handover.py
    "direct connection": "connexion directe",
    "local network": "réseau local",
    "through the lobby server": "via le serveur du lobby",
    "through the relay server {name}": "via le serveur relais {name}",
    "{name} -- {how}, ping {ms} ms, input delay {delay}": "{name} -- {how}, ping {ms} ms, input delay {delay}",
    # ---- lobby/t5lobby/i18n_known.py
    "login timeout": "délai de connexion dépassé",
    "idle timeout": "délai d'inactivité dépassé",
    "banned from this server": "banni de ce serveur",
    "too many connections": "trop de connexions",
    "server full": "serveur plein",
    "slow down": "doucement",
    "bad request": "requête invalide",
    "the server is busy; try again in a few seconds": "le serveur est occupé ; réessaie dans quelques secondes",
    "the chat is busy; try again in a moment": "le chat est occupé ; réessaie dans un instant",
    "that name looks too much like the account {other}": "ce nom ressemble trop au compte {other}",
    "that name looks too much like {name}, who is online": "ce nom ressemble trop à {name}, qui est en ligne",
    "flooding: disconnected": "flood : déconnecté",
    "this server speaks lobby protocol {version}; update the launcher":
        "ce serveur utilise le protocole de lobby {version} ; mets à jour le launcher",
    "build {build} is not accepted by this server; update the launcher and rebuild the "
    "game":
        "ce serveur n'accepte pas la build {build} ; mets à jour le launcher et recompile le jeu",
    "already logged in": "déjà connecté",
    "this server has no accounts": "ce serveur n'a pas de comptes",
    "this server has no guest logins": "ce serveur n'accepte pas les invités",
    "too many failed logins; wait a few minutes": "trop de connexions échouées ; attends quelques minutes",
    "too many failed attempts; wait a few minutes": "trop de tentatives échouées ; attends quelques minutes",
    "too many password changes; wait a minute": "trop de changements de mot de passe ; attends une minute",
    "too many requests for new codes; wait a minute": "trop de demandes de nouveaux codes ; attends une minute",
    "too many new accounts from this address": "trop de nouveaux comptes depuis cette adresse",
    "the saved login has expired; log in with your password":
        "la connexion enregistrée a expiré ; connecte-toi avec ton mot de passe",
    "session expired; log in again": "session expirée ; reconnecte-toi",
    "names are 2-16 letters, digits, spaces or _-.[]()!?":
        "les noms font 2 à 16 caractères : lettres, chiffres, espaces ou _-.[]()!?",
    "that name is reserved": "ce nom est réservé",
    "that name is not allowed here": "ce nom n'est pas autorisé ici",
    "that name belongs to an account": "ce nom appartient à un compte",
    "that name is taken": "ce nom est déjà pris",
    "someone with that name is online": "quelqu'un avec ce nom est en ligne",
    "wrong name or password": "nom ou mot de passe incorrect",
    "wrong password": "mot de passe incorrect",
    "the current password is wrong": "le mot de passe actuel est incorrect",
    "passwords are 6-128 characters": "les mots de passe font 6 à 128 caractères",
    "guests have no password": "les invités n'ont pas de mot de passe",
    "guests have no account": "les invités n'ont pas de compte",
    "wrong name or recovery code (each code works once)":
        "nom ou code de récupération incorrect (chaque code ne sert qu'une fois)",
    "logged in from another place": "connecté depuis un autre endroit",
    "this account is banned for good": "ce compte est banni définitivement",
    "this account is banned for good: {reason}": "ce compte est banni définitivement : {reason}",
    "this account is banned until {time}": "ce compte est banni jusqu'au {time}",
    "this account is banned until {time}: {reason}": "ce compte est banni jusqu'au {time} : {reason}",
    "you are {status}": "impossible pour l'instant (statut : {status})",
    "ranked needs an account": "le Ranked nécessite un compte",
    "ranked matches come from the ranked queue on this server":
        "sur ce serveur, les matchs Ranked viennent de la file Ranked",
    "your character is locked until this ranked set ends":
        "ton personnage est verrouillé jusqu'à la fin de ce set Ranked",
    "the ranked set goes on by itself": "le set Ranked continue tout seul",
    "you are in a ranked set ({mine}-{theirs}); leave it first (that counts as a loss)":
        "tu es dans un set Ranked ({mine}-{theirs}) ; quitte-le d'abord (ça compte comme une défaite)",
    "that player is in a ranked set": "ce joueur est dans un set Ranked",
    "you are not in a ranked set": "tu n'es pas dans un set Ranked",
    "finish your running match with the same game build first":
        "termine d'abord ton match en cours avec la même build du jeu",
    "this PC ran its last match at {fps} fps; ranked needs at least {min_fps} (both "
    "games run at the slower PC's speed). Close other programs or lower the resolution "
    "scale, then play a casual match to measure again":
        "ce PC a joué son dernier match à {fps} fps ; le Ranked demande au moins {min_fps} (les deux jeux tournent à "
        "la vitesse du PC le plus lent). Ferme d'autres programmes ou baisse la résolution interne, puis joue un "
        "match casual pour mesurer à nouveau",
    "chat: slow down": "chat : doucement",
    "history is kept for accounts only": "l'historique n'est gardé que pour les comptes",
    "no such player": "joueur introuvable",
    "no such room": "salon introuvable",
    "room is full": "le salon est plein",
    "you cannot join this room": "tu ne peux pas rejoindre ce salon",
    "not in a room": "tu n'es pas dans un salon",
    "no opponent in the room": "pas d'adversaire dans le salon",
    "that player runs a different build of the game": "ce joueur a une autre build du jeu",
    "finish the match first": "termine d'abord le match",
    "finish or leave the running match first": "termine ou quitte d'abord le match en cours",
    "that match is over; find a new opponent": "ce match est terminé ; trouve un nouvel adversaire",
    "your opponent is no longer available": "ton adversaire n'est plus disponible",
    "that player is not available": "ce joueur n'est pas disponible",
    "busy": "occupé",
    "one challenge at a time": "un défi à la fois",
    "that player has challenges pending": "ce joueur a des défis en attente",
    "no such challenge": "défi introuvable",
    "challenge no longer possible": "le défi n'est plus possible",
    "no such match": "match introuvable",
    "match is {state}": "état du match : {state}",
    "you cannot block yourself": "tu ne peux pas te bloquer toi-même",
    "the block list is full ({max})": "la liste de blocage est pleine ({max})",
    "that player is not on your block list": "ce joueur n'est pas dans ta liste de blocage",
    "you are not in a set": "tu n'es pas dans un set",
    "no such finished match": "match terminé introuvable",
    "guests cannot have friends; create an account (free)":
        "les invités ne peuvent pas avoir d'amis ; crée un compte (gratuit)",
    "there is no account with that name": "aucun compte ne porte ce nom",
    "you cannot add yourself": "tu ne peux pas t'ajouter toi-même",
    "you blocked that player; unblock them first": "tu as bloqué ce joueur ; débloque-le d'abord",
    "your friends list is full ({max})": "ta liste d'amis est pleine ({max})",
    "your last invite to that friend ended a moment ago; try again in {seconds} s":
        "ta dernière invitation à cet ami vient de se terminer ; réessaie dans {seconds} s",
    "your last challenge to that player ended a moment ago; try again in {seconds} s":
        "ton dernier défi à ce joueur vient de se terminer ; réessaie dans {seconds} s",
    "too many friend requests from this internet address today; try again tomorrow":
        "trop de demandes d'ami depuis cette adresse internet aujourd'hui ; réessaie demain",
    "you can send {count} friend requests a day; try again tomorrow":
        "tu peux envoyer {count} demandes d'ami par jour ; réessaie demain",
    "{count} of your friend requests are waiting for an answer; cancel some first":
        "{count} de tes demandes d'ami attendent une réponse ; retire-en d'abord quelques-unes",
    "{name} declined your last request; you can ask again in {days} day(s)":
        "{name} a refusé ta dernière demande ; tu pourras redemander dans {days} jour(s)",
    "that player has too many friend requests waiting": "ce joueur a trop de demandes d'ami en attente",
    "that player's friends list is full": "la liste d'amis de ce joueur est pleine",
    "no friend request from that player": "aucune demande d'ami de ce joueur",
    "no friend request to that player": "aucune demande d'ami à ce joueur",
    "that player is not on your friends list": "ce joueur n'est pas dans ta liste d'amis",
    "that friend is not online": "cet ami n'est pas en ligne",
    "that friend's launcher is too old for invites (it needs 1.1.2 or newer)":
        "le launcher de cet ami est trop ancien pour les invitations (il faut la 1.1.2 ou plus récente)",
    "create a room first, then invite": "crée d'abord un salon, puis invite",
    "that friend is busy right now": "cet ami est occupé en ce moment",
    "one invite at a time": "une invitation à la fois",
    "wait a moment before inviting again": "attends un instant avant d'inviter à nouveau",
    "that player has invites pending": "ce joueur a des invitations en attente",
    "that invite is over": "cette invitation est terminée",
    "the invite is no longer possible": "l'invitation n'est plus possible",
    "{name} is back in the lobby": "{name} est de retour dans le lobby",
    "{name} lost the lobby connection; waiting {seconds} s for them to return":
        "{name} a perdu la connexion au lobby ; attente de {seconds} s pour son retour",
    "your PC ran its last match at {fps} fps": "ton PC a joué son dernier match à {fps} fps",
    "your opponent's PC ran its last match at {fps} fps":
        "le PC de ton adversaire a joué son dernier match à {fps} fps",
    "{name}'s PC ran its last match at {fps} fps": "le PC de {name} a joué son dernier match à {fps} fps",
    "{parts} -- this match runs at the slower PC's speed": "{parts} -- ce match tourne à la vitesse du PC le plus lent",
    "you two played {count} ranked matches in the last 24 hours; this one is unranked "
    "(limit {max})":
        "vous avez joué {count} matchs Ranked ensemble ces dernières 24 heures ; celui-ci ne compte pas en Ranked "
        "(limite {max})",
    "your PC's UDP packets did not reach the lobby server; check the firewall":
        "les paquets UDP de ton PC n'ont pas atteint le serveur du lobby ; vérifie le pare-feu",
    "your opponent reported the result; please report yours":
        "ton adversaire a signalé le résultat ; signale le tien aussi",
    "opponent runs a different build": "l'adversaire a une autre build",
    "not connected to the lobby": "pas connecté au lobby",
    "the lobby server did not answer": "le serveur du lobby n'a pas répondu",
    "no answer to {type}": "pas de réponse à {type}",
    "cannot reach {host}:{port} ({error})": "impossible de joindre {host}:{port} ({error})",
    "the server's certificate does not match the pinned one":
        "le certificat du serveur ne correspond pas à celui enregistré",
    "this server has no encryption (TLS): a password would cross the internet readable. "
    "Play as a guest, or ask the server's host to set up TLS and give you its "
    "fingerprint.":
        "ce serveur n'a pas de chiffrement (TLS) : un mot de passe traverserait internet en clair. Joue en invité, "
        "ou demande à l'hébergeur du serveur de configurer TLS et de te donner son empreinte.",
    "connection closed": "connexion fermée",
    "the server sent a malformed match id": "le serveur a envoyé un ID de match mal formé",
    "message too long": "message trop long",
    "closed": "fermée",
    "Choose your game package (.pkg) first.": "Choisis d'abord ton paquet du jeu (.pkg).",
    "The package file does not exist: {file}": "Le fichier du paquet n'existe pas : {file}",
    "{file} is not a PS3 package (.pkg).": "{file} n'est pas un paquet PS3 (.pkg).",
    "Choose your license file (.rap) first.": "Choisis d'abord ton fichier de licence (.rap).",
    "{file} is not a PS3 license: a .rap file is exactly 16 bytes.":
        "{file} n'est pas une licence PS3 : un fichier .rap fait exactement 16 octets.",
    "This package has no USRDIR/EBOOT.BIN -- it is not a game package (an add-on or "
    "theme?). The port needs {game}.":
        "Ce paquet n'a pas de USRDIR/EBOOT.BIN -- ce n'est pas un paquet de jeu (un add-on ou un thème ?). Le "
        "portage a besoin de {game}.",
    "This package is \"{title}\" ({id}). The port needs {game}.":
        "Ce paquet est « {title} » ({id}). Le portage a besoin de {game}.",
    "This copy is a different version of the game: \"{title}\" version {version}, content "
    "ID {id} (program SHA-1 {sha}...). The port supports only {game}, content ID "
    "{supported}.":
        "Cette copie est une autre version du jeu : « {title} » version {version}, content ID {id} (SHA-1 du "
        "programme {sha}...). Le portage ne prend en charge que {game}, content ID {supported}.",
    # 1.1.5: the package's version, read before the build (tools/build_game.py, launcher/core.py)
    "This package is version {version} of the game (program content ID {id}). The port supports only version "
    "{supported}: {game}, content ID {cid}, {size} bytes. This version cannot be used, whatever the license "
    "(.rap).":
        "Ce paquet est la version {version} du jeu (content ID du programme {id}). Le port ne prend en charge "
        "que la version {supported} : {game}, content ID {cid}, {size} octets. Cette version est inutilisable, "
        "quelle que soit la licence (.rap).",
    "{id}  ({size} bytes) -- version {version} of the game. The port supports only version {supported}; the "
    "build will refuse this package.":
        "{id}  ({size} octets) -- version {version} du jeu. Le port ne prend en charge que la version "
        "{supported} ; la compilation refusera ce paquet.",
    "{id}  ({size} bytes) -- its program has content ID {program}, not the supported one ({supported}). The "
    "build will most likely refuse it.":
        "{id}  ({size} octets) -- son programme a le content ID {program}, pas celui pris en charge "
        "({supported}). La compilation le refusera très probablement.",
    # 1.1.5: the game's own message boxes (launcher/core.py dialog_info, dialog_message)
    "The game shows: \"{text}\" {advice}": "Le jeu affiche : « {text} » {advice}",
    "Your built game data is probably damaged. Open the Build tab, tick \"Redo every step\" and press BUILD "
    "GAME. If the message comes back, download the package again: it must be exactly {size} bytes.":
        "Les données du jeu compilé sont probablement abîmées. Ouvre l'onglet Compiler, coche « Refaire toutes "
        "les étapes » et appuie sur BUILD GAME. Si le message revient, télécharge à nouveau le paquet : il doit "
        "faire exactement {size} octets.",
    "The game could not write its save, so progress may be lost. Check that the disk is not full and that no "
    "antivirus blocks the folder native\\gamedata.":
        "Le jeu n'a pas pu écrire sa sauvegarde : la progression peut être perdue. Vérifie que le disque n'est "
        "pas plein et qu'aucun antivirus ne bloque le dossier native\\gamedata.",
    "The game could not read its save. If it happens every time, click Report a problem.":
        "Le jeu n'a pas pu lire sa sauvegarde. Si cela arrive à chaque fois, clique sur « Signaler un "
        "problème... ».",
    "If the game does not go on, click Report a problem.":
        "Si le jeu ne continue pas, clique sur « Signaler un problème... ».",
    "The license (.rap) does not belong to this package. Use the .rap whose name matches "
    "the package's content ID ({id}).":
        "La licence (.rap) ne correspond pas à ce paquet. Utilise le .rap dont le nom correspond au content ID du "
        "paquet ({id}).",
    "Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press BUILD GAME "
    "again; if it fails again, check that the package is {size} bytes.":
        "Le déchiffrement du programme du jeu a échoué (voir le journal ci-dessus). Coche « Refaire toutes les "
        "étapes » et appuie à nouveau sur BUILD GAME ; si ça échoue encore, vérifie que le paquet fait {size} "
        "octets.",
    "The package is {size} bytes, the supported one is {supported} bytes: the download is incomplete or it is "
    "a different file. Download it again.":
        "Le paquet fait {size} octets, celui pris en charge {supported} octets : le téléchargement est incomplet ou "
        "c'est un autre fichier. Télécharge-le à nouveau.",
    "The ps3recomp copy in this folder does not match this version of the port. Download "
    "the release again and extract it into an empty folder.":
        "La copie de ps3recomp dans ce dossier ne correspond pas à cette version du portage. Télécharge à nouveau la "
        "release et extrais-la dans un dossier vide.",
    "Git is needed to download ps3recomp (the recompiler). Install Git, or use a release "
    "zip, which already contains it.":
        "Git est nécessaire pour télécharger ps3recomp (le recompilateur). Installe Git, ou utilise un zip de "
        "release, qui le contient déjà.",
    "This package's Python is missing pycryptodome. Download the release again.":
        "Il manque pycryptodome dans le Python de ce paquet. Télécharge à nouveau la release.",
    "Could not download the public PS3 key data from github.com (needed once, a few KB). "
    "Check the internet connection and press BUILD GAME again.":
        "Impossible de télécharger les données publiques de clés PS3 depuis github.com (nécessaires une fois, "
        "quelques Ko). Vérifie la connexion internet et appuie à nouveau sur BUILD GAME.",
    "The C++ build tools (Visual Studio 2022 Build Tools, x64 C++ toolset) are not "
    "installed. Open the launcher's Build tab and click Install next to them.":
        "Les outils de compilation C++ (Visual Studio 2022 Build Tools, ensemble d'outils C++ x64) ne sont pas "
        "installés. Ouvre l'onglet Compiler du launcher et clique sur « Installer ce qui manque… ».",
    "clang-cl.exe and lld-link.exe were not found in toolchain\\llvm\\bin. Download the "
    "release again.":
        "clang-cl.exe et lld-link.exe sont introuvables dans toolchain\\llvm\\bin. Télécharge à nouveau la release.",
    "The Windows SDK is missing (needed for Direct3D 12). Install it with the C++ build "
    "tools.":
        "Le Windows SDK manque (nécessaire pour Direct3D 12). Installe-le avec les outils de compilation C++.",
    "clang-cl (LLVM 16 or newer) was not found. Install LLVM or the Visual Studio "
    "component 'C++ Clang tools for Windows'.":
        "clang-cl (LLVM 16 ou plus récent) est introuvable. Installe LLVM ou le composant Visual Studio « C++ Clang "
        "tools for Windows ».",
    "CMake and Ninja were not found. Install the Visual Studio component 'C++ CMake "
    "tools for Windows'.":
        "CMake et Ninja sont introuvables. Installe le composant Visual Studio « C++ CMake tools for Windows ».",
    "CMake and Ninja were not found. On macOS: brew install cmake ninja sdl2 glslang spirv-cross":
        "CMake et Ninja sont introuvables. Sous macOS : brew install cmake ninja sdl2 glslang spirv-cross",
    "glslang and spirv-cross were not found; the game's shaders need them. "
    "On macOS: brew install glslang spirv-cross":
        "glslang et spirv-cross sont introuvables ; les shaders du jeu en ont besoin. Sous macOS : brew install glslang spirv-cross",
    "Building the game is supported on Windows and macOS only.":
        "Le jeu ne peut être compilé que sous Windows et macOS.",
    "This Python refuses pip install (PEP 668; Homebrew's does). Use a virtual environment: python3 -m venv .venv && .venv/bin/pip install pycryptodome, then run the tools with .venv/bin/python.":
        "Ce Python refuse pip install (PEP 668 ; celui de Homebrew le fait). Utilisez un environnement virtuel : python3 -m venv .venv && .venv/bin/pip install pycryptodome, puis lancez les outils avec .venv/bin/python.",
    "expected 1 SPU image, found {count}": "1 image SPU attendue, {count} trouvée(s)",
    "step '{step}' failed: a tool exited with code {code} -- the lines above say why.":
        "l'étape « {step} » a échoué : un outil s'est terminé avec le code {code} -- les lignes ci-dessus disent "
        "pourquoi.",
    "cancelled": "annulé",
    "step '{step}' could not read or write a file: {reason} ({file}). The folder path is "
    "too long for Windows: move the folder to a short path such as C:\\Games\\T5DR.":
        "l'étape « {step} » n'a pas pu lire ou écrire un fichier : {reason} ({file}). Le chemin du dossier est trop "
        "long pour Windows : déplace le dossier vers un chemin court comme C:\\Games\\T5DR.",
    "step '{step}' could not read or write a file: {reason} ({file}). Is the disk full, "
    "or does another program (antivirus, OneDrive) hold the file?":
        "l'étape « {step} » n'a pas pu lire ou écrire un fichier : {reason} ({file}). Le disque est-il plein, ou un "
        "autre programme (antivirus, OneDrive) bloque-t-il le fichier ?",
    "Python 3.10+": "Python 3.10+",
    "pycryptodome (Python AES)": "pycryptodome (Python AES)",
    "ps3recomp source": "source de ps3recomp",
    "Game runtime (t5dr.exe)": "Runtime du jeu (t5dr.exe)",
    "clang-cl + lld-link": "clang-cl + lld-link",
    "C++ build tools (MSVC x64)": "Outils de compilation C++ (MSVC x64)",
    "Windows SDK (Direct3D 12)": "Windows SDK (Direct3D 12)",
    "clang-cl 16+ (LLVM)": "clang-cl 16+ (LLVM)",
    "CMake + Ninja": "CMake + Ninja",
    "{version} at {path}": "{version} dans {path}",
    "installed": "installé",
    "missing -- pip install pycryptodome": "manquant -- pip install pycryptodome",
    "included in this package": "inclus dans ce paquet",
    "git checkout in deps/": "checkout git dans deps/",
    "not present -- will be downloaded with Git": "absent -- sera téléchargé avec Git",
    "not present and Git is missing": "absent, et Git manque",
    "precompiled, included in this package": "précompilé, inclus dans ce paquet",
    "missing from toolchain\\llvm -- download the release again":
        "manquant dans toolchain\\llvm -- télécharge à nouveau la release",
    "not found": "introuvable",
    "missing {tools}": "manquant : {tools}",
    "System information and the settings you use": "Infos système et les réglages que tu utilises",
    "What happened (what you wrote)": "Ce qui s'est passé (ce que tu as écrit)",
    "Launcher log": "Journal du launcher",
    "Game log (the newest one)": "Journal du jeu (le plus récent)",
    "Game log (the newest {count})": "Journaux du jeu (les {count} plus récents)",
    "Build log": "Journal de compilation",
    "Build log (the last build went fine)": "Journal de compilation (la dernière compilation s'est bien passée)",
    "Online: the files of the last match": "En ligne : les fichiers du dernier match",
    "controls.ini (your button settings)": "controls.ini (tes réglages de boutons)",
    "Desync dumps (game state numbers, binary)": "Dumps de désynchro (valeurs de l'état du jeu, binaire)",
    "The last replay (the inputs of the last online session, without names)":
        "Le dernier replay (les entrées de la dernière session en ligne, sans noms)",
    "could not be cleaned of private data": "impossible d'en retirer les données privées",
    "no room left in the size limit": "plus de place dans la limite de taille",
    "could not be read": "illisible",
    "The launcher cannot write next to its folder or into it, so it cannot update "
    "itself. Download the zip from the releases page instead.":
        "Le launcher ne peut écrire ni à côté de son dossier ni dedans, il ne peut donc pas se mettre à jour. "
        "Télécharge plutôt le zip depuis la page des releases.",
    "Refused to download from {host}: not this project's GitHub releases.":
        "Téléchargement depuis {host} refusé : ce ne sont pas les releases GitHub de ce projet.",
    "The download came from {host}. Nothing was changed.": "Le téléchargement venait de {host}. Rien n'a été changé.",
    "GitHub did not return a published release.": "GitHub n'a renvoyé aucune release publiée.",
    "The latest release has an unexpected version ({tag}).": "La dernière release a une version inattendue ({tag}).",
    "Release {version} has no {name} with SHA256SUMS yet.":
        "La release {version} n'a pas encore de {name} avec SHA256SUMS.",
    "The downloaded release does not say it is version {version}. Nothing was changed.":
        "La release téléchargée n'indique pas être la version {version}. Rien n'a été changé.",
    "The downloaded release has no launcher. Nothing was changed.":
        "La release téléchargée n'a pas de launcher. Rien n'a été changé.",
    "This folder has no python\\pythonw.exe, so the launcher cannot update itself (a "
    "development checkout?). Download the zip from the releases page instead.":
        "Ce dossier n'a pas de python\\pythonw.exe, le launcher ne peut donc pas se mettre à jour (une copie de "
        "développement ?). Télécharge plutôt le zip depuis la page des releases.",
    "The download was sent to {host}, which is not GitHub's storage for this project. "
    "Nothing was changed.":
        "Le téléchargement a été redirigé vers {host}, qui n'est pas le stockage GitHub de ce projet. Rien n'a été "
        "changé.",
    "Release {version}: {name} is not on this project's GitHub releases.":
        "Release {version} : {name} n'est pas dans les releases GitHub de ce projet.",
    "Release {version}: {name} is still being uploaded.": "Release {version} : {name} est encore en cours d'envoi.",
    "The download stopped early ({done} of {total} bytes). Try again.":
        "Le téléchargement s'est arrêté trop tôt ({done} sur {total} octets). Réessaie.",
    "The download is not a readable zip ({error}). Nothing was changed.":
        "Le téléchargement n'est pas un zip lisible ({error}). Rien n'a été changé.",
    "The download unpacks to far more than a release should. Nothing was changed.":
        "Le téléchargement se décompresse en bien plus qu'une release ne devrait. Rien n'a été changé.",
    "Not enough free disk space: the update needs about {need} MB next to the folder, "
    "{free} MB are free.":
        "Pas assez d'espace disque : la mise à jour a besoin d'environ {need} Mo à côté du dossier, {free} Mo sont "
        "libres.",
    "SHA256SUMS of release {version} has no line for {name}. Nothing was changed.":
        "Le SHA256SUMS de la release {version} n'a pas de ligne pour {name}. Rien n'a été changé.",
    "SHA256SUMS and GitHub disagree about the download's checksum. Nothing was changed.":
        "SHA256SUMS et GitHub ne sont pas d'accord sur la somme de contrôle du téléchargement. Rien n'a été changé.",
    "The download is damaged or not the published file: its SHA-256 is {got}..., "
    "SHA256SUMS says {want}.... Nothing was changed.":
        "Le téléchargement est endommagé ou n'est pas le fichier publié : son SHA-256 est {got}..., SHA256SUMS "
        "indique {want}.... Rien n'a été changé.",
    "The downloaded release has no python\\pythonw.exe. Nothing was changed.":
        "La release téléchargée n'a pas de python\\pythonw.exe. Rien n'a été changé.",
    "The download is far bigger than a release should be. Nothing was changed.":
        "Le téléchargement est bien plus gros qu'une release ne devrait l'être. Rien n'a été changé.",
    "The download contains an unexpected path ({name}: {why}). Nothing was changed.":
        "Le téléchargement contient un chemin inattendu ({name} : {why}). Rien n'a été changé.",
    "The download contains an unexpected path ({name}). Nothing was changed.":
        "Le téléchargement contient un chemin inattendu ({name}). Rien n'a été changé.",
    "Cancelled.": "Annulé.",
    "Could not download or unpack the update ({error}). Nothing was changed.":
        "Impossible de télécharger ou de décompresser la mise à jour ({error}). Rien n'a été changé.",
    "The download is damaged ({error}). Nothing was changed.":
        "Le téléchargement est endommagé ({error}). Rien n'a été changé.",
    "the new release contains {names} (the player's files)":
        "la nouvelle release contient {names} (les fichiers du joueur)",
    "release.json does not say {version} after the swap": "release.json n'indique pas {version} après l'échange",
    "launcher\\t5dr_launcher.pyw is missing after the swap": "launcher\\t5dr_launcher.pyw manque après l'échange",
    "python\\pythonw.exe is missing after the swap": "python\\pythonw.exe manque après l'échange",
    "the update plan is incomplete": "le plan de mise à jour est incomplet",
    "the launcher did not close": "le launcher ne s'est pas fermé",
    "programs from the folder were still running ({names}); close them and try again":
        "des programmes du dossier tournaient encore ({names}) ; ferme-les et réessaie",
    "the new launcher {version} did not start": "le nouveau launcher {version} n'a pas démarré",
    "could not replace the program files: {error}": "impossible de remplacer les fichiers du programme : {error}",
    "unexpected error: {error}": "erreur inattendue : {error}",
    "GitHub asks to wait with update checks until {time}.":
        "GitHub demande d'attendre {time} avant de rechercher des mises à jour.",
    "GitHub limits update checks right now. Try again later.":
        "GitHub limite les recherches de mises à jour en ce moment. Réessaie plus tard.",
    "GitHub answered with error {code}. Try again later.": "GitHub a répondu avec l'erreur {code}. Réessaie plus tard.",
    "No connection to GitHub. Check the internet connection and try again.":
        "Pas de connexion à GitHub. Vérifie la connexion internet et réessaie.",
    "A build is running. Update when it is finished.":
        "Une compilation est en cours. Mets à jour quand elle sera finie.",
    "The game is running. Close it first, then update.": "Le jeu tourne. Ferme-le d'abord, puis mets à jour.",
    "'Host for friends' is running. Stop hosting first, then update.":
        "« Héberger pour des amis » est actif. Arrête d'héberger d'abord, puis mets à jour.",
    "An online match was found. Update after the match.": "Un match en ligne a été trouvé. Mets à jour après le match.",
    "An online match is running. Update after the match.":
        "Un match en ligne est en cours. Mets à jour après le match.",
    "You are searching for or playing an online match. Update afterwards.":
        "Tu cherches ou joues un match en ligne. Mets à jour après.",
    "Other programs from this folder are still running ({names}): another launcher "
    "window, the game or a lobby server. Close them, then update.":
        "D'autres programmes de ce dossier tournent encore ({names}) : une autre fenêtre du launcher, le jeu ou un "
        "serveur de lobby. Ferme-les, puis mets à jour.",
    "not a plain relative path": "pas un simple chemin relatif",
    "'.', '..' or an empty part": "« . », « .. » ou une partie vide",
    "outside the folder {folder}": "hors du dossier {folder}",
    "named like the player's own files": "nommé comme les fichiers du joueur",
    "a name Windows does not keep as written": "un nom que Windows ne garde pas tel quel",
    "Release {version} is a test version; it is not installed automatically.":
        "La release {version} est une version de test ; elle n'est pas installée automatiquement.",
    "Release {version} is not signed with the project's release key (no SHA256SUMS.sig). It was not made by "
    "the project's release process; nothing was changed.":
        "La release {version} n'est pas signée avec la clé de release du projet (pas de SHA256SUMS.sig). Elle ne "
        "vient pas du processus de release du projet ; rien n'a été changé.",
    "Release {version} failed the signature check ({error}). It was not made by the project's release "
    "process; nothing was changed.":
        "La release {version} n'a pas passé la vérification de signature ({error}). Elle ne vient pas du processus "
        "de release du projet ; rien n'a été changé.",
    "idle": "libre",
    "room": "dans un salon",
    "queue": "en recherche",
    "match": "en match",
    "playing": "en jeu",
    # ---- lobby/t5lobby/discord_rpc.py
    "In lobby": "Dans le lobby",
    "Searching ranked": "Recherche Ranked",
    "Searching quick match": "Recherche Quick Match",
    "Ranked, Set {mine}-{theirs}": "Ranked, set {mine}-{theirs}",
    "Ranked": "Ranked",
    "Casual": "Amical",
    "In match: {mine} vs {theirs} ({what})": "En match : {mine} vs {theirs} ({what})",
    "In match ({what})": "En match ({what})",
    # ---- lobby/t5lobby/lag.py
    "Ping {ping} ms should mean about {frames} frames behind.":
        "Avec {ping} ms de ping, environ {frames} frames de retard, c'est normal.",
    "The games did not report how it went, so there is nothing to compare.":
        "Les jeux n'ont pas dit comment ça s'est passé, il n'y a donc rien à comparer.",
    "It was {observed}.": "C'était {observed}.",
    "That is what the ping explains.": "C'est ce que le ping explique.",
    "That is more than the ping explains.": "C'est plus que ce que le ping explique.",
    "Both PCs ran below full speed.": "Les deux PC ont tourné en dessous de leur pleine vitesse.",
    "Your PC was the slow one ({fps} fps).": "C'est ton PC qui était lent ({fps} fps).",
    "Your PC was the slow one.": "C'est ton PC qui était lent.",
    "Your opponent's PC was the slow one ({fps} fps).": "C'est le PC de ton adversaire qui était lent ({fps} fps).",
    "Your opponent's PC was the slow one.": "C'est le PC de ton adversaire qui était lent.",
    "Both PCs kept up, so the connection stalled now and then (jitter or lost packets).":
        "Les deux PC ont suivi, donc la connexion a calé de temps en temps (jitter ou paquets perdus).",
    "This match lagged: the games waited {secs} s for each other's inputs.":
        "Ce match a eu du lag : les jeux ont attendu {secs} s les entrées de l'autre.",
    "A wired connection and no uploads during matches help.":
        "Une connexion filaire et aucun envoi de fichiers pendant les matchs aident.",
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "Ton adversaire a fermé le jeu.",
    "The connection to your opponent's game was lost.": "La connexion au jeu de ton adversaire a été perdue.",
    "Your opponent's game stopped responding.": "Le jeu de ton adversaire ne répond plus.",
    "Your opponent's game did not get to the fight.": "Le jeu de ton adversaire n'est pas arrivé jusqu'au combat.",
    "Your opponent's game was restarted; the match cannot go on.":
        "Le jeu de ton adversaire a redémarré ; le match ne peut pas continuer.",
    "Loading the fight took too long on this PC (slow disk or a busy PC?); the match was stopped.":
        "Le chargement du combat a pris trop de temps sur ce PC (disque lent ou PC trop occupé ?) ; le match "
        "a été arrêté.",
    "Loading the fight took too long on your opponent's PC; the match was stopped.":
        "Le chargement du combat a pris trop de temps sur le PC de ton adversaire ; le match a été arrêté.",
    "Your opponent's game could not be reached (firewall or router?).":
        "Impossible de joindre le jeu de ton adversaire (pare-feu ou routeur ?).",
    "Your opponent's game is a different build.": "Le jeu de ton adversaire est une autre build.",
    "Your opponent's game is in another match.": "Le jeu de ton adversaire est dans un autre match.",
    "The game could not open its network port (another program uses it?).":
        "Le jeu n'a pas pu ouvrir son port réseau (un autre programme l'utilise ?).",
    "You closed the game during the match: it counts as a loss.":
        "Tu as fermé le jeu pendant le match : ça compte comme une défaite.",
    "The game could not get back to character select and closed itself; it starts again for your next match.":
        "Le jeu n'a pas pu revenir à la sélection des personnages et s'est fermé ; il redémarre pour ton prochain "
        "match.",
    "Your opponent does not want a rematch.": "Ton adversaire ne veut pas de Rematch.",
    "The game is not running any more; leaving the rematch.": "Le jeu ne tourne plus ; on quitte le Rematch.",
    "Rematch against {name}: same connection, the game stays open.":
        "Rematch contre {name} : même connexion, le jeu reste ouvert.",
    "The game could not start; leaving the match.": "Le jeu n'a pas pu démarrer ; on quitte le match.",
    "Playing against {summary}": "Tu joues contre {summary}",
    "The game did not answer its control channel; it is restarted for every opponent "
    "from now on.":
        "Le jeu n'a pas répondu sur son canal de contrôle ; il sera désormais relancé pour chaque adversaire.",
    "Character select...": "Sélection du personnage...",
    "The game is starting...": "Le jeu démarre...",
    "Fight!": "Fight!",
    "Loading the fight...": "Chargement du combat...",
    "Stage select...": "Sélection du stage...",
    "At character select, waiting for the next match.": "À la sélection des personnages, en attente du prochain match.",
    "Match over.": "Match terminé.",
    "Ignored a result the game wrote for an earlier match.":
        "Un résultat écrit par le jeu pour un match précédent a été ignoré.",
    "The match could not be finished ({reason}).": "Le match n'a pas pu être terminé ({reason}).",
    "The match could not be played ({reason}).": "Le match n'a pas pu être joué ({reason}).",
    "The game stopped unexpectedly; the match does not count (repeated crashes do).":
        "Le jeu s'est arrêté de façon inattendue ; le match ne compte pas (les plantages répétés, si).",
    "Result sent (the games went out of sync on {frames} frames); waiting for the "
    "lobby...":
        "Résultat envoyé (les jeux se sont désynchronisés sur {frames} frames) ; en attente du lobby...",
    "Result sent; waiting for the lobby...": "Résultat envoyé ; en attente du lobby...",
    "Lobby: {message}": "Lobby : {message}",
    # ---- lobby/t5lobby/padnav.py
    "(+{count} more)": "(+{count} de plus)",
    # ---- lobby/t5lobby/ranks.py
    "{wins}W {losses}L": "{wins}V {losses}D",
    "{draws}D": "{draws}N",
    "{rank} (placement {done}/{total})": "{rank} (placement {done}/{total})",
    # ---- lobby/t5lobby/sets.py
    "a game was too short to count": "une partie était trop courte pour compter",
    "a fight ended without a winner": "un combat s'est terminé sans vainqueur",
    "too many games without a winner": "trop de parties sans vainqueur",
    "left after the lag check": "parti après le test de lag",
    "the lobby server restarted": "le serveur du lobby a redémarré",
    "a player left right away": "un joueur est parti tout de suite",
    "the next game could not start": "la partie suivante n'a pas pu démarrer",
    "a player left before a game counted": "un joueur est parti avant qu'une partie compte",
    "a player lost the lobby connection": "un joueur a perdu la connexion au lobby",
    "set won": "set gagné",
    "set lost": "set perdu",
    "Set {mine}-{theirs}": "Set {mine}-{theirs}",
    "game {number} of {best}": "partie {number} sur {best}",
    "game {number} of {best} again (no winner)": "partie {number} sur {best} à rejouer (pas de vainqueur)",
    "starts in {seconds} s": "commence dans {seconds} s",
    "The set does not count ({why}); no rating change": "Le set ne compte pas ({why}) ; pas de changement de cote",
    "The set does not count; no rating change": "Le set ne compte pas ; pas de changement de cote",
    "You won the set (your opponent left it)": "Tu as gagné le set (ton adversaire l'a quitté)",
    "You won the set": "Tu as gagné le set",
    "You lost the set (you left it)": "Tu as perdu le set (tu l'as quitté)",
    "You lost the set": "Tu as perdu le set",
    "You won the set {mine}-{theirs}": "Tu as gagné le set {mine}-{theirs}",
    "You lost the set {mine}-{theirs}": "Tu as perdu le set {mine}-{theirs}",
    "set game {number}": "partie {number} du set",
    # ---- lobby/t5lobby/tk_tour.py, tour_text.py (tournaments)
    "A set is played like a casual set with the in-game select; results come from the games. Players who do not accept a called set in time are out.": "Un set se joue comme un set amical avec la sélection dans le jeu ; les résultats viennent des parties. Qui n'accepte pas à temps un set appelé est éliminé.",
    "Accepted. Waiting for {name}...": "Accepté. En attente de {name}...",
    "Bracket": "Bracket",
    "CALLED": "APPELÉ",
    "Cancel tournament": "Annuler le tournoi",
    "Cancel {name}? Nobody can play it any more.": "Annuler {name} ? Plus personne ne pourra y jouer.",
    "Cancelled": "Annulé",
    "Champion: {name}": "Champion : {name}",
    "Check in": "Faire le check-in",
    "Check-in": "Check-in",
    "Check-in 10 minutes before": "Check-in 10 minutes avant",
    "Check-in 15 minutes before": "Check-in 15 minutes avant",
    "Check-in 30 minutes before": "Check-in 30 minutes avant",
    "Check-in 5 minutes before": "Check-in 5 minutes avant",
    "Check-in 60 minutes before": "Check-in 60 minutes avant",
    "Check-in for {name} is open: check in on the Tournaments page, or you are not in the bracket.": "Le check-in de {name} est ouvert : fais-le sur la page Tournois, sinon tu ne seras pas dans le bracket.",
    "Checked in.": "Check-in fait.",
    "Click a set in the bracket.": "Clique sur un set du bracket.",
    "Create": "Créer",
    "Create tournament": "Créer un tournoi",
    "Create...": "Créer...",
    "Disqualify": "Disqualifier",
    "Disqualify which player (name)?": "Disqualifier quel joueur (nom) ?",
    "Disqualify...": "Disqualifier...",
    "Double elimination": "Élimination double",
    "Final": "Finale",
    "Finished": "Terminé",
    "First to 2 games (best of 3)": "2 parties gagnantes (au meilleur des 3)",
    "First to 3 games (best of 5)": "3 parties gagnantes (au meilleur des 5)",
    "Format": "Format",
    "Grand final": "Grande finale",
    "Grand final reset": "Grande finale (reset)",
    "LIVE": "EN DIRECT",
    "Leave the tournament set": "Quitter le set de tournoi",
    "Leave this tournament set?\n\nYou lose the set.": "Quitter ce set de tournoi ?\n\nTu perds le set.",
    "Losers final": "Finale Losers",
    "Losers round {number}": "Tour {number} Losers",
    "Losers semi-final": "Demi-finale Losers",
    "NEEDS THE ORGANIZER": "ATTEND L'ORGANISATEUR",
    "No check-in": "Sans check-in",
    "No tournament selected": "Aucun tournoi sélectionné",
    "Only tournament hosts can create tournaments. Ask the server's owner for a host slot.":
        "Seuls les hôtes de tournoi peuvent créer des tournois. Demande une place d'hôte au propriétaire du serveur.",
    "Pick a tournament to see its bracket.": "Choisis un tournoi pour voir son bracket.",
    "Pick one in the list, or create one.": "Choisis-en un dans la liste, ou crées-en un.",
    "Players": "Joueurs",
    "Players at most": "Joueurs au maximum",
    "Players: {list}": "Joueurs : {list}",
    "Quarter-final": "Quart de finale",
    "Random seeding": "Seeding aléatoire",
    "Report a result": "Saisir un résultat",
    "Reset set": "Réinitialiser le set",
    "Reset set {set}? It is played again from 0-0.": "Réinitialiser le set {set} ? Il est rejoué depuis 0-0.",
    "Round {number}": "Tour {number}",
    "Running": "En cours",
    "Seeded by rating": "Seeding par cote",
    "Seeding": "Seeding",
    "Semi-final": "Demi-finale",
    "Sets": "Sets",
    "Side 1 wins": "Côté 1 gagne",
    "Side 2 wins": "Côté 2 gagne",
    "Sign up": "S'inscrire",
    "Sign-up": "Inscriptions",
    "Single elimination": "Élimination simple",
    "Start now": "Lancer maintenant",
    "Start {name} now, with the players who are in?": "Lancer {name} maintenant, avec les joueurs présents ?",
    "Starts": "Début",
    "TOURNAMENT": "TOURNOI",
    "TOURNAMENT SET · BEST OF {best}": "SET DE TOURNOI · AU MEILLEUR DES {best}",
    "The bracket is drawn when the tournament starts.": "Le bracket est tiré au début du tournoi.",
    "The name needs 3 characters or more.": "Le nom doit faire 3 caractères ou plus.",
    "The organizer decided your tournament set.": "L'organisateur a décidé de ton set de tournoi.",
    "The organizer reset your tournament set; it is called again.": "L'organisateur a réinitialisé ton set de tournoi ; il est relancé.",
    "The set goes on at {mine}-{theirs}.": "Le set reprend à {mine}-{theirs}.",
    "The set has no result; the tournament calls it again or its organizer decides": "Le set n'a pas de résultat ; le tournoi le relance ou son organisateur décide",
    "The set is called again.": "Le set est relancé.",
    "The tournament was cancelled.": "Le tournoi a été annulé.",
    "The tournament {name} has started: you are seed {seed} of {players}. Your sets are called here.": "Le tournoi {name} a commencé : tu es la tête de série {seed} sur {players}. Tes sets sont appelés ici.",
    "The tournament {name} is over: {champion} won it.": "Le tournoi {name} est terminé : {champion} l'a gagné.",
    "The tournament {name} is over: {champion} won it. You finished {place}.": "Le tournoi {name} est terminé : {champion} l'a gagné. Tu as terminé : {place}.",
    "The tournament {name} was cancelled by its organizer.": "Le tournoi {name} a été annulé par son organisateur.",
    "The tournament {name} was cancelled: not enough players.": "Le tournoi {name} a été annulé : pas assez de joueurs.",
    "This tournament had no bracket.": "Ce tournoi n'a pas eu de bracket.",
    "This tournament is for another build of the game.": "Ce tournoi est pour un autre build du jeu.",
    "Tournament": "Tournoi",
    "Tournament set": "Set de tournoi",
    "Tournament set vs {name}": "Set de tournoi contre {name}",
    "Tournament {name} created.": "Tournoi {name} créé.",
    "Tournament {name}: set {set} needs you ({why}). Report the result or reset it.": "Tournoi {name} : le set {set} a besoin de toi ({why}). Saisis le résultat ou réinitialise-le.",
    "Tournament {name}: {code}": "Tournoi {name} : {code}",
    "Tournaments": "Tournois",
    "Winners final": "Finale Winners",
    "Winners round {number}": "Tour {number} Winners",
    "Winners semi-final": "Demi-finale Winners",
    "Withdraw": "Se retirer",
    "Withdraw from {name}? You are out of the tournament.": "Te retirer de {name} ? Tu quittes le tournoi.",
    "Write the start time as HH:MM, e.g. 20:30.": "Écris l'heure de début sous la forme HH:MM, par ex. 20:30.",
    "You are checked in.": "Ton check-in est fait.",
    "You are in. Your next set is called here when its players are known.": "Tu es qualifié. Ton prochain set est appelé ici dès que ses joueurs sont connus.",
    "You are out of {name}.": "Tu es éliminé de {name}.",
    "You are out of {name}: {place}.": "Tu es éliminé de {name} : {place}.",
    "You are out of {name}: {why}.": "Tu es éliminé de {name} : {why}.",
    "You are out: {why}.": "Tu es éliminé : {why}.",
    "You are signed up.": "Tu es inscrit.",
    "You are signed up. Check in now, or you are not in the bracket.": "Tu es inscrit. Fais le check-in maintenant, sinon tu ne seras pas dans le bracket.",
    "You did not check in for {name}; the tournament started without you.": "Tu n'as pas fait le check-in pour {name} ; le tournoi a commencé sans toi.",
    "You finished {place}.": "Tu as terminé : {place}.",
    "You left the tournament.": "Tu as quitté le tournoi.",
    "You won the tournament {name}!": "Tu as gagné le tournoi {name} !",
    "Your next set: {set}.": "Ton prochain set : {set}.",
    "Your opponent did not show up: you win the set.": "Ton adversaire ne s'est pas présenté : tu gagnes le set.",
    "Your opponent is out of the tournament: you win the set.": "Ton adversaire est éliminé du tournoi : tu gagnes le set.",
    "Your tournament set has no result; the organizer decides how it goes on.": "Ton set de tournoi n'a pas de résultat ; l'organisateur décide de la suite.",
    "Your tournament set is ready": "Ton set de tournoi est prêt",
    "accept within {seconds} s": "accepter sous {seconds} s",
    "accepted -- waiting for {name}...": "accepté -- en attente de {name}...",
    "best of {best}": "au meilleur des {best}",
    "bye": "exempt",
    "check-in from {time}": "check-in dès {time}",
    "decided by the organizer": "décidé par l'organisateur",
    "did not show up": "absent",
    "disqualified": "disqualification",
    "disqualified by the organizer": "disqualifié par l'organisateur",
    "ended {time}": "terminé {time}",
    "in 1 hour": "dans 1 heure",
    "in 10 minutes": "dans 10 minutes",
    "in 12 hours": "dans 12 heures",
    "in 15 minutes": "dans 15 minutes",
    "in 2 hours": "dans 2 heures",
    "in 24 hours": "dans 24 heures",
    "in 3 hours": "dans 3 heures",
    "in 30 minutes": "dans 30 minutes",
    "in 5 minutes": "dans 5 minutes",
    "in 6 hours": "dans 6 heures",
    "no-show": "absence",
    "nobody": "personne",
    "none yet": "aucun pour l'instant",
    "not needed": "pas nécessaire",
    "or at (HH:MM)": "ou à (HH:MM)",
    "organizer {name}": "organisé par {name}",
    "place {place}": "place {place}",
    "rated": "classé",
    "results disputed": "résultats contestés",
    "started {time}": "commencé {time}",
    "starts {time}": "début {time}",
    "waiting": "à venir",
    "withdrew": "retiré",
    "{format}, best of {best}": "{format}, au meilleur des {best}",
    "{name} has accepted.": "{name} a accepté.",
    "{name} is not online yet.": "{name} n'est pas encore en ligne.",
    "{name} wins": "{name} gagne",
    "{name} wins set {set}?": "{name} gagne le set {set} ?",
    "{name}'s tournament": "Tournoi de {name}",
    "{players} of {max} players": "{players} joueurs sur {max}",
    "The organizer decided the set.": "L'organisateur a décidé du set.",
    # ---- lobby/t5lobby/i18n_known.py: lobby/t5lobby/server/tournaments.py
    "tournaments need an account": "les tournois nécessitent un compte",
    "no such tournament": "tournoi introuvable",
    "only the server's organizers can create tournaments here": "ici, seuls les organisateurs du serveur peuvent créer des tournois",
    "a tournament name is 3-40 characters": "le nom d'un tournoi fait de 3 à 40 caractères",
    "the format is single or double elimination": "le format est l'élimination simple ou double",
    "a set is first to 2 or first to 3 games": "un set se joue en 2 ou 3 parties gagnantes",
    "the player limit is 8, 16, 32 or 64": "la limite de joueurs est 8, 16, 32 ou 64",
    "the check-in window is 0, 5, 10, 15, 30 or 60 minutes": "le check-in dure 0, 5, 10, 15, 30 ou 60 minutes",
    "seeding is random or by rating": "le seeding est aléatoire ou par cote",
    "that start time has passed": "cette heure de début est déjà passée",
    "a tournament starts within {days} days": "un tournoi commence dans les {days} jours",
    "this server has as many tournaments as it takes; try again later": "ce serveur a déjà autant de tournois qu'il en accepte ; réessaie plus tard",
    "you already run {count} tournaments; finish or cancel one first": "tu organises déjà {count} tournois ; termines-en ou annules-en un d'abord",
    "update the launcher to play in tournaments": "mets à jour le launcher pour jouer des tournois",
    "sign-up for that tournament is closed": "les inscriptions à ce tournoi sont closes",
    "that tournament is played with another build of the game": "ce tournoi se joue avec un autre build du jeu",
    "that tournament is full": "ce tournoi est complet",
    "you are not in that tournament": "tu n'es pas dans ce tournoi",
    "that tournament is over": "ce tournoi est terminé",
    "check-in is not open": "le check-in n'est pas ouvert",
    "that tournament is not running": "ce tournoi n'est pas en cours",
    "that set is not yours to play": "ce set n'est pas le tien",
    "that set is not waiting for you": "ce set ne t'attend pas",
    "only the organizer can do that": "seul l'organisateur peut faire ça",
    "that tournament name is not allowed here":
        "ce nom de tournoi n'est pas autorisé ici",
    "this internet address runs as many tournaments as one organizer may; finish or cancel one first":
        "cette adresse internet a déjà autant de tournois qu'un organisateur peut en avoir ; termine ou annule-en un d'abord",
    "the organizer took you off this tournament":
        "l'organisateur t'a retiré de ce tournoi",
    "you play in that set yourself: a server tournament admin decides it (or cancel the tournament)":
        "tu joues ce set toi-même : un administrateur des tournois du serveur le décide (ou annule le tournoi)",
    "that tournament has started already": "ce tournoi a déjà commencé",
    "a tournament needs at least 2 players": "un tournoi a besoin d'au moins 2 joueurs",
    "no such player in that tournament": "ce joueur n'est pas dans ce tournoi",
    "that player is out already": "ce joueur est déjà éliminé",
    "no such set": "set introuvable",
    "that set is decided; override it instead": "ce set est déjà décidé ; corrige-le plutôt",
    "only a played set can be overridden": "seul un set joué peut être corrigé",
    "that set has not been played": "ce set n'a pas encore été joué",
    "that set was a walkover": "ce set était un forfait",
    "set {set} was already played from this result; reset it first": "le set {set} a déjà été joué avec ce résultat ; réinitialise-le d'abord",
    "finish your match first, then accept the tournament set": "termine d'abord ton match, puis accepte le set du tournoi",
    "finish your set first, then accept the tournament set": "termine d'abord ton set, puis accepte le set du tournoi",
    "you are in a tournament set; finish it first": "tu es dans un set de tournoi ; termine-le d'abord",
    "that player is playing a tournament set": "ce joueur joue un set de tournoi",
    "your tournament set is ready; accept it first": "ton set de tournoi est prêt ; accepte-le d'abord",
    "that player has a tournament set to play": "ce joueur a un set de tournoi à jouer",
    # ---- lobby/t5lobby/theme.py
    "Good connection": "Bonne connexion",
    "Laggy connection": "Connexion qui lag",
    "OK connection": "Connexion correcte",
    "Ping not known yet": "Ping pas encore connu",
    "sec": "sec",
    # ---- lobby/t5lobby/tk_tab.py
    "Leave set (counts as a loss)": "Quitter le set (compte comme défaite)",
    "Leave the ranked set": "Quitter le set Ranked",
    "Leave this ranked set?\n\nLeaving a ranked set counts as losing it.":
        "Quitter ce set Ranked ?\n\nQuitter un set Ranked compte comme une défaite.",
    "Rematch? (a new set)": "Rematch ? (un nouveau set)",
    "in a room": "dans un salon",
    "in lobby": "dans le lobby",
    "matching": "matchmaking",
    "searching": "en recherche",
    "full": "plein",
    "open": "ouvert",
    "Result confirmed": "Résultat confirmé",
    "Result recorded (your opponent did not report)": "Résultat enregistré (ton adversaire n'a rien signalé)",
    "Match decided by forfeit": "Match décidé par forfait",
    "Result decided by the games' state": "Résultat décidé par l'état des jeux",
    "You and your opponent reported different results -- not counted":
        "Toi et ton adversaire avez signalé des résultats différents -- non compté",
    "No result": "Pas de résultat",
    "confirmed": "confirmé",
    "forfeit": "forfait",
    "one-sided": "unilatéral",
    "disputed": "contesté",
    "resolved": "résolu",
    "void": "annulé",
    "draw": "nul",
    "loss": "défaite",
    "win": "victoire",
    "the two games went out of sync": "les deux jeux se sont désynchronisés",
    "too short to count": "trop court pour compter",
    "a game crashed": "un jeu a planté",
    "the reports disagreed": "les signalements ne concordaient pas",
    "left right away": "parti tout de suite",
    "a player left": "un joueur est parti",
    "a player lost the connection": "un joueur a perdu la connexion",
    "a player did not report": "un joueur n'a rien signalé",
    "the connection between the games failed": "la connexion entre les jeux a échoué",
    "both players left": "les deux joueurs sont partis",
    "no result in time": "pas de résultat à temps",
    "repeated crashes count as losses": "les plantages répétés sont des défaites",
    "repeated early quits": "abandons précoces répétés",
    "repeated missing reports": "signalements manquants répétés",
    "scores differed": "les scores différaient",
    "the fight ended without a winner": "le combat s'est terminé sans vainqueur",
    "Match declined.": "Match refusé.",
    "Nobody accepted in time.": "Personne n'a accepté à temps.",
    "Your opponent left.": "Ton adversaire est parti.",
    "No UDP connection to the lobby server (firewall?).": "Pas de connexion UDP au serveur du lobby (pare-feu ?).",
    "Could not connect the two PCs, not even through the relay.":
        "Impossible de connecter les deux PC, même via le relais.",
    "The lobby server's relay is full; try again in a moment.":
        "Le relais du serveur du lobby est plein ; réessaie dans un instant.",
    "Challenge cancelled.": "Défi annulé.",
    "Challenge declined.": "Défi refusé.",
    "Challenge expired.": "Défi expiré.",
    "direct": "directe",
    "via the lobby server's relay": "via le relais du serveur du lobby",
    "via the relay server {name}": "via le serveur relais {name}",
    "Lobby error: {error}": "Erreur du lobby : {error}",
    "guest": "invité",
    "Not connected. Ranked needs an account; guests play casual matches.":
        "Pas connecté. Le Ranked nécessite un compte ; les invités jouent des matchs amicaux.",
    "Passwords are only sent to servers on this PC / your network, or over an encrypted "
    "(TLS) connection.":
        "Les mots de passe ne sont envoyés qu'aux serveurs sur ce PC ou ton réseau, ou via une connexion chiffrée "
        "(TLS).",
    "Double-click a player in the lobby or the leaderboard.":
        "Double-clique sur un joueur dans le lobby ou le classement.",
    "{name} (guest, casual matches only)": "{name} (invité, matchs amicaux seulement)",
    "{record} this session": "{record} cette session",
    "rating {rating}": "cote {rating}",
    "main {character}": "main {character}",
    "server ping {ms} ms": "ping serveur {ms} ms",
    "encrypted": "chiffré",
    "[Server: {notice}]": "[Serveur : {notice}]",
    "Server notice: {notice}": "Annonce du serveur : {notice}",
    "The game is not built.": "Le jeu n'est pas compilé.",
    "Cannot read the build's identity: {error}": "Impossible de lire l'identité de la build : {error}",
    "Enter a password (6 characters or more), or play as a guest.":
        "Entre un mot de passe (6 caractères ou plus), ou joue en invité.",
    "Connecting to {server}...": "Connexion à {server}...",
    "Pick a character, then Ranked match (accounts) or Quick match.":
        "Choisis un personnage, puis match Ranked (avec compte) ou Quick Match.",
    "Encrypted connection (TLS).": "Connexion chiffrée (TLS).",
    "(logged in with your saved login)": "(connecté avec ta connexion enregistrée)",
    "In the lobby.": "Dans le lobby.",
    "Your saved login has expired; log in with your password.":
        "Ta connexion enregistrée a expiré ; connecte-toi avec ton mot de passe.",
    "Create account": "Créer un compte",
    "Type the password again:": "Retape le mot de passe :",
    "The two passwords differ.": "Les deux mots de passe sont différents.",
    "Closing the running game for the online match...": "Fermeture du jeu en cours pour le match en ligne...",
    "Also forget the saved login on this PC?\n\n(No = you are logged in automatically "
    "next time.)":
        "Oublier aussi la connexion enregistrée sur ce PC ?\n\n(Non = tu seras connecté automatiquement la prochaine "
        "fois.)",
    "Log out": "Se déconnecter",
    "Not connected.": "Pas connecté.",
    "Change password": "Changer le mot de passe",
    "Current password:": "Mot de passe actuel :",
    "New password (6 characters or more):": "Nouveau mot de passe (6 caractères ou plus) :",
    "New password again:": "Nouveau mot de passe, encore :",
    "The two new passwords differ.": "Les deux nouveaux mots de passe sont différents.",
    "Password changed. Saved logins on other PCs have ended.":
        "Mot de passe changé. Les connexions enregistrées sur d'autres PC ont pris fin.",
    "Recovery codes": "Codes de récupération",
    "Your password (the old codes stop working):": "Ton mot de passe (les anciens codes ne marcheront plus) :",
    "Save recovery codes": "Enregistrer les codes de récupération",
    "T5DR Online recovery codes for {name} on {server}": "Codes de récupération T5DR Online pour {name} sur {server}",
    "Forgot password": "Mot de passe oublié",
    "Account name:": "Nom du compte :",
    "One of your recovery codes (XXXX-XXXX-XXXX):": "Un de tes codes de récupération (XXXX-XXXX-XXXX) :",
    "Password reset. {count} recovery code(s) left. Log in with the new password.":
        "Mot de passe réinitialisé. Il reste {count} code(s) de récupération. Connecte-toi avec le nouveau mot de "
        "passe.",
    "Server certificate": "Certificat du serveur",
    "For a server with its own (self-signed) certificate: its SHA-256 fingerprint, from "
    "whoever runs it.\nEmpty = no pinning (use tls://host:port for a server with a "
    "normal certificate).":
        "Pour un serveur avec son propre certificat (auto-signé) : son empreinte SHA-256, donnée par celui qui le "
        "gère.\nVide = pas d'épinglage (utilise tls://host:port pour un serveur avec un certificat normal).",
    "Searching for an opponent...": "Recherche d'un adversaire...",
    "Searching for an opponent (ranked: similar rank and a good connection, strict: "
    "within 150 rating points -- this can take a while)...":
        "Recherche d'un adversaire (Ranked : rang proche et bonne connexion, strict : à moins de 150 points de cote "
        "-- ça peut prendre du temps)...",
    "Searching for an opponent (ranked: similar rank and a good connection)...":
        "Recherche d'un adversaire (Ranked : rang proche et bonne connexion)...",
    "Select a room first.": "Choisis d'abord un salon.",
    "Select an opponent in the list first.": "Choisis d'abord un adversaire dans la liste.",
    "Challenge sent.": "Défi envoyé.",
    "Blocked players": "Joueurs bloqués",
    "You are never matched with these players (ranked, quick matches, rooms, challenges, "
    "rematches). They are not told. Accounts stay blocked; a guest is blocked until you "
    "log out.":
        "Tu ne seras jamais mis face à ces joueurs (Ranked, Quick Match, salons, défis, rematchs). Ils ne sont pas "
        "prévenus. Les comptes restent bloqués ; un invité est bloqué jusqu'à ta déconnexion.",
    "Unblocked {name}.": "{name} débloqué.",
    "Unblock": "Débloquer",
    "Block player": "Bloquer le joueur",
    "Block {name}?\n\nYou will not be matched with them again. They are not told. You "
    "can unblock them under \"Blocked players...\".":
        "Bloquer {name} ?\n\nTu ne seras plus mis face à ce joueur. Il n'est pas prévenu. Tu peux le débloquer dans "
        "« Joueurs bloqués... ».",
    "Blocked {name}. You will not be matched again.": "{name} bloqué. Vous ne serez plus mis face à face.",
    "you": "toi",
    "{name} -- {rank}": "{name} -- {rank}",
    "Rating {rating} +/- {rd}": "Cote {rating} +/- {rd}",
    "(provisional)": "(provisoire)",
    "#{place} on the leaderboard": "n° {place} au classement",
    "Record {record}": "Bilan {record}",
    "Played {games}: {wins} won, {losses} lost, win rate {rate} %": "Joués {games} : {wins} gagnés, {losses} perdus, {rate} % de victoires",
    "Ranked {games}, {rate} % won": "Ranked {games}, {rate} % gagnés",
    "Casual {games}, {rate} % won": "Amical {games}, {rate} % gagnés",
    "ranked matches {count}": "matchs Ranked {count}",
    "highest rank {rank}": "meilleur rang {rank}",
    "Characters: {list}": "Personnages : {list}",
    "Matches without result caused in the last 24 h: {count}":
        "Matchs sans résultat causés ces dernières 24 h : {count}",
    "Recovery codes left: {count}": "Codes de récupération restants : {count}",
    "{you} vs {opponent}": "{you} vs {opponent}",
    "casual": "amical",
    "Opponent: {name} ({rank}, {rating})": "Adversaire : {name} ({rank}, {rating})",
    "RANKED": "RANKED",
    "rematch": "Rematch",
    "{name} ({rank}) challenges you": "{name} ({rank}) te défie",
    "Accept": "Accepter",
    "Decline": "Refuser",
    "Challenge {state}.": "Défi : {state}.",
    "connecting...": "connexion...",
    "Your opponent accepted.": "Ton adversaire a accepté.",
    "Match cancelled ({reason}).": "Match annulé ({reason}).",
    "Ranked match vs {name}": "Match Ranked contre {name}",
    "Casual match vs {name}": "Match amical contre {name}",
    "{p1} vs {p2}": "{p1} vs {p2}",
    "ping {ms} ms ({how}), input delay {frames} frames ({delay_ms} ms)":
        "ping {ms} ms ({how}), input delay de {frames} frames ({delay_ms} ms)",
    "Lost the lobby connection -- reconnecting (your match goes on)...":
        "Connexion au lobby perdue -- reconnexion (ton match continue)...",
    "Reconnected to the lobby.": "Reconnecté au lobby.",
    "Lost the lobby connection: {reason}": "Connexion au lobby perdue : {reason}",
    "Lost the connection to the lobby server.": "Connexion au serveur du lobby perdue.",
    "Removed from the lobby: {reason}": "Retiré du lobby : {reason}",
    "The game closed. How did the match against {opponent} end?":
        "Le jeu s'est fermé. Comment s'est terminé le match contre {opponent} ?",
    "I won": "J'ai gagné",
    "I lost": "J'ai perdu",
    "Draw": "Égalité",
    "I quit": "J'ai abandonné",
    "{opponent} wants a rematch": "{opponent} veut un Rematch",
    "Rematch": "Rematch",
    "No thanks": "Non merci",
    "Result sent; waiting for your opponent's report...":
        "Résultat envoyé ; en attente du signalement de ton adversaire...",
    "Rematch offered; waiting for your opponent...": "Rematch proposé ; en attente de ton adversaire...",
    "(other version)": "(autre version)",
    "other version": "autre version",
    "ranked": "Ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "Recherche... ({ranked} en file Ranked, {quick} en Quick Match)",
    "ping about {ms} ms (estimated; measured directly once you both accept)":
        "ping d'environ {ms} ms (estimé ; mesuré en direct dès que vous acceptez tous les deux)",
    "ping not known yet": "ping pas encore connu",
    "Opponent found": "Adversaire trouvé",
    "accept within {seconds} s?": "accepter sous {seconds} s ?",
    "waiting for the opponent...": "en attente de l'adversaire...",
    "Lag check: {text}": "Test de lag : {text}",
    "You left after the lag check. No penalty, no rating change.":
        "Tu es parti après le test de lag. Pas de pénalité, pas de changement de cote.",
    "Your opponent left after the lag check. No penalty for anyone.":
        "Ton adversaire est parti après le test de lag. Pas de pénalité pour personne.",
    "Your opponent left. The set is over.": "Ton adversaire est parti. Le set est terminé.",
    "Rematch {name}": "Rematch contre {name}",
    "Next game": "Partie suivante",
    "Leave": "Quitter",
    "Block {name}": "Bloquer {name}",
    "Leave: too laggy": "Quitter : trop de lag",
    "You lost.": "Tu as perdu.",
    "You won.": "Tu as gagné.",
    "rating {rating} ({delta})": "cote {rating} ({delta})",
    "PROMOTED to {rank}!": "PROMU au rang {rank} !",
    "demoted to {rank}": "rétrogradé au rang {rank}",
    "placed at {rank}": "placé au rang {rank}",
    "placement {done}/{total}": "placement {done}/{total}",
    "your opponent": "ton adversaire",
    "Rematch?": "Rematch ?",
    "Controller off.": "Manette désactivée.",
    "No controller found.": "Aucune manette trouvée.",
    "Controller: {summary}": "Manette : {summary}",
    "Cannot start the lobby server: {error}": "Impossible de lancer le serveur du lobby : {error}",
    "Stop hosting": "Arrêter d'héberger",
    "Starting a lobby server on this PC and asking the router to forward its ports...":
        "Lancement d'un serveur de lobby sur ce PC et demande au routeur de rediriger ses ports...",
    "Starting a lobby server on this PC...": "Lancement d'un serveur de lobby sur ce PC...",
    "<your public IP>": "<ton IP publique>",
    "Hosting. Friends paste this as their Server (copied to the clipboard):\n  {share}":
        "Hébergement en cours. Tes amis collent ceci comme Serveur (copié dans le presse-papiers) :\n  {share}",
    "\n  same network: {lan}": "\n  même réseau : {lan}",
    "\n  Forward TCP+UDP 7781 and UDP 7782 on your router (or tick 'Open router ports').":
        "\n  Redirige TCP+UDP 7781 et UDP 7782 sur ton routeur (ou coche « Ouvrir les ports du routeur »).",
    "Hosting a lobby on this PC. Log in to join it yourself.":
        "Un lobby est hébergé sur ce PC. Connecte-toi pour le rejoindre toi aussi.",
    "Hosting failed: {message}": "Échec de l'hébergement : {message}",
    "Host for friends": "Héberger pour des amis",
    "The lobby server stopped (exit code {code}); see its log in {folder}.":
        "Le serveur du lobby s'est arrêté (code de sortie {code}) ; son journal est dans {folder}.",
    "Stopped hosting.": "Hébergement arrêté.",
    # in-game character select (branch ingame-select)
    "Pick your fighter in the game ({secs} s; Select = random; no pick = the character set here).":
        "Choisis ton combattant dans le jeu ({secs} s ; Select = aléatoire ; sans choix = le personnage choisi ici).",
    "Waiting for your opponent to pick...": "En attente du choix de ton adversaire...",
    "Ranked match (accounts) or Quick match; then pick your fighter in the game (Select = random). The character here is used when you do not pick in time.":
        "Match Ranked (avec compte) ou Quick Match ; puis choisis ton combattant dans le jeu (Select = aléatoire). "
        "Le personnage d'ici sert si tu ne choisis pas à temps.",
    "pick your fighter in the game ({secs} s)": "choisis ton combattant dans le jeu ({secs} s)",
    "(locked for this ranked set)": "(verrouillé pour ce set Ranked)",
    "Pick your fighter in the game": "Choisis ton combattant dans le jeu",
    "Your opponent is picking": "Ton adversaire choisit",
    # ---- lobby/t5lobby/tk_views.py
    "Rank": "Rang",
    "Rating": "Cote",
    "Record": "Bilan",
    "Main": "Main",
    "Ping": "Ping",
    "Room": "Salon",
    "Status": "Statut",
    "Owner": "Créateur",
    "Place": "Place",
    "State": "État",
    "When": "Quand",
    "Characters": "Personnages",
    "Opponent": "Adversaire",
    "Result": "Résultat",
    "Score": "Rounds",
    "Check the server address and your internet connection, then try again.":
        "Vérifie l'adresse du serveur et ta connexion internet, puis réessaie.",
    "Check your internet connection, then try again.": "Vérifie ta connexion internet, puis réessaie.",
    "The server is slow or gone; try again in a minute.": "Le serveur est lent ou absent ; réessaie dans une minute.",
    "Log in again.": "Reconnecte-toi.",
    "Ask whoever runs the server for its current fingerprint (\"Server certificate...\").":
        "Demande à celui qui gère le serveur son empreinte actuelle (« Certificat du serveur... »).",
    "Check the spelling, or use \"Forgot password...\".":
        "Vérifie l'orthographe, ou utilise « Mot de passe oublié... ».",
    "Check the name and the code; each code works once.":
        "Vérifie le nom et le code ; chaque code ne sert qu'une fois.",
    "Pick another name, or wait a minute if that was you.":
        "Choisis un autre nom, ou attends une minute si c'était toi.",
    "Log in with that account's password, or pick another name.":
        "Connecte-toi avec le mot de passe de ce compte, ou choisis un autre nom.",
    "Pick another name.": "Choisis un autre nom.",
    "Update the game to the release this server asks for.":
        "Mets à jour le jeu vers la version demandée par ce serveur.",
    "You both need the same release of the game.": "Vous avez besoin tous les deux de la même version du jeu.",
    "Update the launcher to the newest release.": "Mets à jour le launcher vers la dernière version.",
    "Create an account (free) to play ranked.": "Crée un compte (gratuit) pour jouer en Ranked.",
    "Pick another room or create your own.": "Choisis un autre salon ou crée le tien.",
    "Log in with your password.": "Connecte-toi avec ton mot de passe.",
    "Build the game on the Build tab first.": "Compile d'abord le jeu dans l'onglet Compiler.",
    "Allow T5DR Online through the Windows firewall, then search again.":
        "Autorise T5DR Online dans le pare-feu Windows, puis relance la recherche.",
    "Try again; if it keeps failing, check your firewall or router.":
        "Réessaie ; si ça échoue encore, vérifie ton pare-feu ou ton routeur.",
    "Log in again; your settings are kept.": "Reconnecte-toi ; tes réglages sont conservés.",
    "Type the same password twice.": "Tape deux fois le même mot de passe.",
    "Find a new opponent.": "Trouve un nouvel adversaire.",
    "Check the Play offline tab: does the game start there?":
        "Regarde l'onglet Jouer hors ligne : le jeu s'y lance-t-il ?",
    "Against other players over the internet. Log in or play as a guest; the game starts "
    "by itself, straight into the fight, and the result comes back here.":
        "Contre d'autres joueurs sur internet. Connecte-toi ou joue en invité ; le jeu se lance tout seul, "
        "directement dans le combat, et le résultat revient ici.",
    "Server": "Serveur",
    "Server certificate...": "Certificat du serveur...",
    "Name": "Nom",
    "Log in": "Se connecter",
    "Password": "Mot de passe",
    "Password again": "Confirmer le mot de passe",
    "Name: 2 to 16 letters, digits, spaces or _-.[]()!?": "Nom : 2 à 16 lettres, chiffres, espaces ou _-.[]()!?",
    "Password: 6 to 128 characters": "Mot de passe : 6 à 128 caractères",
    "Both passwords the same": "Les deux mots de passe identiques",
    "You get recovery codes once: the only way back in if you forget the password":
        "Tu reçois des codes de récupération une seule fois : le seul moyen de revenir si tu oublies le mot de passe",
    "Remember me": "Se souvenir de moi",
    "Forgot password...": "Mot de passe oublié...",
    "Casual matches with the name above, no account and no password. Ranked matches, the "
    "leaderboard and your match history need an account.":
        "Matchs amicaux avec le nom ci-dessus, sans compte ni mot de passe. Les matchs Ranked, le classement et ton "
        "historique demandent un compte.",
    "Play as guest": "Jouer en invité",
    "Runs a lobby on this PC. Your friends type the address it shows into their Server "
    "box.":
        "Lance un lobby sur ce PC. Tes amis tapent l'adresse affichée dans leur champ Serveur.",
    "Open router ports (UPnP)": "Ouvrir les ports du routeur (UPnP)",
    "How it works": "Comment ça marche",
    "Quick match (casual) or Ranked match (account).": "Quick Match (amical) ou match Ranked (avec compte).",
    "An opponent is found: accept within 15 seconds.": "Un adversaire est trouvé : accepte sous 15 secondes.",
    "The game opens straight into the fight.": "Le jeu s'ouvre directement sur le combat.",
    "The result comes back here: rematch or next game.": "Le résultat revient ici : Rematch ou partie suivante.",
    "With a controller: A accepts, B declines.": "À la manette : A accepte, B refuse.",
    "Online nobody can pause the fight: Start does not open the pause menu.":
        "En ligne, personne ne peut mettre le combat en pause : Start n'ouvre pas le menu de pause.",
    "Intros and the replay after a round are skipped once both players have pressed Start.":
        "Les intros et le replay après une manche sont passés dès que les deux joueurs ont appuyé sur Start.",
    "Lobby": "Lobby",
    "Leaderboard": "Classement",
    "Profile": "Profil",
    "My profile": "Mon profil",
    "Find an opponent online": "Trouve un adversaire en ligne",
    "Character": "Personnage",
    "Locked for this ranked set": "Verrouillé pour ce set Ranked",
    "Ranked match": "Match Ranked",
    "Quick match": "Quick Match",
    "Casual: the lowest ping first": "Amical : le ping le plus bas d'abord",
    "Strict (ranked: +-150 rating)": "Strict (Ranked : +-150 de cote)",
    "Searching": "Recherche",
    "Looking for an opponent": "Recherche d'un adversaire",
    "Searching for": "Recherche depuis",
    "Stop searching": "Arrêter la recherche",
    "In match": "En match",
    "CASUAL": "AMICAL",
    "Input delay": "Input delay",
    "Connection": "Connexion",
    "Players online": "Joueurs en ligne",
    "Challenge": "Défier",
    "Rooms": "Salons",
    "Create room": "Créer un salon",
    "Join room": "Rejoindre le salon",
    "Leave room": "Quitter le salon",
    "Chat": "Chat",
    "Send": "Envoyer",
    "Refresh": "Actualiser",
    "Order: rating minus twice its uncertainty (a few matches are needed to climb). '?' "
    "= provisional.":
        "Ordre : cote moins deux fois son incertitude (quelques matchs sont nécessaires pour monter). « ? » = "
        "provisoire.",
    "Your account": "Ton compte",
    "Blocked players...": "Joueurs bloqués...",
    "Change password...": "Changer le mot de passe...",
    "New recovery codes...": "Nouveaux codes de récupération...",
    "Dismiss": "Masquer",
    "Use a controller here": "Utiliser une manette ici",
    "none open": "aucun ouvert",
    "Nobody else is online right now. Ranked match and Quick match keep looking until someone comes.":
        "Personne d'autre n'est en ligne pour l'instant. Match Ranked et Quick Match "
        "continuent de chercher jusqu'à ce que quelqu'un arrive.",
    "No rooms open. Create one: friends can join it and play in turn.":
        "Aucun salon ouvert. Crées-en un : tes amis peuvent le rejoindre et jouer à tour de rôle.",
    "Nobody has a ranked result yet. Win a ranked set to be the first.":
        "Personne n'a encore de résultat classé. Gagne un set classé pour être le premier.",
    "In your room “{name}”. Waiting for a second player...":
        "Dans ton salon « {name} ». En attente d'un deuxième joueur...",
    "In the room “{name}”. The match starts when you are both ready.":
        "Dans le salon « {name} ». Le match commence quand vous êtes prêts tous les deux.",
    "Hosting. Friends type this as their Server:\n{share}":
        "Hébergement en cours. Tes amis tapent ceci comme Serveur :\n{share}",
    "Same network: {lan}": "Même réseau : {lan}",
    "Guest · casual matches": "Invité · matchs amicaux",
    "Rating {rating}  ·  {record}": "Cote {rating}  ·  {record}",
    "Main: {character}": "Main : {character}",
    "Server ping {ms} ms": "Ping serveur {ms} ms",
    "Create an account to play ranked": "Crée un compte pour jouer en Ranked",
    "Rated: close to your rank, good connection": "Classé : proche de ton rang, bonne connexion",
    "Similar rank and a good connection, strict: within 150 rating points (this can take "
    "a while).":
        "Rang proche et bonne connexion, strict : à moins de 150 points de cote (ça peut prendre du temps).",
    "Similar rank and a good connection.": "Rang proche et bonne connexion.",
    "The opponent with the lowest ping first.": "D'abord l'adversaire avec le ping le plus bas.",
    "{ranked} in the ranked queue  ·  {quick} in quick match": "{ranked} en file Ranked  ·  {quick} en Quick Match",
    "Character select": "Sélection du personnage",
    "Stage select": "Sélection du stage",
    "Match over": "Match terminé",
    "Waiting for the next match": "En attente du prochain match",
    "Your game is running": "Ton jeu tourne",
    "Starting the game...": "Lancement du jeu...",
    "Waiting for the game...": "En attente du jeu...",
    "vs your opponent": "contre ton adversaire",
    "vs {name}": "contre {name}",
    "{count} frame  ({ms} ms)": "{count} frame  ({ms} ms)",
    "{count} frames  ({ms} ms)": "{count} frames  ({ms} ms)",
    "Direct": "Directe",
    "Local network": "Réseau local",
    "Relay (lobby server)": "Relais (serveur du lobby)",
    "Relay ({name})": "Relais ({name})",
    "Guest": "Invité",
    "{rank}  ·  rating {rating}": "{rank}  ·  cote {rating}",
    "SET · GAME {game}": "SET · PARTIE {game}",
    "Opponent hidden": "Adversaire masqué",
    "Name and side are shown once you both accept.":
        "Le nom et le côté s'affichent dès que vous acceptez tous les deux.",
    "(estimated before you connect)": "(estimé avant la connexion)",
    "Accepted. Waiting for your opponent...": "Accepté. En attente de ton adversaire...",
    "Match ready": "Match prêt",
    "Connecting the two games...": "Connexion des deux jeux...",
    "wants to play you. Accept to start the match.": "veut t'affronter. Accepte pour lancer le match.",
    "YOU WIN": "VICTOIRE",
    "YOU LOSE": "DÉFAITE",
    "DRAW": "ÉGALITÉ",
    "MATCH OVER": "MATCH TERMINÉ",
    "NO CONTEST": "SANS RÉSULTAT",
    "Casual match": "Match amical",
    "ROUNDS  (P1 – P2)": "ROUNDS  (P1 – P2)",
    "ROUNDS  (YOU – THEM)": "ROUNDS  (TOI – ADV.)",
    "GAMES  (YOU – THEM)": "PARTIES  (TOI – ADV.)",
    "SET WON": "SET GAGNÉ",
    "The game waits here for your next match: Rematch, Next game or Leave.":
        "Le jeu attend ici ton prochain match : Rematch, Partie suivante ou Quitter.",
    "SET LOST": "SET PERDU",
    "Ranked set": "Set Ranked",
    "Ranked set vs {name}": "Set Ranked contre {name}",
    "RANKED SET · BEST OF {best}": "SET RANKED · AU MEILLEUR DES {best}",
    "Game {number} of {best} starts in": "La partie {number} sur {best} commence dans",
    "Game {number} of {best} again (no winner), starts in":
        "Partie {number} sur {best} à rejouer (pas de vainqueur), commence dans",
    "Rating {rating}": "Cote {rating}",
    "PROMOTED": "PROMU",
    "DEMOTED": "RÉTROGRADÉ",
    "PLACED": "PLACÉ",
    "Placement match {done} of {total}": "Match de placement {done} sur {total}",
    "Lag check": "Test de lag",
    "Rematch offered. Waiting for {opp}...": "Rematch proposé. En attente de {opp}...",
    "Back to the lobby": "Retour au lobby",
    "New recovery codes": "Nouveaux codes de récupération",
    "Your account is ready": "Ton compte est prêt",
    "These codes are the only way back into your account if you forget the password "
    "(there is no e-mail). Each code works once. Write them down or save them somewhere "
    "safe -- they are not shown again.":
        "Ces codes sont le seul moyen de revenir dans ton compte si tu oublies le mot de passe (il n'y a pas "
        "d'e-mail). Chaque code ne sert qu'une fois. Note-les ou enregistre-les dans un endroit sûr -- ils ne seront "
        "plus affichés.",
    "Save to a file...": "Enregistrer dans un fichier...",
    "I have saved them": "Je les ai enregistrés",
    # ---- friends (tk_tab.py, tk_views.py)
    "Request": "Demande",
    "Friends": "Amis",
    "Invite to a match": "Inviter à un match",
    "Invite to my room": "Inviter dans mon salon",
    "Invite in {seconds} s": "Inviter dans {seconds} s",
    "Remove": "Supprimer",
    "Invite a friend who is online: one click on their side starts a casual match, or brings them into your room.":
        "Invite un ami en ligne : un clic de son côté lance un match amical, ou le fait entrer dans ton salon.",
    "Add a friend": "Ajouter un ami",
    "Send request": "Envoyer la demande",
    "Their account name. They become your friend when they accept.":
        "Son nom de compte. Vous devenez amis dès qu'il accepte.",
    "Requests": "Demandes",
    "Take back": "Retirer",
    "Invite from a friend": "Invitation d'un ami",
    "invites you to the room “{room}”. Accept to join it; the match starts at once.":
        "t'invite dans le salon « {room} ». Accepte pour le rejoindre ; le match commence tout de suite.",
    "invites you to a casual match. Accept to start it.": "t'invite à un match amical. Accepte pour le lancer.",
    "Check the spelling: friends are added by their account name.":
        "Vérifie l'orthographe : les amis s'ajoutent par leur nom de compte.",
    "in a match": "en match",
    "offline": "hors ligne",
    "older launcher: no invites": "vieux launcher : pas d'invitations",
    "Friends ({count})": "Amis ({count})",
    "offline, last seen {when}": "hors ligne depuis {when}",
    "Friends need an account. Log in with one to add friends and invite them.":
        "Les amis nécessitent un compte. Connecte-toi avec un compte pour ajouter des amis et les inviter.",
    "This lobby server has no friends list (it needs version 1.1.2 or newer).":
        "Ce serveur de lobby n'a pas de liste d'amis (il faut la version 1.1.2 ou plus récente).",
    "wants to be your friend": "veut être ton ami",
    "asked: waiting for an answer": "en attente de réponse",
    "{online} online · {count} of {max}": "{online} en ligne · {count} sur {max}",
    "Your friends see when you are online. Invite one who is online to play.":
        "Tes amis voient quand tu es en ligne. Invite-en un qui est en ligne pour jouer.",
    "No friends yet. Add one by account name: they become your friend when they accept.":
        "Pas encore d'amis. Ajoute-en un par son nom de compte : vous devenez amis dès qu'il accepte.",
    "Cancel the invite": "Annuler l'invitation",
    "You and {name} are friends now.": "Toi et {name}, vous êtes amis maintenant.",
    "Friend request sent to {name}. They become your friend when they accept.":
        "Demande d'ami envoyée à {name}. Vous devenez amis dès qu'il accepte.",
    "Request from {name} declined.": "Demande de {name} refusée.",
    "Request to {name} taken back.": "Demande à {name} retirée.",
    "Remove friend": "Supprimer l'ami",
    "Remove {name} from your friends?\n\nYou can ask again later; they have to accept again.":
        "Retirer {name} de tes amis ?\n\nTu pourras redemander plus tard ; il devra accepter à nouveau.",
    "{name} is no longer your friend.": "{name} n'est plus ton ami.",
    "Select a friend in the list first.": "Choisis d'abord un ami dans la liste.",
    "Invite sent to {name}; waiting for an answer ({seconds} s)...":
        "Invitation envoyée à {name} ; en attente de réponse ({seconds} s)...",
    "{name} ({rank}) invites you to the room “{room}”": "{name} ({rank}) t'invite dans le salon « {room} »",
    "{name} ({rank}) invites you to a casual match": "{name} ({rank}) t'invite à un match amical",
    "The invite from {name} ran out.": "L'invitation de {name} a expiré.",
    "The invite from {name} ended.": "L'invitation de {name} est terminée.",
    "{name} declined your invite.": "{name} a refusé ton invitation.",
    "{name} did not answer your invite.": "{name} n'a pas répondu à ton invitation.",
    "The invite to {name} ended.": "L'invitation à {name} est terminée.",
    "{name} wants to be your friend: see the Friends tab.": "{name} veut être ton ami : regarde l'onglet Amis.",
    "{name} accepted your friend request.": "{name} a accepté ta demande d'ami.",
    "{name} declined your friend request.": "{name} a refusé ta demande d'ami.",

    # ---- launcher/replays_ui.py, launcher/t5dr_launcher.pyw (Replays tab), problem_report.py
    "Replays":
        "Replays",
    "Every online match is saved here. Watch plays it back in the game exactly as it was played: the same inputs frame by frame, checked against the live match while it plays.":
        "Chaque match en ligne est enregistré ici. Regarder le rejoue dans le jeu exactement comme il a été joué : les mêmes entrées image par image, comparées au match en direct pendant la lecture.",
    "Date":
        "Date",
    "Fighters":
        "Combattants",
    "Netcode":
        "Netcode",
    "WATCH":
        "REGARDER",
    "Stop replay":
        "Arrêter le replay",
    "Delete":
        "Supprimer",
    "Open replays folder":
        "Ouvrir le dossier des replays",
    "While a replay plays: START (Enter) pauses and goes on, SELECT (Tab) ends the replay. A "
    "rematch is played after the matches before it in the same session: it starts from what they "
    "left.":
        "Pendant un replay : START (Entrée) met en pause et reprend, SELECT (Tab) termine le replay. Une "
        "revanche est jouée après les matchs précédents de la même session : elle part de l'état qu'ils "
        "ont laissé.",
    "Save online matches as replays":
        "Enregistrer les matchs en ligne comme replays",
    "Keep the players' names in replays":
        "Garder les noms des joueurs dans les replays",
    "Rollback":
        "Rollback",
    "Lockstep":
        "Lockstep",
    "(name not saved)":
        "(nom non enregistré)",
    "{matches} match(es) in {files} file(s) in {folder}":
        "{matches} match(s) dans {files} fichier(s) dans {folder}",
    "No replays yet. Play an online match: it is saved here.":
        "Pas encore de replays. Joue un match en ligne : il est enregistré ici.",
    "not finished":
        "pas terminé",
    "won {mine}-{theirs}":
        "gagné {mine}-{theirs}",
    "lost {mine}-{theirs}":
        "perdu {mine}-{theirs}",
    "Close the running game first (Stop game on the Play tab).":
        "Ferme d'abord le jeu ouvert (Arrêter le jeu dans l'onglet Jouer hors ligne).",
    "Build the game first (Build tab).":
        "Compile d'abord le jeu (onglet Compiler).",
    "This replay cannot be played: {why}":
        "Ce replay ne peut pas être lu : {why}",
    "Recorded with another version of the game: it may not play back the same.":
        "Enregistré avec une autre version du jeu : il peut ne pas se rejouer à l'identique.",
    "Playing {fighters} ({when})...":
        "Lecture de {fighters} ({when})...",
    "The replay ended before the end of the match.":
        "Le replay s'est arrêté avant la fin du match.",
    "Replay over: identical to the live match ({checks} checks, same result).":
        "Replay terminé : identique au match en direct ({checks} vérifications, même résultat).",
    "Replay over, but it went a different way from frame {frame} on (the game or its version differs from the one that played it).":
        "Replay terminé, mais à partir de l'image {frame} il s'est passé autre chose (le jeu ou sa version n'est pas celui qui l'a joué).",
    "Replay over.":
        "Replay terminé.",
    "Delete this replay file? It holds {n} match(es) against the same opponent.":
        "Supprimer ce fichier de replay ? Il contient {n} match(s) contre le même adversaire.",
    # ---- lobby/t5lobby/tk_spectate.py, server/spectating.py, launcher Settings (spectating live matches)
    "Spectators":
        "Spectateurs",
    "Friends and room visitors may watch my online matches":
        "Mes amis et les visiteurs de mon salon peuvent regarder mes matchs en ligne",
    "Also my ranked matches":
        "Aussi mes matchs Ranked",
    "They see the match a few seconds late, in their own game. Only when both players allow it; a "
    "ranked match only when both allow ranked too.":
        "Ils voient le match quelques secondes plus tard, dans leur propre jeu. Seulement si les deux "
        "joueurs l'autorisent ; un match Ranked seulement si les deux autorisent aussi le Ranked.",
    "Watch":
        "Regarder",
    "Spectating":
        "Spectateur",
    "Stop watching":
        "Arrêter de regarder",
    "Watching":
        "En direct",
    "Waiting for the match data...":
        "En attente des données du match...",
    "About {seconds} s behind the live match.":
        "Environ {seconds} s de retard sur le match en direct.",
    "It plays from the start of the players' session, a few seconds behind.":
        "La lecture part du début de la session des joueurs, avec quelques secondes de retard.",
    "Watching {p1} vs {p2}.":
        "Tu regardes {p1} vs {p2}.",
    "Spectators watching your match: {count}":
        "Spectateurs de ton match : {count}",
    "The live match is over.":
        "Le match en direct est terminé.",
    "The players turned spectators off.":
        "Les joueurs ont désactivé les spectateurs.",
    "The match data stopped coming.":
        "Les données du match n'arrivent plus.",
    "This session is too long to watch from its start.":
        "Cette session est trop longue pour être regardée depuis le début.",
    "Your own match is starting.":
        "Ton propre match commence.",
    "The match data was damaged.":
        "Les données du match étaient endommagées.",
    "You stopped watching.":
        "Tu as arrêté de regarder.",
    "A friend of the players took your place: the match has as many spectators as it can take.":
        "Un ami des joueurs a pris ta place : le match a autant de spectateurs qu'il peut en accueillir.",
    "this launcher cannot watch matches; update it":
        "ce launcher ne peut pas regarder de matchs ; mets-le à jour",
    "that match is not being played right now":
        "ce match n'est pas en cours",
    "you are playing in that match":
        "tu joues dans ce match",
    "you are in a match yourself":
        "tu es toi-même dans un match",
    "only friends of a player can watch this match":
        "seuls les amis d'un joueur peuvent regarder ce match",
    "the players do not allow spectators":
        "les joueurs n'autorisent pas les spectateurs",
    "neither player can send the match right now":
        "aucun joueur ne peut envoyer le match pour l'instant",
    "this match cannot be watched any more":
        "ce match ne peut plus être regardé",
    "this match has {count} spectators already":
        "ce match a déjà {count} spectateurs",
    "the server cannot show more matches right now":
        "le serveur ne peut pas montrer plus de matchs pour l'instant",
    "too many matches are watched from your network; stop watching one first":
        "trop de matchs sont regardés depuis ton réseau ; arrête d'abord d'en regarder un",
    "the places for guests at this match are taken; log in with an account to watch":
        "les places pour les invités de ce match sont prises ; connecte-toi avec un compte pour regarder",
    "the server cannot show guests more matches right now; log in with an account to watch":
        "le serveur ne peut pas montrer plus de matchs aux invités pour l'instant ; connecte-toi avec un compte pour regarder",
    # firewall hint on the Online tab (t5lobby.fwcheck, tk_tab.fw_hint_text)
    "Firewall":
        "Pare-feu",
    "How to fix":
        "Comment corriger",
    "Windows Firewall blocks {program} on this network. Matches still connect, but some only "
    "through a relay, with more lag.":
        "Le pare-feu Windows bloque {program} sur ce réseau. Les matchs se connectent quand même, "
        "mais certains seulement via un relais, avec plus de lag.",
    "A firewall seems to block T5DR Online's network traffic on this PC.":
        "Un pare-feu semble bloquer le trafic réseau de T5DR Online sur ce PC.",
    # patch 0063 (igpu-4k-stall): Internal resolution Auto, integrated-graphics and GPU-bound hints
    "Auto (matches the screen)":
        "Auto (selon l'écran)",
    "The game picks the step that matches your screen when it starts, at most 1080p on integrated graphics (they share the processor's memory and power).":
        "Le jeu choisit au démarrage le niveau qui correspond à ton écran, au plus 1080p avec une puce graphique intégrée (elle partage la mémoire et l'énergie du processeur).",
    "On this PC: {step}.":
        "Sur ce PC : {step}.",
    "{step} on integrated graphics: a busy built-in GPU slows the processor too (they share its power and memory). For 60 fps choose Auto in Settings -> Internal resolution: {better} here.":
        "{step} avec une puce graphique intégrée : une puce graphique occupée ralentit aussi le processeur (ils partagent son énergie et sa mémoire). Pour 60 fps, choisis Auto dans Paramètres -> Résolution interne : ici {better}.",
    "Auto is the default on integrated graphics.":
        "Avec une puce graphique intégrée, Auto est le réglage par défaut.",
    "Your processor ran at {ghz} GHz ({percent} % of its normal speed): set Windows power mode to Best performance.":
        "Ton processeur a tourné à {ghz} GHz ({percent} % de sa vitesse normale) : règle le mode d'alimentation de Windows sur Meilleures performances.",
    "Extra settings below set {setting}: that wins over this choice.":
        "Les réglages supplémentaires ci-dessous mettent {setting} : cela l'emporte sur ce choix.",
    "Fights were slower than 60 fps because of the graphics (GPU-bound): choose a lower Internal resolution in Settings.":
        "Les combats étaient sous 60 fps à cause du graphisme (limité par le GPU) : choisis une résolution interne plus basse dans Réglages.",
    "Fights were slower than 60 fps: the integrated graphics were busy and slowed the processor too. A lower Internal resolution in Settings helps.":
        "Les combats étaient sous 60 fps : la puce graphique intégrée était occupée et a aussi ralenti le processeur. Une résolution interne plus basse dans Réglages aide.",
    # ---- private and community rooms (lobby/t5lobby/tk_rooms.py; the server's messages: i18n_known.py)
    "private rooms need a newer launcher; update it":
        "les salons privés demandent un launcher plus récent ; mets-le à jour",
    "only the room's host can do that": "seul l'hôte du salon peut faire ça",
    "too many wrong room passwords; try again in {seconds} s":
        "trop de mots de passe de salon faux ; réessaie dans {seconds} s",
    "wrong room password": "mot de passe du salon faux",
    "the room's password changed; try again": "le mot de passe du salon a changé ; réessaie",
    "no room has that invite code": "aucun salon n'a ce code d'invitation",
    "rooms hold 2 to {count} players": "un salon accueille de 2 à {count} joueurs",
    "room passwords are 4-64 characters, no space at either end":
        "les mots de passe de salon font 4 à 64 caractères, sans espace au début ni à la fin",
    "private and community rooms are casual (unranked)":
        "les salons privés et communautaires sont amicaux (pas de Ranked)",
    "you are in that room": "tu es déjà dans ce salon",
    "the room's host removed you from this room": "l'hôte t'a retiré de ce salon",
    "the room's host turned away password guesses from your network; ask the host for an invite":
        "l'hôte du salon a refoulé les essais de mot de passe venant de ton réseau ; demande-lui une invitation",
    "only a room with a password counts wrong guesses": "seul un salon avec mot de passe compte les essais faux",
    "that player is not in your room": "ce joueur n'est pas dans ton salon",
    "you cannot remove yourself; leave the room instead": "tu ne peux pas te retirer toi-même ; quitte plutôt le salon",
    "you can remove that player after their match": "tu pourras retirer ce joueur après son match",
    "only rooms for 3 or more players take turns": "seuls les salons de 3 joueurs ou plus jouent à tour de rôle",
    "you sit out in the room; press Back in line to play again":
        "tu passes ton tour dans le salon ; appuie sur Revenir dans la file pour rejouer",
    "the room picks the next match by itself": "le salon choisit lui-même le match suivant",
    "the room's host removed that player from this room": "l'hôte a retiré ce joueur de ce salon",
    "only the room's players can watch its match": "seuls les joueurs du salon peuvent regarder son match",
    "Anybody": "Tout le monde",
    "Back in line": "Revenir dans la file",
    "Back in line: you play when it is your turn.": "De retour dans la file : tu joues quand c'est ton tour.",
    "Copy invite code": "Copier le code d'invitation",
    "Create a room": "Créer un salon",
    "Everyone in turn": "Chacun son tour",
    "Hide the room from the room list": "Masquer le salon de la liste des salons",
    "In the room “{name}”: {count}/{size} players, taking turns.":
        "Dans le salon « {name} » : {count}/{size} joueurs, chacun son tour.",
    "Invite code": "Code d'invitation",
    "Line: {names}": "File : {names}",
    "New invite code": "Nouveau code d'invitation",
    "Next: {p1} vs {p2} in {seconds} s": "Ensuite : {p1} contre {p2} dans {seconds} s",
    "No room selected. Join a room with its invite code (XXXX-XXXX-XXXX):":
        "Aucun salon choisi. Rejoins un salon avec son code d'invitation (XXXX-XXXX-XXXX) :",
    "Password (4-64 characters):": "Mot de passe (4 à 64 caractères) :",
    "Players in the room:": "Joueurs dans le salon :",
    "Players:": "Joueurs :",
    "Playing: {p1} vs {p2}": "En jeu : {p1} contre {p2}",
    "Private (invite code)": "Privé (code d'invitation)",
    "Private (password)": "Privé (mot de passe)",
    "Remove player": "Retirer le joueur",
    "Remove {name} from the room? They cannot come back into it.":
        "Retirer {name} du salon ? Il ne pourra pas revenir.",
    "Removed {name} from the room.": "{name} a été retiré du salon.",
    "Wrong passwords in the last 10 minutes: {count} (networks: {networks})":
        "Mots de passe faux ces 10 dernières minutes : {count} (réseaux : {networks})",
    "Turn away the guessers": "Refouler ceux qui devinent",
    "Networks turned away: {count}. They cannot try passwords on this room any more.":
        "Réseaux refoulés : {count}. Ils ne peuvent plus essayer de mots de passe sur ce salon.",
    "Room created.": "Salon créé.",
    "Room created. Press Copy invite code to see the code you can share.":
        "Salon créé. Appuie sur Copier le code d'invitation pour voir le code à partager.",
    "Room name (optional):": "Nom du salon (facultatif) :",
    "Room password": "Mot de passe du salon",
    "Room passwords are 4-64 characters, with no space at the start or end.":
        "Les mots de passe de salon font 4 à 64 caractères, sans espace au début ni à la fin.",
    "Room settings": "Réglages du salon",
    "Room settings saved.": "Réglages du salon enregistrés.",
    "Room settings...": "Réglages du salon...",
    "Sit out": "Passer mon tour",
    "The invite code is in the field next to the button: select it and press Ctrl+C to copy it.":
        "Le code d'invitation est dans le champ à côté du bouton : sélectionne-le et appuie sur Ctrl+C pour le copier.",
    "The room's invite code (XXXX-XXXX-XXXX):": "Code d'invitation du salon (XXXX-XXXX-XXXX) :",
    "Turns (3 or more players):": "Tours (3 joueurs ou plus) :",
    "Who can join:": "Qui peut entrer :",
    "Winner stays": "Le gagnant reste",
    "You sit out: your turns are skipped until you press Back in line.":
        "Tu passes ton tour : on te saute jusqu'à ce que tu appuies sur Revenir dans la file.",
    "Your room: {name}": "Ton salon : {name}",
    "hidden": "masqué",
    "invites you to the private room “{room}”. Accept to join it without its password.":
        "t'invite dans le salon privé « {room} ». Accepte pour y entrer sans son mot de passe.",
    "private": "privé",
    "private (invite code)": "privé (code d'invitation)",
    "private (password)": "privé (mot de passe)",
    "{count}/{size} players": "{count}/{size} joueurs",
    "{name} (host)": "{name} (hôte)",
    "{name} (sitting out)": "{name} (passe son tour)",
    "{name} ({rank}) invites you to the private room “{room}”":
        "{name} ({rank}) t'invite dans le salon privé « {room} »",
    "“{room}” is private. Its password:": "« {room} » est privé. Son mot de passe :",
    "this server has no private rooms": "ce serveur n'a pas de salons privés",
}
