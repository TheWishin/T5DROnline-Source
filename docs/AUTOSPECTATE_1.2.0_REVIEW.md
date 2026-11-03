# 1.2.0 idle watching and playback exit review

This is a source review and a maintainer validation checklist. Game-free integration checks are
reported separately in the integration report; no build or game validation is established here.
Earlier proof runs described in SPECTATE.md and REPLAYS.md belong to earlier builds and do not
validate these edits.

## Auto-watch contract

The persisted `auto_spectate` setting defaults to false. Existing spectate capability negotiation,
advertised `watch` flags and ordinary `watch`/`unwatch` messages are reused. There is no new server
message or replay format. A server without spectating has no eligible automatic targets, and old
clients keep their existing manual behavior.

The policy waits 15 seconds of continuous idle state, only in the lobby or waiting in a room.
Own room comes first, then watchable friends, then public watchable rooms. Rank/rating sorting uses
only the data the lobby already advertises; a room's strongest known member or owner is an estimate
of its appeal, not a claim about the fighting pair. Stable tie breaks avoid random process churn.
Attempts are at least 30 seconds apart; the same target has a 120-second cooldown so a refusal can
lead to another target. Stopping or preempting a watch pauses automatic attempts for 120 seconds.

The server's existing refusal path remains authoritative for privacy on both players, ranked
privacy, blocks, private-room membership, compatible builds, spectator places, guests' share,
address/network limits and stream limits. Client hints never grant permission. A friend or room
member retains the existing close-viewer priority, with no new priority for automatic watching.

An existing running game, including a prewarmed idle online game, prevents an automatic boot.
The policy also excludes queueing, challenges, ready checks and an owned match. The spectator's
process is separately tracked; a delayed Watch answer must not replace or stop the match driver's
process. Event preemption must happen before that driver handles the same match event.

## Source trace: exits and the white-screen suspect

| Phase | Old source path and risk | Required behavior after the change |
|---|---|---|
| Boot/title, before first fight | Replay frame controls were behind `g_active`; a SELECT before activation was not consumed by the replay control path. | Poll the viewer outside the active-lockstep gate; close the playback process on SELECT. |
| Initial character select / loading | Lockstep can still be inactive while direct-fight playback waits for its first line. SELECT was ignored by the replay controls; the inactive pad hook supplies neutral input, so a guest mode transition is not established. This is the primary source-supported phase in which a waiting/white picture could remain after SELECT. | Consume viewer exit as playback exit, never as a transition into an ordinary game with replay state still installed. |
| Fight, recorded replay | `replay_frame_wait` consumes SELECT, finishes the verdict and normally exits. `T5_REPLAY_EXIT=0` previously allowed execution to continue after finish. | Explicit SELECT always closes; the diagnostic keep-open setting must not trap the viewer. |
| Fight, live buffer | The main live buffer had a quit callback, but fallback input and barrier waits supplied none and could wait for the 300-second default timeout. | Use the registered quit callback in every live wait. |
| Viewer pause | The pause loop polls every 15 ms for SELECT. | Preserve pause controls and close on SELECT; do not send viewer controls into recorded input. |
| Character select / between matches | The driver polled the next fight, but END or inactivity could arrive while the playback frame stayed fixed. Frame-based finish checks could then fail to close the process. | Poll stream completion and timeout while waiting for the next line, draining any already buffered next fight first. |
| Stream naturally ends | The launcher appends a whole END record. A fight already buffered should finish; an idle wait with no next fight must finish too. | Produce a finished playback state and close normally, without waiting for another frame or match. |
| Privacy revoked / own match / challenge / ready check | Network and UI callbacks can race a pending boot or active spectator process. | Cancel the pending watch, close only its owned process and release the server slot; the player's own match wins. |
| Game window closes | The runtime's vblank ticker pumps window messages and calls `on_window_closed`, independently of a blocked guest replay wait. Replay mode is local, so it exits with code 0. | Log the last cached boundary snapshot and exit directly; do not traverse main-thread mutable replay state from the ticker. The OS closes file handles. The launcher observes process death and unwatches even if no complete verdict exists. |

The exact visible white picture has not been reproduced. The first-select/loading gate and idle
END path are source defects, but the rendering symptom and whether the OS window closes under
every runtime condition require the real build. No memory address was added or guessed.

## Leaving time and process ownership

The Online tab requests a poll every 100 ms. Receipt of a match, challenge or ready event therefore
causes local cancellation on a nominal next poll, before match-driver handling. Busy UI scheduling
can delay that poll. Local manual Stop acts in its UI callback. Neither waits for a lobby reply
before protecting the player's own match.

