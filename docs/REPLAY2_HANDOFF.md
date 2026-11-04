# replay2 implementation and release gates

Branch: `replay2`, based on v1.2.0. No Backdash source, art or text was used. No commit or push.
All implementation, build, test and run artifacts are inside this worktree; the only external
writes are the mandatory shared heavy-slot locks, removed after each owned run.

## Implemented behavior

- Per-match compressed start capsules, captured after loading at a confirmed live boundary.
  Watch loads the selected setup and restores its capsule; old/missing/wrong-build sidecars
  retain session-start playback. Format 1–7 input semantics are unchanged.
- Seek restores compressed periodic rollback checkpoints and resimulates recorded inputs.
  Eight checkpoints, including the origin, bound the cache. The last catch-up frame is presented; the seekable start is one frame after the origin so even a jump to the beginning refreshes the picture. Seek parks before the requested
  input frame. Loading and previous matches are outside the current seek cache.
- Recorded round marks for new sessions, progressively discovered marks for older files.
- 0.25x/0.5x slow motion, 1x, and 2x/4x using skipped draws/presents during undecided fights.
  Loading and result transitions retain normal pacing. Actual performance needs measurement.
- Pause/resume, exact single frame step, P1/P2 local takeover, and permanent unverified
  provenance in status and verdict. A seek catches up on recorded inputs before takeover resumes.
- Launcher filters for either fighter, opponent, netcode and favourites; per-match favourites;
  timeline, round list and all playback controls. Seven languages, including the English source.
- Graceful local command/status IPC; no live-stream spectator changes and no online takeover.

Start capsules include game memory, CPU, RNG, reader tokens, input-rule and driver state. They
are local cache files and are deliberately excluded from reports/privacy exports. No start
capsules are persisted with replay names disabled, because raw guest memory can retain names;
that privacy mode retains historical session-start playback. Folder move
and deletion currently apply to the original replay files; sidecars may need separate cleanup.

## Files

Runtime:
`src/replay/blob.h`, `src/replay/viewer.h`, `src/netplay/replay.cpp`, `replay.h`, `replay_zlib.cpp`,
`t5_hooks.cpp`, `netplay_core.cpp`, `netplay.h`, `src/rollback/rb_state.cpp`, `rb_state.h`,
`rb_net.cpp`, `rb_net.h`, `rb_hooks.cpp`, `rb_rand.cpp`, `src/directfight/df_fight.cpp`,
`df_hooks.cpp`, `df.h`.

Launcher:
`launcher/replay_library.py`, `replays_ui.py`, `t5dr_launcher.pyw`,
`lobby/t5lobby/i18n_{de,es,fr,ja,ko,pt_br}.py`, `tools/package_release.py`, `tools/smoke_release.py`.

Tests/documentation:
`tests/c/replay_test.cpp`, `replay_state_test.cpp`, `replay_viewer_test.cpp`,
`tests/test_replays.py`, `test_replay_viewer.py`, `test_replay_library.py`,
`test_replay_viewer_check.py`, `test_replay_folder_ui.py`, `tools/replay_viewer_check.py`,
`docs/REPLAYS.md`, this handoff. 

## Unit and build evidence

All suites isolate `OPENRECOMP_HOME`, `APPDATA`, `LOCALAPPDATA`, `TEMP` and `TMP`. The owner's
real OpenRecomp config hash was checked before/after and stayed unchanged.

