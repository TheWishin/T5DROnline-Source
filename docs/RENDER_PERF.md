# Render translation performance (patch 0023)

Tekken 5 DR builds a whole frame of RSX commands (~750 KB, ~840 draws in a
fight), flushes it once, and then waits for the flip -- i.e. until our live
D3D12 engine (`libs/video/rsx_live_draw.c`) has walked and translated every
command. Game CPU and translation are therefore serialised, and the frame
fits in a vblank only when `game CPU + translation + present` stays under
16.7 ms. Patch 0023 cuts the translation and removes the first-fight hitch.
Every change has a switch; all are on by default.

(Compiler settings for the game's own CPU per frame -- profile-guided
optimisation of the lifted code, and what else was tried: docs/BUILD_PERF.md.)

## What changed

| Change | Switch (default on) | Effect per fight frame |
|---|---|---|
| Block walk: a run of plain 3D-engine words goes to the engine in one call; the vertex-program and constant upload windows (~70% of all words: the game re-uploads its vertex program for every draw) are stored without the per-word dispatch | `PS3_GCM_BLOCK_WALK=0` | walk 1.9 -> ~1.0 ms |
| Asynchronous vertex fetch: the walker reserves upper-bound space in the upload rings, records the draw, and 3 worker threads read indices, de-duplicate and decode vertices; every flush drains them; a 2D-engine guest write drains first | `RSX_VERTEX_ASYNC=0`, `RSX_VERTEX_THREADS=n` | fetch+upload 1.8 -> 0.3 ms (on the walker) |
| Vertex-program memo (size, hash, inputs, TXL units) keyed on the program actually changing; fragment-program memo (size, structural hash, constants) checked by memcmp | `RSX_VP_MEMO=0`, `RSX_FP_MEMO=0` | layout+PSO lookup 1.1 -> 0.35 ms |
| `rsx_fp_collect_constants` no longer memsets its 32 KB block per draw; word-wise structural hash; one pass over enabled texture units; 4-lane texture mutation hash | -- | ~0.5 ms |
| Present after the flip completes: the flip/vblank handlers run before the D3D submit + DXGI Present, so the game starts its next frame ~0.3-0.5 ms earlier | `PS3_PRESENT_LATE=0` | |
| Fence polls kick the walker only when there is something to walk (they woke it ~22,000 times a second) | `PS3_GCM_KICK_ALWAYS=1` restores | CPU |
| Texture pool: placed resources in 64 MB heaps with same-size block reuse (`CreateCommittedResource` cost 0.5-0.7 ms per texture, up to 20 ms under load) | `RSX_TEX_POOL=0` | fight load: ~90-130 ms of texture work -> ~20 ms |
| PSO disk cache (`ID3D12PipelineLibrary`, `pso_library.bin`) + prewarm: every pipeline is recorded (`pso_prewarm.bin`: key, shader blobs, state) and re-created on a background thread at start-up | `RSX_PSO_LIBRARY=0`, `RSX_PSO_PREWARM=0` | fight load: ~50 PSO builds (25-50 ms) -> 0-1 |

