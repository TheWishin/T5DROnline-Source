# 1.2.3 integration (branch `integration-123`)

Release candidate source for 1.2.3, made from `main` db9711a5 (v1.2.2) on 2026-11-10. Nothing was built into a game,
released, tagged, pushed or deployed. The merged branches themselves were not changed.

## Merges, in order

| # | Branch (tip) | Merge commit | Conflicts |
|---|---|---|---|
| 1 | `t5-perf-123` (5b36ef32; patch 0123 incl. the ring-wrap wake) | d97e21e3 | none |
| 2 | `flash-hz-018` (2be9d7d1; patch 0124) | e7e9c13e | `docs/RENDER_PERF.md` |
| 3 | `vs-overlay-018` (f4e006e4) | e8a016a5 | `CHANGELOG.md` |
| 4 | `playtime-old` (b918f0e5) | c5464d62 | none |
| 5 | `settings-sync` (a72c5cd3, with 22562b68) | 1eb9b830 | none |
| 6 | `t5-costumes-123` (36dfaae7) | 1f013ff2 | `CHANGELOG.md` |
| 7 | `t5-winrate-123` (5b0e05c5) | 9b030cca | `lobby/t5lobby/client.py`, `lobby/t5lobby/server/lobby.py` |
| 8 | `practice-state-018` (0bf5459e) | 4a8cbd7b | none |

`t5-perf-123` sits on `t5-longsession-123` (2a55e17a), so merge 1 also brings a9bc6ca4 (offline Versus never
mirrored), 04d7f9a8 (rollback cost: trimmed means), df896c64 and 2a55e17a (docs, screen side test).

After the merges:

- eb03524e, 0652d76f: the two test-only commits of `lobby-deploy-123` (681c952c, 19ff1514; stand-in tabs and players
  for the win records in five lobby test modules), taken with `cherry-pick -x`.
- 7a9999ef: `docs/INTEGRATION_1.2.0.md` says 31 capabilities (see "Found by the suite").
- After merge 8: the settings guard for launchers started as processes (see "Settings sync: test status") and the
  capability count pinned by a test (see "Capability count").

## Conflict decisions

Both sides were kept every time.

- **`docs/RENDER_PERF.md` (merge 2):** both branches added sections at the end of the file. Order: the 1.2.3 perf
  sections, then "Black flashes on fast displays" (patch 0124).
- **`CHANGELOG.md` (merges 3 and 6):** the perf branch names the section "Unreleased (1.2.3)", the others "Unreleased".
  One section "Unreleased (1.2.3)"; the other branch's entries went under the heading of the same name (vs-overlay's two
  under Offline, the ranked costume entry under Online). No text changed.
- **`lobby/t5lobby/client.py`, `lobby/t5lobby/server/lobby.py` (merge 7):** costumes and win records each added a
  client option and a capability at the same lines (`ranked_costume`, `hud_records`; `CAPS |= ...`). Both kept, in
  the order `lobby-deploy-123` uses: the two files were taken from its merge 2d4fe006, so the launcher's files and the
  server branch's files are the same there. After merge 7, `lobby/` differs from 2d4fe006 only in the six language
  catalogs (texts of the other merged branches).

- **`practice-state-018` (merge 8):** no text conflict. Decision: merged whole, now that the branch is one finished
  commit (0bf5459e, "SELECT+3 puts the round's first state back (offline games)") on main db9711a5 with a clean
  worktree; the first integration left it out as unfinished. It changes `src/training/practice.cpp`,
  `src/training/practice_logic.h` and `src/netplay/t5_hooks.cpp`, files that merge 3 (vs-overlay, `src/training`)
  and merge 1 (perf, `src/netplay`) also change in other places: git joined them without a conflict, both sides are
  in. The joined C++ was not compiled or run here (no game build in this job) -- it belongs to step 1 of "Before a
  release". The branch has no CHANGELOG entry (its text is in `docs/TRAINING.md`); one is to be written with the
  release notes. `tests/test_training.py`: OK at the head.

