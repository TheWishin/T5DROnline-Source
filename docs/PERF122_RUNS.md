# 1.2.2 performance work: run ledger

Working tree: `perf-122`, based on `integration-121` at `f81432c4`.
This ledger records the local evidence for the five requested old-PC levers.
Paths below are relative to the repository unless stated otherwise. Large logs,
executables, profiles, generated source and game-derived pictures remain under
ignored `build/`; they are not files to publish. Analysis and retained results
belong in [RENDER_PERF.md](RENDER_PERF.md).

This is the completed ledger for the earlier optimization round. The subsequent
display-pacing/i3 calibration work has its own ledger in
[FRAME_PACING122_RUNS.md](FRAME_PACING122_RUNS.md); the earlier gates below do not
establish the stricter displayed-frame targets. Synthetic correctness tests and build times are
not evidence of a frame-rate gain. All accepted measurements, invalid attempts
and cancelled reservations are identified below; no required gate is pending.

The only retained new runtime patch is `0116-avx-software-fma.patch`. Its
eight-pair main-thread CPU gate and cross-build state proof are completed below;
the fresh-count PGO comparison is complete and rejected: no clear benefit over
the current profile. Candidates 0117 (address waits) and 0118 (per-slot descriptor validation) were rejected after the initial
12-run matrix. Their source patches, tests and trace tool were removed from the
working tree and archived under `build/perf122/dropped/` with original relative
paths. Historical tests and measurements below describe those archived candidates.

## Reproduction conditions

- All network pairs must use localhost, with no lobby login or live server.
- Heavy runs reserve a coordination lock atomically; timing measurements reserve
  two locks. Locks are released between runs, including failures. Per-run wrapper
  logs record the locks acquired.
- Games are muted, in the background and BelowNormal. Tests use private
  `OPENRECOMP_HOME`, `APPDATA` and `LOCALAPPDATA` where applicable.
- Old-PC comparisons require baseline generated code, software FMA, the forced
  tier-1 path, 2c/4t and 4c/4t affinity masks, and `tools/slow_core.py`, on stage
  30 and stage 20. Each retained change needs paired measurements and cross-build
  rollback/lockstep proof; completed below.
- `build/perf122/input_hashes.json` records the generated inputs used for builds.
  It is local evidence and is not reproduced in this public document.

## Preparation and builds

| run / artifact directory | evidence | observed result |
|---|---|---|
| Tier-1 prepared runtime: `build/perf122/tier1-tree/` | `tools/prepare_ps3recomp.py`, local clone, terminal output | Pinned `f17bcd3`; 85 patches through 0115 applied successfully. Subsequent 0118 reverse-apply check passed. |
| Shared prepared runtime: `build/perf122/deps/` | prepared-tree stamp; root build logs below | Runtime source used by baseline/candidate builds. |
| Final retained series: `build/perf122/final-series/` | `build/perf122/logs/final_series.log` | Fresh pinned tree: all 86 patches apply successfully, ending at retained patch 0116; rejected 0117/0118 absent. |
| Baseline host attempt: `build/perf122/host/` | `build/perf122/logs/build_host.log` | **Failed**, exit 1: build wrapper could not find `vswhere.exe`, followed by access denied. No valid measurement from this attempt. |
| Baseline host retry: `build/perf122/host/` and `build/perf122/baseline/` | `build/perf122/logs/build_host_retry.log` | **Built**, exit 0; final step linked `t5dr.exe`. Compiler warnings retained in log. |
| Baseline DLL: `build/perf122/baseline/` | `build/perf122/logs/build_baseline_dll.log` | **Built**, exit 0; `--march none`, 24 translation units, four compile jobs, shipped profile. Compile 117.2 s, link 0.6 s; output 37.5 MB as reported by builder; largest compiler process 431 MB. |
| Candidate host: `build/perf122/host/` and `build/perf122/candidate/` | `build/perf122/logs/build_candidate_host.log` | **Built**, exit 0; final step linked `t5dr.exe`. Compiler warnings retained in log. |
| Corrected candidate host | `build/perf122/logs/build_candidate_corrected.log` | **Built**, exit 0, runtime library and executable linked. |
| AVX DLL: `build/perf122/avx/` | `build/perf122/logs/build_avx.log` | **Built**, exit 0; `--march avx`, 24 units, four compile jobs, existing shipped profile; compile 81.2 s, link 0.2 s; output 37.3 MB; largest compiler process 429 MB. |
| Fresh-profile DLL: `build/perf122/pgo/` | `build/perf122/logs/build_pgo.log` | **Built**, exit 0; compile 77.4 s, link 0.2 s; output 37.3 MB; largest compiler process 432 MB. |
| Imported instrumented DLL: `build/perf122/pgo-gen/` | `D:/t5dr-work/int130_out/logs/pgo1.log`; source `D:/t5dr-work/int130_out/pgobin/t5dr_game.dll` | Prior local build finished 2026-11-04 08:08, exit 0; compile 108.8 s, link 0.4 s, 66.4 MB. Imported DLL uses the same promoted-0113 generated PPU/SPU inputs recorded in `build/perf122/input_hashes.json`. Training host is this task's baseline host, built from `f81432c4`. |

Build durations are diagnostic, not old-PC performance measurements. The
profile structural-hash comparison below verifies that the retraining uses
the already-promoted SPU functions.

## Guest stores and AVX investigation

The normal game-DLL store path already has patch 0069's DLL-local constant bitmap
pointer and two atomic block-byte checks. The requested patch-0066 follow-up was
therefore already present in the baseline. No duplicate runtime store change was
introduced. The added optimized-IR test verifies all four store widths keep both
atomic reads and share the computed bitmap-byte address.

| run / directory | evidence | observed result |
|---|---|---|
| Guest-store tests: `build/guest-store/` | `build/guest-store/README.txt`; `tests/test_storepath.py` | 7 tests PASS, reported 0.406 s. Optimized LLVM IR preserved at `build/guest-store/store_probe.ll`. |
| VMX baseline correctness: `build/guest-store/base.exe` | `build/guest-store/base-bits.txt` | 32,262,144 cases, **0 differ**. Existing patch 0114, baseline x86-64. |
| VMX AVX compiler level: `build/guest-store/sandy.exe` | `build/guest-store/sandy-bits.txt` | 32,262,144 cases, **0 differ**. Existing patch 0114 with `-march=sandybridge` (AVX, no AVX2/FMA). |
| VMX four-double-lane prototype: `build/guest-store/avx256.exe` | `build/guest-store/avx256-bits.txt`; scratch diff `build/guest-store/avx256-candidate.patch` | 32,262,144 cases, **0 differ**. Experimental AVX float path; not promoted into the runtime patch series. |
| Early AVX timing reservations | `build/guest-store/README.txt` | Fewer than two slots were free; timing attempts exited without measurements. No timing number reported. |
| AVX microbenchmark | `build/guest-store/time_micro.py`; `build/guest-store/avx-micro.json` | 18 completed invocations, six alternated triples, all exit 0; raw values below. Retention still requires the full-game gain gate of at least 3%. |
| AVX compatibility tests | `build/guest-store/README.txt` | `test_pc_compat`: 44 PASS; `test_avx_level`: 3 PASS; `test_vmx_vec`: 7 PASS, including 32,262,144 cases each for baseline, actual `-mavx`, and v3, all zero differences. |
| CMake architecture selections | `build/guest-store/cmake-arch-check.json` | Real CMake script checks for none, avx, v3 and auto/Sandy all exit 0 with expected flags. |

All 18 helper timings, nanoseconds per `vmaddfp`, in execution order. The
series held two heavy slots for 6.8 s, CPU mask `0x1000`, BelowNormal. These
measure the development CPU, not physical Sandy/Ivy Bridge hardware.

