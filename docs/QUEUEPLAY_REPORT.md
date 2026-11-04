# Queueplay implementation report

## Design

The launcher waits for a persistent game's acknowledged, loaded native
Practice state before requesting quick/ranked matchmaking. A found match
uses the existing secure in-game UI channel and `rsx_overlay` layer for
NEW CHALLENGER, pad accept/decline and a 15-second countdown. Only the lobby's
match-start event sends the normal fight command. Decline, expiry and
cancel leave Practice open; older games retain the previous launcher flow.

Local Practice input, START and Practice tools are enabled only outside a
netplay session. The challenger captures offline input until button release.
The accepted session uses the existing leave/select/title/boot-state restore
path, including autosave/reader guards and the existing loading sync point.
Practice neither increments replay/match ordinals nor changes online rules.
No runtime patch or external implementation was copied: the existing overlay
patches already provide the required layer/font/pad APIs.

Initial Practice automatically confirms the game's native initial cursors.
The optional practice-command `T5_FIGHT` payload does not yet choose the
offline fighters; online fighters still follow the lobby's agreed selection.

## Files

- `src/directfight/df_ctl.cpp`, `df_fight.cpp`: Practice command/state,
  native startup, free offline phase, existing reset/session handoff.
- `src/directfight/df_ui.cpp`, `df_ui.h`, `ui_logic.h`: challenger styling,
  offline input capture/release policy on the existing overlay channel.
- `src/netplay/t5_hooks.cpp`: local input while the persistent game has no
  session, Practice tool cleanup, restoration of the normal online path.
- `src/training/practice.cpp`, `training.cpp`: allow tools/display during
  explicitly local persistent Practice; preserve online/replay restrictions.
- `lobby/t5lobby/match_driver.py`, `tk_tab.py`, `tk_views.py`: delayed queue
  start, ready checking, challenger votes/fallback, persistent process reuse.
- `lobby/t5lobby/i18n_{de,es,fr,ja,ko,pt_br}.py`: translations; English uses
  the original source strings, covering all seven supported languages.
- `lobby/tests/test_queueplay.py`: launcher/driver state-machine tests.
- `tests/c/rematch_ui_test.cpp`, `tests/test_rematch_integration.py`,
  `tests/test_training.py`, `tests/test_practice_menu.py`: pad/clock and
  integration/guard coverage.
- `lobby/tests/test_audit_client.py`: initialize the existing hand-built driver
  fixture's new challenger state.
- `tools/queueplay_test.py`, `tests/test_queueplay_proof.py`: local
  Practice-versus-fresh pair/replay proof and fail-closed evidence checks.
- `docs/DIRECTFIGHT.md`, `QUEUEPLAY_PROOF.md`, this report: design and exact
  coordinator commands.

## Validation ledger

All paths below are relative to the worktree. No real accounts or public
lobby servers were used. Games were muted, backgrounded, BelowNormal, with
isolated settings/save paths and an atomically held heavy slot. Each run
released its slot, including failures. The owner's real OpenRecomp config
hash was unchanged.

