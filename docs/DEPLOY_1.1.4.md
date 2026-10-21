# Deploying lobby 1.1.4: central server (the relay node stays)

The steps to update the production lobby from 1.1.3 to 1.1.4, in order, with the checks after each step and the way
back. The procedure is the one of [DEPLOY_1.1.3.md](DEPLOY_1.1.3.md), shorter: 1.1.4 changes no database table and no
relay code, and needs no setting in the env file. **Not rehearsed on a local copy of the servers** like 1.1.3 was (see
"What was checked"): no command here was run against the real servers.

| | Central lobby (Nuremberg) | Relay node `usw` (Hillsboro) |
|---|---|---|
| Address | 46.224.146.6 | 5.78.209.228 |
| Runs now | lobby 1.1.3 | lobby 1.1.3 relay node |
| Code | `/opt/t5lobby` | `/opt/t5lobby` |
| Installed from | `/opt/src/t5dr-lobby-1.1.3/lobby` (check with `ls /opt/src` before you start) | likewise |
| install.sh options | `--self-signed --firewall none` | `--relay-only --relay-id usw --central 46.224.146.6 --firewall none` |

## In short

1. Copy the 1.1.4 `lobby/` to the central server and check it there, including the database on a copy.
2. Notice, then **`drain --wait`** (it waits for running matches and ranked sets).
3. Backup, `install.sh` on the central server (it restarts the service: a few seconds).
4. Checks. Players log in again (1.1.3 launchers by themselves with a saved login).
5. Only after the owner has **published** 1.1.4: `sudo t5lobby-admin release 1.1.4`.

The relay node runs the same relay code in 1.1.3 and 1.1.4 (`relaynode.py`, `relays.py`, `relayctl.py`, `udp.py`:
no difference to v1.1.3): it may stay on 1.1.3. Time: 10-20 minutes, most of it the drain. Downtime: the restart.

## What 1.1.4 changes on the servers

Files: `lobby/t5lobby/server/{config,lobby,rooms,spectating,tournaments}.py`, `lobby/t5lobby/proto.py` (one new
function, `address_net`), `lobby/deploy/t5lobby.env.example` (the settings below, commented out).

- **Database: no change.** A fresh database made by the v1.1.3 lobby and one made by this one have the same 39
  objects (tables and indexes), `PRAGMA user_version` 1 and `kv` `schema.tournaments` 2; `store.py` is identical and
  `tournaments.py` only gained a function. The upgrade check in P2 still runs, and a rollback needs no database step.
- **Password rooms** (docs/ONLINE.md "Rooms"): a guess at a room is paid first out of a lane of the guesser's own
  network (an IPv4 address, an IPv6 /48), only then out of the room's shared budget, so strangers guessing from many
  addresses can no longer lock the members out. IPv6 guesses also count per /56 and /48. The host's room view shows
  the wrong passwords of the last 10 minutes (counts only) and the new message `room_bar` turns those networks away.
- **Spectator limits** (docs/SPECTATE.md "Limits and bounds"): per internet address, per IPv6 network, a guest share
  and reserved stream slots; friends of the players and members of the match's room or tournament come first and
  replace the newest guest at a full match (`spec_end` reason `bumped`).
- **Watch between a match and its rematch**: a room keeps Watch while its session's stream is alive (1.1.3 launchers
  get it too).
- **Jinpachi**: capability `boss_chars`; a casual match's result may name him, ranked matches and tournament sets
  still refuse him.
- **Builds**: 1.1.4 games have a new code ID: 1.1.3 and 1.1.4 players are never paired (queue, challenges, rooms,
  invites, tournaments). 1.1.3 launchers keep working with the new server and see nothing new, except that the
  limits and the room protection apply to them.

## Settings (`/etc/t5lobby/t5lobby.env`)

Nothing to add: the defaults are meant for production. `install.sh` keeps the env file, the certificate and the relay
secret. New (all read from `lobby/t5lobby/server/config.py`):

