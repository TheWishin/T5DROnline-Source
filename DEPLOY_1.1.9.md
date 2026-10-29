# Deploying lobby 1.1.9 (agent S part): leaving a ranked set, set sides, leaderboard split

Central server only (Nuremberg, 46.224.146.6). The relay node is not touched. **Not rehearsed against the real
servers**; nothing here was run on them. Everything was tested on this PC against a local server (127.0.0.1).

It is **lobby server code only** and works with the launchers players have (1.1.7 / 1.1.8): no launcher change is
needed for any rule below (the new texts are translated by 1.1.9 launchers; older ones show the server's English
line). It can go out before the 1.1.9 client release, together with it, or after it.

## What changes on the server

Branch `server-119` (from main 1586bbb). Files:

- `lobby/t5lobby/server/lobby.py` -- the away rules for ranked sets (section "away from a ranked set (1.1.9)"),
  `player_dropped` / `h_logout` / `h_leave_match` / `h_result` / `_grace_expired` / `cancel_match` / `_set_*`,
  `set_end` carries `away_seconds`.
- `lobby/t5lobby/server/casual.py` -- the side coin once per ranked set (`_ranked_set_going`, `_ranked_rematch_swap`).
- `lobby/t5lobby/server/rooms.py` -- a ranked room's set is not ended when its player only lost the lobby.
- `lobby/t5lobby/server/store.py` -- `match_stats_of` (several accounts in one query), the leaderboard's four new
  fields, the history's set view gets `reason` and `by`.
- `lobby/t5lobby/server/config.py` -- `T5L_SET_AWAY_SECONDS` (default 90).
- Launcher side texts only (no effect on the server): `sets.py`, `tk_tab.py`, `i18n_*.py`.

**Database: no change.** No new table, column, index or migration (`PRAGMA user_version` stays). The new
leaderboard fields are computed from the `matches` table (indexes `matches_p1` / `matches_p2`); the history's `reason`
/ `by` come from the existing `sets.reason` / `sets.blame` columns.

**Settings: one new, optional.** `T5L_SET_AWAY_SECONDS` (default **90**). Leave it out of `/etc/t5lobby/t5lobby.env`
to get 90. Never set it short on the real server (the tests use 2-6 s through their own config only).

**Protocol** (all additions; nothing removed or renamed):

