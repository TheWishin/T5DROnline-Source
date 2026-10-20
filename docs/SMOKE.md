# Smoke suite

`tools/smoke/` boots the real game, drives it through its modes with both
pads scripted, and checks that nothing broke: boot, the menus, fights in
every mode, sound, rendering and stability. It needs the game (it runs on the
owner's PC, not in CI); its game-independent parts are unit-tested in CI
(`tests/test_smoke.py`).

Run it after every merge:

    python tools/smoke/run.py                      # quick suite, ~6 min
    python tools/smoke/run.py --suite full         # ~25 min
    python tools/smoke/run.py --only vs_two_pads,practice
    python tools/smoke/run.py --list

Times are for a quiet PC (boot to the title ~24 s). Next to other game
instances and parallel builds everything runs slower -- on 2026-10-17 with
up to 12 other `t5dr.exe` and 35 compiler processes the quick suite took
7.3 min and fps/audio came out as WARN (see "Under load" below).

Options: `--exe PATH` (default `build/cmake/t5dr.exe`; copy the exe first if
you want to relink while the suite runs), `--out DIR` (default
`build/smoke/<time>-<suite>/`), `--set KEY=VALUE` to change a threshold,
`--strict` to fail fps/audio even under load, `--root DIR` for the tree that
holds `game/vfs` (found automatically, also from a worktree under `build/`).

Exit code: **0** nothing unexpected failed (known failures and warnings
allowed), **1** a regression, **2** a test could not run (missing exe, a
scenario bug). `report.md` in the output directory lists what needs
attention first, then every check with links to its evidence;
`report.json` has the same plus all numbers.

## What a test does

Each test starts its own `t5dr.exe` with `tools/run_game.py`'s environment
(`game_command()`) plus:

| variable | why |
|---|---|
| `PS3_WINDOW_BACKGROUND=1` | window opens minimized, focus is never taken |
| `PS3_PAD_FILE`, `PS3_PAD_FILE2` | both pads scripted (physical pads are ignored) |
| `AUDIO_RATE=1` | `[audio-rate]` lines: share of silent mixed blocks per 5 s |
| `LD_FRAME_DUMP`, `LD_FRAME_DUMP_EVERY=60` | the runtime reads back the presented frame about once a second -- the screenshots; nothing on the desktop changes |
| `RSX_SHADER_CACHE_DIR` | one shader cache for all tests (`build/smoke/shader_cache`) |

The working directory is `<out>/<test>/cwd/` with an **empty `gamedata`**
(saves and `scratch` never collide; `save_reload` keeps it for its second
boot). The suite stops only the processes it started: the game through its
own handle, anything the game spawned by parent PID (and only if created
after it), and a kill-on-close job object ends the game if the suite itself
dies. Other `t5dr.exe` and compilers are only counted.

Per test directory: `game.log`, `events.tsv` (timeline: phases, shots, fps,
audio, NIDs), `run.json` (all numbers), `frames/` (every dumped frame as a
small JPEG), `<shot>.png` (full-size frames the scenario asked for).

## Tests

| test | suite | what |
|---|---|---|
| `boot_menu` | quick | boot, START skips the intro movie, title menu, cursor down and back up |
| `arcade_fight` | quick | ARCADE, character select, GAME START, 15 s of round 1 |
| `vs_two_pads` | quick | VS: P1 and P2 pick (P2 one to the right), 10 s on the select screen, stage select, 15 s fight with both pads |
| `practice` | quick | PRACTICE: both fighters and stage confirmed, 12 s |
| `title_twice` | quick | title, attract demo, START, title, attract, START, title (the scene loads that ran out of memory before patch 0012, QA issue 1) |
| `ghost` | full | GHOST BATTLE, 15 s fight |
| `survival_loop` | full | SURVIVAL, 80 s of fights back to back (CIRCLE = kick, RETRY on results) |
| `options` | full | OPTIONS: game page, sound page (BGM volume +1), controller page, EXIT, back at the title |
| `gallery_offline` | full | GALLERY with no network: "retry?" NO, "return to title?" YES, back at the title |
| `save_reload` | full | fresh profile, the OPTIONS round trip (leaving with a changed setting saves), quit, second boot on the same gamedata loads the save; OPTIONS > DELETE SAVE DATA then deletes one of the two saves through the system's save data list (patch 0033) |
| `idle_attract` | full | 10 min with no input: title and attract demo cycle by themselves |

The title is reached the same way in every test (`Game.wait_title`): after the
intro movie's decoder opens, the suite waits for its first picture (or patch
0053's line that the movie goes on without pictures; up to 12 s), then taps
START until the movie has closed (up to 30 s) and the title movie opens. The
`reach.title` detail says what happened: the time to the first picture and the
number of presses, or "the decoder gave no picture" (the 1.1.2 intro hang,
fixed by patch 0053) or "not skipped after N presses".

`no-hang` looks at the gaps between `[fps]` lines up to the moment the suite
starts stopping the game; on a busy PC the kill itself took 10-11 s and used to
read as a hang right after the last check.

Fights are reached by tapping CROSS (both pads in VS) and START every second
until a dumped frame shows the fight HUD: CROSS confirms the fighter, GAME
START and the stage; START skips the VS splash and the intros (CROSS does
not skip arcade intros); tapping stops at the first HUD frame, before START
could pause the fight. Scenario steps wait for what the screen shows (the
attract demo, the title, the HUD), not for fixed times, so a slow machine
makes a test longer, not wrong.

## Checks

Per run (the check ids in the report):

| check | fails when |
|---|---|
| `no-crash` | a `[CRASH]` line, or the game exited by itself |
| `no-hang` | no `[fps]` line for 12 s (`hang_gap_s`), or none in the first 60 s |
| `reach.<milestone>` | the scenario did not get somewhere (`title`, `fight`, `attract1`, `back-to-title`, `saved`, `loaded`, `deleted`) |
| `fps.<phase>` | title/menu phases: median of the phase's full 5-s windows below 58 (`fps_min.title`, `fps_min.menu`); fights are reported (`fps_min.fight` = 0) |
| `audio.<phase>` | menu/fight/attract phases: median silent blocks above 10 % (`audio_silent.*`); the title menu is silent by design and not checked |
| `picture.<phase>` | more than half the phase's frames are black, white or one flat colour |
| `frozen.<phase>` | title/menu/fight/attract: 6+ frames and no change between any two (`frozen_eps`) |
| `fighters` | fight phases: no frame with the fight HUD, or the spike score (below) too high |
| `shot.<name>` | a frame the scenario asked for is missing, not content, or (fight shots) shows no HUD |
| `nids` | an `[hle] unresolved NID` that is not in `known_issues.json` |
| `guest-faults` | the runtime caught a NULL call/read/write or an unregistered OPD (none on a healthy run) |
| `memory` | private bytes grow more than 400 MB after the title (`mem_growth_mb`); runs over 5 min also fail above 15 MB/min in the second half |

`--set KEY=VALUE` overrides any threshold in `checks.DEFAULTS`.

**Under load** (another `t5dr.exe`, or 4+ compiler processes, seen during
the test) fps and audio failures are reported as **WARN** with the reason --
measured next to a parallel build they mean nothing. `--strict` fails them
anyway. Everything else fails regardless.

### Fighters: HUD and spikes

`frames.py` looks at every dumped frame (full size):

- **HUD**: the two health bars are 2D UI at fixed pixels -- rows 62 and 70
  teal (health) or red (damage), row 74 the dark border. Score = share of
  sampled bar columns that match; 0.85+ is a fight. Validated on 684 QA
  screenshots: all 195 fight frames scored 0.89+, every title, menu,
  character select, VS splash, loading, results and attract cut-scene frame
  below 0.5.
- **Spikes** (broken SPU skinning, before patch 0002, drew the fighters as
  huge smooth triangles across the screen): the largest connected area of
  smooth, not-dark 16x16 blocks in the playfield (rows 200-680), as a share of
  it. The two real broken-skinning screenshots score 0.11 and 0.30; 200+ good
  fight frames over 12 stages score 0.06 at most (a dusk stage with a calm
  sea), median 0.004 -- except the marble practice stage with its smooth
  bright floor (0.047-0.082, median 0.055). A test fails when the median
  over its HUD frames reaches 0.09 (`spike_limit`), so one odd camera angle
  does not. The margin to 0.11 is thin: if it ever misfires, per-stage
  reference statistics (kept under build/, not in this public repo) are the
  next step.
- Not covered: fighters that are simply not drawn. There is no sample of it
  (with job chains disabled the game never reaches the title -- the boot
  checks catch that).

## Known failures

`tools/smoke/known_issues.json` holds

- `nids`: unresolved NIDs that are not regressions (name and why);
- `failures`: `{issue, test, check, note[, expect]}` -- `test` and `check`
  are fnmatch patterns over test names and check ids.

A failing check that matches is reported **KNOWN (issue)** and does not
fail the suite; an optional `"detail"` regex narrows the match (e.g. a hang
only counts as the known issue in the phase where that issue hits). When
none of an issue's entries fail in a test, the report adds one check
`known.<issue>` = **XPASS**: the issue no longer reproduces -- confirm, then
delete its entries (`"expect": "maybe"` suppresses that for checks that pass
on some builds anyway). A WARN (fps/audio under load) never counts as a
known failure. Issue ids are `QA-n` for build/qa/REPORT.md's open issues;
use the same scheme for new ones (the id, one line of what and why, where it
is tracked).

History: **QA-1** (sys_memory never reused freed ranges; after the second
return to the title the next scene load went white, hung or called NULL)
failed `title_twice` on the 23:13 main build; **QA-4** (the first save into
a new folder failed, the next boot said "Unable to load Play Data") failed
`save_reload`. Both pass with patch 0012 (`save_reload` reported
`known.QA-4` XPASS), so their entries are gone and the list is empty. The
two NIDs listed (cellHttp timeouts) no longer appear on main either; they
stay listed because they are harmless.

## Adding a test

1. Find the button sequence: `build/qa/ctl.py` (live control) or a
   throwaway scenario with `--only`. Menu indexes, button names and the
   QA-recorded flows are at the top of `tools/smoke/scenarios.py`.
2. Add a function to `scenarios.py`:

   ```python
   @test("my_mode", ("full",), "one line: what it covers", budget=120)
   def my_mode(ctx):
       g = ctx.boot()                    # ctx.boot(label="boot2", keep_gamedata=True) for a second boot
       if not to_title(g):
           return
       g.phase("my-menu", "menu")        # phase kind picks the checks (see checks.py)
       pick_mode(g, OPTIONS)
       g.shot("my-menu")                 # expect="content" | "fight" | "any"
       if start_fight(g):                # taps CROSS until the fight HUD is up
           fight(g, 20)
       g.expect("something", ok, "detail")   # becomes reach.something
   ```

   `g.press("DOWN", gap=450)`, `g.press2(...)` for player 2, `g.hold(...)`/
   `g.release()`, `g.wait(s)` (raises `Abort` when the game exits or stops
   presenting -- the runner records it, no try/except needed).
3. Run it with `--only my_mode` a few times; look at `report.md` and the
   frames. Keep phases you want fps/audio numbers for at least 6 s long
   (one full 5-s window).
4. Put it in `quick` only if it adds little time; the quick suite must stay
   under 6 minutes (tests/test_smoke.py checks the budgets).
5. If it fails on main for a known reason, add a `known_issues.json` entry
   with the issue id in the same commit.

## Audio device

The WASAPI backend (ps3recomp patch 0026) owns the sound device on a thread of
its own, so the game's audio loop never waits for it. With no device at start
the game runs silent and the thread looks again every 2 s. A device that goes
away (`AUDCLNT_E_DEVICE_INVALIDATED` on any call: unplugged, Bluetooth, HDMI off)
or a changed default (`IMMNotificationClient`, plus a 1 s check) is replaced
within about a second. Audio queued in between is dropped; the mixer keeps its
5.33 ms clock and sends the same events to the game either way, so nothing the
simulation sees changes. Each state change is one log line, `t` = seconds since
the audio started:

```
[cellAudio] audio device waiting: no audio device (E_NOTFOUND) (0x80070490); the game runs silent, retrying every 2 s [t=0.00s]
[cellAudio] audio device opened "Speakers (Realtek)" at 48000 Hz (device mix 48000 Hz, 2400 frames, event driven) [t=20.02s]
[cellAudio] audio device lost: AUDCLNT_E_DEVICE_INVALIDATED (0x88890004) in GetCurrentPadding after 12.0 s of sound [t=32.00s]
[cellAudio] default audio device changed, switching [t=41.00s]
```

Test hooks, so no Windows sound setting has to be touched:

| variable | what it does |
|---|---|
| `PS3_AUDIO_FAKE_NODEVICE=20` | no device for the first 20 s (the lookup fails with 0x80070490) |
| `PS3_AUDIO_FAKE_LOSS=40,50,60` | at these times the next stream call fails with `AUDCLNT_E_DEVICE_INVALIDATED` |
| `PS3_AUDIO_FAKE_CHANGE=40,50` | at these times the default-device notification fires and the default counts as a new device (make before break) |
| `PS3_AUDIO_FAKE_STALL=40` | at this time the open device stops consuming (its queue reads full); the mixer gives the stream up after 200 ms and the device is reopened. The game's audio events pause for those 200 ms (before the patch they would have stopped for good) |
| `AUDIO_WAV=audio_mix.f32` | every mixed block (f32le, stereo, 48 kHz) |
| `PS3_AUDIO_DEVICE_WAV=audio_dev.f32` | the same blocks where a device took them, silence where there was none |

Times are seconds since the audio started (about 1 s after the process). The
`[audio-rate]` line ends with `no device N`: blocks of that 5-s window mixed
with no device open. The smoke runner passes its environment on, and relative
capture names land in each test's own `cwd/` (cmd syntax; PowerShell:
`$env:NAME = 'value'`):

