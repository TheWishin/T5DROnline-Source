# 1.2.0 VRR: read-only game-thread stall profile

This is a source audit and a maintainer-local measurement protocol. No game,
build, profiler, test, server connection or runtime capture was run for this
report. The player's approximately 14/19 ms alternation, flat output with a
59.9 limiter, 0.5% stalled frames, 2.5 ms median game part and 6% GPU use are
supplied observations. They have not been reproduced here. There is no measured
stall attribution, latency result or verified VRR improvement in this report.
The nominal host period remains 1001/60000 seconds, approximately 16.6833 ms.

## What the existing probes establish

Patch references are physical lines in the patch file, followed by the
upstream function. They are evidence in this mirror, not an applied dependency
tree or a claim that the maintainer's current upstream revision is identical.

| Source | Available evidence and limitation |
|---|---|
| `patches/ps3recomp/0034-latency.patch`, `runtime/platform/lat_log.h`; `docs/RENDER_PERF.md:301` | QPC event stream: E = pad sampler edge, R = read handing over changed buttons, B = main-thread late sample, F = guest flip request, X = walker reaches flip, K = completion releasing the next game frame, P = Present return. P is neither call entry nor a scanout timestamp. |
| `patches/ps3recomp/0061-game-thread-cpu.patch:10`, `cellGcmSys.c::gt_log_flip`; `tools/game_thread_times.py:29` | Flip sequence, request QPC, release QPC, thread cycles and thread ID. The parser uses consecutive sequence/same-thread rows, computes release-to-request wall time and cycle deltas, and rejects a release outside the corresponding request window. CPU covers work between requests, including snapshots/re-simulation; it is not a phase-by-phase CPU timer confined to release-to-request. |
| `patches/ps3recomp/0015-thread-tuning.patch:418`, `runtime/platform/host_sched.c/.h` | `PS3_SCHED_TRACE` has QPC, event kind, thread tag and argument; semaphore wait/post, lwcond wait, syscall/HLE entry/exit, SPURS job list/chain, FIFO, handler, flip and present events locate host waits. This is instrumentation of calls, not an OS ready-to-run or context-switch trace. |
| `patches/ps3recomp/0061-game-thread-cpu.patch:483`, `boot_main.cpp::host_prof_thread`; `tools/host_prof.py` | `PS3_HOST_PROF`, `PS3_HOST_PROF_WHO=main`, `PS3_HOST_PROF_DEPTH=48`, `PS3_HOST_PROF_AT=a,b`, `PS3_HOST_PROF_US=1000` capture host stacks. `--busy` filters wait samples; `--focus NAME --callers` can explain a candidate subtree. A sampled share is not a per-frame duration. The sampler suspends threads, so compare overhead and do not use its run as the sole latency proof. |
| `patches/ps3recomp/0005-frame-pacing.patch`, `rsx_live_draw.c::ld_pf_frame_log`; later renderer patches | Existing `dt_us` starts at `present_begin`, potentially before other present work. `xlat_us`, `fifo_cpu_us`, GPU timestamps and allocator/fence/present waits separate work downstream of F. Use the new actual-call-entry interval alongside `dt_us`; retain both meanings. |
| `src/rollback/rb_net.cpp:730`, `:783`, `:851` | Latency M marks restore/rollback start, Q marks completion with wall/CPU ms, N marks boundary with re-simulation/early/fighting flags. The `rbnet` statistics include depth, snapshot and re-simulation cost. Correlate by QPC and explicit IDs; a simulation frame number and a displayed flip sequence are different domains. |
| `patches/ps3recomp/0080-rollback-smooth.patch:41`; `src/rollback/rb_net.cpp:800` | `cellGcm_skip_ticks(n)` intentionally gives up exactly n eligible flip-completion ticks. Y marks the skipped tick. It must remain separately counted; a pacer must not compensate it away or label it as a local CPU miss. |

The current game-thread parser reports p50/p90/p99/mean only. Its CPU estimate
divides `QueryThreadCycleTime` deltas by a start-up TSC calibration in the log
header; clock, CPU migration and calibration context matter. Do not treat
wall-minus-that-estimate as exact blocked time. Confirm suspicious tails using
per-thread processor-time counters and an OS scheduling trace.

## Classify a slow frame before changing code

For each candidate retain its preceding and following frames, and record the
following timeline on one QPC timebase. A missing event means unknown, not zero.

