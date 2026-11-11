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

## Release candidate for the owner's test (2026-11-11 afternoon)

Branch release-123-final, on top of c5a10ffa (the input-delay merge stays reverted):

| Commit | What |
|---|---|
| b43edf2c | Docs from docs-123-018 (e046d819), taken once: the long changelog entries for the Controller Setup online and the ring-end flip replace the two short lines of 44ca1717; "rb_cost.txt" -> "the saved measurement"; the stale README RAM bullet (1.2 GB / 8 GB) removed (it contradicted the 4 GB / 0.8 GB bullet above it); `lobby/tests/test_nat2.py` paths in NETPLAY.md. From compat-docs CLAIMS_CHECK.md, the two T5DR items marked FALSE: T19 "~3 MB a fight frame" -> "~4 MB" (RENDER_PERF.md measured 4.2-4.4 MB), T36 = the RAM bullet. docs-123-018's second commit 44c8a12d is the same change as b5038615 (already here) |
| 2e2c4794 | Merge p1-swap-018 (d7e88267): F2 switches the offline Versus input display without the setting ticked and with the training overlay Off; a pad button does the same ([overlay] toggle, R3 by default), offline fights only. Not in c5a10ffa although tonight's test list has F2 and R3; clean merge |
| 6eaaf1b1 | Changelog: that fix folded into the 1.2.3 "Input display in offline Versus" entry (the F2 part fixes a 1.2.3 feature) plus one entry for the overlay button / F2 with the overlay Off |
| 3518bdc3 | `tests/test_practice_menu.py`: the full suite on 6eaaf1b1 failed `test_menu_shown_only_in_practice` (4th failure). The test matched the old local line `const bool online = ...`; since the merge the same condition is computed in `hotkeys()` (`w.online`, also while every display is off) and taken by `frame_body`. The test now checks that form. It fails the same way on d7e88267 itself (that branch did not run it). Tests are not in the player zip |

The zip, the owner's test install and the pair below are built from 6eaaf1b1; 3518bdc3 changes only a test
and this record only docs, so the shipped files are the same.

