# Deploying lobby 1.1.5: central server (the relay node stays)

The steps to update the production lobby from 1.1.4 to 1.1.5, in order, with the checks after each step and the way
back. The procedure is the one of [DEPLOY_1.1.4.md](DEPLOY_1.1.4.md): 1.1.5 changes no database table and no relay
code, and needs no setting in the env file (the new settings have production defaults). **Not rehearsed on a local
copy of the servers** (see "What was checked"): no command here was run against the real servers.

| | Central lobby (Nuremberg) | Relay node `usw` (Hillsboro) |
|---|---|---|
| Address | 46.224.146.6 | 5.78.209.228 |
| Runs now | lobby 1.1.4 | lobby 1.1.3 relay node (not updated with 1.1.4) |
| Code | `/opt/t5lobby` | `/opt/t5lobby` |
| Installed from | `/opt/src/t5dr-lobby-1.1.4/lobby` (check with `ls /opt/src` before you start) | `/opt/src/t5dr-lobby-1.1.3/lobby` |
| install.sh options | `--self-signed --firewall none` | `--relay-only --relay-id usw --central 46.224.146.6 --firewall none` |

## In short

1. Copy the 1.1.5 `lobby/` to the central server and check it there, including the database on a copy.
2. Notice, then **`drain --wait`** (it waits for running matches and ranked sets).
3. Backup, `install.sh` on the central server (it restarts the service: a few seconds).
4. Checks. Players log in again (launchers by themselves with a saved login).
5. Only after the owner has **published** 1.1.5: `sudo t5lobby-admin release 1.1.5`.

**Update the server before the release is published.** A 1.1.5 launcher logs in to a 1.1.4 server, but training
rooms, the health handicap, the side and stage choices, the stats page, the profile's record and the relay-based
Ping column stay off there. 1.1.4 launchers keep working with the 1.1.5 server. 1.1.4 and 1.1.5 games are never
paired whatever the server runs (the game's code ID changed: CODE_VERSION 7).

The relay node runs the same relay code in 1.1.3, 1.1.4 and 1.1.5 (`relaynode.py`, `relays.py`, `relayctl.py`,
`udp.py`: no difference): it may stay as it is. Time: 10-20 minutes, most of it the drain. Downtime: the restart.

## What 1.1.5 changes on the servers

Files: `lobby/t5lobby/server/{config,lobby,rooms,store}.py` and two new ones, `server/casual.py` (side and stage
choices) and `server/matchrules.py` (training rooms and the handicap). `proto.py`, `admin.py`, `status.py`,
`deploy/` and the relay files are unchanged; `deploy/t5lobby.env.example` does not list the four new settings below.

- **Database: no change.** A fresh database made by the v1.1.4 lobby and one made by this one have the same 39
  objects (tables and indexes, identical SQL), `PRAGMA user_version` 1 and `kv` `schema.tournaments` 2. `store.py`
  only gained two read-only queries (`match_stats`, `community_stats`). Training matches are never saved. A
  rollback needs no database step.
- **Ping** (docs/ONLINE.md, docs/RANKED.md "Measured pairs"): a player's entry in the lobby list carries `relays`,
  their round trips to the regional relays (whole ms, sent again only on a real change), so launchers show the
  shorter way. The server remembers the measured ping and path of every pair that played (memory only, at most
  20,000 pairs, for `T5L_PAIR_PING_DAYS`) and uses it in the queues; `match_found`, `challenged` and `invited` carry
  `ping {ms, kind, known, path}`. Above 150 ms measured ping `match_start` gives both games at least 3 frames of
  input delay, 4 above 250 ms (`T5L_PING_DELAYS`; ranked: the higher of it and `T5L_RANKED_INPUT_DELAY`).
- **Rematches after the relay** (docs/NETPLAY.md "Rematches after the relay"): a rematch after a match on the relay is
  a new connection (`match_found` with `keep: false`) that tries the direct path again; a second failure keeps the
  session on the relay (`T5L_REMATCH_DIRECT`). 1.1.4 launchers need nothing new.
- **Lag check** (docs/RANKED.md "Long waits"): a game that waited `T5L_LAG_WAIT_SHARE` of the match time (at least
  3 s), or ran below 85 % of its PC's speed, gives the verdict `slow` ("This match lagged"); a 1.1.4 launcher (no cap
  `lag_wait`) gets `more_lag` for it.