| Phase | Source evidence and next distinguishing measurement |
|---|---|
| Scheduled release -> K -> main thread actually runs | Compare the new scheduled/actual release stamps, K, semaphore post/return and first main-thread B/HLE/syscall event. A gap before the first instrumented event only bounds wake delay: use OS ready-to-run/context-switch events to distinguish preemption from an uninstrumented execution span. |
| Main-thread work -> SPURS kick -> job-list completion | Existing `HS_EV_JC_KICK` and `HS_EV_JOBLIST0/1` bracket job-chain/list work. Inspect helper thread stacks and the main thread's help/wait behavior. Low main-thread CPU does not exclude slow work on helpers. High CPU needs a busy-stack profile, including lifted code and runtime calls; it does not justify a timer change. |
| Draw-request coordination | Pair lwcond/lwmutex/syscall spans on the main thread with the producer's activity. `docs/RENDER_PERF.md:1197` describes this chain from an earlier measured machine. Its 0.4-0.6 ms waits are historical evidence, not this player's result. |
| Net input/scene barriers | `src/netplay/netplay_core.cpp::scene_barrier`, `src/netplay/t5_hooks.cpp` and rollback boundary waits can delay progress deliberately. Record network mode, peer wait, barrier state and transport conditions; keep these outside a local render-budget estimator. A wall-time gap here is not proof of a scheduler stall. |
| Snapshot/restore/re-simulation | Join M/Q/N, depth/cost counters and `src/rollback/rb_net.cpp`/`rb_state.cpp` activity. Snapshot work can run before the release in early-commit paths. Assign costs to their actual execution window; do not double-count them as both game work and idle wait. |
| F -> X -> submit-ready | Compare flush/flip request, FIFO walk and `fifo_cpu_us` with `xlat_us`. Extra wall with stable walker CPU suggests contention/preemption/waits; increased walker CPU points to translation work. This is downstream of the game's F timestamp. |
| Renderer ownership/ring/allocator wait | Patch 0067's `rsx_record_ring.h::ld_rq_wait`, `ld_xo_sync` and `ld_xo_sync_present` wait for ownership, including completion of a handed-off Present. Its recorder-full waits can backpressure the walker. A deadline wait inside Present can therefore delay subsequent translation even though it runs on another thread. Preserve those waits and measure the cost; removing them would invalidate buffer ownership. |
| Submit-ready -> real Present entry -> return -> display | Separate target wait, wake error, swap-chain latency wait, allocator/fence/GPU wait, call duration and driver/display timing. Average 6% GPU use cannot rule out an isolated fence or driver stall. A regular entry interval does not establish regular scanout or latency neutrality. |

Patch 0085 enables semaphore ACQUIRE on Windows, with an at-or-past comparison
for the title's monotonically increasing label during rollback. Its FIFO pump
must remain responsive while an acquire is waiting. Earlier prose saying the
game has no GPU wait describes an older measured configuration; it must not be
generalized into a proof that no current frame can stall in renderer-related
coordination. Do not bypass ACQUIRE or the guest-buffer handover to flatten the
graph. `docs/RENDER_PERF.md:96` explains why the next game frame can overwrite
vertex buffers, textures and programs still needed by translation.

Potential explanations remain hypotheses: main-thread preemption, helper
completion, draw-request waits, net/barrier holds, rollback cost, FIFO/ring
backpressure, timer wake error, driver waits or logging overhead. The existing
source establishes where to distinguish them, not which caused the 0.5% tail.
No new guest address is proposed or inferred.

## Maintainer-local capture and comparison

Keep all game data and runtime captures in the real project, outside this
mirror. The steps below are work still to do on the player's setup.

1. Record build identity, Windows/driver version, GPU, CPU/power policy, display
   refresh and VRR range, confirmed VRR engagement, window mode, sync/tearing
   flags, frame slots and overlap mode. Keep stage, fighters, resolution,
   graphics, netplay input-delay setting and reproducible input fixed. Use a
   visible focused game. Disable Special K and external/driver caps for both
   baseline and new-pacer comparisons. A separate 59.9-cap run is diagnostic.
2. Interleave off/on/timer-only runs rather than making one long off run then
   one long on run. Warm shaders first and separate loading, cold work and
   steady fighting. Collect at least ten minutes per steady configuration
   (about 36,000 frames; approximately 180 events if 0.5% persists), repeat on
   a quiet PC and under realistic background load. Record every discontinuity,
   focus loss, mode switch and intentional skip instead of silently trimming
   them into an improved average.
