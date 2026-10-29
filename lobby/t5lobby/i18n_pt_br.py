"""Brazilian Portuguese texts for the launcher and the Online tab (t5lobby/i18n.py).

English text -> Brazilian Portuguese text. The English text is the key, exactly as written in
t("...") / N_("..."); the Portuguese one keeps the same {placeholders}. Brazilian Portuguese with
"você", short and the way players talk ("controle", "partida"). Names players know from the game and
the lobby stay as they are: Quick Match, Ranked, BUILD GAME, Rematch, Rollback, lobby, input delay, ping,
the character and rank names.

Machine-assisted translation: corrections from players are welcome (docs/ONLINE.md "Languages").
Same keys and groups as i18n_de.py; tests/test_i18n.py and tools/i18n_extract.py check every catalog.
"""

MESSAGES = {
    # ---- launcher/controls_edit.py
    "Removed {sources} from your buttons: that is L2 / R2 at rest on a PlayStation pad, so the game held them all the time. Save to keep this.":
        "{sources} removido dos seus botões: é o L2 / R2 em repouso num controle de PlayStation, então o jogo os mantinha apertados o tempo todo. Salve para manter.",
    "Attack buttons": "Botões de ataque",
    "Several buttons with one press (macros)": "Vários botões num toque (macros)",
    "Start, Select and the other buttons": "Start, Select e os outros botões",
    "Directions": "Direções",
    "1 (Left Punch)": "1 (Soco esquerdo)",
    "2 (Right Punch)": "2 (Soco direito)",
    "3 (Left Kick)": "3 (Chute esquerdo)",
    "4 (Right Kick)": "4 (Chute direito)",
    "Select": "Select",
    "Start / pause": "Start / pausa",
    "Down": "Baixo",
    "Left": "Esquerda",
    "Up": "Cima",
    "Right": "Direita",
    "PlayStation pad, default": "Controle PlayStation, padrão",
    "Xbox pad, default": "Controle Xbox, padrão",
    "X Y A B are 1 2 3 4; bumpers and triggers are L1 R1 L2 R2.":
        "X Y A B são 1 2 3 4; bumpers e gatilhos são L1 R1 L2 R2.",
    "Square Triangle Cross Circle are 1 2 3 4 (DualShock 4, DualSense and most "
    "PS3/PS4-mode sticks).":
        "Quadrado Triângulo X Bola são 1 2 3 4 (DualShock 4, DualSense e a maioria dos sticks no modo PS3/PS4).",
    "Switch pad, default": "Controle Switch, padrão",
    "Y X B A are 1 2 3 4 (Switch Pro controller, sticks in Switch mode).":
        "Y X B A são 1 2 3 4 (controle Switch Pro, sticks no modo Switch).",
    "Xbox-style pad (generic)": "Controle estilo Xbox (genérico)",
    "A B X Y buttons and LB RB, for Xbox-like pads that Windows does not give to XInput.":
        "Botões A B X Y e LB RB, para controles tipo Xbox que o Windows não passa para o XInput.",
    "8-button stick (Vewlix layout)": "Stick de 8 botões (layout Vewlix)",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: X Y RB LB over A B RT LT.":
        "Fileira de cima 1 2 [1+2] [1+3], de baixo 3 4 [3+4] [2+4]: X Y RB LB sobre A B RT LT.",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: B1 B4 B6 B5 over B2 B3 B8 B7.":
        "Fileira de cima 1 2 [1+2] [1+3], de baixo 3 4 [3+4] [2+4]: B1 B4 B6 B5 sobre B2 B3 B8 B7.",
    "6-button stick (Noir / Sega Astro)": "Stick de 6 botões (Noir / Sega Astro)",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: X Y RB over A B RT. LB and LT stay L1 and "
    "L2.":
        "Fileira de cima 1 2 [1+2], de baixo 3 4 [3+4]: X Y RB sobre A B RT. LB e LT continuam L1 e L2.",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: B1 B4 B6 over B2 B3 B8. B5 and B7 stay L1 "
    "and L2.":
        "Fileira de cima 1 2 [1+2], de baixo 3 4 [3+4]: B1 B4 B6 sobre B2 B3 B8. B5 e B7 continuam L1 e L2.",
    "Hitbox": "Hitbox",
    "The 8-button layout above. Directions come from the d-pad or the left stick, which "
    "is read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "O layout de 8 botões acima. As direções vêm do direcional ou do analógico esquerdo, lido como direcional de "
        "8 direções; esquerda+direita (cima+baixo) juntos se anulam.",
    "The 8-button layout above. Directions come from the hat or the left stick, which is "
    "read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "O layout de 8 botões acima. As direções vêm do hat ou do analógico esquerdo, lido como direcional de 8 "
        "direções; esquerda+direita (cima+baixo) juntos se anulam.",
    "The file has {n} settings; the game reads at most {max}.":
        "O arquivo tem {n} configurações; o jogo lê no máximo {max}.",
    "The file has {n} sections; the game reads at most {max}.": "O arquivo tem {n} seções; o jogo lê no máximo {max}.",
    "Changed lines of {sections} that would have overridden this ({what}).":
        "Linhas alteradas de {sections} que teriam sobrescrito isto ({what}).",
    "Lines of your file in other sections still change some buttons.":
        "Linhas do seu arquivo em outras seções ainda mudam alguns botões.",
    "Other lines in your file ({sections}) still change this layout.":
        "Outras linhas do seu arquivo ({sections}) ainda mudam este layout.",
    "{n} lines removed.": "{n} linhas removidas.",
    # ---- launcher/controls_ui.py
    "DirectInput controller": "Controle DirectInput",
    "Xbox pad (XInput)": "Controle Xbox (XInput)",
    "PlayStation pad, read directly": "Controle PlayStation, lido diretamente",
    "Arrows move; A S on top are 1 2, Z X below are 3 4. Q W are L1 R1, 1 2 are L2 R2, Enter is Start, Tab is Select.": "As setas movem; A S em cima são 1 2, Z X embaixo são 3 4. Q W são L1 R1, 1 2 são L2 R2, Enter é Start, Tab é Select.",
    "Arrows move; number pad 4 5 are 1 2, 1 2 are 3 4, 6 is 1+2, 3 is 3+4 (Num Lock on).": "As setas movem; teclado numérico 4 5 são 1 2, 1 2 são 3 4, 6 é 1+2, 3 é 3+4 (Num Lock ligado).",
    "Esc (leaves the game)": "Esc (sai do jogo)",
    "F11 (fullscreen)": "F11 (tela cheia)",
    "F2 (training overlay)": "F2 (painel de treino)",
    "Keyboard, second player": "Teclado, segundo jogador",
    "Keyboard: WASD and U I J K": "Teclado: WASD e U I J K",
    "Keyboard: arrows and A S Z X": "Teclado: setas e A S Z X",
    "Keyboard: arrows and number pad": "Teclado: setas e teclado numérico",
    'Keyboard: pick a game button, then Set selected (or double-click it) and press the key. Esc stops. The game reads the keyboard while its window has the focus.': 'Teclado: escolha um botão do jogo, depois "Configurar selecionado" (ou clique duplo) e aperte a tecla. Esc para. O jogo lê o teclado enquanto a janela dele tem o foco.',
    "Press only that one key. Esc stops.": "Aperte só essa tecla. Esc para.",
    "Press the key for {button}...": "Aperte a tecla para {button}...",
    "The keyboard ([{section}] in controls.ini)": "O teclado ([{section}] no controls.ini)",
    "W A S D move; U I are 1 2, J K are 3 4, O is 1+2, L is 3+4. Y P are L1 R1, H and ; are L2 R2, Enter is Start, Backspace is Select.": "W A S D movem; U I são 1 2, J K são 3 4, O é 1+2, L é 3+4. Y P são L1 R1, H e ; são L2 R2, Enter é Start, Backspace é Select.",
    "{key} is the game's own key; press another one.": '{key} é uma tecla do próprio jogo; aperte outra.',
    "{source} is also {other} for the second keyboard player.": "{source} também é {other} para o segundo jogador do teclado.",
    "Controls - T5DR Online": "Controles - T5DR Online",
    "Press a button on a controller to pick it, then set its buttons. The game reads the "
    "file when it starts.":
        "Aperte um botão em um controle para escolhê-lo e depois configure os botões. O jogo lê o arquivo ao iniciar.",
    "Controllers": "Controles",
    "Player": "Jogador",
    "Controller": "Controle",
    "Pressed now": "Pressionado agora",
    "Move through this window with the controller": "Usar esta janela com o controle",
    "Buttons": "Botões",
    "Game button": "Botão do jogo",
    "Controller button": "Botão do controle",
    "Set up all buttons": "Configurar todos os botões",
    "Set up directions": "Configurar direções",
    "Set selected": "Configurar selecionado",
    "Clear": "Limpar",
    "Layout": "Layout",
    "Use this layout": "Usar este layout",
    "Reset to defaults": "Restaurar padrão",
    "Your changes apply to": "Suas mudanças valem para",
    "Player and directions": "Jogador e direções",
    "Automatic": "Automático",
    "Player 1": "Jogador 1",
    "Player 2": "Jogador 2",
    "8-way d-pad": "Direcional de 8 direções",
    "Analog stick": "Analógico",
    "Both cancel (neutral)": "Ambos se anulam (neutro)",
    "Up wins (Up+Down is Up)": "Cima vence (Cima+Baixo é Cima)",
    "Last direction wins": "Última direção vence",
    "Pass both through": "Deixar passar as duas",
    "This controller is": "Este controle é",
    "Left stick": "Analógico esquerdo",
    "Opposite directions": "Direções opostas",
    "Left stick, 8-way d-pad: a hitbox or stick in left-stick mode sends the direction "
    "as a stick; the game then reads it as d-pad presses. Left+Right (or Up+Down) at "
    "once happens on keyboards and hitboxes; the game cannot take both. Stick and "
    "opposite directions belong to the player's port.":
        "Analógico esquerdo, direcional de 8 direções: um hitbox ou stick no modo analógico esquerdo envia a direção "
        "como analógico; o jogo a lê como direcional. Esquerda+Direita (ou Cima+Baixo) juntos acontece em teclados e "
        "hitboxes; o jogo não aceita os dois. Analógico e direções opostas pertencem à porta do jogador.",
    "Skip": "Pular",
    "Stop": "Parar",
    "Save": "Salvar",
    "Revert": "Descartar",
    "Close": "Fechar",
    "no controller": "sem controle",
    "Controllers cannot be read on this PC.": "Não é possível ler controles neste PC.",
    "No controller found. Plug one in; it shows up here by itself.":
        "Nenhum controle encontrado. Conecte um; ele aparece aqui sozinho.",
    "switched off in [general]": "desligado em [general]",
    "no free player port": "nenhuma porta de jogador livre",
    "No controller chosen": "Nenhum controle escolhido",
    "This controller model ({vid}:{pid})": "Este modelo de controle ({vid}:{pid})",
    "This controller model (no USB ID)": "Este modelo de controle (sem ID USB)",
    "All DirectInput controllers": "Todos os controles DirectInput",
    "All Xbox pads (XInput)": "Todos os controles Xbox (XInput)",
    "Only the controller on player {n}'s port": "Só o controle na porta do jogador {n}",
    "no player": "sem jogador",
    "player {n}": "jogador {n}",
    "yours": "seu",
    "Your own layout": "Seu próprio layout",
    "Player {n}": "Jogador {n}",
    "Buttons you set yourself, or a mix. Pick a layout to start from it.":
        "Botões que você configurou, ou uma mistura. Escolha um layout para começar a partir dele.",
    "On the controller: {up} / {down} choose a button, {accept} sets it, {clear} clears "
    "it, {save} saves, {back} closes. The game reads the file when it starts.":
        "No controle: {up} / {down} escolhem um botão, {accept} configura, {clear} limpa, {save} salva, {back} "
        "fecha. O jogo lê o arquivo ao iniciar.",
    "(no game button)": "(sem botão do jogo)",
    "Press a button on a controller first, or pick one in the list.":
        "Primeiro aperte um botão em um controle, ou escolha um na lista.",
    "Press the button for {button}...": "Aperte o botão para {button}...",
    "Press only that one button on the controller.": "Aperte só esse botão no controle.",
    "{n} of {total}.": "{n} de {total}.",
    "Wait a few seconds to skip it.": "Espere alguns segundos para pular.",
    "That was several buttons at once ({sources}). Press one button only.":
        "Foram vários botões ao mesmo tempo ({sources}). Aperte só um.",
    "{button}: skipped.": "{button}: pulado.",
    "{button} = {source}.": "{button} = {source}.",
    "{source} was {other}; that one has no button now.": "{source} era {other}; esse agora está sem botão.",
    "Stopped.": "Parado.",
    "{button}: cleared.": "{button}: limpo.",
    "Layout: {name}.": "Layout: {name}.",
    "Pick a layout in the list first.": "Primeiro escolha um layout na lista.",
    "Put {name} back to the default buttons? Your comments and other settings in "
    "controls.ini stay.":
        "Voltar {name} para os botões padrão? Seus comentários e outras configurações no controls.ini continuam.",
    "The part of the file that is for all {kind} controllers has button lines too. Reset "
    "those as well?":
        "A parte do arquivo para todos os controles {kind} também tem linhas de botões. Restaurar essas também?",
    "Reset to the defaults. Save to keep it.": "Restaurado ao padrão. Salve para manter.",
    "{name} is {player}. Save to keep it.": "{name} é {player}. Salve para manter.",
    "controls.ini changed": "controls.ini mudou",
    "controls.ini was changed by something else since this screen opened. Overwrite it "
    "with your settings? (The old file is kept as controls.ini.bak.)":
        "O controls.ini foi alterado por outra coisa desde que esta tela abriu. Sobrescrever com suas configurações? "
        "(O arquivo antigo fica como controls.ini.bak.)",
    "Could not save: {error}": "Não foi possível salvar: {error}",
    "Saved {path}. The game reads it when it starts.": "{path} salvo. O jogo lê ao iniciar.",
    "The game that is running keeps its old buttons until you start it again.":
        "O jogo em execução mantém os botões antigos até você reiniciá-lo.",
    "Changes undone.": "Mudanças descartadas.",
    "There are unsaved changes. Save them first, or close with the mouse.":
        "Há mudanças não salvas. Salve primeiro, ou feche com o mouse.",
    "Controls": "Controles",
    "Save the changes to controls.ini?": "Salvar as mudanças no controls.ini?",
    # ---- launcher/core.py
    "Auto (laptops, handhelds, integrated graphics)": "Auto (notebooks, portáteis, gráficos integrados)",
    "On": "Ligado",
    "a mobile processor": "um processador móvel",
    "battery saver is on": "a economia de bateria do Windows está ligada",
    "the Power saver power plan is on": "o plano de energia “Economia de energia” está ativo",
    "this PC has a battery (laptop or handheld)": "este PC tem bateria (notebook ou portátil)",
    "Inputs": "Inputs",
    "Inputs + frame data": "Inputs + dados de frame",
    "Auto (Windows language)": "Auto (idioma do Windows)",
    "No package chosen.": "Nenhum pacote escolhido.",
    "File not found.": "Arquivo não encontrado.",
    "Cannot read the file: {error}": "Não é possível ler o arquivo: {error}",
    "This is not a PS3 package (.pkg).": "Isto não é um pacote de PS3 (.pkg).",
    "{id}  ({size} bytes) -- the supported version": "{id}  ({size} bytes) -- a versão suportada",
    "{id}  ({size} bytes) -- the European version: it plays offline only for now. Online play for it comes in a later update.":
        "{id}  ({size} bytes) -- a versão europeia: por enquanto ela só roda offline. O jogo online para ela virá em uma atualização futura.",
    "checking the game version inside the package…": "verificando a versão do jogo dentro do pacote…",
    "{id}  ({size} bytes) -- Tekken 5 DR, but not the supported package ({supported}). "
    "The build will most likely refuse it.":
        "{id}  ({size} bytes) -- Tekken 5 DR, mas não o pacote suportado ({supported}). A compilação provavelmente "
        "vai recusá-lo.",
    "{id}  ({size} bytes) -- not Tekken 5 DR Online ({title_id}).":
        "{id}  ({size} bytes) -- não é Tekken 5 DR Online ({title_id}).",
    "No license chosen.": "Nenhuma licença escolhida.",
    "Not a PS3 license: a .rap file is exactly 16 bytes.":
        "Não é uma licença de PS3: um arquivo .rap tem exatamente 16 bytes.",
    "{name} -- matches the supported package": "{name} -- corresponde ao pacote suportado",
    "{name} -- matches the package": "{name} -- corresponde ao pacote",
    "{name} -- the name does not match the package's content ID; it may be the wrong "
    "license.":
        "{name} -- o nome não corresponde ao content ID do pacote; pode ser a licença errada.",
    "The output folder": "A pasta de saída",
    "This folder": "Esta pasta",
    "{label} has a long path ({bytes} bytes). Windows allows only {max} characters for a "
    "file path, and the build writes files about {room} characters deeper. Move the "
    "folder to a short path, for example {example}.":
        "{label} tem um caminho longo ({bytes} bytes). O Windows permite só {max} caracteres no caminho de um "
        "arquivo, e a compilação grava arquivos cerca de {room} caracteres mais fundo. Mova a pasta para um caminho "
        "curto, por exemplo {example}.",
    "This folder is inside OneDrive. OneDrive would upload about 1 GB of game data and "
    "can lock files while the game is built. Move the folder out of OneDrive, for "
    "example to {example}.":
        "Esta pasta está dentro do OneDrive. O OneDrive enviaria cerca de 1 GB de dados do jogo e pode travar "
        "arquivos enquanto o jogo é compilado. Tire a pasta do OneDrive, por exemplo para {example}.",
    "This folder is in Program Files, where Windows does not let programs write. Move it "
    "to a folder of your own, for example {example}.":
        "Esta pasta está em Program Files (Arquivos de Programas), onde o Windows não deixa programas gravarem. "
        "Mova-a para uma pasta sua, por exemplo {example}.",
    "Windows does not let the launcher write into this folder. Move it to a folder of "
    "your own, for example {example}.":
        "O Windows não deixa o launcher gravar nesta pasta. Mova-a para uma pasta sua, por exemplo {example}.",
    "This folder is on a network share. Building and playing from there is slow and was "
    "not tested; copy it to a local drive.":
        "Esta pasta está em um compartilhamento de rede. Compilar e jogar a partir dela é lento e não foi testado; "
        "copie-a para um disco local.",
    "The game is not built yet. Open the Build tab, choose your .pkg and .rap, press "
    "BUILD GAME.":
        "O jogo ainda não foi compilado. Abra a aba Compilar, escolha seu .pkg e .rap e aperte BUILD GAME.",
    "t5dr.exe is there but the game data is missing. Build again.":
        "O t5dr.exe está lá, mas faltam os dados do jogo. Compile de novo.",
    "The decrypted program has SHA-1 {sha}..., not the supported version. Build again "
    "from the supported package.":
        "O programa descriptografado tem SHA-1 {sha}..., não é a versão suportada. Compile de novo com o pacote "
        "suportado.",
    "Build the game once (about 2 minutes): this version of the launcher changes the "
    "game code. Click BUILD GAME. Your unpacked game and saves are kept; only the code "
    "is translated and compiled again.":
        "Compile o jogo uma vez (cerca de 2 minutos): esta versão do launcher muda o código do jogo. Clique em BUILD "
        "GAME. Seu jogo descompactado e seus saves continuam; só o código é traduzido e compilado de novo.",
    "Ready: {title_id} v{version}, program SHA-1 {sha}... verified, built {when}.":
        "Pronto: {title_id} v{version}, SHA-1 do programa {sha}... verificado, compilado {when}.",
    "Check & decrypt": "Verificar e decifrar",
    "Key data": "Dados de chaves",
    "Recompiler": "Recompilador",
    "Unpack": "Extrair",
    "Compile": "Compilar",
    "Game files": "Arquivos do jogo",
    "Sound core": "Núcleo de som",
    "Shaders": "Shaders",
    "Translate code": "Traduzir código",
    "The translation step has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, close other programs, press Cancel and then BUILD GAME again; build.log "
    "has the details.":
        "A etapa “Traduzir código” não mostrou nada há {minutes} minutos. Num PC lento ou ocupado ela ainda pode "
        "estar trabalhando. Se nada mudar, feche outros programas, clique em Cancelar e depois em BUILD GAME de "
        "novo; o build.log tem os detalhes.",
    "The graphics card stopped working for the game (the driver crashed, was reset or "
    "updated). Start the game again. If it happens again, update the graphics driver.":
        "A placa de vídeo parou de funcionar para o jogo (o driver travou, foi reiniciado ou atualizado). Abra o "
        "jogo de novo. Se acontecer de novo, atualize o driver de vídeo.",
    "This PC's graphics card or driver cannot run Direct3D 12. Install the newest "
    "graphics driver from AMD, Intel or NVIDIA.":
        "A placa de vídeo ou o driver deste PC não roda Direct3D 12. Instale o driver de vídeo mais recente da AMD, "
        "Intel ou NVIDIA.",
    "This processor is too old for the game: it lacks the SSE4.1 instructions "
    "(processors from about 2008 on have them).":
        "Este processador é antigo demais para o jogo: faltam as instruções SSE4.1 (processadores de 2008 em diante "
        "têm).",
    "The game was built on a PC with a newer processor (AVX2). Press BUILD GAME to build "
    "it again for this PC; your saves are kept.":
        "O jogo foi compilado em um PC com processador mais novo (AVX2). Aperte BUILD GAME para compilar de novo "
        "para este PC; seus saves continuam.",
    "t5dr_game.dll could not be loaded (missing or blocked). Press BUILD GAME again, and "
    "look in the antivirus quarantine.":
        "Não foi possível carregar o t5dr_game.dll (faltando ou bloqueado). Aperte BUILD GAME de novo e olhe a "
        "quarentena do antivírus.",
    "The game could not get back to character select after the last match and closed "
    "itself. It starts again for your next match.":
        "O jogo não conseguiu voltar à seleção de personagem após a última partida e se fechou. Ele abre de novo "
        "para sua próxima partida.",
    "The game stopped after a crash (exit code {code}). The game log has the details.":
        "O jogo parou depois de um crash (código de saída {code}). O log do jogo tem os detalhes.",
    "The game stopped (exit code {code}). The game log has the details.":
        "O jogo parou (código de saída {code}). O log do jogo tem os detalhes.",
    "t5dr.exe is not built yet": "t5dr.exe ainda não foi compilado",
    "Lowest (0.5x)": "Mínima (0,5x)",
    "Lower (0.75x)": "Baixa (0,75x)",
    "Native (720p)": "Nativa (720p)",
    "1080p (1.5x)": "1080p (1,5x)",
    "1440p (2x)": "1440p (2x)",
    "4K (3x)": "4K (3x)",
    "The 3D scene at half size (a quarter of its pixels); HUD and text stay sharp. "
    "For integrated graphics and old laptops.":
        "A cena 3D na metade do tamanho (um quarto dos pixels); HUD e texto continuam nítidos. Para gráficos "
        "integrados e notebooks antigos.",
    "The 3D scene at 3/4 size (about half of its pixels); HUD and text stay sharp. "
    "For weak graphics cards.":
        "A cena 3D em 3/4 do tamanho (cerca de metade dos pixels); HUD e texto continuam nítidos. Para placas de "
        "vídeo fracas.",
    "The PS3's 1280 x 720. Light on any graphics card; the picture is scaled to your window.":
        "Os 1280 x 720 do PS3. Leve para qualquer placa de vídeo; a imagem é ajustada à sua janela.",
    "1920 x 1080: 2.25x the pixels of Native. Sharp on Full HD screens. "
    "If fights drop below 60 fps, go one step down.":
        "1920 x 1080: 2,25x os pixels da Nativa. Nítido em telas Full HD. Se as lutas caírem abaixo de 60 fps, desça "
        "um nível.",
    "2560 x 1440: 4x the pixels of Native. For strong graphics cards. "
    "If fights drop below 60 fps, go one step down.":
        "2560 x 1440: 4x os pixels da Nativa. Para placas de vídeo fortes. Se as lutas caírem abaixo de 60 fps, "
        "desça um nível.",
    "3840 x 2160: 9x the pixels of Native. For very strong graphics cards "
    "(an RTX 3090 needs 1-2 ms of a 16.7 ms frame). If fights drop below 60 fps, go one step down.":
        "3840 x 2160: 9x os pixels da Nativa. Para placas de vídeo muito fortes (uma RTX 3090 usa 1-2 ms de um frame "
        "de 16,7 ms). Se as lutas caírem abaixo de 60 fps, desça um nível.",
    "Auto (by ping)": "Auto (pelo ping)",
    "Window, 1280 x 720 (native; larger with Windows display scaling)":
        "Janela, 1280 x 720 (nativa; maior com a escala de tela do Windows)",
    "Window, 1920 x 1080": "Janela, 1920 x 1080",
    "Window, 2560 x 1440": "Janela, 2560 x 1440",
    "Maximized window": "Janela maximizada",
    "Borderless fullscreen (Alt+Enter or F11 switches in the game)":
        "Tela cheia sem bordas (Alt+Enter ou F11 alterna no jogo)",
    # ---- launcher/online.py
    "Online play": "Jogo online",
    "The lobby files (lobby/t5lobby) are missing from this copy of the launcher, so "
    "online play is not available.\n\n({reason})":
        "Os arquivos do lobby (lobby/t5lobby) estão faltando nesta cópia do launcher, então o jogo online não está "
        "disponível.\n\n({reason})",
    # ---- launcher/problem_report_ui.py
    "Before the zip is made, your Windows user name in file paths becomes <user>, "
    "internet IP addresses become <ip> (addresses of your own network stay), lobby player "
    "names (yours and your opponents') become <player>, and passwords, tokens and match keys "
    "are left out. Your game files, keys, .pkg and .rap are never included. Nothing is "
    "uploaded: you send the zip yourself.":
        "Antes de criar o zip, seu nome de usuário do Windows nos caminhos vira <user>, endereços IP da internet "
        "viram <ip> (os da sua própria rede ficam), nomes de jogadores do lobby (o seu e os dos oponentes) viram "
        "<player>, e senhas, tokens e chaves de partida ficam de fora. Seus arquivos do jogo, chaves, .pkg e .rap "
        "nunca são incluídos. Nada é enviado: você mesmo manda o zip.",
    "{count} bytes": "{count} bytes",
    "Report a problem": "Relatar um problema",
    "This makes one zip file on your Desktop with the logs and settings that help to "
    "find the problem. Send the zip to the person who gave you the game, or attach it to "
    "an issue.":
        "Isto cria um arquivo zip na sua Área de Trabalho com os logs e configurações que ajudam a achar o problema. "
        "Mande o zip para a pessoa que te passou o jogo, ou anexe-o a uma issue.",
    "What happened? (optional)": "O que aconteceu? (opcional)",
    "What goes into the zip": "O que vai no zip",
    "Nothing found yet: no game log, no build log.":
        "Nada encontrado ainda: nenhum log do jogo, nenhum log de compilação.",
    "Could not look at the files: {error}": "Não foi possível ver os arquivos: {error}",
    "Save report on the Desktop": "Salvar o relatório na Área de Trabalho",
    "Cancel": "Cancelar",
    "About {size} before it is packed (a zip is smaller).": "Cerca de {size} antes de compactar (o zip é menor).",
    "About {size}; the limit is {limit}, so the biggest logs are shortened in the "
    "middle.":
        "Cerca de {size}; o limite é {limit}, então os maiores logs são encurtados no meio.",
    "Making the report...": "Criando o relatório...",
    "The report could not be made: {error}": "Não foi possível criar o relatório: {error}",
    "Report saved": "Relatório salvo",
    "{size}. Its folder is open.": "{size}. A pasta dele está aberta.",
    "Send this zip to the person who gave you the game, or attach it to an issue at "
    "{url}.":
        "Mande este zip para a pessoa que te passou o jogo, ou anexe-o a uma issue em {url}.",
    "Send this zip to the person who gave you the game.": "Mande este zip para a pessoa que te passou o jogo.",
    "(shortened in the middle)": "(encurtado no meio)",
    "{name}   left out: {reason}": "{name}   deixado de fora: {reason}",
    "Removed from the text files: {user} user or PC names, {ip} IP addresses, {secret} "
    "passwords, tokens or keys, {email} e-mail addresses.":
        "Removido dos arquivos de texto: {user} nomes de usuário ou de PC, {ip} endereços IP, {secret} senhas, "
        "tokens ou chaves, {email} endereços de e-mail.",
    "Open folder": "Abrir pasta",
    # ---- launcher/t5dr_launcher.pyw
    "Discord": "Discord",
    "Show what I play in my Discord status (Rich Presence)":
        "Mostrar o que estou jogando no meu status do Discord (Rich Presence)",
    "\"In lobby\", \"Searching ranked\" or your match (fighters, ranked set score) with a timer, through the "
    "Discord app on this PC. Without Discord running nothing happens.":
        "“No lobby”, “Procurando Ranked” ou sua partida (lutadores, placar do set Ranked) com um cronômetro, pelo "
        "app do Discord neste PC. Sem o Discord aberto, nada acontece.",
    "Power saving (laptops, handhelds)": "Economia de energia (notebooks, portáteis)",
    "No busy waiting and fewer worker threads: the processor stays cooler and keeps its speed, so the game "
    "holds 60 fps longer. The game itself is the same, online too.":
        "Sem espera ativa e com menos threads de trabalho: o processador esquenta menos e mantém a velocidade, então "
        "o jogo segura os 60 fps por mais tempo. O jogo em si é o mesmo, online também.",
    "On for this PC.": "Ligado neste PC.",
    "Off.": "Desligado.",
    "Auto: on for this PC -- {reason}.": "Auto: ligado neste PC -- {reason}.",
    "Auto: off for this PC (no battery, no mobile processor); the game turns it on by itself if it runs on "
    "integrated graphics.":
        "Auto: desligado neste PC (sem bateria, sem processador móvel); o jogo liga sozinho se rodar em gráficos "
        "integrados.",
    "Power saving is on.": "A economia de energia está ligada.",
    "A": "A",
    "Left punch (1)": "Soco esquerdo (1)",
    "Square": "Quadrado",
    "X": "X",
    "Right punch (2)": "Soco direito (2)",
    "S": "S",
    "Triangle": "Triângulo",
    "Y": "Y",
    "Cross": "X",
    "Left kick (3)": "Chute esquerdo (3)",
    "Z": "Z",
    "B": "B",
    "Circle": "Bola",
    "Right kick (4)": "Chute direito (4)",
    "Arrow keys": "Setas",
    "D-pad, left stick": "Direcional, analógico esquerdo",
    "Move / menus": "Mover / menus",
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
    "Quit the game": "Sair do jogo",
    "A / B": "A / B",
    "Cross / Circle": "X / Bola",
    "Mouse": "Mouse",
    "Online tab: accept / decline": "Aba Online: aceitar / recusar",
    "native Windows build  ·  launcher {version}": "build nativa para Windows  ·  launcher {version}",
    "Build": "Compilar",
    "Play offline": "Jogar offline",
    "Settings": "Configurações",
    "Play online": "Jogar online",
    "Output: {folder}": "Saída: {folder}",
    "Your game": "Seu jogo",
    "Package (.pkg)": "Pacote (.pkg)",
    "License (.rap)": "Licença (.rap)",
    "Browse…": "Procurar…",
    "Supported: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version "
    "01.00 -- the package file and the license (.rap) from your own account. Nothing "
    "leaves this PC.":
        "Suportado: Tekken 5: Dark Resurrection Online, PS3 PSN (EUA), NPUB30009 versão 01.00 -- o arquivo do pacote "
        "e a licença (.rap) da sua própria conta. Nada sai deste PC.",
    "Build tools on this PC": "Ferramentas de compilação neste PC",
    "Needed": "Necessário",
    "Found": "Encontrado",
    "Checking…": "Verificando…",
    "Details": "Detalhes",
    "Check again": "Verificar de novo",
    "Install missing…": "Instalar o que falta…",
    "Press BUILD GAME. It takes a few minutes; the game data stays in this folder.":
        "Aperte BUILD GAME. Leva alguns minutos; os dados do jogo ficam nesta pasta.",
    "BUILD GAME": "BUILD GAME",
    "Redo every step": "Refazer todas as etapas",
    "Skip warm-up": "Pular o aquecimento",
    "Skipping…": "Pulando…",
    "Keep the PC responsive (slower)": "Manter o PC responsivo (mais lento)",
    "Open build.log": "Abrir build.log",
    "Report a problem...": "Relatar um problema...",
    "Check my problem": "Verificar meu problema",
    "Check my problem...": "Verificar meu problema...",
    "Looking…": "Procurando…",
    "No known problem found.": "Nenhum problema conhecido encontrado.",
    "If something still goes wrong, \"Report a problem...\" makes one zip with your logs to send to whoever helps you.":
        "Se algo ainda der errado, \"Relatar um problema...\" cria um zip com seus logs para enviar a quem estiver ajudando você.",
    "Problem": "Problema",
    "Note": "Observação",
    "Help": "Ajuda",
    "The launcher looks in this PC's logs and settings for the problems other players had, and says how to fix them. Nothing is changed and nothing is sent.":
        "O launcher procura nos logs e nas configurações deste PC os problemas que outros jogadores tiveram e diz como corrigi-los. Nada é alterado e nada é enviado.",
    "Your game package is version {version}": "Seu pacote do jogo é a versão {version}",
    "The port works only with version {supported} of the game: TEKKEN 5 DARK RESURRECTION ONLINE, US PSN (NPUB30009), a .pkg of {size} bytes, with its license {rap}; or TEKKEN 5 DARK RESURRECTION, European PSN (NPEA00019), a .pkg of {eu_size} bytes, with its license {eu_rap} (offline only for now). Version {version} cannot be used, whatever the license. Choose a {supported} package on the Build tab and press BUILD GAME.":
        "O port só funciona com a versão {supported} do jogo: TEKKEN 5 DARK RESURRECTION ONLINE, PSN dos EUA (NPUB30009), um .pkg de {size} bytes, com a licença {rap}; ou TEKKEN 5 DARK RESURRECTION, PSN europeia (NPEA00019), um .pkg de {eu_size} bytes, com a licença {eu_rap} (por enquanto só offline). A versão {version} não pode ser usada com nenhuma licença. Escolha um pacote {supported} na aba Compilar e aperte BUILD GAME.",
    "build.log: the package says version {version}.": "build.log: o pacote informa a versão {version}.",
    "Unpacking the game ran out of memory": "A memória acabou ao descompactar o jogo",
    "Close other programs (browser, games, launchers) and press BUILD GAME again; since 1.1.5 the launcher unpacks the game in small pieces. If it fails again, check that Windows has a page file (System > About > Advanced system settings > Performance > Virtual memory: automatic).":
        "Feche outros programas (navegador, jogos, launchers) e aperte BUILD GAME de novo; desde a 1.1.5 o launcher descompacta o jogo em pedaços pequenos. Se falhar de novo, verifique se o Windows tem arquivo de paginação (Sistema > Sobre > Configurações avançadas do sistema > Desempenho > Memória virtual: automática).",
    "build.log: the computer ran out of memory while the game data was unpacked.":
        "build.log: o computador ficou sem memória ao descompactar os dados do jogo.",
    "The game package looks damaged or incomplete": "O pacote do jogo parece danificado ou incompleto",
    "Download the package again (it must be {size} bytes), choose it on the Build tab, tick \"Redo every step\" and press BUILD GAME.":
        "Baixe o pacote de novo (ele deve ter {size} bytes), escolha-o na aba Compilar, marque \"Refazer todas as etapas\" e aperte BUILD GAME.",
    "build.log: the package could not be read to the end or not decrypted.":
        "build.log: não foi possível ler o pacote até o fim ou descriptografá-lo.",
    "The game says its data is damaged": "O jogo diz que seus dados estão danificados",
    "On the Build tab tick \"Redo every step\" and press BUILD GAME: it unpacks the game again. If the message comes back, download the package again (it must be {size} bytes).":
        "Na aba Compilar, marque \"Refazer todas as etapas\" e aperte BUILD GAME: o jogo é descompactado de novo. Se a mensagem voltar, baixe o pacote de novo (ele deve ter {size} bytes).",
    "Game log: the game showed the message \"{message}\".": "Log do jogo: o jogo mostrou a mensagem \"{message}\".",
    "Your graphics card is an older model": "Sua placa de vídeo é um modelo antigo",
    "{gpu} is a Direct3D 12 card of the oldest kind (resource binding tier 1: GeForce cards with a Fermi chip, among them some GT 730 models, and older Intel graphics). The game's graphics take several times longer on it than on later cards, whatever the processor: fights can stay below 30 frames per second, and a lower Internal resolution helps only a little. Later cards (a GT 730 with a Kepler chip, GTX 750, Radeon HD 7000 and newer) run the game at full speed.":
        "{gpu} é uma placa Direct3D 12 do tipo mais antigo (resource binding tier 1: GeForce com chip Fermi, entre elas alguns modelos GT 730, e gráficos Intel antigos). Os gráficos do jogo levam várias vezes mais tempo nela do que em placas posteriores, seja qual for o processador: as lutas podem ficar abaixo de 30 quadros por segundo, e reduzir a Resolução interna ajuda pouco. Placas posteriores (uma GT 730 com chip Kepler, GTX 750, Radeon HD 7000 e mais novas) rodam o jogo em velocidade total.",
    "Game log: {gpu}, resource binding tier {tier}.": "Log do jogo: {gpu}, resource binding tier {tier}.",
    "Your processor has {cores} cores": "Seu processador tem {cores} núcleos",
    "The game is made for 4 cores; on {cores} it can stay below 60 frames per second in fights (an i3-3240 reached about 20). Close other programs while you play, keep Windows' power plan on Balanced or High performance, and see \"Low frame rate\" in the help.":
        "O jogo foi feito para 4 núcleos; com {cores} ele pode ficar abaixo de 60 quadros por segundo nas lutas (um i3-3240 chegava a uns 20). Feche outros programas enquanto joga, deixe o plano de energia do Windows em Equilibrado ou Alto desempenho e veja \"Low frame rate\" na ajuda.",
    "This PC: {cores} cores, {logical} logical processors.":
        "Este PC: {cores} núcleos, {logical} processadores lógicos.",
    "The launcher runs under Wine or Proton": "O launcher está rodando no Wine ou Proton",
    "That works, with a few known differences: since 1.1.5 the launcher sets the safe graphics defaults for Wine by itself. A dark blue or black game window (sound playing) means the Proton build does not suit the game: try another one (Proton Experimental, proton-cachyos-slr). See \"Linux and Steam Deck\" in the help.":
        "Funciona, com algumas diferenças conhecidas: desde a 1.1.5 o launcher define sozinho os padrões gráficos seguros para o Wine. Uma janela do jogo azul-escura ou preta (com som) significa que essa versão do Proton não combina com o jogo: tente outra (Proton Experimental, proton-cachyos-slr). Veja \"Linux and Steam Deck\" na ajuda.",
    "This PC: {wine}.": "Este PC: {wine}.",
    "Windows Firewall blocks the game": "O Firewall do Windows bloqueia o jogo",
    "Online matches then often go through a relay (more lag) or do not connect. Open Windows Security > Firewall & network protection > Allow an app through firewall, and allow t5dr.exe (in {folder}) for private and public networks; or remove the block rule for it there.":
        "Assim as partidas online muitas vezes passam por um relay (mais lag) ou não conectam. Abra Segurança do Windows > Firewall e proteção de rede > Permitir um aplicativo pelo firewall e permita o t5dr.exe (em {folder}) para redes privadas e públicas, ou remova ali a regra que o bloqueia.",
    "Windows Firewall: a block rule or \"Block all incoming connections\" for t5dr.exe.":
        "Firewall do Windows: uma regra de bloqueio ou \"Bloquear todas as conexões de entrada\" para o t5dr.exe.",
    "Checking the build…": "Verificando a compilação…",
    "Your name (shown in the game)": "Seu nome (aparece no jogo)",
    "PLAY OFFLINE": "JOGAR OFFLINE",
    "Arcade, Versus, Practice and the other modes on this PC. To play against people over the "
    "internet, use the":
        "Arcade, Versus, Practice e os outros modos neste PC. Para jogar contra outras pessoas pela internet, use a",
    "Online tab": "aba Online",
    "Stop game": "Parar o jogo",
    "Open newest game log": "Abrir o log mais recente",
    "Open saves folder": "Abrir pasta de saves",
    "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers "
    "both work; see Settings for the keys. Esc closes the game. START skips the intro "
    "movie.":
        "O jogo abre na própria janela (DirectX 12). Teclado e controles estilo Xbox funcionam; veja as teclas em "
        "Configurações. Esc fecha o jogo. START pula o vídeo de abertura.",
    "Display": "Tela",
    "The picture is scaled to the window; how sharp it is depends on Internal resolution. "
    "You can also drag the window's edges. Alt+Enter or F11 switches borderless fullscreen "
    "in the game.":
        "A imagem é ajustada à janela; a nitidez depende da Resolução interna. Você também pode arrastar as bordas "
        "da janela. Alt+Enter ou F11 alterna a tela cheia sem bordas no jogo.",
    "Unlocks": "Desbloqueios",
    "Unlock all stages (the Tekken 5 stages, without clearing Arcade)":
        "Desbloquear todos os cenários (os do Tekken 5, sem zerar o Arcade)",
    "Unlock Jinpachi and Random select (without clearing Arcade)":
        "Desbloquear o Jinpachi e a seleção Random (sem zerar o Arcade)",
    "Unlock all customization items (free in the item shop)":
        "Desbloquear todos os itens de customização (grátis na ITEM SHOP)",
    "Offline only (Arcade, VS, Practice and the rest). Your save is not changed; items you take for free "
    "stay yours (the save is backed up first, in save-backups). Online, both players always get the "
    "same stages; Jinpachi and Random are there in casual matches and rooms, not in ranked.":
        "Só offline (Arcade, VS, Practice e o resto). Seu save não muda; os itens que você pegar de graça "
        "continuam seus (o save é copiado antes, em save-backups). Online, os dois jogadores sempre têm os "
        "mesmos cenários; Jinpachi e Random aparecem nas partidas casuais e nas salas, não no Ranked.",
    "Sound and start": "Som e início",
    "Mute sound": "Silenciar som",
    "Sound and taskbar flash when a match is found, I am challenged or invited, or someone joins my room": "Som e piscada na barra de tarefas quando uma partida é encontrada, quando me desafiam ou me convidam, ou quando alguém entra na minha sala",
    "Start minimized, without taking focus (for testing)": "Iniciar minimizado, sem pegar o foco (para testes)",
    "Advanced: extra settings, one NAME=VALUE per line": "Avançado: configurações extras, uma NOME=VALOR por linha",
    "Internal resolution": "Resolução interna",
    "VSync": "VSync",
    "On (smooth, default)": "Ligado (suave, padrão)",
    "Off (lowest latency, may tear)": "Desligado (menor latência, pode ter tearing)",
    "The game always runs at 60 fps, like on the PS3.": "O jogo sempre roda a 60 fps, como no PS3.",
    "Stage blur / glow": "Desfoque / brilho dos cenários",
    "Off (default)": "Desligado (padrão)",
    "Off": "Desligado",
    "Some stages blur the picture (the misty swamp) or let the sun glow. Off shows them sharp, "
    "without the glow. Only your picture changes: online, both players can choose differently.":
        "Alguns cenários desfocam a imagem (o pântano com névoa) ou fazem o sol brilhar. Desligado mostra tudo "
        "nítido, sem o brilho. Só a sua imagem muda: online, cada jogador pode escolher diferente.",
    "Training overlay": "Overlay de treino",
    "Also in the other offline modes (Arcade, Versus, ...)": "Também nos outros modos offline (Arcade, Versus, ...)",
    "Position:": "Posição:",
    "Top": "Em cima",
    "Bottom": "Embaixo",
    "Practice tools": "Ferramentas de treino",
    "SELECT combos in Practice (offline only)": "Combinações com SELECT no Practice (só offline)",
    "Dummy:": "Dummy:",
    "As set in the game's Practice menu": "Como no menu Practice do jogo",
    "Blocks after the first hit": "Defende depois do primeiro golpe",
    "Crouches": "Fica agachado",
    "Walks forward and back": "Anda para frente e para trás",
    "Sidesteps": "Dá passos laterais",
    "In Practice, hold SELECT and press: 3 round start; f+3 / b+3 the dummy against the wall in front "
    "of / behind you; df+3 / db+3 you against the wall in front of / behind you. 1 records the dummy "
    "(you play it), 2 plays the recording once, 4 in a loop; tap up / down for slot 1-5, forward / "
    "back for what the dummy does.":
        "No Practice, segure SELECT e aperte: 3 início do round; f+3 / b+3 o dummy contra a parede à sua "
        "frente / atrás de você; df+3 / db+3 você contra a parede à sua frente / atrás de você. 1 grava o "
        "dummy (você o controla), 2 reproduz a gravação uma vez, 4 em loop; toque cima / baixo para o "
        "slot 1-5, frente / trás para o que o dummy faz.",
    "Also online (only your own inputs, no frame data)": "Também online (só os seus inputs, sem dados de frame)",
    "In Practice: your last inputs with how many frames each was held, and after each exchange the "
    "startup of the move and who can act first (+3, -12). F2 in the game switches it.":
        "No Practice: seus últimos inputs com quantos frames cada um foi segurado e, após cada troca, o startup do "
        "golpe e quem age primeiro (+3, -12). F2 no jogo liga e desliga.",
    "Your screen: {width} x {height}. In fullscreen, {step} matches it.":
        "Sua tela: {width} x {height}. Em tela cheia, {step} corresponde a ela.",
    "Online input delay": "Input delay online",
    "Frames. Auto: 1 up to about 60 ms ping, 2 above. 0/1/2 count only when your "
    "opponent picked the same, otherwise Auto. Ranked matches always use 2.":
        "Frames. Auto: 1 até uns 60 ms de ping, 2 acima disso. 0/1/2 só valem quando o oponente escolheu o mesmo; "
        "senão, Auto. Partidas Ranked sempre usam 2.",
    "Open the game's port on my router during online matches (UPnP / NAT-PMP / PCP)":
        "Abrir a porta do jogo no meu roteador durante partidas online (UPnP / NAT-PMP / PCP)",
    "Helps the direct connection when your opponent's router is strict. The port is open only while "
    "you play and is closed again afterwards.":
        "Ajuda a conexão direta quando o roteador do oponente é restrito. A porta só fica aberta enquanto você joga "
        "e é fechada depois.",
    "Set up controllers…": "Configurar controles…",
    "Pick a pad, stick or hitbox, press the buttons you want for 1 2 3 4 and the rest, "
    "or start from a layout.":
        "Escolha um controle, stick ou hitbox, aperte os botões que quiser para 1 2 3 4 e o resto, ou comece de um "
        "layout.",
    "(needs the lobby files, which are missing)": "(precisa dos arquivos do lobby, que estão faltando)",
    "Action (Tekken default)": "Ação (padrão do Tekken)",
    "PS3 button": "Botão do PS3",
    "Keyboard": "Teclado",
    "Xbox controller": "Controle Xbox",
    "Keyboard and the first XInput controller both drive player 1 (they are combined). "
    "The keyboard only counts while the game window has focus. The game's own Options menu can change "
    "the button layout for offline play; online games use the launcher's buttons only.":
        "O teclado e o primeiro controle XInput controlam o jogador 1 (são combinados). O teclado só vale enquanto a "
        "janela do jogo tem o foco. O menu Options do próprio jogo pode mudar o layout de botões para jogar "
        "offline; partidas online usam só os botões do launcher.",
    "In this window, on the Online tab, a controller or arcade stick works without mouse "
    "or keyboard: Cross / A accepts a match or rematch and starts a search, Circle / B "
    "declines, leaves or stops the search. It only counts while this window is in front, "
    "and only after the button was let go for a moment. Which stick button is Cross "
    "follows your controls.ini.":
        "Nesta janela, na aba Online, um controle ou arcade stick funciona sem mouse nem teclado: X / A aceita uma "
        "partida ou Rematch e inicia uma busca, Bola / B recusa, sai ou para a busca. Só vale enquanto esta janela "
        "está na frente, e só depois de soltar o botão por um instante. Qual botão do stick é o X segue o seu "
        "controls.ini.",
    "Language": "Idioma",
    "Restart now": "Reiniciar agora",
    "The language changes when the launcher starts again.": "O idioma muda quando o launcher reiniciar.",
    "A build is running. Stop it first, or restart the launcher by hand when it is done.":
        "Há uma compilação em andamento. Pare-a primeiro, ou reinicie o launcher manualmente quando ela terminar.",
    "Close the game first.": "Feche o jogo primeiro.",
    "Choose your Tekken 5 DR Online package": "Escolha seu pacote do Tekken 5 DR Online",
    "All files": "Todos os arquivos",
    "PS3 package": "Pacote de PS3",
    "Choose your license (.rap)": "Escolha sua licença (.rap)",
    "PS3 license": "Licença de PS3",
    "Checking build tools…": "Verificando ferramentas de compilação…",
    "missing": "faltando",
    "ok": "ok",
    "Missing: {names}": "Faltando: {names}",
    "Everything the build needs is installed.": "Tudo o que a compilação precisa está instalado.",
    "All build tools found.": "Todas as ferramentas de compilação foram encontradas.",
    "{count} build tool(s) missing -- click 'Install missing…'.":
        "Faltam {count} ferramenta(s) de compilação -- clique em “Instalar o que falta…”.",
    "Hide details": "Ocultar detalhes",
    "Microsoft Visual Studio 2022 Build Tools: the C++ compiler parts only (MSVC x64, "
    "Windows SDK, CMake, Clang). Download about 2.5 GB, about 7 GB on disk, 10-20 "
    "minutes. You accept Microsoft's license terms for the Build Tools "
    "(visualstudio.microsoft.com/license-terms).":
        "Microsoft Visual Studio 2022 Build Tools: só as partes do compilador C++ (MSVC x64, Windows SDK, CMake, "
        "Clang). Download de cerca de 2,5 GB, cerca de 7 GB em disco, 10-20 minutos. Você aceita os termos de "
        "licença da Microsoft para as Build Tools (visualstudio.microsoft.com/license-terms).",
    "Git for Windows (about 70 MB download).": "Git for Windows (download de cerca de 70 MB).",
    "Install build tools": "Instalar ferramentas de compilação",
    "The build needs these free tools from their makers, installed with Windows' own "
    "installer (winget):\n\n{tools}\n\nWindows will ask for administrator permission. A "
    "console window shows the progress.\n\nInstall now?":
        "A compilação precisa destas ferramentas gratuitas dos fabricantes, instaladas com o instalador do próprio "
        "Windows (winget):\n\n{tools}\n\nO Windows vai pedir permissão de administrador. Uma janela de console "
        "mostra o progresso.\n\nInstalar agora?",
    "Could not start the installer:\n{error}\n\nIs winget (App Installer) available? On "
    "Windows 10 install 'App Installer' from the Microsoft Store.":
        "Não foi possível iniciar o instalador:\n{error}\n\nO winget (Instalador de Aplicativo) está disponível? No "
        "Windows 10, instale o “Instalador de Aplicativo” pela Microsoft Store.",
    "Install failed": "Falha na instalação",
    "Installer running in its own window…": "Instalador rodando na própria janela…",
    "Could not start the build: {error}": "Não foi possível iniciar a compilação: {error}",
    "Building…": "Compilando…",
    "Step {n} of {total}: {title}  —  {elapsed}": "Etapa {n} de {total}: {title}  —  {elapsed}",
    "Done in {elapsed}. Open the Play tab.": "Pronto em {elapsed}. Abra a aba Jogar offline.",
    "Build finished.": "Compilação concluída.",
    "Cancelled. BUILD GAME continues where it stopped.": "Cancelado. BUILD GAME continua de onde parou.",
    "The build stopped. The message below says why; build.log has the details.":
        "A compilação parou. A mensagem abaixo diz o motivo; o build.log tem os detalhes.",
    "The build failed. See the log above and build.log.": "A compilação falhou. Veja o log acima e o build.log.",
    "Build stopped.": "Compilação interrompida.",
    "Could not start the game:\n{error}": "Não foi possível iniciar o jogo:\n{error}",
    "Game started (process {pid}). Log: {log}": "Jogo iniciado (processo {pid}). Log: {log}",
    "starting…": "iniciando…",
    "Running — {elapsed} — {fps}": "Rodando — {elapsed} — {fps}",
    "Click Report a problem.": "Clique em “Relatar um problema...”.",
    "The game closed.": "O jogo foi fechado.",
    "A build is running. Stop it and quit?": "Há uma compilação em andamento. Parar e sair?",
    # ---- launcher/updater.py
    "Check for updates": "Procurar atualizações",
    "Community Discord": "Discord da comunidade",
    "Could not open a browser. The address: {url}": "Não foi possível abrir um navegador. O endereço: {url}",
    "Questions? Ask the players in the community Discord: {url}": "Dúvidas? Pergunte aos jogadores no Discord da comunidade: {url}",
    "Updated from {old} to {new}.": "Atualizado de {old} para {new}.",
    "the new version": "a nova versão",
    "The update to {version} failed and could not be undone completely: {error}.\n\nThe "
    "old program files are in\n{folder}\nYour game, saves and settings (the native "
    "folder) were not touched. Download the zip from the releases page and extract it "
    "over this folder.":
        "A atualização para {version} falhou e não pôde ser desfeita por completo: {error}.\n\nOs arquivos antigos "
        "do programa estão em\n{folder}\nSeu jogo, saves e configurações (a pasta native) não foram mexidos. Baixe o "
        "zip da página de releases e extraia por cima desta pasta.",
    "The update to {version} did not work: {error}.\n\nNothing was changed; this is "
    "still version {current}. Try again later, or download the zip from the releases "
    "page.":
        "A atualização para {version} não deu certo: {error}.\n\nNada foi alterado; esta ainda é a versão {current}. "
        "Tente de novo mais tarde, ou baixe o zip da página de releases.",
    "Update": "Atualização",
    "Updates": "Atualizações",
    "This is a development checkout (no release.json and bundled Python), so it does not "
    "update itself. Use git, or a release zip from\n{page}":
        "Esta é uma cópia de desenvolvimento (sem release.json e sem Python embutido), então não se atualiza "
        "sozinha. Use o git, ou um zip de release de\n{page}",
    "Update to {version}…": "Atualizar para {version}…",
    "Could not check for updates.\n\n{problem}": "Não foi possível procurar atualizações.\n\n{problem}",
    "Version {version} is available: click 'Update to {version}' at the top.":
        "A versão {version} está disponível: clique em “Atualizar para {version}” no topo.",
    "You have the newest version ({version}).": "Você tem a versão mais recente ({version}).",
    "Update available": "Atualização disponível",
    "T5DR Online {version} is available": "T5DR Online {version} está disponível",
    "Download: {size}, published {date}.": "Download: {size}, publicado em {date}.",
    "Download: {size}.": "Download: {size}.",
    "You have {version}.": "Você tem a {version}.",
    "The launcher downloads it, checks it, replaces its program files and starts again. "
    "Your game, saves and settings (the native folder) stay as they are.":
        "O launcher baixa, verifica, substitui os arquivos do programa e reinicia. Seu jogo, saves e configurações "
        "(a pasta native) continuam como estão.",
    "After this update the game is built once more (about 2 minutes): the Play tab "
    "offers BUILD GAME. Only the code is rebuilt; the unpacked game and saves are kept.":
        "Depois desta atualização, o jogo é compilado mais uma vez (cerca de 2 minutos): a aba Jogar offline oferece "
        "BUILD GAME. Só o código é recompilado; o jogo descompactado e os saves continuam.",
    "The game itself does not need to be built again.": "O jogo em si não precisa ser compilado de novo.",
    "If this update changes the game code, the Play tab asks you to build the game once "
    "(about 2 minutes).":
        "Se esta atualização mudar o código do jogo, a aba Jogar offline pede para compilar o jogo uma vez (cerca de "
        "2 minutos).",
    "(no release notes)": "(sem notas da versão)",
    "Update now": "Atualizar agora",
    "Later": "Depois",
    "Release page": "Página da versão",
    "Cancelling…": "Cancelando…",
    "Downloading…": "Baixando…",
    "Unexpected error: {error}": "Erro inesperado: {error}",
    "Downloading… {done} of {total}": "Baixando… {done} de {total}",
    "Downloading… {done}": "Baixando… {done}",
    "Checking the download (SHA-256)…": "Verificando o download (SHA-256)…",
    "Unpacking… {percent}%": "Descompactando… {percent}%",
    "Preparing the restart…": "Preparando o reinício…",
    "Try again": "Tentar de novo",
    "Could not start the update step: {error}": "Não foi possível iniciar a etapa de atualização: {error}",
    "Installing {version}: the launcher restarts in a few seconds…":
        "Instalando {version}: o launcher reinicia em alguns segundos…",
    "Updating to {version}…": "Atualizando para {version}…",
    # ---- lobby/t5lobby/client.py
    "Contacting the lobby server over UDP...": "Contatando o servidor do lobby por UDP...",
    "UDP to the lobby server is blocked (firewall?)": "O UDP para o servidor do lobby está bloqueado (firewall?)",
    "Connecting to your opponent...": "Conectando ao oponente...",
    "Measuring the connection...": "Medindo a conexão...",
    "Direct connection not possible; using the lobby server's relay...":
        "Conexão direta impossível; usando o relay do servidor do lobby...",
    "Direct connection found: the match no longer goes through the lobby server.":
        "Conexão direta encontrada: a partida não passa mais pelo servidor do lobby.",
    "The direct connection was lost; back on the lobby server's relay.":
        "A conexão direta caiu; de volta ao relay do servidor do lobby.",
    "Direct connection not possible; using the relay server {name}...":
        "Conexão direta impossível; usando o servidor relay {name}...",
    "Direct connection found: the match no longer goes through the relay server {name}.":
        "Conexão direta encontrada: a partida não passa mais pelo servidor relay {name}.",
    "The direct connection was lost; back on the relay server {name}.":
        "A conexão direta caiu; de volta ao servidor relay {name}.",
    # ---- lobby/t5lobby/dialogs.py
    "No": "Não",
    "Yes": "Sim",
    "OK": "OK",
    # ---- lobby/t5lobby/fighters.py
    "Random": "Aleatório",
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
    "Stage {number}": "Cenário {number}",
    "Tekken 5 stage {number}": "Cenário {number} do Tekken 5",
    # ---- lobby/t5lobby/handover.py
    "direct connection": "conexão direta",
    "local network": "rede local",
    "through the lobby server": "pelo servidor do lobby",
    "through the relay server {name}": "pelo servidor relay {name}",
    "{name} -- {how}, ping {ms} ms, input delay {delay}": "{name} -- {how}, ping {ms} ms, input delay {delay}",
    # ---- lobby/t5lobby/i18n_known.py
    "login timeout": "tempo de login esgotado",
    "idle timeout": "tempo esgotado por inatividade",
    "banned from this server": "banido deste servidor",
    "too many connections": "conexões demais",
    "server full": "servidor cheio",
    "slow down": "mais devagar",
    "bad request": "requisição inválida",
    "the server is busy; try again in a few seconds": "o servidor está ocupado; tente de novo em alguns segundos",
    "the chat is busy; try again in a moment": "o chat está ocupado; tente de novo daqui a pouco",
    "that name looks too much like the account {other}": "esse nome é parecido demais com a conta {other}",
    "that name looks too much like {name}, who is online": "esse nome é parecido demais com {name}, que está online",
    "flooding: disconnected": "flood de mensagens: desconectado",
    "this server speaks lobby protocol {version}; update the launcher":
        "este servidor usa o protocolo de lobby {version}; atualize o launcher",
    "build {build} is not accepted by this server; update the launcher and rebuild the "
    "game":
        "este servidor não aceita a build {build}; atualize o launcher e recompile o jogo",
    "already logged in": "já está logado",
    "this server has no accounts": "este servidor não tem contas",
    "this server has no guest logins": "este servidor não aceita convidados",
    "too many failed logins; wait a few minutes": "logins com falha demais; espere alguns minutos",
    "too many failed attempts; wait a few minutes": "tentativas com falha demais; espere alguns minutos",
    "too many password changes; wait a minute": "mudanças de senha demais; espere um minuto",
    "too many requests for new codes; wait a minute": "pedidos de códigos novos demais; espere um minuto",
    "too many new accounts from this address": "contas novas demais deste endereço",
    "the saved login has expired; log in with your password": "o login salvo expirou; entre com sua senha",
    "session expired; log in again": "sessão expirada; entre de novo",
    "names are 2-16 letters, digits, spaces or _-.[]()!?":
        "nomes têm 2-16 caracteres: letras, números, espaços ou _-.[]()!?",
    "that name is reserved": "esse nome é reservado",
    "that name is not allowed here": "esse nome não é permitido aqui",
    "that name belongs to an account": "esse nome pertence a uma conta",
    "that name is taken": "esse nome já está em uso",
    "someone with that name is online": "alguém com esse nome está online",
    "wrong name or password": "nome ou senha incorretos",
    "wrong password": "senha incorreta",
    "the current password is wrong": "a senha atual está incorreta",
    "passwords are 6-128 characters": "senhas têm 6-128 caracteres",
    "guests have no password": "convidados não têm senha",
    "guests have no account": "convidados não têm conta",
    "wrong name or recovery code (each code works once)":
        "nome ou código de recuperação incorretos (cada código vale uma vez)",
    "logged in from another place": "login feito em outro lugar",
    "this account is banned for good": "esta conta foi banida para sempre",
    "this account is banned for good: {reason}": "esta conta foi banida para sempre: {reason}",
    "this account is banned until {time}": "esta conta está banida até {time}",
    "this account is banned until {time}: {reason}": "esta conta está banida até {time}: {reason}",
    "you are {status}": "não dá agora (status: {status})",
    "ranked needs an account": "Ranked precisa de uma conta",
    "ranked matches come from the ranked queue on this server": "neste servidor, partidas Ranked vêm da fila Ranked",
    "your character is locked until this ranked set ends": "seu personagem fica travado até este set Ranked acabar",
    "the ranked set goes on by itself": "o set Ranked continua sozinho",
    "you are in a ranked set ({mine}-{theirs}); leave it first (that counts as a loss)":
        "você está em um set Ranked ({mine}-{theirs}); saia primeiro (conta como derrota)",
    "that player is in a ranked set": "esse jogador está em um set Ranked",
    "you are not in a ranked set": "você não está em um set Ranked",
    "finish your running match with the same game build first":
        "primeiro termine sua partida em andamento com a mesma build do jogo",
    "this PC ran its last match at {fps} fps; ranked needs at least {min_fps} (both "
    "games run at the slower PC's speed). Close other programs or lower the resolution "
    "scale, then play a casual match to measure again":
        "este PC rodou a última partida a {fps} fps; Ranked precisa de pelo menos {min_fps} (os dois jogos rodam na "
        "velocidade do PC mais lento). Feche outros programas ou baixe a resolução interna, depois jogue uma partida "
        "casual para medir de novo",
    "chat: slow down": "chat: mais devagar",
    "history is kept for accounts only": "o histórico só é salvo para contas",
    "no such player": "jogador não encontrado",
    "no such room": "sala não encontrada",
    "room is full": "a sala está cheia",
    "you cannot join this room": "você não pode entrar nesta sala",
    "not in a room": "você não está em uma sala",
    "no opponent in the room": "não há oponente na sala",
    "that player runs a different build of the game": "esse jogador usa outra build do jogo",
    "finish the match first": "termine a partida primeiro",
    "finish or leave the running match first": "primeiro termine ou saia da partida em andamento",
    "that match is over; find a new opponent": "essa partida acabou; procure um novo oponente",
    "your opponent is no longer available": "seu oponente não está mais disponível",
    "that player is not available": "esse jogador não está disponível",
    "busy": "ocupado",
    "one challenge at a time": "um desafio por vez",
    "that player has challenges pending": "esse jogador tem desafios pendentes",
    "no such challenge": "desafio não encontrado",
    "challenge no longer possible": "o desafio não é mais possível",
    "no such match": "partida não encontrada",
    "match is {state}": "estado da partida: {state}",
    "you cannot block yourself": "você não pode bloquear a si mesmo",
    "the block list is full ({max})": "a lista de bloqueio está cheia ({max})",
    "that player is not on your block list": "esse jogador não está na sua lista de bloqueio",
    "you are not in a set": "você não está em um set",
    "no such finished match": "partida encerrada não encontrada",
    "guests cannot have friends; create an account (free)": "convidados não podem ter amigos; crie uma conta (grátis)",
    "there is no account with that name": "não existe conta com esse nome",
    "you cannot add yourself": "você não pode adicionar a si mesmo",
    "you blocked that player; unblock them first": "você bloqueou esse jogador; desbloqueie primeiro",
    "your friends list is full ({max})": "sua lista de amigos está cheia ({max})",
    "your last invite to that friend ended a moment ago; try again in {seconds} s":
        "seu último convite para esse amigo acabou de terminar; tente de novo em {seconds} s",
    "your last challenge to that player ended a moment ago; try again in {seconds} s":
        "seu último desafio a esse jogador acabou de terminar; tente de novo em {seconds} s",
    "too many friend requests from this internet address today; try again tomorrow":
        "pedidos de amizade demais deste endereço de internet hoje; tente amanhã",
    "you can send {count} friend requests a day; try again tomorrow":
        "você pode enviar {count} pedidos de amizade por dia; tente amanhã",
    "{count} of your friend requests are waiting for an answer; cancel some first":
        "{count} dos seus pedidos de amizade esperam resposta; cancele alguns primeiro",
    "{name} declined your last request; you can ask again in {days} day(s)":
        "{name} recusou seu último pedido; você pode pedir de novo em {days} dia(s)",
    "that player has too many friend requests waiting": "esse jogador tem pedidos de amizade pendentes demais",
    "that player's friends list is full": "a lista de amigos desse jogador está cheia",
    "no friend request from that player": "não há pedido de amizade desse jogador",
    "no friend request to that player": "não há pedido de amizade para esse jogador",
    "that player is not on your friends list": "esse jogador não está na sua lista de amigos",
    "that friend is not online": "esse amigo não está online",
    "that friend's launcher is too old for invites (it needs 1.1.2 or newer)":
        "o launcher desse amigo é antigo demais para convites (precisa da 1.1.2 ou mais nova)",
    "create a room first, then invite": "primeiro crie uma sala, depois convide",
    "that friend is busy right now": "esse amigo está ocupado agora",
    "one invite at a time": "um convite por vez",
    "wait a moment before inviting again": "espere um momento antes de convidar de novo",
    "that player has invites pending": "esse jogador tem convites pendentes",
    "that invite is over": "esse convite acabou",
    "the invite is no longer possible": "o convite não é mais possível",
    "{name} is back in the lobby": "{name} voltou ao lobby",
    "{name} lost the lobby connection; waiting {seconds} s for them to return":
        "{name} perdeu a conexão com o lobby; esperando {seconds} s pela volta",
    "your PC ran its last match at {fps} fps": "seu PC rodou a última partida a {fps} fps",
    "your opponent's PC ran its last match at {fps} fps": "o PC do oponente rodou a última partida a {fps} fps",
    "{name}'s PC ran its last match at {fps} fps": "o PC de {name} rodou a última partida a {fps} fps",
    "{parts} -- this match runs at the slower PC's speed":
        "{parts} -- esta partida roda na velocidade do PC mais lento",
    "you two played {count} ranked matches in the last 24 hours; this one is unranked "
    "(limit {max})":
        "vocês dois jogaram {count} partidas Ranked nas últimas 24 horas; esta não vale para o Ranked (limite {max})",
    "your PC's UDP packets did not reach the lobby server; check the firewall":
        "os pacotes UDP do seu PC não chegaram ao servidor do lobby; verifique o firewall",
    "your opponent reported the result; please report yours": "seu oponente informou o resultado; informe o seu também",
    "opponent runs a different build": "o oponente usa outra build",
    "not connected to the lobby": "não conectado ao lobby",
    "the lobby server did not answer": "o servidor do lobby não respondeu",
    "no answer to {type}": "sem resposta para {type}",
    "cannot reach {host}:{port} ({error})": "não foi possível alcançar {host}:{port} ({error})",
    "the server's certificate does not match the pinned one": "o certificado do servidor não corresponde ao fixado",
    "this server has no encryption (TLS): a password would cross the internet readable. "
    "Play as a guest, or ask the server's host to set up TLS and give you its "
    "fingerprint.":
        "este servidor não tem criptografia (TLS): uma senha passaria legível pela internet. Jogue como convidado, "
        "ou peça a quem hospeda o servidor para configurar TLS e te passar a impressão digital.",
    "connection closed": "conexão fechada",
    "the server sent a malformed match id": "o servidor enviou um ID de partida malformado",
    "message too long": "mensagem longa demais",
    "closed": "fechada",
    "Choose your game package (.pkg) first.": "Primeiro escolha o pacote do jogo (.pkg).",
    "The package file does not exist: {file}": "O arquivo do pacote não existe: {file}",
    "{file} is not a PS3 package (.pkg).": "{file} não é um pacote de PS3 (.pkg).",
    "Choose your license file (.rap) first.": "Primeiro escolha seu arquivo de licença (.rap).",
    "{file} is not a PS3 license: a .rap file is exactly 16 bytes.":
        "{file} não é uma licença de PS3: um arquivo .rap tem exatamente 16 bytes.",
    "This package has no USRDIR/EBOOT.BIN -- it is not a game package (an add-on or "
    "theme?). The port needs {game}.":
        "Este pacote não tem USRDIR/EBOOT.BIN -- não é um pacote de jogo (um add-on ou tema?). O port precisa de "
        "{game}.",
    "This package is \"{title}\" ({id}). The port needs {game}.":
        "Este pacote é “{title}” ({id}). O port precisa de {game}.",
    "This copy is a different version of the game: \"{title}\" version {version}, content "
    "ID {id} (program SHA-1 {sha}...). The port supports only {game}, content ID "
    "{supported}.":
        "Esta cópia é outra versão do jogo: “{title}” versão {version}, content ID {id} (SHA-1 do programa "
        "{sha}...). O port só suporta {game}, content ID {supported}.",
    # 1.1.5: the package's version, read before the build (tools/build_game.py, launcher/core.py)
    "This package is version {version} of the game (program content ID {id}). The port supports only version "
    "{supported}: {game}, content ID {cid}, {size} bytes. This version cannot be used, whatever the license "
    "(.rap).":
        "Este pacote é a versão {version} do jogo (content ID do programa {id}). O port só suporta a versão "
        "{supported}: {game}, content ID {cid}, {size} bytes. Esta versão não pode ser usada, seja qual for a "
        "licença (.rap).",
    "{id}  ({size} bytes) -- version {version} of the game. The port supports only version {supported}; the "
    "build will refuse this package.":
        "{id}  ({size} bytes) -- versão {version} do jogo. O port só suporta a versão {supported}; a compilação "
        "vai recusar este pacote.",
    "{id}  ({size} bytes) -- its program has content ID {program}, not the supported one ({supported}). The "
    "build will most likely refuse it.":
        "{id}  ({size} bytes) -- o programa dele tem o content ID {program}, não o suportado ({supported}). A "
        "compilação provavelmente vai recusá-lo.",
    # 1.1.5: the game's own message boxes (launcher/core.py dialog_info, dialog_message)
    "The game shows: \"{text}\" {advice}": "O jogo mostra: “{text}” {advice}",
    "Your built game data is probably damaged. Open the Build tab, tick \"Redo every step\" and press BUILD "
    "GAME. If the message comes back, download the package again: it must be exactly {size} bytes.":
        "Os dados do jogo compilado provavelmente estão danificados. Abra a aba Compilar, marque “Refazer todas "
        "as etapas” e aperte BUILD GAME. Se a mensagem voltar, baixe o pacote de novo: ele deve ter exatamente "
        "{size} bytes.",
    "The game could not write its save, so progress may be lost. Check that the disk is not full and that no "
    "antivirus blocks the folder native\\gamedata.":
        "O jogo não conseguiu gravar o save, então o progresso pode se perder. Confira se o disco não está cheio "
        "e se nenhum antivírus bloqueia a pasta native\\gamedata.",
    "The game could not read its save. If it happens every time, click Report a problem.":
        "O jogo não conseguiu ler o save. Se isso acontecer sempre, clique em “Relatar um problema...”.",
    "If the game does not go on, click Report a problem.":
        "Se o jogo não continuar, clique em “Relatar um problema...”.",
    # 1.1.5: the launcher's --search ranked|casual (lobby/t5lobby/tk_tab.py search_on_start)
    "Build the game first (Build tab); then the search starts by itself next time.":
        "Compile o jogo primeiro (aba Compilar); na próxima vez a busca começa sozinha.",
    "Log in to start the search. Tick \"Remember me\" when you log in with your account: next time --search "
    "logs in and starts searching by itself.":
        "Entre para começar a busca. Marque “Lembrar de mim” ao entrar com sua conta: na próxima vez, o --search "
        "entra e começa a buscar sozinho.",
    "Ranked matches need an account: log in with your name and password.":
        "Partidas Ranked precisam de uma conta: entre com seu nome e senha.",
    # 1.1.5: a build step that prints nothing for long (launcher/core.py step_quiet_hint)
    "The step \"{title}\" has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, press Cancel and then BUILD GAME again; build.log has the details.":
        "A etapa “{title}” não mostrou nada há {minutes} minutos. Num PC lento ou ocupado ela ainda pode estar "
        "trabalhando. Se nada mudar, clique em Cancelar e depois em BUILD GAME de novo; o build.log tem os "
        "detalhes.",
    "Last program started: {tool}.": "Último programa iniciado: {tool}.",
    "The license (.rap) does not belong to this package. Use the .rap whose name matches "
    "the package's content ID ({id}).":
        "A licença (.rap) não pertence a este pacote. Use o .rap cujo nome corresponde ao content ID do pacote "
        "({id}).",
    "The decrypted game program is missing or not a supported version. Tick \"Redo every step\" and press BUILD GAME again.":
        "O programa do jogo descriptografado está faltando ou não é uma versão suportada. Marque \"Refazer todas as etapas\" e aperte BUILD GAME de novo.",
    "Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press BUILD GAME "
    "again; if it fails again, check that the package is {size} bytes.":
        "A descriptografia do programa do jogo falhou (veja o log acima). Marque “Refazer todas as etapas” e aperte "
        "BUILD GAME de novo; se falhar de novo, confira se o pacote tem {size} bytes.",
    "The package is {size} bytes, the supported one is {supported} bytes: the download is incomplete or it is "
    "a different file. Download it again.":
        "O pacote tem {size} bytes, o suportado tem {supported} bytes: o download está incompleto ou é outro "
        "arquivo. Baixe de novo.",
    "The ps3recomp copy in this folder does not match this version of the port. Download "
    "the release again and extract it into an empty folder.":
        "A cópia do ps3recomp nesta pasta não corresponde a esta versão do port. Baixe o release de novo e extraia "
        "numa pasta vazia.",
    "Git is needed to download ps3recomp (the recompiler). Install Git, or use a release "
    "zip, which already contains it.":
        "O Git é necessário para baixar o ps3recomp (o recompilador). Instale o Git, ou use um zip de release, que "
        "já o inclui.",
    "This package's Python is missing pycryptodome. Download the release again.":
        "Falta o pycryptodome no Python deste pacote. Baixe o release de novo.",
    "Could not download the public PS3 key data from github.com (needed once, a few KB). "
    "Check the internet connection and press BUILD GAME again.":
        "Não foi possível baixar os dados públicos de chaves do PS3 do github.com (necessários uma vez, poucos KB). "
        "Verifique a conexão com a internet e aperte BUILD GAME de novo.",
    "The C++ build tools (Visual Studio 2022 Build Tools, x64 C++ toolset) are not "
    "installed. Open the launcher's Build tab and click Install next to them.":
        "As ferramentas de compilação C++ (Visual Studio 2022 Build Tools, conjunto de ferramentas C++ x64) não "
        "estão instaladas. Abra a aba Compilar do launcher e clique em “Instalar o que falta…”.",
    "clang-cl.exe and lld-link.exe were not found in toolchain\\llvm\\bin. Download the "
    "release again.":
        "clang-cl.exe e lld-link.exe não foram encontrados em toolchain\\llvm\\bin. Baixe o release de novo.",
    "The Windows SDK is missing (needed for Direct3D 12). Install it with the C++ build "
    "tools.":
        "Falta o Windows SDK (necessário para o Direct3D 12). Instale junto com as ferramentas de compilação C++.",
    "clang-cl (LLVM 16 or newer) was not found. Install LLVM or the Visual Studio "
    "component 'C++ Clang tools for Windows'.":
        "O clang-cl (LLVM 16 ou mais novo) não foi encontrado. Instale o LLVM ou o componente do Visual Studio “C++ "
        "Clang tools for Windows”.",
    "CMake and Ninja were not found. Install the Visual Studio component 'C++ CMake "
    "tools for Windows'.":
        "CMake e Ninja não foram encontrados. Instale o componente do Visual Studio “C++ CMake tools for Windows”.",
    "CMake and Ninja were not found. On macOS: brew install cmake ninja sdl2 glslang spirv-cross":
        "CMake e Ninja não foram encontrados. No macOS: brew install cmake ninja sdl2 glslang spirv-cross",
    "glslang and spirv-cross were not found; the game's shaders need them. "
    "On macOS: brew install glslang spirv-cross":
        "glslang e spirv-cross não foram encontrados; os shaders do jogo precisam deles. No macOS: brew install glslang spirv-cross",
    "Building the game is supported on Windows and macOS only.":
        "O jogo só pode ser compilado no Windows e no macOS.",
    "This Python refuses pip install (PEP 668; Homebrew's does). Use a virtual environment: python3 -m venv .venv && .venv/bin/pip install pycryptodome, then run the tools with .venv/bin/python.":
        "Este Python recusa pip install (PEP 668; o do Homebrew recusa). Use um ambiente virtual: python3 -m venv .venv && .venv/bin/pip install pycryptodome, e execute as ferramentas com .venv/bin/python.",
    "expected 1 SPU image, found {count}": "esperava 1 imagem SPU, encontrou {count}",
    "step '{step}' failed: a tool exited with code {code} -- the lines above say why.":
        "a etapa “{step}” falhou: uma ferramenta saiu com código {code} -- as linhas acima dizem o motivo.",
    "cancelled": "cancelado",
    "step '{step}' could not read or write a file: {reason} ({file}). The folder path is "
    "too long for Windows: move the folder to a short path such as C:\\Games\\T5DR.":
        "a etapa “{step}” não conseguiu ler ou gravar um arquivo: {reason} ({file}). O caminho da pasta é longo "
        "demais para o Windows: mova a pasta para um caminho curto como C:\\Games\\T5DR.",
    "step '{step}' could not read or write a file: {reason} ({file}). Is the disk full, "
    "or does another program (antivirus, OneDrive) hold the file?":
        "a etapa “{step}” não conseguiu ler ou gravar um arquivo: {reason} ({file}). O disco está cheio, ou outro "
        "programa (antivírus, OneDrive) está segurando o arquivo?",
    "Python 3.10+": "Python 3.10+",
    "pycryptodome (Python AES)": "pycryptodome (Python AES)",
    "ps3recomp source": "código-fonte do ps3recomp",
    "Game runtime (t5dr.exe)": "Runtime do jogo (t5dr.exe)",
    "clang-cl + lld-link": "clang-cl + lld-link",
    "C++ build tools (MSVC x64)": "Ferramentas de compilação C++ (MSVC x64)",
    "Windows SDK (Direct3D 12)": "Windows SDK (Direct3D 12)",
    "clang-cl 16+ (LLVM)": "clang-cl 16+ (LLVM)",
    "CMake + Ninja": "CMake + Ninja",
    "{version} at {path}": "{version} em {path}",
    "installed": "instalado",
    "missing -- pip install pycryptodome": "faltando -- pip install pycryptodome",
    "included in this package": "incluído neste pacote",
    "git checkout in deps/": "checkout do git em deps/",
    "not present -- will be downloaded with Git": "não está -- será baixado com o Git",
    "not present and Git is missing": "não está e falta o Git",
    "precompiled, included in this package": "pré-compilado, incluído neste pacote",
    "missing from toolchain\\llvm -- extract the release zip again": "faltando em toolchain\\llvm -- extraia o zip do release de novo",
    "missing from this folder -- extract the release zip again": "faltando nesta pasta -- extraia o zip do release de novo",
    "This folder is incomplete ({folders} missing). Extract the release zip again with \"Extract All\" into a short path such as {example}, then start T5DR Online.exe from there -- not from inside the zip.":
        "Esta pasta está incompleta ({folders} faltando). Extraia o zip do release de novo com \"Extrair Tudo\" em um caminho curto como {example} e abra o T5DR Online.exe de lá -- não de dentro do zip.",
    "This folder is incomplete: extract the release zip again (see the Build tab).": "Esta pasta está incompleta: extraia o zip do release de novo (veja a aba Compilar).",
    "not found": "não encontrado",
    "missing {tools}": "faltando: {tools}",
    "System information and the settings you use": "Informações do sistema e as configurações que você usa",
    "What happened (what you wrote)": "O que aconteceu (o que você escreveu)",
    "Launcher log": "Log do launcher",
    "Game log (the newest one)": "Log do jogo (o mais recente)",
    "Game log (the newest {count})": "Logs do jogo (os {count} mais recentes)",
    "Build log": "Log de compilação",
    "Build log (the last build went fine)": "Log de compilação (a última compilação deu certo)",
    "Online: the files of the last match": "Online: os arquivos da última partida",
    "controls.ini (your button settings)": "controls.ini (sua configuração de botões)",
    "Desync dumps (game state numbers, binary)": "Dumps de desync (números do estado do jogo, binário)",
    "The last replay (the inputs of the last online session, without names)":
        "O último replay (as entradas da última sessão online, sem nomes)",
    "could not be cleaned of private data": "não foi possível limpar os dados privados",
    "no room left in the size limit": "não sobrou espaço no limite de tamanho",
    "could not be read": "não foi possível ler",
    "The launcher cannot write next to its folder or into it, so it cannot update "
    "itself. Download the zip from the releases page instead.":
        "O launcher não consegue gravar ao lado da pasta nem dentro dela, então não pode se atualizar sozinho. Baixe "
        "o zip da página de releases.",
    "Refused to download from {host}: not this project's GitHub releases.":
        "Download de {host} recusado: não são os releases do GitHub deste projeto.",
    "The download came from {host}. Nothing was changed.": "O download veio de {host}. Nada foi alterado.",
    "GitHub did not return a published release.": "O GitHub não retornou um release publicado.",
    "The latest release has an unexpected version ({tag}).":
        "O release mais recente tem uma versão inesperada ({tag}).",
    "Release {version} has no {name} with SHA256SUMS yet.": "O release {version} ainda não tem {name} com SHA256SUMS.",
    "The downloaded release does not say it is version {version}. Nothing was changed.":
        "O release baixado não diz que é a versão {version}. Nada foi alterado.",
    "The downloaded release has no launcher. Nothing was changed.":
        "O release baixado não tem launcher. Nada foi alterado.",
    "This folder has no python\\pythonw.exe, so the launcher cannot update itself (a "
    "development checkout?). Download the zip from the releases page instead.":
        "Esta pasta não tem python\\pythonw.exe, então o launcher não pode se atualizar sozinho (uma cópia de "
        "desenvolvimento?). Baixe o zip da página de releases.",
    "The download was sent to {host}, which is not GitHub's storage for this project. "
    "Nothing was changed.":
        "O download foi enviado para {host}, que não é o armazenamento do GitHub deste projeto. Nada foi alterado.",
    "Release {version}: {name} is not on this project's GitHub releases.":
        "Release {version}: {name} não está nos releases do GitHub deste projeto.",
    "Release {version}: {name} is still being uploaded.": "Release {version}: {name} ainda está sendo enviado.",
    "The download stopped early ({done} of {total} bytes). Try again.":
        "O download parou antes da hora ({done} de {total} bytes). Tente de novo.",
    "The download is not a readable zip ({error}). Nothing was changed.":
        "O download não é um zip legível ({error}). Nada foi alterado.",
    "The download unpacks to far more than a release should. Nothing was changed.":
        "O download descompacta muito mais do que um release deveria. Nada foi alterado.",
    "Not enough free disk space: the update needs about {need} MB next to the folder, "
    "{free} MB are free.":
        "Espaço livre insuficiente: a atualização precisa de cerca de {need} MB ao lado da pasta, e há {free} MB "
        "livres.",
    "SHA256SUMS of release {version} has no line for {name}. Nothing was changed.":
        "O SHA256SUMS do release {version} não tem linha para {name}. Nada foi alterado.",
    "SHA256SUMS and GitHub disagree about the download's checksum. Nothing was changed.":
        "SHA256SUMS e GitHub discordam sobre o checksum do download. Nada foi alterado.",
    "The download is damaged or not the published file: its SHA-256 is {got}..., "
    "SHA256SUMS says {want}.... Nothing was changed.":
        "O download está danificado ou não é o arquivo publicado: o SHA-256 dele é {got}..., o SHA256SUMS diz "
        "{want}.... Nada foi alterado.",
    "The downloaded release has no python\\pythonw.exe. Nothing was changed.":
        "O release baixado não tem python\\pythonw.exe. Nada foi alterado.",
    "The download is far bigger than a release should be. Nothing was changed.":
        "O download é muito maior do que um release deveria ser. Nada foi alterado.",
    "The download contains an unexpected path ({name}: {why}). Nothing was changed.":
        "O download contém um caminho inesperado ({name}: {why}). Nada foi alterado.",
    "The download contains an unexpected path ({name}). Nothing was changed.":
        "O download contém um caminho inesperado ({name}). Nada foi alterado.",
    "Cancelled.": "Cancelado.",
    "Could not download or unpack the update ({error}). Nothing was changed.":
        "Não foi possível baixar ou descompactar a atualização ({error}). Nada foi alterado.",
    "The download is damaged ({error}). Nothing was changed.":
        "O download está danificado ({error}). Nada foi alterado.",
    "the new release contains {names} (the player's files)": "o novo release contém {names} (os arquivos do jogador)",
    "release.json does not say {version} after the swap": "o release.json não diz {version} depois da troca",
    "launcher\\t5dr_launcher.pyw is missing after the swap": "falta launcher\\t5dr_launcher.pyw depois da troca",
    "python\\pythonw.exe is missing after the swap": "falta python\\pythonw.exe depois da troca",
    "the update plan is incomplete": "o plano de atualização está incompleto",
    "the launcher did not close": "o launcher não fechou",
    "programs from the folder were still running ({names}); close them and try again":
        "programas da pasta ainda estavam rodando ({names}); feche-os e tente de novo",
    "the new launcher {version} did not start": "o novo launcher {version} não iniciou",
    "could not replace the program files: {error}": "não foi possível substituir os arquivos do programa: {error}",
    "unexpected error: {error}": "erro inesperado: {error}",
    "GitHub asks to wait with update checks until {time}.":
        "O GitHub pede para esperar até {time} para procurar atualizações.",
    "GitHub limits update checks right now. Try again later.":
        "O GitHub está limitando as buscas de atualização agora. Tente mais tarde.",
    "GitHub answered with error {code}. Try again later.": "O GitHub respondeu com o erro {code}. Tente mais tarde.",
    "No connection to GitHub. Check the internet connection and try again.":
        "Sem conexão com o GitHub. Verifique a conexão com a internet e tente de novo.",
    "A build is running. Update when it is finished.": "Há uma compilação em andamento. Atualize quando terminar.",
    "The game is running. Close it first, then update.": "O jogo está rodando. Feche-o primeiro e depois atualize.",
    "'Host for friends' is running. Stop hosting first, then update.":
        "“Hospedar para amigos” está ativo. Pare de hospedar primeiro e depois atualize.",
    "An online match was found. Update after the match.":
        "Uma partida online foi encontrada. Atualize depois da partida.",
    "An online match is running. Update after the match.":
        "Uma partida online está em andamento. Atualize depois da partida.",
    "You are searching for or playing an online match. Update afterwards.":
        "Você está procurando ou jogando uma partida online. Atualize depois.",
    "Other programs from this folder are still running ({names}): another launcher "
    "window, the game or a lobby server. Close them, then update.":
        "Outros programas desta pasta ainda estão rodando ({names}): outra janela do launcher, o jogo ou um servidor "
        "de lobby. Feche-os e depois atualize.",
    "not a plain relative path": "não é um caminho relativo simples",
    "'.', '..' or an empty part": "“.”, “..” ou uma parte vazia",
    "outside the folder {folder}": "fora da pasta {folder}",
    "named like the player's own files": "com o mesmo nome dos arquivos do jogador",
    "a name Windows does not keep as written": "um nome que o Windows não guarda como está escrito",
    "Release {version} is a test version; it is not installed automatically.":
        "O release {version} é uma versão de teste; não é instalado automaticamente.",
    "Release {version} is not signed with the project's release key (no SHA256SUMS.sig). It was not made by "
    "the project's release process; nothing was changed.":
        "O release {version} não está assinado com a chave de release do projeto (sem SHA256SUMS.sig). Não foi feito "
        "pelo processo de release do projeto; nada foi alterado.",
    "Release {version} failed the signature check ({error}). It was not made by the project's release "
    "process; nothing was changed.":
        "O release {version} falhou na verificação de assinatura ({error}). Não foi feito pelo processo de release "
        "do projeto; nada foi alterado.",
    "idle": "livre",
    "room": "na sala",
    "queue": "na fila",
    "match": "em partida",
    "playing": "jogando",
    # ---- lobby/t5lobby/discord_rpc.py
    "In lobby": "No lobby",
    "Searching ranked": "Procurando Ranked",
    "Searching quick match": "Procurando Quick Match",
    "Ranked, Set {mine}-{theirs}": "Ranked, set {mine}-{theirs}",
    "Ranked": "Ranked",
    "Casual": "Casual",
    "In match: {mine} vs {theirs} ({what})": "Em partida: {mine} vs {theirs} ({what})",
    "In match ({what})": "Em partida ({what})",
    # ---- lobby/t5lobby/lag.py
    "Ping {ping} ms should mean about {frames} frames behind.":
        "Com {ping} ms de ping, o normal é ficar uns {frames} frames atrás.",
    "The games did not report how it went, so there is nothing to compare.":
        "Os jogos não informaram como foi, então não há o que comparar.",
    "It was {observed}.": "Foram {observed}.",
    "That is what the ping explains.": "Isso é o que o ping explica.",
    "That is more than the ping explains.": "É mais do que o ping explica.",
    "Both PCs ran below full speed.": "Os dois PCs rodaram abaixo da velocidade total.",
    "Your PC was the slow one ({fps} fps).": "Seu PC foi o lento ({fps} fps).",
    "Your PC was the slow one.": "Seu PC foi o lento.",
    "Your opponent's PC was the slow one ({fps} fps).": "O PC do oponente foi o lento ({fps} fps).",
    "Your opponent's PC was the slow one.": "O PC do oponente foi o lento.",
    "Both PCs kept up, so the connection stalled now and then (jitter or lost packets).":
        "Os dois PCs deram conta, então a conexão travou de vez em quando (jitter ou pacotes perdidos).",
    "This match lagged: the games waited {secs} s for each other's inputs.":
        "Esta partida teve lag: os jogos esperaram {secs} s pelos comandos um do outro.",
    "A wired connection and no uploads during matches help.":
        "Ajuda usar uma conexão por cabo e não fazer uploads durante as partidas.",
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "Seu oponente fechou o jogo.",
    "The connection to your opponent's game was lost.": "A conexão com o jogo do oponente caiu.",
    "Your opponent's game stopped responding.": "O jogo do oponente parou de responder.",
    "Your opponent's game did not get to the fight.": "O jogo do oponente não chegou à luta.",
    "Your opponent's game was restarted; the match cannot go on.":
        "O jogo do oponente foi reiniciado; a partida não pode continuar.",
    "Loading the fight took too long on this PC (slow disk or a busy PC?); the match was stopped.":
        "O carregamento da luta demorou demais neste PC (disco lento ou PC ocupado?); a partida foi interrompida.",
    "Loading the fight took too long on your opponent's PC; the match was stopped.":
        "O carregamento da luta demorou demais no PC do oponente; a partida foi interrompida.",
    "Your opponent's game could not be reached (firewall or router?).":
        "Não foi possível alcançar o jogo do oponente (firewall ou roteador?).",
    "Your opponent's game is a different build.": "O jogo do oponente é outra build.",
    "Your opponent's game is in another match.": "O jogo do oponente está em outra partida.",
    "The game could not open its network port (another program uses it?).":
        "O jogo não conseguiu abrir a porta de rede (outro programa está usando?).",
    "You closed the game during the match: it counts as a loss.":
        "Você fechou o jogo durante a partida: conta como derrota.",
    "The game could not get back to character select and closed itself; it starts again for your next match.":
        "O jogo não conseguiu voltar à seleção de personagem e se fechou; ele abre de novo para sua próxima partida.",
    "Your opponent does not want a rematch.": "Seu oponente não quer Rematch.",
    "The game is not running any more; leaving the rematch.": "O jogo não está mais rodando; saindo do Rematch.",
    "Rematch against {name}: same connection, the game stays open.":
        "Rematch contra {name}: mesma conexão, o jogo continua aberto.",
    "The game could not start; leaving the match.": "O jogo não conseguiu iniciar; saindo da partida.",
    "Playing against {summary}": "Jogando contra {summary}",
    "The game did not answer its control channel; it is restarted for every opponent "
    "from now on.":
        "O jogo não respondeu no canal de controle; a partir de agora ele é reiniciado para cada oponente.",
    "Character select...": "Seleção de personagem...",
    "The game is starting...": "O jogo está iniciando...",
    "Fight!": "Fight!",
    "Loading the fight...": "Carregando a luta...",
    "Stage select...": "Seleção de cenário...",
    "At character select, waiting for the next match.": "Na seleção de personagem, esperando a próxima partida.",
    "Match over.": "Partida encerrada.",
    "Ignored a result the game wrote for an earlier match.":
        "Um resultado que o jogo gravou para uma partida anterior foi ignorado.",
    "The match could not be finished ({reason}).": "A partida não pôde ser concluída ({reason}).",
    "The match could not be played ({reason}).": "A partida não pôde ser jogada ({reason}).",
    "The game stopped unexpectedly; the match does not count (repeated crashes do).":
        "O jogo parou inesperadamente; a partida não conta (crashes repetidos contam).",
    "Result sent (the games went out of sync on {frames} frames); waiting for the "
    "lobby...":
        "Resultado enviado (os jogos dessincronizaram em {frames} frames); esperando o lobby...",
    "Result sent; waiting for the lobby...": "Resultado enviado; esperando o lobby...",
    "Lobby: {message}": "Lobby: {message}",
    # ---- lobby/t5lobby/padnav.py
    "(+{count} more)": "(+{count} a mais)",
    # ---- lobby/t5lobby/ranks.py
    "{wins}W {losses}L": "{wins}V {losses}D",
    "{draws}D": "{draws}E",
    "{rank} (placement {done}/{total})": "{rank} (classificação {done}/{total})",
    # ---- lobby/t5lobby/sets.py
    "a game was too short to count": "uma partida foi curta demais para contar",
    "a fight ended without a winner": "uma luta terminou sem vencedor",
    "too many games without a winner": "partidas demais sem vencedor",
    "left after the lag check": "saiu depois do teste de lag",
    "the lobby server restarted": "o servidor do lobby reiniciou",
    "a player left right away": "um jogador saiu na hora",
    "the next game could not start": "a próxima partida não pôde começar",
    "a player left before a game counted": "um jogador saiu antes de uma partida contar",
    "a player lost the lobby connection": "um jogador perdeu a conexão com o lobby",
    "set won": "set vencido",
    "set lost": "set perdido",
    "Set {mine}-{theirs}": "Set {mine}-{theirs}",
    "game {number} of {best}": "partida {number} de {best}",
    "game {number} of {best} again (no winner)": "partida {number} de {best} de novo (sem vencedor)",
    "starts in {seconds} s": "começa em {seconds} s",
    "The set does not count ({why}); no rating change": "O set não conta ({why}); sem mudança de pontos",
    "The set does not count; no rating change": "O set não conta; sem mudança de pontos",
    "You won the set (your opponent left it)": "Você venceu o set (seu oponente saiu)",
    "You won the set": "Você venceu o set",
    "You lost the set (you left it)": "Você perdeu o set (você saiu)",
    "You lost the set": "Você perdeu o set",
    "You won the set {mine}-{theirs}": "Você venceu o set por {mine}-{theirs}",
    "You lost the set {mine}-{theirs}": "Você perdeu o set por {mine}-{theirs}",
    "set game {number}": "partida {number} do set",
    # 1.1.9: who left a ranked set, and how; a player away from the set (sets.py, tk_tab.py, the server)
    "You won the set ({how})":
        "Você venceu o set ({how})",
    "You lost the set ({how})":
        "Você perdeu o set ({how})",
    "you left the set":
        "você saiu do set",
    "your opponent left the set":
        "seu oponente saiu do set",
    "you did not come back within {seconds} s":
        "você não voltou em {seconds} s",
    "your opponent did not come back within {seconds} s":
        "seu oponente não voltou em {seconds} s",
    "you quit a game":
        "você abandonou uma partida",
    "your opponent quit a game":
        "seu oponente abandonou uma partida",
    "you lost the connection":
        "você perdeu a conexão",
    "your opponent lost the connection":
        "seu oponente perdeu a conexão",
    "your side could not connect":
        "seu lado não conseguiu conectar",
    "your opponent's side could not connect":
        'o lado do seu oponente não conseguiu conectar',
    "a player did not come back in time":
        "um jogador não voltou a tempo",
    "played again: a player was away":
        "jogada de novo: um jogador estava ausente",
    "A player was away; the set's game starts again.":
        'Um jogador estava ausente; a partida do set começa de novo.',
    "{name} is reconnecting -- {seconds} s left":
        "{name} está reconectando -- faltam {seconds} s",
    "{name} is back; the set goes on":
        "{name} voltou; o set continua",
    "you are back in the ranked set ({mine}-{theirs}); the next game starts soon":
        "você voltou ao set ranqueado ({mine}-{theirs}); a próxima partida começa em breve",
    # ---- lobby/t5lobby/tk_tour.py, tour_text.py (tournaments)
    "A set is played like a casual set with the in-game select; results come from the games. Players who do not accept a called set in time are out.": "Um set é jogado como um set casual com a seleção no jogo; os resultados vêm das partidas. Quem não aceitar a tempo um set chamado está fora.",
    "Accepted. Waiting for {name}...": "Aceito. Esperando {name}...",
    "Bracket": "Bracket",
    "CALLED": "CHAMADO",
    "Cancel tournament": "Cancelar torneio",
    "Cancel {name}? Nobody can play it any more.": "Cancelar {name}? Ninguém mais poderá jogá-lo.",
    "Cancelled": "Cancelado",
    "Champion: {name}": "Campeão: {name}",
    "Check in": "Fazer check-in",
    "Check-in": "Check-in",
    "Check-in 10 minutes before": "Check-in 10 minutos antes",
    "Check-in 15 minutes before": "Check-in 15 minutos antes",
    "Check-in 30 minutes before": "Check-in 30 minutos antes",
    "Check-in 5 minutes before": "Check-in 5 minutos antes",
    "Check-in 60 minutes before": "Check-in 60 minutos antes",
    "Check-in for {name} is open: check in on the Tournaments page, or you are not in the bracket.": "O check-in de {name} está aberto: faça na página Torneios ou você fica fora do bracket.",
    "Checked in.": "Check-in feito.",
    "Click a set in the bracket.": "Clique em um set do bracket.",
    "Create": "Criar",
    "Create tournament": "Criar torneio",
    "Create...": "Criar...",
    "Disqualify": "Desclassificar",
    "Disqualify which player (name)?": "Desclassificar qual jogador (nome)?",
    "Disqualify...": "Desclassificar...",
    "Double elimination": "Eliminação dupla",
    "Final": "Final",
    "Finished": "Encerrado",
    "First to 2 games (best of 3)": "Até 2 partidas vencidas (melhor de 3)",
    "First to 3 games (best of 5)": "Até 3 partidas vencidas (melhor de 5)",
    "Format": "Formato",
    "Grand final": "Grande final",
    "Grand final reset": "Grande final (reset)",
    "LIVE": "AO VIVO",
    "Leave the tournament set": "Sair do set de torneio",
    "Leave this tournament set?\n\nYou lose the set.": "Sair deste set de torneio?\n\nVocê perde o set.",
    "Losers final": "Final da Losers",
    "Losers round {number}": "Rodada {number} da Losers",
    "Losers semi-final": "Semifinal da Losers",
    "NEEDS THE ORGANIZER": "PRECISA DO ORGANIZADOR",
    "No check-in": "Sem check-in",
    "No tournament selected": "Nenhum torneio selecionado",
    "Only tournament hosts can create tournaments. Ask the server's owner for a host slot.":
        "Só os anfitriões de torneio podem criar torneios. Peça uma vaga de anfitrião ao dono do servidor.",
    "Pick a tournament to see its bracket.": "Escolha um torneio para ver o bracket.",
    "Pick one in the list, or create one.": "Escolha um da lista ou crie um.",
    "Players": "Jogadores",
    "Players at most": "Máximo de jogadores",
    "Players: {list}": "Jogadores: {list}",
    "Quarter-final": "Quartas de final",
    "Random seeding": "Seeding aleatório",
    "Report a result": "Informar um resultado",
    "Reset set": "Reiniciar set",
    "Reset set {set}? It is played again from 0-0.": "Reiniciar o set {set}? Ele é jogado de novo a partir de 0-0.",
    "Round {number}": "Rodada {number}",
    "Running": "Em andamento",
    "Seeded by rating": "Seeding por pontos",
    "Seeding": "Seeding",
    "Semi-final": "Semifinal",
    "Sets": "Sets",
    "Side 1 wins": "Lado 1 vence",
    "Side 2 wins": "Lado 2 vence",
    "Sign up": "Inscrever-se",
    "Sign-up": "Inscrições",
    "Single elimination": "Eliminação simples",
    "Start now": "Começar agora",
    "Start {name} now, with the players who are in?": "Começar {name} agora, com os jogadores inscritos?",
    "Starts": "Começa",
    "TOURNAMENT": "TORNEIO",
    "TOURNAMENT SET · BEST OF {best}": "SET DE TORNEIO · MELHOR DE {best}",
    "The bracket is drawn when the tournament starts.": "O bracket é montado quando o torneio começa.",
    "The name needs 3 characters or more.": "O nome precisa de 3 caracteres ou mais.",
    "The organizer decided your tournament set.": "O organizador decidiu seu set de torneio.",
    "The organizer reset your tournament set; it is called again.": "O organizador reiniciou seu set de torneio; ele é chamado de novo.",
    "The set goes on at {mine}-{theirs}.": "O set continua em {mine}-{theirs}.",
    "The set has no result; the tournament calls it again or its organizer decides": "O set não tem resultado; o torneio chama de novo ou o organizador decide",
    "The set is called again.": "O set é chamado de novo.",
    "The tournament was cancelled.": "O torneio foi cancelado.",
    "The tournament {name} has started: you are seed {seed} of {players}. Your sets are called here.": "O torneio {name} começou: você é o seed {seed} de {players}. Seus sets são chamados aqui.",
    "The tournament {name} is over: {champion} won it.": "O torneio {name} acabou: {champion} venceu.",
    "The tournament {name} is over: {champion} won it. You finished {place}.": "O torneio {name} acabou: {champion} venceu. Você terminou em {place}.",
    "The tournament {name} was cancelled by its organizer.": "O torneio {name} foi cancelado pelo organizador.",
    "The tournament {name} was cancelled: not enough players.": "O torneio {name} foi cancelado: jogadores insuficientes.",
    "This tournament had no bracket.": "Este torneio não teve bracket.",
    "This tournament is for another build of the game.": "Este torneio é para outro build do jogo.",
    "Tournament": "Torneio",
    "Tournament set": "Set de torneio",
    "Tournament set vs {name}": "Set de torneio contra {name}",
    "Tournament {name} created.": "Torneio {name} criado.",
    "Tournament {name}: set {set} needs you ({why}). Report the result or reset it.": "Torneio {name}: o set {set} precisa de você ({why}). Informe o resultado ou reinicie-o.",
    "Tournament {name}: {code}": "Torneio {name}: {code}",
    "Tournaments": "Torneios",
    "Winners final": "Final da Winners",
    "Winners round {number}": "Rodada {number} da Winners",
    "Winners semi-final": "Semifinal da Winners",
    "Withdraw": "Desistir",
    "Withdraw from {name}? You are out of the tournament.": "Desistir de {name}? Você sai do torneio.",
    "Write the start time as HH:MM, e.g. 20:30.": "Escreva o horário de início como HH:MM, ex.: 20:30.",
    "You are checked in.": "Seu check-in foi feito.",
    "You are in. Your next set is called here when its players are known.": "Você está dentro. Seu próximo set é chamado aqui quando os jogadores forem definidos.",
    "You are out of {name}.": "Você foi eliminado de {name}.",
    "You are out of {name}: {place}.": "Você foi eliminado de {name}: {place}.",
    "You are out of {name}: {why}.": "Você está fora de {name}: {why}.",
    "You are out: {why}.": "Você está fora: {why}.",
    "You are signed up.": "Você está inscrito.",
    "You are signed up. Check in now, or you are not in the bracket.": "Você está inscrito. Faça o check-in agora ou você fica fora do bracket.",
    "You did not check in for {name}; the tournament started without you.": "Você não fez check-in em {name}; o torneio começou sem você.",
    "You finished {place}.": "Você terminou em {place}.",
    "You left the tournament.": "Você saiu do torneio.",
    "You won the tournament {name}!": "Você venceu o torneio {name}!",
    "Your next set: {set}.": "Seu próximo set: {set}.",
    "Your opponent did not show up: you win the set.": "Seu oponente não apareceu: você vence o set.",
    "Your opponent is out of the tournament: you win the set.": "Seu oponente está fora do torneio: você vence o set.",
    "Your tournament set has no result; the organizer decides how it goes on.": "Seu set de torneio não tem resultado; o organizador decide como continua.",
    "Your tournament set is ready": "Seu set de torneio está pronto",
    "accept within {seconds} s": "aceite em {seconds} s",
    "accepted -- waiting for {name}...": "aceito -- esperando {name}...",
    "best of {best}": "melhor de {best}",
    "bye": "bye",
    "check-in from {time}": "check-in a partir de {time}",
    "decided by the organizer": "decidido pelo organizador",
    "did not show up": "ausente",
    "disqualified": "desclassificado",
    "disqualified by the organizer": "desclassificado pelo organizador",
    "ended {time}": "terminou {time}",
    "in 1 hour": "em 1 hora",
    "in 10 minutes": "em 10 minutos",
    "in 12 hours": "em 12 horas",
    "in 15 minutes": "em 15 minutos",
    "in 2 hours": "em 2 horas",
    "in 24 hours": "em 24 horas",
    "in 3 hours": "em 3 horas",
    "in 30 minutes": "em 30 minutos",
    "in 5 minutes": "em 5 minutos",
    "in 6 hours": "em 6 horas",
    "no-show": "ausência",
    "nobody": "ninguém",
    "none yet": "nenhum ainda",
    "not needed": "não foi preciso",
    "or at (HH:MM)": "ou às (HH:MM)",
    "organizer {name}": "organizador {name}",
    "place {place}": "{place}º lugar",
    "rated": "vale pontos",
    "results disputed": "resultados contestados",
    "started {time}": "começou {time}",
    "starts {time}": "começa {time}",
    "waiting": "a definir",
    "withdrew": "desistência",
    "{format}, best of {best}": "{format}, melhor de {best}",
    "{name} has accepted.": "{name} aceitou.",
    "{name} is not online yet.": "{name} ainda não está online.",
    "{name} wins": "{name} vence",
    "{name} wins set {set}?": "{name} vence o set {set}?",
    "{name}'s tournament": "Torneio de {name}",
    "{players} of {max} players": "{players} de {max} jogadores",
    "The organizer decided the set.": "O organizador decidiu o set.",
    # ---- lobby/t5lobby/i18n_known.py: lobby/t5lobby/server/tournaments.py
    "tournaments need an account": "torneios precisam de uma conta",
    "no such tournament": "torneio não encontrado",
    "only the server's organizers can create tournaments here": "aqui só os organizadores do servidor podem criar torneios",
    "a tournament name is 3-40 characters": "o nome de um torneio tem de 3 a 40 caracteres",
    "the format is single or double elimination": "o formato é eliminação simples ou dupla",
    "a set is first to 2 or first to 3 games": "um set vai até 2 ou 3 partidas vencidas",
    "the player limit is 8, 16, 32 or 64": "o limite de jogadores é 8, 16, 32 ou 64",
    "the check-in window is 0, 5, 10, 15, 30 or 60 minutes": "o check-in dura 0, 5, 10, 15, 30 ou 60 minutos",
    "seeding is random or by rating": "o seeding é aleatório ou por pontos",
    "that start time has passed": "esse horário de início já passou",
    "a tournament starts within {days} days": "um torneio começa em até {days} dias",
    "this server has as many tournaments as it takes; try again later": "este servidor já tem todos os torneios que aceita; tente mais tarde",
    "you already run {count} tournaments; finish or cancel one first": "você já organiza {count} torneios; termine ou cancele um primeiro",
    "update the launcher to play in tournaments": "atualize o launcher para jogar torneios",
    "sign-up for that tournament is closed": "as inscrições desse torneio estão fechadas",
    "that tournament is played with another build of the game": "esse torneio é jogado com outro build do jogo",
    "that tournament is full": "esse torneio está lotado",
    "you are not in that tournament": "você não está nesse torneio",
    "that tournament is over": "esse torneio já acabou",
    "check-in is not open": "o check-in não está aberto",
    "that tournament is not running": "esse torneio não está em andamento",
    "that set is not yours to play": "esse set não é seu",
    "that set is not waiting for you": "esse set não está esperando por você",
    "only the organizer can do that": "só o organizador pode fazer isso",
    "that tournament name is not allowed here":
        "esse nome de torneio não é permitido aqui",
    "this internet address runs as many tournaments as one organizer may; finish or cancel one first":
        "este endereço de internet já tem tantos torneios quanto um organizador pode ter; termine ou cancele um primeiro",
    "the organizer took you off this tournament":
        "o organizador tirou você deste torneio",
    "you play in that set yourself: a server tournament admin decides it (or cancel the tournament)":
        "você mesmo joga esse set: um administrador de torneios do servidor decide (ou cancele o torneio)",
    "that tournament has started already": "esse torneio já começou",
    "a tournament needs at least 2 players": "um torneio precisa de pelo menos 2 jogadores",
    "no such player in that tournament": "esse jogador não está no torneio",
    "that player is out already": "esse jogador já foi eliminado",
    "no such set": "set não encontrado",
    "that set is decided; override it instead": "esse set já foi decidido; corrija-o em vez disso",
    "only a played set can be overridden": "só um set jogado pode ser corrigido",
    "that set has not been played": "esse set ainda não foi jogado",
    "that set was a walkover": "esse set foi W.O.",
    "set {set} was already played from this result; reset it first": "o set {set} já foi jogado com esse resultado; reinicie-o primeiro",
    "finish your match first, then accept the tournament set": "termine sua partida primeiro e depois aceite o set do torneio",
    "finish your set first, then accept the tournament set": "termine seu set primeiro e depois aceite o set do torneio",
    "you are in a tournament set; finish it first": "você está em um set de torneio; termine-o primeiro",
    "that player is playing a tournament set": "esse jogador está jogando um set de torneio",
    "your tournament set is ready; accept it first": "seu set de torneio está pronto; aceite-o primeiro",
    "that player has a tournament set to play": "esse jogador tem um set de torneio para jogar",
    # ---- lobby/t5lobby/theme.py
    "Good connection": "Boa conexão",
    "Laggy connection": "Conexão com lag",
    "OK connection": "Conexão razoável",
    "Ping not known yet": "Ping ainda desconhecido",
    "sec": "seg",
    # ---- lobby/t5lobby/tk_tab.py
    "Leave set (counts as a loss)": "Sair do set (conta como derrota)",
    "Leave the ranked set": "Sair do set Ranked",
    "Leave this ranked set?\n\nLeaving a ranked set counts as losing it.":
        "Sair deste set Ranked?\n\nSair de um set Ranked conta como derrota.",
    "Rematch? (a new set)": "Rematch? (um set novo)",
    "in a room": "em uma sala",
    "in lobby": "no lobby",
    "matching": "pareando",
    "searching": "procurando",
    "full": "cheia",
    "open": "aberta",
    "Result confirmed": "Resultado confirmado",
    "Result recorded (your opponent did not report)": "Resultado registrado (seu oponente não informou)",
    "Match decided by forfeit": "Partida decidida por W.O.",
    "Result decided by the games' state": "Resultado decidido pelo estado dos jogos",
    "You and your opponent reported different results -- not counted":
        "Você e seu oponente informaram resultados diferentes -- não conta",
    "No result": "Sem resultado",
    "confirmed": "confirmado",
    "forfeit": "W.O.",
    "one-sided": "unilateral",
    "disputed": "contestado",
    "resolved": "resolvido",
    "void": "anulado",
    "draw": "empate",
    "loss": "derrota",
    "win": "vitória",
    "the two games went out of sync": "os dois jogos dessincronizaram",
    "too short to count": "curta demais para contar",
    "a game crashed": "um jogo travou",
    "the reports disagreed": "os relatos não bateram",
    "left right away": "saiu na hora",
    "a player left": "um jogador saiu",
    "a player lost the connection": "um jogador perdeu a conexão",
    "a player did not report": "um jogador não informou",
    "the connection between the games failed": "a conexão entre os jogos falhou",
    "both players left": "os dois jogadores saíram",
    "no result in time": "sem resultado a tempo",
    "repeated crashes count as losses": "crashes repetidos contam como derrotas",
    "repeated early quits": "saídas antecipadas repetidas",
    "repeated missing reports": "relatos faltando repetidamente",
    "scores differed": "os placares não bateram",
    "the fight ended without a winner": "a luta terminou sem vencedor",
    "Match declined.": "Partida recusada.",
    "Nobody accepted in time.": "Ninguém aceitou a tempo.",
    "Your opponent left.": "Seu oponente saiu.",
    "No UDP connection to the lobby server (firewall?).": "Sem conexão UDP com o servidor do lobby (firewall?).",
    "Could not connect the two PCs, not even through the relay.":
        "Não foi possível conectar os dois PCs, nem pelo relay.",
    "The lobby server's relay is full; try again in a moment.":
        "O relay do servidor do lobby está cheio; tente de novo daqui a pouco.",
    "Challenge cancelled.": "Desafio cancelado.",
    "Challenge declined.": "Desafio recusado.",
    "Challenge expired.": "Desafio expirado.",
    "direct": "direta",
    "via the lobby server's relay": "pelo relay do servidor do lobby",
    "via the relay server {name}": "pelo servidor relay {name}",
    "Lobby error: {error}": "Erro do lobby: {error}",
    "guest": "convidado",
    "Not connected. Ranked needs an account; guests play casual matches.":
        "Não conectado. Ranked precisa de uma conta; convidados jogam partidas casuais.",
    "Passwords are only sent to servers on this PC / your network, or over an encrypted "
    "(TLS) connection.":
        "Senhas só são enviadas para servidores neste PC ou na sua rede, ou por uma conexão criptografada (TLS).",
    "Double-click a player in the lobby or the leaderboard.": "Clique duas vezes em um jogador no lobby ou no ranking.",
    "{name} (guest, casual matches only)": "{name} (convidado, só partidas casuais)",
    "{record} this session": "{record} nesta sessão",
    "rating {rating}": "pontos {rating}",
    "main {character}": "main {character}",
    "server ping {ms} ms": "ping do servidor {ms} ms",
    "encrypted": "criptografado",
    "[Server: {notice}]": "[Servidor: {notice}]",
    "Server notice: {notice}": "Aviso do servidor: {notice}",
    "The game is not built.": "O jogo não está compilado.",
    "This game is the European version ({title_id}): it plays offline only for now. Online play for the European version comes in a later update; it never plays against the US version (NPUB30009).":
        "Este jogo é a versão europeia ({title_id}): por enquanto ela só roda offline. O jogo online para a versão europeia virá em uma atualização futura; ela nunca joga contra a versão dos EUA (NPUB30009).",
    "Your game is the European version: offline only for now":
        "Seu jogo é a versão europeia: só offline por enquanto",
    "The European version ({title_id}) plays its offline modes. Online play for it comes in a later update; until then online play needs the US version (NPUB30009). European and US games never play each other online.":
        "A versão europeia ({title_id}) roda seus modos offline. O jogo online para ela virá em uma atualização futura; até lá o jogo online precisa da versão dos EUA (NPUB30009). Jogos europeus e dos EUA nunca jogam entre si online.",
    "Build stamp: the game is {title_id}.":
        "Carimbo do build: o jogo é {title_id}.",
    "This Mac build has no online play. For a test match: tools/build_game.py --macos-online (docs/MACOS_ONLINE_TEST.md).":
        "Esta compilação para Mac não tem jogo online. Para uma partida de teste: tools/build_game.py --macos-online (docs/MACOS_ONLINE_TEST.md).",
    "Cannot read the build's identity: {error}": "Não é possível ler a identidade da build: {error}",
    "Enter a password (6 characters or more), or play as a guest.":
        "Digite uma senha (6 caracteres ou mais), ou jogue como convidado.",
    "Connecting to {server}...": "Conectando a {server}...",
    "Pick a character, then Ranked match (accounts) or Quick match.":
        "Escolha um personagem e depois partida Ranked (com conta) ou Quick Match.",
    "Encrypted connection (TLS).": "Conexão criptografada (TLS).",
    "(logged in with your saved login)": "(entrou com seu login salvo)",
    "In the lobby.": "No lobby.",
    "Your saved login has expired; log in with your password.": "Seu login salvo expirou; entre com sua senha.",
    "Create account": "Criar conta",
    "Type the password again:": "Digite a senha de novo:",
    "The two passwords differ.": "As duas senhas são diferentes.",
    "Closing the running game for the online match...": "Fechando o jogo aberto para a partida online...",
    "Also forget the saved login on this PC?\n\n(No = you are logged in automatically "
    "next time.)":
        "Esquecer também o login salvo neste PC?\n\n(Não = você entra automaticamente na próxima vez.)",
    "Log out": "Sair da conta",
    "Not connected.": "Não conectado.",
    "Change password": "Mudar senha",
    "Current password:": "Senha atual:",
    "New password (6 characters or more):": "Nova senha (6 caracteres ou mais):",
    "New password again:": "Nova senha de novo:",
    "The two new passwords differ.": "As duas senhas novas são diferentes.",
    "Password changed. Saved logins on other PCs have ended.":
        "Senha alterada. Os logins salvos em outros PCs foram encerrados.",
    "Recovery codes": "Códigos de recuperação",
    "Your password (the old codes stop working):": "Sua senha (os códigos antigos param de funcionar):",
    "Save recovery codes": "Salvar códigos de recuperação",
    "T5DR Online recovery codes for {name} on {server}":
        "Códigos de recuperação do T5DR Online para {name} em {server}",
    "Forgot password": "Esqueci a senha",
    "Account name:": "Nome da conta:",
    "One of your recovery codes (XXXX-XXXX-XXXX):": "Um dos seus códigos de recuperação (XXXX-XXXX-XXXX):",
    "Password reset. {count} recovery code(s) left. Log in with the new password.":
        "Senha redefinida. Restam {count} código(s) de recuperação. Entre com a nova senha.",
    "Server certificate": "Certificado do servidor",
    "For a server with its own (self-signed) certificate: its SHA-256 fingerprint, from "
    "whoever runs it.\nEmpty = no pinning (use tls://host:port for a server with a "
    "normal certificate).":
        "Para um servidor com certificado próprio (autoassinado): a impressão digital SHA-256 dele, passada por quem "
        "o administra.\nVazio = sem fixação (use tls://host:port para um servidor com certificado normal).",
    "Searching for an opponent...": "Procurando oponente...",
    "Searching for an opponent (ranked: similar rank and a good connection, strict: "
    "within 150 rating points -- this can take a while)...":
        "Procurando oponente (Ranked: rank parecido e boa conexão, estrito: até 150 pontos de diferença -- pode "
        "demorar)...",
    "Searching for an opponent (ranked: similar rank and a good connection)...":
        "Procurando oponente (Ranked: rank parecido e boa conexão)...",
    "Select a room first.": "Primeiro escolha uma sala.",
    "Select an opponent in the list first.": "Primeiro escolha um oponente na lista.",
    "Challenge sent.": "Desafio enviado.",
    "Blocked players": "Jogadores bloqueados",
    "You are never matched with these players (ranked, quick matches, rooms, challenges, "
    "rematches). They are not told. Accounts stay blocked; a guest is blocked until you "
    "log out.":
        "Você nunca será pareado com esses jogadores (Ranked, Quick Match, salas, desafios, rematches). Eles não são "
        "avisados. Contas continuam bloqueadas; um convidado fica bloqueado até você sair da conta.",
    "Unblocked {name}.": "{name} desbloqueado.",
    "Unblock": "Desbloquear",
    "Block player": "Bloquear jogador",
    "Block {name}?\n\nYou will not be matched with them again. They are not told. You "
    "can unblock them under \"Blocked players...\".":
        "Bloquear {name}?\n\nVocê não será mais pareado com esse jogador. Ele não é avisado. Você pode desbloquear "
        "em “Jogadores bloqueados...”.",
    "Blocked {name}. You will not be matched again.": "{name} bloqueado. Vocês não serão mais pareados.",
    "you": "você",
    "{name} -- {rank}": "{name} -- {rank}",
    "Rating {rating} +/- {rd}": "Pontos {rating} +/- {rd}",
    "(provisional)": "(provisório)",
    "#{place} on the leaderboard": "#{place} no ranking",
    "Record {record}": "Campanha {record}",
    "Played {games}: {wins} won, {losses} lost, win rate {rate} %": "Jogadas {games}: {wins} vitórias, {losses} derrotas, {rate} % de vitórias",
    "Ranked {games}, {rate} % won": "Ranked {games}, {rate} % de vitórias",
    "Casual {games}, {rate} % won": "Casual {games}, {rate} % de vitórias",
    "Stats": "Estatísticas",
    "Community stats": "Estatísticas da comunidade",
    "Accounts": "Contas",
    "Matches": "Partidas",
    "Ranked matches": "Partidas ranked",
    "Last 24 hours": "Últimas 24 horas",
    "{matches} matches, {players} players": "{matches} partidas, {players} jogadores",
    "as of {when}": "em {when}",
    "All": "Todas",
    "Fighter": "Lutador",
    "Wins": "Vitórias",
    "Win rate": "% de vitórias",
    "Picked": "Escolhido",
    "No numbers yet.": "Ainda sem números.",
    "This lobby server has no stats page yet (it comes with server 1.1.5).":
        "Este servidor de lobby ainda não tem estatísticas (elas chegam com o servidor 1.1.5).",
    "Win rate per match; a mirror match counts as one win and one loss. Grey: fewer than {count} matches, not much to go on yet. Click a column to sort.":
        "Vitórias por partida; uma partida espelho conta como uma vitória e uma derrota. Em cinza: menos de {count} partidas, ainda pouco confiável. Clique numa coluna para ordenar.",
    "ranked matches {count}": "partidas Ranked {count}",
    "highest rank {rank}": "rank máximo {rank}",
    "Characters: {list}": "Personagens: {list}",
    "Matches without result caused in the last 24 h: {count}":
        "Partidas sem resultado causadas nas últimas 24 h: {count}",
    "Recovery codes left: {count}": "Códigos de recuperação restantes: {count}",
    "{you} vs {opponent}": "{you} vs {opponent}",
    "casual": "casual",
    "Opponent: {name} ({rank}, {rating})": "Oponente: {name} ({rank}, {rating})",
    "RANKED": "RANKED",
    "rematch": "Rematch",
    "{name} ({rank}) challenges you": "{name} ({rank}) te desafia",
    "Accept": "Aceitar",
    "Decline": "Recusar",
    "Challenge {state}.": "Desafio: {state}.",
    "connecting...": "conectando...",
    "Your opponent accepted.": "Seu oponente aceitou.",
    "Match cancelled ({reason}).": "Partida cancelada ({reason}).",
    "Ranked match vs {name}": "Partida Ranked contra {name}",
    "Casual match vs {name}": "Partida casual contra {name}",
    "{p1} vs {p2}": "{p1} vs {p2}",
    "ping {ms} ms ({how}), input delay {frames} frames ({delay_ms} ms)":
        "ping {ms} ms ({how}), input delay de {frames} frames ({delay_ms} ms)",
    "Lost the lobby connection -- reconnecting (your match goes on)...":
        "A conexão com o lobby caiu -- reconectando (sua partida continua)...",
    "Reconnected to the lobby.": "Reconectado ao lobby.",
    "Lost the lobby connection: {reason}": "A conexão com o lobby caiu: {reason}",
    "Lost the connection to the lobby server.": "A conexão com o servidor do lobby caiu.",
    "Removed from the lobby: {reason}": "Removido do lobby: {reason}",
    "The game closed. How did the match against {opponent} end?":
        "O jogo foi fechado. Como terminou a partida contra {opponent}?",
    "I won": "Ganhei",
    "I lost": "Perdi",
    "Draw": "Empate",
    "I quit": "Desisti",
    "{opponent} wants a rematch": "{opponent} quer Rematch",
    "Rematch": "Rematch",
    "No thanks": "Não, valeu",
    "Result sent; waiting for your opponent's report...": "Resultado enviado; esperando o relato do oponente...",
    "Rematch offered; waiting for your opponent...": "Rematch oferecido; esperando o oponente...",
    "(other version)": "(outra versão)",
    "other version": "outra versão",
    "ranked": "Ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "Procurando... ({ranked} na fila Ranked, {quick} no Quick Match)",
    "ping about {ms} ms (estimated; measured directly once you both accept)":
        "ping de uns {ms} ms (estimado; medido direto quando os dois aceitarem)",
    "ping not known yet": "ping ainda desconhecido",
    "Opponent found": "Oponente encontrado",
    "accept within {seconds} s?": "aceitar em {seconds} s?",
    "waiting for the opponent...": "esperando o oponente...",
    "Lag check: {text}": "Teste de lag: {text}",
    "You left after the lag check. No penalty, no rating change.":
        "Você saiu depois do teste de lag. Sem punição, sem mudança de pontos.",
    "Your opponent left after the lag check. No penalty for anyone.":
        "Seu oponente saiu depois do teste de lag. Ninguém é punido.",
    "Your opponent left. The set is over.": "Seu oponente saiu. O set acabou.",
    "Rematch {name}": "Rematch com {name}",
    "Next game": "Próxima partida",
    "Leave": "Sair",
    "Block {name}": "Bloquear {name}",
    "Leave: too laggy": "Sair: lag demais",
    "You lost.": "Você perdeu.",
    "You won.": "Você venceu.",
    "rating {rating} ({delta})": "pontos {rating} ({delta})",
    "PROMOTED to {rank}!": "PROMOVIDO a {rank}!",
    "demoted to {rank}": "rebaixado a {rank}",
    "placed at {rank}": "classificado em {rank}",
    "placement {done}/{total}": "classificação {done}/{total}",
    "your opponent": "seu oponente",
    "Rematch?": "Rematch?",
    "Controller off.": "Controle desligado.",
    "No controller found.": "Nenhum controle encontrado.",
    "Controller: {summary}": "Controle: {summary}",
    "Cannot start the lobby server: {error}": "Não é possível iniciar o servidor do lobby: {error}",
    "Stop hosting": "Parar de hospedar",
    "Starting a lobby server on this PC and asking the router to forward its ports...":
        "Iniciando um servidor de lobby neste PC e pedindo ao roteador para redirecionar as portas...",
    "Starting a lobby server on this PC...": "Iniciando um servidor de lobby neste PC...",
    "<your public IP>": "<seu IP público>",
    "Hosting. Friends paste this as their Server (copied to the clipboard):\n  {share}":
        "Hospedando. Seus amigos colam isto como Servidor (copiado para a área de transferência):\n  {share}",
    "\n  same network: {lan}": "\n  mesma rede: {lan}",
    "\n  Forward TCP+UDP 7781 and UDP 7782 on your router (or tick 'Open router ports').":
        "\n  Redirecione TCP+UDP 7781 e UDP 7782 no seu roteador (ou marque “Abrir portas do roteador”).",
    "Hosting a lobby on this PC. Log in to join it yourself.":
        "Hospedando um lobby neste PC. Entre para participar você também.",
    "Hosting failed: {message}": "Falha ao hospedar: {message}",
    "Host for friends": "Hospedar para amigos",
    "The lobby server stopped (exit code {code}); see its log in {folder}.":
        "O servidor do lobby parou (código de saída {code}); veja o log em {folder}.",
    "Stopped hosting.": "Hospedagem encerrada.",
    # in-game character select (branch ingame-select)
    "Pick your fighter in the game ({secs} s; Select = random; no pick = the character set here).":
        "Escolha seu lutador no jogo ({secs} s; Select = aleatório; sem escolha = o personagem daqui).",
    "Waiting for your opponent to pick...": "Esperando o oponente escolher...",
    "Ranked match (accounts) or Quick match; then pick your fighter in the game (Select = random). The character here is used when you do not pick in time.":
        "Partida Ranked (com conta) ou Quick Match; depois escolha seu lutador no jogo (Select = aleatório). O "
        "personagem daqui vale se você não escolher a tempo.",
    "pick your fighter in the game ({secs} s)": "escolha seu lutador no jogo ({secs} s)",
    "(locked for this ranked set)": "(fixo neste set Ranked)",
    "Pick your fighter in the game": "Escolha seu lutador no jogo",
    "Your opponent is picking": "Seu oponente está escolhendo",
    # ---- lobby/t5lobby/tk_views.py
    "Rank": "Rank",
    "Rating": "Pontos",
    "Record": "Campanha",
    "Main": "Main",
    "Ping": "Ping",
    "Room": "Sala",
    "Status": "Status",
    "Owner": "Dono",
    "Place": "Posição",
    "State": "Estado",
    "When": "Quando",
    "Characters": "Personagens",
    "Opponent": "Oponente",
    "Result": "Resultado",
    "Score": "Rounds",
    "Check the server address and your internet connection, then try again.":
        "Confira o endereço do servidor e sua conexão com a internet, depois tente de novo.",
    "Check your internet connection, then try again.": "Confira sua conexão com a internet, depois tente de novo.",
    "The server is slow or gone; try again in a minute.":
        "O servidor está lento ou fora do ar; tente de novo em um minuto.",
    "Log in again.": "Entre de novo.",
    "Ask whoever runs the server for its current fingerprint (\"Server certificate...\").":
        "Peça a quem administra o servidor a impressão digital atual (“Certificado do servidor...”).",
    "Check the spelling, or use \"Forgot password...\".": "Confira a digitação, ou use “Esqueci a senha...”.",
    "Check the name and the code; each code works once.": "Confira o nome e o código; cada código vale uma vez.",
    "Pick another name, or wait a minute if that was you.": "Escolha outro nome, ou espere um minuto se era você.",
    "Log in with that account's password, or pick another name.":
        "Entre com a senha dessa conta, ou escolha outro nome.",
    "Pick another name.": "Escolha outro nome.",
    "Update the game to the release this server asks for.": "Atualize o jogo para a versão que este servidor pede.",
    "You both need the same release of the game.": "Vocês dois precisam da mesma versão do jogo.",
    "Update the launcher to the newest release.": "Atualize o launcher para a versão mais recente.",
    "Create an account (free) to play ranked.": "Crie uma conta (grátis) para jogar Ranked.",
    "Pick another room or create your own.": "Escolha outra sala ou crie a sua.",
    "Log in with your password.": "Entre com sua senha.",
    "Build the game on the Build tab first.": "Primeiro compile o jogo na aba Compilar.",
    "Allow T5DR Online through the Windows firewall, then search again.":
        "Libere o T5DR Online no firewall do Windows e procure de novo.",
    "Try again; if it keeps failing, check your firewall or router.":
        "Tente de novo; se continuar falhando, confira seu firewall ou roteador.",
    "Log in again; your settings are kept.": "Entre de novo; suas configurações são mantidas.",
    "Type the same password twice.": "Digite a mesma senha duas vezes.",
    "Find a new opponent.": "Procure um novo oponente.",
    "Check the Play offline tab: does the game start there?": "Confira a aba Jogar offline: o jogo abre lá?",
    "Against other players over the internet. Log in or play as a guest; the game starts "
    "by itself, straight into the fight, and the result comes back here.":
        "Contra outros jogadores pela internet. Entre ou jogue como convidado; o jogo abre sozinho, direto na luta, "
        "e o resultado volta para cá.",
    "Server": "Servidor",
    "Server certificate...": "Certificado do servidor...",
    "Name": "Nome",
    "Log in": "Entrar",
    "Password": "Senha",
    "Password again": "Repetir senha",
    "Name: 2 to 16 letters, digits, spaces or _-.[]()!?": "Nome: 2 a 16 letras, números, espaços ou _-.[]()!?",
    "Password: 6 to 128 characters": "Senha: 6 a 128 caracteres",
    "Both passwords the same": "As duas senhas iguais",
    "You get recovery codes once: the only way back in if you forget the password":
        "Você recebe códigos de recuperação uma vez: o único jeito de voltar se esquecer a senha",
    "Remember me": "Lembrar de mim",
    "Forgot password...": "Esqueci a senha...",
    "Casual matches with the name above, no account and no password. Ranked matches, the "
    "leaderboard and your match history need an account.":
        "Partidas casuais com o nome acima, sem conta e sem senha. Partidas Ranked, o ranking e seu histórico de "
        "partidas precisam de uma conta.",
    "Play as guest": "Jogar como convidado",
    "Runs a lobby on this PC. Your friends type the address it shows into their Server "
    "box.":
        "Roda um lobby neste PC. Seus amigos digitam o endereço mostrado no campo Servidor.",
    "Open router ports (UPnP)": "Abrir portas do roteador (UPnP)",
    "How it works": "Como funciona",
    "Quick match (casual) or Ranked match (account).": "Quick Match (casual) ou partida Ranked (com conta).",
    "An opponent is found: accept within 15 seconds.": "Um oponente é encontrado: aceite em até 15 segundos.",
    "The game opens straight into the fight.": "O jogo abre direto na luta.",
    "The result comes back here: rematch or next game.": "O resultado volta para cá: Rematch ou próxima partida.",
    "With a controller: A accepts, B declines.": "Com controle: A aceita, B recusa.",
    "Online nobody can pause the fight: Start does not open the pause menu.":
        "Online ninguém pode pausar a luta: Start não abre o menu de pausa.",
    "Intros and the replay after a round are skipped once both players have pressed Start.":
        "As introduções e o replay depois de um round são pulados quando os dois jogadores apertam Start.",
    "Lobby": "Lobby",
    "Leaderboard": "Ranking",
    "Profile": "Perfil",
    "My profile": "Meu perfil",
    "Find an opponent online": "Encontre um oponente online",
    "Character": "Personagem",
    "Choose your fighter": "Escolha seu lutador",
    "{star} your main: {character}": "{star} seu main: {character}",
    "Arrow keys move, Enter picks, Esc closes. With a controller: Cross / A picks, Circle / B closes.":
        "As setas movem, Enter escolhe, Esc fecha. Com controle: X / A escolhe, Círculo / B fecha.",
    "Locked for this ranked set": "Fixo neste set Ranked",
    "Ranked match": "Partida Ranked",
    "Quick match": "Quick Match",
    "Casual: the lowest ping first": "Casual: o menor ping primeiro",
    "Strict (ranked: +-150 rating)": "Estrito (Ranked: +-150 pontos)",
    "Searching": "Procurando",
    "Looking for an opponent": "Procurando um oponente",
    "Searching for": "Procurando há",
    "Stop searching": "Parar de procurar",
    "In match": "Em partida",
    "CASUAL": "CASUAL",
    "Input delay": "Input delay",
    "Connection": "Conexão",
    "Players online": "Jogadores online",
    "Challenge": "Desafiar",
    "Rooms": "Salas",
    "Create room": "Criar sala",
    "Join room": "Entrar na sala",
    "Leave room": "Sair da sala",
    "Chat": "Chat",
    "Send": "Enviar",
    "Refresh": "Atualizar",
    "Order: rating minus twice its uncertainty (a few matches are needed to climb). '?' "
    "= provisional.":
        "Ordem: pontos menos o dobro da incerteza (algumas partidas são necessárias para subir). “?” = provisório.",
    "Your account": "Sua conta",
    "Blocked players...": "Jogadores bloqueados...",
    "Change password...": "Mudar senha...",
    "New recovery codes...": "Novos códigos de recuperação...",
    "Dismiss": "Ocultar",
    "Use a controller here": "Usar um controle aqui",
    "none open": "nenhuma aberta",
    "Nobody else is online right now. Ranked match and Quick match keep looking until someone comes.":
        "Ninguém mais está online agora. Partida Ranked e Quick Match continuam procurando até alguém chegar.",
    "No rooms open. Create one: friends can join it and play in turn.":
        "Nenhuma sala aberta. Crie uma: seus amigos podem entrar e jogar em rodízio.",
    "Nobody has a ranked result yet. Win a ranked set to be the first.":
        "Ninguém tem resultado ranqueado ainda. Vença um set ranqueado e seja o primeiro.",
    "In your room “{name}”. Waiting for a second player...": "Na sua sala “{name}”. Esperando um segundo jogador...",
    "In the room “{name}”. The match starts when you are both ready.":
        "Na sala “{name}”. A partida começa quando os dois estiverem prontos.",
    "Hosting. Friends type this as their Server:\n{share}":
        "Hospedando. Seus amigos digitam isto como Servidor:\n{share}",
    "Same network: {lan}": "Mesma rede: {lan}",
    "Guest · casual matches": "Convidado · partidas casuais",
    "Rating {rating}  ·  {record}": "Pontos {rating}  ·  {record}",
    "Main: {character}": "Main: {character}",
    "Server ping {ms} ms": "Ping do servidor {ms} ms",
    "Create an account to play ranked": "Crie uma conta para jogar Ranked",
    "Rated: close to your rank, good connection": "Valendo pontos: perto do seu rank, boa conexão",
    "Similar rank and a good connection, strict: within 150 rating points (this can take "
    "a while).":
        "Rank parecido e boa conexão, estrito: até 150 pontos de diferença (pode demorar).",
    "Similar rank and a good connection.": "Rank parecido e boa conexão.",
    "The opponent with the lowest ping first.": "Primeiro o oponente com o menor ping.",
    "{ranked} in the ranked queue  ·  {quick} in quick match": "{ranked} na fila Ranked  ·  {quick} no Quick Match",
    "Character select": "Seleção de personagem",
    "Stage select": "Seleção de cenário",
    "Match over": "Partida encerrada",
    "Waiting for the next match": "Esperando a próxima partida",
    "Your game is running": "Seu jogo está rodando",
    "Starting the game...": "Iniciando o jogo...",
    "Waiting for the game...": "Esperando o jogo...",
    "vs your opponent": "contra seu oponente",
    "vs {name}": "contra {name}",
    "{count} frame  ({ms} ms)": "{count} frame  ({ms} ms)",
    "{count} frames  ({ms} ms)": "{count} frames  ({ms} ms)",
    "Direct": "Direta",
    "Local network": "Rede local",
    "Relay (lobby server)": "Relay (servidor do lobby)",
    "Relay ({name})": "Relay ({name})",
    "Guest": "Convidado",
    "{rank}  ·  rating {rating}": "{rank}  ·  {rating} pontos",
    "SET · GAME {game}": "SET · PARTIDA {game}",
    "Opponent hidden": "Oponente oculto",
    "Name and side are shown once you both accept.": "Nome e lado aparecem quando os dois aceitarem.",
    "(estimated before you connect)": "(estimado antes de conectar)",
    "(measured in your last match together)": "(medido na última partida de vocês)",
    "ping {ms} ms (measured in your last match together)": "ping de {ms} ms (medido na última partida de vocês)",
    "probably a direct connection": "provavelmente uma conexão direta",
    "probably over the local network": "provavelmente pela rede local",
    "probably through a relay server": "provavelmente por um servidor relay",
    "Accepted. Waiting for your opponent...": "Aceito. Esperando o oponente...",
    "Match ready": "Partida pronta",
    "Connecting the two games...": "Conectando os dois jogos...",
    "wants to play you. Accept to start the match.": "quer jogar com você. Aceite para começar a partida.",
    "YOU WIN": "VOCÊ VENCEU",
    "YOU LOSE": "VOCÊ PERDEU",
    "DRAW": "EMPATE",
    "MATCH OVER": "PARTIDA ENCERRADA",
    "NO CONTEST": "SEM RESULTADO",
    "Casual match": "Partida casual",
    "ROUNDS  (P1 – P2)": "ROUNDS  (P1 – P2)",
    "ROUNDS  (YOU – THEM)": "ROUNDS  (VOCÊ – OPONENTE)",
    "GAMES  (YOU – THEM)": "PARTIDAS  (VOCÊ – OPONENTE)",
    "SET WON": "SET VENCIDO",
    "The game waits here for your next match: Rematch, Next game or Leave.":
        "O jogo espera aqui pela sua próxima partida: Rematch, Próxima partida ou Sair.",
    "SET LOST": "SET PERDIDO",
    "Ranked set": "Set Ranked",
    "Ranked set vs {name}": "Set Ranked contra {name}",
    "RANKED SET · BEST OF {best}": "SET RANKED · MELHOR DE {best}",
    "Game {number} of {best} starts in": "A partida {number} de {best} começa em",
    "Game {number} of {best} again (no winner), starts in":
        "Partida {number} de {best} de novo (sem vencedor), começa em",
    "Rating {rating}": "Pontos {rating}",
    "PROMOTED": "PROMOVIDO",
    "DEMOTED": "REBAIXADO",
    "PLACED": "CLASSIFICADO",
    "Placement match {done} of {total}": "Partida de classificação {done} de {total}",
    "Lag check": "Teste de lag",
    "Rematch offered. Waiting for {opp}...": "Rematch oferecido. Esperando {opp}...",
    "Back to the lobby": "Voltar ao lobby",
    "New recovery codes": "Novos códigos de recuperação",
    "Your account is ready": "Sua conta está pronta",
    "These codes are the only way back into your account if you forget the password "
    "(there is no e-mail). Each code works once. Write them down or save them somewhere "
    "safe -- they are not shown again.":
        "Estes códigos são o único jeito de voltar à sua conta se você esquecer a senha (não há e-mail). Cada código "
        "vale uma vez. Anote ou salve em um lugar seguro -- eles não são mostrados de novo.",
    "Save to a file...": "Salvar em um arquivo...",
    "I have saved them": "Já salvei",
    # ---- friends (tk_tab.py, tk_views.py)
    "Request": "Pedido",
    "Friends": "Amigos",
    "Invite to a match": "Convidar para uma partida",
    "Invite to my room": "Convidar para minha sala",
    "Invite in {seconds} s": "Convidar em {seconds} s",
    "Remove": "Remover",
    "Invite a friend who is online: one click on their side starts a casual match, or brings them into your room.":
        "Convide um amigo que está online: um clique do lado dele começa uma partida casual ou o traz para a sua "
        "sala.",
    "Add a friend": "Adicionar amigo",
    "Send request": "Enviar pedido",
    "Their account name. They become your friend when they accept.":
        "O nome da conta da pessoa. Vocês viram amigos quando ela aceitar.",
    "Requests": "Pedidos",
    "Take back": "Retirar",
    "Invite from a friend": "Convite de um amigo",
    "invites you to the room “{room}”. Accept to join it; the match starts at once.":
        "te convida para a sala “{room}”. Aceite para entrar; a partida começa na hora.",
    "invites you to a casual match. Accept to start it.": "te convida para uma partida casual. Aceite para começar.",
    "Check the spelling: friends are added by their account name.":
        "Confira a digitação: amigos são adicionados pelo nome da conta.",
    "in a match": "em partida",
    "offline": "offline",
    "older launcher: no invites": "launcher antigo: sem convites",
    "Friends ({count})": "Amigos ({count})",
    "offline, last seen {when}": "offline desde {when}",
    "Friends need an account. Log in with one to add friends and invite them.":
        "Amigos precisam de uma conta. Entre com uma para adicionar amigos e convidá-los.",
    "This lobby server has no friends list (it needs version 1.1.2 or newer).":
        "Este servidor de lobby não tem lista de amigos (precisa da versão 1.1.2 ou mais nova).",
    "wants to be your friend": "quer ser seu amigo",
    "asked: waiting for an answer": "aguardando resposta",
    "{online} online · {count} of {max}": "{online} online · {count} de {max}",
    "Your friends see when you are online. Invite one who is online to play.":
        "Seus amigos veem quando você está online. Convide um que esteja online para jogar.",
    "No friends yet. Add one by account name: they become your friend when they accept.":
        "Nenhum amigo ainda. Adicione pelo nome da conta: vocês viram amigos quando a pessoa aceitar.",
    "Cancel the invite": "Cancelar o convite",
    "You and {name} are friends now.": "Você e {name} agora são amigos.",
    "Friend request sent to {name}. They become your friend when they accept.":
        "Pedido de amizade enviado para {name}. Vocês viram amigos quando a pessoa aceitar.",
    "Request from {name} declined.": "Pedido de {name} recusado.",
    "Request to {name} taken back.": "Pedido para {name} retirado.",
    "Remove friend": "Remover amigo",
    "Remove {name} from your friends?\n\nYou can ask again later; they have to accept again.":
        "Remover {name} dos seus amigos?\n\nVocê pode pedir de novo depois; a pessoa terá que aceitar outra vez.",
    "{name} is no longer your friend.": "{name} não é mais seu amigo.",
    "Select a friend in the list first.": "Primeiro escolha um amigo na lista.",
    "Invite sent to {name}; waiting for an answer ({seconds} s)...":
        "Convite enviado para {name}; esperando resposta ({seconds} s)...",
    "{name} ({rank}) invites you to the room “{room}”": "{name} ({rank}) te convida para a sala “{room}”",
    "{name} ({rank}) invites you to a casual match": "{name} ({rank}) te convida para uma partida casual",
    "The invite from {name} ran out.": "O convite de {name} expirou.",
    "The invite from {name} ended.": "O convite de {name} terminou.",
    "{name} declined your invite.": "{name} recusou seu convite.",
    "{name} did not answer your invite.": "{name} não respondeu ao seu convite.",
    "The invite to {name} ended.": "O convite para {name} terminou.",
    "{name} wants to be your friend: see the Friends tab.": "{name} quer ser seu amigo: veja a aba Amigos.",
    "{name} accepted your friend request.": "{name} aceitou seu pedido de amizade.",
    "{name} declined your friend request.": "{name} recusou seu pedido de amizade.",

    # ---- launcher/replays_ui.py, launcher/t5dr_launcher.pyw (Replays tab), problem_report.py
    "Replays":
        "Replays",
    "Every online match is saved here. Watch plays it back in the game exactly as it was played: the same inputs frame by frame, checked against the live match while it plays.":
        "Toda partida online fica salva aqui. Assistir reproduz no jogo exatamente como foi jogada: as mesmas entradas quadro a quadro, comparadas com a partida ao vivo enquanto reproduz.",
    "Date":
        "Data",
    "Fighters":
        "Lutadores",
    "Netcode":
        "Netcode",
    "WATCH":
        "ASSISTIR",
    "Stop replay":
        "Parar replay",
    "Delete":
        "Apagar",
    "Open replays folder":
        "Abrir pasta de replays",
    "While a replay plays: START (Enter) pauses and goes on, SELECT (Tab) ends the replay. A "
    "rematch is played after the matches before it in the same session: it starts from what they "
    "left.":
        "Durante um replay: START (Enter) pausa e continua, SELECT (Tab) encerra o replay. Uma revanche é "
        "reproduzida depois das partidas anteriores da mesma sessão: ela começa de onde elas pararam.",
    "Save online matches as replays":
        "Salvar partidas online como replays",
    "Watch replay": "Ver replay",
    "{count} of these matches have a replay on this PC ({mark}). Select one to watch it.":
        "{count} destas partidas têm replay neste PC ({mark}). Escolha uma para assistir.",
    "None of these matches has a replay on this PC (replays are saved on the PC that played, while \"Save online matches as replays\" is on).":
        "Nenhuma destas partidas tem replay neste PC (os replays são salvos no PC que jogou, enquanto \"Salvar partidas online como replays\" está ativado).",
    "No replay of this match on this PC.": "Não há replay desta partida neste PC.",
    "{fighters}, saved on this PC.": "{fighters}, salvo neste PC.",
    "This replay is no longer on this PC.": "Este replay não está mais neste PC.",
    "Keep the players' names in replays":
        "Guardar os nomes dos jogadores nos replays",
    "Rollback":
        "Rollback",
    "Lockstep":
        "Lockstep",
    "(name not saved)":
        "(nome não salvo)",
    "{matches} match(es) in {files} file(s) in {folder}":
        "{matches} partida(s) em {files} arquivo(s) em {folder}",
    "No replays yet. Play an online match: it is saved here.":
        "Ainda não há replays. Jogue uma partida online: ela fica salva aqui.",
    "not finished":
        "não terminada",
    "won {mine}-{theirs}":
        "venceu {mine}-{theirs}",
    "lost {mine}-{theirs}":
        "perdeu {mine}-{theirs}",
    "Close the running game first (Stop game on the Play tab).":
        "Feche primeiro o jogo aberto (Parar o jogo na aba Jogar offline).",
    "Build the game first (Build tab).":
        "Compile o jogo primeiro (aba Compilar).",
    "This replay cannot be played: {why}":
        "Este replay não pode ser reproduzido: {why}",
    "Recorded with another version of the game: it may not play back the same.":
        "Gravado com outra versão do jogo: pode não reproduzir igual.",
    "Playing {fighters} ({when})...":
        "Reproduzindo {fighters} ({when})...",
    "The replay ended before the end of the match.":
        "O replay terminou antes do fim da partida.",
    "Replay over: identical to the live match ({checks} checks, same result).":
        "Replay terminado: idêntico à partida ao vivo ({checks} verificações, mesmo resultado).",
    "Replay over, but it went a different way from frame {frame} on (the game or its version differs from the one that played it).":
        "Replay terminado, mas a partir do quadro {frame} foi diferente (o jogo ou a versão dele não é o que jogou a partida).",
    "Replay over.":
        "Replay terminado.",
    "Delete this replay file? It holds {n} match(es) against the same opponent.":
        "Apagar este arquivo de replay? Ele tem {n} partida(s) contra o mesmo oponente.",
    # ---- lobby/t5lobby/tk_spectate.py, server/spectating.py, launcher Settings (spectating live matches)
    "Spectators":
        "Espectadores",
    "Friends and room visitors may watch my online matches":
        "Amigos e visitantes da minha sala podem assistir às minhas partidas online",
    "Also my ranked matches":
        "Também as minhas partidas Ranked",
    "They see the match a few seconds late, in their own game. Only when both players allow it; a "
    "ranked match only when both allow ranked too.":
        "Eles veem a partida alguns segundos depois, no próprio jogo. Só quando os dois jogadores "
        "permitem; uma partida Ranked só quando os dois permitem Ranked também.",
    "Watch":
        "Assistir",
    "Spectating":
        "Assistindo",
    "Stop watching":
        "Parar de assistir",
    "Watching":
        "Assistindo ao vivo",
    "Waiting for the match data...":
        "Esperando os dados da partida...",
    "About {seconds} s behind the live match.":
        "Cerca de {seconds} s atrás da partida ao vivo.",
    "It plays from the start of the players' session, a few seconds behind.":
        "Começa no início da sessão dos jogadores, alguns segundos atrás.",
    "Watching {p1} vs {p2}.":
        "Assistindo {p1} vs {p2}.",
    "Spectators watching your match: {count}":
        "Espectadores da sua partida: {count}",
    "The live match is over.":
        "A partida ao vivo acabou.",
    "The players turned spectators off.":
        "Os jogadores desligaram os espectadores.",
    "The match data stopped coming.":
        "Os dados da partida pararam de chegar.",
    "This session is too long to watch from its start.":
        "Esta sessão é longa demais para assistir desde o início.",
    "Your own match is starting.":
        "A sua própria partida está começando.",
    "The match data was damaged.":
        "Os dados da partida estavam danificados.",
    "You stopped watching.":
        "Você parou de assistir.",
    "A friend of the players took your place: the match has as many spectators as it can take.":
        "Um amigo dos jogadores ficou com o seu lugar: a partida já tem todos os espectadores que aceita.",
    "this launcher cannot watch matches; update it":
        "este launcher não pode assistir partidas; atualize-o",
    "that match is not being played right now":
        "essa partida não está sendo jogada agora",
    "you are playing in that match":
        "você está jogando nessa partida",
    "you are in a match yourself":
        "você já está em uma partida",
    "only friends of a player can watch this match":
        "só amigos de um jogador podem assistir esta partida",
    "the players do not allow spectators":
        "os jogadores não permitem espectadores",
    "neither player can send the match right now":
        "agora nenhum jogador pode enviar a partida",
    "this match cannot be watched any more":
        "esta partida não pode mais ser assistida",
    "this match has {count} spectators already":
        "esta partida já tem {count} espectadores",
    "the server cannot show more matches right now":
        "o servidor não pode mostrar mais partidas agora",
    "too many matches are watched from your network; stop watching one first":
        "partidas demais estão sendo assistidas da sua rede; pare de assistir uma primeiro",
    "the places for guests at this match are taken; log in with an account to watch":
        "os lugares para convidados nesta partida estão ocupados; entre com uma conta para assistir",
    "the server cannot show guests more matches right now; log in with an account to watch":
        "o servidor não pode mostrar mais partidas a convidados agora; entre com uma conta para assistir",
    # firewall hint on the Online tab (t5lobby.fwcheck, tk_tab.fw_hint_text)
    "Firewall":
        "Firewall",
    "How to fix":
        "Como resolver",
    "Windows Firewall blocks {program} on this network. Matches still connect, but some only "
    "through a relay, with more lag.":
        "O firewall do Windows bloqueia o {program} nesta rede. As partidas ainda se conectam, "
        "mas algumas só por um relay, com mais lag.",
    "A firewall seems to block T5DR Online's network traffic on this PC.":
        "Parece que um firewall bloqueia o tráfego de rede do T5DR Online neste PC.",
    # patch 0063 (igpu-4k-stall): Internal resolution Auto, integrated-graphics and GPU-bound hints
    "Auto (matches the screen)":
        "Auto (conforme a tela)",
    "The game picks the step that matches your screen when it starts, at most 1080p on integrated graphics (they share the processor's memory and power).":
        "O jogo escolhe ao iniciar o nível que combina com a sua tela, no máximo 1080p com gráficos integrados (eles dividem a memória e a energia do processador).",
    "On this PC: {step}.":
        "Neste PC: {step}.",
    "{step} on integrated graphics: a busy built-in GPU slows the processor too (they share its power and memory). For 60 fps choose Auto in Settings -> Internal resolution: {better} here.":
        "{step} com gráficos integrados: uma GPU integrada ocupada também deixa o processador mais lento (eles dividem a energia e a memória). Para 60 fps, escolha Auto em Configurações -> Resolução interna: aqui {better}.",
    "Auto is the default on integrated graphics.":
        "Com gráficos integrados, Auto é o padrão.",
    "Your processor ran at {ghz} GHz ({percent} % of its normal speed): set Windows power mode to Best performance.":
        "Seu processador rodou a {ghz} GHz ({percent} % da velocidade normal): coloque o modo de energia do Windows em Melhor desempenho.",
    "Extra settings below set {setting}: that wins over this choice.":
        "As configurações extras abaixo definem {setting}: isso vale no lugar desta escolha.",
    "Fights were slower than 60 fps because of the graphics (GPU-bound): choose a lower Internal resolution in Settings.":
        "As lutas ficaram abaixo de 60 fps por causa dos gráficos (limitado pela GPU): escolha uma resolução interna menor em Configurações.",
    "Fights were slower than 60 fps: the integrated graphics were busy and slowed the processor too. A lower Internal resolution in Settings helps.":
        "As lutas ficaram abaixo de 60 fps: os gráficos integrados estavam ocupados e deixaram o processador mais lento também. Uma resolução interna menor em Configurações ajuda.",
    "Fights were slower than 60 fps because of the graphics card: it is too slow for this game. Internal resolution Lowest helps a little at most.":
        "As lutas ficaram abaixo de 60 fps por causa da placa de vídeo: ela é lenta demais para este jogo. A resolução interna Mínima ajuda pouco, no máximo.",
    "Fights were slower than 60 fps because of the processor: close other programs while you play. A lower Internal resolution does not help.":
        "As lutas ficaram abaixo de 60 fps por causa do processador: feche outros programas enquanto joga. Uma resolução interna menor não ajuda.",
    # ---- private and community rooms (lobby/t5lobby/tk_rooms.py; the server's messages: i18n_known.py)
    "private rooms need a newer launcher; update it": "salas privadas precisam de um launcher mais novo; atualize-o",
    "only the room's host can do that": "só o anfitrião da sala pode fazer isso",
    "too many wrong room passwords; try again in {seconds} s":
        "senhas de sala erradas demais; tente de novo em {seconds} s",
    "wrong room password": "senha da sala errada",
    "the room's password changed; try again": "a senha da sala mudou; tente de novo",
    "no room has that invite code": "nenhuma sala tem esse código de convite",
    "rooms hold 2 to {count} players": "as salas têm de 2 a {count} jogadores",
    "room passwords are 4-64 characters, no space at either end":
        "senhas de sala têm 4-64 caracteres, sem espaço no começo ou no fim",
    "private and community rooms are casual (unranked)": "salas privadas e de comunidade são casuais (sem Ranked)",
    "you are in that room": "você já está nessa sala",
    "the room's host removed you from this room": "o anfitrião removeu você desta sala",
    "the room's host turned away password guesses from your network; ask the host for an invite":
        "o anfitrião da sala bloqueou as tentativas de senha da sua rede; peça um convite a ele",
    "only a room with a password counts wrong guesses": "só uma sala com senha conta as tentativas erradas",
    "that player is not in your room": "esse jogador não está na sua sala",
    "you cannot remove yourself; leave the room instead": "você não pode remover a si mesmo; saia da sala",
    "you can remove that player after their match": "você pode remover esse jogador depois da partida dele",
    "only rooms for 3 or more players take turns": "só salas de 3 ou mais jogadores se revezam",
    "you sit out in the room; press Back in line to play again":
        "você está de fora na sala; aperte Voltar para a fila para jogar de novo",
    "the room picks the next match by itself": "a sala escolhe a próxima partida sozinha",
    "the room's host removed that player from this room": "o anfitrião removeu esse jogador desta sala",
    "only the room's players can watch its match": "só os jogadores da sala podem assistir à partida dela",
    "Anybody": "Qualquer um",
    "Back in line": "Voltar para a fila",
    "Back in line: you play when it is your turn.": "De volta na fila: você joga quando for a sua vez.",
    "Copy invite code": "Copiar código de convite",
    "Create a room": "Criar uma sala",
    "Everyone in turn": "Todos em rodízio",
    "Hide the room from the room list": "Esconder a sala da lista de salas",
    "In the room “{name}”: {count}/{size} players, taking turns.":
        "Na sala “{name}”: {count}/{size} jogadores, em rodízio.",
    "Invite code": "Código de convite",
    "Line: {names}": "Fila: {names}",
    "New invite code": "Novo código de convite",
    "Next: {p1} vs {p2} in {seconds} s": "Próxima: {p1} vs {p2} em {seconds} s",
    "No room selected. Join a room with its invite code (XXXX-XXXX-XXXX):":
        "Nenhuma sala escolhida. Entre numa sala com o código de convite (XXXX-XXXX-XXXX):",
    "Password (4-64 characters):": "Senha (4-64 caracteres):",
    "Players in the room:": "Jogadores na sala:",
    "Players:": "Jogadores:",
    "Playing: {p1} vs {p2}": "Jogando: {p1} vs {p2}",
    "Private (invite code)": "Privada (código de convite)",
    "Private (password)": "Privada (senha)",
    "Remove player": "Remover jogador",
    "Remove {name} from the room? They cannot come back into it.": "Remover {name} da sala? Não vai poder voltar.",
    "Removed {name} from the room.": "{name} foi removido da sala.",
    "Wrong passwords in the last 10 minutes: {count} (networks: {networks})":
        "Senhas erradas nos últimos 10 minutos: {count} (redes: {networks})",
    "Turn away the guessers": "Bloquear quem tenta adivinhar",
    "Networks turned away: {count}. They cannot try passwords on this room any more.":
        "Redes bloqueadas: {count}. De lá ninguém pode mais tentar senhas nesta sala.",
    "Room created.": "Sala criada.",
    "Room created. Press Copy invite code to see the code you can share.":
        "Sala criada. Aperte Copiar código de convite para ver o código que você pode compartilhar.",
    "Room name (optional):": "Nome da sala (opcional):",
    "Room password": "Senha da sala",
    "Room passwords are 4-64 characters, with no space at the start or end.":
        "Senhas de sala têm 4-64 caracteres, sem espaço no começo ou no fim.",
    "Room settings": "Configurações da sala",
    "Room settings saved.": "Configurações da sala salvas.",
    "Room settings...": "Configurações da sala...",
    "Sit out": "Ficar de fora",
    "The invite code is in the field next to the button: select it and press Ctrl+C to copy it.":
        "O código de convite está no campo ao lado do botão: selecione e aperte Ctrl+C para copiar.",
    "The room's invite code (XXXX-XXXX-XXXX):": "Código de convite da sala (XXXX-XXXX-XXXX):",
    "Turns (3 or more players):": "Rodízio (3 ou mais jogadores):",
    "Who can join:": "Quem pode entrar:",
    "Winner stays": "Quem ganha fica",
    "You sit out: your turns are skipped until you press Back in line.":
        "Você está de fora: sua vez é pulada até apertar Voltar para a fila.",
    "Your room: {name}": "Sua sala: {name}",
    "hidden": "oculta",
    "invites you to the private room “{room}”. Accept to join it without its password.":
        "te convida para a sala privada “{room}”. Aceite para entrar sem a senha.",
    "private": "privada",
    "private (invite code)": "privada (código de convite)",
    "private (password)": "privada (senha)",
    "{count}/{size} players": "{count}/{size} jogadores",
    "{name} (host)": "{name} (anfitrião)",
    "{name} (sitting out)": "{name} (de fora)",
    "{name} ({rank}) invites you to the private room “{room}”":
        "{name} ({rank}) te convida para a sala privada “{room}”",
    "“{room}” is private. Its password:": "“{room}” é privada. A senha:",
    "this server has no private rooms": "este servidor não tem salas privadas",
    # training rooms and the health handicap (1.1.5)
    "My health (casual)": "Minha vida (casual)",
    "TRAINING OVER": "TREINO ENCERRADO",
    "TRAINING: endless health, nothing counted; hold SELECT for 1 s to pick again": "TREINO: vida infinita, nada conta; segure SELECT por 1 s para escolher de novo",
    "Training fight over -- nothing is counted": "Luta de treino encerrada -- nada é contado",
    "Training room: endless health, nothing counted": "Sala de treino: vida infinita, nada conta",
    "Training vs {name}": "Treino contra {name}",
    "health: you {you} %, opponent {opponent} %": "vida: você {you} %, oponente {opponent} %",
    "training": "treino",
    "training: endless health, nothing counted": "treino: vida infinita, nada conta",
    "{percent} %": "{percent} %",
    "training rooms need a newer launcher; update it": "salas de treino precisam de um launcher mais novo; atualize-o",
    "training rooms are casual (unranked)": "salas de treino são casuais (sem ranking)",
    "the health handicap needs a newer launcher; update it": "a desvantagem de vida precisa de um launcher mais novo; atualize-o",
    "life is 30 to 100 in steps of 10": "a vida vai de 30 a 100 em passos de 10",
    "life is 30 to 150 in steps of 10": "a vida vai de 30 a 150 em passos de 10",
    "this server has no training rooms": "este servidor não tem salas de treino",
    "this server has no health handicap": "este servidor não tem desvantagem de vida",
    # Settings -> Graphics (patch 0079)
    "Graphics (weak graphics cards)":
        "Gráficos (placas de vídeo fracas)",
    "Shadows":
        "Sombras",
    "Effects":
        "Efeitos",
    "On (default)":
        "Ligado (padrão)",
    "Off: no shadows of the fighters and the stage. Saves graphics work and some processor time.":
        "Desligado: sem sombras dos lutadores e do cenário. "
        "Economiza trabalho gráfico e um pouco de tempo do "
        "processador.",
    "Off: no hit sparks or other hit effects (also the EWGF lightning), flames, smoke, mist, glows or "
    "waterfalls. Saves graphics work (the most on misty stages) and some processor time.":
        "Desligado: sem faíscas nem outros efeitos de golpes "
        "(nem o raio do EWGF), chamas, fumaça, névoa, brilhos ou "
        "cachoeiras. Economiza trabalho gráfico (mais nos "
        "cenários com névoa) e um pouco de tempo do processador.",
    "Lowest (old graphics cards)":
        "Mínimo (placas de vídeo antigas)",
    "Default":
        "Padrão",
    "Lowest: Internal resolution Lowest; stage blur / glow and shadows off. Effects stay on: the hit effects show what happens in a fight. Default puts them back. Only your picture changes: online, both players can choose differently.":
        "Mínimo: resolução interna Mínima; desfoque / brilho dos cenários e sombras desligados. Os efeitos continuam ligados: os efeitos de golpes mostram o que acontece na luta. Padrão os restaura. Só a sua imagem muda: online, cada jogador pode escolher a sua.",
    # ---- lobby/t5lobby/tk_casual.py
    "Any side": "Qualquer lado",
    "P1 (left)": "P1 (esquerda)",
    "P2 (right)": "P2 (direita)",
    "Challenges, invites, rooms:": "Desafios, convites, salas:",
    "Random stage": "Cenário aleatório",
    "wants to be P{n} on {stage}": "quer ser P{n} em {stage}",
    "wants to be P{n}": "quer ser P{n}",
    "wants to play on {stage}": "quer jogar em {stage}",
    "You both wanted P{n}: a coin flip made you P{m}.":
        "Vocês dois queriam ser P{n}: no cara ou coroa, você ficou com P{m}.",
    "Your opponent wanted another stage: a coin flip chose {stage}.":
        "Seu oponente queria outro cenário: no cara ou coroa, saiu {stage}.",
    "P{n} on {stage}": "P{n} em {stage}",
    "Rematch: swap sides": "Rematch: trocar de lado",
    "with the sides swapped": "com os lados trocados",
    # the fold button right of the Online tab's lists (tk_views.toggle_top)
    "Hide": "Ocultar",
    "Show": "Mostrar",
    # 1.1.9: several open challenges, input delay, sorted lists, split leaderboard (tk_challenges.py)
    "Casual L": "Casual D",
    "Casual W": "Casual V",
    "Challenge withdrawn: a match started.": "Desafio retirado: uma partida começou.",
    "Delay: auto": "Delay: auto",
    "Delay: {frames}": "Delay: {frames}",
    "Input delay {frames} (auto, from the ping)": "Input delay {frames} (auto, pelo ping)",
    "Input delay {frames} (chosen by the challenger)": "Input delay {frames} (escolhido por quem desafiou)",
    "Input delay: {delay}.": "Input delay: {delay}.",
    "Unavailable": "Indisponível",
    "Ranked L": "Ranked D",
    "Ranked W": "Ranked V",
    "The challenge from {name} ran out.": "O desafio de {name} expirou.",
    "The challenge from {name} was withdrawn: a match started.": "O desafio de {name} foi retirado: uma partida começou.",
    "You challenged that player already: your open challenges are under the list.": "Você já desafiou esse jogador: seus desafios abertos estão embaixo da lista.",
    "You challenged {name}.": "Você desafiou {name}.",
    "You took back your challenge to {name}.": "Você retirou seu desafio a {name}.",
    "Your challenge to {name} was not answered in time.": "Seu desafio a {name} não foi respondido a tempo.",
    "Your challenge to {name} was withdrawn: a match started.": "Seu desafio a {name} foi retirado: uma partida começou.",
    "Your open challenges": "Seus desafios abertos",
    "auto": "auto",
    "input delay {delay}": "input delay {delay}",
    "{name} accepted your challenge.": "{name} aceitou seu desafio.",
    "{name} challenges you.": "{name} desafiou você.",
    "{name} declined your challenge.": "{name} recusou seu desafio.",
    "{name} took back the challenge.": "{name} retirou o desafio.",
    "you challenged that player already": "você já desafiou esse jogador",
    "too many challenges at once": "desafios demais ao mesmo tempo",
    "bad field: delay": "Campo inválido: delay",
    # launcher Settings "Screen side" and the Online tab's casual row ("Always left", 1.1.9, casual matches only;
    # docs/NETPLAY.md)
    "Screen side": 'Lado da tela',
    "Always see me on the left": 'Sempre me ver à esquerda',
    "Casual matches only (challenges, friends' invites, rooms): when you are P2, your screen shows the fight mirrored with you on the left, and your left and right are swapped. Your opponent sees the normal picture. Ranked and Quick matches stay as they are. Offline: Versus fights show the P2 side.":
        'Somente partidas casuais (desafios, convites de amigos, salas): quando você é o P2, sua tela mostra a luta espelhada com você à esquerda, e sua esquerda e direita são trocadas. Seu oponente vê a imagem normal. Partidas Ranked e Quick Match ficam como estão. Offline: as lutas Versus mostram o lado do P2.',
}