| Setting | Default | What |
|---|---|---|
| `T5L_ROOM_LANE_GUESSES` | `3` | wrong passwords one network (IPv4 address, IPv6 /48) may try at one room out of its own lane, spent before the room's shared budget |
| `T5L_ROOM_LANE_SECONDS` | `1200` | then one more per this many seconds |
| `T5L_SPEC_PER_ADDRESS` | `2` | matches watched at once from one internet address (IPv4, IPv6 /64) |
| `T5L_SPEC_PER_NET` | `4` | ... from one IPv6 /56 (a /48: twice this); 0 = no limit |
| `T5L_SPEC_GUEST_SHARE` | `0.5` | share of a match's places and of `T5L_MAX_STREAMS` that guests may hold |
| `T5L_SPEC_RESERVED_STREAMS` | `10` | the last stream slots, for friends of the players and room or tournament members only |

Same name and default, new behaviour:

| Setting | Default | Now |
|---|---|---|
| `T5L_ROOM_GUESSES` / `T5L_ROOM_GUESS_SECONDS` | `5` / `30` | also counted per IPv6 /56 (4x a player's budget) and /48 (8x); the room's shared budget (4x, then 3 per `T5L_ROOM_GUESS_SECONDS`) is used only after the guesser's lane |
| `T5L_MAX_SPECTATORS` / `T5L_MAX_STREAMS` | `8` / `50` | guests hold at most 4 places of a match; guests start a stream only below 25 streams, other accounts below 40 (the last 10 are reserved) |

Shared internet addresses (a CGNAT, a dormitory, a cafe) all count against `T5L_SPEC_PER_ADDRESS`; friends and room
members do not count. If players there complain of "too many matches are watched from your network", raise it (or
`T5L_SPEC_PER_NET`) in the env file and restart (`systemctl restart t5lobby`, after a drain).

## Step by step

**PC** = `C:\T5DROnline` (Git Bash), **central** = 46.224.146.6 as root, SSH key as for the 1.1.3 deploy.

### P1. Build the archive (PC)

```sh
git fetch origin
git -c core.autocrlf=false archive --format=tar.gz -o build/lobby_114.tgz REF lobby     # REF: the 1.1.4 commit (tag v1.1.4)
sha256sum build/lobby_114.tgz
scp -i keys/vps_t5lobby build/lobby_114.tgz root@46.224.146.6:/opt/src/
```

### P2. Unpack and check (central; players notice nothing)

```sh
sha256sum /opt/src/lobby_114.tgz
mkdir -p /opt/src/t5dr-lobby-1.1.4 && tar -xzf /opt/src/lobby_114.tgz -C /opt/src/t5dr-lobby-1.1.4
cd /opt/src/t5dr-lobby-1.1.4/lobby
python3 -c "import sys; sys.path.insert(0, '.'); from t5lobby.server import Config, LobbyServer; LobbyServer(Config(db=':memory:')).store.close(); print('code ok')"
# the new code on a copy of today's backup
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

Expect `code ok`, then `schema 1 | tournaments [1, 2] | accounts <N> | matches <M> | integrity ok` with N and M as in
the backup. Anything else: stop here.

### C1. Notice, 10-15 minutes ahead (central)

```sh
sudo t5lobby-admin notice "Server update at 21:00: about 5 minutes. Matches running then finish first." --minutes 45
```

### C2. Drain, back up, install (central)

```sh
sudo t5lobby-admin drain --wait 900          # "no match running: restart now" -- waits for ranked sets and tournament sets too
sudo t5lobby-admin backup                    # the database exactly as the install finds it
bash /opt/src/t5dr-lobby-1.1.4/lobby/deploy/linux/install.sh --self-signed --firewall none
```

`install.sh` keeps the env file and the certificate, checks the code ("code ok"), restarts `t5lobby` and waits for
its health check. Rooms, invite codes and spectator streams end with the restart (memory only, as at every update);
a running tournament resumes (DEPLOY_1.1.3.md "Restarts on 1.1.3").

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
- `status` as before the update (accounts and matches as in P2, `relay usw ... up`); `tour-hosts` still shows the
  `T5L_TOUR_ADMINS` account and the host slots as before.
- The database line: `schema 1 tournaments ('2',) accounts <N> matches <M> friends <as before> integrity ok`.
- A real login with the owner's 1.1.4 launcher: the Online tab loads. With a 1.1.3 launcher: it logs in again by itself.
- If two 1.1.4 launchers are at hand: a quick match offers Jinpachi and the random cell on the select; a room with a
  password lets the right password in and the host's **Room settings** shows **Turn away the guessers**; the Rooms
  list shows **Watch** for a room between a match and its rematch.

### N1. The relay node (optional)

No relay code changed. To keep both machines on the same tree, update it in a quiet moment, as in DEPLOY_1.1.3.md N1
with `1.1.4` in place of `1.1.3` (copy `lobby_114.tgz` there first as in P1/P2):

```sh
sudo t5lobby-admin status                    # "0/100 sessions"
bash /opt/src/t5dr-lobby-1.1.4/lobby/deploy/linux/install.sh --relay-only --relay-id usw --central 46.224.146.6 --firewall none
```

### C4. After the owner has published 1.1.4 (central)

```sh
sudo t5lobby-admin release 1.1.4
```

Launchers of an older release then show `T5DR Online 1.1.4 is out ... update the launcher` in their status bar,
within a few seconds and at every login; 1.1.4 launchers nothing. `release` alone shows the setting, `release --clear`
ends it. Never before the release is public.

## What players see

- The notice; during the drain "the server restarts for an update in a moment" when they queue, create or join a room;
  then "Lost the lobby connection" and a login again (by themselves with a saved login).
- Accounts, ratings, history, friends, blocks, tournaments, remembered logins: unchanged. Rooms and their codes are
  made again by their hosts.
- A 1.1.4 launcher can log in to a 1.1.3 server, but that server refuses a casual result that names Jinpachi
  (`chars is [P1 fighter, P2 fighter]`): the server update comes before 1.1.4 players play each other.

## Rollback to 1.1.3

```sh
sudo t5lobby-admin drain --wait 900
bash /opt/src/t5dr-lobby-1.1.3/lobby/deploy/linux/install.sh --self-signed --firewall none
journalctl -u t5lobby -n 20 --no-pager
```

- No database step: 1.1.3 opens the database as it is (same schema). Rooms end at the restart, as always.
- Without a drain a tournament set being played is void and called again; plan the update outside announced
  tournament times (DEPLOY_1.1.3.md "Restarts on 1.1.3").
- The 1.1.4 settings may stay in the env file (1.1.3 ignores settings it does not know). Spectator limits and the room
  protection are gone again; 1.1.4 launchers keep working but are never paired with 1.1.3 players.
- If `release 1.1.4` was set, clear it: `sudo t5lobby-admin release --clear`.
- Only if the database itself is damaged: restore the backup of C2 (`systemctl stop t5lobby; t5lobby-admin restore
  FILE --yes; systemctl start t5lobby`).

## Risks

1. **Shared addresses** hit `T5L_SPEC_PER_ADDRESS` (2 matches at once per IPv4 address) sooner than a home connection
   does; friends and room or tournament members are exempt. Raise it if players report it.
2. **The server must be updated before 1.1.4 games are played** (Jinpachi results): update the server first, then
   publish; 1.1.3 players then see the release notice (C4).
3. **Rooms, invite codes and spectator streams end at the restart** (memory only, unchanged since 1.0/1.1.3).
4. **Not checked here**: Linux file modes, systemd, ufw (Windows PC); the real servers.

## What was checked

On this PC, nothing outside 127.0.0.1 and nothing against the real servers:

- The diff v1.1.3 .. f2bc928 of `lobby/` read for schema, relay and env changes (above); `store.py`, `relaynode.py`,
  `relays.py`, `relayctl.py`, `udp.py`, `admin.py`, `status.py` and `deploy/linux/` are identical to v1.1.3.
- A fresh database made by each version has the same objects (39), `user_version` 1 and `schema.tournaments` 2.
- The lobby tests that cover the new server behaviour, each in its own process as CI runs them: `test_private_rooms`
  (28 tests), `test_spectate_limits` (3), `test_spectate` (21), `test_deploy` (14), `test_ingame_pick` (17) and
  `test_lobby` (35) all pass. The other lobby modules and a full two-server rehearsal like DEPLOY_1.1.3.md's were not
  run for 1.1.4.