3. Start with minimal timing, then compare with `PS3_FRAMELOG`,
   `PS3_LATENCY_LOG` and `PS3_GAME_THREAD_LOG` enabled. Use unique local paths
   for every run. Match QPC frequency, thread and flip identity; do not join
   rows solely by row index. Compare logging on/off overhead before combining
   all probes. Existing game-thread logging writes on the main thread and
   flushes every 64 flips (0061); this is itself a candidate source of tails.
4. Use a narrow `PS3_SCHED_TRACE`/host-stack profile window to classify the
   slow frames. The existing scheduler trace uses a bounded 4M-record/64 MB
   buffer with a background flusher and stops at capacity; it is not a rolling
   pre-trigger ring and cannot promise ten minutes of detailed events. Check
   trace-full warnings and record coverage. A diagnostic trigger ring must
   explicitly retain pre/post-stall context and report overwrites/drops; no
   synchronous per-frame flush should be added on the critical path.
5. Where the runtime events cannot explain wall time, use a maintainer-local
   OS trace with thread CPU, ready time/context switches, core migration,
   effective clocks, hard faults, allocations/file I/O and DPC/ISR activity.
   Resolve stacks with symbols from the exact build. Profile busy and waiting
   time separately, and repeat with intrusive profiling disabled.
6. For each measured phase report n, p50/p95/p99/p99.5/p99.9, worst, counts above
   17.5/20/33.4 ms, longest consecutive stall run and ordered timelines for the
   worst frames. Include the number of invalid/missing rows. At a 0.5% event
   rate p99 alone can miss the whole issue. Record which phase first deviates
   on every tail, with local scheduling, network/time-sync and cold-work
   classes separate.

For pacing compare actual Present entry intervals against 16.6833 ms, their
median/p95/p99/p99.9, standard deviation, adjacent-interval correlation and
count outside the initial +/-0.5 ms tolerance. Negative adjacent correlation
is useful for the reported short/long alternation, but it does not establish
the cause. Report all frames, misses, skipped ticks and discontinuities first;
also show the explicitly defined ready/on-time steady subset. Compare release,
submit-ready, entry, return and independently measured displayed intervals to
locate the first appearance of the 14/19 ms pair. Present count and independent
display evidence must detect duplicated, dropped or queued pictures; Present
return and a DWM estimate are not photon timestamps.

## Gates before claiming the goal

The player's PC must show steady approximately 16.7 ms actual-call and displayed
intervals on its visible VRR path without an external limiter, with all tails
and skips still accounted for. A good average FPS is insufficient. Test
fullscreen/borderless, high-refresh VRR/non-VRR, fixed 59/60 display lock,
integrated/dedicated GPU, power-saving/timer fallback, focus/minimize/restore,
monitor changes, CPU/translation/GPU load and deliberately late frames. Late
recovery must present ready pictures once, avoid catch-up bursts or an extra
whole-period wait, and preserve slow-PC throughput.

Input delay is a measured release gate: retain the main-thread late pad sample
and compare random-phase E/R -> first reacting presented frame plus independently
measured visible response at p50/p95/tail, with unchanged netplay input delay.
`tools/latency_test.py` defaults to a minimized window and estimates display
time from DWM plus a GPU-copy allowance; its default result cannot prove the
visible VRR latency gate. Use a focused visible protocol and independent
display/latency measurement in the real project. A repeatable regression means
revise the budget/release phase or keep the feature experimental and off.

Display-only intent must be proved on a real pair: lockstep and rollback,
direct/relay, asymmetric PCs and different host pacing modes, delay/jitter/loss,
rollback time-sync skips, rematches and replay playback. Require **0 mismatching
simulation frames**, identical outcomes and no extra/missing simulated frames.
Keep guest dt, frame numbering, rollback horizon, input-delay rules, handler
ordering, ownership barriers and synchronized input semantics unchanged.

This source audit cannot prove patch application to the maintainer's current
dependency, compilation, timer behavior, VRR engagement, pipeline overlap,
tail attribution, presentation improvement, input latency or pair determinism.
Those require the maintainer's real dependency/build and the game/PC runs
above; none has been claimed as passed here.