| pair | executable in `build/guest-store/` | vector ns | scalar ns | exit |
|---|---|---:|---:|---:|
| 0 | `base.exe` | 8.34 | 9.98 | 0 |
| 0 | `sandy.exe` | 6.29 | 9.11 | 0 |
| 0 | `avx256.exe` | 5.61 | 9.13 | 0 |
| 1 | `avx256.exe` | 5.70 | 9.10 | 0 |
| 1 | `sandy.exe` | 6.29 | 9.15 | 0 |
| 1 | `base.exe` | 8.31 | 10.16 | 0 |
| 2 | `base.exe` | 8.71 | 9.94 | 0 |
| 2 | `sandy.exe` | 6.26 | 9.09 | 0 |
| 2 | `avx256.exe` | 5.59 | 9.12 | 0 |
| 3 | `avx256.exe` | 5.66 | 9.09 | 0 |
| 3 | `sandy.exe` | 6.25 | 9.20 | 0 |
| 3 | `base.exe` | 8.36 | 9.91 | 0 |
| 4 | `base.exe` | 8.45 | 10.06 | 0 |
| 4 | `sandy.exe` | 6.28 | 9.13 | 0 |
| 4 | `avx256.exe` | 5.58 | 9.11 | 0 |
| 5 | `avx256.exe` | 5.68 | 9.09 | 0 |
| 5 | `sandy.exe` | 6.35 | 9.13 | 0 |
| 5 | `base.exe` | 8.38 | 10.07 | 0 |

Median paired vector-time ratios to baseline: existing Sandy compiler level
0.750902; experimental four-double-lane AVX1 helper 0.674848. The prototype
was promoted as candidate patch `0116-avx-software-fma.patch` for full-game
testing. Its runtime CPU/OS checks include AVX, OSXSAVE and XMM/YMM state.
This is a candidate until the full-game threshold and cross-build proof pass.

## Condition wait correctness

| run / directory | evidence | observed result |
|---|---|---|
| Targeted suite before prepared-tree stamp refresh | `build/perf122/logs/targeted_tests.log` | 22 tests ran in 6.711 s: OK, one skipped class because the prepared tree's recorded patch series did not yet match. The condition-syscall implementation was not validated by this skipped class. |
| Condition tests after refresh | `build/perf122/logs/cond_tests.log` | 3 tests PASS, 5.191 s, including both wait paths and trace-analysis tests. |
| Broadcast mutation: `build/draw_wait/` | `mutant_broadcast_build.log`, `mutant_broadcast.log` | Mutation rejected: executable reports `FAIL 70 checks`; signaled waiters wrongly completed. This is an expected test failure for deliberately broken code. |
| Timeout mutation: `build/draw_wait/` | `mutant_timeout_build.log`, `mutant_timeout.log` | Mutation rejected: executable reports `FAIL 70 checks`; timeout-result assertions fail. This is an expected test failure for deliberately broken code. |
| Wait microbenchmark | `build/draw_wait/micro/runs.json`, `build/draw_wait/micro/summary.json`; `build/draw_wait/time_micro.py` | 32 invocations, all exit 0; all paths and values below. Four pairs per topology/load. |

The targeted suite also included guest-store, descriptor-cache and PGO-profile
guard tests. Its Python stderr was wrapped by PowerShell as `NativeCommandError`
text; the recorded unittest result is `OK`, not an inferred test failure.

Each condition microbenchmark does 20,000 ping-pong round trips. Both modes
passed semantic checks (CV 67 checks, address-wait 71 checks), including a
deterministic signal before the waiter parks and an assertion that the selected
path actually ran. Evidence: `build/draw_wait/validation.json`.

| topology mask | slow-core busy % | CV median us | address median us | median paired ratio address/CV | address wins |
|---|---:|---:|---:|---:|---:|
| `0xf000` | 0 | 19.225 | 19.506 | 0.984815 | 3/4 |
| `0xf000` | 60 | 42.785 | 40.490 | 0.945545 | 3/4 |
| `0x5500` | 0 | 20.272 | 20.399 | 0.998806 | 2/4 |
| `0x5500` | 60 | 43.837 | 45.052 | 1.047971 | 1/4 |

All 32 individual runs; CV = `address0`, candidate = `address1`. Each log is
under `build/draw_wait/micro/`.

| log basename | round-trip ns | exit |
|---|---:|---:|
| `f000_slow0_rep0_address0.log` | 18875.6 | 0 |
| `f000_slow0_rep0_address1.log` | 20029.3 | 0 |
| `f000_slow0_rep1_address1.log` | 20851.2 | 0 |
| `f000_slow0_rep1_address0.log` | 21223.9 | 0 |
| `f000_slow0_rep2_address0.log` | 19574.9 | 0 |
| `f000_slow0_rep2_address1.log` | 18983.4 | 0 |
| `f000_slow0_rep3_address1.log` | 18318.8 | 0 |
| `f000_slow0_rep3_address0.log` | 18556.5 | 0 |
| `f000_slow60_rep0_address0.log` | 44046.4 | 0 |
| `f000_slow60_rep0_address1.log` | 40562.6 | 0 |
| `f000_slow60_rep1_address1.log` | 41179.1 | 0 |
| `f000_slow60_rep1_address0.log` | 42793.6 | 0 |
| `f000_slow60_rep2_address0.log` | 42776.3 | 0 |
| `f000_slow60_rep2_address1.log` | 39731.4 | 0 |
| `f000_slow60_rep3_address1.log` | 40417.2 | 0 |
| `f000_slow60_rep3_address0.log` | 40017.1 | 0 |
| `5500_slow0_rep0_address0.log` | 20092.5 | 0 |
| `5500_slow0_rep0_address1.log` | 20106.9 | 0 |
| `5500_slow0_rep1_address1.log` | 20415.8 | 0 |
| `5500_slow0_rep1_address0.log` | 19911.3 | 0 |
| `5500_slow0_rep2_address0.log` | 20451.0 | 0 |
| `5500_slow0_rep2_address1.log` | 20387.5 | 0 |
| `5500_slow0_rep3_address1.log` | 20409.7 | 0 |
| `5500_slow0_rep3_address0.log` | 20507.1 | 0 |
| `5500_slow60_rep0_address0.log` | 45862.7 | 0 |
| `5500_slow60_rep0_address1.log` | 47801.6 | 0 |
| `5500_slow60_rep1_address1.log` | 42144.7 | 0 |
| `5500_slow60_rep1_address0.log` | 39998.2 | 0 |
| `5500_slow60_rep2_address0.log` | 41812.1 | 0 |
| `5500_slow60_rep2_address1.log` | 44664.3 | 0 |
| `5500_slow60_rep3_address1.log` | 45438.9 | 0 |
| `5500_slow60_rep3_address0.log` | 55847.7 | 0 |

The 2c/4t slow-core microbenchmark wins three of four pairs; 4c/4t with slow
cores wins one of four. This does not establish a general game-level gain.

## Tier-1 descriptor-cache correctness

`RSX_TIER1_PATH=1` already forces the complete tier-1 descriptor path on a tier-3
GPU. It reproduces CPU code and binding calls, not a Fermi driver's GPU cost.
The 0118 candidate adds per-slot descriptor versions, with
`RSX_TIER1_SLOT_CACHE=0` restoring global-generation invalidation. The test
compiles the actual memo and descriptor-write functions against fake descriptor
heaps and compares every returned table with an independent fresh-copy oracle.

Evidence directory: `build/perf122/tier1-evidence/`, containing `unit.log` and
`unit-results.json`. The latest isolated suite ran 2 tests in 2.475 s, both PASS.
An initial harness compile rejected deprecated `getenv` under `/WX`; the harness
was corrected to define `_CRT_SECURE_NO_WARNINGS` before these successful runs.

