# 1.2.2 displayed-frame pacing continuation

The previous round's changes remain in the tree. Its FPS and CPU results are
historical evidence, not measurements of the stricter display-pacing target.
No commit or push is part of this work. Large artifacts stay under ignored
`build/perf122/pacing/` and `build/perf122/pacing-audit/`.

## Evidence requirements

- Timing runs atomically reserve two coordination slots, release partial
  reservations while waiting, and release both after each run or failure.
- Games use private HOME/config directories, mute, BelowNormal priority and
  background windows. `PS3_WINDOW_BACKGROUND=2` leaves an unfocused window
  non-minimized; `1` retains the previous minimized behavior.
- Use baseline generated code or the retained AVX1 level, force software FMA
  (`PS3_FP_SOFT_FMA=1`, `PS3_CRT_FMA3=0`), tier 1 and the slow-GPU hook. No
  live servers or real accounts. Online peers/proxy bind to localhost.
- A physical-display claim needs successful, non-occluded presents and complete
  DXGI display observations. Missing/occluded statistics are unavailable, never
  zero repeated refreshes. Present-call, guest-flip and live-boundary times are
  separate CPU diagnostics.
- Stand-in CPU calibration requires measured native single-thread integer AND
  scalar-FP throughput at 55-60% of the unthrottled Zen 4 core. Bracketing
  unthrottled samples must stay within 5%. Duty percentage alone is insufficient.

## Runs

Timing acceptance is blocked. The rebuilt host passes and both DLL levels are assembled, but no accepted CPU calibration or new game capture is available. This ledger is not an acceptance statement.

| artifact / run | result |
|---|---|
| `build/perf122/pacing-audit/test_latency_async.log` | PASS: actual runtime logger with blocked disk sink, four producers, 80,000 events; bounded drops accounted and surviving order preserved. |
| `build/perf122/pacing-audit/apply-check.log` | PASS: patch 0119 applies to prepared prior series. |
| `build/perf122/pacing-audit/AUDIT.md` | Source audit of display timing, summary bounds and first-sight work. |
| `build/perf122/pacing/historical-occluded-analysis.json` | Historical AVX pool capture rejected as display evidence: 1,006 occluded rows in the selected 18-second window, no valid display observations. Not a calibrated i3 run. |
| `build/perf122/pacing/historical-hitch-attribution.json` and original `build/perf122/pairs/avx_pair_2c4t_s30_r1/after/game.log` | Historical worst selected interval attributed to first-seen pipeline creation/library path (key `b9ab15efb7fe763e`), HLSL compile counter zero. Diagnostic attribution only; not new stand-in/display performance evidence. |
| `build/perf122/pacing/build.log` | **Not run**: one-slot host-build reservation expired after 900.875 s. All three slots occupied; owner strings retained. No build result or timing number. |
| `build/perf122/pacing/build-retry.log`, `build-retry.json` | **PASS**, exit 0: full host rebuilt/linked with 0119 and accurate rollback timing label. Acquired one slot after 530.485 s; total wait+build 550.954 s. Compiler warnings retained. Lock released; real configuration SHA256 unchanged. |
| `build/perf122/pacing/calibration/initial-link-failure.log`, `build.log`, `attempts.json` | Tiny native probe first link failed (`_fltused`); marker definition corrected it and retry built successfully. This is not a game build or performance result. |
| `build/perf122/pacing/calibration/console.log`, `calibration-timeout.json`, `reservation-status.json`, `attempts.json` | **Not measured**: two-slot calibration reservation expired after 900 s, exit 1, zero timing samples. Occupied locks retained in the status file. No accepted duty. |
| `build/perf122/pacing/calibration-retry/` | **Not measured**: second calibration reservation expired after 600 s, exit 1, zero samples. `calibration.json`, `console.log`, `reservation-status.json`, `attempts.json` retain the result. |
| `build/perf122/pacing/calibration-final/` | **Not measured**: third attempt ended before its 240-s bound with Windows `PermissionError` on `HEAVY2.lock`, exit 1, zero samples. This was lock access/sharing contention, not a completed calibration or a timeout. `calibration.json`, `console.log`, `reservation-status.json`, `attempts.json` preserve it. Lock-sharing/error cleanup was subsequently corrected and tested; no fourth timing attempt. |
| `build/perf122/pacing/test_frame_pacing.log` | PASS: 14 analysis tests, including visibility, stale statistics, boundary gaps, counter wrap, coverage and threshold arithmetic. |
| `build/perf122/pacing/test_calibration.log` | PASS: 4 calibration/slot-ownership tests. |
| `build/perf122/pacing/calibration-unit-final/tests.log`, `result.json` | PASS: final 4 calibration tests and py_compile after lock-sharing/entry-failure cleanup fixes; real config unchanged; no owned stale locks. |
| `build/perf122/pacing/test_fight_bench_rows.log` | PASS: 4 existing CSV drain/window tests. |
| `build/perf122/pacing-audit/test_warmup.log` | PASS: 28 warm-up tests; one existing platform-specific skip. |
| `build/perf122/pacing-audit/unit-home-guard.json` | PASS: real user configuration SHA256 identical before/after isolated unit suites. |
| `build/perf122/pacing-audit/native-home-guard.json` | PASS: final native writer/dump/shutdown regression, actual runtime source, configuration hash unchanged. |
| `build/perf122/pacing/pilot-driver.log`, `pilot-status.json` | **Not run**: prerequisite wait expired after 20 minutes. Host build completed, accepted CPU calibration unavailable. No game started or timing slot reserved. The proposed short window would validate configuration, not steady-minute acceptance. |
| `build/perf122/pacing/required-matrix-status.json` | Explicit 72-case baseline/AVX1 x full/4c4t/i3 x stages 20/30 x offline/RTT50/RTT150 x 60/144-hook manifest. Every requested new metric/state-proof field is null while unmeasured; no old FPS data substituted. |
| `build/perf122/pacing/binary-hashes.json` | Rebuilt host, baseline/AVX1 DLL and retained probe patch hashes. |
| `build/perf122/pacing/bin/before/`, `bin/after/`, `standin-assembly.json` | **Assembled**: same freshly rebuilt host with baseline software-FMA DLL / retained AVX1 DLL. Hashes and required test settings recorded. Calibration and game runs remain unperformed; assembly is not performance evidence. |
| `build/perf122/pacing/final-config-guard.json` | PASS: real user configuration SHA256 still unchanged. |

