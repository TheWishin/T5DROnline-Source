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
    "Auto (Windows language)": "Auto (idioma do Windows)",
    "No package chosen.": "Nenhum pacote escolhido.",
    "File not found.": "Arquivo não encontrado.",
    "Cannot read the file: {error}": "Não é possível ler o arquivo: {error}",
    "This is not a PS3 package (.pkg).": "Isto não é um pacote de PS3 (.pkg).",
    "{id}  ({size} bytes) -- the supported version": "{id}  ({size} bytes) -- a versão suportada",
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
    "Translate code": "Traduzir código",
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
    "Keep the PC responsive (slower)": "Manter o PC responsivo (mais lento)",
    "Open build.log": "Abrir build.log",
    "Report a problem...": "Relatar um problema...",
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
    "Sound and start": "Som e início",
    "Mute sound": "Silenciar som",
    "Start minimized, without taking focus (for testing)": "Iniciar minimizado, sem pegar o foco (para testes)",
    "Advanced: extra settings, one NAME=VALUE per line": "Avançado: configurações extras, uma NOME=VALOR por linha",
    "Internal resolution": "Resolução interna",
    "VSync": "VSync",
    "On (smooth, default)": "Ligado (suave, padrão)",
    "Off (lowest latency, may tear)": "Desligado (menor latência, pode ter tearing)",
    "The game always runs at 60 fps, like on the PS3.": "O jogo sempre roda a 60 fps, como no PS3.",
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
    "The keyboard only counts while the game window has focus. Button layout inside the "
    "game can be changed in its own Options menu.":
        "O teclado e o primeiro controle XInput controlam o jogador 1 (são combinados). O teclado só vale enquanto a "
        "janela do jogo tem o foco. O layout de botões dentro do jogo muda no próprio menu Options dele.",
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
    "The license (.rap) does not belong to this package. Use the .rap whose name matches "
    "the package's content ID ({id}).":
        "A licença (.rap) não pertence a este pacote. Use o .rap cujo nome corresponde ao content ID do pacote "
        "({id}).",
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
    "missing from toolchain\\llvm -- download the release again":
        "faltando em toolchain\\llvm -- baixe o release de novo",
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
    "idle": "livre",
    "room": "na sala",
    "queue": "na fila",
    "match": "em partida",
    "playing": "jogando",
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
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "Seu oponente fechou o jogo.",
    "The connection to your opponent's game was lost.": "A conexão com o jogo do oponente caiu.",
    "Your opponent's game stopped responding.": "O jogo do oponente parou de responder.",
    "Your opponent's game did not get to the fight.": "O jogo do oponente não chegou à luta.",
    "Your opponent's game was restarted; the match cannot go on.":
        "O jogo do oponente foi reiniciado; a partida não pode continuar.",
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
    "ranked": "Ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "Procurando... ({ranked} na fila Ranked, {quick} no Quick Match)",
    "ping about {ms} ms (through the server; measured directly once you both accept)":
        "ping de uns {ms} ms (pelo servidor; medido direto quando os dois aceitarem)",
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
    "Lobby": "Lobby",
    "Leaderboard": "Ranking",
    "Profile": "Perfil",
    "My profile": "Meu perfil",
    "Find an opponent online": "Encontre um oponente online",
    "Character": "Personagem",
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
    "(estimate through the server)": "(estimativa pelo servidor)",
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
}
