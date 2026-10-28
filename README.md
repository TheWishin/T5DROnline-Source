# Tekken 5: Dark Resurrection Online — native Windows port

Tekken 5: Dark Resurrection (PS3, PlayStation Network release) running natively
on Windows. It is recompiled, not emulated. Online play runs through the
launcher's own lobby, like Tekken 6 Native Online.

<!-- RELEASE LINE: the version and date in the next two lines change with every release, when it is tagged
(docs/RELEASING.md "Cutting a release", step 2); the same lines are in docs/README.de.md. -->
**Release 1.1.7 (2026-10-28).** Download
`T5DR-Online-1.1.7.zip` from https://github.com/TheWishin/T5DROnline/releases

**Community Discord:** https://discord.gg/4DwDHAkk2x -- questions, matches, feedback.

**Offline play is ready:** all modes, 60 fps, Xbox pad and arcade stick tested.
**Online works:** tested between two players' PCs over the internet (direct
connection, 26 ms ping, 60 fps). Please end matches normally, not with Alt+F4.

<!-- players:start -->
Found a bug? Please report it (see "Bug reports" below).

Deutsch: `docs\README.de.md` in this folder.

**Languages:** the launcher speaks English, Deutsch, Español, 한국어, 日本語, Português (Brasil)
and Français (**Settings** -> **Language**).

## What is this?

- The PS3 game's program is translated to C++ ahead of time (static
  recompilation) and compiled into a normal Windows program. No emulator runs.
- The model is the same as
  [Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online).
  This repository and its releases contain **no part of the game**.
- You build the game on your own PC from **your own copy**: the PSN package
  (`.pkg`) and the license (`.rap`) from your own account. The launcher does
  this for you.
- Online play between friends works like Tekken 6 Native Online: log in (or
  play as a guest) in the launcher's Online tab, find an opponent, and the game
  starts directly in the fight. See "Online".

## Status (2026-10-21)

Tested on one development PC (Windows 11, 16-core Ryzen 9, RTX 3090). Online play was
tested between two real PCs over the internet (AMD/60 Hz vs Intel/240 Hz).

