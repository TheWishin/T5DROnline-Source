# Changelog

All notable changes, newest first. The project is a test release. Short commit hashes are in parentheses. The state of each
part is in the README's status table.

## v0.1.1-preview (2026-10-17)

The first release on this page. Same as 0.1.0-preview (built and tested the
same day), plus:

- **Music is read straight from the game's archive.** The music stream no longer
  depends on how the game feeds it. This was needed for rollback netcode and also
  makes the music more robust offline.
- **License**: the project's own code is MIT-licensed; the text is in the zip
  (`LICENSES\T5DR-Online-MIT.txt`).

Test build. Tekken 5: Dark Resurrection runs natively on Windows,
built on your PC from your own copy (`.pkg` + `.rap`). Online play between
friends works through the launcher, the same way as Tekken 6 Native Online.
Expect bugs, and please report them.

### Play
- All offline modes: Arcade, Ghost, Versus (two players on one PC), Survival,
  Practice. Music, sound effects and movies.
- 60 fps in menus and fights, also with other programs busy on the PC.
- Fighters and stages render correctly: faces and floor shadows fixed. Resizable
  window, borderless fullscreen (Alt+Enter or F11), higher render resolutions.
- Saving works. The in-game clock shows the real date. The old white-screen
  memory bug is fixed.

### Controls
- Keyboard, Xbox pads (XInput), PlayStation pads, arcade sticks and hitboxes
  (DirectInput), two local players, `controls.ini` for remapping.
- Short taps are never lost: the pads are read every millisecond, and a press
  between two game reads still reaches the game, also online.

### Online
- Launcher Online tab: log in or play as a guest on the public server (preselected).
- Quick and ranked matches, lobby rooms. A found match shows the ping; accept it
  within 15 seconds. The game starts directly in the fight, first to 3 rounds,
  and stays open for Rematch / Next game.
- Ranked: Glicko-2 rating shown with Tekken 5's rank names. Leaving or
  disconnecting counts as a loss, a desync voids the match. Block players,
  optional strict matchmaking, character locked for a ranked set, a post-game lag
  check (too laggy -> leave without penalty).
- Direct connection between the two PCs, with a relay through the lobby server
  when the routers don't allow it. Tested with packet loss, jitter and outages.
- Delay-based netcode (2-3 frames of input delay). Rollback is being finished
  and comes in a later update.
- Run your own server: Linux VPS, Docker, Mac, or **Host for friends** in the
  launcher (`docs/HOSTING.md`).

### Known limits
- Tested on one development PC. Not yet tried on a clean PC or between two real
  PCs over the internet. Weaker PCs are not measured yet.
- Real arcade sticks are not yet tried by a person.
- Some background figures may look flat white.
- The game's own **Online** menu entry crashes after the terms screen. Use the
  launcher's Online tab.
- The first time, Windows Firewall asks about the network: allow it for private
  networks.

## v0.1.0-preview (2026-10-17)

First public test build. Tekken 5: Dark Resurrection runs natively on Windows,
built on your PC from your own copy (`.pkg` + `.rap`). Online play between
friends works through the launcher, the same way as Tekken 6 Native Online.
Expect bugs, and please report them.

### Play
- All offline modes: Arcade, Ghost, Versus (two players on one PC), Survival,
  Practice. Music, sound effects and movies.
- 60 fps in menus and fights, also with other programs busy on the PC.
- Fighters and stages render correctly: faces and floor shadows fixed. Resizable
  window, borderless fullscreen (Alt+Enter or F11), higher render resolutions.
- Saving works. The in-game clock shows the real date. The old white-screen
  memory bug is fixed.

### Controls
- Keyboard, Xbox pads (XInput), PlayStation pads, arcade sticks and hitboxes
  (DirectInput), two local players, `controls.ini` for remapping.
- Short taps are never lost: the pads are read every millisecond, and a press
  between two game reads still reaches the game, also online.

### Online
- Launcher Online tab: log in or play as a guest on the public server (preselected).
- Quick and ranked matches, lobby rooms. A found match shows the ping; accept it
  within 15 seconds. The game starts directly in the fight, first to 3 rounds,
  and stays open for Rematch / Next game.
- Ranked: Glicko-2 rating shown with Tekken 5's rank names. Leaving or
  disconnecting counts as a loss, a desync voids the match. Block players,
  optional strict matchmaking, character locked for a ranked set, a post-game lag
  check (too laggy -> leave without penalty).
- Direct connection between the two PCs, with a relay through the lobby server
  when the routers don't allow it. Tested with packet loss, jitter and outages.
- Delay-based netcode (2-3 frames of input delay). Rollback is being finished
  and comes in a later update.
- Run your own server: Linux VPS, Docker, Mac, or **Host for friends** in the
  launcher (`docs/HOSTING.md`).

### Known limits
- Tested on one development PC. Not yet tried on a clean PC or between two real
  PCs over the internet. Weaker PCs are not measured yet.
- Real arcade sticks are not yet tried by a person.
- Some background figures may look flat white.
- The game's own **Online** menu entry crashes after the terms screen. Use the
  launcher's Online tab.
- The first time, Windows Firewall asks about the network: allow it for private
  networks.

## 2026-10-16 (day one)

