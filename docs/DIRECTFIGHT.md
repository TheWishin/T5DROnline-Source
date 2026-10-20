# Direct fight: boot straight into a VS match

The players pick their fighters on the game's own select screen (or the lobby
picks them), the game goes straight to the fight, and it stays open between
matches (like Tekken 6 Native Online). `src/directfight/` is the
in-game half of that: it drives the game's own mode machine and character
select from the frame boundary hook, applies the fight settings where the game
reads them, calls the netplay hook at fight start, reports the result and waits
at character select for the next fight -- in the same game process for a
rematch (`T5_FIGHT_FILE`) and, in a persistent game (`T5_CTL_DIR`, below), for
every new opponent too. No ps3recomp change (patch series unchanged);
everything is off unless `T5_FIGHT`, `T5_FIGHT_FILE`, `T5_CTL_DIR` or a
`T5_DF_*` variable is set.

All guest addresses are for NPUB30009 v01.00.

## Interface

```
T5_FIGHT=p1,p2,stage[,rounds][,p1color,p2color][ match=<id>][ names=<n1>|<n2>][ ranks=<r1>|<r2>][ pick=<s>]   the first match
T5_FIGHT_FILE=<path>                                 the next matches, one line in the same format
T5_NET_RESULT_FILE=<path>                            {"match": id, "winner": 0|1|null, "score": [p1, p2], ...} per match
T5_DF_STATUS_FILE=<path>                             JSON status for the launcher (rewritten on change)
T5_HUD_NAMES=<P1 name>|<P2 name>                     names under the health bars (lobby names, 16 characters)
T5_HUD_RANKS=<P1 tier>,<P2 tier>                     rank badges, 0-36 in the game's order (0 Beginner, 10 1st Dan, ...)
T5_CTL_DIR=<dir>                                     persistent game: every match is a control command (below)
T5_DF_PICK=<seconds>                                 pick=<seconds> for fight lines without one (tests)
```

- `p1`, `p2`: character id 0-35, 3-letter code or name prefix (table below).
- `stage`: stage id (table below), or `random` / `-1`. Without netplay that is
  the game's own pick. **With netplay it is never the game's pick**: the stage
  panel picks on each PC on its own (QA run fd_random: two different stages,
  desync from frame 0), so `random` becomes a stage derived from the shared
  seed (`T5_NET_SEED`, else the session's) and the match number -- the same on
  both PCs. The lobby always sends a concrete stage anyway (resolved from the
  match seed on the server).
- `rounds`: rounds to win, 1-5 (default `T5_NET_ROUNDS`, else 3). Written to the
  game's rounds-to-win byte at game-mode entry; the HUD shows that many round
  marks.
- `match=<id>` (key=value, anywhere on the line; older builds ignore it): the
  lobby's match id. Netplay puts it into this match's result file, so the
  launcher never takes a result of one match (say, one the lobby voided) for
  the next. The launcher appends it to every line it writes to `T5_FIGHT_FILE`;
  the first match's id is `T5_NET_MATCH`.
- `p1color`, `p2color`: 1 or 2. Kept for old lines; it changes nothing: the
  second confirm it picks the button of is the handicap bar (see "Character
  select in the game"). The costume is the button that confirms the character.
- `pick=<seconds>` (key=value): the in-game select -- both players pick
  character and costume on the select screen within that many seconds; `p1`,
  `p2` are what a player gets who does not pick in time (the launcher's
  character). See "Character select in the game".
- `T5_FIGHT_FILE` is read when the game idles at character select (after a
  match, or from boot when `T5_FIGHT` is not set) and renamed to `<path>.done`
  once consumed. Write it atomically (write to a temp file, rename).
- Status file: `{"state": ..., "frame": N, "match": k, "p1", "p2", "stage",
  "rounds", "last_winner", "last_score", "pick", "b1", "b2", "m1", "m2"}` with
  state one of `title`, `pick`, `pick_wait`, `select`,
  `stage`, `loading`, `fight`, `over`, `neutral` (and in a persistent game
  `reset`: back to the title for a fresh select screen, `leave`: out of a
  fight whose session ended). `neutral` = at character
  select, waiting for `T5_FIGHT_FILE`. `fight` with `match` = k means match k is
  running. `pick`: this player picks on the select screen; `pick_wait`: picked,
  waiting for the opponent's pick. `p1`/`p2` are the fighters (with the in-game
  select: what was picked, once known), `b1`/`b2` the confirm buttons (1 Square,
  2 Triangle, 3 Cross, 4 Circle; 0 = the default), `m1`/`m2` the model ids both
  sides fight with (from FIGHT START on).
- Result file: written by netplay when netplay is on (with `match`, `desync`,
  `frames`, `hash`, `fps`, and `reason` when the match could not be finished;
  docs/NETPLAY.md), by the direct-fight code when netplay is off (`match`,
  `winner`, `score`). Winner 0 = P1, 1 = P2, null = draw; score = rounds won.
- Netplay: run both games with `T5_NET_START=external` and the same `T5_FIGHT`
  (and the same `PS3_FIXED_TIME`, see Determinism). At the first frame of the
  game mode the direct-fight code calls `t5_netplay_start()`; the next frame is
  lockstep frame 0 on both PCs and the HELLO handshake there is the ready
  barrier. Every later match calls it again (sync point). Menu driving goes
  through `t5_netplay_inject()` (added to `src/netplay/t5_hooks.cpp`) so it
  works while netplay owns the pads; without netplay the module's own
  `cellPadGetData` override injects. Before lockstep starts (the first match)
  each PC drives both cursors locally; while lockstep runs (every later match)
  each PC drives only its own slot and the presses go out as its local input,
  so the peer sees them through the exchange -- the two launchers may write
  `T5_FIGHT_FILE` at different times, each player's cursor simply starts
  moving when its own file arrives, and the game states stay identical.
- `names=` / `ranks=` (key=value, fight lines only): the HUD identity for this
  match, names percent-encoded (`Dry%20A|Bee`); without them a line keeps the
  last match's (a rematch: the same two players). See "Names and ranks in the
  HUD".
- After the deciding KO the pads are held neutral and the driver skips the
  replay and win pose itself (see "After the match"). `T5_DF_HOLD=0` turns
  both off (the old behaviour, for comparisons), `T5_DF_SKIP=0` only the
  skipping, `T5_DF_SKIP_BUTTON=<hex>` picks the button (default 0008 = START).
  `T5_DF_STAGE_WAIT=<frames>` (default 30, was 90): from both fighters
  confirmed to the first stage confirm.
- Diagnostics: `T5_DF_PROBE=1` (mode changes), `T5_DF_TRACE=1` (every injected
  press with the cursor state), `T5_DF_LOG`, `T5_DF_DUMP=frames`,
  `T5_DF_DUMP_RANGES`, `T5_DF_DUMP_MODES=1`, `T5_DF_WATCH=addr,...`,
  `T5_DF_POKE=frame:addr:width:value`, `T5_DF_SHOT=frames` (needs
  `LD_SURF_DUMP`/`LD_SURF_DUMP_GATE`; `+n` = n frames after the first FIGHT
  START, whatever the loading took), `T5_DF_SCRIPT[2]` (frame scripts, tests),
  `T5_DF_STARTVS=N` (the title-to-select jump alone), `T5_DF_FIND=frame:text,...`
  (log every address of that text, ASCII and UTF-16BE, in guest memory at
  that frame), `T5_DF_FRESH_LOG`, `T5_DF_FRESH_AT`, `T5_DF_GUARD`,
  `T5_DF_STUCK_SECONDS` (persistent game, "After a session ends"),
  `T5_DF_SELECT_STUCK_SECONDS`, `T5_DF_READER_GUARD=0` ("Select stall after a fight").

Timeline on this PC (60 fps, frames counted from the first frame after boot):
title mode at ~890, start-VS call at +30, select mode at ~925, both characters
and costumes confirmed by ~995 (closed-loop cursor moves every 8 frames),
stage confirm at ~1025, game mode (= FIGHT START, `t5_netplay_start()`) at
~1075, i.e. the fight loads about 19 s after boot instead of ~80 s through the
menus; a second match (rematch or, in a persistent game, a new opponent)
needs only the select-screen part: 3-6 s from the command to FIGHT START.

## How the game is driven

Mode machine (`tcb_mode_manager_t`, object found by its vtable 0x10050054, in
the tcb pool at 0x10624C80 on this path; request struct at +0x58 = {cur, next
(0xE = none), prev}): 0 initialize, 5 namco logo, 1 title (title screen + main
menu), 6 select (`tcb_selectmode_t`: characters, costumes, stage), 4 game
(`tcb_gamemode_t`, the fight), 11 result, 2/7/9 "oldmode", 3 option, 8 end,
10 ranking, 12 gallery, 13 online. Requests go through `func_0025DA54(id,
param)`; the factory is `func_0025E6AC`.

1. Title mode reached (mode 1) + 30 frames: call `func_0004E9DC(4, 3)`, the
   game's own "start game type" routine (4 = VS BATTLE, 3 = both players
   human). It fills the battle config at 0x1008EBAC (+0 game type, +0x28 =
   0x1008EBD4 rounds to win from the options, handicaps 100/100, ...) and
   requests mode 6. The namco logo / intro / title menu are skipped by never
   waiting for them.
2. Select mode: per player, the select record at 0x10093F58 + p*0x78: +0 the
   cursor cell, +8 the portrait id under it, +0x0C the picked model id
   (character + costume), +0x20 the state byte (3 choosing, 9 the handicap bar,
   then done: 0x0C while the other side still chooses, then 0x15 on P1, 0x0D
   on P2). The select
   state 0x1008F070 is 3 while the screen takes input. The cursor is moved by
   injected presses (closed loop: read the cell, step toward the target cell,
   re-read; one step per 8 frames), CROSS confirms the character (or the
   button an in-game pick names: the costume), CROSS again the handicap bar
   (100 %). When both are done, CROSS confirms the stage panel (every 30 frames
   until the select state reaches 4); the stage shown does not matter. The
   confirm writes the panel's own (random) pick to 0x1008F088 (two frames
   before the select state turns 4); the configured stage is written there at
   the top of every frame of the stage phase (before netplay hashes the frame),
   so the pick never shows in the hashed state.
   In a rematch under lockstep the two panels' picks differed (QA run
   fd_rematch: 0x1d vs 0x11 for the 50 frames between confirm and fight start,
   a transient desync); now the hashed state never sees them.
3. First frame in mode 4: rounds to win -> 0x1008EBD4 (u8), stage id ->
   0x1008F088 (the stage confirm writes the panel's pick there; the game-mode
   loader copies it to 0x10053A08 later, so the overwrite wins), then
   `t5_netplay_start()`. This frame is "FIGHT START" in the log/status.
4. Match over: 0x1008EBD5 != 0; the rounds each player won are the fighters'
   counts at 0x100900D1 / 0x100909A1 (1.1.3, docs/NETPLAY.md "Match result";
   before, the battle config's 0x1008EBDA/DB, which stay 0 in direct fights, and
   the winner index 0x1008EBD6 made the score rounds-to-win : 0).
   Result file, state `over`; from here the pads are held neutral and the
   driver skips the replay and win pose (next section); the game returns to
   character select; when the select screen is live again (mode 6, state 3,
   record states 3) the next fight is read from the file or the state is
   `neutral`.

Select grid (cell -> character), measured by walking the cursor and checked
against the screen: cells 0-11 middle row, 12-23 bottom row, 24-34 top row
(column = cell - 24; cell 24, Jinpachi's slot, is skipped by the cursor, so
Jinpachi is not selectable here yet). UP/DOWN cycle top -> middle -> bottom and
skip a row with no cell in that column.

