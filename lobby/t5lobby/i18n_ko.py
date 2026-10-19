"""Korean texts for the launcher and the Online tab (t5lobby/i18n.py).

English text -> Korean text. The English text is the key, exactly as written in t("...") / N_("...");
the Korean one keeps the same {placeholders}. Polite, short UI Korean (합니다 / 하세요) with the words
Tekken players use (왼손 / 오른손 / 왼발 / 오른발, 전적, 주캐). Names from the game and the lobby stay as
they are: Quick Match, Ranked, BUILD GAME, Rematch, Rollback, the character and rank names.

Machine-assisted translation: corrections from players are welcome (docs/ONLINE.md "Languages").
Same keys and groups as i18n_de.py; tests/test_i18n.py and tools/i18n_extract.py check every catalog.
"""

MESSAGES = {
    # ---- launcher/controls_edit.py
    "Attack buttons": "공격 버튼",
    "Several buttons with one press (macros)": "한 번에 여러 버튼 (매크로)",
    "Start, Select and the other buttons": "Start, Select 및 기타 버튼",
    "Directions": "방향",
    "1 (Left Punch)": "1 (왼손)",
    "2 (Right Punch)": "2 (오른손)",
    "3 (Left Kick)": "3 (왼발)",
    "4 (Right Kick)": "4 (오른발)",
    "Select": "Select",
    "Start / pause": "Start / 일시정지",
    "Down": "아래",
    "Left": "왼쪽",
    "Up": "위",
    "Right": "오른쪽",
    "PlayStation pad, default": "PlayStation 패드, 기본",
    "Xbox pad, default": "Xbox 패드, 기본",
    "X Y A B are 1 2 3 4; bumpers and triggers are L1 R1 L2 R2.":
        "X Y A B가 1 2 3 4, 범퍼와 트리거가 L1 R1 L2 R2입니다.",
    "Square Triangle Cross Circle are 1 2 3 4 (DualShock 4, DualSense and most "
    "PS3/PS4-mode sticks).":
        "네모 세모 엑스 동그라미가 1 2 3 4입니다 (DualShock 4, DualSense, PS3/PS4 모드 스틱 대부분).",
    "Switch pad, default": "Switch 패드, 기본",
    "Y X B A are 1 2 3 4 (Switch Pro controller, sticks in Switch mode).":
        "Y X B A가 1 2 3 4입니다 (Switch Pro 컨트롤러, Switch 모드 스틱).",
    "Xbox-style pad (generic)": "Xbox 스타일 패드 (일반)",
    "A B X Y buttons and LB RB, for Xbox-like pads that Windows does not give to XInput.":
        "A B X Y 버튼과 LB RB. Windows가 XInput으로 넘기지 않는 Xbox 계열 패드용입니다.",
    "8-button stick (Vewlix layout)": "8버튼 스틱 (Vewlix 배열)",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: X Y RB LB over A B RT LT.":
        "윗줄 1 2 [1+2] [1+3], 아랫줄 3 4 [3+4] [2+4]: 위 X Y RB LB, 아래 A B RT LT.",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: B1 B4 B6 B5 over B2 B3 B8 B7.":
        "윗줄 1 2 [1+2] [1+3], 아랫줄 3 4 [3+4] [2+4]: 위 B1 B4 B6 B5, 아래 B2 B3 B8 B7.",
    "6-button stick (Noir / Sega Astro)": "6버튼 스틱 (Noir / Sega Astro)",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: X Y RB over A B RT. LB and LT stay L1 and "
    "L2.":
        "윗줄 1 2 [1+2], 아랫줄 3 4 [3+4]: 위 X Y RB, 아래 A B RT. LB와 LT는 L1, L2 그대로입니다.",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: B1 B4 B6 over B2 B3 B8. B5 and B7 stay L1 "
    "and L2.":
        "윗줄 1 2 [1+2], 아랫줄 3 4 [3+4]: 위 B1 B4 B6, 아래 B2 B3 B8. B5와 B7은 L1, L2 그대로입니다.",
    "Hitbox": "Hitbox",
    "The 8-button layout above. Directions come from the d-pad or the left stick, which "
    "is read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "위의 8버튼 배열입니다. 방향은 방향 패드나 왼쪽 스틱에서 오며, 8방향 방향 패드 입력으로 읽힙니다. 왼쪽+오른쪽"
        "(위+아래) 동시 입력은 상쇄됩니다.",
    "The 8-button layout above. Directions come from the hat or the left stick, which is "
    "read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "위의 8버튼 배열입니다. 방향은 햇 스위치나 왼쪽 스틱에서 오며, 8방향 방향 패드 입력으로 읽힙니다. 왼쪽+오른쪽"
        "(위+아래) 동시 입력은 상쇄됩니다.",
    "The file has {n} settings; the game reads at most {max}.":
        "파일에 설정이 {n}개 있습니다. 게임은 최대 {max}개까지 읽습니다.",
    "The file has {n} sections; the game reads at most {max}.":
        "파일에 섹션이 {n}개 있습니다. 게임은 최대 {max}개까지 읽습니다.",
    "Changed lines of {sections} that would have overridden this ({what}).":
        "이 설정을 덮어썼을 {sections}의 줄을 바꿨습니다 ({what}).",
    "Lines of your file in other sections still change some buttons.":
        "파일의 다른 섹션에 있는 줄이 아직 일부 버튼을 바꿉니다.",
    "Other lines in your file ({sections}) still change this layout.":
        "파일의 다른 줄({sections})이 아직 이 배열을 바꿉니다.",
    "{n} lines removed.": "{n}줄을 삭제했습니다.",
    # ---- launcher/controls_ui.py
    "DirectInput controller": "DirectInput 컨트롤러",
    "Xbox pad (XInput)": "Xbox 패드 (XInput)",
    "Controls - T5DR Online": "조작 설정 - T5DR Online",
    "Press a button on a controller to pick it, then set its buttons. The game reads the "
    "file when it starts.":
        "컨트롤러의 버튼을 눌러 선택한 다음 버튼을 설정하세요. 게임은 시작할 때 파일을 읽습니다.",
    "Controllers": "컨트롤러",
    "Player": "플레이어",
    "Controller": "컨트롤러",
    "Pressed now": "지금 누름",
    "Move through this window with the controller": "컨트롤러로 이 창 조작",
    "Buttons": "버튼",
    "Game button": "게임 버튼",
    "Controller button": "컨트롤러 버튼",
    "Set up all buttons": "모든 버튼 설정",
    "Set up directions": "방향 설정",
    "Set selected": "선택한 버튼 설정",
    "Clear": "지우기",
    "Layout": "배열",
    "Use this layout": "이 배열 사용",
    "Reset to defaults": "기본값으로 초기화",
    "Your changes apply to": "변경 사항 적용 대상",
    "Player and directions": "플레이어와 방향",
    "Automatic": "자동",
    "Player 1": "플레이어 1",
    "Player 2": "플레이어 2",
    "8-way d-pad": "8방향 방향 패드",
    "Analog stick": "아날로그 스틱",
    "Both cancel (neutral)": "둘 다 상쇄 (중립)",
    "Up wins (Up+Down is Up)": "위 우선 (위+아래는 위)",
    "Last direction wins": "마지막 입력 우선",
    "Pass both through": "둘 다 전달",
    "This controller is": "이 컨트롤러는",
    "Left stick": "왼쪽 스틱",
    "Opposite directions": "반대 방향 동시 입력",
    "Left stick, 8-way d-pad: a hitbox or stick in left-stick mode sends the direction "
    "as a stick; the game then reads it as d-pad presses. Left+Right (or Up+Down) at "
    "once happens on keyboards and hitboxes; the game cannot take both. Stick and "
    "opposite directions belong to the player's port.":
        "왼쪽 스틱, 8방향 방향 패드: 왼쪽 스틱 모드의 Hitbox나 스틱은 방향을 스틱 입력으로 보내고, 게임은 이를 방향 "
        "패드 입력으로 읽습니다. 왼쪽+오른쪽(또는 위+아래) 동시 입력은 키보드와 Hitbox에서 생기며, 게임은 둘 다 받을 "
        "수 없습니다. 스틱과 반대 방향 설정은 플레이어 포트에 속합니다.",
    "Skip": "건너뛰기",
    "Stop": "중지",
    "Save": "저장",
    "Revert": "되돌리기",
    "Close": "닫기",
    "no controller": "컨트롤러 없음",
    "Controllers cannot be read on this PC.": "이 PC에서는 컨트롤러를 읽을 수 없습니다.",
    "No controller found. Plug one in; it shows up here by itself.":
        "컨트롤러가 없습니다. 연결하면 여기에 자동으로 나타납니다.",
    "switched off in [general]": "[general]에서 꺼짐",
    "no free player port": "빈 플레이어 포트 없음",
    "No controller chosen": "선택한 컨트롤러 없음",
    "This controller model ({vid}:{pid})": "이 컨트롤러 모델 ({vid}:{pid})",
    "This controller model (no USB ID)": "이 컨트롤러 모델 (USB ID 없음)",
    "All DirectInput controllers": "모든 DirectInput 컨트롤러",
    "All Xbox pads (XInput)": "모든 Xbox 패드 (XInput)",
    "Only the controller on player {n}'s port": "플레이어 {n} 포트의 컨트롤러만",
    "no player": "플레이어 없음",
    "player {n}": "플레이어 {n}",
    "yours": "직접 설정",
    "Your own layout": "나만의 배열",
    "Player {n}": "플레이어 {n}",
    "Buttons you set yourself, or a mix. Pick a layout to start from it.":
        "직접 설정한 버튼 또는 혼합입니다. 배열을 고르면 그 배열에서 시작합니다.",
    "On the controller: {up} / {down} choose a button, {accept} sets it, {clear} clears "
    "it, {save} saves, {back} closes. The game reads the file when it starts.":
        "컨트롤러: {up} / {down} 버튼 선택, {accept} 설정, {clear} 지우기, {save} 저장, {back} 닫기. 게임은 시작할 "
        "때 파일을 읽습니다.",
    "(no game button)": "(게임 버튼 없음)",
    "Press a button on a controller first, or pick one in the list.":
        "먼저 컨트롤러의 버튼을 누르거나 목록에서 고르세요.",
    "Press the button for {button}...": "{button}에 쓸 버튼을 누르세요...",
    "Press only that one button on the controller.": "컨트롤러에서 그 버튼 하나만 누르세요.",
    "{n} of {total}.": "{n}/{total}.",
    "Wait a few seconds to skip it.": "건너뛰려면 몇 초 기다리세요.",
    "That was several buttons at once ({sources}). Press one button only.":
        "여러 버튼이 동시에 눌렸습니다 ({sources}). 버튼 하나만 누르세요.",
    "{button}: skipped.": "{button}: 건너뜀.",
    "{button} = {source}.": "{button} = {source}.",
    "{source} was {other}; that one has no button now.": "{source}은(는) {other}였습니다. 이제 그쪽은 버튼이 없습니다.",
    "Stopped.": "중지했습니다.",
    "{button}: cleared.": "{button}: 지움.",
    "Layout: {name}.": "배열: {name}.",
    "Pick a layout in the list first.": "먼저 목록에서 배열을 고르세요.",
    "Put {name} back to the default buttons? Your comments and other settings in "
    "controls.ini stay.":
        "{name}을(를) 기본 버튼으로 되돌릴까요? controls.ini의 주석과 다른 설정은 그대로 남습니다.",
    "The part of the file that is for all {kind} controllers has button lines too. Reset "
    "those as well?":
        "파일에서 모든 {kind} 컨트롤러용 부분에도 버튼 줄이 있습니다. 그것도 초기화할까요?",
    "Reset to the defaults. Save to keep it.": "기본값으로 되돌렸습니다. 유지하려면 저장하세요.",
    "{name} is {player}. Save to keep it.": "{name}은(는) {player}입니다. 유지하려면 저장하세요.",
    "controls.ini changed": "controls.ini 변경됨",
    "controls.ini was changed by something else since this screen opened. Overwrite it "
    "with your settings? (The old file is kept as controls.ini.bak.)":
        "이 화면을 연 뒤 다른 곳에서 controls.ini를 바꿨습니다. 내 설정으로 덮어쓸까요? (이전 파일은 "
        "controls.ini.bak으로 남습니다.)",
    "Could not save: {error}": "저장할 수 없습니다: {error}",
    "Saved {path}. The game reads it when it starts.": "{path}에 저장했습니다. 게임은 시작할 때 읽습니다.",
    "The game that is running keeps its old buttons until you start it again.":
        "실행 중인 게임은 다시 시작할 때까지 이전 버튼을 씁니다.",
    "Changes undone.": "변경 사항을 되돌렸습니다.",
    "There are unsaved changes. Save them first, or close with the mouse.":
        "저장하지 않은 변경 사항이 있습니다. 먼저 저장하거나 마우스로 닫으세요.",
    "Controls": "조작 설정",
    "Save the changes to controls.ini?": "controls.ini에 변경 사항을 저장할까요?",
    # ---- launcher/core.py
    "Auto (Windows language)": "자동 (Windows 언어)",
    "Deutsch": "Deutsch",
    "English": "English",
    "No package chosen.": "선택한 패키지가 없습니다.",
    "File not found.": "파일을 찾을 수 없습니다.",
    "Cannot read the file: {error}": "파일을 읽을 수 없습니다: {error}",
    "This is not a PS3 package (.pkg).": "PS3 패키지(.pkg)가 아닙니다.",
    "{id}  ({size} bytes) -- the supported version": "{id}  ({size}바이트) -- 지원 버전",
    "{id}  ({size} bytes) -- Tekken 5 DR, but not the supported package ({supported}). "
    "The build will most likely refuse it.":
        "{id}  ({size}바이트) -- Tekken 5 DR이지만 지원 패키지({supported})가 아닙니다. 빌드에서 거부될 가능성이 큽니"
        "다.",
    "{id}  ({size} bytes) -- not Tekken 5 DR Online ({title_id}).":
        "{id}  ({size}바이트) -- Tekken 5 DR Online이 아닙니다 ({title_id}).",
    "No license chosen.": "선택한 라이선스가 없습니다.",
    "Not a PS3 license: a .rap file is exactly 16 bytes.":
        "PS3 라이선스가 아닙니다. .rap 파일은 정확히 16바이트입니다.",
    "{name} -- matches the supported package": "{name} -- 지원 패키지와 일치",
    "{name} -- matches the package": "{name} -- 패키지와 일치",
    "{name} -- the name does not match the package's content ID; it may be the wrong "
    "license.":
        "{name} -- 이름이 패키지의 콘텐츠 ID와 맞지 않습니다. 잘못된 라이선스일 수 있습니다.",
    "The output folder": "출력 폴더",
    "This folder": "이 폴더",
    "{label} has a long path ({bytes} bytes). Windows allows only {max} characters for a "
    "file path, and the build writes files about {room} characters deeper. Move the "
    "folder to a short path, for example {example}.":
        "{label}의 경로가 깁니다 ({bytes}바이트). Windows는 파일 경로에 {max}자까지만 허용하는데, 빌드는 약 {room}자 "
        "더 깊은 곳에 파일을 씁니다. 폴더를 짧은 경로로 옮기세요. 예: {example}",
    "This folder is inside OneDrive. OneDrive would upload about 1 GB of game data and "
    "can lock files while the game is built. Move the folder out of OneDrive, for "
    "example to {example}.":
        "이 폴더는 OneDrive 안에 있습니다. OneDrive가 게임 데이터 약 1GB를 업로드하고, 게임을 빌드하는 동안 파일을 "
        "잠글 수 있습니다. 폴더를 OneDrive 밖으로 옮기세요. 예: {example}",
    "This folder is in Program Files, where Windows does not let programs write. Move it "
    "to a folder of your own, for example {example}.":
        "이 폴더는 Program Files 안에 있어서 Windows가 프로그램의 쓰기를 막습니다. 내 폴더로 옮기세요. 예: {example}",
    "Windows does not let the launcher write into this folder. Move it to a folder of "
    "your own, for example {example}.":
        "Windows가 런처의 이 폴더 쓰기를 막습니다. 내 폴더로 옮기세요. 예: {example}",
    "This folder is on a network share. Building and playing from there is slow and was "
    "not tested; copy it to a local drive.":
        "이 폴더는 네트워크 공유에 있습니다. 거기서 빌드하고 플레이하면 느리고, 테스트도 되지 않았습니다. 로컬 드라이"
        "브로 복사하세요.",
    "The game is not built yet. Open the Build tab, choose your .pkg and .rap, press "
    "BUILD GAME.":
        "게임이 아직 빌드되지 않았습니다. 빌드 탭을 열고 .pkg와 .rap를 고른 뒤 BUILD GAME을 누르세요.",
    "t5dr.exe is there but the game data is missing. Build again.":
        "t5dr.exe는 있지만 게임 데이터가 없습니다. 다시 빌드하세요.",
    "The decrypted program has SHA-1 {sha}..., not the supported version. Build again "
    "from the supported package.":
        "복호화된 프로그램의 SHA-1이 {sha}...로 지원 버전이 아닙니다. 지원 패키지로 다시 빌드하세요.",
    "Build the game once (about 2 minutes): this version of the launcher changes the "
    "game code. Click BUILD GAME. Your unpacked game and saves are kept; only the code "
    "is translated and compiled again.":
        "게임을 한 번 빌드하세요 (약 2분): 이 버전의 런처는 게임 코드를 바꿉니다. BUILD GAME을 클릭하세요. 압축을 푼 "
        "게임과 세이브는 그대로 두고, 코드만 다시 변환하고 컴파일합니다.",
    "Ready: {title_id} v{version}, program SHA-1 {sha}... verified, built {when}.":
        "준비 완료: {title_id} v{version}, 프로그램 SHA-1 {sha}... 확인됨, 빌드 {when}.",
    "Check & decrypt": "확인 및 복호화",
    "Key data": "키 데이터",
    "Recompiler": "리컴파일러",
    "Unpack": "압축 풀기",
    "Compile": "컴파일",
    "Game files": "게임 파일",
    "Sound core": "사운드 코어",
    "Translate code": "코드 변환",
    "The graphics card stopped working for the game (the driver crashed, was reset or "
    "updated). Start the game again. If it happens again, update the graphics driver.":
        "그래픽 카드가 게임에서 작동을 멈췄습니다 (드라이버가 충돌했거나 재설정 또는 업데이트됨). 게임을 다시 시작하세"
        "요. 또 그러면 그래픽 드라이버를 업데이트하세요.",
    "This PC's graphics card or driver cannot run Direct3D 12. Install the newest "
    "graphics driver from AMD, Intel or NVIDIA.":
        "이 PC의 그래픽 카드나 드라이버가 Direct3D 12를 실행할 수 없습니다. AMD, Intel 또는 NVIDIA의 최신 그래픽 드라"
        "이버를 설치하세요.",
    "This processor is too old for the game: it lacks the SSE4.1 instructions "
    "(processors from about 2008 on have them).":
        "이 프로세서는 게임을 돌리기에 너무 오래되었습니다. SSE4.1 명령어가 없습니다 (대략 2008년 이후 프로세서에는 "
        "있습니다).",
    "The game was built on a PC with a newer processor (AVX2). Press BUILD GAME to build "
    "it again for this PC; your saves are kept.":
        "게임이 더 새로운 프로세서(AVX2)를 가진 PC에서 빌드되었습니다. BUILD GAME을 눌러 이 PC용으로 다시 빌드하세요"
        ". 세이브는 그대로 남습니다.",
    "t5dr_game.dll could not be loaded (missing or blocked). Press BUILD GAME again, and "
    "look in the antivirus quarantine.":
        "t5dr_game.dll을 불러올 수 없습니다 (없거나 차단됨). BUILD GAME을 다시 누르고 백신 프로그램의 격리 목록을 확인"
        "하세요.",
    "The game could not get back to character select after the last match and closed "
    "itself. It starts again for your next match.":
        "지난 매치 후 게임이 캐릭터 선택으로 돌아가지 못해 스스로 종료했습니다. 다음 매치 때 다시 시작합니다.",
    "The game stopped after a crash (exit code {code}). The game log has the details.":
        "게임이 충돌로 종료되었습니다 (종료 코드 {code}). 자세한 내용은 게임 로그에 있습니다.",
    "The game stopped (exit code {code}). The game log has the details.":
        "게임이 종료되었습니다 (종료 코드 {code}). 자세한 내용은 게임 로그에 있습니다.",
    "t5dr.exe is not built yet": "t5dr.exe가 아직 빌드되지 않았습니다",
    "Lowest (0.5x)": "최저 (0.5x)",
    "Lower (0.75x)": "낮음 (0.75x)",
    "Native (720p)": "네이티브 (720p)",
    "1080p (1.5x)": "1080p (1.5x)",
    "1440p (2x)": "1440p (2x)",
    "4K (3x)": "4K (3x)",
    "The 3D scene at half size (a quarter of its pixels); HUD and text stay sharp. "
    "For integrated graphics and old laptops.":
        "3D 장면을 절반 크기로 그립니다 (픽셀 수 1/4). HUD와 글자는 선명하게 유지됩니다. 내장 그래픽과 오래된 노트북용"
        ".",
    "The 3D scene at 3/4 size (about half of its pixels); HUD and text stay sharp. "
    "For weak graphics cards.":
        "3D 장면을 3/4 크기로 그립니다 (픽셀 수 약 절반). HUD와 글자는 선명하게 유지됩니다. 성능이 낮은 그래픽 카드용"
        ".",
    "The PS3's 1280 x 720. Light on any graphics card; the picture is scaled to your window.":
        "PS3와 같은 1280 x 720. 어떤 그래픽 카드에도 가볍고, 화면은 창 크기에 맞게 늘어납니다.",
    "1920 x 1080: 2.25x the pixels of Native. Sharp on Full HD screens. "
    "If fights drop below 60 fps, go one step down.":
        "1920 x 1080: 네이티브의 2.25배 픽셀. Full HD 화면에서 선명합니다. 대전이 60fps 아래로 떨어지면 한 단계 낮추세"
        "요.",
    "2560 x 1440: 4x the pixels of Native. For strong graphics cards. "
    "If fights drop below 60 fps, go one step down.":
        "2560 x 1440: 네이티브의 4배 픽셀. 고성능 그래픽 카드용. 대전이 60fps 아래로 떨어지면 한 단계 낮추세요.",
    "3840 x 2160: 9x the pixels of Native. For very strong graphics cards "
    "(an RTX 3090 needs 1-2 ms of a 16.7 ms frame). If fights drop below 60 fps, go one step down.":
        "3840 x 2160: 네이티브의 9배 픽셀. 매우 강력한 그래픽 카드용 (RTX 3090은 16.7ms 프레임 중 1-2ms 사용). 대전이"
        " 60fps 아래로 떨어지면 한 단계 낮추세요.",
    "Auto (by ping)": "자동 (핑 기준)",
    "Window, 1280 x 720 (native; larger with Windows display scaling)":
        "창, 1280 x 720 (네이티브, Windows 배율에 따라 커짐)",
    "Window, 1920 x 1080": "창, 1920 x 1080",
    "Window, 2560 x 1440": "창, 2560 x 1440",
    "Maximized window": "최대화된 창",
    "Borderless fullscreen (Alt+Enter or F11 switches in the game)":
        "테두리 없는 전체 화면 (게임에서 Alt+Enter 또는 F11로 전환)",
    # ---- launcher/online.py
    "Online play": "온라인 플레이",
    "The lobby files (lobby/t5lobby) are missing from this copy of the launcher, so "
    "online play is not available.\n\n({reason})":
        "이 런처 사본에 로비 파일(lobby/t5lobby)이 없어 온라인 플레이를 할 수 없습니다.\n\n({reason})",
    # ---- launcher/problem_report_ui.py
    "Before the zip is made, your Windows user name in file paths becomes <user>, "
    "internet IP addresses become <ip> (addresses of your own network stay), lobby player "
    "names (yours and your opponents') become <player>, and passwords, tokens and match keys "
    "are left out. Your game files, keys, .pkg and .rap are never included. Nothing is "
    "uploaded: you send the zip yourself.":
        "zip을 만들기 전에 파일 경로의 Windows 사용자 이름은 <user>로, 인터넷 IP 주소는 <ip>로 바뀌고 (내 네트워크 "
        "주소는 그대로), 로비 플레이어 이름(내 이름과 상대 이름)은 <player>로 바뀌며, 비밀번호, 토큰, 매치 키는 빠집니"
        "다. 게임 파일, 키, .pkg, .rap는 절대 포함되지 않습니다. 아무것도 업로드하지 않으며, zip은 직접 보내면 됩니다"
        ".",
    "{count} bytes": "{count}바이트",
    "Report a problem": "문제 신고",
    "This makes one zip file on your Desktop with the logs and settings that help to "
    "find the problem. Send the zip to the person who gave you the game, or attach it to "
    "an issue.":
        "문제를 찾는 데 도움이 되는 로그와 설정을 담은 zip 파일 하나를 바탕 화면에 만듭니다. zip을 게임을 준 사람에게"
        " 보내거나 이슈에 첨부하세요.",
    "What happened? (optional)": "무슨 일이 있었나요? (선택)",
    "What goes into the zip": "zip에 들어가는 것",
    "Nothing found yet: no game log, no build log.": "아직 아무것도 없습니다: 게임 로그도, 빌드 로그도 없습니다.",
    "Could not look at the files: {error}": "파일을 확인할 수 없습니다: {error}",
    "Save report on the Desktop": "바탕 화면에 보고서 저장",
    "Cancel": "취소",
    "About {size} before it is packed (a zip is smaller).": "압축 전 약 {size} (zip은 더 작습니다).",
    "About {size}; the limit is {limit}, so the biggest logs are shortened in the "
    "middle.":
        "약 {size}. 한도가 {limit}이라 가장 큰 로그는 가운데를 줄입니다.",
    "Making the report...": "보고서를 만드는 중...",
    "The report could not be made: {error}": "보고서를 만들 수 없습니다: {error}",
    "Report saved": "보고서 저장됨",
    "{size}. Its folder is open.": "{size}. 폴더를 열었습니다.",
    "Send this zip to the person who gave you the game, or attach it to an issue at "
    "{url}.":
        "이 zip을 게임을 준 사람에게 보내거나 {url}의 이슈에 첨부하세요.",
    "Send this zip to the person who gave you the game.": "이 zip을 게임을 준 사람에게 보내세요.",
    "(shortened in the middle)": "(가운데 생략)",
    "{name}   left out: {reason}": "{name}   제외: {reason}",
    "Removed from the text files: {user} user or PC names, {ip} IP addresses, {secret} "
    "passwords, tokens or keys, {email} e-mail addresses.":
        "텍스트 파일에서 제거됨: 사용자 또는 PC 이름 {user}개, IP 주소 {ip}개, 비밀번호·토큰·키 {secret}개, 이메일 "
        "주소 {email}개.",
    "Open folder": "폴더 열기",
    # ---- launcher/t5dr_launcher.pyw
    "A": "A",
    "Left punch (1)": "왼손 (1)",
    "Square": "네모",
    "X": "X",
    "Right punch (2)": "오른손 (2)",
    "S": "S",
    "Triangle": "세모",
    "Y": "Y",
    "Cross": "엑스",
    "Left kick (3)": "왼발 (3)",
    "Z": "Z",
    "B": "B",
    "Circle": "동그라미",
    "Right kick (4)": "오른발 (4)",
    "Arrow keys": "방향키",
    "D-pad, left stick": "방향 패드, 왼쪽 스틱",
    "Move / menus": "이동 / 메뉴",
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
    "Quit the game": "게임 종료",
    "A / B": "A / B",
    "Cross / Circle": "엑스 / 동그라미",
    "Mouse": "마우스",
    "Online tab: accept / decline": "온라인 탭: 수락 / 거절",
    "native Windows build  ·  launcher {version}": "Windows 네이티브 빌드  ·  런처 {version}",
    "Build": "빌드",
    "Play offline": "오프라인 플레이",
    "Settings": "설정",
    "Play online": "온라인 플레이",
    "Output: {folder}": "출력: {folder}",
    "Your game": "내 게임",
    "Package (.pkg)": "패키지 (.pkg)",
    "License (.rap)": "라이선스 (.rap)",
    "Browse…": "찾아보기…",
    "Supported: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version "
    "01.00 -- the package file and the license (.rap) from your own account. Nothing "
    "leaves this PC.":
        "지원: Tekken 5: Dark Resurrection Online, PS3 PSN (미국), NPUB30009 버전 01.00 -- 본인 계정의 패키지 파일과 "
        "라이선스(.rap). 아무것도 이 PC 밖으로 나가지 않습니다.",
    "Build tools on this PC": "이 PC의 빌드 도구",
    "Needed": "필요",
    "Found": "확인",
    "Checking…": "확인 중…",
    "Details": "세부 정보",
    "Check again": "다시 확인",
    "Install missing…": "없는 항목 설치…",
    "Press BUILD GAME. It takes a few minutes; the game data stays in this folder.":
        "BUILD GAME을 누르세요. 몇 분 걸리며, 게임 데이터는 이 폴더에 남습니다.",
    "BUILD GAME": "BUILD GAME",
    "Redo every step": "모든 단계 다시 하기",
    "Keep the PC responsive (slower)": "PC 반응성 유지 (더 느림)",
    "Open build.log": "build.log 열기",
    "Report a problem...": "문제 신고...",
    "Checking the build…": "빌드 확인 중…",
    "Your name (shown in the game)": "내 이름 (게임에 표시)",
    "PLAY OFFLINE": "오프라인 플레이",
    "Arcade, Versus, Practice and the other modes on this PC. To play against people over the "
    "internet, use the":
        "Arcade, Versus, Practice 등 이 PC에서 하는 모드입니다. 인터넷 대전은 여기로:",
    "Online tab": "온라인 탭",
    "Stop game": "게임 중지",
    "Open newest game log": "최신 게임 로그 열기",
    "Open saves folder": "세이브 폴더 열기",
    "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers "
    "both work; see Settings for the keys. Esc closes the game. START skips the intro "
    "movie.":
        "게임은 별도 창(DirectX 12)으로 열립니다. 키보드와 Xbox 스타일 컨트롤러 모두 쓸 수 있으며, 키는 설정에서 확인"
        "하세요. Esc는 게임을 닫고, START는 인트로 영상을 건너뜁니다.",
    "Display": "화면",
    "The picture is scaled to the window; how sharp it is depends on Internal resolution. "
    "You can also drag the window's edges. Alt+Enter or F11 switches borderless fullscreen "
    "in the game.":
        "화면은 창 크기에 맞춰지며, 선명도는 내부 해상도에 따라 달라집니다. 창 가장자리를 끌어 크기를 바꿀 수도 있습니"
        "다. 게임에서 Alt+Enter 또는 F11로 테두리 없는 전체 화면을 전환합니다.",
    "Sound and start": "소리 및 시작",
    "Mute sound": "소리 끄기",
    "Start minimized, without taking focus (for testing)": "최소화 상태로 포커스 없이 시작 (테스트용)",
    "Advanced: extra settings, one NAME=VALUE per line": "고급: 추가 설정, 한 줄에 하나씩 NAME=VALUE",
    "Internal resolution": "내부 해상도",
    "VSync": "VSync",
    "On (smooth, default)": "켜기 (부드러움, 기본)",
    "Off (lowest latency, may tear)": "끄기 (최소 지연, 화면 찢김 가능)",
    "The game always runs at 60 fps, like on the PS3.": "게임은 PS3처럼 항상 60fps로 동작합니다.",
    "Your screen: {width} x {height}. In fullscreen, {step} matches it.":
        "내 화면: {width} x {height}. 전체 화면에서는 {step}이(가) 맞습니다.",
    "Online input delay": "온라인 입력 지연",
    "Frames. Auto: 1 up to about 60 ms ping, 2 above. 0/1/2 count only when your "
    "opponent picked the same, otherwise Auto. Ranked matches always use 2.":
        "프레임 단위. 자동: 핑 약 60ms까지 1, 그 이상 2. 0/1/2는 상대도 같은 값을 골랐을 때만 적용되고, 아니면 자동입"
        "니다. Ranked 매치는 항상 2입니다.",
    "Open the game's port on my router during online matches (UPnP / NAT-PMP / PCP)":
        "온라인 매치 중 공유기에서 게임 포트 열기 (UPnP / NAT-PMP / PCP)",
    "Helps the direct connection when your opponent's router is strict. The port is open only while "
    "you play and is closed again afterwards.":
        "상대의 공유기가 엄격할 때 직접 연결에 도움이 됩니다. 포트는 플레이하는 동안에만 열리고 끝나면 다시 닫힙니다.",
    "Set up controllers…": "컨트롤러 설정…",
    "Pick a pad, stick or hitbox, press the buttons you want for 1 2 3 4 and the rest, "
    "or start from a layout.":
        "패드, 스틱, Hitbox를 고르고 1 2 3 4와 나머지에 쓸 버튼을 누르거나, 배열에서 시작하세요.",
    "(needs the lobby files, which are missing)": "(로비 파일이 필요하지만 없습니다)",
    "Action (Tekken default)": "동작 (Tekken 기본)",
    "PS3 button": "PS3 버튼",
    "Keyboard": "키보드",
    "Xbox controller": "Xbox 컨트롤러",
    "Keyboard and the first XInput controller both drive player 1 (they are combined). "
    "The keyboard only counts while the game window has focus. Button layout inside the "
    "game can be changed in its own Options menu.":
        "키보드와 첫 번째 XInput 컨트롤러는 둘 다 플레이어 1을 조작합니다 (합쳐짐). 키보드는 게임 창에 포커스가 있을 "
        "때만 적용됩니다. 게임 안의 버튼 배치는 게임의 Options 메뉴에서 바꿀 수 있습니다.",
    "In this window, on the Online tab, a controller or arcade stick works without mouse "
    "or keyboard: Cross / A accepts a match or rematch and starts a search, Circle / B "
    "declines, leaves or stops the search. It only counts while this window is in front, "
    "and only after the button was let go for a moment. Which stick button is Cross "
    "follows your controls.ini.":
        "이 창의 온라인 탭은 마우스나 키보드 없이 컨트롤러나 아케이드 스틱으로도 쓸 수 있습니다: 엑스 / A는 매치나 "
        "Rematch를 수락하고 검색을 시작하며, 동그라미 / B는 거절, 나가기 또는 검색 중지입니다. 이 창이 맨 앞에 있을 "
        "때만, 그리고 버튼을 잠깐 뗀 뒤에만 적용됩니다. 스틱의 어느 버튼이 엑스인지는 controls.ini를 따릅니다.",
    "Language": "언어",
    "Restart now": "지금 다시 시작",
    "The language changes when the launcher starts again.": "언어는 런처를 다시 시작하면 바뀝니다.",
    "A build is running. Stop it first, or restart the launcher by hand when it is done.":
        "빌드가 진행 중입니다. 먼저 중지하거나, 끝난 뒤 런처를 직접 다시 시작하세요.",
    "Close the game first.": "먼저 게임을 닫으세요.",
    "Choose your Tekken 5 DR Online package": "Tekken 5 DR Online 패키지 선택",
    "All files": "모든 파일",
    "PS3 package": "PS3 패키지",
    "Choose your license (.rap)": "라이선스 선택 (.rap)",
    "PS3 license": "PS3 라이선스",
    "Checking build tools…": "빌드 도구 확인 중…",
    "missing": "없음",
    "ok": "ok",
    "Missing: {names}": "없음: {names}",
    "Everything the build needs is installed.": "빌드에 필요한 것이 모두 설치되어 있습니다.",
    "All build tools found.": "모든 빌드 도구를 찾았습니다.",
    "{count} build tool(s) missing -- click 'Install missing…'.":
        "빌드 도구 {count}개가 없습니다 -- '없는 항목 설치…'를 클릭하세요.",
    "Hide details": "세부 정보 숨기기",
    "Microsoft Visual Studio 2022 Build Tools: the C++ compiler parts only (MSVC x64, "
    "Windows SDK, CMake, Clang). Download about 2.5 GB, about 7 GB on disk, 10-20 "
    "minutes. You accept Microsoft's license terms for the Build Tools "
    "(visualstudio.microsoft.com/license-terms).":
        "Microsoft Visual Studio 2022 Build Tools: C++ 컴파일러 부분만 (MSVC x64, Windows SDK, CMake, Clang). 다운로드"
        " 약 2.5GB, 디스크 약 7GB, 10-20분. Build Tools에 대한 Microsoft 라이선스 조건"
        "(visualstudio.microsoft.com/license-terms)에 동의하게 됩니다.",
    "Git for Windows (about 70 MB download).": "Git for Windows (다운로드 약 70MB).",
    "Install build tools": "빌드 도구 설치",
    "The build needs these free tools from their makers, installed with Windows' own "
    "installer (winget):\n\n{tools}\n\nWindows will ask for administrator permission. A "
    "console window shows the progress.\n\nInstall now?":
        "빌드에는 제작사가 제공하는 다음 무료 도구가 필요하며, Windows 자체 설치 프로그램(winget)으로 설치합니다"
        ":\n\n{tools}\n\nWindows가 관리자 권한을 요청합니다. 콘솔 창에 진행 상황이 표시됩니다.\n\n지금 설치할까요?",
    "Could not start the installer:\n{error}\n\nIs winget (App Installer) available? On "
    "Windows 10 install 'App Installer' from the Microsoft Store.":
        "설치 프로그램을 시작할 수 없습니다:\n{error}\n\nwinget(앱 설치 관리자)이 있나요? Windows 10에서는 Microsoft "
        "Store에서 '앱 설치 관리자'를 설치하세요.",
    "Install failed": "설치 실패",
    "Installer running in its own window…": "설치 프로그램이 별도 창에서 실행 중…",
    "Could not start the build: {error}": "빌드를 시작할 수 없습니다: {error}",
    "Building…": "빌드 중…",
    "Step {n} of {total}: {title}  —  {elapsed}": "{total}단계 중 {n}단계: {title}  —  {elapsed}",
    "Done in {elapsed}. Open the Play tab.": "{elapsed} 만에 완료. 오프라인 플레이 탭을 여세요.",
    "Build finished.": "빌드 완료.",
    "Cancelled. BUILD GAME continues where it stopped.": "취소했습니다. BUILD GAME은 멈춘 곳부터 이어서 합니다.",
    "The build stopped. The message below says why; build.log has the details.":
        "빌드가 중단되었습니다. 아래 메시지에 이유가 있고, build.log에 자세한 내용이 있습니다.",
    "The build failed. See the log above and build.log.": "빌드에 실패했습니다. 위의 로그와 build.log를 확인하세요.",
    "Build stopped.": "빌드 중단됨.",
    "Could not start the game:\n{error}": "게임을 시작할 수 없습니다:\n{error}",
    "Game started (process {pid}). Log: {log}": "게임 시작됨 (프로세스 {pid}). 로그: {log}",
    "starting…": "시작 중…",
    "Running — {elapsed} — {fps}": "실행 중 — {elapsed} — {fps}",
    "Click Report a problem.": "'문제 신고...'를 클릭하세요.",
    "The game closed.": "게임이 종료되었습니다.",
    "A build is running. Stop it and quit?": "빌드가 진행 중입니다. 중지하고 종료할까요?",
    # ---- launcher/updater.py
    "Check for updates": "업데이트 확인",
    "Updated from {old} to {new}.": "{old}에서 {new}(으)로 업데이트했습니다.",
    "the new version": "새 버전",
    "The update to {version} failed and could not be undone completely: {error}.\n\nThe "
    "old program files are in\n{folder}\nYour game, saves and settings (the native "
    "folder) were not touched. Download the zip from the releases page and extract it "
    "over this folder.":
        "{version} 업데이트에 실패했고 완전히 되돌리지 못했습니다: {error}.\n\n이전 프로그램 파일은 다음 위치에 있습니"
        "다:\n{folder}\n게임, 세이브, 설정(native 폴더)은 건드리지 않았습니다. 릴리스 페이지에서 zip을 받아 이 폴더 "
        "위에 압축을 푸세요.",
    "The update to {version} did not work: {error}.\n\nNothing was changed; this is "
    "still version {current}. Try again later, or download the zip from the releases "
    "page.":
        "{version} 업데이트가 되지 않았습니다: {error}.\n\n바뀐 것은 없으며 여전히 버전 {current}입니다. 나중에 다시 "
        "시도하거나 릴리스 페이지에서 zip을 받으세요.",
    "Update": "업데이트",
    "Updates": "업데이트",
    "This is a development checkout (no release.json and bundled Python), so it does not "
    "update itself. Use git, or a release zip from\n{page}":
        "개발용 체크아웃입니다 (release.json과 내장 Python 없음). 그래서 스스로 업데이트하지 않습니다. git을 쓰거나 "
        "다음에서 릴리스 zip을 받으세요:\n{page}",
    "Update to {version}…": "{version}(으)로 업데이트…",
    "Could not check for updates.\n\n{problem}": "업데이트를 확인할 수 없습니다.\n\n{problem}",
    "Version {version} is available: click 'Update to {version}' at the top.":
        "버전 {version}이(가) 나왔습니다: 위쪽의 '{version}(으)로 업데이트'를 클릭하세요.",
    "You have the newest version ({version}).": "최신 버전({version})을 쓰고 있습니다.",
    "Update available": "업데이트 있음",
    "T5DR Online {version} is available": "T5DR Online {version}이(가) 나왔습니다",
    "Download: {size}, published {date}.": "다운로드: {size}, {date} 공개.",
    "Download: {size}.": "다운로드: {size}.",
    "You have {version}.": "현재 버전은 {version}입니다.",
    "The launcher downloads it, checks it, replaces its program files and starts again. "
    "Your game, saves and settings (the native folder) stay as they are.":
        "런처가 내려받아 확인하고, 프로그램 파일을 바꾼 뒤 다시 시작합니다. 게임, 세이브, 설정(native 폴더)은 그대로 "
        "남습니다.",
    "After this update the game is built once more (about 2 minutes): the Play tab "
    "offers BUILD GAME. Only the code is rebuilt; the unpacked game and saves are kept.":
        "이 업데이트 후 게임을 한 번 더 빌드합니다 (약 2분): 오프라인 플레이 탭에 BUILD GAME이 나타납니다. 코드만 다시"
        " 빌드하며, 압축을 푼 게임과 세이브는 그대로입니다.",
    "The game itself does not need to be built again.": "게임 자체는 다시 빌드할 필요가 없습니다.",
    "If this update changes the game code, the Play tab asks you to build the game once "
    "(about 2 minutes).":
        "이 업데이트가 게임 코드를 바꾸면, 오프라인 플레이 탭에서 게임을 한 번 빌드하라고 안내합니다 (약 2분).",
    "(no release notes)": "(릴리스 노트 없음)",
    "Update now": "지금 업데이트",
    "Later": "나중에",
    "Release page": "릴리스 페이지",
    "Cancelling…": "취소 중…",
    "Downloading…": "다운로드 중…",
    "Unexpected error: {error}": "예기치 않은 오류: {error}",
    "Downloading… {done} of {total}": "다운로드 중… {done} / {total}",
    "Downloading… {done}": "다운로드 중… {done}",
    "Checking the download (SHA-256)…": "다운로드 확인 중 (SHA-256)…",
    "Unpacking… {percent}%": "압축 푸는 중… {percent}%",
    "Preparing the restart…": "다시 시작 준비 중…",
    "Try again": "다시 시도",
    "Could not start the update step: {error}": "업데이트 단계를 시작할 수 없습니다: {error}",
    "Installing {version}: the launcher restarts in a few seconds…":
        "{version} 설치 중: 런처가 몇 초 후 다시 시작합니다…",
    "Updating to {version}…": "{version}(으)로 업데이트 중…",
    # ---- lobby/t5lobby/client.py
    "Contacting the lobby server over UDP...": "UDP로 로비 서버에 연결하는 중...",
    "UDP to the lobby server is blocked (firewall?)": "로비 서버로 가는 UDP가 막혀 있습니다 (방화벽?)",
    "Connecting to your opponent...": "상대에게 연결하는 중...",
    "Measuring the connection...": "연결 상태 측정 중...",
    "Direct connection not possible; using the lobby server's relay...":
        "직접 연결이 불가능합니다. 로비 서버의 릴레이를 사용하는 중...",
    "Direct connection found: the match no longer goes through the lobby server.":
        "직접 연결을 찾았습니다: 이제 매치가 로비 서버를 거치지 않습니다.",
    "The direct connection was lost; back on the lobby server's relay.":
        "직접 연결이 끊겼습니다. 다시 로비 서버의 릴레이를 사용합니다.",
    "Direct connection not possible; using the relay server {name}...":
        "직접 연결이 불가능합니다. 릴레이 서버 {name}을(를) 사용하는 중...",
    "Direct connection found: the match no longer goes through the relay server {name}.":
        "직접 연결을 찾았습니다: 이제 매치가 릴레이 서버 {name}을(를) 거치지 않습니다.",
    "The direct connection was lost; back on the relay server {name}.":
        "직접 연결이 끊겼습니다. 다시 릴레이 서버 {name}을(를) 사용합니다.",
    # ---- lobby/t5lobby/dialogs.py
    "No": "아니요",
    "Yes": "예",
    "OK": "확인",
    # ---- lobby/t5lobby/fighters.py
    "Random": "랜덤",
    # ---- lobby/t5lobby/handover.py
    "direct connection": "직접 연결",
    "local network": "로컬 네트워크",
    "through the lobby server": "로비 서버 경유",
    "through the relay server {name}": "릴레이 서버 {name} 경유",
    "{name} -- {how}, ping {ms} ms, input delay {delay}": "{name} -- {how}, 핑 {ms}ms, 입력 지연 {delay}",
    # ---- lobby/t5lobby/i18n_known.py
    "login timeout": "로그인 시간 초과",
    "idle timeout": "오래 활동이 없어 시간 초과",
    "banned from this server": "이 서버에서 차단됨",
    "too many connections": "연결이 너무 많습니다",
    "server full": "서버가 가득 찼습니다",
    "slow down": "너무 빠릅니다",
    "bad request": "잘못된 요청",
    "the server is busy; try again in a few seconds": "서버가 바쁩니다. 몇 초 후 다시 시도하세요",
    "the chat is busy; try again in a moment": "채팅이 바쁩니다. 잠시 후 다시 시도하세요",
    "that name looks too much like the account {other}": "그 이름은 계정 {other}와(과) 너무 비슷합니다",
    "that name looks too much like {name}, who is online": "그 이름은 접속 중인 {name}와(과) 너무 비슷합니다",
    "flooding: disconnected": "메시지 도배: 연결 끊김",
    "this server speaks lobby protocol {version}; update the launcher":
        "이 서버는 로비 프로토콜 {version}을(를) 씁니다. 런처를 업데이트하세요",
    "build {build} is not accepted by this server; update the launcher and rebuild the "
    "game":
        "이 서버는 빌드 {build}을(를) 받지 않습니다. 런처를 업데이트하고 게임을 다시 빌드하세요",
    "already logged in": "이미 로그인되어 있습니다",
    "this server has no accounts": "이 서버에는 계정이 없습니다",
    "this server has no guest logins": "이 서버는 게스트 로그인을 허용하지 않습니다",
    "too many failed logins; wait a few minutes": "로그인 실패가 너무 많습니다. 몇 분 기다리세요",
    "too many failed attempts; wait a few minutes": "실패한 시도가 너무 많습니다. 몇 분 기다리세요",
    "too many new accounts from this address": "이 주소에서 만든 새 계정이 너무 많습니다",
    "the saved login has expired; log in with your password": "저장된 로그인이 만료되었습니다. 비밀번호로 로그인하세요",
    "session expired; log in again": "세션이 만료되었습니다. 다시 로그인하세요",
    "names are 2-16 letters, digits, spaces or _-.[]()!?": "이름은 2-16자의 글자, 숫자, 공백 또는 _-.[]()!?입니다",
    "that name is reserved": "그 이름은 예약되어 있습니다",
    "that name is not allowed here": "그 이름은 여기서 쓸 수 없습니다",
    "that name belongs to an account": "그 이름은 계정에 등록된 이름입니다",
    "that name is taken": "그 이름은 이미 사용 중입니다",
    "someone with that name is online": "그 이름으로 접속 중인 사람이 있습니다",
    "wrong name or password": "이름 또는 비밀번호가 틀렸습니다",
    "wrong password": "비밀번호가 틀렸습니다",
    "the current password is wrong": "현재 비밀번호가 틀렸습니다",
    "passwords are 6-128 characters": "비밀번호는 6-128자입니다",
    "guests have no password": "게스트는 비밀번호가 없습니다",
    "guests have no account": "게스트는 계정이 없습니다",
    "wrong name or recovery code (each code works once)":
        "이름 또는 복구 코드가 틀렸습니다 (코드는 한 번만 쓸 수 있습니다)",
    "logged in from another place": "다른 곳에서 로그인했습니다",
    "this account is banned for good": "이 계정은 영구 정지되었습니다",
    "this account is banned for good: {reason}": "이 계정은 영구 정지되었습니다: {reason}",
    "this account is banned until {time}": "이 계정은 {time}까지 정지되었습니다",
    "this account is banned until {time}: {reason}": "이 계정은 {time}까지 정지되었습니다: {reason}",
    "you are {status}": "지금은 할 수 없습니다 (상태: {status})",
    "ranked needs an account": "Ranked는 계정이 필요합니다",
    "ranked matches come from the ranked queue on this server": "이 서버의 Ranked 매치는 Ranked 대기열에서만 잡힙니다",
    "your character is locked until this ranked set ends": "이 Ranked 세트가 끝날 때까지 캐릭터가 고정됩니다",
    "the ranked set goes on by itself": "Ranked 세트는 자동으로 이어집니다",
    "you are in a ranked set ({mine}-{theirs}); leave it first (that counts as a loss)":
        "Ranked 세트 중입니다 ({mine}-{theirs}). 먼저 나가세요 (패배로 처리됩니다)",
    "that player is in a ranked set": "그 플레이어는 Ranked 세트 중입니다",
    "you are not in a ranked set": "Ranked 세트 중이 아닙니다",
    "finish your running match with the same game build first": "먼저 같은 게임 빌드로 진행 중인 매치를 끝내세요",
    "this PC ran its last match at {fps} fps; ranked needs at least {min_fps} (both "
    "games run at the slower PC's speed). Close other programs or lower the resolution "
    "scale, then play a casual match to measure again":
        "이 PC는 지난 매치를 {fps}fps로 플레이했습니다. Ranked는 최소 {min_fps}가 필요합니다 (두 게임 모두 느린 PC의 "
        "속도로 돌아갑니다). 다른 프로그램을 닫거나 내부 해상도를 낮춘 뒤, 일반 매치를 한 판 해서 다시 측정하세요",
    "chat: slow down": "채팅: 너무 빠릅니다",
    "history is kept for accounts only": "기록은 계정만 저장됩니다",
    "no such player": "그런 플레이어가 없습니다",
    "no such room": "그런 방이 없습니다",
    "room is full": "방이 가득 찼습니다",
    "you cannot join this room": "이 방에 들어갈 수 없습니다",
    "not in a room": "방에 있지 않습니다",
    "no opponent in the room": "방에 상대가 없습니다",
    "that player runs a different build of the game": "그 플레이어는 다른 게임 빌드를 쓰고 있습니다",
    "finish the match first": "먼저 매치를 끝내세요",
    "finish or leave the running match first": "먼저 진행 중인 매치를 끝내거나 나가세요",
    "that match is over; find a new opponent": "그 매치는 끝났습니다. 새 상대를 찾으세요",
    "your opponent is no longer available": "상대가 더 이상 없습니다",
    "that player is not available": "그 플레이어는 지금 대전할 수 없습니다",
    "busy": "바쁨",
    "one challenge at a time": "도전은 한 번에 하나만",
    "that player has challenges pending": "그 플레이어에게 대기 중인 도전이 있습니다",
    "no such challenge": "그런 도전이 없습니다",
    "challenge no longer possible": "더 이상 도전할 수 없습니다",
    "no such match": "그런 매치가 없습니다",
    "match is {state}": "매치 상태: {state}",
    "you cannot block yourself": "자기 자신은 차단할 수 없습니다",
    "the block list is full ({max})": "차단 목록이 가득 찼습니다 ({max})",
    "that player is not on your block list": "그 플레이어는 차단 목록에 없습니다",
    "you are not in a set": "세트 중이 아닙니다",
    "no such finished match": "그런 종료된 매치가 없습니다",
    "{name} is back in the lobby": "{name}님이 로비로 돌아왔습니다",
    "{name} lost the lobby connection; waiting {seconds} s for them to return":
        "{name}님의 로비 연결이 끊겼습니다. 돌아올 때까지 {seconds}초 기다립니다",
    "your PC ran its last match at {fps} fps": "내 PC는 지난 매치를 {fps}fps로 플레이했습니다",
    "your opponent's PC ran its last match at {fps} fps": "상대 PC는 지난 매치를 {fps}fps로 플레이했습니다",
    "{name}'s PC ran its last match at {fps} fps": "{name}님의 PC는 지난 매치를 {fps}fps로 플레이했습니다",
    "{parts} -- this match runs at the slower PC's speed": "{parts} -- 이 매치는 느린 PC의 속도로 진행됩니다",
    "you two played {count} ranked matches in the last 24 hours; this one is unranked "
    "(limit {max})":
        "두 사람은 최근 24시간 동안 Ranked 매치를 {count}판 했습니다. 이번 매치는 랭크에 반영되지 않습니다 (한도 "
        "{max})",
    "your PC's UDP packets did not reach the lobby server; check the firewall":
        "내 PC의 UDP 패킷이 로비 서버에 닿지 않았습니다. 방화벽을 확인하세요",
    "your opponent reported the result; please report yours": "상대가 결과를 보고했습니다. 내 결과도 보고해 주세요",
    "opponent runs a different build": "상대가 다른 빌드를 쓰고 있습니다",
    "not connected to the lobby": "로비에 연결되어 있지 않습니다",
    "the lobby server did not answer": "로비 서버가 응답하지 않았습니다",
    "no answer to {type}": "{type}에 대한 응답 없음",
    "cannot reach {host}:{port} ({error})": "{host}:{port}에 연결할 수 없습니다 ({error})",
    "the server's certificate does not match the pinned one": "서버 인증서가 고정된 인증서와 다릅니다",
    "this server has no encryption (TLS): a password would cross the internet readable. "
    "Play as a guest, or ask the server's host to set up TLS and give you its "
    "fingerprint.":
        "이 서버는 암호화(TLS)가 없습니다: 비밀번호가 인터넷에서 그대로 보입니다. 게스트로 플레이하거나, 서버 운영자에"
        "게 TLS를 설정하고 지문(fingerprint)을 알려 달라고 하세요.",
    "connection closed": "연결이 닫혔습니다",
    "message too long": "메시지가 너무 깁니다",
    "closed": "닫힘",
    "Choose your game package (.pkg) first.": "먼저 게임 패키지(.pkg)를 고르세요.",
    "The package file does not exist: {file}": "패키지 파일이 없습니다: {file}",
    "{file} is not a PS3 package (.pkg).": "{file}은(는) PS3 패키지(.pkg)가 아닙니다.",
    "Choose your license file (.rap) first.": "먼저 라이선스 파일(.rap)을 고르세요.",
    "{file} is not a PS3 license: a .rap file is exactly 16 bytes.":
        "{file}은(는) PS3 라이선스가 아닙니다. .rap 파일은 정확히 16바이트입니다.",
    "This package has no USRDIR/EBOOT.BIN -- it is not a game package (an add-on or "
    "theme?). The port needs {game}.":
        "이 패키지에는 USRDIR/EBOOT.BIN이 없습니다 -- 게임 패키지가 아닙니다 (추가 콘텐츠나 테마?). 이 포트에는 "
        "{game}이(가) 필요합니다.",
    "This package is \"{title}\" ({id}). The port needs {game}.":
        "이 패키지는 '{title}' ({id})입니다. 이 포트에는 {game}이(가) 필요합니다.",
    "This copy is a different version of the game: \"{title}\" version {version}, content "
    "ID {id} (program SHA-1 {sha}...). The port supports only {game}, content ID "
    "{supported}.":
        "이 사본은 다른 버전의 게임입니다: '{title}' 버전 {version}, 콘텐츠 ID {id} (프로그램 SHA-1 {sha}...). 이 포트"
        "는 {game}, 콘텐츠 ID {supported}만 지원합니다.",
    "The license (.rap) does not belong to this package. Use the .rap whose name matches "
    "the package's content ID ({id}).":
        "라이선스(.rap)가 이 패키지의 것이 아닙니다. 이름이 패키지의 콘텐츠 ID({id})와 맞는 .rap를 쓰세요.",
    "Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press BUILD GAME "
    "again; if it fails again, check that the package is {size} bytes.":
        "게임 프로그램 복호화에 실패했습니다 (위 로그 참고). '모든 단계 다시 하기'를 체크하고 BUILD GAME을 다시 누르세"
        "요. 또 실패하면 패키지가 {size}바이트인지 확인하세요.",
    "The package is {size} bytes, the supported one is {supported} bytes: the download is incomplete or it is "
    "a different file. Download it again.":
        "패키지는 {size}바이트인데 지원 패키지는 {supported}바이트입니다: 다운로드가 덜 됐거나 다른 파일입니다. 다시 "
        "다운로드하세요.",
    "The ps3recomp copy in this folder does not match this version of the port. Download "
    "the release again and extract it into an empty folder.":
        "이 폴더의 ps3recomp 사본이 이 버전의 포트와 맞지 않습니다. 릴리스를 다시 받아 빈 폴더에 압축을 푸세요.",
    "Git is needed to download ps3recomp (the recompiler). Install Git, or use a release "
    "zip, which already contains it.":
        "ps3recomp(리컴파일러)를 받으려면 Git이 필요합니다. Git을 설치하거나, 이미 포함된 릴리스 zip을 쓰세요.",
    "This package's Python is missing pycryptodome. Download the release again.":
        "이 패키지의 Python에 pycryptodome이 없습니다. 릴리스를 다시 받으세요.",
    "Could not download the public PS3 key data from github.com (needed once, a few KB). "
    "Check the internet connection and press BUILD GAME again.":
        "github.com에서 공개 PS3 키 데이터를 받을 수 없습니다 (한 번만 필요, 몇 KB). 인터넷 연결을 확인하고 BUILD "
        "GAME을 다시 누르세요.",
    "The C++ build tools (Visual Studio 2022 Build Tools, x64 C++ toolset) are not "
    "installed. Open the launcher's Build tab and click Install next to them.":
        "C++ 빌드 도구(Visual Studio 2022 Build Tools, x64 C++ 도구 세트)가 설치되어 있지 않습니다. 런처의 빌드 탭을 "
        "열고 '없는 항목 설치…'를 클릭하세요.",
    "clang-cl.exe and lld-link.exe were not found in toolchain\\llvm\\bin. Download the "
    "release again.":
        "toolchain\\llvm\\bin에서 clang-cl.exe와 lld-link.exe를 찾을 수 없습니다. 릴리스를 다시 받으세요.",
    "The Windows SDK is missing (needed for Direct3D 12). Install it with the C++ build "
    "tools.":
        "Windows SDK가 없습니다 (Direct3D 12에 필요). C++ 빌드 도구와 함께 설치하세요.",
    "clang-cl (LLVM 16 or newer) was not found. Install LLVM or the Visual Studio "
    "component 'C++ Clang tools for Windows'.":
        "clang-cl(LLVM 16 이상)을 찾을 수 없습니다. LLVM 또는 Visual Studio 구성 요소 'C++ Clang tools for "
        "Windows'를 설치하세요.",
    "CMake and Ninja were not found. Install the Visual Studio component 'C++ CMake "
    "tools for Windows'.":
        "CMake와 Ninja를 찾을 수 없습니다. Visual Studio 구성 요소 'C++ CMake tools for Windows'를 설치하세요.",
    "expected 1 SPU image, found {count}": "SPU 이미지 1개를 기대했지만 {count}개를 찾았습니다",
    "step '{step}' failed: a tool exited with code {code} -- the lines above say why.":
        "'{step}' 단계 실패: 도구가 코드 {code}로 종료했습니다 -- 위 줄에 이유가 있습니다.",
    "cancelled": "취소됨",
    "step '{step}' could not read or write a file: {reason} ({file}). The folder path is "
    "too long for Windows: move the folder to a short path such as C:\\Games\\T5DR.":
        "'{step}' 단계에서 파일을 읽거나 쓸 수 없습니다: {reason} ({file}). 폴더 경로가 Windows에서 쓰기엔 너무 깁니다"
        ": C:\\Games\\T5DR 같은 짧은 경로로 폴더를 옮기세요.",
    "step '{step}' could not read or write a file: {reason} ({file}). Is the disk full, "
    "or does another program (antivirus, OneDrive) hold the file?":
        "'{step}' 단계에서 파일을 읽거나 쓸 수 없습니다: {reason} ({file}). 디스크가 가득 찼거나, 다른 프로그램(백신"
        ", OneDrive)이 파일을 잡고 있나요?",
    "Python 3.10+": "Python 3.10+",
    "pycryptodome (Python AES)": "pycryptodome (Python AES)",
    "ps3recomp source": "ps3recomp 소스",
    "Game runtime (t5dr.exe)": "게임 런타임 (t5dr.exe)",
    "clang-cl + lld-link": "clang-cl + lld-link",
    "C++ build tools (MSVC x64)": "C++ 빌드 도구 (MSVC x64)",
    "Windows SDK (Direct3D 12)": "Windows SDK (Direct3D 12)",
    "clang-cl 16+ (LLVM)": "clang-cl 16+ (LLVM)",
    "CMake + Ninja": "CMake + Ninja",
    "{version} at {path}": "{version} ({path})",
    "installed": "설치됨",
    "missing -- pip install pycryptodome": "없음 -- pip install pycryptodome",
    "included in this package": "이 패키지에 포함됨",
    "git checkout in deps/": "deps/의 git 체크아웃",
    "not present -- will be downloaded with Git": "없음 -- Git으로 다운로드합니다",
    "not present and Git is missing": "없고 Git도 없음",
    "precompiled, included in this package": "미리 컴파일됨, 이 패키지에 포함",
    "missing from toolchain\\llvm -- download the release again": "toolchain\\llvm에 없음 -- 릴리스를 다시 받으세요",
    "not found": "찾을 수 없음",
    "missing {tools}": "없음: {tools}",
    "System information and the settings you use": "시스템 정보와 사용 중인 설정",
    "What happened (what you wrote)": "무슨 일이 있었는지 (내가 쓴 내용)",
    "Launcher log": "런처 로그",
    "Game log (the newest one)": "게임 로그 (최신)",
    "Game log (the newest {count})": "게임 로그 (최신 {count}개)",
    "Build log": "빌드 로그",
    "Build log (the last build went fine)": "빌드 로그 (마지막 빌드는 정상)",
    "Online: the files of the last match": "온라인: 지난 매치의 파일",
    "controls.ini (your button settings)": "controls.ini (버튼 설정)",
    "Desync dumps (game state numbers, binary)": "디싱크 덤프 (게임 상태 수치, 바이너리)",
    "could not be cleaned of private data": "개인 정보를 지울 수 없음",
    "no room left in the size limit": "크기 한도에 남은 공간 없음",
    "could not be read": "읽을 수 없음",
    "The launcher cannot write next to its folder or into it, so it cannot update "
    "itself. Download the zip from the releases page instead.":
        "런처가 자기 폴더 옆이나 안에 쓸 수 없어 스스로 업데이트할 수 없습니다. 대신 릴리스 페이지에서 zip을 받으세요"
        ".",
    "Refused to download from {host}: not this project's GitHub releases.":
        "{host}에서의 다운로드를 거부했습니다: 이 프로젝트의 GitHub 릴리스가 아닙니다.",
    "The download came from {host}. Nothing was changed.":
        "다운로드가 {host}에서 왔습니다. 아무것도 바뀌지 않았습니다.",
    "GitHub did not return a published release.": "GitHub가 공개된 릴리스를 돌려주지 않았습니다.",
    "The latest release has an unexpected version ({tag}).": "최신 릴리스의 버전이 예상과 다릅니다 ({tag}).",
    "Release {version} has no {name} with SHA256SUMS yet.":
        "릴리스 {version}에 아직 SHA256SUMS와 함께 {name}이(가) 없습니다.",
    "The downloaded release does not say it is version {version}. Nothing was changed.":
        "받은 릴리스가 버전 {version}이라고 표시하지 않습니다. 아무것도 바뀌지 않았습니다.",
    "The downloaded release has no launcher. Nothing was changed.":
        "받은 릴리스에 런처가 없습니다. 아무것도 바뀌지 않았습니다.",
    "This folder has no python\\pythonw.exe, so the launcher cannot update itself (a "
    "development checkout?). Download the zip from the releases page instead.":
        "이 폴더에 python\\pythonw.exe가 없어 런처가 스스로 업데이트할 수 없습니다 (개발용 체크아웃?). 대신 릴리스 "
        "페이지에서 zip을 받으세요.",
    "The download was sent to {host}, which is not GitHub's storage for this project. "
    "Nothing was changed.":
        "다운로드가 이 프로젝트의 GitHub 저장소가 아닌 {host}(으)로 보내졌습니다. 아무것도 바뀌지 않았습니다.",
    "Release {version}: {name} is not on this project's GitHub releases.":
        "릴리스 {version}: {name}이(가) 이 프로젝트의 GitHub 릴리스에 없습니다.",
    "Release {version}: {name} is still being uploaded.": "릴리스 {version}: {name}을(를) 아직 업로드하는 중입니다.",
    "The download stopped early ({done} of {total} bytes). Try again.":
        "다운로드가 일찍 멈췄습니다 ({done} / {total}바이트). 다시 시도하세요.",
    "The download is not a readable zip ({error}). Nothing was changed.":
        "다운로드한 파일이 읽을 수 있는 zip이 아닙니다 ({error}). 아무것도 바뀌지 않았습니다.",
    "The download unpacks to far more than a release should. Nothing was changed.":
        "다운로드를 풀면 릴리스보다 훨씬 커집니다. 아무것도 바뀌지 않았습니다.",
    "Not enough free disk space: the update needs about {need} MB next to the folder, "
    "{free} MB are free.":
        "디스크 공간이 부족합니다: 업데이트에 폴더 옆 약 {need}MB가 필요한데, {free}MB만 남아 있습니다.",
    "SHA256SUMS of release {version} has no line for {name}. Nothing was changed.":
        "릴리스 {version}의 SHA256SUMS에 {name} 줄이 없습니다. 아무것도 바뀌지 않았습니다.",
    "SHA256SUMS and GitHub disagree about the download's checksum. Nothing was changed.":
        "SHA256SUMS와 GitHub의 다운로드 체크섬이 다릅니다. 아무것도 바뀌지 않았습니다.",
    "The download is damaged or not the published file: its SHA-256 is {got}..., "
    "SHA256SUMS says {want}.... Nothing was changed.":
        "다운로드가 손상되었거나 공개된 파일이 아닙니다: SHA-256이 {got}...인데 SHA256SUMS는 {want}...입니다. 아무것도"
        " 바뀌지 않았습니다.",
    "The downloaded release has no python\\pythonw.exe. Nothing was changed.":
        "받은 릴리스에 python\\pythonw.exe가 없습니다. 아무것도 바뀌지 않았습니다.",
    "The download is far bigger than a release should be. Nothing was changed.":
        "다운로드가 릴리스로서는 너무 큽니다. 아무것도 바뀌지 않았습니다.",
    "The download contains an unexpected path ({name}: {why}). Nothing was changed.":
        "다운로드에 예상치 못한 경로가 있습니다 ({name}: {why}). 아무것도 바뀌지 않았습니다.",
    "The download contains an unexpected path ({name}). Nothing was changed.":
        "다운로드에 예상치 못한 경로가 있습니다 ({name}). 아무것도 바뀌지 않았습니다.",
    "Cancelled.": "취소했습니다.",
    "Could not download or unpack the update ({error}). Nothing was changed.":
        "업데이트를 다운로드하거나 압축을 풀 수 없습니다 ({error}). 아무것도 바뀌지 않았습니다.",
    "The download is damaged ({error}). Nothing was changed.":
        "다운로드가 손상되었습니다 ({error}). 아무것도 바뀌지 않았습니다.",
    "the new release contains {names} (the player's files)":
        "새 릴리스에 {names}이(가) 들어 있습니다 (플레이어의 파일)",
    "release.json does not say {version} after the swap": "교체 후 release.json에 {version}이(가) 없습니다",
    "launcher\\t5dr_launcher.pyw is missing after the swap": "교체 후 launcher\\t5dr_launcher.pyw가 없습니다",
    "python\\pythonw.exe is missing after the swap": "교체 후 python\\pythonw.exe가 없습니다",
    "the update plan is incomplete": "업데이트 계획이 불완전합니다",
    "the launcher did not close": "런처가 닫히지 않았습니다",
    "programs from the folder were still running ({names}); close them and try again":
        "폴더의 프로그램이 아직 실행 중이었습니다 ({names}). 닫고 다시 시도하세요",
    "the new launcher {version} did not start": "새 런처 {version}이(가) 시작되지 않았습니다",
    "could not replace the program files: {error}": "프로그램 파일을 바꿀 수 없습니다: {error}",
    "unexpected error: {error}": "예기치 않은 오류: {error}",
    "GitHub asks to wait with update checks until {time}.": "GitHub가 {time}까지 업데이트 확인을 기다려 달라고 합니다.",
    "GitHub limits update checks right now. Try again later.":
        "GitHub가 지금 업데이트 확인을 제한하고 있습니다. 나중에 다시 시도하세요.",
    "GitHub answered with error {code}. Try again later.":
        "GitHub가 오류 {code}로 응답했습니다. 나중에 다시 시도하세요.",
    "No connection to GitHub. Check the internet connection and try again.":
        "GitHub에 연결할 수 없습니다. 인터넷 연결을 확인하고 다시 시도하세요.",
    "A build is running. Update when it is finished.": "빌드가 진행 중입니다. 끝난 뒤 업데이트하세요.",
    "The game is running. Close it first, then update.": "게임이 실행 중입니다. 먼저 닫은 뒤 업데이트하세요.",
    "'Host for friends' is running. Stop hosting first, then update.":
        "'친구용 호스트'가 실행 중입니다. 먼저 호스트를 멈춘 뒤 업데이트하세요.",
    "An online match was found. Update after the match.": "온라인 매치가 잡혔습니다. 매치가 끝난 뒤 업데이트하세요.",
    "An online match is running. Update after the match.":
        "온라인 매치가 진행 중입니다. 매치가 끝난 뒤 업데이트하세요.",
    "You are searching for or playing an online match. Update afterwards.":
        "온라인 매치를 찾거나 플레이하는 중입니다. 끝난 뒤 업데이트하세요.",
    "Other programs from this folder are still running ({names}): another launcher "
    "window, the game or a lobby server. Close them, then update.":
        "이 폴더의 다른 프로그램이 아직 실행 중입니다 ({names}): 다른 런처 창, 게임 또는 로비 서버. 닫은 뒤 업데이트하"
        "세요.",
    "not a plain relative path": "단순 상대 경로가 아님",
    "'.', '..' or an empty part": "'.', '..' 또는 빈 부분",
    "outside the folder {folder}": "{folder} 폴더 바깥",
    "named like the player's own files": "플레이어 파일과 같은 이름",
    "idle": "대기 중",
    "room": "방에 있음",
    "queue": "검색 중",
    "match": "매치 중",
    "playing": "플레이 중",
    # ---- lobby/t5lobby/lag.py
    "Ping {ping} ms should mean about {frames} frames behind.":
        "핑 {ping}ms라면 약 {frames}프레임 뒤처지는 것이 정상입니다.",
    "The games did not report how it went, so there is nothing to compare.":
        "게임들이 결과를 알려 주지 않아 비교할 것이 없습니다.",
    "It was {observed}.": "실제로는 {observed}였습니다.",
    "That is what the ping explains.": "핑으로 설명되는 수준입니다.",
    "That is more than the ping explains.": "핑으로 설명되는 것보다 많습니다.",
    "Both PCs ran below full speed.": "두 PC 모두 최고 속도보다 느리게 돌았습니다.",
    "Your PC was the slow one ({fps} fps).": "내 PC가 느렸습니다 ({fps}fps).",
    "Your PC was the slow one.": "내 PC가 느렸습니다.",
    "Your opponent's PC was the slow one ({fps} fps).": "상대 PC가 느렸습니다 ({fps}fps).",
    "Your opponent's PC was the slow one.": "상대 PC가 느렸습니다.",
    "Both PCs kept up, so the connection stalled now and then (jitter or lost packets).":
        "두 PC 모두 속도를 따라갔으니, 연결이 가끔 멈췄던 것입니다 (지터 또는 패킷 손실).",
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "상대가 게임을 닫았습니다.",
    "The connection to your opponent's game was lost.": "상대 게임과의 연결이 끊겼습니다.",
    "Your opponent's game stopped responding.": "상대 게임이 응답하지 않습니다.",
    "Your opponent's game did not get to the fight.": "상대 게임이 대전까지 가지 못했습니다.",
    "Your opponent's game was restarted; the match cannot go on.":
        "상대 게임이 다시 시작되어 매치를 계속할 수 없습니다.",
    "Your opponent's game could not be reached (firewall or router?).":
        "상대 게임에 연결할 수 없습니다 (방화벽 또는 공유기?).",
    "Your opponent's game is a different build.": "상대 게임의 빌드가 다릅니다.",
    "Your opponent's game is in another match.": "상대 게임이 다른 매치 중입니다.",
    "The game could not open its network port (another program uses it?).":
        "게임이 네트워크 포트를 열 수 없습니다 (다른 프로그램이 쓰는 중?).",
    "You closed the game during the match: it counts as a loss.": "매치 중에 게임을 닫았습니다: 패배로 처리됩니다.",
    "The game could not get back to character select and closed itself; it starts again for your next match.":
        "게임이 캐릭터 선택으로 돌아가지 못해 스스로 종료했습니다. 다음 매치 때 다시 시작합니다.",
    "Your opponent does not want a rematch.": "상대가 Rematch를 원하지 않습니다.",
    "The game is not running any more; leaving the rematch.": "게임이 더 이상 실행 중이 아니어서 Rematch에서 나갑니다.",
    "Rematch against {name}: same connection, the game stays open.":
        "{name}님과 Rematch: 같은 연결, 게임은 열린 채로 둡니다.",
    "The game could not start; leaving the match.": "게임을 시작할 수 없어 매치에서 나갑니다.",
    "Playing against {summary}": "대전 상대: {summary}",
    "The game did not answer its control channel; it is restarted for every opponent "
    "from now on.":
        "게임이 제어 채널에 응답하지 않았습니다. 이제부터 상대마다 게임을 다시 시작합니다.",
    "Character select...": "캐릭터 선택...",
    "The game is starting...": "게임 시작 중...",
    "Fight!": "Fight!",
    "Loading the fight...": "대전 불러오는 중...",
    "Stage select...": "스테이지 선택...",
    "At character select, waiting for the next match.": "캐릭터 선택 화면에서 다음 매치를 기다리는 중.",
    "Match over.": "매치 종료.",
    "Ignored a result the game wrote for an earlier match.": "게임이 이전 매치에 대해 기록한 결과를 무시했습니다.",
    "The match could not be finished ({reason}).": "매치를 끝낼 수 없었습니다 ({reason}).",
    "The match could not be played ({reason}).": "매치를 할 수 없었습니다 ({reason}).",
    "The game stopped unexpectedly; the match does not count (repeated crashes do).":
        "게임이 예기치 않게 종료되었습니다. 이 매치는 집계되지 않습니다 (반복되는 충돌은 집계됨).",
    "Result sent (the games went out of sync on {frames} frames); waiting for the "
    "lobby...":
        "결과를 보냈습니다 ({frames}프레임에서 게임 동기화가 어긋남). 로비를 기다리는 중...",
    "Result sent; waiting for the lobby...": "결과를 보냈습니다. 로비를 기다리는 중...",
    "Lobby: {message}": "로비: {message}",
    # ---- lobby/t5lobby/padnav.py
    "(+{count} more)": "(+{count}개 더)",
    # ---- lobby/t5lobby/ranks.py
    "{wins}W {losses}L": "{wins}승 {losses}패",
    "{draws}D": "{draws}무",
    "{rank} (placement {done}/{total})": "{rank} (배치 {done}/{total})",
    # ---- lobby/t5lobby/sets.py
    "a game was too short to count": "경기가 너무 짧아 집계되지 않았습니다",
    "a fight ended without a winner": "승자 없이 끝난 대전이 있었습니다",
    "too many games without a winner": "승자 없는 경기가 너무 많았습니다",
    "left after the lag check": "랙 체크 후 나감",
    "the lobby server restarted": "로비 서버가 다시 시작되었습니다",
    "a player left right away": "한 플레이어가 바로 나갔습니다",
    "the next game could not start": "다음 경기를 시작할 수 없었습니다",
    "a player left before a game counted": "경기가 집계되기 전에 한 플레이어가 나갔습니다",
    "a player lost the lobby connection": "한 플레이어의 로비 연결이 끊겼습니다",
    "set won": "세트 승리",
    "set lost": "세트 패배",
    "Set {mine}-{theirs}": "세트 {mine}-{theirs}",
    "game {number} of {best}": "{best}판 중 {number}경기",
    "game {number} of {best} again (no winner)": "{best}판 중 {number}경기 다시 (승자 없음)",
    "starts in {seconds} s": "{seconds}초 후 시작",
    "The set does not count ({why}); no rating change": "이 세트는 집계되지 않습니다 ({why}). 레이팅 변동 없음",
    "The set does not count; no rating change": "이 세트는 집계되지 않습니다. 레이팅 변동 없음",
    "You won the set (your opponent left it)": "세트 승리 (상대가 나감)",
    "You won the set": "세트 승리",
    "You lost the set (you left it)": "세트 패배 (내가 나감)",
    "You lost the set": "세트 패배",
    "You won the set {mine}-{theirs}": "세트 {mine}-{theirs} 승리",
    "You lost the set {mine}-{theirs}": "세트 {mine}-{theirs} 패배",
    "set game {number}": "세트 {number}경기",
    # ---- lobby/t5lobby/theme.py
    "Good connection": "좋은 연결",
    "Laggy connection": "랙 있는 연결",
    "OK connection": "보통 연결",
    "Ping not known yet": "핑 아직 모름",
    "sec": "초",
    # ---- lobby/t5lobby/tk_tab.py
    "Leave set (counts as a loss)": "세트 나가기 (패배로 처리)",
    "Leave the ranked set": "Ranked 세트 나가기",
    "Leave this ranked set?\n\nLeaving a ranked set counts as losing it.":
        "이 Ranked 세트에서 나갈까요?\n\nRanked 세트에서 나가면 패배로 처리됩니다.",
    "Rematch? (a new set)": "Rematch? (새 세트)",
    "in a room": "방에 있음",
    "in lobby": "로비에 있음",
    "matching": "매치 준비 중",
    "searching": "검색 중",
    "full": "가득 참",
    "open": "열림",
    "Result confirmed": "결과 확정",
    "Result recorded (your opponent did not report)": "결과 기록됨 (상대가 보고하지 않음)",
    "Match decided by forfeit": "기권으로 결정된 매치",
    "Result decided by the games' state": "게임 상태로 결정된 결과",
    "You and your opponent reported different results -- not counted":
        "나와 상대가 서로 다른 결과를 보고했습니다 -- 집계 안 됨",
    "No result": "결과 없음",
    "confirmed": "확정",
    "forfeit": "기권",
    "one-sided": "한쪽 보고",
    "disputed": "이의 있음",
    "resolved": "해결됨",
    "void": "무효",
    "draw": "무승부",
    "loss": "패배",
    "win": "승리",
    "the two games went out of sync": "두 게임의 동기화가 어긋났습니다",
    "too short to count": "너무 짧아 집계 안 됨",
    "a game crashed": "게임 하나가 충돌했습니다",
    "the reports disagreed": "보고 내용이 서로 달랐습니다",
    "left right away": "바로 나감",
    "a player left": "한 플레이어가 나갔습니다",
    "a player lost the connection": "한 플레이어의 연결이 끊겼습니다",
    "a player did not report": "한 플레이어가 보고하지 않았습니다",
    "the connection between the games failed": "게임 간 연결이 실패했습니다",
    "both players left": "두 플레이어 모두 나갔습니다",
    "no result in time": "제시간에 결과 없음",
    "repeated crashes count as losses": "반복되는 충돌은 패배로 처리됩니다",
    "repeated early quits": "반복된 조기 이탈",
    "repeated missing reports": "반복된 결과 미보고",
    "scores differed": "점수가 서로 달랐습니다",
    "the fight ended without a winner": "대전이 승자 없이 끝났습니다",
    "Match declined.": "매치를 거절했습니다.",
    "Nobody accepted in time.": "제시간에 아무도 수락하지 않았습니다.",
    "Your opponent left.": "상대가 나갔습니다.",
    "No UDP connection to the lobby server (firewall?).": "로비 서버와 UDP 연결이 없습니다 (방화벽?).",
    "Could not connect the two PCs, not even through the relay.": "두 PC를 연결할 수 없었습니다. 릴레이로도 안 됩니다.",
    "The lobby server's relay is full; try again in a moment.":
        "로비 서버의 릴레이가 가득 찼습니다. 잠시 후 다시 시도하세요.",
    "Challenge cancelled.": "도전이 취소되었습니다.",
    "Challenge declined.": "도전이 거절되었습니다.",
    "Challenge expired.": "도전이 만료되었습니다.",
    "direct": "직접",
    "via the lobby server's relay": "로비 서버의 릴레이 경유",
    "via the relay server {name}": "릴레이 서버 {name} 경유",
    "Lobby error: {error}": "로비 오류: {error}",
    "guest": "게스트",
    "Not connected. Ranked needs an account; guests play casual matches.":
        "연결되지 않음. Ranked는 계정이 필요하며, 게스트는 일반 매치를 합니다.",
    "Passwords are only sent to servers on this PC / your network, or over an encrypted "
    "(TLS) connection.":
        "비밀번호는 이 PC나 내 네트워크의 서버, 또는 암호화된(TLS) 연결로만 보냅니다.",
    "Double-click a player in the lobby or the leaderboard.": "로비나 순위표에서 플레이어를 더블클릭하세요.",
    "{name} (guest, casual matches only)": "{name} (게스트, 일반 매치만)",
    "{record} this session": "이번 세션 {record}",
    "rating {rating}": "레이팅 {rating}",
    "main {character}": "주캐 {character}",
    "server ping {ms} ms": "서버 핑 {ms}ms",
    "encrypted": "암호화됨",
    "[Server: {notice}]": "[서버: {notice}]",
    "Server notice: {notice}": "서버 공지: {notice}",
    "The game is not built.": "게임이 빌드되지 않았습니다.",
    "Cannot read the build's identity: {error}": "빌드 식별 정보를 읽을 수 없습니다: {error}",
    "Enter a password (6 characters or more), or play as a guest.":
        "비밀번호를 입력하거나 (6자 이상), 게스트로 플레이하세요.",
    "Connecting to {server}...": "{server}에 연결하는 중...",
    "Pick a character, then Ranked match (accounts) or Quick match.":
        "캐릭터를 고른 뒤 Ranked 매치(계정 필요) 또는 Quick Match를 누르세요.",
    "Encrypted connection (TLS).": "암호화된 연결 (TLS).",
    "(logged in with your saved login)": "(저장된 로그인으로 로그인함)",
    "In the lobby.": "로비에 있습니다.",
    "Your saved login has expired; log in with your password.":
        "저장된 로그인이 만료되었습니다. 비밀번호로 로그인하세요.",
    "Create account": "계정 만들기",
    "Type the password again:": "비밀번호를 한 번 더 입력하세요:",
    "The two passwords differ.": "두 비밀번호가 다릅니다.",
    "Closing the running game for the online match...": "온라인 매치를 위해 실행 중인 게임을 닫는 중...",
    "Also forget the saved login on this PC?\n\n(No = you are logged in automatically "
    "next time.)":
        "이 PC에 저장된 로그인도 지울까요?\n\n(아니요 = 다음에 자동으로 로그인됩니다.)",
    "Log out": "로그아웃",
    "Not connected.": "연결되지 않음.",
    "Change password": "비밀번호 변경",
    "Current password:": "현재 비밀번호:",
    "New password (6 characters or more):": "새 비밀번호 (6자 이상):",
    "New password again:": "새 비밀번호 다시 입력:",
    "The two new passwords differ.": "두 새 비밀번호가 다릅니다.",
    "Password changed. Saved logins on other PCs have ended.":
        "비밀번호를 바꿨습니다. 다른 PC의 저장된 로그인은 종료되었습니다.",
    "Recovery codes": "복구 코드",
    "Your password (the old codes stop working):": "비밀번호 (이전 코드는 더 이상 쓸 수 없게 됩니다):",
    "Save recovery codes": "복구 코드 저장",
    "T5DR Online recovery codes for {name} on {server}": "{server}의 {name} 계정 T5DR Online 복구 코드",
    "Forgot password": "비밀번호 찾기",
    "Account name:": "계정 이름:",
    "One of your recovery codes (XXXX-XXXX-XXXX):": "복구 코드 중 하나 (XXXX-XXXX-XXXX):",
    "Password reset. {count} recovery code(s) left. Log in with the new password.":
        "비밀번호를 재설정했습니다. 남은 복구 코드 {count}개. 새 비밀번호로 로그인하세요.",
    "Server certificate": "서버 인증서",
    "For a server with its own (self-signed) certificate: its SHA-256 fingerprint, from "
    "whoever runs it.\nEmpty = no pinning (use tls://host:port for a server with a "
    "normal certificate).":
        "자체(자체 서명) 인증서를 쓰는 서버용: 서버 운영자에게 받은 SHA-256 지문.\n비워 두면 고정하지 않습니다 (일반 "
        "인증서를 쓰는 서버는 tls://host:port 사용).",
    "Searching for an opponent...": "상대를 찾는 중...",
    "Searching for an opponent (ranked: similar rank and a good connection, strict: "
    "within 150 rating points -- this can take a while)...":
        "상대를 찾는 중 (Ranked: 비슷한 랭크와 좋은 연결, 엄격: 레이팅 150점 이내 -- 시간이 걸릴 수 있습니다)...",
    "Searching for an opponent (ranked: similar rank and a good connection)...":
        "상대를 찾는 중 (Ranked: 비슷한 랭크와 좋은 연결)...",
    "Select a room first.": "먼저 방을 고르세요.",
    "Select an opponent in the list first.": "먼저 목록에서 상대를 고르세요.",
    "Challenge sent.": "도전을 보냈습니다.",
    "Blocked players": "차단한 플레이어",
    "You are never matched with these players (ranked, quick matches, rooms, challenges, "
    "rematches). They are not told. Accounts stay blocked; a guest is blocked until you "
    "log out.":
        "이 플레이어들과는 절대 매칭되지 않습니다 (Ranked, Quick Match, 방, 도전, Rematch). 상대에게는 알리지 않습니다"
        ". 계정은 계속 차단되며, 게스트는 로그아웃할 때까지 차단됩니다.",
    "Unblocked {name}.": "{name}님의 차단을 해제했습니다.",
    "Unblock": "차단 해제",
    "Block player": "플레이어 차단",
    "Block {name}?\n\nYou will not be matched with them again. They are not told. You "
    "can unblock them under \"Blocked players...\".":
        "{name}님을 차단할까요?\n\n다시는 매칭되지 않으며, 상대에게는 알리지 않습니다. '차단한 플레이어...'에서 해제할"
        " 수 있습니다.",
    "Blocked {name}. You will not be matched again.": "{name}님을 차단했습니다. 다시는 매칭되지 않습니다.",
    "you": "나",
    "{name} -- {rank}": "{name} -- {rank}",
    "Rating {rating} +/- {rd}": "레이팅 {rating} +/- {rd}",
    "(provisional)": "(임시)",
    "#{place} on the leaderboard": "순위표 {place}위",
    "Record {record}": "전적 {record}",
    "ranked matches {count}": "Ranked 매치 {count}",
    "highest rank {rank}": "최고 랭크 {rank}",
    "Characters: {list}": "캐릭터: {list}",
    "Matches without result caused in the last 24 h: {count}": "최근 24시간 동안 내가 일으킨 결과 없는 매치: {count}",
    "Recovery codes left: {count}": "남은 복구 코드: {count}",
    "{you} vs {opponent}": "{you} vs {opponent}",
    "casual": "일반",
    "Opponent: {name} ({rank}, {rating})": "상대: {name} ({rank}, {rating})",
    "RANKED": "RANKED",
    "rematch": "Rematch",
    "{name} ({rank}) challenges you": "{name} ({rank})님이 도전했습니다",
    "Accept": "수락",
    "Decline": "거절",
    "Challenge {state}.": "도전: {state}.",
    "connecting...": "연결 중...",
    "Your opponent accepted.": "상대가 수락했습니다.",
    "Match cancelled ({reason}).": "매치 취소됨 ({reason}).",
    "Ranked match vs {name}": "{name}님과 Ranked 매치",
    "Casual match vs {name}": "{name}님과 일반 매치",
    "{p1} vs {p2}": "{p1} vs {p2}",
    "ping {ms} ms ({how}), input delay {frames} frames ({delay_ms} ms)":
        "핑 {ms}ms ({how}), 입력 지연 {frames}프레임 ({delay_ms}ms)",
    "Lost the lobby connection -- reconnecting (your match goes on)...":
        "로비 연결이 끊겼습니다 -- 다시 연결하는 중 (매치는 계속됩니다)...",
    "Reconnected to the lobby.": "로비에 다시 연결했습니다.",
    "Lost the lobby connection: {reason}": "로비 연결이 끊겼습니다: {reason}",
    "Lost the connection to the lobby server.": "로비 서버와의 연결이 끊겼습니다.",
    "Removed from the lobby: {reason}": "로비에서 제거됨: {reason}",
    "The game closed. How did the match against {opponent} end?":
        "게임이 종료되었습니다. {opponent}님과의 매치 결과는?",
    "I won": "이겼음",
    "I lost": "졌음",
    "Draw": "무승부",
    "I quit": "기권했음",
    "{opponent} wants a rematch": "{opponent}님이 Rematch를 원합니다",
    "Rematch": "Rematch",
    "No thanks": "괜찮습니다",
    "Result sent; waiting for your opponent's report...": "결과를 보냈습니다. 상대의 보고를 기다리는 중...",
    "Rematch offered; waiting for your opponent...": "Rematch를 신청했습니다. 상대를 기다리는 중...",
    "(other version)": "(다른 버전)",
    "ranked": "Ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "검색 중... (Ranked 대기 {ranked}명, Quick Match {quick}명)",
    "ping about {ms} ms (through the server; measured directly once you both accept)":
        "핑 약 {ms}ms (서버 경유 추정, 둘 다 수락하면 직접 측정)",
    "ping not known yet": "핑 아직 모름",
    "Opponent found": "상대를 찾았습니다",
    "accept within {seconds} s?": "{seconds}초 안에 수락할까요?",
    "waiting for the opponent...": "상대를 기다리는 중...",
    "Lag check: {text}": "랙 체크: {text}",
    "You left after the lag check. No penalty, no rating change.":
        "랙 체크 후 나갔습니다. 페널티도, 레이팅 변동도 없습니다.",
    "Your opponent left after the lag check. No penalty for anyone.":
        "상대가 랙 체크 후 나갔습니다. 아무도 페널티를 받지 않습니다.",
    "Your opponent left. The set is over.": "상대가 나갔습니다. 세트가 끝났습니다.",
    "Rematch {name}": "{name}님과 Rematch",
    "Next game": "다음 경기",
    "Leave": "나가기",
    "Block {name}": "{name} 차단",
    "Leave: too laggy": "나가기: 랙이 심함",
    "You lost.": "패배했습니다.",
    "You won.": "승리했습니다.",
    "rating {rating} ({delta})": "레이팅 {rating} ({delta})",
    "PROMOTED to {rank}!": "{rank}(으)로 승급!",
    "demoted to {rank}": "{rank}(으)로 강등",
    "placed at {rank}": "{rank}에 배치됨",
    "placement {done}/{total}": "배치 {done}/{total}",
    "your opponent": "상대",
    "Rematch?": "Rematch?",
    "Controller off.": "컨트롤러 꺼짐.",
    "No controller found.": "컨트롤러가 없습니다.",
    "Controller: {summary}": "컨트롤러: {summary}",
    "Cannot start the lobby server: {error}": "로비 서버를 시작할 수 없습니다: {error}",
    "Stop hosting": "호스트 중지",
    "Starting a lobby server on this PC and asking the router to forward its ports...":
        "이 PC에서 로비 서버를 시작하고 공유기에 포트 포워딩을 요청하는 중...",
    "Starting a lobby server on this PC...": "이 PC에서 로비 서버를 시작하는 중...",
    "<your public IP>": "<내 공인 IP>",
    "Hosting. Friends paste this as their Server (copied to the clipboard):\n  {share}":
        "호스트 중입니다. 친구들은 이것을 서버 칸에 붙여 넣으면 됩니다 (클립보드에 복사됨):\n  {share}",
    "\n  same network: {lan}": "\n  같은 네트워크: {lan}",
    "\n  Forward TCP+UDP 7781 and UDP 7782 on your router (or tick 'Open router ports').":
        "\n  공유기에서 TCP+UDP 7781과 UDP 7782를 포워딩하세요 (또는 '공유기 포트 열기'를 체크).",
    "Hosting a lobby on this PC. Log in to join it yourself.":
        "이 PC에서 로비를 호스트하고 있습니다. 직접 들어가려면 로그인하세요.",
    "Hosting failed: {message}": "호스트 실패: {message}",
    "Host for friends": "친구용 호스트",
    "The lobby server stopped (exit code {code}); see its log in {folder}.":
        "로비 서버가 종료되었습니다 (종료 코드 {code}). 로그는 {folder}에 있습니다.",
    "Stopped hosting.": "호스트를 중지했습니다.",
    # in-game character select (branch ingame-select)
    "Pick your fighter in the game ({secs} s; Select = random; no pick = the character set here).":
        "게임에서 캐릭터를 고르세요 ({secs}초, Select = 랜덤, 안 고르면 여기서 정한 캐릭터).",
    "Waiting for your opponent to pick...": "상대가 고르기를 기다리는 중...",
    "Ranked match (accounts) or Quick match; then pick your fighter in the game (Select = random). The character here is used when you do not pick in time.":
        "Ranked 매치(계정) 또는 Quick Match를 고른 뒤, 게임에서 캐릭터를 고르세요 (Select = 랜덤). 제시간에 안 고르면"
        " 여기 캐릭터를 씁니다.",
    "pick your fighter in the game ({secs} s)": "게임에서 캐릭터 선택 ({secs}초)",
    "(locked for this ranked set)": "(이 Ranked 세트 동안 고정)",
    "Pick your fighter in the game": "게임에서 캐릭터를 고르세요",
    "Your opponent is picking": "상대가 고르는 중",
    # ---- lobby/t5lobby/tk_views.py
    "Rank": "랭크",
    "Rating": "레이팅",
    "Record": "전적",
    "Main": "주캐",
    "Ping": "핑",
    "Room": "방",
    "Status": "상태",
    "Owner": "방장",
    "Place": "순위",
    "State": "상태",
    "When": "시간",
    "Characters": "캐릭터",
    "Opponent": "상대",
    "Result": "결과",
    "Score": "라운드",
    "Check the server address and your internet connection, then try again.":
        "서버 주소와 인터넷 연결을 확인한 뒤 다시 시도하세요.",
    "Check your internet connection, then try again.": "인터넷 연결을 확인한 뒤 다시 시도하세요.",
    "The server is slow or gone; try again in a minute.": "서버가 느리거나 꺼졌습니다. 1분 뒤 다시 시도하세요.",
    "Log in again.": "다시 로그인하세요.",
    "Ask whoever runs the server for its current fingerprint (\"Server certificate...\").":
        "서버 운영자에게 현재 지문을 물어보세요 ('서버 인증서...').",
    "Check the spelling, or use \"Forgot password...\".": "철자를 확인하거나 '비밀번호 찾기...'를 사용하세요.",
    "Check the name and the code; each code works once.": "이름과 코드를 확인하세요. 코드는 한 번만 쓸 수 있습니다.",
    "Pick another name, or wait a minute if that was you.": "다른 이름을 고르거나, 본인이었다면 1분 기다리세요.",
    "Log in with that account's password, or pick another name.":
        "그 계정의 비밀번호로 로그인하거나 다른 이름을 고르세요.",
    "Pick another name.": "다른 이름을 고르세요.",
    "Update the game to the release this server asks for.": "이 서버가 요구하는 릴리스로 게임을 업데이트하세요.",
    "You both need the same release of the game.": "두 사람 모두 같은 릴리스의 게임이 필요합니다.",
    "Update the launcher to the newest release.": "런처를 최신 릴리스로 업데이트하세요.",
    "Create an account (free) to play ranked.": "Ranked를 하려면 (무료) 계정을 만드세요.",
    "Pick another room or create your own.": "다른 방을 고르거나 직접 만드세요.",
    "Log in with your password.": "비밀번호로 로그인하세요.",
    "Build the game on the Build tab first.": "먼저 빌드 탭에서 게임을 빌드하세요.",
    "Allow T5DR Online through the Windows firewall, then search again.":
        "Windows 방화벽에서 T5DR Online을 허용한 뒤 다시 검색하세요.",
    "Try again; if it keeps failing, check your firewall or router.":
        "다시 시도하세요. 계속 실패하면 방화벽이나 공유기를 확인하세요.",
    "Log in again; your settings are kept.": "다시 로그인하세요. 설정은 그대로 유지됩니다.",
    "Type the same password twice.": "같은 비밀번호를 두 번 입력하세요.",
    "Find a new opponent.": "새 상대를 찾으세요.",
    "Check the Play offline tab: does the game start there?":
        "오프라인 플레이 탭을 확인하세요: 거기서는 게임이 시작되나요?",
    "Against other players over the internet. Log in or play as a guest; the game starts "
    "by itself, straight into the fight, and the result comes back here.":
        "인터넷으로 다른 플레이어와 대전합니다. 로그인하거나 게스트로 플레이하세요. 게임이 자동으로 바로 대전 화면에서"
        " 시작하고, 결과는 여기로 돌아옵니다.",
    "Server": "서버",
    "Server certificate...": "서버 인증서...",
    "Name": "이름",
    "Log in": "로그인",
    "Password": "비밀번호",
    "Password again": "비밀번호 확인",
    "Name: 2 to 16 letters, digits, spaces or _-.[]()!?": "이름: 2-16자의 글자, 숫자, 공백 또는 _-.[]()!?",
    "Password: 6 to 128 characters": "비밀번호: 6-128자",
    "Both passwords the same": "두 비밀번호 일치",
    "You get recovery codes once: the only way back in if you forget the password":
        "복구 코드는 한 번만 받습니다: 비밀번호를 잊었을 때 다시 들어올 유일한 방법입니다",
    "Remember me": "로그인 유지",
    "Forgot password...": "비밀번호 찾기...",
    "Casual matches with the name above, no account and no password. Ranked matches, the "
    "leaderboard and your match history need an account.":
        "위의 이름으로 계정과 비밀번호 없이 일반 매치를 합니다. Ranked 매치, 순위표, 매치 기록은 계정이 필요합니다.",
    "Play as guest": "게스트로 플레이",
    "Runs a lobby on this PC. Your friends type the address it shows into their Server "
    "box.":
        "이 PC에서 로비를 실행합니다. 친구들은 표시된 주소를 서버 칸에 입력합니다.",
    "Open router ports (UPnP)": "공유기 포트 열기 (UPnP)",
    "How it works": "이용 방법",
    "Quick match (casual) or Ranked match (account).": "Quick Match(일반) 또는 Ranked 매치(계정).",
    "An opponent is found: accept within 15 seconds.": "상대가 잡히면 15초 안에 수락하세요.",
    "The game opens straight into the fight.": "게임이 바로 대전 화면으로 열립니다.",
    "The result comes back here: rematch or next game.": "결과는 여기로 돌아옵니다: Rematch 또는 다음 경기.",
    "With a controller: A accepts, B declines.": "컨트롤러: A 수락, B 거절.",
    "Lobby": "로비",
    "Leaderboard": "순위표",
    "Profile": "프로필",
    "My profile": "내 프로필",
    "Find an opponent online": "온라인 상대 찾기",
    "Character": "캐릭터",
    "Locked for this ranked set": "이 Ranked 세트 동안 고정",
    "Ranked match": "Ranked 매치",
    "Quick match": "Quick Match",
    "Casual: the lowest ping first": "일반: 핑이 가장 낮은 상대부터",
    "Strict (ranked: +-150 rating)": "엄격 (Ranked: 레이팅 +-150)",
    "Searching": "검색 중",
    "Looking for an opponent": "상대를 찾고 있습니다",
    "Searching for": "검색 시간",
    "Stop searching": "검색 중지",
    "In match": "매치 중",
    "CASUAL": "일반",
    "Input delay": "입력 지연",
    "Connection": "연결",
    "Players online": "접속 중인 플레이어",
    "Challenge": "도전",
    "Rooms": "방",
    "Create room": "방 만들기",
    "Join room": "방 참가",
    "Leave room": "방 나가기",
    "Chat": "채팅",
    "Send": "보내기",
    "Refresh": "새로고침",
    "Order: rating minus twice its uncertainty (a few matches are needed to climb). '?' "
    "= provisional.":
        "정렬: 레이팅에서 불확실도의 두 배를 뺀 값 (올라가려면 몇 판이 필요합니다). '?' = 임시.",
    "Your account": "내 계정",
    "Blocked players...": "차단한 플레이어...",
    "Change password...": "비밀번호 변경...",
    "New recovery codes...": "새 복구 코드...",
    "Dismiss": "숨기기",
    "Use a controller here": "여기서 컨트롤러 사용",
    "none open": "열린 방 없음",
    "In your room “{name}”. Waiting for a second player...": "내 방 '{name}'. 두 번째 플레이어를 기다리는 중...",
    "In the room “{name}”. The match starts when you are both ready.": "방 '{name}'. 둘 다 준비되면 매치가 시작됩니다.",
    "Hosting. Friends type this as their Server:\n{share}":
        "호스트 중입니다. 친구들은 이것을 서버 칸에 입력합니다:\n{share}",
    "Same network: {lan}": "같은 네트워크: {lan}",
    "Guest · casual matches": "게스트 · 일반 매치",
    "Rating {rating}  ·  {record}": "레이팅 {rating}  ·  {record}",
    "Main: {character}": "주캐: {character}",
    "Server ping {ms} ms": "서버 핑 {ms}ms",
    "Create an account to play ranked": "Ranked를 하려면 계정을 만드세요",
    "Rated: close to your rank, good connection": "랭크 반영: 비슷한 랭크, 좋은 연결",
    "Similar rank and a good connection, strict: within 150 rating points (this can take "
    "a while).":
        "비슷한 랭크와 좋은 연결, 엄격: 레이팅 150점 이내 (시간이 걸릴 수 있습니다).",
    "Similar rank and a good connection.": "비슷한 랭크와 좋은 연결.",
    "The opponent with the lowest ping first.": "핑이 가장 낮은 상대부터.",
    "{ranked} in the ranked queue  ·  {quick} in quick match": "Ranked 대기 {ranked}명  ·  Quick Match {quick}명",
    "Character select": "캐릭터 선택",
    "Stage select": "스테이지 선택",
    "Match over": "매치 종료",
    "Waiting for the next match": "다음 매치를 기다리는 중",
    "Your game is running": "게임 실행 중",
    "Starting the game...": "게임 시작 중...",
    "Waiting for the game...": "게임을 기다리는 중...",
    "vs your opponent": "vs 상대",
    "vs {name}": "vs {name}",
    "{count} frame  ({ms} ms)": "{count}프레임  ({ms}ms)",
    "{count} frames  ({ms} ms)": "{count}프레임  ({ms}ms)",
    "Direct": "직접",
    "Local network": "로컬 네트워크",
    "Relay (lobby server)": "릴레이 (로비 서버)",
    "Relay ({name})": "릴레이 ({name})",
    "Guest": "게스트",
    "{rank}  ·  rating {rating}": "{rank}  ·  레이팅 {rating}",
    "SET · GAME {game}": "세트 · {game}경기",
    "Opponent hidden": "상대 비공개",
    "Name and side are shown once you both accept.": "둘 다 수락하면 이름과 위치가 공개됩니다.",
    "(estimate through the server)": "(서버 경유 추정)",
    "Accepted. Waiting for your opponent...": "수락했습니다. 상대를 기다리는 중...",
    "Match ready": "매치 준비 완료",
    "Connecting the two games...": "두 게임을 연결하는 중...",
    "wants to play you. Accept to start the match.": "님이 대전을 신청했습니다. 수락하면 매치가 시작됩니다.",
    "YOU WIN": "승리",
    "YOU LOSE": "패배",
    "DRAW": "무승부",
    "MATCH OVER": "매치 종료",
    "NO CONTEST": "무효 경기",
    "Casual match": "일반 매치",
    "ROUNDS  (P1 – P2)": "라운드  (P1 – P2)",
    "ROUNDS  (YOU – THEM)": "라운드  (나 – 상대)",
    "GAMES  (YOU – THEM)": "경기  (나 – 상대)",
    "SET WON": "세트 승리",
    "The game waits here for your next match: Rematch, Next game or Leave.":
        "게임은 여기서 다음 매치를 기다립니다: Rematch, 다음 경기 또는 나가기.",
    "SET LOST": "세트 패배",
    "Ranked set": "Ranked 세트",
    "Ranked set vs {name}": "{name}님과 Ranked 세트",
    "RANKED SET · BEST OF {best}": "RANKED 세트 · {best}판 승부",
    "Game {number} of {best} starts in": "{best}판 중 {number}경기 시작까지",
    "Game {number} of {best} again (no winner), starts in": "{best}판 중 {number}경기 다시 (승자 없음), 시작까지",
    "Rating {rating}": "레이팅 {rating}",
    "PROMOTED": "승급",
    "DEMOTED": "강등",
    "PLACED": "배치 완료",
    "Placement match {done} of {total}": "배치 매치 {done}/{total}",
    "Lag check": "랙 체크",
    "Rematch offered. Waiting for {opp}...": "Rematch를 신청했습니다. {opp}님을 기다리는 중...",
    "Back to the lobby": "로비로 돌아가기",
    "New recovery codes": "새 복구 코드",
    "Your account is ready": "계정이 준비되었습니다",
    "These codes are the only way back into your account if you forget the password "
    "(there is no e-mail). Each code works once. Write them down or save them somewhere "
    "safe -- they are not shown again.":
        "이 코드는 비밀번호를 잊었을 때 계정으로 돌아올 유일한 방법입니다 (이메일 없음). 코드는 각각 한 번만 쓸 수 "
        "있습니다. 적어 두거나 안전한 곳에 저장하세요 -- 다시는 표시되지 않습니다.",
    "Save to a file...": "파일로 저장...",
    "I have saved them": "저장했습니다",
}