| variant | random operations | copied tables | reused tables | reused after unrelated writes | result |
|---|---:|---:|---:|---:|---|
| Forced tier 1, slot cache on | 300,000 | 174,817 | 126,415 | 17,157 | PASS, zero descriptor differences |
| Forced tier 1, slot cache off | 300,000 | 191,974 | 109,258 | 0 | PASS, zero descriptor differences |
| Tier 3, slot-cache setting on | 300,000 | 191,974 | 109,258 | 0 | PASS; cache correctly stays off |
| Mutant: missing slot-version write | stops at first stale descriptor | — | — | — | Rejected, exit 4 |
| Mutant: missing slot-version comparison | stops at first stale descriptor | — | — | — | Rejected, exit 4 |
| Mutant: missing ring-epoch check | stops at invalid GPU-table handle | — | — | — | Rejected, exit 3 |

These synthetic copy counts validate the mechanism. They are **not** game draw
counts, CPU-time savings or a frame-rate claim. Paired game numbers and actual
Warm `[xlat-stats]` confirms only 0.0 / 0.1 extra preserved tables per frame on stages 30 / 20; the candidate is rejected.

## PGO retraining, interrupted and recovered

Training uses `tools/pgo_train.py`, one fight at a time, 75 s requested fighting
time per entry. These are training runs rather than performance measurements.
Raw-profile byte sizes below are observed file sizes, not coverage estimates.

| run directory | wrapper log | observed result |
|---|---|---|
| `build/perf122/pgo-train/f00_lil_ask_20_3/` | `build/perf122/logs/pgo_train.log` | Lili/Asuka stage 20: trainer printed `profile written`; `trig.write.ok` present; `fight.profraw` 4,815,440 bytes. Requested 75 s completed, then process-tree termination stalled. |
| `build/perf122/pgo-train/f01_kaz_jin_24_3/` | same log | Root worker terminated the task's stalled game/trainer; wrapper exit 4,294,967,295. This started entry was interrupted; `fight.profraw` is **0 bytes**, unusable. Not counted as completed training. |
| `build/perf122/pgo-extra/f01/f00_kaz_jin_24_3/` | `build/perf122/logs/pgo_train_1.log` | Recovered Kazuya/Jin stage 24: `profile written`; `fight.profraw` 4,815,440 bytes. Trainer exit 0. |
| `build/perf122/pgo-extra/f01/` | same log | Per-entry merge produced `t5dr_lifted.profdata`, 1,903,720 bytes, from one fight. This is not yet the final full training profile. |
| `build/perf122/pgo-extra/f02/f00_pau_kin_33_3/` | `build/perf122/logs/pgo_train_2.log` | Profile written, trainer exit 0; raw 4,815,440 bytes; per-entry merge 1,902,936 bytes. |
| `build/perf122/pgo-extra/f03/f00_xia_bry_34_3/` | `build/perf122/logs/pgo_train_3.log` | Profile written, trainer exit 0; raw 4,815,440 bytes; per-entry merge 1,925,512 bytes. |
| `build/perf122/pgo-extra/f04/f00_hwo_ste_26_3/` | `build/perf122/logs/pgo_train_4.log` | Profile written, trainer exit 0; raw 4,815,440 bytes; per-entry merge 1,937,800 bytes. |
| `build/perf122/pgo-extra/f05/f00_dvj_yos_28_3/` | `build/perf122/logs/pgo_train_5.log` | Profile written, trainer exit 0; raw 4,815,440 bytes; per-entry merge 1,980,256 bytes. |
| `build/perf122/pgo-extra/f06/f00_cha_rav_30_3/` | `build/perf122/logs/pgo_train_6.log` | Profile written, trainer exit 0; raw 4,815,440 bytes; per-entry merge 1,947,152 bytes. |
| `build/perf122/pgo-merged/` | `report.json`, `t5dr_lifted.profdata`, `t5dr_lifted.proftext` | Seven completed fight profiles merged; binary 2,076,056 bytes; text 1,411,758 bytes on disk (includes CRLF). |
| Paired old/new PGO DLL measurements | eight completed pairs below | Rejected; main -0.13%, total CPU -1.01%, sound +0.04%, fps -0.60%, within spread. |

Individual retries used `build/perf122/kill_fix.py` to terminate only the task's
own game process. The first successful entry plus six individual retries cover
stages 20, 24, 33, 34, 26, 28 and 30. Failed zero-byte raw profiles were excluded.

**Baseline-profile correction:** the baseline already contains the profile
retrained for patches 0113/0114, committed as `3524a712` on 2026-11-04 at
08:23:18. The task's shipped profile and that integrated profile are identical
after CRLF normalization; evidence `build/guest-store/pgo-provenance-hashes.json`.
The new seven-fight training supplies fresh counts and PPU coverage; it is not
a repair of stale promoted-SPU entries. Local profiler inputs are recorded in
`build/perf122/profiler_provenance.json`.

| profile part | existing records | new records | shared structural hashes equal | shared structural hashes changed | new names |
|---|---:|---:|---:|---:|---:|
| ppu | 7010 | 7216 | 7006 | 0 | 210 |
| snd | 449 | 449 | 449 | 0 | 0 |
| spu | 38 | 38 | 38 | 0 | 0 |
| skin | 121 | 121 | 121 | 0 | 0 |

The sound core, generic SPU and skinning profile shapes already match. PPU
coverage adds 210 names; four old PPU records are absent from the fresh training.
A performance gain still requires paired DLL runs.

## Completed fight measurements

Snapshot: 2026-11-04T16:22:38 local time. The initial matrix has
12 completed game runs and 12 explicit second-round NOT RUN entries. Only directories
with completed `result.json` files appear below. Each row refers to
`build/perf122/runs/<run>/`; `result.json` contains the complete arguments,
thread table and metrics, with `game.log`, CSVs and private input/status files
beside it. Wrapper results live in `build/perf122/logs/<run>.log`.

The initial control/wait/tier1 comparisons use the candidate host with switches
selecting the old or new path, the same baseline DLL, forced tier 1, software FMA,
slow-core busy 60% and a 4 ms period. Masks: `0xF000` = 2c/4t; `0x5500` = 4c/4t.
These are stand-ins on the development CPU, not measurements on old hardware.

**Early CPU denominator warning:** the first three stage-30 rows were made
before the bench drained the buffered frame CSV and aligned the CPU window.
Their `cpu_ms_per_frame` and thread-table per-frame values use incomplete frame
counts. The numbers are preserved below as invalid, but must not be used to
claim CPU savings. Later completed rows have `cpu_window_csv_covered=true`.
Frame-interval fps, game-thread self-timing and CSV translation timings are
reported as recorded; the external load changed substantially between runs.

| run directory basename | frames in reported interval | fps | p99 interval ms | main CPU p50 ms | FIFO CPU p50 ms | translation wall p50 ms | other busy processors |
|---|---:|---:|---:|---:|---:|---:|---:|
| `control_0x5500_s20_r1` | 1061 | 58.942 | 23.658 | 4.611 | 1.912 | 4.173 | 13.656 |
| `control_0x5500_s30_r1` | 1027 | 57.043 | 22.989 | 5.011 | 2.281 | 4.473 | 18.613 |
| `control_0xF000_s20_r1` | 1009 | 56.018 | 22.661 | 5.492 | 2.318 | 4.458 | 14.281 |
| `control_0xF000_s30_r1` | 835 | 52.249 | 23.296 | 5.817 | 2.450 | 4.675 | 21.167 |
| `tier1_0x5500_s20_r1` | 1025 | 56.944 | 23.262 | 4.489 | 1.892 | 4.043 | 13.175 |
| `tier1_0x5500_s30_r1` | 1064 | 59.123 | 22.987 | 4.402 | 1.925 | 4.088 | 12.366 |
| `tier1_0xF000_s20_r1` | 985 | 54.735 | 22.698 | 5.649 | 2.369 | 4.551 | 11.453 |
| `tier1_0xF000_s30_r1` | 926 | 57.946 | 20.678 | 5.203 | 2.262 | 4.377 | 14.941 |
| `wait_0x5500_s20_r1` | 1079 | 59.901 | 20.757 | 4.155 | 1.735 | 3.923 | 14.964 |
| `wait_0x5500_s30_r1` | 1072 | 59.516 | 22.433 | 4.475 | 1.920 | 4.069 | 11.716 |
| `wait_0xF000_s20_r1` | 1024 | 56.839 | 20.532 | 5.475 | 2.271 | 4.424 | 11.204 |
| `wait_0xF000_s30_r1` | 891 | 55.545 | 22.563 | 5.529 | 2.359 | 4.481 | 19.439 |

