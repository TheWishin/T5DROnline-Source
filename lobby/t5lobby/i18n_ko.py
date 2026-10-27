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
    "Removed {sources} from your buttons: that is L2 / R2 at rest on a PlayStation pad, so the game held them all the time. Save to keep this.":
        "버튼에서 {sources}을(를) 뺐습니다: PlayStation 패드에서 L2 / R2를 놓은 상태라 게임이 계속 누른 것으로 처리했습니다. 유지하려면 저장하세요.",
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
    "PlayStation pad, read directly": "PlayStation 패드 (직접 읽기)",
    "Arrows move; A S on top are 1 2, Z X below are 3 4. Q W are L1 R1, 1 2 are L2 R2, Enter is Start, Tab is Select.": "화살표로 이동. 위의 A S가 1 2, 아래 Z X가 3 4. Q W가 L1 R1, 1 2가 L2 R2, Enter가 Start, Tab이 Select.",
    "Arrows move; number pad 4 5 are 1 2, 1 2 are 3 4, 6 is 1+2, 3 is 3+4 (Num Lock on).": "화살표로 이동. 숫자 패드 4 5가 1 2, 1 2가 3 4, 6이 1+2, 3이 3+4 (Num Lock 켜기).",
    "Esc (leaves the game)": "Esc (게임 종료)",
    "F11 (fullscreen)": "F11 (전체 화면)",
    "F2 (training overlay)": "F2 (트레이닝 표시)",
    "Keyboard, second player": "키보드, 두 번째 플레이어",
    "Keyboard: WASD and U I J K": "키보드: WASD와 U I J K",
    "Keyboard: arrows and A S Z X": "키보드: 화살표와 A S Z X",
    "Keyboard: arrows and number pad": "키보드: 화살표와 숫자 패드",
    'Keyboard: pick a game button, then Set selected (or double-click it) and press the key. Esc stops. The game reads the keyboard while its window has the focus.': '키보드: 게임 버튼을 고른 뒤 "선택한 버튼 설정"(또는 더블 클릭)을 누르고 키를 누르세요. Esc로 중지합니다. 게임은 창에 포커스가 있을 때 키보드를 읽습니다.',
    "Press only that one key. Esc stops.": "그 키 하나만 누르세요. Esc로 중지합니다.",
    "Press the key for {button}...": "{button}에 쓸 키를 누르세요...",
    "The keyboard ([{section}] in controls.ini)": "키보드 (controls.ini의 [{section}])",
    "W A S D move; U I are 1 2, J K are 3 4, O is 1+2, L is 3+4. Y P are L1 R1, H and ; are L2 R2, Enter is Start, Backspace is Select.": "W A S D로 이동. U I가 1 2, J K가 3 4, O가 1+2, L이 3+4. Y P가 L1 R1, H와 ;가 L2 R2, Enter가 Start, Backspace가 Select.",
    "{key} is the game's own key; press another one.": '{key}은(는) 게임 자체가 쓰는 키입니다. 다른 키를 누르세요.',
    "{source} is also {other} for the second keyboard player.": "{source}은(는) 두 번째 키보드 플레이어에게는 {other}이기도 합니다.",
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
    "Auto (laptops, handhelds, integrated graphics)": "자동 (노트북, 휴대용 PC, 내장 그래픽)",
    "On": "켜기",
    "a mobile processor": "모바일 프로세서",
    "battery saver is on": "Windows 배터리 절약 모드가 켜져 있음",
    "the Power saver power plan is on": "전원 관리 옵션 '절전'이 켜져 있음",
    "this PC has a battery (laptop or handheld)": "이 PC에 배터리가 있음 (노트북 또는 휴대용 PC)",
    "Inputs": "입력",
    "Inputs + frame data": "입력 + 프레임 데이터",
    "Auto (Windows language)": "자동 (Windows 언어)",
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
    "The translation step has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, close other programs, press Cancel and then BUILD GAME again; build.log "
    "has the details.":
        "'코드 변환' 단계가 {minutes}분 동안 아무것도 출력하지 않았습니다. 느리거나 바쁜 PC에서는 아직 작업 중일 수 "
        "있습니다. 변화가 없으면 다른 프로그램을 닫고 취소를 누른 뒤 BUILD GAME을 다시 누르세요. 자세한 내용은 "
        "build.log에 있습니다.",
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
    "Discord": "Discord",
    "Show what I play in my Discord status (Rich Presence)": "Discord 상태에 지금 하는 게임 표시 (Rich Presence)",
    "\"In lobby\", \"Searching ranked\" or your match (fighters, ranked set score) with a timer, through the "
    "Discord app on this PC. Without Discord running nothing happens.":
        "'로비에서 대기 중', 'Ranked 검색 중' 또는 내 매치(캐릭터, Ranked 세트 점수)를 시간과 함께 이 PC의 Discord "
        "앱으로 표시합니다. Discord가 실행 중이 아니면 아무 일도 일어나지 않습니다.",
    "Power saving (laptops, handhelds)": "절전 (노트북, 휴대용 PC)",
    "No busy waiting and fewer worker threads: the processor stays cooler and keeps its speed, so the game "
    "holds 60 fps longer. The game itself is the same, online too.":
        "바쁜 대기 없이 작업 스레드를 줄입니다: 프로세서가 덜 뜨거워지고 속도를 유지해 게임이 60fps를 더 오래 지킵니다"
        ". 게임 자체는 같으며 온라인에서도 마찬가지입니다.",
    "On for this PC.": "이 PC에서 켜짐.",
    "Off.": "꺼짐.",
    "Auto: on for this PC -- {reason}.": "자동: 이 PC에서는 켜짐 -- {reason}.",
    "Auto: off for this PC (no battery, no mobile processor); the game turns it on by itself if it runs on "
    "integrated graphics.":
        "자동: 이 PC에서는 꺼짐 (배터리 없음, 모바일 프로세서 아님). 내장 그래픽으로 실행되면 게임이 스스로 켭니다.",
    "Power saving is on.": "절전이 켜져 있습니다.",
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
    "Unlocks": "잠금 해제",
    "Unlock all stages (the Tekken 5 stages, without clearing Arcade)":
        "모든 스테이지 잠금 해제 (Tekken 5 스테이지, Arcade를 클리어하지 않아도)",
    "Unlock Jinpachi and Random select (without clearing Arcade)":
        "Jinpachi와 Random 선택 잠금 해제 (Arcade를 클리어하지 않아도)",
    "Unlock all customization items (free in the item shop)":
        "모든 커스터마이즈 아이템 잠금 해제 (ITEM SHOP에서 무료)",
    "Offline only (Arcade, VS, Practice and the rest). Your save is not changed; items you take for free "
    "stay yours (the save is backed up first, in save-backups). Online, both players always get the "
    "same stages; Jinpachi and Random are there in casual matches and rooms, not in ranked.":
        "오프라인 전용입니다 (Arcade, VS, Practice 등). 세이브는 바뀌지 않습니다. 무료로 받은 아이템은 계속 내 것이 됩니다 (세이브를 먼저 save-backups에 "
        "백업합니다). 온라인에서는 두 플레이어가 항상 같은 스테이지를 씁니다. Jinpachi와 Random은 캐주얼 매치와 방에서 쓸 수 있고, Ranked에서는 쓸 수 없습니다.",
    "Sound and start": "소리 및 시작",
    "Mute sound": "소리 끄기",
    "Sound and taskbar flash when a match is found or someone joins my room": "매치가 잡히거나 누군가 내 방에 들어오면 소리와 작업 표시줄 깜박임",
    "Start minimized, without taking focus (for testing)": "최소화 상태로 포커스 없이 시작 (테스트용)",
    "Advanced: extra settings, one NAME=VALUE per line": "고급: 추가 설정, 한 줄에 하나씩 NAME=VALUE",
    "Internal resolution": "내부 해상도",
    "VSync": "VSync",
    "On (smooth, default)": "켜기 (부드러움, 기본)",
    "Off (lowest latency, may tear)": "끄기 (최소 지연, 화면 찢김 가능)",
    "The game always runs at 60 fps, like on the PS3.": "게임은 PS3처럼 항상 60fps로 동작합니다.",
    "Stage blur / glow": "스테이지 블러 / 빛 번짐",
    "Off (default)": "끄기 (기본)",
    "Off": "끄기",
    "Some stages blur the picture (the misty swamp) or let the sun glow. Off shows them sharp, "
    "without the glow. Only your picture changes: online, both players can choose differently.":
        "일부 스테이지는 화면을 흐리게 하거나(안개 낀 늪) 햇빛을 번지게 합니다. 끄면 번짐 없이 선명하게 보입니다. 내 "
        "화면만 바뀌므로 온라인에서 두 플레이어가 서로 다르게 골라도 됩니다.",
    "Training overlay": "트레이닝 오버레이",
    "Also in the other offline modes (Arcade, Versus, ...)": "다른 오프라인 모드에서도 (Arcade, Versus, ...)",
    "Practice tools": "연습 도구",
    "SELECT combos in Practice (offline only)": "Practice에서 SELECT 조합 (오프라인 전용)",
    "Dummy:": "더미:",
    "As set in the game's Practice menu": "게임의 Practice 메뉴 설정대로",
    "Blocks after the first hit": "첫 히트 후 가드",
    "Crouches": "앉기",
    "Walks forward and back": "앞뒤로 걷기",
    "Sidesteps": "횡이동",
    "In Practice, hold SELECT and press: 3 round start; f+3 / b+3 the dummy against the wall in front "
    "of / behind you; df+3 / db+3 you against the wall in front of / behind you. 1 records the dummy "
    "(you play it), 2 plays the recording once, 4 in a loop; tap up / down for slot 1-5, forward / "
    "back for what the dummy does.":
        "Practice에서 SELECT를 누른 채: 3 라운드 시작 위치; f+3 / b+3 더미를 앞 / 뒤 벽으로; df+3 / db+3 나를 앞 / 뒤 벽으로. 1 더미 녹화 "
        "(직접 조작), 2 녹화를 한 번 재생, 4 반복 재생; 위 / 아래를 짧게 눌러 슬롯 1-5, 앞 / 뒤로 더미 동작 변경.",
    "Also online (only your own inputs, no frame data)": "온라인에서도 (내 입력만, 프레임 데이터 없음)",
    "In Practice: your last inputs with how many frames each was held, and after each exchange the "
    "startup of the move and who can act first (+3, -12). F2 in the game switches it.":
        "Practice에서: 최근 입력과 각 입력을 유지한 프레임 수, 그리고 공방이 끝날 때마다 기술의 발생 프레임과 누가 "
        "먼저 움직일 수 있는지(+3, -12)를 표시합니다. 게임에서 F2로 켜고 끕니다.",
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
    "The keyboard only counts while the game window has focus. The game's own Options menu can change "
    "the button layout for offline play; online games use the launcher's buttons only.":
        "키보드와 첫 번째 XInput 컨트롤러는 둘 다 플레이어 1을 조작합니다 (합쳐짐). 키보드는 게임 창에 포커스가 있을 "
        "때만 적용됩니다. 게임 자체의 Options 메뉴에서 오프라인 플레이용 버튼 배치를 바꿀 수 있습니다. 온라인 "
        "게임은 런처의 버튼 설정만 사용합니다.",
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
    "too many password changes; wait a minute": "비밀번호 변경이 너무 많습니다. 1분 기다리세요",
    "too many requests for new codes; wait a minute": "새 코드 요청이 너무 많습니다. 1분 기다리세요",
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
    "guests cannot have friends; create an account (free)":
        "게스트는 친구를 추가할 수 없습니다. (무료) 계정을 만드세요",
    "there is no account with that name": "그 이름의 계정이 없습니다",
    "you cannot add yourself": "자기 자신은 추가할 수 없습니다",
    "you blocked that player; unblock them first": "그 플레이어를 차단했습니다. 먼저 차단을 해제하세요",
    "your friends list is full ({max})": "친구 목록이 가득 찼습니다 ({max})",
    "your last invite to that friend ended a moment ago; try again in {seconds} s":
        "이 친구에게 보낸 마지막 초대가 방금 끝났습니다. {seconds}초 후에 다시 시도하세요",
    "your last challenge to that player ended a moment ago; try again in {seconds} s":
        "이 플레이어에게 보낸 마지막 도전이 방금 끝났습니다. {seconds}초 후에 다시 시도하세요",
    "too many friend requests from this internet address today; try again tomorrow":
        "오늘 이 인터넷 주소에서 보낸 친구 요청이 너무 많습니다. 내일 다시 시도하세요",
    "you can send {count} friend requests a day; try again tomorrow":
        "친구 요청은 하루에 {count}개까지 보낼 수 있습니다. 내일 다시 시도하세요",
    "{count} of your friend requests are waiting for an answer; cancel some first":
        "보낸 친구 요청 {count}개가 응답을 기다리고 있습니다. 먼저 몇 개를 취소하세요",
    "{name} declined your last request; you can ask again in {days} day(s)":
        "{name}님이 지난 요청을 거절했습니다. {days}일 후 다시 요청할 수 있습니다",
    "that player has too many friend requests waiting": "그 플레이어에게 대기 중인 친구 요청이 너무 많습니다",
    "that player's friends list is full": "그 플레이어의 친구 목록이 가득 찼습니다",
    "no friend request from that player": "그 플레이어의 친구 요청이 없습니다",
    "no friend request to that player": "그 플레이어에게 보낸 친구 요청이 없습니다",
    "that player is not on your friends list": "그 플레이어는 친구 목록에 없습니다",
    "that friend is not online": "그 친구는 접속 중이 아닙니다",
    "that friend's launcher is too old for invites (it needs 1.1.2 or newer)":
        "그 친구의 런처가 너무 오래되어 초대를 받을 수 없습니다 (1.1.2 이상 필요)",
    "create a room first, then invite": "먼저 방을 만든 뒤 초대하세요",
    "that friend is busy right now": "그 친구는 지금 바쁩니다",
    "one invite at a time": "초대는 한 번에 하나만",
    "wait a moment before inviting again": "잠시 기다린 뒤 다시 초대하세요",
    "that player has invites pending": "그 플레이어에게 대기 중인 초대가 있습니다",
    "that invite is over": "그 초대는 끝났습니다",
    "the invite is no longer possible": "더 이상 초대할 수 없습니다",
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
    "the server sent a malformed match id": "서버가 잘못된 매치 ID를 보냈습니다",
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
    "CMake and Ninja were not found. On macOS: brew install cmake ninja sdl2 glslang spirv-cross":
        "CMake와 Ninja를 찾을 수 없습니다. macOS에서는 다음을 실행하세요: brew install cmake ninja sdl2 glslang spirv-cross",
    "glslang and spirv-cross were not found; the game's shaders need them. "
    "On macOS: brew install glslang spirv-cross":
        "glslang과 spirv-cross를 찾을 수 없습니다. 게임의 셰이더에 필요합니다. macOS에서는 다음을 실행하세요: brew install glslang spirv-cross",
    "Building the game is supported on Windows and macOS only.":
        "게임 빌드는 Windows와 macOS에서만 지원됩니다.",
    "This Python refuses pip install (PEP 668; Homebrew's does). Use a virtual environment: python3 -m venv .venv && .venv/bin/pip install pycryptodome, then run the tools with .venv/bin/python.":
        "이 Python은 pip install을 거부합니다(PEP 668, Homebrew의 Python이 그렇습니다). 가상 환경을 사용하세요: python3 -m venv .venv && .venv/bin/pip install pycryptodome 를 실행한 뒤 도구를 .venv/bin/python 으로 실행하세요.",
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
    "The last replay (the inputs of the last online session, without names)":
        "최신 리플레이(마지막 온라인 세션의 입력, 이름 없음)",
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
    "a name Windows does not keep as written": "Windows가 쓴 그대로 저장하지 않는 이름",
    "Release {version} is a test version; it is not installed automatically.":
        "릴리스 {version}은(는) 테스트 버전이라 자동으로 설치되지 않습니다.",
    "Release {version} is not signed with the project's release key (no SHA256SUMS.sig). It was not made by "
    "the project's release process; nothing was changed.":
        "릴리스 {version}은(는) 프로젝트의 릴리스 키로 서명되지 않았습니다 (SHA256SUMS.sig 없음). 프로젝트의 릴리스 "
        "과정에서 만들어진 것이 아닙니다. 아무것도 바뀌지 않았습니다.",
    "Release {version} failed the signature check ({error}). It was not made by the project's release "
    "process; nothing was changed.":
        "릴리스 {version}이(가) 서명 확인을 통과하지 못했습니다 ({error}). 프로젝트의 릴리스 과정에서 만들어진 것이 "
        "아닙니다. 아무것도 바뀌지 않았습니다.",
    "idle": "대기 중",
    "room": "방에 있음",
    "queue": "검색 중",
    "match": "매치 중",
    "playing": "플레이 중",
    # ---- lobby/t5lobby/discord_rpc.py
    "In lobby": "로비에서 대기 중",
    "Searching ranked": "Ranked 검색 중",
    "Searching quick match": "Quick Match 검색 중",
    "Ranked, Set {mine}-{theirs}": "Ranked, 세트 {mine}-{theirs}",
    "Ranked": "Ranked",
    "Casual": "일반",
    "In match: {mine} vs {theirs} ({what})": "대전 중: {mine} vs {theirs} ({what})",
    "In match ({what})": "대전 중 ({what})",
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
    "This match lagged: the games waited {secs} s for each other's inputs.":
        "이 대전은 랙이 있었습니다. 게임들이 서로의 입력을 {secs}초 기다렸습니다.",
    "A wired connection and no uploads during matches help.":
        "유선 연결을 쓰고 대전 중에는 업로드를 하지 않으면 도움이 됩니다.",
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "상대가 게임을 닫았습니다.",
    "The connection to your opponent's game was lost.": "상대 게임과의 연결이 끊겼습니다.",
    "Your opponent's game stopped responding.": "상대 게임이 응답하지 않습니다.",
    "Your opponent's game did not get to the fight.": "상대 게임이 대전까지 가지 못했습니다.",
    "Your opponent's game was restarted; the match cannot go on.":
        "상대 게임이 다시 시작되어 매치를 계속할 수 없습니다.",
    "Loading the fight took too long on this PC (slow disk or a busy PC?); the match was stopped.":
        "이 PC에서 대전 로딩이 너무 오래 걸렸습니다 (느린 디스크 또는 바쁜 PC?). 대전이 중단되었습니다.",
    "Loading the fight took too long on your opponent's PC; the match was stopped.":
        "상대 PC에서 대전 로딩이 너무 오래 걸렸습니다. 대전이 중단되었습니다.",
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
    # ---- lobby/t5lobby/tk_tour.py, tour_text.py (tournaments)
    "A set is played like a casual set with the in-game select; results come from the games. Players who do not accept a called set in time are out.": "세트는 게임 안 캐릭터 선택이 있는 일반 세트처럼 진행되고, 결과는 게임에서 가져옵니다. 호출된 세트를 제때 수락하지 않으면 탈락합니다.",
    "Accepted. Waiting for {name}...": "수락했습니다. {name}님을 기다리는 중...",
    "Bracket": "대진표",
    "CALLED": "호출됨",
    "Cancel tournament": "토너먼트 취소",
    "Cancel {name}? Nobody can play it any more.": "{name}을(를) 취소할까요? 더 이상 아무도 진행할 수 없습니다.",
    "Cancelled": "취소됨",
    "Champion: {name}": "우승: {name}",
    "Check in": "체크인",
    "Check-in": "체크인",
    "Check-in 10 minutes before": "10분 전 체크인",
    "Check-in 15 minutes before": "15분 전 체크인",
    "Check-in 30 minutes before": "30분 전 체크인",
    "Check-in 5 minutes before": "5분 전 체크인",
    "Check-in 60 minutes before": "60분 전 체크인",
    "Check-in for {name} is open: check in on the Tournaments page, or you are not in the bracket.": "{name}의 체크인이 열렸습니다: 토너먼트 페이지에서 체크인하지 않으면 대진표에 들어가지 못합니다.",
    "Checked in.": "체크인 완료.",
    "Click a set in the bracket.": "대진표에서 세트를 클릭하세요.",
    "Create": "만들기",
    "Create tournament": "토너먼트 만들기",
    "Create...": "만들기...",
    "Disqualify": "실격 처리",
    "Disqualify which player (name)?": "실격 처리할 플레이어 (이름)?",
    "Disqualify...": "실격 처리...",
    "Double elimination": "더블 엘리미네이션",
    "Final": "결승",
    "Finished": "종료",
    "First to 2 games (best of 3)": "2승 선승 (3판 승부)",
    "First to 3 games (best of 5)": "3승 선승 (5판 승부)",
    "Format": "방식",
    "Grand final": "그랜드 파이널",
    "Grand final reset": "그랜드 파이널 (리셋)",
    "LIVE": "진행 중",
    "Leave the tournament set": "토너먼트 세트 나가기",
    "Leave this tournament set?\n\nYou lose the set.": "이 토너먼트 세트에서 나갈까요?\n\n세트 패배로 처리됩니다.",
    "Losers final": "루저스 결승",
    "Losers round {number}": "루저스 {number}라운드",
    "Losers semi-final": "루저스 준결승",
    "NEEDS THE ORGANIZER": "주최자 확인 필요",
    "No check-in": "체크인 없음",
    "No tournament selected": "선택한 토너먼트 없음",
    "Only tournament hosts can create tournaments. Ask the server's owner for a host slot.":
        "토너먼트 호스트만 토너먼트를 만들 수 있습니다. 서버 운영자에게 호스트 자리를 요청하세요.",
    "Pick a tournament to see its bracket.": "토너먼트를 고르면 대진표가 보입니다.",
    "Pick one in the list, or create one.": "목록에서 고르거나 새로 만드세요.",
    "Players": "인원",
    "Players at most": "최대 인원",
    "Players: {list}": "참가자: {list}",
    "Quarter-final": "8강",
    "Random seeding": "무작위 시드",
    "Report a result": "결과 입력",
    "Reset set": "세트 초기화",
    "Reset set {set}? It is played again from 0-0.": "{set} 세트를 초기화할까요? 0-0부터 다시 진행합니다.",
    "Round {number}": "{number}라운드",
    "Running": "진행 중",
    "Seeded by rating": "레이팅 순 시드",
    "Seeding": "시드 배정",
    "Semi-final": "준결승",
    "Sets": "세트",
    "Side 1 wins": "1번 측 승리",
    "Side 2 wins": "2번 측 승리",
    "Sign up": "참가 신청",
    "Sign-up": "참가 신청 중",
    "Single elimination": "싱글 엘리미네이션",
    "Start now": "지금 시작",
    "Start {name} now, with the players who are in?": "참가 중인 플레이어로 {name}을(를) 지금 시작할까요?",
    "Starts": "시작",
    "TOURNAMENT": "토너먼트",
    "TOURNAMENT SET · BEST OF {best}": "토너먼트 세트 · {best}판 승부",
    "The bracket is drawn when the tournament starts.": "대진표는 토너먼트가 시작될 때 만들어집니다.",
    "The name needs 3 characters or more.": "이름은 3자 이상이어야 합니다.",
    "The organizer decided your tournament set.": "주최자가 토너먼트 세트를 결정했습니다.",
    "The organizer reset your tournament set; it is called again.": "주최자가 토너먼트 세트를 초기화했습니다. 다시 호출됩니다.",
    "The set goes on at {mine}-{theirs}.": "세트가 {mine}-{theirs}에서 이어집니다.",
    "The set has no result; the tournament calls it again or its organizer decides": "세트에 결과가 없습니다. 토너먼트가 다시 호출하거나 주최자가 결정합니다",
    "The set is called again.": "세트가 다시 호출되었습니다.",
    "The tournament was cancelled.": "토너먼트가 취소되었습니다.",
    "The tournament {name} has started: you are seed {seed} of {players}. Your sets are called here.": "토너먼트 {name}이(가) 시작되었습니다: {players}명 중 {seed}번 시드입니다. 세트는 여기서 호출됩니다.",
    "The tournament {name} is over: {champion} won it.": "토너먼트 {name}이(가) 끝났습니다: 우승은 {champion}님.",
    "The tournament {name} is over: {champion} won it. You finished {place}.": "토너먼트 {name}이(가) 끝났습니다: 우승은 {champion}님. 최종 {place}입니다.",
    "The tournament {name} was cancelled by its organizer.": "주최자가 토너먼트 {name}을(를) 취소했습니다.",
    "The tournament {name} was cancelled: not enough players.": "토너먼트 {name}이(가) 취소되었습니다: 인원 부족.",
    "This tournament had no bracket.": "이 토너먼트는 대진표가 없었습니다.",
    "This tournament is for another build of the game.": "이 토너먼트는 다른 빌드의 게임용입니다.",
    "Tournament": "토너먼트",
    "Tournament set": "토너먼트 세트",
    "Tournament set vs {name}": "{name}님과 토너먼트 세트",
    "Tournament {name} created.": "토너먼트 {name}을(를) 만들었습니다.",
    "Tournament {name}: set {set} needs you ({why}). Report the result or reset it.": "토너먼트 {name}: {set} 세트에 확인이 필요합니다 ({why}). 결과를 입력하거나 초기화하세요.",
    "Tournament {name}: {code}": "토너먼트 {name}: {code}",
    "Tournaments": "토너먼트",
    "Winners final": "위너스 결승",
    "Winners round {number}": "위너스 {number}라운드",
    "Winners semi-final": "위너스 준결승",
    "Withdraw": "기권",
    "Withdraw from {name}? You are out of the tournament.": "{name}에서 기권할까요? 토너먼트에서 탈락합니다.",
    "Write the start time as HH:MM, e.g. 20:30.": "시작 시각은 HH:MM 형식으로 쓰세요. 예: 20:30.",
    "You are checked in.": "체크인했습니다.",
    "You are in. Your next set is called here when its players are known.": "참가 중입니다. 다음 세트는 상대가 정해지면 여기서 호출됩니다.",
    "You are out of {name}.": "{name}에서 탈락했습니다.",
    "You are out of {name}: {place}.": "{name}에서 탈락했습니다: {place}.",
    "You are out of {name}: {why}.": "{name}에서 탈락했습니다: {why}.",
    "You are out: {why}.": "탈락했습니다: {why}.",
    "You are signed up.": "참가 신청했습니다.",
    "You are signed up. Check in now, or you are not in the bracket.": "참가 신청했습니다. 지금 체크인하지 않으면 대진표에 들어가지 못합니다.",
    "You did not check in for {name}; the tournament started without you.": "{name}에 체크인하지 않아 토너먼트가 나 없이 시작되었습니다.",
    "You finished {place}.": "최종 {place}입니다.",
    "You left the tournament.": "토너먼트에서 나갔습니다.",
    "You won the tournament {name}!": "토너먼트 {name}에서 우승했습니다!",
    "Your next set: {set}.": "다음 세트: {set}.",
    "Your opponent did not show up: you win the set.": "상대가 오지 않았습니다: 세트 승리입니다.",
    "Your opponent is out of the tournament: you win the set.": "상대가 토너먼트에서 탈락했습니다: 세트 승리입니다.",
    "Your tournament set has no result; the organizer decides how it goes on.": "토너먼트 세트에 결과가 없습니다. 주최자가 진행 방법을 결정합니다.",
    "Your tournament set is ready": "토너먼트 세트가 준비되었습니다",
    "accept within {seconds} s": "{seconds}초 안에 수락",
    "accepted -- waiting for {name}...": "수락함 -- {name}님을 기다리는 중...",
    "best of {best}": "{best}판 승부",
    "bye": "부전승",
    "check-in from {time}": "{time}부터 체크인",
    "decided by the organizer": "주최자 결정",
    "did not show up": "불참",
    "disqualified": "실격",
    "disqualified by the organizer": "주최자에 의한 실격",
    "ended {time}": "{time}에 종료",
    "in 1 hour": "1시간 후",
    "in 10 minutes": "10분 후",
    "in 12 hours": "12시간 후",
    "in 15 minutes": "15분 후",
    "in 2 hours": "2시간 후",
    "in 24 hours": "24시간 후",
    "in 3 hours": "3시간 후",
    "in 30 minutes": "30분 후",
    "in 5 minutes": "5분 후",
    "in 6 hours": "6시간 후",
    "no-show": "불참",
    "nobody": "없음",
    "none yet": "아직 없음",
    "not needed": "필요 없음",
    "or at (HH:MM)": "또는 시각 (HH:MM)",
    "organizer {name}": "주최자 {name}",
    "place {place}": "{place}위",
    "rated": "레이팅 반영",
    "results disputed": "결과 이의",
    "started {time}": "{time}에 시작함",
    "starts {time}": "{time} 시작",
    "waiting": "미정",
    "withdrew": "기권",
    "{format}, best of {best}": "{format}, {best}판 승부",
    "{name} has accepted.": "{name}님이 수락했습니다.",
    "{name} is not online yet.": "{name}님은 아직 접속하지 않았습니다.",
    "{name} wins": "{name} 승리",
    "{name} wins set {set}?": "{set} 세트를 {name}님의 승리로 할까요?",
    "{name}'s tournament": "{name}님의 토너먼트",
    "{players} of {max} players": "{max}명 중 {players}명",
    "The organizer decided the set.": "주최자가 세트를 결정했습니다.",
    # ---- lobby/t5lobby/i18n_known.py: lobby/t5lobby/server/tournaments.py
    "tournaments need an account": "토너먼트는 계정이 필요합니다",
    "no such tournament": "그런 토너먼트가 없습니다",
    "only the server's organizers can create tournaments here": "이 서버에서는 지정된 주최자만 토너먼트를 만들 수 있습니다",
    "a tournament name is 3-40 characters": "토너먼트 이름은 3~40자입니다",
    "the format is single or double elimination": "방식은 싱글 또는 더블 엘리미네이션입니다",
    "a set is first to 2 or first to 3 games": "세트는 2승 또는 3승 선승제입니다",
    "the player limit is 8, 16, 32 or 64": "최대 인원은 8, 16, 32, 64명 중 하나입니다",
    "the check-in window is 0, 5, 10, 15, 30 or 60 minutes": "체크인 시간은 0, 5, 10, 15, 30, 60분 중 하나입니다",
    "seeding is random or by rating": "시드 배정은 무작위 또는 레이팅 순입니다",
    "that start time has passed": "그 시작 시간은 이미 지났습니다",
    "a tournament starts within {days} days": "토너먼트는 {days}일 안에 시작해야 합니다",
    "this server has as many tournaments as it takes; try again later": "이 서버는 이미 받을 수 있는 만큼 토너먼트가 있습니다. 나중에 다시 시도하세요",
    "you already run {count} tournaments; finish or cancel one first": "이미 토너먼트 {count}개를 주최 중입니다. 먼저 하나를 끝내거나 취소하세요",
    "update the launcher to play in tournaments": "토너먼트에 참가하려면 런처를 업데이트하세요",
    "sign-up for that tournament is closed": "그 토너먼트는 참가 신청이 마감되었습니다",
    "that tournament is played with another build of the game": "그 토너먼트는 다른 빌드의 게임으로 진행됩니다",
    "that tournament is full": "그 토너먼트는 정원이 찼습니다",
    "you are not in that tournament": "그 토너먼트에 참가하고 있지 않습니다",
    "that tournament is over": "그 토너먼트는 끝났습니다",
    "check-in is not open": "체크인이 열려 있지 않습니다",
    "that tournament is not running": "그 토너먼트는 진행 중이 아닙니다",
    "that set is not yours to play": "내 세트가 아닙니다",
    "that set is not waiting for you": "그 세트는 나를 기다리고 있지 않습니다",
    "only the organizer can do that": "주최자만 할 수 있습니다",
    "that tournament name is not allowed here":
        "그 대회 이름은 여기서 사용할 수 없습니다",
    "this internet address runs as many tournaments as one organizer may; finish or cancel one first":
        "이 인터넷 주소에서 이미 주최자 한 명이 열 수 있는 만큼의 대회가 열려 있습니다. 먼저 하나를 끝내거나 취소하세요",
    "the organizer took you off this tournament":
        "주최자가 당신을 이 대회에서 제외했습니다",
    "you play in that set yourself: a server tournament admin decides it (or cancel the tournament)":
        "이 세트는 당신이 직접 경기합니다. 서버의 대회 관리자가 결정합니다(또는 대회를 취소하세요)",
    "that tournament has started already": "그 토너먼트는 이미 시작되었습니다",
    "a tournament needs at least 2 players": "토너먼트에는 최소 2명이 필요합니다",
    "no such player in that tournament": "그 토너먼트에 그런 플레이어가 없습니다",
    "that player is out already": "그 플레이어는 이미 탈락했습니다",
    "no such set": "그런 세트가 없습니다",
    "that set is decided; override it instead": "이미 결정된 세트입니다. 대신 결과를 수정하세요",
    "only a played set can be overridden": "진행된 세트만 결과를 수정할 수 있습니다",
    "that set has not been played": "아직 진행되지 않은 세트입니다",
    "that set was a walkover": "부전승으로 끝난 세트입니다",
    "set {set} was already played from this result; reset it first": "이 결과로 {set} 세트가 이미 진행되었습니다. 먼저 그 세트를 초기화하세요",
    "finish your match first, then accept the tournament set": "먼저 매치를 끝낸 뒤 토너먼트 세트를 수락하세요",
    "finish your set first, then accept the tournament set": "먼저 세트를 끝낸 뒤 토너먼트 세트를 수락하세요",
    "you are in a tournament set; finish it first": "토너먼트 세트 중입니다. 먼저 끝내세요",
    "that player is playing a tournament set": "그 플레이어는 토너먼트 세트 중입니다",
    "your tournament set is ready; accept it first": "토너먼트 세트가 준비되었습니다. 먼저 수락하세요",
    "that player has a tournament set to play": "그 플레이어는 진행할 토너먼트 세트가 있습니다",
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
    "Played {games}: {wins} won, {losses} lost, win rate {rate} %": "플레이 {games}: {wins}승 {losses}패, 승률 {rate} %",
    "Ranked {games}, {rate} % won": "Ranked {games}, 승률 {rate} %",
    "Casual {games}, {rate} % won": "일반 {games}, 승률 {rate} %",
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
    "other version": "다른 버전",
    "ranked": "Ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "검색 중... (Ranked 대기 {ranked}명, Quick Match {quick}명)",
    "ping about {ms} ms (estimated; measured directly once you both accept)":
        "핑 약 {ms}ms (추정치, 둘 다 수락하면 직접 측정)",
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
    "Online nobody can pause the fight: Start does not open the pause menu.":
        "온라인에서는 누구도 대전을 일시정지할 수 없습니다. Start로 일시정지 메뉴가 열리지 않습니다.",
    "Intros and the replay after a round are skipped once both players have pressed Start.":
        "인트로와 라운드 후 리플레이는 두 플레이어가 모두 Start를 누르면 건너뜁니다.",
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
    "Nobody else is online right now. Ranked match and Quick match keep looking until someone comes.":
        "지금은 다른 사람이 온라인에 없습니다. Ranked 매치와 Quick Match는 누군가 올 때까지 계속 찾습니다.",
    "No rooms open. Create one: friends can join it and play in turn.":
        "열린 방이 없습니다. 방을 만들면 친구가 들어와 번갈아 플레이할 수 있습니다.",
    "Nobody has a ranked result yet. Win a ranked set to be the first.":
        "아직 Ranked 결과가 있는 사람이 없습니다. Ranked 세트에서 이겨 첫 번째가 되세요.",
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
    "(estimated before you connect)": "(연결 전 추정치)",
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
    # ---- friends (tk_tab.py, tk_views.py)
    "Request": "요청",
    "Friends": "친구",
    "Invite to a match": "매치에 초대",
    "Invite to my room": "내 방에 초대",
    "Invite in {seconds} s": "{seconds}초 후 초대",
    "Remove": "삭제",
    "Invite a friend who is online: one click on their side starts a casual match, or brings them into your room.":
        "접속 중인 친구를 초대하세요: 상대가 한 번 클릭하면 일반 매치가 시작되거나 내 방으로 들어옵니다.",
    "Add a friend": "친구 추가",
    "Send request": "요청 보내기",
    "Their account name. They become your friend when they accept.": "상대의 계정 이름. 상대가 수락하면 친구가 됩니다.",
    "Requests": "요청",
    "Take back": "취소",
    "Invite from a friend": "친구의 초대",
    "invites you to the room “{room}”. Accept to join it; the match starts at once.":
        "님이 방 '{room}'(으)로 초대했습니다. 수락하면 들어가고 매치가 바로 시작됩니다.",
    "invites you to a casual match. Accept to start it.": "님이 일반 매치에 초대했습니다. 수락하면 시작됩니다.",
    "Check the spelling: friends are added by their account name.":
        "철자를 확인하세요: 친구는 계정 이름으로 추가합니다.",
    "in a match": "매치 중",
    "offline": "오프라인",
    "older launcher: no invites": "구버전 런처: 초대 불가",
    "Friends ({count})": "친구 ({count})",
    "offline, last seen {when}": "오프라인 ({when})",
    "Friends need an account. Log in with one to add friends and invite them.":
        "친구 기능은 계정이 필요합니다. 계정으로 로그인하면 친구를 추가하고 초대할 수 있습니다.",
    "This lobby server has no friends list (it needs version 1.1.2 or newer).":
        "이 로비 서버에는 친구 목록이 없습니다 (버전 1.1.2 이상 필요).",
    "wants to be your friend": "친구 요청을 보냈습니다",
    "asked: waiting for an answer": "응답 대기 중",
    "{online} online · {count} of {max}": "접속 {online}명 · {count}/{max}",
    "Your friends see when you are online. Invite one who is online to play.":
        "친구들은 내가 접속 중인지 볼 수 있습니다. 접속 중인 친구를 초대해 함께 플레이하세요.",
    "No friends yet. Add one by account name: they become your friend when they accept.":
        "아직 친구가 없습니다. 계정 이름으로 추가하세요: 상대가 수락하면 친구가 됩니다.",
    "Cancel the invite": "초대 취소",
    "You and {name} are friends now.": "이제 {name}님과 친구입니다.",
    "Friend request sent to {name}. They become your friend when they accept.":
        "{name}님에게 친구 요청을 보냈습니다. 상대가 수락하면 친구가 됩니다.",
    "Request from {name} declined.": "{name}님의 요청을 거절했습니다.",
    "Request to {name} taken back.": "{name}님에게 보낸 요청을 취소했습니다.",
    "Remove friend": "친구 삭제",
    "Remove {name} from your friends?\n\nYou can ask again later; they have to accept again.":
        "{name}님을 친구에서 삭제할까요?\n\n나중에 다시 요청할 수 있지만, 상대가 다시 수락해야 합니다.",
    "{name} is no longer your friend.": "{name}님은 더 이상 친구가 아닙니다.",
    "Select a friend in the list first.": "먼저 목록에서 친구를 고르세요.",
    "Invite sent to {name}; waiting for an answer ({seconds} s)...":
        "{name}님에게 초대를 보냈습니다. 응답 대기 중 ({seconds}초)...",
    "{name} ({rank}) invites you to the room “{room}”": "{name} ({rank})님이 방 '{room}'(으)로 초대했습니다",
    "{name} ({rank}) invites you to a casual match": "{name} ({rank})님이 일반 매치에 초대했습니다",
    "The invite from {name} ran out.": "{name}님의 초대가 만료되었습니다.",
    "The invite from {name} ended.": "{name}님의 초대가 끝났습니다.",
    "{name} declined your invite.": "{name}님이 초대를 거절했습니다.",
    "{name} did not answer your invite.": "{name}님이 초대에 응답하지 않았습니다.",
    "The invite to {name} ended.": "{name}님에게 보낸 초대가 끝났습니다.",
    "{name} wants to be your friend: see the Friends tab.": "{name}님이 친구 요청을 보냈습니다: 친구 탭을 확인하세요.",
    "{name} accepted your friend request.": "{name}님이 친구 요청을 수락했습니다.",
    "{name} declined your friend request.": "{name}님이 친구 요청을 거절했습니다.",

    # ---- launcher/replays_ui.py, launcher/t5dr_launcher.pyw (Replays tab), problem_report.py
    "Replays":
        "리플레이",
    "Every online match is saved here. Watch plays it back in the game exactly as it was played: the same inputs frame by frame, checked against the live match while it plays.":
        "모든 온라인 대전이 여기에 저장됩니다. 보기를 누르면 플레이했던 그대로 게임에서 재생합니다: 같은 입력을 프레임 단위로 재현하고, 재생하는 동안 실제 대전과 대조합니다.",
    "Date":
        "날짜",
    "Fighters":
        "캐릭터",
    "Netcode":
        "넷코드",
    "WATCH":
        "보기",
    "Stop replay":
        "리플레이 중지",
    "Delete":
        "삭제",
    "Open replays folder":
        "리플레이 폴더 열기",
    "While a replay plays: START (Enter) pauses and goes on, SELECT (Tab) ends the replay. A "
    "rematch is played after the matches before it in the same session: it starts from what they "
    "left.":
        "리플레이 재생 중: START(Enter)로 일시정지/계속, SELECT(Tab)로 리플레이를 끝냅니다. "
        "재대전은 같은 세션의 앞선 대전 다음에 재생됩니다: 앞선 대전이 남긴 "
        "상태에서 시작하기 때문입니다.",
    "Save online matches as replays":
        "온라인 대전을 리플레이로 저장",
    "Keep the players' names in replays":
        "리플레이에 플레이어 이름 남기기",
    "Rollback":
        "Rollback",
    "Lockstep":
        "Lockstep",
    "(name not saved)":
        "(이름 저장 안 됨)",
    "{matches} match(es) in {files} file(s) in {folder}":
        "{folder}에 파일 {files}개, 대전 {matches}개",
    "No replays yet. Play an online match: it is saved here.":
        "아직 리플레이가 없습니다. 온라인 대전을 하면 여기에 저장됩니다.",
    "not finished":
        "끝나지 않음",
    "won {mine}-{theirs}":
        "승리 {mine}-{theirs}",
    "lost {mine}-{theirs}":
        "패배 {mine}-{theirs}",
    "Close the running game first (Stop game on the Play tab).":
        "먼저 실행 중인 게임을 닫으세요(오프라인 플레이 탭의 게임 중지).",
    "Build the game first (Build tab).":
        "먼저 게임을 빌드하세요(빌드 탭).",
    "This replay cannot be played: {why}":
        "이 리플레이는 재생할 수 없습니다: {why}",
    "Recorded with another version of the game: it may not play back the same.":
        "다른 버전의 게임으로 녹화되었습니다: 똑같이 재생되지 않을 수 있습니다.",
    "Playing {fighters} ({when})...":
        "{fighters} 재생 중({when})...",
    "The replay ended before the end of the match.":
        "대전이 끝나기 전에 리플레이가 끝났습니다.",
    "Replay over: identical to the live match ({checks} checks, same result).":
        "리플레이 종료: 실제 대전과 똑같습니다(대조 {checks}회, 같은 결과).",
    "Replay over, but it went a different way from frame {frame} on (the game or its version differs from the one that played it).":
        "리플레이 종료, 하지만 {frame} 프레임부터 다르게 진행되었습니다(게임 또는 그 버전이 대전한 것과 다릅니다).",
    "Replay over.":
        "리플레이 종료.",
    "Delete this replay file? It holds {n} match(es) against the same opponent.":
        "이 리플레이 파일을 삭제할까요? 같은 상대와의 대전 {n}개가 들어 있습니다.",
    # ---- lobby/t5lobby/tk_spectate.py, server/spectating.py, launcher Settings (spectating live matches)
    "Spectators":
        "관전",
    "Friends and room visitors may watch my online matches":
        "친구와 내 방 방문자가 내 온라인 매치를 관전할 수 있음",
    "Also my ranked matches":
        "Ranked 매치도 허용",
    "They see the match a few seconds late, in their own game. Only when both players allow it; a "
    "ranked match only when both allow ranked too.":
        "관전자는 자기 게임에서 몇 초 늦게 매치를 봅니다. 두 플레이어가 모두 허용할 때만 가능하며, Ranked 매치는 둘 다 Ranked도 허용해야 합니다.",
    "Watch":
        "관전",
    "Spectating":
        "관전 중",
    "Stop watching":
        "관전 그만두기",
    "Watching":
        "관전 중",
    "Waiting for the match data...":
        "매치 데이터를 기다리는 중...",
    "About {seconds} s behind the live match.":
        "라이브 매치보다 약 {seconds}초 늦음.",
    "It plays from the start of the players' session, a few seconds behind.":
        "플레이어들의 세션 시작부터, 몇 초 늦게 재생됩니다.",
    "Watching {p1} vs {p2}.":
        "{p1} vs {p2} 관전 중.",
    "Spectators watching your match: {count}":
        "내 매치를 관전하는 사람: {count}",
    "The live match is over.":
        "라이브 매치가 끝났습니다.",
    "The players turned spectators off.":
        "플레이어들이 관전을 껐습니다.",
    "The match data stopped coming.":
        "매치 데이터가 더 이상 오지 않습니다.",
    "This session is too long to watch from its start.":
        "이 세션은 너무 길어서 처음부터 관전할 수 없습니다.",
    "Your own match is starting.":
        "내 매치가 시작됩니다.",
    "The match data was damaged.":
        "매치 데이터가 손상되었습니다.",
    "You stopped watching.":
        "관전을 그만두었습니다.",
    "A friend of the players took your place: the match has as many spectators as it can take.":
        "플레이어의 친구가 당신의 자리를 차지했습니다. 이 매치는 관전자 수가 가득 찼습니다.",
    "this launcher cannot watch matches; update it":
        "이 런처는 매치를 관전할 수 없습니다. 업데이트하세요",
    "that match is not being played right now":
        "그 매치는 지금 진행 중이 아닙니다",
    "you are playing in that match":
        "그 매치의 플레이어입니다",
    "you are in a match yourself":
        "이미 매치 중입니다",
    "only friends of a player can watch this match":
        "플레이어의 친구만 이 매치를 관전할 수 있습니다",
    "the players do not allow spectators":
        "플레이어들이 관전을 허용하지 않습니다",
    "neither player can send the match right now":
        "지금은 어느 플레이어도 매치를 보낼 수 없습니다",
    "this match cannot be watched any more":
        "이 매치는 더 이상 관전할 수 없습니다",
    "this match has {count} spectators already":
        "이 매치에는 이미 관전자가 {count}명 있습니다",
    "the server cannot show more matches right now":
        "서버가 지금은 더 많은 매치를 보여줄 수 없습니다",
    "too many matches are watched from your network; stop watching one first":
        "당신의 네트워크에서 관전 중인 매치가 너무 많습니다. 먼저 하나를 그만 보세요",
    "the places for guests at this match are taken; log in with an account to watch":
        "이 매치의 게스트 관전 자리가 찼습니다. 관전하려면 계정으로 로그인하세요",
    "the server cannot show guests more matches right now; log in with an account to watch":
        "서버가 지금은 게스트에게 더 많은 매치를 보여줄 수 없습니다. 관전하려면 계정으로 로그인하세요",
    # firewall hint on the Online tab (t5lobby.fwcheck, tk_tab.fw_hint_text)
    "Firewall":
        "방화벽",
    "How to fix":
        "해결 방법",
    "Windows Firewall blocks {program} on this network. Matches still connect, but some only "
    "through a relay, with more lag.":
        "Windows 방화벽이 이 네트워크에서 {program}을(를) 차단하고 있습니다. 매치는 연결되지만, 일부는 릴레이를 거쳐서만 연결되어 렉이 더 큽니다.",
    "A firewall seems to block T5DR Online's network traffic on this PC.":
        "방화벽이 이 PC에서 T5DR Online의 네트워크 통신을 차단하는 것 같습니다.",
    # patch 0063 (igpu-4k-stall): Internal resolution Auto, integrated-graphics and GPU-bound hints
    "Auto (matches the screen)":
        "자동 (화면에 맞춤)",
    "The game picks the step that matches your screen when it starts, at most 1080p on integrated graphics (they share the processor's memory and power).":
        "게임이 시작할 때 화면에 맞는 단계를 고릅니다. 내장 그래픽에서는 최대 1080p (프로세서와 메모리, 전력을 함께 쓰기 때문).",
    "On this PC: {step}.":
        "이 PC에서: {step}.",
    "{step} on integrated graphics: a busy built-in GPU slows the processor too (they share its power and memory). For 60 fps choose Auto in Settings -> Internal resolution: {better} here.":
        "내장 그래픽에서 {step}: 내장 GPU가 바쁘면 프로세서도 느려집니다 (전력과 메모리를 함께 씁니다). 60 fps를 위해 설정 -> 내부 해상도에서 자동을 고르세요: 여기서는 {better}.",
    "Auto is the default on integrated graphics.":
        "내장 그래픽에서는 자동이 기본입니다.",
    "Your processor ran at {ghz} GHz ({percent} % of its normal speed): set Windows power mode to Best performance.":
        "프로세서가 {ghz} GHz (정상 속도의 {percent} %)로 동작했습니다: Windows 전원 모드를 최고 성능으로 설정하세요.",
    "Extra settings below set {setting}: that wins over this choice.":
        "아래 추가 설정이 {setting}을(를) 정합니다: 이 선택보다 우선합니다.",
    "Fights were slower than 60 fps because of the graphics (GPU-bound): choose a lower Internal resolution in Settings.":
        "그래픽 때문에 대전이 60 fps보다 느렸습니다 (GPU 한계): 설정에서 내부 해상도를 낮추세요.",
    "Fights were slower than 60 fps: the integrated graphics were busy and slowed the processor too. A lower Internal resolution in Settings helps.":
        "대전이 60 fps보다 느렸습니다: 내장 그래픽이 바빠서 프로세서도 느려졌습니다. 설정에서 내부 해상도를 낮추면 도움이 됩니다.",
    # ---- private and community rooms (lobby/t5lobby/tk_rooms.py; the server's messages: i18n_known.py)
    "private rooms need a newer launcher; update it": "비공개 방은 더 새로운 런처가 필요합니다. 런처를 업데이트하세요",
    "only the room's host can do that": "방장만 할 수 있습니다",
    "too many wrong room passwords; try again in {seconds} s": "방 비밀번호가 너무 많이 틀렸습니다. {seconds}초 후에 다시 시도하세요",
    "wrong room password": "방 비밀번호가 틀렸습니다",
    "the room's password changed; try again": "방 비밀번호가 바뀌었습니다. 다시 시도하세요",
    "no room has that invite code": "그 초대 코드를 가진 방이 없습니다",
    "rooms hold 2 to {count} players": "방 인원은 2명에서 {count}명까지입니다",
    "room passwords are 4-64 characters, no space at either end": "방 비밀번호는 4-64자이며 앞뒤에 공백을 넣을 수 없습니다",
    "private and community rooms are casual (unranked)": "비공개 방과 커뮤니티 방은 일반 매치입니다 (Ranked 아님)",
    "you are in that room": "이미 그 방에 있습니다",
    "the room's host removed you from this room": "방장이 당신을 이 방에서 내보냈습니다",
    "the room's host turned away password guesses from your network; ask the host for an invite":
        "방장이 당신의 네트워크에서 오는 비밀번호 시도를 차단했습니다. 방장에게 초대를 요청하세요",
    "only a room with a password counts wrong guesses": "틀린 시도는 비밀번호가 있는 방에서만 집계됩니다",
    "that player is not in your room": "그 플레이어는 내 방에 없습니다",
    "you cannot remove yourself; leave the room instead": "자기 자신은 내보낼 수 없습니다. 대신 방을 나가세요",
    "you can remove that player after their match": "그 플레이어는 매치가 끝난 뒤에 내보낼 수 있습니다",
    "only rooms for 3 or more players take turns": "3명 이상인 방만 차례대로 플레이합니다",
    "you sit out in the room; press Back in line to play again": "방에서 쉬는 중입니다. 다시 하려면 다시 줄 서기를 누르세요",
    "the room picks the next match by itself": "다음 매치는 방이 알아서 정합니다",
    "the room's host removed that player from this room": "방장이 그 플레이어를 이 방에서 내보냈습니다",
    "only the room's players can watch its match": "그 방의 플레이어만 매치를 관전할 수 있습니다",
    "Anybody": "누구나",
    "Back in line": "다시 줄 서기",
    "Back in line: you play when it is your turn.": "다시 줄을 섰습니다. 차례가 되면 플레이합니다.",
    "Copy invite code": "초대 코드 복사",
    "Create a room": "방 만들기",
    "Everyone in turn": "모두 차례대로",
    "Hide the room from the room list": "방 목록에서 방 숨기기",
    "In the room “{name}”: {count}/{size} players, taking turns.": "방 '{name}': {count}/{size}명, 차례대로 플레이합니다.",
    "Invite code": "초대 코드",
    "Line: {names}": "순서: {names}",
    "New invite code": "새 초대 코드",
    "Next: {p1} vs {p2} in {seconds} s": "다음: {p1} vs {p2}, {seconds}초 후",
    "No room selected. Join a room with its invite code (XXXX-XXXX-XXXX):":
        "선택한 방이 없습니다. 초대 코드로 방에 참가하세요 (XXXX-XXXX-XXXX):",
    "Password (4-64 characters):": "비밀번호 (4-64자):",
    "Players in the room:": "방에 있는 플레이어:",
    "Players:": "인원:",
    "Playing: {p1} vs {p2}": "플레이 중: {p1} vs {p2}",
    "Private (invite code)": "비공개 (초대 코드)",
    "Private (password)": "비공개 (비밀번호)",
    "Remove player": "플레이어 내보내기",
    "Remove {name} from the room? They cannot come back into it.": "{name}님을 방에서 내보낼까요? 다시 들어올 수 없습니다.",
    "Removed {name} from the room.": "{name}님을 방에서 내보냈습니다.",
    "Wrong passwords in the last 10 minutes: {count} (networks: {networks})":
        "최근 10분간 틀린 비밀번호: {count}번 (네트워크: {networks})",
    "Turn away the guessers": "추측하는 사람 차단",
    "Networks turned away: {count}. They cannot try passwords on this room any more.":
        "차단한 네트워크: {count}. 그곳에서는 이 방의 비밀번호를 더 이상 시도할 수 없습니다.",
    "Room created.": "방을 만들었습니다.",
    "Room created. Press Copy invite code to see the code you can share.": "방을 만들었습니다. 공유할 코드를 보려면 초대 코드 복사를 누르세요.",
    "Room name (optional):": "방 이름 (선택):",
    "Room password": "방 비밀번호",
    "Room passwords are 4-64 characters, with no space at the start or end.": "방 비밀번호는 4-64자이며 앞뒤에 공백을 넣을 수 없습니다.",
    "Room settings": "방 설정",
    "Room settings saved.": "방 설정을 저장했습니다.",
    "Room settings...": "방 설정...",
    "Sit out": "쉬기",
    "The invite code is in the field next to the button: select it and press Ctrl+C to copy it.":
        "초대 코드는 버튼 옆 칸에 있습니다. 선택한 뒤 Ctrl+C를 눌러 복사하세요.",
    "The room's invite code (XXXX-XXXX-XXXX):": "방의 초대 코드 (XXXX-XXXX-XXXX):",
    "Turns (3 or more players):": "순서 (3명 이상):",
    "Who can join:": "참가 가능:",
    "Winner stays": "이긴 사람 계속",
    "You sit out: your turns are skipped until you press Back in line.": "쉬는 중입니다. 다시 줄 서기를 누를 때까지 차례를 건너뜁니다.",
    "Your room: {name}": "내 방: {name}",
    "hidden": "숨김",
    "invites you to the private room “{room}”. Accept to join it without its password.":
        "님이 비공개 방 '{room}'(으)로 초대했습니다. 수락하면 비밀번호 없이 들어갑니다.",
    "private": "비공개",
    "private (invite code)": "비공개 (초대 코드)",
    "private (password)": "비공개 (비밀번호)",
    "{count}/{size} players": "{count}/{size}명",
    "{name} (host)": "{name} (방장)",
    "{name} (sitting out)": "{name} (쉬는 중)",
    "{name} ({rank}) invites you to the private room “{room}”": "{name} ({rank})님이 비공개 방 '{room}'(으)로 초대했습니다",
    "“{room}” is private. Its password:": "'{room}'은(는) 비공개 방입니다. 비밀번호:",
    "this server has no private rooms": "이 서버에는 비공개 방이 없습니다",
}