| Area | State |
|---|---|
| Start-up | Works. Boots, opens the window, reaches the title, menus, character select and fights. |
| Menus, fights | 60 fps, also with other programs busy on the PC. The game no longer busy-waits around its frames: about 30 % less CPU on 8 cores / 16 threads. Since 1.1.3 the game's own work and the translation of its drawing take about a quarter less processor time per fight frame, and a PC a little too slow for 60 fps runs fights at 45-55 fps instead of 30-45 (measured with slowed test games; real weak PCs are not measured yet). Since 1.1.4 two changes in the game's code save more processor time per frame on 4 cores under load (registers kept between calls: ~7 % on the main thread, ~18 % on the drawing thread; cheaper memory writes: 5-7 % and 15-25 %), and a frame goes to the graphics card beside the game's next one, so on a slowed 4-core test PC a late frame comes about 1 ms sooner. Since 1.1.5 a dedicated graphics card draws one frame while the game prepares the next, PCs with 2 cores get a 2-core mode, and BUILD GAME ends with a shader warm-up so the first fights on each stage no longer stutter. |
| Laptops, handhelds | **Power saving** (launcher Settings; Auto turns it on with a battery, a power-saving plan, a mobile processor or integrated graphics): fewer helper threads, no busy waiting, the same game online. Not tried on a real laptop or handheld yet. Since 1.1.4 integrated graphics also start with Internal resolution Auto, and the Play offline tab says when the processor ran well under its normal clock (it suggests Windows' power mode Best performance). |
| Game modes | Arcade, Ghost, Versus (two players on one PC), Survival and Practice work. Gallery and the game's own Online menu need Namco's and Sony's servers (gone) and say so. |
| Fighters, stages | All fighters and stages render correctly, including faces, floor shadows and background figures. Stage blur and the sun's glow look as on the PS3 at every internal resolution when Settings -> Stage blur / glow is On (Off, sharp and without the glow, is the default since 1.1.4). |
| Unlocks, costumes | Offline, in launcher Settings -> Unlocks (all off by default): all stages without the fights they normally take, Jinpachi and the random cell on the character select without clearing Arcade, and every customization item for 0 Fight Money (your save is backed up first). Online games use a fresh save of their own, the same on both PCs; only your custom costume comes from your own save, and both players see both costumes (1.1.3). Both PCs check the costume against the game's own item shop tables and fall back to the default one (1.1.4). |
| Display | Resizable window, borderless fullscreen (Alt+Enter or F11). **Internal resolution** from Lowest (0.5x) over Native (720p) to 1080p, 1440p and 4K, or Auto (the screen's step, at most 1080p on integrated graphics) (launcher Settings, `PS3_INTERNAL_RES`); every step checked in fights, menus, movies and character select. Less GPU work at 1080p and above (1.1.3). On integrated graphics Auto is the default (1.1.4). For weak or old graphics cards: Settings -> Graphics (Shadows, Effects, **Lowest (old graphics cards)**) (1.1.5). |
| Music, sound effects, movies | Work. |
| Controls | Keyboard, Xbox pads (XInput), DualShock 4 and DualSense over USB and Bluetooth (read directly, no Steam needed), arcade sticks and hitboxes (DirectInput), two local players, buttons set in the launcher (Settings -> Set up controllers) or in `controls.ini`. Short taps are never lost. Tried by a person: an Xbox pad and an arcade stick, every input came through, smooth. **Set up controllers** found no controller at all from 1.1.0 to 1.1.3; it works again (1.1.4). |
| Training tools | In Practice: an input display (each player's last inputs with how many frames each was held) and frame data after each exchange (startup, and who can act first: `+3`, `-12`), drawn sharp over the picture at any resolution. Launcher Settings -> Training overlay (Off / Inputs / Inputs + frame data, also in the other offline modes, online only your own inputs), F2 switches it in the game. Practice tools (offline): SELECT+3 puts both fighters back to the start or against a wall, the dummy blocks after the first hit / crouches / walks / sidesteps, 5 recording slots for the dummy (Settings -> Practice tools). Online: **training rooms** with a friend, endless health, nothing counted (1.1.5). See [docs/TRAINING.md](docs/TRAINING.md). |
| Input lag | A jab shows on screen about 35-40 ms after the press in fullscreen (the PS3 on a TV: ~42 ms plus the TV), a frame less than before. In a window add one frame (Windows draws the window). |
| Saving | Works. The in-game clock shows the real date. |
| Long sessions | The old memory bug (white screen after a few trips through the title) is fixed. |
| Online play | Works on one PC and through the public lobby server. Rollback netcode: 1 frame of input delay up to ~60 ms ping, 2 above, at least 3 above 150 ms and 4 above 250 ms (1.1.5) (Settings -> Online input delay; ranked: always 2, more above 150 ms), about 60 fps at 150 ms ping on an 8-thread PC (now and then a picture is shown twice), tested at 0/50/150 ms ping with packet loss. Played between two real PCs over the internet (2026-10-18). Quick and ranked search prefer opponents with a low ping (estimated through the nearest relay server, or the ping two players measured in the last 7 days) and widen the search while you wait. The Ping column, a found match, a challenge and an invite show the ping through the nearest relay server and whether the match will most likely be direct or relayed (1.1.5). Many cancelled matches in a row no longer break the open game. Nobody can pause an online fight. Matches connect even when a firewall blocks the game: through the relay when nothing else gets through (1.1.3), and there the game plays like a direct match at the same ping: the launcher forwards the game's packets the moment they arrive (1.1.4). |
| Online character select | Quick matches, rooms and friend invites also offer Jinpachi (top row, right end) and the game's random cell (top row, left end), for both players; ranked matches and tournament sets do not. Mokujin and the random cell draw anew in every match (1.1.4). |
| Casual choices | Challenges, invites and rooms: ask for P1, P2 or any side and for a stage (the stages have their real names), and **Rematch: swap sides** afterwards. **My health (casual)**: a health handicap from 150 % (since 1.1.7) down to 30 %, shown to both players. Ranked and tournaments stay as they are (1.1.5). |
| Intros, replays | Online, the fighters' intros (about 7 s) and the replay after a round (about 9 s) are skipped as soon as both players have pressed Start; one player alone skips nothing, and Start still never pauses an online fight (1.1.4). |
| Friends, invites | Accounts add friends by name on the Online tab's **Friends** page and see who is online, searching or in a match. **Invite** a friend to a casual match or your room: one click on Accept starts it. |
| Rooms | Lobby rooms for 2, or community rooms for up to 8 who take turns (winner stays, or everyone in turn); open, with a password or an invite code, or hidden (1.1.3). Friends who know a room's password always get in, even while strangers guess at it; the host sees how many wrong passwords came and can turn those networks away (1.1.4). **Training rooms** (1.1.5): practice with a friend, damage never KOs, hold SELECT to give up. |
| Tournaments | Accounts join tournaments on the Online tab (tournament hosts create them; for one of the 20 host slots, DM wishin): single or double elimination, sets of best of 3 or 5, up to 64 players; the server calls each set and the game starts by itself (1.1.3). |
| Alerts | In another window while you wait? When a match is found, someone joins your room, it is your turn in a room, a friend invites you, a tournament set is ready or your opponent asks for a rematch, the launcher plays a short chime and its taskbar button flashes until you are back (Settings -> Sound and taskbar flash; on by default; 1.1.4). |
| Replays | Every online match is saved (a few KB). The **Replays** tab plays it again in the game and checks that it is identical to the live match. |
| Spectating | **Watch** a friend's match, a room's match or a tournament set live in your own game, a few seconds behind and checked frame by frame; only when both players allow it (Settings -> Spectators) (1.1.3). A room's Watch also works between a match and its rematch, and friends and room members come first at a full match (1.1.4). |
| Launcher | English plus six translations: Deutsch, Español, 한국어, 日本語, Português (Brasil), Français, with nothing cut off at 100 % and 150 % display scaling. The Settings tab scrolls. Next to every name on the Online tab stands the game's own rank plate, read from your own game after BUILD GAME, and the window redraws more than twice as fast (1.1.4). **Check my problem** finds the known problems in this PC's logs, a **Stats** page shows every fighter's matches and win rate, your profile shows your record and your match history with **Watch replay** (1.1.5). Updates itself; from 1.1.5 only with updates signed by the project. |
| Build from your copy | Works on the development PC. A stopped helper process no longer hangs the build at "Translate code"; a file that fails to compile gets a second try (1.1.3). Unpacking needs far less memory, a package of another version (01.01) is named as such, and a step that prints nothing for long says so (1.1.5). |

## Requirements

**Minimum requirements:** Windows 10 or 11 (64-bit), a 4-core CPU from about
2014 on (Intel Core i5/i7 4th gen, AMD Ryzen or newer; AVX2 recommended), a
DirectX 12-capable graphics card (feature level 11_0) and 8 GB RAM. The CPU
matters most: the game's main work runs on one core, so one fast core helps
more than many cores or a strong graphics card.

In detail:

- Windows 10 (version 1909 or newer) or Windows 11, 64-bit. Nothing else to
  install: no Visual C++ redistributable, no Visual Studio, no DirectX
  download. Windows "N" editions: the movies stay black without the Media
  Feature Pack; the rest works.
- A graphics card with Direct3D 12 (feature level 11_0 or higher) and a
  current driver. That is about: NVIDIA GeForce GTX 600 or newer, AMD Radeon
  HD 7000 or newer, Intel graphics of 6th-gen Core (2015) or newer. Tested on
  an NVIDIA RTX 3090 and on Windows' software renderer (WARP) only. Laptops
  with two graphics chips use the fast one by default.
- A 64-bit Intel or AMD processor with SSE4.1: Intel Core 2 (2008) or newer,
  AMD FX, A-series or Ryzen (2011) or newer. That starts the game; for full
  speed see the minimum above. AVX2 is not needed. With AVX2
  (Intel 4th-gen Core / AMD Ryzen and newer) the build makes faster code; the
  launcher decides this by itself. Only tested on a CPU with AVX2.
- Speed: fights held 60 fps with 4 CPU threads in our tests (fast desktop
  cores); online against a far-away player (rollback, 150 ms) about 50 fps.
  A PC a little too slow for 60 fps runs fights at about 45-55 fps since 1.1.3.
  See [Low frame rate](docs/TROUBLESHOOTING.md#low-frame-rate). Weak graphics:
  **Internal resolution** under [Playing](#playing).
- Any monitor: 60, 120, 144 Hz and more, also slower TVs (50 Hz). The game
  always runs at the PS3's 59.94 frames per second. Any Windows display
  scaling (100-200 %), several monitors.
- Any folder you can write to, on any drive, also with spaces or letters like
  ü or Ł in the name, or in your user name. Not in Program Files, not in a
  OneDrive folder, and keep the path short (under about 150 characters).
- RAM: the game used about 1.2 GB on the development PC. We have not tested
  small PCs. 8 GB or more is a safe guess.
- About 1.5 GB of free disk space. After the build it uses about 1.1 GB, plus
  the 90 MB zip.
- An internet connection during the first build. About 50 KB of public key data
  (two text files) is fetched from github.com. Nothing about you or your game is
  sent.
- **Your own copy** of the game, exactly this one:
  **TEKKEN 5 DARK RESURRECTION ONLINE, US PSN, `NPUB30009`, version 01.00**.
  - the package: `.pkg`, 619,430,240 bytes
  - the license: `.rap` (16 bytes), named
    `UP0700-NPUB30009_00-UPDATE0000010000.rap`
  - **Other versions are refused** (disc copies, other regions, other
    versions). The port is tied to this exact program.

You do **not** need Visual Studio, Git or Python. The zip brings its own Python
and its own compiler (clang-cl and lld-link from LLVM). The game's runtime comes
precompiled. Your PC only translates and compiles the code from your copy.

## Install and first build

1. Download the zip (`T5DR-Online-<version>.zip`, about 90 MB) from the
   Releases page: https://github.com/TheWishin/T5DROnline/releases
2. Extract **everything** into its own folder, for example `C:\T5DR`. Not into
   Program Files. Not from inside the zip viewer.
3. Start `T5DR Online.exe`. Windows may warn once (SmartScreen: the file is not
   signed). Click "More info", then "Run anyway".
4. **Build** tab: choose your `.pkg` and `.rap`. The launcher also looks in
   Downloads, Desktop and Documents. Both lines should get a green check.
5. Click **BUILD GAME**. The launcher:
   - checks your copy (a wrong version or wrong `.rap` is refused within
     seconds),
   - unpacks it into the `native` folder,
   - translates the game's code and compiles it on your PC.

   Time: about 90 seconds on the development PC (16 cores). On a typical PC we
   expect a few minutes (estimate, not measured). **Cancel** is safe: BUILD GAME
   continues where it stopped.
6. **Play offline** tab: type a name (optional) and click **PLAY OFFLINE** (Arcade, Versus,
   Practice ... on this PC). For matches over the internet use the **Play online** tab.

Everything the build makes stays in the `native` folder next to the launcher.
It is game data. Do not share it. To uninstall, delete the whole folder.

## Playing

- The launcher speaks English, German (Deutsch), Spanish (Español), Korean
  (한국어), Japanese (日本語), Brazilian Portuguese (Português (Brasil)) and
  French (Français). **Settings** -> **Language** lists each in its own name;
  Auto follows the language of Windows (English when Windows uses another
  language). A change applies when the launcher starts again (the **Restart
  now** button does that). The game itself stays in English. The Spanish,
  Korean, Japanese, Portuguese and French texts were translated with machine
  help: if something reads wrong, please tell us (see "Bug reports") --
  corrections are welcome.
- The game opens in its own window and scales its picture to the window.
  **Settings** has window sizes, maximized, borderless fullscreen and mute.
  The Settings tab is taller than the window: scroll it with the mouse wheel
  or the scrollbar.
- **Settings** -> **Internal resolution** sets how sharp the picture is, like
  in an emulator: Native is the PS3's 1280 x 720; 1080p, 1440p and 4K draw the
  game larger (sharp on big screens, more work for the graphics card: the
  launcher names the step that matches your screen); Lower and Lowest draw the
  3D scene smaller for weak graphics cards (laptops, integrated graphics), the
  HUD stays sharp. **Auto** picks the step that matches your screen, at most
  1080p on integrated graphics (they share the processor's memory and power,
  so a larger picture slows the whole game there). Since 1.1.4 Auto is the
  default on integrated graphics (from the second game on: the launcher reads
  the first game's log to know); a step you choose stays, and above Auto's step
  Settings and the Play offline tab say that it slows the processor too. It only
  changes the picture, so the other player online does not need the same
  setting. If fights drop below 60 fps, go one step down. More in
  [Troubleshooting](docs/TROUBLESHOOTING.md#low-frame-rate).
- **Settings** -> **VSync**: On (smooth, default) or Off (lowest latency, the
  picture may tear). The game always runs at 60 fps, like on the PS3, so there
  is no frame rate setting. Online, each player can choose their own.
- **Settings** -> **Stage blur / glow**: some stages soften the whole picture
  (the misty swamp, and three more) or let the sun glow (the scrapyard). Off
  (the default since 1.1.4, also for players of older versions once) shows
  those stages sharp, without the glow; On looks as on the PS3, at every
  internal resolution. Online, each player can choose their own.
- **Settings** -> **Graphics (weak graphics cards)**: Shadows and Effects, On
  (default) or Off. Effects Off also hides the hit sparks and other hit effects
  (the EWGF lightning too), flames, smoke, mist and waterfalls. **Lowest (old
  graphics cards)** sets Internal resolution Lowest and switches stage blur /
  glow and shadows off; effects stay on (the hit effects show what happens in
  a fight); **Default** puts them back. Each also leaves
  the processor less to translate. Online, each player can choose their own.
- **Settings** -> **Power saving (laptops, handhelds)**: Auto (default) turns
  it on with a battery, battery saver or the Power saver plan, a mobile
  processor or integrated graphics; On and Off decide yourself. The game then
  uses fewer helper threads and never busy-waits, so the processor stays
  cooler and keeps its clock; the window title says "power saving". The game
  itself is the same, so online the other player does not need the same
  setting. Not tried on a real laptop or handheld yet; see
  [Troubleshooting](docs/TROUBLESHOOTING.md#game-speeds-up-or-slows-down-on-a-laptop-or-handheld).
- **Settings** -> **Training overlay**: in Practice the game shows your last
  inputs (directions as arrows, 1 2 3 4 for the buttons, with how many frames
  each was held) and, after each exchange, the startup of the move (`i10`) and
  who can act first (`BLOCK +3`, `HIT -12`). Off / Inputs / Inputs + frame data;
  it can also be on in the other offline modes, and online (only your own
  inputs). **F2** in the game switches it. It only reads the game, so it never
  changes a match. More in [docs/TRAINING.md](docs/TRAINING.md).
- **Settings** -> **Practice tools** (Practice, offline only; default on): hold
  **SELECT** and press 3 to put both fighters back where the fight started
  (f+3 / b+3: the dummy against the wall in front of / behind you; df+3 /
  db+3: you against the wall), 1 / 2 / 4 to record the dummy, play it once or
  in a loop (5 slots), and tap forward / back for what the dummy does. More in
  [docs/TRAINING.md](docs/TRAINING.md#practice-tools-115).
- **Settings** -> **Unlocks** (offline play; all Off by default):
  - **Unlock all stages**: the Tekken 5 stages (the old ones, normally earned
    after about 50 fights, a few Arcade runs) are there in Arcade, VS, Practice
    and the rest, without clearing Arcade. Your save is not changed: switched off, the
    game is as before.
  - **Unlock Jinpachi and Random select**: the character select has Jinpachi
    (top row, right end) and the random cell (top row, left end) without
    clearing Arcade. Your save is not changed. Online you do not need it: casual
    matches and rooms always have both, ranked never.
  - **Unlock all customization items**: everything in **ITEM SHOP & EQUIP**
    (after picking a fighter in Arcade, Ghost or Survival) costs 0 Fight Money.
    What you take stays in your save like a bought item, also after switching
    it off; the launcher backs up your save once before the first game with it
    (in `save-backups` in the game's folder; copy it back to undo).
  - Online play does not use the stage unlock: there both players always have
    the same stages to pick from (the lobby picks the stage). What you took in
    the item shop and put on does show online, as your custom costume (from
    1.1.3; see "Online").
- **Esc** closes the game. The **Stop game** button does too. In an online
  match press Esc twice: closing the game there (Esc, Alt+F4, the window's X)
  counts as a loss.
- Two players on one PC: connect a second pad, then choose Versus.
- Tips for now:
  - Go back to the title screen as little as you can (memory bug).
  - Do not leave the game idle at the title.
  - Do not use the game's own **Online** menu entry (see "Online").

## Controls

Keyboard (default) and Xbox controller:

| Action | Keyboard | Xbox pad |
|---|---|---|
| Move, menus | Arrow keys | D-pad, left stick |
| Left punch (1) | A | X |
| Right punch (2) | S | Y |
| Left kick (3) | Z | A |
| Right kick (4) | X | B |
| L1 / R1 | Q / W | LB / RB |
| L2 / R2 | 1 / 2 | LT / RT |
| Start | Enter | Start |
| Select | Tab | Back |
| Quit the game | Esc | |

- The keyboard works only while the game window has the focus. Pads work even
  when it does not.
- Keyboard and the first pad both drive player 1. Online, the controller you
  press is your player, whichever port it has (a pinned `[port1] device` in
  `controls.ini` stays the only one).
- PlayStation pads (DualShock 4, DualSense) are read directly, over USB and
  Bluetooth, also after Steam or DS4Windows used them (no Steam needed; started
  through Steam with Steam Input on, the game uses Steam's virtual pad instead).
  Arcade sticks and hitboxes are read through DirectInput. Nothing to install.
  An arcade stick was tried on real hardware: every input came through.
- Pads can be plugged in or out while the game runs.
- In the launcher's Online tab a pad or stick runs the lobby without mouse or
  keyboard: A / Cross accepts, rematches and searches, B / Circle declines and
  stops (DualShock 4 and DualSense too, also over Bluetooth after Steam or
  DS4Windows used them). Only while the launcher is in front. See "Controller in the launcher"
  in https://github.com/TheWishin/T5DROnline/blob/main/docs/ONLINE.md
- **Pad, arcade stick, hitbox or keyboard: set the buttons in the launcher.** Open
  **Settings** and click **Set up controllers...**. The window lists the
  controllers Windows sees and the keyboard, one row per player, and lights the
  row when you press a button (the row also names the game button it is). Pick a
  controller (or just press a button on it; the keyboard: click its row), then
  click **Set up all buttons**: it asks "Press the button for 1 (Left Punch)..."
  and goes on with 2, 3, 4, 1+2, 3+4, 1+3, 2+4, 1+2+3+4, L1, R1, L2, R2, L3, R3,
  Start and Select -- every button of the PS3 pad and every Tekken combo can
  have a key or button of its own, also online. **Skip** keeps a button as it is,
  **Clear** gives it no button. **Set selected** sets one row (also the other
  macros: 1+4, 2+3, 1+2+3 and so on), **Set up directions** is for sticks that
  send their directions as buttons. **Layout** starts from a ready layout: Xbox,
  PlayStation, Switch, arcade stick with 8 buttons (Vewlix), 6 buttons
  (Noir / Sega Astro) or hitbox. For a hitbox you also choose what happens when
  left and right are pressed together (SOCD) and whether the left stick counts as
  a d-pad. **Save** writes `native\controls.ini`; the game reads it when it
  starts. **Reset to defaults** takes the controller back to the default buttons.
  Your comments and other settings in the file are kept.
  With the controller itself: Up / Down choose a button, Cross sets it,
  Triangle clears it, Start saves, Circle closes (the controller's buttons as
  your `controls.ini` has them). This works only while that window is in front;
  untick "Move through this window with the controller" to only test buttons.
- Everything else is set in `controls.ini`. The documented
  sample with every default is `docs\controls.ini` in this folder.
  Put your file at `native\controls.ini` and restart the game.
  Examples (from the sample):
  - `[keys1]` / `preset = tekken` -- WASD to move, U I J K for the buttons.
  - Two players on one keyboard: `[keys1] preset = tekken` and
    `[keys2] preset = numpad`.
  - `1+2 = O` -- one key for two buttons.
- The game's own Options menu can also change the button layout, for offline
  play only (online games use a fresh save of their own, see "Online").
- A test zip made before 2026-10-16 evening has only the keyboard and Xbox pads.
  `controls.ini` and DirectInput came later.

## Online

1. Start the launcher and open the **Online** tab. The public server
   "T5DR Online" is preselected.
2. Click **Play as guest**, or **Log in**. Ranked needs an account: create one in
   the tab and keep the recovery codes it shows.
3. Search a **quick** or **ranked** match, or open a lobby room for a friend
   (a **Training room** to practise together, from 1.1.5).
   When an opponent is found you see the ping and accept within 15 seconds.
4. The game shows its own character select. Pick your fighter with the pad,
   stick or keyboard within 30 seconds: the button you confirm with picks the
   costume, **Select** (Tab on the keyboard, Back on an Xbox pad) picks at
   random. In quick matches, rooms and friend invites the top row also has
   **Jinpachi** (right end) and the game's **random cell** (left end) for both
   players; ranked matches and tournaments have neither. Mokujin's copied
   fighter and the random cell draw anew in every match (the same on both
   PCs). If you pick nothing, you get the character set in the launcher.
   When both of you have picked, the fight starts: first to 3 rounds. The name
   under your fighter counts the seconds down; "PICKING..." under the opponent
   means you wait for their pick.
5. Afterwards pick **Rematch** or **Next game**. A rematch goes back to the
   character select. In a ranked set the fighters of the first game stay for
   every rematch. The game stays open between matches.

Good to know:

- The two PCs send each other the controller inputs directly. If their routers
  don't allow that, a relay server passes them on (the lobby picks the one
  nearest to both of you). With a direct connection each PC learns the other's
  IP address.
- Quick and ranked search look for an opponent with a low ping first and widen
  the search while you wait: any ping after 30 seconds (quick) or 60 seconds
  (ranked). The ping shown for a found match counts the nearest relay server.
  From 1.1.5 the Ping column does too, "~" marks an estimate, and two players
  who played each other in the last 7 days count with the ping they measured.
  A found match, a challenge and an invite also say whether the match will
  most likely be direct or relayed.
- A cable is better than Wi-Fi.
- The first time, Windows Firewall asks whether the game and Python may use the
  network. Allow it for **private networks**. Clicked Cancel? Matches still
  connect, some only through the relay; the Online tab shows a firewall line
  with **How to fix**.
- Netcode: rollback, like Tekken 6 Native Online. Input delay follows the ping:
  1 frame up to about 60 ms, 2 above; from 1.1.5 at least 3 frames above
  150 ms and 4 above 250 ms (ranked too), so far matches jump less.
  **Settings -> Online input delay** can
  fix it at 0, 1 or 2 frames; it counts only when your opponent picked the
  same, otherwise Auto. Ranked matches always use 2. If a match stutters on a
  slow PC, one player can switch to delay netcode: Settings -> "Advanced:
  extra settings" -> `T5_RB_MODE=off`.
- Online games keep a save of their own (`gamedata-online` in the game's
  folder), the same fresh one on both PCs: what you set in the game's own
  **OPTIONS** (button layout, round time, difficulty) and your unlocks apply
  offline only, so both players always play the same game. Set your buttons in
  the launcher (Settings -> Set up controllers); they work online too. Your own
  save is never touched by online play. Only your custom costume is read from
  it (see below).
- Nobody can pause an online fight (from 1.1.2): **Start** does not open the
  pause menu there, for either player. From 1.1.4 the fighters' intros and the
  replay after a round are skipped once **both** players have pressed **Start**
  during them (one player alone skips nothing).
  To quit a match, close the game (Esc twice): that counts as a loss, as before.
- Ranked uses a Glicko-2 rating shown with Tekken 5's own rank names and, from
  1.1.4, the game's own rank plates (Beginner, 9th kyu ... Tekken Lord) next to
  every name. The launcher reads the plates from your unpacked game after BUILD
  GAME (they are not in the download); before that it shows a text badge in the
  plate's colour. Leaving or disconnecting counts as a loss. A desync voids the
  match.
- **Friends** (accounts, from 1.1.2): add a friend by account name on the Online
  tab's **Friends** page. Once they accept, you see when they are online,
  searching or in a match. **Invite to a match** (or to your room) asks them;
  one click on **Accept** on their side starts it. Blocking a player ends the
  friendship.
- **Your custom costumes online** (from 1.1.3): what you bought and put on in
  the item shop offline shows in online matches, for you and your opponent.
- **Tournaments** (accounts, from 1.1.3): the Online tab's **Tournaments** page
  lists the server's tournaments. **Sign up** (and **Check in** when it asks),
  and when your set is ready the tab shows "Your tournament set is ready":
  **Accept** within 5 minutes and the game starts by itself. Sets are best of 3
  or 5, played like casual sets with the in-game select; the bracket (single or
  double elimination) fills in by itself. Tournament hosts create them with
  **Create...**. There are 20 host slots: if you want to host tournaments, DM
  **wishin**. See [docs/TOURNAMENTS.md](docs/TOURNAMENTS.md).
- **Private and community rooms** (from 1.1.3): **Create room** asks how many
  players (2 to 8) and who can join: anybody, a password or an invite code; it
  can also hide the room from the list. Others select it and press **Join
  room** (it asks for the password), or type the invite code into **Join room**
  with no room selected. Share the code with **Copy invite code**: it appears in
  the field next to the button, press Ctrl+C there. In a room for 3 or more you
  take turns, one match after another, by **Winner stays** or **Everyone in
  turn**; **Sit out** skips your turns. The host can change the password and
  remove a player in **Room settings...**. A friend you invite to your room needs
  no password. Only a private room's players can watch its matches. These rooms
  are casual. See [docs/ONLINE.md](docs/ONLINE.md) "Rooms".
- **Training rooms** (from 1.1.5): **Create room -> Training room**. You and a
  friend fight with endless health: damage never KOs, health refills, no round
  timer, nothing is counted. Hold **SELECT** for a second to give up and go back
  to the character select; **Leave room** works any time. Both need 1.1.5.
- **Sides, stages and a handicap in casual matches** (from 1.1.5): next to
  Strict on the Play online tab, ask for P1, P2 or any side and for a stage
  (or Random) for challenges, invites and rooms; when both want the same, a
  coin flip decides. **Rematch: swap sides** (Y on a pad) swaps them for the
  rematch. **My health (casual)** sets your health from 150 % (since 1.1.7;
  before: 100 %) down to 30 %;
  both players see both values. Ranked and tournament matches are unchanged.
  See [docs/ONLINE.md](docs/ONLINE.md) "Training rooms and the health handicap".
- **Stats and your history** (from 1.1.5): the **Stats** page next to the
  Leaderboard shows the server's matches and every fighter's win rate (all,
  ranked, casual); your profile shows your record, the win rate of each of
  your fighters and your match history, where **Watch replay** plays a match
  that has a replay on this PC.
- More in [docs/ONLINE.md](docs/ONLINE.md) and [docs/RANKED.md](docs/RANKED.md).

### Start a search from a shortcut

From 1.1.5, `T5DR Online.exe --search ranked` opens the launcher on the Online
tab, logs in and starts a ranked search. `--search casual` starts a quick
match instead. This works only with a saved login: log in once with your
account and **Remember me** ticked. Without a saved login, the tab opens and
tells you to log in. Then click the search button yourself.

- **Desktop shortcut:** right-click `T5DR Online.exe` -> **Show more options**
  -> **Create shortcut** (Windows 11). Open the shortcut's **Properties** and
  add ` --search ranked` at the end of **Target**, after the closing quote:
  `"C:\Games\T5DR\T5DR Online.exe" --search ranked`
- **Steam** (as a non-Steam game): add `T5DR Online.exe` with **Games -> Add a
  Non-Steam Game to My Library**, then **Properties -> Launch options**:
  `--search casual`

### Spectating

A friend in a match, any room's match or a tournament set can be watched live:
**Watch** on the Friends page (below the list), in the Rooms list, or above a
tournament's bracket (click the set first). Your game shows the match a
few seconds behind, exactly as it is played (the same inputs, checked while it
plays). Whenever you join, it plays the players' session from its start (a
rematch depends on the matches before it). Settings -> Spectators: "Friends and
room visitors may watch my online matches" (on) and "Also my ranked matches"
(off); a match is watched only when both players allow it. Both players' custom
costumes show for the spectators too. Details: [docs/SPECTATE.md](docs/SPECTATE.md).

### Replays

Every online match is saved as a replay (a few KB, in `native\replays`). The
**Replays** tab lists them with date, fighters, result and opponent; **Watch**
plays the match again in the game, exactly as it happened: the same inputs
frame by frame, checked against the live match while it plays (the tab says
"identical to the live match" at the end). While it plays, **START** (Enter)
pauses, **SELECT** (Tab) ends it. A rematch is shown after the matches before
it in the same session (a rematch starts from what the match before it left).
The tab can switch recording off or leave the players' names out. A
replay plays only with the game version that recorded it. Details:
[docs/REPLAYS.md](docs/REPLAYS.md).

The game's own **Online** menu entry needs Sony's servers, which are gone: after
the terms screen it says "A network error occurred" and goes back to the title.

You can run your own server: on a small Linux VPS, with Docker, on a Mac, or
with **Host for friends** in the launcher. See [docs/HOSTING.md](docs/HOSTING.md).

## Updating

The launcher offers new versions; click **Update**.

- At start (at most once an hour) and with **Check for updates** at the top,
  the launcher asks GitHub for the newest published release. It shows the
  version, what is new and the download size.
- **Update now** downloads the zip (about 90 MB), checks it against the
  published SHA-256 checksum and (from 1.1.5) the release's signature by the
  project's release key, replaces the program files and starts the
  launcher again. That takes a few seconds plus the download.
- Your `native` folder (unpacked game, saves, logs) and your settings stay as
  they are.
- If the new version changes the game code, the Play offline tab says **Build the game
  once (about 2 minutes)**. Click **BUILD GAME**. Only the code is rebuilt.
- The launcher never updates while the game, a build or an online match (or a
  search) is running. If anything goes wrong, it puts the old files back and
  says why.

By hand (versions 1.0.0 and older, which cannot update themselves, or if the
update keeps failing):

1. Extract the new release into a **new** folder.
2. Copy your old `native` folder into it. This keeps the unpacked game and your
   saves.
3. Start the launcher. If the new version changes the game code, the Play offline
   tab says so. Click **BUILD GAME** again. Only the code is rebuilt.

## Bug reports

**First try "Check my problem"** (Play offline tab; on the Build tab after a
failed build, from 1.1.5). It looks in this PC's logs and settings for the
problems other players had and says how to fix each. Nothing is sent.

**Problems? Click "Report a problem"** (Play offline tab; also in the Build tab,
and in the Play online tab after a match). The launcher makes ONE zip on your Desktop and
opens its folder. Send the zip to the person who gave you the game, or attach it
to an issue at https://github.com/TheWishin/T5DROnline/issues. You can add a few
words about what happened in the window.

The zip holds the newest game logs, `build.log` when the build was the problem,
the launcher's log, the files of your last online match, your newest replay
(inputs only, the players' names taken out), your `controls.ini`,
desync dumps if there are any, and `system.txt`: Windows version, processor,
graphics card and driver, memory, screens (refresh rate, scaling), the release
version and build id, and the settings you use. The window lists everything
before it saves. Nothing is uploaded: you send the zip yourself.

Before the zip is made, your Windows user name in file paths becomes `<user>`,
internet IP addresses become `<ip>` (addresses of your own network stay), and
passwords, tokens and match keys are left out. The zip is at most 20 MB; a
bigger log keeps its start and its end. Your game files, keys, `.pkg` and `.rap`
are never in it.

If the launcher itself does not start, send by hand `native\build.log` (build
problems) or the newest file in `native\logs\` (game problems), plus your Windows
version, graphics card and what you did just before. Those files contain folder
paths with your Windows user name, so look at them before you post them in public.

More help: `docs\TROUBLESHOOTING.md` in this folder.

## FAQ

**Do I need a PS3 or RPCS3?** No. You need the `.pkg` and `.rap` of your own
purchase. RPCS3 is not used or installed.

**Can I use a disc copy, the EU/JP version or another version?** No. Only
NPUB30009 version 01.00. The builder refuses everything else.

**Where can I get the game?** From your own PlayStation Network account. We do
not provide the package or the license and cannot help to get them.

**Does it run on Linux or macOS?** macOS on Apple silicon: yes, offline, built from source
(see "Building on macOS"). No release zip or launcher there yet, and online play is a test build
(docs/MACOS_ONLINE_TEST.md). Linux: not
supported, but players run the Windows release under Proton or Wine; what they found is in
[docs/TROUBLESHOOTING.md "Linux and Steam Deck"](docs/TROUBLESHOOTING.md#linux-and-steam-deck-wine-proton).

**Does it run on Windows on ARM (Snapdragon laptops)?** Not tested. Windows 11
should run it through its x64 emulation, more slowly; Windows 10 on ARM cannot.
See `docs\TROUBLESHOOTING.md`, "Windows versions and other PCs".

**Why does the build need the internet?** Once, to fetch about 50 KB of public
key data from github.com (see Credits).

**Why is Windows warning me about the launcher?** `T5DR Online.exe` is a tiny
unsigned starter. Code signing is not set up yet.

**Where are my saves?** In `native\gamedata`. The Play offline tab has an **Open
saves folder** button. Back it up before you experiment.

**Is the PSN "Online" mode coming back?** No. The servers are gone. Online play
will use our own lobby.

**How do I uninstall?** Delete the folder.

## Credits

- **[ps3recomp](https://github.com/sp00nznet/ps3recomp)** by Ned Heller
  (sp00nznet) and contributors (MIT). It lifts the PS3 code and provides the
  runtime libraries: D3D12 graphics, WASAPI audio, XInput pads. We build against
  **NoahBPeterson's branch** `infamous/upstream-sync`
  (https://github.com/NoahBPeterson/ps3recomp), pinned at commit `f17bcd3`, plus
  our patches in `patches/ps3recomp/`.
- **n0madic** -- the macOS (Apple silicon) port: Metal renderer fixes, SDL2
  sound, VideoToolbox movies (ps3recomp patches 0071-0073, 1.1.5).
- **[Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online)**
  by Ekspym. The inspiration for how this project works: a build-it-yourself
  launcher, a lobby and rollback netcode.
- **RPCS3** -- we never run or install it. We followed its open source as a
  reference for the PS3 package and license (NPDRM) decryption. The build also
  downloads two public text files from its repository (`rpcs3/Crypto/key_vault.h`
  and `key_vault.cpp`) to read the public key tables from them.
- The ATRAC3plus music decoder is FFmpeg's, via PPSSPP's `at3_standalone`
  (LGPL-2.1 or later), as vendored by ps3recomp.
- Movies are decoded with Windows Media Foundation (VideoToolbox on macOS).
- The release zip also carries Python (PSF license) and LLVM clang-cl / lld-link
  (Apache-2.0 with LLVM exception). Their license texts are in `LICENSES\`.
- The game itself is the work of Bandai Namco and the original Tekken team.
- Developed with the help of Claude (Anthropic), an AI assistant.

## Legal

No Sony or Namco code, keys or assets are in this repository or in a release.
You must own the game. The game's program, its data, the translated code, the
keys and your `.pkg` / `.rap` stay on your own PC. Git ignores them, and the
project's CI runs a guard that fails on anything game-derived.

This is a fan project. It is not affiliated with or endorsed by Bandai Namco
Entertainment or Sony Interactive Entertainment. Tekken is a trademark of Bandai
Namco. Rules about decrypting and converting games you own differ by country.
You are responsible for following yours. This is not legal advice.

This project's own code and docs are under the MIT License (`LICENSE`). Source code:
https://github.com/TheWishin/T5DROnline-Source
ps3recomp is MIT-licensed too. The license covers none of the game.
<!-- players:end -->

## Building from source

Most players should use the release zip. Developers build like this.

You need Windows 10/11, Visual Studio 2022 Build Tools (MSVC x64, Windows SDK,
CMake + Ninja, clang-cl), Python 3.10+ and Git. The launcher's Build tab can
install the Visual Studio parts for you (winget, with your consent).

```
python tools/build_game.py --pkg <your.pkg> --rap <your.rap>
python tools/run_game.py [--log FILE] [NAME=VALUE ...]
```

`build_game.py` fetches ps3recomp at the pinned commit, applies
`patches/ps3recomp/*.patch` in name order, then unpacks, decrypts, lifts and
compiles. Each step is skipped when its output exists. `--out DIR` puts all
output under DIR.

## Building on macOS

Apple silicon, macOS 13 or newer, Xcode command line tools and
`brew install cmake ninja sdl2 glslang spirv-cross` (glslang and spirv-cross translate the game's
shaders for Metal). Python 3.10+ with pycryptodome; Homebrew's Python refuses a plain `pip install`,
so use a virtual environment:

```
python3 -m venv .venv && .venv/bin/pip install pycryptodome
.venv/bin/python tools/build_game.py --pkg <your.pkg> --rap <your.rap> --out native
.venv/bin/python tools/run_game.py --out native
```

Offline only for players: online play on a Mac is a test build until a Mac-vs-PC match is proven in sync
(`--macos-online`, docs/MACOS_ONLINE_TEST.md); the launcher and the release zip are Windows-only. Keyboard: arrow keys
(d-pad), Space (cross), Q (circle), E (square), R (triangle), U/O (L1/R1), Return (start), Tab
(select); the sticks are W/A/S/D and I/J/K/L. `PS3_PAD_FILE=<file>` drives the pad from a script.

Where to read on:

- `docs/` — how each part works: rendering, netplay, rollback, the lobby, hosting,
  releases.
- `docs/RELEASE.md` — the launcher, the zip and how it is packaged
  (`tools/package_release.py`).
- `docs/ONLINE.md` — the lobby: protocol, NAT traversal, self-hosting.
- `docs/CI.md` — continuous integration and the game-data guard
  (`python tools/check_no_game_data.py` before you commit).
- `docs/controls.ini` — every control setting.
- `docs/TRAINING.md` — the training overlay (input display, frame data) and the
  runtime's overlay layer it draws with.
- `docs/TROUBLESHOOTING.md` — fixes for players.
- `docs/WEAK_PC.md` — why some PCs run fights at 40-50 fps (causes, what the logs
  show, measurements, D3D12 vs Vulkan) and a checklist to paste to players.
- `CHANGELOG.md` — what landed, by day.

**Never commit anything game-derived.** The repository is public.
