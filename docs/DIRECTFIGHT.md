# Direct fight: boot straight into a VS match

The lobby picks the characters, the game starts in the fight, and it stays
open between matches (like Tekken 6 Native Online). `src/directfight/` is the
in-game half of that: it drives the game's own mode machine and character
select from the frame boundary hook, applies the fight settings where the game
reads them, calls the netplay hook at fight start, reports the result and waits
at character select for the next fight. No ps3recomp change (patch series
unchanged); everything is off unless `T5_FIGHT`, `T5_FIGHT_FILE` or a `T5_DF_*`
variable is set.

All guest addresses are for NPUB30009 v01.00.

## Interface

```
T5_FIGHT=p1,p2,stage[,rounds][,p1color,p2color]      the first match (from boot)
T5_FIGHT_FILE=<path>                                 the next matches, one line in the same format
T5_NET_RESULT_FILE=<path>                            {"winner": 0|1|null, "score": [p1, p2]} per match
T5_DF_STATUS_FILE=<path>                             JSON status for the launcher (rewritten on change)
```

- `p1`, `p2`: character id 0-35, 3-letter code or name prefix (table below).
- `stage`: stage id (table below), or `random` / `-1` for the game's own pick.
- `rounds`: rounds to win, 1-5 (default 3). Written to the game's rounds-to-win
  byte at game-mode entry; the HUD shows that many round marks.
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
- Result file: written by netplay when netplay is on (it already does), by the
  direct-fight code when netplay is off. Winner 0 = P1, 1 = P2, null = draw;
  score = rounds won.
- Netplay: run both games with `T5_NET_START=external` and the same `T5_FIGHT`
  (and the same `PS3_FIXED_TIME`, see Determinism). At the first frame of the
  game mode the direct-fight code calls `t5_netplay_start()`; the next frame is
  lockstep frame 0 on both PCs and the HELLO handshake there is the ready
  barrier. Every later match calls it again (sync point). Menu driving goes
  through `t5_netplay_inject()` (added to `src/netplay/t5_hooks.cpp`) so it
  works while netplay owns the pads; without netplay the module's own
  `cellPadGetData` override injects.
- Diagnostics: `T5_DF_PROBE=1` (mode changes), `T5_DF_TRACE=1` (every injected
  press with the cursor state), `T5_DF_LOG`, `T5_DF_DUMP=frames`,
  `T5_DF_DUMP_RANGES`, `T5_DF_DUMP_MODES=1`, `T5_DF_WATCH=addr,...`,
  `T5_DF_POKE=frame:addr:width:value`, `T5_DF_SHOT=frames` (needs
  `LD_SURF_DUMP`/`LD_SURF_DUMP_GATE`), `T5_DF_SCRIPT[2]` (frame scripts, tests),
  `T5_DF_STARTVS=N` (the title-to-select jump alone).

Timeline on this PC (60 fps, frames counted from the first frame after boot):
title mode at ~900, start-VS call at +30, select mode at ~935, both characters
and costumes confirmed by ~1010 (closed-loop cursor moves every 8 frames),
stage confirm at ~1130, game mode (= FIGHT START, `t5_netplay_start()`) at
~1180, i.e. the fight loads about 20 s after boot instead of ~80 s through the
menus; a second match from the file needs only the select-screen part.

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
   until the select state reaches 4); the stage shown does not matter.
3. First frame in mode 4: rounds to win -> 0x1008EBD4 (u8), stage id ->
   0x1008F088 (the stage confirm writes the panel's pick there; the game-mode
   loader copies it to 0x10053A08 later, so the overwrite wins), then
   `t5_netplay_start()`. This frame is "FIGHT START" in the log/status.
4. Match over: 0x1008EBD5 != 0 with wins at 0x1008EBDA/0x1008EBDB (per
   netplay's finding; 0x1008EBD0 is the round counter next to them). Result
   file, state `over`; the game shows the win pose and returns to character
   select on its own; when the select screen is live again (mode 6, state 3,
   record states 3) the next fight is read from the file or the state is
   `neutral`.

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
