# Deploying lobby 1.1.2: central server and relay node

The exact steps to update the two production servers from the 1.1.1 lobby to 1.1.2, in order, with the checks
after each step and the way back. Rehearsed end to end on a local copy of both servers on 2026-10-19, and the
steps the later merges touch again on 2026-10-20 with main 67e3591 merged (see "What the rehearsal did" at the
end): no command here was run against the real servers.

| | Central lobby (Nuremberg) | Relay node `usw` (Hillsboro) |
|---|---|---|
| Address | 46.224.146.6 | 5.78.209.228 |
| Runs now | lobby 1.1.1 (`python3 -m t5lobby.server`) | lobby 1.1.1 relay node (`python3 -m t5lobby.server.relaynode`) |
| Code | `/opt/t5lobby` (installed by `install.sh`) | `/opt/t5lobby` |
| Source it was installed from | `/opt/src/t5dr-lobby/lobby` (check with `ls /opt/src`) | `/opt/src/T5DROnline/lobby` (likewise) |
| Settings | `/etc/t5lobby/t5lobby.env`, `tls/`, `relays.json`, `relay-usw.secret` | `/etc/t5lobby/t5lobby.env`, `relay.secret` |
| Data | `/var/lib/t5lobby/t5lobby.db`, `backups/` | none |
| Ports | TCP 7781, UDP 7781 + 7782, status 127.0.0.1:7780 | UDP 7781, status 127.0.0.1:7780 |
| install.sh options | `--self-signed --firewall none` | `--relay-only --relay-id usw --central 46.224.146.6` |

Both run as the systemd service `t5lobby`; `sudo t5lobby-admin ...` is the admin tool on both.

## In short

1. Copy the 1.1.2 `lobby/` to both servers and check it there (players notice nothing).
2. Tell the players (a server notice), 10-15 minutes ahead.
3. **Drain** the central server, then the **quiet check** (the 1.1.1 admin tool does not wait for ranked sets).
4. Update the **relay node** (no match uses it during the drain).
5. Update the **central server** (`install.sh` restarts it: a few seconds).
6. Checks. Players log in again (see "What players see").
7. Only after the owner has **published** the 1.1.2 release: `sudo t5lobby-admin release 1.1.2`.

Time: 20-30 minutes, most of it the drain. Downtime: the central restart, a few seconds.

## What 1.1.2 changes on the servers

- **Database**: the first numbered schema migration (`PRAGMA user_version` 0 -> 1) adds the tables `friends` and
  `friend_requests` and three indexes, in one transaction, at the first start. Nothing else in the database
  changes. An older server opens the upgraded database (tested with v1.1.1).
- **Friends and invites** (accounts, launchers 1.1.2+ only, cap `friends`). Older launchers get none of these
  messages (checked: every message a 1.1.1 launcher received from the 1.1.2 server is one a 1.1.1 server sends).
- **Region matchmaking**: the queues pair players whose estimated ping fits a window that grows while they
  wait (ranked: 80 ms + 10 ms/s, anybody after 60 s; quick: 80 ms + 20 ms/s, anybody after 30 s). The old
  400 ms cap of the ranked queue is gone, and the quick queue no longer pairs any two players at once.
- **Security**: bind tokens in the relay control channel are sealed (to nodes that say `etokens`; an older node
  still gets them readable, and the central server logs once that it should be updated); a 1.1.2 node refuses
  control requests stamped before it started (a request recorded before a node restart cannot be played back
  after it); password changes and new recovery codes 3 per account, then one per 20 s; the UDP total limit only
  counts pings; the database files lose "others" permissions at every start.
- **Security review 2** (main e080edd): at most `T5L_FRIEND_REQUESTS_ADDRESS` friend requests a day from one internet
  address (all its accounts together); after a declined or taken-back invite or challenge the same two wait
  `T5L_INVITE_RETRY_SECONDS` before the next one; a request taken back and sent again within a day is not announced
  again; an invite to a **ranked** room keeps the room's ready check; a profile shows "last seen" only to the
  account itself and its friends (a 1.1.1 launcher never showed it). Launcher side only: relay pings paced, Discord
  status hardened, controller presses on a new question ignored for 0.4 s.
