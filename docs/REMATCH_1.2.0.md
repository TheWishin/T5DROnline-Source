# The rematch question in the game (1.2.0)

After a casual online match the game itself asks **Rematch?**. Each player answers with the controller (or the
keyboard) in the game; the launcher window stays behind. It is on by default when both players have 1.2.0 (launcher,
game and the lobby server); with an older opponent, launcher or server the launcher asks as before.

## What the player sees

A panel over the game picture (the overlay layer of the training tools, `rsx_overlay.c`: drawn into the backbuffer
after the internal-resolution scaling, so it is sharp and the same size at every Internal resolution and window size):

```
 REMATCH?                                          10
 You won.
 Bob is deciding...                (grey; green: "Bob wants a rematch!", red: "Bob does not want a rematch.")
 You want a rematch. Waiting for Bob...           (after your yes)
 [=================================-------------]  (the countdown bar; red for the last 3 s)
 (X) A [Z]  Rematch          (O) B [X]  No thanks
```

- **Cross** (PlayStation) / **A** (Xbox) = Rematch, **Circle** / **B** = No thanks. The keyboard keys are the ones bound
  to Cross and Circle in `controls.ini` (`[keys1]`, default Z and X); the launcher reads them and the game draws them
  as key caps. The PlayStation symbols are drawn by the game (no font has them everywhere).
- **10 seconds** (`T5L_INGAME_REMATCH_SECONDS`), counted down in big digits and a bar.
- The opponent's choice shows as it comes. After your yes, Circle takes it back ("Take it back").
- Both yes: "Rematch! Starting..." and the rematch goes on in the running session (in-game select, fight).
- A no from either side, or the time running out: the reason ("No rematch. Back to the lobby." / "Time is up.")
  for a moment, then the question goes and the launcher comes to the front, as after a declined rematch before.
- The buttons do nothing for the first 0.7 s of a question, and a button already held when it appears counts only
  after it was let go: a player still mashing kicks after the KO does not answer by accident. Directions, punches,
  START and every other button do nothing.
