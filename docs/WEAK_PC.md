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
  Vulkan](#d3d12-or-vulkan)), and patch 0062 took them: the D3D12 recording
  halved, the whole translation a quarter shorter.
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
- **Patch 0061 made the main thread's own work smaller**: every lock and unlock
  of the game's light-weight mutexes was two Windows kernel calls, even with
  nobody else waiting -- about a third of its work in a fight. Measured on 4
  cores / 8 threads: CPU per frame 6.3 -> 4.6 ms (median), online with
  rollback 9-11 -> 6-6.7 ms (docs/RENDER_PERF.md "The game thread's own
  time").
- **1.2.1, old PCs** ([below](#old-pcs-121)): what the game needs and why, the
  **Old PC settings** the launcher picks by itself on 2 cores or an old graphics
  card, and less processor work on every PC from before 2013 (no AVX2/FMA3):
  the SPU sound core and the skinning keep their registers in host registers
  (patch 0113), the game thread's vector float math runs four lanes at a time
  (patch 0114) -- the same results bit for bit.

## Old PCs (1.2.1)

The owner: *"weak PC means OLD PC. T4 should run on old specs, and T5DR too -- it's static recomp."* The target is a
PC from 2010-2012: a processor with 2 cores / 4 threads (Intel Core i3-2100, i3-3240) or 4 cores without
Hyper-Threading (Core i5-2500), the oldest graphics cards with Direct3D 12 at feature level 11_0 (NVIDIA Kepler GT
630/730, AMD GCN 1 HD 7000), 4 GB RAM.

### What the game needs, and why

| requirement | what needs it | old PCs it leaves out | can it go? |
|---|---|---|---|
| Windows 10 or 11, 64-bit | Direct3D 12 (the renderer) | Windows 7 / 8.1 | no: Direct3D 12 exists only on Windows 10 and newer (a Direct3D 11 renderer is not planned) |
| a 64-bit processor with **SSE4.1** | the runtime is compiled with `-msse4.1`: the SPU sound core's byte shuffles, blends and float ops (`spu_helpers.h`) | Intel Core 2 before "Penryn" (E6000, Q6000 -- 2006/2007), AMD Phenom II, Athlon II, the A-series "Llano" (2011), E-series "Bobcat" | not usefully: the scalar fallbacks exist and give the same bits, but on them the sound core needs 2-3x its time -- 1.0 needed 9-12 ms of each 5.33 ms audio tick before SSE4.1 -- so such a PC would lose its sound. The game says so at its start (exit code 14, `src/platform/cpu_check.cpp`) and since 1.2.1 **Check my problem** says it before a build. Every Intel Core i3/i5/i7 and every AMD FX / A-series from 2012 / Ryzen has SSE4.1. **Since branch t5-oldhw-019** the release also ships `runtime\sse2\t5dr.exe` (CMake `T5DR_X86_BASELINE`, ps3recomp patch 0126: SSE2 forms of the helpers with the same bits) and BUILD GAME picks it on such a processor (`tools/build_game.py` `choose_runtime`, CPUID through the bundled clang): same game state, about 1.3x the processor time, see [SSE2_BASELINE.md](SSE2_BASELINE.md) |
| CMPXCHG16B (`-mcx16`) | the runtime's atomics | none: Windows 8.1 and newer need it themselves | -- |
| AVX, AVX2, FMA3 | none is required. The build selects x86-64-v3 with its full feature set; since 1.2.2 it selects AVX1 on Sandy/Ivy Bridge with OS AVX support, otherwise the x86-64 baseline. AVX1 keeps exact software FMA; see RENDER_PERF.md "1.2.2" | -- | -- |
| Direct3D 12, feature level 11_0 | the renderer | Intel HD 2000-4000 (Sandy and Ivy Bridge graphics: Intel never shipped a Direct3D 12 driver for them), AMD HD 5000/6000 (TeraScale), NVIDIA before Fermi | no (no driver to talk to); Intel HD 4200-4600 (Haswell) have Direct3D 12 but players saw device losses on HD 4400 (TROUBLESHOOTING "Intel HD 4400") |
| resource binding tier 1 | supported since 1.1.5 (patch 0081's tier-1 path) | -- | -- |
| RAM | the game: 0.8 GB working set, 1.1 GB committed in a fight (measured below); BUILD GAME: the lift ~0.6 GB, each compile job 0.3-0.6 GB (the number of jobs follows the free memory) | -- | 4 GB is enough |

### The Old PC settings

Launcher -> Settings -> Graphics -> **Old PC**: Internal resolution Lowest, no stage blur, no shadows, no effects.
Fewer draws for the processor to translate and for the card to draw (GitHub #12's PC: 24 -> 34 fps with shadows and
effects off). On an old PC -- a processor with 2 cores or fewer, or a graphics card with resource binding tier 1 as the
newest game log names it -- the launcher chooses them **by itself, once**, while the graphics settings are still as it
ships them, and says so on the Play tab; **Default** puts the normal look back, and then it never chooses them again.
Picture only: online both players may differ. (The owner's "Lowest" keeps the effects on; "Old PC" is the stronger
step.) The game's own 2-core mode (1.1.5) switches on by itself on 2 cores.

### Measured

On this PC (Ryzen 9 7950X) by stand-ins -- the game on 2 cores / 4 threads or 4 cores, `tools/slow_core.py` taking 60 %
of them, the software paths of a CPU without FMA3, the tier-1 path forced (RENDER_PERF.md "1.2.1: old PCs"):

| stand-in | 1.2.0 | 1.2.1 | 1.2.1 with the Old PC settings |
|---|---|---|---|
| 2 cores / 4 threads: fps; processor time a frame | 59.4; 19.4 ms | 59.0-59.5; 18.0-18.6 ms | 59.5-60.0; 16.0-16.4 ms |
| 4 cores / 4 threads, the pool stage | 52.3 (a stall); 15.4 ms | 59.7; 15.0 ms | -- |

The stand-ins hold ~60 either way, so the gain shows as processor time: 4-7 % less a frame, 15-18 % less with the Old
PC settings -- on a real 2-core PC that is about the frame rate it gains. Real players: an i5-2500 (4 cores, 3.3 GHz)
with a Kepler GT 730 plays fights at 55-60 fps (1.1.5 log); GitHub #12's i3-3240 with a Fermi GT 730 at 20-34 fps,
bound by the card at the defaults and by its 2 cores with lighter settings. Memory: the game 0.8 GB working set, 1.1
GB committed in a fight.

### The old graphics card (GitHub #12)

The i3-3240 + Fermi GT 730 (resource binding tier 1) logs said game 17-22 ms, "render translation" 27 ms and GPU
32-37 ms a fight frame at 0.5x. What that was, and what changed since:

- **"Translation 27 ms" was 20 ms of waiting for the GPU** (one frame in flight, 1.1.4); the translation's own work
  was ~6.6 ms on his 2 cores against 3.5 on the i5-2500 (twice the per-core load: 2 cores + Hyper-Threading). Since
  1.1.5 a dedicated card has two frames in flight, so the wait overlaps the next frame (patch 0075: +7-13 % with a GPU
  slower than the game, measured with `RSX_TEST_SLOW_GPU`).
- **The GPU's 32-37 ms are per draw, not per pixel**: 16x the pixels (0.5x -> 2x) cost only 22 % of the frame rate.
  ~830 draws a fight frame; his 1.1.6 warm-up log (`build/issue12`, local) has `[gpu-pass]` lines only from menus and
  4-second warm-up fights (30-100 draws a frame): 1280 x 720 passes at 50-65 us a draw and the present (one full-screen
  copy) at 1.2 ms -- consistent with a card of ~14 GB/s memory (the DDR3 GT 730) that is simply slow. Shadows and
  effects off cut the draws by ~40 % (his 24 -> 34 fps): the **Old PC settings** do that by themselves now.
- What nothing here can measure (every GPU here is tier 3): whether tier-1 descriptor emulation or the per-draw
  constants read from system memory over PCIe (`[gpu-pass]` "read from system memory per frame": 4.3 MB of vertex
  constants in a fight) dominate on such a card. Patch 0081 already trims the binding work on tier 1 (`[gpu] tier-1
  binding path: on`). **What would settle it:** one fight's game log from that PC with 1.2.1 at the defaults and one
  with the Old PC settings (the `[gpu-pass]` lines are on by default on tier 1), plus the same fight with
  `RSX_TIER1_PATH=0` under Extra settings.

### A second old GT 730: frames held, not drawn (1.2.3, report YESB6Y)

An i7-9700 (8 cores) with a Fermi GT 730 (resource binding tier 1, the last Fermi driver from March 2018) on a 75 Hz
screen, 1.2.2 at the defaults: menus at **37.5 fps = 75 / 2**, fights at **25 = 75 / 3**, and every slow window read
"translation 24 ms, GPU wait 23 ms, GPU busy 4 ms a frame (17 %)" -- the game 1.4 ms, the translation's own work 1.0.
The card worked 4 ms of each frame and still the frame waited 23 ms for it: something held the frame's command list
before the card started it, in whole refreshes of the screen. The verdict called it "CPU-bound". What 1.2.3 does
(RENDER_PERF.md "1.2.3: frames held before the GPU starts them"):

- each list's start on the GPU is put on the processor's clock, so the log says how long the queue held it
  ("GPU queue: ... held before the GPU started it", and how many of those started right after a display refresh);
- such a window gets the verdict **"GPU held"** (the driver or the display path, not the processor, not the
  resolution) and the launcher says to try VSync Off;
- on a screen faster than 60 Hz the game presents without vsync from then on (no tearing; what the 59/60 Hz
  display lock has always done). Whether that frees this card is **not known**: nothing here holds frames like it
  (every GPU on this PC is resource binding tier 3). The next log from such a PC answers it -- the same "GPU queue"
  part after the switch.

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
| **Slow CPU cores** (old/low-clock CPU, laptop at low clocks, Zen 2 handheld) | **yes -- the main cause** | `[slow-frames]` "CPU N (game N ...)", median game 13-17 ms; many "late for their vblank"; `vblank clock` below 59.9 (0059: the clock follows the frames) | stand-in by test hooks: game part 15.5 ms -> 40 fps before, 49-50 after 0059; 18 ms -> 30 / 43-44 | patch 0059; patch 0061 (the main thread's own work per fight frame about a quarter smaller, [RENDER_PERF.md](RENDER_PERF.md#the-game-threads-own-time-patch-0061-branch-game-thread-cpu)); power mode / charger; close programs (they take the shared core) |
| **Few cores** (4-6 logical processors) | no, at a fast core | `[sched] CPU budget: 4 logical processors` | 2c/4t, 4c/4t, 3c/6t, 6c/6t, 4c/8t, 6c/12t, 8c/16t: 59.95 fps each; game part 8.1 ms at 2c/4t vs 5.1-5.9 at 8c/16t | patch 0027/0047 size the pools; nothing to set |
| **SMT sibling busy** (another program on the other thread of the game's core) | yes, adds to a slow core | game median up, "other programs N busy" | 4c/4t with the siblings busy: game part 6.5-7.1 -> 9.8-10.3 ms, translation 2.3 -> 3.7 ms (+45-60 %) -- still 60 here | close programs; a slower core with busy siblings drops below 60 |
| **SPU / SPURS job threads competing** | no | spurs-job / spu threads in fight_bench | skinning wait 0.7 ms at 4 processors (patch 0027); job threads 0.5 of a core at 32 | fixed in 0027 |
| **Background programs** (browser, recorder, virus scan, update) | sometimes | 0059: "other programs X of Y logical processors busy" next to the slow frames | 4 busy programs on the game's 2c/4t at the same priority: 60 fps, game part 8.1 -> 9.3-9.7 ms; game *below* 3 busy programs (idle priority): 60, game part 10.1 ms | the game's own threads run above normal priority, so equal programs mostly cost the shared core and cache; close them anyway |
| **Lower process priority** (game started at low priority, "efficiency mode") | rarely | the same as above | idle-priority game under 3 busy programs: 59.96 fps at this core speed | do not start the game below normal / in efficiency mode |
| **Power plan, laptop heat, battery** | yes on laptops/handhelds; on APUs on AC too | `[power]`, `[slow-frames]` "processor clock limit X of Y MHz (held back ...)", "on battery"; since 0063 "processors at X GHz on average (Y % of their Z)" -- the 780M mini PC on AC, Balanced plan, 4K: 2.26 GHz, 81 % of 2.79 (1.1.4's launcher says it once on the Play offline tab: RENDER_PERF.md "1.1.4: Auto by default on integrated graphics") | EcoQoS on the whole game (Windows' efficiency mode): game part +5-15 %, translation +5-25 % | charger, "Best performance", power saving Auto (0047) |
| **Display not 60 Hz** (50 Hz TV, 75/144 Hz with VSync) | no | `[pacing] display 50 Hz: slower than the game's 59.94 Hz ...` / `display 144 Hz: vsync on` | simulated 50, 75, 144 Hz: 59.94 fps each; 75 Hz shows frames unevenly (present p95 20.9 ms) but the game keeps its speed | 120 Hz or 60 Hz for the smoothest picture; VRR |
| **Overlay fps counter on a 144 Hz screen** | a reading, not a cause | -- | -- | the game's own `[fps]` line / the launcher's fps is the game's speed |
| **iGPU at high Internal resolution** | yes at 1440p/4K | `[slow-frames]` "GPU N", GPU wait ms; `[gpu] adapter: ... integrated`; since 0063 "GPU busy N %" and "GPU-bound" / "integrated graphics busy" at the end of the line. A stronger APU (780M) shows a long **game** part instead: the busy GPU slows the CPU work through the shared memory and power (RENDER_PERF.md "4K on integrated graphics") | this PC's 2-CU Radeon: Native 2.5 ms GPU, 60 fps; 1080p 6.3 ms, 60 fps; 4K 24-32 ms, **28-35 fps**; Auto (1080p) 59.7 fps | Internal resolution 1080p or Auto (at most 1080p on integrated graphics), Native/Lower on weak ones |
| **Old graphics card** (resource binding tier 1: the GT 730 with the Fermi chip, GT 4xx/5xx, Haswell graphics) | **yes** -- a player's i3-3240 + GT 730 4 GB: 20 fps | `[gpu] adapter: ... resource binding tier 1`; GPU busy 32-37 ms a frame that hardly follows the resolution (0.5x vs 2x: +30 % fps for 16x fewer pixels); before 1.1.5 also a "GPU wait" of ~20 ms inside the translation; since 1.1.5 `GPU-bound: the graphics card needs X ms a frame at <step> -- the card itself is the limit` and `[gpu-pass]` lines (per pass, and what the GPU reads from system memory) | no such card here; a stand-in by `RSX_TEST_SLOW_GPU` (RENDER_PERF.md "2-core mode and slow graphics cards") | 1.1.5: two frames in flight on a dedicated card (the GPU no longer waits for the game and the game no longer for the GPU); beyond that a newer card -- a lower resolution saves little |
| **2 cores / 4 threads** (i3-3240, i5-4210M) | at a slow core, yes | `[sched] processors: 4 logical, 2 cores ..., 2-core mode`; the game thread's processor time 1.8-2.4x the 4-core PC's at the same clock | stand-in (2 cores here + `tools/slow_core.py`): the game thread on a core of its own was 21-33 % slower (everything else on one core), fewer workers 12-18 % slower | 1.1.5: the sound core no longer prefers the game thread's processor; `PS3_TWO_CORE_OWN=1` to try the own core on a real 2-core PC |
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

1.1.4 (integration build with 0066, `PS3_LAPTOP=auto`): the pool stage at 4K
is the 780M player's picture -- 55.4 fps, 6.4 % late frames, GPU 80 % busy,
and 46.5 fps / 61 % late with more programs busy -- against **59.6 fps** with
Auto (1080p); stage 20 at 4K 35.5-37.4 fps, Auto 57.9-59.9. So the launcher
now makes Auto the default on integrated graphics and warns above it
(RENDER_PERF.md "1.1.4: Auto by default on integrated graphics").

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
- The same saving was open in D3D12, and patch 0062 (branch `xlat-cpu`)
  took it: a descriptor table is copied only when no earlier table holds the
  same descriptors, state is recorded only when it differs from what the
  command list already has bound (every pass that binds its own state forgets
  the cache), one vertex and index buffer view serves the whole upload ring.
  D3D12 recording 0.78 -> 0.39 ms per frame (median, paired runs on a loaded
  PC), and with a cheaper command walk and PSO key the whole translation
  3.23 -> 2.47 ms; lockstep pairs, old build against new, dump byte-identical
  surfaces of the same frames. Details: docs/RENDER_PERF.md "Translation CPU".
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
>    handhelds) use **Auto** (the default there since 1.1.4), **1080p** or
>    lower -- never more than your screen. 1440p and 4K need a real graphics
>    card: a busy built-in GPU also slows the processor.
>    **An old or weak graphics card** (a GT 730 and the like, 1.1.5 or
>    newer): Settings -> Graphics -> **Lowest (old graphics cards)** --
>    the 3D scene at half size, no stage blur or shadows (the effects, hit
>    sparks too, stay on). It also leaves the processor less to translate.
>    **Default** puts it back.
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
- 1.1.5: `GPU-bound: the graphics card needs X ms a frame at <step> -- the
  card itself is the limit (an old graphics card: resource binding tier 1)`:
  the card, not the resolution (Native or below already); the `[gpu-pass]`
  lines of such a log say which passes take the time -- please keep them for
  us. Since patch 0081 they start with the binding work per frame (`per frame:
  binding 830 draws, tables set ..., descriptor heaps ...`) and the log says
  `[gpu] tier-1 binding path: on` (RENDER_PERF.md "Online pictures and old
  graphics cards"). `CPU-bound: the game needs X ms ... the render translation Y`: the
  processor; `CPU and GPU in turn`: one frame in flight
  (`RSX_FRAMES_IN_FLIGHT=1`, or integrated graphics) with a slow GPU.
- `processors at X GHz on average (Y % of their Z)` well under 100 % on AC
  power with late frames: the power mode (Balanced holds an APU back), or the
  built-in GPU taking the shared power budget -- Best performance and a lower
  Internal resolution both help. 1.1.4's launcher says it once after a game.
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

## i3-3240 stand-in

The 1.2.2 continuation targets Ivy Bridge 2 cores / 4 threads at 3.4 GHz,
AVX without AVX2/FMA3, SSE4.1 and 4-8 GB RAM. Keep the baseline generated
DLL and compare the retained AVX1 DLL using the same host; force software
FMA (`PS3_FP_SOFT_FMA=1`, `PS3_CRT_FMA3=0`) and resource-binding tier 1
(`RSX_TIER1_PATH=1`). The mask `0xF000` selects the two adjacent SMT cores
used for this task. Old PC settings are Lowest internal resolution, stage
blur, shadows and effects off. Test both stages 30 (pool) and 20.

`tools/calibrate_slow_core.py` builds fixed native single-thread integer
and scalar-FP workloads without AVX/FMA. It brackets each slowed sample by
unthrottled samples, verifies deterministic checksums and process priorities,
and accepts a duty only if **both** median throughput ratios are 55-60%
and every unthrottled bracket stays within 5%. Use the accepted duty and
4,000-us period on the exact game mask. The previous round's nominal
`--busy 60` was not such a calibration. Its CPU results must not be relabeled
as measured i3-3240 performance.

This is a scheduling-availability proxy on Zen 4, not an emulation of Ivy
Bridge IPC, caches, RAM bandwidth or SMT efficiency. Synchronized busy
intervals can themselves add wake jitter, unlike a continuously running
3.4 GHz core. Baseline/AVX1 code avoids unsupported guest-code instructions,
but does not change the host processor's microarchitecture.
The development machine's RAM/VRAM capacity is also unchanged; this proxy
does not reproduce paging or memory pressure in a real 4-8 GB installation.

The GPU proxy uses `RSX_TEST_SLOW_GPU=16000000,256` with the forced tier-1
binding path. It adds a **fixed compute workload** and cannot reproduce
Fermi bandwidth, driver cost or the scaling of Old PC settings. In
particular, disabling game effects does not reduce that injected workload.
Do not lower the hook simply to make a 60 FPS result: a GPU that actually
needs 32 ms/frame is already 15.33 ms over the 16.67-ms budget before CPU
work, and requires at least a 1.92x GPU-time improvement. Those are budget
arithmetic, not a new measurement of the player's card.

| i3-3240 stand-in: ms/frame | before | after | interpretation |
|---|---:|---:|---|
| Game thread CPU | not measured | not measured | CPU execution, separately from release-to-flip wall time |
| Translation | not measured | not measured | FIFO CPU and wall time must both be reported |
| Sound core CPU | not measured | not measured | Sum named sound-core threads over the covered CPU window |
| Skinning CPU | not measured | not measured | Sum job workers; parallel CPU time is not a serial frame cost |
| GPU | not measured | not measured | Timestamp workload including the fixed slow-GPU dispatch |

The shared heavy slots prevented calibration and new game captures. No
accepted slowdown duty or new before/after budget is available; the exact
CPU limit on this machine class is therefore not established. The fixed
GPU-workload limitation above is known from how the proxy is constructed,
not a measurement of the player's Fermi card with the new settings.

No new 60 FPS or constant-frame-time claim follows from the earlier average
FPS tables. Acceptance needs complete successful non-occluded DXGI display
observations, a full steady-minute capture, zero offline >20-ms frames and
at most one/minute online through RTT 150 ms. The required p50/p95/p99/p99.9,
threshold counts, repeated refreshes and 15.7-17.7-ms share belong to that
display capture. Missing display evidence is unavailable, not zero judder.

Next levers, ranked by what can settle the limit:

1. Measure the real Fermi card with Old PC settings and GPU-pass timestamps;
   reduce the expensive passes or binding/upload traffic identified there.
   A fixed synthetic GPU delay cannot evaluate those optimizations.
2. If measured GPU time falls below 16.67 ms, optimize whichever exceeds the
   remaining serial CPU budget: game release-to-flip plus translation,
   accounting for skinning waits and sound-core competition on two cores.
3. For first-sight hitches, cover both requested stages and representative
   effects in warm-up; then move pipeline-library serialization off the
   steady render path if captures implicate it. For online-only tails,
   correlate rollback depth/restore/resimulation costs before changing rules.
4. Remove probe/log and wake jitter proven by those captures; retain
   frame-identical rollback/lockstep and replay checks for simulation changes.

Every run and reservation is in [FRAME_PACING122_RUNS.md](FRAME_PACING122_RUNS.md).
