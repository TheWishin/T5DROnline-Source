# Tekken 5: Dark Resurrection Online — native Windows port

Tekken 5: Dark Resurrection (PS3, PlayStation Network release) running natively
on Windows. It is recompiled, not emulated. Online play between friends is
being built.

**No release zip is published yet (2026-10-16).** Until one is, see "Building
from source" at the end of this page.

<!-- players:start -->
**Test release. Expect bugs.** Please report them (see "Bug reports" below).

Deutsch: https://github.com/TheWishin/T5DROnline/blob/main/docs/README.de.md

## What is this?

- The PS3 game's program is translated to C++ ahead of time (static
  recompilation) and compiled into a normal Windows program. No emulator runs.
- The model is the same as
  [Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online).
  This repository and its releases contain **no part of the game**.
- You build the game on your own PC from **your own copy**: the PSN package
  (`.pkg`) and the license (`.rap`) from your own account. The launcher does
  this for you.
- Online play between friends (a lobby, the two PCs talk directly) is the goal.
  It is **not playable yet**. See "Online".

## Status (2026-10-16)

Tested on one development PC (Windows 11, 16-core Ryzen 9). Not yet tried on a
clean PC.

| Area | State |
|---|---|
| Start-up | Works. Boots, opens the window, reaches the title, menus, character select and fights. |
| Menus | 60 fps. |
| Fights | Run, but at about 30-45 fps, not 60. Being worked on. |
| Game modes | Arcade, Ghost, Versus (two players on one PC), Survival and Practice work in test runs. Options work too, but "Delete Save Data" does nothing. Gallery needs PSN and fails cleanly offline. |
| Fighters, stages | Render correctly. 14 fighters and 12 stages were tried. |
| Graphics glitches | Every fighter's face is dark (brown/black). Light see-through rectangles on floors/walls in some stages. Some background figures are flat white. |
| Music, sound effects | Work. Short drops can happen when the frame rate dips. |
| Movies | Intro and title movies play with sound. They slow down when the game runs under 60 fps. |
| Keyboard, Xbox pad | Work. |
| PlayStation pads, arcade sticks | Built in (`controls.ini`). Not yet tried on real hardware by a person. |
| Saving | Unreliable. The first save on a fresh profile can fail without a message. Saves worked in other tests. The in-game clock reads 1970. |
| Long sessions | Memory bug. After about two trips through the title screen, or about 3 minutes idle at the title, the screen can turn white or the game can crash. Restart the game. A fix is in progress. |
| Online play | In progress. Not playable yet. |
| Build from your copy | Works on the development PC (about 90 seconds). Not yet tried on a clean PC. |

## Requirements

- Windows 10 or 11, 64-bit.
- A graphics card with DirectX 12, and a 64-bit CPU with SSE4.1 (practically
  every PC of the last 10+ years).
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
6. **Play** tab: type a name (optional) and click **PLAY**.

Everything the build makes stays in the `native` folder next to the launcher.
It is game data. Do not share it. To uninstall, delete the whole folder.

## Playing

- The game opens in its own window. It draws at 1280 x 720 and scales to the
  window. **Settings** has window sizes, maximized, borderless (experimental:
  not yet tested with the real game window) and mute.
- **Esc** closes the game. The **Stop game** button does too.
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
  through DirectInput. Nothing to install. Not yet tried on real hardware by a
  person.
- Pads can be plugged in or out while the game runs.
- To change keys or buttons, make a `controls.ini`. The documented sample with
  every default is
  https://github.com/TheWishin/T5DROnline/blob/main/docs/controls.ini
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

**In progress. You cannot play online yet.**

What is planned (the same model as Tekken 6 Native Online):

- You open the launcher, log in (or play as a guest), find an opponent in the
  lobby and play.
- The two PCs send each other the controller inputs directly. Delay-based first,
  rollback later. A cable is better than Wi-Fi.
- A small lobby server only introduces the players, helps them through their
  routers and relays the traffic when that fails. Both players need the same
  build.
- With a direct connection each PC learns the other's IP address.

What exists today:

- The lobby server and client (matchmaking, NAT traversal, relay, ratings) are
  in the repository, with 55 tests on one PC.
- Not done: the netplay code is not merged into the game, the launcher's Online
  tab is still a placeholder, and nothing was tried across two real networks.

Do not use the game's own **Online** menu entry. Sony's servers are gone. After
the terms screen it crashes (known).

Friends who want to try the lobby later can run their own server. See
https://github.com/TheWishin/T5DROnline/blob/main/docs/ONLINE.md
("Running your own server").

## Updating

1. Extract the new release into a **new** folder.
2. Copy your old `native` folder into it. This keeps the unpacked game and your
   saves.
3. Start the launcher. If the new version changes the game code, the Play tab
   says so. Click **BUILD GAME** again. Only the code is rebuilt.

## Bug reports

Please send:

- Build problems: `native\build.log` (Build tab, **Open build.log**). It is
  overwritten by each build, so copy it before you build again.
- Game problems: the newest file in `native\logs\` (Play tab, **Open newest game
  log**). The last 10 logs are kept.
- Your Windows version, graphics card and driver, and what you did just before.

Open an issue at https://github.com/TheWishin/T5DROnline/issues and attach the
files.

The logs contain no game data and no keys. They do contain folder paths, which
can include your Windows user name. Look before you post them in public.

More help: https://github.com/TheWishin/T5DROnline/blob/main/docs/TROUBLESHOOTING.md

## FAQ

**Do I need a PS3 or RPCS3?** No. You need the `.pkg` and `.rap` of your own
purchase. RPCS3 is not used or installed.

**Can I use a disc copy, the EU/JP version or another version?** No. Only
NPUB30009 version 01.00. The builder refuses everything else.

**Where can I get the game?** From your own PlayStation Network account. We do
not provide the package or the license and cannot help to get them.

**Does it run on Linux or macOS?** No. Only Windows runs a recompiled title
today.

**Why does the build need the internet?** Once, to fetch about 50 KB of public
key data from github.com (see Credits).

**Why is Windows warning me about the launcher?** `T5DR Online.exe` is a tiny
unsigned starter. Code signing is not set up yet.

**Where are my saves?** In `native\gamedata`. The Play tab has an **Open saves
folder** button. Back it up before you experiment.

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

## Legal

No Sony or Namco code, keys or assets are in this repository or in a release.
You must own the game. The game's program, its data, the translated code, the
keys and your `.pkg` / `.rap` stay on your own PC. Git ignores them, and the
project's CI runs a guard that fails on anything game-derived.

This is a fan project. It is not affiliated with or endorsed by Bandai Namco
Entertainment or Sony Interactive Entertainment. Tekken is a trademark of Bandai
Namco. Rules about decrypting and converting games you own differ by country.
You are responsible for following yours. This is not legal advice.

This repository does not have a license file for its own code yet; a license is
still to be chosen. ps3recomp is MIT-licensed (see above).
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

- `CLAUDE.md` — developer notes with the real state of the port, the pipeline
  and the findings.
- `docs/RELEASE.md` — the launcher, the zip and how it is packaged
  (`tools/package_release.py`).
- `docs/ONLINE.md` — the lobby: protocol, NAT traversal, self-hosting.
- `docs/CI.md` — continuous integration and the game-data guard
  (`python tools/check_no_game_data.py` before you commit).
- `docs/controls.ini` — every control setting.
- `docs/TROUBLESHOOTING.md` — fixes for players.
- `CHANGELOG.md` — what landed, by day.

**Never commit anything game-derived.** The repository is public.