Recorded processor-time breakdown; invalid rows have the denominator defect
described above. Values are processor milliseconds per frame, not wall time.

| run | all threads | main | sound SPU | skinning (chain + jobs) | draw thread | denominator |
|---|---:|---:|---:|---:|---:|---|
| `control_0x5500_s20_r1` | 19.797 | 4.680 | 4.557 | 2.817 | 1.632 | covered |
| `control_0x5500_s30_r1` | 21.573 | 4.935 | 4.790 | 3.376 | 1.640 | covered |
| `control_0xF000_s20_r1` | 22.837 | 5.680 | 5.252 | 3.589 | 2.206 | covered |
| `control_0xF000_s30_r1` | 25.505 | 5.801 | 6.063 | 3.518 | 2.208 | invalid for comparison |
| `tier1_0x5500_s20_r1` | 19.916 | 4.404 | 4.404 | 3.433 | 1.846 | covered |
| `tier1_0x5500_s30_r1` | 19.485 | 4.482 | 4.482 | 3.268 | 1.805 | covered |
| `tier1_0xF000_s20_r1` | 24.263 | 5.792 | 5.640 | 3.502 | 2.492 | covered |
| `tier1_0xF000_s30_r1` | 23.666 | 5.304 | 5.405 | 3.716 | 2.179 | invalid for comparison |
| `wait_0x5500_s20_r1` | 17.866 | 4.206 | 3.899 | 2.886 | 1.704 | covered |
| `wait_0x5500_s30_r1` | 19.114 | 4.400 | 3.999 | 3.412 | 1.637 | covered |
| `wait_0xF000_s20_r1` | 23.203 | 5.052 | 5.278 | 3.692 | 2.073 | covered |
| `wait_0xF000_s30_r1` | 24.183 | 5.752 | 5.506 | 3.858 | 2.490 | invalid for comparison |

### Second round: explicitly not run

Evidence: `build/perf122/skip_labels.json`, `build/perf122/logs/matrix.log`,
and the twelve per-label logs below. No result directory or measurement is
claimed for these entries. Both candidates were rejected after full first-round
topology/stage coverage: the descriptor cache had essentially no eligible
warm-frame reuse, and traced signal-to-ready time leaves little useful room
for a wake-latency change. Subsequent slots were assigned to AVX/PGO proof.

| log path | status |
|---|---|
| `build/perf122/logs/control_0x5500_s20_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/control_0x5500_s30_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/control_0xF000_s20_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/control_0xF000_s30_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/tier1_0x5500_s20_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/tier1_0x5500_s30_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/tier1_0xF000_s20_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/tier1_0xF000_s30_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/wait_0x5500_s20_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/wait_0x5500_s30_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/wait_0xF000_s20_r2.log` | NOT RUN; second round cancelled after candidate rejection |
| `build/perf122/logs/wait_0xF000_s30_r2.log` | NOT RUN; second round cancelled after candidate rejection |

### Main-thread condition traces

Each path is `build/perf122/runs/<run>/cond_trace.json`, with the binary trace
in `sched.bin`. Main-thread waits are on the draw manager's condition. The table
uses complete game-thread trace-frame counts, rather than the early bench CSV
denominators. `bench_wait_ms_per_frame` in these early JSONs is consequently
an overestimate; the reliable trace-normalized values are below.

| run | trace game frames | main waits | total wait ms | wait ms / trace frame | signal-to-ready median / p95 us | mutex reacquire median us | trace-window coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| `control_0xF000_s30_r1` | 936 | 1860 | 1041.2134 | 1.112407 | 3.500 / 6.300 | 8.900 | 98.80% |
| `tier1_0xF000_s30_r1` | 1037 | 2060 | 1053.9412 | 1.016337 | 3.500 / 5.500 | 8.700 | 99.44% |
| `wait_0xF000_s30_r1` | 1004 | 1992 | 1048.2880 | 1.044112 | 3.600 / 5.900 | 8.700 | 99.97% |

The main thread waits roughly twice per game frame. Median signal-to-ready
latency is only 3.5-3.6 us per wait in these traces; the roughly 1.0-1.1 ms total
wait includes draw work. Candidate 0117 was rejected; the original condition-wait path remains the
default.

### Forced-tier-1 game counts

The last complete 600-render-frame statistics window in each tier1/control
run is recorded below. These counts expose whether the proposed cache can
actually avoid copies, independently of external CPU load.

| run | statistics end frame | draws/frame | tables copied/frame | tables reused/frame | additional per-slot reuse/frame |
|---|---:|---:|---:|---:|---:|
| `control_0x5500_s20_r1` | 3000 | 835 | 166 | 669 | 0.0 |
| `control_0x5500_s30_r1` | 3000 | 802 | 199 | 603 | 0.0 |
| `control_0xF000_s20_r1` | 3000 | 839 | 160 | 679 | 0.0 |
| `control_0xF000_s30_r1` | 3000 | 799 | 186 | 613 | 0.0 |
| `tier1_0x5500_s20_r1` | 3000 | 835 | 162 | 673 | 0.1 |
| `tier1_0x5500_s30_r1` | 3000 | 805 | 202 | 603 | 0.0 |
| `tier1_0xF000_s20_r1` | 3000 | 840 | 159 | 681 | 0.1 |
| `tier1_0xF000_s30_r1` | 3000 | 794 | 201 | 594 | 0.0 |

On stage 30, the new cache preserved 0.0 extra tables per warm frame; on
stage 20, 0.1. This is too little eligible work to justify keeping the candidate
based on the confounded fps changes. Candidate 0118 was removed from the retained patch series. Its fps movement
cannot be claimed as a gain under these changing external loads.

### Translation sampling profile

Evidence: `build/perf122/runs/control_0xF000_s30_r1/ticker-profile.json`
and `ticker-profile.log`: 2,999 busy and 7,001 idle samples, 10 s at 1,000/s.
Self samples: `sink_end_impl` 429 (14.3%), FIFO walk 299 (10.0%), `blk_span`
248 (8.3%), block dispatch 246 (8.2%), D3DCOMPILER 235 (7.8%), texture
hashing 165 (5.5%), QPC 149 (5.0%), NVIDIA driver 113 (3.8%).

This profile covers fight +10..20 s, before the +24 s timing window. New run
directories have cold private shader caches; shader compilation and cache
file I/O remain visible. It therefore does not represent fully warmed steady
translation. QPC includes benchmark instrumentation. Object inspection also
confirms that span byteswaps and change counting already vectorize. No further
renderer patch was introduced on this evidence.

A later warm profile samples stage 20 on 4c/4t, fight +24..34 s:
`build/perf122/runs/control_0x5500_s20_r1/ticker-profile.json` and
`ticker-profile.log`, 2,911 busy / 7,089 idle samples, 10 s at 1,000/s.

| self symbol | busy samples | busy share |
|---|---:|---:|
| `sink_end_impl` | 533 | 18.3% |
| `gcm_rsx_process_fifo_unlocked` | 375 | 12.9% |
| `texture_content_hash` | 268 | 9.2% |
| `blk_span` | 254 | 8.7% |
| `[ntdll.dll]RtlQueryPerformanceCounter` | 206 | 7.1% |
| `rsx_dispatch_method_block` | 198 | 6.8% |
| `rsx_live_draw_method_block` | 100 | 3.4% |
| `YmmLoop` | 90 | 3.1% |
| `[nvwgf2umx.dll]` | 76 | 2.6% |
| `[win32u.dll]NtUserPeekMessage` | 59 | 2.0% |
| `texture_srv_slot` | 49 | 1.7% |
| `rsx_dispatch_method` | 47 | 1.6% |

