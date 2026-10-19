# Tekken 5: Dark Resurrection Online — native Windows port

Tekken 5: Dark Resurrection (PS3, PlayStation Network release) running natively
on Windows. It is recompiled, not emulated. Online play between friends is
being built.

**Release 1.1.0 (2026-10-19).** Download
`T5DR-Online-1.1.0.zip` from https://github.com/TheWishin/T5DROnline/releases

**Offline play is ready:** all modes, 60 fps, Xbox pad and arcade stick tested.
**Online works:** tested between two players' PCs over the internet (direct
connection, 26 ms ping, 60 fps). Please end matches normally, not with Alt+F4.

<!-- players:start -->
Found a bug? Please report it (see "Bug reports" below).

Deutsch: `docs\README.de.md` in this folder.

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

## Status (2026-10-17)

Tested on one development PC (Windows 11, 16-core Ryzen 9, RTX 3090). Online play was
tested between two real PCs over the internet (AMD/60 Hz vs Intel/240 Hz).

| Area | State |
|---|---|
| Start-up | Works. Boots, opens the window, reaches the title, menus, character select and fights. |
| Menus, fights | 60 fps, also with other programs busy on the PC. Weaker PCs are not measured yet. |
| Game modes | Arcade, Ghost, Versus (two players on one PC), Survival and Practice work. Gallery and the game's own Online menu need Namco's and Sony's servers (gone) and say so. |
| Fighters, stages | All fighters and stages render correctly, including faces, floor shadows and background figures. |
| Display | Resizable window, borderless fullscreen (Alt+Enter or F11). **Internal resolution** from Lowest (0.5x) over Native (720p) to 1080p, 1440p and 4K (launcher Settings, `PS3_INTERNAL_RES`); every step checked in fights, menus, movies and character select. |
| Music, sound effects, movies | Work. |
| Controls | Keyboard, Xbox pads (XInput), PlayStation pads, arcade sticks and hitboxes (DirectInput), two local players, buttons set in the launcher (Settings -> Set up controllers) or in `controls.ini`. Short taps are never lost. Tried by a person: an Xbox pad and an arcade stick, every input came through, smooth. |
| Input lag | A jab shows on screen about 35-40 ms after the press in fullscreen (the PS3 on a TV: ~42 ms plus the TV), a frame less than before. In a window add one frame (Windows draws the window). |
| Saving | Works. The in-game clock shows the real date. |
| Long sessions | The old memory bug (white screen after a few trips through the title) is fixed. |
| Online play | Works on one PC and through the public lobby server. Rollback netcode: 1 frame of input delay up to ~60 ms ping, 2 above (Settings -> Online input delay; ranked: always 2), about 60 fps at 150 ms ping on an 8-thread PC (now and then a picture is shown twice), tested at 0/50/150 ms ping with packet loss. Played between two real PCs over the internet (2026-10-18). |
| Build from your copy | Works on the development PC. |

## Requirements

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
  AMD FX, A-series or Ryzen (2011) or newer. AVX2 is not needed. With AVX2
  (Intel 4th-gen Core / AMD Ryzen and newer) the build makes faster code; the
  launcher decides this by itself. Only tested on a CPU with AVX2.
- Speed: fights held 60 fps with 4 CPU threads in our tests (fast desktop
  cores); online against a far-away player (rollback, 150 ms) about 50 fps.
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

- The launcher speaks English or German (Deutsch). **Settings** -> **Language**:
  Auto follows the language of Windows. A change applies when the launcher
  starts again (the **Restart now** button does that). The game itself stays
  in English.
- The game opens in its own window and scales its picture to the window.
  **Settings** has window sizes, maximized, borderless fullscreen and mute.
