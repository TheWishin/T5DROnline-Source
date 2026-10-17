# Ranked play: accounts, ranks, match integrity, the match flow

What a player does, like Tekken 6 Native Online: open the launcher's **Online**
tab, log in (or play as a guest), pick a character, press **Ranked match**. When
an opponent is found the game starts by itself, the result is reported by
itself, the rank moves, and **Rematch** keeps both games open for the next one.

The lobby (server, NAT traversal, relay, Glicko-2) is described in
[ONLINE.md](ONLINE.md); the netplay layer in [NETPLAY.md](NETPLAY.md). This page
covers what sits on top: accounts, ranks, the rules that keep results honest,
and the glue between the lobby and the game.

## Contents

- [Accounts](#accounts)
- [Ranks](#ranks)
- [Matchmaking](#matchmaking)
- [Characters and stages](#characters-and-stages)
- [Results and match integrity](#results-and-match-integrity)
- [The match flow (glue)](#the-match-flow-glue)
- [Game control channel (persistent game)](#game-control-channel-persistent-game)
- [In-game identity: names and ranks in the HUD](#in-game-identity-names-and-ranks-in-the-hud)
- [What the game side still needs](#what-the-game-side-still-needs)
- [Slow PCs](#slow-pcs)
- [Stick and competitive checklist](#stick-and-competitive-checklist)
- [Server settings](#server-settings)
- [Protocol additions](#protocol-additions)
- [Tests and tools](#tests-and-tools)

## Accounts

| | Guest | Account |
|---|---|---|
| Needs | a name | a name and a password (6-128 characters) |
| Casual: quick match, rooms, challenges | yes | yes |
| Ranked queue, ranked rooms | no (unless the server sets `T5L_GUEST_RANKED`) | yes |
| Rating, rank, history, leaderboard | no (W/L of the session only) | yes |

**Names**: 2-16 characters, letters, digits, space and `_-.[]()!?`, unique without
regard to case (an account's name cannot be used by a guest; a name a guest is
using cannot be registered while that guest is online). Reserved names are
refused for guests and new accounts: admin, moderator, server, system, lobby,
guest, unknown, player, p1, p2, cpu, tekken, namco, bandai, ... compared without
case, spaces and punctuation ("A.d-min" = "admin"), plus anything starting with
admin, moderator, official or t5lobby (`proto.RESERVED_NAMES`).

**Remembered login.** "Remember me" (on by default) makes the server issue a
login token (32 random bytes). The launcher stores only that token -- never the
password -- in `%APPDATA%\T5DROnline\online.json` (per Windows user, outside the
program folder; `T5_ONLINE_DIR` overrides it), one per server. The server keeps
only its SHA-256. The next time the Online tab opens it logs in with the token.
A token lasts 30 days from its last use (`T5L_SESSION_DAYS`). **Log out** asks
whether to forget the saved login; yes ends it on the server too.

**Change password** (old + new): every remembered login of the account ends
(other PCs must log in again); this PC gets a fresh one.

**Recovery without e-mail.** Registration hands out 8 one-time recovery codes
(`ABCD-EFGH-JKMN`, about 59 bits each, stored hashed). The launcher shows them
once with a "Save to a file..." button. **Forgot password...** takes the name,
one code and a new password; each code works once, and all remembered logins
end. Logged in, "New recovery codes..." (needs the password) replaces the set.
Failed attempts share the login lockout (5, then one per minute per address and
per name). Last resort, the server's host:

```sh
python -m t5lobby.server.accounts_admin --db t5lobby.db show NAME
python -m t5lobby.server.accounts_admin --db t5lobby.db reset-password NAME   # prints a one-time password
python -m t5lobby.server.accounts_admin --db t5lobby.db recovery-codes NAME
python -m t5lobby.server.accounts_admin --db t5lobby.db logout-all NAME
```

**No passwords in clear over the internet.** The client refuses to send a
password or a saved-login token over a plain connection unless the server is on
this PC or the local network (loopback, 10/8, 172.16/12, 192.168/16, link-local;
host names are resolved). Over the internet that needs TLS: `tls://host:port`
for a server with a normal certificate, or the server's SHA-256 fingerprint
under **Server certificate...** for a self-signed one (pinned; see ONLINE.md
"Security"). Guests need no credentials and work everywhere. A friend group on
a VPN with public-looking addresses can set `"plain_passwords": true` in
online.json (not recommended).

Taking over: logging in to an account that is already online moves it to the
new connection (the old one is told "logged in from another place"); a match in
progress moves with it.

## Ranks

The tiers are **the game's own ranks**, in the game's order: Tekken 5 DR keeps
one badge sprite per rank in a table in its program (`beginner_b`,
`9th_kyu_b` ... `tekken_lord_b`, each followed by a Japanese variant). Index =
`t5lobby.ranks.RANKS` index, so a tier can be handed to the game's HUD as is.

| Tier | Rank | From rating | | Tier | Rank | From rating |
|---|---|---|---|---|---|---|
| 0 | Beginner | (placement) | | 19 | Warrior | 1880 |
| 1 | 9th Kyu | (floor) | | 20 | Master | 1920 |
| 2 | 8th Kyu | 1150 | | 21 | Virtuoso | 1960 |
| 3 | 7th Kyu | 1200 | | 22 | Champion | 2000 |
| 4 | 6th Kyu | 1250 | | 23 | Lone Wolf | 2040 |
| 5 | 5th Kyu | 1300 | | 24 | Destroyer | 2080 |
| 6 | 4th Kyu | 1350 | | 25 | Berserker | 2120 |
| 7 | 3rd Kyu | 1400 | | 26 | Sage | 2160 |
| 8 | 2nd Kyu | 1440 | | 27 | Legend | 2200 |
| 9 | 1st Kyu | 1480 | | 28 | Fujin | 2240 |
| 10 | 1st Dan | 1520 | | 29 | Raijin | 2280 |
| 11 | 2nd Dan | 1560 | | 30 | Deity | 2320 |
| 12 | 3rd Dan | 1600 | | 31 | Lord of War | 2360 |
| 13 | 4th Dan | 1640 | | 32 | Dragon Lord | 2400 |
| 14 | 5th Dan | 1680 | | 33 | Tekken Lord | 2450 |
| 15 | 6th Dan | 1720 | | 34 | Dark Lord | 2500 |
| 16 | 7th Dan | 1760 | | 35 | Kouryu | 2550 |
| 17 | Shihan | 1800 | | 36 | Kirin | 2600 |
| 18 | Expert | 1840 | | | | |

The rating is Glicko-2 (start 1500, RD 350; ONLINE.md). A new account starts
around 1st Kyu / 1st Dan; 40 points per Dan-level step means a win against an
equal opponent (+10-20 once the rating has settled, much more at first) moves
you noticeably, and the top names stay rare.

- **Placement**: the first 5 ranked matches (`T5L_PLACEMENT`) show "Beginner
  (placement n/5)" -- what the game itself shows for a new profile. After the
  5th the tier is set from the rating, at most 3rd Dan (`T5L_PLACEMENT_CAP`, 12);
  higher has to be earned.
- **Promotion**: as soon as the rating reaches a higher tier's threshold
  (several tiers at once after a big jump). The result line says "PROMOTED to ...".
- **Demotion, with hysteresis**: only when the rating is 30 points
  (`T5L_HYSTERESIS`) below the current tier's threshold, and never in the 3
  matches (`T5L_SHIELD`) after a promotion. The new tier is the highest one
  whose threshold is within 30 points of the rating, so it is not lost again at
  once.
- **Kyu ranks are never lost** (as in the arcade): once at 1st Dan you never drop
  below it; before that, never below your placement tier.
- **Provisional**: while the rating deviation is above 110 (`T5L_PROVISIONAL_RD`)
  the rank shows with a "?" ("2nd Dan?"); RD grows again with inactivity.
- **Leaderboard** order: rating minus twice the deviation (a few matches are
  needed to climb), accounts with at least one ranked match.

Profile (double-click a player): rank, rating +/- RD, provisional/placement,
record, highest rank, leaderboard place, characters (games and wins each, the
most played is the "main"), matches without result caused in the last 24 h,
and the match history (when, result, opponent, both characters, score, rating
change, status and reason).

## Matchmaking

Ranked queue as in ONLINE.md: pairs by rating (window 100 points + 25/s, up to
800) and ping (80 ms + 10/s, up to 400), equal builds only, accounts only.
Rooms may be ranked (`T5L_RANKED_ROOMS=0` turns that off: then only the queue
gives ranked matches). Challenges are always casual.

**Anti win-trading cap**: the same two accounts move each other's rating at
most 10 times per 24 hours (`T5L_PAIR_CAP`); later matches between them are
played as casual (both are told).

## Characters and stages

The player picks a character in the launcher before queueing (or "Random"); it
is shown in the lobby and sent with the queue request. At match start the
server resolves "random" picks and the stage with the match's shared seed, so
both PCs get the same, and sends `fight: {p1, p2, stage, rounds}` in
`match_start`. The launcher turns it into the direct-fight mode's environment
([DIRECTFIGHT.md](DIRECTFIGHT.md)):

    T5_FIGHT=<p1 id>,<p2 id>,<stage id>,<rounds to win>      e.g. 15,14,20,3 = Kazuya vs Heihachi, stage 20, first to 3

Keys ("jin", "s20") are stable; the ids in `lobby/t5lobby/data/fighters.json`
are the game's own (character ids 0-35 in the game's order, stage ids 17-34 of
its stage select; names are known for two stages so far). Not offered: Jinpachi
(no cursor cell in Versus) and Panda (reached through Kuma's cell with another
button, unverified). Rounds: first to 3 (`T5L_ROUNDS`), like Tekken 6 online.
The stage is always resolved by the server: the game's own random pick happens
before lockstep starts and would differ between the two PCs.

## Results and match integrity

Each launcher reports what its game saw. A report (`result` message) carries:

| Field | |
|---|---|
| `winner`, `score` | 0 = P1, 1 = P2, null = draw / no result; rounds won by P1 and P2 |
| `source` | `game` (the game's result file), `manual` (the player answered), `quit` (this player left), `crash` (this player's game died), `disconnect` (this player's game lost the opponent) |
| `desync` | frames on which the two games' state hashes differed (netplay's detector) |
| `hash`, `frames` | the state hash at the end of the match and the frames played, when the game writes them |

The launcher fills these in by itself: the game's result file gives the match
id, winner, score, desync count (from the match's sync point), the state hash of
the deciding frame and the frames played (docs/NETPLAY.md); the game's log adds
the desync count as a cross-check (`DESYNC at frame` / `sync check ... N
mismatching`), a lost opponent (`peer lost (<reason>)`) and crashes (`[CRASH]`,
or an exit code other than 0, 3, 4, 5); a game window closed without a result
is a quit (the tab asks "How did it end?" when it cannot tell).

**Stale results.** A result file is only ever reported for the match it names
(`"match"`): the id comes from `T5_NET_MATCH` for the first match and from the
`match=<id>` the launcher appends to every `T5_FIGHT_FILE` line. A file naming
another match is moved aside (`results/stale-*.json`). When the lobby settles a
match without this side's report (e.g. voided on the opponent's desync report)
the file is moved aside at once (`results/unreported-*.json`), and the start of
a rematch inside the running game clears whatever is left. (QA run r01_ranked:
match 1 was voided on one player's report while the other game was still
fighting it; that game's result for match 1 was then reported as the result of
the rematch.)

How the server decides (`LobbyServer._reconcile` and friends):

| Situation | Status | Rating | Blame |
|---|---|---|---|
| any report has `desync` > 0 | void (`desync`) at once | no | no |
| both report the same winner | **confirmed** (scores compared; differing scores are dropped) | yes | |
| ... but less than 30 s after the match started (`T5L_MIN_MATCH_SECONDS`, server clock) | void (`too_short`) | no | |
| both games report no winner and no round won (a fight left without a result) | void (`no_result`) | no | |
| winners differ, both sent a state hash, hashes equal, exactly one report is from the game | **resolved**: the game's report wins (the other was changed by hand) | yes | |
| winners differ, hashes differ | void (`desync`) | no | |
| winners differ, no evidence | **disputed** (logged, counted per player) | no | |
| a player quits (`leave_match`, closing the game, logging out mid-match) | **forfeit**: a loss | yes | quitter |
| ... within the minimum match length | void (`early_quit`) | no | quitter (strike) |
| a game crashes, the other game finished the match | onesided: the other result stands | yes | |
| a game crashes, the other did not finish | void (`crash`) | no | crasher (strike) |
| both games lost each other (both `disconnect`), or `disconnect` + a result | void (`connection`) | no | no |
| a player's **lobby connection** drops mid-match and does not come back within 60 s (`T5L_RECONNECT_GRACE`) | **forfeit** (`disconnect`), unless the opponent already reported that player as the winner | yes | dropped player |
| only one report within 90 s (`T5L_RESULT_TIMEOUT`), and it names the *other* player as winner | onesided (a report against one's own interest) | yes | |
| only one report claiming the reporter won, the opponent online but silent | void (`no_report`) | no | silent player (strike) |
| only one report, the opponent left the lobby | onesided (`T5L_ACCEPT_ONESIDED`) | yes | |
| nothing at all within 3 h | void (`timeout`) | no | |

**Strikes**: a void with blame is a strike for that account. From the third
strike within 24 hours (`T5L_STRIKE_LIMIT`), further crashes, early quits and
missing reports in ranked matches count as **losses** (`forfeit`, reason
`crash_repeat` ...). The profile shows the count, so friends notice.

**Disconnects.** The launcher reconnects to the lobby by itself (resumes the
session; the game is not touched, it talks to the opponent directly) and the
match carries on. The opponent sees "X lost the lobby connection; waiting 60 s".
Only a player who stays away loses. When the two *games* lose each other, the
netplay layer notices after `T5_NET_TIMEOUT` (20 s from the lobby; shorter
outages just pause the fight), ends the match -- result file with the reason
(`peer_timeout`, `peer_quit`, `peer_stalled`, `peer_restarted`, ...), then the
game closes with exit code 3 -- and the launcher reports `disconnect` with that
reason; the server decides as above. Nobody plays on against an idle opponent.
A game that cannot even connect (no answer, another build, exit codes 4/5) is
reported the same way, with `no_peer` / `build_mismatch` / `rejected`.

**Desyncs** are never repaired and never counted: the two players did not see
the same match. Netplay's detector compares a hash of the match state every
frame; the launcher counts the mismatches from the match's FIGHT START (a
netplay sync point: frame counters, input ring and random seeds are set equal
there), so a select screen that was out of step for a moment before a rematch
does not void a fight that ran in sync. Menu-driven matches (without direct
fight) often desync in the menus under CPU load (NETPLAY.md "Limits") -- those
void.

**Limits, honestly**: results are self-reported by the two launchers. A
modified launcher can lie; the rules above make lying unprofitable where the
evidence allows (state hash, server clock, lobby presence) and visible where it
does not (strikes, disputes, history). Every report, the path, RTT and the
reasons are stored for review. A real referee needs the server to re-simulate
the inputs, which is out of reach for now.

## The match flow (glue)

`lobby/t5lobby/match_driver.py` (`MatchDriver`) sits between `LobbyClient` and
the game; the Online tab feeds it every lobby event and polls it. Same code for
the launcher, `lobby/tools/ranked_session.py` and the tests.

1. **match_found** -- a game left over from the previous opponent is closed
   (process mode) or sent back to idle (persistent mode). A rematch inside the
   running games keeps it.
2. **match_start** -- the game is started with the lobby's environment:
   `T5_NET_MODE/PORT/PEER/DELAY/TIMEOUT/MATCH/ROUNDS/PATH/RTT_MS/SEED/BUILD/KEY`
   (`KEY`: the match's secret from `match_start`, which authenticates the two
   games' packets),
   `T5_NET_RESULT_FILE=<out>\logs\online\result-<first match id>.json`,
   `T5_FIGHT` with `T5_NET_START=external` and `PS3_FIXED_TIME=<the match's
   start time from the server>` (the same frozen clock on both PCs),
   `T5_FIGHT_FILE` and `T5_DF_STATUS_FILE` (next to the result file),
   `T5_HUD_NAMES`, `T5_HUD_RANKS` (see below). The game boots straight into
   the fight. An offline game that is still open is closed first. The tab shows "Ranked match vs X -- Jin
   vs Lili -- ping 23 ms (direct), input delay 3 frames (50 ms)".
3. **During play** the game log is followed for desyncs, a lost opponent and
   crashes.
4. **Result** -- when the result file appears it is read (only if it names
   this match), moved to `logs\online\results\<match id>.json` (so the next
   match in the same process starts clean) and reported with the evidence; a
   file with a `reason` is a `disconnect`. This PC's speed in the match (`fps`)
   goes to the lobby (`perf`, see "Slow PCs") and into online.json. No result
   and the game closed: crash / disconnect / quit as above.
5. **After** -- the game stays open (win pose, then character select, state
   `neutral`). **Rematch** (both within 20 s, `T5L_REMATCH_WINDOW`): when both
   games still run and are connected, the server starts the next match without
   a new connection (`match_start` with `continue: true`); each launcher writes
   the next `T5_FIGHT` line to its game's `T5_FIGHT_FILE` and the same game
   process plays it (characters can be changed in the launcher between
   matches). Otherwise a new connection and a new game.

Two ways to run the game, picked automatically (`game_mode` in online.json
forces one):

- **process** (today's builds): one `t5dr.exe` per opponent, set up from the
  environment at boot; rematches continue in it through `T5_FIGHT_FILE`. A new
  opponent restarts the game (boot straight into the fight, ~20 s).
- **persistent** (builds that understand `T5_CTL_DIR`, detected by looking
  for that string in `t5dr.exe` / `t5dr_game.dll`): the game starts once and
  stays open between opponents; every match is a command (next section).

## Game control channel (persistent game)

Proposal for the remaining step -- a new opponent without restarting the game
(direct fight already keeps the game open for rematches through
`T5_FIGHT_FILE`). Implemented on the launcher side and in
`lobby/tools/stub_game.py`. File based, like the result
file and netplay's pad files, so the game side is a few lines of C:

- The launcher starts the game once with `T5_CTL_DIR=<dir>` (plus
  `T5_HUD_*`), no `T5_NET_*`. The game boots to an idle state (a menu or a
  "waiting for opponent" screen) and writes `<dir>/state.json`.
- Launcher -> game: `<dir>/cmd.json`, replaced atomically (write `.tmp`, rename),
  `seq` increasing:
  ```json
  {"seq": 3, "cmd": "fight", "match": "m1a2b3...", "env": {"T5_NET_MODE": "host", "T5_NET_PORT": "52685",
   "T5_NET_PEER": "1.2.3.4:61234", "T5_NET_DELAY": "3", "...": "...", "T5_FIGHT": "9,33,4,3",
   "T5_NET_RESULT_FILE": "...\\result-m1a2b3.json", "T5_HUD_NAMES": "Kazuya|Lili", "T5_HUD_RANKS": "11,3"}}
  {"seq": 4, "cmd": "idle"}      end the netplay session (free the UDP port), back to waiting
  {"seq": 5, "cmd": "quit"}      exit
  ```
  "fight" = set up netplay from `env` exactly as if those variables had been
  there at boot, load the fight from `T5_FIGHT`, start lockstep
  (`t5_netplay_start()`), write the result file at the end, stay connected
  (a rematch is another "fight" with the same `env`).
- Game -> launcher: `<dir>/state.json`, replaced atomically whenever it changes:
  `{"seq": <last command handled>, "state": "idle|connecting|loading|fight|result|error", "match": ..., "error": ...}`.
- Poll `cmd.json`'s modification time once a second while idle, every 30 frames
  otherwise; ignore a `seq` already handled.

## In-game identity: names and ranks in the HUD

The fight HUD shows the player's name ("Unknown" today) and a rank badge
("Beginner") under each health bar. The launcher passes what the lobby knows:

    T5_HUD_NAMES=<P1 name>|<P2 name>       lobby names, 16 characters at most
    T5_HUD_RANKS=<P1 tier>,<P2 tier>       tiers as above (0 = Beginner, 10 = 1st Dan, ...); guests 0

Findings so far (2026-10-17, a lobby match of the real game, memory dumped at
the start of round 1):

- Both players show "Unknown" and a "Beginner" badge, plus a "PLAYER DATA 0 W 0 L
  0.00 %" bar -- the per-profile record from the save.
- The badge is a sprite picked from the game's rank table (`beginner_b` ...,
  the same order as RANKS), so a rank number per player selects it.
- "Unknown" is not the PSN name: the game reads only `sceNpManagerGetNpId`
  (the runtime answers "PS3Player"), and `PS3_NICKNAME` only feeds
  cellSysutil's nickname. The program's own "UNKNOWN" (0x1001EBE0) is a debug
  state name. At the fight the text exists as UTF-16BE in the HUD's text list
  (0x104EB902, 0x104EB92E, 0x104EB95E, with the "0 W", "0 L", "0.00 %" pieces and
  layout codes `FFF0`-`FFF6`) -- that is the rendered copy. Its source (save
  profile or a text resource from T55DATA) is neither in the program's static
  data (0x10000000-0x1075FFFF) nor in 0x00480000-0x0FFFFFFF (almost all of that
  is unused; dumped at the same moment of another match).
- Next step: dump 0x10760000-0x1FFFFFFF (where the game's own heap must be) at
  character select, find the UTF-16 "Unknown" that
  the text list is built from and the rank number next to it, then write both
  from `T5_HUD_NAMES` / `T5_HUD_RANKS` at fight start. That hook belongs next to
  the direct-fight code (it knows when the fight is set up); until then the
  variables are ignored.

## What the game side still needs

Netplay and direct fight are merged; the launcher uses `T5_FIGHT`,
`T5_NET_START=external`, `PS3_FIXED_TIME`, `T5_FIGHT_FILE` and
`T5_DF_STATUS_FILE` as DIRECTFIGHT.md describes. Still open, in order of value:

1. **A new opponent without restarting the game**: netplay set up again for a
   new peer (port, peer, delay, seed, build) while the game waits at character
   select -- the control channel above, or `T5_FIGHT_FILE` growing the
   `T5_NET_*` values. Until then the launcher restarts the game for a new
   opponent (direct fight makes that ~20 s instead of ~80 s through the menus).
2. HUD hook for `T5_HUD_NAMES` / `T5_HUD_RANKS` (findings above).
3. **netplay** (menu-driven play only): the menus still diverge at ~frame 1590
   under load. Direct fight avoids it.

Done (2026-10-17, branch netplay-hardening): `match`, `desync`, `hash`,
`frames`, `fps` and `reason` in the result file; the boot take-over race (main
loop frame 1 vs 2, then mostly a deadlock) fixed; a lost or restarted opponent,
a missing one and another build end the match with a reason instead of hanging
or playing on alone.

## Slow PCs

Lockstep runs at the slower PC's speed: in the QA run with one game held to one
CPU core (15 fps) both games crawled at 15 fps. So the lobby checks speed before
a match:

- After every online match the launcher takes this PC's own speed from the
  game (`fps` in the result file: frames per second with the time spent waiting
  for the opponent left out; else netplay's `speed:` log line, else the median
  of the runtime's `[fps]` lines), keeps it in online.json and reports it to the
  server (`perf`; again after every login).
- **Ranked**: a PC whose last match ran below `T5L_MIN_FPS` (40) cannot queue
  for ranked or join a ranked room ("this PC ran its last match at 32 fps;
  ranked needs at least 40 ..."). A casual match measures it again.
- **Every match**: when either PC is below `T5L_WARN_FPS` (55), both players get
  a `slow_pc` notice at match found ("Bob's PC ran its last match at 38 fps --
  this match runs at the slower PC's speed"); `brief()` carries `fps`.
- A PC that has never played online has no measure and is not held back.

## Stick and competitive checklist

What a stick (or hitbox) player needs, and where it stands:

- **Controls** -- `controls.ini` next to `t5dr.exe` (sample: `docs/controls.ini`,
  patch 0009): XInput and DirectInput sticks, hitboxes, DS4/DualSense, two local
  players, hot-plug, works while the window is unfocused (`background = 1`).
  Presets for common layouts (`preset = classic | standard | ps ...`); Tekken
  names 1/2/3/4 = LP/RP/LK/RK. **Hitbox SOCD** (`socd =`, patch 0009):
  `neutral` (default: L+R and U+D both cancel), `up` (the hitbox convention:
  L+R = neutral, U+D = up), `last` (last input wins), `off`. `macros = tekken`
  puts 1+2, 3+4, 1+3, 2+4 on the shoulder buttons (B5-B8 on an 8-button stick).
  `latency_log = 1` logs how old the pad samples are when the game reads them.
  Online, this PC's port 1 is what is sent; the opponent arrives over the network.
- **Input delay** -- shown for every match in the Online tab ("input delay 3
  frames (50 ms)"): the lobby picks it from the measured ping
  (`suggest_delay`: same PC / LAN 2, 40 ms ping 3, 100 ms 5). Delay-based for
  now; rollback (ROLLBACK.md) will hide most of it.
- **Display latency** -- play in the game window at native size or "Borderless
  fullscreen" (Settings tab) on the monitor's native refresh; turn on the TV's
  game mode; cable instead of Wi-Fi for the match; close other heavy programs
  (lockstep runs at the slower PC's speed; one instance runs at 60 fps on this
  PC, two on one PC ~35-40).
- **Fair matches** -- same build on both sides (enforced), ranked = similar rank
  and good ping, rematch keeps the connection, quitting = a loss.

What still needs a human with a real stick (not testable here):

- every button and direction of a real stick and a hitbox, in the menus and in a
  fight, both as P1 and P2, through `controls.ini` presets;
- SOCD behaviour on a real hitbox (dashes, crouch-dash, Korean backdash);
- whether 2-3 frames of delay feel acceptable on LAN, and from which ping it
  stops being fun (input display, frame-tight punishes, just-frame moves like
  Electric Wind God Fist);
- stick hot-plug in the middle of a ranked match;
- display lag of the window vs borderless fullscreen with a stick.

## Server settings

New `T5L_*` variables (all in `server/config.py`):

| Variable | Default | |
|---|---|---|
| `T5L_SESSION_DAYS` | 30 | a remembered login lasts this long unused |
| `T5L_RECOVERY_CODES` | 8 | recovery codes per account |
| `T5L_PLACEMENT` / `T5L_PLACEMENT_CAP` | 5 / 12 | placement matches; highest tier they give (3rd Dan) |
| `T5L_HYSTERESIS` / `T5L_SHIELD` | 30 / 3 | demotion margin; matches after a promotion without demotion |
| `T5L_PROVISIONAL_RD` | 110 | above this RD the rank shows "?" |
| `T5L_RECONNECT_GRACE` | 60 | seconds a player who lost the lobby mid-match may come back |
| `T5L_MIN_MATCH_SECONDS` | 30 | shorter matches never count |
| `T5L_STRIKE_LIMIT` | 3 | blamed voids per 24 h before they count as losses |
| `T5L_PAIR_CAP` | 10 | ranked matches per pair of accounts per 24 h |
| `T5L_REMATCH_WINDOW` | 20 | seconds to agree on a rematch |
| `T5L_RANKED_ROOMS` | 1 | rooms may be ranked |
| `T5L_ROUNDS` | 3 | rounds to win (`T5_FIGHT`) |
| `T5L_MIN_FPS` | 40 | a PC whose last match ran slower may not play ranked (0 = off) |
| `T5L_WARN_FPS` | 55 | below this both players are told at match found (0 = off) |

The database upgrades itself (new columns and tables are added on start).

## Protocol additions

Additive (protocol 1; `welcome.features` lists them: ranks, sessions, recovery,
passwd, profile, history, chars, integrity, rematch).

| Client -> server | Reply |
|---|---|
| `login` `mode: register\|account` + `remember` | `login_ok` + `session` (token), + `recovery_codes` after register |
| `login` `mode: session`, `session` | `login_ok` |
| `logout` `forget`, `session` | ends the remembered login |
| `passwd` `old`, `new`, `remember` | `passwd_ok` (+ `session`) |
| `recover` (no login needed) `name`, `code`, `password` | `recovered {name, codes_left}` |
| `recovery_codes` `password` | `recovery_codes {codes}` |
| `set_char` `char`; `queue` + `char` | |
| `profile` `name`, `history`; `history` `name`, `limit`, `offset`; `leaderboard` `limit`, `offset` | `profile {profile}`, `history {rows}`, `leaderboard {rows}` (+ rank, provisional, main, online) |
| `result` + `source`, `desync`, `hash`, `frames`, `reason` | `result_ack` |
| `perf` `fps` (this PC's speed in its last match; re-sent after every login) | -- |
| `rematch` `match`, `accept`, `keep` | `rematch {state: waiting\|accepted, next}` |

Server -> client: players in `lobby_state` and `brief()` carry `tier`, `rank`,
`provisional`, `placement`, `main`, `char`; `match_found` + `you`, `rematch_of`,
`keep`; `match_start` + `fight {p1, p2, stage, rounds}`, `players [brief, brief]`,
`continue`, `rematch_of`, `min_seconds`, `start_time`, `key` (T5_NET_KEY); `brief()` + `fps`;
`match_result` + `reason`, `blame`
(you/opponent), `fight`, `rematch_window`, and `rating` + `rank_before`,
`rank_after`, `event` (placed/promoted/demoted); `rematch {state: offered\|declined}`;
notices `opponent_dropped`, `opponent_back`, `pair_cap`, `slow_pc`. The client adds
`reconnecting` / `reconnected` events.

## Tests and tools

```sh
cd lobby/tests
python -m unittest test_ranked      # ranks, accounts, integrity rules, rematch, driver + stub game
python -m unittest test_tk_tab      # the Online tab: register, saved login, TLS refusal, leaderboard/profile
```

`lobby/tools/ranked_session.py` plays a whole ranked session on one PC through
the launcher's glue: two accounts, characters, ranked queue, punch, both games,
result files, reports, rank changes, rematches in the running games, profile,
history and leaderboard. With the stub game (seconds) or the real game
(`--exe`, scripted input with `--env1/--env2 T5_NET_SCRIPT=...`). `--persistent`
runs the stub in control-channel mode; `--fail-p2 crash|quit|vanish` and
`--env2 T5_STUB_DESYNC=1` exercise the integrity rules.

**Measured on this PC (2026-10-17).** Stub games: a ranked session of three
matches (queue match + two rematches inside the running stub processes) goes
from queue to confirmed results, rating changes, placement (2 matches) and
"placed at 6th Kyu? / 3rd Dan?", profile, history and leaderboard; the same in
persistent (control channel) mode; `--fail-p2 crash` -> void (crash, blamed),
`quit` -> forfeit, `vanish` -> the survivor reports `disconnect`, void
(no_report, blamed), `T5_STUB_DESYNC=1` -> void (desync).

Real game (`t5dr.exe` from main with netplay + direct fight, two instances on
this PC, localhost lobby, `ranked_session.py --exe ... --attacks --rounds 2
--matches 3`, other work's games running alongside, 25-47 fps):

- lobby -> ranked queue -> LAN punch -> both games started by the driver with
  `T5_FIGHT=26,33,23,2`, `T5_NET_START=external`, `PS3_FIXED_TIME` -> both boot
  straight into Asuka vs Lili (`[df] FIGHT START` at frame ~1177) -> lockstep
  from the fight -> `match 1 over` -> both result files -> both launchers
  report -> **confirmed**, ratings 1500 -> 1662 / 1338, placement 1/2.
- **Rematch in the same game processes**: both launchers wrote the next fight
  to `T5_FIGHT_FILE`; the games went back to character select and fought
  again (FIGHT START match 2 at frame 5434, match 3 at 9770). All three matches
  confirmed, `0 mismatching frame(s)` through frame 11,399. After match 2 both
  accounts were placed (Asuka 3rd Dan?, Lili 6th Kyu?); match 3 promoted Asuka
  to 6th Dan. Profile, history (characters, stages, scores, rating changes) and
  leaderboard as expected. Run: `build/rk/e2e7` (local only).
- An earlier pair (`e2e6`) confirmed match 1 the same way; between the matches
  the select screens went out of step for 50 frames (frames 4644-4693, while the
  direct-fight code drives the cursors under lockstep) and the second match,
  whose fight itself stayed in sync, was voided as a desync. Since then the
  driver counts mismatches from FIGHT START (a netplay sync point) only.
- Odd, for direct fight: with rounds 2, match 1 of `e2e7` ended "P1 1 - P2 0".
- Menu-driven play without direct fight (earlier runs): lockstep in sync
  for 13,199 frames once, but three pairs desynced in the menus (frame ~1590,
  and once from frame 0 because the two games took over lockstep at main loop
  frame 1 and 2) -- those matches would be voided; direct fight avoids it.
- Games killed by hand were reported as `crash`, the opponent's netplay timeout
  as `disconnect`; the server voided the match with the crasher blamed, and the
  automatic rematch started a fresh pair of games over a new connection.