| Run | Result | Artifact |
|---|---|---|
| Viewer policy | Pass | `build/replay-viewer-tests.log` |
| Viewer plus blob boundary tests | Pass | `build/replay-viewer-tests-blob.log` |
| Driver/RNG syntax | Pass; two pre-existing format warnings | `build/replay-host-syntax.log` |
| Initial integration syntax | Failed: name clash and Windows min/max macros, fixed | `build/replay-integration-syntax.log` |
| Corrected hook syntax | Pass | `build/replay-hooks-syntax-final.log` |
| Initial capsule suite | One incorrect new expected frame in test, fixed | `build/replay2-capsule-tests/replays.log` |
| Corrected capsule suite | Pass | `build/replay2-capsule-tests/replays-final.log` |
| Capsule/state suite | 35 tests: 32 pass, 3 Tk skips | `build/replay2-capsule-tests/replays-final2.log` |
| Native synthetic full state test compile | Pass | `build/replay2-capsule-tests/rb-state-compile.log` |
| Initial launcher/i18n | Environment failure: installed Tcl lookup | `build/replay2-launcher-tests/unit-i18n.log` |
| Launcher/full i18n with worktree Tcl copy | 106 pass, including seven-language layout walks | `build/replay2-launcher-tests/unit-i18n-tcl-local.log` |
| Launcher focused checks | 26 pass | `build/replay2-launcher-tests/library-ui.log` |
| Added UI regression checks | 11 pass | `build/replay2-launcher-tests/library-ui-final.log` |
| Launcher final checks | 27 pass | `build/replay2-launcher-tests/library-ui-complete.log` |
| Full replay-related suite, first run | 107 tests, one old folder-test mock fixture needs new filter setup | `build/replay2-final-tests/replay-suite.log` |
| Full replay-related suite, corrected | 112/112 pass | `build/replay2-final-tests/replay-suite-final.log` |
| Data-region manager address regression | Pass | `build/replay2-final-tests/viewer-address-regression.log` |
| Probe predicate/environment units | 5 pass | `build/replay2-launcher-tests/viewer-probe-unit.log` |
| Folder UI mock regression | 7 pass | `build/replay2-launcher-tests/folder-ui.log` |
| First host configure | Access denied running installed WinGet CMake | `build/replay2-host-build.log` |
| VS CMake + older shared runtime | Configure pass; build fails on missing existing overlay-layer APIs | `build/replay2-host-build-vs.log` |
| VS CMake + compatible patched runtime | Build pass; US game DLL copied locally | `build/replay2-host-build-patched.log` |
| Incremental integrated host build | Pass | `build/replay2-host-incremental.log` |
| Legacy 1.2.0 rollback playback | Pass: 3 results,113 hashes,0 differences; 144.1s | `build/legacy-rollback/run.log`, `verdicts.jsonl` |
| Legacy 1.2.0 lockstep playback | Pass: 1 result,42 hashes,0 differences; 64.1s | `build/legacy-lockstep/run.log`, `verdicts.jsonl` |
| Final round-mark host rebuild | Pass | `build/replay2-host-rounds.log` |
| Viewer controls, corrected | Pass: pause,3 exact steps,back/forward seeks,all speeds,29 hashes,0 differences,identical result | `build/viewer-controls-rb2/result.json` |
| P1 takeover | Pass: control,60 local frames,control0 preserves unverified frame696 | `build/viewer-take-p1/result.json` |
| New rollback recording pair | Pass: 2 matches,0 mismatches on both peers,capsules and round index written | `build/capsule-proof/pair/report.json`, `pair-run.json` |
| Independent match2 start | Pass: only match2,35 hashes,0 differences,same live final hash | `build/capsule-match2/p01_T5R-20261104-123117-70c9/verdict.json` |
| Seek final-frame presentation rebuild | Pass | `build/replay2-host-seek-present.log` |
| Viewer controls after presentation fix | Pass:29 hashes,0 differences,identical result | `build/viewer-controls-rb3/result.json` |
| P2 takeover | Pass:60 local frames,control0 retains unverified frame704 | `build/viewer-take-p2/result.json` |
| Lockstep streaming-exclusion rebuild | Pass | `build/replay2-host-audio-excludes.log` |
| Lockstep viewer controls | Pass:45 hashes,7/7 sync,0 differences,identical result | `build/viewer-controls-ls/result.json` |
| Privacy cache guard rebuild | Pass | `build/replay2-host-privacy.log` |
| Anonymous binary writer rebuild | Pass | `build/replay2-host-privacy-binary.log` |
| Final replay suite before privacy guard | 113/113 pass | `build/replay2-final-tests/replay-suite-release.log` |
| Final complete replay suite | 114/114 pass, including anonymous binary/no-capsule regression | `build/replay2-final-tests/replay-suite-privacy-final.log` |
| Two-slot timing audit | Not run: only one slot free, two required | `build/replay2-perf-slot-audit.json` |
| First viewer control probe | Pause +3 exact steps pass; seek rejected by overly strict data-region manager validator, corrected | `build/viewer-controls-rb/result.json`, `events.jsonl`, `game.log` |

