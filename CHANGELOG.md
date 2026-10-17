# Changelog

All notable changes, newest first. The project is a test release. Short commit hashes are in parentheses. The state of each
part is in the README's status table.

## v0.1.7-preview (2026-10-17)

More robust online play. Both players need 0.1.7. After the update press
**BUILD GAME** once.

- **After an aborted match** (opponent gone, connection lost) the open game is
  clean again and the next match starts normally. Tested: 10 of 10 cycles of
  "match -> abort -> next match" in one game, with rollback and with delay netcode.
- A button pressed in the very first frames of a fight no longer makes the game
  hang while loading (rollback).
- Some pairings (e.g. Asuka vs Law) no longer go out of sync against a freshly
  started game.
- If the game still gets stuck, it closes itself after 60 seconds and the
  launcher starts a new one.

Known: with a very bad connection (many corrections right at the final KO) the
game can still get stuck at the end of a match; it then recovers as above. A
fix is in progress.

## v0.1.6-preview (2026-10-17)

**Important online fix:** choosing Devil Jin online gave you Feng and the other
way round, and Kuma came out as Panda. Every character is now the one you pick
(checked for all 35 on the select screen). Both players need 0.1.6. After the
update press **BUILD GAME** once (about 2 minutes).

- **Delete Save Data** no longer deletes every save at once: a list shows your
  saves, you pick one and confirm.
- 18 system functions the game asks for now answer properly (e.g. Options ->
  Online Manual says "not available" instead of failing).
- The sound core's 13 effect functions (reverb, pitch, mix, ...) run as compiled
  code instead of an interpreter: less CPU work in fights.
- Checked: all 35 characters and 34 stages render; the background figures and
  the game's own Online menu (clean "network error", no crash) are fine.

## v0.1.5-preview (2026-10-17)

Faster on weaker PCs, and online stays in sync between any two PCs. Both players
need 0.1.5. After the update press **BUILD GAME** once (about 2 minutes).

### Performance
- **60 fps in fights on 4-thread PCs** (was about 32). Thread counts follow the
  CPUs the game may use; the main thread no longer spins while waiting.
- Rollback at 150 ms ping: about 50 fps on 4-8 threads (was about 30).
- **New: 3D resolution** (launcher -> Settings): Original, Lower or Lowest, for
  weak graphics cards. Players with different settings stay in sync.

### Online
- **Any two x64 PCs compute the same game**: Intel or AMD, with or without
  AVX2/FMA. The game code no longer uses math that differs between CPUs.
  Tested: 160,000 frames compared between different builds, 0 differences.
- **Fewer void ranked matches:** camera and cloth-motion values that could
  differ for a few frames at a KO (e.g. Bryan vs Steve) no longer count as a
  desync.

## v0.1.4-preview (2026-10-17)

Online feels like Tekken 6 Native Online now, and the game runs on more PCs.
Both players need 0.1.4. After the update press **BUILD GAME** once (the game
code changed; it takes about 2 minutes).

### Online
- **The game stays open for a new opponent**, not only for a rematch: 5-7
  seconds from Accept to the fight (was about 20).
- **Your lobby names and ranks show in the fight** instead of "Unknown".
- **Mashing buttons at the final KO** no longer starts a stray VS battle that
  blocked the next match.
- **Fewer void ranked matches:** camera values that differed for a moment
  between the two PCs no longer count as a desync.

### Runs on more PCs
- Folder and Windows user names with any characters (e.g. `Ł`, `東京`) work; the
  game did not start there before.
- Windows N editions work (movies need the Media Feature Pack; without it they
  stay black and the game runs on).
- TVs and monitors below 60 Hz (50 Hz, 30 Hz) no longer slow the game down;
  120/144/165 Hz monitors keep the exact game speed.
- Laptops with two graphics chips use the fast one.
- A graphics driver crash shows a message instead of a frozen window.
- The window has the right size with Windows scaling (125-200 %).
- The launcher finds OneDrive folders and warns if the game folder is inside one.

## v0.1.3-preview (2026-10-17)

**Rollback netcode is the online default, like Tekken 6 Native Online.** Both
players need 0.1.3 (the lobby pairs only equal versions).

- **Rollback:** your own inputs act after 2 frames, whatever the ping. When the
  opponent's input arrives late, the game corrects itself in the background.
  Tested at 0, 50 and 150 ms ping with 3 % packet loss and jitter: two matches
  plus a rematch in one game, in sync, no crash, no hang.
- **Sound with rollback:** a sound is never played twice and never cut; music
  runs on without gaps.
- **Fallback:** if a match stutters because a PC is too slow, one player can
  switch to the older delay netcode: launcher -> Settings -> "Advanced: extra settings",
  add the line `T5_RB_MODE=off`. The match then runs with delay netcode on both PCs.
- Players who don't offer rollback (older builds of the same version) get delay
  netcode automatically.

## v0.1.2-preview (2026-10-17)

**Use this version for online play.** 0.1.0 and 0.1.1 could not play online:
their zip lacked part of the online code, and match results were not counted.

- **Online works from the zip.** The prebuilt game program now contains netplay
  and the direct start into the fight. A new check in the release test fails if
  they are ever missing again.
- **Match results count.** The winner is read correctly, so quick and ranked
  matches are confirmed instead of void (14 of 14 test matches, both winners).
- **Windows Firewall:** `TROUBLESHOOTING.md` has a new "Online play" section:
  what to click, where the prompt hides, what the status messages mean.
- **Tried on real hardware** (2026-10-17): an Xbox pad and an arcade stick, every
  input came through, the game ran smoothly.
- Launcher: use it with a pad or stick (A / Cross accepts and searches, B / Circle
  declines and cancels), only while the launcher is in front.
- Sound comes back when a headset or speaker is plugged in later, unplugged or
  switched; the game's timing never changes.
- Host for friends no longer crashes on a German Windows (router lookup).

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
