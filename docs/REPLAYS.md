# Replays

Every online match is saved as a small file, and the launcher's **Replays** tab plays it back in
the game, exactly as it was played: both players' inputs frame by frame, the same random seeds,
the same netcode, checked against the live match while it plays. Code: `src/netplay/replay.cpp`
(record and play), `src/netplay/t5_hooks.cpp` (sync points, the playback's pace),
`src/netplay/netplay_core.cpp` (the inputs, the replay as a peer), `src/directfight/df_fight.cpp`
(each match's setup), `launcher/replays.py` + `launcher/replays_ui.py` (the list, Watch),
`tools/replay_play.py` (play files back and check them).

## What is recorded

One file per netplay session -- one opponent: the first match and every rematch after it (a
persistent game starts a new session for every new opponent). It is written into
`native\replays` (`T5_REPLAY_DIR`, set by the launcher while **Save online matches as replays** is
on, the default) and holds:

- the session: this PC's side (P1/P2), the build id (`T5_NET_BUILD`), the netcode the session ran
  (rollback or lockstep) and its input delays, the session seed (`T5_NET_SEED`) and the match seed
  the random generators were seeded with at lockstep frame 0, the date;
- each match's setup at FIGHT START: both fighters, their confirm buttons (the costumes), the model
  ids the game fights with, stage, rounds to win, whether it was picked on the in-game select screen,
  and -- unless **Keep the players' names in replays** is off (`T5_REPLAY_NAMES=0`) -- the two
  names under the health bars; since format 3 (1.1.3) also the custom costume blocks both
  fighters wore (docs/DIRECTFIGHT.md "Custom costumes online": the 0x108 bytes the driver wrote
  for each side at FIGHT START), which the playback writes again -- checked the same way as live --
  so a replay shows both players' customizations; a format 2 file plays with the default costumes,
  as its match had them;
- each match's result: winner, score, the state hash of the deciding frame (the one the result
  file has, equal on both PCs), how many frames mismatched live;
- every sync point of the session (docs/NETPLAY.md): its kind (the next match's start, the end of a
  fight's loading, a lockstep scene change, the in-game select's pause and resume), the frame this
  game reached it at and the frame both games went on from, the seed the random generators got
  there (Mersenne Twister, C `rand()`, the TLS generator with its per-call-site streams of
  `rb_rand.cpp`, the scene LCG -- all from that one value, `reseed()`) and the game's frame
  counters after it;
- both players' confirmed inputs for every frame of the session (buttons and the four axes), and
  the state hash the peers compare (`kDefaultHash` / `kGame`: lockstep's per-frame hash, rollback's
  final hash) of every 60th frame (`T5_REPLAY_HASH_EVERY`).

The inputs are taken from netplay's input rings once both are final (this PC's decided -- they never
change -- and the peer's arrived in order), so they are exactly what the game ran with, the
rollback loop's corrections included. Nothing of the recording writes guest memory or changes what
the game does.

### The file

```
T5REPLAY 1                       first line
{"format": 1, "build": ..., ...}  one line of JSON: what the Replays tab lists
<zlib stream>                     the binary below (Python's zlib reads it)
```

The binary (little-endian): `T5RP`, version 3, flags (rollback), side, delay, rollback delay,
session seed, match seed, frames, hash interval, the last frame the recording game ran (its inputs
reach the input delay further: decided ahead, never run -- the playback ends at the last frame; a
format-1 file from development has no such field and plays to frames minus the delay); the matches
(setup, result, names; format 3: a flag and the two costume blocks); the sync
points; the hashes (frame, 64-bit hash); then the inputs as 12 columns (P1 buttons low, high, lx,
ly, rx, ry, then P2) of one byte per frame, each XORed with the frame before, so a held input is a
run of zeros. The JSON line is a view of the binary; the game reads only the binary.
`launcher/replays.py` reads both (`read_header`, `read_payload`).

Size: 2.5-5.5 KB for a match of 1-2 minutes with both players mashing buttons and motion inputs
the whole time (the tests' worst case; see Tested), a few hundred bytes of it the hashes.

## Watching

**Replays** tab: one row per match (date, the two fighters with this player's first, the result
from this player's side, the opponent, rollback or lockstep, rematch). **WATCH** starts the game in
playback mode:

```
T5_NET_MODE=replay  T5_REPLAY_FILE=<file>  T5_REPLAY_MATCH=<k>  T5_REPLAY_RESULT=<verdict.json>
```

The local pad (keyboard or controller, not a player in a replay) steers it:

| Button | Keyboard | What it does |
|---|---|---|
| START | Enter | pause; again: go on |
| SELECT | Tab | end the replay (the game closes) |

The game closes by itself a few seconds after the watched match's KO, and the tab shows the verdict
("identical to the live match (N checks, same result)", or the frame from which it went another way).
`T5_REPLAY_CONTROLS=0` takes the pad away from the playback (tests), `T5_REPLAY_EXIT=0` keeps the
game open after the end.

**No faster pace.** Double speed, and the earlier matches of a session as fast as possible, were
built and measured: the frame did not wait for its vblank tick, but the game still shows one picture
per vblank (the flip waits for it), and such a playback ran at 30-44 frames a second -- slower than
normal (59). Faster would need frames that skip the draw and the flip, like the rollback loop's
re-simulated frames; not done. A playback runs at the game's own pace.

**A rematch is played after the matches before it.** The game state at a rematch's start is what the
match before it left (leftovers in the fight block, the C heap, effect pools...): both live PCs share
that history, a freshly started game does not -- a persistent game that has played and a fresh one
differ in 1,662 of 1,662 frames' hashes without the boot-state copy (docs/DIRECTFIGHT.md "A game that
has played meets a fresh one"). The netplay guarantee is "a fresh game equals a persistent game at a
new session's start" (title visit, boot-state copy). So a replay always starts at its session's
start, and watching match k plays matches 1..k-1 first (the viewer sees them; SELECT ends it).

## How the playback works

The playback is netplay's local mode (no socket, no devices) with the file as a perfect peer
(`netplay_core.cpp`, `s.replay`): every input of every frame is known, so nothing is predicted and
the rollback loop never rolls back. Everything else is the live code path:

- **The same netcode.** A rollback session plays back through the rollback loop (its sync point
  rules, the barrier after the boundary's hash, the final hashes), a lockstep session through the
  lockstep (ring resets are sync points there). The file decides (`rb_net.cpp offered_by_env`),
  whatever `T5_RB_MODE` says. The same side: the recorder's slot, so the direct-fight driver's
  "my player's record" checks (select screen live, the pause request) fire at the same frames.
- **The same fights.** Direct fight (process mode) takes each match's line from the file
  (`p1,p2,stage,rounds buttons=b1|b2 [pick=N] [names=]`): the first at the title, the next ones at
  the select screen after each match, like `T5_FIGHT_FILE` lines. A picked match is driven like a
  lobby-picked one (the recorded buttons); `pick=` stays on the line so the lockstep pauses for the
  next select screen where the live one paused. FIGHT START compares the model ids and the stage
  with the recording.
- **The same frame 0.** The session's start is `t5_netplay_start()` at FIGHT START of match 1, as
  live: equal counters, input ring cleared, the generators seeded with the recorded match seed; the
  TLS generator pinned to the recorded session seed while the select mode runs (Mokujin's pick).
- **The same sync points, with the recorded seeds and counters.** The k-th `scene_barrier()` of the
  playback is the k-th recorded sync point. The frame the playback continues at follows the
  recording: arriving earlier than the recording's continuation, it jumps there (as the earlier PC
  of a live pair does); arriving later -- a fresh game loads a fight more slowly than a persistent
  one that has played, so this is the usual case at the end of the first loading -- it keeps its own
  frame number and the recorded frames are looked up that many frames on. Either way the game's
  frame counters (0x106D4D88, 0x1008EB9C, 0x1008F07C, 0x1009442C) are set to the recorded values
  and the generators get the recorded seed: what the game state is after a sync point does not
  depend on how long this PC took to get there. The kind of each sync point is checked.
- **Every recorded hash compared.** At each frame whose recorded hash exists, the playback's hash of
  the same frame (lockstep: the per-frame hash; rollback: the final hash) must be equal; each match's
  result (winner, score, the deciding frame's hash) must be equal. `T5_REPLAY_RESULT` gets the
  verdict:

```json
{"file": "T5R-....t5replay", "watched": 2, "matches_total": 2, "end": "the watched match is over",
 "frames": 4093, "hashes_compared": 69, "hash_mismatches": 0, "first_mismatch": null,
 "sync_points": 3, "sync_points_recorded": 3, "sync_point_problems": 0, "setup_problems": 0,
 "identical": true, "matches": [{"n": 1, "winner": 0, "score": [1, 0], "hash": "a127dd4580ccb38c",
 "recorded_winner": 0, "recorded_hash": "a127dd4580ccb38c", "same": true, ...}]}
```

## Privacy

What a replay never holds: IP addresses, ports, the match key, the lobby's match id, account data.
Player names only as the HUD shows them, and only while **Keep the players' names in replays** is on.
**Report a problem** adds the newest replay (`replay/` in the zip) with every name taken out
(`replays.strip_names`: the JSON's names become `<player>`, the binary's are emptied; the copy still
plays back), the same rule as for the logs.

## Cost

Recording reads netplay's rings and the hashes it computes anyway. The inputs go into 4096-frame
chunks that never move: the main thread appends and publishes the frame count, one writer thread
(below-normal priority) reads below that count without a lock; the rest (matches, sync points,
hashes) is small and taken under a mutex. A write is a request to that thread (an event) at each
match's end and again once its after-match frames are in; it compresses and writes the file in 2-8 ms.
Only a session's end writes on the calling thread (the process may end right after). The main
thread's time inside the recording is logged once a minute and at a session's end:

```
replay: recording cost the frame 0.57 us on average, 74.5 us at most, over 3600 frames
```

(final runs pX: 0.57-0.70 us on average, 8.6-172 us at most per frame, the most being a chunk
allocation or the thread being preempted on a PC running 8 games. A first version copied the
session and started a thread at each match's end on the main thread: up to 39 ms once, under load;
that is why it is the writer thread now.) Sync: every match below ran with recording on, with 0
mismatching frames live.

## Tested

Two games on this PC (`tools/fight_flow_test.py`, `tools/pick_flow_test.py`: host and joiner, both
recording into their own folder, muted, minimized, below-normal priority, both players mashing with
motion inputs), then every file played back by `tools/replay_play.py` (the whole session) and compared: every recorded hash (one per 60 frames), every
sync point, each match's FIGHT START setup and result.

| run | netcode | flow | matches (stage) | files |
|---|---|---|---|---|
| t1 | rollback | process mode, a rematch through `T5_FIGHT_FILE` | Jin vs Lili x2 (20) | 2 |
| pR | rollback | persistent, N R R N R N, 2 rounds | Jin vs Lili (27, 20, 33, 25, 31), Steve vs Hwoarang (27) | 6 |
| pL | lockstep | persistent, N R N R, 2 rounds, rematches change fighters through the select screen in lockstep | Marduk vs King (24), Devil Jin vs Mokujin (29), Asuka vs Law (17), Steve vs Hwoarang (27) | 4 |
| pP | rollback | in-game select (picks, the pause at the select screen and the resume), 2 sessions of 2 | Jin vs Lili (22), Kazuya vs Xiaoyu (30), Steve vs Steve mirror (18), Bryan vs Law (27) | 4 |
| pV | rollback | process mode, 3 matches | Asuka vs Law (27), Dragunov vs Lili (34), Kazuya vs Heihachi (29) | 2 |
| pW | lockstep | persistent, N R | Steve vs Hwoarang (27, 30) | 2 |
| pX | rollback | persistent, N R N | Kuma vs Panda (26, 27, 21) | 4 |
| pY | rollback | persistent, N R, 2 rounds | Raven vs Feng (27), Baek vs Armor King (32) | 2 |
| pZ | lockstep | process mode, 2 rounds | Yoshimitsu vs Nina (19), Lee vs Julia (27) | 2 |
| pQ | lockstep | process mode | Wang vs Ganryu (27), Roger Jr. vs Anna (23) | 2 |

Live: 30 matches, every one confirmed by both games with 0 mismatching frames. Recorded: 30 files
(host and joiner each), 4.4-4.7 KB per minute of play with both players mashing (5 KB for a match of
two rounds; 2.8-7 KB per match). Played back with the final build (before the merge with 1.1.2's
main; run final4): **30 of 30 files identical to the live match** -- 3,509 recorded hashes compared, 0
different; 370 sync points, all where the recording had them; 60 of 60 match results the same winner,
score and deciding frame's hash (20 of them on stage 27), as `tools/replay_play.py` prints them:

```
| replay | match | mode | stage | fighters | winner live / replay | final hash live | final hash replay | same |
| T5R-20261019-162607-9ec6.t5replay | 1 | rollback | 27 | Jin vs Lili | 0 / 0 | 073882e52780ad87 | 073882e52780ad87 | True |
| T5R-20261019-162607-9ec6.t5replay | 2 | rollback | 20 | Jin vs Lili | 1 / 1 | f2bc0384c44e2982 | f2bc0384c44e2982 | True |
| T5R-20261019-165122-3dda.t5replay | 2 | lockstep | 29 | Devil Jin vs Mokujin | 1 / 1 | 85b04dc0325081cd | 85b04dc0325081cd | True |
| T5R-20261019-170041-d7bf.t5replay | 2 | lockstep | 27 | Steve vs Hwoarang | 1 / 1 | a5f5ea0a72dca487 | a5f5ea0a72dca487 | True |
| T5R-20261019-170630-a17b.t5replay | 1 | rollback | 18 | Steve vs Steve | 0 / 0 | 800be2bf95d213cb | 800be2bf95d213cb | True |
| T5R-20261019-170630-a17b.t5replay | 2 | rollback | 27 | Bryan vs Law | 1 / 1 | b254c0c1b2640f91 | b254c0c1b2640f91 | True |
... (60 rows)
30 of 30 replays identical to the live match (every recorded hash and result)
```

After the merge with main 7486b0c (1.1.2: series up to 0048) the same check on the merged build,
runs pM1-pM3: rollback persistent with a rematch (Steve vs Hwoarang, 25 and 27), lockstep process mode
(Lili vs Kazuya 31, Jin vs Dragunov 27), in-game picks with the pause and resume (Devil Jin vs Mokujin
20, Asuka vs Xiaoyu 27): 6 matches live with 0 mismatching frames, **6 of 6 files identical** (12 of
12 results, 416 hashes).

Also checked: the viewer's pause (`replay_play.py --press 10:START,15:START`, the second match of t1
watched): "paused at frame 2746", "going on (paused 5.0 s)" in the log, the verdict still identical.
(These runs were made while the playback still had double speed and a fast-forward for the earlier
matches; both were taken out afterwards -- see "No faster pace" -- and the merged build's runs pM1-pM3
played at normal speed.) A file whose names were taken out for a
report plays the same (tests). Bugs the proof runs found and fixed (none of them in the game's
determinism -- the hashes were equal every time): a lockstep playback held a match's result for
netplay's 3-second fallback and lost it when the recording ended sooner; a playback that ran to the
last recorded input -- the inputs are decided the input delay ahead -- went past the last frame the
live game ran and met a sync point the recording could not have (pW, host's file: the file now holds
that last frame, format 2); a lockstep game that wrote its file at the very frame of a result had
not counted that frame yet (pZ, joiner's file: counted before the match watch now, and a playback
never stops before a recorded match's end).

## Limits

- A replay plays back only on the game build that recorded it (the build id is in the file; the tab
  warns when it differs). The same lift, the same patches: the hashes say whether it still matches.
- Offline VS is not recorded (the offline game is not deterministic from a known state: no netplay
  sync points, menus with their own history).
- Only direct-fight sessions (the launcher's way) are replays; netplay from boot through the menus
  (`T5_NET_START=boot`) is not recorded (no match setup to play it from).
- The hash is compared every 60 frames (a difference shows up to 59 frames late; the result's hash
  is compared exactly).
- The playback shows the game's "Unknown" in the HUD when names were not kept.

## Files and variables

| | |
|---|---|
| `T5_REPLAY_DIR` | record online sessions into this folder (the launcher: `native\replays`) |
| `T5_REPLAY_NAMES=0` | leave the players' names out |
| `T5_REPLAY_HASH_EVERY` | hash interval in frames (default 60) |
| `T5_NET_MODE=replay` + `T5_REPLAY_FILE` | play a file back |
| `T5_REPLAY_MATCH=k` | watch match k (0 / unset: the whole session, every match checked) |
| `T5_REPLAY_RESULT` | the verdict (JSON) |
| `T5_REPLAY_CONTROLS`, `T5_REPLAY_EXIT`, `T5_REPLAY_TAIL` | pad control, close at the end, frames shown after the KO (360) |
| `tools/replay_play.py` | play files or folders back, print the table, exit 0 when all are identical; `--press` tests the controls |
| `launcher/replays.py` | read, list, prune (the newest 200 files are kept), strip names |
| `tests/test_replays.py`, `tests/c/replay_test.cpp` | format, both readers and writers against each other, the frame renumbering, the tab, the report |
