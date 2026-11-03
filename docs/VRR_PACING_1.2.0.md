# 1.2.0 VRR pacing candidate

This is an opt-in host presentation experiment, not a measured performance result. The supplied player observations are approximately alternating 14/19 ms frames, flat output under an external 59.9 limiter, and a game-thread tail affecting approximately 0.5% of frames. They have not been reproduced in this mirror. The intended clock remains **60000/1001 Hz**, approximately **16.6833 ms** per frame.

The implementation is the next patch in the existing runtime series, `patches/ps3recomp/0103-vrr-pacing.patch`. `tools/build_game.py` discovers patches in filename order; no patch manifest or simulation compatibility version change is required. The source-only stall investigation and maintainer capture procedure are in [VRR_STALL_PROFILE_1.2.0.md](VRR_STALL_PROFILE_1.2.0.md).

## What must remain identical

Pacing controls host release and presentation times. It must not change guest time steps, simulation frame numbers, agreed input delay, pad contents, rollback horizons, match rules, guest-memory ownership, or replay rules. Preserve the late main-thread pad sample and the existing FIFO/renderer handover. A presentation slot skipped during late recovery is host bookkeeping; it must not drop a guest frame. A requested rollback time-sync skip must still be honored exactly once.

The application marks network accounting and scene-barrier contexts through a host-only
`cellGcm_vrr_external_hold()` serial. The runtime compares that serial across a frame before accepting a
budget sample. Conservative online tagging can freeze adaptation even when the peer was immediately ready;
this is deliberate because an unclassified peer hold must not inflate the local rendering budget. These
markers are not a phase profiler and do not identify the cause of the supplied rare stalls.

## Comparison procedure in the real project

`PS3_VRR_PACING=0` selects the existing path and is the default. `1` selects timer-only comparison;
`2` requests controlled presentation with `RSX_PRESENT_MODE=tearing` and renderer overlap enabled.
Controlled presentation is gated off for exclusive fullscreen, display lock and a custom `PS3_VBLANK_HZ`.
This is explicit opt-in, not automatic VRR detection. Confirm the effective mode in the log for each run.

`PS3_VRR_BUDGET_MS` freezes the release-to-ready budget for controlled comparisons; accepted values are
positive and below 16.68 ms, then clamped below one nominal period. Without a fixed value the initial budget
is 4 ms, with a rolling p99 local ready-cost estimate plus a 0.2 ms guard, prompt increases and slow reductions.
Choose the smallest stable measured budget, especially when online tagging freezes adaptation. It is not a
claim that 4 ms meets the player's latency gate. `PS3_VRR_SPIN_US` defaults to zero, is capped at 200 us, and
stays zero in laptop power mode. High-resolution timer failure falls back to an ordinary timer/wait and must
be visible in the timing report.

Analyze a captured log without launching the game using:

```text
python tools/perf_compare.py pacing <frames.csv> --series <intervals.csv>
```

Run that command separately for off, timer-only and controlled-present logs; save its JSON output alongside
each capture in the real project. `--series` writes a separate timeline CSV. Old frame logs remain readable,
but lack actual Present-entry measurements and cannot supply the new distribution retrospectively.

Keep all runtime captures, player logs, game data and screenshots out of this source mirror. A maintainer must first apply the full series to the pinned dependency in the real project and build there. Do not infer patch application or compilation success from patch text review.

Use the player's visible, focused VRR setup. Record monitor refresh and VRR range, actual present mode, fullscreen/borderless/window mode, driver options, frame slots, power mode and CPU load. Disable Special K and driver/external frame caps for the main comparison. Keep the fight, stage, resolution, warm shader state and input-delay setting unchanged. Alternate baseline, timer-only and controlled-present runs; use at least ten steady minutes per configuration, both quiet and under realistic load. Test the external 59.9 limiter only as a separate diagnostic comparison.

Use `PS3_FRAMELOG`, `PS3_LATENCY_LOG` and `PS3_GAME_THREAD_LOG` on the same QPC timebase. Collect short scheduler traces separately around tail events rather than continuously flushing diagnostic output in a measured fight. Repeat logging on/off to quantify its overhead. The old frame-log `dt_us` remains the interval between the existing pre-Present stamps; it must not be relabeled as the interval between actual DXGI call entries. A Present return and DWM timing are also not scanout or photon timestamps.

Inspect actual Present-entry intervals for both all valid frames and the ready/on-time steady subset. Report median, p95, p99, p99.5, p99.9, worst, standard deviation, adjacent-interval correlation, counts outside 16.6833 +/-0.5 ms and counts above 17.5/20/33.4 ms. Report misses, local stalls, intentional time-sync skips, discontinuities and missing log rows separately. Do not make a flat graph by silently excluding slow frames. Check the time series for the original 14/19 alternation and short catch-up pairs following late frames.

## Player-PC acceptance gates

- Present-call **and independently measured displayed-frame** timing are approximately flat at 16.6833 ms in warm fighting without Special K or another limiter. The initially proposed +/-0.5 ms tolerance needs platform evidence; document any adjustment. Check duplicates, dropped pictures and driver/DWM queuing.
- Input delay is no worse at the same netplay input-delay setting: compare random-phase pad event/release to the first reacting presented frame and an independent visible-reaction measurement at p50, p95 and the tail. A flat frame graph alone does not satisfy this gate. Revise the release budget or keep the mode experimental if delay regresses.
- Late game/translation frames present once when ready, retain slow-PC throughput, and recover without short catch-up bursts. Resume, occlusion, resize and monitor changes invalidate old targets. Fixed-refresh display lock, unsupported backends, timer failure and power-saving fallback retain usable behavior.
- Real pair tests in lockstep and rollback, direct and relay, asymmetric fast/slow PCs, delay/jitter/loss, repeated rematches and replay playback show **0 mismatching simulation frames**, identical agreed outcomes, and no missing or extra simulation frames. Include different pacing settings on the two PCs and rollback time-sync skips.

The rare game-thread stall is a separate acceptance item: classify the worst frames using wall time versus CPU/cycles and phase timelines before proposing any game/runtime optimization. Average GPU occupancy of 6% does not rule out an individual GPU, fence or Present stall.

## Verification boundaries

Repository work is limited to source edits, static inspection and authored regression tests. No dependency checkout, patch-series application, compilation, test execution, game run, server contact or player measurement is performed here. The maintainer must run the game-free regression tests, then apply/build in the real project, then satisfy the display, input-latency and pair-determinism gates above. Until those checks pass, application/compilation and the performance goal remain unproved.

Parser fixtures are in `tests/test_perf_compare_vrr.py`. Network-budget wiring checks are in
`tests/test_vrr_network_budget.py`; the standalone `tests/c/netplay_fuzz.cpp` harness also checks online
versus local budget tagging behavior. `tests/test_vrr_pacing.py` extracts the exact policy and Windows wait
headers from patch 0103 for synthetic C harnesses in `tests/c/vrr_pacer_test.c` and `tests/c/vrr_wait_test.c`.
Those cover rational accumulation, ordinary jitter, alternating work, late recovery, slow local work,
immutable target copies, skipped ticks, reset, early wakes, timer failures and cancellation without game data.
These are authored regression checks, not recorded passes. Source checks and fake OS tests cannot establish
real Windows timer behavior or renderer scheduling safety.