- **Side and stage choices** (feature `casual_choice`; docs/ONLINE.md "Sides and stages by choice"): the message
  `casual_prefs {side, stage}`, `rematch {swap: true}`, `welcome.casual.stages`. Challenges, invites and rooms only;
  ranked and quick keep the server's sides and a random stage.
- **Stats** (feature `stats`): the message `stats` returns the Online tab's stats page (accounts, players, matches,
  the last 24 hours, every fighter, ranked and casual apart). It reads every counted match, so the server computes it
  at most every 300 s for everybody; it is in the `HEAVY` rate class. The profile has `stats {ranked, casual}`.
- **Training rooms and the health handicap** (cap `match_rules`, features `training` and `handicap`;
  docs/ONLINE.md "Training rooms and the health handicap"): `room_create {training: true}`, `set_life {life}` (30 to
  100 in steps of 10), `match_found` / `match_start.fight` with `training`, `rounds: 1` and `life`. A training match
  ends with status `training`: no winner, no rating, no strike, not saved; **Leave room** ends it at any time. The
  handicap applies to casual matches between two launchers with the cap, never to ranked or tournament matches.
- **Capabilities:** the server now reads the first 32 caps of a client's `hello` (was 16; a 1.1.5 launcher sends
  16, among them the new `lag_wait` and `match_rules`).
- **Builds:** 1.1.5 games have a new code ID: 1.1.4 and 1.1.5 players are never paired (queue, challenges, rooms,
  invites, tournaments). 1.1.4 launchers keep working with the new server.

## Settings (`/etc/t5lobby/t5lobby.env`)

Nothing to add: the defaults are meant for production. `install.sh` keeps the env file, the certificate and the relay
secret. New (all read from `lobby/t5lobby/server/config.py`):

| Setting | Default | What |
|---|---|---|
| `T5L_PING_DELAYS` | `150:3,250:4` | at least this rollback input delay above a measured round trip, `ms:frames` pairs, for both PCs, ranked and casual; `""` = off |
| `T5L_PAIR_PING_DAYS` | `7` | the measured ping of two players who played counts this long for their next estimate (queues, the ping before a match); memory only, gone after a restart |
| `T5L_REMATCH_DIRECT` | `1` | a rematch after a match on the relay tries the direct path again; `0` = stay on the relay |
| `T5L_LAG_WAIT_SHARE` | `0.05` | a game that waited this share of the match time (3 s or more) for the other's inputs makes the lag check say "this match lagged"; `0` = off |

Fixed in the code (no setting): the stats page is computed at most every 300 s (`STATS_SECONDS`), at most 20,000
pairs are remembered (`PAIR_NET_MAX`), 32 caps are read.

## Step by step

**PC** = `C:\T5DROnline` (Git Bash), **central** = 46.224.146.6 as root, SSH key as for the 1.1.4 deploy.

### P1. Build the archive (PC)

```sh
git fetch origin
git -c core.autocrlf=false archive --format=tar.gz -o build/lobby_115.tgz REF lobby     # REF: the 1.1.5 commit (tag v1.1.5)
sha256sum build/lobby_115.tgz
scp -i keys/vps_t5lobby build/lobby_115.tgz root@46.224.146.6:/opt/src/
```

### P2. Unpack and check (central; players notice nothing)