```
top    : --  Eddy Baek Mokujin DevilJin Raven Asuka Feng Ganryu Wang ArmorKing
middle : Anna Marduk Law Hwoarang King Lili Dragunov Heihachi Christie Paul Jack-5 Bruce
bottom : RogerJr Lei Nina Steve Kazuya Xiaoyu Jin Lee Julia Yoshimitsu Bryan Kuma
```

Kuma and Panda share the last bottom cell: a punch button (SQUARE) confirms
Kuma, a kick button Panda. The driver presses SQUARE for Kuma and
`T5_DF_ALT_BUTTON` (default CIRCLE) for Panda; checked by forcing both
(before, Kuma was confirmed with CROSS and came out as Panda).

## Character select in the game (branch ingame-select)

Owner's request: pick the character in the game, not in the launcher. With
`pick=N` on the fight line (the lobby sends it, docs/RANKED.md "Character
select in the game") each player picks character and costume on the game's own
select screen, then both PCs fight exactly those picks with the usual
lockstep/rollback start. The two select screens are **not** in lockstep: each
PC's select screen runs on its own, and only the picks travel.

What the select screen does (probes with scripted pads, build/cs/exp):

- Every face button confirms the character, and the button is the costume:
  Square (LP) and Triangle (RP), Cross (LK) and Circle (RK) give the same
  model for most characters (two costumes; Lili 0x4D / 0x4E, Dragunov 0x4F /
  0x50); Triangle is a third costume for Law, Yoshimitsu, Jin, Lee, Anna,
  Ganryu, Bruce and Raven; Xiaoyu and Asuka have four (Xiaoyu 0x10, 0x13, 0x11,
  0x14 for LP, RP, LK, RK). Kuma's cell gives Kuma with a punch button (model
  0x1E) and Panda with a kick button (0x1F). The picked model id is at record
  +0x0C. Full table: "Mirror matches" below.
- State 9 after the confirm is the **handicap bar** (100 %), not a costume
  choice; the next confirm finishes the pick. The record then reads 0x0C while
  the other side still chooses (always on P2; on P1 at the select screen a
  match returns to, not at a fresh one), then 0x15 on P1 and 0x0D on P2.
- L1 loads customize data ("L1 BUTTON : LOAD CUSTOMIZE DATA"); Start, Select,
  R1, L2, R2, L3 and R3 do nothing here. There is no random cell (Jinpachi's
  cell 24 is skipped by the cursor).
- The name and rank plates of the select screen come from the VS custom data
  (see "Names and ranks in the HUD") and are read every frame: written at the
  select screen they show at once.

The flow, per PC (`df_fight.cpp` phases Pick and PickWait, helpers in
`df_pick.cpp`):

1. **Pick.** Once the select screen takes input, this PC's pad drives this
   player's side only (P1 on the host, P2 on the joiner), the other side reads
   neutral. The pad is read through the runtime's pad layer
   (`cellPad_sample_local(0)`: controls.ini, sticks, keyboard,
   `PS3_PAD_FILE`) and filtered: d-pad and left stick as directions, one face
   button at a time (so the confirming button, the costume, is never in
   doubt), **Select = random** (character and costume drawn on this PC), L1,
   Start and the rest never reach the game. A button held when the screen came
   up counts only after it was let go (the Cross that accepted the match in the
   launcher must not pick). The name plate under this player's portrait counts
   down ("CHOOSE 17"). After the confirm the driver confirms the handicap bar
   at 100 %.
2. The pick -- character, button, model id -- goes to the opponent's game as a
   **PICK packet** over the netplay session (docs/NETPLAY.md "In-game
   select"), keyed by the session's match number, resent every 100 ms until
   acknowledged.
3. **PickWait.** The opponent's plate says "PICKING..." until its pick is in.
   Then the driver moves the opponent's cursor to its pick and confirms with its
   button (as for a lobby-picked fight), then the stage (the line's, from the
   lobby), FIGHT START, lockstep frame 0 / the resume (below). At FIGHT START
   both sides' model ids are logged ("fighters: P1 ... (model 0x..), P2 ...",
   every fight) and compared with the picks ("PICK MISMATCH" if not).
4. **Timeout.** No pick within N seconds of this player's select screen
   coming up: the driver picks the line's character for this player (the
   launcher's) with the default button ("TIME UP"), and that pick goes to the
   opponent like any other. A game that never sends a pick (but keeps its
   session alive) is waited for N + 45 s, then its side gets the line's
   character too.

