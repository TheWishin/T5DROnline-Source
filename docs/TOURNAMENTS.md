# Tournaments

Community tournaments inside the lobby (from 1.1.3). An organizer creates one, players sign up in the launcher's
Online tab, and at the start time the lobby server builds the bracket, calls each set, and the players play it
like any set in the lobby: the game starts by itself, the results come from the games. The bracket fills in by
itself; the organizer only steps in when something needs a person.

What it needs: a lobby server from 1.1.3 on and launchers from 1.1.3 on. Older launchers keep working against the
new server and see nothing of it. Accounts only: a guest can look, but not sign up or organize.

## Contents

- [For players](#for-players)
- [For organizers](#for-organizers)
- [How a set ends](#how-a-set-ends): the rules
- [Brackets](#brackets): seeding, byes, double elimination, the grand final reset, places
- [Ratings](#ratings)
- [For streamers: the bracket as JSON](#for-streamers-the-bracket-as-json)
- [Server settings](#server-settings)
- [The database and restarts](#the-database-and-restarts)
- [Protocol](#protocol)
- [Code and tests](#code-and-tests)
- [Limits](#limits)

## For players

The **Tournaments** page of the Online tab (next to Friends) lists the server's tournaments: running ones first,
then the ones open for sign-up, then the ones that finished in the last week. Pick one to see its details and its
bracket.

1. **Sign up** while it says *Sign-up*. **Leave** takes you off the list again until it starts.
2. **Check in**, when the tournament has a check-in window (for example "check-in 10 minutes before"): when the
   window opens the tab says so, and only the players who checked in are put in the bracket. Signing up while the
   window is open checks you in at once. A tournament without a window takes everyone who signed up.
3. At the start time the server seeds the players, draws the bracket and calls the first sets. When your set is
   ready, the tab shows **"Your tournament set is ready"**: the tournament, the round ("Winners semi-final",
   "Losers round 2", "Grand final" ...), your opponent and the best-of, with a countdown. The launcher comes to
   the front. Press **Accept** (or **A** on the pad) within **5 minutes**. When you are both in, the game starts
   by itself.
4. The set plays like a casual set with the in-game character select: you pick your fighter in the game before
   every game (you may switch between games), first to 3 rounds per game, and the next game starts by itself a few
   seconds after the last one. First to 2 games (best of 3) or first to 3 (best of 5), as the organizer set it.
5. When the set is decided the bracket moves on, and your next set is called the same way. The tab tells you when
   you are out ("You are out of Friday Cup: place 5."), and everyone gets the champion and their place at the end.

While a set is called for you, or you are playing one, the lobby keeps you out of the queues, rooms, challenges
and invites (and takes you out of a queue when the call comes). Between your sets you may play casual matches;
when your next set is called, finish or leave that match within the no-show time.

**Withdraw** (on the tournament's page while it runs) takes you out of the tournament: a set you are in goes to
your opponent.

## For organizers

Any account can organize, unless the server's owner narrowed it (`T5L_TOUR_ORGANIZERS`, below). On the Tournaments
page: **Create...**, then

| Field | Choices |
|---|---|
| Name | 3-40 characters |
| Format | single or double elimination |
| Sets | first to 2 games (best of 3), first to 3 (best of 5) |
| Starts | in 5 minutes ... in 24 hours, or at a time of day (HH:MM, today or tomorrow); at most 14 days ahead |
| Players at most | 8, 16, 32 or 64 |
| Check-in | none, or 5, 10, 15, 30, 60 minutes before the start |
| Seeding | random, or by rating (the lobby's Glicko-2 rating) |

The tournament is played with the game build of the organizer's launcher; players with another build cannot sign up
(the lobby pairs equal builds only). An organizer runs at most 2 tournaments at once, the server 20.

On the tournament's page the organizer has:

- **Start now**: start before the time (with the players who are in; at least 2).
- **Cancel tournament**: at any time before it is over. Sets being played end without a result.
- Click a set in the bracket, then:
  - **<name> wins**: report the result of a set whose two players are known and that has not been decided --
    called, being played (its games stop counting), or waiting for you after a dispute. On a decided set it
    **overrides** the result, as long as no later set was played from it.
  - **Reset set**: the set is played again from 0-0 (a decided set too, with the same condition), and called again.
  - **Disqualify...**: the player (by name) is out. A set they are in goes to the opponent; later sets they would
    have reached are walkovers for their opponents.

A set **needs the organizer** (the bracket shows "NEEDS THE ORGANIZER", the organizer gets a notice in the tab)
when the two launchers reported different winners (a dispute), or when it ended without a result three times
(below). Report the winner, or reset it.

The server's owner can name accounts that may run every tournament (`T5L_TOUR_ADMINS`): the same buttons on every
tournament, and no limit on how many they run.

## How a set ends

Every game of a set is a lobby match with all the lobby's rules for results (RANKED.md "Results and match
integrity"): both launchers report what their game saw, desyncs are found by the games' state hashes, crashes and
lost connections are told apart. On top, for the set:

| What happens | The set |
|---|---|
| a player wins the games needed | decided: the bracket moves on |
| a player quits a game (closes it, leaves the match) or leaves the set between games -- **also at 0-0** | lost by that player (`forfeit`) |
| a player loses the lobby connection and is not back within 60 s (`T5L_RECONNECT_GRACE`) | lost by that player |
| a game is void by a desync, a draw, too short | that game is played again (at most 2 times per set, `T5L_SET_REPLAYS`) |
| the set ends without a result: a crash, a broken connection nobody is blamed for, a third replay, "Leave: too laggy" | the set is **called again** with the score it had (both accept again) -- at most 2 times (`T5L_TOUR_RETRIES`), then it waits for the organizer |
| the two launchers report different winners (a dispute) | it waits for the organizer |
| a player has not accepted when the no-show time (5 min, `T5L_TOUR_NOSHOW`) is over, or is offline then | a **no-show**: the set is lost and the player is out of the tournament |
| neither accepted | both are out; their next opponents get walkovers |
| both accepted but one is still busy (in another match) another 5 minutes later | the busy one is the no-show |
| a player withdraws or is disqualified | the set goes to the opponent |

Unlike a ranked set there is no character lock: the players pick in the game before every game (casual sets work
the same way). There is no rematch after a tournament set: the next set is called by the bracket.

## Brackets

`lobby/t5lobby/server/bracket.py`, pure logic.

- **Seeding**: random (a seed drawn when the tournament is created, kept in the database), or by rating (the
  accounts' Glicko-2 ratings at the start; ties broken by the same random draw).
- **Size**: the players rounded up to a power of two (5 players: 8 slots). Seed 1 meets seed 8 (16: 1 v 16, 8 v 9,
  ...), and seeds 1 and 2 can only meet in the final. The empty slots are **byes** for the top seeds: they start
  in round 2. Two byes never meet.
- **Single elimination**: one lost set is out. Round names: ... Quarter-final, Semi-final, Final.
- **Double elimination**: a lost set in the winners bracket drops the player into the **losers bracket**; a second
  lost set is out. The losers bracket alternates a round among its own players with a round where the losers of
  the next winners round drop in, in alternating order (so two players do not meet again right away). 8 players:
  winners rounds 1-3, losers rounds 1-4.
- **Grand final**: the winners bracket's champion (side 1) against the losers bracket's (side 2). If the losers'
  side wins, both have lost once and the **reset** (Grand final reset) decides. If the winners' side wins, or the
  grand final went by forfeit of a disqualified player, there is no reset.
- **Byes and disqualifications** move through the bracket like players: a set with one side empty is a walkover
  (it is not drawn in the first round), the loser of a walkover is "nobody", and so is a disqualified player from
  the moment of the disqualification.
- **Places** as usual: everyone knocked out in the same round shares the place. Single elimination: 1, 2, 3, 3,
  5, 5, 5, 5, 9 ...; double elimination: 1, 2, 3, 4, 5, 5, 7, 7, 9 ... (the grand final's loser is 2nd, the losers
  final's 3rd). Disqualified players get no place.

The page draws the bracket with one column per round, the winners bracket on top, the losers bracket below and the
grand final on the right; a set being played has an orange frame and "LIVE" with its game score, a called set
"CALLED", a set that needs the organizer a red frame.

## Ratings

Tournament sets are **casual**: no rating change; the record counts each set once (win or loss), like a casual
game. With `T5L_TOUR_RATED=1` a tournament set is rated like a ranked set: one Glicko-2 update when it is decided
(not per game), with the anti win-trading cap and the same-address rule of ranked play (RANKED.md); the setting
applies to the tournaments created while it is on.

## For streamers: the bracket as JSON

The server's status port serves the brackets read-only, with names only (no accounts, no addresses):

```
GET http://127.0.0.1:7780/tournaments            the list: [{id, name, state, format, best_of, start, players, champion, ...}]
GET http://127.0.0.1:7780/tournaments/<id>       one tournament: entrants (name, seed, place), bracket.sets
                                                 ({id, bracket W/L/GF, round, index, p [names], state, live, winner,
                                                 score, reason, wins [the game score while it is played]}),
                                                 standings [{name, place}]
```

The answers allow any origin (`Access-Control-Allow-Origin: *`), so an overlay page in OBS's browser source can read
them, and they are rebuilt at most once a second. The status port listens on 127.0.0.1 only
(`T5L_STATUS_HOST`, `T5L_STATUS_PORT`; HOSTING.md "Status, health, metrics"). To give a streamer the brackets, put a
reverse proxy in front that passes `/tournaments` only, for example with Caddy:

```
lobby.example.org:8443 {
    handle /tournaments* {
        reverse_proxy 127.0.0.1:7780
    }
}
```

or let the streamer use an SSH tunnel (`ssh -L 7780:127.0.0.1:7780 user@server`).

## Server settings

All `T5L_*` (server/config.py):

| Variable | Default | |
|---|---|---|
| `T5L_TOUR_ORGANIZERS` | `any` | who may create tournaments: `any` (every account), `none`, or a comma-separated list of account names |
| `T5L_TOUR_ADMINS` | | account names that may run every tournament (start, cancel, report, override, reset, disqualify) |
| `T5L_TOUR_RATED` | `0` | tournament sets change the rating (once per set) |
| `T5L_TOUR_NOSHOW` | `300` | seconds to accept a called set |
| `T5L_TOUR_RETRIES` | `2` | times a set without a result is called again before it waits for the organizer |
| `T5L_TOUR_MAX_OPEN` | `20` | tournaments not finished yet on the server |
| `T5L_TOUR_PER_ORGANIZER` | `2` | ... per organizer |
| `T5L_TOUR_MAX_DAYS` | `14` | how far ahead a tournament may start |
| `T5L_TOUR_KEEP_DAYS` | `7` | finished tournaments stay in the list this long (the database keeps them) |
| `T5L_TOUR_TICK` | `0.5` | seconds between the server's looks at start times and no-show times |

The sets also use the lobby's `T5L_SET_NEXT_SECONDS` (countdown between games), `T5L_SET_REPLAYS`,
`T5L_RECONNECT_GRACE`, `T5L_INGAME_PICK` and the result rules of RANKED.md.

`t5lobby-admin status` has a line `tournaments  1 running, 2 open for sign-up, 3 sets being played`; `/metrics` has
`t5lobby_tournaments_running`, `t5lobby_tournaments_created_total`, `t5lobby_tournaments_finished_total`.

## The database and restarts

Three tables -- `tournaments`, `tour_entrants`, `tour_sets` (one row per bracket set: its sources, players, state,
result and what is going on with it) -- with their own schema version (the `kv` entry `schema.tournaments`): each
step of `tournaments.MIGRATIONS` runs once, in one transaction with its version number, at the server's start. They
are independent of the other numbered upgrades (`store.MIGRATIONS`), so neither renumbers the other. Every change
is written in the same transaction as the rest of what the server does in that moment (store.py `defer_commits`).

A **restart** resumes the tournaments: sign-up and check-in go on (a start time that passed meanwhile starts the
tournament at once), and a running tournament carries on from its bracket. A set that was being played lived in the
last server's memory: its running game is void (`server_restart`, like every match then), and the set is **called
again with the score it had** (from the set's own row in `sets`) -- the players log in again and accept. A set that
was called gets a fresh no-show time. A restart does not count as one of the set's retries.

## Protocol

Clients announce `tournaments` in `hello.caps`; the server lists `tournaments` in `welcome.features` and adds
`welcome.tournaments {noshow, organizers}`. Only clients with the cap get the pushed messages; any logged-in client
may read the list.

| Client -> server | Reply |
|---|---|
| `tour_list` | `tour_list {rows [summary], can_create, rated}` |
| `tour_get` `tournament` | `tour {tournament}`: the summary + `entrants`, `bracket {format, size, rounds, losers_rounds, sets}`, `standings` |
| `tour_create` `name, format, set_wins, start (unix time), max_players, checkin_minutes, seeding` | `tour` |
| `tour_join` / `tour_leave` / `tour_checkin` `tournament` | `tour` |
| `tour_accept` `tournament, set` | `ok` (then `tour_call` with the new state to both) |
| `tour_admin` `tournament, op: start\|cancel\|report\|override\|reset\|dq`, `set`, `winner` (0/1), `score`, `player` | `tour` |

A summary: `id, name, organizer, format, set_wins, best_of, start, starts_in, checkin_minutes, checkin_opens,
max_players, seeding, rated, state (signup|checkin|running|finished|cancelled), players, checked_in, created,
started, ended, champion, reason, rev`, and for the asker `you {entrant, checked_in, seed, dq, place, set, build_ok}`
and `can_manage`.

| Server -> client (cap) | |
|---|---|
| `tour_call` | `tournament {id, name}`, `set {id, bracket, round, index, format, rounds, losers_rounds}`, `best_of`, `wins_needed`, `side`, `score [you, opponent]` (a set called again goes on there), `replay`, `opponent` (brief), `opponent_online`, `deadline` (seconds), `noshow`, `accepted [you, opponent]` |
| `tour_call_end` | `tournament`, `set`, `reason: started \| no_show \| opponent_out \| decided \| reset \| attention \| cancelled` |
| `tour_changed` | `id, rev, state`: fetch it again if it is on screen (sent at most every `T5L_TOUR_TICK`) |
| `tour_notice` | `code: started (seed, players) \| checkin_open \| no_checkin \| dq (reason) \| eliminated (place) \| finished (champion, place) \| cancelled (reason) \| attention (set, why; to the organizer)`, `tournament {id, name}` |

The set's games are ordinary `match_found` (origin `tournament`, then `set`; no ready check), `match_start`,
`match_result` and `set_end` messages; their `set` has `tournament {id, name, set, bracket, round, format, rounds,
losers_rounds}`, and the set machinery's fields (`rated: true` here means "a best-of set", `wins`, `number`,
`next`). A launcher's MatchDriver plays them like a ranked set (`set_next` between games). `match_cancel` has the
reason `organizer` when the organizer decided a set whose game was being set up.

## Code and tests

- `lobby/t5lobby/server/bracket.py` -- the brackets (no I/O)
- `lobby/t5lobby/server/tournaments.py` -- `TourManager` (requests, the tick, persistence, migrations, the JSON
  endpoint) and `TourSet` (the lobby's best-of set with the tournament's rules); `lobby.py` only calls its hooks
- `lobby/t5lobby/tour_client.py` -- the client's calls (mixed into `LobbyClient`, `tournaments=True`)
- `lobby/t5lobby/tk_tour.py`, `tour_text.py` -- the Tournaments page, the bracket canvas, the Create window, the
  call card; every text through `t()` with a German entry
- `lobby/tests/test_tournaments.py` -- brackets (seeding, byes for every size up to 65, double elimination played
  out for 2..65 players with random results, the grand final reset, walkovers after a disqualification, places,
  undoing a set), the server (settings and limits, sign-up and check-in, seeding by rating, calls and no-shows, a
  quit at 0-0, a desync replay, a crash called again with its score, a dispute for the organizer, casual and rated
  sets, report/override/reset/disqualify/withdraw/cancel, a restart in the middle of a set, the migration, the JSON
  endpoint, an older client), four launchers' match drivers with stub games, and **8 stub clients playing a whole
  double-elimination bracket** with a grand final reset on a local lobby (32 games, about 7 s)
- `lobby/tests/test_tk_tour.py` -- the Online tab with withdrawn windows: the list, Sign up, the call card and
  Accept, a set in the tab's game, the bracket on the canvas, the Create window, the organizer's buttons, German

```sh
cd lobby/tests
python ../../tests/ci_unittest.py test_tournaments test_tk_tour
```

## Limits

- No seeding by hand, no swiss or round-robin, no third-place set.
- The organizer cannot add a player after the start or swap two players in the bracket (disqualify and reset are
  the tools).
- Blocks between players do not keep them apart in a bracket (a bracket cannot choose); the organizer can
  disqualify a player who misbehaves.
- No spectating of a set (the JSON endpoint shows the score as it happens).
- Not tried with real games of several real players over the internet yet: the end-to-end runs use the lobby's
  stub clients and stub games on one PC.