| Check | Result |
|---|---|
| `tests/test_vs_overlay.py`, `test_always_left.py`, `test_screen_side.py` after the merge | 12 + 26 tests OK |
| ps3recomp (`prepare_ps3recomp.py --source D:\t4-night\w018\ps3recomp`) | f17bcd3 + 96 patches applied, 13 s, `build/preflight/123b/ps3recomp` |
| Player zip (`package_release.py --release --version 1.2.3`, inside vcvars64, LLVM 23.1.3 from rel123all's `build/rd/llvm`, `--keys` = the local keys file for the scan) | OK, 105 s. 95 imports checked; scan of folder and zip: 2,221 files, 275.7 MB, no game files, no lifted code, no keys |
| `smoke_release.py` with the GUI checks | 14/14 passed (launcher offscreen: 5 tabs; starter with a package chosen alive after 15 s). Not code-signed |
| Preflight step 1 (`release_notes.py --check`, on b43edf2c) | section for 1.2.3 found (94 lines) |
| Preflight step 2 (`check_no_game_data.py`, index and `v1.2.2..HEAD`, on b43edf2c) | 1,102 files / 215 files, nothing game-derived |
| Preflight step 7 (changelog date, no HTML comments, README + README.de release lines), on b43edf2c and again on 3518bdc3 | no leftovers |
| Signing | owner (T5DR_RELEASE_SIGNING_KEY; not looked for). The launcher trusts update key c2acdfbc80f3c4c2 |
| Rollback pair, the test install's own t5dr.exe both sides (RTT 100, 2 % loss, Kazuya vs Heihachi, stage 20, mash + moves; host with T5_VS_OVERLAY=1, T5_TRAINING=frames, T5_TRAINING_ALL=1) | 6,600 frames compared, 0 mismatching; 6,921 frames, 2-1, hash 66cb88a8ee951822 on both sides; 2,198 / 2,104 rollbacks, 58.8 / 59.0 fps |

Zip: `D:\t4-night\w018\rel123final\build\preflight\123b\dist\T5DR-Online-1.2.3.zip`, 98,256,305 bytes,
2,221 files, SHA-256 `0a05d352c837da8fc70a9e17d1c9a89cf9e7c9b6b0be600402a1e5e12470e799`.
(An earlier zip of b43edf2c, before the merge, sha 27934fa9..., is replaced.)

**Owner test install.** The zip unpacked into `D:\t4-night\w018\owner-test-123\T5DR-Online-1.2.3\` and built
the way the launcher's BUILD GAME runs it: the bundled `python\python.exe tools\build_game.py --out
<folder>\native --pkg <owner's .pkg> --rap <owner's .rap>`, cwd `native`, PYTHONUTF8=1, below normal. The package
and license were read where they are (the .pkg in the owner's Downloads, the .rap in C:\T5DROnline\game);
nothing was copied into a git tree. Keys fetched by the build's own keys step (39 entries). PARAM.SFO: NPUB30009
version 01.00; program SHA-1 be80165b...a6a4 verified. Steps deps 1 s, keys 1 s, decrypt 1 s, unpack 13 s, lift
39 s, spu 4 s, compile 46 s (24 files, t5dr_game.dll 37.1 MB) -- 105 s. Code id 026ae10eb5865121, crossplay
t5x-b7bd005de04d (the merge of d7e88267 changes the code id; every 1.2.3 tester needs this same zip). The
launcher's Play tab state for that folder: "Ready: NPUB30009 v01.00 ... verified". No shader warm-up was run
(the launcher starts it itself). No launcher.json was written: the folder starts as a new player's folder.

Boot: `tools/smoke/run.py --only boot_menu,practice` against the install's t5dr.exe and game/vfs (own cwd and empty
gamedata, shader cache outside the install, muted, below normal): PASS, 29 checks, 88 s -- intro skipped, title
at 60.0 fps, practice select 58.8, a 12-s practice fight at 59.9 fps. No game process left.

**Unit tests and the whole preflight on the final code tree (3518bdc3).**

| Run | Result |
|---|---|
| `tools/release_preflight.py --version 1.2.3 --llvm <rel123all LLVM> --ps3recomp-source D:\t4-night\w018\ps3recomp --keys <local keys> --keep`, worktree venv, in an own detached worktree `D:\t4-night\w018\rel123pf` (the script empties `build/preflight/` first) | Steps 1-5 OK in 3 min (changelog 98 lines; guard 1,102 index files and 225 files of v1.2.2..HEAD; 96 patches; zip 98,256,305 bytes, 2,221 files, scan OK, sha 13cca2ac...89e79 -- not byte-equal to the 123b zip, same sources; zip smoke 14/14 with the GUI checks). **PREFLIGHT FAILED at 6** only through the three known venv failures: 2,062 tests in 1,669 s, failures=3, skipped=15 -- test_compile_robust.Jobs.test_peak_memory_of_a_finished_process, test_release_tools.PeImports.test_python_exe, test_updater.Busy.test_process_list_sees_this_python (they fail the same way on main db9711a5 with this venv, see above). Step 7 is not reached by the script; run on its own on 3518bdc3: no leftovers. HEAVY.lock was held for steps 1-5 only |
| The same discovery on 6eaaf1b1 (before the test fix) | 2,062 tests, failures=4 (the three above + test_practice_menu, fixed in 3518bdc3), skipped=15, 1,706 s |
| `tests/ci_unittest.py -v --timeout 2400 test_layout_lobby_entry`, alone (other agents' games and the preflight's suite ran on the PC at the same time) | OK, 11 tests, 681 s |

Not done: CI, update drills, signing, a lockstep pair and a ranked/quick match on the merged build (the one rollback
pair above has scripted pads), anything with a real controller. Nothing was pushed, tagged, drafted, uploaded or
deployed; the lobby server is unchanged (the ranked costume row and the win records need the new one).

## Practice-reset fix merged; the owner's test install replaced (2026-11-11, 16:00-16:30)

| Commit | What |
|---|---|
| ab71527f | Merge practice-flake-018 (96a54034, based on c5a10ffa): a button pressed as the Practice round comes up was kept in the reset state and played again after every SELECT+3. Both pads are held neutral from the fight's loading (phase 7..16) until the state is kept (offline Practice only, `T5_PRACTICE_NEUTRAL_START=0` turns it off); tools/practice_state_check.py waits for the game. No conflicts with 2e2c4794 / 3518bdc3 (git merged practice.cpp, practice_logic.h, the tests and TRAINING.md by itself). One sentence added to the existing 1.2.3 Practice reset entry of the changelog |

| Check (on ab71527f) | Result |
|---|---|
| test_training, test_practice_menu, test_practice_state_check, test_game_setup, test_netplay_fuzz (+ test_vs_overlay) | 23 + 10 + 8 + 5 + 1 (+ 12) = 59 tests OK |
| Full discovery (`python -m unittest discover -s tests`, worktree venv, PS3RECOMP_DIR = 123c tree) | 2,070 tests in 1,642 s, failures=3 (only the known venv three: test_compile_robust.Jobs, test_release_tools.PeImports, test_updater.Busy), skipped=15 |
| Player zip, procedure as above into `build/preflight/123c` (fresh 96-patch tree) | OK, 91 s; 95 imports checked; scan of folder and zip: 2,221 files, 275.7 MB, no game files, no lifted code, no keys |
| `smoke_release.py` with the GUI checks | 14/14 passed |
| Owner test install | Old folder renamed to `D:\t4-night\w018\owner-test-123\T5DR-Online-1.2.3-old` (nothing ran from it; it had no launcher.json and no save), new zip unpacked at the same path, BUILD GAME as before: 80 s, NPUB30009 v01.00, program verified, code id 5dc12e62a8b08b76, crossplay t5x-aca7330335c2. Launcher Play state: "Ready" |
| Boot (`tools/smoke/run.py --only boot_menu,practice` on the install's game) | PASS, 29 checks |
| `tools/practice_state_check.py` on the install's game (resets + frames) | PASS: 17 resets, 0 bad, 0 sides flipped, worst place 0 units, worst facing 0.00 rad; 3 resets x 1,801 frames = 5,403 frames compared with the fresh round, 0 different |
| Lockstep pair on the install's game (RTT 60, `--mode1 off --mode2 off`, Kazuya vs Heihachi, stage 20, 3 rounds, mash + moves) -- the pair missing after the F2/R3 merge | 10,200 frames compared, 0 mismatching; 10,326 frames, 3-2, hash cc17ad78d06d5953 on both sides |

Zip: `D:\t4-night\w018\rel123final\build\preflight\123c\dist\T5DR-Online-1.2.3.zip`, 98,258,061 bytes, 2,221 files,
SHA-256 `3ef4046bcaf4eb99ba3e933c7f6070fcf75f217aba7bee371c4243753a966172`. It replaces the 123b zip (0a05d352...)
for tonight's test.

Not done on ab71527f: a rollback pair (the rollback pair above ran on 6eaaf1b1; the practice change is gated to
offline Practice), the branch's own repro (mash_repro.py) on this build, the whole release_preflight.py run, CI,
update drills, signing, anything with a real controller or a real two-PC match.