- Pads work while the game window is not the active window (as in a match); the keyboard needs the game window.
- Texts in all 7 languages (the launcher's catalogs). Letters the game's own 5x7 font lacks (accents, Japanese,
  Korean) are drawn from Windows' fonts (Segoe UI, Yu Gothic UI, Malgun Gothic, ...); a text no installed font can
  draw makes the game refuse the question, and the launcher asks instead.

Not in the game (the launcher's question is still there for them, behind the game): **Rematch: swap sides**, Next
game, Block, Leave: too laggy.

## Which matches

Quick matches, challenges, invites and classic rooms (two players), and the rematches of those. Not: ranked sets and
ranked rooms (their next game starts by itself), tournament sets, community rooms (the room picks the next pair),
training rooms (they go back to the select screen by themselves), a casual set that is still running (FT2 and up:
its next game starts by itself; the question comes after the set is decided).

## How it works

Server (`lobby/t5lobby/server/rematch.py`): when both players' clients have the cap `ingame_rematch_v1` and
`T5L_INGAME_REMATCH` is on (default), the match result carries `rematch_ui {v: 1, kind: rematch, policy, timeout,
auto_after, room_mode, actions}` and `rematch_window` = the question's 10 s. The server's deadline is 10 s +
`VOTE_GRACE` (1.5 s), so a yes pressed at 9.9 s still counts on its way; then `rematch {state: expired}` to both.
Votes go through `h_rematch` as before (same checks, `offered` / `declined` to the opponent, `keep` = continue in
the running games). Older clients: no `rematch_ui`, the 20 s window (`T5L_REMATCH_WINDOW`).

Launcher (`lobby/t5lobby/match_driver.py`, "the rematch question in the game"): on a `match_result` with
`rematch_ui` the driver hands the question to the game through `IngameUI` (`lobby/t5lobby/ingame_ui.py`): the
texts (from `tk_tab._ingame_labels`, translated), the actions the server permits now, how long it shows, the
countdown. It follows the lobby's events (`offered`, `declined`, `expired`, `set_end`, `match_start`) and the
game's answers; a vote from the game is the same `client.rematch(...)` the launcher's button sends (one yes and one
no at most per match; the launcher's own bar is answered too: note `ingame_vote`). While the game shows the
question the launcher does not come forward; when the question ends without a rematch it does (note
`ingame_ui_fallback`).

The game (`src/directfight/df_ui.cpp`, `ui_logic.h`): a worker thread reads `ui.json` (every 50 ms; only a new
revision counts), prepares the glyphs, writes the answer (`ui_action.json`) and a heartbeat (`ui_ready.json`: the
revision it shows). The main thread, at the live frame boundary only (never in a re-simulated frame or a replay),
peeks the local player's controller (`t5_local_player_pad_ui`: the port pressed last; patch 0089's
`cellPad_peek_local` uses its own tap reader, patch 0116, so a short press survives a loading frame without
consuming either gameplay reader's presses) and draws the overlay layer 1 (the question wins over the training
overlay while shown). Nothing of it touches guest memory, the exchanged inputs or the netplay session: both games
simulate the same, whatever the players press during the question. The game logs `in-game question shown: rematch
for match ...` and `in-game question answered: accept|decline (match ...)`.

Replays and spectating: the question adds nothing to a recording (it changes no input). 1.2.0 sessions are written as
replay format 7 and guarded live SESSION 3 whether the after-round skip rule is on or off (docs/REPLAYS.md); a rematch
continued in the running session goes on in the same file.

Fallback: if the game does not acknowledge the question within 3 s (`HEALTH_SECONDS`: an older game without the
marker `T5_INGAME_REMATCH`, an overlay that is not ready, a text it cannot draw) or stops answering, the question
goes and the launcher comes forward with its own question (the rest of the window).

## Switches

| Switch | Default | |
|---|---|---|
| `T5L_INGAME_REMATCH` (server) | `1` | `0`: never offered; every launcher asks itself, 20 s |
| `T5L_INGAME_REMATCH_SECONDS` (server) | `10` | the countdown (1-120) |
| `T5L_CASUAL_REMATCH_POLICY` (server) | `both_confirm` | `auto_unless_declined`: the rematch starts unless a player declines within `auto_after` (5 s; each launcher sends its own yes then) |
| room setting "Rematch rule" | Both players confirm | the same choice for a classic room |
| `T5_INGAME_REMATCH` (launcher) | on | `0`: this launcher asks in its own window (does not tell the server it can) |
| `T5L_AUTO_SKIP` (server) / `T5_AUTO_SKIP` (launcher) | on | the agreed after-round skip (docs/NETPLAY.md "Automatic skips"): offered, used only when both players ticked the box (off by default); independent of the in-game rematch; `0` = never |
| `T5L_AUTO_SKIP_INTRO` (server) | on | the fighters' intros skipped in every match between two 1.2.0 games (cap `auto_skip_intro_v1`, fight `auto_skip_intro`); `0` = both players press START as before |

## Tests

- Game-free: `tests/c/rematch_ui_test.cpp` (`tests/test_rematch_ui.py`: the menu on a fake pad and clock -- the input
  lock, held buttons, directions while confirming, one action at a time, countdown, parsing), `lobby/tests/
  test_ingame_ui.py` (the channel), `test_driver_ingame_ui.py` (the driver's question: accept, decline, take back,
  opponent's choice, timeout, yes at the last moment, server expiry, refused vote, game that never shows it,
  automatic policy, ranked/old servers/community), `test_tk_ingame_ui.py`, `test_rematch_server.py` (default on, 10 s
  + grace, a yes in the grace counts, training/community excluded, skip rule off without its switch).
- With two real games and a local lobby: `python tools/e2e/run.py --suite ingame [--netcode lockstep] [--replays]`
  (`tools/e2e/e2e_ingame.py`): accept/accept, accept/decline, a yes at 9.2 s, timeout, both mashing buttons from the
  KO through the question (3 matches), a classic room, a relayed match, one launcher switched off.

## Measured

2026-11-03, branch `rematch-ingame-120` (fd213cc9, one real game pair per scenario, local lobby, `--replays`):

| scenario | rollback | lockstep |
|---|---|---|
| accept/accept, then accept/decline (`ingame_rematch_flow`) | PASS, 75 checks | PASS, 75 checks |
| a yes at 9.2 s, then a timeout (`ingame_rematch_timing`) | PASS, 76 | PASS, 76 |
| both mashing from the KO through the question, 3 matches (`ingame_rematch_mash`) | PASS, 120 | PASS, 120 |
| classic room, rematch + Circle stays in the room (`ingame_rematch_room`) | PASS, 71 | PASS, 71 |
| relayed match: the rematch is a new connection, relay again (`ingame_rematch_relay`) | PASS, 62 | PASS, 62 |
| one launcher with `T5_INGAME_REMATCH=0` (`ingame_rematch_off`) | PASS, 51 | PASS, 51 |

28 matches, 0 mismatching frames, the same result hash on both PCs every time; 36 of 36 recorded sessions played back
identical. The local pairs had no network shaping (95 rollbacks in all in the rollback runs). Pictures of the question
in all 7 languages at Lowest (1280x720) and 4K (1920x1080 window): `ingame_rematch_pictures` (build/ only).