Everything below landed on `main` in one day, except the player docs.

### Docs, controls and CI

- **Player docs** (branch `player-docs`, not on `main` yet). The README is
  rewritten for players. New: a German README (`docs/README.de.md`),
  `docs/TROUBLESHOOTING.md` and this changelog.
- **Controls** (`f158ee2`, patch 0009). DirectInput 8 next to XInput, so
  PlayStation pads, DualShock 4, DualSense, arcade sticks and hitboxes work, also
  while the window is unfocused. Two local players, hot-plug, and a `controls.ini`
  for remapping with presets and macros (`docs/controls.ini` documents every
  default). Not yet tried on real hardware by a person.
- **CI on GitHub** (`c8ee350`, `5c2bb02`, `b38da79`). Every push and pull request
  runs a guard that fails on anything game-derived, Python tests, the lobby tests
  and a build of the patched runtime. No game data is used, so CI cannot boot the
  game. See `docs/CI.md`.

### Launcher, release and lobby

- **Launcher** (`43fb9e3`). A Windows program with four tabs: Build, Play,
  Settings, Online. Pick your `.pkg` and `.rap`, click BUILD GAME, click PLAY. It
  shows progress, one plain red sentence when something fails, and keeps the last
  10 game logs. The Online tab was a placeholder at first.
- **Build for players** (`88325eb`). Everything goes under one folder (`native`).
  The version and license are checked **before** the 600 MB unpack, so a wrong
  copy is refused within seconds (1.6 s measured).
- **No Visual Studio needed** (`88325eb`, `1b35ec4`, patch 0020). The runtime is
  shipped precompiled. The player's PC compiles only the game code into
  `t5dr_game.dll` with a bundled clang-cl and lld-link. Measured from the packaged
  zip with a bare Windows PATH: BUILD GAME 90 s, game at 60 fps, 90 MB zip.
- **Release zip** (`e91f37c`). `tools/package_release.py` builds the zip and scans
  it, and again after zipping, for game files, lifted code and keys. It refuses to
  package on any hit. `docs/RELEASE.md` has the numbers.
- **Lobby** (`ff5e5ea`, `d6b9c18`, `213b52f`). A server and client in plain Python:
  guest and account logins, rooms, quick and ranked matches (Glicko-2), NAT hole
  punching with a relay fallback, build check, rate limits. Hardened later:
  only private LAN addresses as punch candidates, a guard against deeply nested
  JSON, a rate-limited relay. 55 tests. The Online tab for it (`02f78ad`) exists
  in the lobby code but is not wired into the launcher yet. `docs/ONLINE.md`
  documents it, including running your own server. Tested on one PC only.
- `docs/RELEASE.md` (`1938fa5`) has the numbers measured from the 0.1.0-rc1 zip.

### Game: it plays

- **Movies** (`ea5020a`, patch 0006). Intro and title movies play with sound. H.264
  is decoded with Windows Media Foundation, and the ATRAC3plus audio is decoded
  too. About 30 pictures per second.
- **Music** (`277d475`, patch 0003). The ATRAC streaming API works, so music plays.
  The choppy sound is fixed: silent mixed blocks fell from about 55 % to about
  0.1-1.6 % (measured under load).
- **Fighters render** (`eb7a5b2`, patches 0002 and 0007). The SPURS skinning jobs
  run, so the fighters are visible. Menus 60 fps, fights about 40-44 fps.
- **60 fps timing** (`c6ca38e`). Vblank now runs at 59.94 Hz on the performance
  counter. Before, the game ran 4 % fast.
- **Quiet window for tests** (`32b2339`, patch 0021). `PS3_WINDOW_BACKGROUND=1`
  opens the game window minimized, also with the live-draw renderer.

### Game: first boot

- **Sound core and graphics** (`9b0d7bc`, `fb45576`). The SPU sound core is
  translated and runs. The D3D12 live-draw renderer is on by default. Audio pacing
  is even (5.33 ms blocks) and a non-48 kHz sound device no longer silences the
  game. The log is quiet (`PS3_VERBOSE=0`), which lifted the game from about 34 to
  about 63 fps. The game reaches menus and fights.
- **Build pipeline and first boot** (`a18f995`). `tools/build_game.py` goes from the
  `.pkg` and `.rap` to a running `t5dr.exe`: unpack, decrypt, check the program's
  SHA-1, translate 23,059 functions, compile with clang-cl. The game boots, opens
  its D3D12 window and loads its data.

### Start of the port

- **Decryptor** (`a811497`). Our own `tools/unself.py` decrypts the game's
  `EBOOT.BIN` with your `.rap`. The keys are read from a local, git-ignored file.
  First findings: 16,856 functions found, 252 imports in 20 libraries, one SPU
  sound core, PSN calls that we will bypass.
- **Project start** (`9a5ebe0`). Ground rules, the plan, and a `.gitignore` that
  blocks everything game-derived. The repository is public: nothing from the game
  goes in.

## Known problems at the end of the day

See the status table in the README and `docs/TROUBLESHOOTING.md`. The main ones:
fights run at 30-45 fps, every fighter's face is dark, a memory bug can turn the
screen white after repeated visits to the title, saving is unreliable, and
online play is not playable yet.