## Reproduction

Use `python tools/calibrate_slow_core.py --cpus 0xF000 --wait-seconds 900
--out build/pacing/calibration` and retain its accepted duty, period, mask and
raw samples. The native probe is baseline SSE2 without AVX2/FMA; it measures
scheduling availability, not Ivy Bridge IPC/cache/memory/SMT behavior.

For each fight use `tools/fight_bench.py --polite --cpus 0xF000 --skip 24
--secs 84`, the accepted `slow_core.py` duty on the same mask, Old PC settings
(`PS3_INTERNAL_RES=lowest PS3_STAGE_BLUR=0 PS3_SHADOWS=0 PS3_EFFECTS=0`),
`RSX_TIER1_PATH=1 RSX_TEST_SLOW_GPU=16000000,256`, and separate frame/latency
logs. Use the same host/cache and input schedule for both DLL levels.

Analyze with `python tools/frame_pacing.py <frames.csv> --window-json
<result.json> --latency <lat.log> --json <pacing.json>`. A supplied
`--display-hz` must describe the physical monitor, never `RSX_TEST_DISPLAY_HZ`.
The latter tests wait policy; it does not switch the monitor to 144 Hz.

For local rollback use `tools/rollback_net_test.py --polite --latlog --mash`,
RTT 50/150, 3% loss, and `T5_NET_BIND=127.0.0.1`. Give both peers separate
frame logs, homes and disjoint masks. Compare hashes, not only FPS.

## Changes in this continuation

Earlier-round edits are preserved. The continuation changes these files:

- `patches/ps3recomp/0119-display-pacing-probe.patch`
- `src/rollback/rb_net.cpp` (labels live-boundary times accurately)
- `tools/frame_pacing.py`, `tools/calibrate_slow_core.py`, `tools/slow_core.py`
- `tools/rollback_net_test.py`, `tools/shader_warmup.py`
- `tests/test_frame_pacing.py`, `tests/test_latency_async.py`,
  `tests/test_slow_core_calibration.py`, `tests/test_background_warmup.py`
- `docs/RENDER_PERF.md`, `docs/WEAK_PC.md`, `docs/PERF122_RUNS.md`,
  `docs/FRAME_PACING122_RUNS.md`

Proposed commit message: `perf: validate display pacing and remove latency-probe I/O hitches`

Player-facing change: background shader warm-up now includes the pool and
stage 20; performance diagnostics distinguish physical display observations
from CPU/present-call timing. No claim of a measured FPS gain accompanies
the code/test changes alone. CHANGELOG.md is unchanged.

## Acceptance gates still open

- Accepted 55-60% native CPU calibration on the i3 mask.
- All displayed-frame before/after rows, per-minute thresholds, band shares and repeat/skip counts from the required matrix.
- New rollback/lockstep pairs and replay/state proof with the rebuilt host (no new simulation logic was intentionally changed).
- Real Fermi scaling, real Ivy Bridge behavior, RAM pressure and a physical 144 Hz display remain outside what the fixed compute/duty-cycle hooks can reproduce.

All owned build/queue processes have ended. No test game or local-network pair was launched in this continuation. No owned heavy lock remains; other owners' locks were not removed. The requested constant-frame and 60-FPS targets remain unverified.