- **Settings** -> **Internal resolution** sets how sharp the picture is, like
  in an emulator: Native is the PS3's 1280 x 720; 1080p, 1440p and 4K draw the
  game larger (sharp on big screens, more work for the graphics card: the
  launcher names the step that matches your screen); Lower and Lowest draw the
  3D scene smaller for weak graphics cards (laptops, integrated graphics), the
  HUD stays sharp. It only changes the picture, so the other player online
  does not need the same setting. If fights drop below 60 fps, go one step
  down. More in [Troubleshooting](docs/TROUBLESHOOTING.md#low-frame-rate).
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
- Keyboard and the first pad both drive player 1.
- PlayStation pads (DualShock 4, DualSense), arcade sticks and hitboxes are read
  through DirectInput. Nothing to install. An arcade stick was tried on real
  hardware: every input came through.
- Pads can be plugged in or out while the game runs.
- In the launcher's Online tab a pad or stick runs the lobby without mouse or
  keyboard: A / Cross accepts, rematches and searches, B / Circle declines and
  stops. Only while the launcher is in front. See "Controller in the launcher"
  in https://github.com/TheWishin/T5DROnline/blob/main/docs/ONLINE.md
- **Pad, arcade stick or hitbox: set the buttons in the launcher.** Open
  **Settings** and click **Set up controllers...**. The window lists the
  controllers Windows sees, one row per player, and lights the row when you
  press a button (the row also names the game button it is). Pick a controller
  (or just press a button on it), then click **Set up all buttons**: it asks
  "Press the button for 1 (Left Punch)..." and goes on with 2, 3, 4, 1+2, 3+4,
  1+3, 2+4, 1+2+3+4, Start and Select. **Skip** keeps a button as it is,
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
- The keyboard and everything else is set in `controls.ini`. The documented
  sample with every default is `docs\controls.ini` in this folder.
  Put your file at `native\controls.ini` and restart the game.
  Examples (from the sample):
  - `[keys1]` / `preset = tekken` -- WASD to move, U I J K for the buttons.
  - Two players on one keyboard: `[keys1] preset = tekken` and
    `[keys2] preset = numpad`.
  - `1+2 = O` -- one key for two buttons.
- The game's own Options menu can also change the button layout.
- A test zip made before 2026-10-16 evening has only the keyboard and Xbox pads.
  `controls.ini` and DirectInput came later.

## Online

1. Start the launcher and open the **Online** tab. The public server
   "T5DR Online" is preselected.
2. Click **Play as guest**, or **Log in**. Ranked needs an account: create one in
   the tab and keep the recovery codes it shows.
3. Search a **quick** or **ranked** match, or open a lobby room for a friend.
   When an opponent is found you see the ping and accept within 15 seconds.
4. The game shows its own character select. Pick your fighter with the pad,
   stick or keyboard within 30 seconds: the button you confirm with picks the
   costume, **Select** (Tab on the keyboard, Back on an Xbox pad) picks at
   random. If you pick nothing, you get the character set in the launcher.
   When both of you have picked, the fight starts: first to 3 rounds. The name
   under your fighter counts the seconds down; "PICKING..." under the opponent
   means you wait for their pick.
5. Afterwards pick **Rematch** or **Next game**. A rematch goes back to the
   character select. In a ranked set the fighters of the first game stay for
   every rematch. The game stays open between matches.

Good to know:

- The two PCs send each other the controller inputs directly. If their routers
  don't allow that, the lobby server relays them. With a direct connection each
  PC learns the other's IP address.
- A cable is better than Wi-Fi.
- The first time, Windows Firewall asks whether the game and Python may use the
  network. Allow it for **private networks**.
- Netcode: rollback, like Tekken 6 Native Online. Input delay follows the ping:
  1 frame up to about 60 ms, 2 above. **Settings -> Online input delay** can
  fix it at 0, 1 or 2 frames; it counts only when your opponent picked the
  same, otherwise Auto. Ranked matches always use 2. If a match stutters on a
  slow PC, one player can switch to delay netcode: Settings -> "Advanced:
  extra settings" -> `T5_RB_MODE=off`.
- Ranked uses a Glicko-2 rating shown with Tekken 5's own rank names. Leaving or
  disconnecting counts as a loss. A desync voids the match.
- More in [docs/ONLINE.md](docs/ONLINE.md) and [docs/RANKED.md](docs/RANKED.md).

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
  published SHA-256 checksum, replaces the program files and starts the
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

**Problems? Click "Report a problem"** (Play offline tab; also in the Build tab,
and in the Play online tab after a match). The launcher makes ONE zip on your Desktop and
opens its folder. Send the zip to the person who gave you the game, or attach it
to an issue at https://github.com/TheWishin/T5DROnline/issues. You can add a few
words about what happened in the window.

The zip holds the newest game logs, `build.log` when the build was the problem,
the launcher's log, the files of your last online match, your `controls.ini`,
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

**Does it run on Linux or macOS?** No. Only Windows runs a recompiled title
today.

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
- **[Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online)**
  by Ekspym. The inspiration for how this project works: a build-it-yourself
  launcher, a lobby and rollback netcode.
- **RPCS3** -- we never run or install it. We followed its open source as a
  reference for the PS3 package and license (NPDRM) decryption. The build also
  downloads two public text files from its repository (`rpcs3/Crypto/key_vault.h`
  and `key_vault.cpp`) to read the public key tables from them.
- The ATRAC3plus music decoder is FFmpeg's, via PPSSPP's `at3_standalone`
  (LGPL-2.1 or later), as vendored by ps3recomp.
- Movies are decoded with Windows Media Foundation.
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

Where to read on:

- `docs/` — how each part works: rendering, netplay, rollback, the lobby, hosting,
  releases.
- `docs/RELEASE.md` — the launcher, the zip and how it is packaged
  (`tools/package_release.py`).
- `docs/ONLINE.md` — the lobby: protocol, NAT traversal, self-hosting.
- `docs/CI.md` — continuous integration and the game-data guard
  (`python tools/check_no_game_data.py` before you commit).
- `docs/controls.ini` — every control setting.
- `docs/TROUBLESHOOTING.md` — fixes for players.
- `CHANGELOG.md` — what landed, by day.

**Never commit anything game-derived.** The repository is public.
