# Render translation performance (patch 0023)

Tekken 5 DR builds a whole frame of RSX commands (~750 KB, ~840 draws in a
fight), flushes it once, and then waits for the flip -- i.e. until our live
D3D12 engine (`libs/video/rsx_live_draw.c`) has walked and translated every
command. Game CPU and translation are therefore serialised, and the frame
fits in a vblank only when `game CPU + translation + present` stays under
16.7 ms. Patch 0023 cuts the translation and removes the first-fight hitch.
Every change has a switch; all are on by default.

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