- `leaderboard` rows: + `ranked_wins`, `ranked_losses`, `casual_wins`, `casual_losses` (counted matches split as the
  profile's `stats` counts them: every game of a ranked set is a ranked match). The old fields stay.
- `notice` codes: `opponent_dropped` (now also for a closed launcher; + `left`, `set`), new `opponent_away` (the time
  left at 60 / 30 / 10 s), `opponent_back` ("X is back; the set goes on"), new `set_resumed` (to the returning
  player, with `info` = the set and `slot`). Older launchers show the `msg` in the status line (English).
- `match_result` / `match_cancel` reason `set_restart` (the next game of a set, left before its fight, played again);
  `match_result` reason `no_return`; set reason `no_return` (`set_end` `outcome_reason`, history). Older launchers show
  the code word for an unknown reason, nothing breaks.
- `set_end` + `away_seconds`; history rows' `set` + `reason`, `by` (you | opponent).

## What players see

- **Leave set** (the button) counts at once, as before: the leaver loses the set, the other player wins it and gets
  the points. The history now says it: "set won 0-1 (your opponent left the set)".
- A crash, a closed launcher or a lost connection between two games -- or in the next game before its fight began --
  no longer loses the set at once (1.1.8: closing the launcher was a forfeit, the 2026-10-28 set). The set waits
  90 s; the other player reads "Alice is reconnecting -- 90 s left" (again at 60, 30, 10 s). Back in time (the
  launcher reconnects, or the player starts it and logs in): "Alice is back; the set goes on", the next game starts
  with the same score, sides and characters, over a new connection. Not back: the leaver loses the set, the other
  player wins and gets the points ("did not come back within 90 s"). Both gone: the set does not count.
- Mid-fight nothing changes (closing the game = a quit = the set lost; a crash = void with a strike), except that a
  lost lobby connection during a set's game also gets 90 s (was `T5L_RECONNECT_GRACE`, 60 s).
- Sides: one coin per ranked set (best-of-3 sets already kept their sides; now also the game played again after a
  return, and the ranked rematches of launchers without sets). Quick: a coin per match, as before.
- The leaderboard gets ranked / casual W/L columns with the 1.1.9 launcher (agent L); older launchers ignore the fields.

## How to deploy

Same steps as [docs/DEPLOY_1.1.5.md](docs/DEPLOY_1.1.5.md) / DEPLOY_1.1.7.md, with `1.1.9` in the names:

1. **P1** build the archive from the merged commit to deploy (`lobby_119.tgz`), copy it to the central server.
2. **P2** unpack into `/opt/src/t5dr-lobby-1.1.9`, check it there (`code ok`; the database line on a copy of the
   latest backup -- no migration expected).
3. **C1** server notice 10-15 min ahead (`t5lobby-admin notice ...`).
4. **C2** `sudo t5lobby-admin drain --wait 900` (waits for running matches and ranked sets), then
   `sudo t5lobby-admin backup`, then `install.sh --self-signed --firewall none` from the new folder (restarts the
   service; the env file stays as it is -- do NOT add `T5L_SET_AWAY_SECONDS` unless the owner wants another value).
5. **C3** checks, plus:
   - `journalctl -u t5lobby --since "-5 min" --no-pager | grep -i error` -- nothing new.
   - With two launchers (1.1.7/1.1.8 are fine): a ranked set, game 1 played, close one launcher during the 6 s
     countdown; the other sees "... is reconnecting -- 90 s left"; start the closed launcher again (saved login):
     "you are back in the ranked set (1-0)", game 2 starts, same sides. Log lines: `set s... : X is away, 90 s to
     come back`, `set s...: X is back`.
   - A leaderboard request from a 1.1.9 launcher shows the ranked / casual columns; a 1.1.8 launcher's leaderboard
     looks as before.
6. After the owner has published 1.1.9: `sudo t5lobby-admin release 1.1.9`.

## Rollback

`install.sh` from the folder the server ran before (`ls /opt/src`; production runs the 1.1.7-era lobby), after a
drain. **No database step**: nothing in the database was changed by 1.1.9's code, an older server reads it as before.
Sets that ended under 1.1.9 rules keep their rows (`reason` `no_return` is just a text the old server never writes).
Matches with reason `set_restart` are ordinary void rows without blame (no strike).

## What was verified (this PC, local server only)

- `lobby/tests/test_set_away.py` (15 tests): the Leave set button, closed launcher and crash between games and back
  (now also: the next game is a new connection, not `continue`), the time-left notices, the next game left before
  its fight (closed launcher, game gone, crash report, the restart limit, connection lost and not back), not back,
  both gone, a ranked room's set, sides inside a set for launchers without sets, quick still by coin, the
  leaderboard fields. 14 of 15 fail on main 1586bbb (the quick coin test passes on both: unchanged behaviour), all
  pass on this branch.
- One bug found by the e2e run and fixed: after a return, game 2 was announced as `continue` (inside the running
  games) because both players had sent `set_next keep` before the launcher died; the returning launcher has no
  running game. `_set_dropped` now sets the set's `fresh` flag (new connection). Test: `AwayAndBackTest` asserts
  `continue` is false (old code: 2 of the 3 tests fail, new code: pass).
- `lobby/tests/test_tournaments.py`: its fake player's crash/quit in game 2 now sends `game_playing` first (leaving a
  later game before its fight is "away" since 1.1.9); the 2 tests that broke pass again.
- Every lobby test module in its own process (`lobby/tests`), all OK; `tests/test_i18n.py`,
  `tests/test_no_dead_code.py`, `tools/check_no_game_data.py` OK.
- The e2e lobby harness (`tools/e2e/run.py`, real Online tabs + stub games, the real 90 s window): `bo3_away_back`
  (launcher killed between games, started again 10 s later, the set goes on; then closed in game 2 before its fight
  and back again; set won 2-0, rated once; 31 checks) and `bo3_away_gone` (killed, not back: the other player wins
  after 90 s, notices at 90/60/30/10 s, history, the leaver's later login reads the new rating; 23 checks), plus
  the existing `bo3_2_0`, `bo3_2_1`, `bo3_quit_g1..g3`, `bo3_leave_set`, `bo3_desync_replay`, `bo3_rating_once` and
  `lobby_drop`, all PASS.
- **Not verified**: the real game (`t5dr.exe`) in an away/return set -- the e2e uses the stub game; the net suite and
  perf are unaffected (no client/game code changed); nothing was run against the real servers.
