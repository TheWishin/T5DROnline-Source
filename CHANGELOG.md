# Changelog

All notable changes, newest first. The project is a test release: no release zip
is published yet. A first zip, `T5DR-Online-0.1.0-rc1`, was built and checked on
the development PC. Short commit hashes are in parentheses. The state of each
part is in the README's status table.

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