Playback stop now kills its captured process and calls `wait(timeout=0.25)`. If exit is not
observed, the process handle and running-game guard remain in place. The normal online game's
stop path is unchanged. An own-match launch waits up to 5 seconds for the previous process to be
observed dead and refuses to reuse a still-running spectator. The 250 ms limit bounds the explicit
wait, not process-call overhead,
scheduler delays or the next game boot, so it is not a strict wall-clock guarantee. Normal replay
wait loops poll at 10 ms (live waits) or 15 ms
(pause); active main-frame boundaries are nominally about 17 ms. Loader/geometry drains and
keyread takeover also poll SELECT. Add scheduling and verdict/file work to those intervals.
These intervals are not runtime latency results.
Measure event receipt to spectator process death and to own-match boot on the target build.
An ordinary stream END drains recorded playback still in the local buffer, potentially the rest
of a long late-joined session; its time to close is not bounded by these cancellation intervals.
SELECT, privacy revocation and the player's own match do not wait for that backlog.

## Real-build checks and logging

Exercise SELECT, game-window close and natural END separately in every applicable matrix row,
for recorded replays and growing live streams, rollback and lockstep. Include no SESSION yet,
SESSION but no MATCH, fight loading, stalled inputs, a stalled barrier, paused playback, a rematch
decision gap, and END before a first fight. Include an END that has a complete next fight buffered,
so the cleanup cannot truncate valid playback.

If the white picture remains, capture the following in the maintainer's real environment, without
adding player logs or screenshots to this mirror:

- The new `replay exit:` and `replay window close: last boundary` phase lines: reason (exit),
  playback frame, active/idle/paused flags, current and next direct-fight mode, and whether the
  file is live. Window close reports a cached snapshot, which can predate the close event.
- The exit reason and phase at SELECT/window-close/END, wall-clock timestamp, local pad sample,
  `g_active`, `g_idle`, playback frame and main-thread/frame-semaphore hook reached.
- The awaited item (SESSION, INPUTS, BARRIER or next MATCH), live end/bad/timeout state, newest
  record kind, buffered input count and next requested match index.
- Entry and return of playback finish, verdict write and process exit; for window close, whether
  the runtime's main loop received the close request and guest workers left their waits.
- Launcher event receipt, watch generation/pending state, stream id, spectator PID, driver PID,
  stop request, process death and any late Watch callback. Check that a stale callback cannot
  launch a new spectator after a challenge or match event.

Auto-watch needs real server checks for privacy revocation, private/hidden rooms, guests' quota,
per-address/network quota, reserved stream slots and a refusal followed by fallback. Also check
match/ready/challenge arrivals at each point of Watch request, answer, boot and playback, plus
manual Stop, setting disabled, disconnect and launcher close. Old servers and clients need a
compatibility smoke test, with automatic watching disabled on servers without the capability.

The changes must leave both players' simulation identical. A real pair test is required with
**0 mismatching frames**, both with and without spectators, and replay hashes/results must still
match the recorded live session. A build and game run are required to prove renderer/window
cleanup and actual leave/boot times; source contracts and mocked tests cannot prove them.

## Regression inventory

The branch adds the following regression tests. See the integration report for checks executed
on this working copy; native fixtures still need a permitted build:

| File | Coverage |
|---|---|
| `lobby/tests/test_auto_spectate.py` | Idle eligibility, off default, target order and cooldowns. |
| `tests/test_auto_spectate_setting.py` | Persisted opt-in, malformed saved values, UI wiring and bounded playback-stop behavior. |
| `tests/test_auto_spectate_catalogs.py` | New setting text in every language catalog. |
| `lobby/tests/test_spectate_cancel.py` | Pending-watch cancellation and stale answers. |
| `lobby/tests/test_spectate_lifecycle.py` | Owned-process cleanup, preemption, callback races and automatic lifecycle. |
| `lobby/tests/test_spectate_dispatch.py` | Spectator cancellation before match-driver dispatch and tab teardown. |
| `lobby/tests/test_auto_spectate_limits.py` | Existing server privacy and spectator limits through ordinary Watch requests. |
| `tests/test_replay_exit_contract.py` | Replay control/exit source contracts across active and inactive phases. |
| `tests/test_replay_stream_exit.py` | Shared live quit callback, idle END/timeout polling and file-handle cleanup source contracts. |
| `tests/test_replays.py` with `tests/c/replay_test.cpp` | Four behavioral tests, five synthetic scenarios: END before the first fight, no-END waiting, buffered fight/input preservation followed by END, registered input-wait cancellation and registered sync-point-wait cancellation. The fixture requires compilation to execute. |

Existing `lobby/tests/test_spectate.py`, `lobby/tests/test_spectate_limits.py`,
`lobby/tests/test_driver_persistent.py`, `tests/test_replays.py`, `tests/test_i18n.py` and
the replay C++ tests remain relevant. Some existing tests compile or start a local lobby server;
they must be selected according to the permitted validation scope.
