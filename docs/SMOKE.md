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
| `boot_menu` | quick | boot, START skips the intro movie, title menu, 12 s idle, cursor down/up |
| `arcade_fight` | quick | ARCADE, character select, GAME START, 20 s of round 1 |
| `vs_two_pads` | quick | VS: P1 and P2 pick (P2 one to the right), 10 s on the select screen, stage select, 20 s fight with both pads |
| `practice` | quick | PRACTICE: both fighters and stage confirmed, 15 s |
| `title_twice` | quick | title, attract demo, START, title, attract, START, title (third scene load) |
| `ghost` | full | GHOST BATTLE, 25 s fight |
| `survival_loop` | full | SURVIVAL, 2 min of fights back to back (CIRCLE = kick, RETRY on results) |
| `options` | full | OPTIONS: game, sound, controller pages and back |
| `gallery_offline` | full | GALLERY with no network: "retry?" NO, "return to title?" YES |
| `save_reload` | full | fresh profile, VS round so the game saves, quit, second boot on the same gamedata loads it |
| `idle_attract` | full | 10 min with no input: title and attract demo cycle by themselves |

Fights are reached by tapping CROSS (both pads in VS) until two dumped frames
in a row show the fight HUD; that gets through character select, stage
select, the VS splash and intros whatever their timing.

## Checks

Per run (the check ids in the report):

| check | fails when |
|---|---|
| `no-crash` | a `[CRASH]` line, or the game exited by itself |
| `no-hang` | no `[fps]` line for 12 s (`hang_gap_s`), or none in the first 60 s |
| `reach.<milestone>` | the scenario did not get somewhere (`title`, `fight`, `saved`, `loaded`) |
| `fps.<phase>` | title/menu phases: median of the phase's full 5-s windows below 58 (`fps_min.title`, `fps_min.menu`); fights are reported (`fps_min.fight` = 0) |
| `audio.<phase>` | menu/fight/attract phases: median silent blocks above 10 % (`audio_silent.*`); the title menu is silent by design and not checked |
| `picture.<phase>` | more than half the phase's frames are black, white or one flat colour |
| `frozen.<phase>` | title/menu/fight/attract: 6+ frames and no change between any two (`frozen_eps`) |
| `fighters` | fight phases: no frame with the fight HUD, or the spike score (below) too high |
| `shot.<name>` | a frame the scenario asked for is missing, not content, or (fight shots) shows no HUD |
| `nids` | an `[hle] unresolved NID` that is not in `known_issues.json` |
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
  it. The two real broken-skinning screenshots score 0.11 and 0.30; 169 good
  fight frames over 12 stages score 0.06 at most (a dusk stage with a calm
  sea), median 0.004. A test fails when the median over its HUD frames
  reaches 0.08 (`spike_limit`), so one odd camera angle does not.
- Not covered: fighters that are simply not drawn. There is no sample of it
  (with job chains disabled the game never reaches the title -- the boot
  checks catch that).

## Known failures

`tools/smoke/known_issues.json` holds

- `nids`: unresolved NIDs that are not regressions (name and why);
- `failures`: `{issue, test, check, note[, expect]}` -- `test` and `check`
  are fnmatch patterns over test names and check ids.

A failing check that matches is reported **KNOWN (issue)** and does not
fail the suite. A matching check that *passes* is reported **XPASS**: the
issue may be fixed -- confirm, then delete the entry (or set
`"expect": "maybe"` for checks that pass on some builds anyway). Issue ids
are `QA-n` for build/qa/REPORT.md's open issues; use the same scheme for new
ones (the id, one line of what and why, where it is tracked).

Current entries: **QA-1** (sys_memory never reuses freed ranges; the third
scene load through the title goes white -- `title_twice`, `idle_attract`)
and **QA-4** (the first save into a new folder fails -- `save_reload`).
Both are expected to fail on main until their fixes land.

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

## Unit tests

`python -m unittest discover -s tests` runs `tests/test_smoke.py` with the
rest: log parsing, every check against synthetic runs, known-issue marking,
the report and exit codes, process selection by parent PID, the frame
heuristics on synthetic images (needs Pillow; skipped without it), and the
runner's error path. CI installs Pillow for it.