**Mirror matches (1.1.0 blocker, fixed 2026-10-19).** When the second of the
two sides confirms the model the first one already has, the select screen
gives it another costume ("the second confirm gets the other costume" -- the
game's own rule, on the picked model, not the button: Steve Square and Steve
Triangle collide as well). Each PC used to confirm its own player first -- the
host P1, the joiner P2 -- so the two games put the other costume on different
sides (Steve vs Steve, both Square: host P1 0x29 / P2 0x2A, joiner P1 0x2A /
P2 0x29, every frame of the fight apart; e2e `cs_mirror`; two timeouts with
the same launcher fighter too). Now P1 is confirmed first on every PC and on
every path, and P2 only once P1's record is past the handicap bar (state 0x0C
and up, `p1_settled()`): on the joiner the player's confirm (or the driver's,
for a timeout or Select) is held -- the name plate says READY -- until the
host's pick has come and has been driven onto P1; the opponent's pick stays
hidden until this player has chosen, as before. In a lobby-picked or locked
fight (a ranked set's games 2 and 3, launcher-picked rematches) the Select
phase confirms P2 of a mirror only after P1 is settled. The game's rule then
runs the same way on both PCs, whatever "the other costume" is for the
fighter. It is (model of the first pick -> the second pick's model, both sides
confirming the same button; probe with one offline game, P1 confirmed first):

| Fighter | LP (Square) | RP (Triangle) | LK (Cross) | RK (Circle) |
|---|---|---|---|---|
| Paul | 00 -> 01 | 00 -> 01 | 01 -> 00 | 01 -> 00 |
| Law | 02 -> 03 | 04 -> 02 | 03 -> 02 | 03 -> 02 |
| Lei | 05 -> 06 | 05 -> 06 | 06 -> 05 | 06 -> 05 |
| King | 07 -> 08 | 07 -> 08 | 08 -> 07 | 08 -> 07 |
| Yoshimitsu | 09 -> 0A | 0B -> 09 | 0A -> 09 | 0A -> 09 |
| Nina | 0C -> 0D | 0C -> 0D | 0D -> 0C | 0D -> 0C |
| Hwoarang | 0E -> 0F | 0E -> 0F | 0F -> 0E | 0F -> 0E |
| Xiaoyu | 10 -> 13 | 13 -> 10 | 11 -> 14 | 14 -> 11 |
| Christie | 15 -> 16 | 15 -> 16 | 16 -> 15 | 16 -> 15 |
| Jin | 19 -> 1A | 1B -> 19 | 1A -> 19 | 1A -> 19 |
| Julia | 1C -> 1D | 1C -> 1D | 1D -> 1C | 1D -> 1C |
| Kuma | 1E -> 1F | 1E -> 1F | -- | -- |
| Panda | -- | -- | 1F -> 1E | 1F -> 1E |
| Bryan | 20 -> 21 | 20 -> 21 | 21 -> 20 | 21 -> 20 |
| Heihachi | 22 -> 23 | 22 -> 23 | 23 -> 22 | 23 -> 22 |
| Kazuya | 24 -> 25 | 24 -> 25 | 25 -> 24 | 25 -> 24 |
| Lee | 26 -> 27 | 28 -> 26 | 27 -> 26 | 27 -> 26 |
| Steve | 29 -> 2A | 29 -> 2A | 2A -> 29 | 2A -> 29 |
| Marduk | 2B -> 2C | 2B -> 2C | 2C -> 2B | 2C -> 2B |
| Mokujin | 2D -> 2E | 2D -> 2E | 2E -> 2D | 2E -> 2D |
| Eddy | 17 -> 18 | 17 -> 18 | 18 -> 17 | 18 -> 17 |
| Jack-5 | 2F -> 30 | 2F -> 30 | 30 -> 2F | 30 -> 2F |
| Roger Jr. | 31 -> 32 | 31 -> 32 | 32 -> 31 | 32 -> 31 |
| Anna | 33 -> 34 | 35 -> 33 | 34 -> 33 | 34 -> 33 |
| Wang | 36 -> 37 | 36 -> 37 | 37 -> 36 | 37 -> 36 |
| Ganryu | 38 -> 39 | 3A -> 38 | 39 -> 38 | 39 -> 38 |
| Asuka | 3B -> 3D | 3D -> 3B | 3C -> 3E | 3E -> 3C |
| Bruce | 3F -> 40 | 41 -> 3F | 40 -> 3F | 40 -> 3F |
| Baek | 42 -> 43 | 42 -> 43 | 43 -> 42 | 43 -> 42 |
| Devil Jin | 44 -> 45 | 44 -> 45 | 45 -> 44 | 45 -> 44 |
| Raven | 46 -> 47 | 48 -> 46 | 47 -> 46 | 47 -> 46 |
| Feng | 49 -> 4A | 49 -> 4A | 4A -> 49 | 4A -> 49 |
| Armor King | 4B -> 4C | 4B -> 4C | 4C -> 4B | 4C -> 4B |
| Lili | 4D -> 4E | 4D -> 4E | 4E -> 4D | 4E -> 4D |
| Dragunov | 4F -> 50 | 4F -> 50 | 50 -> 4F | 50 -> 4F |

So the second pick takes the first's alternative: two-costume fighters swap,
the Triangle (third) costume falls back to the Square one, Xiaoyu and Asuka
swap LP/RP and LK/RK, and **a Kuma mirror makes P2 Panda** (a Panda mirror P2
Kuma); the lobby's history still says Kuma vs Kuma, the lock replays the same
(P1 Kuma, then P2 with Kuma's button -> Panda). Verified online after the fix
(two games, local lobby): e2e `cs_mirror` PASS (Steve Square x2: 0x29 / 0x2A
on both PCs; Jin Triangle vs Cross); ranked_session mirrors: rollback quick +
rematches (Steve LP/LP, Baek RK/RK, Xiaoyu RK/LP, Kuma LP/RP -> Kuma vs Panda),
lockstep room (Steve timeout/timeout, Devil Jin LP/RP, Xiaoyu RK/RK), a
rollback ranked set Steve LP/LP with games 2 and 3 locked (0x29 / 0x2A in all
three) and a lockstep ranked set Kuma RP/LP (Kuma vs Panda in all three): 15
mirror matches, 0 mismatching frames, the same hash, all confirmed.

**Rematches.** Between two matches of a session the lockstep (or rollback) used
to keep running through the select screen. With the in-game select it pauses
there: when the select screen is back after a match, both games ask for a pause
at the same game frame (`t5_netplay_pause()`); the next frame is a sync point
(under rollback every input before it is confirmed), and from there the hooks
run as between two sessions (keyread tick with neutral pads, the session's
socket and keepalives stay). At the next FIGHT START `t5_netplay_start()`
resumes at the paused frame number with a sync point that also sets the game's
frame counters, input ring and random seeds equal (the two select screens ran
for different numbers of frames); the rollback loop starts again from there.
The first match of a session needs none of this: its lockstep starts at FIGHT
START anyway.

**Ranked lock.** A ranked set (best of 3, docs/RANKED.md "Ranked sets") is
picked in its game 1 only; games 2 and 3 come with no `pick` (the set's
characters are those game 1 picked): the select screen is skipped and the
driver picks both sides as in a lobby-picked fight, on each PC locally (after a
picked game the lockstep is paused there all the same). The costumes come
along as `buttons=b1|b2` on the fight line (the lobby keeps the confirm buttons
game 1 reported); without it a fighter that is the same as in the session's
last fight keeps its costume -- only within one netplay session, so a set game
over a new connection (a replay after a desync, a restarted game) needs the
lobby's buttons. The set's next game starts by itself after the countdown (no
vote): the game gets the same "fight" command in the running session (or a new
session); one that comes while the win pose still runs waits for the select
screen.

Not done: no in-game text beyond the name plates (the launcher's status line
says the same: "Pick your fighter in the game", "Waiting for your opponent to
pick..."); Jinpachi stays unpickable (no cell); the customize data (L1) is not
offered online.

Test: `tools/pick_flow_test.py` -- two games on this PC, each player's picks
pressed through its `PS3_PAD_FILE` closed-loop on the cursor cell the game
logs (`T5_DF_TRACE=1`), scenarios per match: `<char>:<lp|rp|lk|rk>`,
`random`, `timeout`, `late<s>:<char>:<button>`; persistent flow with new
sessions and rematches, or process flow (`T5_FIGHT_FILE`); `--locked-after`
for a ranked set's lock. A match passes when both games log the same picks
(character, button, model) at FIGHT START, scripted picks are what was asked,
and both results have the same winner and state hash with 0 mismatching frames.

**Results** (2026-10-18/19, two games on this PC, muted, minimized, below-normal
priority, other agents' games beside them -- 22-55 fps):

- **Through a local lobby** (`lobby/tools/ranked_session.py --exe ... --persistent
  --attacks --ingame-pick --pick1 ... --pick2 ...`, the launcher's glue, scripted
  picks): **19 matches, every one started on both PCs with the same fighters and
  costumes, every result confirmed, 0 mismatching frames.**

  | Run | Mode | What |
  |---|---|---|
  | e2e_ranked | rollback | ranked set of 3: game 1 picked Jin (Triangle) vs Lili (Cross) over the launchers' Kazuya/Heihachi; games 2 and 3 skipped the select screen with the same fighters and costumes; the history says jin vs lili |
  | e2e_ranked_ls | lockstep | ranked set of 2: Select = random (Heihachi), Kuma's cell + Cross = Panda; game 2 locked to Panda vs Heihachi |
  | e2e_room_ls | lockstep | room match, then the room rematch with both changing; a random pick, a timeout (the launcher's character) |
  | e2e_room_rb | rollback | room match + rematch, both changing, a pick 6 s late |
  | e2e_quick_rb | rollback | quick match + rematch, both changing |
  | e2e_sets_rb | rollback | ranked set of 2, then the next opponent (a new pairing, a new session) against a **freshly started game** (P2's game closed in between), P1 changes Jin -> Steve, set of 2 again |
  | e2e_sets_ls | lockstep | quick: 2 pairings of 2, rematches where only P1 changes (Kazuya -> Julia, Asuka -> Law), a fresh game in the second pairing |

- **After the merge with main (2026-10-19: ranked sets of best of 3, the TLS
  generator fix, rollback-crash, lobby hardening)**, `lobby/tools/ranked_session.py
  --exe ... --persistent --ingame-pick --rounds 1 --plan ...` (the planned
  winner's game attacks through T5_NET_PADFILE), table by `tools/pick_report.py`:
  **28 of 28 matches started on both PCs with the same fighters and costumes,
  0 mismatching frames, the same state hash, confirmed.**

  | Run | Mode | What |
  |---|---|---|
  | m_quick_rb / m_quick_ls | rollback / lockstep | quick match + 3 rematches; every rematch changes both fighters across column 11 and the top row (Bruce/Kuma/Panda <-> Raven/Eddy/Devil Jin/Armor King) and costumes (Devil Jin Cross -> Circle, Armor King Square -> Circle) |
  | m_room_rb / m_room_ls | rollback / lockstep | room match + 2 rematches with new picks; Select = random and timeouts on either side |
  | m_set_rb / m_set_ls | rollback / lockstep | ranked set 2-1 / 1-2: game 1 picked (Kuma Triangle vs Xiaoyu Circle = her 4th costume; Lili vs Panda), games 2 and 3 started by themselves after 6 s with `buttons=2\|4`, the same models |
  | m_switch_rb / m_switch_ls | rollback / lockstep | quick pairing of 2, P2's game closed, a new pairing of 2 against a freshly started game |

  Also launcher-picked rematches (no in-game select, the owner's "rematch with
  a character change" report on 1.0.x) across column 11 and the top row in both
  directions, with `buttons=` on new sessions and rematches:
  `pick_flow_test.py --no-pick --mash --rematch-every 2`, 4/4 rollback (m_np_rb)
  and 4/4 lockstep (m_np_ls), 0 mismatching frames.
- **`tools/pick_flow_test.py`** (no lobby; persistent unless noted): 20 of 25
  matches OK across the runs t1, rep1, big_ls, final_rb, proc_rb. The 5 others:
  Devil Jin (big_ls match 6; the TLS generator, fixed since, see "Known
  transient mismatches"); two short
  mismatches under rollback in final_rb (22 frames Wang vs Heihachi, 1 frame
  Raven vs Asuka, mid-fight, same winner; the same pairs ran clean in
  e2e_room_rb); one hang that was the driver's cursor (from column 11 -- Bruce,
  Kuma -- the top row was never reached; fixed); and in process mode under
  rollback at ~22 fps one game showed "The installed game data is corrupted"
  after a KO (mode 8, the game's end) -- the post-match loads under deep
  rollbacks (depth 9), the known rollback-over-loads problem (ROLLBACK.md 31),
  not the select screen.
- Picks seen: every costume button, Xiaoyu's four costumes, Kuma/Panda,
  random, timeouts on either side, a late pick, mirror matches (in these runs
  the two PCs gave the other costume to different sides unnoticed; fixed, see
  "Mirror matches").

## After the match: no input reaches the select screen

Release dry run finding: mashing buttons through the deciding KO started the
game's own next VS battle ("VS BATTLE 2 / GET READY FOR THE NEXT BATTLE", the
Champion/Challenger round), and the rematch fight never started. What happens
(offline repro, build/dp/work/mash1, `T5_DF_PROBE=1`): the mashing skips the KO
replay and win pose, the game returns to the select screen (mode 6) about 140
frames after the KO, and the same mashing then picks both fighters (CROSS) and
the stage there -- the select mode requests the game mode by itself. When the
launcher's next fight arrives (a rematch is only written after both players
accepted it, often seconds later), the driver finds the game in a fight it did
not start: "fight requested but the game is in mode 4". Under lockstep both
PCs start that battle in step, but its stage is the panel's own random pick
on each PC, so it desyncs as well.

The fix, in `df_fight.cpp`:

- **From the frame the match is decided** (0x1008EBD5 set in this fight) **until
  the driver's next select**, both pads read neutral: `hold_pads()` turns the
  injection on with no buttons. Offline that is the module's own
  `cellPadGetData` override; under lockstep it is the local slot's exchanged
  input (`t5_netplay_inject` -> `np::set_local_inject`), so each PC holds its
  own player from the same game frame (both see the decision at the same
  lockstep frame) and the peer's held input arrives through the exchange.
  Presses sampled in the `delay` frames before that frame still apply -- they
  land in the KO slow motion, long before the select screen. The driver's own
  presses at the next select go through as before.
- With every pad neutral the game would play the whole replay and win pose
  (~850 frames, 14 s). The driver **skips them like a player**: one START
  press (`T5_DF_SKIP_BUTTON`; CROSS does not skip, run mash3) every 20 frames
  from 40 frames after the decision until the game asks for the select mode;
  each press is released before the game reacts to it with the mode change,
  so none reaches the select screen. Under lockstep each PC presses its own
  slot at the same frame. KO to a live select screen: ~185 frames (3 s).

Tests (`tools/fight_flow_test.py`, two games on this PC, both mashing face
buttons and directions the whole time with `--mash`, one round per match,
the rematch line written 25 s after the results like players clicking Rematch
late, `--rematch-wait 25`):

| Build, mode | Matches | Next fight started | Mismatching frames |
|---|---|---|---|
| `T5_DF_HOLD=0` (the old behaviour), lockstep (run rm0b_nohold) | 2 | match 2 never started ("fight requested but the game is in mode 4": the game's own battle) | 1,848 by frame 9599 (the battle's own random stage) |
| fix, rollback (the default; run rb_mash) | 4 | every time, 2.0-3.1 s from the line to FIGHT START | 0, results confirmed on both sides |
| fix, lockstep `T5_RB_MODE=off` (runs final_mash, ls_mash) | 4 + 3 | every time, 2.0-3.4 s | 0 (14,399 lockstep frames in final_mash) |

**A match end that a rollback takes back** (desync hunt, 2026-10-19): under
rollback the deciding KO can be seen on a predicted frame and then undone by
the correction -- the fight goes on (netplay logs "the match end seen at frame
N was rolled back -- no result yet"). The driver used to stay in its "over"
state: it held this PC's player neutral for the rest of the fight and pressed
START every 20 frames to skip a win pose that never came, which paused the
running fight; the pause menu's presses ended in the game's end mode (8), and
the next reset hung there until the 60-s stuck check ended the game (run
mx_cpus4_rb: a 4-processor joiner, KO at frame 2022 undone, the match ran on to
4689). Now the driver goes back to the fight when the decided byte is 0 again
in the fight phase, and releases the pads.

**Online START reaches the game only where it skips** (1.1.2, NETPLAY.md "No pause
online"): in a session both games take START out of both players' inputs except in a
round's replay and from 40 frames after a decision seen in this fight until the select
screen is asked for -- exactly where this driver's skip presses (and the rollback loop's
post-match rule) land. A START press in a fight that went on (the case above) can no
longer pause it; the driver needs START nowhere else (its menu presses are face buttons
and directions, the in-game select blocks START).

**The fight's loading and intros take no input either** under netplay: from
FIGHT START until the fight phase word 0x1008F070 passes 12 (7 = game mode
start, 8-12 loading and intros, 17 = fighting; again between rounds) the
driver holds this PC's player, once lockstep runs (before that the hooks'
override of the game's pad read is in use, and FIGHT START clears it). The
rollback loop sends neutral input there by itself (its intro rule); in lockstep
a faster PC otherwise runs the last loading frames before the scene barrier
with input the other PC never sees.

## Names and ranks in the HUD

Each fight shows a name and a rank badge under the health bars ("Unknown" and
"Beginner" until now), and the select screen shows the same with "0 W 0 L
0.00 %". They come from the VS **custom data** of each side (the "1P/2P
CUSTOM DATA LOAD" of the VS select): two blocks of 0x1F4 bytes, P1 then P2, at
the address in the TOC entry 0x46ECD0 (0x106C9934 on this path).

- Name: UTF-16BE at +0x134, 20 characters. Read by 0x2A1740 (block + p*0x1F4 +
  0x134 unless the game is in its online mode), copied by 0x1052B0 (u16 copy, at
  most 20) in 0x105BB4; if it is blank (0x105474: empty or all U+3000) the HUD
  shows message 0x104FF of the text resource, "Unknown" (ASCII in the loaded
  text table, 0x41580360 in this run; the UTF-16 copies at 0x104EB8xx are the
  HUD's rendered text list).
- Rank: u8 at +0x11C, read by 0x2A180C; the badge sprite comes from the table
  at 0x100692F0 (`beginner_b`, `9th_kyu_b`, ... pairs of English/Japanese
  sprite names), the same 37 ranks in the same order as `t5lobby.ranks.RANKS`.
  Checked on screen: 1 = 9th kyu, 3 = 7th kyu, 10 = 1st dan, 12 = 3rd dan,
  33 = Tekken Lord; 34, 35 and 36 all show the **Dark Lord** badge (Kouryu and
  Kirin have no English badge in the HUD).
- Found with `T5_DF_FIND` (where "Unknown" is), the lifted code (who reads the
  message id 0x104FF) and `T5_DF_POKE` tests (build/dp/work/poke1, poke_a,
  poke_b: "TEST"/"AB" with 1st dan / Dark Lord, Tekken Lord / 9th kyu).

At the first frame of the game mode (FIGHT START, before `t5_netplay_start()`)
the driver writes `T5_HUD_NAMES` / `T5_HUD_RANKS` (or a fight line's `names=` /
`ranks=`) into both blocks; a name only if one is given (else the game's
"Unknown"), at most 16 characters, printable ASCII. The HUD is built while the
fight loads, so the names show from the round intro on, and the select screen
of the next match shows them too. Both PCs write the same values (the lobby's
P1/P2 list) at the same lockstep frame; the blocks are outside the netplay
state hash anyway and nothing in a fight reads them (every match since: equal
hashes). The launcher passes the lobby names and tiers (guests and players
still in placement: 0, Beginner): `match_driver.hud_values()`.

## Persistent game (T5_CTL_DIR): a new opponent without a new process

Tekken 6 Native Online keeps the game open between all matches. With
`T5_CTL_DIR=<dir>` the game does too: the launcher starts it once without any
`T5_NET_*`, and every match is a command in `<dir>/cmd.json` (protocol:
docs/RANKED.md "Game control channel"; code: `src/directfight/df_ctl.cpp`):

```
{"seq": 3, "cmd": "fight", "match": "m1a2...", "rematch": false, "env": {"T5_NET_MODE": "host", "T5_NET_PORT": "52685", ...,
 "T5_FIGHT": "9,33,20,3", "T5_NET_RESULT_FILE": "...", "T5_DF_STATUS_FILE": "...", "T5_HUD_NAMES": "A|B", "T5_HUD_RANKS": "11,3"}}
{"seq": 4, "cmd": "idle"}     the session ends (BYE, UDP port free again), back to a fresh select screen
{"seq": 5, "cmd": "quit"}     exit
```

The game answers in `<dir>/state.json`: `{"ctl": 1, "seq": <last command
taken>, "state": "boot|idle|connecting|loading|fight|result|error", "match",
"error", "session", "frame"}` (the direct-fight status file keeps working as
before). `cmd.json` is looked at every 6 frames while the game waits, every 30
otherwise.

How a new opponent is played:

1. **"idle"** (the launcher sends it when a match with someone else is found):
   the netplay session ends (`t5_netplay_session_end`: BYE, socket closed; the
   rollback loop stops and drops its undo logs), the pads are held, and the
   driver makes a fresh select screen, whatever the last opponent left behind
   (battle config, VS counters, cursor positions). **After a fight** (the game
   mode ran since the last title) it goes back to the **title** (mode request 1
   through the game's own 0x25DA54, from a live select screen with no mode
   change pending; from the win pose it first skips it as above), puts the
   match-state areas back as they were at boot (next paragraph) once the title
   has settled, and calls the start-VS routine again. **Without a fight since
   the title** it never visits the title a second time (that corrupts the game,
   see "After a session ends"): an untouched select screen stays as it is, a
   used one is restarted -- the start-VS routine, and the select mode ended and
   built again by the game's mode manager (see "Select restarts"). This happens
   while the players accept and the lobby punches.
2. **"fight"** for a new session: its `env` goes to the session environment
   overlay (`t5_env_overlay_*`, src/netplay/netplay_core.cpp) -- not to the
   process environment: the runtime caches every `getenv()` value for good
   (ps3recomp boot_main.cpp) -- then `t5_netplay_session_begin()` sets netplay
   up from it exactly as at boot (new socket on the given port, new session id
   and nonce, handshake from now on), and the driver drives the select screen
   as for a first match (both cursors locally; lockstep starts at FIGHT START).
3. At FIGHT START `t5_netplay_start()` begins the new session's lockstep at
   frame 0: frame counters, input ring and random seeds set as at a first
   start; the keyread thread stays parked from the first session on, and
   between sessions the main thread keeps running its tick with neutral pads.
4. Under rollback (the default) the loop takes over in every session as in
   a first match (it is offered in a persistent game too: `rb_net.cpp`
   `offered_by_env`, `session_reset`).
5. The result file is written as before. A **rematch** is a "fight" with
   `"rematch": true` (or the same `T5_NET_MODE/PORT/PEER/KEY/SEED`) while the
   session runs: the next match in it, as a `T5_FIGHT_FILE` line in process mode.
6. A session that ends by itself (peer lost, no connection, other build:
   `T5_NET_ON_LOST` does not apply) writes its result file with the reason as
   before, but the game stays open: a fight is left with mode request 6, the
   driver goes back to a fresh select screen as in 1., `state.json` says `error`
   with the reason until the next command. Exit codes 3/4/5 are process mode
   only; a persistent game that cannot get back to a select screen within 60 s
   ends itself with exit code 6 (below).

**A game that has played meets a fresh one.** The new opponent's game may have
just started. Two things differ then, and both had to go:

- *Leftovers.* A match leaves values in the hashed match state (the fight
  block, the unused third/fourth fighter blocks, effect records) that a game
  that has never fought has as zeros, and the next fight does not overwrite
  all of them: 1,662 of 1,662 frames mismatching (run dm2, lockstep; the fight
  itself the same). The four game areas of the netplay hash
  (0x1008E000+0x4000, 0x10099600+0x600, 0x100A0900+0x200, 0x100A3B00+0x300;
  `T5_DF_FRESH_RANGES`, `T5_DF_FRESH=0` off) are copied at boot when the
  title has settled, right before the first start VS, and put back at the same
  point of every later title visit (3.3 KB differed after one match). From
  there both games run the same title -> start VS -> select -> fight path
  from the same bytes. A select screen restarted in place (no fight since the
  title) needs no copy: only select-screen words changed since, and the
  restart writes them again.
- *Loading time.* The played game loads the next fight from its caches and
  ends the loading a few frames earlier or later than a fresh one. In lockstep
  the loading's scene change is a sync point anyway; under rollback it was not
  (ring resets are ordinary state there), and the two games then fought
  2 frames apart: 4,228 mismatching frames (run rb_ps1). Now the end of the
  loading -- the first frame the phase word shows the intros (11, 12) or the
  fight (17) after a fight start, where nothing is predicted wrong -- is a sync
  point in both modes (reset-fix; fight-polish used the first ring reset,
  which is "Fight!" itself: see "After a session ends"), and the frames of the
  game mode's start, loading and intros (phase 0..12) are not hash-compared in
  direct fight (both sides send a fixed value; a difference that lasts reaches
  the fight, where every frame is compared), nor is the first frame after a
  scene barrier (the side that did not jump hashed it before the barrier's
  reseed). `t5_hooks.cpp` `g_await_load`, `fight_loaded_now`, `kIntroHash`;
  `rb_net.cpp` `scene_change`.

Measured (`tools/fight_flow_test.py --flow persistent --fresh-at 2 --mash`,
two games on this PC, "idle" then "fight" 0.3-1 s apart): rollback, 5 matches
(run rb_ps5): every one confirmed, equal hashes, 0 mismatching frames, up to 19
rollbacks per match, command to FIGHT START 4.5-8.0 s; lockstep
`T5_RB_MODE=off`, 4 matches (run ls_ps2): the same, 4.0-6.3 s. Against ~19 s for
a new process. Through the lobby (Accept to FIGHT): docs/ONLINE.md.

Limits: `PS3_FIXED_TIME` cannot change after boot (the runtime reads it once);
a persistent game runs on its real clock (no effect on the fight state seen).
A peer must run the same build (the build id check makes sure): the end of the
loading is a sync point only from this build on.

## After a session ends (reset-fix, 2026-10-17)

Release dry run of 0.1.6 (persistent game, rollback, a PC loaded by other
benchmarks): player A's fight never finished loading, B waited at the end of
the loading until it gave the match up (`peer_stalled`), A gave up too
(`peer_timeout`). B went leave -> reset -> title -> neutral; when the
launcher's "idle" came, B's game broke for good (`guest_call: OPD 0x004635A8
-> code 0 not registered` -- the vblank handler -- NULL calls in the sound
threads, FIFO jumps to unmapped IO, fence queue overflow), and the launcher
fell back to a new process. A sat at "leave: waiting in mode 4" for minutes.
Three faults, none of them the boot-state copy (a fourth, older one came up
in the cycle test):

- **The second title visit after a fight corrupts the game.** Title mode,
  select (start VS), title again with no game mode in between: the title's
  set-up initialises a model whose data pointer is stale (0x2AE3D4 on an object
  pointing into the game heap, `count` 0x02120420), 0x2DBBEC asks the small
  block allocator 0x2BB634 for 138 MB, gets NULL, and its memset 0x3AF974
  clears guest memory from there on: the OPD page 0x463000 and the code image
  below 0x08481084 with it (`T5_DF_GUARD=4635A8:10` caught the store). The
  title once after a fight is fine, and so is title -> select -> title
  without any fight (boot). Reproduced offline in one process (fight, leave or
  play it out, two "idle"): 7 of 7 runs, also after a match played to its end,
  with the copy off (`T5_DF_FRESH=0`), with each of the four copy areas alone,
  with the title's autosave answered without saving. B had exactly that: the
  session-end reset was the title visit, the launcher's "idle" the second one.
  **Fix:** the driver goes to the title only when the game mode ran since its
  last title visit. Otherwise it keeps an untouched select screen, and restarts
  a used one: the start-VS routine at the select screen refills the VS config,
  and since 1.1.3 the mode manager ends the select mode and builds a new one
  (the restart "in place" of this fix -- the running select mode setting itself
  up again, phase 3 -> 0 -> 3 -- broke the game after 4-11 restarts: "Select
  restarts" below).
- **A reset during a mode change.** An "idle" a few frames after start VS
  found the title with the select mode requested, and the boot state went
  back under the select mode's set-up: NULL reads from then on (offline repro;
  in the dry run's timing it did not happen, in the cycle test it did). Now
  the reset acts only when no mode change is pending (`next` = 14), and the
  copy is put back on the settled title right before start VS -- the point at
  boot where it is taken.
- **A game that has played and a fresh one fought apart (Asuka vs Law).**
  Not from this dry run, found by the cycle test: every next match with Asuka
  vs Law on stage 25 desynced (1,641-4,128 of ~2,000-4,400 frames, often
  different winners), rollback and lockstep, on main too (run ff_asu_main:
  `fight_flow_test --flow persistent --fresh-at 2 --chars asu,law,kaz,hei`);
  fresh against fresh and other pairs were fine. Per-frame dumps (runs
  asu_dump, asu_fine): both games equal through the loading, then the played
  one reached the intros 2 frames later, and the sync point -- "the first ring
  reset after a fight start" -- turned out to be "Fight!" itself (phase 17),
  after the intros: each game ran its Fight! frame on a random state with a
  different number of draws and a different clock, and the barrier's reseed
  came only after it. **Fix:** the sync point is the end of the loading proper,
  the first boundary at which the phase word shows 11..17 (`fight_loaded_now()`,
  rollback and lockstep); the intros then run 28 frames in step on both PCs and
  "Fight!" falls on the same frame (runs ff_asu7 / ff_asu7ls: Asuka vs Law
  after a match against a fresh game, 0 mismatching frames in both modes, 3 of
  3 matches each). Also: FIGHT START waits for the first frame the game mode's
  own phase word reaches 7 (it was the first frame the mode manager says
  "game"; a played game was then one set-up frame behind at netplay frame 1),
  and the boot-state copy covers the whole fight-state block
  0x1008E000..0x100A5000 (a played game carries 7.5 KB of leftovers there,
  beyond the four hashed areas: effect and physics tables 0x10099C28..,
  0x1009A018.., 0x100A3E00..; a fresh game has zeros).
- **A rollback into the fight's loading (A's hang).** The intro rule (no input
  from the match start to "Fight!", docs/ROLLBACK.md section 22) looked at
  phases 7..12 only. The first boundary of a session is lockstep frame 0, where
  the game mode has just set the phase word to 2: the dry-run harness's press
  at frame 2 went out (B's frame log: `2 I ... 004080808080`), A had predicted
  neutral, rolled back 9 frames into the first frames of the loading, and the
  loading never finished; the request to leave the fight was never taken.
  Reproduced on main: `tools/rollback_net_test.py --fight 15,14,27,1 --rtt 150
  --env2 T5_NET_SCRIPT=@2:3:0x40` (the joiner presses at frame 2) -- the host
  rolled back 9 frames, its intro never ended, the joiner waited at the end of
  the loading; with the fix the press goes out neutral, 0 rollbacks, the fight
  loads (runs press150_main / press150_f9). Now
  every phase up to 12 is intro while the mode manager is in the game mode
  (`t5_df_game_mode()`), in the rollback loop and for lockstep frame 0's
  sample (`t5_hooks.cpp` `intro_input_now`); select screens (mode 6, phases
  0-5) still take the driver's presses.
- **A fight left after "Fight!" leaves something behind.** A fight whose
  session ended in the loading was first left (mode request 6) only once its
  intros were over: the game ran the intros and the Fight! frame alone. The
  next match against a fresh game then fought apart for its first 200-260
  frames (cycle test cycle 9: Kazuya vs Heihachi, 200; cycle 10: Asuka vs Law,
  261 -- both modes, every time; the final state and winner equal). At Fight!
  the fresh game set the fighters' start fields (+0x414 = 1150.0 from
  0x10084E94, +0x64C) and the played one did not, so P1 stood 12 units off
  until the fighters met. Not in the data section: copying the whole of
  0x10050000..0x100A5000 back to its boot state did not change it (scan:
  `T5_DF_FRESH_SCAN`); leaving at once (main's way) or at the end of the
  loading did (0 mismatching frames). **Fix:** a fight whose session ended is
  left at the first frame of its intros (phase word 11), or at once when the
  session ended later; never in the middle of the loading (loads in flight).
  A hung loading never takes the request (`stuck_check` ends such a game).
  `T5_DF_LEAVE_PHASE=<p>` (leave once the phase word is past p, default 10)
  for comparisons.

Also at a session's end: the rollback loop puts back the present's
min-vblanks word it zeroed at its start (0x106D4D98), and the sound hooks
forget the session (a session that ended inside a re-simulation left them
"re-simulating": every later play call matched against stale entries, the
library tick skipped). A reset or leave that gets nowhere for 60 s
(`T5_DF_STUCK_SECONDS`, 0 = never; since 1.1.2 also at least 20 frames per
second of it, so a game its PC starves is not taken for stuck: "Select stall
after a fight") writes `state.json` `error`/`stuck` and ends
the process with exit code 6; the launcher starts a fresh game for the next
match and says so on the Play tab.

Diagnostics added: `T5_DF_FRESH_LOG=1` (every word the copy changes),
`T5_DF_FRESH_AT=<n>` (put the copy back n frames into the settled title; tests),
`T5_DF_GUARD=addr:len,...` (`T5_DF_GUARD_AT=<frame>`, default the first title:
those pages read-only, the first writer of each logged with its lifted chain),
`T5_DF_FRESH_SCAN=addr:len,...` (at every copy, list the runs of words in those
areas that differ from the boot state; nothing is copied), `T5_DF_LEAVE_PHASE`
(above). A reset or leave that has waited 30 s (half of
`T5_DF_STUCK_SECONDS`) logs the mode manager's words, the mode object, every
semaphore's count and waiters, and each guest thread's last kernel call with
its callers.

**Fixed (latency branch): a hang at the end of a match under heavy rollback.**
A match played to its end, the session ended 13-25 frames after the KO (the
launcher's "idle"), the driver's START skip taken (mode request 6), and the
game mode never finished: mode 4, next 6, phase word 17, the fight music
stopped, the select data never read. `stuck_check` ended the game after 60 s
(exit 6). Seen once in 10 rollback cycles and often with a choppy opponent
(`reset_cycle_test.py --stutter 80`: 4 of 8 cycles). The cause was not the
KO: a read of the game's async reader (ZsAread) completed in a frame that a
rollback then re-simulated. The reader signals completion with a kernel
semaphore that the main thread's reader service takes with a trywait; the
restore put the service back to "busy" but could not give the token back, so
the request stayed "in progress" for good and the loader task waiting on it
never finished -- and the game mode cannot end while a task of its scene is
busy. The rollback loop now saves and restores that semaphore's count with
every boundary (after the loaders are drained). `reset_cycle_test.py
--stutter 80 --cycles 12`: 0 hangs in 13 match ends on S (before: 3 of the
first 4). docs/ROLLBACK.md section 30 has the trail (call traces of the mode
manager, the busy task, the reader) and the one other failure under that
stutter (an abort in NU::File, also seen on main).

**Test:** `tools/reset_cycle_test.py` -- one persistent game S (never
restarted) against a persistent opponent O (started again when a cycle killed
it); every cycle is a match that ends abnormally, S back at neutral by
itself, then the next match against a new session played to its end:

    python tools/reset_cycle_test.py --exe <t5dr.exe> --vfs <game/vfs> --out <dir> [--cycles 10] [--env T5_RB_MODE=off]
        [--start-cycle N]   # begin the schedule (end, point, fighters, stage) at cycle N
        [--stutter MS]      # O suspended for MS every 0.2-0.6 s during the matches

Ends, in turn: `stall` (O suspended, then killed), `kill`, `quit` (O's BYE),
`peer_idle` (O's launcher leaves), `idle` (S's launcher leaves), `no_peer` (no
opponent at all), `desync` (O on another stage, both leave), `normal` (played
out, then "idle" for both, as the launcher ends a match without rematch); each at
the fight's loading, in the fight or at the select screen before FIGHT START,
in turn. A cycle passes when S comes back to neutral, the next match is
confirmed on both sides (same winner and gameplay hash, 0 mismatching frames)
and S's log has no bad guest call, NULL call/read/write, fence queue overflow,
crash or stuck line; the FIFO walker's resyncs are counted apart.

**Results** (this PC, 2026-10-17, runs proof2_rb and proof2_ls): rollback and
lockstep (`T5_RB_MODE=off`) 10 of 10 cycles each in one S process (started
once), every next match confirmed on both sides with the same winner and
gameplay hash and 0 mismatching frames; no bad guest call, NULL access, fence
overflow, crash or stuck line in S's log. S back at neutral after: stall 4.0-4.6
s, kill in the fight 11.4 s (the 10 s session timeout), kill in the loading 14 s,
quit 0.6 s, the peer's idle 4.8 s, its own idle 1.4-1.6 s, no peer 28 s (the
connect timeout), desync 1.8 s, normal end 3.6 s. FIFO walker resyncs (the
walker's own recovery, also in ordinary fights on main): rollback 2 in S over the
10 cycles, lockstep 0. Before the leave fix cycles 9 and 10 failed in both modes
(200 and 261 mismatching frames); before the title fix a second reset with no
fight in between broke the game, as in the dry run. Also: `tests/` 143 OK,
`lobby/tests` 296 OK, the smoke quick suite 81 checks PASS.

**Found 2026-10-19 by the mirror costume probe, fixed in 1.1.3:** the select
screen restarted in place several times in a row without a fight between broke
the game -- see the next section.

## Select restarts (select-restart, 1.1.3)

**The bug.** A persistent game whose sessions end at the select screen without a
fight -- an opponent who leaves during the pick, again and again; matches the
lobby cancels -- broke after the 4th to 11th such session: the main thread wrote
into the null page, the vblank handler's descriptor (OPD 0x4635A8) read zero
(`guest_call: OPD 0x004635A8 -> code 0 not registered` every vblank), NULL calls
in the sound threads; the broken game sat in "connecting" for good. One restart
per process never failed (136 of 136 in the mirror probe).

**Reproduced** with `tools/pick_flow_test.py --offline --aborts 15 --env
T5_DF_SELECT_RESTART=inplace` (the old restart) and with a one-game probe
(fight command, both picks, "idle" at the stage panel): the 4th restart failed
in all 4 runs (the same function and addresses each time), never an earlier
one.

**Cause.** Each "idle" after a used select screen restarted it "in place": the
driver called the start-VS routine `func_0004E9DC(4, 3)` at the select screen.
Its own request for the select mode is dropped by the mode manager while the
select mode is the current one (`0x25D978` returns when cur == the mode asked
for: the probe's mode log shows no mode change and the same `tcb_selectmode_t`
object 0x10629900 before and after). What it did do was make the running
select mode start its set-up again (phase word 0x1008F070 3 -> 0 -> 3): the
set-up (phase 0 of the select's exec 0x5AF04, which creates the scene's tasks)
builds the select scene a second time -- the two fighters' preview models with
their animation and resource managers, portraits, the rest -- and nothing ever
ended the first scene: a call trace of the model code
(`T5_RB_CALLTRACE=2B1F40,...`) showed every earlier restart's models
(0x1042CA10/0x1042D890, then 0x10451150/0x10451FD0, 0x10475890/..., each set
0x24740 above the last) still updated every frame. The scene heap filled up;
in the 4th restart's set-up the model code's allocation (`0x2B1F40` through the
select's update `0x1159AC -> 0x109320 -> 0x2B81E0 -> 0x2ADAB8 -> 0x2B29A0 ->
0x2B1900 -> 0x2B1808`, its node allocator at object +0x10, vtable slot 0x18)
returned NULL, the node was written into the null page (dropped), and
`0x2DBBEC` took a count from it and memset 138 MB from NULL (`0x3AF974`) --
the OPD page and the code image below 0x08481084 cleared, as in the title's
second visit above.

**Fix** (`src/directfight/df_fight.cpp` `select_restart()`, no runtime patch):
the restart is a mode change. After the start-VS routine (VS config, players,
VS counters filled as before) the driver writes the request the manager
dropped into the manager itself, as `0x25D978` would for another mode: next
(+0x5C) = 6, param (+0x64) = 0. The manager then does what it does for every
mode change: it waits until no task of the select scene is busy (loads in
flight), ends the select mode with its whole scene -- the heap goes back -- and
builds a new `tcb_selectmode_t` (prev = 6), which runs its set-up once, like
the one the title's start VS makes. The switch takes 1-2 frames; the select
screen is live again 37-60 frames after the restart, median 44 (in place: 36-37). The trace with the fix:
each restart's models stop being updated at the switch and the next set reuses
their addresses; the mode objects come from the manager's own ring
(0x10629900, 0x1062C780, ... 0x10682880, then back to 0x1062A200). The reset
counts the restart done only once the select mode object changed and went
through phases 0..3 (`g_restart_obj`); when the manager is busy with another
change (never seen) the old in-place restart is the fallback and is logged.
`T5_DF_SELECT_RESTART=inplace` keeps the old way for comparisons.

**Test:** `tools/pick_flow_test.py` (persistent flow; `--offline` for one game
without netplay):

    python tools/pick_flow_test.py --exe <t5dr.exe> --out <dir> --aborts 50 --matches 4 --rematch-every 2 --mash
        [--abort-plan K:N,...]          # N more aborted sessions after match K
        [--abort-how mix|both|host|join] # who leaves (default: in turn)
        [--fresh-after-aborts join]     # match 1 against a freshly started game
        [--offline] [--env T5_RB_MODE=off] [--env T5_DF_SELECT_RESTART=inplace]

Each aborted session is a "fight" command with a new session (new ports, seed,
key; in-game pick) to both games; once the select screen is live the scripted
players move the cursor a few cells (the preview models load), one of them
maybe confirms its pick (never both: the fight must not start), or nothing;
after 0.4-4 s the session ends -- both launchers send "idle", or one game's
does (the other one's session ends with the peer's BYE, its launcher's
"idle" comes 1-2.5 s later). Checked per abort: both games back at neutral,
one more "select screen restarted" in each log, no NULL access, bad guest
call, crash or stuck line. Then the matches as usual: both games fight what was
picked, same winner and state hash, 0 mismatching frames.
`tests/test_select_restart.py` covers the harness's checks and that the
restart stays a mode change.

**Results** (this PC, 2026-10-19, runs in build/selrestart/runs):
- The old restart (`T5_DF_SELECT_RESTART=inplace`, or main): the 4th restart
  broke the game in every run -- the one-game probe 3 of 3, `--offline` (run
  pf_inplace), and a rollback pair (inplace_rb: both games at the same abort,
  `bad_guest_call` + `null_write`).
- The fix, one game, the driver picking both sides and "idle" at the stage
  panel (the mirror probe's way): 60 restarts in a row, no fault (run f1).
- `--offline --aborts 60 --abort-plan 2:10 --matches 4 --rematch-every 2
  --mash` (final_off): 70 of 70 aborted sessions (60 in a row, then a match and
  a rematch, 10 more, a match and a rematch), every select screen restarted,
  4 of 4 matches with a result, no fault line.
- Rollback pair, the same plan, the joiner started again after the first 60
  (`--fresh-after-aborts join`: a game with 60 restarts against a fresh one)
  (final_rb): 70 of 70 aborted sessions in both games, 4 of 4 matches (two of
  them rematches) on both PCs with the same fighters, winner and state hash,
  0 mismatching frames in 28 sync checks, 672 rollbacks (mashing).
- Lockstep pair (`T5_RB_MODE=off`, the host started again after the first 60)
  (final_ls): the same, 70 of 70, 4 of 4, 0 mismatching frames.
- Before the merge with main 1.1.2: rollback pairs pr_rb1 (50 + 4 matches) and
  pr_rb2 (50, fresh joiner, mashing), lockstep pr_ls1 (50 + 4, mashing),
  offline pf_off8 (20 aborts between 6 matches): all OK, 0 mismatching frames.

An aborted session takes 2.2-9 s in the harness (its own random waits
included); the restart itself 37-60 frames. Seen once in these runs and not a
restart: a select screen entered from the title after a fight that stayed at
select phase 1 for good (offline, a heavily loaded PC, pf_off2); the same wait
is in a main-build log without any restart (build/bo3/runs/e3/p2, 42 s) --
the boot-state copy and the game's file reader, fixed in the next section.

## Select stall after a fight (select-stall, 1.1.2)

**The bug.** A select screen that a persistent game opens from the title after a
fight -- a new opponent, a room's Ready again, a set game played again --
sometimes stayed at select phase 1 (the phase word 0x1008F070) for good: offline
on a heavily loaded PC (build/selrestart pf_off2: 4,400+ frames until the run
ended) and in a lobby match of the main build (build/bo3/runs/e3/p2: 46 s until
the next command, then the reset waited in mode 6). The players saw a frozen
character select ("Rematch / character select hangs").

**What phase 1 waits for.** The select mode's exec (0x5AF04, phase table at
0x5B090): phase 0 waits for the scene's resource manager and asks for three
loads (0x275CBC: the portrait/preview resources 61/62, 0x119FF4's, 44); phase 1
waits until those resources are loaded (0x2739F4 -> the resource object's state
+0x48 = 7) and goes to phase 2. Every scene load goes through the game's async
reader (ZsAread): the main thread's reader service (0x9A784, once per frame)
starts the request at the head of its queue (service object 0x1009FE28: +8
busy = 1, posts the reader thread's request semaphore, id at +0), and while busy
takes the reader thread's completion token with a trywait (semaphore id at +4);
requests come from a pool of 64 x 0x28 bytes at 0x1009FF68 (+0 status, +4
next). In both stalls the select had asked for its loads, but no file was ever
opened again: the reader service said "busy" with 5 requests queued, the
reader thread sat parked on its request semaphore, and no completion token
would ever come.

**Cause.** All of the reader's data (0x1009FE20..0x100A0988: thread id, service
object, path buffer, quit flag, request pool, config copy) lies inside the
fight-state block the boot-state copy takes and puts back ("Persistent game":
0x1008E000..0x100A5000). The copy is taken 30 frames into the boot title,
right before the first start VS. The title starts a read there (T55DATA1
entry 0x105, 1.2 MB): on a quiet PC it is done after 30 frames, on a loaded PC
or a slow disk it is not, and the copy then says "busy, the title's request
queued". At the first title visit after a fight the copy goes back while the
reader is idle: the service waits for the completion of a read the reader
thread never got, every later request queues behind it, and the select's
set-up never ends. The reverse (copy idle, put back during a read) drops the
read in flight from the queue and leaves its token to complete the next
request before that one's data is read. Reproduced every time with
`PS3_TEST_FS_DELAY=150` (150 ms per file open/read): the copy logs `reader busy
1, queue 0x1009FF68 (1 request(s))`, the first restore puts that back, the next
select stays at phase 1 with 5 requests queued and 0 tokens (220 s until the run
gave up). A CPU hog alone (3 busy processes on the game's 4 processors) never
caught the read in flight at the copy point; a slow disk does.

**Fix** (`df_fight.cpp`, no runtime patch, no game logic changed):
- The boot-state copy never covers the reader's data (`kReaderData`): the
  default area is split around it (an area from `T5_DF_FRESH_RANGES` too). At an
  idle reader those bytes equal the boot copy's anyway (`T5_DF_FRESH_SCAN` over
  them: no difference after fights), so nothing else the restore does changes.
- The title waits for the reader before the copy is taken or put back and
  before start VS: no request queued or in flight (`reader_idle`), at most 10 s
  from the title's start (then it goes on; safe, the reader is not copied).
  Logged as "waiting for the title's loads before start VS".
- Backstop (`select_load_check`): a select screen still loading (Select, or the
  in-game select's Pick before the screen takes input) whose reader is wedged --
  busy, no completion token, the reader thread parked on its request semaphore
  -- for `T5_DF_SELECT_STUCK_SECONDS` (10), or that has nothing to load (reader
  idle with an empty queue, the reader thread, the "decoder" that inflates what
  was read and TNUD::ASync all parked on their semaphores, phase word and modes
  unchanged) for `T5_DF_STUCK_SECONDS` (60), logs what it waits on and ends the
  game with exit code 6, as a stuck
  reset does (the launcher starts a fresh game for the match; match_driver
  reports `game_stuck`, no strike). A slow load never trips it: the reader
  thread then waits for its data, not for a request, or a loader works (under
  a CPU hog the decoder alone held one select at phase 1 for 30 s with the
  reader idle: S1 cycle 30, before the decoder was part of the rule).
- Stuck exits need frames too (`kStuckMinFps` = 20 frames per second of the
  wait): the checks run at frame boundaries, so a game really stuck in a mode
  change keeps its frame rate, while one its PC starves keeps going slowly
  (select_stall_test O1, the old way under a CPU hog: 0.8-2.7 fps for a minute,
  and the reset's 60 s ended the game in the frame its select screen had loaded).
- `T5_DF_READER_GUARD=0` = the old way (reader copied, no wait), for comparisons;
  the reader's state is in the copy/restore lines and the select's wait lines.

**Test:** `tools/select_stall_test.py` -- one persistent game, offline; every
cycle is a "fight" command for a new session 0.5-4 s after the last FIGHT START,
so the old fight is left in its loading, intros or fight, the game goes to the
title, puts the boot state back and drives a new select screen into the next
fight. A cycle passes at FIGHT START with no fault line; a cycle without one is a
stall (reader, pool and threads dumped through PS3_DEBUG).

    python tools/select_stall_test.py --exe <t5dr.exe> --out <dir> [--cycles 30] [--fs-delay MS]
        [--cpus N --cpu-first K --hog H] [--env K=V] [--keep-going]

**Results** (this PC, 2026-10-19, build/selstall/runs; main merged up to
7486b0c, so with 0047's power saving; 0048 and later main changes leave the game
binary as it was):
- The old way (`T5_DF_READER_GUARD=0`), a slow disk: with 150 ms per read the
  copy caught the title's read every time and the first select after a fight
  stayed at phase 1 (d1: 220 s, then the run gave up; dA2: ended by the backstop
  after 10 s); with 40 ms per read (OLD40 + OLDF, 7 boots, the last on the
  final exe) every boot copy said "busy 1" and every first select after a fight
  wedged -- 7 of 7, each ended by the backstop after 10 s ("the async reader
  waits for a read nobody does", reader busy 1, 5 requests, 0 tokens).
- The old way under a CPU hog only (O1: 3 busy processes on the game's 4
  processors, 30 cycles): no wedge -- the copy and all 27 restores found the
  reader idle; the one failure was the reset's 60 s exit at 0.8-2.7 fps, which
  the frame rule now prevents.
- The fix, 150 ms per read (dB2): 4 of 4 cycles (the title waits for its read
  before the copy; select set-up 2,235-2,263 frames, slow and moving).
- The fix, CPU hog only, power saving on / off (F1 / F0, `PS3_LAPTOP=1/0`): 30 of
  30 cycles each. CPU hog plus a 40 ms disk (S1 / S0): 30 of 30 each, select
  set-up 606-1,144 frames; the boot copy waited for the title's read in each.
  Final exe, the same load with the PC at up to 97 % (other agents' games too,
  the game at 0.1-50 fps): power saving on (P1, R1) 28 of 28 cycles that reached
  their select, power saving off (P0, R0) 35 of 35; two runs counted a cycle as
  failed that was only starved -- P1 cycle 10 (its select done at 1-4 fps as the
  old harness gave up; the harness now waits while anything moves) and R1's
  first boot (0.2-7 fps for 4 minutes, never at the title) -- no stall, no
  STUCK exit in any of them.
- Pairs, every match a new session (title visit and restore before each one),
  mashing, the joiner restarted before match 4 (a game that has played meets a
  fresh one), the joiner's disk at 40 ms per read (its boot copy waited for the
  title's read in both of its starts): rollback with power saving on (FRB) and
  off (QRB, final exe), lockstep with it off (FLS) and on (QLS, final exe): 6 of
  6 matches each, the same winner and result hash on both PCs, 0 mismatching
  frames; also without the slow disk (prb1 rollback, pls1 lockstep on 4
  processors each): 6 of 6 each, in sync.
- After the merge with main bdabaea (replays, 0044 unlock; exe built from
  d4c3a66): rollback pair (ZRB, power saving on) and lockstep pair (ZLS, off),
  slow-disk joiner, fresh joiner before match 4: 6 of 6 each, same hashes, 0
  mismatching frames; offline Z0 (off) 15 of 15, Z1 (on) 9 of 10 -- its cycle 2
  was a select loading at 1-10 fps with the decoder working (13-21 other games
  and 26 compilers on the PC) when the harness's 180 s no-progress limit ran out;
  no STUCK. Smoke on that exe still to rerun on a quieter PC (two runs under
  that load: no-hang gaps / "could not write pad file").
- Smoke quick on the pre-merge final exe: PASS (81 checks; one earlier run failed
  vs_two_pads' end shot -- its mashed fight ended in a KO before the shot, no
  HUD; that test alone and the whole suite again passed).

## Rematches between two real PCs (rematch-fix, 2026-10-18)

"Rematch has never worked" between two PCs (owner, 1.0.0, room "JinFury vs
Wishin": a room match, Ready again, a room match, then Rematch: the control
command came, no FIGHT START followed; then eight "queued flip never reached
by the FIFO walker" lines and the picture gone; the friend quit). On one PC
the dry runs rematched fine. What real players do differently, and what each
did:

- **The rematch keeps the characters, and the two commands come apart.** The
  lobby's rematch is the same two picks; P1's cursor already sits on its
  character, so P1's driver confirms within ~10 frames of its command. A
  persistent game started a rematch only at a "live" select screen, tested as
  *P1's record is still choosing* -- right for a fresh select screen, wrong in
  a rematch, where the peer drives its own player through the exchanged
  input. When P2's command came later than P1's confirm (any real lobby: two
  launchers, two networks), P2's driver never started, P1 waited for P2's
  pick, and both games stayed at the select screen for good. The test flow
  changed the characters every match (the cursor had to travel) and handed
  both commands over within a few frames, so it never got there. Reproduced
  with `tools/fight_flow_test.py --flow persistent --pattern NR --same-chars
  --skew 1.5 --rematch-wait 8` (run e2b: P2's command 85 frames after P1's,
  no FIGHT START on either side for 150 s). **Fix:** the select screen is
  live when the select mode takes input and every record *this PC drives* is
  still choosing (`select_live()` in df_fight.cpp): in a rematch that is the
  own player only; the peer's may be anywhere. Same run with the fix (f1):
  every rematch at FIGHT START 2-3 s after its command on both sides.
- **The frozen picture was a closed window.** "queued flip never reached by
  the FIFO walker" with `get` stuck and `put` moving is what the runtime logs
  when its window is gone: closing the window (Alt+F4, the X button, Esc)
  stopped the FIFO walker and the presents but not the process -- a game
  without a window at about one frame a second, still in its netplay
  session, still "running" for its launcher (reproduced by posting WM_CLOSE:
  the same eight lines). The 0.1.8 folder's log shows a game left running an
  hour after its window was closed; 1.0.0's 19:43 log shows the friend's game
  at one frame a second. Now a closed window ends the game (ps3recomp patch
  0035, `ps3_set_window_closed_handler`); with a netplay session that is a
  quit -- docs/NETPLAY.md "Connection problems".
- **cmd.json could not always be replaced.** The game read cmd.json with a
  plain `fopen`; Windows refuses the launcher's atomic replace while another
  process has the file open without delete sharing, and the harness lost a
  command that way (one in ~20). The game opens it with delete sharing now,
  and the launcher retries the replace (`match_driver.replace_retry`).
- **Under rollback the post-match frames and a rematch's select screen are no
  longer predicted** (docs/ROLLBACK.md section 31): the input after the KO is
  a rule of the game state on both PCs (the same hold and START skip the
  driver did), and the select screen of a rematch runs in lockstep. Both are
  places where the game loads (win pose, result, the select screen's
  portraits and models) through its file request thread. **Not fixed:** a
  rollback across such a load still leaks a file handle now and then, and
  after enough of them the request thread aborts (`abort() is called from
  ... 0x374150`, the game ends with exit code 1) -- with both sides mashing
  buttons, about once in 8 matches of one session; never in lockstep.
  docs/ROLLBACK.md section 31 has what is known.

The driver's own START skip and pad hold stay as they were offline and in
lockstep; under rollback the rule decides the post-match input and the
driver's presses there are ignored.

`tools/fight_flow_test.py` drives these flows: `--pattern NNR` (room match,
Ready again = a new session, Rematch), `--same-chars`, `--skew S`
(`--skew-first host|join|alt|random`), `--stutter MS`, `--hz2 240` (the
joiner's display at 240 Hz: no display lock, the 59.94 Hz clock),
`--close K:ROLE:S` (WM_CLOSE to that game S seconds into match K; the closed
game must end with exit code 7 and "quit", its peer report "peer_quit", and
the next match is a new session against a freshly started game), and it fails
a run on any FIFO stall in the game logs.

Results: see docs/ROLLBACK.md section 31 (the cycle runs).

## Known transient mismatches

**Devil Jin and Mokujin desync online (found by ingame-select, 2026-10-18;
fixed by desync-hunt, docs/NETPLAY.md "Desync hunt").** The in-game select's
test runs picked every character, and two of them went out of sync with or
without the in-game select (Mokujin 4 of 6 lobby-picked matches apart for good
from the first frame after the intros; Devil Jin as P2 4 of 4 for 81-618
frames, xyz points of both fighters). Both came from the title's second random
generator, the main thread's TLS LCG 0x3AFC3C, which was never reseeded: the
game mode's set-up picks Mokujin's copied fighter from it, and the camera and
effects (Devil Jin's) draw from it in the fight. It is now reseeded at every
sync point and pinned to the session seed while the select mode runs -- the
two select screens of the in-game select run for different numbers of frames,
so the pin matters for every picked fight. Nothing of this branch excluded
either character or any hash word for it.

Two kinds of words differed between the two games in the runs of this work;
neither changed the fight (the same hash again afterwards, the same result).

- **Camera-relative copies, 100 frames.** Two 0x128-byte float blocks at
  0x10099770 and 0x10099960 and the counters 0x10090708 / 0x10090FD8 differ
  slightly for exactly 100 frames from lockstep frame 1229 (about 20 s into
  the match), in different fights, then everything is equal again. The source:
  the camera floats around 0x10053780 (not hashed) already differ between the
  two PCs before; at that moment 0x10053590 and these blocks get values from
  them. Main has it too (A/B with two pairs running at once, the same scripted
  match, lockstep: main 3 of 6 runs with 100 mismatching frames, fight-polish
  0 of 6; earlier 2 of ~11 on fight-polish). Since any mismatch voids a ranked
  match, these words are now left out of the state hash (`kDefaultHashSkip`
  in src/netplay/t5_hooks.cpp, `kGameSkip` in src/rollback/rb_state.cpp).
  Since branch cross-cpu the whole camera blocks are left out (0x1F0 bytes
  each from 0x10099730 and 0x10099920, which hold the copies above, and
  8 bytes at each counter): from the final KO camera of Bryan vs Steve
  (stage 28) more of them differed for 21 frames, then all was equal again
  and both results matched -- with identical builds on both sides too, in
  lockstep (1 of 4 runs) and more often under rollback (7 of 9 at RTT 50,
  0 of 2 with `T5_RB_CUT=none`: re-simulated frames skip the draw, which
  adds to it). Camera state that follows timing, not input.
- **Secondary motion.** 0x1008FF00, 0x1008FFB0 and (since cross-cpu)
  0x1008FFF0, 12 bytes each: xyz points a fraction of a unit apart for
  13-20 frames under rollback (Christie vs Feng, stage 17, same build on
  both sides), the fight unchanged.
- **Pool addresses.** 0x100911D0, 0x10091AA0, 0x10091AB8-0x10091B07: addresses
  the animation update takes from a pool at a match intro; they differ when the
  pool's history differs (run ds1, a rematch). Left out of the hash since
  rollback phase 10 (docs/ROLLBACK.md section 20).
- **Boot-mode lockstep menus** (`tools/netplay_test.py --pair`, no direct
  fight): the attract mode's Versus setup block (0x1008EBA8, 0x100996B4..D4)
  one frame apart at frame ~4465-4475, then every frame mismatching -- the known
  menu-transition limit of NETPLAY.md, on main (1 of 3 runs) as on this branch
  (2 of 4). Online play does not go through the menus (direct fight).

## Unlocks (branch unlock-stages, 1.1.2)

Player request: "an option to auto unlock the stages from the base Tekken 5 --
clearing Arcade Mode a few times to unlock them is tedious". Then the owner:
"also unlock all customs". Launcher Settings -> Unlocks: **Unlock all stages**
(`T5_UNLOCK_STAGES=1`) and **Unlock all customization items**
(`T5_UNLOCK_ITEMS=1`), both off by default, offline only. Code:
`src/directfight/df_unlock.cpp` (entry detours, `rb::detour`; installed at
static init in the exe build, at the first frame boundary in the game-DLL build).

**How the game keeps its unlocks** (found by diffing saves before and after
Arcade runs -- the offline-soak agent's arcade saves -- and the lifted code):

- One byte of the system save, SYS-DATA +0x4A (in memory 0x106849AA: the save
  image lives at 0x10684960, 0x218C0 bytes; its "setting" objects at
  0x10684690, this one 0x106848B8). Bits: 0x01 Tekken 5 stages earned, 0x02
  Jinpachi earned, 0x10 / 0x20 the same two **offered** (the title says
  "... now available" once and sets them: 0x2A7358). Earned by the counter at
  SYS-DATA +0x4C (0x2A76F8, one per fight of Arcade, Ghost, VS, Survival:
  game types in the mask 0x353; > 49 -> 0x01, > 99 -> 0x02), Jinpachi also by
  clearing Arcade (0x42FAC). The counter goes up in online fights too.
- Everything that offers them asks 0x2A732C(mask) = (byte & mask) != 0, with
  0x10 or 0x20: the stage tables' availability callbacks (table 0x4410BC, three
  columns per stage id: the old stages 0-13 and 15 are `0x613F8` = check(0x10)
  in two of them, never in the third; ids 14 and 16 are never offered), the
  stage select's OLD/NEW switch (0x1151D0), the random stage picker (0x5C930:
  with 0x10 its 50-bit mask takes the old ids too), the select grid's Jinpachi
  and random cells (0x112F04, 0x58F64: the top row grows from 10 to 12 cells)
  and a select set-up (0x248768). Nothing in a fight calls it
  (`T5_UNLOCK_TRACE=1` logs each caller once with the mode: modes 0, 1 and 6).
- `T5_UNLOCK_STAGES=1` answers 1 for mask 0x10. No guest memory is written:
  the save keeps the player's byte, autosaves write it back unchanged, and the
  setting off is the old game. Checked: the VS stage panel's list (0x1009405C)
  holds 17..34 without it and 0..13, 15, 17..34, 37 with it on a fresh save
  (runs t_on / t_fixed), and PRACTICE's stage select shows NEW STAGE SELECT /
  OLD STAGE SELECT with the same list (run prac1); the save file is not
  rewritten. (Poking the byte
  instead, the first try, went into the save with the title's autosave.)

**Customization items.** The item shop (ITEM SHOP & EQUIP after picking a
fighter in Arcade, Ghost or Survival; `tcb_cusswg_shop_t`) works on each
side's VS custom data, 0x106C9934 + side * 0x1F4: the fighter's three costumes,
0x58 bytes each -- +0x00 32 u16 parts bought (item id in the low byte, in the
order bought), +0x40 4 u16 the parts worn (HEAD, FACE, BODY up, BODY down; -1
none), +0x48 3 u32 colours bought (a bit per colour of COLOR1..3), +0x54 3 u8
the colours worn -- and +0x114 the Fight Money (name +0x134, rank +0x11C).
0x2A77B0(side) builds it at the fighter's confirm from the side's profile
(SYS-DATA +0x400: +8 Fight Money, +0x420 + c * 0x108 the three costumes of
character c in the item numbering, Lili = 0x1F), and the shop writes it back.
Checked by buying with Fight Money poked in (runs shop6, shop9): Lace
Hairband = item 0x33 into +0x00 and worn at +0x40. `T5_UNLOCK_ITEMS=1` makes
every price 0: 0x152A18(character, costume, category, index) tail-calls one
of two price functions -- the lifted code runs a tail call only after the
function returned, so the detours sit on the two: parts 0x152918 (the body of 0x1528F0;
the per-character table *(0x10076724)[c] of {item id, price}) and colours
0x1522C8. The shop then sells everything for 0 G through its own buy path
(bought list, worn slot, Fight Money unchanged; run shop12; Lili wears the
hairband in the Arcade fight after it, run shop13). Answering "bought" from the
shop's checks instead (0x29E754 parts, 0x29E7F4 colours) is not enough: the
shop then shows EQUIPPED and equips nothing, its equip path searches the list
itself (runs shop4, shop8). What is taken for free stays in the save like a
bought item; the launcher copies the save folder to `save-backups/free-items-*`
once before the first game with the setting.

**Online: one answer on both PCs.** The unlocks reach what two netplay games
must agree on whenever the select screens or the stage pickers run in step: in
a lockstep rematch (no in-game select) each PC drives only its own cursor and
the peer replays those presses on its own grid, so a grid with Jinpachi's and
the random cell on one PC puts the same presses on another fighter or costume.
Run ctrl_ls (`--env1 T5_UNLOCK_ONLINE=save`: the host's save has 0x33 and
both settings on, the joiner a fresh save, lockstep, `fight_flow_test --pattern
NRRNR`): match 1 in sync, the first rematch put P2 (Devil Jin) on model 0x43 on
one PC and 0x45 on the other -- 1,327 mismatching frames, different winners.
So a game started for online play (`T5_NET_MODE`, `T5_CTL_DIR`, `T5_FIGHT`,
`T5_FIGHT_FILE`) answers every check as a fresh save does (stages and Jinpachi
not offered), whatever its save and settings; the launcher also leaves the two
settings out of online games. The stage of an online match is the lobby's and
the driver writes it, which works for every stage id with or without the
unlock (the Tekken 5 stages online: docs/RANKED.md "Characters and stages").
With the rule (runs rule_rb / rule_ls: the same pair and pattern, stages 0, 13,
15, 5, 9, the host's save with every unlock and free-bought items, both
settings on; the joiner fresh, both off): 5/5 matches in rollback and 5/5 in
lockstep, 0 mismatching frames, the same hash. `T5_UNLOCK_ONLINE=save` keeps
the old behaviour (tests only).

The Tekken 5 stages themselves in netplay (for the lobby's `T5L_OLD_STAGES`):
every one of them, ids 0-13 and 15, in one persistent session of 15 matches (a
new session, then 14 rematches; 30 different fighters; both players mashing
with motion inputs, 1 round): runs old_rb (rollback) 15/15 and old_ls
(lockstep) 15/15, 28,919 and 29,852 frames, 0 mismatching frames, the same
hash and winner on both PCs.

**The game's own options online (found by the same pair tests).** A
player's save reaches the match through the game's own OPTIONS too: the
start-game routine copies Difficulty (SYS-DATA +4, 0x1008F094), Round Time
(+6, 0x1008F09C, which 0x4E8C0 turns into the round timer 0x1008F054) and +7
(0x1008F098) into the hashed battle state, and 0x1CC28 copies Difficulty again
during the match. A host whose save had EASY / 1 round (an Arcade soak save)
against a fresh save: every compared frame mismatching (run c2: 1,411 of
1,634; desync dumps of opt_dump: 0x1008F094 3 vs 1 and its copy 0x1008F0CC).
Writing the three words after start VS was not enough (0x1CC28). So **an online
game keeps a save of its own**: ps3recomp patch 0044 adds `PS3_SAVEDATA_DIR`
(the save folder; default ./gamedata/...), and the launcher points every game
it starts for online play at `<game folder>/gamedata-online` -- both PCs start
from the same fresh save, and the player's own save is never read or written
by online play. Runs osave_rb / osave_ls (the host's own save the EASY one with
every unlock and both settings, its online save fresh): 3/3 and 3/3, 0
mismatching frames. What a player sets in the game's OPTIONS (button layout,
difficulty, round time, volumes) therefore applies offline only; buttons for
online play are set in the launcher (controls.ini), which works below netplay.

**Customization online today:** none, on either PC: the direct-fight driver
starts VS with 0x4E9DC, not through the VS menu (0x572CC -> 0x1F99BC, which
copies the save's profile for both sides and sets their profile pointers
0x106C9E38[side]); with the pointers at 0, 0x2A77B0 builds no custom data and
both fighters wear their default costumes on both PCs (traced in t_df_items).

**Plan: each player's custom costume online (not in 1.1.2).** Checked by
hand (run cos1, one game): the fight reads its costumes from the VS custom
data -- with no profile, as online, Lili's costume block is zeros; the Lace
Hairband written into it between the select confirm and the fight's loading
(bought list +0x00 and worn HEAD +0x40 of costume 1) is on her in the fight's
intro. So:

1. The launcher reads the player's own save (SYS-DATA, profile +0x400): for
   every character the 0x108-byte costume block at +0x820 + c * 0x108 (only
   the non-empty ones; Fight Money and names stay out) and announces a cap
   `costumes` with its queue/ready message.
2. The lobby server, when both clients have the cap (and a server setting,
   say `T5L_COSTUMES`, allows it; ranked too only if the items are cosmetic),
   sends both players' blocks to both in `match_start` (`fight.costumes`,
   size-checked, at most 35 x 0x108 bytes per player). Both PCs then hold the
   same bytes from the same message: nothing to agree on over the netplay
   link, and locked set games, rematches and the in-game select need nothing
   extra.
3. The launcher writes them to a file named on the fight line; at FIGHT START
   (before `t5_netplay_start()` and the fight's loading) the driver writes,
   for each side, the block of the fighter it fights with (the item
   character index: the fighter object +0x40, as 0x2A77B0 reads it) into that
   side's VS custom data. Both PCs load the same item models for both sides.
4. The VS custom data is outside the netplay hash and does not change during
   a fight; anything the items change in the match (item models, an item
   move) is the same on both PCs. Proof wanted: rollback and lockstep pairs
   with costumes on both sides and mirrors, 0 mismatching frames, frame dumps
   of both PCs showing the same costumes. Still open: whether any item has a
   gameplay effect (T5 item moves) -- it decides ranked, not determinism.

## Character ids

The game's own order (3-letter codes at 0x1001CE58, 8 bytes apart; names at
0x10003F18; the `face_XXX` portrait table at 0x10069824 is in a different,
display order).

| id | code | name | id | code | name | id | code | name |
|---|---|---|---|---|---|---|---|---|
| 0 | pau | Paul | 12 | pan | Panda | 24 | wan | Wang |
| 1 | law | Law | 13 | bry | Bryan | 25 | gan | Ganryu |
| 2 | lei | Lei | 14 | hei | Heihachi | 26 | ask | Asuka |
| 3 | kin | King | 15 | kaz | Kazuya | 27 | bru | Bruce |
| 4 | yos | Yoshimitsu | 16 | lee | Lee | 28 | bae | Baek |
| 5 | nin | Nina | 17 | ste | Steve | 29 | dvj | Devil Jin |
| 6 | hwo | Hwoarang | 18 | mar | Marduk | 30 | rav | Raven |
| 7 | xia | Xiaoyu | 19 | mok | Mokujin | 31 | fen | Feng |
| 8 | cha | Christie | 20 | edd | Eddy | 32 | amk | Armor King |
| 9 | jin | Jin | 21 | jac | Jack-5 | 33 | lil | Lili |
| 10 | jul | Julia | 22 | rog | Roger Jr. | 34 | dra | Dragunov |
| 11 | kum | Kuma | 23 | ann | Anna | 35 | jnp | Jinpachi |

## Stage ids

The stage select lists ids 17-34 (0x11-0x22, the list at 0x1009405C the stage
panel is built from; its random pick lands in 0x1008F088 at the confirm). The
old Tekken 5 stages have the sprite names `stage_1_old` .. `stage_16_old`:
ids 0-13 and 15, offered once unlocked (14 and 16 are empty slots; with the
unlock the panel also lists 37, not tried). See "Unlocks".
Verified by forcing the id and looking at the fight: 20 (scrapyard with
wrecked trucks), 33 (industrial yard). The game's own picks seen in runs: 24,
25, 31, 33. Names for every id are still to be matched to screenshots.

## Determinism and netplay

Both PCs run the same `T5_FIGHT`, so both drive the same cursor path from the
same game state; the frame numbers at which they get there differ with
loading, which is why lockstep starts at the fight, not at boot. At FIGHT START
netplay sets the game's frame counters equal on both sides, clears the input
ring and reseeds the random generators from the match seed. The remaining
boot-time variance is the clock (patch 0012: `PS3_FIXED_TIME=<unix seconds>`
freezes it; the launcher should pass the same value to both players, e.g.
derived from the match seed) and guest memory allocation, which patch 0012
made deterministic for a given call sequence.

Evidence: see the report (build/df/REPORT.md) -- single-instance runs
(characters, stage, round marks, result file, second match), and the
host/join pair started with `T5_NET_START=external`.

## Files

- `src/directfight/df_hooks.cpp`: frame-boundary hook (lv2 sys_semaphore_wait
  on the main thread's per-frame semaphore, installed from the
  `cellSysutilRegisterCallback` HLE override so it never shares a NID with
  netplay's `cellPadInit` override), mode manager finder, pad injection,
  diagnostics.
- `src/directfight/df_fight.cpp`: the match driver described above, the pad
  hold after the KO and through the intros, the HUD identity, the persistent
  game's sessions and boot-state areas.
- `src/directfight/df_ctl.cpp`: the control channel of a persistent game
  (cmd.json / state.json, a small JSON reader, the session environment).
- `src/directfight/df_pick.cpp`: the in-game select's helpers (the local pad
  for the select screen, the name plates as hints, the PICK value, model ids);
  its phases are in `df_fight.cpp`.
- `src/netplay/t5_hooks.cpp`: `t5_netplay_inject(port, on, buttons)` and
  `t5_netplay_enabled()`, `t5_netplay_start()` (netplay's); for a persistent
  game `t5_netplay_session_begin/end`, `t5_netplay_take_session_lost`; for the
  in-game select `t5_netplay_pause()` (resumed by `t5_netplay_start()`);
  `netplay_core.cpp`: `t5_netplay_pick_send/peer` (PICK packets).
- `src/netplay/netplay_core.cpp`: `np::session_begin/end` (the per-session
  state in one struct), the session environment overlay `t5_env*`.
- `src/rollback/rb_net.cpp`, `rb_state.cpp`: `session_reset`, `state_reset`.
- Tests: `tools/pick_flow_test.py` (the in-game select, two games, scripted
  picks; `--aborts`/`--offline`: sessions that end at the select screen, "Select
  restarts"), `tools/fight_flow_test.py` (pairs, many matches, rematch or
  persistent flow, `--mash`, `--fresh-at`), `tools/reset_cycle_test.py` (one
  persistent game through every way a session ends), `tools/dryrun_online.py
  --mode persistent --new-opponent` (through a lobby, Accept-to-FIGHT times),
  `lobby/tests/test_driver_persistent.py`.
