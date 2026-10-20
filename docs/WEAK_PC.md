# Weak PCs: why some players get 40-50 fps

The owner asked: *"Can you make a Vulkan renderer? I hear some people play at
40-50 fps."* This page is the study behind the answer (branch `weakpc-fps`,
ps3recomp patch 0059, 2026-10-20). The [player checklist](#player-checklist)
at the end can be pasted to players as it is.

## The short answer

- **No Vulkan for this.** The D3D12 calls cost 0.7-1.0 ms of a 16.7 ms frame
  on this PC, the same on NVIDIA and on AMD integrated graphics. A Vulkan
  renderer would save perhaps 0.3 ms of that (0.6-0.7 ms on a slow CPU): a
  few percent, for weeks of work and a second renderer to keep correct. The
  same few percent can be had in the D3D12 path (see [D3D12 or
  Vulkan](#d3d12-or-vulkan)).
- **What limits those players is the speed of one CPU core.** The game's
  main thread (Namco's code, recompiled) needs 5-6 ms per fight frame on this
  PC's fast cores, 8-10 ms on 2-4 slower or shared cores. Add the render
  translation (2.2-3.8 ms) and a CPU with roughly half this PC's speed per
  core runs past 16.7 ms.
- **And the PS3's vblank made it worse.** A frame completes on a vblank, as
  on the PS3. A frame that took 18-20 ms waited for the *next* vblank and
  took 33.4 ms, so a PC that could do 50-55 fps showed 30-45. **Fixed in
  patch 0059**: a late frame is shown as soon as it is ready. Measured with a
  slowed game: **40 -> 49-50 fps** and **30 -> 43-44 fps**; online (rollback,
  150 ms, the slow PC on one side) **32 -> 46 fps**, in sync.
- Core count is not the limit: 2 cores / 4 threads held 60 fps here. GPU
  only at high Internal resolution on integrated graphics (4K on this PC's
  small Radeon: 28 fps; Native and 1080p: 60).
- The game logs now say which case a player has (`[slow-frames]`, below), and
  Report a problem carries it.

## How a fight frame is built

```
vblank tick -> game part (main thread)            -> flip request -> translation (D3D12)  -> next vblank tick
  release      logic, skinning jobs, RSX commands     one flush       walker on the ticker     flip completes,
               5-6 ms here, 8-16 ms on slow CPUs                      2.2-4.4 ms               next frame starts
```

The game runs one game frame per vblank, like the PS3: its speed *is* its
frame rate. The game part and the translation are in series (the game waits
for its flip; docs/RENDER_PERF.md "Is the handover wait necessary?"). A
frame makes 60 fps when game part + translation stay under 16.7 ms.

- **Translation late** (the game asked for its flip in time, the walk ran
  past the tick): already shown at once before 0059 -- the walk runs on the
  ticker thread, so the tick simply came when the walk was done (measured:
  +3 ms of translation kept frames at 17-18 ms, 55-58 fps).
- **Game part late** (the main thread itself ran past the tick): waited for
  the tick after that -- 33.4 ms. A game part around 15-17 ms gives a mix of
  16.7 and 33.4 ms frames: the steady 40-45 fps of the reports. Above 16.7
  every frame takes two vblanks: 30 fps.

## Causes, and what the logs show

"Logs" = the game log the launcher keeps (`native\logs\game-*.log`), which
Report a problem puts into the zip; `system.txt` carries the last
`[slow-frames]`, `[pacing]`, `[netplay] speed:` lines. Since patch 0059 a
`[slow-frames]` line looks like this:

    [slow-frames] last 30 s: 1501 frames, 74 slow (over 20.9 ms): CPU 74 (game 42, render translation 0,
    vblank thread late 0), GPU 0, present 0; 733 late for their vblank, shown when translated; median per
    frame: game 15.4 ms, translation 4.3, GPU wait 0.0, present 0.3; worst 39.0 ms (CPU, game); vblank
    clock 50.01 Hz; other programs 4.4 of 32 logical processors busy, the game 2.0 (of 16 it may use) |
    on AC power (no battery: a desktop PC), power plan "Balanced", processor clock limit 4501 of 4501 MHz

It comes every 30 s while frames are slow or late (every 5 minutes when all
is well). New in 0059: "late for their vblank, shown when translated", the
background load ("other programs ... busy, the game ..."), and a tick that
waited for the walk now counts as translation, not "vblank thread late".

| cause | plausible for a steady 40-50? | what the log shows | measured here | verdict / what helps |
|---|---|---|---|---|
| **Slow CPU cores** (old/low-clock CPU, laptop at low clocks, Zen 2 handheld) | **yes -- the main cause** | `[slow-frames]` "CPU N (game N ...)", median game 13-17 ms; many "late for their vblank"; `vblank clock` below 59.9 (0059: the clock follows the frames) | stand-in by test hooks: game part 15.5 ms -> 40 fps before, 49-50 after 0059; 18 ms -> 30 / 43-44 | patch 0059; power mode / charger; close programs (they take the shared core) |
| **Few cores** (4-6 logical processors) | no, at a fast core | `[sched] CPU budget: 4 logical processors` | 2c/4t, 4c/4t, 3c/6t, 6c/6t, 4c/8t, 6c/12t, 8c/16t: 59.95 fps each; game part 8.1 ms at 2c/4t vs 5.1-5.9 at 8c/16t | patch 0027/0047 size the pools; nothing to set |
| **SMT sibling busy** (another program on the other thread of the game's core) | yes, adds to a slow core | game median up, "other programs N busy" | 4c/4t with the siblings busy: game part 6.5-7.1 -> 9.8-10.3 ms, translation 2.3 -> 3.7 ms (+45-60 %) -- still 60 here | close programs; a slower core with busy siblings drops below 60 |
| **SPU / SPURS job threads competing** | no | spurs-job / spu threads in fight_bench | skinning wait 0.7 ms at 4 processors (patch 0027); job threads 0.5 of a core at 32 | fixed in 0027 |
| **Background programs** (browser, recorder, virus scan, update) | sometimes | 0059: "other programs X of Y logical processors busy" next to the slow frames | 4 busy programs on the game's 2c/4t at the same priority: 60 fps, game part 8.1 -> 9.3-9.7 ms; game *below* 3 busy programs (idle priority): 60, game part 10.1 ms | the game's own threads run above normal priority, so equal programs mostly cost the shared core and cache; close them anyway |
| **Lower process priority** (game started at low priority, "efficiency mode") | rarely | the same as above | idle-priority game under 3 busy programs: 59.96 fps at this core speed | do not start the game below normal / in efficiency mode |
| **Power plan, laptop heat, battery** | yes on laptops/handhelds | `[power]`, `[slow-frames]` "processor clock limit X of Y MHz (held back ...)", "on battery" | EcoQoS on the whole game (Windows' efficiency mode): game part +5-15 %, translation +5-25 % | charger, "Best performance", power saving Auto (0047) |
| **Display not 60 Hz** (50 Hz TV, 75/144 Hz with VSync) | no | `[pacing] display 50 Hz: slower than the game's 59.94 Hz ...` / `display 144 Hz: vsync on` | simulated 50, 75, 144 Hz: 59.94 fps each; 75 Hz shows frames unevenly (present p95 20.9 ms) but the game keeps its speed | 120 Hz or 60 Hz for the smoothest picture; VRR |
| **Overlay fps counter on a 144 Hz screen** | a reading, not a cause | -- | -- | the game's own `[fps]` line / the launcher's fps is the game's speed |
| **iGPU at high Internal resolution** | yes at 1440p/4K | `[slow-frames]` "GPU N", GPU wait ms; `[gpu] adapter: ... integrated`; since 0063 "GPU busy N %" and "GPU-bound" / "integrated graphics busy" at the end of the line. A stronger APU (780M) shows a long **game** part instead: the busy GPU slows the CPU work through the shared memory and power (RENDER_PERF.md "4K on integrated graphics") | this PC's 2-CU Radeon: Native 2.5 ms GPU, 60 fps; 1080p 6.3 ms, 60 fps; 4K 24-32 ms, **28-35 fps**; Auto (1080p) 59.7 fps | Internal resolution 1080p or Auto (at most 1080p on integrated graphics), Native/Lower on weak ones |
| **D3D12 driver overhead per draw** | no | `fifo_cpu_us` / translation median | 830 draws a frame; D3D12 recording 0.57-0.69 ms + submit 0.05-0.09 + present 0.12-0.18 ms, the same on the RTX 3090 and the Radeon | see [D3D12 or Vulkan](#d3d12-or-vulkan) |
| **PSO compiles** | no (one-time hitches) | `[pso-prewarm] N pipeline(s) created ahead`; `RSX_HITCH_LOG=1` lists misses | first session of a build: 95 misses, 42 compiles, 1.1 s in total, worst frame 0.7 s; second session: 0 compiles | the cache warms itself; only the first fight after a build hitches |
| **Online: the other player's PC** | **yes** | `[netplay] speed: X fps, this PC Y fps without the waits for the peer` (now in system.txt) | rollback pair, one slow PC: both games at that PC's speed (32 fps before 0059, 46 after) | both games run at the slower PC's speed; the lobby keeps <40 fps PCs out of ranked |
| **Online: deep rollbacks at high ping** | at 150 ms+ with a busy PC | `[rbnet]` lines: rollbacks, re-simulated frames | default pair at RTT 150: 300-frame median 60.0 fps (16 logical processors each) | docs/ROLLBACK.md |
| **Windows Game Mode / HAGS** | unlikely; not tested (system settings) | 0059: system.txt "Windows graphics settings: Game Mode ..., hardware-accelerated GPU scheduling ..." | -- (both at their defaults here) | leave on; if a player has stutter only, try toggling HAGS (needs a restart) |

## Measurements

All on the development PC: Ryzen 9 7950X (32 logical processors, ~5 GHz),
RTX 3090 and the CPU's integrated Radeon (2 RDNA2 compute units),
Windows 11, display 59.95 Hz (display lock on). Direct fight Lili vs Asuka,
stage 20, P1 attacking, `tools/fight_bench.py --polite` (muted, below
normal), window fight start +24..42 s (~1,000 frames). Two games at a time,
one on each CCD half (logical processors 0-15 / 16-31) with the same
configuration, so each row has two runs. Other agents' games kept 2.7-8
processors busy. "Game part" and "translation" come from the latency probe
(`PS3_LATENCY_LOG`: release -> flip request -> walker reached the flip).
Local evidence: `build/wfps/runs/` (git-ignored).

### CPU: cores, threads, priority, power

| configuration (affinity mask) | fps | p99 ms | game part ms | translation ms |
|---|---|---|---|---|
| 8 cores / 16 threads (0xFFFF) | 59.95-59.96 | 17.7-18.9 | 5.1-6.0 | 2.2-2.9 |
| 6c/12t, 4c/8t, 6c/6t, 3c/6t (0xFFF, 0xFF, 0x555, 0x3F) | 59.95-59.96 | 17.7-18.7 | -- | -- |
| 4c/4t (0x55) | 59.95-59.96 | 17.9-18.8 | 6.5-7.1 | 2.3 |
| 2c/4t (0xF) | 59.95-59.96 | 18.0-18.7 | 8.0-8.2 | 2.6-2.7 |
| 4c/4t, the 4 sibling threads busy (a program on each core's other thread) | 59.90-59.96 | 18.2-18.4 | 9.8-10.3 | 3.7-3.8 |
| the same + EcoQoS | 59.90-59.95 | 18.4 | 10.3-10.5 | 3.7-3.8 |
| 2c/4t + EcoQoS | 59.89-59.95 | 18.7-19.1 | 8.5-8.6 | 3.0-3.2 |
| 8c/16t + EcoQoS | 59.95-59.96 | 18.0-18.1 | 6.2-6.6 | 2.8-3.0 |
| 2c/4t + 4 busy programs, same priority | 59.95 | 17.8-18.0 | 9.3-9.7 | 3.4-3.5 |
| 3c/6t, game at idle priority below 3 busy programs | 59.96 | 18.9-19.1 | 10.1-10.2 | 3.6 |

Nothing on this PC's cores goes below 60: the worst stand-in (busy siblings)
still left 3 ms of the 16.7. Process-level knobs cannot lower a core's clock
(EcoQoS only took 6-25 %), so the slow-core case was reproduced with test
hooks that add CPU time to the frame (below).

### A slower PC by test hooks, and patch 0059

`PS3_TEST_SLOW_GAME_US=N` busy-waits N us on the main thread before it asks
for its flip, `PS3_TEST_SLOW_XLAT_US=N` on the walker when it reaches the
flip (patch 0059, test only). 8c/16t each, final build, `PS3_LATE_FLIP=0`
(before) against the default:

| stand-in | game part + translation | before: fps / p50 / p99 ms | 0059: fps / p50 / p99 ms | vblank clock before / after |
|---|---|---|---|---|
| none (60 fps PC) | 5.9 + 2.4-2.9 | 59.95 / 16.7 / 17.8-19.0 | 59.96 / 16.7 / 17.7-18.9 | -- |
| +10 ms game, +2 ms translation (a core ~1.6x slower) | 15.5 + 4.3 | **39.4-40.0** / 28.0-28.4 / 30.9-33.3 | **48.5-50.0** / 20.0-20.5 / 21.1-22.7 | 59.95 / 48.9 |
| +12.5 ms game, +2 ms translation (~2x slower) | 18.0 + 4.3 | **29.98-30.01** / 33.4 / 34.2-34.9 | **42.8-44.2** / 22.6-23.3 / 23.7-25.2 | 59.95 / 43.0 |
| +6 ms game, +3 ms translation (an earlier build, `PS3_LATE_FLIP=0`) | 11.4 + 5.3 | 54.7-58.5 / 16.7-17.1 / 28.0-29.1: frames of 17-18 ms, not 33 -- a frame late only by its translation was already shown at once | -- | -- |

The `[slow-frames]` lines of the same runs: before "CPU 687 (game 686 ...)",
"0 late"; after "CPU 370 (game 370 ...)", "741 late for their vblank, shown
when translated".

**Online.** `tools/rollback_net_test.py --fight 26,33,20,2 --rtt 150
--jitter 5 --loss 3 --mode1 default --mode2 default` (rollback, the online
default), the joiner slowed by +10 ms / +2 ms, both sides `PS3_LATE_FLIP`
0 or default, 8c/16t each (final build):

| | match fps (300-frame median) host / joiner | sync |
|---|---|---|
| before (`PS3_LATE_FLIP=0`) | 31.6 / 31.8 (30.6) | 0 mismatching frames, same result hash |
| 0059 | **45.8 / 46.5 (46.2)** | 0 mismatching frames, same result hash |
| 0059, both at full speed | 57.5 / 58.7 (60.0) | 0 mismatching frames, same result hash |

A lockstep pair (RTT 30, 1 % loss) with the slowed joiner and 0059: 0
mismatching frames, same hash, the slow side at 49 fps.

### GPU: integrated graphics and Internal resolution

`RSX_ADAPTER=radeon` (the 7950X's 2-CU Radeon -- about a UHD 620 / older
Vega 3 class, a sixth of a 780M), all processors, power saving on by itself:

| Internal resolution | fps | GPU ms per frame (median) | walker CPU ms | `[slow-frames]` |
|---|---|---|---|---|
| Native | 59.95 | 2.5-2.6 | 2.25-2.53 | -- |
| 1080p | 59.95 | 6.3 | 2.27-2.35 | -- |
| 4K | 27.7-28.6 | 32.2-33.4 | 2.36-2.39 | "GPU 853" of 854 slow, GPU wait 26.5 ms |

0059 changes nothing for a GPU-bound frame (4K: 27.7-28.4 fps without, 28.5-28.6 with).

### Displays

`RSX_TEST_DISPLAY_HZ` (simulated refresh, display lock off), 8c/16t:
50 Hz 59.94 fps (presents without vsync, as in patch 0031), 75 Hz 59.94-59.95
(uneven on the screen, as expected: present-to-present p95 20.9 ms), 144 Hz
59.94. A non-60 display never slows the game.

### Renderer CPU per frame (the D3D12 side)

Frame log (`PS3_FRAMELOG`) medians, 826-838 draws per frame, ms. Patch 0059
splits the recording after the texture binding into the columns
`ph_desc_us`, `ph_cbcopy_us`, `ph_api_us`, `ph_post_us`:

| | RTX 3090 | Radeon (integrated) |
|---|---|---|
| walker CPU per frame (`fifo_cpu_us`) | 2.35-2.93 | 2.25-2.53 |
| FIFO walk, method dispatch, vertex-program/constant windows | 0.73-0.92 | 0.70-0.76 |
| texture lookup + binding (guest texture hash 0.17-0.25 of it) | 0.42-0.51 | 0.34-0.40 |
| PSO key + lookup (our hash table) | 0.24-0.29 | 0.24-0.26 |
| vertex layout/fetch hand-off (3 workers decode) | 0.22-0.24 | 0.21-0.25 |
| **D3D12 recording**: barriers, render-target binding, descriptor tables (`ph_desc`) | 0.27-0.32 | 0.25-0.28 |
| **D3D12 recording**: root signature, PSO, CBVs, viewport, scissor, IA, draw (`ph_api` + `ph_post`) | 0.31-0.46 | 0.33-0.39 |
| vertex-constant block copies (8 KB per changed block) | 0.07-0.08 | 0.07 |
| **submit** (ExecuteCommandLists) | 0.09 | 0.04-0.06 |
| **present** (DXGI Present call) | 0.17-0.18 | 0.12-0.18 |
| GPU time per frame | 0.8-0.9 | 2.5-2.6 |

The D3D12 calls: **0.7-1.0 ms per frame** (the recording ~0.8 us per draw), ~5 %
of a frame, ~30 % of the translation; the rest of the translation is our own
work (walking the PS3 command stream, hashing guest textures and states). The
game part (5-6 ms here) is the larger share of the critical path everywhere.

## D3D12 or Vulkan

**On Windows, Vulkan would not fix 40-50 fps.**

- The API work a Vulkan backend could change is the 0.7-1.0 ms above.
  Vulkan's per-draw cost is of the same kind (thin API, the driver records
  the same state); what it adds are push descriptors and more dynamic state.
  Optimistically that halves the recording part: **~0.3 ms per frame here,
  ~0.6-0.7 ms on a CPU with half the per-core speed** -- 3 % of a 20 ms
  frame. The game part, the walk, the texture hashing and the GPU work stay.
- The same saving is open in D3D12: copy the 16-entry SRV table only when it
  changed (today every draw copies one), and skip state that did not change
  since the previous draw (descriptor heaps, root signature, render targets,
  viewport, scissor, stencil reference). Estimated 0.2-0.3 ms per frame here.
  Not done in 0059: every pass that binds its own state (copies, the stage
  filter's guest view, depth snapshots, present filters, the overlay) would
  have to invalidate the cache, and a missed one draws wrong; it is worth it
  only with a frame-exact picture comparison of every stage, for ~2 % of a
  frame.
- Cost of a Vulkan backend: `rsx_live_draw.c` is 13,600 lines of D3D12
  (surfaces with scale factors, depth snapshots, texture pool, PSO library
  and prewarm, filters, the overlay, DRED). A second backend means writing
  and then keeping two of them correct, plus SPIR-V instead of HLSL for the
  decompiled shaders: weeks, then a permanent cost on every renderer fix.

**Linux and the Steam Deck** are a different question. D3D12 exists only on
Windows; on Linux the game runs through Proton, which turns D3D12 into
Vulkan (vkd3d-proton) -- that layer costs some CPU on the walker thread, but
it is not where a Deck loses frames. The Deck's Zen 2 cores (2.4-3.5 GHz)
have roughly half this PC's per-core speed: an estimated game part of 11-13
ms plus 4-6 ms of translation, i.e. around the 16.7 ms line -- 0059 matters
more there than the API. A native Linux build needs far more than a renderer
(window, WASAPI audio, XInput/DirectInput/HID pads, Media Foundation movies,
sockets, the build toolchain and launcher; docs/MACOS.md has the same list
for macOS: 70-100 agent-days). Recommended order: try the Windows release
under Proton on a Deck first; a native Vulkan renderer only if Linux/Deck
becomes a goal of its own.

## What changed (patch 0059)

| change | switch |
|---|---|
| **Late frames shown when ready.** The first vblank tick a frame misses now waits for it (up to one period, like a variable-refresh display); when the walker has translated the frame, the tick fires at once and the ticks after it follow from there. One vblank per frame as before -- the vblank clock never runs above the frame rate or above 59.94/60; a frame still not done after the extra period gets the held tick and the next together, as before. Timing only: the game runs the same frames, so the two PCs of a match may differ (pairs above in sync) | `PS3_LATE_FLIP=0` = the old way |
| `[slow-frames]`: "N late for their vblank, shown when translated"; "other programs X of Y logical processors busy, the game Z (of W it may use)"; a tick that waited for the walk counts as translation, not "vblank thread late"; the line also comes every 30 s when frames are only late | `PS3_SLOW_FRAMES=0` |
| Frame log: the draw recording after the texture binding in four columns (`ph_desc_us`, `ph_cbcopy_us`, `ph_api_us`, `ph_post_us`) | with `PS3_FRAMELOG` only |
| Test hooks `PS3_TEST_SLOW_GAME_US`, `PS3_TEST_SLOW_XLAT_US`: a slower PC on a fast one | off unless set |

Repository side: `tools/fight_bench.py --priority normal|below|idle`,
`--hog N [--hog-cpus MASK] [--hog-priority P]` (busy programs of our own next
to the game), `--ecoqos` (the game under Windows' efficiency mode), and the
renderer split per frame from the frame log; the problem report's
`system.txt` gets "Windows graphics settings: Game Mode ...; hardware-
accelerated GPU scheduling ..." (read only) and the `[netplay] speed:` lines,
and keeps `[slow-frames]` lines up to 900 characters.

Checked: smoke quick PASS (one fps WARN in practice-select, 57.6, the same
on main's build back to back), `tests/` 700 OK, the rollback and lockstep
pairs above, every fight_bench row above.

## Player checklist

Paste this to a player who reports 40-50 fps:

> **If the game runs at 40-50 fps, please check:**
>
> 1. **Update to 1.1.3 or newer.** It shows a frame as soon as it is ready
>    instead of waiting for the next screen refresh: on a PC that is a bit
>    too slow for 60 this alone gives 5-15 fps more.
> 2. **Laptop or handheld: plug in the charger** and set Windows to
>    **Best performance** (Settings -> System -> Power -> Power mode), or
>    your handheld's Turbo/Performance mode. Leave **Power saving** in the
>    launcher on **Auto**.
> 3. **Close other programs** while you play: browser (especially video),
>    Discord video/streaming, recorders and overlays, downloads, updates.
>    The game needs one fast processor core for itself.
> 4. **Internal resolution:** on integrated graphics (laptops, mini PCs,
>    handhelds) use **Auto**, **1080p** or lower -- never more than your
>    screen. 1440p and 4K need a real graphics card.
> 5. **Online:** both games always run at the speed of the slower PC. If
>    you only see 40-50 fps against one opponent, the slow PC may be theirs.
> 6. **Do not start the game in "efficiency mode"** or at low priority
>    (Task Manager, Process Lasso and similar tools).
> 7. A 50, 75 or 144 Hz screen does not slow the game. If an fps counter
>    of an overlay says something else, trust the fps in the launcher.
> 8. Still slow? Play one fight, then click **Report a problem** in the
>    launcher and send us the zip. The report says whether the processor,
>    the graphics card or other programs were the limit.

For us, in that report (`system.txt`, "How the game ran"):

- `[slow-frames] ... CPU N (game N ...)`, median game 12-17 ms, many "late
  for their vblank": the processor's single-core speed. Ask for power mode,
  charger, other programs; nothing else to set.
- `other programs X of Y logical processors busy` with X large: background
  programs.
- `GPU N` and a GPU wait of several ms, or "GPU-bound" / "integrated
  graphics busy" at the end of the line: Internal resolution too high for
  the graphics. "What the log says about speed" in `system.txt` says it in
  one line.
- `processor clock limit A of B MHz (held back ...)`: heat or the power
  plan.
- `[netplay] speed: 45 fps, this PC 59 fps without the waits for the peer`:
  the opponent's PC.
- `vblank clock` below 59.9 Hz with late frames: the game ran slower than
  60 because its frames were late (since 0059 the clock follows the frames).

## Reproducing

Build: any tree with the series up to 0059 (`tools/prepare_ps3recomp.py`).
Never run tests from `build/cmake` (other agents use it).

    # a weaker CPU on this PC (logical processors 0-3 = 2 cores / 4 threads)
    python tools/fight_bench.py --exe <t5dr.exe> --polite --cpus 0xF --json out.json
    # siblings busy: game on one thread per core, busy programs on the others
    python tools/fight_bench.py --exe <t5dr.exe> --polite --cpus 0x55 --hog 4 --hog-cpus 0xAA
    # background programs above the game
    python tools/fight_bench.py --exe <t5dr.exe> --polite --cpus 0x3F --hog 3 --priority idle
    # a slower core by test hooks, before/after 0059
    python tools/fight_bench.py --exe <t5dr.exe> --polite --cpus 0xFFFF PS3_TEST_SLOW_GAME_US=10000 PS3_TEST_SLOW_XLAT_US=2000 PS3_LATE_FLIP=0
    python tools/fight_bench.py --exe <t5dr.exe> --polite --cpus 0xFFFF PS3_TEST_SLOW_GAME_US=10000 PS3_TEST_SLOW_XLAT_US=2000
    # integrated graphics, display rates
    python tools/fight_bench.py --exe <t5dr.exe> --polite RSX_ADAPTER=radeon PS3_INTERNAL_RES=1080p
    python tools/fight_bench.py --exe <t5dr.exe> --polite --cpus 0xFFFF RSX_TEST_DISPLAY_HZ=50

Add `PS3_LATENCY_LOG=<file>` for the per-frame game part and translation
(events B, F, X, K, V and, with 0059, L = a held tick released by its frame).