- **Tekken 5 stages online** (unlock-stages, main 64ef2f5): `T5L_OLD_STAGES`, **off by default**. With 1 a match's
  stage may be one of the 15 Tekken 5 stages, but only when both launchers announce `old_stages` (1.1.2): a 1.1.1
  launcher always gets the stage select's own stages (rehearsed). Leave it off for this deploy; switching it on is
  one env line and a drained restart, best once most players have 1.1.2.
- **From this rehearsal** (branch `deploy-rehearsal`): `drain --wait` also waits for ranked sets (the drain fix);
  friends rows of deleted accounts are dropped at start (after a rollback); `t5lobby-admin release X.Y.Z`;
  launchers from 1.1.2 on keep their saved login when the server is unreachable and log in again by themselves
  after a restart.

## Settings (`/etc/t5lobby/t5lobby.env`)

`install.sh` keeps the existing env file, the TLS certificate and the relay secret. **Nothing has to be set or
changed for 1.1.2.** Keep what is there; in particular on the central server `T5L_RELAYS=/etc/t5lobby/relays.json`,
on the node `T5L_RELAY_SECRET_FILE=/etc/t5lobby/relay.secret`, `T5L_RELAY_ID=usw`,
`T5L_RELAY_CENTRAL=46.224.146.6`, `T5L_UDP_PORT2=0`.

New settings, all optional (the env file will not list them; the defaults apply):

| Setting | Default | What |
|---|---|---|
| `T5L_PING_START` | 80 | ms: the queues' estimated-ping window at first |
| `T5L_PING_WIDEN` / `T5L_QUICK_PING_WIDEN` | 10 / 20 | ms per second of waiting the window grows (ranked / quick) |
| `T5L_PING_ANY_SECONDS` / `T5L_QUICK_PING_ANY_SECONDS` | 60 / 30 | seconds after which any ping goes (0 = never) |
| `T5L_MAX_FRIENDS` | 100 | friends per account |
| `T5L_FRIEND_REQUESTS_DAY` | 20 | friend requests an account may send per 24 h |
| `T5L_FRIEND_PENDING` | 30 | unanswered requests at once, per sender and per receiver |
| `T5L_FRIEND_REQUEST_DAYS` | 14 | days before an unanswered request runs out |
| `T5L_FRIEND_RETRY_DAYS` | 7 | days before a declined request may be sent again |
| `T5L_INVITE_SECONDS` | 60 | seconds an invite waits for its answer |
| `T5L_FRIEND_REQUESTS_ADDRESS` | 60 | friend requests per 24 h from one internet address, all its accounts (0 = no limit) |
| `T5L_INVITE_RETRY_SECONDS` | 30 | after a no or a take-back, seconds before the same player may invite or challenge the same player again (0 = off) |
| `T5L_OLD_STAGES` | 0 | 1 = Tekken 5 stages may be drawn when both launchers know them (leave 0 for this deploy) |

Built in, no setting: password changes and new recovery codes (3 per account, then one per 20 s); the drain also
waiting for ranked sets.

## Before the day

- The code to deploy is the 1.1.2 release commit **with branch `deploy-rehearsal` merged** (the drain, rollback
  and update-notice fixes; it already contains main 67e3591). Call it `REF` below (the tag `v1.1.2` once it exists).
  Deploying main as it is also works; then read "Without the deploy-rehearsal fixes" at the end.