```sh
sha256sum /opt/src/lobby_115.tgz
mkdir -p /opt/src/t5dr-lobby-1.1.5 && tar -xzf /opt/src/lobby_115.tgz -C /opt/src/t5dr-lobby-1.1.5
cd /opt/src/t5dr-lobby-1.1.5/lobby
python3 -c "import sys; sys.path.insert(0, '.'); from t5lobby.server import Config, LobbyServer; LobbyServer(Config(db=':memory:')).store.close(); print('code ok')"
# the new code on a copy of today's backup, and the stats page's query on the real data
sudo t5lobby-admin backup                                   # note "N accounts, M matches"
B=$(ls -t /var/lib/t5lobby/backups/t5lobby-*.db | head -1); install -m 600 "$B" /root/precheck.db
python3 - <<'EOF'
import sys, time; sys.path.insert(0, ".")
from t5lobby.server import Config, LobbyServer
s = LobbyServer(Config(db="/root/precheck.db", status_port=0))
one = lambda q: s.store.db.execute(q).fetchone()[0]
print("schema", s.store.schema_version(), "| tournaments", s.tours.migrated, "| accounts", one("SELECT COUNT(*) FROM accounts"),
      "| matches", one("SELECT COUNT(*) FROM matches"), "| integrity", one("PRAGMA integrity_check"))
t = time.monotonic(); st = s.store.community_stats()
print("stats page:", st["matches"], "counted matches,", st["players"], "players,", len(st["fighters"]), "fighters in",
      round(time.monotonic() - t, 2), "s")
s.store.close()
EOF
rm -f /root/precheck.db /root/precheck.db-wal /root/precheck.db-shm
```

Expect `code ok`, then `schema 1 | tournaments [] | accounts <N> | matches <M> | integrity ok` with N and M as in
the backup (`[]`: the tournaments schema is already 2, nothing to migrate), and a stats line in well under a second.
Anything else: stop here.

### C1. Notice, 10-15 minutes ahead (central)

```sh
sudo t5lobby-admin notice "Server update at 21:00: about 5 minutes. Matches running then finish first." --minutes 45
```

### C2. Drain, back up, install (central)

```sh
sudo t5lobby-admin drain --wait 900          # "no match running: restart now" -- waits for ranked sets and tournament sets too
sudo t5lobby-admin backup                    # the database exactly as the install finds it
bash /opt/src/t5dr-lobby-1.1.5/lobby/deploy/linux/install.sh --self-signed --firewall none
```

`install.sh` keeps the env file and the certificate, checks the code ("code ok"), restarts `t5lobby` and waits for
its health check. Rooms (training rooms too), invite codes, spectator streams and the remembered pair pings end with
the restart (memory only); a running tournament resumes (DEPLOY_1.1.3.md "Restarts on 1.1.3").

### C3. Checks (central)

```sh
systemctl is-active t5lobby
journalctl -u t5lobby --since "-5 min" --no-pager | grep -E "schema|listening|relay usw|WARNING|ERROR|Traceback"
sudo t5lobby-admin status
sudo t5lobby-admin tour-hosts
curl -s http://127.0.0.1:7780/tournaments | head -5
sudo runuser -u t5lobby -- python3 -c "import sqlite3; c = sqlite3.connect('/var/lib/t5lobby/t5lobby.db'); q = lambda s: c.execute(s).fetchone(); print('schema', q('PRAGMA user_version')[0], 'tournaments', q(\"SELECT value FROM kv WHERE key = 'schema.tournaments'\"), 'accounts', q('SELECT COUNT(*) FROM accounts')[0], 'matches', q('SELECT COUNT(*) FROM matches')[0], 'friends', q('SELECT COUNT(*) FROM friends')[0], 'integrity', q('PRAGMA quick_check')[0])"
```

- `active`; the log: `listening: TCP 0.0.0.0:7781 (TLS)`, `relay usw ... is up`, no schema upgrade line (there is
  none), no WARNING, ERROR or Traceback.
- `status` as before the update (accounts and matches as in P2, `relay usw ... up`); `tour-hosts` as before.
- The database line: `schema 1 tournaments ('2',) accounts <N> matches <M> friends <as before> integrity ok`.
- A real login with the owner's 1.1.4 launcher: the Online tab loads as before.
- With a 1.1.5 launcher (a release candidate before publishing): the Online tab shows **Stats** next to the
  Leaderboard with numbers, the profile shows "Played N: ...", the Play online tab has the side, stage and **My
  health (casual)** choices, and **Create room** offers **Training room**.
- If two 1.1.5 launchers are at hand: a training room's fight never KOs and SELECT held for a second ends it; a
  challenge with a side wish shows it to the other player; the found-match card shows a ping and the path.

### N1. The relay node (optional)

