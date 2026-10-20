# Deploying lobby 1.1.3: central server (and the relay node)

The steps to update the production lobby from 1.1.2 to 1.1.3, in order, with the checks after each step and the way
back. Rehearsed end to end on a local copy of both servers on 2026-10-20 (see "What the rehearsal did" at the end):
no command here was run against the real servers. The procedure is the one of [DEPLOY_1.1.2.md](DEPLOY_1.1.2.md),
shorter: the installed admin tool now waits for ranked sets itself, and the relay node needs no update.

| | Central lobby (Nuremberg) | Relay node `usw` (Hillsboro) |
|---|---|---|
| Address | 46.224.146.6 | 5.78.209.228 |
| Runs now | lobby 1.1.2 (since 2026-10-20, schema 1, friends tables) | lobby 1.1.2 relay node |
| Code | `/opt/t5lobby` | `/opt/t5lobby` |
| Installed from | `/opt/src/t5dr-lobby-1.1.2/lobby` (check with `ls /opt/src`) | likewise |
| install.sh options | `--self-signed --firewall none` | `--relay-only --relay-id usw --central 46.224.146.6 --firewall none` |

## In short

1. Copy the 1.1.3 `lobby/` to the central server and check it there, including the database upgrade on a copy.
2. Decide the tournament settings (below) and put them into `/etc/t5lobby/t5lobby.env` if they differ from the defaults.
3. Notice, then **`drain --wait`** (the installed 1.1.2 tool waits for running matches and ranked sets: no hand check).
4. `install.sh` on the central server (it restarts the service: a few seconds).
5. Checks. Players log in again (1.1.2 launchers by themselves with a saved login, 1.1.1 by hand).
6. Only after the owner has **published** 1.1.3: `sudo t5lobby-admin release 1.1.3`.

The relay node runs the same relay code in 1.1.2 and 1.1.3 (`relaynode.py`, `relayctl.py`, `udp.py`, `relays.py`
unchanged): it may stay on 1.1.2. Every mix was rehearsed (central 1.1.2/1.1.3 x node 1.1.2/1.1.3).

Time: 10-20 minutes, most of it the drain. Downtime: the central restart, a few seconds.

## What 1.1.3 changes on the servers

- **Database**: the community tournaments' tables `tournaments`, `tour_entrants`, `tour_sets` and the index
  `tournaments_state`, created at the first start, with their **own schema version** (`kv` key `schema.tournaments` =
  1; `PRAGMA user_version` stays 1). Nothing else in the database changes (rehearsed: every other table identical).
  1.1.2 opens the upgraded database (rehearsed) and ignores the new tables.
- **Community tournaments** (docs/TOURNAMENTS.md): organizers create single/double elimination brackets, the server
  calls the sets, players accept within `T5L_TOUR_NOSHOW` (or are out), sets are best-of sets like ranked sets
  (unrated by default). Kept in the database: a restart resumes them. The status port also serves the brackets as
  JSON (`/tournaments`, `/tournaments/<id>`, names only) for streamers' overlays.
- **Spectating** (docs/SPECTATE.md): friends (and, for room and tournament matches, anybody) watch a live match; one
  player's launcher uploads the session's stream **through the lobby server's TLS connection**; the server keeps it
  from the session's start (memory) and sends it to each spectator.
- **Rooms** (docs/ONLINE.md "Rooms"): community rooms (3-8 players taking turns) and private rooms (password or
  invite code, hidden). Rooms live in the server's memory only (as before): a restart ends them and their codes.
- **Connection fallback** (docs/NETPLAY.md "When Windows Firewall blocks the game"): a direct match whose game heard
  nothing from its opponent moves onto the relay (the best relay for the pair, a regional node included) within
  `T5L_GAME_FALLBACK` seconds. `T5L_RELAY_TIMEOUT` default 6 -> 10 s.
- **Builds**: 1.1.3 games have new build ids (netplay version 4, new runtime patches): 1.1.1/1.1.2 and 1.1.3 players
  are never paired (queue, challenges, rooms, invites, tournaments). Older launchers get no tournament, spectator or
  private-room message; private rooms are left out of their room list (rehearsed with 1.1.1 and 1.1.2 launchers).
