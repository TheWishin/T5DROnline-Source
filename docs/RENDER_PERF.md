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
cuts the per-frame CPU work; the launcher's **3D resolution** setting
(`PS3_RENDER_SCALE`) is for weak graphics.

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
| `PS3_RENDER_SCALE=0.25..1` (or 540/360): every live render target below the guest size; multiplies `PS3_RES_SCALE` | launcher **3D resolution** | GPU, below |
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
cheaper re-simulation, not more threads.

### GPU: 3D resolution

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