Both cache files live in the shader cache directory
(`scratch\rsx_shader_cache_v2\`, or `RSX_SHADER_CACHE_DIR`). The prewarm file
is tied to the executable's build (PE time stamp + image size) and is
discarded by any other build; a library from another driver/GPU is replaced.

## Measuring

`PS3_FRAMELOG=<csv>` gained columns: `xlat_us` (guest's last flush -> walker
reached the flip: the translation the game waits for), `fifo_cpu_us` (walker
thread CPU time, immune to preemption), and the per-draw phases `ph_layout`,
`ph_fetch`, `ph_upload`, `ph_pso`, `ph_const`, `ph_texbind`, `texhash`,
`clear`. `RSX_HITCH_LOG=1` prints slow texture decodes, every PSO miss with
its split, and a `[render-stats]` line every 600 frames.

Scripted runs open the window minimised (`PS3_WINDOW_BACKGROUND=1`). Windows 11
then ignores `timeBeginPeriod(1)` unless the process opts out (patch 0015
does): without it every 1-4 ms wait rounds to 15.6 ms, the vblank fires up to
14 ms late, and a fight measured minimised loses ~13 fps that a visible
window would not. Compare builds only with the opt-out in place.

## Results

Direct fight `T5_FIGHT=lil,ask,20,3` with scripted P1 input, window minimised,
RTX 3090 / Ryzen 9 7950X. Each configuration ran twice, interleaved with the
others; steady state = fight start +24..42 s (~1,040 frames), fight load =
fight start -2..+22 s. "base" is main's build (0001-0022 + 0015) without
0023; the other rows are 0023 with the named switches.

Quiet machine:

| config | fps | p99 ms | translation mean / p99 ms | fight load: worst translation / PSO / textures ms |
|---|---|---|---|---|
| base | 59.94 | 16.91 | 4.53 / 5.21 | 30.9 / 17.8 / 97.7 |
| 0023 all on | 59.94 | 16.91 | **2.39 / 3.08** | **5.8 / 0.0 / 12.1** |
| all switches off | 59.94 | 16.92 | 4.16 / 4.69 | 28.9 / 17.1 / 93.9 |
| `RSX_VERTEX_ASYNC=0` | 59.94 | 17.00 | 3.44 / 3.89 | 7.2 / 0.0 / 12.3 |
| `PS3_GCM_BLOCK_WALK=0` | 59.94* | 17.0* | 2.98 / 4.04 | 6.2 / 0.0 / 11.8 |
| `RSX_VP_MEMO=0 RSX_FP_MEMO=0` | 59.94 | 17.03 | 2.73 / 3.46 | 6.3 / 0.0 / 12.1 |
| `PS3_PRESENT_LATE=0` | 59.94 | 17.01 | 2.46 / 3.15 | 6.0 / 0.0 / 12.7 |
| `PS3_GCM_KICK_ALWAYS=1` | 59.94 | 17.03 | 2.40 / 2.83 | 5.8 / 0.0 / 11.8 |
| `RSX_TEX_POOL=0 RSX_PSO_PREWARM=0 RSX_PSO_LIBRARY=0` | 59.94 | 17.09 | 2.60 / 3.52 | 29.8 / 17.9 / 100.9 |

\* one of the two runs had a single 1.36 s present stall from outside the
process; the other run: 59.94 fps.

Loaded (16 busy-loop processes on the 32 logical CPUs), frames over 17.5 ms
in the ~16 s steady window:

| config | fps | p99 ms | frames > 17.5 ms | translation mean / p99 ms | fight load: worst / PSO / textures ms |
|---|---|---|---|---|---|
| base | 43.16 | 33.67 | 292 | 7.08 / 9.59 | 41.0 / 23.5 / 127.4 |
| 0023 all on | **59.83** | **17.14** | **2** | **3.98 / 5.38** | **11.6 / 0.0 / 18.8** |
| all switches off | 53.03 | 33.50 | 124 | 6.19 / 8.47 | 42.7 / 24.2 / 133.7 |
| `RSX_VERTEX_ASYNC=0` | 58.59 | 33.38 | 24 | 5.41 / 6.76 | 10.4 / 3.2 / 16.5 |
| no pool/library/prewarm | 59.50 | 17.20 | 8 | 4.05 / 5.10 | 43.6 / 25.5 / 137.6 |

The game's own CPU time per frame is ~5.4 ms quiet and ~8 ms loaded; with
the translation at 2.4-4 ms the frame keeps 4+ ms of slack. The remaining
100-230 ms frames at fight start are the game loading the stage (translation
is small in them). The prewarm needs one earlier session with the same
build; the very first one after a (re)build still builds its pipelines.

Steady-state counters (`RSX_HITCH_LOG=1`, quiet): 0 failed vertex jobs,
0 2D-engine barrier drains, vertex-program memo 94.6% hits, fragment-program
memo 99.7%, every texture placed in the pool (1 heap). Frame dumps of 66
consecutive fight frames: no frame differs from the previous one by more
than 3.9% of its pixels (the fighters moving; median 1.5%), fighters,
stage, reflections, effects, shadows and HUD present in all of them.

## Is the handover wait necessary? (option 4)

Not removable cheaply. Letting the game start frame N+1 as soon as frame N's
command words are copied would keep the commands safe, but not the data they
point at: the SPURS skinning jobs rewrite the fighters' vertex buffers early
in the next frame (on the PS3 that is safe because the RSX has finished by
the time the flip completes), the fragment programs and dynamic textures
live in guest memory, and labels/fences must still be written in command
order. Releasing early therefore needs a snapshot of every buffer the frame
reads, which is the vertex fetch itself. With translation at ~3 ms the
serialisation costs less than the vblank slack, so the wait stays; what was
taken off it is the D3D present (`PS3_PRESENT_LATE`) and the vertex fetch
(now drained only at the flush). Overlapping translation with the game's
*own* frame was tried by the pacing work and fails: the game rewrites and
rewinds commands before its single flush.

## Weaker PCs (patch 0027)

Fights hold 60 fps on the development PC (Ryzen 9 7950X, 32 logical
processors, RTX 3090). Friends will play on 4-8 core PCs with mid-range or
integrated graphics, and online both games run at the slower PC's speed.
Patch 0027 makes the runtime size itself to the processors it may use and
cuts the per-frame CPU work; for weak graphics the launcher had a **3D
resolution** setting (`PS3_RENDER_SCALE`), since patch 0038 the Lower and
Lowest steps of **Internal resolution** (see [Internal
resolution](#internal-resolution-patch-0038-branch-internal-res)).

### What limited a fight at 4-6 logical processors

The game held to N logical processors (affinity mask, below), traced with
`PS3_SCHED_TRACE`:

- **The skinning job list is on the frame's critical path.** Once per fight
  frame the main thread kicks one SPURS job list of ~380 vertex skinning
  jobs and waits for it before it flushes its commands. The jobs are lifted
  SPU code whose float math went through the exact SPU emulation (widen to
  double, truncate, range checks, TwoSum for every multiply-add): ~20 ms of
  CPU per frame. 12 threads finish that in 2.4 ms; the 2 threads a 4-thread
  PC gets needed 10.9 ms (trace median), the flush came after the vblank and
  every frame took 33 ms.
- **The kick itself**: the chain walker ran `VirtualQuery` over the
  384-descriptor list twice per kick -- 1.6 ms from the kick to the first
  job at 4 processors.
- **The SPU sound core** costs ~0.85 of a core whatever the frame rate (a
  5.33 ms audio tick at HIGHEST priority) -- a fifth of a 2-core/4-thread PC.
- **Pools sized from the machine, not the process.** `GetSystemInfo`
  reports every processor, so under an affinity mask (or a job object) the
  SPURS pool started 11 workers on 4 processors; the 3 vertex-fetch workers
  of 0023 were fixed.
- **Busy waiting.** The main thread polls the flip with `usleep(100)` for
  the rest of every frame, and sub-millisecond sleeps were a `SwitchToThread`
  spin: one processor busy all frame (~0.45 of a core). Idle vertex workers
  spin 2,000 `PAUSE`s before they sleep.
- **Per-job overhead**: every job cleared a whole 256 KB local store (~1 ms
  of CPU a frame for 384 jobs) and read three debug variables with `getenv`
  (the CRT's environment lock, taken by every worker for every job).

Not a limit: the translation (3.5-4 ms on the walker), the game's main
thread (7-8 ms busy), the GPU (below).

### What changed

| Change | Switch | Effect |
|---|---|---|
| The render-only skinning images (skin1x/skin4x) are compiled with `SPU_FAST_FLOAT`: host IEEE single-precision ops instead of the exact SPU emulation (fa/fs/fm within 1 ulp, the multiply-adds within 2: `runtime/spu/tests/test_spu_fast_float.c`, 4.6 M lanes). Their output is only drawn: no netplay hash, no rollback state, no game decision reads it; the sound core and every other image stay exact. Screenshots identical to the eye | CMake `-DT5DR_SPU_FAST_SKIN=OFF` | job list at 4 processors 10.9 -> 4.7 ms (trace medians); job workers at 32 processors 0.9 -> 0.5 cores |
| Lifted SPU C gets the lifted PPU code's `-march` (x86-64-v3 when the PC has AVX2) and `-ffp-contract=off`; the exact float path is unchanged (the SPU float/helper/numeric tests pass compiled that way) | `T5DR_LIFTED_ARCH` | sound core ~7 % less CPU (paired runs on two 8-processor halves) |
| Committed-range answers for job lists cached (guest memory is never decommitted) | -- | kick -> first job 1.6 ms -> 0.03 ms |
| CPU budget = the process's affinity mask (`host_sched_cpus()`, printed as `[sched] CPU budget`) | `PS3_CPUS=n` | pools below |
| SPURS job threads: half the budget, max 12 (was half the machine) | `SPURS_JOB_THREADS` | 32: 12 as before; 8: 4; 4: 2 |
| Vertex-fetch workers: 3 from 12 processors, 2 from 8, else 1; idle spin 300 `PAUSE`s below 12 | `RSX_VERTEX_THREADS` | 0 (synchronous) was clearly worse at 4 (37 vs 52 fps) |
| Sub-ms `usleep` on the high-resolution timer below 12 processors | `PS3_SCHED_SUBMS=spin\|pause\|timer` | ~0.45 core less; fps the same within the noise |
| Job local store: only the job's own regions and the context block are cleared (the real job manager clears nothing) | `SPURS_JOB_ZERO_LS=1` | ~1 ms CPU a frame |
| Per-job debug `getenv`s read once | -- | |
| `PS3_RENDER_SCALE=0.25..1` (or 540/360): every live render target below the guest size; multiplies `PS3_RES_SCALE` (patch 0038: an alias of `PS3_INTERNAL_RES`, and below native only the 3D target shrinks) | launcher **3D resolution** (now Internal resolution) | GPU, below |
| GPU time per frame from D3D12 timestamp queries: frame log column `gpu_us`; `RSX_GPU_TIME=1` prints `[gpu-time]` every 600 frames | `RSX_GPU_TIME` | |

From 12 logical processors up every pool default is what it was; the
development PC only gets the cheaper skinning and job overhead.

### How it was measured

The setup, packaged as `tools/fight_bench.py --cpus N`: direct fight
`T5_FIGHT=lil,ask,20,3`, P1 pressing buttons, window minimised, window fight
start +24..42 s (~1,000 frames), fps from the presents, p99 frame time,
per-thread CPU time. The CPU limit is an affinity
mask set on the wrapper right before `CreateProcess`, so the game inherits
it before its pools size themselves: logical processors 0..N-1. On the
7950X processors 2k and 2k+1 are the two threads of one core, so **4 =
2 cores / 4 threads**, 6 = 3c/6t, 8 = 4c/8t; **4c** = processors 0,2,4,6
(4 cores, no SMT). These cores run at ~5 GHz: a PC with the same thread
count and older cores has less headroom than these numbers show.

"Before" is main 0b85c10 (series 0001-0026, 0028, 0029); "after" adds 0027.
(0031 came later: 0027 applies before it unchanged and the series builds;
not re-measured with it.)
Before ran with `SPURS_JOB_THREADS` = N/2, what its `GetSystemInfo` sizing
gives on a real N-thread PC (under the mask it would start 11 workers).
The PC was shared with other agents' builds and games: each run waited for
fewer than 12 busy processors, two rounds interleaved; "other load" is what
other programs used during the window. Under heavy load (25-30 of 32
processors busy) the limited runs of both builds lose 20-25 fps; earlier
runs on the 0024 series under that load are in the commit message, not here.

### Results: single fight

| logical processors | before fps / p99 ms | after fps / p99 ms | frames > 17.5 ms per 1000, before -> after | game CPU (cores), before -> after | other load |
|---|---|---|---|---|---|
| 4 (2c/4t) | 31.8 / 33.6 (33.6, 30.0) | **59.8 / 16.9** (59.8, 59.9) | 891 -> 2 | 2.71 -> 2.45 | 10-13 |
| 4c (4c/4t) | 56.9 / 33.4 (58.8, 54.9) | **59.2 / 25.1** (58.4, 59.9) | 57 -> 13 | 2.82 -> 2.10 | 8-10 |
| 6 (3c/6t) | 59.3 / 25.1 | **59.9 / 16.9** | 10 -> 2 | 3.73 -> 2.27 | 7-8 |
| 8 (4c/8t) | 59.9 / 16.8 | 59.7 / 17.0 | 1 -> 5 | 3.66 -> 2.46 | 6-8 |
| 32 | 59.2 / 25.3 | **59.9 / 16.9** | 12 -> 1 | 3.62 -> 3.15 | 6-7 |

The main thread's wait for the skinning jobs per frame: 4 processors 6.4-9.4
-> 0.7 ms, 6: 4.6 -> 0.4 ms, 32: 0.2 -> 0 ms. At 32 processors the 11 job
workers use 0.9 -> 0.5 of a core and the sound core 0.72 -> 0.66.

### Results: rollback pair at RTT 150 (online default)

`tools/rollback_net_test.py --fight 26,33,20,2 --rtt 150 --jitter 5
--loss 3 --delay 6 --mode1 default --mode2 default --matches 1`: two
instances on this PC through the harness's proxy, the default
configuration (no `T5_RB_MODE`: rollback, input delay 2), one match of two
rounds with the attack scripts, each instance on N logical processors of
its own (the second CCD: 16.. for the host, 24.. for the joiner). fps =
the rollback loop's frames per second over the match, host / joiner.

| logical processors per instance | before fps | after fps | after: rollbacks (re-simulated frames), host / joiner | sync |
|---|---|---|---|---|
| 4 (2c/4t) | 32.7 / 33.1 | **50.1 / 51.0** | 528 / 497 (1,412 / 1,397 of 4,400) | 0 mismatching frames, same result hash both sides |
| 6 (3c/6t) | 31.0 / 31.5 | **48.7 / 49.4** | 516 / 488 (1,401 / 1,350) | same |
| 8 (4c/8t) | 28.7 / 29.0 | **48.4 / 49.2** | 531 / 499 (1,442 / 1,337) | same, host at 3D resolution 0.5 |

The 4- and 8-processor pairs ran with ~20 of the 32 processors busy with
other programs; the 6-processor pairs waited for fewer than 10 (a first
try under load: 31.4 / 31.7 before, 34.4 / 34.8 after), so all of them
are slower than a PC of that size on its own; the rollback agent measured
47-48 fps for this case with all 32 processors on a loaded machine. At the
higher frame rate the same 150 ms span more frames, so each misprediction
re-simulates more of them: ~1,400 instead of 400-800 of the match's 4,400
frames. Rollback at RTT 150 stays the heaviest case: 60 fps there needs a
cheaper re-simulation, not more threads. (The latency branch got there: 60.0 fps window
median on 8 processors per game -- docs/ROLLBACK.md section 29.)

### GPU: 3D resolution

(Patch 0027's measurements. Patch 0038 replaced the setting by Internal
resolution, where Lower and Lowest keep the 1280 x 720 display buffers and
the small targets at full size; its own numbers are in [Internal
resolution](#internal-resolution-patch-0038-branch-internal-res).)

A fight frame draws its 3D pass into a 2048 x 1440 target (2.9 M pixels,
3.2 times the 1280 x 720 output) with a 2048 x 1440 depth buffer, a
512 x 512 shadow map (zeta 0xAF0000, sampled with a depth compare -- the
runtime logs it as `[shadow]`), two 128 x 128 targets and the
1280 x 720 output with the HUD. `PS3_RENDER_SCALE` (launcher: Original 1 /
Lower 0.75 / Lowest 0.5) scales all of them; the present scales the result
to the window. Only host pixels change: the game's memory, commands and
state are the same at any scale, so the two PCs of a match may differ
(checked below).

GPU time per fight frame, RTX 3090, D3D12 timestamps around each frame's
command list (`gpu_us`), ~1,000 steady fight frames per run. An idle 3090
clocks down (the same frame then reads 2-4 ms), so the GPU was kept busy by
two other instances at `PS3_RES_SCALE=4`; their work also lengthens some of
our frames' spans, hence the p10 next to the median:

| 3D resolution | GPU ms per frame, p10 (two runs) | median (two runs) | fps |
|---|---|---|---|
| Original (1) | 1.15 / 0.52 | 1.17 / 0.55 | 59.9 |
| Lower (0.75) | 0.41 / 0.41 | 0.46 / 1.03 | 59.9 |
| Lowest (0.5) | 0.29 / 0.30 | 0.35 / 0.37 | 59.8 |
| for scale: `PS3_RES_SCALE=2` / `3` (earlier runs, others' load) | 0.63-0.87 / 1.17 | | |

So on this GPU a frame is ~0.25 ms of fixed work (840 draws, vertex work,
the shadow pass) plus ~0.3 ms that scales with the pixel count; Lowest cuts
the second part to a quarter. By raw throughput a GTX 1050 is ~20 times
slower than a 3090 and integrated graphics 30-90 times, i.e. roughly 10-50 ms
per frame at Original -- that is where Lower and Lowest decide between 60
and 30 fps (an estimate: not measured on such a GPU). Lowest makes the HUD visibly softer (640 x 360 upscaled).

**No "smaller shadows" option.** The shadow map is a 512 x 512 depth-only
pass (0.26 M pixels, 9 % of the 3D pass's pixels), its cost is mostly the
fighters' vertices, which a smaller map does not reduce, and it already
shrinks with the 3D resolution. A separate scale would need per-surface
scales through the surface copies and depth snapshots of the live renderer
for a gain too small to measure here.

### Netplay with different settings on the two PCs

- Lockstep (`--mode1 off --mode2 off`), host at 3D resolution 0.5, joiner
  at 1, RTT 30 ms, 1 % loss, one match: `sync check through frame 4199: 0
  mismatching` on both sides, the same result hash `d0d12f20ce51b8d2`,
  58 fps.
- Rollback (default), host at 0.5, 8 processors each, RTT 150: 0
  mismatching, the same result hash on both sides (the 8-processor row
  above).
- Every rollback pair in the table, before and after: 0 mismatching frames,
  the same result hash on both PCs, no decode errors, no aborts.

## Input latency (patch 0034, branch `latency`)

How long a press takes to reach the screen, measured end to end, and the
part of it that was ours rather than the game's.

### How it is measured

`tools/latency_test.py` boots a direct fight (Lili vs Asuka, stage 20; P2
idle), taps P1's jab (SQUARE) at a random moment every ~1.2 s and reads the
runtime's latency probe (`PS3_LATENCY_LOG=<file>`, patch 0034,
`runtime/platform/lat_log.h`): every step stamped on the
QueryPerformanceCounter clock, the same clock the script's
`perf_counter_ns()` reads when it writes the pad file.

| event | where |
|---|---|
| press | the script writes `PS3_PAD_FILE` |
| E | the pad layer's 1 ms sampler sees the button go down (tap latch, patch 0025) |
| R | a read hands the title the new buttons (cellPadGetData, or netplay's local sample) |
| B | offline: the main thread reads the pads at the top of its frame (`T5_LATE_INPUT`) |
| F | the title asks for a flip: its frame is simulated and drawn; carries watched guest words (`PS3_LATENCY_WATCH`) |
| X | the FIFO walker reached that flip: translated |
| K | a vblank tick completes the flip: the title's next frame starts |
| P | Present() returned for that flip |
| C | the display's vblank clock as DWM keeps it (last vblank, period) |

The reaction: P1's button-hold counter in the fight block (0x1008F01C: 1, 2,
3 ... while held) names the first frame whose fight logic saw the press; the
move flag 0x10090064 (0x80000000 for one frame) names the frame the jab
starts in. Frame dumps around presses (`--frames`, `LD_FRAME_DUMP_GATE`)
show the jab's first pose in exactly that frame (P1's pixels change 7-9 k ->
30 k against the previous frame: runs/vis1). The game's own delay is one
frame between the two (60 of 60 presses).

`to display vblank` is the next vblank of the display after Present() + 0.5 ms
of GPU copy, from the DWM clock -- a minimised test window cannot show the
picture itself. That is when scanout of the new picture begins in borderless
fullscreen or exclusive fullscreen (independent flip). In a normal window DWM
composes the picture and shows it one refresh later: add 16.7 ms to every
"display" number in a window, before and after alike.

### What was ours

- **The present waited for a vblank tick, then for the display.** A
  translated flip waited for the next tick of the game's 59.94 Hz QPC clock
  (~8 ms on average), and the present then waited for the display's own next
  refresh (another ~half a refresh, wandering with the beat between 59.94 Hz
  and the display's rate) -- the "~1.2 frames" of the frame-pacing notes.
- **The pads were read on another thread.** The game's keyread thread reads
  the pads at the vblank, then waits for the frame lock the main thread holds
  and writes its ring after the main thread took this frame's entry: 5-12 %
  of presses (more on a busy PC) came a frame late.

### What changed

| change | switch (default on) | effect |
|---|---|---|
| A flip is presented as soon as the walker has translated it, not at the next vblank tick; the title still sees it complete on the tick, so the game's pace is unchanged | `PS3_PRESENT_AT_XLAT=0` | present queue 7.7-8.5 -> 0.3 ms |
| **Display lock**: on a 59/60 Hz display with vsync, the vblank ticks follow the display's own vblank clock (DWM). The period is the display's (the game runs at 59.94 or 60.00 Hz, like a PS3 on that TV), the phase is set so a tick comes `lead` before a display vblank; `lead` = the 99th percentile of the last 4 s of tick-to-present times + 1.5 ms (`PS3_DISPLAY_MARGIN_MS`), up at once after two late frames, down 1 ms a second. Presents use sync interval 0 on the flip model without tearing: the newest frame is shown at the next refresh, a late one is replaced instead of queueing a frame of delay | `PS3_DISPLAY_LOCK=0`, `PS3_DISPLAY_LEAD_MS=<ms>` | display wait 9.3-10.6 -> 3.7-4.2 ms |
| The pads are read by the main thread at the top of its frame (the netplay take-over, offline) | `T5_LATE_INPUT=0` | no press a frame late |

Other displays keep patch 0031's 59.94 Hz clock (`[pacing] display lock on`
or nothing in the log): slower displays present without vsync, faster ones
(120/144 Hz) show a frame at the next refresh after it is translated (now
right after translation instead of after the next tick), VRR with
`RSX_PRESENT_MODE=tearing` at once. `RSX_TEST_DISPLAY_HZ` (simulated
displays) turns the lock off. The waitable swap chain (max frame latency 1,
flip model) of patch 0005 stays as it was; under the display lock nothing
queues, so the present does not wait on it.

### Results

Medians in ms, 60 presses per run (58-60 used: the press must land in the
fight with P1 idle), two runs each where two numbers are given. "Before" is the
same build with `PS3_PRESENT_AT_XLAT=0 PS3_DISPLAY_LOCK=0 T5_LATE_INPUT=0` (the
old present path and pad thread), online also with the old rollback settings
(`T5_RB_NET_DELAY=2`, no direct-call cut, no early rollback). Window minimised,
display 59.952 Hz, runs under `build/lat/runs/`; "load" = processors other
programs kept busy.

| part | offline before | offline after | 8 processors, before | 8 processors, after | online RTT 0, before | online RTT 0, after | online RTT 150, before | online RTT 150, after |
|---|---|---|---|---|---|---|---|---|
| runs (load) | LB1, LB2 (14, 10) | LA1, LA2 (14, 14) | L8Bb (5) | L8Ab (2) | PB0b (7) | PA0b (5) | PB150 (18) | PA150 (9) |
| sample (press -> 1 ms sampler) | 1.2 / 1.0 | 1.1 / 1.4 | 1.2 | 1.0 | 1.3 | 1.0 | 1.4 | 1.1 |
| to the frame that reads it (online: + input delay) | 8.8 / 10.2 | 6.3 / 8.8 | 8.4 | 5.7 | 40.5 (2 frames) | 23.2 (1 frame) | 38.0 (2) | 38.8 (2) |
| the game's own frame (input read -> move starts) | 16.7 | 16.7 | 16.7 | 16.7 | 16.7 | 16.7 | 16.7 | 16.7 |
| sim + draw of the reacting frame | 6.4 / 6.0 | 6.5 / 6.3 | 5.7 | 5.3 | 7.1 | 6.4 | 9.1 | 6.9 |
| translation | 2.8 / 2.4 | 2.6 / 2.7 | 2.2 | 2.2 | 2.3 | 2.3 | 2.9 | 2.4 |
| present queue (translated -> Present returned) | 7.7 / 8.5 | **0.3 / 0.3** | 9.1 | **0.2** | 7.5 | **0.3** | 4.9 | **0.3** |
| to the display's vblank | 10.6 / 9.3 | **4.2 / 3.7** | 9.6 | **3.3** | 6.1 | **2.9** | 6.3 | **3.8** |
| **total, press -> display (median)** | **54.4 / 54.9** | **38.3 / 39.7** | **53.5** | **34.3** | **81.2** | **53.6** | **82.0** | **71.1** |
| total, mean / p90 | 54.8, 54.0 / 61.7, 60.9 | 38.7, 40.0 / 46.0, 46.0 | 53.3 / 61.3 | 35.1 / 42.9 | 81.3 / 88.0 | 53.1 / 60.7 | 82.7 / 93.0 | 70.9 / 78.0 |
| presses read a frame late (keyread race) | 6 of 58, 4 of 59 | 0 of 59, 0 of 60 | 5 of 60 | 0 of 59 | -- | -- | -- | -- |

So offline a press now reaches the screen ~16 ms (one frame) sooner: ~2.1-2.4
frames from the press to the start of scanout in fullscreen (34-40 ms), of
which the game's own frame and its simulation/draw are ~1.4 frames and our
translation + present + display wait ~0.4 frame (6.2-6.9 ms; was ~1.2 frames,
19-22 ms). For comparison, a PS3 on a CRT/TV: the press waits for the next
vblank (8.3 ms on average), the game's own frame (16.7), and the frame is shown
at the vblank after it was rendered (16.7) -- ~42 ms plus the TV's own
processing. Online at RTT 0 the input delay is now 1 frame instead of 2 (-27.6
ms in total); at RTT 150 it stays 2 frames (-10.9 ms from the present path).

Display cadence over the presses (offline after): 10 and 12 of 3 396
refreshes showed no new frame under 14 processors of other load, 8 of 3 396
on the quiet 8-processor run; before: 4 and 0 (LB1, LB2) -- the lock trades a
few repeated pictures under load (a frame that misses its lead) for the
lower latency; `lead` keeps that near 0.3 %.

Offline fight speed is unchanged: `tools/fight_bench.py` 59.94 fps with the
simulated 50 Hz and 144 Hz displays of patch 0031 (`RSX_TEST_DISPLAY_HZ`, no
lock), the smoke suite's fps checks at 59.8-59.9 with the lock on.

## Internal resolution (patch 0038, branch `internal-res`)

One setting, like an emulator's: **launcher -> Settings -> Internal
resolution**, `PS3_INTERNAL_RES` for the runtime. It replaces the two knobs
of before: `PS3_RES_SCALE` (patch 0010, higher resolutions, environment only)
and `PS3_RENDER_SCALE` (patch 0027, the launcher's "3D resolution: Original /
Lower / Lowest"). Both names still work: they are read as the same setting
(a factor 0.25-4 or an output height), both set multiply, and
`PS3_INTERNAL_RES` wins over them. The launcher turns a saved "3D
resolution" into the new setting (0.75 -> Lower, 0.5 -> Lowest).

| step | `PS3_INTERNAL_RES` | factor | display buffers (HUD, 2D, movies: the picture) | 3D target (guest 2048 x 1440) | shadow map / glow buffers |
|---|---|---|---|---|---|
| Lowest | `lowest` | 0.5 | 1280 x 720 | 1024 x 720 | 512 / 128 |
| Lower | `lower` | 0.75 | 1280 x 720 | 1536 x 1080 | 512 / 128 |
| **Native** (default) | `native` | 1 | 1280 x 720 | 2048 x 1440 | 512 / 128 |
| 1080p | `1080p` | 1.5 | 1920 x 1080 | 3072 x 2160 | 768 / 192 |
| 1440p | `1440p` | 2 | 2560 x 1440 | 4096 x 2880 | 1024 / 256 |
| 4K | `4k` | 3 | 3840 x 2160 | 6144 x 4320 | 1536 / 384 |

`PS3_INTERNAL_RES` also takes a factor or a height (`900` = 1.25x). The log
names the step (`[display] internal resolution 1440p (2x) from
PS3_INTERNAL_RES: display buffers 2560x1440`), so does the window title.
Render targets take about 80 MB of video memory at Native and 0.7 GB at 4K.

**Default: Native.** The GPU's speed is not known before the game draws, and
the window or monitor size alone would pick 1080p-4K on most screens -- 2.3
to 9 times the 3D pixels. That is nothing for the RTX 3090 (below) but a
frame-rate loss on integrated or older graphics, and online both games run at
the slower PC's speed (the lobby also keeps a PC whose last match ran below
40 fps out of ranked). Native is what every player had before and what
emulators default to; the launcher names the step that matches the player's
screen ("Your screen: 2560 x 1440. In fullscreen, 1440p matches it."), so it
is one click.

### How Tekken 5 DR draws a frame

From the draw CSV (`RSX_DRAW_CSV`), surface dumps (`LD_SURF_DUMP`) and the
dumped fragment programs (`LD_HLSL_DUMP`) of the whole smoke suite (boot,
movies, title, menus, options, gallery, save/delete, character select, all
modes, attract demo) and a direct fight on each of the 18 stages:

- a 512 x 512 shadow map (colour 0x0, zeta 0xAF0000, scissor 1,1-511,511),
  sampled with a depth compare (2x2 PCF in the runtime, texel size from the
  texture itself);
- the 3D pass into a 2048 x 1440 target (0x17F0000, zeta 0x2330000): the game
  supersamples. Each stage uses part of it -- 1536 x 1024 up to 2048 x 1440,
  scissor = viewport (stage 17 1792 x 1440, 18 1536 x 1280, 24 and 27
  1536 x 1024, 20/22/25/31/33 the whole target); menus and character select
  likewise;
- on some stages a glow: the 3D target drawn into two 128 x 128 buffers,
  blurred back and forth, added onto the 3D target (stage 20; see [Stage blur
  and glow](#stage-blur-and-glow-patch-0043-branch-stage-blur));
- one draw that filters the 3D target down into the 1280 x 720 display buffer
  (0x0 / 0x3A0000, zeta 0x740000) -- on stages 24, 26, 28 and 34 a soft focus
  of four taps, elsewhere one tap -- then the HUD, text, menus and movie frames
  on top. Reflections (stages 27, 29, 30) are drawn in the 3D pass itself.

What the usual internal-resolution problems would need, and what this game
does: no surface is multisampled (surface AA mode 0 everywhere -- the
supersampling replaces it) and nothing resolves; no 2D blit copies a live
surface (`[res] 2D blit` never appears: its 2D blits are texture uploads);
no fragment program reads the pixel position (WPOS; 343 programs) or uses
derivatives; all primitives are triangle strips and quads (no lines or
points with a pixel width); every surface the game samples is sampled with
normalized coordinates (rectangle textures are normalized by the guest size);
no zeta is shared between passes of different size. (A CPU read of a render
target would see the same at every step: the live renderer never writes
surfaces back to guest memory.)

### What changed

| change | why |
|---|---|
| One parser for the setting (`rsx_internal_res_scale()`: names, factors, heights, the two aliases), used by the renderer, the window title and the log | one runtime path |
| Every surface and zeta carries its own factor. Above native everything scales. **Below native only targets at least as large as the canvas that are not display buffers shrink** (the 3D target); the display buffers, the shadow map and the glow buffers keep the guest size | at Lower/Lowest the HUD, text and menus stay sharp (the old 0.5 drew them at 640 x 360), shadows look the same, and the game's own downsample still filters the smaller 3D pass; the work that costs GPU time still shrinks |
| A zeta takes the factor of the colour target it is bound with (recreated if a pass of another factor binds it -- never happens here, `outgrown` would say so) | depth and colour of a pass must match |
| Viewport = the target's exact host size; scissor scaled with the target's factor | no sub-pixel rounding at 0.75/1.5 |
| **Fix:** below native the scissor gets one host pixel more to the right and below | the game's downsample samples up to the edge of a 1536 x 1280 viewport; at Lowest a host texel is two guest texels wide and the last bilinear tap reached the cleared black next to it: the right column of the picture was 20 % darker, the bottom row 6 % (stage 18: last column 69 vs 86 -> 84.4 vs 86.2 at Native). The extra pixel gets the scene's own continuation |
| Copies between surfaces (NV3089 1:1 and resolve blits) at each surface's factor; different factors use a filtered draw | stays right if a copy goes from a scaled 3D target into a display buffer (unused by Tekken 5 DR) |
| **Present:** a picture larger than the window is filtered down with n x n bilinear taps (an exact box for 2x and 3x) instead of one tap | 4K in a 1280 x 720 window, or 1440p on a 1080p monitor, is supersampling instead of shimmering |
| The window no longer opens at the `PS3_RES_SCALE` size; Display setting and Windows display scaling decide it | internal resolution and window size are separate, as in an emulator |
| Launcher: "Internal resolution" (6 steps, a cost hint each, the step that matches the screen); Display "Borderless fullscreen" now starts the game's own borderless fullscreen (`PS3_FULLSCREEN=1`) instead of restyling the window from outside | with the outside restyle (by the code) Esc closed the game at once and Alt+Enter twice left a framed window as large as the monitor |
| Test hooks `RSX_TEST_CLIENT_SIZE=WxH` (swap chain as if the client area had that size, while the window stays minimised) and `RSX_TEST_BB_SHOT=<file>` (read back what the window shows, after letterbox and scaling) | fullscreen on 1440p/4K/16:10/21:9 monitors checked without taking the screen |

### Checked at every step

Local evidence under `build/res/` (git-ignored; frame dumps of the game stay
local):

- **Fights, all 18 stages (ids 17-34), every step**: a direct fight (Lili vs
  Asuka, 1 round, `PS3_FIXED_TIME`), five consecutive presented frames in the
  intro close-up (+6 s), with the HUD (+24 s) and while P1 attacks (+30 s),
  every live surface at +31 s (`runs/tour/<step>/s<id>/`, overview sheets
  `runs/tour/all_<step>.png`). Looked at: fighters, faces and self-shadows,
  floor shadows, the reflecting floors of 27/29/30, snow (25), fog (34), the
  sun and glow (20, 33), hit sparks, "READY/FIGHT/FINAL ROUND" overlays, the
  VS splash, subtitles. No step showed anything Native does not.
- **HUD and 2D alignment**: the HUD band of each step's frame scaled to
  1280 x 720 against Native's, by phase correlation: 0.00-0.10 px offset at
  every step (stages whose HUD burst caught the same moment: 9-13 per step).
- **Edges**: the last column/row of the picture against Native per stage:
  within +-5.5 % at every step after the fix (Lowest before: -20 %).
- **Movies, logos, notices**: a boot without input for 75 s at every step
  (`runs/tour/<step>/boot/`): notices, logos, the intro movie with its "PRESS
  START" overlay, the title logo.
- **Menus, character select, stage select, practice, attract demo**: the
  smoke suite's quick tests at every step (`smoke/quick_<step>/`), all PASS
  (fps/audio warnings only, from other games on the PC).
- **Logs** of all 108 stage runs + 6 boots: 0 `[surface-fail]`, 0 D3D
  failures, 0 crashes, 0 zeta re-creations, 0 surface re-sizes.
- **Displays** (`runs/disp/`, `RSX_TEST_CLIENT_SIZE` + `RSX_TEST_BB_SHOT`):
  2560 x 1440 at Native (bilinear 2x up), 1440p (1:1, the plain copy), 4K (2x2
  taps down), Lowest; 3840 x 2160 at Native and 4K (1:1); 1920 x 1080 at 1080p
  (1:1) and 1440p (2x2 taps down); 2560 x 1600 at 1440p: 80-pixel bars top and
  bottom; 3440 x 1440: 440-pixel bars left and right. Windows display scaling
  (`PS3_TEST_DPI`): 120 dpi -> 1600 x 900 client, 144 -> 1920 x 1080 (1:1 with
  1080p), 192 and 288 -> 2227 x 1252 (the 95 % / 90 % work-area limit of this
  2560 x 1440 monitor).

### Speed and GPU time

`tools/fight_bench.py` (direct fight Lili vs Asuka on stage 20 -- the whole
2048 x 1440 target and the glow, the heaviest stage per pixel -- P1 pressing
buttons, window fight start +24..42 s), RTX 3090 / Ryzen 9 7950X, window
minimised. Back to back: for each step the base build (main without 0038,
with the old switch that gave that step) and then the new build with
`PS3_INTERNAL_RES`, 4 rounds interleaved, 47 of 48 runs used. The PC was
shared with other agents' games and builds (16-31 of 32 processors busy,
median 29) and the runs went at below-normal priority, muted, partly while
the owner played Tekken 8: **the fps numbers say nothing about the
resolution** (the base build swung 15-60 fps at the same step; the same
load made a 1080p boot crawl at 1-16 fps with the base build as well as the
new one). GPU time per frame (D3D12 timestamps, frame log `gpu_us`) is the
comparison that holds:

| step | base build (main, no 0038) with | GPU ms per frame, p10: base / new | GPU ms, median: base / new | new: GPU time vs Native (p10 / median) | fps, median of 4: base / new (load-bound, see above) |
|---|---|---|---|---|---|
| Lowest | `PS3_RENDER_SCALE=0.5` | 0.28 / 0.31 | 0.31 / 0.34 | 0.82x / 0.72x | 54.1 / 44.9 |
| Lower | `PS3_RENDER_SCALE=0.75` | 0.33 / 0.34 | 0.35 / 0.36 | 0.91x / 0.76x | 40.2 / 44.2 |
| **Native** | -- | 0.36 / 0.38 | 0.39 / 0.48 | 1.00x / 1.00x | 55.4 / 35.4 |
| 1080p | `PS3_RES_SCALE=1.5` | 0.46 / 0.48 | 0.76 / 0.80 | 1.28x / 1.66x | 32.5 / 41.7 |
| 1440p | `PS3_RES_SCALE=2` | 0.62 / 0.65 | 0.92 / 0.95 | 1.73x / 1.99x | 43.3 / 45.0 |
| 4K | `PS3_RES_SCALE=3` | 1.18 / 1.13 | 1.84 / 1.80 | 3.00x / 3.74x | 53.4 / 41.4 |

- **Cost of each step on this GPU**: 4K takes about 3x Native's GPU time,
  1.1-1.8 ms of a 16.7 ms frame; 1440p ~1.7x, 1080p ~1.3x. A frame is a fixed
  part (840 draws, vertex work, the shadow pass) plus a part that grows with
  the pixels, which is why 9x the pixels cost 3x here; on a GPU 20-50 times
  slower (integrated graphics, a GTX 1050) the pixel part dominates and the
  steps cost close to their pixel ratio (2.25x / 4x / 9x) -- an estimate, not
  measured on such a GPU.
- **Cost of the change**: at the same step the new build needs the same GPU
  time as the old switches within the run-to-run spread (+0.01-0.03 ms at
  Native and below, where the HUD/display buffers now stay at 1280 x 720;
  above native both draw the same pixels).
- **Lowest / Lower** cut the 3D pass to 25 % / 56 % of its pixels. On the
  3090 that is 0.82x / 0.91x of Native's GPU time (the fixed part dominates);
  the old 0.5 drew the HUD at 640 x 360 as well and saved 0.03 ms more.
- One run of the 48 (1080p, new build, during the owner's game) crawled at
  0.4 fps from the logos on and never reached the fight. The same load and
  priority gave 1-16 fps boots with the base build too (two base / new boot
  pairs back to back: base 0.9-16 fps, new 8.9-52 fps); the other three
  1080p bench runs and all 18 tour runs at 1080p completed.
- Earlier, quieter tour runs (normal priority, GPU busy with other games):
  Native 0.3-0.5 ms, Lowest 0.25-0.35 ms, 4K 1.0-2.3 ms per fight frame across
  the 18 stages.
- The smoke suite reads back one frame per second for its checks; at 4K that
  is a 33 MB readback and costs about 10 fps in its menus (title 49 fps at 4K,
  57-58 at Native/Lowest under similar load), which is why its menu fps
  warnings rise with the step. A real session does no readbacks.

### Online with different settings on the two PCs

Only host pixels change, so the two players may choose different steps:

- Rollback (default), host **4K** vs joiner **Lowest**, RTT 50 ms +-5, 3 %
  loss, one match of two rounds (`tools/rollback_net_test.py --fight
  26,33,20,2 --env1 PS3_INTERNAL_RES=4k --env2 PS3_INTERNAL_RES=lowest`):
  `sync through frame 4199: 0 mismatching` on both sides, the same result
  hash `23f0ad06f479ba2f`, 112 / 423 rollbacks (203 / 887 frames
  re-simulated). Again on the build rebased onto main with patch 0035: 0
  mismatching, hash `dcf764875296aa5f` on both sides, 148 / 385 rollbacks
  (361 / 1,428 frames re-simulated). (28-35 fps: the PC ran 12 other games
  and a build, the pair at below-normal priority.)
- Lockstep, host **1440p** vs joiner **Lower**, RTT 30 ms, 1 % loss: 0
  mismatching, the same result hash `93f6b16c9bdd829d` on both sides.

## Stage blur and glow (patch 0043, branch `stage-blur`)

Player report: "Some stages like Ominous Mist have a 'blur' effect on them
which is especially bad when playing with a higher internal resolution. It'd
be nice if we could disable this." Two things came of it: the blur now looks
at every internal resolution as it does at Native (the fix), and **launcher
-> Settings -> Stage blur / glow: On (default) / Off** turns the stages' blur
and glow off (`PS3_STAGE_BLUR=0`).

### What the effect is

Found with draw CSVs, the dumped fragment programs and frame-exact surface
dumps of every stage (ids 17-34; intro and fight). Five stages filter the
picture after the 3D pass; the others, the HUD, the menus and the movies do not:

| stage | effect | draws |
|---|---|---|
| 34 (the misty swamp with the willows; by its look the player's "Ominous Mist"), 24, 26, 28 | soft focus | the downsample of the 3D target (2048 x 1440) into the display buffer reads it four times: a centre tap and three taps 2 guest texels around it (a triangle; the offsets come from vertex constants, in guest texels), weighted 1/16 for the centre and 5/16 for each of the others on stage 34, then a colour curve. The stage scenes behind the title screen and practice mode use the same kind of program |
| 20 (the scrapyard) | glow around the sun | the 3D target averaged with four taps into a 128 x 128 buffer, twelve passes back and forth between two 128 x 128 buffers with four diagonal taps each (a Kawase blur, offsets growing per pass), the result blended onto the 3D target |

The runtime calls such a draw a **filter kernel**: a fragment program that
samples a render-target surface two or more times on one texture unit
(`rsx_fp_texture_tap_mask`). Every other read of a render target in this game
is a single tap (the plain downsample of the other 13 stages, stage 33's heat
haze, which reads the 3D target once at an offset taken from a normal map).

### Why it looked worse above Native

The kernels' offsets are guest texels, and they rely on the bilinear filter:
at Native each tap averages a 2 x 2 texel footprint, so taps 2 texels apart
blend into one soft picture. Patch 0038 scales the render targets, and the
offsets stay where they are in texture space (normalised coordinates, as they
should), but each tap's footprint shrinks with the host texel: at 4K a guest
texel is 3 x 3 host texels, the footprint a third as wide, and the four taps
no longer meet. The picture becomes three or four sharp copies of every edge,
1.25 Native pixels apart -- 3.8 pixels on a 4K screen (1080p 1.9, 1440p 2.5):
a doubled outline on branches, hair and every other edge of the 3D scene. The
glow's Kawase passes, which put each tap on a texel corner, skip host texels
at 1440p and 4K: its buffers came out banded and blotchy instead of smooth.
Not a wrong size or a wrong offset -- the same kernel with too little filter
under each tap.

### The fix

A filter kernel on a scaled surface (above Native) samples a **guest-size
view** of it: the surface box-filtered to its guest size (each guest texel the
area-weighted mean of the host texels it covers -- exact for 1.5x and 3x as
well as 2x), made again only when the surface was written since
(`ld_guest_view_srv`: one extra 3-vertex draw before the kernel's draw records
its state, like the scaled copies of 0038). The taps then cover what they
cover at Native, on a supersampled picture. Single-tap reads keep the full
internal resolution, so every other stage (and the HUD of these five) stays as
sharp as before; below Native nothing changes. The log names every kernel
once: `[stage-blur] filter pso ...: unit 0 reads 0x17F0000 2048x1440 (x3) into
0x0 1280x720: guest-size view`.

### The switch

`PS3_STAGE_BLUR=0` (also `off`, `false`, `no`; the launcher's Off): every tap
of a filter kernel reads the kernel's centre -- the tap nearest the taps' mean
when it is less than half the kernel's radius away (the soft-focus kernel's
centre tap), else the mean (a symmetric kernel). This is an HLSL post-pass on
the decompiled program (`rsx_fp_apply_single_tap`, part of the PSO identity),
so the weights and the colour curve stay and the picture keeps its colours,
only sharp. A draw that blends a **glow buffer** (a surface last drawn by a
filter kernel and smaller than the canvas) onto a full-size target is not
drawn: the sun has no glow. The log says `[display] stage blur/glow: off
(PS3_STAGE_BLUR)` and names the first skipped glow composites. HUD, menus,
movies and the other 13 stages draw exactly as with On.

### Checked

Frame-exact comparisons come from **lockstep pairs** (`tools/rollback_net_test.py
--mode1 off --mode2 off --fight lil,ask,<stage>,1` with `T5_NET_SHOT=300,900,1500`
and `LD_SURF_DUMP`): the two games run the same game frames, so the host at
Native and the joiner at another step (or with Off) dump every surface of the
same frame. Two single offline runs do not show the same picture at the same
fight frame, even with `T5_DF_SHOT=+n` (n frames after FIGHT START): the
camera angle comes from random numbers that depend on timing. Hit sparks and
splashes can differ even within a pair (they are not part of the state the
pair keeps equal), so the comparisons below use idle fighters or leave them out. Local evidence under `build/blur/`
(git-ignored).

"Detail" below is the mean gradient of the 3D picture under the HUD band at the
step's own output size, relative to the Native picture of the same frame
scaled up bilinearly: 1.0 = looks like Native; ghost copies of edges raise it.
Three shots per pair (intro, fight), ranges over the shots:

| stage | step | before (main) | after (0043) |
|---|---|---|---|
| 34 | 1080p | 1.16-1.31 | 1.01-1.06 |
| 34 | 1440p | 1.24-1.45 | 1.07-1.15 |
| 34 | 4K | 1.28-1.53 | 1.03-1.05 |
| 24 | 1080p | 1.17-1.28 | 1.05-1.07 |
| 24 | 1440p | 1.23-1.36 | 1.09-1.13 |
| 24 | 4K | 1.26-1.47 | 1.04-1.06 |
| 26 | 1440p | 1.17-1.29 | 1.10-1.17 |
| 26 | 4K | 1.19-1.36 | 1.05-1.08 |
| 28 | 1440p | 1.42-1.54 | 1.21-1.25 |
| 28 | 4K | 1.42-1.57 | 1.11-1.15 |

Stage 28 keeps more of its own detail through its kernel. Stage 20's glow
buffers, scaled to 128 x 128 and compared with Native's of the same frame
(fighters idle, so no hit sparks differ): 4K before a mean difference of
0.27-0.35 levels, max 9-13, after 0.03-0.05, max 1-2; 1440p before 0.18, max 6,
after 0.24-0.27, max 3 (3 % dimmer on average: the box view of a supersampled
picture against Native's point samples, under a blend that multiplies colour by
alpha); the roughness of the buffer before 1.2-2.1x Native's, after 1.0-1.1x.
To the eye: the doubled branch and hair outlines on stage 34 at 4K are gone
and the soft focus looks like Native's; the glow's banding is gone.

Off: the five stages are sharp (detail Off/On on stage 34: 1.30-1.43 at
Native, 1.65-2.07 at 4K), the colours unchanged, stage 20 without the sun's
glow. Every stage was run On against Off (lockstep pairs, fighters idle, at
Native and at 4K): all 18 render correctly with Off and the HUD is the same;
on the 13 stages without a filter the runtime logs no kernel and draws
exactly as with On (what still differs between the two pictures are the
stages' own animated textures and particles -- waterfalls, fire, steam --
which differ between any two games). Smoke suite: quick PASS at Native (On);
at 4K boot, practice and arcade PASS with On and with Off. (A whole quick run
at 4K with Off, next to 19 other games, missed five of its frame shots --
33 MB readbacks timing out -- and failed on that; the frames it got were
right, and the tests passed again on a quieter PC.)

**Cost:** one box pass per filtered surface and frame (stage 34 at 4K:
6144 x 4320 -> 2048 x 1440, nine loads per guest texel). GPU time per fight
frame (frame log `gpu_us`, median of two runs each, the GPU shared with other
agents' games): stage 34 at 4K 1.80 ms before, 1.43 after, 2.47 Off; stage 20
at 4K 2.11 / 1.71 / 1.83; stage 34 at Native 0.67 / 0.43 -- within the spread
of these runs, nothing measurable.

**Online:** host pixels only -- the patch reads no guest memory and changes no
command, so the two players may choose differently. Rollback pairs (the online
default, `tools/rollback_net_test.py --mode1 default --mode2 default`) with one
side Off, 7 matches of two rounds: stage 34 Native On vs Native Off at RTT 50 ms
/ 3 % loss (2 matches, 850 / 498 rollbacks), stage 20 4K On vs 1440p Off at
RTT 150 ms / 3 % (2 matches, 829 / 505), stages 24, 26 and 28 4K Off vs Native
On at RTT 100 ms / 2 % (3 matches, 482 / 532): 0 mismatching frames and the
same result hash on both sides in every match. All 70 lockstep pair runs above
(Native against 1080p / 1440p / 4K, On against Off): 0 mismatching frames. (The
PC ran 10-19 other games during these runs, at 16-23 fps for the pairs.)

## Laptops, handhelds and 8-core APUs (patch 0047, branch `laptop-perf`)

Two player reports: an HP Omen 15 (2017, i7-7700HQ, GTX 1050/1060 with
Optimus) where "the game goes faster but then goes slow", and a Zen 4 APU
(8 cores / 16 threads, Radeon 780M; first thought a handheld, then a mini PC
at 65 W) at 40-52 fps in fights at 720p, 1080p and 4K alike, menus at 60.
The game's speed is its frame rate (one game frame per vblank, like the
PS3), so both are frames that miss their vblank: the CPU side of a frame
(the game, then the render translation) took longer than 16.7 ms. On a
laptop that happens when heat or the power limit lowers the clock after a
few minutes; on an APU the CPU and the graphics share one power budget; on
8 cores with SMT a busy-waiting thread on the sibling of the main thread or
the walker slows the frame's critical path. In every case the waste around
the game is what to cut: the game's own work stays what it is.

### Where the CPU went

`tools/fight_bench.py` now prints, per thread, the share of one processor,
the CPU time per frame and the context switches per second (a thread that
wakes thousands of times a second keeps its core out of its sleep states;
`--json` has every number, `--polite` mutes the game and starts it at
below-normal priority; a kill-on-close job ends the game if the bench is
killed). Fight Lili vs Asuka on stage 20, P1 pressing buttons. Before patch
0047, all 32 logical processors (spin mode for sub-ms sleeps), 3.1
processors for the game:

| thread | share of one processor | context switches/s | what it was doing |
|---|---|---|---|
| main | 75 % | 11,300 | the game's frame (~5-8 ms), then polling the flip: `while (cellGcmGetFlipStatus()) usleep(100)` (0x34BA30), each usleep a SwitchToThread spin from 12 processors up |
| sound core (`spu`) | 58-66 % | 1,300-2,300 | the SPU sound DSP, 187.5 ticks a second: real work |
| SPURS job threads (11) | 57 % | 3,500 | skinning: ~8 ms of work a frame, ~10 ms with 11 threads |
| vertex-fetch workers (3) | 54 % (with driver threads) | 3,600 | ~2 ms of work a frame, the rest 2,000 `PAUSE`s after every job |
| ticker | 27 % | 850 | vblank clock + render translation (~3-4 ms a frame) + present, and a poll through the last millisecond before every tick |
| pad sampler | 7-9 % | 1,100-1,500 | the 1 ms sampler (with a scripted pad file: a file open per sample; a real pad costs 1-3 %) |
| audio mixer | 1 % | 1,850 | a 250 us timer poll between blocks (20 wake-ups per 5.33 ms block) |

The D3D12 driver is not where it goes: the walker's own CPU time per frame
(frame log `fifo_cpu_us`, thread cycles) was 4.0-4.2 ms rendering on this
PC's integrated Radeon (RDNA2, the 780M's driver family) and 4.0-4.05 ms on
the RTX 3090 (paired runs on the two CCDs, halves swapped); the iGPU's GPU
time was 2.8 ms a frame at Native. Nor the GPU: the same fps at 720p and 4K,
and `[slow-frames]` (below) names the GPU only when the CPU waits for its
fences.

### What changed

| change | for whom | switch |
|---|---|---|
| **The flip wait without the poll**: a usleep under 1 ms right after `cellGcmGetFlipStatus` said WAITING waits for the status to change (WaitOnAddress, woken by the vblank's flip completion), at most 20 ms -- one wake-up a frame instead of 50-100 timer wake-ups, or instead of a processor spinning all frame; the frame starts a few microseconds after its flip instead of up to one poll later. The rollback netcode keeps the plain poll on the main thread (its early rollback looks at the network between two polls: `cellGcm_flip_poll_plain`) | everyone | `PS3_FLIP_WAIT=0` |
| Vblank ticker: a high-resolution waitable timer to the microsecond next to the FIFO kick event; it used to wait whole milliseconds (up to 1 ms late) and then poll the last millisecond (FIFO walk + GCM pump + message pump per round); now it polls the last 250 us, none with power saving. Two `getenv` per loop round went too | everyone | `PS3_TICKER_SPIN_US=n` |
| Audio mixer sleeps until its next block is due; it polls every 250 us only while it waits for a block the game writes late (as before) | everyone | -- |
| Sub-ms sleeps spin (SwitchToThread) only from **24** logical processors up (was 12); 3 vertex workers with 2,000 `PAUSE`s also only from 24, one worker with 300 below (was 3 from 12, 2 from 8: on 16 logical processors two workers cost 0.33-0.37 of a processor and 4,400 wake-ups a second, one 0.19, the walk took the same 3.0-3.6 ms). 8 cores with SMT -- the common gaming CPU -- no longer spin on the siblings of the walker and the main thread | 8-23 logical processors | `PS3_SCHED_SUBMS`, `RSX_VERTEX_THREADS`, `RSX_VERTEX_SPIN` |
| The frame-latency wait before a vsync'd present never runs past the game's next vblank tick (was: up to 20 ms on the ticker, i.e. on the game's clock) | displays that are not 59/60 Hz, VSync on | -- |
| **Power saving** (`PS3_LAPTOP`, launcher **Settings -> Power saving: Auto / On / Off**): sub-ms sleeps on the timer, no ticker poll, one vertex worker with the short spin, at most 6 SPURS job threads, background threads (audio device, PSO writer ...) on EcoQoS. The game, its 60 fps, the 1 ms pad sampling and the tap latch are unchanged | Auto: a battery (laptop, handheld), battery saver or the Power saver plan on, a mobile processor by name (Ryzen ...U/H/HS/HX, Ryzen Z1/Z2/AI, Core ...U/H/HQ/HX/P/Y/G7, Core Ultra, N100 ...), or the renderer on integrated graphics (D3D12 UMA: an APU, whose CPU and GPU share one power budget) | `PS3_LAPTOP=1/0/auto` |
| Display lock (patch 0034): every DWM sample is checked, not only the once-a-second one; a period outside 59.3-60.7 Hz or no clock three samples in a row turns the lock off at once (it used to follow a bad period for up to a second); three such drops in 30 s keep it off for a minute; the tick period is never shorter than 1/60 s | 59/60 Hz displays | `PS3_DISPLAY_LOCK=0` |
| Diagnostics: `[sched] power saving on/off (why)`, `[power]` (AC/battery, plan, processor clock limit), `[gpu] adapter: ... integrated/dedicated`, `[gpu] display: ...` (which adapter drives the window's screen: a laptop with two GPUs copies every frame across, "hybrid present"), every 30 s with slow frames a `[slow-frames]` line (below); the window title says "power saving" | everyone | `PS3_SLOW_FRAMES=0` |

The game never runs faster than 60: its clock is the ticker's (59.94 Hz, or
a 59/60 Hz display's own with the display lock); after a stall the ticker
fires each missed vblank once, which can only lose game time, and the
`[slow-frames]` line reports the clock's rate over the window (`vblank clock
59.94 Hz`, flagged above 60.05). "Faster, then slow" on a laptop is a game
that ran at 60 and then lost frames to heat or the power limit.

On a "59 Hz" display with the display lock, `N of M frames late for their
vblank` counts frames whose release-to-present took longer than the lock's
lead; with the lead at its maximum (16.48 ms) every frame over 16.5 ms is
"late", even one that still makes the next vblank tick. Nearly all frames
late (2,485 of 2,495 in the APU log) is the symptom of a CPU-bound frame,
not a cause: the lock costs no throughput (the guest's flip completes on the
first tick after its translation, with or without it).

### `[slow-frames]`

    [slow-frames] last 30 s: 1381 frames, 495 slow (over 20.9 ms): CPU 479 (game 401, render
    translation 25, vblank thread late 53), GPU 0, present 16; median per frame: game 7.4 ms,
    translation 0.3, GPU wait 0.0, present 0.4; worst 250.1 ms (CPU, game); vblank clock 59.95 Hz |
    on AC power (no battery: a desktop PC), power plan "Ausbalanciert", processor clock limit 4501 of 4501 MHz

A frame is slow when it was shown more than 1.25 vblanks after the one
before. Its reason is what took its time: **CPU, game** (the game's frame
from its release by the vblank to its flip request: game logic, skinning,
command building), **CPU, render translation** (flip request -> the walker
reached the flip), **CPU, vblank thread late** (the tick that released the
frame came more than 2 ms late: the ticker got no processor), **GPU** (the
CPU waited for GPU fences for 30 % of the frame or more) or **present**
(the present call, including the frame-latency wait, took 4 ms or more: a
display path through another GPU, a compositor). The power part is read
each time, so heat or a battery that lowers the clock limit shows up next
to the slow frames. Every 5 minutes without slow frames there is a quiet
line. "Report a problem" puts the last few of these lines, the power
source, plan and power mode, the processor clock limit and Windows' thermal
zone temperatures (where the PC has a sensor Windows reads) into
`system.txt`.

### Two GPUs

Checked on this PC, whose screen hangs off the RTX 3090 and which also has
the 7950X's integrated Radeon: `RSX_ADAPTER=radeon` renders on the iGPU and
every frame is copied to the other GPU for the screen, the hybrid present of
an Optimus laptop the other way round. The log says `[gpu] adapter: AMD
Radeon(TM) Graphics (... integrated) -- RSX_ADAPTER`, `[sched] power saving
on (integrated graphics (AMD Radeon(TM) Graphics) share the processor's
power budget)`, `[gpu] display: the window's screen is driven by NVIDIA
GeForce RTX 3090, the game renders on AMD Radeon(TM) Graphics -- every frame
is copied between the two GPUs`; the display lock stayed on (the DWM clock
is the screen's), present median 0.4 ms, no slow frame classed GPU or
present beyond the load's. The exports `NvOptimusEnablement` /
`AmdPowerXpressRequestHighPerformance` and the high-performance adapter
choice are unchanged; the per-app choice in Windows' Graphics settings still
wins over both.

### Results

Paired runs: two games at the same time on the two CCDs of this PC (logical
processors 0-15 and 16-31, 8 cores with SMT each -- the APU's layout), the
halves swapped for the second round, `tools/fight_bench.py --polite`
(muted, below-normal priority), window fight start +24..42 s. Other agents'
games kept 20-30 of the 32 processors busy all the time, so fps below 60 is
the load's; CPU time and wake-ups per frame are the comparison that holds.
"Before" is the series to 0042 (main 932b1c9), "default" this patch with
power saving off (what a desktop gets), "power saving" with it on.

| logical processors | build | fps | frames > 17.5 ms per 1000 | p99 ms | game CPU (processors) | CPU ms per frame | context switches/s | other load |
|---|---|---|---|---|---|---|---|---|
| 16 (8c/16t) | before | 59.93 | 197 | 19.1 | 3.14 | 52.4 | 13,187 | 19.7 |
| 16 | **default** | 59.96 | 198 | 19.1 | **2.21** | **36.8** | 8,260 | 20.5 |
| 16 | before | 59.37 | 275 | 25.3 | 3.17 | 53.5 | 17,172 | 22.4 |
| 16 | **power saving** | 59.64 | 258 | 20.5 | **2.30** | **38.7** | 8,302 | 23.2 |
| 16, more load | before / default (an earlier build with 2 vertex workers) | 54.1 / **59.3** | 451 / 303 | 28.5 / 26.8 | 2.91 / 2.53 | 53.7 / 42.7 | 19,071 / 11,581 | 25 |
| 4 (2c/4t) | before / power saving | 26.3 / 29.6 | 999 / 996 | 67.4 / 54.0 | 1.58 / 1.64 | 60.2 / 55.8 | 11,260 / 8,029 | 29.7 |
| 4 (2c/4t) | default / power saving | 28.9 / 29.0 | 979 / 981 | 74 / 100 | **1.59 / 1.57** | 55.7 / 54.0 | 8,388 / 8,160 | 29.5 |

On 16 logical processors the game needs 30 % less CPU for the same 60 fps:
the main thread 94 % of a processor (3,700 wake-ups a second) -> 42 % (530),
the vertex workers 60 % (three) -> 18 % (one), the walk the same 3.2-3.7 ms
(`fifo_cpu_us`). On 4 threads -- the "4-core laptop" stand-in -- the game
used 1.57-1.64 of its 4 processors (39-41 %) with power saving off or on,
the frame rate set by the 30 other busy processors; below 8 logical
processors the defaults of patch 0027 already avoided spinning, so there
power saving only saves wake-ups (8,400 -> 8,200 a second) and the patch's
general part the rest (11,300 -> 8,400).

**Input latency** (`tools/latency_test.py --polite`, 30 jab presses each,
before and default side by side on the two halves, swapped): median press ->
display vblank 47.9 -> 43.3 ms (29.5 processors busy) and 38.9 -> 38.4 ms (22
busy); refreshes without a new frame 274 -> 177 and 9 -> 9 of ~1,680. The
flip now releases the main thread a few microseconds after the vblank
instead of after the next poll.

**Online.** Power saving is timing only, so the two PCs of a match may
differ: rollback (default settings, RTT 50 +-5 ms, 3 % loss, host with power
saving, joiner without, 8 logical processors each), one match of two rounds:
sync through frame 4199 0 mismatching on both sides, the same result hash
`02f57cf40b7058e3`, 56 / 525 rollbacks (84 / 2,359 frames re-simulated),
no decode error or abort. Lockstep (RTT 30 ms, 1 % loss, host without,
joiner with): 0 mismatching, the same hash `56c3b7de99c1dee9`.

Not tried: a real laptop, handheld or APU (this PC has none), the game's
fps at such a CPU's own clocks, a battery, a thermal sensor (Windows reports
none here; `system.txt` then says so).

## GPU time on integrated graphics (patch 0051, branch `igpu-perf`)

The 780M player (Zen 4 APU, 65 W mini PC) stayed slower than RPCS3 at 1080p
and 4K after the CPU pass (patch 0047). On an APU the graphics share the
processor's memory, so what costs memory bandwidth and shader time on the GPU
also costs the CPU. This pass measures where the GPU time of a fight goes and
makes the expensive parts cheaper without changing the picture.

### Measuring: GPU time per pass

`RSX_GPU_PASSES=1` puts a GPU timestamp at every boundary of GPU work in a
command list -- a draw pass (render target and zeta bound), a clear, a copy,
the depth snapshot of the shadow map, the stage filter's guest-size view, the
present -- labelled with what starts there, and every 600 frames prints

    [gpu-pass] 600 frames, 21.66 ms GPU per frame in 1.0 lists; per frame: | pass 0x017F0000
    6144x4320 rgba8 z 0x02330000: 15.92 ms (3.0x, 599 draws) | guest view 0x017F0000 2048x1440
    rgba8: 2.42 ms (1.0x) | pass 0x003A0000 3840x2160 rgba8 z 0x00740000: 1.20 ms ...

(no CPU wait: the results are read once their fence has passed; off by
default). Measured on this PC's integrated graphics -- the Ryzen 9 7950X's
Radeon (RDNA2, 2 compute units, the 780M's driver family and memory model,
about a sixth of a 780M's shader throughput) with `RSX_ADAPTER=radeon`, while
the screen hangs off the RTX 3090 -- in a direct fight (Lili vs Asuka, P1
pressing buttons, `tools/fight_bench.py --polite`), the last two 600-frame
windows after FIGHT START. The GPU's own clock moves with its temperature and
the load of the PC (16-31 of 32 processors busy with other agents' games), so
the unchanged 3D pass varies by ~10 % between runs; the column in brackets is
everything but the 3D pass, which is what changed.

Where it went before (ms of GPU per frame):

| stage | step | whole frame | 3D pass (2048 x 1440 x scale^2) | guest-size view (0043) | display buffers (downsample + HUD) | present to a 1280 x 720 window | shadow map + its depth snapshot | glow (stage 20) |
|---|---|---|---|---|---|---|---|---|
| 20 | Native | 2.42 | 1.81 | -- | 0.29 | 0.13 | 0.06 | 0.09 |
| 20 | 1080p | 6.98 | 3.98 | 1.36 | 0.62 | 0.47 | 0.13 | 0.31 |
| 20 | 1440p | 10.13 | 6.58 | 1.43 | 0.99 | 0.43 | 0.23 | 0.36 |
| 20 | 4K | 25.05 | 14.67 | 4.44 | 2.74 | 1.84 | 0.43 | 0.74 |
| 34 | 1080p | 6.60 | 3.99 | 1.26 | 0.68 | 0.43 | 0.13 | -- |
| 34 | 4K | 24.32 | 14.88 | 4.67 | 2.41 | 1.68 | 0.49 | -- |
| 27 | 4K | 21.44 | 18.20 | -- | 1.11 | 1.48 | 0.47 | -- |

- **The 3D pass is 60-85 % of every frame**: the game's own shading of its
  supersampled 2048 x 1440 picture (600 draws), times the scale squared. It is
  what Internal resolution buys; nothing outside the game's shaders makes it
  cheaper without drawing fewer pixels.
- **The guest-size view of patch 0043** (the stage blur and glow kernels read
  the scaled 3D target box-filtered to the PS3's size) was the next item: 19-20 %
  of a 1080p-4K frame on the blur and glow stages. Its loop with per-texel
  bounds and weights was shader-bound, not bandwidth-bound.
- **The present** filters a picture larger than the window with n x n taps
  (patch 0038): 1.5-1.8 ms at 4K into a 1280 x 720 window.
- Small: the shadow map pass and the compute copy of its depth (0.06 ms at
  Native, 0.4-0.5 ms at 4K, where the map is 1536 x 1536), the glow buffers,
  clears (fast clears, 0.01-0.1 ms). The display-buffer passes (the game's
  downsample of the 3D picture plus 14-17 HUD draws) cost their pixels; the HUD's
  overdraw is a few draws. Not there at all in a fight: feedback copies (a draw
  sampling its own target), texture uploads, surface copies.
- Formats: every target of a fight is RGBA8 (no FP16 target is drawn), depth is
  `D32_FLOAT_S8X24` -- on AMD a 32-bit depth plane and a separate stencil plane,
  so a narrower format would save nothing there.

### What changed

| change | picture | switch |
|---|---|---|
| Guest-size view: its own unrolled path per Internal resolution step instead of the loop -- 1.5x (1080p): the loop's 2 x 2 texels and weights in the loop's order; 2x, 3x, 4x: the whole host texels unrolled (bit-identical everywhere), or on AMD pairs of texels with one bilinear tap halfway between their centres: 2x one tap instead of 4, 3x four taps weighted 4:2:2:1 instead of 9, 4x four instead of 16 | identical: max difference 0 on AMD and NVIDIA (below) | `RSX_GVIEW_FAST=0` (the loop) / `1` (unrolled) / `2` (pairs) |
| Present at an exact integer ratio (4K or 1440p internal in a window or screen of a half or a third): the same pairs on AMD -- 2x one tap instead of 4, 3x four instead of 9, 4x four instead of 16. Any other ratio, and other GPUs: the n x n taps as before | identical on AMD at 2x and 3x; 4x within one level in 0.005 % of the pixels | `RSX_PRESENT_FAST=1/0` |
| **With power saving** (patch 0047; on by itself on integrated graphics): above native, targets smaller than the canvas -- the 512 x 512 shadow map and the 128 x 128 glow buffers -- keep their guest size, as they do below native; the glow then needs no guest-size view | shadow edges as at Native; glow as at Native | `RSX_SMALL_TARGETS_NATIVE=1/0` |
| `RSX_GPU_PASSES=1` per-pass timestamps; `RSX_FAST_SELFCHECK=1` makes every guest-size view and the present twice from the same input at a frame-exact surface dump (`LD_SURF_DUMP`), the new path and the old, and writes both; the surface dump also writes the frame's backbuffer | -- | -- |

Bilinear pairs are exact in arithmetic (tests/test_igpu_filters.py checks every
tap layout against the box on random textures) and were bit-identical on AMD's
texture units, but NVIDIA's rounded 0.1-4.5 % of the pixels one level
differently (max 1 of 255), so the pairs are AMD's default and other GPUs get
the unrolled loads, which do the loop's arithmetic.

**Same picture.** `RSX_FAST_SELFCHECK=1` in fights on stages 20 and 34 at
1080p, 1440p and 4K (into 1280 x 720 and 960 x 540 windows: present ratios 1.5,
2, 3 and 4), every guest-size view of the frame (3D target, display buffers,
glow buffers, shadow map) and the backbuffer, new path against old on the same
input: **max difference 0, SSIM 1.000000** in every image, on the integrated
Radeon (pairs) and on the RTX 3090 (unrolled loads). Smoke quick passes.

### Results

The same runs after the change (power saving off: what a desktop GPU gets; and
the default on integrated graphics, where power saving turns itself on), ms of
GPU per frame, everything but the 3D pass in brackets:

| stage | step | before | after, power saving off | after, integrated graphics default (power saving on) |
|---|---|---|---|---|
| 20 | 1080p | 6.98 (3.00) | 6.47 (2.68) | 5.98 (2.28) |
| 20 | 1440p | 10.13 (3.41) | 10.00 (2.82) | 9.20 (2.37) |
| 20 | 4K | 25.05 (10.18) | 22.19 (6.91) | 21.66 (5.74) |
| 34 | 1080p | 6.60 (2.61) | 6.30 (2.32) | 5.53 (2.17) |
| 34 | 1440p | 9.75 (3.08) | 9.86 (2.33) | 8.63 (2.17) |
| 34 | 4K | 24.32 (9.22) | 19.25 (5.50) | 19.35 (4.71) |
| 27 | 1440p | 8.08 (0.90) | 7.37 (0.92) | 7.97 (0.70) |
| 27 | 4K | 21.44 (3.02) | (load-bound run) | 18.38 (1.31) |
| 20 / 34 / 27 | Native | 2.42 / 2.43 / 2.35 | (no change: nothing is scaled) | 2.63 / 2.45 / 2.35 |

Per pass at 4K: the guest-size view 4.4-4.7 -> 1.7-2.4 ms, the present into a
1280 x 720 window 1.5-1.8 -> 0.4-0.7 ms, with power saving the shadow map and
its snapshot 0.4-0.5 -> 0.06 ms and the glow 0.74 -> 0.10 ms. At 1440p the view
1.3-1.4 -> 0.6-0.9 ms and the present 0.4 -> 0.2-0.3 ms; at 1080p the view
1.3 -> 1.0 ms. Everything around the 3D pass now costs 17-40 % less GPU time
at 1440p and 4K (30-49 % with power saving), the whole frame 8-21 % at 4K.

**What this means for a 780M.** Its 12 RDNA3 compute units do about six times
this GPU's work, so a fight frame takes it roughly 0.4 ms at Native, 1 ms at
1080p, 1.5 ms at 1440p and 3.5 ms at 4K (estimated from these runs, not
measured on a 780M): the GPU was not what held that PC below 60 -- the CPU side
was (patch 0047). What this pass saves there is memory traffic the GPU no longer
puts on the shared bus at 1440p and 4K. For integrated graphics Native or 1080p
stays the sensible step.

**Online**: host pixels only, nothing the game reads changes, so the two PCs
of a match may differ. Rollback pair (default settings, one match of two rounds), host at 4K on the RTX 3090 with per-pass timestamps and the AMD paths forced on (`RSX_GVIEW_FAST=2 RSX_PRESENT_FAST=1`), joiner at 1080p with power saving (shadow map and glow at guest size), the joiner's game suspended for 60 ms every 0.2-0.6 s (`--stutter 60`: deep rollbacks), a direct connection (after this PC's restart the test proxy got no replies from the games): sync through frame 4199 0 mismatching on both sides, the same result hash `40ab59479a3c405c`, 158 / 277 rollbacks (605 / 1,474 frames re-simulated), no decode error or abort. Before the restart a pair through the proxy (RTT 50 ms, 3 % loss) with the joiner rendering on the integrated Radeon at 1440p stayed in sync through frame 2999 (0 mismatching) before the overloaded PC slowed the host to 1-2 fps.

**A GPU hang on the integrated Radeon, not this patch.** After this PC was
restarted, with 16-18 other games running and only 3.6 of its 31 GB free, a
game rendering on the integrated Radeon at 1080p stopped twice with
`DXGI_ERROR_DEVICE_HUNG` near the title screen. DRED (`[dred]` lines in the
log) puts both hangs in one of the game's own command lists, at its first
clear (`last=0`: not even the clear finished) or among its indexed draws
(`last=8`), neither one of this patch's passes (those are non-indexed draws and
copies at the end of a frame). An A/B on that GPU at 1080p, same build, same
load, interleaved, two games at a time at below-normal priority, boot -> title
-> direct fight -> 40 s of fighting, stages 20 and 26:

| build | runs | reached the fight | hung | other games running | free memory |
|---|---|---|---|---|---|
| 0051, every path off (`RSX_GVIEW_FAST=0 RSX_PRESENT_FAST=0 RSX_SMALL_TARGETS_NATIVE=0`) | 24 | 24 | 0 | 3-10 | 9.0-15.7 GB |
| 0051, default | 24 | 24 | 0 | 2-10 | 9.3-17.3 GB |
| main without 0051 | 24 | 24 | 0 | 1-10 | 9.4-17.1 GB |

So the hang did not come back in 72 runs, with or without the patch; with
the GPU stopping at a frame's first clear under heavy memory pressure it looks
like the integrated GPU's memory being paged out by Windows, not anything the
game draws. `RSX_GVIEW_FAST=0 RSX_PRESENT_FAST=0 RSX_SMALL_TARGETS_NATIVE=0`
still turns every change of this patch off.

## Late frames shown when ready (patch 0059, branch `weakpc-fps`)

Why some players had 40-50 fps, and whether a Vulkan renderer would help:
[WEAK_PC.md](WEAK_PC.md). In short: the limit is the speed of the core that
runs the game's main thread, and a frame whose game part ran past its vblank
used to wait for the next one (33.4 ms for a frame of 18-20). Now the first
tick a frame misses waits for it, up to one period, and fires as soon as the
walker has translated the frame (`PS3_LATE_FLIP=0` = the old way): a slowed
game went from 40 to 49-50 fps and from 30 to 43-44 fps, a rollback pair with
one slow PC from 32 to 46 fps, in sync; a 60 fps PC is unchanged. The D3D12
calls are 0.7-1.0 ms of a frame (frame log columns `ph_desc_us`,
`ph_cbcopy_us`, `ph_api_us`, `ph_post_us`), the same on NVIDIA and on the
integrated Radeon.

## 4K on integrated graphics (patch 0063, branch `igpu-4k-stall`)

Player report on 1.1.2: an AMD Radeon 780M mini PC (Zen 4, 8 cores / 16
threads, on AC), a 1920 x 1080 screen at 59 Hz, Internal resolution **4K** in
every run. Fights at 32-38 fps in borderless fullscreen, 40-47 in a large
window and 43-57 in a 1280 x 720 window -- "much higher even though the
internal resolution was unchanged". Power saving Auto or Off "made no
difference". The `[slow-frames]` lines of the fights:

| run (player's logs) | fps | median per frame: game / translation / GPU wait / present ms | slow frames classed GPU |
|---|---|---|---|
| borderless 1920 x 1080 | 32-38 | 13.8-15.9 / 4.6-5.2 / 0.0 / 0.6-0.9 | 24-199 of ~1,000 |
| borderless (second run) | 32-40 | 14.4-14.5 / 4.9-5.2 / 0.0 / 0.7-0.8 | 55-94 |
| window 1848 x 1040 | 40-47 | 13.2-13.3 / 5.0-5.1 / 0.0 / 0.9-1.0 | 0 |
| window 1280 x 720 | 43-57 | 11.1-11.3 / 3.6-3.9 / 0.0 / 1.0-1.3 | 0-54 |

In menus the same runs had a game part of 2.6-3.9 ms. On this PC a fight's
game part is 5-6 ms (a quiet 7950X), so the question was: does the game's main
thread wait for the GPU inside its "game" part, which `[slow-frames]` would
then wrongly call CPU?

### Where the game thread waits: nowhere on the GPU

What Tekken 5 DR's main thread does in a frame (`PS3_SCHED_TRACE`, every
main-thread syscall and HLE call over 20 us, against the release and flip
times of the frame log; `build/igpu4k/scripts/trace_frames.py`):

- release (the vblank tick completes the flip and the GCM pump runs the flip
  and user-command handlers) -> the main thread takes the semaphore the user
  handler posted (already posted: 0.0x ms) -> game logic, the skinning job
  chain kick (~5.5 ms after release on this PC) -> it waits for the skinning
  (1.3 ms of SPURS jobs) and the draw request manager thread (a cond and an
  lwmutex) -> `cellGcmSetUserCommand` + `SetFlip`: the frame's commands are
  flushed and the walker starts translating them;
- the FIFO walker does **not** run during the game part: the game flushes its
  frame once, at the end. Labels, the back-end semaphore, `GET_REPORT` and the
  reference register are written by the walker when it walks them (on the
  CPU, not after the GPU), the flip completes on the vblank after the walker
  reached it -- no readback, no fence wait, no label poll in the game part;
- the main thread's blocked time inside the game part is **0.4-0.6 ms a
  frame** (cond wait 0.25-0.28, lwmutex 0.17-0.21, the user-command semaphore
  0.06), NVIDIA 4K and integrated Radeon 1440p alike; the rest of the game part
  it runs.

Only one wait in the whole frame depends on the GPU: with one command
allocator the walker could record nothing of frame N+1 until the GPU had
finished frame N (`ld_begin_recording`). That shows as **translation** and
`GPU wait`, and `[slow-frames]` already classes those frames GPU -- on this
PC's 2-CU Radeon at 4K it is 12-18 ms of a 28-31 ms frame. On the player's PC
`GPU wait` was 0.0 in the median: the GPU was not slower than the game part,
the game part itself was long.

### What makes the game part long on an APU

The game part is the main thread's own CPU work (and its helper threads'),
running while the GPU draws the previous frame. On integrated graphics the
GPU and the processor share one memory and one power budget, so a busy GPU
slows the processor's work. Measured on this PC: two games at once on the two
halves of the 7950X (game A on logical processors 0-15 = 8 cores / 16 threads,
the player's layout, NVIDIA, Native), game B on 16-31 either rendering 4K on
the integrated Radeon (GPU busy 83-86 %) or Native on the NVIDIA (60 fps, more
CPU work than the 35 fps iGPU game). Game A's processor time per frame
(`fight_bench.py`), two interleaved rounds:

| neighbour on the other CCD | A's main thread ms/frame | A's walker (ticker) ms/frame | other load |
|---|---|---|---|
| integrated Radeon at 4K (round 1 / 2) | 8.27 / 9.93 | 4.46 / 5.23 | 20.6 / 26.8 |
| NVIDIA at Native (round 1 / 2) | 7.35 / 8.24 | 4.22 / 4.89 | 18.4 / 27.1 |

+12-21 % on the main thread, +5-7 % on the walker, from a 2-CU GPU working
next door, while the processors' clock stayed at 4.6 GHz (`processors at ...`
in `[slow-frames]`). The 780M has six times the compute units on the same
kind of memory; at 4K -- whose 3D pass in this game is **6144 x 4320**, the
supersampled 2048 x 1440 target times three -- it can take far more of the
memory's bandwidth, and its 65 W are shared with the cores. That is the most
likely reading of the 780M's long game part (no 780M here to measure it on):
the game's own work, slowed by the GPU's load, not a wait. It would also
explain the window sizes: whatever the output costs the GPU (the downscale,
the compositor) adds to that load. The player's logs agree: `GPU wait` 0.0 in the median but up to
199 GPU-classed frames per 30 s, i.e. the GPU needed about as long as the
whole CPU frame.

### Recording the next frame while the GPU draws: slower on integrated graphics

The one real stall (the walker waiting for the GPU before it records) can be
removed: patch 0063 gives the renderer **two frames in flight** --
`RSX_FRAMES_IN_FLIGHT=2`: two command allocators, two sets of upload, vertex,
index and constant rings and of the shader-visible descriptor rings; a slot
is waited for only when it comes round again, retired textures move with
their slot, everything else the CPU writes for the GPU already rotated
(present descriptors per backbuffer, the overlay's 8 slots). Nothing the guest
sees changes (labels, reports, flips stay walker-time). On the integrated
Radeon at 4K, interleaved A/B, `RSX_GPU_PASSES=1`:

| ms of GPU per frame | one frame in flight | two frames in flight |
|---|---|---|
| 3D pass 6144 x 4320 | 15.8-16.5 | 18.0-18.2 |
| guest-size view (stage filter) | 1.84-1.96 | 4.20-4.25 |
| display buffers 3840 x 2160 (each of two) | 1.22-1.29 | 2.52-2.54 |
| shadow map pass | 0.36-0.39 | 1.29-1.33 |
| whole frame | 23.5-24.5 | 31.7-32.0 |
| fps | 34.8 / 37.5 | 31.0 / 31.8 |

The overlap saves the 4 ms the GPU used to idle, and the walker's work (texture
hashing, vertex decoding into the upload rings, constant copies) now runs
while the GPU draws -- on one memory that costs the GPU 8 ms a frame. So the
default stays one frame in flight (`RSX_FRAMES_IN_FLIGHT=2` is there for a
discrete GPU slower than the game, where there is no shared memory; not
measured: this PC's RTX 3090 is never the limit). The frame-latency queue
stays at 1.

### Present and composition

The swap chain is flip model (`FLIP_DISCARD`, two buffers, frame-latency
waitable, max latency 1, tearing flag where Windows has it) at exactly the
client area's size, resized with the window; in borderless fullscreen that is
the monitor's size, which is what Windows needs for independent flip (no
desktop composition). A picture larger than the window goes through one
downscale pass, patch 0051's bilinear pairs on AMD (2x: one tap per pixel,
3x: four): 1.5 ms at 4K into 1920 x 1080 on the 2-CU Radeon, essentially one
read of the 33 MB 4K picture -- it cannot get much cheaper without a smaller
picture. Not checked
here: whether the 780M's borderless window really got independent flip (this
PC's screen hangs off the RTX 3090, and test windows stay minimised).

### What changed (patch 0063 + launcher)

| change | why | switch |
|---|---|---|
| `[slow-frames]` splits the game part: `game part 14.1 ms on average: main thread running 13.5, waiting for the renderer 0.0, for other game threads 0.6 (its processor time 12.9 ms a frame)` -- every blocking lv2 call and the flip wait time themselves on the main thread (one thread-local test elsewhere), counted only between the release and the flip request; a semaphore posted from a GCM handler, or a sleep while the walker has commands left (a label/fence poll), is a wait for the renderer | the 780M log said "CPU, game" and could not say whether that was work or waiting. A renderer wait inside the game part now counts as GPU for the slow frame | -- |
| `GPU busy 17.2 ms a frame (62 % of the time, integrated graphics)`: GPU timestamps (two per command list, read after their fence: no wait) are on by default | GPU time without `PS3_FRAMELOG` | `RSX_GPU_TIME=0` |
| `processors at 3.42 GHz on average (76 % of their 4.50)` (PDH "% Processor Performance", English counter names) | on an APU the clock drops while the GPU is busy; the old "clock limit" only says what the power plan allows | `PS3_CLOCK_SAMPLE=0` |
| verdict at the end of the line: `GPU-bound: the graphics need 22.9 ms a frame ...` (GPU busy >= 85 % or most slow frames GPU) or `integrated graphics busy 64 % of the time: they share the processor's power and memory ...` (>= 50 %); a present that blocked while the GPU was >= 85 % busy is a GPU frame | the launcher and the problem report read it | -- |
| `PS3_INTERNAL_RES=auto`: the step that matches the window's screen, at most 1080p on integrated graphics (`[display] internal resolution 1080p (1.5x) from PS3_INTERNAL_RES=auto (screen 2560x1440, integrated graphics: at most 1080p)`) | a choice for the launcher's Auto | -- |
| `RSX_FRAMES_IN_FLIGHT=2` (above) | off by default | `RSX_FRAMES_IN_FLIGHT` |
| `power saving off (PS3_LAPTOP=0: launcher Settings -> Power saving Off, or a PS3_LAPTOP line in its extra settings or in Windows' environment)` | the player's four logs all said `PS3_LAPTOP=0` although Auto was tried | -- |
| Launcher: Power saving **Auto** is sent as `PS3_LAPTOP=auto` (was: nothing), so a variable left in Windows' environment cannot overrule it; Settings names an Extra-settings line that does (`Extra settings below set PS3_LAPTOP=0: that wins over this choice.`) | the launcher itself was right (Auto = unset); the game got `=0` from Off, the Extra settings box or the environment | -- |
| Launcher: Internal resolution **Auto (matches the screen)** -- a seventh choice, Native stays the default; with Auto the Settings hint says what it picks on this PC | the owner decides whether it becomes the default | -- |
| Launcher: on integrated graphics (from the last game log's `[gpu] adapter`), a step larger than the screen gets `4K (3x) on integrated graphics: try 1080p (1.5x) for 60 fps.`; after a game whose log says GPU-bound / integrated graphics busy, the Play tab says so | the 780M player's case | -- |
| Problem report: `system.txt` gets "What the log says about speed" (GPU-bound windows, integrated graphics busy, Internal resolution above the screen on integrated graphics); `[slow-frames]` lines are kept whole (1,800 characters) | -- | -- |

### Results

`tools/fight_bench.py --polite` (Lili vs Asuka, stage 20 -- the heaviest per
pixel, P1 pressing buttons, window fight start +24..42 s), Internal resolution
4K, `PS3_LAPTOP=0` as in the player's logs, the swap chain as for a 1920 x 1080
borderless window or a 1280 x 720 window (`RSX_TEST_CLIENT_SIZE`; the game
window minimised). "Before" is main (1.1.2's runtime, 0001..0053), "after"
this branch (0051 + 0059 + 0063). Other agents' games and builds kept 19-30 of
the 32 processors busy, so the CPU-bound NVIDIA numbers move with that load;
the iGPU runs are GPU-bound. Medians per frame over the last 15 s:

| GPU, picture | build | fps | game part ms | translation ms (GPU wait) | GPU ms per frame | other load |
|---|---|---|---|---|---|---|
| integrated Radeon, 4K into 1920 x 1080 | before | 30.1-32.5 (4 runs) | 7.4-8.4 | 17.1-21.7 (12.3-17.9) | 26.6-27.6 | 21-29 |
| integrated Radeon, 4K into 1920 x 1080 | after | 33.6-35.3 (3 runs; a 4th at 24.5 under 30 of 32 busy) | 8.5-13.7 | 15.3-19.3 (10.4-15.5) | 24.0-24.3 | 20-29 |
| integrated Radeon, 4K into 1280 x 720 | before | 25.4-25.5 | 8.6-9.4 | 21.5-27.4 (16.9-23.0) | 34.3-34.7 | 26-30 |
| integrated Radeon, 4K into 1280 x 720 | after | 28.3-28.5 | 10.8-14.3 | 20.2-24.0 (15.3-19.4) | 30.0-30.4 | 26-29 |
| integrated Radeon, 4K, power saving on (Auto on an APU) | after | 25.0 | 11.7 | 14.3 (9.8) | 22.7 | 28 |
| integrated Radeon, **Auto** (-> 1080p), power saving on | after | **59.7** | 9.3 | 3.9 (0.0) | **6.4** | 24 |
| integrated Radeon, 1080p | before | 50.1 | 11.2 | 4.3 (0.0) | 7.7 | 27 |
| RTX 3090, 4K into 1920 x 1080 | before | 57.3-59.9 (5 runs) | 8.3-10.2 | 4.1-4.8 | 1.5-2.1 | 20-29 |
| RTX 3090, 4K into 1920 x 1080 | after | 54.2-59.9 (5 runs; 24.8 once at 30 of 32 busy) | 8.3-12.4 | 4.2-5.1 | 1.2-1.6 | 19-30 |

- On this 2-CU Radeon 4K is GPU-bound in both builds; after: 9-12 % less GPU
  time per frame (0051's cheaper filters) and 9-12 % more fps. The 4K -> 720p
  window costs this GPU more than 4K -> 1080p (30 vs 24 ms); on the player's
  780M the 720p window was the fastest -- not reproduced here.
- **What helps an APU at 4K is a smaller picture**: Auto (1080p on integrated
  graphics) runs the same fight at 59.7 fps with 6.4 ms of GPU per frame.
- RTX 3090: unchanged within the load's noise (pairs at the same load: 59.9 /
  59.8, 58.0 / 57.3); the main thread's processor time per frame is the same
  in both builds (8.2 / 7.8, 9.0 / 8.9 ms), so the wait accounting costs
  nothing measurable.
- The new line on the integrated Radeon at 4K (one window): `game part 9.1 ms
  on average: main thread running 8.6, waiting for the renderer 0.0, for
  other game threads 0.6 (its processor time 8.3 ms a frame); GPU busy 22.9 ms a frame (84 % of
  the time, integrated graphics) ... | GPU-bound: the graphics need 22.9 ms a
  frame (integrated graphics) -- a lower Internal resolution is what helps`.

**Online and the picture.** Only timing and host pixels change, so the two PCs of a match
may differ. Rollback pair (RTT 50 +-5 ms, 3 % loss, delay 1, one match of two rounds, Lili vs
Asuka on stage 20): host on the RTX 3090 at 4K with two frames in flight, joiner on the
integrated Radeon with Auto (-> 1080p) and power saving: `sync through frame 6599: 0
mismatching` on both sides, the same result hash `6921d865e3a4381f`, 57.2 fps (an earlier
build of the branch: 0 mismatching, hash `dcb35942ae7c6184`). Lockstep pair, both on the RTX
3090 at Native, host two frames in flight, joiner one, frame-exact surface dumps at netplay
frames 300/900/1500 (`T5_NET_SHOT` + `LD_SURF_DUMP`): the shadow maps identical, the 3D target
and the display buffers different only in the background crowd and the water splashes -- a
control pair with the same settings on both sides differs there as well (those effects are
not part of the state a pair keeps equal). The default, one frame in flight, records the same
commands as before; patch 0063 adds two timestamps to each command list. Smoke quick: PASS
(80 checks; 3 fps WARN from the other games on the PC).
## Translation CPU (patch 0062, branch `xlat-cpu`)

The weak-PC study ([WEAK_PC.md](WEAK_PC.md)) left the render translation at
2.2-3.8 ms of every fight frame, on the frame's critical path, with the D3D12
calls 0.7-1.0 ms of it. Patch 0062 cuts the translation by about a quarter and
the D3D12 recording by half, without changing a pixel.

### Who waits for whom

| thread | per fight frame |
|---|---|
| main (the game) | the frame's logic, the skinning job list (on the SPURS workers), the command buffer; then **one** flush (`put`) and the flip request, then it waits for the flip |
| ticker | the vblank clock; walks the command stream from that flush to the flip marker and records the D3D12 command list: the **translation**; the flip completes at the tick (at once for a late frame, 0059); after the flip handlers, submit and Present |
| rsx-vertex (1-3) | each draw's vertex fetch and decode, handed over by the walker; drained before the submit |

Game and translation are in series by design: once its flip completed the
game may rewrite its vertex buffers, textures and programs ("Is the handover
wait necessary?" above). Nothing else serializes them: the walker's CPU time
per frame is the translation's wall time (median 2.14 vs 2.23 ms, frame log
`fifo_cpu_us` and `xlat_us`), so the walker does nothing before the frame's
single flush and never waits inside the translation (the vertex workers keep
up; submit and Present come after the flip, off the critical path). The
threading stays as it is; the lever is the walker's own CPU per frame.

### Where the walker's time went

ETW/WPR needs an administrator, so `tools/thread_profile.py` samples the
ticker thread itself: 2,000 times a second it suspends the thread, reads its
instruction pointer and the top of its stack, and resumes it; samples in a
kernel wait are left out; addresses map to functions through the linker map,
or to source lines with a build that has a PDB (`llvm-symbolizer
--inlining`, see the tool). Fight Lili vs Asuka on stage 20, frame log on;
share of the ticker's busy samples before the patch:

| where | share |
|---|---|
| FIFO walk and method dispatch (`gcm_rsx_process_fifo_unlocked`, `rsx_dispatch_method_block`, `rsx_live_draw_method_block`, `gcm_io2ea`): the stream is mostly short method blocks -- 47 % of them one word, 44 % four (the vertex program, re-uploaded for every draw, one instruction per block) -- each walked, looked up and branched per word | 27 % |
| display driver (`nvwgf2umx.dll`), D3D12 runtime and kernel submit: 14 state calls and one 16-descriptor table copy per draw (11,650 and 830 a frame), plus ~40 heap-start queries a draw | 24 % |
| byte-wise FNV over ~170 bytes a draw for the PSO key and 192 bytes for a diagnostic descriptor signature | 7.5 % |
| texture mutation hash (126 textures, 3.7 MB a frame, read from memory) | 7.4 % |
| `QueryPerformanceCounter` (the frame log's phase timers: both builds pay it in every number below) | 4.6 % |
| vertex job hand-off (`ld_vjob_submit`) | 4.6 % |
| vertex-constant block copies (8 KB a draw when the constants changed) | 2.9 % |
| everything else in a draw: layout, texture and sampler slots, surfaces, pixel constants | ~22 % |

### What changed

| change | switch (default on) | effect |
|---|---|---|
| **D3D12 state only when it changes.** The draw remembers what the open command list has bound (descriptor heaps, root signature, PSO, root CBVs, descriptor tables, render targets, viewport, scissor, stencil reference, topology, vertex and index buffer views) and records only what differs. Forgotten at every command-list reset and right before every other pass that records pipeline state on the list (surface copies, depth snapshots, the stage-blur guest-size view, the present copy, the training overlay) | `RSX_STATE_CACHE=0` | state calls 11,650 -> ~1,900 a frame |
| **Descriptor tables reused.** A draw whose 16 texture slots equal those of a table already in the descriptor ring gets that table again (a 64-entry memo by slots), as long as nothing was written into the CPU-side SRV heap since (a refreshed texture or a re-made surface keeps its slot but gets a new descriptor; every such write bumps a generation) and the ring did not start over. The sampler table checks the previous call's table first. The heaps' start handles are read once | `RSX_STATE_CACHE=0` | table copies 830 -> ~170 a frame |
| **One vertex and one index buffer view for the whole ring.** A draw's vertices start at a multiple of their stride in the upload ring (a few bytes of padding), so one view per stride serves every draw through `BaseVertexLocation`, and one index view through `StartIndexLocation` | `RSX_RING_VIEWS=0` | view calls 1,660 -> ~30 a frame |
| Pixel-constant block reused when the next draw's constants and alpha reference are the same bytes | `RSX_STATE_CACHE=0` | |
| The sampled render targets' transitions in one `ResourceBarrier` call each way (was one call per surface) | -- | |
| **PSO key memo.** The key stays the byte-wise FNV it was, so the PSO cache, the pipeline library and the prewarm file keep their names; its inputs are first looked up in a 256-entry memo and compared in full | `RSX_STATE_CACHE=0` | PSO lookup phase 0.25-0.30 -> 0.12-0.15 ms |
| The recent-draw ring's descriptor signature (diagnostics only) is a word hash instead of byte-wise FNV | -- | |
| **Span dispatch.** A block of incrementing words that all land in registers of one kind (plain state, the transform program window, the transform constant window) is handled as one span: exactly the register stores, write counts and program and constant updates the per-word loop made (`tests/c/xlat_dispatch_test.c` compares both on random streams), without its table lookup and branches per word; a one-word state block is two stores | `RSX_DISPATCH_SPANS=0` | |
| **Header runs in the FIFO walker.** After a method block the fast path takes the next headers itself while each is another plain subchannel-0 block within one IO page and carries no method the walker acts on (reference, labels, reports, semaphores): the same bookkeeping per header as the loop's top (budget, ring position, trace ring), without its flip, branch and probe checks | `PS3_GCM_HEADER_RUN=0` | |
| A locked compare-exchange per draw for two debug flags is a plain load; the draw-CSV hook returns at once without `RSX_DRAW_CSV` | -- | |
| `[xlat-stats]` lines next to `[render-stats]` (`RSX_HITCH_LOG=1`): per frame the draws, state calls made and skipped (by kind), tables copied and reused, PSO key memo hits, textures hashed and their megabytes | -- | |

Nothing here reads or writes guest memory differently, and no command is
skipped: the GPU receives the same draws with the same bound state.

### Results

Paired runs: the old build (series to 0059, `weakpc-fps`) and the new one at
the same time, one on each CCD half (logical processors 0-15 / 16-31, 8 cores
with SMT each), halves swapped for the second repetition;
`tools/fight_bench.py --polite`, direct fight Lili vs Asuka, P1 attacking,
window fight start +24..42 s (~1,070 frames), frame log medians and p99 per
run, mean of the two runs. Other programs kept 14-30 of the 32 processors busy
(the absolute numbers are higher than on a quiet PC, which is why the pairs
run side by side); stage 27 ran below 60 fps in its loaded repetition in both
builds.

| stage, internal resolution | walker CPU per frame, median: before -> after | p99 | D3D12 recording, median | p99 | submit / Present call (both builds) |
|---|---|---|---|---|---|
| 20 (scrapyard, 835 draws), Native | 3.19 -> 2.56 ms (-20 %) | 5.16 -> 4.32 | 0.78 -> 0.43 (-45 %) | 1.24 -> 0.75 | 0.13-0.14 / 0.23-0.25 |
| 20, 1080p | 3.66 -> 2.63 (-28 %) | 4.95 -> 3.87 | 0.90 -> 0.45 (-51 %) | 1.24 -> 0.64 | 0.14-0.16 / 0.25-0.28 |
| 27 (550 draws), Native | 3.43 -> 2.73 (-20 %) | 4.66 -> 4.02 | 0.73 -> 0.36 (-51 %) | 1.04 -> 0.53 | 0.20-0.22 / 0.33-0.34 |
| 27, 1080p | 2.99 -> 2.29 (-23 %) | 3.99 -> 3.25 | 0.72 -> 0.34 (-53 %) | 1.10 -> 0.52 | 0.17 / 0.30-0.31 |
| 34 (misty swamp, 745 draws), Native | 3.18 -> 2.46 (-23 %) | 4.05 -> 3.31 | 0.79 -> 0.40 (-50 %) | 1.04 -> 0.55 | 0.12-0.13 / 0.22-0.23 |
| 34, 1080p | 2.95 -> 2.15 (-27 %) | 4.02 -> 3.14 | 0.73 -> 0.34 (-53 %) | 1.09 -> 0.53 | 0.11 / 0.20 |
| **all** | **3.23 -> 2.47 ms (-24 %)** | **4.47 -> 3.65 (-18 %)** | **0.78 -> 0.39 (-50 %)** | **1.12 -> 0.59 (-48 %)** | 0.15 / 0.27 |

Each of the 12 pairs: walker CPU 0.69-0.89x, D3D12 recording 0.45-0.62x of
the old build's. The translation's wall time (`xlat_us`) fell the same:
3.21 -> 2.44 ms median, 5.06 -> 3.75 ms p99. The ticker thread's whole CPU
time per frame (walk, vblank clock, submit, Present; thread times, not the
frame log) 3.92 -> 3.15 ms. Submit (one `ExecuteCommandLists`) and the
Present call are per frame, not per draw, and stay as they were. The internal
resolution does not change the CPU side (the same draws).

On the weak-PC stand-ins of [WEAK_PC.md](WEAK_PC.md) a translation of
2.3-3.8 ms becomes ~1.8-2.9 ms: 0.5-0.9 ms more of every frame for the game
part, about what a 3-5 % faster core would give.

### Same picture

Lockstep pairs (`tools/rollback_net_test.py --mode1 off --mode2 off --fight
<p1>,<p2>,<stage>,1`): the old build as host and the new one as joiner run the
same game frames, and at lockstep frames 300, 900 and 1500 both dump every live
surface (`T5_NET_SHOT` with `LD_SURF_DUMP`: the two display buffers, the 3D
target, the shadow map, the glow buffers), compared byte for byte. Stages 20,
27 and 34 at Native and 1080p, Lili vs Asuka and Jack-5 vs Bryan; 34 old/new
pairs and 12 controls (old/old, new/new). Two things differ between any two
games, whatever their builds: the stages' animated parts (puddles on 20, the
background waterfall of 27, the water and mist of 34) follow a counter of the
frames each game ran since it started, which differs by 1-40 frames when one
loaded faster; and Lili's ribbon (cloth the game simulates outside the state a
match keeps equal) and the odd splash.

- **Pairs whose counters matched: every surface byte-identical** -- stage 27
  1080p and stage 34 1080p (12 of 12 surfaces each), stage 20 Native (all but
  Lili's ribbon in two shots; the ribbon also differed in 2 of 4 old/old
  pairs); with intermediate builds of this patch also stage 20 Native (18 of
  18) and stage 27 Native (12 of 12).
- Pairs whose counters differed: fighters (but Lili's ribbon), HUD, shadow map
  and glow buffers identical; the animated stage parts differ as they do in
  old/old pairs.
- A new/new pair with matching counters: identical but for one splash.

All 46 pairs stayed in lockstep sync (0 mismatching frames).

### Online

The patch changes only how the host draws, never guest memory or the command
stream, so the two players may run either build: a rollback pair, old build as
host, new one as joiner, RTT 150 ms +-5, 3 % loss, one match of two rounds
(`tools/rollback_net_test.py --fight 26,33,20,2 --mode1 default --mode2
default`): sync through frame 4199 with 0 mismatching frames on both sides,
the same result hash `a1f87325795b0036`, 576 / 553 rollbacks, no decode error
or abort. The 46 lockstep pairs above: 0 mismatching frames.

Also checked: smoke quick PASS on the new build (two fps WARNs from the other
games on the PC), `tests/` (709 OK, with `tests/test_xlat_cpu.py`: the span
dispatch against the per-word loop on 200,000 random blocks; three
deliberately broken copies of the span code all failed it), the whole series
applies in name order on a fresh tree (`tools/prepare_ps3recomp.py`).

### What is left

- The texture mutation hash: ~0.2 ms a frame (126 textures, 3.7 MB read from
  memory every frame; memory-bound, a faster hash would not help). Only
  knowing which guest pages were written would; Windows' write watch belongs
  to the rollback.
- The display driver: ~0.4 ms in the ~2,700 calls a frame that remain (830
  draws and the state that really changes: vertex constants ~520, PSO ~275,
  descriptor tables ~890).
- The command walk: ~0.5 ms for tens of thousands of short method blocks a
  frame, now a few nanoseconds each.
- The frame log's own phase timers (`PS3_FRAMELOG`) cost ~0.15 ms of every
  number above, in both builds; a player's game does not run them.
## The game thread's own time (patch 0061, branch `game-thread-cpu`)

[WEAK_PC.md](WEAK_PC.md) found that one core's speed limits the players at
40-50 fps: the game's main thread needs 5-6 ms per fight frame here and
8-10 ms on slow or shared cores, and a frame is that plus the translation.
This branch is the main thread's own time: the lifted code and the runtime
services it calls every frame (the build -- PGO/LTO -- and the translation
are other branches).

### How it was measured

- **A sampling profiler that needs no admin rights**: the runtime's own
  `PS3_HOST_PROF=<file>`, extended. `PS3_HOST_PROF_WHO=main` samples only the
  threads whose name contains `main` (the game's main thread),
  `PS3_HOST_PROF_DEPTH=48` keeps each sample's whole host stack (x64 unwind
  tables), `PS3_HOST_PROF_AT=a,b` is the window in seconds after start,
  `PS3_HOST_PROF_US` the period (1 ms). `tools/host_prof.py PROFILE --map
  t5dr.map [--busy] [--focus NAME --callers]` gives self and inclusive time
  per function (a lifted function is `func_<guest address>`), the samples by
  kind (lifted code, guest memory helpers, indirect calls, HLE calls, lv2
  syscalls, netplay/rollback, system calls) and, for a sample stopped in a
  system DLL, the export it stopped in and the runtime function that called
  it. `--busy` leaves out the samples blocked in a wait.
- **Per displayed frame**: `PS3_GAME_THREAD_LOG=<file>` writes one line per
  flip request of the game; `tools/game_thread_times.py` turns it into the
  main thread's CPU time per frame (its thread cycles between two flip
  requests: the frame's work, re-simulated frames and snapshots included,
  waits left out) and the game part in wall time (the frame's release -> its
  flip request), median, p90, p99. `tools/fight_bench.py` sets it and prints
  the bench window's numbers.

The fight is `tools/fight_bench.py`'s (Lili vs Asuka, stage 20, P1 pressing
buttons, window fight start +20..60 s). Other agents' builds and games kept
8-31 of the 32 processors busy during the work, so single runs move by 10-20 %;
before/after numbers are paired runs (both games at the same time on the two
CCD halves, swapped every round), shares of a profile are within one run.

### Where the main thread's time went

Offline fight, 16 logical processors, series to 0059. The main thread was
busy ~5.4 ms of each 16.7 ms frame (the rest it waits for its flip):

| what | share of the busy time | ms per frame |
|---|---|---|
| lifted code (the game) | 58 % | 3.1 |
| **lwmutex lock/unlock: two kernel calls per pair even when the lock was free** (`NtWaitForSingleObject` with a zero timeout, `NtReleaseSemaphore`: the lwmutex was a kernel semaphore) | **32 %** | **1.7** |
| VMX float helpers (`vmx_vmaddfp`, `vmx_vaddfp`, ... out of line) | 5 % | 0.27 |
| HLE dispatch (`ps3_hle_call`): a scan of every registered handler per call, with an out-of-line `std::atomic` load per entry; the GCM pump's three locked instructions; the breadcrumb lookup | 2.5 % (8.7 % once the lwmutex calls were gone) | 0.14 |
| indirect calls (`ps3_indirect_call`, the fast path) | 1.7 % | 0.09 |
| everything else (lv2 syscalls, out-of-line guest memory, timers) | < 1 % | |

The lifted code's profile is flat: the 30 hottest functions together are a
quarter of the busy time (share of the busy time before -> with 0061; the
shares grow as the total shrinks):

| function (guest address) | before | 0061 | function | before | 0061 | function | before | 0061 |
|---|---|---|---|---|---|---|---|---|
| 0x355C70 | 3.8 % | 4.6 % | 0x36A758 | 0.8 % | 0.9 % | 0x1551B0 | 0.6 % | 1.0 % |
| 0x355B34 | 2.2 % | 3.1 % | 0x36A7C8 | 0.7 % | 0.9 % | 0x397AF8 | 0.5 % | 0.5 % |
| 0x36AFB8 | 1.8 % | 2.3 % | 0x3A6A40 | 0.7 % | 0.8 % | 0x391728 | 0.5 % | 1.0 % |
| 0x35375C | 1.6 % | 2.1 % | 0x391A4C | 0.7 % | 0.8 % | 0x36991C | 0.5 % | 0.5 % |
| 0x3ADEC4 | 1.5 % | 2.5 % | 0x36A9E0 | 0.7 % | 0.6 % | 0x283CD0 | 0.5 % | 0.9 % |
| 0x07CB14 | 1.4 % | 1.2 % | 0x3524C4 | 0.7 % | 0.7 % | 0x35C230 | 0.5 % | 0.8 % |
| 0x36A8F4 | 0.9 % | 0.9 % | 0x0C5044 | 0.6 % | 0.5 % | 0x369430 | 0.4 % | 0.5 % |
| 0x3520D0 | 0.9 % | 1.1 % | 0x2B29A0 | 0.4 % | 0.5 % | 0x36AE60 | 0.4 % | 0.6 % |
| 0x354160 | 0.9 % | 1.4 % | 0x3694E8 | 0.4 % | 0.3 % | 0x351EBC | 0.4 % | 0.7 % |
| 0x3596C4 | 0.8 % | 1.0 % | 0x0F66CC | 0.4 % | 0.5 % | 0x389788 | 0.4 % | 0.3 % |

The top ones are the draw packet writers (`0x355C70` and `0x355B34`, the
16-byte packet moves: byte loops with the guest registers in memory and two
reservation-bitmap checks per store), the draw-list append `0x354160`, and
the vector math around `0x36A758`..`0x36AFB8`; by subtree the fighters' model
draw (`0x387324`, 15 %) and the scene update (`0x10BD8`, 18 %).

Online (rollback, the default, at RTT 100 ms, 8 logical processors each),
on top of that:

| what | share of the busy time | |
|---|---|---|
| **indirect calls on the full path**: the rollback layer installs `ps3_icall_hook` for the session, and with a hook every indirect call took `ps3_indirect_call_impl` -- a dozen environment probes and the uncached 3 MB hash lookup | **7 %** (5.5 % in it, 1.3 % in the hook) | |
| rollback snapshots (`state_commit`) | 11-12 % | 0.49-0.60 ms per commit, ~2.2 commits per frame, 160-330 pages (0.6-1.3 MB) each; of a commit 0.27-0.35 ms is `GetWriteWatch` (the kernel's walk over the 105 MB state, 27,000 pages, and its TLB shootdowns: 0.14 ms with no other thread running, 0.27 ms with six, in a stand-alone test; one call or seven, with or without a separate reset: the same) and 0.17-0.27 ms the two page copies. About 90 % of it is the early commit, which runs while the frame waits for its translation; the commit at the frame boundary, on the critical path, is ~0.08 ms per frame |
| state hashes | 0.1 % | the gameplay hash (`rb::state_game_hash`, ~25 KB) ~7 us per frame |
| re-simulation | | 1.7-2.2 ms per re-simulated frame, 0.2-0.4 ms per displayed frame on average at RTT 100 |

### What changed (ps3recomp patch 0061)

| change | switch | effect |
|---|---|---|
| **lwmutex without a kernel call while it is free** (`runtime/ppu/ppu_lwm_fast.h`): an atomic word per lwmutex; a locker that finds it held sleeps on a condition variable; an unlock with waiters hands the lock to one of them (it stays locked, as the semaphore's release to a waiting thread did and as the PS3's kernel does). Any thread may unlock, a timed-out lock takes nothing, unlocking a free lock leaves it free -- as before. The guest's owner/recursion words are written as before | `PS3_LWM_FAST=0` | the 32 % above (1.7 ms of kernel calls per frame here), and the same on every thread that takes lwmutexes (the draw thread, the sound threads) |
| **The indirect-call fast path with a hook installed**: the hook is consulted there, with the same target, at the same point and with the same one-shot bypass as on the full path (which now only sees unregistered or null targets and the diagnostics) | `PS3_ICALL_HOOK_FAST=0` | the 7 % of the online busy time above |
| HLE dispatch: the registered handlers by index (rebuilt when one is added; the first registration of a NID still wins), the GCM pump returns at once when nothing is pending, the call-site memo of the breadcrumb 64 -> 1024 entries | -- | HLE dispatch 8.7 % -> 3.6 % of the busy time |
| `-mcx16` for the runtime and `src/` (CMake, clang only): the MSVC STL gives every `<atomic>` function `target("cx16")`, and clang never inlines a function with target features its caller lacks -- every `std::atomic` load, store and compare-exchange in the runtime was an out-of-line call. Every x64 CPU Windows 10/11 runs on has CMPXCHG16B. The lifted code keeps its options | -- | the calls become the instructions they wrap |
| Profiler: `PS3_HOST_PROF_WHO=<name>`, `PS3_HOST_PROF_DEPTH`, `PS3_HOST_PROF_US`; `PS3_GAME_THREAD_LOG` | off unless set | measurements only |

Tried and left out: forcing the VMX float helpers inline made the functions
that use them slower (13.8 % -> 16.2 % of the busy time; register pressure in
the large lifted functions). The lifter is unchanged: the hot lifted loops
(guest registers kept in `ctx`, two reservation-bitmap checks per store) would
need register promotion and alias information, not a clearly safe change.
The snapshot's copies could be halved (a shadow of page pointers), but nine
tenths of them run in the flip wait already, and `GetWriteWatch`'s cost is
the kernel's, the same for every call shape.

Nothing here changes what the game computes: no lifted code, no guest-visible
value, no floating point; the lwmutex keeps mutual exclusion and hands a
contended lock on in turn, only faster when nobody waits.

### Results

Per displayed frame, the game's main thread, ms. "CPU" is its thread time
(its own work), "game part" the wall time from the frame's release to its
flip request (what the frame's translation waits for: the work plus the
waits for the draw thread and the skinning jobs). Paired runs, the two
builds at the same time, swapped every round; "before" is the series to 0059
with the measuring tools only, "0061" the final build. Ranges are the
rounds, the value in brackets their median.

Offline fight, 8 logical processors each (4 cores / 8 threads, the two
halves of the second CCD), 4 rounds, 12-17 other processors busy:

| | before | 0061 |
|---|---|---|
| CPU, median | 6.11-7.32 (6.27) | **4.52-5.49 (4.56)** |
| CPU, p99 | 7.31-8.94 (8.07) | **5.73-6.88 (6.06)** |
| game part, median | 6.21-8.40 (6.56) | **5.48-7.49 (5.64)** |
| game part, p99 | 8.64-13.57 (9.95) | **7.58-12.93 (8.87)** |
| draw thread CPU (`NU::Draw::RequestManager`) | 3.0-3.5 | 2.7-3.1 |

On 16 logical processors (8 rounds, 14-24 other processors busy) the CPU
median went 5.98-8.07 (7.2) -> 4.87-6.19 (5.7). The game part gains less
than the CPU: with its own work done sooner, the main thread waits longer for
the draw thread (`sys_cond_wait`, 0.37 -> 0.56 ms per frame) -- that thread
is the next limit (lifted code, 92 % of its time).

Online, rollback (the default) at RTT 100 ms +-5, 3 % loss, one match per
run, host and joiner on 8 logical processors each, 2 rounds (host / joiner
values together), 17-23 other processors busy:

| | before | 0061 |
|---|---|---|
| CPU, median | 9.04-10.77 | **5.95-6.70** |
| CPU, p99 | 17.8-20.1 | **11.9-13.7** |
| game part, median | 8.8-11.9 | **6.5-7.3** |
| game part, p99 | 17.9-22.4 | **12.6-14.9** |
| displayed frame time, p99 | 24.9-29.7 | **22.6-23.1** |
| match fps | 54.9-58.0 | **57.5-58.8** |

A slower PC by the test hooks of patch 0059 (+10 ms game, +2 ms
translation, 8 logical processors, offline): 41.8 -> 44.0 fps. That stand-in
adds a fixed 10 ms, so it understates the gain: on a core half as fast, the
kernel calls and the dispatch overhead that are gone took twice as long.

### Same game

Nothing of what the game computes changed, and two PCs with and without
0061 play each other. Proof (`tools/rollback_net_test.py`, three matches per
run: Asuka vs Lili stage 20, then Lili vs Dragunov stage 24 and its rematch;
RTT 100 / 3 % loss for rollback, RTT 30 / 1 % loss for lockstep):

| pair (host / joiner) | mode | frames compared per side | result |
|---|---|---|---|
| 0061 / 0061 (twice) | rollback | 16,200 | 0 mismatching frames, the same three result hashes on both PCs |
| 0061 / 0061 (twice) | lockstep | 16,200 | the same |
| 0061 / main (twice), main / 0061 | rollback | 16,200 | the same |
| 0061 / main, main / 0061 (twice) | lockstep | 16,200 | the same |

"main" is main's own build (series to 0053, its CMake) from the same lift.
Of each "twice", one run used the build before the lock moved into its own
header (the same code).
The rollback runs had 450-1,870 rollbacks per side (up to 7,378 re-simulated
frames). The online measurements above were in sync too. Smoke quick PASS
(one fps WARN under load in practice-select, as before), `tests/` OK,
`tests/test_lwm_fast.py` runs the lock's own stress test (8 threads, every
lock path, hand-over, timeouts, unlock by another thread).

### What is left

The main thread is now ~83 % lifted code. Its profile is flat (the 30
hottest functions are a third of the busy time); the biggest single items are the
draw packet writers and the out-of-line VMX helpers (7 %). Online, the
snapshots (11-12 % of the busy time, nine tenths of it in the flip wait) and
re-simulation (1.7-2.2 ms per re-simulated frame) remain; hashing is under
0.1 ms a frame in both modes (lockstep: the netplay frame start, hash
included, ~10 us). The draw thread's wait is the next step for the game
part.
## SPU side on weak PCs (patch 0064, branch `spu-perf`)

Players on 4-core / 4-thread laptops (i5-7300HQ) see ~40 fps in fights.
The game's SPU work runs as lifted SPU code on host threads: the **sound
core** (`bnuscore`, one thread, a 5.33 ms tick 187.5 times a second) and the
SPURS **skinning jobs** (`skin1x`/`skin4x`, ~390 jobs per fight frame on the
walker `spurs-chain` and the `spurs-job` workers, then the small `jcsignal`
job that wakes the game). Before this patch, on 4 logical processors, that
was ~47 % of all the game's CPU time: the sound core alone took 60-65 % of a
processor -- more than the game's main thread (~45 %) -- and the skinning
~9 ms of CPU per frame.

### Where the time went

Measured with `tools/thread_sampler.py` (new: samples a thread's
instruction pointer and resolves it with `llvm-symbolizer` against an exe
built with line tables, inlined helpers included), `SPU_PROF=1` (new, below)
and a `PS3_SCHED_TRACE`:

- **Sound core**: half of its time in the SPU_NEAR_FLOAT float ops
  (`spu_fa`/`fs`/`fm`/`fma`, ~22 instructions per operation for the SPU's
  zero and extended-range rules); ~8 % in the two hooks every transfer
  between lifted functions called (`yz_lockstep_tick`,
  `spu_task_launch_check`: calls and env-cached switches); the local-store
  accessors' debug hook (one load and a branch, but a call the compiler cannot
  see into, so the register file was reloaded from memory after every
  local-store access); a debug scan of every DMA PUT for a crash in another
  title (`POISON-DMA`).
