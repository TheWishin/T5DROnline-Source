"""Japanese texts for the launcher and the Online tab (t5lobby/i18n.py).

English text -> Japanese text. The English text is the key, exactly as written in t("...") / N_("...");
the Japanese one keeps the same {placeholders}. Short です / ます UI Japanese with the words players use
(対戦, 戦績, 持ちキャラ, アケコン, 入力遅延). Names from the game and the lobby stay as they are:
Quick Match, Ranked, BUILD GAME, Rematch, Rollback, the character and rank names.

Machine-assisted translation: corrections from players are welcome (docs/ONLINE.md "Languages").
Same keys and groups as i18n_de.py; tests/test_i18n.py and tools/i18n_extract.py check every catalog.
"""

MESSAGES = {
    "OpenRecomp-FGC is open: you can be online in one launcher at a time.":
        "OpenRecomp-FGCが開いています。オンラインにできるランチャーは同時に1つだけです。",
    "Search stopped because the game is running in another launcher. You are still logged in.":
        "別のランチャーでゲームが起動しているため、検索を停止しました。ログインは維持されています。",
    "{count} other player(s) are searching with a different build":
        "異なるビルドで検索中の他のプレイヤーが{count}人います",
    'T5DR Online {latest} is out. Update the launcher (it offers the update when it starts, or press "Check for updates").':
        'T5DR Online {latest} が公開されました。ランチャーを更新してください（起動時に更新が案内されます。または「アップデートを確認」を押してください）。',
    "Intel HD Graphics 4400: graphics device lost": "Intel HD Graphics 4400：グラフィックスデバイスが失われました",
    "Game log: Intel HD Graphics 4400 was selected and the graphics device was lost.":
        "ゲームログ：Intel HD Graphics 4400 が選択され、グラフィックスデバイスが失われました。",
    "private messages are unavailable": "プライベートメッセージを利用できません",
    "private messages: slow down": "プライベートメッセージ：少し待ってください",
    "write a private message first": "先にプライベートメッセージを入力してください",
    "muted is a boolean": "muted は真偽値で指定してください",
    "the private mute list is full": "プライベートメッセージのミュートリストがいっぱいです",
    "private reports: slow down": "プライベート通報：少し待ってください",
    "choose between 1 and 5 private message lines": "プライベートメッセージを1〜5行選択してください",
    "these private message lines cannot be verified; reconnect and try new lines":
        "これらのプライベートメッセージ行を検証できません。再接続して新しい行で試してください",
    "Intel HD Graphics 4400 lost the graphics device (exit code 12). Try the latest graphics driver offered by your PC maker, close GPU-heavy programs and overlays, and choose Lowest (0.5x) Internal resolution. If this PC has another GPU, select it for t5dr.exe in Windows Graphics settings. These steps may not fix it. If it still fails, click Report a problem and send the report to the maintainer.":
        "Intel HD Graphics 4400 のグラフィックスデバイスが失われました（終了コード 12）。PC メーカーが提供する最新のグラフィックスドライバーを試し、GPU 負荷の高いプログラムやオーバーレイを閉じ、内部解像度を最低（0.5x）にしてください。別の GPU がある場合は、Windows のグラフィック設定で t5dr.exe 用に選択してください。これらの手順で解決するとは限りません。引き続き失敗する場合は「問題を報告」をクリックし、レポートを管理者に送ってください。",
    # Private chat.
    "Private messages": "プライベートメッセージ",
    "Private messages ({count})": "プライベートメッセージ ({count})",
    "Message player": "メッセージを送る",
    "Private messages are relayed, not saved by the server. Only lines you select are sent with a report.":
        "プライベートメッセージはサーバーが中継し、保存はしません。通報時は選択した行だけが送信されます。",
    "Message {name}": "{name} にメッセージ",
    "Report selected lines": "選択した行を通報",
    "Select up to {count} lines to report.": "通報する行を {count} 行まで選択してください。",
    "Send selected lines to moderators?": "選択した行をモデレーターに送信しますか？",
    "Report sent to moderators.": "モデレーターに通報を送信しました。",
    "Private chat is unavailable on this server.": "このサーバーではプライベートチャットを利用できません。",
    "Private messages are kept only until you log out or close the launcher.":
        "プライベートメッセージはログアウトするかランチャーを閉じるまでだけ保持されます。",
    "Block {name}? This also leaves any running match against them.":
        "{name} をブロックしますか？この相手との進行中の対戦からも退出します。",
    "DEV": "DEV",
    "Mention a player with @name; press Tab to complete.": "@nameでプレイヤーに呼びかけます。Tabキーで名前を補完できます。",
    # ---- lobby/t5lobby/tk_ranked_chars.py and its profile column headings (1.2.0)
    "Ranked by character": "キャラクター別 Ranked 戦績",
    "No ranked games played.": "Ranked の対戦記録はありません。",
    "Games": "対戦数",
    "Losses": "敗北",
    "Draws": "引き分け",
    # Simultaneous room tables (1.2.0)
    "mode is line or tables": "モードはlineかtablesです",
    "table is 1 to {count}": "対戦台は1から{count}です",
    "simultaneous room tables need a newer launcher; update it": "複数対戦台には新しいランチャーが必要です。更新してください",
    "simultaneous room tables are casual and cannot be training rooms": "複数対戦台はカジュアル専用で、トレーニングルームにはできません",
    "this room does not have simultaneous tables": "このルームには複数対戦台がありません",
    "choose two different players for the table": "対戦台で対戦する別々のプレイヤーを2人選んでください",
    "choose available players and an idle table": "対戦可能なプレイヤーと空いている対戦台を選んでください",
    "you cannot pair these players": "このプレイヤー同士は対戦できません",
    "One match, taking turns": "順番に1試合ずつ",
    "Several matches at once": "複数の試合を同時進行",
    "Room format:": "ルーム形式:",
    "Tables...": "対戦台...",
    "Room tables": "ルームの対戦台",
    "Table {table}: {players}": "対戦台 {table}: {players}",
    "Empty table": "空いている対戦台",
    "Available: {names}": "対戦可能: {names}",
    "Away: {names}": "離席中: {names}",
    "Table:": "対戦台:",
    "Player 1:": "プレイヤー1:",
    "Player 2:": "プレイヤー2:",
    "Set pair": "組み合わせを設定",
    "Watch table": "対戦台を観戦",
    "Select two different available players.": "対戦可能な別々のプレイヤーを2人選んでください。",
    "Select a table.": "対戦台を選んでください。",
    "Available to play": "対戦に参加",
    "You are away until you press Available to play.": "「対戦に参加」を押すまで離席扱いになります。",
    "You are available for a free table.": "空いている対戦台で対戦できる状態です。",
    "this server has no simultaneous room tables": "このサーバーはルーム内の複数対戦台に対応していません",
    # Casual first-to sets (1.2.0)
    "the casual set goes on by itself": "カジュアルセットは自動で続行されます",
    "FT{wins}": "FT{wins}",
    "Casual sets:": "カジュアルセット:",
    "First to:": "先取数:",
    "Older launchers play single games.": "古いランチャーでは単発の対戦になります。",
    "Casual set": "カジュアルセット",
    "Casual set vs {name}": "{name}とのカジュアルセット",
    "CASUAL SET · FT{wins}": "カジュアルセット · FT{wins}",
    "Leave set": "セットを退出",
    "Leave the casual set": "カジュアルセットを退出",
    "Leave this casual set?\n\nCompleted games keep their results. No set penalty or rating change.": "このカジュアルセットを退出しますか？\n\n終了した対戦の結果は残ります。セットのペナルティやレーティングの変動はありません。",
    "The casual set ended {mine}-{theirs}. Completed games keep their results; no rating change.": "カジュアルセットは{mine}-{theirs}で終了しました。終了した対戦の結果は残り、レーティングは変わりません。",
    "first_to: 1, 2, 3, 5 or 10": "first_to: 1、2、3、5、10",
    # ---- launcher/controls_edit.py
    "Removed {sources} from your buttons: that is L2 / R2 at rest on a PlayStation pad, so the game held them all the time. Save to keep this.":
        "ボタンから {sources} を外しました。PlayStation パッドで L2 / R2 を離した状態のため、ゲームではずっと押されたままになっていました。残すには保存してください。",
    "Attack buttons": "攻撃ボタン",
    "Several buttons with one press (macros)": "1回の押下で複数ボタン（マクロ）",
    "Start, Select and the other buttons": "Start、Select などのボタン",
    "Directions": "方向",
    "1 (Left Punch)": "1（左パンチ）",
    "2 (Right Punch)": "2（右パンチ）",
    "3 (Left Kick)": "3（左キック）",
    "4 (Right Kick)": "4（右キック）",
    "Select": "Select",
    "Start / pause": "Start / ポーズ",
    "Down": "下",
    "Left": "左",
    "Up": "上",
    "Right": "右",
    "PlayStation pad, default": "PlayStationパッド（標準）",
    "Xbox pad, default": "Xboxパッド（標準）",
    "X Y A B are 1 2 3 4; bumpers and triggers are L1 R1 L2 R2.":
        "X Y A B が 1 2 3 4、バンパーとトリガーが L1 R1 L2 R2 です。",
    "Square Triangle Cross Circle are 1 2 3 4 (DualShock 4, DualSense and most "
    "PS3/PS4-mode sticks).":
        "□ △ × ○ が 1 2 3 4 です（DualShock 4、DualSense、PS3/PS4モードのアケコンの大半）。",
    "Switch pad, default": "Switchパッド（標準）",
    "Y X B A are 1 2 3 4 (Switch Pro controller, sticks in Switch mode).":
        "Y X B A が 1 2 3 4 です（Switch Proコントローラー、Switchモードのアケコン）。",
    "Xbox-style pad (generic)": "Xbox風パッド（汎用）",
    "A B X Y buttons and LB RB, for Xbox-like pads that Windows does not give to XInput.":
        "A B X Y ボタンと LB RB。Windows が XInput に渡さない Xbox風パッド用です。",
    "8-button stick (Vewlix layout)": "8ボタンアケコン（Vewlix配列）",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: X Y RB LB over A B RT LT.":
        "上段 1 2 [1+2] [1+3]、下段 3 4 [3+4] [2+4]：上が X Y RB LB、下が A B RT LT。",
    "Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: B1 B4 B6 B5 over B2 B3 B8 B7.":
        "上段 1 2 [1+2] [1+3]、下段 3 4 [3+4] [2+4]：上が B1 B4 B6 B5、下が B2 B3 B8 B7。",
    "6-button stick (Noir / Sega Astro)": "6ボタンアケコン（Noir / Sega Astro）",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: X Y RB over A B RT. LB and LT stay L1 and "
    "L2.":
        "上段 1 2 [1+2]、下段 3 4 [3+4]：上が X Y RB、下が A B RT。LB と LT は L1 と L2 のままです。",
    "Top row 1 2 [1+2], bottom row 3 4 [3+4]: B1 B4 B6 over B2 B3 B8. B5 and B7 stay L1 "
    "and L2.":
        "上段 1 2 [1+2]、下段 3 4 [3+4]：上が B1 B4 B6、下が B2 B3 B8。B5 と B7 は L1 と L2 のままです。",
    "Hitbox": "Hitbox",
    "The 8-button layout above. Directions come from the d-pad or the left stick, which "
    "is read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "上の8ボタン配列です。方向は十字キーまたは左スティックから入り、8方向の十字キー入力として読み取ります。左+右（"
        "上+下）の同時押しは打ち消し合います。",
    "The 8-button layout above. Directions come from the hat or the left stick, which is "
    "read as 8-way d-pad presses; left+right (up+down) at once cancel.":
        "上の8ボタン配列です。方向はハットスイッチまたは左スティックから入り、8方向の十字キー入力として読み取ります。"
        "左+右（上+下）の同時押しは打ち消し合います。",
    "The file has {n} settings; the game reads at most {max}.":
        "ファイルの設定は{n}個ですが、ゲームが読むのは最大{max}個です。",
    "The file has {n} sections; the game reads at most {max}.":
        "ファイルのセクションは{n}個ですが、ゲームが読むのは最大{max}個です。",
    "Changed lines of {sections} that would have overridden this ({what}).":
        "これを上書きしていた {sections} の行を変更しました（{what}）。",
    "Lines of your file in other sections still change some buttons.":
        "ファイルの他のセクションにある行が、まだ一部のボタンを変更しています。",
    "Other lines in your file ({sections}) still change this layout.":
        "ファイルの他の行（{sections}）が、まだこの配列を変更しています。",
    "{n} lines removed.": "{n}行を削除しました。",
    # ---- launcher/controls_ui.py
    "DirectInput controller": "DirectInputコントローラー",
    "Xbox pad (XInput)": "Xboxパッド（XInput）",
    "PlayStation pad, read directly": "PlayStationパッド（直接読み取り）",
    "Arrows move; A S on top are 1 2, Z X below are 3 4. Q W are L1 R1, 1 2 are L2 R2, Enter is Start, Tab is Select.": "矢印キーで移動。上の A S が 1 2、下の Z X が 3 4。Q W が L1 R1、1 2 が L2 R2、Enter が Start、Tab が Select。",
    "Arrows move; number pad 4 5 are 1 2, 1 2 are 3 4, 6 is 1+2, 3 is 3+4 (Num Lock on).": "矢印キーで移動。テンキー 4 5 が 1 2、1 2 が 3 4、6 が 1+2、3 が 3+4（NumLock オン）。",
    "Esc (leaves the game)": "Esc（ゲームを終了）",
    "F11 (fullscreen)": "F11（フルスクリーン）",
    "F2 (training overlay)": "F2（トレーニング表示）",
    "Keyboard, second player": "キーボード（2人目）",
    "Keyboard: WASD and U I J K": "キーボード: WASD と U I J K",
    "Keyboard: arrows and A S Z X": "キーボード: 矢印キーと A S Z X",
    "Keyboard: arrows and number pad": "キーボード: 矢印キーとテンキー",
    "Keyboard: pick a game button, then Set selected (or double-click it) and press the key. Esc stops. The game reads the keyboard while its window has the focus.": "キーボード: ゲームのボタンを選び、「選択したボタンを設定」（またはダブルクリック）を押してからキーを押してください。Esc で中止。ゲームはウィンドウにフォーカスがある間キーボードを読みます。",
    "Press only that one key. Esc stops.": "そのキーだけを押してください。Esc で中止。",
    "Press the key for {button}...": "{button} に使うキーを押してください...",
    "The keyboard ([{section}] in controls.ini)": "キーボード（controls.ini の [{section}]）",
    "W A S D move; U I are 1 2, J K are 3 4, O is 1+2, L is 3+4. Y P are L1 R1, H and ; are L2 R2, Enter is Start, Backspace is Select.": "W A S D で移動。U I が 1 2、J K が 3 4、O が 1+2、L が 3+4。Y P が L1 R1、H と ; が L2 R2、Enter が Start、Backspace が Select。",
    "{key} is the game's own key; press another one.": '{key} はゲーム自体が使うキーです。別のキーを押してください。',
    "{source} is also {other} for the second keyboard player.": "{source} は2人目のキーボードプレイヤーでは {other} でもあります。",
    "Controls - T5DR Online": "操作設定 - T5DR Online",
    "Press a button on a controller to pick it, then set its buttons. The game reads the "
    "file when it starts.":
        "コントローラーのボタンを押して選び、ボタンを設定してください。ゲームは起動時にファイルを読み込みます。",
    "Controllers": "コントローラー",
    "Player": "プレイヤー",
    "Controller": "コントローラー",
    "Pressed now": "押下中",
    "Move through this window with the controller": "この画面をコントローラーで操作",
    "Buttons": "ボタン",
    "Game button": "ゲームのボタン",
    "Controller button": "コントローラーのボタン",
    "Set up all buttons": "全ボタンを設定",
    "Set up directions": "方向を設定",
    "Set selected": "選択したボタンを設定",
    "Clear": "クリア",
    "Layout": "配列",
    "Use this layout": "この配列を使う",
    "Reset to defaults": "初期設定に戻す",
    "Your changes apply to": "変更の適用先",
    "Player and directions": "プレイヤーと方向",
    "Automatic": "自動",
    "Player 1": "プレイヤー1",
    "Player 2": "プレイヤー2",
    "8-way d-pad": "8方向十字キー",
    "Analog stick": "アナログスティック",
    "Both cancel (neutral)": "両方打ち消し（ニュートラル）",
    "Up wins (Up+Down is Up)": "上優先（上+下は上）",
    "Last direction wins": "後入力優先",
    "Pass both through": "両方そのまま通す",
    "This controller is": "このコントローラーは",
    "Left stick": "左スティック",
    "Opposite directions": "反対方向の同時入力",
    "Left stick, 8-way d-pad: a hitbox or stick in left-stick mode sends the direction "
    "as a stick; the game then reads it as d-pad presses. Left+Right (or Up+Down) at "
    "once happens on keyboards and hitboxes; the game cannot take both. Stick and "
    "opposite directions belong to the player's port.":
        "左スティック、8方向十字キー：左スティックモードの Hitbox やアケコンは方向をスティックとして送り、ゲームはそれ"
        "を十字キー入力として読み取ります。左+右（または上+下）の同時押しはキーボードや Hitbox で起こり、ゲームは両方"
        "を受け付けられません。スティックと反対方向の設定はプレイヤーのポートごとです。",
    "Skip": "スキップ",
    "Stop": "停止",
    "Save": "保存",
    "Revert": "元に戻す",
    "Close": "閉じる",
    "no controller": "コントローラーなし",
    "Controllers cannot be read on this PC.": "このPCではコントローラーを読み取れません。",
    "No controller found. Plug one in; it shows up here by itself.":
        "コントローラーが見つかりません。接続すると自動でここに表示されます。",
    "switched off in [general]": "[general] でオフ",
    "no free player port": "空きプレイヤーポートなし",
    "No controller chosen": "コントローラー未選択",
    "This controller model ({vid}:{pid})": "このコントローラーの機種（{vid}:{pid}）",
    "This controller model (no USB ID)": "このコントローラーの機種（USB IDなし）",
    "All DirectInput controllers": "すべてのDirectInputコントローラー",
    "All Xbox pads (XInput)": "すべてのXboxパッド（XInput）",
    "Only the controller on player {n}'s port": "プレイヤー{n}のポートのコントローラーのみ",
    "no player": "プレイヤーなし",
    "player {n}": "プレイヤー{n}",
    "yours": "自分で設定",
    "Your own layout": "自分の配列",
    "Player {n}": "プレイヤー{n}",
    "Buttons you set yourself, or a mix. Pick a layout to start from it.":
        "自分で設定したボタン、または混在です。配列を選ぶとそこから始めます。",
    "On the controller: {up} / {down} choose a button, {accept} sets it, {clear} clears "
    "it, {save} saves, {back} closes. The game reads the file when it starts.":
        "コントローラー操作：{up} / {down} でボタンを選択、{accept} で設定、{clear} でクリア、{save} で保存、{back} "
        "で閉じる。ゲームは起動時にファイルを読み込みます。",
    "(no game button)": "（ゲームのボタンなし）",
    "Press a button on a controller first, or pick one in the list.":
        "先にコントローラーのボタンを押すか、リストから選んでください。",
    "Press the button for {button}...": "{button} に使うボタンを押してください...",
    "Press only that one button on the controller.": "コントローラーのそのボタンだけを押してください。",
    "{n} of {total}.": "{n}/{total}。",
    "Wait a few seconds to skip it.": "スキップするには数秒待ってください。",
    "That was several buttons at once ({sources}). Press one button only.":
        "複数のボタンが同時に押されました（{sources}）。ボタンは1つだけ押してください。",
    "{button}: skipped.": "{button}：スキップ。",
    "{button} = {source}.": "{button} = {source}。",
    "{source} was {other}; that one has no button now.": "{source} は {other} でした。そちらには今ボタンがありません。",
    "Stopped.": "停止しました。",
    "{button}: cleared.": "{button}：クリア。",
    "Layout: {name}.": "配列：{name}。",
    "Pick a layout in the list first.": "先にリストから配列を選んでください。",
    "Put {name} back to the default buttons? Your comments and other settings in "
    "controls.ini stay.":
        "{name} を初期設定のボタンに戻しますか？ controls.ini のコメントや他の設定はそのまま残ります。",
    "The part of the file that is for all {kind} controllers has button lines too. Reset "
    "those as well?":
        "ファイル内のすべての {kind} コントローラー向けの部分にもボタンの行があります。それも戻しますか？",
    "Reset to the defaults. Save to keep it.": "初期設定に戻しました。残すには保存してください。",
    "{name} is {player}. Save to keep it.": "{name} は {player} です。残すには保存してください。",
    "controls.ini changed": "controls.ini が変更されました",
    "controls.ini was changed by something else since this screen opened. Overwrite it "
    "with your settings? (The old file is kept as controls.ini.bak.)":
        "この画面を開いた後に controls.ini が別のところで変更されました。自分の設定で上書きしますか？（元のファイルは"
        " controls.ini.bak として残ります。）",
    "Could not save: {error}": "保存できませんでした：{error}",
    "Saved {path}. The game reads it when it starts.": "{path} を保存しました。ゲームは起動時に読み込みます。",
    "The game that is running keeps its old buttons until you start it again.":
        "起動中のゲームは、再起動するまで以前のボタンのままです。",
    "Changes undone.": "変更を元に戻しました。",
    "There are unsaved changes. Save them first, or close with the mouse.":
        "未保存の変更があります。先に保存するか、マウスで閉じてください。",
    "Controls": "操作設定",
    "Save the changes to controls.ini?": "変更を controls.ini に保存しますか？",
    # ---- launcher/core.py
    "Auto (laptops, handhelds, integrated graphics)": "自動（ノートPC、携帯型PC、内蔵グラフィック）",
    "On": "オン",
    "a mobile processor": "モバイル向けプロセッサー",
    "battery saver is on": "Windows のバッテリー節約機能がオン",
    "the Power saver power plan is on": "電源プラン「省電力」が有効",
    "this PC has a battery (laptop or handheld)": "このPCにはバッテリーがある（ノートPCまたは携帯型PC）",
    "Inputs": "入力",
    "Inputs + frame data": "入力 + フレームデータ",
    "Auto (Windows language)": "自動（Windowsの言語）",
    "No package chosen.": "パッケージが選択されていません。",
    "File not found.": "ファイルが見つかりません。",
    "Cannot read the file: {error}": "ファイルを読み込めません：{error}",
    "This is not a PS3 package (.pkg).": "PS3パッケージ（.pkg）ではありません。",
    "{id}  ({size} bytes) -- the supported version": "{id}  ({size} バイト) -- 対応バージョン",
    "{id}  ({size} bytes) -- the European version: it plays offline only for now. Online play for it comes in a later update.":
        "{id}  ({size} バイト) -- 欧州版：今のところオフラインでのみ遊べます。欧州版のオンライン対戦は今後のアップデートで対応します。",
    "checking the game version inside the package…": "パッケージ内のゲームバージョンを確認中…",
    "{id}  ({size} bytes) -- Tekken 5 DR, but not the supported package ({supported}). "
    "The build will most likely refuse it.":
        "{id}  ({size} バイト) -- Tekken 5 DR ですが対応パッケージ（{supported}）ではありません。ビルドはほぼ確実に拒"
        "否します。",
    "{id}  ({size} bytes) -- not Tekken 5 DR Online ({title_id}).":
        "{id}  ({size} バイト) -- Tekken 5 DR Online ではありません（{title_id}）。",
    "No license chosen.": "ライセンスが選択されていません。",
    "Not a PS3 license: a .rap file is exactly 16 bytes.":
        "PS3のライセンスではありません。.rap ファイルはちょうど16バイトです。",
    "{name} -- matches the supported package": "{name} -- 対応パッケージと一致",
    "{name} -- matches the package": "{name} -- パッケージと一致",
    "{name} -- the name does not match the package's content ID; it may be the wrong "
    "license.":
        "{name} -- 名前がパッケージのコンテンツIDと一致しません。違うライセンスかもしれません。",
    "The output folder": "出力フォルダー",
    "This folder": "このフォルダー",
    "{label} has a long path ({bytes} bytes). Windows allows only {max} characters for a "
    "file path, and the build writes files about {room} characters deeper. Move the "
    "folder to a short path, for example {example}.":
        "{label}のパスが長すぎます（{bytes} バイト）。Windows のファイルパスは {max} 文字までで、ビルドはさらに約 "
        "{room} 文字深くファイルを書き込みます。フォルダーを短いパスに移動してください（例：{example}）。",
    "This folder is inside OneDrive. OneDrive would upload about 1 GB of game data and "
    "can lock files while the game is built. Move the folder out of OneDrive, for "
    "example to {example}.":
        "このフォルダーは OneDrive の中にあります。OneDrive が約1GBのゲームデータをアップロードし、ビルド中にファイル"
        "をロックすることがあります。フォルダーを OneDrive の外に移動してください（例：{example}）。",
    "This folder is in Program Files, where Windows does not let programs write. Move it "
    "to a folder of your own, for example {example}.":
        "このフォルダーは Program Files の中にあり、Windows がプログラムの書き込みを許可しません。自分のフォルダーに移"
        "動してください（例：{example}）。",
    "Windows does not let the launcher write into this folder. Move it to a folder of "
    "your own, for example {example}.":
        "Windows がランチャーにこのフォルダーへの書き込みを許可していません。自分のフォルダーに移動してください（例："
        "{example}）。",
    "This folder is on a network share. Building and playing from there is slow and was "
    "not tested; copy it to a local drive.":
        "このフォルダーはネットワーク共有上にあります。そこからのビルドとプレイは遅く、テストもされていません。ローカ"
        "ルドライブにコピーしてください。",
    "The game is not built yet. Open the Build tab, choose your .pkg and .rap, press "
    "BUILD GAME.":
        "ゲームはまだビルドされていません。ビルドタブを開き、.pkg と .rap を選んで BUILD GAME を押してください。",
    "t5dr.exe is there but the game data is missing. Build again.":
        "t5dr.exe はありますが、ゲームデータがありません。もう一度ビルドしてください。",
    "The decrypted program has SHA-1 {sha}..., not the supported version. Build again "
    "from the supported package.":
        "復号したプログラムの SHA-1 は {sha}... で、対応バージョンではありません。対応パッケージからビルドし直してくだ"
        "さい。",
    "Build the game once (about 2 minutes): this version of the launcher changes the "
    "game code. Click BUILD GAME. Your unpacked game and saves are kept; only the code "
    "is translated and compiled again.":
        "ゲームを一度ビルドしてください（約2分）：このバージョンのランチャーはゲームコードを変更します。BUILD GAME "
        "をクリックしてください。展開済みのゲームとセーブはそのまま残り、コードだけを変換・コンパイルし直します。",
    "Ready: {title_id} v{version}, program SHA-1 {sha}... verified, built {when}.":
        "準備完了：{title_id} v{version}、プログラム SHA-1 {sha}... 確認済み、ビルド {when}。",
    "Check & decrypt": "確認と復号",
    "Key data": "鍵データ",
    "Recompiler": "リコンパイラー",
    "Unpack": "展開",
    "Compile": "コンパイル",
    "Game files": "ゲームファイル",
    "Sound core": "サウンドコア",
    "Shaders": "シェーダー",
    "Translate code": "コード変換",
    "The translation step has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, close other programs, press Cancel and then BUILD GAME again; build.log "
    "has the details.":
        "「コード変換」ステップが {minutes} 分間何も出力していません。遅いPCや負荷の高いPCではまだ処理中の場合がありま"
        "す。変化がなければ他のプログラムを閉じ、キャンセルを押してからもう一度 BUILD GAME を押してください。詳細は "
        "build.log にあります。",
    "The graphics card stopped working for the game (the driver crashed, was reset or "
    "updated). Start the game again. If it happens again, update the graphics driver.":
        "グラフィックカードがゲームで動作しなくなりました（ドライバーのクラッシュ、リセット、または更新）。ゲームをも"
        "う一度起動してください。再発する場合はグラフィックドライバーを更新してください。",
    "This PC's graphics card or driver cannot run Direct3D 12. Install the newest "
    "graphics driver from AMD, Intel or NVIDIA.":
        "このPCのグラフィックカードまたはドライバーは Direct3D 12 を実行できません。AMD、Intel、NVIDIA の最新グラフィ"
        "ックドライバーをインストールしてください。",
    "This processor is too old for the game: it lacks the SSE4.1 instructions "
    "(processors from about 2008 on have them).":
        "このプロセッサーはゲームには古すぎます。SSE4.1 命令がありません（2008年ごろ以降のプロセッサーにはあります）。",
    "The game was built on a PC with a newer processor (AVX2). Press BUILD GAME to build "
    "it again for this PC; your saves are kept.":
        "ゲームはより新しいプロセッサー（AVX2）のPCでビルドされています。BUILD GAME を押してこのPC用にビルドし直してく"
        "ださい。セーブは残ります。",
    "t5dr_game.dll could not be loaded (missing or blocked). Press BUILD GAME again, and "
    "look in the antivirus quarantine.":
        "t5dr_game.dll を読み込めませんでした（見つからないか、ブロックされています）。もう一度 BUILD GAME を押し、ウ"
        "イルス対策ソフトの隔離を確認してください。",
    "The game could not get back to character select after the last match and closed "
    "itself. It starts again for your next match.":
        "前の対戦の後、ゲームがキャラクター選択に戻れず自動で終了しました。次の対戦で再び起動します。",
    "The game stopped after a crash (exit code {code}). The game log has the details.":
        "ゲームがクラッシュで停止しました（終了コード {code}）。詳細はゲームログにあります。",
    "The game stopped (exit code {code}). The game log has the details.":
        "ゲームが停止しました（終了コード {code}）。詳細はゲームログにあります。",
    "t5dr.exe is not built yet": "t5dr.exe はまだビルドされていません",
    "Lowest (0.5x)": "最低 (0.5x)",
    "Lower (0.75x)": "低 (0.75x)",
    "Native (720p)": "ネイティブ (720p)",
    "1080p (1.5x)": "1080p (1.5x)",
    "1440p (2x)": "1440p (2x)",
    "4K (3x)": "4K (3x)",
    "The 3D scene at half size (a quarter of its pixels); HUD and text stay sharp. "
    "For integrated graphics and old laptops.":
        "3Dシーンを半分のサイズで描画します（ピクセル数は1/4）。HUDと文字はくっきりのままです。内蔵グラフィックや古い"
        "ノートPC向け。",
    "The 3D scene at 3/4 size (about half of its pixels); HUD and text stay sharp. "
    "For weak graphics cards.":
        "3Dシーンを3/4のサイズで描画します（ピクセル数は約半分）。HUDと文字はくっきりのままです。性能の低いグラフィッ"
        "クカード向け。",
    "The PS3's 1280 x 720. Light on any graphics card; the picture is scaled to your window.":
        "PS3と同じ 1280 x 720。どのグラフィックカードでも軽く、画面はウィンドウに合わせて拡大されます。",
    "1920 x 1080: 2.25x the pixels of Native. Sharp on Full HD screens. "
    "If fights drop below 60 fps, go one step down.":
        "1920 x 1080：ネイティブの2.25倍のピクセル。フルHD画面でくっきり。対戦が60fpsを下回るなら1段階下げてください。",
    "2560 x 1440: 4x the pixels of Native. For strong graphics cards. "
    "If fights drop below 60 fps, go one step down.":
        "2560 x 1440：ネイティブの4倍のピクセル。高性能グラフィックカード向け。対戦が60fpsを下回るなら1段階下げてくだ"
        "さい。",
    "3840 x 2160: 9x the pixels of Native. For very strong graphics cards "
    "(an RTX 3090 needs 1-2 ms of a 16.7 ms frame). If fights drop below 60 fps, go one step down.":
        "3840 x 2160：ネイティブの9倍のピクセル。非常に高性能なグラフィックカード向け（RTX 3090 で16.7msのフレーム中"
        "1-2ms）。対戦が60fpsを下回るなら1段階下げてください。",
    "Auto (by ping)": "自動（Pingで決定）",
    "Window, 1280 x 720 (native; larger with Windows display scaling)":
        "ウィンドウ 1280 x 720（ネイティブ、Windowsの拡大率で大きくなります）",
    "Window, 1920 x 1080": "ウィンドウ 1920 x 1080",
    "Window, 2560 x 1440": "ウィンドウ 2560 x 1440",
    "Maximized window": "最大化ウィンドウ",
    "Borderless fullscreen (Alt+Enter or F11 switches in the game)":
        "ボーダーレス全画面（ゲーム中に Alt+Enter または F11 で切り替え）",
    # Display: own window size, Picture format (ps3recomp patch 0107)
    'pixels': 'ピクセル',
    'Window, my own size:':
        'ウィンドウ（サイズを指定）:',
    'Width {wmin}-{wmax} and height {hmin}-{hmax}, whole numbers. Until then the game uses {w} x {h}.':
        '幅 {wmin}～{wmax}、高さ {hmin}～{hmax} の整数で入力してください。それまではゲームは {w} x {h} を使います。',
    'Picture format':
        '画面の形',
    'Whole picture (16:9, black bars on other screens; default)':
        '全体を表示（16:9、他の画面では黒帯あり・標準）',
    'Fill the screen (no bars; cuts the left and right edges)':
        '画面いっぱい（黒帯なし・左右の端が切れる）',
    'Stretch to the screen (no bars; fighters look wider)':
        '画面に合わせて引き伸ばす（黒帯なし・キャラが横に広がる）',
    '4:3 (the middle of the picture, bars left and right)':
        '4:3（画面の中央、左右に黒帯）',
    'True 4:3 (the game draws for a 4:3 screen; offline only, online the middle of the picture)':
        '本来の4:3（ゲームが4:3画面向けに描画。オフラインのみ、オンラインでは画面の中央）',
    'For screens that are not 16:9, such as 16:10 and 3:2 laptops. The game draws 16:9, so Fill cuts a little off the sides and Stretch widens everything. Only your picture changes: online, both players can choose differently.':
        '16:10 や 3:2 のノートPCなど、16:9 ではない画面向けです。ゲームは 16:9 で描画するので、「画面いっぱい」は左右が少し切れ、「引き伸ばす」は全体が横に広がります。変わるのは自分の画面だけなので、オンラインでは2人が別々に選べます。',
    # ---- launcher/online.py
    "Online play": "オンラインプレイ",
    "The lobby files (lobby/t5lobby) are missing from this copy of the launcher, so "
    "online play is not available.\n\n({reason})":
        "このランチャーにはロビーのファイル（lobby/t5lobby）がないため、オンラインプレイは使えません。\n\n({reason})",
    # ---- launcher/problem_report_ui.py
    # Report a problem: Send to the developer (problem_report_ui.py, report_send.py); one Discord server
    'New launcher':
        '新しいランチャー',
    'Optional launcher with Tekken 5 DR and Tekken 4 in one window; this launcher keeps working.':
        'Tekken 5 DR と Tekken 4 を 1 つのウィンドウで使える任意のランチャーです。このランチャーもそのまま使えます。',
    'Contact (optional, e.g. your Discord name):':
        '連絡先（任意、例: Discord の名前）:',
    'Enough reports from this PC for today. Save the zip and send it yourself.':
        '今日はこの PC からのレポートが上限に達しました。zip を保存して自分で送ってください。',
    'Making the report and sending it...':
        'レポートを作成して送信しています...',
    'OpenRecomp-FGC Discord':
        'OpenRecomp-FGC Discord',
    'Press Send: your logs and settings go straight to the developer. Or save the zip and send it yourself.':
        '送信を押すと、ログと設定が開発者に直接届きます。zip を保存して自分で送ることもできます。',
    'Questions? Ask the players in the OpenRecomp-FGC Discord: {url}':
        '質問は OpenRecomp-FGC Discord のプレイヤーに聞いてください: {url}',
    'Save on the Desktop instead':
        '代わりにデスクトップに保存',
    'Send to the developer':
        '開発者に送信',
    'Sending... {done} of {total}':
        '送信中... {done} / {total}',
    'Sends your logs to the developer with your lobby name. No game files, no keys, no passwords.':
        'ログをロビー名と一緒に開発者へ送ります。ゲームファイル、キー、パスワードは含みません。',
    'Sent, thanks (report #{id})':
        '送信しました。ありがとうございます（レポート #{id}）',
    'The developer has your report ({size}). If you asked for an answer, it comes to the contact you gave.':
        '開発者がレポートを受け取りました（{size}）。返事を希望した場合は、入力した連絡先に届きます。',
    'The report could not be sent: {error}':
        'レポートを送信できませんでした: {error}',
    'The report is too big to send. Save the zip and send it yourself.':
        'レポートが大きすぎて送信できません。zip を保存して自分で送ってください。',
    'The server cannot take reports yet. Save the zip and send it yourself.':
        'サーバーはまだレポートを受け付けていません。zip を保存して自分で送ってください。',
    'The server cannot take reports yet. Save the zip and send it yourself: to the person who gave you the game, or attach it to an issue.':
        'サーバーはまだレポートを受け付けていません。zip を保存して自分で送ってください。ゲームをくれた人に送るか、issue に添付してください。',
    'The server could not be reached. Check the internet connection, or save the zip.':
        'サーバーに接続できませんでした。インターネット接続を確認するか、zip を保存してください。',
    "Before the zip is made, your Windows user name in file paths becomes <user>, internet IP addresses become <ip> (addresses of your own network stay), lobby player names (yours and your opponents') become <player>, and passwords, tokens and match keys are left out. Your game files, keys, .pkg and .rap are never included.":
        'zip を作る前に、ファイルパス内の Windows ユーザー名は <user>、インターネットの IP アドレスは <ip>（自分のネットワークのアドレスはそのまま）、ロビーのプレイヤー名（自分と対戦相手）は <player> に置き換えられ、パスワード、トークン、対戦キーは除外されます。ゲームファイル、キー、.pkg、.rap が含まれることはありません。',
    "{count} bytes": "{count} バイト",
    "Report a problem": "問題を報告",
    "This makes one zip file on your Desktop with the logs and settings that help to "
    "find the problem. Send the zip to the person who gave you the game, or attach it to "
    "an issue.":
        "問題の調査に役立つログと設定をまとめた zip ファイルをデスクトップに1つ作ります。zip をゲームをくれた人に送る"
        "か、Issue に添付してください。",
    "What happened? (optional)": "何が起きましたか？（任意）",
    "What goes into the zip": "zip に入るもの",
    "Nothing found yet: no game log, no build log.": "まだ何も見つかりません：ゲームログもビルドログもありません。",
    "Could not look at the files: {error}": "ファイルを確認できませんでした：{error}",
    "Save report on the Desktop": "デスクトップにレポートを保存",
    "Cancel": "キャンセル",
    "About {size} before it is packed (a zip is smaller).": "圧縮前で約 {size}（zip はもっと小さくなります）。",
    "About {size}; the limit is {limit}, so the biggest logs are shortened in the "
    "middle.":
        "約 {size}。上限は {limit} なので、最も大きいログは中ほどを省略します。",
    "Making the report...": "レポートを作成中...",
    "The report could not be made: {error}": "レポートを作成できませんでした：{error}",
    "Report saved": "レポートを保存しました",
    "{size}. Its folder is open.": "{size}。保存先フォルダーを開きました。",
    "Send this zip to the person who gave you the game, or attach it to an issue at "
    "{url}.":
        "この zip をゲームをくれた人に送るか、{url} の Issue に添付してください。",
    "Send this zip to the person who gave you the game.": "この zip をゲームをくれた人に送ってください。",
    "(shortened in the middle)": "（中ほどを省略）",
    "{name}   left out: {reason}": "{name}   除外：{reason}",
    "Removed from the text files: {user} user or PC names, {ip} IP addresses, {secret} "
    "passwords, tokens or keys, {email} e-mail addresses.":
        "テキストファイルから削除：ユーザー名・PC名 {user} 件、IPアドレス {ip} 件、パスワード・トークン・キー "
        "{secret} 件、メールアドレス {email} 件。",
    "Open folder": "フォルダーを開く",
    # ---- launcher/t5dr_launcher.pyw
    "Discord": "Discord",
    "Show what I play in my Discord status (Rich Presence)":
        "Discord のステータスにプレイ中の内容を表示（Rich Presence）",
    "\"In lobby\", \"Searching ranked\" or your match (fighters, ranked set score) with a timer, through the "
    "Discord app on this PC. Without Discord running nothing happens.":
        "「ロビーで待機中」「Ranked 検索中」、または対戦（キャラクター、Ranked セットのスコア）を経過時間つきで、この"
        "PCの Discord アプリを通じて表示します。Discord が起動していなければ何も起きません。",
    "Power saving (laptops, handhelds)": "省電力（ノートPC、携帯型PC）",
    "No busy waiting and fewer worker threads: the processor stays cooler and keeps its speed, so the game "
    "holds 60 fps longer. The game itself is the same, online too.":
        "ビジーウェイトをやめ、ワーカースレッドを減らします：プロセッサーの温度が上がりにくく速度を保てるので、ゲーム"
        "が60fpsを長く維持できます。ゲーム自体は同じで、オンラインでも変わりません。",
    "On for this PC.": "このPCではオン。",
    "Off.": "オフ。",
    "Auto: on for this PC -- {reason}.": "自動：このPCではオン -- {reason}。",
    "Auto: off for this PC (no battery, no mobile processor); the game turns it on by itself if it runs on "
    "integrated graphics.":
        "自動：このPCではオフ（バッテリーなし、モバイル向けプロセッサーではない）。内蔵グラフィックで動く場合はゲーム"
        "が自動でオンにします。",
    "Power saving is on.": "省電力がオンです。",
    "A": "A",
    "Left punch (1)": "左パンチ (1)",
    "Square": "□",
    "X": "X",
    "Right punch (2)": "右パンチ (2)",
    "S": "S",
    "Triangle": "△",
    "Y": "Y",
    "Cross": "×",
    "Left kick (3)": "左キック (3)",
    "Z": "Z",
    "B": "B",
    "Circle": "○",
    "Right kick (4)": "右キック (4)",
    "Arrow keys": "矢印キー",
    "D-pad, left stick": "十字キー、左スティック",
    "Move / menus": "移動 / メニュー",
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
    "Quit the game": "ゲーム終了",
    "A / B": "A / B",
    "Cross / Circle": "× / ○",
    "Mouse": "マウス",
    "Online tab: accept / decline": "オンラインタブ：受ける / 断る",
    "native Windows build  ·  launcher {version}": "Windows ネイティブ版  ·  ランチャー {version}",
    "Build": "ビルド",
    "Play offline": "オフラインプレイ",
    "Settings": "設定",
    "Play online": "オンラインプレイ",
    "Output: {folder}": "出力先：{folder}",
    "Your game": "あなたのゲーム",
    "Package (.pkg)": "パッケージ (.pkg)",
    "License (.rap)": "ライセンス (.rap)",
    "Browse…": "参照…",
    "Supported: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version 01.00 (online and offline), "
    "and TEKKEN 5 DARK RESURRECTION, PS3 PSN (Europe), NPEA00019 version 01.00 (offline only for now) -- the "
    "package file and the license (.rap) from your own account. Nothing leaves this PC.":
        "対応：Tekken 5: Dark Resurrection Online、PS3 PSN（北米）、NPUB30009 バージョン 01.00（オンラインとオフライン）、および TEKKEN 5 DARK RESURRECTION、PS3 PSN（欧州）、NPEA00019 バージョン 01.00（現在はオフラインのみ） -- 自分のアカウントのパッケージファイルとライセンス（.rap）。このPCの外には何も送られません。",
    "Build tools on this PC": "このPCのビルドツール",
    "Needed": "必要",
    "Found": "検出",
    "Checking…": "確認中…",
    "Details": "詳細",
    "Check again": "再確認",
    "Install missing…": "不足分をインストール…",
    "Press BUILD GAME. It takes a few minutes; the game data stays in this folder.":
        "BUILD GAME を押してください。数分かかります。ゲームデータはこのフォルダーに残ります。",
    "BUILD GAME": "BUILD GAME",
    "Redo every step": "全ステップをやり直す",
    "Preparing shaders... (Skip)": "シェーダーを準備中...（スキップ）",
    "Your opponent left the match -- back to the lobby": "対戦相手が退出しました -- ロビーに戻ります",
    "Match over -- back to the lobby": "対戦終了 -- ロビーに戻ります",
    "Skip warm-up": "ウォームアップをスキップ",
    "Skipping…": "スキップ中…",
    "Keep the PC responsive (slower)": "PCの操作性を優先（遅くなります）",
    "Open build.log": "build.log を開く",
    "Report a problem...": "問題を報告...",
    "Check my problem": "問題をチェック",
    "Check my problem...": "問題をチェック...",
    "Looking…": "確認中…",
    "No known problem found.": "既知の問題は見つかりませんでした。",
    "If something still goes wrong, \"Report a problem...\" makes one zip with your logs to send to whoever helps you.":
        "それでも問題が続く場合は、「問題を報告...」でログをまとめたzipを作り、手伝ってくれる人に送ってください。",
    "Problem": "問題",
    "Note": "注意",
    "Help": "ヘルプ",
    "The launcher looks in this PC's logs and settings for the problems other players had, and says how to fix them. Nothing is changed and nothing is sent.":
        "ランチャーがこのPCのログと設定から、他のプレイヤーに起きた問題を探し、直し方を表示します。何も変更せず、何も送信しません。",
    "Your game package is version {version}": "ゲームのパッケージがバージョン{version}です",
    "The port works only with version {supported} of the game: TEKKEN 5 DARK RESURRECTION ONLINE, US PSN (NPUB30009), a .pkg of {size} bytes, with its license {rap}; or TEKKEN 5 DARK RESURRECTION, European PSN (NPEA00019), a .pkg of {eu_size} bytes, with its license {eu_rap} (offline only for now). Version {version} cannot be used, whatever the license. Choose a {supported} package on the Build tab and press BUILD GAME.":
        "このポートはゲームのバージョン{supported}でのみ動作します：TEKKEN 5 DARK RESURRECTION ONLINE、北米PSN（NPUB30009）、{size}バイトの.pkgとそのライセンス{rap}；またはTEKKEN 5 DARK RESURRECTION、欧州PSN（NPEA00019）、{eu_size}バイトの.pkgとそのライセンス{eu_rap}（今はオフラインのみ）。バージョン{version}はどのライセンスでも使えません。ビルドタブで{supported}のパッケージを選び、BUILD GAMEを押してください。",
    "build.log: the package says version {version}.": "build.log：パッケージのバージョンは{version}です。",
    "Unpacking the game ran out of memory": "ゲームの展開中にメモリが不足しました",
    "Close other programs (browser, games, launchers) and press BUILD GAME again; since 1.1.5 the launcher unpacks the game in small pieces. If it fails again, check that Windows has a page file (System > About > Advanced system settings > Performance > Virtual memory: automatic).":
        "他のプログラム（ブラウザー、ゲーム、ランチャー）を閉じて、もう一度BUILD GAMEを押してください。1.1.5からランチャーはゲームを小さな単位で展開します。それでも失敗する場合は、Windowsにページファイルがあるか確認してください（システム > バージョン情報 > システムの詳細設定 > パフォーマンス > 仮想メモリ：自動）。",
    "build.log: the computer ran out of memory while the game data was unpacked.":
        "build.log：ゲームデータの展開中にメモリが足りなくなりました。",
    "The game package looks damaged or incomplete": "ゲームのパッケージが壊れているか不完全です",
    "Download the package again (it must be {size} bytes), choose it on the Build tab, tick \"Redo every step\" and press BUILD GAME.":
        "パッケージをもう一度ダウンロードし（{size}バイトである必要があります）、ビルドタブで選んで「全ステップをやり直す」にチェックを入れ、BUILD GAMEを押してください。",
    "build.log: the package could not be read to the end or not decrypted.": "build.log：パッケージを最後まで読めなかったか、復号できませんでした。",
    "The game says its data is damaged": "ゲームがデータの破損を報告しています",
    "On the Build tab tick \"Redo every step\" and press BUILD GAME: it unpacks the game again. If the message comes back, download the package again (it must be {size} bytes).":
        "ビルドタブで「全ステップをやり直す」にチェックを入れてBUILD GAMEを押すと、ゲームが展開し直されます。それでもメッセージが出る場合は、パッケージをもう一度ダウンロードしてください（{size}バイトである必要があります）。",
    "Game log: the game showed the message \"{message}\".": "ゲームログ：ゲームが「{message}」というメッセージを表示しました。",
    "Your graphics card is an older model": "グラフィックカードが古いモデルです",
    "{gpu} is a Direct3D 12 card of the oldest kind (resource binding tier 1: GeForce cards with a Fermi chip, among them some GT 730 models, and older Intel graphics). The game's graphics take several times longer on it than on later cards, whatever the processor: fights can stay below 30 frames per second, and a lower Internal resolution helps only a little. Later cards (a GT 730 with a Kepler chip, GTX 750, Radeon HD 7000 and newer) run the game at full speed.":
        "{gpu}は最も古い種類のDirect3D 12カードです（resource binding tier 1：Fermiチップの GeForce、一部のGT 730を含む、および古いIntelグラフィックス）。プロセッサーに関係なく、ゲームのグラフィックスは新しいカードの数倍の時間がかかります。対戦が30フレーム毎秒を下回ることがあり、内部解像度を下げてもあまり効果はありません。それ以降のカード（KeplerチップのGT 730、GTX 750、Radeon HD 7000以降）ならフルスピードで動きます。",
    "Game log: {gpu}, resource binding tier {tier}.": "ゲームログ：{gpu}、resource binding tier {tier}。",
    "Your processor has {cores} cores": "プロセッサーのコア数は{cores}です",
    "The game is made for 4 cores; on {cores} it can stay below 60 frames per second in fights (an i3-3240 reached about 20). Close other programs while you play, keep Windows' power plan on Balanced or High performance, and see \"Low frame rate\" in the help.":
        "このゲームは4コア向けです。{cores}コアでは対戦中に60フレーム毎秒を下回ることがあります（i3-3240では約20）。プレイ中は他のプログラムを閉じ、Windowsの電源プランを「バランス」か「高パフォーマンス」にして、ヘルプの「Low frame rate」を見てください。",
    "This PC: {cores} cores, {logical} logical processors.": "このPC：{cores}コア、論理プロセッサー{logical}個。",
    "The launcher runs under Wine or Proton": "ランチャーがWineまたはProtonで動いています",
    "That works, with a few known differences: since 1.1.5 the launcher sets the safe graphics defaults for Wine by itself. A dark blue or black game window (sound playing) means the Proton build does not suit the game: try another one (Proton Experimental, proton-cachyos-slr). See \"Linux and Steam Deck\" in the help.":
        "動作しますが、いくつか既知の違いがあります。1.1.5からランチャーがWine向けの安全なグラフィックス設定を自動で使います。ゲーム画面が濃い青や黒のまま（音は出る）なら、そのProtonビルドはゲームに合っていません。別のもの（Proton Experimental、proton-cachyos-slr）を試してください。ヘルプの「Linux and Steam Deck」を見てください。",
    "This PC: {wine}.": "このPC：{wine}。",
    "The game's graphics did not start under Wine or Proton": "WineまたはProtonでゲームのグラフィックが起動しませんでした",
    "Try another Proton build first (in Steam: the game's Properties > Compatibility: Proton Experimental, GE-Proton or proton-cachyos). If that does not help, install Microsoft's shader compiler into the game's prefix: protontricks <the game's Steam id> d3dcompiler_47 (plain Wine: winetricks d3dcompiler_47). Plain Wine also needs vkd3d-proton for Direct3D 12. See \"Linux and Steam Deck\" in the help.":
        "まず別のProtonを試してください（Steamでゲームのプロパティ > 互換性：Proton Experimental、GE-Proton、proton-cachyos）。それでも直らない場合は、MicrosoftのシェーダーコンパイラーをゲームのPrefixに入れてください：protontricks <ゲームのSteam ID> d3dcompiler_47（Steamを使わないWine：winetricks d3dcompiler_47）。Steamを使わないWineではDirect3D 12のためにvkd3d-protonも必要です。ヘルプの「Linux and Steam Deck」を参照してください。",
    "Game log: {line}": "ゲームのログ：{line}",
    "Windows Firewall blocks the game": "Windowsファイアウォールがゲームをブロックしています",
    "Online matches then often go through a relay (more lag) or do not connect. Open Windows Security > Firewall & network protection > Allow an app through firewall, and allow t5dr.exe (in {folder}) for private and public networks; or remove the block rule for it there.":
        "その場合、オンライン対戦はリレー経由（遅延が増える）になるか、つながりません。Windows セキュリティ > ファイアウォールとネットワーク保護 > ファイアウォールによるアプリケーションの許可 を開き、t5dr.exe（{folder}内）をプライベートとパブリックのネットワークで許可するか、そこにあるブロックのルールを削除してください。",
    "Windows Firewall: a block rule or \"Block all incoming connections\" for t5dr.exe.":
        "Windowsファイアウォール：t5dr.exeのブロックルール、または「すべての着信接続をブロック」。",
    "Checking the build…": "ビルドを確認中…",
    "Your name (shown in the game)": "名前（ゲーム内に表示）",
    "PLAY OFFLINE": "オフラインプレイ",
    "Arcade, Versus, Practice and the other modes on this PC. To play against people over the "
    "internet, use the":
        "Arcade、Versus、Practice など、このPCで遊ぶモードです。インターネット対戦はこちら：",
    "Online tab": "オンラインタブ",
    "Stop game": "ゲームを停止",
    "Open newest game log": "最新のゲームログを開く",
    "Open saves folder": "セーブフォルダーを開く",
    "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers "
    "both work; see Settings for the keys. Esc closes the game. START skips the intro "
    "movie.":
        "ゲームは専用ウィンドウ（DirectX 12）で開きます。キーボードとXbox風コントローラーの両方が使えます。キー配置は"
        "設定を参照してください。Esc でゲームを閉じ、START でオープニング映像をスキップします。",
    "Display": "表示",
    "The picture is scaled to the window; how sharp it is depends on Internal resolution. "
    "You can also drag the window's edges. Alt+Enter or F11 switches borderless fullscreen "
    "in the game.":
        "画面はウィンドウに合わせて拡大縮小され、鮮明さは内部解像度で決まります。ウィンドウの端をドラッグしてサイズを"
        "変えることもできます。ゲーム中は Alt+Enter または F11 でボーダーレス全画面に切り替わります。",
    "Unlocks": "アンロック",
    "Unlock all stages (the Tekken 5 stages, without clearing Arcade)":
        "全ステージをアンロック（Tekken 5 のステージ、Arcade をクリアしなくても）",
    "Unlock Jinpachi and Random select (without clearing Arcade)":
        "Jinpachi と Random セレクトをアンロック（Arcade をクリアしなくても）",
    "Unlock all customization items (free in the item shop)":
        "全カスタマイズアイテムをアンロック（ITEM SHOP で無料）",
    "Offline only (Arcade, VS, Practice and the rest). Your save is not changed; items you take for free "
    "stay yours (the save is backed up first, in save-backups). Online, both players always get the "
    "same stages; Jinpachi and Random are there in casual matches and rooms, not in ranked.":
        "オフライン専用です（Arcade、VS、Practice など）。セーブは変更されません。無料で手に入れたアイテムはそのまま自分のものになります（先にセーブを save-backups "
        "にバックアップします）。オンラインでは両プレイヤーが常に同じステージになります。Jinpachi と Random はカジュアルマッチとルームで使えますが、Ranked では使えません。",
    "Sound and start": "サウンドと起動",
    "Mute sound": "ミュート",
    "Sound and taskbar flash for lobby notifications": "ロビーの通知時に音を鳴らしてタスクバーを点滅させる",
    "Sound when a match is found:": "マッチが見つかったときのサウンド：",
    'Announcer ("Get ready for the next battle")': 'ゲームのアナウンス（"Get ready for the next battle"）',
    "Beep": "ビープ音",
    "Your own WAV file": "自分のWAVファイル",
    "Choose WAV file…": "WAVファイルを選択…",
    "Play": "再生",
    "That file is not a WAV sound the launcher can play (plain PCM WAV only).": "ランチャーで再生できるWAVサウンドではありません（通常のPCM WAVのみ）。",
    "That sound is longer than 5 seconds.": "サウンドが5秒を超えています。",
    "That file is larger than 2 MB.": "ファイルが2 MBを超えています。",
    "That file could not be read or copied.": "ファイルを読み込めないか、コピーできませんでした。",
    "Your WAV file is gone.": "WAVファイルが見つかりません。",
    "{problem} The beep is used instead.": "{problem} 代わりにビープ音を使います。",
    "Your sound: {name}": "サウンド：{name}",
    "The announcer needs your built game (BUILD GAME): until then the beep plays.": "アナウンスにはビルド済みのゲームが必要です（BUILD GAME）。それまではビープ音が鳴ります。",
    "Choose a WAV sound": "WAVサウンドを選択",
    "WAV sound": "WAVサウンド",
    "Start minimized, without taking focus (for testing)": "最小化して起動、フォーカスを奪わない（テスト用）",
    "Advanced: extra settings, one NAME=VALUE per line": "詳細：追加設定（1行に1つ、NAME=VALUE）",
    "Internal resolution": "内部解像度",
    "VSync": "VSync",
    "On (smooth, default)": "オン（なめらか、標準）",
    "Off (lowest latency, may tear)": "オフ（最小遅延、ティアリングあり）",
    "The game always runs at 60 fps, like on the PS3.": "ゲームは PS3 と同じく常に 60fps で動作します。",
    "Stage blur / glow": "ステージのぼかし / 光彩",
    "Off (default)": "オフ（標準）",
    "Off": "オフ",
    "Some stages blur the picture (the misty swamp) or let the sun glow. Off shows them sharp, "
    "without the glow. Only your picture changes: online, both players can choose differently.":
        "一部のステージは画面をぼかしたり（霧の沼）、太陽を光らせたりします。オフにすると光彩なしでくっきり表示します"
        "。変わるのは自分の画面だけなので、オンラインでも各プレイヤーが別々に選べます。",
    "Training overlay": "トレーニング表示",
    "Also in the other offline modes (Arcade, Versus, ...)": "他のオフラインモードでも表示（Arcade、Versus など）",
    "Position:": "位置:",
    "Top": "上",
    "Bottom": "下",
    "Practice tools": "練習ツール",
    "SELECT combos in Practice (offline only)": "Practice で SELECT コンビネーション（オフラインのみ）",
    "Dummy:": "ダミー：",
    "As set in the game's Practice menu": "ゲームの Practice メニューの設定どおり",
    "Blocks after the first hit": "最初のヒット後にガード",
    "Crouches": "しゃがむ",
    "Walks forward and back": "前後に歩く",
    "Sidesteps": "横移動する",
    "Dashes in": "前ダッシュする",
    "Backdashes": "バックダッシュする",
    "Backdash cancels": "バックダッシュキャンセル",
    "Wavedashes": "風神ステップ",
    "In Practice, START opens the practice menu: the dummy's behaviour and counter-attack, recordings (8 "
    "slots per character, kept for next time), restart position, input delay. Hold SELECT and press: 3 "
    "restart; f+3 / b+3 the dummy against the wall in front of / behind you; df+3 / db+3 you against the "
    "wall; START remembers the position. 1 records the dummy (you play it), 2 plays once, 4 in a loop; "
    "tap up / down for the slot.":
        "Practice では START でトレーニングメニューを開きます：ダミーの動きと反撃、記録（キャラごとに8スロット、次回も保存）、開始位置、入力遅延。SELECT を押しながら：3 "
        "でやり直し、f+3 / b+3 でダミーを前 / 後ろの壁際へ、df+3 / db+3 で自分を壁際へ、START で位置を記憶。1 でダミーを記録（自分で操作）、2 で1回再生、4 でループ再生。上 "
        "/ 下を軽く押してスロットを選択。",
    "Also online (only your own inputs, no frame data)": "オンラインでも表示（自分の入力のみ、フレームデータなし）",
    "In Practice: your last inputs with how many frames each was held, and after each exchange the "
    "startup of the move and who can act first (+3, -12). F2 in the game switches it.":
        "Practice で：直近の入力と各入力を押していたフレーム数、攻防ごとに技の発生と先に動ける側（+3、-12）を表示しま"
        "す。ゲーム中は F2 で切り替えます。",
    "Your screen: {width} x {height}. In fullscreen, {step} matches it.":
        "画面：{width} x {height}。全画面では {step} が合います。",
    "Online input delay": "オンライン入力遅延",
    "Frames. Auto: 1 up to about 60 ms ping, 2 above. 0/1/2 count only when your "
    "opponent picked the same, otherwise Auto. Ranked matches always use 2.":
        "フレーム単位。自動：Ping 約60msまでは1、それ以上は2。0/1/2 は相手も同じ値を選んだときだけ有効で、それ以外は自"
        "動です。Ranked 対戦は常に2です。",
    "Open the game's port on my router during online matches (UPnP / NAT-PMP / PCP)":
        "オンライン対戦中にルーターでゲームのポートを開く（UPnP / NAT-PMP / PCP）",
    "Helps the direct connection when your opponent's router is strict. The port is open only while "
    "you play and is closed again afterwards.":
        "相手のルーターが厳しい場合に直接接続を助けます。ポートはプレイ中だけ開き、終わると閉じます。",
    "Set up controllers…": "コントローラー設定…",
    "Pick a pad, stick or hitbox, press the buttons you want for 1 2 3 4 and the rest, "
    "or start from a layout.":
        "パッド、アケコン、Hitbox を選び、1 2 3 4 などに使うボタンを押すか、配列から始めてください。",
    "(needs the lobby files, which are missing)": "（ロビーのファイルが必要ですが、ありません）",
    "Action (Tekken default)": "操作（Tekken標準）",
    "PS3 button": "PS3ボタン",
    "Keyboard": "キーボード",
    "Xbox controller": "Xboxコントローラー",
    "Keyboard and the first XInput controller both drive player 1 (they are combined). "
    "The keyboard only counts while the game window has focus. The game's own Options menu can change "
    "the button layout for offline play; online games use the launcher's buttons only.":
        "キーボードと1台目の XInput コントローラーはどちらもプレイヤー1を操作します（合成されます）。キーボードはゲー"
        "ムウィンドウにフォーカスがあるときだけ有効です。ゲーム自体の Options メニューでオフラインプレイ用のボタン配置を"
        "変更できます。オンライン対戦ではランチャーのボタン設定だけが使われます。",
    "In this window, on the Online tab, a controller or arcade stick works without mouse "
    "or keyboard: Cross / A accepts a match or rematch and starts a search, Circle / B "
    "declines, leaves or stops the search. It only counts while this window is in front, "
    "and only after the button was let go for a moment. Which stick button is Cross "
    "follows your controls.ini.":
        "このウィンドウのオンラインタブは、マウスやキーボードなしでコントローラーやアケコンでも操作できます：× / A "
        "で対戦や Rematch を受けて検索を開始、○ / B で断る・退出・検索の中止。このウィンドウが前面にあるときだけ、そし"
        "てボタンを一度離した後だけ有効です。アケコンのどのボタンが × かは controls.ini に従います。",
    "Language": "言語",
    "Restart now": "今すぐ再起動",
    "The language changes when the launcher starts again.": "言語はランチャーの再起動後に切り替わります。",
    "A build is running. Stop it first, or restart the launcher by hand when it is done.":
        "ビルドが実行中です。先に停止するか、終わってから手動でランチャーを再起動してください。",
    "Close the game first.": "先にゲームを閉じてください。",
    "Choose your Tekken 5 DR Online package": "Tekken 5 DR Online のパッケージを選択",
    "All files": "すべてのファイル",
    "PS3 package": "PS3パッケージ",
    "Choose your license (.rap)": "ライセンスを選択 (.rap)",
    "PS3 license": "PS3ライセンス",
    "Checking build tools…": "ビルドツールを確認中…",
    "missing": "なし",
    "ok": "ok",
    "Missing: {names}": "不足：{names}",
    "Everything the build needs is installed.": "ビルドに必要なものはすべてインストールされています。",
    "All build tools found.": "すべてのビルドツールが見つかりました。",
    "{count} build tool(s) missing -- click 'Install missing…'.":
        "ビルドツールが {count} 個不足しています -- 「不足分をインストール…」をクリックしてください。",
    "Hide details": "詳細を隠す",
    "Microsoft Visual Studio 2022 Build Tools: the C++ compiler parts only (MSVC x64, "
    "Windows SDK, CMake, Clang). Download about 2.5 GB, about 7 GB on disk, 10-20 "
    "minutes. You accept Microsoft's license terms for the Build Tools "
    "(visualstudio.microsoft.com/license-terms).":
        "Microsoft Visual Studio 2022 Build Tools：C++ コンパイラー部分のみ（MSVC x64、Windows SDK、CMake、Clang）。ダ"
        "ウンロード約2.5GB、ディスク使用量約7GB、10〜20分。Build Tools の Microsoft ライセンス条項（"
        "visualstudio.microsoft.com/license-terms）に同意することになります。",
    "Git for Windows (about 70 MB download).": "Git for Windows（ダウンロード約70MB）。",
    "Install build tools": "ビルドツールをインストール",
    "The build needs these free tools from their makers, installed with Windows' own "
    "installer (winget):\n\n{tools}\n\nWindows will ask for administrator permission. A "
    "console window shows the progress.\n\nInstall now?":
        "ビルドには、各メーカーが提供する次の無料ツールが必要です。Windows 標準のインストーラー（winget）でインストー"
        "ルします：\n\n{tools}\n\nWindows が管理者権限を求めます。進行状況はコンソールウィンドウに表示されます。"
        "\n\n今すぐインストールしますか？",
    "Could not start the installer:\n{error}\n\nIs winget (App Installer) available? On "
    "Windows 10 install 'App Installer' from the Microsoft Store.":
        "インストーラーを起動できませんでした：\n{error}\n\nwinget（アプリ インストーラー）は使えますか？ Windows 10 "
        "では Microsoft Store から「アプリ インストーラー」をインストールしてください。",
    "Install failed": "インストールに失敗しました",
    "Installer running in its own window…": "インストーラーを別ウィンドウで実行中…",
    "Could not start the build: {error}": "ビルドを開始できませんでした：{error}",
    "Building…": "ビルド中…",
    "Step {n} of {total}: {title}  —  {elapsed}": "ステップ {n}/{total}：{title}  —  {elapsed}",
    "Done in {elapsed}. Open the Play tab.": "{elapsed} で完了。オフラインプレイタブを開いてください。",
    "Build finished.": "ビルドが完了しました。",
    "Cancelled. BUILD GAME continues where it stopped.":
        "キャンセルしました。BUILD GAME は止まったところから再開します。",
    "The build stopped. The message below says why; build.log has the details.":
        "ビルドが止まりました。理由は下のメッセージに、詳細は build.log にあります。",
    "The build failed. See the log above and build.log.":
        "ビルドに失敗しました。上のログと build.log を確認してください。",
    "Build stopped.": "ビルドを停止しました。",
    "Could not start the game:\n{error}": "ゲームを起動できませんでした：\n{error}",
    "Game started (process {pid}). Log: {log}": "ゲームを起動しました（プロセス {pid}）。ログ：{log}",
    "starting…": "起動中…",
    "Running — {elapsed} — {fps}": "実行中 — {elapsed} — {fps}",
    "Click Report a problem.": "「問題を報告...」をクリックしてください。",
    "The game closed.": "ゲームが終了しました。",
    "A build is running. Stop it and quit?": "ビルドが実行中です。停止して終了しますか？",
    # ---- launcher/updater.py
    "Check for updates": "アップデートを確認",
    "Could not open a browser. The address: {url}": "ブラウザーを開けませんでした。アドレス: {url}",
    "Updated from {old} to {new}.": "{old} から {new} にアップデートしました。",
    "the new version": "新しいバージョン",
    "The update to {version} failed and could not be undone completely: {error}.\n\nThe "
    "old program files are in\n{folder}\nYour game, saves and settings (the native "
    "folder) were not touched. Download the zip from the releases page and extract it "
    "over this folder.":
        "{version} へのアップデートに失敗し、完全には元に戻せませんでした：{error}。\n\n古いプログラムファイルの場所："
        "\n{folder}\nゲーム、セーブ、設定（native フォルダー）には触れていません。リリースページから zip をダウンロー"
        "ドし、このフォルダーに上書きで展開してください。",
    "The update to {version} did not work: {error}.\n\nNothing was changed; this is "
    "still version {current}. Try again later, or download the zip from the releases "
    "page.":
        "{version} へのアップデートができませんでした：{error}。\n\n何も変更されておらず、バージョンは {current} のま"
        "まです。後でもう一度試すか、リリースページから zip をダウンロードしてください。",
    "Update": "アップデート",
    "Updates": "アップデート",
    "This is a development checkout (no release.json and bundled Python), so it does not "
    "update itself. Use git, or a release zip from\n{page}":
        "これは開発用のチェックアウトです（release.json と同梱 Python がありません）。そのため自動アップデートしません"
        "。git を使うか、次の場所からリリースの zip を入手してください：\n{page}",
    "Update to {version}…": "{version} にアップデート…",
    "Could not check for updates.\n\n{problem}": "アップデートを確認できませんでした。\n\n{problem}",
    "Version {version} is available: click 'Update to {version}' at the top.":
        "バージョン {version} が利用できます：上の「{version} にアップデート」をクリックしてください。",
    "You have the newest version ({version}).": "最新バージョン（{version}）です。",
    "Update available": "アップデートがあります",
    "T5DR Online {version} is available": "T5DR Online {version} が利用できます",
    "Download: {size}, published {date}.": "ダウンロード：{size}、{date} 公開。",
    "Download: {size}.": "ダウンロード：{size}。",
    "You have {version}.": "現在のバージョンは {version} です。",
    "The launcher downloads it, checks it, replaces its program files and starts again. "
    "Your game, saves and settings (the native folder) stay as they are.":
        "ランチャーがダウンロードして確認し、プログラムファイルを置き換えて再起動します。ゲーム、セーブ、設定（"
        "native フォルダー）はそのまま残ります。",
    "After this update the game is built once more (about 2 minutes): the Play tab "
    "offers BUILD GAME. Only the code is rebuilt; the unpacked game and saves are kept.":
        "このアップデートの後、ゲームをもう一度ビルドします（約2分）：オフラインプレイタブに BUILD GAME が表示されます"
        "。コードだけを再ビルドし、展開済みのゲームとセーブは残ります。",
    "The game itself does not need to be built again.": "ゲーム本体を再ビルドする必要はありません。",
    "If this update changes the game code, the Play tab asks you to build the game once "
    "(about 2 minutes).":
        "このアップデートでゲームコードが変わる場合、オフラインプレイタブで一度ビルドするよう案内されます（約2分）。",
    "(no release notes)": "（リリースノートなし）",
    "Update now": "今すぐアップデート",
    "Later": "後で",
    "Release page": "リリースページ",
    "Cancelling…": "キャンセル中…",
    "Downloading…": "ダウンロード中…",
    "Unexpected error: {error}": "予期しないエラー：{error}",
    "Downloading… {done} of {total}": "ダウンロード中… {done} / {total}",
    "Downloading… {done}": "ダウンロード中… {done}",
    "Checking the download (SHA-256)…": "ダウンロードを確認中（SHA-256）…",
    "Unpacking… {percent}%": "展開中… {percent}%",
    "Preparing the restart…": "再起動の準備中…",
    "Try again": "再試行",
    "Could not start the update step: {error}": "アップデート処理を開始できませんでした：{error}",
    "Installing {version}: the launcher restarts in a few seconds…":
        "{version} をインストール中：数秒後にランチャーが再起動します…",
    "Updating to {version}…": "{version} にアップデート中…",
    # ---- lobby/t5lobby/client.py
    "Contacting the lobby server over UDP...": "UDP でロビーサーバーに接続中...",
    "UDP to the lobby server is blocked (firewall?)":
        "ロビーサーバーへの UDP がブロックされています（ファイアウォール？）",
    "Connecting to your opponent...": "対戦相手に接続中...",
    "Measuring the connection...": "接続を測定中...",
    "Direct connection not possible; using the lobby server's relay...":
        "直接接続できません。ロビーサーバーの中継を使用中...",
    "Direct connection found: the match no longer goes through the lobby server.":
        "直接接続が見つかりました：対戦はもうロビーサーバーを経由しません。",
    "The direct connection was lost; back on the lobby server's relay.":
        "直接接続が切れました。ロビーサーバーの中継に戻りました。",
    "Direct connection not possible; using the relay server {name}...":
        "直接接続できません。中継サーバー {name} を使用中...",
    "Direct connection found: the match no longer goes through the relay server {name}.":
        "直接接続が見つかりました：対戦はもう中継サーバー {name} を経由しません。",
    "The direct connection was lost; back on the relay server {name}.":
        "直接接続が切れました。中継サーバー {name} に戻りました。",
    # ---- lobby/t5lobby/dialogs.py
    "No": "いいえ",
    "Yes": "はい",
    "OK": "OK",
    # ---- lobby/t5lobby/fighters.py
    "Random": "ランダム",
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
    "Stage {number}": "ステージ {number}",
    "Tekken 5 stage {number}": "Tekken 5 ステージ {number}",
    # ---- lobby/t5lobby/handover.py
    "direct connection": "直接接続",
    "local network": "ローカルネットワーク",
    "through the lobby server": "ロビーサーバー経由",
    "through the relay server {name}": "中継サーバー {name} 経由",
    "{name} -- {how}, ping {ms} ms, input delay {delay}": "{name} -- {how}、Ping {ms}ms、入力遅延 {delay}",
    # ---- lobby/t5lobby/i18n_known.py
    "login timeout": "ログインがタイムアウトしました",
    "idle timeout": "無操作のためタイムアウトしました",
    "banned from this server": "このサーバーから BAN されています",
    "too many connections": "接続が多すぎます",
    "server full": "サーバーが満員です",
    "slow down": "操作が速すぎます",
    "bad request": "不正なリクエスト",
    "the server is busy; try again in a few seconds": "サーバーが混雑しています。数秒後にもう一度試してください",
    "the chat is busy; try again in a moment": "チャットが混雑しています。少ししてからもう一度試してください",
    "that name looks too much like the account {other}": "その名前はアカウント {other} に似すぎています",
    "that name looks too much like {name}, who is online": "その名前はオンライン中の {name} に似すぎています",
    "flooding: disconnected": "連投のため切断されました",
    "this server speaks lobby protocol {version}; update the launcher":
        "このサーバーはロビープロトコル {version} を使っています。ランチャーをアップデートしてください",
    "build {build} is not accepted by this server; update the launcher and rebuild the "
    "game":
        "このサーバーはビルド {build} を受け付けません。ランチャーをアップデートしてゲームをビルドし直してください",
    "already logged in": "すでにログインしています",
    "this server has no accounts": "このサーバーにはアカウントがありません",
    "this server has no guest logins": "このサーバーはゲストログインできません",
    "too many failed logins; wait a few minutes": "ログインの失敗が多すぎます。数分待ってください",
    "too many failed attempts; wait a few minutes": "失敗した試行が多すぎます。数分待ってください",
    "too many password changes; wait a minute": "パスワードの変更が多すぎます。1分待ってください",
    "too many requests for new codes; wait a minute": "新しいコードの要求が多すぎます。1分待ってください",
    "too many new accounts from this address": "このアドレスからの新規アカウントが多すぎます",
    "the saved login has expired; log in with your password":
        "保存されたログインの期限が切れました。パスワードでログインしてください",
    "session expired; log in again": "セッションの期限が切れました。もう一度ログインしてください",
    "names are 2-16 letters, digits, spaces or _-.[]()!?":
        "名前は2〜16文字で、文字、数字、スペース、_-.[]()!? が使えます",
    "that name is reserved": "その名前は予約されています",
    "that name is not allowed here": "その名前はここでは使えません",
    "that name belongs to an account": "その名前はアカウントで使われています",
    "that name is taken": "その名前はすでに使われています",
    "someone with that name is online": "その名前の人がオンラインにいます",
    "wrong name or password": "名前またはパスワードが違います",
    "wrong password": "パスワードが違います",
    "the current password is wrong": "現在のパスワードが違います",
    "passwords are 6-128 characters": "パスワードは6〜128文字です",
    "guests have no password": "ゲストにはパスワードがありません",
    "guests have no account": "ゲストにはアカウントがありません",
    "wrong name or recovery code (each code works once)": "名前または復旧コードが違います（各コードは1回だけ使えます）",
    "logged in from another place": "別の場所からログインされました",
    "this account is banned for good": "このアカウントは永久BANされています",
    "this account is banned for good: {reason}": "このアカウントは永久BANされています：{reason}",
    "this account is banned until {time}": "このアカウントは {time} までBANされています",
    "this account is banned until {time}: {reason}": "このアカウントは {time} までBANされています：{reason}",
    "you are {status}": "今はできません（状態：{status}）",
    "ranked needs an account": "Ranked にはアカウントが必要です",
    "ranked matches come from the ranked queue on this server":
        "このサーバーの Ranked 対戦は Ranked のマッチング待ちからのみ組まれます",
    "your character is locked until this ranked set ends": "この Ranked セットが終わるまでキャラクターは固定です",
    "the ranked set goes on by itself": "Ranked セットは自動で続きます",
    "you are in a ranked set ({mine}-{theirs}); leave it first (that counts as a loss)":
        "Ranked セット中です（{mine}-{theirs}）。先に抜けてください（負け扱いになります）",
    "that player is in a ranked set": "そのプレイヤーは Ranked セット中です",
    "you are not in a ranked set": "Ranked セット中ではありません",
    "finish your running match with the same game build first": "先に同じゲームビルドで進行中の対戦を終えてください",
    "this PC ran its last match at {fps} fps; ranked needs at least {min_fps} (both "
    "games run at the slower PC's speed). Close other programs or lower the resolution "
    "scale, then play a casual match to measure again":
        "このPCの前回の対戦は {fps}fps でした。Ranked には最低 {min_fps} が必要です（両方のゲームが遅い方のPCの速度で"
        "動きます）。他のプログラムを閉じるか内部解像度を下げてから、カジュアル対戦をして測り直してください",
    "chat: slow down": "チャット：送信が速すぎます",
    "history is kept for accounts only": "履歴はアカウントのみ保存されます",
    "no such player": "そのプレイヤーは存在しません",
    "no such room": "そのルームは存在しません",
    "room is full": "ルームが満員です",
    "you cannot join this room": "このルームには入れません",
    "not in a room": "ルームに入っていません",
    "no opponent in the room": "ルームに対戦相手がいません",
    "that player runs a different build of the game": "そのプレイヤーは別のゲームビルドを使っています",
    "finish the match first": "先に対戦を終えてください",
    "finish or leave the running match first": "先に進行中の対戦を終えるか抜けてください",
    "that match is over; find a new opponent": "その対戦は終わっています。新しい相手を探してください",
    "your opponent is no longer available": "対戦相手はもういません",
    "that player is not available": "そのプレイヤーは今対戦できません",
    "busy": "取り込み中",
    "one challenge at a time": "対戦申し込みは一度に1つだけです",
    "that player has challenges pending": "そのプレイヤーには保留中の対戦申し込みがあります",
    "no such challenge": "その対戦申し込みは存在しません",
    "challenge no longer possible": "この対戦申し込みはもうできません",
    "no such match": "その対戦は存在しません",
    "match is {state}": "対戦の状態：{state}",
    "you cannot block yourself": "自分自身はブロックできません",
    "the block list is full ({max})": "ブロックリストがいっぱいです（{max}）",
    "that player is not on your block list": "そのプレイヤーはブロックリストにいません",
    "you are not in a set": "セット中ではありません",
    "no such finished match": "その終了済みの対戦は存在しません",
    "guests cannot have friends; create an account (free)":
        "ゲストはフレンドを持てません。（無料の）アカウントを作成してください",
    "there is no account with that name": "その名前のアカウントはありません",
    "you cannot add yourself": "自分自身は追加できません",
    "you blocked that player; unblock them first": "そのプレイヤーをブロックしています。先にブロックを解除してください",
    "your friends list is full ({max})": "フレンドリストがいっぱいです（{max}）",
    "your last invite to that friend ended a moment ago; try again in {seconds} s":
        "このフレンドへの前回の招待は終わったばかりです。{seconds} 秒後にもう一度試してください",
    "your last challenge to that player ended a moment ago; try again in {seconds} s":
        "このプレイヤーへの前回の対戦申し込みは終わったばかりです。{seconds} 秒後にもう一度試してください",
    "too many friend requests from this internet address today; try again tomorrow":
        "このインターネットアドレスからの今日のフレンド申請が多すぎます。明日もう一度試してください",
    "you can send {count} friend requests a day; try again tomorrow":
        "フレンド申請は1日 {count} 件までです。明日もう一度試してください",
    "{count} of your friend requests are waiting for an answer; cancel some first":
        "送ったフレンド申請のうち {count} 件が返事待ちです。先にいくつか取り消してください",
    "{name} declined your last request; you can ask again in {days} day(s)":
        "{name} さんが前回の申請を断りました。{days} 日後にもう一度申請できます",
    "that player has too many friend requests waiting": "そのプレイヤーには返事待ちのフレンド申請が多すぎます",
    "that player's friends list is full": "そのプレイヤーのフレンドリストはいっぱいです",
    "no friend request from that player": "そのプレイヤーからのフレンド申請はありません",
    "no friend request to that player": "そのプレイヤーへのフレンド申請はありません",
    "that player is not on your friends list": "そのプレイヤーはフレンドリストにいません",
    "that friend is not online": "そのフレンドはオンラインではありません",
    "that friend's launcher is too old for invites (it needs 1.1.2 or newer)":
        "そのフレンドのランチャーは古すぎて招待を受けられません（1.1.2 以降が必要）",
    "create a room first, then invite": "先にルームを作成してから招待してください",
    "that friend is busy right now": "そのフレンドは今取り込み中です",
    "one invite at a time": "招待は一度に1つだけです",
    "wait a moment before inviting again": "少し待ってから、もう一度招待してください",
    "that player has invites pending": "そのプレイヤーには保留中の招待があります",
    "that invite is over": "その招待は終了しています",
    "the invite is no longer possible": "この招待はもうできません",
    "{name} is back in the lobby": "{name} さんがロビーに戻りました",
    "{name} lost the lobby connection; waiting {seconds} s for them to return":
        "{name} さんのロビー接続が切れました。戻るまで {seconds} 秒待ちます",
    "your PC ran its last match at {fps} fps": "あなたのPCの前回の対戦は {fps}fps でした",
    "your opponent's PC ran its last match at {fps} fps": "相手のPCの前回の対戦は {fps}fps でした",
    "{name}'s PC ran its last match at {fps} fps": "{name} さんのPCの前回の対戦は {fps}fps でした",
    "{parts} -- this match runs at the slower PC's speed": "{parts} -- この対戦は遅い方のPCの速度で動きます",
    "you two played {count} ranked matches in the last 24 hours; this one is unranked "
    "(limit {max})":
        "お二人は直近24時間に Ranked 対戦を {count} 回行いました。この対戦はランクに反映されません（上限 {max}）",
    "your PC's UDP packets did not reach the lobby server; check the firewall":
        "あなたのPCの UDP パケットがロビーサーバーに届きませんでした。ファイアウォールを確認してください",
    "your opponent reported the result; please report yours": "相手が結果を報告しました。あなたも報告してください",
    "opponent runs a different build": "相手は別のビルドを使っています",
    "not connected to the lobby": "ロビーに接続していません",
    "the lobby server did not answer": "ロビーサーバーから応答がありませんでした",
    "no answer to {type}": "{type} への応答がありません",
    "cannot reach {host}:{port} ({error})": "{host}:{port} に接続できません（{error}）",
    "the server's certificate does not match the pinned one": "サーバーの証明書が固定された証明書と一致しません",
    "this server has no encryption (TLS): a password would cross the internet readable. "
    "Play as a guest, or ask the server's host to set up TLS and give you its "
    "fingerprint.":
        "このサーバーには暗号化（TLS）がありません：パスワードが読める状態でインターネットを通ります。ゲストでプレイす"
        "るか、サーバーの運営者に TLS を設定してフィンガープリントを教えてもらってください。",
    "connection closed": "接続が閉じられました",
    "the server sent a malformed match id": "サーバーから不正な対戦IDが届きました",
    "message too long": "メッセージが長すぎます",
    "closed": "閉じられました",
    "Choose your game package (.pkg) first.": "先にゲームパッケージ（.pkg）を選んでください。",
    "The package file does not exist: {file}": "パッケージファイルがありません：{file}",
    "{file} is not a PS3 package (.pkg).": "{file} は PS3 パッケージ（.pkg）ではありません。",
    "Choose your license file (.rap) first.": "先にライセンスファイル（.rap）を選んでください。",
    "{file} is not a PS3 license: a .rap file is exactly 16 bytes.":
        "{file} は PS3 のライセンスではありません。.rap ファイルはちょうど16バイトです。",
    "This package has no USRDIR/EBOOT.BIN -- it is not a game package (an add-on or "
    "theme?). The port needs {game}.":
        "このパッケージには USRDIR/EBOOT.BIN がありません -- ゲームのパッケージではありません（追加コンテンツやテーマ"
        "？）。この移植版には {game} が必要です。",
    "This package is \"{title}\" ({id}). The port needs {game}.":
        "このパッケージは「{title}」（{id}）です。この移植版には {game} が必要です。",
    "This copy is a different version of the game: \"{title}\" version {version}, content "
    "ID {id} (program SHA-1 {sha}...). The port supports only {game}, content ID "
    "{supported}.":
        "このコピーは別バージョンのゲームです：「{title}」バージョン {version}、コンテンツID {id}（プログラム SHA-1 "
        "{sha}...）。この移植版が対応しているのは {game}、コンテンツID {supported} だけです。",
    # 1.1.5: the package's version, read before the build (tools/build_game.py, launcher/core.py)
    "This package is version {version} of the game (program content ID {id}). The port supports only version "
    "{supported}: {game}, content ID {cid}, {size} bytes. This version cannot be used, whatever the license "
    "(.rap).":
        "このパッケージはゲームのバージョン {version} です（プログラムのコンテンツID "
        "{id}）。この移植版が対応しているのはバージョン {supported} だけです：{game}、コンテンツID {cid}、{size} "
        "バイト。このバージョンは、どのライセンス（.rap）でも使えません。",
    "{id}  ({size} bytes) -- version {version} of the game. The port supports only version {supported}; the "
    "build will refuse this package.":
        "{id}  ({size} バイト) -- ゲームのバージョン {version} です。この移植版はバージョン {supported} "
        "だけに対応しています。ビルドはこのパッケージを拒否します。",
    "{id}  ({size} bytes) -- its program has content ID {program}, not the supported one ({supported}). The "
    "build will most likely refuse it.":
        "{id}  ({size} バイト) -- このプログラムのコンテンツIDは {program} "
        "で、対応するもの（{supported}）ではありません。ビルドはほぼ確実に拒否します。",
    # 1.1.5: the game's own message boxes (launcher/core.py dialog_info, dialog_message)
    "The game shows: \"{text}\" {advice}": "ゲームのメッセージ：「{text}」 {advice}",
    "Your built game data is probably damaged. Open the Build tab, tick \"Redo every step\" and press BUILD "
    "GAME. If the message comes back, download the package again: it must be exactly {size} bytes.":
        "ビルドしたゲームデータが壊れている可能性があります。ビルドタブを開き、「全ステップをやり直す」にチェック"
        "を入れて BUILD GAME を押してください。それでもこのメッセージが出る場合は、パッケージをダウンロードし直し"
        "てください（ちょうど {size} バイトのはずです）。",
    "The game could not write its save, so progress may be lost. Check that the disk is not full and that no "
    "antivirus blocks the folder native\\gamedata.":
        "ゲームがセーブデータを書き込めませんでした。進行状況が失われる可能性があります。ディスクの空き容量と、ウ"
        "イルス対策ソフトが native\\gamedata フォルダーをブロックしていないか確認してください。",
    "The game could not read its save. If it happens every time, click Report a problem.":
        "ゲームがセーブデータを読み込めませんでした。毎回起きる場合は「問題を報告...」をクリックしてください。",
    "If the game does not go on, click Report a problem.":
        "ゲームが先に進まない場合は「問題を報告...」をクリックしてください。",
    # 1.1.5: the launcher's --search ranked|casual (lobby/t5lobby/tk_tab.py search_on_start)
    "Build the game first (Build tab); then the search starts by itself next time.":
        "先にゲームをビルドしてください（ビルドタブ）。次回からは検索が自動で始まります。",
    "Log in to start the search. Tick \"Remember me\" when you log in with your account: next time --search "
    "logs in and starts searching by itself.":
        "検索を始めるにはログインしてください。アカウントでログインするときに「ログイン状態を保持」にチェックを入"
        "れておくと、次回からは --search で自動的にログインして検索が始まります。",
    "Ranked matches need an account: log in with your name and password.":
        "Ranked 対戦にはアカウントが必要です。名前とパスワードでログインしてください。",
    # 1.1.5: a build step that prints nothing for long (launcher/core.py step_quiet_hint)
    "The step \"{title}\" has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
    "working. If nothing changes, press Cancel and then BUILD GAME again; build.log has the details.":
        "「{title}」ステップが {minutes} 分間何も出力していません。遅いPCや負荷の高いPCではまだ処理中の場合があり"
        "ます。変化がなければキャンセルを押してからもう一度 BUILD GAME を押してください。詳細は build.log "
        "にあります。",
    "Last program started: {tool}.": "最後に起動したプログラム：{tool}",
    "The license (.rap) does not belong to this package. Use the .rap whose name matches "
    "the package's content ID ({id}).":
        "ライセンス（.rap）がこのパッケージのものではありません。名前がパッケージのコンテンツID（{id}）と一致する "
        ".rap を使ってください。",
    "The decrypted game program is missing or not a supported version. Tick \"Redo every step\" and press BUILD GAME again.":
        "復号したゲームプログラムがないか、対応バージョンではありません。「全ステップをやり直す」にチェックを入れて、もう一度BUILD GAMEを押してください。",
    "Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press BUILD GAME "
    "again; if it fails again, check that the package is {size} bytes.":
        "ゲームプログラムの復号に失敗しました（上のログを参照）。「全ステップをやり直す」にチェックを入れて、もう一度"
        " BUILD GAME を押してください。また失敗する場合は、パッケージが {size} バイトか確認してください。",
    "The package is {size} bytes, the supported one is {supported} bytes: the download is incomplete or it is "
    "a different file. Download it again.":
        "パッケージは {size} バイトですが、対応パッケージは {supported} バイトです：ダウンロードが不完全か、別のファイ"
        "ルです。もう一度ダウンロードしてください。",
    "The ps3recomp copy in this folder does not match this version of the port. Download "
    "the release again and extract it into an empty folder.":
        "このフォルダーの ps3recomp はこのバージョンの移植版と一致しません。リリースをもう一度ダウンロードし、空のフォ"
        "ルダーに展開してください。",
    "Git is needed to download ps3recomp (the recompiler). Install Git, or use a release "
    "zip, which already contains it.":
        "ps3recomp（リコンパイラー）のダウンロードには Git が必要です。Git をインストールするか、同梱済みのリリース "
        "zip を使ってください。",
    "This package's Python is missing pycryptodome. Download the release again.":
        "このパッケージの Python に pycryptodome がありません。リリースをもう一度ダウンロードしてください。",
    "Could not download the public PS3 key data from github.com (needed once, a few KB). "
    "Check the internet connection and press BUILD GAME again.":
        "github.com から公開 PS3 鍵データをダウンロードできませんでした（初回のみ必要、数KB）。インターネット接続を確"
        "認して、もう一度 BUILD GAME を押してください。",
    "The C++ build tools (Visual Studio 2022 Build Tools, x64 C++ toolset) are not "
    "installed. Open the launcher's Build tab and click Install next to them.":
        "C++ ビルドツール（Visual Studio 2022 Build Tools、x64 C++ ツールセット）がインストールされていません。ランチ"
        "ャーのビルドタブを開き、「不足分をインストール…」をクリックしてください。",
    "clang-cl.exe and lld-link.exe were not found in toolchain\\llvm\\bin. Download the "
    "release again.":
        "toolchain\\llvm\\bin に clang-cl.exe と lld-link.exe が見つかりません。リリースをもう一度ダウンロードしてくだ"
        "さい。",
    "The Windows SDK is missing (needed for Direct3D 12). Install it with the C++ build "
    "tools.":
        "Windows SDK がありません（Direct3D 12 に必要）。C++ ビルドツールと一緒にインストールしてください。",
    "clang-cl (LLVM 16 or newer) was not found. Install LLVM or the Visual Studio "
    "component 'C++ Clang tools for Windows'.":
        "clang-cl（LLVM 16 以降）が見つかりません。LLVM か、Visual Studio のコンポーネント「C++ Clang tools for "
        "Windows」をインストールしてください。",
    "CMake and Ninja were not found. Install the Visual Studio component 'C++ CMake "
    "tools for Windows'.":
        "CMake と Ninja が見つかりません。Visual Studio のコンポーネント「C++ CMake tools for Windows」をインストール"
        "してください。",
    "CMake and Ninja were not found. On macOS: brew install cmake ninja sdl2 glslang spirv-cross":
        "CMake と Ninja が見つかりません。macOS では次を実行してください: brew install cmake ninja sdl2 glslang spirv-cross",
    "glslang and spirv-cross were not found; the game's shaders need them. "
    "On macOS: brew install glslang spirv-cross":
        "glslang と spirv-cross が見つかりません。ゲームのシェーダーに必要です。macOS では次を実行してください: brew install glslang spirv-cross",
    "Building the game is supported on Windows and macOS only.":
        "ゲームのビルドに対応しているのは Windows と macOS のみです。",
    "This Python refuses pip install (PEP 668; Homebrew's does). Use a virtual environment: python3 -m venv .venv && .venv/bin/pip install pycryptodome, then run the tools with .venv/bin/python.":
        "この Python は pip install を拒否します (PEP 668。Homebrew の Python が該当)。仮想環境を使ってください: python3 -m venv .venv && .venv/bin/pip install pycryptodome を実行し、ツールは .venv/bin/python で起動します。",
    "expected 1 SPU image, found {count}": "SPU イメージは1つのはずが {count} 個見つかりました",
    "step '{step}' failed: a tool exited with code {code} -- the lines above say why.":
        "ステップ「{step}」に失敗しました：ツールがコード {code} で終了しました -- 理由は上の行にあります。",
    "cancelled": "キャンセルされました",
    "step '{step}' could not read or write a file: {reason} ({file}). The folder path is "
    "too long for Windows: move the folder to a short path such as C:\\Games\\T5DR.":
        "ステップ「{step}」でファイルを読み書きできませんでした：{reason}（{file}）。フォルダーのパスが Windows には長"
        "すぎます：C:\\Games\\T5DR のような短いパスにフォルダーを移動してください。",
    "step '{step}' could not read or write a file: {reason} ({file}). Is the disk full, "
    "or does another program (antivirus, OneDrive) hold the file?":
        "ステップ「{step}」でファイルを読み書きできませんでした：{reason}（{file}）。ディスクがいっぱいか、別のプログ"
        "ラム（ウイルス対策ソフト、OneDrive）がファイルを使用していませんか？",
    "Python 3.10+": "Python 3.10+",
    "pycryptodome (Python AES)": "pycryptodome (Python AES)",
    "ps3recomp source": "ps3recomp ソース",
    "Game runtime (t5dr.exe)": "ゲームランタイム (t5dr.exe)",
    "clang-cl + lld-link": "clang-cl + lld-link",
    "C++ build tools (MSVC x64)": "C++ ビルドツール (MSVC x64)",
    "Windows SDK (Direct3D 12)": "Windows SDK (Direct3D 12)",
    "clang-cl 16+ (LLVM)": "clang-cl 16+ (LLVM)",
    "CMake + Ninja": "CMake + Ninja",
    "{version} at {path}": "{version}（{path}）",
    "installed": "インストール済み",
    "missing -- pip install pycryptodome": "なし -- pip install pycryptodome",
    "included in this package": "このパッケージに同梱",
    "git checkout in deps/": "deps/ の git チェックアウト",
    "not present -- will be downloaded with Git": "なし -- Git でダウンロードします",
    "not present and Git is missing": "なし、Git もありません",
    "precompiled, included in this package": "コンパイル済み、このパッケージに同梱",
    "missing from toolchain\\llvm -- extract the release zip again": "toolchain\\llvm にありません -- リリースの zip をもう一度展開してください",
    "missing from this folder -- extract the release zip again": "このフォルダーにありません -- リリースの zip をもう一度展開してください",
    "This folder is incomplete ({folders} missing). Extract the release zip again with \"Extract All\" into a short path such as {example}, then start T5DR Online.exe from there -- not from inside the zip.":
        "このフォルダーは不完全です（{folders} がありません）。リリースの zip を \"すべて展開\" で {example} のような短いパスにもう一度展開し、そこから T5DR Online.exe を起動してください。zip の中からは起動しないでください。",
    "This folder is incomplete: extract the release zip again (see the Build tab).": "このフォルダーは不完全です: リリースの zip をもう一度展開してください（ビルドタブを参照）。",
    "not found": "見つかりません",
    "missing {tools}": "不足：{tools}",
    "System information and the settings you use": "システム情報と使用中の設定",
    "What happened (what you wrote)": "何が起きたか（入力した内容）",
    "Launcher log": "ランチャーのログ",
    "Game log (the newest one)": "ゲームログ（最新）",
    "Game log (the newest {count})": "ゲームログ（最新 {count} 件）",
    "Build log": "ビルドログ",
    "Build log (the last build went fine)": "ビルドログ（前回のビルドは正常）",
    "Online: the files of the last match": "オンライン：前回の対戦のファイル",
    "controls.ini (your button settings)": "controls.ini（ボタン設定）",
    "Desync dumps (game state numbers, binary)": "同期ズレのダンプ（ゲーム状態の数値、バイナリ）",
    "The last replay (the inputs of the last online session, without names)":
        "最新のリプレイ（最後のオンラインセッションの入力、名前なし）",
    "could not be cleaned of private data": "個人情報を取り除けませんでした",
    "no room left in the size limit": "サイズ上限に空きがありません",
    "could not be read": "読み込めませんでした",
    "The launcher cannot write next to its folder or into it, so it cannot update "
    "itself. Download the zip from the releases page instead.":
        "ランチャーが自分のフォルダーの隣にも中にも書き込めないため、自動アップデートできません。代わりにリリースペー"
        "ジから zip をダウンロードしてください。",
    "Refused to download from {host}: not this project's GitHub releases.":
        "{host} からのダウンロードを拒否しました：このプロジェクトの GitHub リリースではありません。",
    "The download came from {host}. Nothing was changed.": "ダウンロードは {host} からでした。何も変更していません。",
    "GitHub did not return a published release.": "GitHub から公開済みのリリースが返ってきませんでした。",
    "The latest release has an unexpected version ({tag}).": "最新リリースのバージョンが想定外です（{tag}）。",
    "Release {version} has no {name} with SHA256SUMS yet.":
        "リリース {version} にはまだ SHA256SUMS 付きの {name} がありません。",
    "The downloaded release does not say it is version {version}. Nothing was changed.":
        "ダウンロードしたリリースがバージョン {version} だと示していません。何も変更していません。",
    "The downloaded release has no launcher. Nothing was changed.":
        "ダウンロードしたリリースにランチャーがありません。何も変更していません。",
    "This folder has no python\\pythonw.exe, so the launcher cannot update itself (a "
    "development checkout?). Download the zip from the releases page instead.":
        "このフォルダーに python\\pythonw.exe がないため、ランチャーは自動アップデートできません（開発用チェックアウト"
        "？）。代わりにリリースページから zip をダウンロードしてください。",
    "The download was sent to {host}, which is not GitHub's storage for this project. "
    "Nothing was changed.":
        "ダウンロードは、このプロジェクトの GitHub ストレージではない {host} に転送されました。何も変更していません。",
    "Release {version}: {name} is not on this project's GitHub releases.":
        "リリース {version}：{name} はこのプロジェクトの GitHub リリースにありません。",
    "Release {version}: {name} is still being uploaded.": "リリース {version}：{name} はまだアップロード中です。",
    "The download stopped early ({done} of {total} bytes). Try again.":
        "ダウンロードが途中で止まりました（{done} / {total} バイト）。もう一度試してください。",
    "The download is not a readable zip ({error}). Nothing was changed.":
        "ダウンロードしたファイルは読める zip ではありません（{error}）。何も変更していません。",
    "The download unpacks to far more than a release should. Nothing was changed.":
        "ダウンロードを展開するとリリースとしては大きすぎます。何も変更していません。",
    "Not enough free disk space: the update needs about {need} MB next to the folder, "
    "{free} MB are free.":
        "ディスクの空き容量が足りません：アップデートにはフォルダーの隣に約 {need}MB 必要ですが、空きは {free}MB です"
        "。",
    "SHA256SUMS of release {version} has no line for {name}. Nothing was changed.":
        "リリース {version} の SHA256SUMS に {name} の行がありません。何も変更していません。",
    "SHA256SUMS and GitHub disagree about the download's checksum. Nothing was changed.":
        "SHA256SUMS と GitHub でダウンロードのチェックサムが一致しません。何も変更していません。",
    "The download is damaged or not the published file: its SHA-256 is {got}..., "
    "SHA256SUMS says {want}.... Nothing was changed.":
        "ダウンロードが壊れているか、公開されたファイルではありません：SHA-256 は {got}... ですが、SHA256SUMS は "
        "{want}... です。何も変更していません。",
    "The downloaded release has no python\\pythonw.exe. Nothing was changed.":
        "ダウンロードしたリリースに python\\pythonw.exe がありません。何も変更していません。",
    "The download is far bigger than a release should be. Nothing was changed.":
        "ダウンロードがリリースとしては大きすぎます。何も変更していません。",
    "The download contains an unexpected path ({name}: {why}). Nothing was changed.":
        "ダウンロードに想定外のパスが含まれています（{name}：{why}）。何も変更していません。",
    "The download contains an unexpected path ({name}). Nothing was changed.":
        "ダウンロードに想定外のパスが含まれています（{name}）。何も変更していません。",
    "Cancelled.": "キャンセルしました。",
    "Could not download or unpack the update ({error}). Nothing was changed.":
        "アップデートをダウンロードまたは展開できませんでした（{error}）。何も変更していません。",
    "The download is damaged ({error}). Nothing was changed.":
        "ダウンロードが壊れています（{error}）。何も変更していません。",
    "the new release contains {names} (the player's files)":
        "新しいリリースに {names}（プレイヤーのファイル）が含まれています",
    "release.json does not say {version} after the swap": "入れ替え後の release.json が {version} になっていません",
    "launcher\\t5dr_launcher.pyw is missing after the swap": "入れ替え後に launcher\\t5dr_launcher.pyw がありません",
    "python\\pythonw.exe is missing after the swap": "入れ替え後に python\\pythonw.exe がありません",
    "the update plan is incomplete": "アップデートの計画が不完全です",
    "the launcher did not close": "ランチャーが終了しませんでした",
    "programs from the folder were still running ({names}); close them and try again":
        "フォルダー内のプログラムがまだ実行中でした（{names}）。閉じてからもう一度試してください",
    "the new launcher {version} did not start": "新しいランチャー {version} が起動しませんでした",
    "the new launcher did not confirm startup before the timeout":
        "新しいランチャーは制限時間内に起動を確認しませんでした",
    "could not replace the program files: {error}": "プログラムファイルを置き換えられませんでした：{error}",
    "unexpected error: {error}": "予期しないエラー：{error}",
    "GitHub asks to wait with update checks until {time}.":
        "GitHub から {time} までアップデートの確認を待つよう求められています。",
    "GitHub limits update checks right now. Try again later.":
        "GitHub が現在アップデートの確認を制限しています。後でもう一度試してください。",
    "GitHub answered with error {code}. Try again later.":
        "GitHub がエラー {code} を返しました。後でもう一度試してください。",
    "No connection to GitHub. Check the internet connection and try again.":
        "GitHub に接続できません。インターネット接続を確認して、もう一度試してください。",
    "A build is running. Update when it is finished.": "ビルドが実行中です。終わってからアップデートしてください。",
    "The game is running. Close it first, then update.":
        "ゲームが起動しています。先に閉じてからアップデートしてください。",
    "'Host for friends' is running. Stop hosting first, then update.":
        "「フレンド用ホスト」が実行中です。先にホストを止めてからアップデートしてください。",
    "An online match was found. Update after the match.":
        "オンライン対戦が見つかりました。対戦の後でアップデートしてください。",
    "An online match is running. Update after the match.": "オンライン対戦中です。対戦の後でアップデートしてください。",
    "You are searching for or playing an online match. Update afterwards.":
        "オンライン対戦を検索中またはプレイ中です。終わってからアップデートしてください。",
    "Other programs from this folder are still running ({names}): another launcher "
    "window, the game or a lobby server. Close them, then update.":
        "このフォルダーの他のプログラムがまだ実行中です（{names}）：別のランチャーウィンドウ、ゲーム、またはロビーサー"
        "バー。閉じてからアップデートしてください。",
    "not a plain relative path": "単純な相対パスではありません",
    "'.', '..' or an empty part": "「.」「..」または空の部分",
    "outside the folder {folder}": "{folder} フォルダーの外",
    "named like the player's own files": "プレイヤー自身のファイルと同じ名前",
    "a name Windows does not keep as written": "Windows が書いたとおりに保存しない名前",
    "Release {version} is a test version; it is not installed automatically.":
        "リリース {version} はテスト版のため、自動ではインストールされません。",
    "Release {version} is not signed with the project's release key (no SHA256SUMS.sig). It was not made by "
    "the project's release process; nothing was changed.":
        "リリース {version} はプロジェクトのリリース鍵で署名されていません（SHA256SUMS.sig なし）。プロジェクトのリリ"
        "ース手順で作られたものではありません。何も変更していません。",
    "Release {version} failed the signature check ({error}). It was not made by the project's release "
    "process; nothing was changed.":
        "リリース {version} は署名の確認に失敗しました（{error}）。プロジェクトのリリース手順で作られたものではありま"
        "せん。何も変更していません。",
    "idle": "待機中",
    "room": "ルーム内",
    "queue": "マッチング中",
    "match": "対戦中",
    "playing": "プレイ中",
    # ---- lobby/t5lobby/discord_rpc.py
    "In lobby": "ロビーで待機中",
    "Searching ranked": "Ranked 検索中",
    "Searching quick match": "Quick Match 検索中",
    "Ranked, Set {mine}-{theirs}": "Ranked、セット {mine}-{theirs}",
    "Ranked": "Ranked",
    "Casual": "カジュアル",
    "In match: {mine} vs {theirs} ({what})": "対戦中：{mine} vs {theirs}（{what}）",
    "In match ({what})": "対戦中（{what}）",
    # ---- lobby/t5lobby/lag.py
    "Ping {ping} ms should mean about {frames} frames behind.":
        "Ping {ping}ms なら、約 {frames} フレームの遅れが普通です。",
    "The games did not report how it went, so there is nothing to compare.":
        "ゲームから状況の報告がなかったため、比較するものがありません。",
    "It was {observed}.": "実際は {observed} でした。",
    "That is what the ping explains.": "Ping で説明できる範囲です。",
    "That is more than the ping explains.": "Ping で説明できるより多いです。",
    "Both PCs ran below full speed.": "両方のPCが全速を下回っていました。",
    "Your PC was the slow one ({fps} fps).": "遅かったのはあなたのPCです（{fps}fps）。",
    "Your PC was the slow one.": "遅かったのはあなたのPCです。",
    "Your opponent's PC was the slow one ({fps} fps).": "遅かったのは相手のPCです（{fps}fps）。",
    "Your opponent's PC was the slow one.": "遅かったのは相手のPCです。",
    "Both PCs kept up, so the connection stalled now and then (jitter or lost packets).":
        "両方のPCは追いついていたので、接続がときどき止まっていました（ジッターまたはパケットロス）。",
    "This match lagged: the games waited {secs} s for each other's inputs.":
        "この対戦はラグがありました。ゲームが互いの入力を {secs} 秒待ちました。",
    "A wired connection and no uploads during matches help.":
        "有線接続にして、対戦中はアップロードを控えると改善します。",
    # ---- lobby/t5lobby/match_driver.py
    "Your opponent closed the game.": "相手がゲームを閉じました。",
    "The connection to your opponent's game was lost.": "相手のゲームとの接続が切れました。",
    "Your opponent's game stopped responding.": "相手のゲームが応答しなくなりました。",
    "Your opponent's game did not get to the fight.": "相手のゲームが対戦開始までたどり着けませんでした。",
    "Your opponent's game was restarted; the match cannot go on.":
        "相手のゲームが再起動されたため、対戦を続けられません。",
    "Loading the fight took too long on this PC (slow disk or a busy PC?); the match was stopped.":
        "このPCで対戦の読み込みに時間がかかりすぎました（ディスクが遅いか、PCの負荷が高い？）。対戦は中止されました。",
    "Loading the fight took too long on your opponent's PC; the match was stopped.":
        "相手のPCで対戦の読み込みに時間がかかりすぎました。対戦は中止されました。",
    "Your opponent's game could not be reached (firewall or router?).":
        "相手のゲームに接続できませんでした（ファイアウォールかルーター？）。",
    "Your opponent's game is a different build.": "相手のゲームは別のビルドです。",
    "Your opponent's game is in another match.": "相手のゲームは別の対戦中です。",
    "The game could not open its network port (another program uses it?).":
        "ゲームがネットワークポートを開けませんでした（別のプログラムが使用中？）。",
    "You closed the game during the match: it counts as a loss.": "対戦中にゲームを閉じました：負けとして扱われます。",
    "The game could not get back to character select and closed itself; it starts again for your next match.":
        "ゲームがキャラクター選択に戻れず自動で終了しました。次の対戦で再び起動します。",
    "Your opponent does not want a rematch.": "相手は Rematch を希望していません。",
    "The game is not running any more; leaving the rematch.": "ゲームが終了しているため、Rematch から抜けます。",
    "Rematch against {name}: same connection, the game stays open.":
        "{name} さんと Rematch：同じ接続のまま、ゲームも開いたままです。",
    "The game could not start; leaving the match.": "ゲームを起動できなかったため、対戦から抜けます。",
    "Playing against {summary}": "対戦相手：{summary}",
    "The game did not answer its control channel; it is restarted for every opponent "
    "from now on.":
        "ゲームが制御チャンネルに応答しませんでした。今後は対戦相手ごとに再起動します。",
    "Character select...": "キャラクター選択...",
    "The game is starting...": "ゲームを起動中...",
    "Fight!": "Fight!",
    "Loading the fight...": "対戦を読み込み中...",
    "Stage select...": "ステージ選択...",
    "At character select, waiting for the next match.": "キャラクター選択画面で次の対戦を待っています。",
    "Match over.": "対戦終了。",
    "Ignored a result the game wrote for an earlier match.": "ゲームが前の対戦用に書いた結果を無視しました。",
    "The match could not be finished ({reason}).": "対戦を終えられませんでした（{reason}）。",
    "The match could not be played ({reason}).": "対戦できませんでした（{reason}）。",
    "The game stopped unexpectedly; the match does not count (repeated crashes do).":
        "ゲームが予期せず停止しました。この対戦はカウントされません（クラッシュが繰り返されるとカウントされます）。",
    "Result sent (the games went out of sync on {frames} frames); waiting for the "
    "lobby...":
        "結果を送信しました（{frames} フレームで同期ズレ）。ロビーを待っています...",
    "Result sent; waiting for the lobby...": "結果を送信しました。ロビーを待っています...",
    "Lobby: {message}": "ロビー：{message}",
    # ---- lobby/t5lobby/padnav.py
    "(+{count} more)": "（ほか {count} 件）",
    # ---- lobby/t5lobby/ranks.py
    "{wins}W {losses}L": "{wins}勝 {losses}敗",
    "{draws}D": "{draws}分",
    "{rank} (placement {done}/{total})": "{rank}（段位認定 {done}/{total}）",
    # ---- lobby/t5lobby/sets.py
    "a game was too short to count": "試合が短すぎてカウントされませんでした",
    "a fight ended without a winner": "勝者なしで終わった試合がありました",
    "too many games without a winner": "勝者なしの試合が多すぎます",
    "left after the lag check": "ラグチェック後に退出",
    "the lobby server restarted": "ロビーサーバーが再起動しました",
    "a player left right away": "プレイヤーがすぐに退出しました",
    "the next game could not start": "次の試合を開始できませんでした",
    "a player left before a game counted": "試合がカウントされる前にプレイヤーが退出しました",
    "a player lost the lobby connection": "プレイヤーのロビー接続が切れました",
    "set won": "セット勝利",
    "set lost": "セット敗北",
    "Set {mine}-{theirs}": "セット {mine}-{theirs}",
    "game {number} of {best}": "{best}試合中の第{number}試合",
    "game {number} of {best} again (no winner)": "{best}試合中の第{number}試合をやり直し（勝者なし）",
    "starts in {seconds} s": "{seconds} 秒後に開始",
    "The set does not count ({why}); no rating change": "このセットはカウントされません（{why}）。レートの変動なし",
    "The set does not count; no rating change": "このセットはカウントされません。レートの変動なし",
    "You won the set (your opponent left it)": "セットに勝ちました（相手が退出）",
    "You won the set": "セットに勝ちました",
    "You lost the set (you left it)": "セットに負けました（自分が退出）",
    "You lost the set": "セットに負けました",
    "You won the set {mine}-{theirs}": "セット {mine}-{theirs} で勝ちました",
    "You lost the set {mine}-{theirs}": "セット {mine}-{theirs} で負けました",
    "set game {number}": "セット第{number}試合",
    # 1.1.9: who left a ranked set, and how; a player away from the set (sets.py, tk_tab.py, the server)
    "You won the set ({how})":
        "セットに勝ちました（{how}）",
    "You lost the set ({how})":
        "セットに負けました（{how}）",
    "you left the set":
        "自分がセットから退出",
    "your opponent left the set":
        "相手がセットから退出",
    "you did not come back within {seconds} s":
        "自分が{seconds}秒以内に戻らなかった",
    "your opponent did not come back within {seconds} s":
        "相手が{seconds}秒以内に戻らなかった",
    "you quit a game":
        "自分が試合を中断",
    "your opponent quit a game":
        "相手が試合を中断",
    "you lost the connection":
        "自分の接続が切れた",
    "your opponent lost the connection":
        "相手の接続が切れた",
    "your side could not connect":
        "自分側が接続できなかった",
    "your opponent's side could not connect":
        '相手側が接続できなかった',
    "a player did not come back in time":
        "プレイヤーが時間内に戻りませんでした",
    "played again: a player was away":
        "再試合：プレイヤーが不在でした",
    "A player was away; the set's game starts again.":
        'プレイヤーが不在でした。セットの試合をやり直します。',
    "{name} is reconnecting -- {seconds} s left":
        "{name} さんが再接続中 -- 残り {seconds} 秒",
    "{name} is back; the set goes on":
        "{name} さんが戻りました。セットを続けます",
    "you are back in the ranked set ({mine}-{theirs}); the next game starts soon":
        "ランクセットに戻りました（{mine}-{theirs}）。次の試合がまもなく始まります",
    # ---- lobby/t5lobby/tk_tour.py, tour_text.py (tournaments)
    "A set is played like a casual set with the in-game select; results come from the games. Players who do not accept a called set in time are out.": "セットはゲーム内でキャラクターを選ぶカジュアルのセットと同じように行われ、結果はゲームから取られます。呼ばれたセットを時間内に受けないと失格です。",
    "Accepted. Waiting for {name}...": "受けました。{name} さんを待っています...",
    "Bracket": "トーナメント表",
    "CALLED": "呼び出し中",
    "Cancel tournament": "トーナメントを中止",
    "Cancel {name}? Nobody can play it any more.": "{name} を中止しますか？ もう誰もプレイできなくなります。",
    "Cancelled": "中止",
    "Champion: {name}": "優勝: {name}",
    "Check in": "チェックイン",
    "Check-in": "チェックイン",
    "Check-in 10 minutes before": "10 分前からチェックイン",
    "Check-in 15 minutes before": "15 分前からチェックイン",
    "Check-in 30 minutes before": "30 分前からチェックイン",
    "Check-in 5 minutes before": "5 分前からチェックイン",
    "Check-in 60 minutes before": "60 分前からチェックイン",
    "Check-in for {name} is open: check in on the Tournaments page, or you are not in the bracket.": "{name} のチェックインが始まりました。トーナメントのページでチェックインしないとトーナメント表に入れません。",
    "Checked in.": "チェックイン済み。",
    "Click a set in the bracket.": "トーナメント表のセットをクリックしてください。",
    "Create": "作成",
    "Create tournament": "トーナメント作成",
    "Create...": "作成...",
    "Disqualify": "失格にする",
    "Disqualify which player (name)?": "失格にするプレイヤー（名前）は？",
    "Disqualify...": "失格にする...",
    "Double elimination": "ダブルエリミネーション",
    "Final": "決勝",
    "Finished": "終了",
    "First to 2 games (best of 3)": "2 本先取（3本勝負）",
    "First to 3 games (best of 5)": "3 本先取（5本勝負）",
    "Format": "形式",
    "Grand final": "グランドファイナル",
    "Grand final reset": "グランドファイナル（リセット）",
    "LIVE": "対戦中",
    "Leave the tournament set": "トーナメントのセットから抜ける",
    "Leave this tournament set?\n\nYou lose the set.": "このトーナメントのセットから抜けますか？\n\nセットは負けになります。",
    "Losers final": "ルーザーズ決勝",
    "Losers round {number}": "ルーザーズ {number}回戦",
    "Losers semi-final": "ルーザーズ準決勝",
    "NEEDS THE ORGANIZER": "主催者の対応待ち",
    "No check-in": "チェックインなし",
    "No tournament selected": "トーナメントが選ばれていません",
    "Only tournament hosts can create tournaments. Ask the server's owner for a host slot.":
        "トーナメントを作成できるのはトーナメントホストだけです。ホストの枠はサーバーの管理者に頼んでください。",
    "Pick a tournament to see its bracket.": "トーナメントを選ぶとトーナメント表が表示されます。",
    "Pick one in the list, or create one.": "リストから選ぶか、新しく作成してください。",
    "Players": "人数",
    "Players at most": "最大人数",
    "Players: {list}": "参加者: {list}",
    "Quarter-final": "準々決勝",
    "Random seeding": "ランダムシード",
    "Report a result": "結果を入力",
    "Reset set": "セットをリセット",
    "Reset set {set}? It is played again from 0-0.": "セット {set} をリセットしますか？ 0-0 からやり直しになります。",
    "Round {number}": "{number}回戦",
    "Running": "開催中",
    "Seeded by rating": "レート順シード",
    "Seeding": "シード",
    "Semi-final": "準決勝",
    "Sets": "セット",
    "Side 1 wins": "サイド1の勝ち",
    "Side 2 wins": "サイド2の勝ち",
    "Sign up": "エントリー",
    "Sign-up": "エントリー受付中",
    "Single elimination": "シングルエリミネーション",
    "Start now": "今すぐ開始",
    "Start {name} now, with the players who are in?": "今エントリーしているプレイヤーで {name} を開始しますか？",
    "Starts": "開始",
    "TOURNAMENT": "トーナメント",
    "TOURNAMENT SET · BEST OF {best}": "トーナメントセット · {best}本勝負",
    "The bracket is drawn when the tournament starts.": "トーナメント表は開始時に作られます。",
    "The name needs 3 characters or more.": "名前は 3 文字以上にしてください。",
    "The organizer decided your tournament set.": "主催者がトーナメントのセットの結果を決めました。",
    "The organizer reset your tournament set; it is called again.": "主催者がトーナメントのセットをリセットしました。もう一度呼ばれます。",
    "The set goes on at {mine}-{theirs}.": "セットは {mine}-{theirs} から続きます。",
    "The set has no result; the tournament calls it again or its organizer decides": "セットの結果が出ませんでした。トーナメントが再び呼び出すか、主催者が決めます",
    "The set is called again.": "セットがもう一度呼ばれました。",
    "The tournament was cancelled.": "トーナメントは中止されました。",
    "The tournament {name} has started: you are seed {seed} of {players}. Your sets are called here.": "トーナメント {name} が始まりました。あなたは {players} 人中 {seed} 番シードです。セットはここで呼ばれます。",
    "The tournament {name} is over: {champion} won it.": "トーナメント {name} が終わりました。優勝は {champion} さんです。",
    "The tournament {name} is over: {champion} won it. You finished {place}.": "トーナメント {name} が終わりました。優勝は {champion} さん。最終順位: {place}。",
    "The tournament {name} was cancelled by its organizer.": "トーナメント {name} は主催者により中止されました。",
    "The tournament {name} was cancelled: not enough players.": "トーナメント {name} は中止されました: 人数不足。",
    "This tournament had no bracket.": "このトーナメントにはトーナメント表がありませんでした。",
    "This tournament is for another build of the game.": "このトーナメントは別のビルドのゲーム用です。",
    "Tournament": "トーナメント",
    "Tournament set": "トーナメントのセット",
    "Tournament set vs {name}": "{name} さんとトーナメントのセット",
    "Tournament {name} created.": "トーナメント {name} を作成しました。",
    "Tournament {name}: set {set} needs you ({why}). Report the result or reset it.": "トーナメント {name}: セット {set} に対応が必要です（{why}）。結果を入力するかリセットしてください。",
    "Tournament {name}: {code}": "トーナメント {name}: {code}",
    "Tournaments": "トーナメント",
    "Winners final": "ウィナーズ決勝",
    "Winners round {number}": "ウィナーズ {number}回戦",
    "Winners semi-final": "ウィナーズ準決勝",
    "Withdraw": "棄権",
    "Withdraw from {name}? You are out of the tournament.": "{name} を棄権しますか？ トーナメントから外れます。",
    "Write the start time as HH:MM, e.g. 20:30.": "開始時刻は HH:MM の形で書いてください（例: 20:30）。",
    "You are checked in.": "チェックインしました。",
    "You are in. Your next set is called here when its players are known.": "参加中です。次のセットは対戦相手が決まるとここで呼ばれます。",
    "You are out of {name}.": "{name} で敗退しました。",
    "You are out of {name}: {place}.": "{name} で敗退しました: {place}。",
    "You are out of {name}: {why}.": "{name} から外れました: {why}。",
    "You are out: {why}.": "敗退しました: {why}。",
    "You are signed up.": "エントリーしました。",
    "You are signed up. Check in now, or you are not in the bracket.": "エントリーしました。今チェックインしないとトーナメント表に入れません。",
    "You did not check in for {name}; the tournament started without you.": "{name} にチェックインしなかったため、トーナメントはあなた抜きで始まりました。",
    "You finished {place}.": "最終順位: {place}。",
    "You left the tournament.": "トーナメントから抜けました。",
    "You won the tournament {name}!": "トーナメント {name} で優勝しました！",
    "Your next set: {set}.": "次のセット: {set}。",
    "Your opponent did not show up: you win the set.": "相手が来ませんでした。セットはあなたの勝ちです。",
    "Your opponent is out of the tournament: you win the set.": "相手がトーナメントから外れました。セットはあなたの勝ちです。",
    "Your tournament set has no result; the organizer decides how it goes on.": "トーナメントのセットの結果が出ませんでした。この後どうするかは主催者が決めます。",
    "Your tournament set is ready": "トーナメントのセットの準備ができました",
    "accept within {seconds} s": "{seconds} 秒以内に受けてください",
    "accepted -- waiting for {name}...": "受けました -- {name} さんを待っています...",
    "best of {best}": "{best}本勝負",
    "bye": "不戦勝",
    "check-in from {time}": "{time} からチェックイン",
    "decided by the organizer": "主催者の判定",
    "did not show up": "不参加",
    "disqualified": "失格",
    "disqualified by the organizer": "主催者による失格",
    "ended {time}": "{time} に終了",
    "in 1 hour": "1 時間後",
    "in 10 minutes": "10 分後",
    "in 12 hours": "12 時間後",
    "in 15 minutes": "15 分後",
    "in 2 hours": "2 時間後",
    "in 24 hours": "24 時間後",
    "in 3 hours": "3 時間後",
    "in 30 minutes": "30 分後",
    "in 5 minutes": "5 分後",
    "in 6 hours": "6 時間後",
    "no-show": "不参加",
    "nobody": "なし",
    "none yet": "まだありません",
    "not needed": "不要",
    "or at (HH:MM)": "または時刻 (HH:MM)",
    "organizer {name}": "主催 {name}",
    "place {place}": "{place}位",
    "rated": "レート変動あり",
    "results disputed": "結果に異議",
    "started {time}": "{time} に開始",
    "starts {time}": "{time} 開始",
    "waiting": "未定",
    "withdrew": "棄権",
    "{format}, best of {best}": "{format}、{best}本勝負",
    "{name} has accepted.": "{name} さんが受けました。",
    "{name} is not online yet.": "{name} さんはまだオンラインではありません。",
    "{name} wins": "{name} の勝ち",
    "{name} wins set {set}?": "セット {set} は {name} さんの勝ちにしますか？",
    "{name}'s tournament": "{name} さんのトーナメント",
    "{players} of {max} players": "{players} / {max} 人",
    "The organizer decided the set.": "主催者がセットの結果を決めました。",
    # ---- lobby/t5lobby/i18n_known.py: lobby/t5lobby/server/tournaments.py
    "tournaments need an account": "トーナメントにはアカウントが必要です",
    "no such tournament": "そのトーナメントは存在しません",
    "only the server's organizers can create tournaments here": "このサーバーではトーナメントを作成できるのは主催者だけです",
    "a tournament name is 3-40 characters": "トーナメント名は 3～40 文字です",
    "the format is single or double elimination": "形式はシングルかダブルエリミネーションです",
    "a set is first to 2 or first to 3 games": "セットは 2 本先取か 3 本先取です",
    "the player limit is 8, 16, 32 or 64": "参加人数の上限は 8・16・32・64 のいずれかです",
    "the check-in window is 0, 5, 10, 15, 30 or 60 minutes": "チェックインの時間は 0・5・10・15・30・60 分のいずれかです",
    "seeding is random or by rating": "シードはランダムかレート順です",
    "that start time has passed": "その開始時刻はもう過ぎています",
    "a tournament starts within {days} days": "トーナメントは {days} 日以内に開始してください",
    "this server has as many tournaments as it takes; try again later": "このサーバーはこれ以上トーナメントを受け付けられません。後でもう一度試してください",
    "you already run {count} tournaments; finish or cancel one first": "すでに {count} 件のトーナメントを主催しています。先に 1 件を終えるか中止してください",
    "update the launcher to play in tournaments": "トーナメントに参加するにはランチャーを更新してください",
    "sign-up for that tournament is closed": "そのトーナメントのエントリーは締め切られました",
    "that tournament is played with another build of the game": "そのトーナメントは別のビルドのゲームで行われます",
    "that tournament is full": "そのトーナメントは満員です",
    "you are not in that tournament": "そのトーナメントにエントリーしていません",
    "that tournament is over": "そのトーナメントは終了しました",
    "check-in is not open": "チェックインは開いていません",
    "that tournament is not running": "そのトーナメントは開催中ではありません",
    "that set is not yours to play": "そのセットはあなたの試合ではありません",
    "that set is not waiting for you": "そのセットはあなたを待っていません",
    "only the organizer can do that": "それができるのは主催者だけです",
    "that tournament name is not allowed here":
        "その大会名はここでは使えません",
    "this internet address runs as many tournaments as one organizer may; finish or cancel one first":
        "このインターネットアドレスからは、主催者1人が開ける数の大会がすでに開かれています。先に1つ終えるか中止してください",
    "the organizer took you off this tournament":
        "主催者があなたをこの大会から外しました",
    "you play in that set yourself: a server tournament admin decides it (or cancel the tournament)":
        "このセットはあなた自身が対戦します。サーバーの大会管理者が決めます（または大会を中止してください）",
    "that tournament has started already": "そのトーナメントはすでに始まっています",
    "a tournament needs at least 2 players": "トーナメントには 2 人以上必要です",
    "no such player in that tournament": "そのトーナメントにそのプレイヤーはいません",
    "that player is out already": "そのプレイヤーはすでに敗退しています",
    "no such set": "そのセットは存在しません",
    "that set is decided; override it instead": "そのセットは決着済みです。代わりに結果を修正してください",
    "only a played set can be overridden": "結果を修正できるのは行われたセットだけです",
    "that set has not been played": "そのセットはまだ行われていません",
    "that set was a walkover": "そのセットは不戦勝でした",
    "set {set} was already played from this result; reset it first": "この結果でセット {set} がすでに行われました。先にそのセットをリセットしてください",
    "finish your match first, then accept the tournament set": "先に対戦を終えてから、トーナメントのセットを受けてください",
    "finish your set first, then accept the tournament set": "先にセットを終えてから、トーナメントのセットを受けてください",
    "you are in a tournament set; finish it first": "トーナメントのセット中です。先に終えてください",
    "that player is playing a tournament set": "そのプレイヤーはトーナメントのセット中です",
    "your tournament set is ready; accept it first": "トーナメントのセットの準備ができました。先に受けてください",
    "that player has a tournament set to play": "そのプレイヤーにはこれから行うトーナメントのセットがあります",
    # ---- lobby/t5lobby/theme.py
    "Good connection": "良好な接続",
    "Laggy connection": "ラグのある接続",
    "OK connection": "まずまずの接続",
    "Ping not known yet": "Ping はまだ不明",
    "sec": "秒",
    # ---- lobby/t5lobby/tk_tab.py
    "Leave set (counts as a loss)": "セットから抜ける（負け扱い）",
    "Leave the ranked set": "Ranked セットから抜ける",
    "Leave this ranked set?\n\nLeaving a ranked set counts as losing it.":
        "この Ranked セットから抜けますか？\n\nRanked セットから抜けると負けになります。",
    "Rematch? (a new set)": "Rematch？（新しいセット）",
    "in a room": "ルーム内",
    "in lobby": "ロビー",
    "matching": "対戦準備中",
    "searching": "検索中",
    "full": "満員",
    "open": "募集中",
    "Result confirmed": "結果確定",
    "Result recorded (your opponent did not report)": "結果を記録しました（相手が未報告）",
    "Match decided by forfeit": "棄権により決着",
    "Result decided by the games' state": "ゲームの状態で結果を判定",
    "You and your opponent reported different results -- not counted":
        "あなたと相手の報告した結果が違います -- カウントされません",
    "No result": "結果なし",
    "confirmed": "確定",
    "forfeit": "棄権",
    "one-sided": "片側のみ",
    "disputed": "食い違い",
    "resolved": "解決済み",
    "void": "無効",
    "draw": "引き分け",
    "loss": "負け",
    "win": "勝ち",
    "the two games went out of sync": "2つのゲームの同期がずれました",
    "too short to count": "短すぎてカウントされません",
    "a game crashed": "ゲームがクラッシュしました",
    "the reports disagreed": "報告内容が一致しませんでした",
    "left right away": "すぐに退出",
    "a player left": "プレイヤーが退出しました",
    "a player lost the connection": "プレイヤーの接続が切れました",
    "a player did not report": "プレイヤーが報告しませんでした",
    "the connection between the games failed": "ゲーム間の接続に失敗しました",
    "both players left": "両方のプレイヤーが退出しました",
    "no result in time": "時間内に結果なし",
    "repeated crashes count as losses": "繰り返しのクラッシュは負けとして扱われます",
    "repeated early quits": "早期退出の繰り返し",
    "repeated missing reports": "未報告の繰り返し",
    "scores differed": "スコアが一致しませんでした",
    "the fight ended without a winner": "試合は勝者なしで終わりました",
    "Match declined.": "対戦が断られました。",
    "Nobody accepted in time.": "時間内に誰も受けませんでした。",
    "Your opponent left.": "相手が退出しました。",
    "No UDP connection to the lobby server (firewall?).":
        "ロビーサーバーと UDP で接続できません（ファイアウォール？）。",
    "Could not connect the two PCs, not even through the relay.":
        "2台のPCを接続できませんでした。中継経由でも接続できません。",
    "The lobby server's relay is full; try again in a moment.":
        "ロビーサーバーの中継が満員です。少ししてからもう一度試してください。",
    "Challenge cancelled.": "対戦申し込みが取り消されました。",
    "Challenge declined.": "対戦申し込みが断られました。",
    "Challenge expired.": "対戦申し込みの期限が切れました。",
    "direct": "直接",
    "via the lobby server's relay": "ロビーサーバーの中継経由",
    "via the relay server {name}": "中継サーバー {name} 経由",
    "Lobby error: {error}": "ロビーエラー：{error}",
    "guest": "ゲスト",
    "Not connected. Ranked needs an account; guests play casual matches.":
        "未接続。Ranked にはアカウントが必要です。ゲストはカジュアル対戦をプレイします。",
    "Passwords are only sent to servers on this PC / your network, or over an encrypted "
    "(TLS) connection.":
        "パスワードは、このPC・自分のネットワーク上のサーバーか、暗号化（TLS）接続でのみ送信されます。",
    "Select a player and choose Profile, or double-click a player in the leaderboard.":
        "プレイヤーを選んで「プロフィール」を押すか、ランキングでプレイヤーをダブルクリックしてください。",
    "{name} (guest, casual matches only)": "{name}（ゲスト、カジュアル対戦のみ）",
    "{record} this session": "このセッション {record}",
    "rating {rating}": "レート {rating}",
    "main {character}": "持ちキャラ {character}",
    "server ping {ms} ms": "サーバー Ping {ms}ms",
    "encrypted": "暗号化",
    "[Server: {notice}]": "[サーバー：{notice}]",
    "Server notice: {notice}": "サーバーからのお知らせ：{notice}",
    "The game is not built.": "ゲームがビルドされていません。",
    "This game is the European version ({title_id}): it plays offline only for now. Online play for the European version comes in a later update; it never plays against the US version (NPUB30009).":
        "このゲームは欧州版（{title_id}）です：今のところオフラインでのみ遊べます。欧州版のオンライン対戦は今後のアップデートで対応します。北米版（NPUB30009）とは対戦しません。",
    "Your game is the European version: offline only for now":
        "あなたのゲームは欧州版です：今のところオフラインのみ",
    "The European version ({title_id}) plays its offline modes. Online play for it comes in a later update; until then online play needs the US version (NPUB30009). European and US games never play each other online.":
        "欧州版（{title_id}）はオフラインのモードで遊べます。欧州版のオンライン対戦は今後のアップデートで対応します。それまではオンライン対戦に北米版（NPUB30009）が必要です。欧州版と北米版がオンラインで対戦することはありません。",
    "Build stamp: the game is {title_id}.":
        "ビルドスタンプ：ゲームは {title_id} です。",
    "This Mac build has no online play. For a test match: tools/build_game.py --macos-online (docs/MACOS_ONLINE_TEST.md).":
        "この Mac 版ビルドにはオンライン対戦がありません。テスト対戦には: tools/build_game.py --macos-online (docs/MACOS_ONLINE_TEST.md)。",
    "Cannot read the build's identity: {error}": "ビルドの識別情報を読み込めません：{error}",
    "Enter a password (6 characters or more), or play as a guest.":
        "パスワード（6文字以上）を入力するか、ゲストでプレイしてください。",
    "Connecting to {server}...": "{server} に接続中...",
    "Pick a character, then Ranked match (accounts) or Quick match.":
        "キャラクターを選んでから、Ranked 対戦（アカウント）か Quick Match を選んでください。",
    "Encrypted connection (TLS).": "暗号化された接続（TLS）。",
    "(logged in with your saved login)": "（保存されたログインでログインしました）",
    "In the lobby.": "ロビーにいます。",
    "Your saved login has expired; log in with your password.":
        "保存されたログインの期限が切れました。パスワードでログインしてください。",
    "Create account": "アカウント作成",
    "Type the password again:": "パスワードをもう一度入力してください：",
    "The two passwords differ.": "2つのパスワードが一致しません。",
    "Closing the running game for the online match...": "オンライン対戦のため、起動中のゲームを閉じています...",
    "Also forget the saved login on this PC?\n\n(No = you are logged in automatically "
    "next time.)":
        "このPCに保存されたログインも削除しますか？\n\n（いいえ = 次回は自動でログインします。）",
    "Log out": "ログアウト",
    "Not connected.": "未接続。",
    "Change password": "パスワード変更",
    "Current password:": "現在のパスワード：",
    "New password (6 characters or more):": "新しいパスワード（6文字以上）：",
    "New password again:": "新しいパスワード（確認）：",
    "The two new passwords differ.": "2つの新しいパスワードが一致しません。",
    "Password changed. Saved logins on other PCs have ended.":
        "パスワードを変更しました。他のPCに保存されたログインは無効になりました。",
    "Recovery codes": "復旧コード",
    "Your password (the old codes stop working):": "パスワード（古いコードは使えなくなります）：",
    "Save recovery codes": "復旧コードを保存",
    "T5DR Online recovery codes for {name} on {server}": "{server} の {name} 用 T5DR Online 復旧コード",
    "Forgot password": "パスワードを忘れた",
    "Account name:": "アカウント名：",
    "One of your recovery codes (XXXX-XXXX-XXXX):": "復旧コードのいずれか（XXXX-XXXX-XXXX）：",
    "Password reset. {count} recovery code(s) left. Log in with the new password.":
        "パスワードを再設定しました。復旧コードの残りは {count} 個です。新しいパスワードでログインしてください。",
    "Server certificate": "サーバー証明書",
    "For a server with its own (self-signed) certificate: its SHA-256 fingerprint, from "
    "whoever runs it.\nEmpty = no pinning (use tls://host:port for a server with a "
    "normal certificate).":
        "独自（自己署名）証明書のサーバー用：運営者から受け取った SHA-256 フィンガープリント。\n空欄 = 固定しない（通"
        "常の証明書のサーバーには tls://host:port を使用）。",
    "Searching for an opponent...": "対戦相手を検索中...",
    "Searching for an opponent (ranked: similar rank and a good connection, strict: "
    "within 150 rating points -- this can take a while)...":
        "対戦相手を検索中（Ranked：近いランクと良好な接続、厳密：レート差150以内 -- 時間がかかることがあります）...",
    "Searching for an opponent (ranked: similar rank and a good connection)...":
        "対戦相手を検索中（Ranked：近いランクと良好な接続）...",
    "Select a room first.": "先にルームを選んでください。",
    "Select an opponent in the list first.": "先にリストから対戦相手を選んでください。",
    "Challenge sent.": "対戦を申し込みました。",
    "Challenge sent": "対戦を申し込みました",
    "Blocked players": "ブロックしたプレイヤー",
    "You are never matched with these players (ranked, quick matches, rooms, challenges, "
    "rematches). They are not told. Accounts stay blocked; a guest is blocked until you "
    "log out.":
        "これらのプレイヤーとは今後マッチングしません（Ranked、Quick Match、ルーム、対戦申し込み、Rematch）。相手には"
        "通知されません。アカウントはブロックされたままで、ゲストはログアウトするまでブロックされます。",
    "Unblocked {name}.": "{name} さんのブロックを解除しました。",
    "Unblock": "ブロック解除",
    "Block player": "プレイヤーをブロック",
    "Block {name}?\n\nYou will not be matched with them again. They are not told. You "
    "can unblock them under \"Blocked players...\".":
        "{name} さんをブロックしますか？\n\n今後マッチングしません。相手には通知されません。「ブロックしたプレイヤー"
        "...」で解除できます。",
    "Blocked {name}. You will not be matched again.": "{name} さんをブロックしました。今後マッチングしません。",
    "you": "自分",
    "{name} -- {rank}": "{name} -- {rank}",
    "Rating {rating} +/- {rd}": "レート {rating} +/- {rd}",
    "(provisional)": "（暫定）",
    "#{place} on the leaderboard": "ランキング {place} 位",
    "Record {record}": "戦績 {record}",
    "Played {games}: {wins} won, {losses} lost, win rate {rate} %": "対戦 {games}：{wins}勝 {losses}敗、勝率 {rate} %",
    "Ranked {games}, {rate} % won": "Ranked {games}、勝率 {rate} %",
    "Casual {games}, {rate} % won": "カジュアル {games}、勝率 {rate} %",
    "Stats": "統計",
    "Community stats": "コミュニティ統計",
    "Accounts": "アカウント",
    "Matches": "対戦数",
    "Ranked matches": "Ranked対戦",
    "Last 24 hours": "直近24時間",
    "{matches} matches, {players} players": "{matches}対戦、{players}人",
    "as of {when}": "{when} 時点",
    "All": "すべて",
    "Fighter": "キャラクター",
    "Wins": "勝利",
    "Win rate": "勝率",
    "Picked": "使用率",
    "No numbers yet.": "まだデータがありません。",
    "This lobby server has no stats page yet (it comes with server 1.1.5).": "このロビーサーバーにはまだ統計がありません（サーバー1.1.5で追加されます）。",
    "Win rate per match; a mirror match counts as one win and one loss. Grey: fewer than {count} matches, not much to go on yet. Click a column to sort.":
        "勝率は対戦ごと。同キャラ対戦は1勝1敗として数えます。灰色：対戦数が{count}未満で、まだ参考程度です。列をクリックで並べ替え。",
    "ranked matches {count}": "Ranked 対戦 {count}",
    "highest rank {rank}": "最高段位 {rank}",
    "Characters: {list}": "キャラクター：{list}",
    "Matches without result caused in the last 24 h: {count}": "直近24時間に自分が原因の結果なし対戦：{count}",
    "Recovery codes left: {count}": "復旧コードの残り：{count}",
    "{you} vs {opponent}": "{you} vs {opponent}",
    "casual": "カジュアル",
    "Opponent: {name} ({rank}, {rating})": "対戦相手：{name}（{rank}、{rating}）",
    "RANKED": "RANKED",
    "rematch": "Rematch",
    "{name} ({rank}) challenges you": "{name}（{rank}）さんから対戦の申し込み",
    "Accept": "受ける",
    "Decline": "断る",
    "Challenge {state}.": "対戦申し込み：{state}。",
    "connecting...": "接続中...",
    "Your opponent accepted.": "相手が受けました。",
    "Match cancelled ({reason}).": "対戦が中止されました（{reason}）。",
    "Ranked match vs {name}": "{name} さんと Ranked 対戦",
    "Casual match vs {name}": "{name} さんとカジュアル対戦",
    "{p1} vs {p2}": "{p1} vs {p2}",
    "ping {ms} ms ({how}), input delay {frames} frames ({delay_ms} ms)":
        "Ping {ms}ms（{how}）、入力遅延 {frames} フレーム（{delay_ms}ms）",
    "Lost the lobby connection -- reconnecting (your match goes on)...":
        "ロビーとの接続が切れました -- 再接続中（対戦は続きます）...",
    "Reconnected to the lobby.": "ロビーに再接続しました。",
    "Lost the lobby connection: {reason}": "ロビーとの接続が切れました：{reason}",
    "Lost the connection to the lobby server.": "ロビーサーバーとの接続が切れました。",
    "Removed from the lobby: {reason}": "ロビーから退出させられました：{reason}",
    "The game closed. How did the match against {opponent} end?":
        "ゲームが終了しました。{opponent} さんとの対戦の結果は？",
    "I won": "勝った",
    "I lost": "負けた",
    "Draw": "引き分け",
    "I quit": "棄権した",
    "{opponent} wants a rematch": "{opponent} さんが Rematch を希望しています",
    "Rematch": "Rematch",
    "No thanks": "やめておく",
    "Result sent; waiting for your opponent's report...": "結果を送信しました。相手の報告を待っています...",
    "Rematch offered; waiting for your opponent...": "Rematch を申し込みました。相手を待っています...",
    "(other version)": "（別バージョン）",
    "other version": "別バージョン",
    "ranked": "Ranked",
    "Searching... ({ranked} in the ranked queue, {quick} quick)":
        "検索中...（Ranked 待ち {ranked} 人、Quick Match {quick} 人）",
    "ping about {ms} ms (estimated; measured directly once you both accept)":
        "Ping 約 {ms}ms（推定。両者が受けると直接測定）",
    "ping not known yet": "Ping はまだ不明",
    "Opponent found": "対戦相手が見つかりました",
    "accept within {seconds} s?": "{seconds} 秒以内に受けますか？",
    "waiting for the opponent...": "相手を待っています...",
    "Lag check: {text}": "ラグチェック：{text}",
    "You left after the lag check. No penalty, no rating change.":
        "ラグチェック後に退出しました。ペナルティもレートの変動もありません。",
    "Your opponent left after the lag check. No penalty for anyone.":
        "相手がラグチェック後に退出しました。どちらにもペナルティはありません。",
    "Your opponent left. The set is over.": "相手が退出しました。セットは終了です。",
    "Rematch {name}": "{name} さんと Rematch",
    "Next game": "次の試合",
    "Leave": "退出",
    "Block {name}": "{name} をブロック",
    "Leave: too laggy": "退出：ラグがひどい",
    "You lost.": "負けました。",
    "You won.": "勝ちました。",
    "rating {rating} ({delta})": "レート {rating}（{delta}）",
    "PROMOTED to {rank}!": "{rank} に昇段！",
    "demoted to {rank}": "{rank} に降段",
    "placed at {rank}": "{rank} に認定",
    "placement {done}/{total}": "段位認定 {done}/{total}",
    "your opponent": "相手",
    "Rematch?": "Rematch？",
    "Controller off.": "コントローラーオフ。",
    "No controller found.": "コントローラーが見つかりません。",
    "Controller: {summary}": "コントローラー：{summary}",
    "Cannot start the lobby server: {error}": "ロビーサーバーを起動できません：{error}",
    "Stop hosting": "ホストを停止",
    "Starting a lobby server on this PC and asking the router to forward its ports...":
        "このPCでロビーサーバーを起動し、ルーターにポート転送を依頼しています...",
    "Starting a lobby server on this PC...": "このPCでロビーサーバーを起動しています...",
    "<your public IP>": "<あなたのグローバルIP>",
    "Hosting. Friends paste this as their Server (copied to the clipboard):\n  {share}":
        "ホスト中です。フレンドはこれをサーバー欄に貼り付けます（クリップボードにコピー済み）：\n  {share}",
    "\n  same network: {lan}": "\n  同じネットワーク：{lan}",
    "\n  Forward TCP+UDP 7781 and UDP 7782 on your router (or tick 'Open router ports').":
        "\n  ルーターで TCP+UDP 7781 と UDP 7782 を転送してください（または「ルーターのポートを開く」にチェック）。",
    "Hosting a lobby on this PC. Log in to join it yourself.":
        "このPCでロビーをホスト中です。自分も入るにはログインしてください。",
    "Hosting failed: {message}": "ホストに失敗しました：{message}",
    "Host for friends": "フレンド用ホスト",
    "The lobby server stopped (exit code {code}); see its log in {folder}.":
        "ロビーサーバーが停止しました（終了コード {code}）。ログは {folder} にあります。",
    "Stopped hosting.": "ホストを停止しました。",
    # in-game character select (branch ingame-select)
    "Pick your fighter in the game ({secs} s; Select = random; no pick = the character set here).":
        "ゲーム内でキャラクターを選んでください（{secs} 秒、Select = ランダム、未選択ならここで設定したキャラクター）"
        "。",
    "Waiting for your opponent to pick...": "相手のキャラクター選択を待っています...",
    "Ranked match (accounts) or Quick match; then pick your fighter in the game (Select = random). The character here is used when you do not pick in time.":
        "Ranked 対戦（アカウント）か Quick Match を選び、ゲーム内でキャラクターを選びます（Select = ランダム）。時間内"
        "に選ばないとここのキャラクターになります。",
    "pick your fighter in the game ({secs} s)": "ゲーム内でキャラクター選択（{secs} 秒）",
    "(locked for this ranked set)": "（この Ranked セット中は固定）",
    "Pick your fighter in the game": "ゲーム内でキャラクターを選んでください",
    "Your opponent is picking": "相手が選択中",
    # ---- lobby/t5lobby/tk_views.py
    "Rank": "段位",
    "Rating": "レート",
    "Record": "戦績",
    "Main": "持ちキャラ",
    "Ping": "Ping",
    "Room": "ルーム",
    "Status": "状態",
    "Owner": "作成者",
    "Place": "順位",
    "State": "状態",
    "When": "日時",
    "Characters": "キャラクター",
    "Opponent": "対戦相手",
    "Result": "結果",
    "Score": "ラウンド",
    "Check the server address and your internet connection, then try again.":
        "サーバーアドレスとインターネット接続を確認して、もう一度試してください。",
    "Check your internet connection, then try again.": "インターネット接続を確認して、もう一度試してください。",
    "The server is slow or gone; try again in a minute.":
        "サーバーが遅いか停止しています。1分後にもう一度試してください。",
    "Log in again.": "もう一度ログインしてください。",
    "Ask whoever runs the server for its current fingerprint (\"Server certificate...\").":
        "サーバーの運営者に現在のフィンガープリントを聞いてください（「サーバー証明書...」）。",
    "Check the spelling, or use \"Forgot password...\".":
        "つづりを確認するか、「パスワードを忘れた...」を使ってください。",
    "Check the name and the code; each code works once.": "名前とコードを確認してください。各コードは1回だけ使えます。",
    "Pick another name, or wait a minute if that was you.": "別の名前にするか、自分だった場合は1分待ってください。",
    "Log in with that account's password, or pick another name.":
        "そのアカウントのパスワードでログインするか、別の名前にしてください。",
    "Pick another name.": "別の名前にしてください。",
    "Update the game to the release this server asks for.":
        "このサーバーが求めるリリースにゲームをアップデートしてください。",
    "You both need the same release of the game.": "お互いに同じリリースのゲームが必要です。",
    "Update the launcher to the newest release.": "ランチャーを最新リリースにアップデートしてください。",
    "Create an account (free) to play ranked.": "Ranked をプレイするには（無料の）アカウントを作成してください。",
    "Pick another room or create your own.": "別のルームを選ぶか、自分で作成してください。",
    "Log in with your password.": "パスワードでログインしてください。",
    "Build the game on the Build tab first.": "先にビルドタブでゲームをビルドしてください。",
    "Allow T5DR Online through the Windows firewall, then search again.":
        "Windows ファイアウォールで T5DR Online を許可してから、もう一度検索してください。",
    "Try again; if it keeps failing, check your firewall or router.":
        "もう一度試してください。失敗が続く場合はファイアウォールかルーターを確認してください。",
    "Log in again; your settings are kept.": "もう一度ログインしてください。設定はそのまま残ります。",
    "Type the same password twice.": "同じパスワードを2回入力してください。",
    "Find a new opponent.": "新しい対戦相手を探してください。",
    "Check the Play offline tab: does the game start there?":
        "オフラインプレイタブを確認してください：そこではゲームが起動しますか？",
    "Against other players over the internet. Log in or play as a guest; the game starts "
    "by itself, straight into the fight, and the result comes back here.":
        "インターネットで他のプレイヤーと対戦します。ログインするかゲストでプレイしてください。ゲームは自動で起動して"
        "対戦から始まり、結果はここに戻ってきます。",
    "Server": "サーバー",
    "Server certificate...": "サーバー証明書...",
    "Name": "名前",
    "Log in": "ログイン",
    "Password": "パスワード",
    "Password again": "パスワード（確認）",
    "Name: 2 to 16 letters, digits, spaces or _-.[]()!?": "名前：2〜16文字の文字、数字、スペース、_-.[]()!?",
    "Password: 6 to 128 characters": "パスワード：6〜128文字",
    "Both passwords the same": "2つのパスワードが一致",
    "You get recovery codes once: the only way back in if you forget the password":
        "復旧コードは一度だけ表示されます：パスワードを忘れたときに戻れる唯一の方法です",
    "Remember me": "ログイン状態を保持",
    "Forgot password...": "パスワードを忘れた...",
    "Casual matches with the name above, no account and no password. Ranked matches, the "
    "leaderboard and your match history need an account.":
        "上の名前でアカウントもパスワードもなしにカジュアル対戦ができます。Ranked 対戦、ランキング、対戦履歴にはアカウ"
        "ントが必要です。",
    "Play as guest": "ゲストでプレイ",
    "Runs a lobby on this PC. Your friends type the address it shows into their Server "
    "box.":
        "このPCでロビーを動かします。フレンドは表示されたアドレスをサーバー欄に入力します。",
    "Open router ports (UPnP)": "ルーターのポートを開く（UPnP）",
    "How it works": "遊び方",
    "Quick match (casual) or Ranked match (account).": "Quick Match（カジュアル）か Ranked 対戦（アカウント）。",
    "An opponent is found: accept within 15 seconds.": "対戦相手が見つかったら15秒以内に受けてください。",
    "The game opens straight into the fight.": "ゲームは対戦画面から直接始まります。",
    "The result comes back here: rematch or next game.": "結果はここに戻ります：Rematch か次の試合へ。",
    "With a controller: A accepts, B declines.": "コントローラー：A で受ける、B で断る。",
    "Online nobody can pause the fight: Start does not open the pause menu.":
        "オンラインでは誰も対戦をポーズできません。Start でポーズメニューは開きません。",
    "Intros are skipped by themselves; the replay after a round once both players have pressed Start.":
        "イントロは自動でスキップされます。ラウンド後のリプレイは、両プレイヤーが Start を押すとスキップされます。",
    "Lobby": "ロビー",
    "Leaderboard": "ランキング",
    "Profile": "プロフィール",
    "My profile": "マイプロフィール",
    "Find an opponent online": "オンラインで対戦相手を探す",
    "Character": "キャラクター",
    "Choose your fighter": "キャラクターを選ぶ",
    "{star} your main: {character}": "{star} メイン：{character}",
    "Arrow keys move, Enter picks, Esc closes. With a controller: Cross / A picks, Circle / B closes.":
        "矢印キーで移動、Enterで決定、Escで閉じる。コントローラー：× / Aで決定、○ / Bで閉じる。",
    "Locked for this ranked set": "この Ranked セット中は固定",
    "Ranked match": "Ranked 対戦",
    "Quick match": "Quick Match",
    "Casual: the lowest ping first": "カジュアル：Ping が低い相手から",
    "Strict (ranked: +-150 rating)": "厳密（Ranked：レート ±150）",
    "Searching": "検索中",
    "Looking for an opponent": "対戦相手を探しています",
    "Searching for": "検索時間",
    "Stop searching": "検索をやめる",
    "In match": "対戦中",
    "CASUAL": "カジュアル",
    "Input delay": "入力遅延",
    "Connection": "接続",
    "Players online": "オンラインのプレイヤー",
    "Challenge": "対戦を申し込む",
    "Rooms": "ルーム",
    "Create room": "ルーム作成",
    "Join room": "ルームに入る",
    "Leave room": "ルームから出る",
    "Chat": "チャット",
    "Send": "送信",
    "Refresh": "更新",
    "Order: rating minus twice its uncertainty (a few matches are needed to climb). '?' "
    "= provisional.":
        "並び順：レートから不確かさの2倍を引いた値（上がるには何戦か必要です）。「?」= 暫定。",
    "Your account": "アカウント",
    "Blocked players...": "ブロックしたプレイヤー...",
    "Change password...": "パスワード変更...",
    "New recovery codes...": "新しい復旧コード...",
    "Dismiss": "閉じる",
    "Use a controller here": "ここでコントローラーを使う",
    "none open": "募集中のルームなし",
    "Nobody else is online right now. Ranked match and Quick match keep looking until someone comes.":
        "今はほかに誰もオンラインにいません。Ranked 対戦と Quick Match は誰かが来るまで探し続けます。",
    "No rooms open. Create one: friends can join it and play in turn.":
        "募集中のルームはありません。ルームを作ると、フレンドが入って交代で対戦できます。",
    "Nobody has a ranked result yet. Win a ranked set to be the first.":
        "まだ Ranked の結果がある人はいません。Ranked セットに勝って一番乗りしよう。",
    "In your room “{name}”. Waiting for a second player...":
        "自分のルーム「{name}」。2人目のプレイヤーを待っています...",
    "In the room “{name}”. The match starts when you are both ready.":
        "ルーム「{name}」。お互いの準備ができたら対戦が始まります。",
    "Hosting. Friends type this as their Server:\n{share}":
        "ホスト中です。フレンドはこれをサーバー欄に入力します：\n{share}",
    "Same network: {lan}": "同じネットワーク：{lan}",
    "Guest · casual matches": "ゲスト · カジュアル対戦",
    "Rating {rating}  ·  {record}": "レート {rating}  ·  {record}",
    "Main: {character}": "持ちキャラ：{character}",
    "Server ping {ms} ms": "サーバー Ping {ms}ms",
    "Create an account to play ranked": "Ranked をプレイするにはアカウントを作成",
    "Rated: close to your rank, good connection": "レート変動あり：近いランク、良好な接続",
    "Similar rank and a good connection, strict: within 150 rating points (this can take "
    "a while).":
        "近いランクと良好な接続、厳密：レート差150以内（時間がかかることがあります）。",
    "Similar rank and a good connection.": "近いランクと良好な接続。",
    "The opponent with the lowest ping first.": "Ping が最も低い相手から。",
    "{ranked} in the ranked queue  ·  {quick} in quick match": "Ranked 待ち {ranked} 人  ·  Quick Match {quick} 人",
    "Character select": "キャラクター選択",
    "Stage select": "ステージ選択",
    "Match over": "対戦終了",
    "Waiting for the next match": "次の対戦を待っています",
    "Your game is running": "ゲーム起動中",
    "Starting the game...": "ゲームを起動中...",
    "Waiting for the game...": "ゲームを待っています...",
    "vs your opponent": "vs 相手",
    "vs {name}": "vs {name}",
    "{count} frame  ({ms} ms)": "{count} フレーム  ({ms}ms)",
    "{count} frames  ({ms} ms)": "{count} フレーム  ({ms}ms)",
    "Direct": "直接",
    "Local network": "ローカルネットワーク",
    "Relay (lobby server)": "中継（ロビーサーバー）",
    "Relay ({name})": "中継（{name}）",
    "Guest": "ゲスト",
    "{rank}  ·  rating {rating}": "{rank}  ·  レート {rating}",
    "SET · GAME {game}": "セット · 第{game}試合",
    "Opponent hidden": "相手は非公開",
    "Name and side are shown once you both accept.": "お互いが受けると名前とサイドが表示されます。",
    "(estimated before you connect)": "（接続前の推定）",
    "(measured in your last match together)": "（前回の対戦で測定）",
    "ping {ms} ms (measured in your last match together)": "Ping {ms}ms（前回の対戦で測定）",
    "probably a direct connection": "おそらく直接接続",
    "probably over the local network": "おそらくローカルネットワーク経由",
    "probably through a relay server": "おそらく中継サーバー経由",
    "Accepted. Waiting for your opponent...": "受けました。相手を待っています...",
    "Match ready": "対戦準備完了",
    "Connecting the two games...": "2つのゲームを接続中...",
    "wants to play you. Accept to start the match.": "さんから対戦の申し込みです。受けると対戦が始まります。",
    "YOU WIN": "勝利",
    "YOU LOSE": "敗北",
    "DRAW": "引き分け",
    "MATCH OVER": "対戦終了",
    "NO CONTEST": "ノーコンテスト",
    "Casual match": "カジュアル対戦",
    "ROUNDS  (P1 – P2)": "ラウンド  (P1 – P2)",
    "ROUNDS  (YOU – THEM)": "ラウンド  (自分 – 相手)",
    "GAMES  (YOU – THEM)": "試合  (自分 – 相手)",
    "SET WON": "セット勝利",
    "The game waits here for your next match: Rematch, Next game or Leave.":
        "ゲームはここで次の対戦を待ちます：Rematch、次の試合、または退出。",
    "SET LOST": "セット敗北",
    "Ranked set": "Ranked セット",
    "Ranked set vs {name}": "{name} さんと Ranked セット",
    "RANKED SET · BEST OF {best}": "RANKED セット · {best}本勝負",
    "Game {number} of {best} starts in": "{best}試合中の第{number}試合開始まで",
    "Game {number} of {best} again (no winner), starts in":
        "{best}試合中の第{number}試合をやり直し（勝者なし）、開始まで",
    "Rating {rating}": "レート {rating}",
    "PROMOTED": "昇段",
    "DEMOTED": "降段",
    "PLACED": "段位認定",
    "Placement match {done} of {total}": "段位認定戦 {done}/{total}",
    "Lag check": "ラグチェック",
    "Rematch offered. Waiting for {opp}...": "Rematch を申し込みました。{opp} さんを待っています...",
    "Back to the lobby": "ロビーに戻る",
    "New recovery codes": "新しい復旧コード",
    "Your account is ready": "アカウントの準備ができました",
    "These codes are the only way back into your account if you forget the password "
    "(there is no e-mail). Each code works once. Write them down or save them somewhere "
    "safe -- they are not shown again.":
        "これらのコードは、パスワードを忘れたときにアカウントに戻れる唯一の方法です（メールはありません）。各コードは"
        "1回だけ使えます。書き留めるか安全な場所に保存してください -- 二度と表示されません。",
    "Save to a file...": "ファイルに保存...",
    "I have saved them": "保存しました",
    # ---- friends (tk_tab.py, tk_views.py)
    "Request": "申請",
    "Friends": "フレンド",
    "Invite to a match": "対戦に招待",
    "Invite to my room": "自分のルームに招待",
    "Invite in {seconds} s": "招待まであと {seconds} 秒",
    "Remove": "削除",
    "Invite a friend who is online: one click on their side starts a casual match, or brings them into your room.":
        "オンラインのフレンドを招待しましょう：相手のワンクリックでカジュアル対戦が始まるか、あなたのルームに入ります"
        "。",
    "Add a friend": "フレンドを追加",
    "Send request": "申請を送る",
    "Their account name. They become your friend when they accept.":
        "相手のアカウント名。相手が承認するとフレンドになります。",
    "Requests": "申請",
    "Take back": "取り消す",
    "Invite from a friend": "フレンドからの招待",
    "invites you to the room “{room}”. Accept to join it; the match starts at once.":
        "さんからルーム「{room}」への招待です。受けると入室し、対戦がすぐ始まります。",
    "invites you to a casual match. Accept to start it.": "さんからカジュアル対戦への招待です。受けると始まります。",
    "Check the spelling: friends are added by their account name.":
        "つづりを確認してください：フレンドはアカウント名で追加します。",
    "in a match": "対戦中",
    "offline": "オフライン",
    "older launcher: no invites": "古いランチャー：招待不可",
    "Friends ({count})": "フレンド（{count}）",
    "offline, last seen {when}": "オフライン（{when}）",
    "Friends need an account. Log in with one to add friends and invite them.":
        "フレンド機能にはアカウントが必要です。アカウントでログインすると、フレンドの追加や招待ができます。",
    "This lobby server has no friends list (it needs version 1.1.2 or newer).":
        "このロビーサーバーにはフレンドリストがありません（バージョン 1.1.2 以降が必要）。",
    "wants to be your friend": "フレンド申請が届いています",
    "asked: waiting for an answer": "返事待ち",
    "{online} online · {count} of {max}": "オンライン {online} 人 · {count}/{max}",
    "Your friends see when you are online. Invite one who is online to play.":
        "フレンドにはあなたがオンラインかどうかが見えます。オンラインのフレンドを招待して遊びましょう。",
    "No friends yet. Add one by account name: they become your friend when they accept.":
        "まだフレンドがいません。アカウント名で追加しましょう：相手が承認するとフレンドになります。",
    "Cancel the invite": "招待を取り消す",
    "You and {name} are friends now.": "{name} さんとフレンドになりました。",
    "Friend request sent to {name}. They become your friend when they accept.":
        "{name} さんにフレンド申請を送りました。相手が承認するとフレンドになります。",
    "Request from {name} declined.": "{name} さんからの申請を断りました。",
    "Request to {name} taken back.": "{name} さんへの申請を取り消しました。",
    "Remove friend": "フレンドを削除",
    "Remove {name} from your friends?\n\nYou can ask again later; they have to accept again.":
        "{name} さんをフレンドから削除しますか？\n\n後でまた申請できますが、相手がもう一度承認する必要があります。",
    "{name} is no longer your friend.": "{name} さんはフレンドではなくなりました。",
    "Select a friend in the list first.": "先にリストからフレンドを選んでください。",
    "Invite sent to {name}; waiting for an answer ({seconds} s)...":
        "{name} さんに招待を送りました。返事を待っています（{seconds} 秒）...",
    "{name} ({rank}) invites you to the room “{room}”": "{name}（{rank}）さんからルーム「{room}」への招待",
    "{name} ({rank}) invites you to a casual match": "{name}（{rank}）さんからカジュアル対戦への招待",
    "The invite from {name} ran out.": "{name} さんからの招待の期限が切れました。",
    "The invite from {name} ended.": "{name} さんからの招待は終了しました。",
    "{name} declined your invite.": "{name} さんが招待を断りました。",
    "{name} did not answer your invite.": "{name} さんから招待への返事がありませんでした。",
    "The invite to {name} ended.": "{name} さんへの招待は終了しました。",
    "{name} wants to be your friend: see the Friends tab.":
        "{name} さんからフレンド申請が届きました：フレンドタブを見てください。",
    "{name} accepted your friend request.": "{name} さんがフレンド申請を承認しました。",
    "{name} declined your friend request.": "{name} さんがフレンド申請を断りました。",

    # ---- launcher/replays_ui.py, launcher/t5dr_launcher.pyw (Replays tab), problem_report.py
    "Replays":
        "リプレイ",
    "Every online match is saved here. Watch plays it back in the game exactly as it was played: the same inputs frame by frame, checked against the live match while it plays.":
        "オンライン対戦はすべてここに保存されます。「見る」を押すと、プレイされたとおりにゲーム内で再生します：同じ入力を1フレームずつ再現し、再生中にライブの対戦と照合します。",
    "Date":
        "日付",
    "Fighters":
        "キャラクター",
    "Netcode":
        "ネットコード",
    "WATCH":
        "見る",
    "Stop replay":
        "リプレイを停止",
    "Delete":
        "削除",
    "Open replays folder":
        "リプレイフォルダーを開く",
    "Save online matches as replays":
        "オンライン対戦をリプレイとして保存する",
    "Watch replay": "リプレイを見る",
    "{count} of these matches have a replay on this PC ({mark}). Select one to watch it.":
        "このうち{count}件の対戦はこのPCにリプレイがあります（{mark}）。選ぶと見られます。",
    "None of these matches has a replay on this PC (replays are saved on the PC that played, while \"Save online matches as replays\" is on).":
        "このPCにはどの対戦のリプレイもありません（リプレイは「オンライン対戦をリプレイとして保存する」がオンの間、対戦したPCに保存されます）。",
    "No replay of this match on this PC.": "この対戦のリプレイはこのPCにありません。",
    "{fighters}, saved on this PC.": "{fighters}、このPCに保存済み。",
    "This replay is no longer on this PC.": "このリプレイはもうこのPCにありません。",
    "Keep the players' names in replays":
        "リプレイにプレイヤー名を残す",
    "Rollback":
        "Rollback",
    "Lockstep":
        "Lockstep",
    "(name not saved)":
        "（名前は保存されていません）",
    "{matches} match(es) in {files} file(s) in {folder}":
        "{folder} に {files} ファイル、{matches} 試合",
    "No replays yet. Play an online match: it is saved here.":
        "リプレイはまだありません。オンライン対戦をプレイすると、ここに保存されます。",
    "not finished":
        "未終了",
    "won {mine}-{theirs}":
        "勝ち {mine}-{theirs}",
    "lost {mine}-{theirs}":
        "負け {mine}-{theirs}",
    "Close the running game first (Stop game on the Play tab).":
        "まず起動中のゲームを閉じてください（オフラインプレイタブの「ゲームを停止」）。",
    "Build the game first (Build tab).":
        "まずゲームをビルドしてください（ビルドタブ）。",
    "This replay cannot be played: {why}":
        "このリプレイは再生できません：{why}",
    "Recorded with another version of the game: it may not play back the same.":
        "別のバージョンのゲームで記録されています：同じようには再生されない可能性があります。",
    "Playing {fighters} ({when})...":
        "{fighters} を再生中（{when}）...",
    "The replay ended before the end of the match.":
        "対戦の終わりより前にリプレイが終了しました。",
    "Replay over: identical to the live match ({checks} checks, same result).":
        "リプレイ終了：ライブの対戦と完全に一致しました（照合 {checks} 回、同じ結果）。",
    "Replay over, but it went a different way from frame {frame} on (the game or its version differs from the one that played it).":
        "リプレイ終了。ただしフレーム {frame} から違う展開になりました（ゲームまたはそのバージョンが対戦時のものと異なります）。",
    "Replay over.":
        "リプレイ終了。",
    "Delete this replay file? It holds {n} match(es) against the same opponent.":
        "このリプレイファイルを削除しますか？同じ相手との {n} 試合が入っています。",
    # ---- lobby/t5lobby/tk_spectate.py, server/spectating.py, launcher Settings (spectating live matches)
    "Spectators":
        "観戦",
    "Friends and room visitors may watch my online matches":
        "フレンドとルームの訪問者が自分のオンライン対戦を観戦できる",
    "Automatically watch":
        "自動で観戦",
    "Automatically watch the match at my room's table while I wait for my turn":
        "自分の順番を待つ間、ルームの自分の卓の対戦を自動で観戦する",
    "Not while the game is being built.":
        "ゲームのビルド中は観戦しません。",
    "Not while your own game is open: it stays ready so your next match starts quickly.":
        "自分のゲームが開いている間は観戦しません（次の対戦をすぐ始められるよう待機中です）。",
    "Your room's matches are shown automatically while you wait.":
        "待っている間、ルームの対戦が自動で表示されます。",
    "Your room's matches are no longer shown automatically.":
        "ルームの対戦は自動で表示されなくなりました。",
    "Automatically watch matches while idle":
        "待機中は自動で対戦を観戦する",
    "Also my ranked matches":
        "Ranked 対戦も観戦できる",
    "They see the match a few seconds late, in their own game. Only when both players allow it; a "
    "ranked match only when both allow ranked too.":
        "観戦者は自分のゲームで数秒遅れて対戦を見ます。両プレイヤーが許可したときだけで、Ranked 対戦は両方が Ranked も許可したときだけです。",
    "Watch":
        "観戦",
    "Spectating":
        "観戦中",
    "Stop watching":
        "観戦をやめる",
    "Watching":
        "観戦中",
    "Waiting for the match data...":
        "対戦データを待っています...",
    "About {seconds} s behind the live match.":
        "ライブの対戦より約 {seconds} 秒遅れ。",
    "It plays from the start of the players' session, a few seconds behind.":
        "プレイヤーのセッションの最初から、数秒遅れで再生されます。",
    "Watching {p1} vs {p2}.":
        "{p1} vs {p2} を観戦中。",
    "Spectators watching your match: {count}":
        "あなたの対戦の観戦者: {count}",
    "The live match is over.":
        "ライブの対戦は終わりました。",
    "The players turned spectators off.":
        "プレイヤーが観戦をオフにしました。",
    "The match data stopped coming.":
        "対戦データが届かなくなりました。",
    "This session is too long to watch from its start.":
        "このセッションは長すぎて最初から観戦できません。",
    "Your own match is starting.":
        "自分の対戦が始まります。",
    "The match data was damaged.":
        "対戦データが壊れていました。",
    "You stopped watching.":
        "観戦をやめました。",
    "A friend of the players took your place: the match has as many spectators as it can take.":
        "プレイヤーのフレンドにあなたの観戦枠が譲られました。この対戦の観戦枠はいっぱいです。",
    "this launcher cannot watch matches; update it":
        "このランチャーは対戦を観戦できません。更新してください",
    "that match is not being played right now":
        "その対戦は今行われていません",
    "you are playing in that match":
        "その対戦のプレイヤーです",
    "you are in a match yourself":
        "すでに対戦中です",
    "only friends of a player can watch this match":
        "この対戦はプレイヤーのフレンドだけが観戦できます",
    "the players do not allow spectators":
        "プレイヤーが観戦を許可していません",
    "neither player can send the match right now":
        "今はどちらのプレイヤーも対戦を送れません",
    "this match cannot be watched any more":
        "この対戦はもう観戦できません",
    "this match has {count} spectators already":
        "この対戦にはすでに {count} 人の観戦者がいます",
    "the server cannot show more matches right now":
        "サーバーは今これ以上の対戦を表示できません",
    "too many matches are watched from your network; stop watching one first":
        "あなたのネットワークから観戦している対戦が多すぎます。先にどれかの観戦をやめてください",
    "the places for guests at this match are taken; log in with an account to watch":
        "この対戦のゲスト用の観戦枠は埋まっています。観戦するにはアカウントでログインしてください",
    "the server cannot show guests more matches right now; log in with an account to watch":
        "サーバーは今、ゲストにこれ以上の対戦を表示できません。観戦するにはアカウントでログインしてください",
    # firewall hint on the Online tab (t5lobby.fwcheck, tk_tab.fw_hint_text)
    "Firewall":
        "ファイアウォール",
    "How to fix":
        "解決方法",
    "Windows Firewall blocks {program} on this network. Matches still connect, but some only "
    "through a relay, with more lag.":
        "Windows ファイアウォールがこのネットワークで {program} をブロックしています。対戦は接続できますが、一部は中継経由になり、ラグが大きくなります。",
    "A firewall seems to block T5DR Online's network traffic on this PC.":
        "ファイアウォールがこの PC で T5DR Online の通信をブロックしているようです。",
    # patch 0063 (igpu-4k-stall): Internal resolution Auto, integrated-graphics and GPU-bound hints
    "Auto (matches the screen)":
        "自動（画面に合わせる）",
    "The game picks the step that matches your screen when it starts, at most 1080p on integrated graphics (they share the processor's memory and power).":
        "起動時に画面に合う段階をゲームが選びます。内蔵グラフィックでは最大1080p（プロセッサーとメモリーと電力を共有するため）。",
    "On this PC: {step}.":
        "このPCでは：{step}。",
    "{step} on integrated graphics: a busy built-in GPU slows the processor too (they share its power and memory). For 60 fps choose Auto in Settings -> Internal resolution: {better} here.":
        "内蔵グラフィックで{step}：内蔵GPUの負荷が高いとプロセッサーも遅くなります（電力とメモリーを共有しているため）。60 fpsには設定 -> 内部解像度で自動を選んでください（このPCでは{better}）。",
    "Auto is the default on integrated graphics.":
        "内蔵グラフィックでは自動が標準です。",
    "Your processor ran at {ghz} GHz ({percent} % of its normal speed): set Windows power mode to Best performance.":
        "プロセッサーは{ghz} GHz（通常の速度の{percent} %）で動作していました：Windowsの電源モードを「最適なパフォーマンス」にしてください。",
    "Extra settings below set {setting}: that wins over this choice.":
        "下の追加設定で{setting}が設定されています：この選択より優先されます。",
    "Fights were slower than 60 fps because of the graphics (GPU-bound): choose a lower Internal resolution in Settings.":
        "グラフィックが原因で対戦が60 fpsより遅くなりました（GPUがボトルネック）：設定で内部解像度を下げてください。",
    "Fights were slower than 60 fps: the integrated graphics were busy and slowed the processor too. A lower Internal resolution in Settings helps.":
        "対戦が60 fpsより遅くなりました：内蔵グラフィックの負荷が高く、プロセッサーも遅くなりました。設定で内部解像度を下げると改善します。",
    "Fights were slower than 60 fps because of the graphics card: it is too slow for this game. Internal resolution Lowest helps a little at most.":
        "グラフィックカードが原因で対戦が60 fpsより遅くなりました：このゲームには性能が足りません。内部解像度を最低にしても、改善はわずかです。",
    "Fights were slower than 60 fps because of the processor: close other programs while you play. A lower Internal resolution does not help.":
        "プロセッサーが原因で対戦が60 fpsより遅くなりました：プレイ中は他のプログラムを閉じてください。内部解像度を下げても改善しません。",
    # ---- private and community rooms (lobby/t5lobby/tk_rooms.py; the server's messages: i18n_known.py)
    "private rooms need a newer launcher; update it": "非公開ルームには新しいランチャーが必要です。アップデートしてください",
    "only the room's host can do that": "それができるのはルームのホストだけです",
    "too many wrong room passwords; try again in {seconds} s": "ルームのパスワードを何度も間違えました。{seconds} 秒後にもう一度試してください",
    "wrong room password": "ルームのパスワードが違います",
    "the room's password changed; try again": "ルームのパスワードが変わりました。もう一度試してください",
    "no room has that invite code": "その招待コードのルームはありません",
    "rooms hold 2 to {count} players": "ルームの人数は 2～{count} 人です",
    "room passwords are 4-64 characters, no space at either end": "ルームのパスワードは 4～64 文字で、前後に空白は使えません",
    "private and community rooms are casual (unranked)": "非公開ルームとコミュニティルームはカジュアルです（Ranked ではありません）",
    "you are in that room": "すでにそのルームにいます",
    "the room's host removed you from this room": "ホストによってこのルームから外されました",
    "the room's host turned away password guesses from your network; ask the host for an invite":
        "ルームのホストがあなたのネットワークからのパスワード入力を締め出しました。ホストに招待を頼んでください",
    "only a room with a password counts wrong guesses": "間違った入力を数えるのはパスワード付きのルームだけです",
    "that player is not in your room": "そのプレイヤーはあなたのルームにいません",
    "you cannot remove yourself; leave the room instead": "自分は外せません。ルームから出てください",
    "you can remove that player after their match": "そのプレイヤーは対戦が終わってから外せます",
    "only rooms for 3 or more players take turns": "交代制は 3 人以上のルームだけです",
    "you sit out in the room; press Back in line to play again": "ルームで休憩中です。また遊ぶには「列に戻る」を押してください",
    "the room picks the next match by itself": "次の対戦はルームが自動で決めます",
    "the room's host removed that player from this room": "ホストがそのプレイヤーをこのルームから外しました",
    "only the room's players can watch its match": "そのルームの対戦を観戦できるのはルームのプレイヤーだけです",
    "Anybody": "誰でも",
    "Back in line": "列に戻る",
    "Back in line: you play when it is your turn.": "列に戻りました。順番が来たら対戦します。",
    "Copy invite code": "招待コードをコピー",
    "Create a room": "ルームを作成",
    "Everyone in turn": "全員で順番に",
    "Hide the room from the room list": "ルーム一覧に表示しない",
    "In the room “{name}”: {count}/{size} players, taking turns.": "ルーム「{name}」：{count}/{size} 人で順番に対戦します。",
    "Invite code": "招待コード",
    "Line: {names}": "順番：{names}",
    "New invite code": "新しい招待コード",
    "Next: {p1} vs {p2} in {seconds} s": "次：{p1} vs {p2}（あと {seconds} 秒）",
    "No room selected. Join a room with its invite code (XXXX-XXXX-XXXX):":
        "ルームが選ばれていません。招待コードでルームに入ります（XXXX-XXXX-XXXX）：",
    "Password (4-64 characters):": "パスワード（4～64 文字）：",
    "Players in the room:": "ルームのプレイヤー：",
    "Players:": "人数：",
    "Playing: {p1} vs {p2}": "対戦中：{p1} vs {p2}",
    "Private (invite code)": "非公開（招待コード）",
    "Private (password)": "非公開（パスワード）",
    "Remove player": "プレイヤーを外す",
    "Remove {name} from the room? They cannot come back into it.": "{name} さんをルームから外しますか？ もう戻れなくなります。",
    "Removed {name} from the room.": "{name} さんをルームから外しました。",
    "Wrong passwords in the last 10 minutes: {count} (networks: {networks})":
        "直近10分間の間違ったパスワード：{count} 件（ネットワーク：{networks}）",
    "Turn away the guessers": "推測している人を締め出す",
    "Networks turned away: {count}. They cannot try passwords on this room any more.":
        "締め出したネットワーク：{count}。そこからはこのルームのパスワードをもう試せません。",
    "Room created.": "ルームを作成しました。",
    "Room created. Press Copy invite code to see the code you can share.": "ルームを作成しました。共有できるコードは「招待コードをコピー」で表示されます。",
    "Room name (optional):": "ルーム名（省略可）：",
    "Room password": "ルームのパスワード",
    "Room passwords are 4-64 characters, with no space at the start or end.": "ルームのパスワードは 4～64 文字で、前後に空白は使えません。",
    "Room settings": "ルーム設定",
    "Room settings saved.": "ルーム設定を保存しました。",
    "Room settings...": "ルーム設定...",
    "Sit out": "休憩する",
    "The invite code is in the field next to the button: select it and press Ctrl+C to copy it.":
        "招待コードはボタンの横の欄にあります。選択して Ctrl+C でコピーしてください。",
    "The room's invite code (XXXX-XXXX-XXXX):": "ルームの招待コード（XXXX-XXXX-XXXX）：",
    "Turns (3 or more players):": "順番（3 人以上）：",
    "Who can join:": "参加できる人：",
    "Winner stays": "勝者残り",
    "You sit out: your turns are skipped until you press Back in line.": "休憩中です。「列に戻る」を押すまで順番を飛ばします。",
    "Your room: {name}": "自分のルーム：{name}",
    "hidden": "非表示",
    "invites you to the private room “{room}”. Accept to join it without its password.":
        "さんから非公開ルーム「{room}」への招待です。受けるとパスワードなしで入れます。",
    "private": "非公開",
    "private (invite code)": "非公開（招待コード）",
    "private (password)": "非公開（パスワード）",
    "{count}/{size} players": "{count}/{size} 人",
    "{name} (host)": "{name}（ホスト）",
    "{name} (sitting out)": "{name}（休憩中）",
    "{name} ({rank}) invites you to the private room “{room}”": "{name}（{rank}）さんから非公開ルーム「{room}」への招待",
    "“{room}” is private. Its password:": "「{room}」は非公開です。パスワード：",
    "this server has no private rooms": "このサーバーには非公開ルームがありません",
    # training rooms and the health handicap (1.1.5)
    "My health (casual)": "自分の体力（カジュアル）",
    "TRAINING OVER": "トレーニング終了",
    "TRAINING: endless health, nothing counted; hold SELECT for 1 s to pick again": "トレーニング：体力無限・記録なし。SELECT を 1 秒押し続けると選び直し",
    "Training fight over -- nothing is counted": "トレーニングの対戦が終わりました -- 何も記録されません",
    "Training room: endless health, nothing counted": "トレーニングルーム：体力無限・記録なし",
    "Training vs {name}": "{name} とトレーニング",
    "health: you {you} %, opponent {opponent} %": "体力：あなた {you} %、相手 {opponent} %",
    "training": "トレーニング",
    "training: endless health, nothing counted": "トレーニング：体力無限・記録なし",
    "{percent} %": "{percent} %",
    "training rooms need a newer launcher; update it": "トレーニングルームには新しいランチャーが必要です。アップデートしてください",
    "training rooms are casual (unranked)": "トレーニングルームはカジュアル（ランクなし）です",
    "the health handicap needs a newer launcher; update it": "体力ハンデには新しいランチャーが必要です。アップデートしてください",
    "life is 30 to 100 in steps of 10": "体力は 30〜100 の 10 刻みです",
    "life is 30 to 150 in steps of 10": "体力は 30〜150 の 10 刻みです",
    "this server has no training rooms": "このサーバーにはトレーニングルームがありません",
    "this server has no health handicap": "このサーバーには体力ハンデがありません",
    # Settings -> Graphics (patch 0079)
    "Graphics (weak graphics cards)":
        "グラフィック（性能の低いグラフィックカード向け）",
    "Shadows":
        "影",
    "Effects":
        "エフェクト",
    "On (default)":
        "オン（標準）",
    "Off: no shadows of the fighters and the stage. Saves graphics work and some processor time.":
        "オフ：キャラクターとステージの影を描きません。グラフィックの負荷と少しのプロセッサー時間を減らします。",
    "Off: no hit sparks or other hit effects (also the EWGF lightning), flames, smoke, mist, glows or "
    "waterfalls. Saves graphics work (the most on misty stages) and some processor time.":
        "オフ：ヒット時の火花などのヒットエフェクト（風神拳の稲妻も）、炎、煙、霧、光彩、滝を描きません。グラフィックの負"
        "荷（霧のステージで特に）と少しのプロセッサー時間を減らします。",
    "Lowest (old graphics cards)":
        "最低（古いグラフィックカード）",
    "Default":
        "標準",
    "Lowest: Internal resolution Lowest; stage blur / glow and shadows off. Effects stay on: the hit effects show what happens in a fight. Default puts them back. Only your picture changes: online, both players can choose differently.":
        "最低：内部解像度を「最低」にし、ステージのぼかし / 光彩と影をオフにします。エフェクトはオンのままです（ヒットエフェクトで対戦の状況がわかります）。「標準」で元に戻ります。変わるのは自分の画面だけなので、オンラインでも各プレイヤーが別々に選べます。",
    # ---- 1.2.1: launcher/problem_check.py old_cpu
    "Your processor is too old for the game":
        "プロセッサーが古すぎてゲームを動かせません",
    "The game needs a processor with SSE4.1: Intel Core 2 from 2008 on (E7000, E8000, Q8000, Q9000) or any Core i3/i5/i7, AMD FX, A-series from 2012 or Ryzen. This one does not have it, so the game stops at its start.":
        "このゲームには SSE4.1 対応のプロセッサーが必要です: 2008 年以降の Intel Core 2（E7000、E8000、Q8000、Q9000）またはすべての Core i3/i5/i7、AMD FX、2012 年以降の A シリーズ、Ryzen。このプロセッサーは対応していないため、ゲームは起動時に止まります。",
    "This PC: no SSE4.1.":
        "この PC: SSE4.1 なし。",
    # ---- 1.2.1: Old PC settings (launcher/core.py OLD_PC_PRESET)
    "a processor with {cores} cores":
        "{cores} コアのプロセッサー",
    "an old graphics card ({name}: resource binding tier 1)":
        "古いグラフィックカード（{name}: resource binding tier 1）",
    "This PC looks like an old PC ({why}), so the launcher chose the Old PC settings: Internal resolution Lowest, no stage blur, no shadows and no effects. Settings -> Graphics -> Default puts the normal look back.":
        "この PC は古い PC のようです（{why}）。そのためランチャーは古い PC 向けの設定を選びました: 内部解像度「最低」、ステージのぼかしなし、影なし、エフェクトなし。設定 -> グラフィック -> 「デフォルト」で通常の見た目に戻ります。",
    "Old PC":
        "古い PC",
    "Old PC: like Lowest, and the effects off too -- for a 2-core processor or a graphics card from before ~2013. The launcher chooses it by itself once on such a PC, as long as you have not changed these settings.":
        "古い PC: 「最低」と同じで、さらにエフェクトもオフ -- 2 コアのプロセッサーや 2013 年ごろより前のグラフィックカード向け。この設定を変えていなければ、そのような PC ではランチャーが一度だけ自動で選びます。",
    # ---- lobby/t5lobby/tk_casual.py
    "Any side": "どちらでも",
    "P1 (left)": "P1（左）",
    "P2 (right)": "P2（右）",
    "Challenges, invites, rooms:": "対戦申し込み・招待・ルーム：",
    "Random stage": "ランダムステージ",
    "wants to be P{n} on {stage}": "P{n}・{stage} を希望",
    "wants to be P{n}": "P{n} を希望",
    "wants to play on {stage}": "{stage} を希望",
    "You both wanted P{n}: a coin flip made you P{m}.": "お互い P{n} を希望したため、コイントスであなたは P{m} になりました。",
    "Your opponent wanted another stage: a coin flip chose {stage}.": "相手は別のステージを希望しました。コイントスで {stage} に決まりました。",
    "P{n} on {stage}": "P{n}・{stage}",
    "Rematch: swap sides": "Rematch：サイド交代",
    "with the sides swapped": "サイドを交代して",
    # the fold button right of the Online tab's lists (tk_views.toggle_top)
    "Hide": "隠す",
    "Show": "表示",
    # 1.1.9: several open challenges, input delay, sorted lists, split leaderboard (tk_challenges.py)
    "Casual L": "カジュアル敗",
    "Casual W": "カジュアル勝",
    "Challenge withdrawn: a match started.": "対戦申し込みは取り下げられました: 試合が始まりました。",
    "input delays above 2 frames need a newer launcher and server": "3フレーム以上の入力遅延には新しいランチャーとサーバーが必要です",
    "Delay: auto": "遅延: 自動",
    "Delay: {frames}": "遅延: {frames}",
    "Input delay {frames} (auto, from the ping)": "入力遅延 {frames}（自動、Pingから）",
    "Input delay {frames} (chosen by the challenger)": "入力遅延 {frames}（申し込んだ側が指定）",
    "Input delay: {delay}.": "入力遅延: {delay}。",
    "Unavailable": "対戦不可",
    "Ranked L": "Ranked 敗",
    "Ranked W": "Ranked 勝",
    "The challenge from {name} ran out.": "{name} さんからの対戦申し込みの期限が切れました。",
    "The challenge from {name} was withdrawn: a match started.": "{name} さんからの対戦申し込みは取り下げられました: 試合が始まりました。",
    "You challenged that player already: your open challenges are under the list.": "そのプレイヤーにはすでに申し込み済みです: 申し込み中の一覧はリストの下にあります。",
    "You challenged {name}.": "{name} さんに対戦を申し込みました。",
    "You took back your challenge to {name}.": "{name} さんへの対戦申し込みを取り消しました。",
    "Your challenge to {name} was not answered in time.": "{name} さんへの対戦申し込みに時間内の返事がありませんでした。",
    "Your challenge to {name} was withdrawn: a match started.": "{name} さんへの対戦申し込みは取り下げられました: 試合が始まりました。",
    "Your open challenges": "申し込み中の対戦",
    "auto": "自動",
    "input delay {delay}": "入力遅延 {delay}",
    "{name} accepted your challenge.": "{name} さんが対戦申し込みを受けました。",
    "{name} challenges you.": "{name} さんから対戦を申し込まれました。",
    "{name} declined your challenge.": "{name} さんが対戦申し込みを断りました。",
    "{name} took back the challenge.": "{name} さんが対戦申し込みを取り消しました。",
    "you challenged that player already": "そのプレイヤーにはすでに申し込み済みです",
    "too many challenges at once": "一度に申し込みすぎです",
    "bad field: delay": "不正な項目: delay",
    # launcher Settings "Screen side" and the Online tab's casual row ("Always left", 1.1.9, casual matches only;
    # docs/NETPLAY.md)
    "Screen side": '画面の向き',
    "As dealt": "割り当てどおり",
    "Always left": "常に左側",
    "Always right": "常に右側",
    "Casual matches only: show your fighter on the chosen side and swap left/right controls when mirrored. Ranked and Quick matches keep the dealt side. Offline: Versus previews the chosen side.":
        "カジュアル対戦のみ：選んだ側に自分のキャラクターを表示し、左右反転時は左右の操作も入れ替えます。Ranked と Quick Match は割り当てられた側のままです。オフライン：Versus で選んだ側の表示を確認できます。",
    "Graphics compatibility warning": "グラフィックス互換性の警告",
    "Could not stop the shader warm-up": "シェーダーのウォームアップを停止できませんでした",
    "This PC lists older Intel graphics ({gpus}). Intel HD 4400-class graphics may lack a working Direct3D 12 driver and may not run the game. Building the game does not add graphics support. If this PC has another graphics card, select it in Windows Graphics settings. Continue building?":
        "この PC には古い Intel グラフィックス（{gpus}）が搭載されています。Intel HD 4400 クラスでは、動作する Direct3D 12 ドライバーがなく、ゲームを実行できない場合があります。ゲームをビルドしてもグラフィックスの対応状況は変わりません。別のグラフィックスカードがある場合は、Windows のグラフィックス設定で選択してください。ビルドを続けますか？",
    "Launcher button bindings and macros take priority over the game's Controller Setup. Set them in Settings > Set up controllers… in the launcher.":
        "ランチャーのボタン割り当てとマクロは、ゲーム内の Controller Setup より優先されます。ランチャーの「設定 > コントローラー設定…」で変更してください。",
    "Casual matches only (challenges, friends' invites, rooms): when you are P2, your screen shows the fight mirrored with you on the left, and your left and right are swapped. Your opponent sees the normal picture. Ranked and Quick matches stay as they are. Offline: Versus fights show the P2 side.":
        'カジュアル対戦のみ（対戦申し込み・フレンドの招待・ルーム）：P2 のとき、自分の画面だけ対戦が左右反転して自分が左側に表示され、左右の入力も入れ替わります。相手には通常の画面が表示されます。Ranked 対戦と Quick Match はそのままです。オフライン：Versus の対戦は P2 側の視点になります。',
    # Replay folder in Settings (docs/REPLAYS.md)
    "Replay folder":
        "リプレイフォルダー",
    "Choose an existing folder for new replays. Leave this empty to use the default. Old replays stay where they are unless you choose to move them.":
        "新しいリプレイの保存先として既存のフォルダーを選んでください。空欄にすると既定のフォルダーを使います。移動を選ばない限り、古いリプレイは元の場所に残ります。",
    "Browse...":
        "参照...",
    "Use default folder":
        "既定のフォルダーを使う",
    "Apply folder":
        "フォルダーを適用",
    "Using replay folder: {folder}":
        "使用中のリプレイフォルダー: {folder}",
    "Move existing replays from {source} to {destination}? Choose No to leave them where they are.":
        "既存のリプレイを {source} から {destination} に移動しますか？ 元の場所に残すには「いいえ」を選んでください。",
    "Moved {moved} replay file(s). {retained} file(s) remain in {source}; existing files were not replaced.":
        "リプレイファイルを {moved} 個移動しました。{retained} 個のファイルは {source} に残っています。既存のファイルは置き換えていません。",
    "Could not move replays: {error}. The original files have been kept.":
        "リプレイを移動できませんでした: {error}。元のファイルは保持されています。",
    "Close the running game before changing the replay folder.":
        "リプレイフォルダーを変更する前に、起動中のゲームを終了してください。",
    "Replay folder {folder} is missing or is not writable. Using the default folder: {default}.":
        "リプレイフォルダー {folder} が見つからないか、書き込みできません。既定のフォルダーを使います: {default}。",
    "The default replay folder {folder} is not writable. Replays cannot be saved there.":
        "既定のリプレイフォルダー {folder} に書き込みできません。ここにはリプレイを保存できません。",
    "Rematch starts in {seconds} s unless you decline.": "辞退しなければ{seconds}秒後に再戦します。",
    "Draw.": "引き分け。",
    "No rematch. Back to the lobby.": "再戦なし。ロビーに戻ります。",
    "Rematch! Starting...": "再戦！開始します...",
    "Take it back": "取り消す",
    "Time is up. Back to the lobby.": "時間切れ。ロビーに戻ります。",
    "You want a rematch. Waiting for {name}...": "再戦を希望しました。{name}を待っています...",
    "{name} does not want a rematch.": "{name}は再戦を希望していません。",
    "{name} is deciding...": "{name}が考え中...",
    "{name} wants a rematch!": "{name}が再戦を希望しています！",
    "invalid rematch policy": "再戦ルールが無効です",
    "auto_skip_after_round must be boolean": "スキップ設定は有効か無効で指定してください",
    "rematch rules require an updated launcher": "再戦ルールにはランチャーの更新が必要です",
    "rematch rules require a classic casual room": "再戦ルールは通常のカジュアルルームで利用できます",
    "round skips require an updated launcher": "ラウンドのスキップにはランチャーの更新が必要です",
    "Auto-skip replays and round endings (both players agree)": "リプレイとラウンド終了演出を自動スキップ（両者の同意）",
    "Round endings": "ラウンド終了",
    "Skip replays and round endings automatically (offline)": "リプレイとラウンド終了演出を自動でスキップ（オフライン）",
    "Online the skip counts only when both players tick \"Auto-skip replays and round endings\" in the Online tab (casual matches; never ranked).": "オンラインでは、両方のプレイヤーがオンラインタブで「リプレイとラウンド終了演出を自動スキップ（両者の同意）」にチェックを入れた場合のみスキップされます（カジュアルのみ、ランクマッチでは無効）。",
    "Rematch rule:": "再戦ルール：",
    "Both players confirm": "両プレイヤーが確認",
    "Start automatically unless declined": "辞退しなければ自動開始",
    "Skip replays after rounds (both players must agree)": "ラウンド後のリプレイをスキップ（両者の同意が必要）",
    "this server has no in-game rematch": "このサーバーはゲーム内の再戦に対応していません",
    "this server has no automatic round skips": "このサーバーはラウンド後の自動スキップに対応していません",
    # Server chat-filter notices (1.2.0).
    "Message blocked: hate terms are not allowed.": "メッセージは送信されませんでした。差別的な表現は使用できません。",
    "This name is not allowed.": "この名前は使用できません。",
    "This room name is not allowed.": "このルーム名は使用できません。",
    "Chat is muted for this account.": "このアカウントのチャットはミュートされています。",
    "Cannot load the chat filter. Check T5L_CHAT_FILTER_PATH.": "チャットフィルターを読み込めません。T5L_CHAT_FILTER_PATH を確認してください。",
    # Personal player mutes (1.2.0).
    "Muted players...": "ミュート中のプレイヤー...",
    "Muted players": "ミュート中のプレイヤー",
    "Mute": "ミュート",
    "Unmute": "ミュート解除",
    "Muted {name}.": "{name} をミュートしました。",
    "Unmuted {name}.": "{name} のミュートを解除しました。",
    "Mute hides their lobby, room and private chat, mentions and invites for you. You can still play together. Block also prevents matches and ends friendship. Accounts remember mutes on this server; guests remember them on this device.": "ミュートすると、そのプレイヤーのロビー・ルーム・プライベートチャット、メンション、招待が自分に表示されなくなります。対戦は引き続き可能です。ブロックすると対戦もできなくなり、フレンド関係が解除されます。アカウントのミュート設定はこのサーバーに、ゲストの設定はこの端末に保存されます。",
    "Mute hides this player's chat, mentions and invites for you. Block also prevents matches and private messages.": "ミュートすると、このプレイヤーのチャット、メンション、招待が自分に表示されなくなります。ブロックすると対戦とプライベートメッセージもできなくなります。",

    "Personal mute is unavailable on this server.": "このサーバーでは個別ミュートを利用できません。",
    "Chat is muted until {until}.": "チャットは {until} までミュートされています。",

    # netext: online feel, connection line, search options, Remove my data
    'Responsive': '反応重視',
    'Balanced': 'バランス',
    'Smooth': 'なめらか',
    'Online feel:': 'オンラインの感触:',
    'For Auto. Responsive: the least delay. Balanced: one frame more when a PC cannot keep up with its rollbacks. Smooth: more delay, fewer and smaller rollbacks. Different choices meet at Balanced.': 'Auto のとき。反応重視: 遅延を最小に。バランス: PC がロールバックに追いつけないときは 1 フレーム追加。なめらか: 遅延を増やし、ロールバックを少なく小さく。選択が違うときはバランスになります。',
    'Show the connection line in online matches (ping, delay, rollbacks; F3 in the game)': 'オンライン対戦で接続ラインを表示 (Ping、遅延、ロールバック。ゲーム中は F3)',
    'F3 (connection line)': 'F3 (接続ライン)',
    'Search options': '検索オプション',
    'Search options...': '検索オプション...',
    'Search options: {options}.': '検索オプション: {options}。',
    "For Quick match and Ranked match. Your opponent's options count too. The more you choose, the longer the search can take.": 'Quick Match と Ranked 用。相手のオプションも適用されます。多く選ぶほど検索に時間がかかることがあります。',
    'Highest ping': '最大 Ping',
    'Any': '制限なし',
    'No opponents on Wi-Fi': 'Wi-Fi の相手を除く',
    'Only opponents whose PC keeps 60 fps': '60 fps を保てる PC の相手のみ',
    "Wi-Fi and speed come from your opponent's launcher (its last match); a launcher that does not say is not left out.": 'Wi-Fi と速度は相手のランチャーが伝えます (前回の対戦)。伝えないランチャーは除外されません。',
    'Your area': 'あなたの地域',
    'Auto (the nearest server)': '自動 (最寄りのサーバー)',
    'Language you speak': '話す言語',
    "The launcher's language": 'ランチャーの言語',
    'This server has no search options yet: they count once it has.': 'このサーバーにはまだ検索オプションがありません。対応すると有効になります。',
    'North America': '北米',
    'South America': '南米',
    'Europe': 'ヨーロッパ',
    'Africa': 'アフリカ',
    'Asia': 'アジア',
    'Oceania': 'オセアニア',
    'ping up to {ms} ms': 'Ping {ms} ms まで',
    'no Wi-Fi': 'Wi-Fi なし',
    'steady 60 fps': '安定 60 fps',
    'Remove my data': 'データを削除',
    'Remove my data...': 'データを削除...',
    'Choose what goes. Nothing is removed before you confirm twice.': '削除するものを選んでください。2 回確認するまで何も削除されません。',
    'My account {name} on {server}: profile, rating, friends, blocks, saved logins. Your matches stay in other players\' history as "deleted player".': '{server} のアカウント {name}: プロフィール、レーティング、フレンド、ブロック、保存したログイン。あなたの対戦はほかのプレイヤーの履歴に "deleted player" として残ります。',
    'My account on the server: log in with your account first (a guest has nothing on the server).': 'サーバーのアカウント: 先にアカウントでログインしてください (ゲストはサーバーに何も残りません)。',
    'On this PC': 'この PC',
    'Online tab settings and saved logins': 'オンラインタブの設定と保存したログイン',
    'Replays ({count} files)': 'リプレイ ({count} ファイル)',
    'Game logs ({count} files)': 'ゲームのログ ({count} ファイル)',
    'The save the game uses online': 'ゲームがオンラインで使うセーブ',
    "This PC's measured rollback cost": 'この PC で測ったロールバックの負荷',
    'Nothing of the online play is stored on this PC.': 'この PC にはオンラインプレイのデータはありません。',
    "The game build, your offline save and the launcher's settings stay.": 'ゲームのビルド、オフラインのセーブ、ランチャーの設定は残ります。',
    'Remove...': '削除...',
    'Nothing chosen.': '何も選ばれていません。',
    '- your account on the server': '- サーバーのアカウント',
    'Remove this?\n\n{what}': 'これを削除しますか?\n\n{what}',
    'Your password:': 'パスワード:',
    'This cannot be undone. The server removes your account {name} now: {matches} match(es) and {sets} set(s) keep their result under "deleted player", {friends} friend(s) lose you from their list.\n\nRemove it?': '元に戻せません。サーバーはアカウント {name} を今すぐ削除します: {matches} 件の対戦と {sets} 件のセットは "deleted player" として結果が残り、{friends} 人のフレンドのリストからあなたが消えます。\n\n削除しますか?',
    'Your account and its data were removed from the server.': 'アカウントとそのデータはサーバーから削除されました。',
    'This cannot be undone. Remove the chosen files from this PC?': '元に戻せません。選んだファイルをこの PC から削除しますか?',
    'Removed {removed} item(s); {failed} could not be removed (in use?): {first}': '{removed} 件を削除しました。{failed} 件は削除できませんでした (使用中?): {first}',
    'Removed: {what}.': '削除しました: {what}。',
    'Not connected. Your account was removed from the server.': '未接続。アカウントはサーバーから削除されました。',
    'guests have no account on the server: there is nothing to remove': 'ゲストにはサーバーのアカウントがありません。削除するものはありません',
    'too many requests; wait a minute': 'リクエストが多すぎます。1 分待ってください',
    'this account no longer exists': 'このアカウントはもうありません',
    'you are {status}: finish or leave it first': '現在 {status} です。先に終えるか抜けてください',
    'you are in a set: finish or leave it first': 'セット中です。先に終えるか抜けてください',
    'you take part in a tournament that is not over: leave it (or let it end) first': '終わっていないトーナメントに参加しています。先に抜けてください (または終了を待ってください)',
    'this account was removed': 'このアカウントは削除されました',
    'this server cannot remove accounts yet; ask its host': 'このサーバーはまだアカウントを削除できません。管理者に問い合わせてください',
    "EU edition": "EU版",
    "US edition": "US版",
    "Sound for a challenge:": "挑戦を受けたときのサウンド：",
    "New challenger (default)": "新たな挑戦者（既定）",
    "Chime": "チャイム",
    "{problem} The chime is used instead.": "{problem} 代わりにチャイムが鳴ります。",
    "The announcer needs your built game (BUILD GAME): until then the chime plays.": "アナウンスにはビルド済みのゲームが必要です（BUILD GAME）。それまではチャイムが鳴ります。",
    "For an incoming challenge or invite when you are in another window. The announcer is read from your own game (after BUILD GAME); without it the chime plays. Your own sound: a WAV file of at most 5 seconds and 2 MB, copied into the launcher's folder.": "別のウィンドウを見ているとき、挑戦や招待を受けると鳴ります。アナウンスは自分のゲーム（BUILD GAME後）から読み込み、ない場合はチャイムが鳴ります。自分のサウンド：5秒・2 MB以内のWAVファイル（ランチャーのフォルダーにコピーされます）。",
    "For a found match or tournament set when you are in another window. The announcer is read from your own game (after BUILD GAME); without it the beep plays. Your own sound: a WAV file of at most 5 seconds and 2 MB, copied into the launcher's folder.": "別のウィンドウを見ているとき、マッチが見つかるか大会のセットが準備できると鳴ります。アナウンスは自分のゲーム（BUILD GAME後）から読み込み、ない場合はビープ音が鳴ります。自分のサウンド：5秒・2 MB以内のWAVファイル（ランチャーのフォルダーにコピーされます）。",
    'Video clips': '??????',
    'Keep the last 30 seconds': '???30???????',
    'Ctrl+F10 or hold SELECT + R3 for 1 second to save an MP4 in Videos/T5DR Online. Includes game sound only. Disabled while power saving is on. Windows only.': 'Ctrl+F10????SELECT + R3?1????????????/T5DR Online?MP4??????????????????????????????????Windows?????',
}

# Replay viewer and local library.
MESSAGES.update({
    'Back 10 s': '10???',
    'Favourite': '?????',
    'Favourites only': '???????',
    'Forward 10 s': '10???',
    'Frame step': '????',
    'Frame {frame} / {end}': '???? {frame} / {end}',
    'Pause': '????',
    'Replay over: unverified from frame {frame} (player control).': '??????????? {frame} ????????????????',
    'Resume': '??',
    'Round {n}': '???? {n}',
    'START (Enter) pauses or resumes; SELECT (Tab) ends playback. Taking control uses the local pad and marks playback unverified from that frame. Older replays may need earlier matches to play first.': 'START?Enter??????????SELECT?Tab????????????????????????????????????????????????????????????????????????',
    'Speed': '??',
    'Take P{side}': 'P{side}???',
    'Unverified: player control': '???????????',
    'Verified playback': '??????',
})

MESSAGES['This replay command is unavailable at the current frame.'] = '??????????????????????????'

# Practice while searching.
MESSAGES.update({
    "NEW CHALLENGER": "新たな挑戦者",
    "Starting Practice before searching...": "検索前にプラクティスを開始しています...",
    "Practice could not start; search was not started.": "プラクティスを開始できなかったため、検索を開始しませんでした。",
})