- **From this rehearsal** (branch `deploy-rehearsal-113`): a deleted account's id is never given to a new account
  (before: the next registration after deleting the newest account inherited its history, friends, tournament
  entries and a tournament's organizer rights); the env template lists every 1.1.3 setting.

## Settings (`/etc/t5lobby/t5lobby.env`)

`install.sh` keeps the env file, the certificate and the relay secret. **Nothing has to be set for 1.1.3**; the
defaults below apply. Decide the first block before the deploy (owner):

| Setting | Default | Decide / what |
|---|---|---|
| `T5L_TOUR_ORGANIZERS` | `any` | **owner**: who may create tournaments: `any` (every account), `none`, or a comma list of account names. With `any`, throw-away accounts can fill the server's 20 open tournaments (limits below); a list (the owner, trusted community organizers) is the cautious start |
| `T5L_TOUR_ADMINS` | (none) | **owner**: account names that may run every tournament (start, cancel, report, override, reset, disqualify) and are not held by the limits -- at least the owner's account |
| `T5L_TOUR_RATED` | `0` | **owner**: 1 = tournament sets change the rating (once per set, like a ranked set) |
| `T5L_TOUR_NOSHOW` | `300` | seconds to accept a called set; who has not is a no-show (out) |
| `T5L_TOUR_RETRIES` | `2` | a set that ended without a result is called again this often, then waits for the organizer |
| `T5L_TOUR_MAX_OPEN` / `T5L_TOUR_PER_ORGANIZER` | `20` / `2` | open tournaments on the server / per organizer and per internet address |
| `T5L_TOUR_MAX_DAYS` / `T5L_TOUR_KEEP_DAYS` | `14` / `7` | latest start ahead / days a finished one stays listed |
| `T5L_TOUR_BLAMED_VOIDS` | `1` | games of one set a player may void by their own doing (a crash) before the set is lost |
| `T5L_TOUR_TICK` | `0.5` | seconds between looks at start times and no-shows |
| `T5L_TOUR_GET_RATE` / `T5L_TOUR_GET_BURST` | `2` / `10` | bracket requests per second per connection, after a burst |
| `T5L_MAX_SPECTATORS` | `8` | spectators per match |
| `T5L_MAX_STREAMS` | `50` | matches watched at once, whole server |
| `T5L_SPECTATE_BUFFER_KB` | `2048` | a session's stream kept from its start (compressed, ~3 h); memory: up to `T5L_MAX_STREAMS` x this (100 MB; the unit allows 512 MB) |
| `T5L_SPECTATE_RATE_KB` | `16` | KB/s a streamer may upload (a match needs well under 1) |
| `T5L_SPECTATE_IDLE` | `90` | a stream of a finished match with no new data this long ends |
| `T5L_ROOM_MAX_SIZE` | `8` | most players in a community room (2 = no community rooms) |
| `T5L_ROOM_NEXT_SECONDS` | `8` | a community room's pause between a result and its next match |
| `T5L_ROOM_GUESSES` / `T5L_ROOM_GUESS_SECONDS` | `5` / `30` | wrong room passwords / codes a player may try, then one per 30 s (address 2x, room 4x) |
| `T5L_GAME_FALLBACK` | `90` | seconds after a direct match's start in which a silent game may move it onto the relay (0 = off) |
| `T5L_RELAY_TIMEOUT` | `10` | seconds to set up the relay path (1.1.2: 6) |

Keep everything that is there (`T5L_RELAYS`, the TLS paths, `T5L_OLD_STAGES` if set). A setting goes into the env
file as `NAME=value` on its own line; the server reads it at its start (C2 below restarts it anyway).

## Step by step

**PC** = `C:\T5DROnline` (Git Bash), **central** = 46.224.146.6 as root, SSH key as for the 1.1.2 deploy.

### P1. Build the archive (PC)

```sh
git fetch origin
git -c core.autocrlf=false archive --format=tar.gz -o build/lobby_113.tgz REF lobby     # REF: the 1.1.3 commit (tag v1.1.3)
sha256sum build/lobby_113.tgz
scp -i keys/vps_t5lobby build/lobby_113.tgz root@46.224.146.6:/opt/src/
```

### P2. Unpack and check (central; players notice nothing)

```sh
sha256sum /opt/src/lobby_113.tgz
mkdir -p /opt/src/t5dr-lobby-1.1.3 && tar -xzf /opt/src/lobby_113.tgz -C /opt/src/t5dr-lobby-1.1.3
cd /opt/src/t5dr-lobby-1.1.3/lobby
python3 -c "import sys; sys.path.insert(0, '.'); from t5lobby.server import Config, LobbyServer; LobbyServer(Config(db=':memory:')).store.close(); print('code ok')"
# the database upgrade on a copy of today's backup (both upgrades: the store's and the tournaments' own)
sudo t5lobby-admin backup                                   # note "N accounts, M matches"
B=$(ls -t /var/lib/t5lobby/backups/t5lobby-*.db | head -1); install -m 600 "$B" /root/precheck.db
python3 - <<'EOF'
import sys; sys.path.insert(0, ".")
from t5lobby.server import Config, LobbyServer
s = LobbyServer(Config(db="/root/precheck.db", status_port=0))
one = lambda q: s.store.db.execute(q).fetchone()[0]
print("schema", s.store.schema_version(), "| tournaments", s.tours.migrated, "| accounts", one("SELECT COUNT(*) FROM accounts"),
      "| matches", one("SELECT COUNT(*) FROM matches"), "| integrity", one("PRAGMA integrity_check"))
s.store.close()
EOF
rm -f /root/precheck.db /root/precheck.db-wal /root/precheck.db-shm
```

Expect `schema 1 | tournaments [1] | accounts <N> | matches <M> | integrity ok` (rehearsal: `schema 1 |
tournaments [1] | accounts 109 | matches 412 | integrity ok`). Anything else: stop here.

### C1. Notice, 10-15 minutes ahead (central)

```sh
sudo t5lobby-admin notice "Server update at 21:00: about 5 minutes. Matches running then finish first." --minutes 45
```

### C2. Drain, then install (central)

```sh
sudo t5lobby-admin drain --wait 900          # "no match running: restart now" -- it waits for ranked sets too (1.1.2)
sudo t5lobby-admin backup                    # the database exactly as the upgrade finds it
bash /opt/src/t5dr-lobby-1.1.3/lobby/deploy/linux/install.sh --self-signed --firewall none
```

The 1.1.2 tool prints "N match(es) still running, M ranked set(s) not finished" and says "restart now" when both are
0 (rehearsed with 12 players on 1.1.1 and 1.1.2 launchers: 2 min 42 s). `install.sh` keeps the env file and the
certificate, checks the code ("code ok"), restarts `t5lobby` (the tournament tables are made at this start) and waits
for its health check. Rehearsal: up again 9 s after the stop (stop + install + start; on the server only the restart).

### C3. Checks (central)

```sh
systemctl is-active t5lobby
journalctl -u t5lobby --since "-5 min" --no-pager | grep -E "tournament|schema|listening|relay usw|WARNING|ERROR|Traceback"
sudo t5lobby-admin status
curl -s http://127.0.0.1:7780/tournaments | head -5
sudo runuser -u t5lobby -- python3 -c "import sqlite3; c = sqlite3.connect('/var/lib/t5lobby/t5lobby.db'); q = lambda s: c.execute(s).fetchone(); print('schema', q('PRAGMA user_version')[0], 'tournaments', q(\"SELECT value FROM kv WHERE key = 'schema.tournaments'\"), 'accounts', q('SELECT COUNT(*) FROM accounts')[0], 'matches', q('SELECT COUNT(*) FROM matches')[0], 'friends', q('SELECT COUNT(*) FROM friends')[0], 'integrity', q('PRAGMA quick_check')[0])"
stat -c '%a %U:%G %n' /var/lib/t5lobby/t5lobby.db*
```

- The log: `database: tournament schema 1 (tournaments, entrants, bracket sets)` once, `listening: TCP 0.0.0.0:7781
  (TLS)`, `relay usw ... is up`, no ERROR or Traceback.
- `status`: a new line `tournaments 0 running, 0 open for sign-up, 0 sets being played`; `relay usw ... up`;
  accounts as in P2.
- `/tournaments`: `{"tournaments": [], ...}`.
- The database line: `schema 1 tournaments ('1',) accounts <N> matches <M> friends <as before> integrity ok`;
  files `600` (or `640`) `t5lobby:t5lobby`.
- A real login with the owner's launcher (1.1.2: by itself with the saved login).

### N1. The relay node (optional)

No relay code changed. To keep both machines on the same tree, update it in a quiet moment (or during C2's drain,
when no match is relayed):

```sh
# node
sudo t5lobby-admin status                    # "0/100 sessions"
bash /opt/src/t5dr-lobby-1.1.3/lobby/deploy/linux/install.sh --relay-only --relay-id usw --central 46.224.146.6 --firewall none
```

(copy `lobby_113.tgz` there first as in P1/P2.) Checks as in DEPLOY_1.1.2.md N1.

### C4. After the owner has published 1.1.3 (central)

```sh
sudo t5lobby-admin release 1.1.3
```

1.1.1 and 1.1.2 launchers then show `T5DR Online 1.1.3 is out. Players on it cannot play against your 1.1.2: update
the launcher (...)` in their status bar (rehearsed with both); 1.1.3 launchers nothing. Never before the release
is public.

## What players see

- The notice; during the drain "the server restarts for an update in a moment" when they queue, create or join a
  room; then "Lost the lobby connection". 1.1.2 launchers log in again by themselves with a saved login; 1.1.1
  launchers by hand. A 1.1.3 launcher before the server update: no Tournaments, Watch or private rooms ("this server
  has no private rooms"), everything else works (rehearsed).
- Accounts, ratings, history, friends, blocks, remembered logins: unchanged.

## Restarts on 1.1.3 (this deploy's rollback, every later update)

`drain` on a 1.1.3 server holds the new features (rehearsed with a running 4-player tournament, a spectator and a
private community room, then a restart):

- **Tournaments**: no tournament starts, no set is called, a called set does not start, the no-show clocks stand
  still; the sets being played go on to their end and `drain --wait` waits for them (they are saved like ranked
  sets). Rehearsed: both first-round sets ended during the drain, the final was not called; after the restart it was
  called (fresh no-show time), accepted and played. Without a drain (a crash, an emergency) the set being played is
  void and called again with the score it had (rehearsed: final called again, attempt 2).
- **Rooms**: a community room starts no next match during the drain; at the restart every room ends (rooms live in
  memory), including private rooms and their invite codes -- the hosts make them again, a code passed around
  before the restart no longer works.
- **Spectators** keep watching the running match during the drain; its stream ends with the match ("over"); the
  restart ends every stream.
- Before a restart, look at `t5lobby-admin status` (the tournaments line) and the tournament list: a restart in the
  middle of a tournament costs the players of a called set a new accept (5 minutes, or they are out).

## Rollback to 1.1.2

```sh
# central
sudo t5lobby-admin drain --wait 900          # if the server answers: the running tournament sets finish
bash /opt/src/t5dr-lobby-1.1.2/lobby/deploy/linux/install.sh --self-signed --firewall none
journalctl -u t5lobby -n 20 --no-pager
```

- Rehearsed without a drain, in the middle of a tournament final: 1.1.2 started on the 1.1.3 database (tournament
  tables untouched), voided the 8 running matches and 4 open sets (the tournament set among them); 1.1.1, 1.1.2 and
  1.1.3 launchers logged in and played, relayed through a 1.1.3 node too. Back on 1.1.3: the tournament resumed.
- While 1.1.2 runs there are no tournaments, spectators or private rooms; a 1.1.3 launcher says so.
- **Tournaments that should start while 1.1.2 runs start at once when 1.1.3 is back**, with whoever is online then
  (the others become no-shows after 5 minutes). Before a long rollback, tell the organizers (or cancel/re-create
  those tournaments with a T5L_TOUR_ADMINS account once 1.1.3 is back).
- Avoid `delete-user` / `purge-inactive` while 1.1.2 runs: 1.1.2 gives a new account the highest deleted id again
  (the fix is in 1.1.3), and tournament entries and organizer rights are stored by account id.
- Only if the database itself is damaged: restore the backup of C2 (`systemctl stop t5lobby; t5lobby-admin restore
  FILE --yes; systemctl start t5lobby`).

## Risks and findings

1. **Account ids were given twice (fixed in deploy-rehearsal-113).** After `delete-user` or `purge-inactive` of the
   newest account the next registration got its id -- and its match and set history, pair counts, tournament entries
   and the organizer rights of its tournaments (start, cancel, report results). Now the highest id ever used is
   kept (`kv` `accounts.max_id`); tests in `lobby/tests/test_deploy.py`. Still possible while rolled back to 1.1.2
   (see Rollback).
2. **Tournament organizers**: `T5L_TOUR_ORGANIZERS=any` lets every account create tournaments (limits: 20 open, 2
   per organizer and per address). Decide before the deploy (Settings).
3. **Restarts during tournaments** (above): plan updates outside announced tournament times; always drain.
4. **Rooms and invite codes end at every restart** (memory only, unchanged since 1.0; more noticeable now that
   codes are shared).
5. **Spectator streams go through the central server** (TLS, its bandwidth and memory: up to 100 MB at the
   defaults, measured stream 189 bytes for a short stub match; the real game writes a few KB a minute).
6. **The status port serves the tournament brackets** (names, bracket, standings) at `/tournaments` -- it stays on
   127.0.0.1; expose only those paths through a reverse proxy if streamers need them (docs/TOURNAMENTS.md "For
   streamers").
7. **Old and new launchers never meet** (different builds): after the release is public, C4.
8. **Connection fallback** moves a match onto a relay mid-start: the relay node must be up (it is checked every 5 s);
   rehearsed through `usw` with node 1.1.2 and 1.1.3. On this PC every packet is loopback, which the stub game's
   emulated firewall lets through, so the harness asked for the fallback itself (`nat_fallback`); the detection in
   the launcher is covered by `lobby/tests/test_firewall.py`.
9. **Not checked here**: Linux file modes, systemd, ufw (Windows PC); the real game (stub games only).

## What the rehearsal did

On this PC, nothing outside 127.0.0.1 (`build/deployrehearsal113/`, scripts in its `tools/`):

- **Mirror of production**: a central lobby and a relay-only node installed from the v1.1.2 tag with the real
  `install.sh` (`--root` staging), on the synthetic database of the 1.1.2 rehearsal (made by v1.1.1 launchers on
  v1.1.1, upgraded to 1.1.2 -- the way production's was), plus 1.1.2-era data through the v1.1.2 launcher glue: 106
  accounts, 30 friendships (pending and declined requests too), 399 matches, 162 sets, blocks, bans, notices.
- **Baseline on 1.1.2**: 1.1.1, 1.1.2 and 1.1.3 launcher glue (logins, quick, cross-version, relayed through usw,
  friends): 52 checks PASS.
- **Deploy 1, 1.1.2 -> 1.1.3** (integration-113 6fdbee5) with 12 players on 1.1.1 and 1.1.2 launchers playing ranked
  sets and quick matches: notice, drain 2 min 42 s (4 ranked sets waited for), `install.sh`, up after 9 s; three
  new tables, the `kv` tournament schema, everything else identical; the 12 players back 5 s later.
- **Clients on central 1.1.3 + node 1.1.2** (then **node 1.1.3**): logins (password, remembered from older servers,
  guest) for all three versions, quick per version, 40 s in the queue next to another version (never paired),
  challenges and room joins across versions refused, relayed matches through usw for every version, 1.1.2 friends and
  invites on 1.1.3 (a 1.1.2 friend shows "version" on a 1.1.3 list, invites refused), connection fallback onto usw,
  spectating (stream id, a friend watches, the stream arrives through the lobby, ends after the match), a private
  community room (wrong password refused, left out of a 1.1.2 launcher's list, 2 matches in turn), the `release
  1.1.3` notice for 1.1.1 and 1.1.2 launchers only; message audit: 1.1.1 and 1.1.2 launchers only ever got message
  types their own server version sends, no message type with new keys. 60 + 13 + 13 checks PASS (after two harness
  fixes: an account the live players were using, the fallback asked by the harness).
- **Tournament**: a 4-player single elimination with stub games played to its champion (first run); a second one was
  running through deploy 2.
- **Deploy 2, 1.1.3 -> deploy-rehearsal-113** with the tournament (two first-round sets), a spectator and a private
  community room live: drain 3 min 37 s, held the tournament and the room as described in "Restarts on 1.1.3".
- **Rollback**: 1.1.3 -> 1.1.2 without a drain during the tournament final, clients on central 1.1.2 + node 1.1.3
  (25 checks PASS), `delete-user` of the newest accounts and a new registration under 1.1.2 (id given again, as
  expected for 1.1.2), then 1.1.2 -> 1.1.3 again with a drain: the final called again (attempt 2) and played to its
  champion.
- Tests on deploy-rehearsal-113: the lobby suite the CI way (29 modules, one process each) all exit 0, `python -m
  unittest discover -s tests -q` 745 tests OK (10 skipped), `python tools/check_no_game_data.py` exit 0.