Compiler DLLs account for 0 self samples in this later profile. The warm
profile confirms FIFO/dispatch, texture hashing and draw translation as the
CPU work. Benchmark QPC timers remain visible. It supplies no evidence that
the rejected descriptor-invalidation optimization addresses a meaningful
share of that work.

Archived rejected artifacts (original paths beneath the archive root):

| archive path | role |
|---|---|
| `build/perf122/dropped/patches/ps3recomp/0117-cond-address-wake.patch` | rejected candidate evidence; absent from active source/tests/tools |
| `build/perf122/dropped/patches/ps3recomp/0118-tier1-slot-cache.patch` | rejected candidate evidence; absent from active source/tests/tools |
| `build/perf122/dropped/tests/c/cond_address_test.c` | rejected candidate evidence; absent from active source/tests/tools |
| `build/perf122/dropped/tests/c/tier1_descriptor_cache_test.c` | rejected candidate evidence; absent from active source/tests/tools |
| `build/perf122/dropped/tests/test_cond_address.py` | rejected candidate evidence; absent from active source/tests/tools |
| `build/perf122/dropped/tests/test_tier1_descriptor_cache.py` | rejected candidate evidence; absent from active source/tests/tools |
| `build/perf122/dropped/tools/cond_trace.py` | rejected candidate evidence; absent from active source/tests/tools |

## Retained-code validation and cross-build proof

Status read from completed logs on 2026-11-04T16:39:14 local time.
The retained host and DLLs were validated independently of the rejected
wait/descriptor candidates. Binary identities are recorded locally in
`build/perf122/binary_hashes.json`.

| validation run / directory | evidence | observed result |
|---|---|---|
| Fresh retained runtime series: `build/perf122/final-series/` | `build/perf122/logs/final_series.log`, `build/perf122/final_source_check.json` | 86 patches apply; all 653 compared source files match the build source, zero differences. |
| Retained host rebuild | `build/perf122/logs/build_retained_host.log` | Exit 0; retained executable linked successfully. |
| Actual AVX DLL loader guard: `build/perf122/guard/` | `build/perf122/logs/avx_loader_guard.log`, `guard/game.log` | PASS: `T5DR_TEST_CPU=noavx` makes the runtime reject the actual AVX DLL before initialization, expected game exit 14; test wrapper exit 0. |
| Targeted retained-candidate suite | `build/perf122/logs/final_targeted_candidate.log` | 76 tests OK in 10.437 s. A source-only CMake assertion was removed afterwards; this did not change runtime code. |
| Builder/renderer regression suite | `build/perf122/logs/builder_regressions.log` | 97 tests OK in 58.996 s, one Tk test skipped because Tcl initialization/display support was unavailable. |
| Private test-home guard: `build/perf122/unit-home/` | `build/perf122/unit-home-guard.json` | Test exit 0; protected configuration hash equal before/after; private test home used. |

### Cross-build network pairs

Baseline host versus the retained AVX build as joiner; both use software FMA
and forced tier 1. Games are muted, in the background and BelowNormal; the
network/proxy is localhost only. Each directory contains per-side `game.log`,
frame logs, result and recorded replay files; `summary.txt` reports both sides.

| pair directory | wrapper log | fight / network | compared through frame | mismatching host / join | shared result hash | additional result |
|---|---|---|---:|---:|---|---|
| `build/perf122/proof/rb150/` | `build/perf122/logs/cross_rb150.log` | Lili/Asuka, stage 20; rollback RTT 150 +/-5 ms, 3% loss | 3599 | 0 / 0 | `087916b94ba9c6d3` | One match completed; host/join rollbacks 1,088/1,061; decode errors 0, aborts 0. |
| `build/perf122/proof/lockstep/` | `build/perf122/logs/cross_lockstep.log` | Lili/Asuka, stage 30; lockstep RTT 30 +/-2 ms, 1% loss | 3599 | 0 / 0 | `f2fdbfcb1219ebbb` | One match completed; decode errors 0, aborts 0. |

The harness stopped the games after their completed matches; `exit killed` in
the summaries is the harness shutdown, not a crash or incomplete match. These
runs establish state equivalence, not a performance comparison.

### Playback of the four recorded replays

Every completed verdict compares all recorded hashes and the match result.
Playback executable: retained AVX build, software FMA paths.

| output directory | wrapper log | playback frames | hashes compared | mismatches | result hash | identical |
|---|---|---:|---:|---:|---|---|
| `build/perf122/replays/rb150_host/` | `build/perf122/logs/replay-rb150-host.log` | 3598 | 60 | 0 | `087916b94ba9c6d3` | true |
| `build/perf122/replays/rb150_join/` | `build/perf122/logs/replay-rb150-join.log` | 3597 | 60 | 0 | `087916b94ba9c6d3` | true |
| `build/perf122/replays/lockstep_host/` | `build/perf122/logs/replay-lockstep-host.log` | 3601 | 61 | 0 | `f2fdbfcb1219ebbb` | true |
| `build/perf122/replays/lockstep_join/` | `build/perf122/logs/replay-lockstep-join.log` | 3601 | 61 | 0 | `f2fdbfcb1219ebbb` | true |

### Excluded first AVX paired attempt

Directory `build/perf122/pairs/avx_pair_2c4t_s30_r1_interrupted/`; wrapper log
`build/perf122/logs/avx-paired-0-interrupted.log`; exclusion note `INVALID.txt`.
The pair started at 16:32:33. The coordinator restarted the reservation wrapper
at 16:33:05 without realizing that the games had started. The games finished
naturally and wrote complete side results and `pair.json` with `ok:true`, but
supervision was lost and the interference interval is uncertain. The task
therefore excludes this attempt despite the complete raw data.

By the 16:33:55 process snapshot, the old runner/game/hog descendants had all
exited. Its two unreleased lock files were removed after confirming that their
writer processes were gone. This task archived the folder within its workspace
and reran the same condition. The exclusion is not a claim that the games failed
to finish.

Raw excluded values below are for audit only; each side has its own
`result.json` in the excluded directory.

| excluded side | frames | fps | p99 interval ms | main CPU p50 ms | total CPU ms/frame | translation wall p50 ms | other busy processors |
|---|---:|---:|---:|---:|---:|---:|---:|
| `before/` | 931 | 51.704301 | 23.665900 | 5.383227 | 24.126575 | 4.469000 | 19.007287 |
| `after/` | 1012 | 56.195823 | 23.419910 | 4.973504 | 22.272190 | 4.426000 | 18.896167 |

The supervised rerun is `build/perf122/pairs/avx_pair_2c4t_s30_r1/`,
with `build/perf122/logs/avx-paired-0.log` reporting exit 0. Its accepted raw
results are separate from the excluded folder. The completed AVX matrix follows;
the completed fresh-profile PGO comparison is reported separately below.

## Completed AVX paired matrix

Evidence snapshot: 2026-11-04T17:04:36 local time. Eight accepted pairs
(16 game invocations), two repetitions of every topology/stage combination.
Both builds run concurrently on disjoint masks; repetition 2 swaps masks.
The excluded `_interrupted` duplicate remains excluded. Source evidence:
`build/guest-store/paired-analysis/rows.csv`, `summary.json`, and
`build/perf122/avx_table.json`. The analysis rechecks binary identities,
display/CPU CSV coverage, and main-thread cycle logs; isolation errors: zero.

Before = retained host with baseline DLL; after = same host and shipped profile
with AVX DLL. Software FMA and forced tier 1 remain enabled. Complete masks,
frame counts, other load, all metric ratios and recomputation checks are in the
CSV/JSON files above.