No timing claim follows from a build or a model test. The synthetic state harness allocates its
own blank VM and tests real snapshot/restore, exclusion changes, preserved live bytes and rejected
truncation/bad page maps; it contains no game data.

## Exact real-game gates

Completed subsets are recorded above; do not repeat unchanged successful gates just to broaden
this report. Still needed: the full multi-round/new-lockstep recording matrix, independent match3
and lockstep capsules, Mokujin/custom-costume/handicap/skip combinations, cache eviction and
round-jump stress, visual/audio inspection, takeover beyond original result and lifecycle exits.
The isolated speed/capture-cost measurement was blocked by shared slot availability: only one
slot was free at the final audit, two are required. No claimed achieved speed multiplier.


For every command below: acquire a shared heavy slot atomically; release it in `finally`,
including timeout/failure. One pair per slot. Performance runs require two free slots. Set
`PS3_AUDIO_MUTE=1`, `PS3_WINDOW_BACKGROUND=1`; launch BelowNormal. Never use a lobby, real account
or public address. Replay mode has no socket; pair tests bind exclusively to `127.0.0.1`.
Use a private HDD0 copy and isolated application/temp directories, all below `build/`.

Use the freshly built `build/cmake-replay2/t5dr.exe`, the owner's US v1.00 VFS as read-only input,
and set `PS3_HDD0_ROOT` to the worktree copy. `$OldRb` and `$OldLs` below are the existing format-7
1.2.0 corpus files identified in the local run scripts.

1. **Legacy rollback:** `python tools/replay_play.py --exe $Exe --vfs $Vfs --out build/legacy-rollback
   --match 0 --timeout 240 --env PS3_HDD0_ROOT=$Hdd $OldRb`. All three match results and hashes must
   be identical; no capsule opt-in. Repeat for `$OldLs` under `build/legacy-lockstep`.
2. **New recording, rollback:** `python tools/fight_flow_test.py --exe $Exe --vfs $Vfs
   --out build/replay2-pair-rb --flow rematch --matches 3 --rounds 2 --chars 9,33
   --stages 20,27,30 --mash --moves --polite --port 29610 --seconds 600
   --env T5_NET_BIND=127.0.0.1 --env T5_REPLAY_DIR=<per-side-worktree-dir>`.
   Keep each side's recording directory distinct via `--env1`/`--env2`. Require both sides'
   three results to agree, zero mismatching frames, and `.start1`/`.start2`/`.start3` plus round marks.
3. **New recording, lockstep:** repeat gate 2 under `build/replay2-pair-ls`, port 29620,
   `--env T5_RB_MODE=off`. Require zero mismatching frames. Play every file from both pairs with
   `tools/replay_play.py --match 0`; all recorded hashes/results must be identical.
4. **Independent starts:** fresh process, select match 2 and then 3 from both new recordings,
   `T5_REPLAY_CAPSULES=1`, matching actual `T5_NET_BUILD`. Require the restored target frame in
   the log, no preceding fight, zero hash mismatches, correct winner/score/final hash. Include stage27,
   Mokujin, custom costumes, handicap and automatic intro/round skip rules in follow-up cases.
5. **Seek/control matrix:** `python tools/replay_viewer_check.py --exe $Exe --vfs $Vfs
   --out build/viewer-<case> --hdd0 build/viewer-<case>/hdd0 --file $Replay --match <N>
   --scenario controls --timeout 240 --command-timeout 60` (make a private HDD0 copy under this
   fresh output first). For each netcode on an old file and a new independent-start file: pause,
   step three times (each status frame increases by exactly one), seek backward60 and forward90
   frames (paused exactly at target), jump to each round, ±600 frames, seek to origin and end,
   repeat after >8 checkpoints have evicted middle entries. Run to the end and require identical.
   Repeat after ring discovery/round change; verify audio and picture resume after every restore.