- `python tools/check_no_game_data.py` and the lobby tests pass on `REF` (CI's `lobby` job).
- The owner decides the time: the evening's quietest hour. Check `sudo t5lobby-admin status` the day before for
  what "quiet" is.

## Step by step

Commands marked **PC** run in `C:\T5DROnline` (Git Bash), **central** on 46.224.146.6, **node** on 5.78.209.228,
as root (or with sudo). SSH: the key used for the 1.1.1 deploy (`keys/vps_t5lobby`, known hosts in `keys/`).

### P1. Build the archive (PC)

```sh
git fetch origin
git -c core.autocrlf=false archive --format=tar.gz -o build/lobby_112.tgz REF lobby
sha256sum build/lobby_112.tgz
scp -i keys/vps_t5lobby build/lobby_112.tgz root@46.224.146.6:/opt/src/
scp -i keys/vps_t5lobby build/lobby_112.tgz root@5.78.209.228:/opt/src/
```

`core.autocrlf=false` matters: with CRLF line ends the env template breaks `install.sh` ("127.0.0.1\r").

### P2. Unpack and check, on both servers (no effect on players)

```sh
# central and node
sha256sum /opt/src/lobby_112.tgz                      # the same as on the PC
mkdir -p /opt/src/t5dr-lobby-1.1.2
tar -xzf /opt/src/lobby_112.tgz -C /opt/src/t5dr-lobby-1.1.2
cd /opt/src/t5dr-lobby-1.1.2/lobby
python3 -c "import sys; sys.path.insert(0, '.'); from t5lobby.server import Config, LobbyServer; LobbyServer(Config(db=':memory:')).store.close(); print('code ok')"
timedatectl | grep -i synchronized                    # "System clock synchronized: yes" on BOTH
date +%s                                              # central and node: the same second (see Risks, clocks)
```

The old source folders stay: they are the way back.

**Central only -- try the database upgrade on a copy** (catches a migration problem before anything is
stopped):

```sh
# central
sudo t5lobby-admin backup                              # prints the file and "N accounts, M matches": note them
B=$(ls -t /var/lib/t5lobby/backups/t5lobby-*.db | head -1)
install -m 600 "$B" /root/precheck.db
cd /opt/src/t5dr-lobby-1.1.2/lobby && python3 - <<'EOF'
import sys; sys.path.insert(0, ".")
from t5lobby.server.store import Store
st = Store("/root/precheck.db"); one = lambda q: st.db.execute(q).fetchone()[0]
print("migrated", st.migrated, "| schema", st.schema_version(), "| accounts", one("SELECT COUNT(*) FROM accounts"),
      "| matches", one("SELECT COUNT(*) FROM matches"), "| integrity", one("PRAGMA integrity_check"))
st.close()
EOF
rm -f /root/precheck.db /root/precheck.db-wal /root/precheck.db-shm
```

Expect `migrated [1] | schema 1 | accounts <N> | matches <M> | integrity ok` (rehearsal:
`migrated [1] | schema 1 | accounts 100 | matches 148 | integrity ok`). Anything else: stop here.

### C1. Tell the players, 10-15 minutes ahead (central)

```sh
sudo t5lobby-admin notice "Server update at 21:00: about 5 minutes. Matches running then finish first." --minutes 45
```

### C2. Drain (central)

```sh
sudo t5lobby-admin drain --wait 900
```

From now on no new match starts (queues, rooms, challenges, rematches are refused with "the server restarts for
an update in a moment"); running matches finish; a ranked set's next game still starts by itself. The tool prints
"N match(es) still running" and ends with `no match running: restart now`.

**The drain fix.** The 1.1.2 admin tool (deploy-rehearsal) also waits for ranked sets: it prints "N match(es) still
running, M ranked set(s) not finished" and says "restart now" only when both are 0. Today the installed tool is
still 1.1.1's, so C3 does that check by hand; from the next update on `drain --wait` alone is enough.

### C3. The quiet check (central) -- do not skip

The installed 1.1.1 admin tool says "restart now" as soon as no **match** runs, also while a ranked set waits
6 s between two of its games. A restart then voids the set and the game already won (the rehearsal reproduced
it: "restart now" with 3 ranked sets between games 1 and 2; they ended 4 minutes later). Run this until it
prints `quiet: restart now` (it waits up to 20 minutes):

```sh
sudo runuser -u t5lobby -- python3 - <<'EOF'
import json, sqlite3, time, urllib.request
db = sqlite3.connect("/var/lib/t5lobby/t5lobby.db", timeout=10)
for i in range(600):
    sets = db.execute("SELECT COUNT(*) FROM sets WHERE status = 'playing'").fetchone()[0]
    st = json.load(urllib.request.urlopen("http://127.0.0.1:7780/status", timeout=5))
    n = st["matches"]["running"]
    if st.get("draining") and n == 0 and sets == 0:
        print(time.strftime("%H:%M:%S"), "quiet: restart now"); raise SystemExit(0)
    if i % 5 == 0:
        print(time.strftime("%H:%M:%S"), f"{n} match(es) running, {sets} ranked set(s) not finished ...", flush=True)
    time.sleep(2)
print("still busy after 20 min"); raise SystemExit(1)
EOF
```

(Run it as `t5lobby`, never as root: a root process must not create database files the service cannot open.)
Then one more backup, the database exactly as the upgrade finds it (the way back if the database itself had to go
back): `sudo t5lobby-admin backup`.

**Drain timing.** A first-to-3 match takes 2-7 minutes; a best-of-3 ranked set up to three of them plus two 6 s
countdowns; a player who lost the lobby between two set games has 60 s to come back. Rehearsal (synthetic
players, stub games): 3.5 and 5.5 minutes. If it is still busy after 30 minutes, restarting anyway voids what
runs: matches and sets end `void (server_restart)`, no rating change, no blame.

### N1. Update the relay node (node), during the drain

With the central server drained, no new match is relayed; the node's running sessions end with their matches.

```sh
# node
sudo t5lobby-admin status                       # "0/100 sessions" -- else wait (a session closes 2 min after its last packet)
grep -E '^T5L_RELAY_(ID|CENTRAL)' /etc/t5lobby/t5lobby.env      # usw and 46.224.146.6
bash /opt/src/t5dr-lobby-1.1.2/lobby/deploy/linux/install.sh --relay-only --relay-id usw --central 46.224.146.6 --firewall none
```

`install.sh` keeps the env file and `relay.secret` ("keeping the existing ..."), copies the code, checks it
("code ok"), restarts the service and checks its health. `--firewall none` leaves ufw as it is (UDP 7781 is open
since the first install; `ufw status | grep 7781` to see).

Checks:

```sh
# node
sudo t5lobby-admin status       # "relay node usw  up 0d 0h 0m", "central   last request N s ago" with N < 10
journalctl -u t5lobby -n 20 --no-pager           # "relay node usw listening: UDP 0.0.0.0:7781, control only from ['46.224.146.6']"
# central
sudo t5lobby-admin status | grep 'relay usw'     # "up" again within 5-20 s
```

The central server may log `relay usw ... is down` and `is up` around the restart: expected.

### C4. Update the central server (central)

```sh
# central
bash /opt/src/t5dr-lobby-1.1.2/lobby/deploy/linux/install.sh --self-signed --firewall none
```

It keeps the env file and the certificate ("keeping the existing certificate (players pinned its fingerprint)"),
copies the code, checks it, restarts `t5lobby` (the database upgrade runs at this start) and waits for its health
check. The old process runs until that restart: the downtime is the restart itself. The restart ends the drain.

### C5. Checks (central)

```sh
systemctl is-active t5lobby                               # active
journalctl -u t5lobby --since "-5 min" --no-pager | grep -E "schema|listening|relay usw|WARNING|ERROR|Traceback"
```

Expect `database upgraded to schema 1: friends and friend requests ...`, `listening: TCP 0.0.0.0:7781 (TLS), UDP
7781 + probe 7782`, `relay usw (Oregon (US West)) is up`, and no ERROR or Traceback. (A `relay usw runs an older
version` warning means the node is still 1.1.1: N1 was skipped or failed.)

```sh
sudo t5lobby-admin status                                 # up; "relay usw ... up"; accounts = N from P2
sudo t5lobby-admin fingerprint /etc/t5lobby/tls/cert.pem --plain   # = the fingerprint in lobby/servers.json
sudo runuser -u t5lobby -- python3 -c "import sqlite3; c = sqlite3.connect('/var/lib/t5lobby/t5lobby.db'); q = lambda s: c.execute(s).fetchone()[0]; print('schema', q('PRAGMA user_version'), 'accounts', q('SELECT COUNT(*) FROM accounts'), 'matches', q('SELECT COUNT(*) FROM matches'), 'sets', q('SELECT COUNT(*) FROM sets'), 'friends', q('SELECT COUNT(*) FROM friends'), 'integrity', q('PRAGMA quick_check'))"
stat -c '%a %U:%G %n' /var/lib/t5lobby/t5lobby.db* /var/lib/t5lobby/backups /var/lib/t5lobby/backups/* | head
sudo t5lobby-admin user OWNER-ACCOUNT                     # rating, record and "friends   0" as before
```

- `schema 1`, accounts and matches as noted in P2 (more only if players registered or played since), `friends 0`,
  `integrity ok`.
- File modes: the database files `600` (or `640`), owner `t5lobby:t5lobby`; nothing readable by "others" (the
  systemd unit's `UMask=0077` already made them so; 1.1.2 also takes "others" away at every start).
- `grep -E 'OLD_STAGES|FRIEND_REQUESTS_ADDRESS|INVITE_RETRY' /etc/t5lobby/t5lobby.env` prints nothing: the defaults
  (old stages off, 60 friend requests per address a day, 30 s between invites after a no).
- Then a real login: the owner's 1.1.1 launcher logs in, a quick match against a second PC or the test account,
  and one relayed match if possible (on the central server the log says `match m...: relay usw (...)`, and no
  "older version" warning).

### C6. After the owner has published 1.1.2 (central)

Different game builds are never paired: once 1.1.2 is out, a 1.1.1 launcher waits in a queue its opponents are not
in. Tell those launchers (never before the release is public):

```sh
sudo t5lobby-admin release 1.1.2
```

Every launcher that reports an older release gets, within 5 s and at every login, in its status bar:
`T5DR Online 1.1.2 is out. Players on it cannot play against your 1.1.1: update the launcher (it offers the update
when it starts, or press "Check for updates").` (checked with the 1.1.1 Online tab). `release` alone shows the
setting, `release --clear` ends it.

## What players see

- At C1: the notice in the status bar. At C2: "the server restarts for an update in a moment; running matches finish
  first. Try again in a minute" when they try to queue.
- At C4 every launcher loses the lobby ("Lost the lobby connection"). **1.1.1 launchers do not log in again by
  themselves**: the player logs in again (with the password), or restarts the launcher, which uses the saved
  login. Guests type their name again. (Launchers from 1.1.2 on log in again by themselves with a saved login
  a few seconds after the server is back.) Worth saying in the notice or on Discord.
- After C4: the same accounts, ratings, ranks, history, blocks and remembered logins. A 1.1.2 launcher (once
  released) gets a Friends page; a 1.1.1 launcher sees no difference.

## Rollback

**Central back to 1.1.1** (if C4 or C5 fails, or players report problems):

```sh
# central
sudo t5lobby-admin drain --wait 900            # if it is up; then the quiet check of C3 again
bash /opt/src/t5dr-lobby/lobby/deploy/linux/install.sh --self-signed --firewall none
journalctl -u t5lobby -n 20 --no-pager         # "listening: ...", no Traceback
```

(`/opt/src/t5dr-lobby/lobby` stands for the v1.1.1 tree the central server was last installed from. If it is not
there or not v1.1.1, any v1.1.1 `lobby/` works: `git -c core.autocrlf=false archive --format=tar.gz -o
build/lobby_111.tgz v1.1.1 lobby` on the PC, copied and unpacked like P1/P2. Copy it there in P2 already.)

- The upgraded database stays: v1.1.1 opens it and works (tested: logins, remembered logins, quick, ranked sets,
  relayed matches through a 1.1.2 node). It does not know the friends tables and leaves them alone; it ignores the
  `release` setting and the new env settings (`T5L_OLD_STAGES`, `T5L_FRIEND_REQUESTS_ADDRESS`, ...: a server reads
  only the settings it knows). No data written by 1.1.2 has to be removed.
- While rolled back, avoid `delete-user` and `purge-inactive`: v1.1.1 deletes accounts without their friends rows,
  and SQLite gives the next new account the deleted one's id. 1.1.2 with the deploy-rehearsal fix drops those
  rows at its next start (rehearsed: `dropped 4 friends row(s) of deleted accounts`); main 7486b0c without it
  makes the new account the deleted one's friend (rehearsed: "Newcomer" showed up on "Kire"'s friends list).
- Only if the database itself is damaged: `systemctl stop t5lobby`, `t5lobby-admin restore /var/lib/t5lobby/backups/<the
  P2 backup> --yes`, `systemctl start t5lobby`. Everything since that backup (results, new accounts) is lost.
- Going forward again later: the same steps from C1.

**Node back to 1.1.1**:

```sh
# node
bash /opt/src/T5DROnline/lobby/deploy/linux/install.sh --relay-only --relay-id usw --central 46.224.146.6 --firewall none
```

(`/opt/src/T5DROnline/lobby` is the folder the node was installed from, per HOSTING.md; `ls /opt/src` shows it. Any
v1.1.1 `lobby/` works: `git -c core.autocrlf=false archive --format=tar.gz -o build/lobby_111.tgz v1.1.1 lobby`.)

A 1.1.1 node works with the 1.1.2 central server (tested): the central server sees that the node does not say
`etokens` and sends the bind tokens readable, as today, with one log line. A 1.1.2 node also works with a 1.1.1
central server (tested), so the order of the two rollbacks does not matter.

## Risks and findings

1. **Drain returns too early (fixed in deploy-rehearsal, workaround C3).** `drain --wait` counted only running
   matches; between two games of a ranked set none runs, and a restart then voids the set (the game already won
   is lost, no rating change). Reproduced in the rehearsal with the 1.1.1 and main admin tools. The fixed admin
   tool also waits for sets still `playing` in the database (against an older server too). For this deploy the
   installed tool is 1.1.1's: hence step C3.
2. **Everybody is logged out by the restart, and 1.1.1 launchers stay logged out.** Also, a launcher started while
   the server was unreachable deleted its saved login ("Your saved login has expired") -- e.g. during a restart.
   Both fixed for launchers from 1.1.2 on (deploy-rehearsal). For this deploy: say it in the notice.
3. **Rollback + account deletion = inherited friendships (fixed in deploy-rehearsal).** See Rollback. Related and
   older than 1.1.2 (not fixed): a reused account id also inherits the deleted account's match and set history,
   character statistics and pair counts (they are stored by account id). Rare: it needs `delete-user` /
   `purge-inactive` of the newest account and a new registration right after.
4. **Old and new launchers are never paired**: queue, challenges ("that player runs a different build of the
   game"), rooms, invites. The lobby list marks the others "(other version)"; the queue says nothing. Hence C6
   (new in deploy-rehearsal), after the release is public.
5. **Mixed window, central 1.1.2 + node 1.1.1**: works, but bind tokens cross the internet readable (as with 1.1.1)
   until the node is updated: update the node first (N1 before C4). Seen on the wire in the rehearsal: 2 of 2
   session requests readable with a 1.1.1 node, 2 of 2 sealed with a 1.1.2 node.
6. **Clocks**: a 1.1.2 node refuses control requests stamped more than 5 s before its own start. If the central
   server's clock is behind the node's by more than 5 s, the node refuses everything for that long after each
   node restart (DOWN, matches take the central relay). P2 checks NTP on both.
7. **Tekken 5 stages (`T5L_OLD_STAGES`)**: off by default and for this deploy. Switched on in the rehearsal (env line,
   drained restart): 2 of 4 pairs of 1.1.2 launchers got `t5s07`, the 1.1.1 pairs only the stage select's own
   stages, all matches confirmed. Switch it on only when the 1.1.2 game is out (its game must know those stages).
8. **Security review 2 limits** are new for players: an invite or challenge right after a "no" is refused for 30 s
   ("your last invite to that friend ended a moment ago; try again in N s", rehearsed); the same holds for any kind
   of invite between the same two. More than 60 friend requests a day from one address are refused (LAN parties:
   raise `T5L_FRIEND_REQUESTS_ADDRESS`).
9. **Matchmaking changes with the defaults**: the quick queue no longer pairs two far-apart players at once (up to
   30 s), the ranked queue may pair any ping after 60 s (before: never above 400 ms). Visible to players; tune with
   the `T5L_PING_*` settings if needed (restart).
10. **install.sh replaces the code before its check**: if "code ok" fails, the running server still has the old code
   in memory but the new code on disk; run the old `install.sh` (Rollback) before anything restarts the service.
   P2's check makes this unlikely.
11. **Not checked here**: file permissions on Linux (this PC is Windows; the logic is unit-tested with a fake POSIX
   `stat`), systemd, ufw. C5 checks the modes on the real server.

### Without the deploy-rehearsal fixes (deploying main as it is)

The steps are the same; C3 is needed for every later update too; C6 does not exist (`t5lobby-admin notice "T5DR
Online 1.1.2 is out: update the launcher" --hours 72` instead, which every player sees); while rolled back to 1.1.1
do not delete accounts; launchers keep losing their saved login when they start during an outage.

## What the rehearsal did

On this PC, nothing outside 127.0.0.1 (`build/deployrehearsal/`, scripts in `build/deployrehearsal/tools/`):

- A **central lobby** and a **relay-only node** installed from the v1.1.1 tag with the real `install.sh`
  (`--root` staging: `--self-signed`, and `--relay-only --relay-id usw --central 127.0.0.1`), run with the
  staged systemd unit's environment and the env files `install.sh` wrote; only the ports were local. The central
  server's `relays.json` and `relay-usw.secret` as in production (the node behind a transparent UDP forwarder that
  recorded the control channel).
- **Synthetic data through the v1.1.1 launcher glue** (LobbyClient + MatchDriver + stub games, each client from its
  own loopback address, production limits): 100 accounts (38 remembered logins, recovery codes), 70 ranked
  best-of-3 sets with Glicko-2 ratings 1132-1838, 148 matches, guests, quick, rooms (one ranked), a challenge, 15
  blocks (one undone), password changes, a recovery, new codes, a forgotten login; admin ban, address ban,
  notice, backups.
- **Deploy 1** (v1.1.1 -> main 7486b0c) with 12 players playing on (4 ranked pairs, 2 quick guest pairs):
  notice, drain 3.5 min, quiet check, `install.sh`, restart (8 s here, stop + install + start). Schema 0 -> 1,
  two new tables, three indexes; every other table identical (digests), apart from logins touching `last_seen`
  and `sessions.last_used` and the drain flag; certificate kept. The players were back right after the restart (the harness logs in again 5 s after losing the
  lobby, as a player would).
- **Clients** (v1.1.1 and 1.1.2 glue, stub games), on central 1.1.1 + node 1.1.1, central 1.1.2 + node 1.1.1,
  central 1.1.2 + node 1.1.2, and central 1.1.1 (rollback) + node 1.1.2: password, remembered (made by
  v1.1.1) and guest logins; quick (paired with the same version only); 40 s in the quick queue next to the other
  version: never paired; challenges and room joins across versions refused with a version error; ranked best-of-3
  sets confirmed, one rating update per set; relayed matches put on usw (round trips simulated: far from the
  central server, near the node) and confirmed; friends (request, accept, presence, casual and room invites, an
  old-launcher friend shown as "update", invites to it refused, the old launcher hearing nothing); message audit:
  the 1.1.1 launchers only ever got message types a 1.1.1 server sends. 34 + 45 + 6 + 22 checks, all PASS.
- **Relay node** checks (HMAC, replays, clock, node id, sealed and readable tokens) on 1.1.1 and 1.1.2: a request
  recorded before a node restart was taken again by 1.1.1 and refused by 1.1.2 (`clock`).
- **2026-10-20, main 67e3591 merged** (security review 2, unlock-stages old stages): deploy 3 (deploy-rehearsal
  a336a53 -> 00978ff) with 8 players playing on: the fixed `drain --wait` went on through a moment with 0 matches
  and 3 sets between games (03:06:16) and said "restart now" at 03:08:20 when the sets had ended; `install.sh`,
  restart; only the drain flag changed in the database. Then the clients again (login, quick, cross-version,
  relayed through usw with sealed tokens, friends incl. the 30 s invite hold after a "no", `release` notice, message
  audit): all PASS after three harness fixes (a relative stub path, a filter that took the admin notice for the
  update notice, friends left from the day before). `T5L_OLD_STAGES=1`: see risk 7; then off again.
- Tests on that head (00978ff + this doc and the env template): the lobby suite the CI way (22 modules, one process
  each) all exit 0, `python -m unittest discover -s tests -q` 603 tests OK (9 skipped), `python
  tools/check_no_game_data.py` exit 0.
- **Deploy 2** (main -> deploy-rehearsal) with 3 ranked pairs playing: the installed (main) admin said "restart now"
  at 20:35:26 while 3 sets were between games; the fixed one waited until 20:39:25, when they had ended.
- `release 1.1.2`: the v1.1.1 Online tab (hidden window) showed the update text in its status bar; 1.1.2
  clients got nothing.
- **Rollback** to v1.1.1 on the upgraded database: starts, everything above works; `delete-user` of the newest
  account and a new registration under 1.1.1, then 1.1.2 again: main would have made the new account a friend of
  the deleted one's friend; deploy-rehearsal dropped the 4 stale rows.