No relay code changed since 1.1.3. To keep both machines on the same tree, update it in a quiet moment, as in
DEPLOY_1.1.3.md N1 with `1.1.5` in place of `1.1.3` (copy `lobby_115.tgz` there first as in P1/P2):

```sh
sudo t5lobby-admin status                    # "0/100 sessions"
bash /opt/src/t5dr-lobby-1.1.5/lobby/deploy/linux/install.sh --relay-only --relay-id usw --central 46.224.146.6 --firewall none
```

### C4. After the owner has published 1.1.5 (central)

```sh
sudo t5lobby-admin release 1.1.5
```

Launchers of an older release then show `T5DR Online 1.1.5 is out ... update the launcher` in their status bar,
within a few seconds and at every login; 1.1.5 launchers nothing. `release` alone shows the setting, `release --clear`
ends it. Never before the release is public.

## What players see

- The notice; during the drain "the server restarts for an update in a moment" when they queue, create or join a room;
  then "Lost the lobby connection" and a login again (by themselves with a saved login).
- Accounts, ratings, history, friends, blocks, tournaments, remembered logins: unchanged. Rooms and their codes are
  made again by their hosts. The Ping column's measured values start over (estimates until a pair plays again).
- 1.1.4 launchers: nothing new to see, except the rematch after the relay (it may play direct again), the lag check's
  "more lag" after a match that stood still, and 3-4 frames of input delay in matches above 150 ms.

## Rollback to 1.1.4

```sh
sudo t5lobby-admin drain --wait 900
bash /opt/src/t5dr-lobby-1.1.4/lobby/deploy/linux/install.sh --self-signed --firewall none
journalctl -u t5lobby -n 20 --no-pager
```

- No database step: 1.1.4 opens the database as it is (same schema; no training match was saved). Rooms end at the
  restart, as always.
- Without a drain a tournament set being played is void and called again; plan the update outside announced
  tournament times (DEPLOY_1.1.3.md "Restarts on 1.1.3").
- Settings of 1.1.5 in the env file may stay (1.1.4 ignores settings it does not know). 1.1.5 launchers keep logging
  in, without training rooms, the handicap, the choices and the stats page; they are still paired only with each
  other.
- If `release 1.1.5` was set, clear it: `sudo t5lobby-admin release --clear`.
- Only if the database itself is damaged: restore the backup of C2 (`systemctl stop t5lobby; t5lobby-admin restore
  FILE --yes; systemctl start t5lobby`).

## Risks

1. **More input delay above 150 ms for everybody** (ranked and casual, also between 1.1.4 launchers): the owner's
   choice for smoother far matches. If players report it as worse, `T5L_PING_DELAYS=""` in the env file and a
   restart (after a drain) turns it off.
2. **The stats page reads every counted match**: cached for 300 s, so at most one such query per 5 minutes; P2 times
   it on the real data. If it is slow, the whole lobby waits for it while it runs.
3. **The server must be updated before 1.1.5 is published**, or 1.1.5 players see none of the new online features
   until it is (C4 only after publishing).
4. **Memory only:** rooms, invite codes, spectator streams and the remembered pair pings end at the restart (as
   before; the pair pings are new).
5. **Not checked here**: Linux file modes, systemd, ufw (Windows PC); the real servers; a full two-server rehearsal.

## What was checked

On this PC, nothing outside 127.0.0.1 and nothing against the real servers:

- The diff v1.1.4 .. d43e3e4 (integration-115) of `lobby/` read for schema, relay, env and protocol changes (above);
  `relaynode.py`, `relays.py`, `relayctl.py`, `udp.py`, `proto.py`, `admin.py`, `status.py` and `deploy/` are
  identical to v1.1.4.
- A fresh database made by each version has the same 39 objects with the same SQL, `user_version` 1 and
  `schema.tournaments` 2. A database made by the v1.1.4 lobby opens with this one as in P2 (`tournaments []`,
  `integrity ok`), and the stats query runs on it.
- The lobby tests of the new server behaviour, each in its own process as CI runs them, all pass: `test_training`
  (14 tests), `test_casual` (22), `test_net_ping` (21), `test_stats` (7), `test_firewall` (32), `test_deploy` (14),
  `test_lobby` (35) and `test_ranked` (55).