```
set PS3_AUDIO_FAKE_NODEVICE=20
set AUDIO_WAV=audio_mix.f32
set PS3_AUDIO_DEVICE_WAV=audio_dev.f32
python tools/smoke/run.py --only arcade_fight,practice --out build/audio
python tools/audio_device_check.py build/audio/arcade_fight --first-sound-after 20
```

`tools/audio_device_check.py` reads the log lines and both captures and checks
that nothing reaches the device while none is open, that every block it got is
the mix block of the same index (the music stays in step with the game), that
nearly every loud block reaches an open device, and that a lost device is open
again within `--max-gap` seconds (1 by default). For a netplay pair
(`tools/netplay_test.py --pair --env1 PS3_AUDIO_FAKE_LOSS=...`) run it on `run1/`.

`libs/audio/tests/test_audio_device.c` (in the patched ps3recomp, 16 s, build
line in its header) runs the real mixer and device threads against the hooks
without a game: the audio events keep 187.5 per second, longest gap under
100 ms, with no device, with one, and across two losses and a default change;
a stalled device is given up after 200 ms and replaced.

## Unit tests

`python -m unittest discover -s tests` runs `tests/test_smoke.py` with the
rest: log parsing, every check against synthetic runs, known-issue marking,
the report and exit codes, process selection by parent PID, the frame
heuristics on synthetic images (needs Pillow; skipped without it), and the
runner's error path. CI installs Pillow for it.

