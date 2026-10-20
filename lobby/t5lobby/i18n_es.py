"""Spanish texts for the launcher and the Online tab (t5lobby/i18n.py).

English text -> Spanish text. The English text is the key, exactly as written in t("...") / N_("...");
the Spanish one keeps the same {placeholders}. Neutral Latin American Spanish in the tu-form ("control",
"la PC"), short and the way players talk. Names players know from the game and the lobby stay as they are:
Quick Match, Ranked, BUILD GAME, Rematch, Rollback, lobby, input delay, ping, the character and rank names.

Machine-assisted translation: corrections from players are welcome (docs/ONLINE.md "Languages").
Same keys and groups as i18n_de.py; tests/test_i18n.py and tools/i18n_extract.py check every catalog.
"""

MESSAGES = {
    # ---- launcher/controls_edit.py
    "Attack buttons": "Botones de ataque",
    "Several buttons with one press (macros)": "Varios botones a la vez (macros)",
    "Start, Select and the other buttons": "Start, Select y los demás botones",
    "Directions": "Direcciones",
    "1 (Left Punch)": "1 (Puño izquierdo)",
    "2 (Right Punch)": "2 (Puño derecho)",
    "3 (Left Kick)": "3 (Patada izquierda)",
    "4 (Right Kick)": "4 (Patada derecha)",
    "Select": "Select",
    "Start / pause": "Start / pausa",
    "Down": "Abajo",
    "Left": "Izquierda",
    "Up": "Arriba",
    "Right": "Derecha",
    "PlayStation pad, default": "Control PlayStation, predeterminado",
    "Xbox pad, default": "Control Xbox, predeterminado",
    "X Y A B are 1 2 3 4; bumpers and triggers are L1 R1 L2 R2.":
        "X Y A B son 1 2 3 4; bumpers y gatillos son L1 R1 L2 R2.",
    "Square Triangle Cross Circle are 1 2 3 4 (DualShock 4, DualSense and most "
    "PS3/PS4-mode sticks).":
        "Cuadrado Triángulo X Círculo son 1 2 3 4 (DualShock 4, DualSense y la mayoría de los sticks en modo "
        "PS3/PS4).",
    "Switch pad, default": "Control Switch, predeterminado",
    "Y X B A are 1 2 3 4 (Switch Pro controller, sticks in Switch mode).":
        "Y X B A son 1 2 3 4 (control Switch Pro, sticks en modo Switch).",
    "Xbox-style pad (generic)": "Control tipo Xbox (genérico)",
    "A B X Y buttons and LB RB, for Xbox-like pads that Windows does not give to XInput.":
        "Botones A B X Y y LB RB, para controles tipo Xbox que Windows no pasa a XInput.",
    "8-button stick (Vewlix layout)": "Stick de 8 botones (diseño Vewlix)",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: X Y RB LB over A B RT LT.":
        "Fila superior 1 2 [1+2] [1+3], fila inferior 3 4 [3+4] [2+4]: X Y RB LB sobre A B RT LT.",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: B1 B4 B6 B5 over B2 B3 B8 B7.":
        "Fila superior 1 2 [1+2] [1+3], fila inferior 3 4 [3+4] [2+4]: B1 B4 B6 B5 sobre B2 B3 B8 B7.",
    "6-button stick (Noir / Sega Astro)": "Stick de 6 botones (Noir / Sega Astro)",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: X Y RB over A B RT. LB and LT stay L1 and "
    "L2.":
        "Fila superior 1 2 [1+2], fila inferior 3 4 [3+4]: X Y RB sobre A B RT. LB y LT siguen siendo L1 y L2.",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: B1 B4 B6 over B2 B3 B8. B5 and B7 stay L1 "
    "and L2.":
        "Fila superior 1 2 [1+2], fila inferior 3 4 [3+4]: B1 B4 B6 sobre B2 B3 B8. B5 y B7 siguen siendo L1 y L2.",
    "Hitbox": "Hitbox",
    "The 8-button layout above. Directions come from the d-pad or the left stick, which "
    "is read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "El diseño de 8 botones de arriba. Las direcciones vienen de la cruceta o del stick izquierdo, que se lee "
        "como cruceta de 8 direcciones; izquierda+derecha (arriba+abajo) a la vez se anulan.",
    "The 8-button layout above. Directions come from the hat or the left stick, which is "
    "read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "El diseño de 8 botones de arriba. Las direcciones vienen del hat o del stick izquierdo, que se lee como "
        "cruceta de 8 direcciones; izquierda+derecha (arriba+abajo) a la vez se anulan.",
    "The file has {n} settings; the game reads at most {max}.":
        "El archivo tiene {n} ajustes; el juego lee como máximo {max}.",
    "The file has {n} sections; the game reads at most {max}.":
        "El archivo tiene {n} secciones; el juego lee como máximo {max}.",
    "Changed lines of {sections} that would have overridden this ({what}).":
        "Líneas cambiadas de {sections} que habrían sobrescrito esto ({what}).",
    "Lines of your file in other sections still change some buttons.":
        "Líneas de tu archivo en otras secciones todavía cambian algunos botones.",
    "Other lines in your file ({sections}) still change this layout.":
        "Otras líneas de tu archivo ({sections}) todavía cambian este diseño.",
    "{n} lines removed.": "{n} líneas eliminadas.",
    # ---- launcher/controls_ui.py
    "DirectInput controller": "Control DirectInput",
    "Xbox pad (XInput)": "Control Xbox (XInput)",
    "PlayStation pad, read directly": "Control PlayStation, leído directamente",
    "Arrows move; A S on top are 1 2, Z X below are 3 4. Q W are L1 R1, 1 2 are L2 R2, Enter is Start, Tab is Select.": "Las flechas mueven; A S arriba son 1 2, Z X abajo son 3 4. Q W son L1 R1, 1 2 son L2 R2, Enter es Start, Tab es Select.",
    "Arrows move; number pad 4 5 are 1 2, 1 2 are 3 4, 6 is 1+2, 3 is 3+4 (Num Lock on).": "Las flechas mueven; teclado numérico 4 5 son 1 2, 1 2 son 3 4, 6 es 1+2, 3 es 3+4 (Bloq Num activado).",
    "Esc (leaves the game)": "Esc (sale del juego)",
    "F11 (fullscreen)": "F11 (pantalla completa)",
    "F2 (training overlay)": "F2 (panel de entrenamiento)",
    "Keyboard, second player": "Teclado, segundo jugador",
    "Keyboard: WASD and U I J K": "Teclado: WASD y U I J K",
    "Keyboard: arrows and A S Z X": "Teclado: flechas y A S Z X",
    "Keyboard: arrows and number pad": "Teclado: flechas y teclado numérico",
    'Keyboard: pick a game button, then Set selected (or double-click it) and press the key. Esc stops. The game reads the keyboard while its window has the focus.': 'Teclado: elige un botón del juego, luego "Asignar seleccionado" (o doble clic) y presiona la tecla. Esc detiene. El juego lee el teclado mientras su ventana tiene el foco.',
    "Press only that one key. Esc stops.": "Presiona solo esa tecla. Esc detiene.",
    "Press the key for {button}...": "Presiona la tecla para {button}...",
    "The keyboard ([{section}] in controls.ini)": "El teclado ([{section}] en controls.ini)",
    "W A S D move; U I are 1 2, J K are 3 4, O is 1+2, L is 3+4. Y P are L1 R1, H and ; are L2 R2, Enter is Start, Backspace is Select.": "W A S D mueven; U I son 1 2, J K son 3 4, O es 1+2, L es 3+4. Y P son L1 R1, H y ; son L2 R2, Enter es Start, Retroceso es Select.",
    "{key} is the game's own key; press another one.": '{key} es una tecla del propio juego; presiona otra.',
    "{source} is also {other} for the second keyboard player.": "{source} también es {other} para el segundo jugador del teclado.",
    "Controls - T5DR Online": "Controles - T5DR Online",
    "Press a button on a controller to pick it, then set its buttons. The game reads the "
    "file when it starts.":
        "Presiona un botón en un control para elegirlo y luego asigna sus botones. El juego lee el archivo al "
        "iniciar.",
    "Controllers": "Controles",
    "Player": "Jugador",
    "Controller": "Control",
    "Pressed now": "Presionado ahora",
    "Move through this window with the controller": "Usar esta ventana con el control",
    "Buttons": "Botones",
    "Game button": "Botón del juego",
    "Controller button": "Botón del control",
    "Set up all buttons": "Asignar todos los botones",
    "Set up directions": "Asignar direcciones",
    "Set selected": "Asignar seleccionado",
    "Clear": "Borrar",
    "Layout": "Diseño",
    "Use this layout": "Usar este diseño",
    "Reset to defaults": "Restablecer valores",
    "Your changes apply to": "Tus cambios se aplican a",
    "Player and directions": "Jugador y direcciones",
    "Automatic": "Automático",
    "Player 1": "Jugador 1",
    "Player 2": "Jugador 2",
    "8-way d-pad": "Cruceta de 8 direcciones",
    "Analog stick": "Stick analógico",
    "Both cancel (neutral)": "Se anulan (neutral)",
    "Up wins (Up+Down is Up)": "Gana arriba (Arriba+Abajo es Arriba)",
    "Last direction wins": "Gana la última dirección",
    "Pass both through": "Dejar pasar ambas",
    "This controller is": "Este control es",
    "Left stick": "Stick izquierdo",
    "Opposite directions": "Direcciones opuestas",
    "Left stick, 8-way d-pad: a hitbox or stick in left-stick mode sends the direction "
    "as a stick; the game then reads it as d-pad presses. Left+Right (or Up+Down) at "
    "once happens on keyboards and hitboxes; the game cannot take both. Stick and "
    "opposite directions belong to the player's port.":
        "Stick izquierdo, cruceta de 8 direcciones: un hitbox o stick en modo stick izquierdo envía la dirección "
        "como stick; el juego la lee como cruceta. Izquierda+Derecha (o Arriba+Abajo) a la vez pasa en teclados y "
        "hitboxes; el juego no puede tomar ambas. Stick y direcciones opuestas pertenecen al puerto del jugador.",
    "Skip": "Omitir",
    "Stop": "Detener",
    "Save": "Guardar",
    "Revert": "Descartar",
    "Close": "Cerrar",
    "no controller": "sin control",
    "Controllers cannot be read on this PC.": "No se pueden leer controles en esta PC.",
    "No controller found. Plug one in; it shows up here by itself.":
        "No se encontró ningún control. Conecta uno; aparecerá aquí solo.",
    "switched off in [general]": "desactivado en [general]",
    "no free player port": "no hay puerto de jugador libre",
    "No controller chosen": "Ningún control elegido",
    "This controller model ({vid}:{pid})": "Este modelo de control ({vid}:{pid})",
    "This controller model (no USB ID)": "Este modelo de control (sin ID USB)",
    "All DirectInput controllers": "Todos los controles DirectInput",
    "All Xbox pads (XInput)": "Todos los controles Xbox (XInput)",
    "Only the controller on player {n}'s port": "Solo el control en el puerto del jugador {n}",
    "no player": "sin jugador",
    "player {n}": "jugador {n}",
    "yours": "tuyo",
    "Your own layout": "Tu propio diseño",
    "Player {n}": "Jugador {n}",
    "Buttons you set yourself, or a mix. Pick a layout to start from it.":
        "Botones que asignaste tú, o una mezcla. Elige un diseño para empezar desde él.",
    "On the controller: {up} / {down} choose a button, {accept} sets it, {clear} clears "
    "it, {save} saves, {back} closes. The game reads the file when it starts.":
        "En el control: {up} / {down} eligen un botón, {accept} lo asigna, {clear} lo borra, {save} guarda, {back} "
        "cierra. El juego lee el archivo al iniciar.",
    "(no game button)": "(sin botón del juego)",
    "Press a button on a controller first, or pick one in the list.":
        "Primero presiona un botón en un control, o elige uno de la lista.",
    "Press the button for {button}...": "Presiona el botón para {button}...",
    "Press only that one button on the controller.": "Presiona solo ese botón en el control.",
    "{n} of {total}.": "{n} de {total}.",
    "Wait a few seconds to skip it.": "Espera unos segundos para omitirlo.",
    "That was several buttons at once ({sources}). Press one button only.":
        "Fueron varios botones a la vez ({sources}). Presiona solo uno.",
    "{button}: skipped.": "{button}: omitido.",
    "{button} = {source}.": "{button} = {source}.",
    "{source} was {other}; that one has no button now.": "{source} era {other}; ese ya no tiene botón.",
    "Stopped.": "Detenido.",
    "{button}: cleared.": "{button}: borrado.",
    "Layout: {name}.": "Diseño: {name}.",
    "Pick a layout in the list first.": "Primero elige un diseño de la lista.",
    "Put {name} back to the default buttons? Your comments and other settings in "
    "controls.ini stay.":
        "¿Restablecer {name} a los botones predeterminados? Tus comentarios y otros ajustes en controls.ini se "
        "conservan.",
    "The part of the file that is for all {kind} controllers has button lines too. Reset "
    "those as well?":
        "La parte del archivo para todos los controles {kind} también tiene líneas de botones. ¿Restablecerlas "
        "también?",
    "Reset to the defaults. Save to keep it.": "Restablecido a los valores predeterminados. Guarda para conservarlo.",
    "{name} is {player}. Save to keep it.": "{name} es {player}. Guarda para conservarlo.",
    "controls.ini changed": "controls.ini cambió",
    "controls.ini was changed by something else since this screen opened. Overwrite it "
    "with your settings? (The old file is kept as controls.ini.bak.)":
        "Algo más cambió controls.ini desde que se abrió esta pantalla. ¿Sobrescribirlo con tus ajustes? (El archivo "
        "anterior se guarda como controls.ini.bak.)",
    "Could not save: {error}": "No se pudo guardar: {error}",
    "Saved {path}. The game reads it when it starts.": "Se guardó {path}. El juego lo lee al iniciar.",
    "The game that is running keeps its old buttons until you start it again.":
        "El juego en curso mantiene sus botones anteriores hasta que lo reinicies.",
    "Changes undone.": "Cambios descartados.",
    "There are unsaved changes. Save them first, or close with the mouse.":
        "Hay cambios sin guardar. Guárdalos primero, o cierra con el mouse.",
    "Controls": "Controles",
    "Save the changes to controls.ini?": "¿Guardar los cambios en controls.ini?",
    # ---- launcher/core.py
    "Auto (laptops, handhelds, integrated graphics)": "Auto (laptops, handhelds, gráficos integrados)",
    "On": "Activado",
    "a mobile processor": "un procesador móvil",
    "battery saver is on": "el ahorro de batería de Windows está activado",
    "the Power saver power plan is on": "el plan de energía “Economizador” está activo",
    "this PC has a battery (laptop or handheld)": "esta PC tiene batería (laptop o handheld)",
    "Inputs": "Inputs",
    "Inputs + frame data": "Inputs + datos de frames",
    "Auto (Windows language)": "Auto (idioma de Windows)",
    "No package chosen.": "No se eligió ningún paquete.",
    "File not found.": "Archivo no encontrado.",
    "Cannot read the file: {error}": "No se puede leer el archivo: {error}",
    "This is not a PS3 package (.pkg).": "Esto no es un paquete de PS3 (.pkg).",
    "{id}  ({size} bytes) -- the supported version": "{id}  ({size} bytes) -- la versión compatible",
    "{id}  ({size} bytes) -- Tekken 5 DR, but not the supported package ({supported}). "
    "The build will most likely refuse it.":
        "{id}  ({size} bytes) -- Tekken 5 DR, pero no el paquete compatible ({supported}). Lo más probable es que la "
        "compilación lo rechace.",
    "{id}  ({size} bytes) -- not Tekken 5 DR Online ({title_id}).":
        "{id}  ({size} bytes) -- no es Tekken 5 DR Online ({title_id}).",
    "No license chosen.": "No se eligió ninguna licencia.",
    "Not a PS3 license: a .rap file is exactly 16 bytes.":
        "No es una licencia de PS3: un archivo .rap tiene exactamente 16 bytes.",
    "{name} -- matches the supported package": "{name} -- coincide con el paquete compatible",
    "{name} -- matches the package": "{name} -- coincide con el paquete",
    "{name} -- the name does not match the package's content ID; it may be the wrong "
    "license.":
        "{name} -- el nombre no coincide con el content ID del paquete; puede ser la licencia equivocada.",
    "The output folder": "La carpeta de salida",
    "This folder": "Esta carpeta",
    "{label} has a long path ({bytes} bytes). Windows allows only {max} characters for a "
    "file path, and the build writes files about {room} characters deeper. Move the "
    "folder to a short path, for example {example}.":
        "{label} tiene una ruta larga ({bytes} bytes). Windows permite solo {max} caracteres en la ruta de un "
        "archivo, y la compilación escribe archivos unos {room} caracteres más adentro. Mueve la carpeta a una ruta "
        "corta, por ejemplo {example}.",
    "This folder is inside OneDrive. OneDrive would upload about 1 GB of game data and "
    "can lock files while the game is built. Move the folder out of OneDrive, for "
    "example to {example}.":
        "Esta carpeta está dentro de OneDrive. OneDrive subiría cerca de 1 GB de datos del juego y puede bloquear "
        "archivos mientras se compila el juego. Saca la carpeta de OneDrive, por ejemplo a {example}.",
    "This folder is in Program Files, where Windows does not let programs write. Move it "
    "to a folder of your own, for example {example}.":
        "Esta carpeta está en Program Files (Archivos de programa), donde Windows no deja escribir a los programas. "
        "Muévela a una carpeta tuya, por ejemplo {example}.",
    "Windows does not let the launcher write into this folder. Move it to a folder of "
    "your own, for example {example}.":
        "Windows no deja que el launcher escriba en esta carpeta. Muévela a una carpeta tuya, por ejemplo {example}.",
    "This folder is on a network share. Building and playing from there is slow and was "
    "not tested; copy it to a local drive.":
        "Esta carpeta está en una ubicación de red. Compilar y jugar desde ahí es lento y no se probó; cópiala a un "
        "disco local.",
    "The game is not built yet. Open the Build tab, choose your .pkg and .rap, press "
    "BUILD GAME.":
        "El juego aún no está compilado. Abre la pestaña Compilar, elige tu .pkg y .rap y presiona BUILD GAME.",
    "t5dr.exe is there but the game data is missing. Build again.":
        "t5dr.exe está, pero faltan los datos del juego. Compila de nuevo.",
    "The decrypted program has SHA-1 {sha}..., not the supported version. Build again "
    "from the supported package.":
        "El programa descifrado tiene SHA-1 {sha}..., no es la versión compatible. Compila de nuevo con el paquete "
        "compatible.",
    "Build the game once (about 2 minutes): this version of the launcher changes the "
    "game code. Click BUILD GAME. Your unpacked game and saves are kept; only the code "
    "is translated and compiled again.":
        "Compila el juego una vez (unos 2 minutos): esta versión del launcher cambia el código del juego. Haz clic "
        "en BUILD GAME. Tu juego desempaquetado y tus partidas guardadas se conservan; solo se traduce y compila el "
        "código de nuevo.",
    "Ready: {title_id} v{version}, program SHA-1 {sha}... verified, built {when}.":
        "Listo: {title_id} v{version}, SHA-1 del programa {sha}... verificado, compilado {when}.",
    "Check & decrypt": "Verificar y descifrar",
    "Key data": "Datos de claves",
    "Recompiler": "Recompilador",
    "Unpack": "Extraer",
    "Compile": "Compilar",
    "Game files": "Archivos del juego",
    "Sound core": "Núcleo de sonido",
    "Translate code": "Traducir código",
    "The translation step has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, close other programs, press Cancel and then BUILD GAME again; build.log "
    "has the details.":
        "El paso “Traducir código” no ha mostrado nada en {minutes} minutos. En una PC lenta u ocupada puede seguir "
        "trabajando. Si nada cambia, cierra otros programas, pulsa Cancelar y luego BUILD GAME otra vez; build.log "
        "tiene los detalles.",
    "The graphics card stopped working for the game (the driver crashed, was reset or "
    "updated). Start the game again. If it happens again, update the graphics driver.":
        "La tarjeta gráfica dejó de funcionar para el juego (el driver falló, se reinició o se actualizó). Inicia el "
        "juego de nuevo. Si vuelve a pasar, actualiza el driver de video.",
    "This PC's graphics card or driver cannot run Direct3D 12. Install the newest "
    "graphics driver from AMD, Intel or NVIDIA.":
        "La tarjeta gráfica o el driver de esta PC no puede ejecutar Direct3D 12. Instala el driver de video más "
        "reciente de AMD, Intel o NVIDIA.",
    "This processor is too old for the game: it lacks the SSE4.1 instructions "
    "(processors from about 2008 on have them).":
        "Este procesador es demasiado viejo para el juego: le faltan las instrucciones SSE4.1 (los procesadores "
        "desde 2008 aprox. las tienen).",
    "The game was built on a PC with a newer processor (AVX2). Press BUILD GAME to build "
    "it again for this PC; your saves are kept.":
        "El juego se compiló en una PC con un procesador más nuevo (AVX2). Presiona BUILD GAME para compilarlo de "
        "nuevo para esta PC; tus partidas guardadas se conservan.",
    "t5dr_game.dll could not be loaded (missing or blocked). Press BUILD GAME again, and "
    "look in the antivirus quarantine.":
        "No se pudo cargar t5dr_game.dll (falta o está bloqueado). Presiona BUILD GAME de nuevo y revisa la "
        "cuarentena del antivirus.",
    "The game could not get back to character select after the last match and closed "
    "itself. It starts again for your next match.":
        "El juego no pudo volver a la selección de personaje tras la última partida y se cerró solo. Se iniciará de "
        "nuevo para tu próxima partida.",
    "The game stopped after a crash (exit code {code}). The game log has the details.":
        "El juego se detuvo por un fallo (código de salida {code}). El log del juego tiene los detalles.",
    "The game stopped (exit code {code}). The game log has the details.":
        "El juego se detuvo (código de salida {code}). El log del juego tiene los detalles.",
    "t5dr.exe is not built yet": "t5dr.exe aún no está compilado",
    "Lowest (0.5x)": "Mínima (0.5x)",
    "Lower (0.75x)": "Baja (0.75x)",
    "Native (720p)": "Nativa (720p)",
    "1080p (1.5x)": "1080p (1.5x)",
    "1440p (2x)": "1440p (2x)",
    "4K (3x)": "4K (3x)",
    "The 3D scene at half size (a quarter of its pixels); HUD and text stay sharp. "
    "For integrated graphics and old laptops.":
        "La escena 3D a la mitad de tamaño (una cuarta parte de sus píxeles); el HUD y el texto siguen nítidos. Para "
        "gráficos integrados y laptops viejas.",
    "The 3D scene at 3/4 size (about half of its pixels); HUD and text stay sharp. "
    "For weak graphics cards.":
        "La escena 3D a 3/4 de tamaño (cerca de la mitad de sus píxeles); el HUD y el texto siguen nítidos. Para "
        "tarjetas gráficas débiles.",
    "The PS3's 1280 x 720. Light on any graphics card; the picture is scaled to your window.":
        "Los 1280 x 720 de la PS3. Ligero para cualquier tarjeta gráfica; la imagen se escala a tu ventana.",
    "1920 x 1080: 2.25x the pixels of Native. Sharp on Full HD screens. "
    "If fights drop below 60 fps, go one step down.":
        "1920 x 1080: 2.25x los píxeles de Nativa. Nítido en pantallas Full HD. Si las peleas bajan de 60 fps, baja "
        "un nivel.",
    "2560 x 1440: 4x the pixels of Native. For strong graphics cards. "
    "If fights drop below 60 fps, go one step down.":
        "2560 x 1440: 4x los píxeles de Nativa. Para tarjetas gráficas potentes. Si las peleas bajan de 60 fps, baja "
        "un nivel.",
    "3840 x 2160: 9x the pixels of Native. For very strong graphics cards "
    "(an RTX 3090 needs 1-2 ms of a 16.7 ms frame). If fights drop below 60 fps, go one step down.":
        "3840 x 2160: 9x los píxeles de Nativa. Para tarjetas gráficas muy potentes (una RTX 3090 necesita 1-2 ms de "
        "un frame de 16.7 ms). Si las peleas bajan de 60 fps, baja un nivel.",
    "Auto (by ping)": "Auto (según ping)",
    "Window, 1280 x 720 (native; larger with Windows display scaling)":
        "Ventana, 1280 x 720 (nativa; más grande con el escalado de Windows)",
    "Window, 1920 x 1080": "Ventana, 1920 x 1080",
    "Window, 2560 x 1440": "Ventana, 2560 x 1440",
    "Maximized window": "Ventana maximizada",
    "Borderless fullscreen (Alt+Enter or F11 switches in the game)":
        "Pantalla completa sin bordes (Alt+Enter o F11 cambia en el juego)",
    # ---- launcher/online.py
    "Online play": "Juego online",
    "The lobby files (lobby/t5lobby) are missing from this copy of the launcher, so "
    "online play is not available.\n\n({reason})":
        "Faltan los archivos del lobby (lobby/t5lobby) en esta copia del launcher, así que el juego online no está "
        "disponible.\n\n({reason})",
    # ---- launcher/problem_report_ui.py
    "Before the zip is made, your Windows user name in file paths becomes <user>, "
    "internet IP addresses become <ip> (addresses of your own network stay), lobby player "
    "names (yours and your opponents') become <player>, and passwords, tokens and match keys "
    "are left out. Your game files, keys, .pkg and .rap are never included. Nothing is "
    "uploaded: you send the zip yourself.":
        "Antes de crear el zip, tu nombre de usuario de Windows en las rutas se vuelve <user>, las direcciones IP de "
        "internet se vuelven <ip> (las de tu propia red se quedan), los nombres de jugadores del lobby (el tuyo y "
        "los de tus rivales) se vuelven <player>, y se omiten contraseñas, tokens y claves de partida. Tus archivos "
        "del juego, claves, .pkg y .rap nunca se incluyen. No se sube nada: tú mismo envías el zip.",
    "{count} bytes": "{count} bytes",
    "Report a problem": "Reportar un problema",
    "This makes one zip file on your Desktop with the logs and settings that help to "
    "find the problem. Send the zip to the person who gave you the game, or attach it to "
    "an issue.":
        "Esto crea un archivo zip en tu Escritorio con los logs y ajustes que ayudan a encontrar el problema. Envía "
        "el zip a la persona que te dio el juego, o adjúntalo a un issue.",
    "What happened? (optional)": "¿Qué pasó? (opcional)",
    "What goes into the zip": "Qué va en el zip",
    "Nothing found yet: no game log, no build log.": "Aún no se encontró nada: ni log del juego ni log de compilación.",
    "Could not look at the files: {error}": "No se pudieron revisar los archivos: {error}",
    "Save report on the Desktop": "Guardar el reporte en el Escritorio",
    "Cancel": "Cancelar",
    "About {size} before it is packed (a zip is smaller).": "Unos {size} antes de comprimir (el zip es más pequeño).",
    "About {size}; the limit is {limit}, so the biggest logs are shortened in the "
    "middle.":
        "Unos {size}; el límite es {limit}, así que los logs más grandes se acortan en el medio.",
    "Making the report...": "Creando el reporte...",
    "The report could not be made: {error}": "No se pudo crear el reporte: {error}",
    "Report saved": "Reporte guardado",
    "{size}. Its folder is open.": "{size}. Su carpeta está abierta.",
    "Send this zip to the person who gave you the game, or attach it to an issue at "
    "{url}.":
        "Envía este zip a la persona que te dio el juego, o adjúntalo a un issue en {url}.",
    "Send this zip to the person who gave you the game.": "Envía este zip a la persona que te dio el juego.",
    "(shortened in the middle)": "(acortado en el medio)",
    "{name}   left out: {reason}": "{name}   omitido: {reason}",
    "Removed from the text files: {user} user or PC names, {ip} IP addresses, {secret} "
    "passwords, tokens or keys, {email} e-mail addresses.":
        "Quitado de los archivos de texto: {user} nombres de usuario o de PC, {ip} direcciones IP, {secret} "
        "contraseñas, tokens o claves, {email} direcciones de e-mail.",
    "Open folder": "Abrir carpeta",
    # ---- launcher/t5dr_launcher.pyw
    "Discord": "Discord",
    "Show what I play in my Discord status (Rich Presence)":
        "Mostrar lo que juego en mi estado de Discord (Rich Presence)",
    "\"In lobby\", \"Searching ranked\" or your match (fighters, ranked set score) with a timer, through the "
    "Discord app on this PC. Without Discord running nothing happens.":
        "“En el lobby”, “Buscando Ranked” o tu partida (personajes, marcador del set Ranked) con un temporizador, a "
        "través de la app de Discord en esta PC. Sin Discord abierto no pasa nada.",
    "Power saving (laptops, handhelds)": "Ahorro de energía (laptops, handhelds)",
    "No busy waiting and fewer worker threads: the processor stays cooler and keeps its speed, so the game "
    "holds 60 fps longer. The game itself is the same, online too.":
        "Sin espera activa y con menos hilos de trabajo: el procesador se mantiene más fresco y conserva su "
        "velocidad, así el juego sostiene los 60 fps por más tiempo. El juego en sí es el mismo, también online.",
    "On for this PC.": "Activado en esta PC.",
    "Off.": "Desactivado.",
    "Auto: on for this PC -- {reason}.": "Auto: activado en esta PC -- {reason}.",
    "Auto: off for this PC (no battery, no mobile processor); the game turns it on by itself if it runs on "
    "integrated graphics.":
        "Auto: desactivado en esta PC (sin batería ni procesador móvil); el juego lo activa solo si corre con "
        "gráficos integrados.",
    "Power saving is on.": "El ahorro de energía está activado.",
    "A": "A",
    "Left punch (1)": "Puño izquierdo (1)",
    "Square": "Cuadrado",
    "X": "X",
    "Right punch (2)": "Puño derecho (2)",
    "S": "S",
    "Triangle": "Triángulo",
    "Y": "Y",
    "Cross": "X",
    "Left kick (3)": "Patada izquierda (3)",
    "Z": "Z",
    "B": "B",
    "Circle": "Círculo",
    "Right kick (4)": "Patada derecha (4)",
    "Arrow keys": "Flechas",
    "D-pad, left stick": "Cruceta, stick izquierdo",
    "Move / menus": "Mover / menús",
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
    "Quit the game": "Salir del juego",
    "A / B": "A / B",
    "Cross / Circle": "X / Círculo",
    "Mouse": "Mouse",
    "Online tab: accept / decline": "Pestaña Online: aceptar / rechazar",
    "native Windows build  ·  launcher {version}": "build nativa para Windows  ·  launcher {version}",
    "Build": "Compilar",
    "Play offline": "Jugar offline",
    "Settings": "Ajustes",
    "Play online": "Jugar online",
    "Output: {folder}": "Salida: {folder}",
    "Your game": "Tu juego",
    "Package (.pkg)": "Paquete (.pkg)",
    "License (.rap)": "Licencia (.rap)",
    "Browse…": "Examinar…",
    "Supported: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version "
    "01.00 -- the package file and the license (.rap) from your own account. Nothing "
    "leaves this PC.":
        "Compatible: Tekken 5: Dark Resurrection Online, PS3 PSN (EE. UU.), NPUB30009 versión 01.00 -- el archivo "
        "del paquete y la licencia (.rap) de tu propia cuenta. Nada sale de esta PC.",
    "Build tools on this PC": "Herramientas de compilación en esta PC",
    "Needed": "Necesario",
    "Found": "Encontrado",
    "Checking…": "Revisando…",
    "Details": "Detalles",
    "Check again": "Revisar de nuevo",
    "Install missing…": "Instalar lo que falta…",
    "Press BUILD GAME. It takes a few minutes; the game data stays in this folder.":
        "Presiona BUILD GAME. Tarda unos minutos; los datos del juego se quedan en esta carpeta.",
    "BUILD GAME": "BUILD GAME",
    "Redo every step": "Rehacer todos los pasos",
    "Keep the PC responsive (slower)": "Mantener la PC usable (más lento)",
    "Open build.log": "Abrir build.log",
    "Report a problem...": "Reportar un problema...",
    "Checking the build…": "Revisando la compilación…",
    "Your name (shown in the game)": "Tu nombre (se ve en el juego)",
    "PLAY OFFLINE": "JUGAR OFFLINE",
    "Arcade, Versus, Practice and the other modes on this PC. To play against people over the "
    "internet, use the":
        "Arcade, Versus, Practice y los demás modos en esta PC. Para jugar contra otros por internet, usa la",
    "Online tab": "pestaña Online",
    "Stop game": "Detener juego",
    "Open newest game log": "Abrir el log más reciente",
    "Open saves folder": "Abrir carpeta de partidas guardadas",
    "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers "
    "both work; see Settings for the keys. Esc closes the game. START skips the intro "
    "movie.":
        "El juego se abre en su propia ventana (DirectX 12). Funcionan el teclado y los controles tipo Xbox; las "
        "teclas están en Ajustes. Esc cierra el juego. START salta el video de introducción.",
    "Display": "Pantalla",
    "The picture is scaled to the window; how sharp it is depends on Internal resolution. "
    "You can also drag the window's edges. Alt+Enter or F11 switches borderless fullscreen "
    "in the game.":
        "La imagen se escala a la ventana; su nitidez depende de la Resolución interna. También puedes arrastrar los "
        "bordes de la ventana. Alt+Enter o F11 cambia a pantalla completa sin bordes en el juego.",
    "Unlocks": "Desbloqueos",
    "Unlock all stages (the Tekken 5 stages, without clearing Arcade)":
        "Desbloquear todos los escenarios (los de Tekken 5, sin completar Arcade)",
    "Unlock all customization items (free in the item shop)":
        "Desbloquear todos los ítems de personalización (gratis en la ITEM SHOP)",
    "Offline only (Arcade, VS, Practice and the rest). Your save is not changed; items you take for free "
    "stay yours (the save is backed up first, in save-backups). Online, both players always get the "
    "same stages and the default costumes.":
        "Solo offline (Arcade, VS, Practice y los demás). Tu partida guardada no cambia; los ítems que "
        "tomes gratis se quedan contigo (antes se hace una copia de la partida guardada, en save-backups). "
        "Online, ambos jugadores siempre tienen los mismos escenarios y los trajes predeterminados.",
    "Sound and start": "Sonido e inicio",
    "Mute sound": "Silenciar sonido",
    "Start minimized, without taking focus (for testing)": "Iniciar minimizado, sin tomar el foco (para pruebas)",
    "Advanced: extra settings, one NAME=VALUE per line": "Avanzado: ajustes extra, uno NOMBRE=VALOR por línea",
    "Internal resolution": "Resolución interna",
    "VSync": "VSync",
    "On (smooth, default)": "Activado (fluido, predeterminado)",
    "Off (lowest latency, may tear)": "Desactivado (menor latencia, puede haber tearing)",
    "The game always runs at 60 fps, like on the PS3.": "El juego siempre corre a 60 fps, como en la PS3.",
    "Stage blur / glow": "Desenfoque / brillo de escenarios",
    "On (default)": "Activado (predeterminado)",
    "Off": "Desactivado",
    "Some stages blur the picture (the misty swamp) or let the sun glow. Off shows them sharp, "
    "without the glow. Only your picture changes: online, both players can choose differently.":
        "Algunos escenarios desenfocan la imagen (el pantano con niebla) o hacen brillar el sol. Desactivado los "
        "muestra nítidos, sin el brillo. Solo cambia tu imagen: online, cada jugador puede elegir distinto.",
    "Training overlay": "Overlay de entrenamiento",
    "Also in the other offline modes (Arcade, Versus, ...)": "También en los demás modos offline (Arcade, Versus, ...)",
    "Also online (only your own inputs, no frame data)": "También online (solo tus inputs, sin datos de frames)",
    "In Practice: your last inputs with how many frames each was held, and after each exchange the "
    "startup of the move and who can act first (+3, -12). F2 in the game switches it.":
        "En Practice: tus últimos inputs con cuántos frames se mantuvo cada uno, y tras cada intercambio el startup "
        "del movimiento y quién puede actuar primero (+3, -12). F2 en el juego lo activa o desactiva.",
    "Your screen: {width} x {height}. In fullscreen, {step} matches it.":
        "Tu pantalla: {width} x {height}. En pantalla completa, {step} coincide con ella.",
    "Online input delay": "Input delay online",
    "Frames. Auto: 1 up to about 60 ms ping, 2 above. 0/1/2 count only when your "
    "opponent picked the same, otherwise Auto. Ranked matches always use 2.":
        "Frames. Auto: 1 hasta unos 60 ms de ping, 2 por encima. 0/1/2 solo cuentan si tu rival eligió lo mismo; si "
        "no, Auto. Las partidas Ranked siempre usan 2.",
    "Open the game's port on my router during online matches (UPnP / NAT-PMP / PCP)":
        "Abrir el puerto del juego en mi router durante partidas online (UPnP / NAT-PMP / PCP)",
    "Helps the direct connection when your opponent's router is strict. The port is open only while "
    "you play and is closed again afterwards.":
        "Ayuda a la conexión directa cuando el router de tu rival es estricto. El puerto solo está abierto mientras "
        "juegas y se cierra después.",
    "Set up controllers…": "Configurar controles…",
    "Pick a pad, stick or hitbox, press the buttons you want for 1 2 3 4 and the rest, "
    "or start from a layout.":
        "Elige un control, stick o hitbox, presiona los botones que quieras para 1 2 3 4 y el resto, o empieza desde "
        "un diseño.",
    "(needs the lobby files, which are missing)": "(necesita los archivos del lobby, que faltan)",
    "Action (Tekken default)": "Acción (por defecto de Tekken)",
    "PS3 button": "Botón de PS3",
    "Keyboard": "Teclado",
    "Xbox controller": "Control Xbox",
    "Keyboard and the first XInput controller both drive player 1 (they are combined). "
    "The keyboard only counts while the game window has focus. The game's own Options menu can change "
    "the button layout for offline play; online games use the launcher's buttons only.":
        "El teclado y el primer control XInput manejan al jugador 1 (se combinan). El teclado solo cuenta mientras "
        "la ventana del juego tiene el foco. El menú Options del propio juego puede cambiar la asignación de "
        "botones para jugar offline; las partidas online solo usan los botones del launcher.",
    "In this window, on the Online tab, a controller or arcade stick works without mouse "
    "or keyboard: Cross / A accepts a match or rematch and starts a search, Circle / B "
    "declines, leaves or stops the search. It only counts while this window is in front, "
    "and only after the button was let go for a moment. Which stick button is Cross "
    "follows your controls.ini.":
        "En esta ventana, en la pestaña Online, un control o stick arcade funciona sin mouse ni teclado: X / A "
        "acepta una partida o Rematch e inicia una búsqueda, Círculo / B rechaza, sale o detiene la búsqueda. Solo "
        "cuenta mientras esta ventana está al frente, y solo después de soltar el botón un momento. Qué botón del "
        "stick es X depende de tu controls.ini.",
    "Language": "Idioma",
    "Restart now": "Reiniciar ahora",
    "The language changes when the launcher starts again.": "El idioma cambia cuando el launcher se reinicia.",
    "A build is running. Stop it first, or restart the launcher by hand when it is done.":
        "Hay una compilación en curso. Detenla primero, o reinicia el launcher a mano cuando termine.",
    "Close the game first.": "Cierra el juego primero.",
    "Choose your Tekken 5 DR Online package": "Elige tu paquete de Tekken 5 DR Online",
    "All files": "Todos los archivos",
    "PS3 package": "Paquete de PS3",
    "Choose your license (.rap)": "Elige tu licencia (.rap)",
    "PS3 license": "Licencia de PS3",
    "Checking build tools…": "Revisando herramientas de compilación…",
    "missing": "falta",
    "ok": "ok",
    "Missing: {names}": "Falta: {names}",
    "Everything the build needs is installed.": "Todo lo que necesita la compilación está instalado.",
    "All build tools found.": "Se encontraron todas las herramientas de compilación.",
    "{count} build tool(s) missing -- click 'Install missing…'.":
        "Faltan {count} herramienta(s) de compilación -- haz clic en “Instalar lo que falta…”.",
    "Hide details": "Ocultar detalles",
    "Microsoft Visual Studio 2022 Build Tools: the C++ compiler parts only (MSVC x64, "
    "Windows SDK, CMake, Clang). Download about 2.5 GB, about 7 GB on disk, 10-20 "
    "minutes. You accept Microsoft's license terms for the Build Tools "
    "(visualstudio.microsoft.com/license-terms).":
        "Microsoft Visual Studio 2022 Build Tools: solo las partes del compilador de C++ (MSVC x64, Windows SDK, "
        "CMake, Clang). Descarga de unos 2.5 GB, unos 7 GB en disco, 10-20 minutos. Aceptas los términos de licencia "
        "de Microsoft para las Build Tools (visualstudio.microsoft.com/license-terms).",
    "Git for Windows (about 70 MB download).": "Git for Windows (descarga de unos 70 MB).",
    "Install build tools": "Instalar herramientas de compilación",
    "The build needs these free tools from their makers, installed with Windows' own "
    "installer (winget):\n\n{tools}\n\nWindows will ask for administrator permission. A "
    "console window shows the progress.\n\nInstall now?":
        "La compilación necesita estas herramientas gratuitas de sus fabricantes, instaladas con el instalador "
        "propio de Windows (winget):\n\n{tools}\n\nWindows pedirá permiso de administrador. Una ventana de consola "
        "muestra el progreso.\n\n¿Instalar ahora?",
    "Could not start the installer:\n{error}\n\nIs winget (App Installer) available? On "
    "Windows 10 install 'App Installer' from the Microsoft Store.":
        "No se pudo iniciar el instalador:\n{error}\n\n¿Está disponible winget (Instalador de aplicación)? En "
        "Windows 10 instala “Instalador de aplicación” desde Microsoft Store.",
    "Install failed": "Falló la instalación",
    "Installer running in its own window…": "El instalador se ejecuta en su propia ventana…",
    "Could not start the build: {error}": "No se pudo iniciar la compilación: {error}",
    "Building…": "Compilando…",
    "Step {n} of {total}: {title}  —  {elapsed}": "Paso {n} de {total}: {title}  —  {elapsed}",
    "Done in {elapsed}. Open the Play tab.": "Listo en {elapsed}. Abre la pestaña Jugar offline.",
    "Build finished.": "Compilación terminada.",
    "Cancelled. BUILD GAME continues where it stopped.": "Cancelado. BUILD GAME continúa donde se detuvo.",
    "The build stopped. The message below says why; build.log has the details.":
        "La compilación se detuvo. El mensaje de abajo dice por qué; build.log tiene los detalles.",
    "The build failed. See the log above and build.log.": "La compilación falló. Mira el log de arriba y build.log.",
    "Build stopped.": "Compilación detenida.",
    "Could not start the game:\n{error}": "No se pudo iniciar el juego:\n{error}",
    "Game started (process {pid}). Log: {log}": "Juego iniciado (proceso {pid}). Log: {log}",
    "starting…": "iniciando…",
    "Running — {elapsed} — {fps}": "En ejecución — {elapsed} — {fps}",
    "Click Report a problem.": "Haz clic en “Reportar un problema...”.",
    "The game closed.": "El juego se cerró.",
    "A build is running. Stop it and quit?": "Hay una compilación en curso. ¿Detenerla y salir?",
    # ---- launcher/updater.py
    "Check for updates": "Buscar actualizaciones",
    "Updated from {old} to {new}.": "Actualizado de {old} a {new}.",
    "the new version": "la nueva versión",
    "The update to {version} failed and could not be undone completely: {error}.\n\nThe "
    "old program files are in\n{folder}\nYour game, saves and settings (the native "
    "folder) were not touched. Download the zip from the releases page and extract it "
    "over this folder.":
        "La actualización a {version} falló y no se pudo deshacer por completo: {error}.\n\nLos archivos anteriores "
        "del programa están en\n{folder}\nTu juego, partidas guardadas y ajustes (la carpeta native) no se tocaron. "
        "Descarga el zip desde la página de releases y extráelo sobre esta carpeta.",
    "The update to {version} did not work: {error}.\n\nNothing was changed; this is "
    "still version {current}. Try again later, or download the zip from the releases "
    "page.":
        "La actualización a {version} no funcionó: {error}.\n\nNo se cambió nada; sigue siendo la versión {current}. "
        "Inténtalo más tarde, o descarga el zip desde la página de releases.",
    "Update": "Actualización",
    "Updates": "Actualizaciones",
    "This is a development checkout (no release.json and bundled Python), so it does not "
    "update itself. Use git, or a release zip from\n{page}":
        "Esta es una copia de desarrollo (sin release.json ni Python incluido), así que no se actualiza sola. Usa "
        "git, o un zip de release desde\n{page}",
    "Update to {version}…": "Actualizar a {version}…",
    "Could not check for updates.\n\n{problem}": "No se pudieron buscar actualizaciones.\n\n{problem}",
    "Version {version} is available: click 'Update to {version}' at the top.":
        "La versión {version} está disponible: haz clic arriba en “Actualizar a {version}”.",
    "You have the newest version ({version}).": "Tienes la versión más reciente ({version}).",
    "Update available": "Actualización disponible",
    "T5DR Online {version} is available": "T5DR Online {version} está disponible",
    "Download: {size}, published {date}.": "Descarga: {size}, publicada el {date}.",
    "Download: {size}.": "Descarga: {size}.",
    "You have {version}.": "Tienes la {version}.",
    "The launcher downloads it, checks it, replaces its program files and starts again. "
    "Your game, saves and settings (the native folder) stay as they are.":
        "El launcher la descarga, la verifica, reemplaza sus archivos y se reinicia. Tu juego, partidas guardadas y "
        "ajustes (la carpeta native) se quedan como están.",
    "After this update the game is built once more (about 2 minutes): the Play tab "
    "offers BUILD GAME. Only the code is rebuilt; the unpacked game and saves are kept.":
        "Después de esta actualización, el juego se compila una vez más (unos 2 minutos): la pestaña Jugar offline "
        "ofrece BUILD GAME. Solo se recompila el código; el juego desempaquetado y las partidas guardadas se "
        "conservan.",
    "The game itself does not need to be built again.": "El juego en sí no necesita compilarse de nuevo.",
    "If this update changes the game code, the Play tab asks you to build the game once "
    "(about 2 minutes).":
        "Si esta actualización cambia el código del juego, la pestaña Jugar offline te pedirá compilarlo una vez "
        "(unos 2 minutos).",
    "(no release notes)": "(sin notas de la versión)",
    "Update now": "Actualizar ahora",
    "Later": "Más tarde",
    "Release page": "Página de la versión",
    "Cancelling…": "Cancelando…",
    "Downloading…": "Descargando…",
    "Unexpected error: {error}": "Error inesperado: {error}",
    "Downloading… {done} of {total}": "Descargando… {done} de {total}",
    "Downloading… {done}": "Descargando… {done}",
    "Checking the download (SHA-256)…": "Verificando la descarga (SHA-256)…",
    "Unpacking… {percent}%": "Descomprimiendo… {percent}%",
    "Preparing the restart…": "Preparando el reinicio…",
    "Try again": "Reintentar",
    "Could not start the update step: {error}": "No se pudo iniciar el paso de actualización: {error}",
    "Installing {version}: the launcher restarts in a few seconds…":
        "Instalando {version}: el launcher se reinicia en unos segundos…",
    "Updating to {version}…": "Actualizando a {version}…",
    # ---- lobby/t5lobby/client.py
    "Contacting the lobby server over UDP...": "Contactando al servidor del lobby por UDP...",
    "UDP to the lobby server is blocked (firewall?)": "El UDP al servidor del lobby está bloqueado (¿firewall?)",
    "Connecting to your opponent...": "Conectando con tu rival...",
    "Measuring the connection...": "Midiendo la conexión...",
    "Direct connection not possible; using the lobby server's relay...":
        "No es posible una conexión directa; usando el relay del servidor del lobby...",
    "Direct connection found: the match no longer goes through the lobby server.":
        "Conexión directa encontrada: la partida ya no pasa por el servidor del lobby.",
    "The direct connection was lost; back on the lobby server's relay.":
        "Se perdió la conexión directa; de vuelta en el relay del servidor del lobby.",
    "Direct connection not possible; using the relay server {name}...":
        "No es posible una conexión directa; usando el servidor relay {name}...",
    "Direct connection found: the match no longer goes through the relay server {name}.":
        "Conexión directa encontrada: la partida ya no pasa por el servidor relay {name}.",
    "The direct connection was lost; back on the relay server {name}.":
        "Se perdió la conexión directa; de vuelta en el servidor relay {name}.",
    # ---- lobby/t5lobby/dialogs.py
    "No": "No",
    "Yes": "Sí",
    "OK": "OK",
    # ---- lobby/t5lobby/fighters.py
    "Random": "Aleatorio",
    # ---- lobby/t5lobby/handover.py
    "direct connection": "conexión directa",
    "local network": "red local",
    "through the lobby server": "a través del servidor del lobby",
    "through the relay server {name}": "a través del servidor relay {name}",
    "{name} -- {how}, ping {ms} ms, input delay {delay}": "{name} -- {how}, ping {ms} ms, input delay {delay}",
    # ---- lobby/t5lobby/i18n_known.py
    "login timeout": "tiempo de inicio de sesión agotado",
    "idle timeout": "tiempo agotado por inactividad",
    "banned from this server": "baneado de este servidor",
    "too many connections": "demasiadas conexiones",
    "server full": "servidor lleno",
    "slow down": "más despacio",
    "bad request": "solicitud no válida",
    "the server is busy; try again in a few seconds": "el servidor está ocupado; inténtalo de nuevo en unos segundos",
    "the chat is busy; try again in a moment": "el chat está ocupado; inténtalo de nuevo en un momento",
    "that name looks too much like the account {other}": "ese nombre se parece demasiado a la cuenta {other}",
    "that name looks too much like {name}, who is online":
        "ese nombre se parece demasiado a {name}, que está conectado",
    "flooding: disconnected": "spam de mensajes: desconectado",
    "this server speaks lobby protocol {version}; update the launcher":
        "este servidor usa el protocolo de lobby {version}; actualiza el launcher",
    "build {build} is not accepted by this server; update the launcher and rebuild the "
    "game":
        "este servidor no acepta la build {build}; actualiza el launcher y recompila el juego",
    "already logged in": "ya iniciaste sesión",
    "this server has no accounts": "este servidor no tiene cuentas",
    "this server has no guest logins": "este servidor no permite invitados",
    "too many failed logins; wait a few minutes": "demasiados inicios de sesión fallidos; espera unos minutos",
    "too many failed attempts; wait a few minutes": "demasiados intentos fallidos; espera unos minutos",
    "too many password changes; wait a minute": "demasiados cambios de contraseña; espera un minuto",
    "too many requests for new codes; wait a minute": "demasiadas solicitudes de códigos nuevos; espera un minuto",
    "too many new accounts from this address": "demasiadas cuentas nuevas desde esta dirección",
    "the saved login has expired; log in with your password":
        "el inicio de sesión guardado expiró; entra con tu contraseña",
    "session expired; log in again": "la sesión expiró; vuelve a iniciar sesión",
    "names are 2-16 letters, digits, spaces or _-.[]()!?":
        "los nombres tienen 2-16 caracteres: letras, números, espacios o _-.[]()!?",
    "that name is reserved": "ese nombre está reservado",
    "that name is not allowed here": "ese nombre no está permitido aquí",
    "that name belongs to an account": "ese nombre pertenece a una cuenta",
    "that name is taken": "ese nombre ya está en uso",
    "someone with that name is online": "alguien con ese nombre está conectado",
    "wrong name or password": "nombre o contraseña incorrectos",
    "wrong password": "contraseña incorrecta",
    "the current password is wrong": "la contraseña actual es incorrecta",
    "passwords are 6-128 characters": "las contraseñas tienen 6-128 caracteres",
    "guests have no password": "los invitados no tienen contraseña",
    "guests have no account": "los invitados no tienen cuenta",
    "wrong name or recovery code (each code works once)":
        "nombre o código de recuperación incorrectos (cada código sirve una vez)",
    "logged in from another place": "se inició sesión desde otro lugar",
    "this account is banned for good": "esta cuenta está baneada para siempre",
    "this account is banned for good: {reason}": "esta cuenta está baneada para siempre: {reason}",
    "this account is banned until {time}": "esta cuenta está baneada hasta {time}",
    "this account is banned until {time}: {reason}": "esta cuenta está baneada hasta {time}: {reason}",
    "you are {status}": "no se puede ahora (estado: {status})",
    "ranked needs an account": "Ranked necesita una cuenta",
    "ranked matches come from the ranked queue on this server":
        "en este servidor, las partidas Ranked salen de la búsqueda Ranked",
    "your character is locked until this ranked set ends":
        "tu personaje está bloqueado hasta que termine este set Ranked",
    "the ranked set goes on by itself": "el set Ranked continúa solo",
    "you are in a ranked set ({mine}-{theirs}); leave it first (that counts as a loss)":
        "estás en un set Ranked ({mine}-{theirs}); sal primero (cuenta como derrota)",
    "that player is in a ranked set": "ese jugador está en un set Ranked",
    "you are not in a ranked set": "no estás en un set Ranked",
    "finish your running match with the same game build first":
        "primero termina tu partida en curso con la misma build del juego",
    "this PC ran its last match at {fps} fps; ranked needs at least {min_fps} (both "
    "games run at the slower PC's speed). Close other programs or lower the resolution "
    "scale, then play a casual match to measure again":
        "esta PC jugó su última partida a {fps} fps; Ranked necesita al menos {min_fps} (ambos juegos corren a la "
        "velocidad de la PC más lenta). Cierra otros programas o baja la resolución interna, y luego juega una "
        "partida casual para medir de nuevo",
    "chat: slow down": "chat: más despacio",
    "history is kept for accounts only": "el historial solo se guarda para cuentas",
    "no such player": "ese jugador no existe",
    "no such room": "esa sala no existe",
    "room is full": "la sala está llena",
    "you cannot join this room": "no puedes entrar a esta sala",
    "not in a room": "no estás en una sala",
    "no opponent in the room": "no hay rival en la sala",
    "that player runs a different build of the game": "ese jugador tiene otra build del juego",
    "finish the match first": "primero termina la partida",
    "finish or leave the running match first": "primero termina o sal de la partida en curso",
    "that match is over; find a new opponent": "esa partida terminó; busca un nuevo rival",
    "your opponent is no longer available": "tu rival ya no está disponible",
    "that player is not available": "ese jugador no está disponible",
    "busy": "ocupado",
    "one challenge at a time": "un desafío a la vez",
    "that player has challenges pending": "ese jugador tiene desafíos pendientes",
    "no such challenge": "ese desafío no existe",
    "challenge no longer possible": "el desafío ya no es posible",
    "no such match": "esa partida no existe",
    "match is {state}": "estado de la partida: {state}",
    "you cannot block yourself": "no puedes bloquearte a ti mismo",
    "the block list is full ({max})": "la lista de bloqueo está llena ({max})",
    "that player is not on your block list": "ese jugador no está en tu lista de bloqueo",
    "you are not in a set": "no estás en un set",
    "no such finished match": "esa partida terminada no existe",
    "guests cannot have friends; create an account (free)":
        "los invitados no pueden tener amigos; crea una cuenta (gratis)",
    "there is no account with that name": "no hay ninguna cuenta con ese nombre",
    "you cannot add yourself": "no puedes agregarte a ti mismo",
    "you blocked that player; unblock them first": "bloqueaste a ese jugador; desbloquéalo primero",
    "your friends list is full ({max})": "tu lista de amigos está llena ({max})",
    "your last invite to that friend ended a moment ago; try again in {seconds} s":
        "tu última invitación a ese amigo acaba de terminar; inténtalo de nuevo en {seconds} s",
    "your last challenge to that player ended a moment ago; try again in {seconds} s":
        "tu último desafío a ese jugador acaba de terminar; inténtalo de nuevo en {seconds} s",
    "too many friend requests from this internet address today; try again tomorrow":
        "demasiadas solicitudes de amistad desde esta dirección de internet hoy; inténtalo mañana",
    "you can send {count} friend requests a day; try again tomorrow":
        "puedes enviar {count} solicitudes de amistad al día; inténtalo mañana",
    "{count} of your friend requests are waiting for an answer; cancel some first":
        "{count} de tus solicitudes de amistad esperan respuesta; retira algunas primero",
    "{name} declined your last request; you can ask again in {days} day(s)":
        "{name} rechazó tu última solicitud; puedes volver a pedirlo en {days} día(s)",
    "that player has too many friend requests waiting":
        "ese jugador tiene demasiadas solicitudes de amistad pendientes",
    "that player's friends list is full": "la lista de amigos de ese jugador está llena",
    "no friend request from that player": "no hay solicitud de amistad de ese jugador",
    "no friend request to that player": "no hay solicitud de amistad para ese jugador",
    "that player is not on your friends list": "ese jugador no está en tu lista de amigos",
    "that friend is not online": "ese amigo no está conectado",
    "that friend's launcher is too old for invites (it needs 1.1.2 or newer)":
        "el launcher de ese amigo es demasiado viejo para invitaciones (necesita 1.1.2 o más nuevo)",
    "create a room first, then invite": "primero crea una sala y luego invita",
    "that friend is busy right now": "ese amigo está ocupado ahora",
    "one invite at a time": "una invitación a la vez",
    "wait a moment before inviting again": "espera un momento antes de volver a invitar",
    "that player has invites pending": "ese jugador tiene invitaciones pendientes",
    "that invite is over": "esa invitación terminó",
    "the invite is no longer possible": "la invitación ya no es posible",
    "{name} is back in the lobby": "{name} volvió al lobby",
    "{name} lost the lobby connection; waiting {seconds} s for them to return":
        "{name} perdió la conexión con el lobby; esperando {seconds} s a que vuelva",
    "your PC ran its last match at {fps} fps": "tu PC jugó su última partida a {fps} fps",
    "your opponent's PC ran its last match at {fps} fps": "la PC de tu rival jugó su última partida a {fps} fps",
    "{name}'s PC ran its last match at {fps} fps": "la PC de {name} jugó su última partida a {fps} fps",
    "{parts} -- this match runs at the slower PC's speed":
        "{parts} -- esta partida corre a la velocidad de la PC más lenta",
    "you two played {count} ranked matches in the last 24 hours; this one is unranked "
    "(limit {max})":
        "ustedes dos jugaron {count} partidas Ranked en las últimas 24 horas; esta no cuenta para Ranked (límite "
        "{max})",
    "your PC's UDP packets did not reach the lobby server; check the firewall":
        "los paquetes UDP de tu PC no llegaron al servidor del lobby; revisa el firewall",
    "your opponent reported the result; please report yours":
        "tu rival reportó el resultado; por favor reporta el tuyo",
    "opponent runs a different build": "el rival tiene otra build",
    "not connected to the lobby": "no conectado al lobby",
    "the lobby server did not answer": "el servidor del lobby no respondió",
    "no answer to {type}": "sin respuesta a {type}",
    "cannot reach {host}:{port} ({error})": "no se puede llegar a {host}:{port} ({error})",
    "the server's certificate does not match the pinned one": "el certificado del servidor no coincide con el guardado",
    "this server has no encryption (TLS): a password would cross the internet readable. "
    "Play as a guest, or ask the server's host to set up TLS and give you its "
    "fingerprint.":
        "este servidor no tiene cifrado (TLS): una contraseña viajaría legible por internet. Juega como invitado, o "
        "pide a quien aloja el servidor que configure TLS y te dé su huella digital.",
    "connection closed": "conexión cerrada",
    "the server sent a malformed match id": "el servidor envió un ID de partida mal formado",
    "message too long": "mensaje demasiado largo",
    "closed": "cerrada",
    "Choose your game package (.pkg) first.": "Primero elige tu paquete del juego (.pkg).",
    "The package file does not exist: {file}": "El archivo del paquete no existe: {file}",
    "{file} is not a PS3 package (.pkg).": "{file} no es un paquete de PS3 (.pkg).",
    "Choose your license file (.rap) first.": "Primero elige tu archivo de licencia (.rap).",
    "{file} is not a PS3 license: a .rap file is exactly 16 bytes.":
        "{file} no es una licencia de PS3: un archivo .rap tiene exactamente 16 bytes.",
    "This package has no USRDIR/EBOOT.BIN -- it is not a game package (an add-on or "
    "theme?). The port needs {game}.":
        "Este paquete no tiene USRDIR/EBOOT.BIN -- no es un paquete de juego (¿un add-on o tema?). El port necesita "
        "{game}.",
    "This package is \"{title}\" ({id}). The port needs {game}.":
        "Este paquete es “{title}” ({id}). El port necesita {game}.",
    "This copy is a different version of the game: \"{title}\" version {version}, content "
    "ID {id} (program SHA-1 {sha}...). The port supports only {game}, content ID "
    "{supported}.":
        "Esta copia es otra versión del juego: “{title}” versión {version}, content ID {id} (SHA-1 del programa "
        "{sha}...). El port solo admite {game}, content ID {supported}.",
    "The license (.rap) does not belong to this package. Use the .rap whose name matches "
    "the package's content ID ({id}).":
        "La licencia (.rap) no pertenece a este paquete. Usa el .rap cuyo nombre coincide con el content ID del "
        "paquete ({id}).",
    "Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press BUILD GAME "
    "again; if it fails again, check that the package is {size} bytes.":
        "Falló el descifrado del programa del juego (ver el log arriba). Marca “Rehacer todos los pasos” y presiona "
        "BUILD GAME de nuevo; si vuelve a fallar, revisa que el paquete tenga {size} bytes.",
    "The package is {size} bytes, the supported one is {supported} bytes: the download is incomplete or it is "
    "a different file. Download it again.":
        "El paquete tiene {size} bytes y el compatible tiene {supported} bytes: la descarga está incompleta o es "
        "otro archivo. Descárgalo de nuevo.",
    "The ps3recomp copy in this folder does not match this version of the port. Download "
    "the release again and extract it into an empty folder.":
        "La copia de ps3recomp en esta carpeta no coincide con esta versión del port. Descarga el release de nuevo y "
        "extráelo en una carpeta vacía.",
    "Git is needed to download ps3recomp (the recompiler). Install Git, or use a release "
    "zip, which already contains it.":
        "Se necesita Git para descargar ps3recomp (el recompilador). Instala Git, o usa un zip de release, que ya lo "
        "incluye.",
    "This package's Python is missing pycryptodome. Download the release again.":
        "Al Python de este paquete le falta pycryptodome. Descarga el release de nuevo.",
    "Could not download the public PS3 key data from github.com (needed once, a few KB). "
    "Check the internet connection and press BUILD GAME again.":
        "No se pudieron descargar los datos públicos de claves de PS3 desde github.com (se necesitan una vez, unos "
        "KB). Revisa la conexión a internet y presiona BUILD GAME de nuevo.",
    "The C++ build tools (Visual Studio 2022 Build Tools, x64 C++ toolset) are not "
    "installed. Open the launcher's Build tab and click Install next to them.":
        "Las herramientas de compilación de C++ (Visual Studio 2022 Build Tools, conjunto de herramientas C++ x64) "
        "no están instaladas. Abre la pestaña Compilar del launcher y haz clic en “Instalar lo que falta…”.",
    "clang-cl.exe and lld-link.exe were not found in toolchain\\llvm\\bin. Download the "
    "release again.":
        "No se encontraron clang-cl.exe y lld-link.exe en toolchain\\llvm\\bin. Descarga el release de nuevo.",
    "The Windows SDK is missing (needed for Direct3D 12). Install it with the C++ build "
    "tools.":
        "Falta el Windows SDK (necesario para Direct3D 12). Instálalo con las herramientas de compilación de C++.",
    "clang-cl (LLVM 16 or newer) was not found. Install LLVM or the Visual Studio "
    "component 'C++ Clang tools for Windows'.":
        "No se encontró clang-cl (LLVM 16 o más nuevo). Instala LLVM o el componente de Visual Studio “C++ Clang "
        "tools for Windows”.",
    "CMake and Ninja were not found. Install the Visual Studio component 'C++ CMake "
    "tools for Windows'.":
        "No se encontraron CMake y Ninja. Instala el componente de Visual Studio “C++ CMake tools for Windows”.",
    "expected 1 SPU image, found {count}": "se esperaba 1 imagen SPU, se encontraron {count}",
    "step '{step}' failed: a tool exited with code {code} -- the lines above say why.":
        "el paso “{step}” falló: una herramienta terminó con código {code} -- las líneas de arriba dicen por qué.",
    "cancelled": "cancelado",
    "step '{step}' could not read or write a file: {reason} ({file}). The folder path is "
    "too long for Windows: move the folder to a short path such as C:\\Games\\T5DR.":
        "el paso “{step}” no pudo leer o escribir un archivo: {reason} ({file}). La ruta de la carpeta es demasiado "
        "larga para Windows: mueve la carpeta a una ruta corta como C:\\Games\\T5DR.",
    "step '{step}' could not read or write a file: {reason} ({file}). Is the disk full, "
    "or does another program (antivirus, OneDrive) hold the file?":
        "el paso “{step}” no pudo leer o escribir un archivo: {reason} ({file}). ¿El disco está lleno, o algún otro "
        "programa (antivirus, OneDrive) tiene el archivo abierto?",
    "Python 3.10+": "Python 3.10+",
    "pycryptodome (Python AES)": "pycryptodome (Python AES)",
    "ps3recomp source": "código fuente de ps3recomp",
    "Game runtime (t5dr.exe)": "Runtime del juego (t5dr.exe)",
    "clang-cl + lld-link": "clang-cl + lld-link",
    "C++ build tools (MSVC x64)": "Herramientas de compilación C++ (MSVC x64)",
    "Windows SDK (Direct3D 12)": "Windows SDK (Direct3D 12)",
    "clang-cl 16+ (LLVM)": "clang-cl 16+ (LLVM)",
    "CMake + Ninja": "CMake + Ninja",
    "{version} at {path}": "{version} en {path}",
    "installed": "instalado",
    "missing -- pip install pycryptodome": "falta -- pip install pycryptodome",
    "included in this package": "incluido en este paquete",
    "git checkout in deps/": "checkout de git en deps/",
    "not present -- will be downloaded with Git": "no está -- se descargará con Git",
    "not present and Git is missing": "no está y falta Git",
    "precompiled, included in this package": "precompilado, incluido en este paquete",
    "missing from toolchain\\llvm -- download the release again":
        "falta en toolchain\\llvm -- descarga el release de nuevo",
    "not found": "no encontrado",
    "missing {tools}": "falta: {tools}",
    "System information and the settings you use": "Información del sistema y los ajustes que usas",
    "What happened (what you wrote)": "Qué pasó (lo que escribiste)",
    "Launcher log": "Log del launcher",
    "Game log (the newest one)": "Log del juego (el más reciente)",
    "Game log (the newest {count})": "Logs del juego (los {count} más recientes)",
    "Build log": "Log de compilación",
    "Build log (the last build went fine)": "Log de compilación (la última compilación salió bien)",
    "Online: the files of the last match": "Online: los archivos de la última partida",
    "controls.ini (your button settings)": "controls.ini (tu configuración de botones)",
    "Desync dumps (game state numbers, binary)": "Volcados de desync (números del estado del juego, binario)",
    "The last replay (the inputs of the last online session, without names)":
        "El último replay (las entradas de la última sesión online, sin nombres)",
    "could not be cleaned of private data": "no se pudo limpiar de datos privados",
    "no room left in the size limit": "no queda espacio en el límite de tamaño",
    "could not be read": "no se pudo leer",
    "The launcher cannot write next to its folder or into it, so it cannot update "
    "itself. Download the zip from the releases page instead.":
        "El launcher no puede escribir junto a su carpeta ni dentro de ella, así que no puede actualizarse solo. "
        "Descarga el zip desde la página de releases.",
    "Refused to download from {host}: not this project's GitHub releases.":
        "Descarga desde {host} rechazada: no son los releases de GitHub de este proyecto.",
    "The download came from {host}. Nothing was changed.": "La descarga vino de {host}. No se cambió nada.",
    "GitHub did not return a published release.": "GitHub no devolvió un release publicado.",
    "The latest release has an unexpected version ({tag}).":
        "El release más reciente tiene una versión inesperada ({tag}).",
    "Release {version} has no {name} with SHA256SUMS yet.": "El release {version} aún no tiene {name} con SHA256SUMS.",
    "The downloaded release does not say it is version {version}. Nothing was changed.":
        "El release descargado no dice que sea la versión {version}. No se cambió nada.",
    "The downloaded release has no launcher. Nothing was changed.":
        "El release descargado no tiene launcher. No se cambió nada.",
    "This folder has no python\\pythonw.exe, so the launcher cannot update itself (a "
    "development checkout?). Download the zip from the releases page instead.":
        "Esta carpeta no tiene python\\pythonw.exe, así que el launcher no puede actualizarse solo (¿una copia de "
        "desarrollo?). Descarga el zip desde la página de releases.",
    "The download was sent to {host}, which is not GitHub's storage for this project. "
    "Nothing was changed.":
        "La descarga se envió a {host}, que no es el almacenamiento de GitHub de este proyecto. No se cambió nada.",
    "Release {version}: {name} is not on this project's GitHub releases.":
        "Release {version}: {name} no está en los releases de GitHub de este proyecto.",
    "Release {version}: {name} is still being uploaded.": "Release {version}: {name} todavía se está subiendo.",
    "The download stopped early ({done} of {total} bytes). Try again.":
        "La descarga se detuvo antes de tiempo ({done} de {total} bytes). Inténtalo de nuevo.",
    "The download is not a readable zip ({error}). Nothing was changed.":
        "La descarga no es un zip legible ({error}). No se cambió nada.",
    "The download unpacks to far more than a release should. Nothing was changed.":
        "La descarga se descomprime en mucho más de lo que debería un release. No se cambió nada.",
    "Not enough free disk space: the update needs about {need} MB next to the folder, "
    "{free} MB are free.":
        "No hay suficiente espacio libre: la actualización necesita unos {need} MB junto a la carpeta y hay {free} "
        "MB libres.",
    "SHA256SUMS of release {version} has no line for {name}. Nothing was changed.":
        "El SHA256SUMS del release {version} no tiene línea para {name}. No se cambió nada.",
    "SHA256SUMS and GitHub disagree about the download's checksum. Nothing was changed.":
        "SHA256SUMS y GitHub no coinciden en el checksum de la descarga. No se cambió nada.",
    "The download is damaged or not the published file: its SHA-256 is {got}..., "
    "SHA256SUMS says {want}.... Nothing was changed.":
        "La descarga está dañada o no es el archivo publicado: su SHA-256 es {got}..., SHA256SUMS dice {want}.... No "
        "se cambió nada.",
    "The downloaded release has no python\\pythonw.exe. Nothing was changed.":
        "El release descargado no tiene python\\pythonw.exe. No se cambió nada.",
    "The download is far bigger than a release should be. Nothing was changed.":
        "La descarga es mucho más grande de lo que debería ser un release. No se cambió nada.",
    "The download contains an unexpected path ({name}: {why}). Nothing was changed.":
        "La descarga contiene una ruta inesperada ({name}: {why}). No se cambió nada.",
    "The download contains an unexpected path ({name}). Nothing was changed.":
        "La descarga contiene una ruta inesperada ({name}). No se cambió nada.",
    "Cancelled.": "Cancelado.",
    "Could not download or unpack the update ({error}). Nothing was changed.":
        "No se pudo descargar o descomprimir la actualización ({error}). No se cambió nada.",
    "The download is damaged ({error}). Nothing was changed.": "La descarga está dañada ({error}). No se cambió nada.",
    "the new release contains {names} (the player's files)":
        "el nuevo release contiene {names} (los archivos del jugador)",
    "release.json does not say {version} after the swap": "release.json no dice {version} después del cambio",
    "launcher\\t5dr_launcher.pyw is missing after the swap": "falta launcher\\t5dr_launcher.pyw después del cambio",
    "python\\pythonw.exe is missing after the swap": "falta python\\pythonw.exe después del cambio",
    "the update plan is incomplete": "el plan de actualización está incompleto",
    "the launcher did not close": "el launcher no se cerró",
    "programs from the folder were still running ({names}); close them and try again":
        "programas de la carpeta seguían abiertos ({names}); ciérralos e inténtalo de nuevo",
    "the new launcher {version} did not start": "el nuevo launcher {version} no se inició",
    "could not replace the program files: {error}": "no se pudieron reemplazar los archivos del programa: {error}",
    "unexpected error: {error}": "error inesperado: {error}",
    "GitHub asks to wait with update checks until {time}.":
        "GitHub pide esperar hasta las {time} para buscar actualizaciones.",
    "GitHub limits update checks right now. Try again later.":
        "GitHub está limitando las búsquedas de actualizaciones. Inténtalo más tarde.",
    "GitHub answered with error {code}. Try again later.": "GitHub respondió con el error {code}. Inténtalo más tarde.",
    "No connection to GitHub. Check the internet connection and try again.":
        "Sin conexión con GitHub. Revisa la conexión a internet e inténtalo de nuevo.",
    "A build is running. Update when it is finished.": "Hay una compilación en curso. Actualiza cuando termine.",
    "The game is running. Close it first, then update.": "El juego está abierto. Ciérralo primero y luego actualiza.",
    "'Host for friends' is running. Stop hosting first, then update.":
        "“Hostear para amigos” está activo. Deja de hostear primero y luego actualiza.",
    "An online match was found. Update after the match.":
        "Se encontró una partida online. Actualiza después de la partida.",
    "An online match is running. Update after the match.":
        "Hay una partida online en curso. Actualiza después de la partida.",
    "You are searching for or playing an online match. Update afterwards.":
        "Estás buscando o jugando una partida online. Actualiza después.",
    "Other programs from this folder are still running ({names}): another launcher "
    "window, the game or a lobby server. Close them, then update.":
        "Otros programas de esta carpeta siguen abiertos ({names}): otra ventana del launcher, el juego o un "
        "servidor de lobby. Ciérralos y luego actualiza.",
    "not a plain relative path": "no es una ruta relativa simple",
    "'.', '..' or an empty part": "“.”, “..” o una parte vacía",
    "outside the folder {folder}": "fuera de la carpeta {folder}",
    "named like the player's own files": "con el mismo nombre que los archivos del jugador",
    "a name Windows does not keep as written": "un nombre que Windows no guarda tal como está escrito",
    "Release {version} is a test version; it is not installed automatically.":
        "El release {version} es una versión de prueba; no se instala automáticamente.",
    "Release {version} is not signed with the project's release key (no SHA256SUMS.sig). It was not made by "
    "the project's release process; nothing was changed.":
        "El release {version} no está firmado con la clave de releases del proyecto (falta SHA256SUMS.sig). No salió "
        "del proceso de releases del proyecto; no se cambió nada.",
    "Release {version} failed the signature check ({error}). It was not made by the project's release "
    "process; nothing was changed.":
        "El release {version} no pasó la verificación de firma ({error}). No salió del proceso de releases del "
        "proyecto; no se cambió nada.",
    "idle": "libre",
    "room": "en sala",
    "queue": "buscando",
    "match": "en partida",
    "playing": "jugando",
    # ---- lobby/t5lobby/discord_rpc.py
    "In lobby": "En el lobby",
    "Searching ranked": "Buscando Ranked",
    "Searching quick match": "Buscando Quick Match",
    "Ranked, Set {mine}-{theirs}": "Ranked, set {mine}-{theirs}",
    "Ranked": "Ranked",
    "Casual": "Casual",
    "In match: {mine} vs {theirs} ({what})": "En partida: {mine} vs {theirs} ({what})",
    "In match ({what})": "En partida ({what})",
    # ---- lobby/t5lobby/lag.py
    "Ping {ping} ms should mean about {frames} frames behind.":
        "Con {ping} ms de ping, lo normal es ir unos {frames} frames atrás.",
    "The games did not report how it went, so there is nothing to compare.":
        "Los juegos no informaron cómo fue, así que no hay nada que comparar.",
    "It was {observed}.": "Fueron {observed}.",
    "That is what the ping explains.": "Eso es lo que explica el ping.",
    "That is more than the ping explains.": "Es más de lo que explica el ping.",
    "Both PCs ran below full speed.": "Ambas PC corrieron por debajo de la velocidad máxima.",
    "Your PC was the slow one ({fps} fps).": "Tu PC fue la lenta ({fps} fps).",
    "Your PC was the slow one.": "Tu PC fue la lenta.",
    "Your opponent's PC was the slow one ({fps} fps).": "La PC de tu rival fue la lenta ({fps} fps).",
    "Your opponent's PC was the slow one.": "La PC de tu rival fue la lenta.",
    "Both PCs kept up, so the connection stalled now and then (jitter or lost packets).":
        "Ambas PC aguantaron, así que la conexión se trabó de vez en cuando (jitter o paquetes perdidos).",
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "Tu rival cerró el juego.",
    "The connection to your opponent's game was lost.": "Se perdió la conexión con el juego de tu rival.",
    "Your opponent's game stopped responding.": "El juego de tu rival dejó de responder.",
    "Your opponent's game did not get to the fight.": "El juego de tu rival no llegó a la pelea.",
    "Your opponent's game was restarted; the match cannot go on.":
        "El juego de tu rival se reinició; la partida no puede continuar.",
    "Loading the fight took too long on this PC (slow disk or a busy PC?); the match was stopped.":
        "La carga del combate tardó demasiado en este PC (¿disco lento o PC ocupado?); la partida se detuvo.",
    "Loading the fight took too long on your opponent's PC; the match was stopped.":
        "La carga del combate tardó demasiado en el PC de tu rival; la partida se detuvo.",
    "Your opponent's game could not be reached (firewall or router?).":
        "No se pudo llegar al juego de tu rival (¿firewall o router?).",
    "Your opponent's game is a different build.": "El juego de tu rival es otra build.",
    "Your opponent's game is in another match.": "El juego de tu rival está en otra partida.",
    "The game could not open its network port (another program uses it?).":
        "El juego no pudo abrir su puerto de red (¿lo usa otro programa?).",
    "You closed the game during the match: it counts as a loss.":
        "Cerraste el juego durante la partida: cuenta como derrota.",
    "The game could not get back to character select and closed itself; it starts again for your next match.":
        "El juego no pudo volver a la selección de personaje y se cerró solo; se iniciará de nuevo para tu próxima "
        "partida.",
    "Your opponent does not want a rematch.": "Tu rival no quiere Rematch.",
    "The game is not running any more; leaving the rematch.": "El juego ya no está corriendo; saliendo del Rematch.",
    "Rematch against {name}: same connection, the game stays open.":
        "Rematch contra {name}: misma conexión, el juego sigue abierto.",
    "The game could not start; leaving the match.": "El juego no pudo iniciar; saliendo de la partida.",
    "Playing against {summary}": "Jugando contra {summary}",
    "The game did not answer its control channel; it is restarted for every opponent "
    "from now on.":
        "El juego no respondió en su canal de control; desde ahora se reinicia para cada rival.",
    "Character select...": "Selección de personaje...",
    "The game is starting...": "El juego está iniciando...",
    "Fight!": "Fight!",
    "Loading the fight...": "Cargando la pelea...",
    "Stage select...": "Selección de escenario...",
    "At character select, waiting for the next match.": "En la selección de personaje, esperando la siguiente partida.",
    "Match over.": "Partida terminada.",
    "Ignored a result the game wrote for an earlier match.":
        "Se ignoró un resultado que el juego escribió para una partida anterior.",
    "The match could not be finished ({reason}).": "La partida no se pudo terminar ({reason}).",
    "The match could not be played ({reason}).": "La partida no se pudo jugar ({reason}).",
    "The game stopped unexpectedly; the match does not count (repeated crashes do).":
        "El juego se detuvo inesperadamente; la partida no cuenta (los fallos repetidos sí).",
    "Result sent (the games went out of sync on {frames} frames); waiting for the "
    "lobby...":
        "Resultado enviado (los juegos se desincronizaron en {frames} frames); esperando al lobby...",
    "Result sent; waiting for the lobby...": "Resultado enviado; esperando al lobby...",
    "Lobby: {message}": "Lobby: {message}",
    # ---- lobby/t5lobby/padnav.py
    "(+{count} more)": "(+{count} más)",
    # ---- lobby/t5lobby/ranks.py
    "{wins}W {losses}L": "{wins}V {losses}D",
    "{draws}D": "{draws}E",
    "{rank} (placement {done}/{total})": "{rank} (clasificación {done}/{total})",
    # ---- lobby/t5lobby/sets.py
    "a game was too short to count": "una partida fue demasiado corta para contar",
    "a fight ended without a winner": "una pelea terminó sin ganador",
    "too many games without a winner": "demasiadas partidas sin ganador",
    "left after the lag check": "salió tras el chequeo de lag",
    "the lobby server restarted": "el servidor del lobby se reinició",
    "a player left right away": "un jugador salió de inmediato",
    "the next game could not start": "la siguiente partida no pudo iniciar",
    "a player left before a game counted": "un jugador salió antes de que contara una partida",
    "a player lost the lobby connection": "un jugador perdió la conexión con el lobby",
    "set won": "set ganado",
    "set lost": "set perdido",
    "Set {mine}-{theirs}": "Set {mine}-{theirs}",
    "game {number} of {best}": "partida {number} de {best}",
    "game {number} of {best} again (no winner)": "partida {number} de {best} otra vez (sin ganador)",
    "starts in {seconds} s": "empieza en {seconds} s",
    "The set does not count ({why}); no rating change": "El set no cuenta ({why}); sin cambio de puntos",
    "The set does not count; no rating change": "El set no cuenta; sin cambio de puntos",
    "You won the set (your opponent left it)": "Ganaste el set (tu rival lo abandonó)",
    "You won the set": "Ganaste el set",
    "You lost the set (you left it)": "Perdiste el set (lo abandonaste)",
    "You lost the set": "Perdiste el set",
    "You won the set {mine}-{theirs}": "Ganaste el set {mine}-{theirs}",
    "You lost the set {mine}-{theirs}": "Perdiste el set {mine}-{theirs}",
    "set game {number}": "partida {number} del set",
    # ---- lobby/t5lobby/tk_tour.py, tour_text.py (tournaments)
    "A set is played like a casual set with the in-game select; results come from the games. Players who do not accept a called set in time are out.": "Un set se juega como un set casual con la selección en el juego; los resultados salen de las partidas. Quien no acepte a tiempo un set llamado queda eliminado.",
    "Accepted. Waiting for {name}...": "Aceptado. Esperando a {name}...",
    "Bracket": "Bracket",
    "CALLED": "LLAMADO",
    "Cancel tournament": "Cancelar torneo",
    "Cancel {name}? Nobody can play it any more.": "¿Cancelar {name}? Nadie podrá jugarlo.",
    "Cancelled": "Cancelado",
    "Champion: {name}": "Campeón: {name}",
    "Check in": "Hacer check-in",
    "Check-in": "Check-in",
    "Check-in 10 minutes before": "Check-in 10 minutos antes",
    "Check-in 15 minutes before": "Check-in 15 minutos antes",
    "Check-in 30 minutes before": "Check-in 30 minutos antes",
    "Check-in 5 minutes before": "Check-in 5 minutos antes",
    "Check-in 60 minutes before": "Check-in 60 minutos antes",
    "Check-in for {name} is open: check in on the Tournaments page, or you are not in the bracket.": "El check-in de {name} está abierto: hazlo en la página Torneos o no entras en el bracket.",
    "Checked in.": "Check-in hecho.",
    "Click a set in the bracket.": "Haz clic en un set del bracket.",
    "Create": "Crear",
    "Create tournament": "Crear torneo",
    "Create...": "Crear...",
    "Disqualify": "Descalificar",
    "Disqualify which player (name)?": "¿Qué jugador descalificar (nombre)?",
    "Disqualify...": "Descalificar...",
    "Double elimination": "Eliminación doble",
    "Final": "Final",
    "Finished": "Terminado",
    "First to 2 games (best of 3)": "A 2 partidas ganadas (al mejor de 3)",
    "First to 3 games (best of 5)": "A 3 partidas ganadas (al mejor de 5)",
    "Format": "Formato",
    "Grand final": "Gran final",
    "Grand final reset": "Gran final (reset)",
    "LIVE": "EN VIVO",
    "Leave the tournament set": "Abandonar el set de torneo",
    "Leave this tournament set?\n\nYou lose the set.": "¿Abandonar este set de torneo?\n\nPierdes el set.",
    "Losers final": "Final de Losers",
    "Losers round {number}": "Ronda {number} de Losers",
    "Losers semi-final": "Semifinal de Losers",
    "NEEDS THE ORGANIZER": "ESPERA AL ORGANIZADOR",
    "No check-in": "Sin check-in",
    "No tournament selected": "Ningún torneo seleccionado",
    "Only tournament hosts can create tournaments. Ask the server's owner for a host slot.":
        "Solo los anfitriones de torneos pueden crear torneos. Pide al dueño del servidor una plaza de anfitrión.",
    "Pick a tournament to see its bracket.": "Elige un torneo para ver su bracket.",
    "Pick one in the list, or create one.": "Elige uno de la lista o crea uno.",
    "Players": "Jugadores",
    "Players at most": "Máximo de jugadores",
    "Players: {list}": "Jugadores: {list}",
    "Quarter-final": "Cuartos de final",
    "Random seeding": "Seeding aleatorio",
    "Report a result": "Reportar un resultado",
    "Reset set": "Reiniciar set",
    "Reset set {set}? It is played again from 0-0.": "¿Reiniciar el set {set}? Se vuelve a jugar desde 0-0.",
    "Round {number}": "Ronda {number}",
    "Running": "En curso",
    "Seeded by rating": "Seeding por puntos",
    "Seeding": "Seeding",
    "Semi-final": "Semifinal",
    "Sets": "Sets",
    "Side 1 wins": "Gana el lado 1",
    "Side 2 wins": "Gana el lado 2",
    "Sign up": "Inscribirse",
    "Sign-up": "Inscripción",
    "Single elimination": "Eliminación simple",
    "Start now": "Empezar ya",
    "Start {name} now, with the players who are in?": "¿Empezar {name} ya, con los jugadores que están?",
    "Starts": "Empieza",
    "TOURNAMENT": "TORNEO",
    "TOURNAMENT SET · BEST OF {best}": "SET DE TORNEO · AL MEJOR DE {best}",
    "The bracket is drawn when the tournament starts.": "El bracket se arma cuando empieza el torneo.",
    "The name needs 3 characters or more.": "El nombre necesita 3 caracteres o más.",
    "The organizer decided your tournament set.": "El organizador decidió tu set de torneo.",
    "The organizer reset your tournament set; it is called again.": "El organizador reinició tu set de torneo; se vuelve a llamar.",
    "The set goes on at {mine}-{theirs}.": "El set sigue en {mine}-{theirs}.",
    "The set has no result; the tournament calls it again or its organizer decides": "El set no tiene resultado; el torneo lo vuelve a llamar o decide su organizador",
    "The set is called again.": "El set se vuelve a llamar.",
    "The tournament was cancelled.": "El torneo se canceló.",
    "The tournament {name} has started: you are seed {seed} of {players}. Your sets are called here.": "El torneo {name} empezó: eres el seed {seed} de {players}. Tus sets se llaman aquí.",
    "The tournament {name} is over: {champion} won it.": "El torneo {name} terminó: lo ganó {champion}.",
    "The tournament {name} is over: {champion} won it. You finished {place}.": "El torneo {name} terminó: lo ganó {champion}. Tu resultado: {place}.",
    "The tournament {name} was cancelled by its organizer.": "Su organizador canceló el torneo {name}.",
    "The tournament {name} was cancelled: not enough players.": "El torneo {name} se canceló: faltan jugadores.",
    "This tournament had no bracket.": "Este torneo no tuvo bracket.",
    "This tournament is for another build of the game.": "Este torneo es para otro build del juego.",
    "Tournament": "Torneo",
    "Tournament set": "Set de torneo",
    "Tournament set vs {name}": "Set de torneo contra {name}",
    "Tournament {name} created.": "Torneo {name} creado.",
    "Tournament {name}: set {set} needs you ({why}). Report the result or reset it.": "Torneo {name}: el set {set} te necesita ({why}). Reporta el resultado o reinícialo.",
    "Tournament {name}: {code}": "Torneo {name}: {code}",
    "Tournaments": "Torneos",
    "Winners final": "Final de Winners",
    "Winners round {number}": "Ronda {number} de Winners",
    "Winners semi-final": "Semifinal de Winners",
    "Withdraw": "Retirarse",
    "Withdraw from {name}? You are out of the tournament.": "¿Retirarte de {name}? Quedas fuera del torneo.",
    "Write the start time as HH:MM, e.g. 20:30.": "Escribe la hora de inicio como HH:MM, p. ej. 20:30.",
    "You are checked in.": "Hiciste check-in.",
    "You are in. Your next set is called here when its players are known.": "Estás dentro. Tu próximo set se llama aquí cuando se sepan sus jugadores.",
    "You are out of {name}.": "Quedaste fuera de {name}.",
    "You are out of {name}: {place}.": "Quedaste fuera de {name}: {place}.",
    "You are out of {name}: {why}.": "Estás fuera de {name}: {why}.",
    "You are out: {why}.": "Estás fuera: {why}.",
    "You are signed up.": "Estás inscrito.",
    "You are signed up. Check in now, or you are not in the bracket.": "Estás inscrito. Haz check-in ahora o no entras en el bracket.",
    "You did not check in for {name}; the tournament started without you.": "No hiciste check-in en {name}; el torneo empezó sin ti.",
    "You finished {place}.": "Tu resultado: {place}.",
    "You left the tournament.": "Saliste del torneo.",
    "You won the tournament {name}!": "¡Ganaste el torneo {name}!",
    "Your next set: {set}.": "Tu próximo set: {set}.",
    "Your opponent did not show up: you win the set.": "Tu rival no se presentó: ganas el set.",
    "Your opponent is out of the tournament: you win the set.": "Tu rival quedó fuera del torneo: ganas el set.",
    "Your tournament set has no result; the organizer decides how it goes on.": "Tu set de torneo no tiene resultado; el organizador decide cómo sigue.",
    "Your tournament set is ready": "Tu set de torneo está listo",
    "accept within {seconds} s": "acepta en {seconds} s",
    "accepted -- waiting for {name}...": "aceptado -- esperando a {name}...",
    "best of {best}": "al mejor de {best}",
    "bye": "pase libre",
    "check-in from {time}": "check-in desde {time}",
    "decided by the organizer": "decidido por el organizador",
    "did not show up": "ausente",
    "disqualified": "descalificado",
    "disqualified by the organizer": "descalificado por el organizador",
    "ended {time}": "terminó {time}",
    "in 1 hour": "en 1 hora",
    "in 10 minutes": "en 10 minutos",
    "in 12 hours": "en 12 horas",
    "in 15 minutes": "en 15 minutos",
    "in 2 hours": "en 2 horas",
    "in 24 hours": "en 24 horas",
    "in 3 hours": "en 3 horas",
    "in 30 minutes": "en 30 minutos",
    "in 5 minutes": "en 5 minutos",
    "in 6 hours": "en 6 horas",
    "no-show": "no se presentó",
    "nobody": "nadie",
    "none yet": "ninguno aún",
    "not needed": "no hizo falta",
    "or at (HH:MM)": "o a las (HH:MM)",
    "organizer {name}": "organiza {name}",
    "place {place}": "puesto {place}",
    "rated": "con puntos",
    "results disputed": "resultados en disputa",
    "started {time}": "empezó {time}",
    "starts {time}": "empieza {time}",
    "waiting": "pendiente",
    "withdrew": "retirado",
    "{format}, best of {best}": "{format}, al mejor de {best}",
    "{name} has accepted.": "{name} aceptó.",
    "{name} is not online yet.": "{name} todavía no está online.",
    "{name} wins": "Gana {name}",
    "{name} wins set {set}?": "¿{name} gana el set {set}?",
    "{name}'s tournament": "Torneo de {name}",
    "{players} of {max} players": "{players} de {max} jugadores",
    "The organizer decided the set.": "El organizador decidió el set.",
    # ---- lobby/t5lobby/i18n_known.py: lobby/t5lobby/server/tournaments.py
    "tournaments need an account": "los torneos requieren una cuenta",
    "no such tournament": "ese torneo no existe",
    "only the server's organizers can create tournaments here": "aquí solo los organizadores del servidor pueden crear torneos",
    "a tournament name is 3-40 characters": "el nombre de un torneo tiene de 3 a 40 caracteres",
    "the format is single or double elimination": "el formato es eliminación simple o doble",
    "a set is first to 2 or first to 3 games": "un set es a 2 o a 3 partidas ganadas",
    "the player limit is 8, 16, 32 or 64": "el límite de jugadores es 8, 16, 32 o 64",
    "the check-in window is 0, 5, 10, 15, 30 or 60 minutes": "el check-in dura 0, 5, 10, 15, 30 o 60 minutos",
    "seeding is random or by rating": "el seeding es aleatorio o por puntos",
    "that start time has passed": "esa hora de inicio ya pasó",
    "a tournament starts within {days} days": "un torneo empieza dentro de {days} días",
    "this server has as many tournaments as it takes; try again later": "este servidor ya tiene todos los torneos que admite; inténtalo más tarde",
    "you already run {count} tournaments; finish or cancel one first": "ya organizas {count} torneos; termina o cancela uno primero",
    "update the launcher to play in tournaments": "actualiza el launcher para jugar torneos",
    "sign-up for that tournament is closed": "la inscripción a ese torneo está cerrada",
    "that tournament is played with another build of the game": "ese torneo se juega con otro build del juego",
    "that tournament is full": "ese torneo está lleno",
    "you are not in that tournament": "no estás en ese torneo",
    "that tournament is over": "ese torneo ya terminó",
    "check-in is not open": "el check-in no está abierto",
    "that tournament is not running": "ese torneo no está en curso",
    "that set is not yours to play": "ese set no es tuyo",
    "that set is not waiting for you": "ese set no te está esperando",
    "only the organizer can do that": "solo el organizador puede hacer eso",
    "that tournament name is not allowed here":
        "ese nombre de torneo no está permitido aquí",
    "this internet address runs as many tournaments as one organizer may; finish or cancel one first":
        "desde esta dirección de internet ya hay tantos torneos como puede tener un organizador; termina o cancela uno primero",
    "the organizer took you off this tournament":
        "el organizador te quitó de este torneo",
    "you play in that set yourself: a server tournament admin decides it (or cancel the tournament)":
        "tú juegas ese set: lo decide un administrador de torneos del servidor (o cancela el torneo)",
    "that tournament has started already": "ese torneo ya empezó",
    "a tournament needs at least 2 players": "un torneo necesita al menos 2 jugadores",
    "no such player in that tournament": "ese jugador no está en el torneo",
    "that player is out already": "ese jugador ya está eliminado",
    "no such set": "ese set no existe",
    "that set is decided; override it instead": "ese set ya está decidido; corrígelo en su lugar",
    "only a played set can be overridden": "solo se puede corregir un set jugado",
    "that set has not been played": "ese set aún no se jugó",
    "that set was a walkover": "ese set fue un pase libre",
    "set {set} was already played from this result; reset it first": "el set {set} ya se jugó con este resultado; reinícialo primero",
    "finish your match first, then accept the tournament set": "primero termina tu partida y luego acepta el set del torneo",
    "finish your set first, then accept the tournament set": "primero termina tu set y luego acepta el set del torneo",
    "you are in a tournament set; finish it first": "estás en un set de torneo; termínalo primero",
    "that player is playing a tournament set": "ese jugador está jugando un set de torneo",
    "your tournament set is ready; accept it first": "tu set de torneo está listo; acéptalo primero",
    "that player has a tournament set to play": "ese jugador tiene un set de torneo pendiente",
    # ---- lobby/t5lobby/theme.py
    "Good connection": "Buena conexión",
    "Laggy connection": "Conexión con lag",
    "OK connection": "Conexión aceptable",
    "Ping not known yet": "Ping aún desconocido",
    "sec": "seg",
    # ---- lobby/t5lobby/tk_tab.py
    "Leave set (counts as a loss)": "Abandonar el set (cuenta como derrota)",
    "Leave the ranked set": "Abandonar el set Ranked",
    "Leave this ranked set?\n\nLeaving a ranked set counts as losing it.":
        "¿Abandonar este set Ranked?\n\nAbandonar un set Ranked cuenta como perderlo.",
    "Rematch? (a new set)": "¿Rematch? (un set nuevo)",
    "in a room": "en una sala",
    "in lobby": "en el lobby",
    "matching": "armando partida",
    "searching": "buscando",
    "full": "llena",
    "open": "abierta",
    "Result confirmed": "Resultado confirmado",
    "Result recorded (your opponent did not report)": "Resultado registrado (tu rival no lo reportó)",
    "Match decided by forfeit": "Partida decidida por abandono",
    "Result decided by the games' state": "Resultado decidido por el estado de los juegos",
    "You and your opponent reported different results -- not counted":
        "Tú y tu rival reportaron resultados distintos -- no cuenta",
    "No result": "Sin resultado",
    "confirmed": "confirmado",
    "forfeit": "abandono",
    "one-sided": "unilateral",
    "disputed": "disputado",
    "resolved": "resuelto",
    "void": "anulado",
    "draw": "empate",
    "loss": "derrota",
    "win": "victoria",
    "the two games went out of sync": "los dos juegos se desincronizaron",
    "too short to count": "demasiado corta para contar",
    "a game crashed": "un juego falló",
    "the reports disagreed": "los reportes no coincidieron",
    "left right away": "salió de inmediato",
    "a player left": "un jugador salió",
    "a player lost the connection": "un jugador perdió la conexión",
    "a player did not report": "un jugador no reportó",
    "the connection between the games failed": "falló la conexión entre los juegos",
    "both players left": "ambos jugadores salieron",
    "no result in time": "sin resultado a tiempo",
    "repeated crashes count as losses": "fallos repetidos cuentan como derrotas",
    "repeated early quits": "abandonos tempranos repetidos",
    "repeated missing reports": "reportes faltantes repetidos",
    "scores differed": "los marcadores no coincidieron",
    "the fight ended without a winner": "la pelea terminó sin ganador",
    "Match declined.": "Partida rechazada.",
    "Nobody accepted in time.": "Nadie aceptó a tiempo.",
    "Your opponent left.": "Tu rival se fue.",
    "No UDP connection to the lobby server (firewall?).": "Sin conexión UDP con el servidor del lobby (¿firewall?).",
    "Could not connect the two PCs, not even through the relay.":
        "No se pudieron conectar las dos PC, ni siquiera por el relay.",
    "The lobby server's relay is full; try again in a moment.":
        "El relay del servidor del lobby está lleno; inténtalo de nuevo en un momento.",
    "Challenge cancelled.": "Desafío cancelado.",
    "Challenge declined.": "Desafío rechazado.",
    "Challenge expired.": "Desafío expirado.",
    "direct": "directa",
    "via the lobby server's relay": "por el relay del servidor del lobby",
    "via the relay server {name}": "por el servidor relay {name}",
    "Lobby error: {error}": "Error del lobby: {error}",
    "guest": "invitado",
    "Not connected. Ranked needs an account; guests play casual matches.":
        "No conectado. Ranked necesita una cuenta; los invitados juegan partidas casuales.",
    "Passwords are only sent to servers on this PC / your network, or over an encrypted "
    "(TLS) connection.":
        "Las contraseñas solo se envían a servidores en esta PC o tu red, o por una conexión cifrada (TLS).",
    "Double-click a player in the lobby or the leaderboard.":
        "Haz doble clic en un jugador del lobby o de la clasificación.",
    "{name} (guest, casual matches only)": "{name} (invitado, solo partidas casuales)",
    "{record} this session": "{record} en esta sesión",
    "rating {rating}": "puntos {rating}",
    "main {character}": "main {character}",
    "server ping {ms} ms": "ping al servidor {ms} ms",
    "encrypted": "cifrado",
    "[Server: {notice}]": "[Servidor: {notice}]",
    "Server notice: {notice}": "Aviso del servidor: {notice}",
    "The game is not built.": "El juego no está compilado.",
    "Cannot read the build's identity: {error}": "No se puede leer la identidad de la build: {error}",
    "Enter a password (6 characters or more), or play as a guest.":
        "Escribe una contraseña (6 caracteres o más), o juega como invitado.",
    "Connecting to {server}...": "Conectando a {server}...",
    "Pick a character, then Ranked match (accounts) or Quick match.":
        "Elige un personaje y luego partida Ranked (con cuenta) o Quick Match.",
    "Encrypted connection (TLS).": "Conexión cifrada (TLS).",
    "(logged in with your saved login)": "(sesión iniciada con tu inicio de sesión guardado)",
    "In the lobby.": "En el lobby.",
    "Your saved login has expired; log in with your password.":
        "Tu inicio de sesión guardado expiró; entra con tu contraseña.",
    "Create account": "Crear cuenta",
    "Type the password again:": "Escribe la contraseña otra vez:",
    "The two passwords differ.": "Las dos contraseñas no coinciden.",
    "Closing the running game for the online match...": "Cerrando el juego abierto para la partida online...",
    "Also forget the saved login on this PC?\n\n(No = you are logged in automatically "
    "next time.)":
        "¿Olvidar también el inicio de sesión guardado en esta PC?\n\n(No = entras automáticamente la próxima vez.)",
    "Log out": "Cerrar sesión",
    "Not connected.": "No conectado.",
    "Change password": "Cambiar contraseña",
    "Current password:": "Contraseña actual:",
    "New password (6 characters or more):": "Contraseña nueva (6 caracteres o más):",
    "New password again:": "Contraseña nueva otra vez:",
    "The two new passwords differ.": "Las dos contraseñas nuevas no coinciden.",
    "Password changed. Saved logins on other PCs have ended.":
        "Contraseña cambiada. Los inicios de sesión guardados en otras PC terminaron.",
    "Recovery codes": "Códigos de recuperación",
    "Your password (the old codes stop working):": "Tu contraseña (los códigos viejos dejan de funcionar):",
    "Save recovery codes": "Guardar códigos de recuperación",
    "T5DR Online recovery codes for {name} on {server}":
        "Códigos de recuperación de T5DR Online para {name} en {server}",
    "Forgot password": "Olvidé mi contraseña",
    "Account name:": "Nombre de la cuenta:",
    "One of your recovery codes (XXXX-XXXX-XXXX):": "Uno de tus códigos de recuperación (XXXX-XXXX-XXXX):",
    "Password reset. {count} recovery code(s) left. Log in with the new password.":
        "Contraseña restablecida. Quedan {count} código(s) de recuperación. Entra con la contraseña nueva.",
    "Server certificate": "Certificado del servidor",
    "For a server with its own (self-signed) certificate: its SHA-256 fingerprint, from "
    "whoever runs it.\nEmpty = no pinning (use tls://host:port for a server with a "
    "normal certificate).":
        "Para un servidor con su propio certificado (autofirmado): su huella SHA-256, que te da quien lo "
        "administra.\nVacío = sin fijar (usa tls://host:port para un servidor con certificado normal).",
    "Searching for an opponent...": "Buscando rival...",
    "Searching for an opponent (ranked: similar rank and a good connection, strict: "
    "within 150 rating points -- this can take a while)...":
        "Buscando rival (Ranked: rango parecido y buena conexión, estricto: a menos de 150 puntos -- puede tardar)...",
    "Searching for an opponent (ranked: similar rank and a good connection)...":
        "Buscando rival (Ranked: rango parecido y buena conexión)...",
    "Select a room first.": "Primero elige una sala.",
    "Select an opponent in the list first.": "Primero elige un rival de la lista.",
    "Challenge sent.": "Desafío enviado.",
    "Blocked players": "Jugadores bloqueados",
    "You are never matched with these players (ranked, quick matches, rooms, challenges, "
    "rematches). They are not told. Accounts stay blocked; a guest is blocked until you "
    "log out.":
        "Nunca te emparejarán con estos jugadores (Ranked, Quick Match, salas, desafíos, rematches). No se les "
        "avisa. Las cuentas quedan bloqueadas; un invitado queda bloqueado hasta que cierres sesión.",
    "Unblocked {name}.": "{name} desbloqueado.",
    "Unblock": "Desbloquear",
    "Block player": "Bloquear jugador",
    "Block {name}?\n\nYou will not be matched with them again. They are not told. You "
    "can unblock them under \"Blocked players...\".":
        "¿Bloquear a {name}?\n\nNo volverán a emparejarte con este jugador. No se le avisa. Puedes desbloquearlo en "
        "“Jugadores bloqueados...”.",
    "Blocked {name}. You will not be matched again.": "{name} bloqueado. No volverán a emparejarlos.",
    "you": "tú",
    "{name} -- {rank}": "{name} -- {rank}",
    "Rating {rating} +/- {rd}": "Puntos {rating} +/- {rd}",
    "(provisional)": "(provisional)",
    "#{place} on the leaderboard": "#{place} en la clasificación",
    "Record {record}": "Récord {record}",
    "ranked matches {count}": "partidas Ranked {count}",
    "highest rank {rank}": "rango máximo {rank}",
    "Characters: {list}": "Personajes: {list}",
    "Matches without result caused in the last 24 h: {count}":
        "Partidas sin resultado causadas en las últimas 24 h: {count}",
    "Recovery codes left: {count}": "Códigos de recuperación restantes: {count}",
    "{you} vs {opponent}": "{you} vs {opponent}",
    "casual": "casual",
    "Opponent: {name} ({rank}, {rating})": "Rival: {name} ({rank}, {rating})",
    "RANKED": "RANKED",
    "rematch": "Rematch",
    "{name} ({rank}) challenges you": "{name} ({rank}) te desafía",
    "Accept": "Aceptar",
    "Decline": "Rechazar",
    "Challenge {state}.": "Desafío: {state}.",
    "connecting...": "conectando...",
    "Your opponent accepted.": "Tu rival aceptó.",
    "Match cancelled ({reason}).": "Partida cancelada ({reason}).",
    "Ranked match vs {name}": "Partida Ranked contra {name}",
    "Casual match vs {name}": "Partida casual contra {name}",
    "{p1} vs {p2}": "{p1} vs {p2}",
    "ping {ms} ms ({how}), input delay {frames} frames ({delay_ms} ms)":
        "ping {ms} ms ({how}), input delay de {frames} frames ({delay_ms} ms)",
    "Lost the lobby connection -- reconnecting (your match goes on)...":
        "Se perdió la conexión con el lobby -- reconectando (tu partida sigue)...",
    "Reconnected to the lobby.": "Reconectado al lobby.",
    "Lost the lobby connection: {reason}": "Se perdió la conexión con el lobby: {reason}",
    "Lost the connection to the lobby server.": "Se perdió la conexión con el servidor del lobby.",
    "Removed from the lobby: {reason}": "Expulsado del lobby: {reason}",
    "The game closed. How did the match against {opponent} end?":
        "El juego se cerró. ¿Cómo terminó la partida contra {opponent}?",
    "I won": "Gané",
    "I lost": "Perdí",
    "Draw": "Empate",
    "I quit": "Abandoné",
    "{opponent} wants a rematch": "{opponent} quiere Rematch",
    "Rematch": "Rematch",
    "No thanks": "No, gracias",
    "Result sent; waiting for your opponent's report...": "Resultado enviado; esperando el reporte de tu rival...",
    "Rematch offered; waiting for your opponent...": "Rematch ofrecido; esperando a tu rival...",
    "(other version)": "(otra versión)",
    "other version": "otra versión",
    "ranked": "Ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "Buscando... ({ranked} en la búsqueda Ranked, {quick} en Quick Match)",
    "ping about {ms} ms (estimated; measured directly once you both accept)":
        "ping de unos {ms} ms (estimado; se mide directo cuando ambos acepten)",
    "ping not known yet": "ping aún desconocido",
    "Opponent found": "Rival encontrado",
    "accept within {seconds} s?": "¿aceptar en {seconds} s?",
    "waiting for the opponent...": "esperando al rival...",
    "Lag check: {text}": "Chequeo de lag: {text}",
    "You left after the lag check. No penalty, no rating change.":
        "Saliste tras el chequeo de lag. Sin penalización ni cambio de puntos.",
    "Your opponent left after the lag check. No penalty for anyone.":
        "Tu rival salió tras el chequeo de lag. Nadie recibe penalización.",
    "Your opponent left. The set is over.": "Tu rival se fue. El set terminó.",
    "Rematch {name}": "Rematch con {name}",
    "Next game": "Siguiente partida",
    "Leave": "Salir",
    "Block {name}": "Bloquear a {name}",
    "Leave: too laggy": "Salir: mucho lag",
    "You lost.": "Perdiste.",
    "You won.": "Ganaste.",
    "rating {rating} ({delta})": "puntos {rating} ({delta})",
    "PROMOTED to {rank}!": "¡ASCENDISTE a {rank}!",
    "demoted to {rank}": "bajaste a {rank}",
    "placed at {rank}": "clasificado en {rank}",
    "placement {done}/{total}": "clasificación {done}/{total}",
    "your opponent": "tu rival",
    "Rematch?": "¿Rematch?",
    "Controller off.": "Control desactivado.",
    "No controller found.": "No se encontró ningún control.",
    "Controller: {summary}": "Control: {summary}",
    "Cannot start the lobby server: {error}": "No se puede iniciar el servidor del lobby: {error}",
    "Stop hosting": "Dejar de hostear",
    "Starting a lobby server on this PC and asking the router to forward its ports...":
        "Iniciando un servidor de lobby en esta PC y pidiendo al router que redirija sus puertos...",
    "Starting a lobby server on this PC...": "Iniciando un servidor de lobby en esta PC...",
    "<your public IP>": "<tu IP pública>",
    "Hosting. Friends paste this as their Server (copied to the clipboard):\n  {share}":
        "Hosteando. Tus amigos pegan esto como su Servidor (copiado al portapapeles):\n  {share}",
    "\n  same network: {lan}": "\n  misma red: {lan}",
    "\n  Forward TCP+UDP 7781 and UDP 7782 on your router (or tick 'Open router ports').":
        "\n  Redirige TCP+UDP 7781 y UDP 7782 en tu router (o marca “Abrir puertos del router”).",
    "Hosting a lobby on this PC. Log in to join it yourself.":
        "Hay un lobby alojado en esta PC. Inicia sesión para entrar tú también.",
    "Hosting failed: {message}": "Falló el hosteo: {message}",
    "Host for friends": "Hostear para amigos",
    "The lobby server stopped (exit code {code}); see its log in {folder}.":
        "El servidor del lobby se detuvo (código de salida {code}); mira su log en {folder}.",
    "Stopped hosting.": "Se dejó de hostear.",
    # in-game character select (branch ingame-select)
    "Pick your fighter in the game ({secs} s; Select = random; no pick = the character set here).":
        "Elige tu personaje en el juego ({secs} s; Select = aleatorio; sin elegir = el personaje de aquí).",
    "Waiting for your opponent to pick...": "Esperando a que tu rival elija...",
    "Ranked match (accounts) or Quick match; then pick your fighter in the game (Select = random). The character here is used when you do not pick in time.":
        "Partida Ranked (con cuenta) o Quick Match; luego elige tu personaje en el juego (Select = aleatorio). Si no "
        "eliges a tiempo, se usa el personaje de aquí.",
    "pick your fighter in the game ({secs} s)": "elige tu personaje en el juego ({secs} s)",
    "(locked for this ranked set)": "(fijo en este set Ranked)",
    "Pick your fighter in the game": "Elige tu personaje en el juego",
    "Your opponent is picking": "Tu rival está eligiendo",
    # ---- lobby/t5lobby/tk_views.py
    "Rank": "Rango",
    "Rating": "Puntos",
    "Record": "Récord",
    "Main": "Main",
    "Ping": "Ping",
    "Room": "Sala",
    "Status": "Estado",
    "Owner": "Dueño",
    "Place": "Puesto",
    "State": "Estado",
    "When": "Cuándo",
    "Characters": "Personajes",
    "Opponent": "Rival",
    "Result": "Resultado",
    "Score": "Rounds",
    "Check the server address and your internet connection, then try again.":
        "Revisa la dirección del servidor y tu conexión a internet, y vuelve a intentarlo.",
    "Check your internet connection, then try again.": "Revisa tu conexión a internet y vuelve a intentarlo.",
    "The server is slow or gone; try again in a minute.": "El servidor está lento o caído; inténtalo en un minuto.",
    "Log in again.": "Vuelve a iniciar sesión.",
    "Ask whoever runs the server for its current fingerprint (\"Server certificate...\").":
        "Pide a quien administra el servidor su huella actual (“Certificado del servidor...”).",
    "Check the spelling, or use \"Forgot password...\".": "Revisa cómo lo escribiste, o usa “Olvidé mi contraseña...”.",
    "Check the name and the code; each code works once.": "Revisa el nombre y el código; cada código sirve una vez.",
    "Pick another name, or wait a minute if that was you.": "Elige otro nombre, o espera un minuto si eras tú.",
    "Log in with that account's password, or pick another name.":
        "Inicia sesión con la contraseña de esa cuenta, o elige otro nombre.",
    "Pick another name.": "Elige otro nombre.",
    "Update the game to the release this server asks for.": "Actualiza el juego a la versión que pide este servidor.",
    "You both need the same release of the game.": "Ambos necesitan la misma versión del juego.",
    "Update the launcher to the newest release.": "Actualiza el launcher a la versión más reciente.",
    "Create an account (free) to play ranked.": "Crea una cuenta (gratis) para jugar Ranked.",
    "Pick another room or create your own.": "Elige otra sala o crea la tuya.",
    "Log in with your password.": "Inicia sesión con tu contraseña.",
    "Build the game on the Build tab first.": "Primero compila el juego en la pestaña Compilar.",
    "Allow T5DR Online through the Windows firewall, then search again.":
        "Permite T5DR Online en el firewall de Windows y vuelve a buscar.",
    "Try again; if it keeps failing, check your firewall or router.":
        "Inténtalo de nuevo; si sigue fallando, revisa tu firewall o router.",
    "Log in again; your settings are kept.": "Vuelve a iniciar sesión; tus ajustes se conservan.",
    "Type the same password twice.": "Escribe la misma contraseña dos veces.",
    "Find a new opponent.": "Busca un nuevo rival.",
    "Check the Play offline tab: does the game start there?": "Revisa la pestaña Jugar offline: ¿el juego inicia ahí?",
    "Against other players over the internet. Log in or play as a guest; the game starts "
    "by itself, straight into the fight, and the result comes back here.":
        "Contra otros jugadores por internet. Inicia sesión o juega como invitado; el juego se abre solo, directo en "
        "la pelea, y el resultado vuelve aquí.",
    "Server": "Servidor",
    "Server certificate...": "Certificado del servidor...",
    "Name": "Nombre",
    "Log in": "Iniciar sesión",
    "Password": "Contraseña",
    "Password again": "Repetir contraseña",
    "Name: 2 to 16 letters, digits, spaces or _-.[]()!?": "Nombre: de 2 a 16 letras, números, espacios o _-.[]()!?",
    "Password: 6 to 128 characters": "Contraseña: de 6 a 128 caracteres",
    "Both passwords the same": "Ambas contraseñas iguales",
    "You get recovery codes once: the only way back in if you forget the password":
        "Recibes códigos de recuperación una sola vez: la única forma de volver a entrar si olvidas la contraseña",
    "Remember me": "Recordarme",
    "Forgot password...": "Olvidé mi contraseña...",
    "Casual matches with the name above, no account and no password. Ranked matches, the "
    "leaderboard and your match history need an account.":
        "Partidas casuales con el nombre de arriba, sin cuenta ni contraseña. Las partidas Ranked, la clasificación "
        "y tu historial necesitan una cuenta.",
    "Play as guest": "Jugar como invitado",
    "Runs a lobby on this PC. Your friends type the address it shows into their Server "
    "box.":
        "Abre un lobby en esta PC. Tus amigos escriben la dirección que muestra en su casilla Servidor.",
    "Open router ports (UPnP)": "Abrir puertos del router (UPnP)",
    "How it works": "Cómo funciona",
    "Quick match (casual) or Ranked match (account).": "Quick Match (casual) o partida Ranked (con cuenta).",
    "An opponent is found: accept within 15 seconds.": "Se encuentra un rival: acepta en menos de 15 segundos.",
    "The game opens straight into the fight.": "El juego se abre directo en la pelea.",
    "The result comes back here: rematch or next game.": "El resultado vuelve aquí: Rematch o siguiente partida.",
    "With a controller: A accepts, B declines.": "Con control: A acepta, B rechaza.",
    "Online nobody can pause the fight: Start does not open the pause menu.":
        "En línea nadie puede pausar el combate: Start no abre el menú de pausa.",
    "Lobby": "Lobby",
    "Leaderboard": "Clasificación",
    "Profile": "Perfil",
    "My profile": "Mi perfil",
    "Find an opponent online": "Busca un rival online",
    "Character": "Personaje",
    "Locked for this ranked set": "Fijo en este set Ranked",
    "Ranked match": "Partida Ranked",
    "Quick match": "Quick Match",
    "Casual: the lowest ping first": "Casual: primero el ping más bajo",
    "Strict (ranked: +-150 rating)": "Estricto (Ranked: +-150 puntos)",
    "Searching": "Buscando",
    "Looking for an opponent": "Buscando un rival",
    "Searching for": "Buscando desde hace",
    "Stop searching": "Dejar de buscar",
    "In match": "En partida",
    "CASUAL": "CASUAL",
    "Input delay": "Input delay",
    "Connection": "Conexión",
    "Players online": "Jugadores online",
    "Challenge": "Desafiar",
    "Rooms": "Salas",
    "Create room": "Crear sala",
    "Join room": "Entrar a sala",
    "Leave room": "Salir de la sala",
    "Chat": "Chat",
    "Send": "Enviar",
    "Refresh": "Actualizar",
    "Order: rating minus twice its uncertainty (a few matches are needed to climb). '?' "
    "= provisional.":
        "Orden: puntos menos el doble de su incertidumbre (se necesitan algunas partidas para subir). “?” = "
        "provisional.",
    "Your account": "Tu cuenta",
    "Blocked players...": "Jugadores bloqueados...",
    "Change password...": "Cambiar contraseña...",
    "New recovery codes...": "Nuevos códigos de recuperación...",
    "Dismiss": "Ocultar",
    "Use a controller here": "Usar un control aquí",
    "none open": "ninguna abierta",
    "In your room “{name}”. Waiting for a second player...": "En tu sala “{name}”. Esperando a un segundo jugador...",
    "In the room “{name}”. The match starts when you are both ready.":
        "En la sala “{name}”. La partida empieza cuando ambos estén listos.",
    "Hosting. Friends type this as their Server:\n{share}":
        "Hosteando. Tus amigos escriben esto como su Servidor:\n{share}",
    "Same network: {lan}": "Misma red: {lan}",
    "Guest · casual matches": "Invitado · partidas casuales",
    "Rating {rating}  ·  {record}": "Puntos {rating}  ·  {record}",
    "Main: {character}": "Main: {character}",
    "Server ping {ms} ms": "Ping al servidor {ms} ms",
    "Create an account to play ranked": "Crea una cuenta para jugar Ranked",
    "Rated: close to your rank, good connection": "Con puntos: cerca de tu rango, buena conexión",
    "Similar rank and a good connection, strict: within 150 rating points (this can take "
    "a while).":
        "Rango parecido y buena conexión, estricto: a menos de 150 puntos (puede tardar).",
    "Similar rank and a good connection.": "Rango parecido y buena conexión.",
    "The opponent with the lowest ping first.": "Primero el rival con el ping más bajo.",
    "{ranked} in the ranked queue  ·  {quick} in quick match":
        "{ranked} en la búsqueda Ranked  ·  {quick} en Quick Match",
    "Character select": "Selección de personaje",
    "Stage select": "Selección de escenario",
    "Match over": "Partida terminada",
    "Waiting for the next match": "Esperando la siguiente partida",
    "Your game is running": "Tu juego está corriendo",
    "Starting the game...": "Iniciando el juego...",
    "Waiting for the game...": "Esperando al juego...",
    "vs your opponent": "contra tu rival",
    "vs {name}": "contra {name}",
    "{count} frame  ({ms} ms)": "{count} frame  ({ms} ms)",
    "{count} frames  ({ms} ms)": "{count} frames  ({ms} ms)",
    "Direct": "Directa",
    "Local network": "Red local",
    "Relay (lobby server)": "Relay (servidor del lobby)",
    "Relay ({name})": "Relay ({name})",
    "Guest": "Invitado",
    "{rank}  ·  rating {rating}": "{rank}  ·  {rating} puntos",
    "SET · GAME {game}": "SET · PARTIDA {game}",
    "Opponent hidden": "Rival oculto",
    "Name and side are shown once you both accept.": "El nombre y el lado se muestran cuando ambos acepten.",
    "(estimated before you connect)": "(estimado antes de conectar)",
    "Accepted. Waiting for your opponent...": "Aceptado. Esperando a tu rival...",
    "Match ready": "Partida lista",
    "Connecting the two games...": "Conectando los dos juegos...",
    "wants to play you. Accept to start the match.": "quiere jugar contigo. Acepta para empezar la partida.",
    "YOU WIN": "GANASTE",
    "YOU LOSE": "PERDISTE",
    "DRAW": "EMPATE",
    "MATCH OVER": "PARTIDA TERMINADA",
    "NO CONTEST": "SIN RESULTADO",
    "Casual match": "Partida casual",
    "ROUNDS  (P1 – P2)": "ROUNDS  (P1 – P2)",
    "ROUNDS  (YOU – THEM)": "ROUNDS  (TÚ – RIVAL)",
    "GAMES  (YOU – THEM)": "PARTIDAS  (TÚ – RIVAL)",
    "SET WON": "SET GANADO",
    "The game waits here for your next match: Rematch, Next game or Leave.":
        "El juego espera aquí tu próxima partida: Rematch, Siguiente partida o Salir.",
    "SET LOST": "SET PERDIDO",
    "Ranked set": "Set Ranked",
    "Ranked set vs {name}": "Set Ranked contra {name}",
    "RANKED SET · BEST OF {best}": "SET RANKED · AL MEJOR DE {best}",
    "Game {number} of {best} starts in": "La partida {number} de {best} empieza en",
    "Game {number} of {best} again (no winner), starts in":
        "Partida {number} de {best} otra vez (sin ganador), empieza en",
    "Rating {rating}": "Puntos {rating}",
    "PROMOTED": "ASCENSO",
    "DEMOTED": "DESCENSO",
    "PLACED": "CLASIFICADO",
    "Placement match {done} of {total}": "Partida de clasificación {done} de {total}",
    "Lag check": "Chequeo de lag",
    "Rematch offered. Waiting for {opp}...": "Rematch ofrecido. Esperando a {opp}...",
    "Back to the lobby": "Volver al lobby",
    "New recovery codes": "Nuevos códigos de recuperación",
    "Your account is ready": "Tu cuenta está lista",
    "These codes are the only way back into your account if you forget the password "
    "(there is no e-mail). Each code works once. Write them down or save them somewhere "
    "safe -- they are not shown again.":
        "Estos códigos son la única forma de volver a tu cuenta si olvidas la contraseña (no hay e-mail). Cada "
        "código sirve una vez. Anótalos o guárdalos en un lugar seguro -- no se vuelven a mostrar.",
    "Save to a file...": "Guardar en un archivo...",
    "I have saved them": "Ya los guardé",
    # ---- friends (tk_tab.py, tk_views.py)
    "Request": "Solicitud",
    "Friends": "Amigos",
    "Invite to a match": "Invitar a una partida",
    "Invite to my room": "Invitar a mi sala",
    "Invite in {seconds} s": "Invitar en {seconds} s",
    "Remove": "Quitar",
    "Invite a friend who is online: one click on their side starts a casual match, or brings them into your room.":
        "Invita a un amigo conectado: con un clic de su lado empieza una partida casual o entra a tu sala.",
    "Add a friend": "Agregar amigo",
    "Send request": "Enviar solicitud",
    "Their account name. They become your friend when they accept.": "Su nombre de cuenta. Serán amigos cuando acepte.",
    "Requests": "Solicitudes",
    "Take back": "Retirar",
    "Invite from a friend": "Invitación de un amigo",
    "invites you to the room “{room}”. Accept to join it; the match starts at once.":
        "te invita a la sala “{room}”. Acepta para entrar; la partida empieza de inmediato.",
    "invites you to a casual match. Accept to start it.": "te invita a una partida casual. Acepta para empezarla.",
    "Check the spelling: friends are added by their account name.":
        "Revisa cómo lo escribiste: los amigos se agregan por su nombre de cuenta.",
    "in a match": "en partida",
    "offline": "desconectado",
    "older launcher: no invites": "launcher viejo: sin invitaciones",
    "Friends ({count})": "Amigos ({count})",
    "offline, last seen {when}": "desconectado desde {when}",
    "Friends need an account. Log in with one to add friends and invite them.":
        "Los amigos necesitan una cuenta. Inicia sesión con una para agregar amigos e invitarlos.",
    "This lobby server has no friends list (it needs version 1.1.2 or newer).":
        "Este servidor de lobby no tiene lista de amigos (necesita la versión 1.1.2 o más nueva).",
    "wants to be your friend": "quiere ser tu amigo",
    "asked: waiting for an answer": "esperando respuesta",
    "{online} online · {count} of {max}": "{online} conectados · {count} de {max}",
    "Your friends see when you are online. Invite one who is online to play.":
        "Tus amigos ven cuándo estás conectado. Invita a uno que esté conectado para jugar.",
    "No friends yet. Add one by account name: they become your friend when they accept.":
        "Aún no tienes amigos. Agrega uno por su nombre de cuenta: serán amigos cuando acepte.",
    "Cancel the invite": "Cancelar la invitación",
    "You and {name} are friends now.": "Tú y {name} ya son amigos.",
    "Friend request sent to {name}. They become your friend when they accept.":
        "Solicitud de amistad enviada a {name}. Serán amigos cuando acepte.",
    "Request from {name} declined.": "Solicitud de {name} rechazada.",
    "Request to {name} taken back.": "Solicitud a {name} retirada.",
    "Remove friend": "Quitar amigo",
    "Remove {name} from your friends?\n\nYou can ask again later; they have to accept again.":
        "¿Quitar a {name} de tus amigos?\n\nPuedes volver a pedirlo después; tendrá que aceptar de nuevo.",
    "{name} is no longer your friend.": "{name} ya no es tu amigo.",
    "Select a friend in the list first.": "Primero elige un amigo de la lista.",
    "Invite sent to {name}; waiting for an answer ({seconds} s)...":
        "Invitación enviada a {name}; esperando respuesta ({seconds} s)...",
    "{name} ({rank}) invites you to the room “{room}”": "{name} ({rank}) te invita a la sala “{room}”",
    "{name} ({rank}) invites you to a casual match": "{name} ({rank}) te invita a una partida casual",
    "The invite from {name} ran out.": "La invitación de {name} expiró.",
    "The invite from {name} ended.": "La invitación de {name} terminó.",
    "{name} declined your invite.": "{name} rechazó tu invitación.",
    "{name} did not answer your invite.": "{name} no respondió a tu invitación.",
    "The invite to {name} ended.": "La invitación a {name} terminó.",
    "{name} wants to be your friend: see the Friends tab.": "{name} quiere ser tu amigo: mira la pestaña Amigos.",
    "{name} accepted your friend request.": "{name} aceptó tu solicitud de amistad.",
    "{name} declined your friend request.": "{name} rechazó tu solicitud de amistad.",

    # ---- launcher/replays_ui.py, launcher/t5dr_launcher.pyw (Replays tab), problem_report.py
    "Replays":
        "Replays",
    "Every online match is saved here. Watch plays it back in the game exactly as it was played: the same inputs frame by frame, checked against the live match while it plays.":
        "Cada partida online se guarda aquí. Ver la reproduce en el juego exactamente como se jugó: las mismas entradas cuadro por cuadro, comparadas con la partida en vivo mientras se reproduce.",
    "Date":
        "Fecha",
    "Fighters":
        "Peleadores",
    "Netcode":
        "Netcode",
    "WATCH":
        "VER",
    "Stop replay":
        "Detener replay",
    "Delete":
        "Borrar",
    "Open replays folder":
        "Abrir carpeta de replays",
    "While a replay plays: START (Enter) pauses and goes on, SELECT (Tab) ends the replay. A "
    "rematch is played after the matches before it in the same session: it starts from what they "
    "left.":
        "Mientras se reproduce un replay: START (Enter) pausa y sigue, SELECT (Tab) termina el replay. Una "
        "revancha se reproduce después de las partidas anteriores de la misma sesión: empieza desde donde "
        "ellas quedaron.",
    "Save online matches as replays":
        "Guardar las partidas online como replays",
    "Keep the players' names in replays":
        "Guardar los nombres de los jugadores en los replays",
    "Rollback":
        "Rollback",
    "Lockstep":
        "Lockstep",
    "(name not saved)":
        "(nombre no guardado)",
    "{matches} match(es) in {files} file(s) in {folder}":
        "{matches} partida(s) en {files} archivo(s) en {folder}",
    "No replays yet. Play an online match: it is saved here.":
        "Todavía no hay replays. Juega una partida online: se guarda aquí.",
    "not finished":
        "sin terminar",
    "won {mine}-{theirs}":
        "ganaste {mine}-{theirs}",
    "lost {mine}-{theirs}":
        "perdiste {mine}-{theirs}",
    "Close the running game first (Stop game on the Play tab).":
        "Primero cierra el juego abierto (Detener juego en la pestaña Jugar offline).",
    "Build the game first (Build tab).":
        "Primero compila el juego (pestaña Compilar).",
    "This replay cannot be played: {why}":
        "Este replay no se puede reproducir: {why}",
    "Recorded with another version of the game: it may not play back the same.":
        "Grabado con otra versión del juego: puede que no se reproduzca igual.",
    "Playing {fighters} ({when})...":
        "Reproduciendo {fighters} ({when})...",
    "The replay ended before the end of the match.":
        "El replay terminó antes del final de la partida.",
    "Replay over: identical to the live match ({checks} checks, same result).":
        "Replay terminado: idéntico a la partida en vivo ({checks} comprobaciones, mismo resultado).",
    "Replay over, but it went a different way from frame {frame} on (the game or its version differs from the one that played it).":
        "Replay terminado, pero desde el cuadro {frame} fue distinto (el juego o su versión no es el que la jugó).",
    "Replay over.":
        "Replay terminado.",
    "Delete this replay file? It holds {n} match(es) against the same opponent.":
        "¿Borrar este archivo de replay? Tiene {n} partida(s) contra el mismo rival.",
    # ---- lobby/t5lobby/tk_spectate.py, server/spectating.py, launcher Settings (spectating live matches)
    "Spectators":
        "Espectadores",
    "Friends and room visitors may watch my online matches":
        "Mis amigos y quien visite mi sala pueden ver mis partidas online",
    "Also my ranked matches":
        "También mis partidas Ranked",
    "They see the match a few seconds late, in their own game. Only when both players allow it; a "
    "ranked match only when both allow ranked too.":
        "Ven la partida unos segundos después, en su propio juego. Solo si los dos jugadores lo "
        "permiten; una partida Ranked solo si los dos permiten también Ranked.",
    "Watch":
        "Ver",
    "Spectating":
        "Viendo",
    "Stop watching":
        "Dejar de ver",
    "Watching":
        "Viendo en vivo",
    "Waiting for the match data...":
        "Esperando los datos de la partida...",
    "About {seconds} s behind the live match.":
        "Unos {seconds} s por detrás de la partida en vivo.",
    "It plays from the start of the players' session, a few seconds behind.":
        "Se ve desde el inicio de la sesión de los jugadores, unos segundos por detrás.",
    "Watching {p1} vs {p2}.":
        "Viendo {p1} vs {p2}.",
    "Spectators watching your match: {count}":
        "Espectadores de tu partida: {count}",
    "The live match is over.":
        "La partida en vivo ha terminado.",
    "The players turned spectators off.":
        "Los jugadores desactivaron los espectadores.",
    "The match data stopped coming.":
        "Los datos de la partida dejaron de llegar.",
    "This session is too long to watch from its start.":
        "Esta sesión es demasiado larga para verla desde el inicio.",
    "Your own match is starting.":
        "Empieza tu propia partida.",
    "The match data was damaged.":
        "Los datos de la partida estaban dañados.",
    "You stopped watching.":
        "Dejaste de ver la partida.",
    "A friend of the players took your place: the match has as many spectators as it can take.":
        "Un amigo de los jugadores ocupó tu lugar: la partida ya tiene todos los espectadores que admite.",
    "this launcher cannot watch matches; update it":
        "este launcher no puede ver partidas; actualízalo",
    "that match is not being played right now":
        "esa partida no se está jugando ahora",
    "you are playing in that match":
        "juegas en esa partida",
    "you are in a match yourself":
        "ya estás en una partida",
    "only friends of a player can watch this match":
        "solo los amigos de un jugador pueden ver esta partida",
    "the players do not allow spectators":
        "los jugadores no permiten espectadores",
    "neither player can send the match right now":
        "ahora ningún jugador puede enviar la partida",
    "this match cannot be watched any more":
        "esta partida ya no se puede ver",
    "this match has {count} spectators already":
        "esta partida ya tiene {count} espectadores",
    "the server cannot show more matches right now":
        "el servidor no puede mostrar más partidas ahora",
    "too many matches are watched from your network; stop watching one first":
        "desde tu red ya se ven demasiadas partidas; deja de ver una primero",
    "the places for guests at this match are taken; log in with an account to watch":
        "los lugares para invitados de esta partida están ocupados; inicia sesión con una cuenta para verla",
    "the server cannot show guests more matches right now; log in with an account to watch":
        "el servidor no puede mostrar más partidas a invitados ahora; inicia sesión con una cuenta para verlas",
    # firewall hint on the Online tab (t5lobby.fwcheck, tk_tab.fw_hint_text)
    "Firewall":
        "Firewall",
    "How to fix":
        "Cómo solucionarlo",
    "Windows Firewall blocks {program} on this network. Matches still connect, but some only "
    "through a relay, with more lag.":
        "El firewall de Windows bloquea {program} en esta red. Las partidas se conectan igual, "
        "pero algunas solo a través de un relay, con más lag.",
    "A firewall seems to block T5DR Online's network traffic on this PC.":
        "Parece que un firewall bloquea el tráfico de red de T5DR Online en este PC.",
    # patch 0063 (igpu-4k-stall): Internal resolution Auto, integrated-graphics and GPU-bound hints
    "Auto (matches the screen)":
        "Auto (según la pantalla)",
    "The game picks the step that matches your screen when it starts, at most 1080p on integrated graphics (they share the processor's memory and power).":
        "El juego elige al arrancar el nivel que corresponde a tu pantalla, como mucho 1080p con gráficos integrados (comparten la memoria y la energía del procesador).",
    "On this PC: {step}.":
        "En este PC: {step}.",
    "{step} on integrated graphics: try {better} for 60 fps.":
        "{step} con gráficos integrados: prueba {better} para 60 fps.",
    "Extra settings below set {setting}: that wins over this choice.":
        "Los ajustes extra de abajo ponen {setting}: eso manda sobre esta opción.",
    "Fights were slower than 60 fps because of the graphics (GPU-bound): choose a lower Internal resolution in Settings.":
        "Los combates fueron más lentos que 60 fps por los gráficos (limitado por la GPU): elige una resolución interna más baja en Ajustes.",
    "Fights were slower than 60 fps: the integrated graphics were busy and slowed the processor too. A lower Internal resolution in Settings helps.":
        "Los combates fueron más lentos que 60 fps: los gráficos integrados estaban ocupados y frenaron también el procesador. Una resolución interna más baja en Ajustes ayuda.",
    # ---- private and community rooms (lobby/t5lobby/tk_rooms.py; the server's messages: i18n_known.py)
    "private rooms need a newer launcher; update it": "las salas privadas necesitan un launcher más nuevo; actualízalo",
    "only the room's host can do that": "solo el anfitrión de la sala puede hacer eso",
    "too many wrong room passwords; try again in {seconds} s":
        "demasiadas contraseñas de sala incorrectas; inténtalo de nuevo en {seconds} s",
    "wrong room password": "contraseña de sala incorrecta",
    "the room's password changed; try again": "la contraseña de la sala cambió; inténtalo de nuevo",
    "no room has that invite code": "ninguna sala tiene ese código de invitación",
    "rooms hold 2 to {count} players": "las salas admiten de 2 a {count} jugadores",
    "room passwords are 4-64 characters, no space at either end":
        "las contraseñas de sala tienen 4-64 caracteres, sin espacios al principio ni al final",
    "private and community rooms are casual (unranked)": "las salas privadas y de comunidad son casual (sin Ranked)",
    "you are in that room": "ya estás en esa sala",
    "the room's host removed you from this room": "el anfitrión te sacó de esta sala",
    "the room's host turned away password guesses from your network; ask the host for an invite":
        "el anfitrión de la sala rechazó los intentos de contraseña desde tu red; pídele una invitación",
    "only a room with a password counts wrong guesses": "solo una sala con contraseña cuenta los intentos fallidos",
    "that player is not in your room": "ese jugador no está en tu sala",
    "you cannot remove yourself; leave the room instead": "no puedes sacarte a ti mismo; mejor sal de la sala",
    "you can remove that player after their match": "puedes sacar a ese jugador después de su partida",
    "only rooms for 3 or more players take turns": "solo las salas de 3 o más jugadores se turnan",
    "you sit out in the room; press Back in line to play again":
        "estás fuera de turno en la sala; pulsa Volver a la fila para jugar de nuevo",
    "the room picks the next match by itself": "la sala elige la siguiente partida por sí sola",
    "the room's host removed that player from this room": "el anfitrión sacó a ese jugador de esta sala",
    "only the room's players can watch its match": "solo los jugadores de la sala pueden ver su partida",
    "Anybody": "Cualquiera",
    "Back in line": "Volver a la fila",
    "Back in line: you play when it is your turn.": "De vuelta en la fila: juegas cuando sea tu turno.",
    "Copy invite code": "Copiar código de invitación",
    "Create a room": "Crear una sala",
    "Everyone in turn": "Todos por turnos",
    "Hide the room from the room list": "Ocultar la sala de la lista de salas",
    "In the room “{name}”: {count}/{size} players, taking turns.":
        "En la sala “{name}”: {count}/{size} jugadores, por turnos.",
    "Invite code": "Código de invitación",
    "Line: {names}": "Fila: {names}",
    "New invite code": "Nuevo código de invitación",
    "Next: {p1} vs {p2} in {seconds} s": "Siguiente: {p1} vs {p2} en {seconds} s",
    "No room selected. Join a room with its invite code (XXXX-XXXX-XXXX):":
        "No hay sala elegida. Entra a una sala con su código de invitación (XXXX-XXXX-XXXX):",
    "Password (4-64 characters):": "Contraseña (4-64 caracteres):",
    "Players in the room:": "Jugadores en la sala:",
    "Players:": "Jugadores:",
    "Playing: {p1} vs {p2}": "Jugando: {p1} vs {p2}",
    "Private (invite code)": "Privada (código de invitación)",
    "Private (password)": "Privada (contraseña)",
    "Remove player": "Sacar jugador",
    "Remove {name} from the room? They cannot come back into it.":
        "¿Sacar a {name} de la sala? No podrá volver a entrar.",
    "Removed {name} from the room.": "{name} fue sacado de la sala.",
    "Wrong passwords in the last 10 minutes: {count} (networks: {networks})":
        "Contraseñas incorrectas en los últimos 10 minutos: {count} (redes: {networks})",
    "Turn away the guessers": "Rechazar a quienes adivinan",
    "Networks turned away: {count}. They cannot try passwords on this room any more.":
        "Redes rechazadas: {count}. Ya no pueden probar contraseñas en esta sala.",
    "Room created.": "Sala creada.",
    "Room created. Press Copy invite code to see the code you can share.":
        "Sala creada. Pulsa Copiar código de invitación para ver el código que puedes compartir.",
    "Room name (optional):": "Nombre de la sala (opcional):",
    "Room password": "Contraseña de la sala",
    "Room passwords are 4-64 characters, with no space at the start or end.":
        "Las contraseñas de sala tienen 4-64 caracteres, sin espacios al principio ni al final.",
    "Room settings": "Ajustes de la sala",
    "Room settings saved.": "Ajustes de la sala guardados.",
    "Room settings...": "Ajustes de la sala...",
    "Sit out": "Pasar turno",
    "The invite code is in the field next to the button: select it and press Ctrl+C to copy it.":
        "El código de invitación está en el campo junto al botón: selecciónalo y pulsa Ctrl+C para copiarlo.",
    "The room's invite code (XXXX-XXXX-XXXX):": "Código de invitación de la sala (XXXX-XXXX-XXXX):",
    "Turns (3 or more players):": "Turnos (3 o más jugadores):",
    "Who can join:": "Quién puede entrar:",
    "Winner stays": "El ganador se queda",
    "You sit out: your turns are skipped until you press Back in line.":
        "Pasas turno: tus turnos se saltan hasta que pulses Volver a la fila.",
    "Your room: {name}": "Tu sala: {name}",
    "hidden": "oculta",
    "invites you to the private room “{room}”. Accept to join it without its password.":
        "te invita a la sala privada “{room}”. Acepta para entrar sin su contraseña.",
    "private": "privada",
    "private (invite code)": "privada (código de invitación)",
    "private (password)": "privada (contraseña)",
    "{count}/{size} players": "{count}/{size} jugadores",
    "{name} (host)": "{name} (anfitrión)",
    "{name} (sitting out)": "{name} (fuera de turno)",
    "{name} ({rank}) invites you to the private room “{room}”": "{name} ({rank}) te invita a la sala privada “{room}”",
    "“{room}” is private. Its password:": "“{room}” es privada. Su contraseña:",
    "this server has no private rooms": "este servidor no tiene salas privadas",
}