- **Skinning jobs**: `spu_rotqby` was a quarter of a job -- on x86 the byte
  rotates, shifts and the `cwd` family were scalar byte loops of 90-200
  instructions; every job ends in a halt, and MSVC's `longjmp` unwinds the
  frames it skips (~0.8 us of a ~25 us job); the POISON scan.
- **The game waiting**: the main thread kicks the chain, works ~3.5 ms, then
  blocks until the list is done. On 4 processors it blocked on ~60 % of
  fight frames, 1.3 ms at the median, 2.8 ms at p90, its processor idle
  meanwhile. The SPU threads themselves sleep properly (no spinning: the
  sound core waits on its event queue, the job threads on events/condition
  variables); kick -> first job 0.03-0.5 ms.

### What changed

| change | switch | effect |
|---|---|---|
| x86 forms of the byte permutes: `rotqby`, `rotqbyi`, `shlqby`, `shlqbyi`, `rotqbybi`, `shlqbybi`, `rotqmby`, `rotqmbyi`, `rotqmbybi` are one `pshufb` with an index built from the SPU byte arithmetic; `cbd/chd/cwd/cdd` and the x forms a compare + blend; `fsm/fsmh/fsmb` a compare; `shufb` without its three byte swaps (16 -> 6 instructions) | compile-time (`SPU_SCALAR_HELPERS` = the loops) | skinning job ~25 -> ~10 us |
| SPU_NEAR_FLOAT ops in about half the instructions: exponent tests on `abs(x)` as signed compares; no test of the operands for exponent 255 (an Inf/NaN operand always gives an Inf/NaN result, which sends the vector to the exact path as before); the exact path a cold call that returns in a register | -- | sound core -30 % |
| Lifted images are compiled with `SPU_LS_NO_HOOKS`: no debug hooks in `spu_ls_read128/write128` (the runtime's own accessors keep them) | CMake / `build_game_dll.py` define | the compiler keeps SPU registers in host registers across loads |
| The per-transfer hooks inline: with none of their diagnostics armed they are the stack-reset check (only with entries registered), the step count and the LS-0 job end | `SPU_LOCKSTEP`, `SPU_EXITTRACE`, ... arm the old path | sound core ~-8 % |
| The halt landing pad's `longjmp` does not unwind (the jmp_buf's Frame set to 0; the unwinding jump stays when user shadow stacks (CET) are on) | `PS3_SPU_HALT_UNWIND=1` | ~0.8 us per job |
| The POISON-DMA scan of every PUT is off | `SPU_POISON_DMA=1` | ~3 % of a job |
| **The waiting PPU thread runs jobs**: a thread about to block in `sys_event_queue_receive` on a queue SPURS attached first takes jobs from the open job list, like one more worker, and blocks only for the jobs still running elsewhere; a batch is opened without workers too (2-3 processors) | `SPURS_JOB_HELP=0` | on 4 processors the main thread ran ~3 jobs per frame and blocked 0.00-0.01 ms (was 0.65-1.2 ms per frame) |
| Diagnostics: `SPU_PROF=1` (per job binary jobs/time per walk, list wall time, kick -> start, the waiting thread's jobs and blocked time, every 600 walks), `SPURS_JOB_HASH=1` (FNV hash of every byte the jobs PUT, one `[spu-hash]` line per walk), `SPU_SELFCHECK` (compile the lifted SPU code with it: every rewritten helper also runs the code it replaced and counts differences) | off | -- |

Thread counts are unchanged (they come from 0027/0047: on 4 processors the
walker and one worker, 8 job threads from 16); with the waiting game thread
helping, a third thread takes jobs exactly when the game would otherwise sit
idle. Priorities unchanged.

### Results

Paired runs, `tools/fight_bench.py --polite` (Lili vs Asuka, stage 20,
window fight start +24..42 s), before = main's series plus the `SPU_PROF`/
`SPURS_JOB_HASH` instrumentation with `SPURS_JOB_HELP=0`, after = 0064,
started together on two halves (4 processors: 8-11 / 12-15, 16: 0-15 /
16-31), the halves swapped every round. Other agents' games kept 16-26
processors busy, so the fps are this PC under load -- a weaker PC -- not a
quiet 7950X. Median (range) over the rounds:

| | runs | fps | frames > 17.5 ms per 1000 | p99 ms | game CPU ms per frame | sound core: share of a processor (ms per 5.33 ms tick) | skinning: CPU ms per frame (threads) | main thread ms per frame |
|---|---|---|---|---|---|---|---|---|
| 4 processors, before | 4 | 38.5 (37.3-45.1) | 893 | 37.6 | 47.5 | 64 % (3.39) | 8.79 (2) | 8.8 |
| 4 processors, after | 4 | **55.6** (46.9-57.4) | 378 | 32.6 | **31.5** | **36 %** (1.92) | **3.32** (2) | 8.8 |
| 4, power saving (`PS3_LAPTOP=1`), before | 2 | 50.4 (41.5-59.2) | 525 | 34.0 | 43.1 | 58 % (3.10) | 9.24 (2) | 8.4 |
| 4, power saving, after | 2 | **58.0** (57.1-58.8) | 330 | 30.5 | **30.9** | **35 %** (1.86) | **3.22** (2) | 8.3 |
| 16 processors, before | 2 | 59.96 | 182 | 19.0 | 35.7 | 52 % (2.78) | 8.84 (8) | 6.9 |
| 16 processors, after | 2 | 59.95 | 185 | 18.9 | **28.6** | **33 %** (1.76) | **3.93** (8) | 7.3 |

**The pool stage (stage id 30: the poolside with the crowd dancing round the
pool; a player on a 4-core i5-7300HQ laptop: "55-60 fps, but on stages with
lots of 3D models like the pool stage it drops considerably").** The crowd is
skinned in the same job list: ~420 jobs a fight frame against ~390 on stage
20, so 7 % more skinning, and the list ran longer than the game's own work
before it waited -- on 4 processors it blocked 1.0-1.6 ms a frame (2.3 ms in
one earlier run) where stage 20 blocked 0.65-1.2. Same paired setup, `--fight
lil,ask,30,3`, 27-30 other processors busy (so these fps are a much weaker
PC than this one):

| pool stage, 4 processors | runs | fps | frames > 17.5 ms per 1000 | p99 ms | game CPU ms per frame | sound core | skinning CPU ms per frame | skinning job (us) | list wall time | game thread blocked per frame |
|---|---|---|---|---|---|---|---|---|---|---|
| before | 4 + 2 | 31.9 (20.8-42.2); 37.4 with `SPU_PROF` | 975; 903 | 53.4; 44.3 | 55.1; 48.7 | 65 % | 10.8 | 28.2-30.2 | 6.0-6.8 ms | 1.0-1.6 ms |
| after | 4 + 2 | **41.0** (38.3-44.6); **52.9** with `SPU_PROF` | 754; 437 | 46.1; 35.7 | **34.4; 30.9** | **36 %** | **3.9** | **10.0-11.4** | **2.3-2.4 ms** | **0.01 ms** (ran 2-5 jobs itself) |

On a CPU with half this one's speed per core the before list would take
~12 ms of the frame on two threads (24 ms of CPU) while the game's own work
before the wait is ~7 ms: ~5 ms of every pool frame spent waiting -- and the sound core alone
would need ~1.3 processors (more than its 5.33 ms tick). After: ~8 ms of CPU
over three threads, done before the game needs it, and the sound core ~0.7
of a processor.

Per job and per frame (`SPU_PROF=1`, one 600-walk window per run):

| | skinning job (us) | jobs per frame | skinning CPU per frame | list wall time | game thread: jobs run / blocked per frame |
|---|---|---|---|---|---|
| 4 processors, before | 26.4-26.7 | 391 | 10.3-10.5 ms | 5.6 ms | 0 / 0.65-1.22 ms (0.4-0.7 waits) |
| 4 processors, after | 9.9-10.6 | 390 | 3.9-4.2 ms | 2.3-2.6 ms | 2.6-3.1 / 0.00-0.01 ms |
| 16 processors, before | 24.2-24.4 | 390 | 9.4-9.5 ms | 1.3-1.6 ms | 0 / 0 |
| 16 processors, after | 9.5-10.0 | 390 | 3.7-3.9 ms | 0.7-0.8 ms | 0 / 0 |

The `jcsignal` job is 20-28 us either way (its time is the event it sends).
The SPU threads' context switches fell from ~1,050 to ~750 a second (4
processors). One "after" run in ~36 had the sound core at 95 % of a processor
from its boot on (late audio blocks during the title). Hunted afterwards with
72 boots, 3 at a time on this loaded PC: new and old build 36 each, 4, 8 and
16 processors, power saving on and off, `SPU_PROF=1`, the sound core's CPU
logged every second from boot (a watcher would have sampled it with
`tools/thread_sampler.py` above 75 % for 3 s):

| build | runs | sound core, fight window: median (max) | highest 1-s share from boot | seconds above 75 % | runs with late audio blocks (blocks) |
|---|---|---|---|---|---|
| new | 36 | 37 % (42 %) | 55 % | 0 of 2,167 | 4 (70) |
| old | 36 | 66 % (71 %) | 83 % | 66 of 2,176 | 21 (709) |

It never came back (with the 16 earlier checks: 1 in ~88 boots of the new
build). In the outlier run itself the job lists and the waiting game thread
looked like every other run (10.4-10.6 us per job, 0.00-0.01 ms blocked), and
the sound core was already hot before the first skinning list ran; the
job-help path only touches threads waiting on a queue SPURS attached (queue 1),
never the sound core (it waits on its own queue, 5). Most likely the PC (its
processors were shared with 25-30 others' processes); if a player's
`[cellAudio] sound glitches` lines ever show it, `tools/thread_sampler.py
--threads spu` on that game names the code.

### The same results, bit for bit

- The helpers against the code they replace, exactly: `tests/run_ps3recomp_tests.py`
  `spu_int_sse` (every shift count and position, every fsm selector, shufb
  with and without special selectors: 3.9 M checks) and `spu_near_float_sse`
  (the 0041 code copied in; every pair of operand exponents plus 3 M random
  vectors biased to zero/denormal/overflow/cancellation: 19.3 M checks).
- In the game: a `SPU_SELFCHECK` build ran boot, title, select and a fight --
  **5.86 billion** helper calls on real data (sound core fa/fs/fm/fma/fnms
  2.8 G, shufb 2.0 G, rotqby 0.57 G, ...), **0 differences**.
- Lockstep pairs, new host against a before joiner (two pairs, three
  `T5_NET_SHOT` frame dumps each, all six surfaces): 0 mismatching frames
  and the same result hash; 3 of the 6 shots byte-identical in every surface,
  one more identical except Lili's hair strands (secondary motion). The
  others differ the way two games of the *same* build differ: the fight
  camera is not kept equal between two games (two same-build pairs, old/old
  and new/new: 0 of 6 shots identical). Likewise `SPURS_JOB_HASH`: 4,498 of
  6,792 and 3,957 of 6,854 skinning walks gave the same hash on both sides
  (~3.2 M jobs' output byte-identical); the same-build pairs, whose cameras
  had drifted apart, matched 0 walks.
- Rollback pairs (RTT 150, 3 % loss, 500-570 rollbacks a side): new/new,
  new host/before joiner and before host/new joiner, 0 mismatching frames,
  the same result hash both sides; lockstep new/new the same.
- Nothing here reaches game state: the skinned vertices are only drawn, and
  the sound core's samples and replies are the same bits; the game thread
  running jobs changes which thread computes them, not what.
- Smoke quick PASS (audio PASS: 0 % silent blocks in fights); `tests/` OK.

### Not done

- The SPU_NEAR_FLOAT operand tests (zero for a denormal operand) are still
  done on every operand; values that come straight from another float op
  are already flushed. Knowing that needs the lifter (~10 % of the sound core
  at most: an experiment without them took 10-15 % off).
- Job staging (copying the 17 KB binary and clearing the job's regions per
  job, ~12 % of a job) and the 8-byte guest-memory copy loops (~5 %).
- Not tried on a real 4-core laptop or an APU.
## Thread placement (patch 0065, branch `sched-perf`)

Player report: an i5-7300HQ laptop (4 cores, 4 threads, no SMT) plays fights
at about 40 fps. This section is the study of where the game's threads run,
at which priority and how many of them there are -- on that CPU and on kinds
this PC does not have (Intel hybrid) or has only in part (two CCDs, SMT).

**Result:** on 4 processors slowed to a ~40 fps stand-in, fights run 8.6 %
faster (39.6 -> 43.0 fps, faster in 8 of 8 paired rounds, p99 35.9 -> 34.0
ms, a third fewer late audio blocks), on the pool stage (id 30, its crowd
of party guests) 22 % faster (8 of 8): one more skinning thread and the
game's own threads one step above its helpers. On all 32 processors of this
busy PC the game held 59.95 fps where it had dropped to 42-54. Hybrid CPUs get the performance cores
for the frame's threads, two-CCD Ryzens keep them on one CCD, the main thread
and the translation never share a core; the log says all of it.

### The threads of a fight

`tools/fight_bench.py`, 4 cores / 4 threads (affinity 0x55), the PC busy with
other programs (39 fps): CPU per frame of every thread and how it waits.
Priorities are relative to the process class (+1 above normal, +2 highest).

| thread | what it does | CPU per frame | priority before -> 0065 | how it waits |
|---|---|---|---|---|
| `spu` | the SPU sound core (lifted DSP), 187.5 ticks a second | 15.4 ms (0.6 of a core, fixed per second) | +2 | its mailbox: condition variable (10 ms re-poll) |
| `main` | the game's main PPU thread: game logic, kicks the skinning, builds the RSX commands | 8.5 ms | +1 -> +2 | lv2 cond / semaphore / event queue (its helper threads, the skinning), the flip (WaitOnAddress, 0047) |
| `ticker` | vblank clock, FIFO walk = render translation, present | 4.4 ms | +2 | high-resolution timer + FIFO kick event, polls the last 250 us before a tick |
| `spurs-chain` | the skinning job chain's walker; takes jobs itself | 4.1 ms | +1 | an event per chain |
| `spurs-job` (1 on 4 cores; 0065: 2) | skinning jobs | 3.6 ms | +1 | condition variable per job list |
| `NU::Draw::RequestManager` | game thread (lv2 priority 1001): the main thread hands it draw work and waits for it | 3.4 ms | +1 -> +2 | lv2 cond |
| `rsx-vertex` | vertex fetch for the translation | 2.8 ms | +1 | 300 PAUSEs, then WaitOnAddress |
| `pad sampler` | 1 ms pad / keyboard sampling (tap latch) | 2.5 ms with the bench's script file; 1-3 % of a core with a real pad | +2 | high-resolution timer |
| `bnusCoreUpdateThread`, `CnuSound2Thread`, `bnusCoreDecoder*` | the game's sound threads | 0.3 ms | +1 -> +2 | lv2 waits |
| `audio-mix` | cellAudio mixer | 0.07 ms | time-critical | high-resolution timer to the next block |
| `keyread`, `NU::File::RequestManager`, `NU::System::RenderDuration`, `NU::Draw::Geometry::RequestManager`, `particle` | game threads (lv2 1000-1001) | ~0 | +1 -> +2 | lv2 waits |
| loaders: `ZsAread`, `TNUD::ASync`, `decoder`, `data check`, http | lv2 priority >= 1002 | 0 | 0 | semaphores |
| `audio-device`, PSO writer, prewarm, replay writer, pad hot-plug | background | ~0 | -1 (EcoQoS with power saving) | events, timers |
| `netplay-rx`, `netplay-tick` (online) | receive inputs, keepalives | ~0 | 0 -> +2 / +1 | `recvfrom`, 50 ms sleep |
| D3D12 driver threads | | 0.07 ms | -- | -- |

Nothing spins in a fight on a small CPU: sub-millisecond sleeps use the timer
below 24 logical processors (0047), the flip wait sleeps until the flip, the
vertex worker's 300 PAUSEs bridge two draws of one walk. A trace
(`PS3_SCHED_TRACE`, 4 processors, PC busy) shows the frame's critical path:
in its game part the main thread waits ~26 ms of a 40 ms frame in lv2
`sys_cond_wait` for `NU::Draw::RequestManager` and ~8 ms for an lwmutex that
thread holds -- the two hand the frame back and forth -- then the skinning
and the translation; the sound core runs beside them.

### What the scheduler did, CPU by CPU (before 0065)

**(a) 4 cores / 4 threads.** CPU budget 4 (affinity mask): 2 SPURS job
threads (walker + 1 worker), 1 vertex worker, sub-ms sleeps on the timer, no
ideal processors. Oversubscribed? On this PC's ~5 GHz cores the game uses
1.5-1.8 of its 4 processors; on cores 2-2.5x slower the same work is 3.5-4.5
processors -- yes, on the player's PC every thread competes. The workers ran
at +1, the same level as the main thread and the game's own threads; the
translation (+2) was above them. Making the workers lower is the obvious fix
and it is wrong: at below normal -15 % (4 of 4 rounds), at normal -6 % -- the
main thread waits for the skinning, and lower workers then lose their
processor to every other program. Raising the main thread alone did nothing
(+0.1 %): it waits for its helper threads. What helped: one more job thread,
and the main thread *with* the game's other threads one step up.

**(b) Intel hybrid.** EfficiencyClass (`GetSystemCpuSetInformation`) was read
only to rank cores for the opt-in `PS3_SCHED_CPUS=fast` and
`PS3_SCHED_IDEAL=1` (which ranked the whole PC, not the affinity mask).
Nothing kept the main thread or the translation off the efficiency cores:
Windows' Thread Director decides, and with the performance cores busy (our
own workers among them) it moves threads to the E-cores. EcoQoS: the process
opts out of power throttling (EXECUTION_SPEED off), and only background
threads (audio device, PSO writer, trace) get EcoQoS, with power saving --
none of the frame's threads. That part was right.

**(c) Two CCDs (7950X).** Nothing by default: the main thread, the
translation and the game's threads wherever Windows put them, their
hand-offs (cond signals, the command buffer, the flip) crossing between the
two caches.

**(d) SMT.** Nothing kept the main thread and the translation apart; Windows
prefers an idle core, but its default ideal processors can put both on one
core's two threads.

### What changed

`runtime/platform/host_sched_plan.h` (new: pure functions over the processor
table, unit-tested) makes one plan at start; `host_sched.c` applies it to each
thread as it starts.

| change | for | switch |
|---|---|---|
| **The game's own threads one step up**: the main thread and every guest thread of lv2 priority < 1002 (draw request managers, sound threads; their order among themselves stays the PS3's) +1 -> +2, above the SPURS and vertex workers (+1); the translation and the sound core stay +2 | everyone | `PS3_SCHED_PRIO_MAIN`, `_PPU`, `_PPUHI` (=1: before) |
| **SPURS job threads**: half the logical processors or one per core but the main thread's, whichever is more -- 3 instead of 2 on 4 cores without SMT, 5 instead of 3 on 6c/6t; SMT CPUs unchanged | CPUs without SMT | `SPURS_JOB_THREADS` |
| **Performance cores only** for the main thread, the game's threads, the translation, the sound core and the vertex worker (the translation waits for it): a CPU set (`SetThreadSelectedCpuSets`) of the processors with the highest EfficiencyClass. The skinning workers may use every core (hundreds of small jobs dealt out as they finish) but a low-power island's | Intel 12th gen and later, Core Ultra | `PS3_SCHED_PLACE=0` |
| **One cache group**: with several last-level caches the main thread, the game's threads, the translation and the sound core stay in the group with the larger L3 when the sizes differ (X3D's V-Cache CCD), else the one holding the best-ranked core -- if it has 6 cores or more (Ryzen 3000's 4-core CCXs do not). Workers on both | two-CCD Ryzens; Core Ultra (its low-power island stays out) | `PS3_SCHED_PLACE=0` |
| **Ideal processors**: main thread, translation and sound core on three different physical cores, best-ranked first (CPPC preferred cores, Turbo Boost Max), processor 0's core last (it takes most device interrupts and DPCs; on a CPU that ranks no core, like the i5-7300HQ, "by number" put the main thread there) | everyone | `PS3_SCHED_IDEAL=0` |
| The frame's threads and workers say "never EcoQoS" for themselves (`ThreadPowerThrottling`, EXECUTION_SPEED off) besides the process-wide opt-out | hybrids, an older Windows where the process opt-out fails | `PS3_SCHED_THROTTLE=0` |
| The vertex workers go through `host_sched` (`PS3_SCHED_PRIO_VERTEX`, CPU set) | -- | -- |
| Online: the netplay receive thread at +2 (was normal: an input packet could wait a time slice behind the game's threads), the tick thread +1, both named | online | -- |
| `[sched] processors:` / `[sched] placement:` lines and one line each for the main thread, the translation and the sound core (priority, ideal processor, CPU set, EcoQoS, whether Windows took each); the problem report keeps them | everyone | -- |

This PC limited to 4 cores / 4 threads (0x5500):

    [sched] processors: 4 logical, 4 cores (of 32), no SMT, small; one core type; one cache group
    [sched] placement: game thread, translation, sound core on any processor, ideal LP 10 / 8 / 14; game's other threads anywhere
    [sched] placement: workers anywhere; SPURS 3 at a time, vertex workers 1; priorities: game +2, translation +2, sound +2, workers +1/+1
    [sched] game thread 'main': priority +2, ideal processor LP 10 (ok), CPU set none, EcoQoS never (ok)

All 32 processors:

    [sched] processors: 32 logical, 16 cores (of 32), SMT; one core type; 2 cache groups, the game in group 0 (LP 0-15, 8 cores: best-ranked core)
    [sched] placement: game thread, translation, sound core on LP 0-15 (one cache group), ideal LP 6 / 10 / 4; game's other threads the same
    [sched] placement: workers anywhere; SPURS 12 at a time, vertex workers 3; priorities: game +2, translation +2, sound +2, workers +1/+1

A 12700H as the unit test builds it: the frame on the P-cores LP 0-11, ideal
LP 2 / 4 / 6 (core 2 its favoured core, processor 0's core last), vertex
fetch on LP 0-11, skinning anywhere.

Tried and dropped:

- Workers off the game's cores (a CPU set without the main thread's and the
  translation's cores, both their threads, from 6 cores with SMT): on 6c/12t
  and 8c/16t the game took 8-13 % more CPU per frame (35.7 -> 40.3 and 35.2
  -> 38.0 ms), the translation got 0.2-0.6 ms longer and context switches
  went up; other programs' load was higher in 7 of those 8 runs (most
  likely they moved onto the freed cores) and the workers crowded the rest. The ideal processors keep the main thread and the
  translation apart without it.
- The workers in the CCD too, sized from it (8 job threads, 1 vertex worker
  instead of 12 / 3 at 32 processors): the translation 2.7 -> 3.6 ms.
- The translation waiting for a vertex worker's last job by WaitOnAddress
  instead of spinning: translation 2.9 -> 4.7 ms in a paired round under
  load (the wake-up came later than the spin noticed the job).

### How it was measured

`tools/slow_core.py` (new): slower processors on this PC. One busy process per
logical processor of a mask, each pinned to its processor at time-critical
priority (above every thread of a game started below normal), all taking
their processor for the first part of each 4 ms period on the same clock --
the game keeps all its processors for the rest, every thread slowed alike
(`--busy 40` takes ~30-35 % of the time; Windows' timers wake late). Not
exact: a thread frozen for 2 ms can hold a lock another thread needs, which a
slow core does not do.

Paired runs: two configurations at the same time on two 4-processor masks, 4
cores without SMT each, swapped every round, each with its own slow_core
`--busy 40`; fps over fight start +24..42 s. First the two CCDs (0x55 /
0x550000), then -- another agent's pinned games loaded CCD1 -- both on CCD0
(0x55 / 0x5500). Other agents' games kept 11-31 of the 32 processors busy (a
round starts once at most 22 are busy and at most 2 compilers run, or after
4 minutes). The mask alone moved fps by 5-20 % from round to round
(processor 0, in 0x55, was the slower side in most rounds), so only the
geometric mean over swapped rounds compares two configurations.

### Results

4 cores / 4 threads, slow_core `--busy 40` (fights at 30-55 fps), Lili vs Asuka on stage 20 unless the row says otherwise:

| B against A | masks | rounds | B faster in | fps B / A |
|---|---|---|---|---|
| SPURS workers below normal (-1) against +1 (before 0065) | CCDs | 4 | 0 | -15.0 % |
| SPURS workers normal (0) against +1 | CCDs | 4 | 1 | -5.7 % |
| 3 SPURS job threads against 2 (before 0065) | CCDs | 4 | 4 | +9.4 % |
| main thread +2 alone | CCDs | 4 | 3 | +0.1 % |
| 0065 draft with 2 job threads against 3 | CCD0 | 6 | 2 | -4.5 % |
| 0065 draft without ideal processors | CCD0 | 6 | 3 | +0.4 % |
| 0065 draft with the game's threads +2 | CCD0 | 6 | 3 | +3.5 %; late audio blocks 917 -> 102 |
| **0065 against before** | CCD0 | 8 | **8** | **+8.6 %**: 39.6 -> 43.0 fps (mean), p99 35.9 -> 34.0 ms, 42.0 -> 40.7 ms CPU per frame, late audio blocks 324 -> 216 |
| **0065 against before, the pool stage** (id 30: the crowd of party guests around the pool, the stage a 4c/4t player saw drop) | CCD0 | 8 | **8** | **+22.3 %**: 34.8 -> 41.0 fps (mean; the six rounds at 40-58 fps 41.9 -> 48.6), p99 36.4 -> 33.0 ms, 45.2 -> 41.4 ms CPU per frame |
| the same without slow_core (the other agents' load only: 28 of 32 processors busy) | CCD0 | 6 | **6** | **+19.8 %**: 31.3 -> 36.8 fps (mean), p99 88 -> 54 ms, 51.3 -> 48.3 ms CPU per frame |

Bigger CPUs, without slow_core (the CPU per frame of the whole game and of
the walker, `fifo_cpu_us`, are means over the runs):

| CPU (affinity) | how | fps before -> 0065 | p99 ms | CPU ms per frame | walker ms | other programs (processors) |
|---|---|---|---|---|---|---|
| 8c/16t (0x0F0F0F0F / 0xF0F0F0F0: 4 cores of each CCD, so no cache group of 6) | paired, swapped, 5 rounds | 59.10 -> 59.89 (lowest 57.7 -> 59.7) | 24.0 -> 19.0 | 37.5 -> 37.4 | 3.08 -> 2.98 | 18 |
| all 32 (7950X: the frame's threads on CCD0, workers on both) | one game at a time, alternating, 4 runs each | 48.7 -> 59.95 (every 0065 run 59.95) | 37.7 -> 18.5 | 55.4 -> 48.5 | 3.97 -> 3.75 | 16-29 |

(A sixth 8c/16t round ran while this branch's exe was being linked -- both games froze for 4 s -- and is left out.)

Online: a rollback pair (RTT 150 +-5 ms, 3 % loss, host on 4c/8t, joiner on
4c/4t) and a lockstep pair (RTT 30, 1 % loss, the masks swapped), one match
each: sync through frame 4199 0 mismatching frames on both sides of both
pairs, the same result hash (rollback `7756e4de9093d63d`, 559 / 581 rollbacks,
57-58 fps; lockstep `89e1a56b4f15809b`), no decode error or abort. Priorities
and placement are timing only: they never reach the game state.

### Not done

- No hybrid CPU here: (b) is unit-tested only (`tests/c/sched_plan_test.c`:
  12700H, 1215U, 13900K, Core Ultra 155H / 125H with the low-power island,
  7950X, 7950X3D, 7800X3D, 3700X, 4c/4t, 2c/4t, 4c/8t, 6c/6t, 6c/12t, masks
  across CCDs, processor 0 ranked first, 4,000 random tables against the
  rules every plan must keep). (c) and (d) ran on this 7950X under other
  agents' load (tables above); a two-CCD Ryzen on its own was not tried.
- A real i5-7300HQ: the slow_core stand-in slows every thread alike; a real
  Kaby Lake core is also slower per clock in the translation's hashing and the
  lifted code, which this cannot model. Its power saving (on by itself: a
  mobile processor) was off in these runs; at 4 processors it only stops the
  ticker's 250 us poll and puts background threads on EcoQoS.

## Combined 1.1.3 vs 1.1.2 (branch `perf-combined`)

The owner's goal: 60 fps on weak PCs. The reference player has an i5-7300HQ
laptop (4 cores, 4 threads, no SMT) with a GTX 1050 Ti at 720p Native: on
1.1.2 most stages ran at 55-60 fps, the pool stage (id 30, the crowd of
party guests) dropped a lot. The 1.1.3 patches above were each measured
alone. This section measures them together, against 1.1.2, and estimates
what is left on that laptop.

**Result.**

- On this PC, 4 cores with one thread each, the same fights at the same
  time: 1.1.3 needs **38-48 % less CPU per frame** for the whole game than
  1.1.2, the SPU side 57-65 % less, the main thread 8-23 % less; the
  frame's critical path (game part + translation) is **36-51 % shorter**.
  Pool stage: 52 -> 60 fps on the 4 cores, 29 -> 53 fps with the cores
  slowed.
- PGO (cpu-build-opt) on top: the main thread 2-10 % less CPU, the game
  part 7-9 % shorter; the frame rate moved within the noise; the draw
  thread gained nothing.
- **The i5-7300HQ (estimate): 1.1.3 with PGO runs the pool stage at about
  58-60 fps** (most likely ~59.7), stage 20 at 59-60. That is close, but not
  a locked 60: 1-5 % of the frames (up to ~22 % with the pessimistic
  assumptions) still run 1-5 ms past their 16.7 ms. A locked 60 on the pool
  stage needs the critical path about 15 % shorter (28 % in the pessimistic
  case).
- **What is left is one core's speed**, on two threads in series: the main
  thread's own work (the game's code, ~55 % of the critical path), the
  render translation (~30 %), and the main thread waiting for the game's
  draw thread (~20 %). The SPU side is off the critical path now (the main
  thread never waits for the skinning), and so is the GPU.

### The three builds

All three are built the way a player's game is (docs/RELEASE.md): a
runtime `t5dr.exe` compiled with `-DT5DR_GAME_DLL=ON` and the lifted code
compiled into `t5dr_game.dll` by that version's `tools/build_game_dll.py`,
x86-64-v3 (the i5-7300HQ has AVX2 as well), LLVM 23.1.3, from one lift (the
lifter is the same in both versions, sha1 `6bb0bf00`).

| | source | game DLL |
|---|---|---|
| A, 1.1.2 | tag `v1.1.2` (8eb6972): series to 0053 | 45.7 MB |
| B, 1.1.3 | integration-113 caa7158: + 0051, 0059, 0061, 0062, 0063, 0064, 0065 | 44.3 MB |
| C, 1.1.3 + PGO | B's `t5dr.exe`; the DLL built with cpu-build-opt's tool and its shipped profile (`tools/gamedll/t5dr_lifted.proftext`, four parts) | 36.9 MB |

integration-113 has moved on since (cpu-build-opt merged with this same
profile file; review-113's 0063 change moves the processor clock's first
PDH query off the vblank thread -- a one-time 0.3-0.4 s freeze ~30 s after
start, which came before the measuring window in every run here; security
review 3's `-fno-caret-diagnostics`, which gives the same objects). None of
it changes the numbers below.

### How it was measured

- `tools/fight_bench.py` (a copy that also takes the latency probe
  `PS3_LATENCY_LOG` for every build), `--polite` (below normal, muted), Lili
  vs Asuka, P1 attacking, window fight start +24..42 s, Native, a warm
  shader cache per build (`RSX_SHADER_CACHE_DIR`; a player's cache is warm
  after the first fight).
- **All three builds at the same time**, each on its own 4 cores with one
  logical processor per core (a 4c/4t CPU): 0x5500 (cores 4-7, CCD0),
  0x550000 (8-11) and 0x55000000 (12-15, CCD1); processor 0's core stays
  out. Round r puts build i on group (i + r) mod 3, so every build visits
  every group, and each round is a paired comparison of all three.
- **Slowed**: `tools/slow_core.py --busy 50` on each group (it took 33-43 %
  of the time under this load).
- The four conditions (stage 30, stage 30 slowed, stage 20, stage 20
  slowed) took turns round by round, 6 rounds each.
- The PC was shared the whole time: other agents' games, builds and test
  harnesses kept 16-31 of the 32 processors busy, and the SMT sibling of
  each test core was mostly 77-100 % busy (sampled in every round from the
  fourth on; 41-61 % in one sample before). The tables keep
  the rounds where other programs (without this bench's own games and
  slow_core) used at most 22.5 processors; the rest are listed at the end.
- A slowdown matched to the laptop (`--busy 38`, ~28 % taken) was started
  after the batch, but the PC stayed at 28-31 busy processors (slow_core
  itself then took only 12-30 %); it is left out.

Columns, per displayed frame, median over the rounds:

- fps and p99 frame time from the presents (as everywhere in this file);
- **frames late**: game frames (the main thread's frame start to the next,
  probe event B) longer than 17.5 ms, i.e. past their 16.7 ms vblank (the
  presents jitter around the vblank, so their own times do not show this);
- main thread: its CPU time (thread times; with 0064 it also runs a few
  skinning jobs);
- **game part** (B -> flip request F) and **translation** (F -> walker
  reached the flip X): in series, together the frame's critical path;
- SPU: CPU of the sound core thread (`spu`) + the skinning threads
  (`spurs-chain`, `spurs-job`);
- draw thread: `NU::Draw::RequestManager`, the game thread the main thread
  hands draw work to;
- game CPU: all the game's threads (with ~1.5 ms of the bench's own pad
  script sampler).

### Results

Pool stage (30), 4 cores, 3 rounds, other programs 18-21 processors:

| build | fps | p99 ms | frames late | main thread CPU ms | game part ms | translation ms | SPU CPU ms (sound + skinning) | draw thread ms | game CPU ms |
|---|---|---|---|---|---|---|---|---|---|
| 1.1.2 | 52.2 | 43.6 | 17 % | 6.09 | 10.52 | 3.11 | 18.7 (9.9 + 8.9) | 3.00 | 36.0 |
| 1.1.3 | **59.7** | 22.4 | 1 % | 5.09 | 6.20 | 2.78 | 8.5 (5.5 + 3.0) | 2.55 | 23.0 |
| 1.1.3 + PGO | **59.7** | 21.6 | 1 % | 4.54 | 5.91 | 2.72 | 8.2 (5.2 + 3.0) | 2.84 | 22.7 |

Pool stage, 4 cores slowed, 4 rounds, other programs 16-22 processors:

| build | fps | p99 ms | frames late | main thread CPU ms | game part ms | translation ms | SPU CPU ms (sound + skinning) | draw thread ms | game CPU ms |
|---|---|---|---|---|---|---|---|---|---|
| 1.1.2 | 29.0 | 51.0 | 100 % | 6.52 | 21.40 | 6.86 | 26.5 (18.0 + 8.5) | 3.07 | 45.6 |
| 1.1.3 | **52.6** | 29.6 | 56 % | 5.92 | 13.07 | 4.50 | 9.3 (6.3 + 3.1) | 2.97 | 25.0 |
| 1.1.3 + PGO | **52.6** | 25.8 | 67 % | 5.64 | 12.46 | 4.71 | 9.5 (6.3 + 3.2) | 2.93 | 25.9 |

Stage 20 (scrapyard), 4 cores, 3 rounds, other programs 18-21 processors:

| build | fps | p99 ms | frames late | main thread CPU ms | game part ms | translation ms | SPU CPU ms (sound + skinning) | draw thread ms | game CPU ms |
|---|---|---|---|---|---|---|---|---|---|
| 1.1.2 | 45.4 | 48.0 | 52 % | 7.49 | 13.80 | 3.34 | 19.1 (12.6 + 8.1) | 2.93 | 37.7 |
| 1.1.3 | **60.0** | 20.4 | 1 % | 5.95 | 7.36 | 2.84 | 8.1 (5.3 + 2.5) | 2.90 | 23.9 |
| 1.1.3 + PGO | **60.0** | 20.0 | 1 % | 5.42 | 6.70 | 2.81 | 8.1 (5.3 + 2.6) | 3.11 | 24.2 |

Stage 20, 4 cores slowed, 3 rounds, other programs 19-22 processors:

| build | fps | p99 ms | frames late | main thread CPU ms | game part ms | translation ms | SPU CPU ms (sound + skinning) | draw thread ms | game CPU ms |
|---|---|---|---|---|---|---|---|---|---|
| 1.1.2 | 20.4 | 82.9 | 100 % | 8.18 | 32.90 | 6.81 | 29.1 (21.0 + 7.7) | 3.50 | 51.9 |
| 1.1.3 | **46.2** | 58.8 | 80 % | 6.56 | 15.34 | 2.92 | 10.6 (7.9 + 3.1) | 3.02 | 27.9 |
| 1.1.3 + PGO | **49.7** | 30.7 | 75 % | 6.44 | 12.68 | 4.63 | 9.0 (6.8 + 2.2) | 2.95 | 25.3 |

Paired ratios (geometric mean over the rounds of each table; in brackets
the rounds in which the newer build was better):

| | stage 30 | stage 30 slowed | stage 20 | stage 20 slowed |
|---|---|---|---|---|
| 1.1.3 / 1.1.2: fps | 1.16x (3/3) | 1.84x (4/4) | 1.48x (3/3) | 2.16x (3/3) |
| main thread CPU | 0.83x (3/3) | 0.92x (4/4) | 0.84x (3/3) | 0.77x (3/3) |
| game part + translation | 0.64x (3/3) | 0.62x (4/4) | 0.53x (3/3) | 0.49x (3/3) |
| SPU CPU | 0.43x (3/3) | 0.35x (4/4) | 0.38x (3/3) | 0.36x (3/3) |
| game CPU | 0.62x (3/3) | 0.54x (4/4) | 0.60x (3/3) | 0.52x (3/3) |
| PGO / 1.1.3: main thread CPU | 0.90x (3/3) | 0.92x (3/4) | 0.92x (3/3) | 0.98x (2/3) |
| game part | 0.92x (3/3) | 0.93x (3/4) | 0.92x (3/3) | 0.91x (3/3) |
| draw thread CPU | 1.09x (0/3) | 1.02x (2/4) | 1.03x (1/3) | 0.95x (1/3) |
| fps | 1.00x (2/3) | 1.01x (3/4) | 1.00x (3/3) | 1.07x (3/3) |

How the single patches add up:

- 0064 said SPU -40 %: together -57..-65 % (sound core 9.9-12.6 -> 5.3-5.5
  ms, skinning 8-9 -> 2.5-3.0 ms per frame).
- 0061 said game thread -27 % (4c/8t, quieter): the main thread's CPU
  here -16..-23 % (-8 % in one slowed set), on cores whose SMT siblings were
  busy.
- 0062 said translation -24 %: -12..-22 % on the 4 cores; slowed, 1.1.2's
  translation was also held up by its other threads, so -31..-42 %.
- 0059 shows in the slowed runs: 1.1.2's late frames waited for the next
  vblank (every frame late, 29 fps), 1.1.3's are shown when translated.
- 0065 and the SPU change show most where other programs compete (next
  paragraph).
- PGO said main thread -4..-6 %: -2..-10 % here.

**1.1.2 suffers more from other programs than a player's 1.1.2 does.**
With the game below normal (`--polite`), 1.1.2's main and draw threads run
at +1, one step below other programs' normal threads; 0065 put them at +2,
level with them. So under this PC's load 1.1.2's game part is stretched by
waits for its own helper threads (here 10.5-13.8 ms of game part for 6-7.5
ms of main thread CPU; 1.1.3: 6-7.4 for 5-6), and in the rounds left out of
the tables (other programs 24-28.5 processors) 1.1.2 fell to 13-41 fps
where 1.1.3 kept 21-60. A player's game runs at normal priority, so the fps
ratios above are larger than a player sees on an idle PC; the CPU ratios
carry over. A quick 1.1.2 run on stage 20 with 17 busy processors (not
paired) held 59.95 fps.

### The i5-7300HQ

The laptop's cores are taken as 0.55-0.60 of this PC's (the owner's
figure). The test cores here were not quiet ones: their SMT siblings were
mostly 77-100 % busy, which [WEAK_PC.md](WEAK_PC.md) measured as +45 % game part
and +60 % translation with fully busy siblings. So a test core was about
0.7 of a quiet core (0.65-0.8), a slowed one 0.7 x (1 - 0.33..0.43) = 0.40-0.47.
The laptop (0.55-0.60, no SMT, nothing else running) lies between the two
conditions.

The estimate replays every measured frame on the laptop: its game part and
translation (the critical path; in series by design, everything in them is
the game's CPU work or waits for its other threads) scaled by
e / s (e = the test core's speed, s = the laptop's), on the 59.94 Hz clock
with each version's rule (1.1.2: a game part past its tick waits for the
next tick; 1.1.3: a late frame is shown when translated, ~0.8 ms later as
measured). Replayed at the measured speed it gives the measured fps within
1 % for 1.1.3 in three of the four sets, 3-13 % too high in the stage 20
slowed set and 2-9 % too high for 1.1.2: it leaves out stalls longer than a
frame, so it is a little optimistic. The whole
game's CPU per frame, scaled the same way, checks the 4 cores' capacity.

| stage | build | laptop fps, s = 0.55 / 0.60 (from the 4-core runs) | (from the slowed runs) | frames late | critical path on the laptop: median / slowest 5 % | 4 laptop cores busy |
|---|---|---|---|---|---|---|
| 30 | 1.1.3 | 59.3 / 59.6 | 59.1 / 59.6 | 2-10 % | 11.2 / 16.6 ms | 40-48 % |
| 30 | 1.1.3 + PGO | **59.7 / 59.8** | **59.5 / 59.8** | 1-5 % | 10.6 / 15.2 ms | 40-49 % |
| 20 | 1.1.3 | 59.8 / 59.8 | 59.3 / 59.7 | 1-7 % | 12.4 / 15.5 ms | 42-53 % |
| 20 | 1.1.3 + PGO | 59.8 / 59.9 | 59.1 / 59.7 | 1-9 % | 12.1 / 15.1 ms | 42-48 % |

(e = 0.7. With e = 0.65 every 1.1.3 row is 59.5-59.9 fps with at most 3 %
late. With e = 0.8, the pessimistic end: pool stage 1.1.3 57.2-58.9 fps and
9-27 % late, + PGO 58.0-59.5 fps and 5-22 % late.)

- **Does 1.1.3 reach 60 fps on stage 30 there? Nearly.** The average comes
  to 58-60 fps (with PGO most likely ~59.7); the median frame needs ~11 of
  its 16.7 ms, but the slowest 1-10 % of frames (1-5 % with PGO; up to
  ~25 % with the pessimistic numbers) run 1-5 ms late -- seen as small hitches rather than
  as a lower frame rate. A locked 60 (99 % of pool frames in time, 1 ms
  spare) needs the critical path ~15 % shorter (e = 0.7, s = 0.575; ~28 %
  at e = 0.8, s = 0.55): 1.3-2.5 ms per frame in today's terms here
  (median 8.7 ms, p99 15.0 ms with PGO).
- 1.1.2 on the same model comes out at 29-49 fps -- below the 55-60 the
  player saw on most stages, because 1.1.2's frames here carry the waits
  described above. What does carry over: 1.1.2 needs 36-38 ms of CPU per
  frame here, 63-72 % of the laptop's 4 cores before anything else runs,
  so the pool stage's extra skinning (~420 jobs a frame against ~390) had
  nowhere to go; 1.1.3 leaves more than half of the 4 cores free.
- Not modelled: Kaby Lake's lower speed per clock is in the 0.55-0.60;
  slow_core freezes threads ~1.7 ms at a time, which a slow core does not;
  the laptop's power saving (`PS3_LAPTOP` Auto turns it on for a mobile
  processor) was off here -- at 4 processors 0064 measured it slightly
  faster (58.0 against 55.6 fps); programs running beside the game on the
  laptop take from the same 4 cores.
- The GPU is not the limit: the RTX 3090 needs 0.4 ms per frame here at
  Native; a GTX 1050 Ti is several times slower, still a few ms, and it
  draws beside the next frame's CPU work.

### What is left

1.1.3 + PGO, pool stage, 4 cores (the laptop needs ~1.2x these, e/s =
0.7/0.575), from the probe and 1.1.3's `[slow-frames]` split of the game
part:

| part of the critical path | per frame here | share |
|---|---|---|
| main thread running: the game's own code (lifted PPU code ~83 %), its own CPU 4.5-4.7 ms | 4.9 ms | ~55 % |
| main thread waiting for other game threads: the draw thread `NU::Draw::RequestManager` (lv2 cond / lwmutex hand-offs; the draw thread itself 2.6-3.1 ms CPU) | 1.7 ms | ~20 % |
| main thread waiting for the renderer | 0.0 ms | -- |
| translation (walker) | 2.7 ms | ~30 % |
| SPU (skinning, sound core) | 0 on the critical path: the main thread runs open jobs instead of waiting (0064); the sound core has its own thread, 5.2-5.5 ms CPU per frame (~1/3 of a core here, ~0.4 of a laptop core) | -- |

The next steps, by size:

1. The main thread's own code. The profile is flat (RENDER_PERF "The game
   thread's own time"); the build options are used up (docs/BUILD_PERF.md:
   every guest store is a relaxed atomic plus a reservation check, so the
   PPU registers are reloaded after every store). A lifter change there is
   the big lever left.
2. The hand-off with the draw thread: ~1.7 ms of waiting per frame. The
   draw thread is lifted code as well and got nothing from PGO (0.95-1.09x
   of 1.1.3's CPU): give its functions their own share of the profile, or
   find where the two threads wait for each other (`PS3_SCHED_TRACE`).
3. The translation, ~2.7 ms: per 0062's "What is left" the command walk
   ~0.5 ms, the display driver ~0.4 ms, the texture hash ~0.2 ms.

Local evidence: `build/perfcomb/` (git-ignored: `runs/`, `scripts/bench.py`
for the rounds, `scripts/estimate.py` for the replay model,
`scripts/summ.py` / `mdtable.py` for the tables).

## Lifted code: register promotion (patch 0066, branch `lifter-regpromo`)

The game's main thread is ~83 % lifted code ("The game thread's own time"
above) and its profile is flat: no single function to fix, so the lever is
the quality of everything the lifter emits. The lifted code kept every guest
register in the context struct -- `ctx->gpr[n]`, `ctx->fpr[n]`, `ctx->cr`,
`ctx->xer`, `ctx->ctr` -- and `ctx` is memory the compiler must assume any
guest store, fence or call can change: the inline guest store ends in a
compiler fence, the inline load is an atomic access. So every register a
function wrote was stored, and every register it read after a guest memory
access was loaded again. The hottest function of a fight (the 16-byte packet
copy: a byte loop) loaded its two pointers and its counter from the context
and stored them back on every byte it moved.

### What changed (ps3recomp patch 0066)

`ppu_lifter.py --regpromo on|off` (on by default; `tools/build_game.py` lifts
with it, `T5DR_LIFT_REGPROMO=0` without -- the lift's stamp records it, so a
switch lifts again). A post-pass over each function's final C body:

- The GPRs, FPRs, CR, XER and CTR the function uses become C locals of the
  field's own type (`uint64_t`, `double`, `uint32_t`), loaded from the
  context at entry. The compiler keeps them in host registers; nothing can
  change a local behind its back.
- They go back into the context only where something outside the function
  can look: before every **escape** -- a line that hands `ctx` to a function
  (a direct or indirect call, `ps3_hle_call`, `lv2_syscall`, the trampoline
  drain, `ppu_mtfsf`; kept verbatim), every `return`, every trampoline hand-off,
  the jump-table dispatch and the end of the body. Only what may differ from
  the context is written back: a may-"dirty" dataflow over the body's labels
  and gotos (a register written on any path since the context was last up to
  date). After a call every local is loaded again (the callee may have changed
  anything); the compiler drops the loads nobody uses.
- LR, the vector registers, VSCR, FPSCR and the reservation stay in the
  context everywhere. Other threads write a thread's `reserve_addr` (a
  store-conditional breaks the others' reservations) and `ppu_stwcx32` reads
  it through `g_active_ctx`; nothing else reads or writes the promoted fields
  of a running thread's context except at those escapes (crash dumps and
  stuck-thread diagnostics may now show a register a few instructions old).
- The pass is a strict recognizer of the lifter's own line shapes: a function
  with any line it does not understand (an unknown context field or callee,
  control flow it does not model) keeps its unpromoted body. In Tekken 5 DR
  21,942 of 23,059 functions are promoted; the other 1,117 touch no guest
  register (import stubs, bare trampolines). `--regpromo-skip FILE` keeps listed functions unpromoted (not
  needed: every function the runtime's entry detours patch -- rollback sound,
  heap, random, the direct-call cut, unlocks -- still has a prologue
  `rb_detour.cpp` accepts, and the detours install on both builds).
- Not done: `__restrict` on `ctx`. It is not provably valid -- the HLE
  handlers and `ppu_stwcx32` reach the same context through `g_active_ctx`,
  other threads write `reserve_addr` -- and after promotion the hot code
  hardly touches `ctx` anyway. CR stays one 32-bit local: splitting it into
  fields saves little, since a written field goes back to the context at the
  next exit anyway.

Guest memory accesses, their order and their values are unchanged: the pass
only moves where register values live between two escapes. Build cost
(`build_game.py`'s player-side steps, this PC under load): the lift 18 ->
~45 s (the pass runs while the lifter writes the source, in one process);
the DLL compile (`build_game_dll.py --jobs 8`, interleaved runs) 63.7 / 66.0 s
before, 66.2 / 62.2 s after -- the same wall time, 17 chunks instead of 15,
compiler CPU +7 % (436-456 -> 468-497 s summed); `t5dr_game.dll` 44.3 ->
47.7 MB.

### Results

Paired runs (`fight_bench.py --polite`, Lili vs Asuka, window fight start
+24..42 s; old and new build started together on two halves of the second
CCD, 4 cores without SMT each -- `0x55000000` / `0x00550000` -- swapped every
round; 6 rounds per row). Other agents kept 27-31 of the 32 processors busy
the whole time, so the fps are those of a much weaker, loaded PC and move a
lot between rounds; the CPU time per frame of the game thread (its thread
cycles between two flip requests, `PS3_GAME_THREAD_LOG`) is the steady
number. "slow core" = `tools/slow_core.py --cpus 0x55550000 --busy 50` from
the sched-perf branch: TIME_CRITICAL busy loops took ~40 % of every one of
those processors (the game had them ~60 % of the time: a slower CPU).
Medians of the rounds:

| | build | fps | game thread CPU ms/frame p50 / p99 | main thread ms/frame | draw thread ms/frame | game part p50 |
|---|---|---|---|---|---|---|
| pool stage (30), 4 cores | before | 39.9 | 6.23 / 7.95 | 6.27 | 3.08 | 14.7 |
| | after | **41.8** | **5.83 / 7.69** | **5.96** | **2.57** | 14.2 |
| stage 20, 4 cores | before | 39.8 | 6.70 / 8.08 | 6.56 | 3.21 | 15.6 |
| | after | **44.0** | **6.29 / 7.54** | **6.34** | **2.71** | 14.8 |
| pool stage, 4 cores, slow core | before | 29.4 | 6.15 / 7.68 | 6.27 | 3.08 | 19.7 |
| | after | **32.5** | **5.77 / 7.18** | **5.92** | **2.45** | 18.4 |
| stage 20, 4 cores, slow core | before | 49.4 | 5.74 / 7.29 | 5.85 | 2.97 | 14.6 |
| | after | 48.5 | **5.36 / 6.83** | **5.34** | **2.45** | 14.9 |

- Game thread CPU per frame: -6 to -7 % (paired median ratio 0.928-0.935),
  lower in 23 of 24 rounds.
- The draw thread (`NU::Draw::RequestManager`, lifted code too, the main
  thread's next wait): -16 to -20 % CPU per frame.
- fps: paired median ratio +3 to +13 %, higher in 20 of 24 rounds. Under this
  load the processor half a game got moved its fps more than the build did
  (two rounds of the stage-20 slow-core row: the new build on the half that
  was busier then, -20 and -15 fps).

Profile of the main thread on the pool stage (`thread_sampler.py` on the
DLL, RVAs resolved with an lld-link map; one run per build): still flat; the
packet copy went from 9.3 % to 8.0 % of the lifted samples and runs in host
registers. What is
left per guest access is the memory model, not the registers: every inline
store checks the SPU coherence bitmap twice (pointer through the DLL's import,
line bit), every load two gates; the VMX float helpers are out-of-line calls.

### The same results, bit for bit

- **Function by function, old lift against new lift** (`tools/regpromo_diff.py`,
  new): both lifts' versions of the same function compiled into one harness
  with the lifted code's options (`/O2 /Ob2`, `-ffp-contract=off`,
  `-march=x86-64-v3`), run on the same random inputs -- registers drawn from
  zero, -1, small, 32-bit sign/zero-extended, sandbox pointers and random
  64-bit values; FPRs normal, denormal, +-0, +-Inf and NaNs; random CR, XER,
  CTR, vector registers and guest memory (a 64 KB sandbox every guest address
  folds into). Compared after every run: the whole context, guest memory, and
  a trace of every guest load and store (address and value), every
  store-conditional and every call out of the function together with a hash
  of the **whole context at that call** -- a register not written back before
  a call, or not reloaded after it, shows up at that call. The callee stubs
  change volatile and non-volatile registers, CR/XER/CTR/LR, a vector
  register and a memory word as a function of everything seen so far, and
  sometimes leave a trampoline to drain. A run that passes 20,000 events (a
  loop on a random counter) is stopped and compared by trace and memory.
  - the **100 hottest functions** of a pool-stage fight (main-thread profile):
    100,000 inputs each, **10 M runs, 0 differences**; again built for the
    x86-64 baseline: 10,000 inputs each, 1 M runs, 0 differences;
  - **every function of the game** (23,059): 300 inputs each, 6.9 M runs,
    **0 differences**; 42 functions first could not be judged -- a loop that
    touches no guest memory (the title's own `b .` hang among them) never
    ends; again with an event counted at every label: 5,000 inputs each,
    210,000 runs, **0 differences**.
- **Random lifted-style functions** (`tools/test_ppu_regpromo.py`, new; its
  default run is 150 functions x 1,500 inputs, the final one 400 x 2,000):
  random functions built from every line shape the lifter emits for this
  game (loops forward and back, calls direct/indirect/syscall/conditional,
  conditional returns and trampolines, jump-table switches, callee-save
  snapshots, carry, record forms, FP and vector lines, store-conditional)
  x86-64-v3 and baseline: **0 differences** (1.6 M runs); plus 28
  checks of what is written back where. (It found a bug in the pass on the
  way: `a & ctx->gpr[n]`, a binary AND, was taken for an address-of -- only
  an extra store, but now exact.)
- **Instruction by instruction** (`tools/test_ppu_lift.py --regpromo`): every
  conformance case runs as a promoted function of its own (1,174 of 1,202
  cases; 28 vector-only cases touch no promoted register): 1,533 checks, 0
  failed, as without. The suite runs again: it compiles with clang-cl and
  gets the raw access macros it was missing (plain `cl` cannot compile the
  lifter's FP helpers since patch 0032, so it had been compiling nothing),
  and its 5 FPSCR/VRSAVE decode checks expect the lowering the lifter has
  emitted since it models those registers (they expected no-ops).
- **Online, old build against new build** (`tools/cross_build_test.py`, RTT
  100 +-5 ms, 3 % loss, three matches per mode, the pool stage first; final
  state hash of every frame compared, built-in sync check, result files):

  | pair (host / joiner) | mode | frames compared | rollbacks per side | result |
  |---|---|---|---|---|
  | old / new: Asuka vs Lili stage 30, Lili vs Dragunov stage 20 + rematch | rollback | 16,197 | 1,464 / 1,789 | 0 differ, same 3 result hashes |
  | | lockstep | 13,681 | -- | 0 differ, same 3 result hashes |
  | new / old: Lili vs Asuka stage 30, Dragunov vs Lili stage 24 + rematch | rollback | 17,865 | 2,137 / 2,047 | 0 differ, same 3 result hashes |
  | | lockstep | 17,841 | -- | 0 differ, same 3 result hashes |
  | new x86-64-v3 / new baseline with the software fma (`PS3_FP_SOFT_FMA=1`: a PC without AVX2/FMA3): Dragunov vs Asuka stage 30, Asuka vs Dragunov stage 20 + rematch | rollback | 13,197 | 1,545 / 1,462 | 0 differ, same 3 result hashes |
  | | lockstep | 13,222 | -- | 0 differ, same 3 result hashes |

  The detours the runtime installs on lifted functions (direct-call cut, sound
  hooks, sound heap, random generators) went in on both builds; their
  prologues are push/sub sequences `rb_detour.cpp` accepts in both lifts
  (checked statically for all 55 targets, the diagnostics' too).
  `tools/fp_audit.py --strict` (`--audit`): no estimate instructions, no
  x87, no MXCSR writes, no C runtime math in either DLL.
- **One known difference class, never seen in the game**: a single-precision
  *signalling* NaN loaded by `lfs` and stored again by `stfs`. The lifter
  lowers them as C float/double conversions, and LLVM may fold
  `fptrunc(fpext(x))` to `x` (keeping the NaN signalling, as the PPU does)
  or not (quieting it): which, depends on what the optimizer can see, so it
  already differed from site to site in the old lift (an `lfs`/`stfs` pair
  with no guest access between them folded) and can differ between the two
  lifts. The harness quiets such values in its data for that reason (it
  found only this class before). A probe build (every `lfs` checked) loaded
  **0** signalling NaNs through boot and four fights (stages 30, 20, 24, 34).
- FP code is unchanged (`ppu_fp_det.h`): `test_fp_det` PASS.
- Smoke quick on the new build: exit 0 (boot_menu, arcade_fight, title_twice PASS; vs_two_pads and practice
  fps WARN at 54.6/55.4 with 8-9 other games and 8-10 compilers running). `tests/` 780 OK.

Found on the way, not from this patch: the guest's deliberate hang (`b .`,
an empty infinite loop) is undefined behaviour in C++ (forward progress), and
clang compiles what leads to it as unreachable -- in the old lift too, e.g.
func_0001084C's trampoline drain before its `b .` became an unconditional
call through a possibly-null pointer. Harmless while the title never takes
that path; compiling the lifted code with `-fno-finite-loops` would keep it a
hang.

### What is left

- The guest memory path is now most of what the lifted code spends on its
  own: every inline store checks the SPU coherence bitmap before and after
  the store (the bitmap pointer through the DLL's import, then the line's
  bit), every load two gates. Making that cheaper needs proof work on the
  SPU reservation protocol, not register work.
- Vector registers stay in the context: the VMX helpers take them by pointer
  and are out-of-line calls (forcing them inline was slower, 0061).
- The lift takes ~25 s longer: the pass runs while the lifter writes the
  source, in one process.
- Not tried on a real 4-core laptop; the fps here are of this PC with 27-31
  of its 32 processors busy elsewhere.
## Overlap: the present and the D3D12 calls off the critical path (patch 0067, branch `xlat-overlap`)

The goal is 60 fps on weak 4-core / 4-thread PCs (the i5-7300HQ report), the pool stage (id 30) included. A fight
frame there is three things in a row: the game's own part (its release -> its flip request), the translation of
its commands (the walker, on the ticker thread) and the walk from the translated flip to the next release. This
branch looked for every part of the translation and the present that can run beside the game's next frame
without changing anything the game sees.

### Where the game and the translation serialize

`PS3_LATENCY_LOG` stamps every frame: F (the game asked for its flip), X (the walker reached it), P (Present
returned), K (the next frame released). `build/xlatov/scripts/latsplit.py` turns them into a per-frame split.
Four processors (0x55 / 0x5500: four cores of CCD0, one thread each), `tools/slow_core.py --busy 40` on them,
Lili vs Asuka on the pool stage, the series to 0065 (medians, p99 in brackets; the PC was busy with other agents'
games, 14-30 of 32 processors):

| | game part | translation (F -> X) | X -> release | frame |
|---|---|---|---|---|
| all frames | 12.0 (37.7) | 4.5 (8.8) | 0.6 (7.7) | 17.8 (51.1) |
| frames that missed their vblank | 20.6 | 4.9 | 2.5 | |

- **The game flushes once.** A `PS3_SCHED_TRACE` of the pool stage (three frames alike): release -> the
  skinning kick at +5.7-6.4 ms -> `cellGcmSetUserCommand` at +9.4-12.2 ms and the flip request 5 us later (the
  only two moves of `put` in the frame) -> the walk +9.4 -> +13.6 ms -> the present -> the user handler -> the
  release at the vblank, +16.0 ms. The walker cannot start before; walking past `put` -- the "translate while the
  game builds" idea -- would read words the RSX never sees, and the game rewrites and rewinds them before its
  flush (above, "Is the handover wait necessary?").
- **The game waits for the RSX itself.** After its flip request it polls the flip status, and its next frame
  starts with the semaphores the flip and user handlers post; the user command is the last command of the frame,
  so on a PS3 its handler runs when the RSX has executed every draw. Releasing the game into its next frame while
  the translation still reads the frame's vertex buffers (the skinning rewrites them in the next frame),
  textures, fragment programs and index buffers would need a guard on the game's stores. The lifted code stores
  straight into guest memory, so the only guard is page protection -- and with it a file read into a protected
  page fails in the kernel, and a game thread stopped on a page while it holds an lwmutex a GCM handler needs
  (the handlers run on the walker's thread) would wait for ever. Not done: the flip still completes only after
  the translation has read and written everything of the frame.
- **What can move** is everything after the frame's last read of guest memory. That is the queued vertex
  fetches (drained when the walker reaches the flip) -- after them come the present (present copy, overlay,
  command list Close + ExecuteCommandLists, DXGI Present: 0.5 ms at the median, 1.4-1.9 ms at p90-p99, and for a
  late frame it sat between the translation and the release: X -> release 2.5 ms on average) and, during the
  walk, the D3D12 calls themselves (only host values).

### What changed

| change | switch | effect |
|---|---|---|
| **The present on the renderer thread.** When the walker reaches a flip it drains the frame's vertex jobs (the last guest-memory reads), follows a window resize or fullscreen switch (DXGI wants the window's own thread for those) and hands the frame to the new `rsx-render` thread: present copy, overlay, submit, Present, frame log run there while the flip completes and the game starts its next frame. Exclusive fullscreen presents on the walker as before | `RSX_XLAT_OVERLAP=1` (0 = off) | a late frame's X -> release from ~2 ms to ~0.2 ms |
| **The command-list calls on the renderer thread.** The walker records into an object with the command list's own interface (`libs/video/rsx_record_ring.h`): each call of the 30 methods the translation uses is copied with its arrays into a 4 MB ring, the renderer thread makes the real call while the walker goes on. Close, ExecuteCommandLists, fence waits and Reset (`ld_flush`, `ld_begin_recording`) and a present made on the walker take the real list over first (`ld_own_enter`: the ring is empty, every call made). The renderer thread sleeps whenever the ring is empty; the walker wakes it every 256 calls (~10 times a fight frame), at a present and before it waits for it | `RSX_XLAT_OVERLAP=2`, the default (1: the present only) | translation and walker CPU -0.1..0.5 ms; the renderer thread ~0.5 ms of processor time a frame |
| The next walk waits for the present (`rsx_live_draw_sync` in `cellGcm_rsx_process_fifo`); a display-buffer registration, a mid-frame flush, shutdown wait for the renderer thread themselves | -- | in fights the walk never waited (1-2 waits per 600 frames) |
| `[slow-frames]`: the present column is the walker's hand-off plus its waits for the renderer thread; the display lock pairs a handed-off present with the release of its own frame | -- | |
| `RSX_XLAT_OVERLAP_AB=N`: frames alternate every N between the mode and "everything on the walker"; every 1,000 frames of each kind a line compares the walker's processor time, the translation, the frame time and the frames over 17.5 ms -- the same game under the same load. `RSX_HITCH_LOG=1`: an `[xlat-overlap]` line every 600 presents | measurements only | |

The guest sees nothing new: the walker still writes every label, report, reference and `get` of the frame when it
walks them, before the flip; the flip completes when the walker reached it and the frame's guest reads are done,
as before; the command list gets the same calls in the same order.

### Results

**Interleaved A/B (the cleanest measure on a busy PC).** One game, `RSX_XLAT_OVERLAP_AB=8`: the frames switch
every 8 between the patch and "everything on the walker" (exactly the old path), so both kinds share the game, the
stage, the load and the processors; each line compares 1,000 fight frames of each kind. Four processors (four
cores, one thread each), Lili vs Asuka. "slow_core 72" (`tools/slow_core.py --busy 72`) is the weak-PC stand-in:
every thread of the game slowed alike to 37-52 fps, the 4 processors saturated (every thread competes, like the
i5-7300HQ's, whose cores are ~2.2-2.5 times slower than this 7950X's). Medians of the windows, before -> after, ms:

| build, run | windows | walker CPU per frame | translation | frame time, median | frames over 17.5 ms |
|---|---|---|---|---|---|
| **1.1.4 (with 0066)**, pool stage, slow_core 72 (39 fps) | 2 | 2.73 -> 2.43, 2.48 -> 2.25 | 7.94 -> 7.60, 7.63 -> 7.35 | 24.56 -> **23.53**, 24.32 -> **23.41** | 978 -> 950, 924 -> 878 |
| **1.1.4**, stage 20, slow_core 72 (51 fps) | 3 | -0.32..-0.36 | -0.32..-0.36 | 20.06 -> **19.09**, 19.02 -> **16.91**, 20.31 -> **19.64** | 766 -> 604, 585 -> 434, 779 -> 686 |
| 1.1.3 base, pool stage, slow_core 72 (46 fps), two masks | 4 | -0.19..-0.26 | -0.2..-2.3 | 23.85 -> 23.01, 20.55 -> 19.97, 24.08 -> 23.27, 19.96 -> 19.37 | -2..-21 % |
| 1.1.3 base, stage 20, slow_core 72 (46 fps), two masks | 4 | -0.21..-0.30 | -0.5..-2.3 | 23.88 -> 23.05, 20.96 -> 20.10, 24.17 -> 23.43, 20.08 -> 19.36 | -1..-23 % |
| 1.1.3 base, pool / stage 20 without slow_core (60 fps) | 6 | -0.14..-0.21 | -0.14..-0.21 | 16.68 = 16.68 (every frame on time either way) | 0-9 -> 0-8 |

- The frame median is 0.6-1.0 ms shorter (up to 2.1) wherever frames miss their vblank, 3-26 % fewer frames over
  17.5 ms; at 60 fps nothing changes but the headroom (translation -0.15-0.2 ms).
- Two parts: the present on the renderer thread (mode 1) leaves the translation as it was and releases a late
  frame ~0.2 ms after it was translated instead of ~2 ms (A/B mode 1 against 0, pool stage slowed: frame median
  24.40 -> 23.62 and 21.60 -> 20.58, frames over 17.5 ms 983 -> 960 and 927 -> 887); recording the calls through the
  renderer thread (mode 2) takes 0.2-0.4 ms more off the walker -- the display driver's time for ~2,000-2,700 calls
  a frame, less the packets' (A/B mode 2 against 1: translation 4.30 -> 4.10, 4.26 -> 4.06, 6.03 -> 5.61 ms).
- The renderer thread's processor time: ~0.3 ms a frame with mode 1, ~0.5 ms with mode 2 (~150 context switches a
  second). The first version of mode 2 woke the thread every 16 calls and let it spin 300 pauses between them:
  ~2 ms a frame and 700-1,400 switches a second, and on saturated 4 processors (slow_core 60) paired runs lost what
  the walk gained (pool stage 53.9 -> 52.4 fps); woken every 256 calls with no spin it gains there (rows above).

**Paired runs against integration-114** (the same `t5dr_game.dll` with 0066 for both runtimes; `tools/fight_bench.py`
on 0x55 / 0x5500, masks swapped every round, slow_core 72 on each; the PC was busy with other agents' games -- up to
5 others and 2 compilers -- so the stand-in ran at 17-48 fps and the mask moved fps by up to 30 %; fps geometric mean
over the rounds, p99 median of the rounds):

| stage | rounds | integration-114 | + 0067 | faster in | frames over 17.5 ms |
|---|---|---|---|---|---|
| pool (30), slow_core 72 | 4 | 27.2 fps, p99 101.9 ms | **27.4 fps, p99 81.7 ms** | 3 of 4 | 1,903 -> 1,965 |
| 20, slow_core 72 | 4 | 36.0 fps, p99 42.8 ms | **37.5 fps (+4.4 %), p99 35.4 ms** | 2 of 4 | 2,306 -> 2,522 |
| pool, no slow_core | 2 | 59.85 fps, p99 22.8 ms | 59.91 fps, p99 22.4 ms | 2 of 2 | 588 -> 564 |

Earlier paired sets on the 1.1.3 base (quieter PC): pool stage slow_core 40 56.1 -> 57.6 fps (+2.8 %, 3 of 4), slow_core
72 42.5 -> 45.4 (+6.8 %, 3 of 4, p99 32.1 -> 27.9 ms); stage 20 slow_core 72 40.2 -> 42.5 (+5.6 %, p99 31.2 -> 28.2).
Paired runs on this PC cannot resolve a 3 % change against the other programs' load; the A/B above can.

### Same picture, same game

**Pictures.** Lockstep pairs (`tools/rollback_net_test.py --mode1 off --mode2 off`, Jack-5 vs Bryan, Native): the
old runtime as host and this branch as joiner run the same game frames, and at lockstep frames 300, 900 and 1500
both dump every live surface and the backbuffer (`T5_NET_SHOT` + `LD_SURF_DUMP`), compared byte for byte
(`build/xlatov/scripts/paircmp.py`). As in 0062's check, the stages' animated parts follow the frames each game ran
since it started, so only pairs whose two renderer frame counters matched can be identical; a pair whose counters
differed was run again:

| base | stage | pair (host / joiner) | counters | result |
|---|---|---|---|---|
| **1.1.4** (integration-114, same game DLL) | 30 (pool) | old / new | equal | **15 of 15 identical** (3 shots x 4 surfaces + backbuffer) |
| **1.1.4** | 20 (glow) | old / new | equal on the 7th try | **21 of 21 identical** (6 surfaces + backbuffer x 3) |
| 1.1.4 | 20 | old / new, 6 tries | 1-6 apart | 9 of 21: shadow map and glow buffers identical, the animated puddles apart |
| 1.1.3 | 30 | old / new, old / old | equal | 15 of 15 identical, both |
| 1.1.3 | 34 (stage blur, depth snapshot, compute) | old / new, old / old | equal | 15 of 15 identical, both |
| 1.1.3 | 20 | old / old | equal | 21 of 21 identical |
| 1.1.3 | 30 | new / new | 1 apart | 3 of 15: shadow maps identical, the pool's water apart -- as any two games a frame apart |

**Same game.** Rollback pairs (RTT 150 +-5 ms, 3 % loss, delay 6, two matches: Asuka vs Lili on stage 20, then
on the pool stage; host on 0x00FF0000, joiner on 0x55000000) and lockstep pairs (RTT 30, 1 % loss); "old" = the
integration-114 runtime with the same `t5dr_game.dll` (the same code ID):

| base | pair (host / joiner) | mode | frames compared per side | rollbacks per side | result |
|---|---|---|---|---|---|
| **1.1.4** | new / new | rollback | 10,800 | 1,277-1,370 | 0 mismatching, the same two result hashes on both PCs |
| **1.1.4** | old / new | rollback | 10,800 | 1,306-1,375 | the same |
| **1.1.4** | new / new, new / old | lockstep | 10,800-11,400 | -- | 0 mismatching, the same hashes |
| **1.1.4** | e2e `cross_build_pair` (lobby, a match + 2 rematches, this build / integration-114) | rollback, lockstep | -- | -- | PASS, 72 checks each, the same hashes |
| 1.1.3 | new / new, old / new, new / old | rollback | 10,800 | 1,316-1,378 | 0 mismatching, the same hashes |
| 1.1.3 | new / new, old / new, new / old | lockstep | 10,800-11,400 | -- | the same |

Nothing the patch adds writes guest memory (`tests/test_xlat_overlap.py` checks the patch): what the game computes
cannot change, so the code ID stays (no CODE_VERSION bump) and two players may run either build.
`tests/c/xlat_ring_test.c` (built against the patched source by the test): 300,000 random calls of all 30 recorded
methods with every array size the translation passes, NULL pointers, render-target ranges, clears with and without
rects, plus presents and both syncs, through a 16 KB ring (it wraps thousands of times and fills); every call
reaches the replaying thread once, in order, with its arguments (the two logs byte-identical); copies of the ring
with a lost root constant, a render-target list recorded as one handle and a lost copy box fail it, one that never
publishes hangs (the test's timeout reports it). Smoke quick on the final build: exit 0 (81 PASS, two fps WARNs with
7 other games running). `tests/` 809 OK; `tools/prepare_ps3recomp.py` applies all 50 patches.

### Not done

- Overlapping the translation with the game's own frame: see above -- the game's single flush and its wait for
  the user command leave no room without lying to it about the RSX's progress.
- A second translation thread: the walk, the dispatch and each draw's translation share the register file and the
  renderer's caches; the D3D12 calls were the separable part, and they are cheap after 0062 (recording them
  through the ring saves only 0.15-0.4 ms of a 3-4.5 ms translation).
- Not tried on a real 4-core laptop.