### Each accepted pair and both output directories

| before directory | after directory | main CPU ms before / after | total CPU ms before / after | fps before / after | main ratio after/before |
|---|---|---:|---:|---:|---:|
| `build/perf122/pairs/avx_pair_2c4t_s20_r1/before/` | `build/perf122/pairs/avx_pair_2c4t_s20_r1/after/` | 5.398431 / 4.877287 | 22.253322 / 21.038993 | 59.751016 / 59.608372 | 0.903464 |
| `build/perf122/pairs/avx_pair_2c4t_s20_r2/before/` | `build/perf122/pairs/avx_pair_2c4t_s20_r2/after/` | 5.171815 / 5.132613 | 22.269571 / 21.897007 | 58.295302 / 58.537406 | 0.992420 |
| `build/perf122/pairs/avx_pair_2c4t_s30_r1/before/` | `build/perf122/pairs/avx_pair_2c4t_s30_r1/after/` | 5.540548 / 5.064813 | 23.807883 / 22.578621 | 53.507732 / 55.889386 | 0.914136 |
| `build/perf122/pairs/avx_pair_2c4t_s30_r2/before/` | `build/perf122/pairs/avx_pair_2c4t_s30_r2/after/` | 5.189884 / 5.107003 | 23.073940 / 22.930613 | 57.057166 / 57.235647 | 0.984030 |
| `build/perf122/pairs/avx_pair_4c4t_s20_r1/before/` | `build/perf122/pairs/avx_pair_4c4t_s20_r1/after/` | 4.987146 / 4.008599 | 21.035546 / 18.043155 | 55.346632 / 59.333366 | 0.803786 |
| `build/perf122/pairs/avx_pair_4c4t_s20_r2/before/` | `build/perf122/pairs/avx_pair_4c4t_s20_r2/after/` | 4.039212 / 4.386536 | 16.729024 / 19.362745 | 59.944887 / 59.947263 | 1.085988 |
| `build/perf122/pairs/avx_pair_4c4t_s30_r1/before/` | `build/perf122/pairs/avx_pair_4c4t_s30_r1/after/` | 4.369545 / 3.607859 | 19.174727 / 16.671798 | 59.278399 / 59.664482 | 0.825683 |
| `build/perf122/pairs/avx_pair_4c4t_s30_r2/before/` | `build/perf122/pairs/avx_pair_4c4t_s30_r2/after/` | 4.137355 / 4.543562 | 18.150728 / 21.141582 | 58.679966 / 57.639755 | 1.098180 |

Additional raw per-side values; side directories are the full paths above.
Frame counts here are display-window counts. FIFO CPU is the CSV translation
CPU metric, distinct from translation wall time in earlier matrix tables.

| pair | side | mask | frames | other busy processors | game part ms | FIFO CPU ms | sound SPU CPU ms/frame | draw CPU ms/frame | p99 interval ms |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `avx_pair_2c4t_s20_r1` | before | `0xf000` | 1076 | 17.849236 | 12.195350 | 2.418000 | 4.828986 | 2.014641 | 20.135000 |
| `avx_pair_2c4t_s20_r1` | after | `0xf0000000` | 1073 | 17.952622 | 11.399450 | 2.221000 | 4.781589 | 1.943485 | 20.073760 |
| `avx_pair_2c4t_s20_r2` | before | `0xf0000000` | 1050 | 16.246815 | 11.932700 | 2.255000 | 5.034722 | 2.162247 | 20.385590 |
| `avx_pair_2c4t_s20_r2` | after | `0xf000` | 1054 | 16.232495 | 11.864650 | 2.275000 | 4.857269 | 1.980634 | 20.256400 |
| `avx_pair_2c4t_s30_r1` | before | `0xf000` | 964 | 19.674684 | 12.630900 | 2.378500 | 5.581588 | 2.084482 | 23.279130 |
| `avx_pair_2c4t_s30_r1` | after | `0xf0000000` | 1006 | 19.676352 | 12.031400 | 2.300000 | 5.070692 | 1.982030 | 22.378200 |
| `avx_pair_2c4t_s30_r2` | before | `0xf0000000` | 1027 | 16.246786 | 12.137050 | 2.284000 | 4.992890 | 2.019778 | 20.293520 |
| `avx_pair_2c4t_s30_r2` | after | `0xf000` | 1030 | 16.256996 | 12.073700 | 2.315500 | 5.101056 | 1.834449 | 20.343600 |
| `avx_pair_4c4t_s20_r1` | before | `0x5500` | 996 | 20.041142 | 11.978150 | 2.134500 | 4.656348 | 1.705142 | 27.552000 |
| `avx_pair_4c4t_s20_r1` | after | `0x55000000` | 1068 | 20.159179 | 8.650700 | 1.748000 | 3.673735 | 1.705109 | 23.649030 |
| `avx_pair_4c4t_s20_r2` | before | `0x55000000` | 1079 | 16.729416 | 9.373900 | 1.630000 | 3.572743 | 1.410697 | 20.067880 |
| `avx_pair_4c4t_s20_r2` | after | `0x5500` | 1080 | 16.619929 | 10.662850 | 1.860000 | 4.289216 | 1.930147 | 20.602500 |
| `avx_pair_4c4t_s30_r1` | before | `0x5500` | 1068 | 16.020476 | 9.566500 | 1.924500 | 3.937252 | 1.751612 | 23.575800 |
| `avx_pair_4c4t_s30_r1` | after | `0x55000000` | 1074 | 16.167538 | 8.286500 | 1.664000 | 3.633005 | 1.323892 | 20.862520 |
| `avx_pair_4c4t_s30_r2` | before | `0x55000000` | 1057 | 17.516103 | 8.894800 | 1.783000 | 3.984689 | 1.380522 | 24.228840 |
| `avx_pair_4c4t_s30_r2` | after | `0x5500` | 1038 | 17.558799 | 11.414150 | 2.162000 | 4.384566 | 2.088648 | 23.216890 |

### Aggregate by topology and stage

Geometric means of the two swapped-mask repetitions. CPU values are milliseconds
of processor time per frame. Change percentages are geometric means of paired
ratios, not comparisons of unrelated best runs.

| topology / stage | main CPU before / after | main change | total CPU before / after | total change | fps before / after | fps change |
|---|---:|---:|---:|---:|---:|---:|
| 2c4t / 30 | 5.362350 / 5.085865 | -5.156% | 23.438039 / 22.753936 | -2.919% | 55.253955 / 56.558511 | +2.361% |
| 2c4t / 20 | 5.283908 / 5.003321 | -5.310% | 22.261445 / 21.463713 | -3.583% | 59.018671 / 59.070462 | +0.088% |
| 4c4t / 30 | 4.251865 / 4.048769 | -4.777% | 18.655703 / 18.774136 | +0.635% | 58.978423 / 58.643381 | -0.568% |
| 4c4t / 20 | 4.488222 / 4.193312 | -6.571% | 18.759108 / 18.691308 | -0.361% | 57.599892 / 59.639525 | +3.541% |

All eight accepted pairs: main-thread CPU **-5.456%**; all-thread CPU
**-1.573%**; fps **+1.342%**. The retention gate is at least
3% less **main-thread processor work**, which the point estimate meets in all
four topology/stage strata. This is not a claim of at least 3% whole-game fps;
the observed whole-game fps gain is 1.342%. Six of eight individual main-thread
pairs improve, while both 4c/4t second repetitions regress; the mask-position
effect is material. The all-pair descriptive 95% ratio interval is 0.8584-1.0413.
Treating each swapped-mask configuration as cancelling a stable multiplicative
CCD effect gives the narrower 0.9331-0.9579 interval across four configurations;
that depends on the stable-effect assumption and does not remove external-load
uncertainty. The raw results above retain the regressions.