| Run | Result | Evidence |
| --- | --- | --- |
| Runtime configure/build, matching 85-patch dependencies | PASS, compiler warnings only | `build/queueplay/configure.log`, `build/queueplay/build.log` |
| Rebuild after reset hardening, shared dependencies | PASS; superseded by isolated dependencies below | `build/queueplay/rebuild-final2.log` |
| First rebuild wrapper attempt | Failed before compilation because cmd parsed a slash-separated script path; fixed | `build/queueplay/rebuild-final.log` |
| Exact runtime prepared inside worktree, no network | PASS, all 85 patches applied | `build/queueplay/prepare-runtime.log` |
| Final isolated runtime build, then incremental rebuild | PASS, compiler warnings only | `build/queueplay/build-isolated.log` |
| Launcher initial broader test run | Initial rematch regression fixed; installed Tcl initialization error remained | `build/queueplay-checks/launcher-unit.log`, `launcher-unit-retry.log` |
| Final launcher/driver/UI-channel suites | PASS, 70 tests | `build/queueplay-checks/driver-unit-final.log` |
| Review fixes: visible boot cancellation and rejected-vote retry | PASS, 74 driver tests, 48 i18n tests, 6 audit tests | `build/queueplay-checks/driver-review-final.log`, `i18n-review-final.log`, `audit-client-final.log` |
| Catalog/engine/message suites, seven languages | PASS, 48 tests | `build/queueplay-checks/i18n-unit-final.log` |
| Fake-pad/clock C++ menu plus integration tests | PASS, 6 tests | `build/queueplay-tests/overlay-unittests.log` |
| Final integration checks, including stale decided flag/loading watchdog guards | PASS, 6 tests | `build/queueplay/integration-final.log` |
| Training/Practice/shadow suites, first run | Stale shared runtime header caused one compile error; no gameplay run | `build/queueplay-tests/training-unittests.log` |
| Training/Practice/shadow suites, matching dependencies | PASS, 45 tests; 2 Tcl GUI skips | `build/queueplay-tests/training-unittests-rerun.log` |
| Proof evidence checker, initial and final | PASS, 7 tests each | `build/queueplay-proof-unit/tests.log`, `build/queueplay/proof-unit-final.log` |
| Smoke pair, 2 seconds Practice vs fresh, rollback + both replays | PASS, 1,874 result frames, 0 mismatches, same hash `359fac16a435206b`; both replays identical | `build/queueplay/smoke-rb/report.json`, `build/queueplay/smoke-rb.log` |
| Initial 180-second Practice rollback pair + both replays | PASS, 1,874 result frames, 0 mismatches, same hash `359fac16a435206b`; both replays identical with per-frame hashes | `build/queueplay/proof-rb/report.json`, `build/queueplay/proof-rb.log` |
| Heavy slot unavailable attempts | No game started; retried when a slot became available | Tool transcript (no run folder created) |

The smoke replay used the default 60-frame hash interval. The proof runner
now sets `T5_REPLAY_HASH_EVERY=1` in the process environment, as the recorder
reads that setting at process scope.

Review subsequently cleared the previous match's decided flag when starting
Practice setup and added Practice loading to the stuck-load protection. The
shared dependency tree also advanced during review, so the final build uses
an isolated checkout prepared inside this worktree from the local source
clone, with exactly this branch's 85 patches. No downloads or commits were
needed. Final runtime SHA-256:
`2f51008f10fdeffded7b38c3ecd97e0fdb28eaf00130dd3407df501beb8c5dc0`.
The local game DLL used for testing has SHA-256
`89bc5c8acb2291da33027de0d39940603efc2b1a1bc69fd80a6a7bed26956213`.

**Coordinator handoff: final-binary proof is pending.** All three heavy slots
remained occupied through repeated 50-second acquisition waits. No lockstep
pair or native challenger probe was started. The passing 180-second rollback
run predates the final reset hardening; it must not be presented as proof of
the final binary. Run the exact PowerShell wrapper in
[QUEUEPLAY_PROOF.md](QUEUEPLAY_PROOF.md): it executes 180-second rollback
with `--challenger-probe`, then 180-second lockstep, each with both replays.
Required reports are `build/queueplay/proof-rollback/report.json` and
`build/queueplay/proof-lockstep/report.json`. Both must say `ok: true`, both
peers must report zero mismatches, and all four replays must be identical.
The rollback report must also say `challenger_probe.ok: true`.

The built runtime is `build/queueplay/cmake/t5dr.exe`, with its local game
DLL alongside it. Build artifacts and runtime dependencies are ignored;
only source, tests and documentation are left as version-controlled changes.

## Remaining manual check

Use a local lobby with test guests and the newly built runtime. Search quick
and ranked while Practice is already loaded. Hold a kick as the offer
arrives, release it, then verify Cross/A accepts and Circle/B declines. Let
one offer expire for 15 seconds. Decline/expiry/cancel must retain Practice;
accept must preserve the process PID and start the agreed session. Check the
overlay-unavailable fallback in the launcher too. The fake-pad/clock suite
automates the input/deadline policy; this checks a physical controller and
the rendered panel. The native widget/layout suite also needs a working Tcl
installation; bare `tkinter.Tcl()` currently fails on this Python install.

## Proposed commit and player-facing line

Proposed commit: `feat: practice while searching with in-game challenger ready check`

Player-facing changelog line (CHANGELOG.md intentionally untouched):
“Practice while searching for quick or ranked matches, and answer the new
challenger directly in the game with your controller.”

No git commit or push was performed. Changes are left in the worktree.
