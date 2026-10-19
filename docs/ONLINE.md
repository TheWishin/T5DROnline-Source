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
- [NAT traversal and the relay](#nat-traversal-and-the-relay) (and [regional relays](#regional-relays))
- [Ratings, queues, results](#ratings-queues-results)
- [Friends and invites](#friends-and-invites)
- [Discord Rich Presence](#discord-rich-presence)
- [Protocol reference](#protocol-reference)
- [Security and abuse protection](#security-and-abuse-protection)
- [Running your own server](#running-your-own-server)
- [Tests, demo, measurements](#tests-demo-measurements)
- [Plugging in: launcher and netplay](#plugging-in-launcher-and-netplay)
- [Controller in the launcher](#controller-in-the-launcher)
- [Languages](#languages)
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
    discord_rpc.py   optional Discord Rich Presence over the Discord app's local IPC pipe (no SDK)
    tk_tab.py     the launcher's Online tab (tkinter): its logic and state; launcher/online.py imports it
    tk_views.py   the Online tab's screens: login, lobby, searching, match found, in match, result, errors
    theme.py      the launcher's dark look: ttk theme, fonts, drawn badges / ping bars / countdown ring
    padnav.py     controller buttons for the tab: XInput + WinMM readers, the polling thread and its rules
    padmap.py     the game's controls.ini (Cross / Circle / Triangle of each pad) for padnav
    cli.py        python -m t5lobby.cli: the same from a console
    servers.py    servers.json: the launcher's server list, typed addresses (host:port#fingerprint)
    portmap.py    opt-in UPnP IGD / NAT-PMP port forwarding for "Host for friends"
    server/       python -m t5lobby.server
      lobby.py    players, rooms, queues, challenges, matches, results, bans, status numbers
      udp.py      UDP ping, endpoint registration, NAT probe, relay
      store.py    SQLite: accounts (scrypt hashes), sessions, recovery codes, ratings, ranks, history, bans,
                  blocked players, server notices, friends and friend requests; numbered schema migrations
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
8. **Character select in the game.** When both players' launchers and games
   can, `match_start.fight` has `pick` (seconds, 30): the game shows its own
   select screen and each player picks fighter and costume there (the button
   you confirm with is the costume, Select = random). The two games exchange
   the picks and start the fight. Nothing picked in time: the character set in
   the launcher. A rematch goes back to the select screen the same way; in a
   ranked set only the first game is picked, the rest keep those fighters
   (docs/RANKED.md "Character select in the game").
9. **Result.** After the game both launchers report the winner (from the
   game's result file, or the player answers "I won / I lost") and, after an
   in-game pick, the fighters. The server reconciles the two reports and
   updates ratings.

## Handover to the game

`MatchTicket.game_env()`:

| Variable | Read by netplay today | Meaning |
|---|---|---|
| `T5_NET_MODE` | yes | `host` (P1, slot 0) or `join` (P2, slot 1) |
| `T5_NET_PORT` | yes | local UDP port: exactly the port the lobby punched through (relay bridge: a free local port). Bind it. |
| `T5_NET_PEER` | yes | `ip:port` of the opponent (direct/LAN), of the lobby server's relay, or `127.0.0.1:<port>` of the launcher's relay bridge |
| `T5_NET_DELAY` | yes | input delay in frames for the lockstep (host's value wins, as netplay already does); the rollback delay is never above it |
| `T5_RB_NET_DELAY` | yes | ranked only: the server's fixed rollback input delay (`T5L_RANKED_INPUT_DELAY`, default 2, in `match_start` as `input_delay`); other matches get the player's own setting from the launcher (`auto`, 0, 1, 2; docs/NETPLAY.md "Input delay") |
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
| `T5_FIGHT`, `T5_NET_START`, `PS3_FIXED_TIME` | direct fight | the fight from the server's `fight` (docs/DIRECTFIGHT.md); with `pick=N` on it when the players pick in the game |
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

The whole story -- why the same two homes sometimes got a direct connection and sometimes not, what
1.1.1 changed, the NAT simulator and its numbers -- is in docs/NETPLAY.md, "Getting a direct
connection". In short:

On `nat_begin` each client opens the game socket (any free port, or the fixed
port the player forwarded on the router), asks the router to forward that port
when the player allows it (launcher Settings, PCP / NAT-PMP / UPnP, 10-minute
lease), and sends `REGISTER` with its secret per-match token to the server's
UDP port, and `PROBE` to the second UDP port. The server answers with the
endpoint it saw. If the two ports saw different source ports, the NAT maps per
destination ("symmetric"); when the two ports are close, its next ports can be
guessed. Two symmetric NATs whose ports cannot be guessed go straight to the
relay.

The client then reports its own interface addresses (`nat_local`). The server
sends each side the other's candidates (`nat_punch`):

- the public endpoint it observed (for a symmetric peer only after its
  predicted ports: that endpoint leads to the server only);
- the peer's router forward, only on the peer's own public address;
- the peer's private interface addresses, only when both have the same public
  IP (same router or same PC: hairpinning through the router often fails).
  Only private addresses are accepted, so a client cannot aim its opponent's
  punches at hosts on the internet;
- for a symmetric peer whose ports count up, the next 24 ports it will use
  (an older client gets the next 8, ahead of the public endpoint).

A client with the `nat2` cap also gets a plan: both start at the same server
time, at first only with a low TTL (each side opens its own NAT without its
punch reaching the other router) until the other side has said through the
server that it started too (`nat_punching` -> `nat_peer_punching`), then 20
punches a second to every candidate for the rest of the 6-second window, the predicted ports walked in
the order the peer's NAT hands them out. An older client punches every
candidate every 30 ms for the window from the moment its message arrives, as
before. Every punch received is answered with a punch carrying `F_HEARD`; a
punch carrying `F_HEARD` proves the path works both ways. A packet from an
address that was not a candidate (the peer's NAT used another port) becomes a
"reflexive" candidate. After the first confirmation the client waits 120 ms for
a better one (local beats public), then measures 12 round trips with
`PPING`/`PPONG` and reports `nat_result` (median RTT, jitter = p90 - median).

The server waits for both reports (or the end of the window). When one side got
through and the other did not, the failed side punches once more (2.5 s); only
when both fail does the server open a **relay session** (`nat_relay`).
Both clients send `RELAY_BIND` with their token from the game socket to the
server's UDP port; from then on, every packet from one bound endpoint that is
not addressed to the server is forwarded to the other bound endpoint, from the
same port. The game therefore talks to `server:7781` as if it were the
opponent. One UDP port serves every relayed match (the session is found by the
sender's address), so a self-hoster forwards one TCP and one or two UDP ports.
Between two `nat2` clients the game socket stays in the launcher instead (relay
bridge): the game talks to it on 127.0.0.1, the launcher carries its packets
to the relay and tries the direct path in 3-second bursts every 40 s (both at
the same server time); once it works both ways the match leaves the relay
(`nat_upgrade`), and goes back to it if the direct path goes quiet.

If a NAT re-maps the game's port between the launcher's bind and the game's
first packet, game traffic (`T5NP` magic) from the same IP is accepted for the
bound side that has gone quiet for 2 s. Strangers are dropped.

Relay limits per player: 400 packets/s and 512 kbit/s (the game sends ~60
packets/s, ~85 kbit/s); at most 100 relay sessions. A session closes when its
match ends (result, cancel or the 3 h limit); one left idle for 120 s after its
match is gone is swept up.

Not handled: UDP blocked entirely (the match is cancelled with
`udp_unreachable` and the player is told to check the firewall); IPv6 (the
netplay layer is IPv4-only too); two symmetric NATs with random ports and no
router forward on either side (relay).

### Regional relays

(1.1.1; setting up a node: docs/HOSTING.md "Adding a relay server"; code: `server/relays.py`,
`server/relaynode.py`, `relayctl.py`.) The relay above sits in the lobby server, wherever that is:
two players far from it -- both in California, the server in Nuremberg -- get California -> Germany
-> California, 300-400 ms. **Relay-only nodes** in other regions take that detour away; the lobby,
accounts and ranking stay on the one central server.

*Which relay.* The path through a relay is player A -> relay -> player B, so its round trip is the sum
of both players' round trips to the relay. A client with the `relays` cap gets the list of nodes in
`welcome` (`relays: [{id, name, host, port}]`), measures its UDP round trip to each (SPING, as to the
server) in the background after login and every 5 minutes between matches, and reports it
(`relay_rtt {rtts: {id: ms}}`); its round trip to the server itself is its `udp_rtt`. When a match
needs a relay, the server takes the relay with the smallest sum -- its own one is a candidate like
any other (a tie goes to it) -- among the nodes that are up and that both players reached. A pair
with an older client gets the server's own relay, exactly as before (an older client binds to the
lobby server's address and nowhere else).

*Opening a session on a node.* The central server asks the node over the control channel (below) to
open a session with two fresh 16-byte bind tokens and a lease (the match time limit + 2 minutes). A
node that is full answers so, one that does not answer within 1.5 s is marked down; either way the
next relay in the order is tried, down to the server's own. Then both clients get `nat_relay` with
`relay {id, name, host, port}` and their `relay_token`; each binds its game socket to the node
(`RELAY_BIND` with that token, the same packet as for the server's relay), measures the path through it
and reports `nat_result` as usual; `match_start` carries `relay` too, and the game (or the relay bridge)
talks to the node. A bind token works for `T5L_RELAY_BIND_SECONDS` (60) after the session opened.
When the match ends, the server closes the session (after the rematch window, like its own); a
rematch inside the running games keeps it and renews its lease. Between two `nat2` clients the relay
bridge works the same with a node: the match moves onto the direct path when it starts to work.

*Health.* The central server sends every node a `status` request every `T5L_RELAY_CHECK_SECONDS` (5);
a node that has not answered for `T5L_RELAY_DEAD_SECONDS` (20) is down: no new sessions until it
answers again. relays.json is read again when it changes; clients with the cap get the new list
(`relays`) and measure it.

*The control channel* (`relayctl.py`): UDP datagrams to the node's relay port,
`"T5RC" | version 1 | kind (1 request, 2 reply) | JSON | HMAC-SHA256` over everything before the MAC,
under a secret the two machines share (a file on each, never in the repository). A request carries
`op` (`status`, `open {sid, tokens, lease}`, `renew {sid, lease}`, `info {sid}`, `close {sid}`), a
random `id`, the sender's clock `ts` and the node's `node` id. The node takes it only with a valid MAC,
a `ts` within 120 s of its own clock (an authentic request outside that window gets one `clock`
answer, so the operator learns why), an `id` it has not seen and its own id; with
`T5L_RELAY_CENTRAL` only from the central server's address. The answer carries `re` (the request's
id) and is signed the same way; the central server takes only answers to its open requests, from the
address it asked. Each retry is a new datagram with a new id; the operations are idempotent.

*What a node relays*: the server relay's rules (server/udp.py, shared code) -- only between the two
endpoints that bound with a session's tokens, only the game's packets and the lobby's peer packets, at
most `T5L_RELAY_MAX_BYTES`, per-player packet and bandwidth caps, `T5L_MAX_RELAYS` sessions,
`T5L_MAX_RELAYS_PER_IP` sessions per internet address (checked at the bind), the lease (never more
than its own `T5L_RELAY_MAX_SECONDS` at a time), 120 s without a packet closes a session, and a
closed session's id cannot be opened again. A stranger gets answers to UDP pings (never larger than
the ping) and nothing else.

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

## Friends and invites

(1.1.2; code: `server/lobby.py` "friends", `server/store.py`, `client.py`, the Friends page in `tk_tab.py` /
`tk_views.py`.) Like a console friends list. **Accounts only**: a guest has no account to keep friends on, so the
server refuses every friends message from a guest ("guests cannot have friends; create an account (free)"), and a
guest's name is not an account name anyone can add.

**Adding a friend.** Type the other player's account name on the Online tab's **Friends** page and press **Send
request**. They see "X wants to be your friend" and the request under REQUESTS; **Accept** makes you friends (on
both lists at once), **Decline** tells you so. If they had asked you already, your request is their answer: you are
friends at once. You can take back a request that waits (**Take back**). A request nobody answers runs out after 14
days.

**The list.** Each friend shows as online (in the lobby, in a room, searching), in a match, or offline ("last seen"),
with their rank. It changes by itself: the server pushes every change with the lobby updates (at most ~3 a second).
The tab name shows the requests waiting for you: "Friends (2)".

**Removing.** Select a friend, **Remove**. The other side's list changes too; nobody is told more.

**Invites.** Select a friend who is online and press **Invite to a match** (a casual match) or, when you are in a
room of your own, **Invite to my room**. They get a question like a challenge: "X invites you to a casual match"
with **Accept (A)** / **Decline (B)**. **One click starts it**: a casual match begins without a ready check (both of
you said yes already); for a room invite they join your room and the room's match starts at once. An invite waits 60
seconds, then runs out; your button reads **Cancel the invite** meanwhile. An invite ends when either of you starts
another match, leaves, or logs out. Only casual matches: ranked comes from the ranked queue (or a ranked room, which
a room invite can be).

**Limits** (against spam, all in `server/config.py`):

| | Default | Variable |
|---|---|---|
| friends per account | 100 | `T5L_MAX_FRIENDS` |
| friend requests an account sends per 24 hours (answered or not) | 20 | `T5L_FRIEND_REQUESTS_DAY` |
| requests waiting for an answer, sent by one account, and to one account | 30 | `T5L_FRIEND_PENDING` |
| an unanswered request runs out after | 14 days | `T5L_FRIEND_REQUEST_DAYS` |
| after a decline, the same request again only after | 7 days | `T5L_FRIEND_RETRY_DAYS` |
| an invite waits for an answer | 60 s | `T5L_INVITE_SECONDS` |
| invites | one at a time per player, one per 2 s, at most 3 waiting for one player | |

The requests and invites also count against the usual per-connection limits (2 requests a second, burst 20).

**Blocks override friendship.** Blocking a friend ends the friendship and cancels every request and invite between
the two. Unblocking does not make you friends again. A request from you to someone who blocked you is never shown to
them: it looks like a request nobody answers, and it runs out. You cannot ask someone you blocked yourself ("unblock
them first").

**Older launchers.** Everything above is switched on by the client: a launcher announces the `friends` cap in
`hello`, and the server sends friends messages only to such clients (`welcome.features` lists `friends` so a new
launcher knows the server has them). A 1.1.0 or 1.1.1 launcher logs in, plays and is matched exactly as before and
never receives one of the new messages, also when its account has friends (they see it online, with "older launcher:
no invites"). A new launcher on an older server finds no `friends` feature and the Friends page says the server
does not have them.

**Storage.** Two tables, added by the first numbered schema migration (`PRAGMA user_version` 1; `store.MIGRATIONS`):
`friends` (one row per direction) and `friend_requests` (with their state: pending, accepted, declined, cancelled,
expired; answered ones are deleted after 60 days). The migration runs once, at the server's first start after the
update, in one transaction with the version number. A database from a newer server is used as it is, and the 1.1.0
server still opens an upgraded database (tested), so going back to an older release works. Deleting an account
(admin tool) deletes its friends and requests.

## Discord Rich Presence

Optional, **off by default**: launcher **Settings -> Discord -> "Show what I play in my Discord status"**. Then the
player's Discord status reads "Playing T5DR Online" with one of

| State | Discord shows |
|---|---|
| logged in, in the lobby or a room | In lobby |
| searching | Searching ranked / Searching quick match |
| in a match | In match: Jin vs Kazuya (Ranked, Set 1-0) -- your fighter first, the ranked set's score from your side; (Casual) for other matches; "In match (Ranked)" while the fighters are still being picked |

and the time since that state began. Not logged in: nothing. The texts follow the launcher's language.

How (`lobby/t5lobby/discord_rpc.py`, pure Python, no Discord SDK): the launcher talks to the **Discord app on the
same PC** over its documented local IPC pipe, `\\.\pipe\discord-ipc-0` to `-9` (a Unix socket of that name on
Linux / macOS): a handshake with the application id, then `SET_ACTIVITY` frames. Nothing goes over the network from
the launcher; Discord shows the status to the player's Discord friends. A background thread does the talking: at
most one update per 4 seconds (Discord's own limit is 5 per 20 s), the newest state wins, Discord's PING is answered,
the activity is taken down when the setting is turned off or the launcher closes. **Without Discord running it does
nothing**: it looks for the pipe every 20 seconds, quietly (one line in launcher.log, no message to the player).
When Discord starts later, or restarts, the status appears by itself.

**The application id.** Discord names the game after a Discord *application*, which the person who ships the launcher
creates once. The id is a config value: `application_id` in `lobby/t5lobby/data/discord.json` (shipped with the
release; empty = Rich Presence does nothing and Settings says so), overridden per player by `"discord_app_id"` in
launcher.json, and by the environment variable `T5_DISCORD_APP_ID`.

Creating the application (the owner, once, about 5 minutes; nobody else can do this for you):

1. Open https://discord.com/developers/applications and log in with your Discord account.
2. **New Application**. Name: **T5DR Online** (this is the name players see after "Playing"). Accept Discord's
   developer terms. Create.
3. On the **General Information** page copy the **Application ID** (a long number).
4. Put it into `lobby/t5lobby/data/discord.json` as `"application_id": "<the number>"` and commit; the next release
   carries it. (To try it first: launcher.json `"discord_app_id"`, or `T5_DISCORD_APP_ID` in the environment.)
5. Optional, a picture next to the status: **Rich Presence -> Art Assets -> Add Image(s)**, upload your own logo
   (512 x 512 or larger) -- never art taken from the game -- and name the asset, e.g. `logo`; then set
   `"large_image": "logo"` in the same file. Without it the status has no picture.
6. Check: Discord running on your PC, the setting on, log in to the Online tab -- your Discord profile shows "In
   lobby" within a few seconds. `python -m t5lobby.discord_rpc <application id>` (in `lobby/`) shows "In lobby" for
   30 seconds without the launcher.

The application needs no bot, no OAuth redirect and no secret; the id is not a secret either (every Discord status
shows it to anyone who looks).

## Protocol reference

### Control channel

TCP (optionally TLS), one JSON object per line, UTF-8, at most 8 KiB per line
from a client. Every message has `"t"`. A request may carry `"rid"` (integer);
the reply carries it back as `"re"` (`{"t":"ok"}` when there is nothing else to
say, `{"t":"error","code":...,"msg":...}` on refusal).

Client to server:

| t | fields | reply / effect |
|---|---|---|
| `hello` | `proto`, `client`, `build: {elf, code, net, release, id}`, `caps` (optional: `delta`, `blind_ready`, `notices`, `ingame_pick`, `sets`, `nat2`, `relays`, `friends`) | `welcome {server, proto, udp_port, udp_port2, build, accounts, guests, motd, ip, time, ..., caps, relay_only}`; with the `relays` cap also `relays [{id, name, host, port}]` (regional relays); with the `friends` cap also `friend_limits {max, per_day, invite_seconds}` |
| `login` | `mode: guest\|account\|register\|resume`, `name`, `password`, `token` | `login_ok {you, token, resumed?}` |
| `ping` | | `pong {time}` (keepalive; silent clients are dropped after 90 s) |
| `udp_rtt` | `ms` | the client's UDP ping to the server (lobby list, matchmaking) |
| `relay_rtt` | `rtts {id: ms}` (`relays` cap) | none: the client's UDP round trips to the regional relays; one it could not reach is left out (and never chosen for its matches) |
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
| `nat_local` | `match`, `addrs [[ip,port]]`, `nat: eim\|symmetric\|unknown`, `port`, `mapped [ip, port]` (nat2: the game port's router forward) | |
| `nat_result` | `match`, `phase: punch\|relay`, `ok`, `peer`, `kind`, `rtt_ms`, `jitter_ms` | |
| `game_started` | `match` | |
| `result` | `match`, `winner: 0\|1\|null`, `score: [p1, p2]`, `chars` (in-game select: the fighters), `costumes` (their confirm buttons, kept by a ranked set) | `result_ack`; the other player gets `notice result_pending` |
| `leave_match` | `match` | cancels before start; a loss report while playing |
| `block` / `unblock` / `blocks` | `name` (or `player`) | `blocked` / `unblocked` / `blocks {rows}`; a match with that player ends like a quit |
| `leave_set` | `reason` (`lag`) | leave the games in a row between two games, no penalty; `set_end` to both |
| `lag` | `match`, `frames`, `waited_ms`, `pc_fps`, `fps` | after a match; both players then get `lag_check` |
| `nat_punching` | `match` (nat2, `plan.wait_peer`) | none: this side's planned punch has started; the other side gets `nat_peer_punching` |
| `nat_upgrade` | `match`, `path: direct\|relay`, `rtt_ms` (nat2) | none: a relayed match moved onto the direct path (or back), for the log and the `relay_upgrades` counter |
| `friends` | (`friends` cap, accounts) | `friends {friends [{name, status: online\|in_match\|offline, activity, invite: ok\|busy\|offline\|update\|version, since, last_seen, rating, rank, tier, ...}], incoming [{name, time}], outgoing [{name, time}], max, requests_left}` |
| `friend_add` | `name` (an account) | `friend_added {name, state: pending\|friends}`; the other side gets `friend_request {name, time}` |
| `friend_answer` | `name`, `accept` | `ok`; the asker gets `friend_update {name, state: accepted\|declined}` |
| `friend_cancel` / `friend_remove` | `name` | `ok` (take back a request / end a friendship) |
| `invite` | `name` (a friend online), `kind: casual\|room` | `invite_sent {invite, name, kind, expires}`; the friend gets `invited` |
| `invite_answer` | `invite`, `accept` | accepted: casual -> `match_found` (origin `invite`, no ready check) for both; room -> `room {room}` and the room's match starts (origin `invite`, no ready check) |
| `invite_cancel` | `invite` | `ok`; both get `invite_update` |
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
| `nat_begin` | `match`, `token` (hex, secret), `tag` (hex, shared by both players), `side`, `udp_port`, `udp_port2`, `nat2` (the server plans the punch) |
| `nat_punch` | `match`, `candidates [{ip, port, kind: local\|mapped\|public}]`, `timeout`; to a `nat2` client also `plan {start_at, start_in, window, interval, slow_start, ttl_open, wait_peer, scan [{ip, ports}]}` (docs/NETPLAY.md "Getting a direct connection"); `retry` on the one second chance |
| `nat_peer_punching` | `match`: the opponent's planned punch has started (its NAT is open toward us) |
| `nat_relay` | `match`, `udp_port`, `reason`, `bridge` (both clients `nat2`: keep the game socket in the launcher and upgrade to the direct path when it works); on a regional relay (both clients `relays`) also `relay {id, name, host, port}` and `relay_token` (hex: bind there with it instead of the match token) |
| `relays` | `relays [{id, name, host, port}]`: the regional relays changed (clients with the `relays` cap measure them again) |
| `match_start` | `match`, `role`, `slot`, `path`, `peer`, `relay_port`, `relay {id, name, host, port}` (a regional relay), `rtt_ms`, `jitter_ms`, `delay`, `rounds`, `ranked`, `build`, `opponent`, `seed`, `fight {p1, p2, stage, rounds, pick}` |
| `match_cancel` | `match`, `reason: declined\|ready_timeout\|opponent_left\|udp_unreachable\|no_connection\|relay_full`, `you` (true = because of you) |
| `match_result` | `match`, `status`, `winner`, `score`, `ranked`, `rating {before, after, delta}`, `you` |
| `set_end` | `set`, `reason: declined\|left\|lag\|expired\|cancelled`, `by: you\|opponent\|null` |
| `lag_check` | after a match, to both players: ping, expected and observed frames behind, verdict, cause, a sentence (RANKED.md) |
| `server_notice` | `id`, `text`, `expires`, `cleared` -- a message from the admin tool (clients without the `notices` cap get a `notice` instead) |
| `notice` | `code`, `msg` (never contains an IP address) |
| `friends` | clients with the `friends` cap: the whole list (as the `friends` reply) after login and whenever it changed |
| `friend_status` | `name`, `status`, `activity`, `invite`: a friend came online, went into a match, went offline ... |
| `friend_request` / `friend_update` | someone asks you; the answer to your request (`state: accepted\|declined`) |
| `invited` | `invite`, `from` (brief), `kind: casual\|room`, `room {id, name, ranked}`, `expires` |
| `invite_update` | `invite`, `state: accepted\|declined\|cancelled\|expired`, `name` (the other side), `kind` |
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

A regional relay node (`server/relaynode.py`) answers `SPING` and `RELAY_BIND` the same way and nothing
else of this table; the central server's control datagrams to it start with `T5RC` ("Regional relays").

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
- **Regional relay nodes** take orders only from the central server: every control datagram is signed
  (HMAC-SHA256, shared secret), fresh (timestamp, one-time id) and meant for that node; a session
  exists only when the central server opened it, and its bind tokens work for a minute. Nobody can use
  a node as a proxy (above, "Regional relays").
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
| `T5L_UDP_PORT2` | `7782` | NAT probe port; `0` = off (symmetric NATs are then only found by failing to punch, and their ports are never predicted) |
| `T5L_DB` | `t5lobby.db` | SQLite file; back it up to keep accounts and ratings |
| `T5L_MOTD` | | message shown after login |
| `T5L_ACCOUNTS` / `T5L_GUESTS` | `1` / `1` | allow accounts / guests |
| `T5L_GUEST_RANKED` | `0` | guests in the ranked queue (their rating lasts the session) |
| `T5L_BUILDS` | | comma-separated build ids to accept; empty = any (pairing still requires equal builds) |
| `T5L_TLS_CERT` / `T5L_TLS_KEY` | | PEM files: control channel over TLS |
| `T5L_RELAY` / `T5L_FORCE_RELAY` | `1` / `0` | offer the relay / use only the relay |
| `T5L_RELAY_KBPS` / `T5L_RELAY_PPS` / `T5L_MAX_RELAYS` | `512` / `400` / `100` | relay caps |
| `T5L_RELAYS` / `T5L_RELAY_SECRET_FILE` | | regional relay nodes: relays.json (a file, re-read when it changes, or the JSON itself) / the secret for nodes without their own ("Regional relays") |
| `T5L_RELAY_CHECK_SECONDS` / `T5L_RELAY_DEAD_SECONDS` | `5` / `20` | health check of every node, and the silence after which a node gets no new matches |
| relay node: `T5L_RELAY_SECRET_FILE`, `T5L_RELAY_ID`, `T5L_RELAY_CENTRAL`, `T5L_RELAY_BIND_SECONDS` | `60` (the last) | `python run.py relay`: its secret, its id in relays.json, the central server's address(es) (optional), how long a session's bind tokens work |
| `T5L_MAX_CLIENTS` / `T5L_MAX_PER_IP` | `500` / `8` | connection caps (raise MAX_PER_IP for LAN parties behind one router) |
| `T5L_READY_TIMEOUT`, `T5L_PUNCH_TIMEOUT`, `T5L_RELAY_TIMEOUT`, `T5L_RESULT_TIMEOUT` | 15, 6, 6, 90 s | (the punch window was 3 s up to 1.1.0) |
| `T5L_PUNCH_TTL_OPEN` / `T5L_PREDICT_PORTS` / `T5L_RELAY_UPGRADE` | `0.5` / `24` / `1` | low-TTL opening of each side's own NAT (s), ports tried after a symmetric NAT's last one, relayed matches of two new clients move onto the direct path when it works (docs/NETPLAY.md "Getting a direct connection") |
| `T5L_BLIND_READY` | `1` | queue matches show only the ping until both accepted |
| `T5L_INGAME_PICK` | `30` | seconds to pick the fighter on the game's own select screen (both clients must be able to); `0` = the launchers' characters |
| `T5L_STRICT_RANGE` / `T5L_PAIR_COOLDOWN` / `T5L_MAX_BLOCKS` | `150` / `30` / `200` | strict matchmaking range, same-opponent cooldown (s), blocks per player |
| `T5L_MAX_FRIENDS` / `T5L_FRIEND_REQUESTS_DAY` / `T5L_FRIEND_PENDING` | `100` / `20` / `30` | friends per account, requests sent per 24 h, requests waiting per sender and per receiver ("Friends and invites") |
| `T5L_FRIEND_REQUEST_DAYS` / `T5L_FRIEND_RETRY_DAYS` / `T5L_INVITE_SECONDS` | `14` / `7` / `60` | an unanswered request runs out; a declined one may be repeated after; an invite waits |
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
python -m unittest discover -s lobby/tests          # ~350 tests, ~6 min, all on localhost
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

**Friends** (`test_friends.py`): requests, accepting and declining, both asking at once, taking back, removing,
the list with presence (online, searching, in a match, offline, another build, an older launcher), the limits
(per day, waiting, list size, a full inbox, running out), blocks ending a friendship and hiding requests, invites
(casual and room with one click, declined, cancelled, run out, who can be invited, a queue match ending one), a
restart keeping friendships, the schema migration (old, oldest, newer, a failed step, deleting an account, the
1.1.0 server on an upgraded database), and the 1.1.0 and 1.1.1 clients (from git) and the 1.1.0 server.
`test_tk_friends.py`: the Friends page and invites in the Online tab (no visible window) and Rich Presence fed by
the tab. **Discord** (`test_discord.py`): the IPC frames against a fake Discord on a test-only pipe (never the
real Discord's): handshake, updates, taking it down, the rate limit, PING, no Discord, Discord starting later and
restarting, a refused application id, the configuration, the texts in English and German.

**Regional relays** (`test_relays.py`, `lobby/tools/relay_e2e.py`): the control channel, the relay node's
limits, the choice by the sum of both round trips, dead / silent / full nodes, relays.json changes, the
direct upgrade from a regional relay, compatibility with the 1.1.0 client and server from git; the tool
runs a central server and two nodes as processes with UDP delay proxies between each player and each
relay, and plays stub games (or `--exe t5dr.exe`) through the chosen one:

```sh
python lobby/tools/relay_e2e.py                       # scenarios best, dead, old (~1 min)
```

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

## How the Online tab looks

One dark theme for the whole launcher (`lobby/t5lobby/theme.py`, plain Tk 8.6: no image files, no game
assets; Segoe UI and Bahnschrift). The Online tab (`tk_views.py`, driven by the state in `tk_tab.py`)
shows one card at a time next to the player's profile card (name, rank badge drawn in the tier's
colour, rating, W-L):

| State | The card |
|---|---|
| Not logged in | Server, name, then Log in / Create account (password rules checked as you type) / Guest; Host for friends |
| In the lobby | Ranked match and Quick match, the character, Strict; the players, rooms (a lock = cannot be joined now) and chat below |
| Searching | A turning ring, the time searching, the queues, Stop searching (B) |
| Match found | Ping bars (green up to 60 ms, yellow up to 120, red above), a 15 s countdown ring, Accept (A) / Decline (B); the opponent is shown once both accepted |
| In a match | The opponent, ping, input delay, connection, "Your game is running" and where the game is |
| Result | Win / loss banner, rounds, rating change, promotion / demotion / placement, lag check, Rematch (A) / Next game / Leave (B) / Block |
| Errors | One line on a red banner: what went wrong and what to do |
| Friends (a page next to Lobby, Leaderboard, Profile) | Your friends with a dot (green online, yellow in a match, grey ring offline), rank and what they do; Invite to a match / Invite to my room / Remove; Add a friend (account name); REQUESTS with Accept / Decline / Take back |
| Invite from a friend | Their badge and name, "invites you to a casual match" (or "to the room ..."), Accept (A) / Decline (B) |

A ranked set's score goes into `OnlineTab.set_var` ("Set 1-0, game 2 of 3"); the match cards show it as a
tag. Tests: `tests/test_online_ui_walk.py` walks the launcher through every state (local server, two
CLI clients, scripted players) and fails on any error in launcher.log; with `T5_UI_SHOTS=<dir>` it also
saves a picture of each state (run that on a desktop nobody looks at: the window is mapped, transparent).

## Controller in the launcher

The Online tab runs with a pad or an arcade stick, no mouse or keyboard needed once you are logged in
("Remember me" logs you in by itself). Like Tekken 6 Native Online.

| Button | What it does |
|---|---|
| **A** (Cross) | Accept a found match, a challenge or a friend's invite. Rematch (also when the opponent offers one). Search: ranked for an account at first, quick for a guest, afterwards the kind you searched last. After you left a game (B), A is "back to ranked". |
| **B** (Circle) | Decline a found match, a challenge or a friend's invite. Leave / No thanks after a game. Stop searching. |
| **Y** (Triangle) | Nothing. Every match gets a random stage from the server, a rematch too, so there is no stage to choose. (The fighter is picked in the game itself, with the game's controls.) |

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
  is read once, through XInput. (The game reads DualShock 4 / DualSense as HID devices since ps3recomp patch
  0042; WinMM, like DirectInput, gets nothing from a Bluetooth pad that Steam or DS4Windows switched to its
  extended report, so the launcher does not see such a pad until it is turned off and on.) Plain `ctypes`, one thread, 60 polls a second while the launcher is in front
  (measured with a real XInput pad: 0.7% of one core), 20 looks at the foreground window a second while it is
  not (0.01%).
- Switch: **Use a controller here** at the bottom of the tab (saved as `pad` in `online.json`).
  `T5_PAD_NAV=0` in the environment turns the feature off.
- With `background = 1` in `controls.ini` (the default) a running game reads the pad too, also while the
  launcher is in front: a press that accepts a match is also a Cross in the game, which waits at its
  character select. Set `background = 0` if that gets in the way.
- Test hook: `T5_PAD_FILE=<file>` makes a virtual pad of the buttons named in the file (`A`, or
  `dinput:054C:09CC B2`); with it the real pads are ignored (`T5_PAD_DEVICES=1`: both).
- Setting the buttons: Settings -> **Set up controllers...** (`launcher/controls_ui.py`, `launcher/controls_edit.py`)
  writes the same `controls.ini` the game and this tab read; it uses padnav's device readers and the same foreground
  rule (nothing is read unless its window is in front). The tab picks up a saved change by itself (it reads the file
  again when it changes).
- Code: `lobby/t5lobby/padmap.py` (controls.ini), `lobby/t5lobby/padnav.py` (devices, polling rules, thread),
  `lobby/t5lobby/tk_tab.py` (what each button does). Tests: `lobby/tests/test_padnav.py`,
  `lobby/tests/test_tk_pad.py`, `tests/test_padmap_sync.py`; they use a fake pad and a fake clock.
  Not tried with a real stick yet (the XInput pad on the development PC was only read, not pressed).

## Languages

The launcher and the Online tab speak English and German (Settings -> Language; Auto follows Windows).
`lobby/t5lobby/i18n.py` has the lookup: `t("English text", name=value)`; the English text is the key, the German
catalog is `i18n_de.py`. The lobby server stays English and sends English: its error texts, notices and kick
reasons carry a `code` or a fixed sentence, and the client puts the sentences it knows into German
(`i18n.translate_message`, the list is `i18n_known.py`; an unknown sentence is shown as it came). The lag
check is built on the client from the numbers in the `lag_check` event (`lag.describe_event`), not from its
`text`. A new server message, client error or build-tool error needs an entry in `i18n_known.py` and a
German text; `python tools/i18n_extract.py` lists what is missing and `tests/test_i18n.py` fails until it
is there.

## What is left

- Netplay side of the handover extras above: socket adoption (everything else is done).
- The persistent game starts with the first match; starting it already when the player
  queues would make the first match as quick as the later ones.
- TURN-style relay on a separate host, or several relay regions; today the relay is the lobby server.
- IPv6. (Port prediction for symmetric NATs and the game port's router forward came with 1.1.1;
  PCP / NAT-PMP / UPnP are so far tested against fake routers only.)
- The lobby list still goes to everybody (deltas made it ~26x cheaper); past several hundred
  players it needs paging or interest filtering.
- Moderation beyond the admin tool (docs/HOSTING.md): in-game reporting of cheaters, a kick
  without a ban.
- Relay sessions do not survive a server restart (relayed games in progress break).
- Spectating, replays, region tags. (Friends came with 1.1.2: "Friends and invites".)
- The server has not been run on a real VPS or across two real NATs yet; everything above was
  measured on localhost.