### Retained tests and memory sample

| run / artifact | evidence | result |
|---|---|---|
| Final retained suite | `build/perf122/logs/final_targeted_retained.log` | 76 tests OK, 14.382 s, against retained source. |
| Final suite home guard | `build/perf122/final-unit-home-guard.json` | Exit 0; protected owner configuration hash equal before/after. Private test home: `build/perf122/final-unit-home/`. |
| Fight memory samples | `build/perf122/memory_samples.json` | Sampled from accepted `avx_pair_2c4t_s20_r2`; byte values below. |

| side | working-set bytes | working set decimal GB | private bytes | private decimal GB | peak working-set bytes |
|---|---:|---:|---:|---:|---:|
| before | 987,357,184 | 0.987357 | 1,290,829,824 | 1.290830 | 992,518,144 |
| after | 988,045,312 | 0.988045 | 1,291,046,912 | 1.291047 | 990,425,088 |

These are individual fight samples on the development PC, not a bound on all
stages or a measurement of total Windows memory use.

## Auxiliary re-simulation diagnostic: excluded from acceptance

Directory `build/perf122/resim/avx-resim-s30-r1/`, with `a/` baseline and `b/`
AVX side logs; manifest and full 30-batch-per-build data are in `manifest.json`
and `resim_comparison.json`. Wrapper log:
`build/perf122/logs/avx-resim-s30-r1.log`, exit 0. Stage 30, 2c/4t masks
`0xF000` and `0xF0000000`, slow-core 60%, 30 batches of eight re-simulated
frames per build, `T5_RB_MODE=test`, `T5_RB_CUT_TAIL=1`.

| side | batches | gameplay boundaries checked | gameplay mismatches | cumulative final-state mismatches at end |
|---|---:|---:|---:|---:|
| baseline `a/` | 30 | 240 | 0 | 32 |
| AVX `b/` | 30 | 240 | 0 | 33 |

Paired CPU-cycle median ratio AVX/baseline: **0.995105**; steady paired
geometric mean ratio: **0.981568**. This mode skips draw work targeted by the
optimization and its full-state checks fail on the baseline too. It is
**not accepted as state-equivalence proof or as the performance retention gate**.
The completed cross-build network and replay tests above supply state proof.
No full-state failure is hidden behind the zero gameplay-boundary count.

Three further auxiliary reservations were cancelled before games started.
Their explicit records are:

| record | status |
|---|---|
| `build/perf122/logs/avx-resim-s20-r1-notrun.json` | NOT RUN; diagnostic skipped after the baseline/full-state failure and draw-skip limitation |
| `build/perf122/logs/avx-resim-s30-r2-notrun.json` | NOT RUN; diagnostic skipped after the baseline/full-state failure and draw-skip limitation |
| `build/perf122/logs/avx-resim-s20-r2-notrun.json` | NOT RUN; diagnostic skipped after the baseline/full-state failure and draw-skip limitation |

The waiting auxiliary worker was cancelled after process/suspend inspection
confirmed there were no current game processes. An earlier attempt to inspect
a PGO reservation before deferral raised an `NtQuery` assertion because PID
105756 had already exited. No action was taken and no deferred game run is
counted from that attempt. The accepted PGO paired matrix is separate and will
be appended when complete.

## Evidence completion status

Attempts, including interrupted/invalid runs, are recorded with their actual output directories.
Timing runs are distinguished from tracing/profiling runs because those hooks add work.

| required evidence | run directories | numbers / status |
|---|---|---|
| Stage 30, 2c/4t, initial wait/tier1 comparisons | completed rows above | candidates rejected; second round explicitly NOT RUN |
| Stage 20, 2c/4t, initial wait/tier1 comparisons | completed rows above | candidates rejected; second round explicitly NOT RUN |
| Stage 30, 4c/4t, initial wait/tier1 comparisons | completed rows above | candidates rejected; second round explicitly NOT RUN |
| Stage 20, 4c/4t, initial wait/tier1 comparisons | completed rows above | candidates rejected; second round explicitly NOT RUN |
| Main/draw condition-wait trace on 2c/4t | three completed traces above | measured; candidate rejected |
| Forced-tier-1 translation thread profiles | cold and warm profiles above | completed |
| AVX gain decision, main-thread CPU threshold 3% | eight accepted pairs above | completed: main -5.456%, total CPU -1.573%, fps +1.342%; explicitly not a 3% whole-game fps claim |
| Retrained PGO gain, same generated inputs | eight completed pairs below | no clear win; retain original trained profile |
| Old/new rollback, RTT 150 ms, 3% loss | `build/perf122/proof/rb150/` | completed; both through 3599, zero mismatches, hash `087916b94ba9c6d3` |
| Old/new lockstep | `build/perf122/proof/lockstep/` | completed; both through 3599, zero mismatches, hash `f2fdbfcb1219ebbb` |
| Recorded replays on retained build | playback directories above | 4 completed identical verdicts; see individual playback rows |
| Frame-exact old/new surfaces for the descriptor candidate | not performed | candidate 0118 was rejected; no renderer behavior change is retained |

For a future descriptor-path visual comparison, use a lockstep pair with identical graphics settings,
`RSX_TIER1_PATH=1`, `T5_NET_SHOT=300,900,1500`, and distinct per-side
`LD_SURF_DUMP` and `LD_SURF_DUMP_GATE` paths. Existing hooks dump every live
surface and the backbuffer. `tools/rollback_net_test.py` requires these dump and
gate variables explicitly through `--env1`/`--env2`; it does not create them as
`tools/netplay_test.py` does. Compare surface payloads and renderer frame counters
at each shot. Pool water and stage-20 puddles animate with renderer-frame count;
counter differences can make same-build pairs differ too. Report those cases
separately and rerun before claiming byte-identical pictures. Store all dumps
under ignored `build/`.


## Fresh PGO: eight completed comparison pairs

The before DLL uses the existing 1.2.1 profile; the after DLL uses the newly
trained seven-fight profile. Both use `--march none`, the same retained host,
the same generated source, and complete CSV/CPU windows. The two mask groups
are exchanged in repetition 2. All wrapper logs are
`build/perf122/logs/pgo-paired-0.log` through `pgo-paired-7.log`; each pair also
has `pair.json`, `before.log`, `after.log` and both games' full logs.

| pair / both run directories | masks before / after | main CPU ms before / after | total CPU ms before / after | sound CPU ms before / after | fps before / after |
|---|---|---:|---:|---:|---:|
| `build/perf122/pairs/pgo_pair_2c4t_s30_r1/before/` + `after/` | 0xf000 / 0xf0000000 | 5.4133 / 5.1090 | 23.4623 / 21.9038 | 5.4894 / 5.0486 | 55.7059 / 57.6558 |
| `build/perf122/pairs/pgo_pair_2c4t_s20_r1/before/` + `after/` | 0xf000 / 0xf0000000 | 5.0445 / 4.7796 | 21.8535 / 20.4905 | 4.9982 / 4.6353 | 59.7507 / 59.8462 |
| `build/perf122/pairs/pgo_pair_4c4t_s30_r1/before/` + `after/` | 0x5500 / 0x55000000 | 4.2948 / 3.8107 | 18.5886 / 16.4538 | 4.0343 / 3.3767 | 59.2787 / 59.8483 |
| `build/perf122/pairs/pgo_pair_4c4t_s20_r1/before/` + `after/` | 0x5500 / 0x55000000 | 4.6752 / 4.0766 | 20.6332 / 17.6357 | 4.5816 / 3.7604 | 58.1983 / 59.8573 |
| `build/perf122/pairs/pgo_pair_2c4t_s30_r2/before/` + `after/` | 0xf0000000 / 0xf000 | 5.4326 / 5.6030 | 24.1052 / 24.6865 | 5.1916 / 5.7711 | 55.0232 / 53.2313 |
| `build/perf122/pairs/pgo_pair_2c4t_s20_r2/before/` + `after/` | 0xf0000000 / 0xf000 | 5.2947 / 5.5978 | 22.9659 / 24.1403 | 5.2503 / 5.5080 | 58.5025 / 56.2299 |
| `build/perf122/pairs/pgo_pair_4c4t_s30_r2/before/` + `after/` | 0x55000000 / 0x5500 | 3.9857 / 4.4742 | 17.6223 / 19.4920 | 3.5798 / 4.1656 | 59.3485 / 58.5060 |
| `build/perf122/pairs/pgo_pair_4c4t_s20_r2/before/` + `after/` | 0x55000000 / 0x5500 | 4.2665 / 4.9862 | 18.0093 / 21.0569 | 3.9420 / 4.9738 | 57.9745 / 55.9937 |

