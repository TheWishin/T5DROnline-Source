# Preflight 1.2.3 (local, 2026-11-10/11)

Candidate: branch release-123-all at 566d8d89. Nothing was pushed, tagged, drafted, uploaded or deployed.
Run on the developer PC with the worktree's own venv (CPython 3.12.10), steps run one by one (not the
whole `tools/release_preflight.py`, so its steps 1-3, 6 and 7 are not part of this record).

| Step | Result |
|---|---|
| 1. `tests/ci_unittest.py -v --timeout 2400 test_layout_lobby_entry`, alone, normal priority | OK, 11 tests, 1273.6 s (21 min 14 s wall, 00:11-00:32). Another game and some Python jobs of other sessions were running on the PC. |
| 2. LLVM | `tools/fetch_llvm.py --dest build/rd/llvm`: SHA-256 OK, LLVM 23.1.3, 82 s |
| 3. ps3recomp | local clone at f17bcd3 as source, 95 patches applied, 32 s |
| 4. Player zip (`package_release.py --release --version 1.2.3`, inside vcvars64, MSVC 14.44.35207) | OK, 111 s. Binary check: 95 imports checked; scan of folder and zip: 2218 files, 275.6 MB, no game files, no lifted code, no keys (key-bytes scan run with the local keys file) |
| 5. `smoke_release.py` with the GUI checks, bare PATH | 14/14 checks passed, 37 s |

Zip: `D:\t4-night\w018\rel123all\build\preflight\123\dist\T5DR-Online-1.2.3.zip` (98,239,904 bytes)

SHA-256: `1b0b1b9041a99f7dfdebc1756f6329f737390f8fe6a809e8170577e4f77e7e6e`

GUI checks: the desktop had no input for over an hour. The checks use no window titles: the launcher is
rendered offscreen (5 tab images, exit 0 after 14 s) and `T5DR Online.exe` is started with a package chosen
(starter exit 0, launcher process still alive after 15 s, then closed by the check).

Not done here: preflight step 6 (all unit tests) and step 7 (changelog/README release lines) as one run, CI,
the update drills, the signing step. The zip is not code-signed (smoke: "no signing service set up").

Two first attempts at step 4 failed through a wrong relative LLVM path in the local helper script (not a
repository problem); the third run, with absolute paths, is the one recorded.

## Final candidate: release-123-final (2026-11-11)

Branch release-123-final = release-123-all (4559187c) plus, in this order:

| Commit | What |
|---|---|
| 7908bdf1 | Merge t5-spikes-018 (fbbb3d39): patch 0125, the ring-end flip (EWGF). No number collision: the series ended at 0124; 96 patches apply on f17bcd3 |
| 03e30fc6 | Merge quick-binds-018 (2d6b3568): the game's Controller Setup online (quick-match shortcuts). Reviewed: reads the offline SYS-DATA only (never writes a save), changes only this PC's sample before it is exchanged, inactive offline, in replays and outside a fight |
| b5038615 | Fix after the merge: game_setup.cpp includes t5_win.h (macOS syntax test), netplay_fuzz.cpp gets a stand-in for np::game_setup_buttons |

Build of b5038615's sources: `build_game.py --steps lift spu compile`, code id e1fd499920e36361, crossplay
t5x-b98cfc23bb3c. Nothing was pushed, tagged, drafted, uploaded or deployed. All runs one at a time
(HEAVY.lock), below normal priority, muted.

| Proof | Result |
|---|---|
| (a) Rollback pair RTT 60, final build both sides (Kazuya vs Heihachi, stage 20, 3 rounds, both mashing with motion inputs) | 8,400 frames compared, 0 mismatching; 8,768 frames, 3-1, hash 78a06e13006c60eb on both sides |
| (a) Rollback pair RTT 150, 3 % loss | 8,400 frames compared, 0 mismatching (2,721 / 2,702 rollbacks); 8,768 frames, 3-1, hash 38b7c8133d43fccb on both sides |
| (b) Lockstep pair RTT 60 | 6,600 frames compared, 0 mismatching; 6,697 frames, 0-3, hash f14708c18e0eb556 on both sides |
| The same three pairs on the build before b5038615 | 0 mismatching each; hashes e122c31bb00179be, 025fcb67debca4a1, 0c29c797d8d45f44, equal on both sides |
| (c) Offline Practice, Kazuya, EWGF x10, patch 0125 on (`tools/frame_skips.py`, build before b5038615) | Run 2: 2,017 frames, 0 requests over 1.6 frames apart, 0 lost pictures; 2 frames ended at the ring's end and kept their flip in the FIFO, 0 flips outside it. Run 1: 3 ring-end frames kept, 0 flips outside; one 2.4 s gap that the tool counts as a lost picture was a single pipeline creation taking 2,398 ms (`[hitch] pso frame=3656`), not the ring end |
| (d) `tests/test_game_setup.py`, `tests/test_ring_end_flip.py` | 5 + 9 tests OK |
| (d) Practice reset in the game (`tools/practice_state_check.py`, build before b5038615) | 2 of 3 runs PASS (17 resets, 0 bad; 5,403 frames, 0 different from the fresh round). First run FAIL: after each of 17 resets P1 did a kick and ended 359 units off its place, and the frames part was cut 90 frames short (0 different). The pre-merge build (566d8d89 + 0125) passed its one run. The merged code is not active offline; cause not found -- open |

Unit tests (worktree venv `rel123final-venv`, CPython 3.12.10, pillow + pycryptodome, PS3RECOMP_DIR = the
96-patch tree):

| Run | Result |
|---|---|
| Discovery without the three modules below, on b5038615 + this record | 1,948 tests, 3 failures, 0 errors, 15 skipped: only the three known venv failures. The known venv failures fail the same way on main (db9711a5) with this venv: test_compile_robust.Jobs.test_peak_memory_of_a_finished_process, test_release_tools.PeImports.test_python_exe, test_updater.Busy.test_process_list_sees_this_python. A first run on 03e30fc6 had two more (test_macos_port: game_setup.cpp, test_netplay_fuzz: setUpClass), from the quick-binds merge; b5038615 fixes them |
| test_font_fallback (on 03e30fc6) | 3 tests OK |
| test_i18n (on 03e30fc6) | 98 tests OK |
| test_layout_lobby_entry (on 03e30fc6) | 11 tests OK |

Not done: a new player zip and zip smoke for this branch (the zip recorded above is release-123-all's), CI,
update drills. The pairs use scripted pads and no offline save, so they show that the merge leaves the sync
intact, not the mapping itself; the mapping is covered by the unit tests only (no real controller, no real
quick match). Branch docs-123-018 (e046d819, made by another session in this worktree) has longer changelog
entries for both fixes and is not merged here.
