# Online play: lobby, matchmaking, NAT traversal

The game's own PSN mode is dead and bypassed. Online play works like Tekken 6
Native Online: open the launcher, log in (or play as a guest), find an opponent
in the lobby, play. The two PCs talk to each other directly; a small lobby
server only introduces them, helps them through their routers, relays the
traffic when that fails, and keeps ratings.

The lobby's job ends when it hands each player's game the opponent's address
and the session parameters. From there the netplay layer (`src/netplay`,
branch `netplay`) exchanges pad input over UDP.

Everything is standard-library Python 3.10+ (asyncio, sqlite3, ssl). Nothing to
install for players or for whoever runs the server.

## Contents

- [Pieces](#pieces)
- [What happens in a match](#what-happens-in-a-match)
- [Handover to the game](#handover-to-the-game)
- [NAT traversal and the relay](#nat-traversal-and-the-relay)
- [Ratings, queues, results](#ratings-queues-results)
- [Protocol reference](#protocol-reference)
- [Security and abuse protection](#security-and-abuse-protection)
- [Running your own server](#running-your-own-server)
- [Tests, demo, measurements](#tests-demo-measurements)
- [Plugging in: launcher and netplay](#plugging-in-launcher-and-netplay)
- [Controller in the launcher](#controller-in-the-launcher)
- [What is left](#what-is-left)

## Pieces

```
lobby/
  t5lobby/
    proto.py      wire format shared by client and server, delay formula
    client.py     LobbyClient: what the launcher uses (own thread + asyncio loop, event queue)
    nat.py        the game socket while the lobby owns it: register, punch, relay bind, ping
    handover.py   MatchTicket -> environment for t5dr.exe; optional socket handover
    buildid.py    build identity both players must share
    rating.py     Glicko-2
    ranks.py      the game's rank tiers on top of Glicko-2 (placement, promotion, demotion)
    lag.py        the post-game lag check: ping X should mean Y frames behind, it was Z
    fighters.py   character / stage keys <-> the game's ids (data/fighters.json) for T5_FIGHT
    match_driver.py  the glue: match_start -> game -> result file -> report -> rematch
    tk_tab.py     the launcher's Online tab (tkinter); launcher/online.py imports it
    padnav.py     controller buttons for the tab: XInput + WinMM readers, the polling thread and its rules
    padmap.py     the game's controls.ini (Cross / Circle / Triangle of each pad) for padnav
    cli.py        python -m t5lobby.cli: the same from a console
    servers.py    servers.json: the launcher's server list, typed addresses (host:port#fingerprint)
    portmap.py    opt-in UPnP IGD / NAT-PMP port forwarding for "Host for friends"
    server/       python -m t5lobby.server
      lobby.py    players, rooms, queues, challenges, matches, results, bans, status numbers
      udp.py      UDP ping, endpoint registration, NAT probe, relay
      store.py    SQLite: accounts (scrypt hashes), sessions, recovery codes, ratings, ranks, history, bans,
                  blocked players, server notices
      admin.py    python -m t5lobby.server.admin: status, users, bans, passwords, recovery codes,
                  backups, certificates (accounts_admin.py: the account commands alone)
      status.py   local HTTP /health, /status, /metrics
      backup.py   online SQLite backups, restore
      selfsigned.py  self-signed TLS certificate with the standard library (no openssl)
      host.py     python -m t5lobby.server.host: "Host for friends" on a player's PC
      config.py   T5L_* environment variables
      ratelimit.py token buckets, temporary bans
  run.py          python lobby/run.py server|host|admin -- works with the release's isolated Python
  servers.json    the servers the release lists (a placeholder until the public server exists)
  Dockerfile, compose.yaml, deploy/   packaging: Docker, systemd + install.sh, Windows (docs/HOSTING.md)
  tests/          ~290 tests: server + simulated clients on localhost, the Online tab, the stub game,
                  hosting and operations, the Tekken 6 style options (test_t6.py), the controller
                  buttons with a fake pad (test_padnav.py, test_tk_pad.py)
  tools/
    two_players.py   two players on one PC: lobby -> punch -> two game instances
    ranked_session.py  two ranked accounts on one PC through the launcher's glue (stub or real game)
    stub_game.py     stand-in for t5dr.exe: netplay handshake, result file, netplay log lines
    relay_latency.py what the relay adds to the round trip
    load_test.py     what N lobby players and K relayed matches cost the server
```

```
  PC A (launcher)                    lobby server                     PC B (launcher)
  LobbyClient ---- TCP JSON lines ---- :7781/tcp ---- TCP JSON lines ---- LobbyClient
     |  game socket (UDP :pA)            :7781/udp  (register, relay)       |  game socket (UDP :pB)
     |------------- register --------------->|<------------- register ------|
     |<===================== punch / ping, direct ========================>|
     |- - - - - - or, when punching fails, through :7781/udp (relay) - - - ->|
     v                                                                     v
  t5dr.exe  T5_NET_MODE=host T5_NET_PORT=pA          t5dr.exe  T5_NET_MODE=join T5_NET_PORT=pB
            T5_NET_PEER=B's endpoint (or relay)                T5_NET_PEER=A's endpoint (or relay)
```

## What happens in a match

1. **Hello.** The client connects over TCP and sends its lobby protocol version
   and its build identity. A different protocol version is refused
   (`proto_mismatch`); a server can also pin the builds it accepts.
2. **Login.** Guest (just a name), account (name + password), register, or
   resume (after a dropped connection, with the session token).
3. **Lobby.** The server pushes `lobby_state` (players with status, rating,
   UDP ping to the server, build; open rooms; queue sizes) whenever something
   changes, at most ~3 times a second.
4. **Finding an opponent**, three ways:
   - *Quick match*: the queue pairs the players with the lowest estimated ping
     (sum of both players' ping to the server).
   - *Ranked*: pairs by rating and ping; the allowed rating gap grows while you
     wait (100 points + 25 per second, at most 800) and so does the allowed
     ping (80 ms + 10 per second, at most 400). Accounts only (configurable).
     The *strict* option keeps the gap at 150 points. The same two players are not
     paired again for 30 s after a ranked game.
   - Players who blocked each other are never paired by any of these.
   - *Rooms*: create one, someone joins; *challenges*: pick a player, they accept.
   Players are only ever paired with the **same build id**.
5. **Ready check.** Both must accept within 15 s (an accepted challenge skips
   it). Whoever declines or times out leaves the queue; the other keeps their
   place in it. A match from the queue is *blind* for clients that ask
   (`caps: ["blind_ready"]`): both see the ping between them, and neither sees the other's
   name or side until both accepted (`match_reveal`). The ping at that point is the
   server's estimate (both players' UDP round trips to the server, added), because the PCs
   are only connected after the accept; the real ping between them is measured in step 6
   and arrives in `match_start`. See RANKED.md, "Tekken 6 style options".
6. **NAT traversal** (next section): each launcher opens the UDP socket the game
   will use, registers it with the server, punches through to the other
   player, measures the round trip. If that fails, both bind to the relay.
7. **match_start.** Each launcher gets a `MatchTicket`, frees the port and
   hands the game `ticket.game_env()`: a new `t5dr.exe` started with it
   (process mode), or a "fight" command to the game that is already open
   (persistent mode, below). The server suggests the input delay from the
   measured round trip.
8. **Result.** After the game both launchers report the winner (from the
   game's result file, or the player answers "I won / I lost"). The server
   reconciles the two reports and updates ratings.

## Handover to the game

`MatchTicket.game_env()`:

| Variable | Read by netplay today | Meaning |
|---|---|---|
| `T5_NET_MODE` | yes | `host` (P1, slot 0) or `join` (P2, slot 1) |
| `T5_NET_PORT` | yes | local UDP port: exactly the port the lobby punched through. Bind it. |
| `T5_NET_PEER` | yes | `ip:port` of the opponent (direct/LAN) or of the lobby server's relay |
| `T5_NET_DELAY` | yes | input delay in frames (host's value wins, as netplay already does) |
| `T5_NET_TIMEOUT` | yes | seconds the peer may be silent / stall before the match ends (20) |
| `T5_NET_MATCH` | yes | match id; logged and written into the result file |
| `T5_NET_ROUNDS` | yes | rounds to win (3); direct fight takes them from `T5_FIGHT` |
| `T5_NET_PATH` | yes (logged) | `direct`, `lan` or `relay` |
| `T5_NET_RTT_MS` | yes (logged) | measured round trip |
| `T5_NET_SEED` | yes | 32-bit value both sides share (random generators; a `random` stage) |
| `T5_NET_BUILD` | yes | build id in the netplay HELLO; a peer with another one is refused |
| `T5_NET_KEY` | yes | the match's secret (server -> both clients over TCP only): every netplay packet carries a SipHash-2-4 tag under it |
| `T5_NET_RESULT_FILE` | yes | where the game writes the result (below) |
| `T5_NET_SOCKET_FILE` | proposed | only with socket handover (below) |
| `T5_FIGHT`, `T5_NET_START`, `PS3_FIXED_TIME` | direct fight | the fight from the server's `fight` (docs/DIRECTFIGHT.md) |
| `T5_HUD_NAMES`, `T5_HUD_RANKS` | direct fight | both players' lobby names and rank tiers, shown in the fight HUD |

**Persistent game (the default for builds that understand it).** Like Tekken 6
Native Online the game stays open between all matches. The launcher starts it
once with `T5_CTL_DIR` and hands every match over as a command with the same
variables (docs/DIRECTFIGHT.md "Persistent game", docs/RANKED.md "Game control
channel"): on `match_found` the game ends its netplay session and goes back to
a fresh select screen while the players accept and the NAT is punched; on
`match_start` it sets netplay up for the new opponent on the punched port and
drives the select screen. A rematch is the next match in the running session.
A game that does not take a command within 10 s (90 s while it boots), or dies
twice, is replaced by one process per opponent for the rest of the session
(`match_driver.MatchDriver`, `game_mode` in online.json forces either).

Measured through a lobby (fight-polish, `tools/dryrun_online.py --mode persistent
--new-opponent`, a local lobby server, two guests and two games on this PC, every
match a new pairing, quick match, rollback): **Accept to FIGHT 5.1-7.5 s** for
the 2nd to 4th opponent (runs dry_persist, dry_persist2: 4.0, 4.5; 5.6, 5.1;
7.0, 6.5; 7.5, 6.8 s), 19.6-20.6 s for the first match, which starts the game
(a new process every time before, ~20 s). All 6 matches confirmed. The longer
ones came right after the previous match: the game first skips that match's win
pose and goes back to a fresh select screen (~5.5 s at 60 fps from "idle" to
FIGHT, here at ~44 fps with both games on one PC).

The host calls `T5_NET_PEER` while it waits and takes as its peer the first
game whose HELLO carries a valid tag (on the relay path that comes from the
relay); without a key only a HELLO from `T5_NET_PEER`'s IP counts. After the
handshake both games accept only the other one's process (session id + nonce
+ tag) and follow it to a new address when its NAT re-maps the port
(docs/NETPLAY.md, "Connection problems").

**Input delay.** `suggest_delay(rtt, jitter) = clamp(ceil((rtt/2 + jitter + 2 ms) / 16.68 ms) + 1, 2, 10)`:
the input sampled at frame f is used at f + d on both PCs, so it must cross the
network (one way) within d frames, with one frame of slack for the two PCs'
frame clocks being out of phase. The server uses the larger of the two
players' measurements. Same PC / LAN: 2. 40 ms ping: 3. 100 ms: 5.

**Result file** (`T5_NET_RESULT_FILE`), written by the game when the match ends:

```json
{"match": "m752f00f03e2f", "winner": 0, "score": [3, 1], "desync": 0, "frames": 9120,
 "hash": "ceace43900b83115", "fps": 58.7}
```

`winner` 0 = P1 (host), 1 = P2 (join), `null` = draw; `score` = rounds won by
P1 and P2 (optional); `match` = the match it belongs to (the launcher refuses a
file naming another match); `desync`/`hash`/`frames` = the netplay evidence;
`fps` = this PC's own speed. A match that could not be finished has `"winner":
null` and a `reason` (`peer_timeout`, `peer_quit`, `no_peer`, `build_mismatch`,
...; docs/NETPLAY.md), and the game then closes (exit code 3/4/5). The launcher
reads the file as soon as it appears; without it the player is asked.

**Port handover (default).** The launcher closes its socket right before
starting the game, which binds the same port. UDP has no TIME_WAIT, so the
port is free immediately, and NAT mappings live 30 s or more, far longer than
the game needs to start (the netplay connects at frame 0).

**Socket handover (optional, `LobbyClient(handover="share")`).** No gap at all:
the launcher keeps a duplicate of the punched socket and, once the game process
exists, duplicates it into that process (`socket.share(pid)` =
`WSADuplicateSocketW`) and writes the blob as hex to `T5_NET_SOCKET_FILE`. The
game side (not implemented in netplay yet; tested here with a Python child):

```cpp
// instead of socket() + bind(): adopt the launcher's socket, already bound to T5_NET_PORT
if (const char* path = getenv("T5_NET_SOCKET_FILE")) {
    std::string hex;                       // wait up to ~5 s for the file, read it
    WSAPROTOCOL_INFOW info;                // hex-decode sizeof(info) bytes into it
    SOCKET s = WSASocketW(FROM_PROTOCOL_INFO, FROM_PROTOCOL_INFO, FROM_PROTOCOL_INFO,
                          &info, 0, 0);
    DeleteFileA(path);
    // then the usual SO_RCVTIMEO / SIO_UDP_CONNRESET setup on s
}
```

## NAT traversal and the relay

On `nat_begin` each client opens the game socket (any free port, or the fixed
port the player forwarded on the router) and sends `REGISTER` with its secret
per-match token to the server's UDP port, and `PROBE` to the second UDP port.
The server answers with the endpoint it saw. If the two ports saw different
source ports, the NAT maps per destination ("symmetric"); punching between two
symmetric NATs is pointless, so that pair goes straight to the relay.

The client then reports its own interface addresses (`nat_local`). The server
sends each side the other's candidates (`nat_punch`):

- the public endpoint it observed, always;
- the peer's private interface addresses, only when both have the same public
  IP (same router or same PC: hairpinning through the router often fails).
  Only private addresses are accepted, so a client cannot aim its opponent's
  punches at hosts on the internet.

Both clients send `PUNCH` to every candidate every 30 ms, for 3 s. Every punch
received is answered with a punch carrying `F_HEARD`; a punch carrying
`F_HEARD` proves the path works both ways. A packet from an address that was
not a candidate (the peer's NAT used another port) becomes a "reflexive"
candidate. After the first confirmation the client waits 120 ms for a better
one (local beats public), then measures 12 round trips with `PPING`/`PPONG` and
reports `nat_result` (median RTT, jitter = p90 - median).

When either side fails, the server opens a **relay session** (`nat_relay`).
Both clients send `RELAY_BIND` with their token from the game socket to the
server's UDP port; from then on, every packet from one bound endpoint that is
not addressed to the server is forwarded to the other bound endpoint, from the
same port. The game therefore talks to `server:7781` as if it were the
opponent. One UDP port serves every relayed match (the session is found by the
sender's address), so a self-hoster forwards one TCP and one or two UDP ports.

If a NAT re-maps the game's port between the launcher's bind and the game's
first packet, game traffic (`T5NP` magic) from the same IP is accepted for the
bound side that has gone quiet for 2 s. Strangers are dropped.

Relay limits per player: 400 packets/s and 512 kbit/s (the game sends ~60
packets/s, ~85 kbit/s); at most 100 relay sessions. A session closes when its
match ends (result, cancel or the 3 h limit); one left idle for 120 s after its
match is gone is swept up.

Not handled: UDP blocked entirely (the match is cancelled with
`udp_unreachable` and the player is told to check the firewall); IPv6 (the
netplay layer is IPv4-only too); port prediction for symmetric NATs.

## Ratings, queues, results

**Glicko-2** (Glickman 2012, τ = 0.5, start 1500 / RD 350 / σ 0.06), one
rating period per ranked match; RD grows again by one empty period per week of
inactivity. The implementation reproduces the paper's worked example
(1464.06 / 151.52 / 0.05999). Leaderboard order: r - 2·RD.

**Rank tiers, accounts and result reconciliation** (disconnects, quits,
crashes, desyncs, disputes, minimum match length, strikes, rematches) are in
[RANKED.md](RANKED.md). In short: both reports agree -> `confirmed`; a desync
-> `void`; quitting -> `forfeit` (a loss); losing the lobby for longer than the
grace period -> `forfeit`; winners differ -> decided by the netplay state hash
when there is one (`resolved`), else `disputed`.

## Protocol reference

### Control channel

TCP (optionally TLS), one JSON object per line, UTF-8, at most 8 KiB per line
from a client. Every message has `"t"`. A request may carry `"rid"` (integer);
the reply carries it back as `"re"` (`{"t":"ok"}` when there is nothing else to
say, `{"t":"error","code":...,"msg":...}` on refusal).

Client to server:

| t | fields | reply / effect |
|---|---|---|
| `hello` | `proto`, `client`, `build: {elf, code, net, release, id}`, `caps` (optional: `delta`, `blind_ready`, `notices`) | `welcome {server, proto, udp_port, udp_port2, build, accounts, guests, motd, ip, time, ..., caps, relay_only}` |
| `login` | `mode: guest\|account\|register\|resume`, `name`, `password`, `token` | `login_ok {you, token, resumed?}` |
| `ping` | | `pong {time}` (keepalive; silent clients are dropped after 90 s) |
| `udp_rtt` | `ms` | the client's UDP ping to the server (lobby list, matchmaking) |
| `lobby` | | `lobby_state` now |
| `leaderboard` | `limit` | `leaderboard {rows}` |
| `chat` | `text` (200 chars) | `chat` to everyone |
| `queue` / `unqueue` | `mode: quick\|ranked`, `char`, `strict` (ranked) | `queued {mode, strict}` |
| `room_create` | `name`, `ranked` | `room {room}` |
| `room_join` / `room_leave` / `rematch` | `room` | `room {room}`; two members start a ready check |
| `challenge` | `player` (id) | `challenge {challenge}`; target gets `challenged` |
| `challenge_reply` | `challenge`, `accept` | accepted: match without ready check |
| `challenge_cancel` | `challenge` | |
| `ready` | `match`, `accept` | |
| `nat_local` | `match`, `addrs [[ip,port]]`, `nat: eim\|symmetric\|unknown`, `port` | |
| `nat_result` | `match`, `phase: punch\|relay`, `ok`, `peer`, `kind`, `rtt_ms`, `jitter_ms` | |
| `game_started` | `match` | |
| `result` | `match`, `winner: 0\|1\|null`, `score: [p1, p2]` | `result_ack`; the other player gets `notice result_pending` |
| `leave_match` | `match` | cancels before start; a loss report while playing |
| `block` / `unblock` / `blocks` | `name` (or `player`) | `blocked` / `unblocked` / `blocks {rows}`; a match with that player ends like a quit |
| `leave_set` | `reason` (`lag`) | leave the games in a row between two games, no penalty; `set_end` to both |
| `lag` | `match`, `frames`, `waited_ms`, `pc_fps`, `fps` | after a match; both players then get `lag_check` |
| `logout` | | `bye`, connection closed |

Server to client (pushed):

| t | fields |
|---|---|
| `lobby_state` | `players [{id, name, guest, status, rating, rd, record, room, rtt, build, release}]`, `rooms [{id, name, owner, members, ranked, build, status}]`, `queue {quick, ranked}` |
| `lobby_delta` | only to clients with `caps: ["delta"]`, after one `lobby_state`: `players` (changed or new), `gone` (ids), `rooms` (changed or new), `rooms_gone`, `queue` -- each only when it changed. The client library merges it and emits a complete `lobby_state` |
| `chat` | `from`, `text`, `time` |
| `challenged` / `challenge_update` | `challenge`, `from` / `state: accepted\|declined\|cancelled\|expired` |
| `match_found` | `match`, `ranked`, `origin: queue\|room\|challenge`, `role`, `slot`, `opponent`, `ready_check`, `ready_timeout`, `ping {ms, kind: estimate, known}`, `set`. A blind check (queue match, client with `blind_ready`) has `blind: true`, `opponent: null` and no `role` / `slot` |
| `match_reveal` | blind checks only, once both accepted: `match`, `role`, `slot`, `opponent`, `you` |
| `opponent_ready` | `match` |
| `nat_begin` | `match`, `token` (hex, secret), `tag` (hex, shared by both players), `side`, `udp_port`, `udp_port2` |
| `nat_punch` | `match`, `candidates [{ip, port, kind}]`, `timeout` |
| `nat_relay` | `match`, `udp_port`, `reason` |
| `match_start` | `match`, `role`, `slot`, `path`, `peer`, `relay_port`, `rtt_ms`, `jitter_ms`, `delay`, `rounds`, `ranked`, `build`, `opponent`, `seed` |
| `match_cancel` | `match`, `reason: declined\|ready_timeout\|opponent_left\|udp_unreachable\|no_connection\|relay_full`, `you` (true = because of you) |
| `match_result` | `match`, `status`, `winner`, `score`, `ranked`, `rating {before, after, delta}`, `you` |
| `set_end` | `set`, `reason: declined\|left\|lag\|expired\|cancelled`, `by: you\|opponent\|null` |
| `lag_check` | after a match, to both players: ping, expected and observed frames behind, verdict, cause, a sentence (RANKED.md) |
| `server_notice` | `id`, `text`, `expires`, `cleared` -- a message from the admin tool (clients without the `notices` cap get a `notice` instead) |
| `notice` | `code`, `msg` (never contains an IP address) |
| `kicked` | `reason` |

Error codes: `bad_request`, `proto_mismatch`, `version_mismatch`,
`auth_failed`, `name_taken`, `bad_name`, `not_allowed`, `not_found`, `busy`,
`rate_limited`, `server_full`, `bad_state`.

**Lobby list updates.** At most every 0.3 s (`T5L_LOBBY_INTERVAL`), when something changed. A
client that announced `caps: ["delta"]` (this library does) gets the whole list after login or
after asking (`lobby`), then deltas; others get the whole list every time (the first 300 players
and 100 rooms). Whole lists for everyone cost O(players^2) -- 46 Mbit/s at 100 players before
the ranked entries grew; deltas cut that 26x (docs/HOSTING.md, "Resource estimate"). The `rtt` shown in the list only changes when
a player's ping moves by more than 5 ms or 20%; matchmaking uses the exact value.

The client library adds its own events: `match_start` carries a `ticket`
(MatchTicket); `nat_status {phase, text}` for the UI; `disconnected {reason}`. Texts it shows
(`notice`, `nat_status`, `disconnected`, ...) never contain an IP address: the server and the
client both remove them.

### UDP packets

Big-endian, 6-byte header `"T5LB" type version(1)`:

| type | name | to | layout after the header | size |
|---|---|---|---|---|
| 1/2 | `SPING`/`SPONG` | server | seq u32, sender time f64 (echoed) | 18 |
| 3/4 | `REGISTER`/`REG_ACK` | server | token 16 B (+ seen ip 4 B, port u16 in the ack) | 32 / 32 |
| 5/6 | `PROBE`/`PROBE_ACK` | server, 2nd port | same as REGISTER | 32 / 32 |
| 7/8 | `RELAY_BIND`/`RELAY_ACK` | server | same as REGISTER | 32 / 32 |
| 16 | `PUNCH` | peer | tag 8 B, side u8, flags u8 (1 = heard), seq u32 | 20 |
| 17/18 | `PPING`/`PPONG` | peer | tag 8 B, side u8, seq u32, time f64 | 27 |

Answers are never larger than requests (no amplification). The game's packets
(`T5NP...`) are never parsed, only relayed.

## Security and abuse protection

- **No secrets in the repository.** All server settings come from `T5L_*`
  environment variables; the database and any TLS key stay outside the repo
  (`lobby/.gitignore` blocks `*.db`, `*.pem`, `*.key`).
- **Passwords**: scrypt (N = 2^14, r = 8, p = 1), 16-byte random salt per
  account, constant-time comparison, never logged or stored in clear. The
  launcher does not save them. The CLI reads them from an environment variable,
  never from the command line.
- **Transport**: the control channel is plain TCP unless the server is given a
  certificate (`T5L_TLS_CERT`, `T5L_TLS_KEY`). Without TLS, passwords cross the
  network readable: use guest mode, or a password used nowhere else. A friend
  group can use a self-signed certificate and pin its SHA-256 fingerprint in
  the clients (`LobbyClient(tls_fingerprint=...)`, `--tls-fingerprint`), no
  certificate authority needed.
- **Your address is shared with your opponent**: direct play means each PC
  learns the other's public IP address. The lobby list never shows addresses;
  only the matched opponent's game gets one. Players who mind can use a
  relay-only server (`T5L_FORCE_RELAY=1`), which hides the addresses from each
  other at the cost of the detour via the server.
- **Rate limits** (token buckets): 20 messages/s per connection (burst 40);
  after 10 over-limit messages the address is banned for 60 s. New connections:
  0.5/s per address (burst 10), at most 8 at once per address, 500 in total.
  Failed password logins: 5, then one per minute, per address and per account
  name. Account creation: 3 per address, then one per 10 minutes. Chat: 1 line/s (burst 5).
  Challenges: one pending at a time, one per 2 s, at most 3 waiting per target.
  UDP control packets: 100/s per address. Login must finish within 15 s.
- **Input validation**: lines over 8 KiB close the connection; malformed or
  deeply nested JSON is refused; names are 2-16 characters from a fixed set;
  chat is cut to 200 printable characters; scores and winners are checked.
- **UDP**: unknown tokens get no answer; the relay only forwards between two
  endpoints that proved they hold the match's secret tokens, never sends more
  than it receives, and caps each side's rate.
- **Version check**: the server recomputes the build id from the reported ELF
  hash and code id (it does not trust the client's `id`), pairs only equal
  builds, and can pin the accepted builds (`T5L_BUILDS`). A client also refuses
  a `match_start` for a different build. Note this checks honesty, not
  tampering: a modified client can claim any build.
- **Results are self-reported**: two colluding accounts can trade wins. The
  reports, the match path and RTT are kept in the database for review.
- **Moderation**: `python -m t5lobby.server.admin` bans accounts (the reason is shown only after
  the correct password or saved login) and addresses/networks, resets passwords, recovery codes
  and ratings, ends remembered logins, purges old guest records and inactive accounts. Bans take
  effect within 5 s (the player is kicked). `T5L_NAME_BLOCKLIST` adds words to the reserved names.
- **More limits**: a client that stops reading is dropped once 1 MB is queued for it; UDP control
  packets are also capped for all senders together (5000/s), so spoofed pings cannot be reflected
  at many victims. The public-server profile and the reasons: docs/HOSTING.md.

## Running your own server

**[docs/HOSTING.md](HOSTING.md)** covers it: hosting options and costs, a 15-minute VPS setup
(`lobby/deploy/linux/install.sh`), Docker (`lobby/compose.yaml`), TLS with Let's Encrypt or a
pinned self-signed certificate, `servers.json`, "Host for friends" on Windows, the admin tool,
backups, monitoring, firewall rules and measured resource use. The short version:

A friend group needs one machine everybody can reach: a cheap VPS (any Linux
with Python 3.10+, 1 CPU and 512 MB are plenty) or one player's PC with ports
forwarded on the router (the launcher's **Host for friends** sets that up, TLS included).

```sh
# copy the lobby/ folder over (tests/ and tools/ are optional), then:
cd lobby
python3 -m t5lobby.server                     # TCP 7781, UDP 7781 + 7782, database ./t5lobby.db
```

Open (or forward on the router) **TCP 7781**, **UDP 7781** and, for NAT type
detection, **UDP 7782**. Players enter `your.host.name:7781` (or the IP) in the
launcher's Online tab.

On Windows (a player's PC): install Python from python.org, then in a console
`cd lobby` and `py -m t5lobby.server`; allow Python through the Windows
firewall when asked; forward the three ports to that PC's LAN address on the
router. That player then plays against others through their own server like
everybody else.

Settings (environment variables; command-line flags `--host --port --udp-port
--udp-port2 --db --log-level --force-relay` override them):

| Variable | Default | |
|---|---|---|
| `T5L_HOST` | `0.0.0.0` | bind address |
| `T5L_PORT` / `T5L_UDP_PORT` | `7781` | control (TCP) and UDP port |
| `T5L_UDP_PORT2` | `7782` | NAT probe port; `0` = off (symmetric NATs are then only found by failing to punch) |
| `T5L_DB` | `t5lobby.db` | SQLite file; back it up to keep accounts and ratings |
| `T5L_MOTD` | | message shown after login |
| `T5L_ACCOUNTS` / `T5L_GUESTS` | `1` / `1` | allow accounts / guests |
| `T5L_GUEST_RANKED` | `0` | guests in the ranked queue (their rating lasts the session) |
| `T5L_BUILDS` | | comma-separated build ids to accept; empty = any (pairing still requires equal builds) |
| `T5L_TLS_CERT` / `T5L_TLS_KEY` | | PEM files: control channel over TLS |
| `T5L_RELAY` / `T5L_FORCE_RELAY` | `1` / `0` | offer the relay / use only the relay |
| `T5L_RELAY_KBPS` / `T5L_RELAY_PPS` / `T5L_MAX_RELAYS` | `512` / `400` / `100` | relay caps |
| `T5L_MAX_CLIENTS` / `T5L_MAX_PER_IP` | `500` / `8` | connection caps (raise MAX_PER_IP for LAN parties behind one router) |
| `T5L_READY_TIMEOUT`, `T5L_PUNCH_TIMEOUT`, `T5L_RELAY_TIMEOUT`, `T5L_RESULT_TIMEOUT` | 15, 3, 6, 90 s | |
| `T5L_BLIND_READY` | `1` | queue matches show only the ping until both accepted |
| `T5L_STRICT_RANGE` / `T5L_PAIR_COOLDOWN` / `T5L_MAX_BLOCKS` | `150` / `30` / `200` | strict matchmaking range, same-opponent cooldown (s), blocks per player |
| `T5L_LAG_TOLERANCE` / `T5L_LAG_WAIT` | `1` / `6` | post-game lag check: extra frames allowed, seconds to wait for the second report |
| `T5L_ACCEPT_ONESIDED` | `1` | count a lone result report when the other player left |
| `T5L_LOG_LEVEL` | `INFO` | |
| `T5L_LOG_FILE`, `T5L_LOG_MAX_MB`, `T5L_LOG_BACKUPS` | , `10`, `5` | also log to a file, rotated (Windows hosts) |
| `T5L_CONN_RATE` / `T5L_CONN_BURST` | `0.5` / `10` | new connections per address per second, after a burst |
| `T5L_MAX_PENDING_KB` | `1024` | unread output per connection before it is dropped |
| `T5L_LOBBY_INTERVAL` | `0.3` | seconds between lobby list updates (at most) |
| `T5L_UDP_CTL_PPS` | `5000` | server-addressed UDP packets per second, all senders together |
| `T5L_NAME_BLOCKLIST` | | file with extra words refused in new names |
| `T5L_STATUS_HOST` / `T5L_STATUS_PORT` | `127.0.0.1` / `7780` | HTTP /health, /status, /metrics; `0` = off |
| `T5L_STATUS_LOG_MINUTES` | `15` | a one-line status in the log |
| `T5L_BACKUP_DIR`, `T5L_BACKUP_HOURS`, `T5L_BACKUP_KEEP` | , `24`, `14` | automatic online database backups |
| `T5L_ADMIN_POLL` | `5` | seconds until bans made with the admin tool take effect |

TLS: a self-signed certificate needs no domain, CA or openssl
(`python -m t5lobby.server.admin gen-cert --dir tls` prints the fingerprint players pin); with a
domain, Let's Encrypt via `lobby/deploy/linux/install.sh --domain`. The server reloads renewed
certificate files by itself. systemd unit, Docker image, Windows scheduled task: docs/HOSTING.md.

Load: each relayed match costs about 2 x 85 kbit/s of bandwidth; direct
matches cost the server nothing after the handshake. The lobby list costs
~25 kbit/s per player at 100 players (deltas). Measured numbers: docs/HOSTING.md.

## Tests, demo, measurements

```sh
python -m unittest discover -s lobby/tests          # ~140 tests, ~3 min, all on localhost
```

Unit: Glicko-2 against the paper's example, wire format, delay formula, token
buckets, password hashing, build ids, ticket environment. End to end (real
server, several clients): guest and account login, lockout after 5 wrong
passwords, name rules, lobby list and chat; quick match punched over LAN
candidates and over the public endpoint; relay when one client drops every
direct packet, and when the server forces it; the game's handshake on the
handed-over ports (joiner sends, host answers whoever spoke) on both paths;
strangers cannot inject into a relay; decline and ready timeout (the innocent
player keeps their queue place); UDP blocked -> cancelled; rooms with ready
check and rematch; challenges; confirmed / disputed / one-sided / void results
with Glicko-2 updates in the database; guests kept out of ranked; session
resume after a dropped connection; cross-build pairing refused (queue,
challenge, room); build allow-list; protocol mismatch; flooding -> rate limit
-> ban; per-address connection cap; garbage, long lines, login timeout; UDP
ping rate limit and no amplification; ranked matching by rating window and
ping; socket handover into a child process; TLS with a pinned self-signed
certificate (wrong pin refused); the launcher's Online tab driven through a
whole match. Hosting (`test_hosting.py`): admin tool (bans and kicks, saved logins ended by a
ban, address bans, password, recovery-code and rating resets, purges), status/health/metrics,
online and scheduled backups and restore, upgrade of an old database, lobby deltas against the
server's view and for old clients, the pure-Python certificate checked with openssl, certificate
reload, servers.json, Host for friends end to end, UPnP/NAT-PMP against fake routers; the Online
tab's Host for friends button.

**Two players on one PC** (`lobby/tools/two_players.py`): starts a local
server, logs in two guests, quick match, then starts two games with the
handed-over environment. With `--exe` it runs `t5dr.exe` built with the netplay
layer; without, `stub_game.py` (does netplay's HELLO handshake and 60 frames
of input exchange, then writes a result file like the game -- the winner follows
the shared seed -- which both sides report).

```sh
python lobby/tools/two_players.py                                   # stub, direct
python lobby/tools/two_players.py --relay                           # stub, relay
python lobby/tools/two_players.py --exe <t5dr.exe with netplay> --vfs game/vfs --seconds 45 --no-input [--relay]
```

Measured on this PC (2026-10-16), with the `netplay` branch's t5dr.exe as of
that evening:

- LAN-punched path: both instances log `[netplay] connected`, `lockstep
  starts: frame 0, delay 2`, and `sync check through frame 2399: 0 mismatching
  frame(s) -- in sync` (45 s run).
- Forced relay: the host logs `peer 127.0.0.1:<relay port> says hello`; in sync
  through frame 1799 (35 s); the relay forwarded 2060 / 2062 packets
  (374 KB each way, ~59 packets/s, ~85 kbit/s), 0 dropped.
- Relay overhead (`lobby/tools/relay_latency.py`, 64-byte packets, localhost):
  at 60 round trips/s direct median 0.139 ms vs relay 0.308 ms (+0.17 ms,
  p99 +0.38 ms); at 250/s +0.095 ms median. Under 2% of a frame. Unpaced
  ping-pong (~10,000 packets/s) loses packets by design: the 400 packets/s cap.
  Over the internet the relay's real cost is the detour via the server's
  location, not its processing.

## Plugging in: launcher and netplay

**Launcher**: `launcher/online.py` imports `t5lobby.tk_tab` (wired, branch
`ranked`). The tab uses `app.settings` (nickname, `path`, `out_dir`),
`app.game_state()`, `app.start_game(env)` and `app.set_status()`; it reads the
build identity from `<out>/game/EBOOT.elf` and `<out>/build/t5dr_build.json`
(`code_id`), and keeps its own settings and the saved login (a token, never a
password) per Windows user in `%APPDATA%\T5DROnline\online.json`. Matches run
through `match_driver.MatchDriver` (RANKED.md, "The match flow"). The release
zip carries `lobby/t5lobby/` (tools/package_release.py).

**Netplay**: result file (with match id and evidence), `T5_NET_ROUNDS`,
`T5_NET_MATCH`, the host calling `T5_NET_PEER`, `T5_NET_BUILD` in the HELLO and
`T5_NET_KEY` are done. Left: optionally adopt the socket from
`T5_NET_SOCKET_FILE` (snippet above).

## Controller in the launcher

The Online tab runs with a pad or an arcade stick, no mouse or keyboard needed once you are logged in
("Remember me" logs you in by itself). Like Tekken 6 Native Online.

| Button | What it does |
|---|---|
| **A** (Cross) | Accept a found match or a challenge. Rematch (also when the opponent offers one). Search: ranked for an account at first, quick for a guest, afterwards the kind you searched last. After you left a game (B), A is "back to ranked". |
| **B** (Circle) | Decline a found match or a challenge. Leave / No thanks after a game. Stop searching. |
| **Y** (Triangle) | Nothing. Every match gets a random stage from the server, a rematch too, so there is no stage to choose. |

- The buttons say which pad button presses them: "Accept (A)", "Decline (B)", "Ranked match (A)". A stick
  shows its own button names, "Accept (B2)". The line under the lobby names the pad and its Cross, Circle and
  Triangle. With several pads, the one you pressed last gives the names.
- The question "How did the match end?" (I won, I lost), "Block" and "Leave: too laggy" are never answered
  by a pad. Those you click.
- **Only when the launcher window is in front** and the Online tab is showing. While the game or any other
  window is in front (or a dialog of the launcher is open), the pads are not even read, so presses in the
  game never reach the launcher.
- **A press counts only after the button was up for 0.3 s** with the launcher in front. A button that is held
  when the launcher comes forward, or mashed (the end of a fight), does nothing. Two buttons pressed at once
  are no press. After an action the next one waits 0.6 s. A press that waited more than 1 s for the window
  (a dialog was open) is dropped.
- **Which stick button is Cross follows the game's `controls.ini`** (`docs/controls.ini`, runtime patch 0009).
  The launcher finds the file the way the game does: `PS3_CONTROLS` (also from Settings, "extra settings"),
  else `controls.ini` next to `t5dr.exe` (`<output>\build\cmake`), else in the output folder
  (`native\controls.ini`), else the built-in defaults. It reads the same presets (`standard`, `ps`, `switch`,
  `xbox`), sections (`[xinput]`, `[dinput]`, `[dinput.VVVV:PPPP]`, `[port1.dinput]`, `[port1] device = ...`)
  and `TARGET = SOURCE` lines, and again when the file changes. A remapped stick works the same in the
  launcher and in the game. A button bound to two PS3 buttons at once (a macro such as `3+4 = B8`) is
  neither Cross nor Circle here. `tests/test_padmap_sync.py` fails when the game's presets change and
  `lobby/t5lobby/padmap.py` was not updated.
- Xbox pads and XInput-mode sticks are read with XInput. Everything else (PS3/PS4-mode sticks and hitboxes,
  DualShock 4, DualSense, generic pads) with the Windows joystick API (WinMM, `joyGetPosEx`): the same button
  numbers as the game's DirectInput side (B1..B32, the hat), no packages. A pad that Windows shows through both
  is read once, through XInput. Plain `ctypes`, one thread, 60 polls a second while the launcher is in front
  (measured with a real XInput pad: 0.7% of one core), 20 looks at the foreground window a second while it is
  not (0.01%).
- Switch: **Use a controller here** at the bottom of the tab (saved as `pad` in `online.json`).
  `T5_PAD_NAV=0` in the environment turns the feature off.
- With `background = 1` in `controls.ini` (the default) a running game reads the pad too, also while the
  launcher is in front: a press that accepts a match is also a Cross in the game, which waits at its
  character select. Set `background = 0` if that gets in the way.
- Test hook: `T5_PAD_FILE=<file>` makes a virtual pad of the buttons named in the file (`A`, or
  `dinput:054C:09CC B2`); with it the real pads are ignored (`T5_PAD_DEVICES=1`: both).
- Code: `lobby/t5lobby/padmap.py` (controls.ini), `lobby/t5lobby/padnav.py` (devices, polling rules, thread),
  `lobby/t5lobby/tk_tab.py` (what each button does). Tests: `lobby/tests/test_padnav.py`,
  `lobby/tests/test_tk_pad.py`, `tests/test_padmap_sync.py`; they use a fake pad and a fake clock.
  Not tried with a real stick yet (the XInput pad on the development PC was only read, not pressed).

## What is left

- Netplay side of the handover extras above: socket adoption (everything else is done).
- The persistent game starts with the first match; starting it already when the player
  queues would make the first match as quick as the later ones.
- TURN-style relay on a separate host, or several relay regions; today the relay is the lobby server.
- Port prediction for symmetric NATs; IPv6. (UPnP/NAT-PMP exists for "Host for friends" only,
  opt-in, and is so far tested against fake routers only.)
- The lobby list still goes to everybody (deltas made it ~26x cheaper); past several hundred
  players it needs paging or interest filtering.
- Moderation beyond the admin tool (docs/HOSTING.md): in-game reporting of cheaters, a kick
  without a ban.
- Relay sessions do not survive a server restart (relayed games in progress break).
- Spectating, replays, region tags, friends list.
- The server has not been run on a real VPS or across two real NATs yet; everything above was
  measured on localhost.