After/before geometric ratios across the two crossed placements:

| condition | main CPU | total CPU | sound CPU | fps |
|---|---:|---:|---:|---:|
| 2c4t, stage 30 | 0.986595 | 0.977795 | 1.011108 | 1.000647 |
| 2c4t, stage 20 | 1.000856 | 0.992764 | 0.986372 | 0.981168 |
| 4c4t, stage 30 | 0.998012 | 0.989478 | 0.986911 | 0.997636 |
| 4c4t, stage 20 | 1.009473 | 0.999682 | 1.017640 | 0.996677 |

Overall: main **-0.130%**, total CPU **-1.010%**, SPU sound CPU **+0.041%**,
fps **-0.600%**. Each metric wins only 4/8 individual placements. Descriptive
95% intervals across the four crossed conditions all include ratio 1: main
0.9838-1.0139, total 0.9754-1.0046, sound 0.9749-1.0266, fps 0.9801-1.0081.
These small-sample intervals assume stable CCD effects; they do not remove
shared-machine uncertainty. The fresh profile is **not retained**. The existing
profile was already trained for promoted SPU code; its tracked bytes are unchanged.

Validation and full raw aggregation: `build/guest-store/paired-analysis/`,
`build/guest-store/pgo-final-analysis.json`, `build/guest-store/pgo-final-decision.json`.
All 16 accepted AVX/PGO pairs pass raw CSV, CPU denominator, main-thread log,
binary-hash, same-host and profile-isolation checks. The suffixed interrupted
pair is excluded. The final generated-input recheck found **27 files, 0 differences**
(`build/perf122/input_recheck.json`).

## Changed files and review handoff

| file | change |
|---|---|
| `CMakeLists.txt` | Common automatic CPU selection and explicit AVX1 source-build flags. |
| `README.md` | Current automatic CPU build-level guidance. |
| `docs/BUILD_PERF.md` | Distinguish the old scalar-code study from the measured vector AVX1 level. |
| `docs/PERF122_RUNS.md` | This complete run ledger, including exclusions and failed attempts. |
| `docs/RELEASE.md` | AVX/OS-state compatibility guard documentation. |
| `docs/RENDER_PERF.md` | 1.2.2 before/after results, decisions, limits and state proofs; correct stale PGO note. |
| `docs/WEAK_PC.md` | Optional AVX1 level without raising the minimum CPU requirement. |
| `patches/ps3recomp/0116-avx-software-fma.patch` | Exact AVX1 vector software FMA and the pre-initialization CPU/OS guard. |
| `tests/test_avx_level.py` | CPU/OS guard, deferred initialization, AVX/SSE cleanup and negative control. |
| `tests/test_fight_bench_rows.py` | Complete-row draining, timeout/exit and original-window bounds. |
| `tests/test_pc_compat.py` | Automatic AVX1 feature selection and feature omissions. |
| `tests/test_storepath.py` | Compiled optimized IR keeps both coherence checks and ordering. |
| `tests/test_vmx_vec.py` | AVX1 scalar/vector bit comparison alongside baseline and v3. |
| `tools/build_game_dll.py` | Safe AVX1 label, compiler flags and automatic feature probe. |
| `tools/fight_bench.py` | Drain buffered CSV before owned-process termination; persist coverage/window bounds. |

Proposed commit message: `perf: add exact AVX1 builds for old CPUs and fix benchmark windows`

Player-facing changelog line (not added to CHANGELOG.md):

> Older AVX-capable PCs automatically get a faster game build, with the same online game state.

No commit, push, release or deployment was performed. The working branch remains
`perf-122`, HEAD `f81432c4`. All game networking used localhost, with no real
account login. Changes are left in the working tree. Only AVX1 (0116), its build
integration, regression tests, documentation and the benchmark correction remain;
the synchronization/descriptor candidates and new PGO data are not shipped.


## Final bookkeeping checks

| check | evidence | result |
|---|---|---|
| Changed working-tree source scan (not just index) | `build/perf122/changed_source_guard.json` | All 15 changed files pass path, text, size, generated-code and embedded-data checks. No game data is added. |
| Final generated-input hashes | `build/perf122/input_recheck.json` | 27 generated input files unchanged from the build snapshot. |
| Legacy FMA speed assertion, controlled rerun | `build/perf122/logs/legacy_fma_controlled.log` | 1 test PASS in 2.567 s, two timing slots reserved. The earlier 97-test regression suite included this speed assertion without a reservation; that earlier timing is not acceptance evidence for any new performance claim. |

The retained-code 76-test suite and the cross-build/replay gates were already complete before this bookkeeping
check. The legacy check adds no product change and is not used to inflate the AVX or PGO gain.

### Explicit child-directory index

Compact parent tables above share a before/after or a/b prefix. These child paths
are expanded here for direct lookup; their results are in the corresponding tables.

- `build/perf122/runs/control_0x5500_s30_r1/`
- `build/perf122/runs/control_0xF000_s20_r1/`
- `build/perf122/runs/tier1_0x5500_s20_r1/`
- `build/perf122/runs/tier1_0x5500_s30_r1/`
- `build/perf122/runs/tier1_0xF000_s20_r1/`
- `build/perf122/runs/tier1_0xF000_s30_r1/`
- `build/perf122/runs/wait_0x5500_s20_r1/`
- `build/perf122/runs/wait_0x5500_s30_r1/`
- `build/perf122/runs/wait_0xF000_s20_r1/`
- `build/perf122/runs/wait_0xF000_s30_r1/`
- `build/perf122/pairs/avx_pair_2c4t_s30_r1_interrupted/before/`
- `build/perf122/pairs/avx_pair_2c4t_s30_r1_interrupted/after/`
- `build/perf122/pairs/pgo_pair_2c4t_s20_r1/after/`
- `build/perf122/pairs/pgo_pair_2c4t_s20_r2/after/`
- `build/perf122/pairs/pgo_pair_2c4t_s30_r1/after/`
- `build/perf122/pairs/pgo_pair_2c4t_s30_r2/after/`
- `build/perf122/pairs/pgo_pair_4c4t_s20_r1/after/`
- `build/perf122/pairs/pgo_pair_4c4t_s20_r2/after/`
- `build/perf122/pairs/pgo_pair_4c4t_s30_r1/after/`
- `build/perf122/pairs/pgo_pair_4c4t_s30_r2/after/`
- `build/perf122/proof/rb150/host/`
- `build/perf122/proof/rb150/join/`
- `build/perf122/proof/lockstep/host/`
- `build/perf122/proof/lockstep/join/`
- `build/perf122/replays/lockstep_host/p01_T5R-20261104-162644-ea0a/`
- `build/perf122/replays/lockstep_join/p01_T5R-20261104-162645-b41a/`
- `build/perf122/replays/rb150_host/p01_T5R-20261104-162516-fe4e/`
- `build/perf122/replays/rb150_join/p01_T5R-20261104-162518-cc31/`
- `build/perf122/resim/avx-resim-s30-r1/a/`
- `build/perf122/resim/avx-resim-s30-r1/b/`