## Patch series

`tools/prepare_ps3recomp.py` on a fresh tree at the pin: 93 patches on main, 94 after merge 1, 95 after merge 2 and
at the head. 0123 and 0124 both change `libs/video/rsx_live_draw.c`; 0124 was made without 0123 and applies after it
as it is. The two together were not compiled or run here.

## Root suite per step

The CI way (`tests/ci_unittest.py`, the three layout modules on their own), in a venv made for this job
(Python 3.12, pycryptodome, pillow), `APPDATA` / `LOCALAPPDATA` pointed at an empty folder per run, each step on a
detached copy of its commit. `PS3RECOMP_DIR` = the freshly patched tree of that step.

| Step | Head | Tests | Failed | Skipped | i18n / font / lobby layout |
|---|---|---|---|---|---|
| main | db9711a5 | 1,796 | 3 | 12 | 98 OK / 3 OK / timed out at 900 s |
| 1 perf | d97e21e3 | 1,809 | 3 | 12 | 98 OK / 3 OK / timed out |
| 2 flash-hz | e7e9c13e | 1,817 | 3 | 12 | 98 OK / 3 OK / timed out |
| 3 vs-overlay | e8a016a5 | 1,827 | 3 | 12 | 98 OK / 3 OK / timed out |
| 4 playtime | c5464d62 | 1,870 | 3 | 12 | 98 OK / 3 OK / timed out |
| 5 settings-sync | 1eb9b830 | 1,902 | 3 | 15 | 98 OK / 3 OK / timed out |
| 6 costumes | 1f013ff2 | 1,902 | 4 | 15 | 98 OK / 3 OK / 11 OK |
| 7 win records | 9b030cca | 1,905 | 4 | 15 | 98 OK / 3 OK / 11 OK |
| head | 7a9999ef | 1,905 | 3 | 15 | 98 OK / 3 OK / 11 OK |

- The 3 failures are the same on main and at every step and come from the venv: its `python.exe` is a small starter
  for the real interpreter (`test_compile_robust.Jobs.test_peak_memory_of_a_finished_process`,
  `test_release_tools.PeImports.test_python_exe`, `test_updater.Busy.test_process_list_sees_this_python`).
- `test_layout_lobby_entry` needs 560-885 s for its 11 tests on this PC; with three suites running at once it passed
  the 900 s limit (main too). Runs with fewer suites beside them, or a 2,400 s limit, pass.
- Steps 6 and 7 were run twice: the first run died at the fourth failure while printing it (cp1252 output, an
  arrow character in the message); the numbers are from the second run with UTF-8 output.
- Lobby modules the merges touch, at the head: test_cycle6_lobby_ui 2, test_ping_delay_contract 4,
  test_room_leave_regressions 8, test_spectate_dispatch 5, test_tk_callback_cleanup 4, test_ranked_costume 21,
  test_hud_records 12, test_tk_charsel 5: all OK. The whole lobby suite was not run.
- `tools/check_no_game_data.py`: 1,084 files, nothing game-derived.

## Found by the suite

`tests/test_audit_cycle1_docs.py` compares the capability count in `docs/INTEGRATION_1.2.0.md` with the client's
hello. `t5-costumes-123` and `t5-winrate-123` each add one capability and left the count at 29, so the test fails on
each branch alone (step 6: 30, step 7: 31). Fixed at the head: 31. `lobby-deploy-123` (3f4596b3) says 30 and also has
`profile_pics`, so its client sends 32 and the same test should fail there (read from its files, not run). 32 is also
all the server reads (`caps[:32]`): the next capability after the profile picture would be dropped without a word.

## Settings sync: test status

