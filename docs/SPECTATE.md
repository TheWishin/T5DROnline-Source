# Spectating live matches

A friend, or anybody in the lobby for a room's match, can watch an online match while it is
played: in their own game, a few seconds behind, exactly as it happens. It is built on the replay
format ([REPLAYS.md](REPLAYS.md)): the same data, sent while the session is played, played back by
the same netcode playback path while it grows.

## For players

- **Watch a friend**: Online tab -> Friends -> select a friend who is in a match -> **Watch**
  (below the list). **Watch a room's match**: Lobby -> Rooms -> select a room that is playing ->
  **Watch**. A private room's match (locked with a password or an invite code, or hidden: ONLINE.md
  "Rooms", 1.1.3) only its members can watch -- the players waiting for their turn: **Watch** with no room
  selected watches your own room's match; the players' friends cannot. Between a room's match and its rematch
  (1.1.4) the room keeps **Watch** while somebody already watches the players' session: you join them and see the
  rematch with them (a session nobody watched yet: Watch comes back when the rematch starts). Your game starts and shows the match; the Spectating card at the top of the tab says
  how far behind the live match it is. **Stop watching** closes the game. In the game START pauses
  (you fall further behind), SELECT ends it.
- **Watch a tournament set**: Online tab -> Tournaments -> the tournament -> click the set in the
  bracket -> **Watch** (above the bracket). Any set whose game is being played, when both its players
  allow spectators (docs/TOURNAMENTS.md; a rated tournament's sets count as ranked for "Also my ranked
  matches"). The Spectating card says TOURNAMENT.
- **The players' custom costumes** (1.1.3, docs/DIRECTFIGHT.md "Custom costumes online") are in the
  stream: your game shows both players in the customization they fight in.
- **From the start of the session.** Whenever you join, the game plays the players' session from its
  start (see "Late join" below), so a friend who joins 2 minutes into a match watches it from its
  first frame, 2 minutes behind. Joining before or right at the start: a few seconds behind.
- **Privacy** (launcher Settings -> Spectators): "Friends and room visitors may watch my online
  matches" (on by default) and "Also my ranked matches" (off by default). A match can be watched
  only if **both** players allow it (for a ranked match: both allow ranked). Switching it off during
  a match stops every spectator at once. A player who blocked you is never watched by you.
- The players see "Spectators watching your match: N" in the status line. Their games never wait
  for spectators and never notice them.
- A launcher without spectating (before 1.1.3) is never watched (it cannot say yes) and never sees
  any of it; its player's matches just have no Watch.

## How it works

```
 players' PCs                      lobby server                       spectators' PCs
 game (P1) --T5_REPLAY_LIVE file-->  launcher --spec_data (zlib)--> buffer --spec_data--> launcher --file--> game
 (writer thread, every 200 ms)       (only while somebody watches)   (from the session start)      (plays it like a
                                                                                                   replay that grows)
```

1. **The stream.** For every match the server gives a stream id (`match_start.stream`: the id of the
   session's first match; a rematch in the running games keeps it). The match driver sets
   `T5_REPLAY_LIVE=<logs/online/live>/live-<stream>.t5live` in the game's environment. The game's
   replay recorder (src/netplay/replay.cpp) then also appends the session to that file as records:
   SESSION (slot, delays, seeds, hash interval, build), INPUTS (both confirmed inputs per frame,
   XOR'd with the frame before), HASH (the compared state hash every 60 frames), BARRIER (every sync
   point with its seed and counters), MATCH (setup at FIGHT START, again with the result), LAST (the
   last frame the game ran and its wall clock), END. The frame only queues small records under the
   lock it takes for the replay anyway; the replay's writer thread appends every 200 ms (and the
   session's end writes END). Format: replay.cpp "the live stream".
2. **Upload.** Only one player's launcher sends it (P1's, P2's if P1's cannot): when the server
   asks (`spec_want`, the first spectator), the client library (lobby/t5lobby/spectate.py,
   `ClientMixin`) reads the file as it grows, compresses it into one zlib stream and sends pieces of
   at most 4 KB, at most 8 KB every half second, in order, from where the server's copy ends. It
   pauses when the last spectator leaves (`spec_stop`) and ends with the END record (`eof`).
3. **Server** (lobby/t5lobby/server/spectating.py): keeps each session's compressed stream from its
   start and sends it to every spectator from offset 0 as fast as that spectator's connection takes
   it (16 KB pieces, never more than 192 KB unsent). It checks who may watch, counts spectators and
   tells the players.
4. **Spectator.** The launcher unpacks the pieces into a file of whole records
   (`spectate.Receiver`; a stream that stops gets an END record) and starts its game at once:
   `T5_NET_MODE=replay T5_REPLAY_FILE=<that file>`. The game boots while the players' games still
   load: the SESSION record goes out at the players' handshake (`rec_session_known`, from
   `connect_locked`: the host's seed and delay, rollback when both offer it -- what frame 0 records),
   the netplay core waits for it (`T5_REPLAY_LIVE_WAIT`, 300 s), the title starts VS and the select
   screen waits for the first fight's line like a persistent game waits for its command. The
   playback sees the `T5LIVE` magic and reads the file as it grows: everything is the replay path
   (the recorder's slot, its sync points, seeds and counters, the direct fight's lines, the rollback
   or lockstep loop), plus:
   - before each frame the inputs for it (and the input delay after it) must be there; when they
     are not, the frame waits until 120 more frames came (`T5_REPLAY_LIVE_BUFFER`): a short buffer
     instead of a stutter at every piece;
   - a sync point, or the next match's fight line, that has not come yet is waited for; the select
     screen waits like a slow load (the frames are renumbered as in a replay);
   - hashes and results are compared when the recorded ones come (the playback can be ahead of the
     live game's final hash by a few frames);
   - the end of the stream (END) ends the playback at the live game's last frame; nothing new for
     300 s ends it too (`T5_REPLAY_LIVE_TIMEOUT`; between matches nothing comes while the players
     decide on the rematch);
   - a SESSION that disagrees with the one the playback started with (the players' games
     reconnected before frame 0) counts as a setup problem: the verdict is not identical.
   The verdict (`T5_REPLAY_RESULT`) is a replay's plus `live`, `stalls`, `stall_seconds`,
   `delay_avg` / `delay_max` (seconds behind the live game, from the LAST records' clock),
   `uncompared`; `T5_REPLAY_STATUS` gets the frame, the delay and the state once a second (the
   Spectating card).

### Late join: from the session's start

A spectator who joins mid-match starts at the **start of the players' session** and plays at the
game's own pace. The two other choices do not hold up:

- *From the next match*: a rematch in the running games starts from what the match before it left
  (the fight block, the C heap, effect pools...; REPLAYS.md "A rematch is played after the matches
  before it"). A spectator's fresh game equals the players' games only at the session's start (title
  visit, boot-state copy), so there is no "next match" to start from short of a full state snapshot
  (100+ MB).
- *Catch-up* (play faster until live): the game shows one picture per vblank; playback without the
  frame wait ran at 30-44 fps, slower than 59 (REPLAYS.md "No faster pace"). Faster would need frames
  without draw and flip, like the rollback loop's re-simulated ones, across loads and sync points:
  not robust enough for a release.

So the server keeps the whole session (a few KB a match) and every spectator gets all of it. The
cost: joining 2 minutes late means watching 2 minutes behind; joining at the match start, a few
seconds (the buffer and the upload's half-second steps). A session longer than the server's buffer
(`T5L_SPECTATE_BUFFER_KB`, 2 MB, hours of play) cannot be watched any more.

### Ranked default: off

"Also my ranked matches" is off by default: a ranked opponent is a stranger the queue picked, not
someone the player chose to play in front of their friends; a rated match should have nothing the
player did not choose. Both players switch it on to be watched. Casual matches, rooms and friends'
invites are watchable by default (both players chose each other or a public room). Nothing in the
stream is hidden from either player (it is what both screens show), and it comes seconds late.

### Limits and bounds

| | default | server setting |
|---|---|---|
| spectators per match | 8 | `T5L_MAX_SPECTATORS` |
| streams watched at once (server) | 50 | `T5L_MAX_STREAMS` |
| matches watched at once per internet address (IPv4, IPv6 /64) | 2 | `T5L_SPEC_PER_ADDRESS` |
| ... per IPv6 /56 (a /48: twice that) | 4 | `T5L_SPEC_PER_NET` |
| guests' share of a match's places, and of the streams below which a guest may start one | half | `T5L_SPEC_GUEST_SHARE` |
| stream slots kept for close viewers | the last 10 | `T5L_SPEC_RESERVED_STREAMS` |
| a session's stream kept (compressed) | 2048 KB | `T5L_SPECTATE_BUFFER_KB` |
| a streamer's upload | 16 KB/s, burst 256 KB | `T5L_SPECTATE_RATE_KB` |
| a stream with nothing new, its match over | ends after 90 s | `T5L_SPECTATE_IDLE` |

**Who comes first** (hardening 1.1.4; security review 3 found that about 50 guest connections from about 7
addresses took every stream slot of the server, so nobody else could watch anything). *Close viewers* -- a friend
of either player, a member of the match's room, the organizer or a player of its tournament -- come first: at a full
match a close viewer takes the place of the newest guest (else the newest other account), who gets `spec_end`
`bumped` ("A friend of the players took your place ..."); the last 10 stream slots of the server are theirs only;
the limits per address neither apply to them nor count them (there are only so many of them per match). Everybody
else watches at most 2 matches at once per internet address (IPv6: per /64, 4 per /56, 8 per /48); guests hold at
most half of a match's places and start a stream only while the server shows fewer than half of its maximum. 52
guest connections from 7 addresses now get at most 14 watches and 10 streams; a stranger with an account and a
friend still find a slot (lobby/tests/test_spectate_limits.py).

A match needs a few hundred bytes a second compressed (the measurement below); the client sends at
most 16 KB/s, the server ends a stream that sends more, a piece out of order or over 5 KB. A
spectator unpacks at most 64 MB. The spectator's game reads untrusted data: every record length,
count and index is checked (a broken record is skipped or ends the stream). The spectator's launcher
passes on only whole records its own parser took, and ends the watch on a state hash more than 3,600
frames behind the newest (the game sorts each one into place: a hand-made stream of ever older hashes
kept it busy for hours), and it makes a file only for the answer to its own `watch` (a `watching`
nobody asked for is ignored).

## Protocol (capability `spectate`, feature `spectate`)

| message | from | fields |
|---|---|---|
| `spec_prefs` | client | `allow`, `ranked` -- after every login and when changed |
| `watch` | client | `name` (a friend), `room`, or `tournament` + `set` (a tournament set's game) -> `watching` {stream, match, players, ranked, room, began, spectators[, tournament {id, name, set}]} |
| `unwatch` | client | |
| `spec_data` | streamer | `stream`, `off`, `data` (base64), `eof` |
| `spec_fail` | streamer | `stream`, `why` |
| `spec_want` | server | `stream`, `match`, `from` -> the streamer sends from there |
| `spec_stop` | server | `stream` -> the streamer pauses |
| `spec_data` | server | `stream`, `off`, `data` -> a spectator |
| `spec_end` | server | `stream`, `reason`: over, not_allowed, stopped, unavailable, too_long, your_match |
| `spectators` | server | `match`, `count` -> the players |

`match_start` has `stream` and friend entries / `friend_status` have `watch` (true: this viewer
may watch now) for clients with the cap; rooms in the lobby list have `watch` (anybody may; a private room's is
always false there, and its members get their own `watch` in the room's view, the `room` message). Between a
room's match and its rematch (1.1.4; status no longer `playing`, the room's set still running) `watch` stays true
while the session's stream is alive -- somebody started watching it and it was not ended -- and `watch {room}`
joins that stream (`watching.match` = the match that just ended; `_spec_match_started` carries every spectator
into the rematch). `spec_prefs` switched off in that pause ends the stream at once (`not_allowed`), as during a
match.
Refusals (`watch`): not_allowed (not a friend, not a room, not a member of a private room, the players do not
allow it, blocked; locking a room sends the spectators who are not its members away: `spec_end` not_allowed),
bad_state (not playing, a player of it), busy (in a match), version_mismatch (another build),
server_full (the limits). A spectator who gets a match of their own stops watching (`your_match`).

### Tournaments

A tournament's sets are public (anybody's launcher lists them, the bracket is on the status port), so
anybody whose launcher shows tournaments (cap `tournaments`) may watch a set's game being played
(`SpectateMixin._spec_tournament_may_watch` -> `TourManager.may_watch`); the rest of the rules apply (both
players allow it -- the set counts as ranked when the tournament is rated --, blocks, the limit, not a
player of it). `watch {tournament, set}` finds the set's current game (`TourManager.set_match`; between two
games: bad_state). `tour_get`'s bracket rows of sets being played have `watch` (their game can be watched
now); the bracket's revision moves when a set's game starts or ends (`TourManager.match_live`, a
`tour_changed`), so a shown Tournaments page turns its Watch button on at once. A set's next games in the
running games keep the session, so they keep the stream: a spectator sees the whole set.

### Custom costumes in the stream

The MATCH records are the replay binary's matches of this build -- format 3, with the custom costume
blocks both sides fought in (src/netplay/replay.cpp `put_match` / `get_match`). The spectator's game
writes them at its FIGHT START like a replay does (`df_costume.cpp`, `CostumeMode::Replay`), checked again;
a playback whose written blocks differ from the recorded ones counts a setup problem (`play_fight`), so
"identical" includes the costumes. The launcher's parser (`spectate.parse_match`) reads them too.

### When the match moves onto the relay

A game that hears nothing on the direct path moves its match onto the relay (docs/NETPLAY.md "When
Windows Firewall blocks the game"): both games start the session again, for the same match -- the same
stream id, so the same live file. A session that ends before its handshake writes nothing but the magic
(no LAST, no END; `live_append`), so the new session's file (`CREATE_ALWAYS`, the magic again) continues
the stream byte for byte where the uploader stands, and a spectator already watching gets the new
session (its game was waiting for the first SESSION record anyway). The server keeps the stream while the
match is on its way to the relay (`_spec_tick`: `fallback` and state `relay` count as being played).
A stream that never gets a session is ended by the server as before.

## Tools and tests

- `tools/spectate_test.py --live <file the host's game writes> --out DIR --late 60`: spectator games on
  copies of a growing live file, fed in pieces like the launcher does; exit 0 = every spectator
  identical to the live game.
- `tools/e2e/run.py --only spectate_live --exe ...`: the whole path through the launcher's Online tab,
  a local lobby server and real games (a room match and its rematch, a friend watching from the start,
  a guest 60 s late, a baseline pair without spectators at the same time).
- `lobby/tests/test_spectate.py`: who may watch, privacy, ranked, rooms, the limit, bounds, older
  launchers, the stream byte for byte through the server, the parser, uploader and receiver; the relay
  fallback keeping the stream; costume blocks in MATCH records.
- `lobby/tests/test_tournaments.py` `SpectateSetTest`, `lobby/tests/test_tk_tour.py` `TkTourWatchTest`: a
  tournament set watched (the bracket's `watch`, the Tournaments page's Watch, the refusals).
- `tests/test_replays.py`: the live stream's costume blocks played back, a restarted session's stream.
- `tools/e2e/run.py --only int_tour_watch,int_tour_watch_ls,int_fw_costumes`: a tournament set with both
  players in custom costumes watched from the bracket (rollback, lockstep); a match moving onto the relay
  with costumes and a spectator who watched before the move.

## Proof (2026-10-20, branch spectate on main 06adda9)

The PC ran 15-20 games of other test runs at 100 % CPU the whole time (the players' games ran at
35-50 fps): absolute frame times are that PC's, the comparisons are what counts.

**The whole path** (`tools/e2e/run.py --only spectate_live`, run fin_live: a local lobby server, four
launchers' Online tabs, real games in persistent mode, rollback). Ava's room, Bo joins: a match and a
rematch in the running games (stages 34 and 25, in-game picks). Vi, Ava's friend, presses Watch on the
Friends page as the match starts; Wu, a guest, presses Watch on Ava's room 60 s later.

| spectator | joined | hashes compared | different | results | final hashes | behind the live game |
|---|---|---|---|---|---|---|
| Vi (friend) | at the start | 90 | 0 | 2 of 2 the same | a1ed461a284718ef, ae870d51b572510e | 3.3 s on average, 5.3 s at most |
| Wu (room) | 60 s later | 90 | 0 | 2 of 2 the same | a1ed461a284718ef, ae870d51b572510e | 63 s (the session from its start) |

Both played every frame the live session played (5,377), 0 different hashes, 0 setup problems; the
stream ended "over" when Ava left the set. The session was 81 KB as records, 13 KB compressed through the
server (about 6:1; ~150 bytes a second of play). An earlier run (e2eD) the same: 88 hashes, 0
different, Vi 4.5 s behind.

**The players are not affected.** The same two players and the same scripted fights, one run at a time,
alternating: without spectators and without any live stream (launchers without the cap), and watched by
two spectators whose launchers receive the stream (their games would be on other PCs):

| run | spectators | frame times while fighting p50 / p95 / p99 (ms), Ava -- Bo | fps match 1 -- rematch | recording on the frame, avg / max (us) |
|---|---|---|---|---|
| base 1 | none, no stream | 26.0/36.5/50.5 -- 25.5/36.5/51.5 | 40.9 -- 38.5 | 2.15 / 2341, 1.22 / 970 |
| stream 1 | 2 | 28.5/39.5/52.5 -- 28.5/39.0/55.0 | 41.2 -- 34.1 | 1.29 / 1133, 0.93 / 433 |
| base 2 | none, no stream | 31.0/38.0/51.0 -- 30.5/39.0/55.0 | 36.4 -- 33.5 | 0.97 / 614, 0.68 / 74 |
| stream 2 | 2 | 18.0/35.0/49.5 -- 17.5/37.0/69.0 | 44.1 -- 46.7 | 0.91 / 117, 0.96 / 941 |
| live (fin_live) | 2, their games on this PC too | 17.0/34.0/49.5 -- 17.0/34.0/50.0 | 47.7 -- 49.4 | 0.88 / 33, 0.97 / 154 |

Every match: 0 mismatching frames, the same winner and final hash on both PCs. The spread between runs
(p50 17-31 ms) is the other games' load; runs with and without spectators overlap. What recording costs
the frame stays about 1 us with or without the live stream (the frame queues a few small records; the
writer thread appends the file); the spikes of a millisecond or two are there without any stream too
(a full CPU preempting the main thread). In both stream runs the files both receivers got were the
players' live stream byte for byte (75,582 and 96,398 bytes, plus the END record the launcher adds).

**Lockstep** (game level, `tools/spectate_test.py` beside `tools/fight_flow_test.py --flow rematch
--env T5_RB_MODE=off`, run fin_ls: process mode, 2 matches on stages 27 and 31): spectator 1 started with
the stream (its game booted before the session was known), spectator 2 60 s later -- both identical, 70
hashes, 20 of 20 sync points, both results the same.

**After merging main d222992** (the review's replay header checks, which now guard the live SESSION and
MATCH records too; 0053; no pause online), with at most 2 games at a time: a rollback pair (persistent, a
rematch, stage 27) wrote its live stream, then two spectators played it fed at about the live rate, the
second 30 s later (run s6a): both identical, 72 hashes, 3 of 3 sync points, both results the same.

Tests: `lobby/tests/test_spectate.py` (13), `tests/test_replays.py`
`test_live_stream_plays_like_the_file` (the game's writer and reader against Python's parser).