6. **Takeover:** repeat the probe with `--scenario take-p1` and `--scenario take-p2`, fresh output/private HDD0 for each, seek and step to a known frame, take control,
   inject different directions/buttons, verify only chosen side changes. Require
   `verified=false`, correct `unverified_from`, `identical=false`. Seek earlier, return to
   recorded inputs (`control 0`) and verify provenance remains unverified; no socket or online result.
7. **Skipped-present performance:** with two slots held and no other timing load, replay the
   same recorded undecided fight interval at 1x,2x,4x,0.5x,0.25x, three runs each. Measure simulated
   frames/wall-time and actual presents, not displayed FPS alone. Require preserved hashes/results;
   report achieved rates, present counts and frame-time distribution. Do not claim 2x/4x until measured.
8. **Viewer lifecycle:** quit before first fight, during load, paused, seeking, at final frame,
   and between matches; Stop and window close. Expect process exit and launcher release. Open old
   files with absent/corrupt/wrong-build sidecars and verify safe legacy fallback. Export a names-stripped
   replay and verify the original privacy behavior with no start capsules attached.

## Proposed commit

`feat(replays): add snapshot seeking and interactive replay viewer`

Player-facing changelog lines (CHANGELOG.md intentionally untouched):

- Find replays using fighter, opponent and netcode filters, and keep per-match favourites.
- Watch with seeking, round jumps, speed, frame step and local P1/P2 takeover marked unverified.
- New local match-start caches allow later matches to open independently; old replay files remain supported.

## Final verification state

Final host executable SHA256: `1ad962a3a5dd1733daf3f785078961241235fe204367e55118c9fee0b96dd904`.
Final build/test result and real-config before/after hash:
`build/replay2-final-tests/result-privacy-final.txt`. `git diff --check` passed.
No test/game processes or heavy locks remain owned by replay2. No commits, pushes, live servers
or real account logins. CHANGELOG.md untouched. The final privacy writer changes affect new
names-off recordings only; all names-on playback/game proofs above remain applicable.

Exact changed/new files:

- `docs/REPLAY2_HANDOFF.md`
- `docs/REPLAYS.md`
- `launcher/replay_library.py`
- `launcher/replays_ui.py`
- `launcher/t5dr_launcher.pyw`
- `lobby/t5lobby/i18n_de.py`
- `lobby/t5lobby/i18n_es.py`
- `lobby/t5lobby/i18n_fr.py`
- `lobby/t5lobby/i18n_ja.py`
- `lobby/t5lobby/i18n_ko.py`
- `lobby/t5lobby/i18n_pt_br.py`
- `src/directfight/df.h`
- `src/directfight/df_fight.cpp`
- `src/directfight/df_hooks.cpp`
- `src/netplay/netplay.h`
- `src/netplay/netplay_core.cpp`
- `src/netplay/replay.cpp`
- `src/netplay/replay.h`
- `src/netplay/replay_zlib.cpp`
- `src/netplay/t5_hooks.cpp`
- `src/replay/blob.h`
- `src/replay/viewer.h`
- `src/rollback/rb_hooks.cpp`
- `src/rollback/rb_net.cpp`
- `src/rollback/rb_net.h`
- `src/rollback/rb_rand.cpp`
- `src/rollback/rb_state.cpp`
- `src/rollback/rb_state.h`
- `tests/c/replay_state_test.cpp`
- `tests/c/replay_test.cpp`
- `tests/c/replay_viewer_test.cpp`
- `tests/test_replay_folder_ui.py`
- `tests/test_replay_library.py`
- `tests/test_replay_viewer.py`
- `tests/test_replay_viewer_check.py`
- `tests/test_replays.py`
- `tools/package_release.py`
- `tools/replay_viewer_check.py`
- `tools/smoke_release.py`