## End-to-end online scenarios

`tools/e2e/run.py` plays the online flows the way two players would, on this
PC: a **local** lobby server (`python -m t5lobby.server` on 127.0.0.1, its own
database; any other address is refused), two players each driven through the
launcher's own Online tab (`launcher/online.py` -> `t5lobby.tk_tab.OnlineTab`
with its `LobbyClient` and `MatchDriver`, buttons pressed with `invoke()`), the
launcher's game code (`core.Settings`, `core.GameRun`, `core.game_state`) and
real games in persistent mode (a copy of `t5dr.exe` per run, hard-linked into
each player's `native\`). Scenarios where the game does not matter use
`lobby/tools/stub_game.py`. Between two real games a UDP proxy (the
*shaper*) adds round trip, jitter and loss or cuts the link; the lobby's own
NAT step still runs and the games are then pointed at the proxy.

    python tools/e2e/run.py --list
    python tools/e2e/run.py --suite quick          # lobby + stub scenarios, ~4 min, no game needed
    python tools/e2e/run.py --suite game           # real matches (one round each), ~75 min
    python tools/e2e/run.py                        # everything
    python tools/e2e/run.py --only ranked_set,room_flow --repeat 3

Output: `build/e2e/runs/<time>/report.md` (a table with runs and PASS / FAIL /
SKIP per scenario, failures first, then every check and the evidence: match
ids, paths, input delays, rollbacks, fps, result hashes), `report.json`, and
per scenario its server log, both players' `native\logs` and desync dumps.
These hold player names and local addresses: never commit them.

Groups: accounts (register, saved login, wrong password, guest, the same
account on two PCs, a server restart), quick match (blind found, accept,
decline, timeout), ranked (sets with rating and rank after every game, the
character lock, the pair cooldown and cap, a quit mid-set, ranked rooms),
rooms (Ready again = a new session, then a rematch: the 1.0.0 hang), rematch
(decline, window timeout, five in a row), netcode (rollback and lockstep, input
delay Auto/0/1/2, RTT 20-250 ms, 2/10 % loss, jitter, the relay path, a
mixed pair, and 1.1.1's relay bridge: a match that starts on the relay because
the punch was blocked moves onto the direct path at the match's start + 35 s
while the fight runs, `net_relay_upgrade` with real games and
`relay_upgrade_stub` with stub games plus a 1.1.0-style client that stays on
the relay; regional relays: two relay-only nodes (`run.py relay`) next to the
lobby server and a UDP delay proxy per player and relay, the lobby must pick
the node with the smallest round-trip sum and fall back to the next one when
it stops -- `relay_regional` with real games, `relay_regional_stub`, and
`relay_e2e_tool` / `relay_e2e_tool_game` run `lobby/tools/relay_e2e.py` as
it is; `relay_old_client` plays the real 1.1.0 Online tab, client and match
driver from the git tag `v1.1.0` against 1.1.1 on the lobby server's own
relay; `net_relay_smooth` (suite net, 1.1.4): relayed against direct at the same emulated network -- the
relayed path as two shaped legs through a relay node, `E2E_SMOOTH_CASES` / `E2E_SMOOTH_PATHS` (`relay-old` =
1.1.3's bridge) / `E2E_SMOOTH_CPUS` (a busy PC), rollbacks/s, depth, stalls, time-sync sleeps and fps per match in
`smooth.json` (docs/NETPLAY.md "Relayed matches"); `net_vsync_off`: VSync off in one game of the match, in sync), failures (Alt+F4 = forfeit, a killed game = crash, a cut network
= disconnect, a game restarted between matches, another build refused),
launcher extras (Report a problem without names/IPs/tokens, the update check
against mocked GitHub answers, settings that survive a restart), the in-game
character select (picks, costumes, mirrors, Random, the pick timeout, ranked
lock) and best-of-3 ranked sets. Every scenario also fails when `launcher.log` gets
an "error in the launcher" line (a Tk callback that raised).

Like the smoke suite: windows minimized, games muted (`PS3_AUDIO_MUTE=1`) and
at below-normal priority, no window or dialog ever shown (the Tk root and
every Toplevel are withdrawn, message boxes and file dialogs answered by the
runner), the clipboard never touched, only processes started by the runner
stopped (a kill-on-close job ends them if it dies). fps checks only warn while
other games or builds run. `tests/test_e2e.py` covers the shaper, the log
parser, the scenario list and the report without a game.
