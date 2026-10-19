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
  `LD_SURF_DUMP`/`LD_SURF_DUMP_GATE`), `T5_DF_SCRIPT[2]` (frame scripts, tests),
  `T5_DF_STARTVS=N` (the title-to-select jump alone), `T5_DF_FIND=frame:text,...`
  (log every address of that text, ASCII and UTF-16BE, in guest memory at
  that frame), `T5_DF_FRESH_LOG`, `T5_DF_FRESH_AT`, `T5_DF_GUARD`,
  `T5_DF_STUCK_SECONDS` (persistent game, "After a session ends").

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
4. Match over: 0x1008EBD5 != 0 with wins at 0x1008EBDA/0x1008EBDB (per
   netplay's finding; 0x1008EBD0 is the round counter next to them; the
   tallies stay 0 in direct fights, the winner index 0x1008EBD6 decides).
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
  0x50), Xiaoyu has four (0x10, 0x11, 0x13, 0x14 for LP, LK, RP, RK). Kuma's
  cell gives Kuma with a punch button (model 0x1E) and Panda with a kick button
  (0x1F). The picked model id is at record +0x0C.
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

**Ranked lock.** After the first game of a ranked set the lobby sends no
`pick` (the set's characters are those the first game picked): the select
screen is skipped and the driver picks both sides as in a lobby-picked fight,
on each PC locally (the lockstep is paused there all the same). A fighter that
is the same as in the session's last fight keeps its costume (the lock names
characters only). Whether the set's next game was voted (Rematch) or started
by the lobby on its own, the game gets the same "fight" command in the running
session; one that comes while the win pose still runs waits for the select
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

- **`tools/pick_flow_test.py`** (no lobby; persistent unless noted): 20 of 25
  matches OK across the runs t1, rep1, big_ls, final_rb, proc_rb. The 5 others:
  Devil Jin (big_ls match 6; see "Known transient mismatches"); two short
  mismatches under rollback in final_rb (22 frames Wang vs Heihachi, 1 frame
  Raven vs Asuka, mid-fight, same winner; the same pairs ran clean in
  e2e_room_rb); one hang that was the driver's cursor (from column 11 -- Bruce,
  Kuma -- the top row was never reached; fixed); and in process mode under
  rollback at ~22 fps one game showed "The installed game data is corrupted"
  after a KO (mode 8, the game's end) -- the post-match loads under deep
  rollbacks (depth 9), the known rollback-over-loads problem (ROLLBACK.md 31),
  not the select screen.
- Picks seen: every costume button, Xiaoyu's four costumes, Kuma/Panda,
  random, timeouts on either side, a late pick, mirror matches (P2 gets the
  other costume: logged, not a mismatch).

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
   used one is restarted in place by the same start-VS routine. This happens
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
  a used one in place: the start-VS routine called at a live select screen
  makes the select mode set itself up again (phase 3 -> 0 -> 3, VS config
  refilled, its music restarted; checked 3 times in a row and before a fight).
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
(`T5_DF_STUCK_SECONDS`, 0 = never) writes `state.json` `error`/`stuck` and ends
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

**Devil Jin and Mokujin desync online (found by ingame-select, 2026-10-18; not
fixed).** The in-game select's test runs picked every character, and two of
them went out of sync with or without the in-game select -- the same with
lobby-picked fights as on main (`tools/pick_flow_test.py --no-pick`, lockstep,
`T5_NET_DESYNC_DUMP`):

- **Mokujin**: 4 of 6 lobby-picked matches with Mokujin went apart for good
  (1,122-1,503 mismatching frames, from the first frame after the intros, the
  results differ). Mokujin copies a random fighter's moves each round; that
  choice is not the same on both PCs. Run mok_np.
- **Devil Jin**: as P2 it desynced in 4 of 4 lobby-picked matches (his default
  costume; 81-618 mismatching frames), as P1 in 1 of 8; with his other costume
  in most matches either way. The words that differ are xyz points of his
  fighter block and of the opponent's (+0x368 and +0x6C8 of his block, +0x0,
  +0x580, +0x6D4 of the other one, 0x10099660/70, 0x100A3D34, 0x100A3DEC),
  far into the fight, for 35-600 frames, then equal again; the winner was the
  same every time. Points that follow timing, not input (wings or effects),
  like the camera words below -- but too many and too central to leave out of
  the hash without knowing what reads them. Runs dvj1, dvj2, dvj3, dvj_np.

Either one voids a ranked match today. Next step: find the RNG Mokujin's style
comes from (and seed it from the match seed), and what writes Devil Jin's
points.

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
old Tekken 5 stages have the sprite names `stage_1_old` .. `stage_16_old`.
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
  picks), `tools/fight_flow_test.py` (pairs, many matches, rematch or
  persistent flow, `--mash`, `--fresh-at`), `tools/reset_cycle_test.py` (one
  persistent game through every way a session ends), `tools/dryrun_online.py
  --mode persistent --new-opponent` (through a lobby, Accept-to-FIGHT times),
  `lobby/tests/test_driver_persistent.py`.
