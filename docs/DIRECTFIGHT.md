# Direct fight: boot straight into a VS match

The lobby picks the characters, the game starts in the fight, and it stays
open between matches (like Tekken 6 Native Online). `src/directfight/` is the
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
T5_FIGHT=p1,p2,stage[,rounds][,p1color,p2color][ match=<id>][ names=<n1>|<n2>][ ranks=<r1>|<r2>]   the first match
T5_FIGHT_FILE=<path>                                 the next matches, one line in the same format
T5_NET_RESULT_FILE=<path>                            {"match": id, "winner": 0|1|null, "score": [p1, p2], ...} per match
T5_DF_STATUS_FILE=<path>                             JSON status for the launcher (rewritten on change)
T5_HUD_NAMES=<P1 name>|<P2 name>                     names under the health bars (lobby names, 16 characters)
T5_HUD_RANKS=<P1 tier>,<P2 tier>                     rank badges, 0-36 in the game's order (0 Beginner, 10 1st Dan, ...)
T5_CTL_DIR=<dir>                                     persistent game: every match is a control command (below)
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
- `p1color`, `p2color`: 1 or 2, the costume (the button of the second confirm).
  Unverified beyond costume 1.
- `T5_FIGHT_FILE` is read when the game idles at character select (after a
  match, or from boot when `T5_FIGHT` is not set) and renamed to `<path>.done`
  once consumed. Write it atomically (write to a temp file, rename).
- Status file: `{"state": ..., "frame": N, "match": k, "p1", "p2", "stage",
  "rounds", "last_winner", "last_score"}` with state one of `title`, `select`,
  `stage`, `loading`, `fight`, `over`, `neutral`. `neutral` = at character
  select, waiting for `T5_FIGHT_FILE`. `fight` with `match` = k means match k is
  running.
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
  that frame).

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
   cursor cell, +8 the portrait id under it, +0x20 the state byte (3 choosing,
   9 costume, then 0x15 (P1) / 0x0D (P2) done). The select state 0x1008F070 is
   3 while the screen takes input. The cursor is moved by injected presses
   (closed loop: read the cell, step toward the target cell, re-read; one step
   per 8 frames), CROSS confirms the character, the costume button confirms
   again. When both are done, CROSS confirms the stage panel (every 30 frames
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

| Build | Matches | Next fight started | Mismatching frames |
|---|---|---|---|
| `T5_DF_HOLD=0` (the old behaviour) | 2 | match 2 never started ("fight requested but the game is in mode 4"; the game's own battle) | 1,848 by frame 9599 |
| fix (runs/rm1, ds1, rm2) | 3 + 3 + 3 | every time, 3.0-4.5 s from the line to FIGHT START | 0 in the matches (rm2: the transient 100-frame one of "Known transient mismatches") |

Select grid (cell -> character), measured by walking the cursor and checked
against the screen: cells 0-11 middle row, 12-23 bottom row, 24-34 top row
(column = cell - 24; cell 24, Jinpachi's slot, is skipped by the cursor, so
Jinpachi is not selectable here yet). UP/DOWN cycle top -> middle -> bottom and
skip a row with no cell in that column.

```
top    : --  Eddy Baek Mokujin Feng Raven Asuka DevilJin Ganryu Wang ArmorKing
middle : Anna Marduk Law Hwoarang King Lili Dragunov Heihachi Christie Paul Jack-5 Bruce
bottom : RogerJr Lei Nina Steve Kazuya Xiaoyu Jin Lee Julia Yoshimitsu Bryan Kuma
```

Panda has no cell (Kuma's cell with the alternate confirm button, `T5_DF_ALT_BUTTON`,
default CIRCLE -- unverified).

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
   the netplay session ends (`t5_netplay_session_end`: BYE, socket closed), the
   pads are held, and the driver goes back to the **title** (mode request 1
   through the game's own 0x25DA54, from a live select screen; from the win
   pose it first skips it as above) and calls the start-VS routine again, as at
   boot: a fresh select screen whatever the last opponent left behind (battle
   config, VS counters, cursor positions). This happens while the players
   accept and the lobby punches, so it costs nothing later.
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
4. The result file is written as before. A **rematch** is a "fight" with
   `"rematch": true` (or the same `T5_NET_MODE/PORT/PEER/KEY/SEED`) while the
   session runs: the next match in it, as a `T5_FIGHT_FILE` line in process mode.
5. A session that ends by itself (peer lost, no connection, other build:
   `T5_NET_ON_LOST` does not apply) writes its result file with the reason as
   before, but the game stays open: a fight is left with mode request 6, the
   driver goes back to a fresh select screen, `state.json` says `error` with
   the reason until the next command. Exit codes 3/4/5 are process mode only.

Measured (`tools/fight_flow_test.py --flow persistent`, two games on this PC,
"idle" then "fight" 0.3-1 s apart, both mashing): command to FIGHT START
4.3-6.7 s for a new session (runs ps2/ps3), against ~20 s for a new process;
every match confirmed with equal hashes, 0 mismatching frames. A game that has
played several sessions also meets a freshly started one in sync (run ps4,
`--fresh-at`). Accept-to-FIGHT through the lobby: docs/ONLINE.md.

Limits: `PS3_FIXED_TIME` cannot change after boot (the runtime reads it once);
a persistent game runs on its real clock (no effect on the fight state seen so
far). The rollback loop (`T5_RB_MODE=net`, developer builds) is process mode
only: it is negotiated at boot.

## Known transient mismatches

Two kinds of words differed between the two games in the runs of this work;
neither changed the fight (the same hash again afterwards, the same result).

- **Camera-relative copies, 100 frames.** Two 0x128-byte float blocks at
  0x10099770 and 0x10099960 and the counters 0x10090708 / 0x10090FD8 differ
  slightly for exactly 100 frames from lockstep frame 1229 (about 20 s into
  the match), in different fights, then everything is equal again. The source:
  the camera floats around 0x10053780 (not hashed) already differ between the
  two PCs before; at that moment 0x10053590 and these blocks get values from
  them. Main shows it as often as this branch (A/B with two pairs running at
  once, the same scripted match: main 2 of 5 runs with 100 mismatching frames,
  fight-polish 0 of 5; earlier 2 of ~11 on fight-polish). Since any mismatch
  voids a ranked match, these words are now left out of the state hash
  (`kDefaultHashSkip` in src/netplay/t5_hooks.cpp).
- **Pool addresses.** 0x100911D0, 0x10091AA0, 0x10091AB8-0x10091B07: addresses
  the animation update takes from a pool at a match intro; they differ when the
  pool's history differs (run ds1, a rematch). The rollback10 branch leaves
  them out of the hash (docs/ROLLBACK.md section 20); until that is merged the
  tests here pass the same list in `T5_NET_HASH_SKIP`.

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
- `src/directfight/df_fight.cpp`: the match driver described above.
- `src/netplay/t5_hooks.cpp`: `t5_netplay_inject(port, on, buttons)` and
  `t5_netplay_enabled()` (new), `t5_netplay_start()` (netplay's).