Its own module `tests/test_settings_sync.py`: 29 pass, 3 skipped (they need an OpenRecomp checkout in
`T5DR_TEST_OPENRECOMP_SRC`; none was given, and the owner's OpenRecomp folder is not to be touched). The runs wrote
nothing into the real `%APPDATA%\T5DROnline` (checked: only `online.json` from 2026-11-08 is there) and nothing into
the runs' own stand-in folders. Closed after merge 8: the guard in `launcher/core.py` was "unittest was imported before core", so a launcher that a
tool or test starts as its own process (GUI smoke of the preflight, e2e, i18n_layout) could read and write the
player's real settings.json when the tool forgot `T5_SETTINGS_DIR` / `T5_ONLINE_DIR`. Now the player's folder is
used only by a launcher a player started (`core.shared_settings_refusal`): the launcher's `main()` declares itself
(`core.declare_launcher`), and it is refused when started with a testing option (`--screenshots`, `--build-steps`,
`--play-seconds`, `--low-priority`, `--force`), from a source tree (`.git` or `tests/ci_unittest.py` next to it), from
a folder inside the temporary folder, or with a test variable set (`CI`, `GITHUB_ACTIONS`, `PYTEST_CURRENT_TEST`,
`T5DR_TESTING`, `T5_FW_CHECK=0`, `T5DR_FW_CHECK=0`). Refused = no shared file at all (launcher.json only), one line
in launcher.log. A folder named by `T5_SETTINGS_DIR` / `T5_ONLINE_DIR` is used by any process, as before. Decision:
refuse, not redirect -- a process cannot know a tool's test folder, and a guessed one would hide the mistake.
Consequence: a launcher run from a developer checkout no longer shares settings with OpenRecomp unless
`T5_SETTINGS_DIR` names the folder. `tests/test_settings_guard.py` (11 tests) runs `core` in child processes that
are no unittest run and have none of the variables, with `APPDATA` pointed at the test's own stand-in folder: none
writes the stand-in "real" path, the player's own launcher does. Not done here (owner's PC): the same with real
launcher windows and the real OpenRecomp.

## Capability count

A fully enabled 1.2.3 client sends **31** capabilities in its hello (the last two are `ranked_costume` and
`hud_records`); the server reads the first **32** (`caps[:32]`), so one place is left. `docs/INTEGRATION_1.2.0.md`
says 31. `tests/test_audit_cycle1_docs.py` checks the number against the client's hello, the two names on both sides,
the server's limit and both documents. `lobby-deploy-123` is a different state (it also has `profile_pics`, one more).

## Playtime

The whole commit is this repository's launcher (Play tab, `launcher/playtime.py`, updater keeps `playtime.json`, the
release zip carries the module, six catalogs, 43 tests) and nothing else, so it was merged whole. It keeps
`playtime.json` next to `launcher.json` (per folder), while merge 5 moves the settings to one file per user: a second
T5DR folder starts its playtime at 0.

## Left out

- **`profile-pic-018` (ba83d6fe):** in `lobby-deploy-123` but not in the list for this integration. The 1.2.3
  launcher from this branch has no profile pictures; a server from `lobby-deploy-123` offers them.
- **Whole lobby suite, game build, pairs, e2e, smoke, preflight:** not run. No heavy game job was started, so
  `D:\t4-night\day\locks\HEAVY.lock` (an entry from 2026-11-06) was neither needed nor touched.

## Before a release

1. Build and run 0123 + 0124 together (smoke quick, rollback and lockstep pairs, old/new cross pair), and decide
   whether 1.2.3 needs a new CODE_VERSION: merge 7 changes `src/directfight/df_fight.cpp`, merge 1 `src/netplay`
   and `src/rollback`, merge 3 `src/training`; no branch changed the number.
2. Server and launcher from the same state: decide on the profile picture (in or out on both sides) and fix the
   capability count on `lobby-deploy-123`.
3. Settings sync against the real OpenRecomp code (the 3 skipped tests) and with launchers started as processes.
4. The commits of the merged branches carry co-author lines; `tools/publish_source.py` removes them for the public
   mirror as before.
