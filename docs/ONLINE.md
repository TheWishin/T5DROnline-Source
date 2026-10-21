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
- [Rooms](#rooms) (classic, community rooms that take turns, private rooms with a password or an invite code)
- [Friends and invites](#friends-and-invites)
- [Discord Rich Presence](#discord-rich-presence)
- [Chime and taskbar flash](#chime-and-taskbar-flash)
- Tournaments: their own page, [TOURNAMENTS.md](TOURNAMENTS.md)
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
    notify.py     the chime (made in code) and the taskbar flash for a player who is elsewhere, and their rules
    tk_tab.py     the launcher's Online tab (tkinter): its logic and state; launcher/online.py imports it
    tk_views.py   the Online tab's screens: login, lobby, searching, match found, in match, result, errors
    tk_tour.py    the Online tab's Tournaments page, bracket canvas, Create window, "Your tournament set is ready"
    tk_rooms.py   the Online tab's rooms: Create room window, locked-room join, the room's row (line, Sit out,
                  Room settings, Copy invite code)
    tour_client.py, tour_text.py  the client's tournament calls; their texts (docs/TOURNAMENTS.md)
    theme.py      the launcher's dark look: ttk theme, fonts, drawn badges / ping bars / countdown ring
    padnav.py     controller buttons for the tab: XInput, PlayStation (HID) and WinMM readers, the polling
                  thread and its rules
    padmap.py     the game's controls.ini (Cross / Circle / Triangle of each pad) for padnav
    cli.py        python -m t5lobby.cli: the same from a console
    servers.py    servers.json: the launcher's server list, typed addresses (host:port#fingerprint)
    portmap.py    opt-in UPnP IGD / NAT-PMP port forwarding for "Host for friends"
    server/       python -m t5lobby.server
      lobby.py    players, rooms, queues, challenges, matches, results, bans, status numbers
      rooms.py    rooms: classic, community (a line that takes turns), private (password / invite code, hidden)
      tournaments.py, bracket.py  community tournaments: sign-up, calls, sets, organizer actions; the brackets
      udp.py      UDP ping, endpoint registration, NAT probe, relay
      store.py    SQLite: accounts (scrypt hashes), sessions, recovery codes, ratings, ranks, history, bans,
                  blocked players, server notices, friends and friend requests; numbered schema migrations
      admin.py    python -m t5lobby.server.admin: status, users, bans, passwords, recovery codes,
                  backups, certificates (accounts_admin.py: the account commands alone)
      status.py   local HTTP /health, /status, /metrics, /tournaments (the brackets for streamers)
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
     (the best relay path: the smallest sum of both players' round trips to a relay, the
     server's own included -- docs/RANKED.md "Found match"), within a ping window that grows
     while they wait (80 ms + 20 per second; any ping after 30 s).
   - *Ranked*: pairs by rating and ping; the allowed rating gap grows while you
     wait (100 points + 25 per second, at most 800) and so does the allowed
     ping (80 ms + 10 per second; any ping after 60 s). Accounts only (configurable).
     The *strict* option keeps the gap at 150 points. The same two players are not
     paired again for 30 s after a ranked game.
   - Players who blocked each other are never paired by any of these.
   - *Rooms*: create one, someone joins -- also locked with a password or an invite code, or for up to 8
     players who take turns ([Rooms](#rooms)); *challenges*: pick a player, they accept.
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
   **No pause** (1.1.2): neither player can pause the fight -- both games take START out of
   both players' inputs (docs/NETPLAY.md "No pause online"). START still skips the replay
   after a round, and the games skip the last replay and the win pose by themselves. Quitting a
   match is closing the game (Esc twice, Alt+F4, the window's X), which counts as a loss
   (forfeit) as before; the launcher's Leave / Leave set after a game works as before.
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
The game's packets cross the bridge on a thread of its own (1.1.4, "the pump": `nat.RelayBridge`), raised to
the priority of the game's own network thread, not on the lobby client's event loop at normal priority: on a
PC whose processors the game keeps busy the old way held a packet for a whole time slice now and then (two
passes per round trip: p50 5.7 ms, p95 13 ms, max 26 ms added; with the pump 0.2 / 0.3 / 1.9 ms --
`lobby/tools/bridge_latency.py --hog 4 --cpus 2`), on both PCs of every relayed match. Launcher only: the
relay server sees the same packets as before (docs/NETPLAY.md "Relayed matches").

If a NAT re-maps the game's port between the launcher's bind and the game's
first packet, game traffic (`T5NP` magic) from the same IP is accepted for the
bound side that has gone quiet for 2 s. Strangers are dropped.

Relay limits per player: 400 packets/s and 512 kbit/s (the game sends ~60
packets/s, ~85 kbit/s); at most 100 relay sessions. A session closes when its
match ends (result, cancel or the 3 h limit); one left idle for 120 s after its
match is gone is swept up.

A game that hears nothing on the direct path (1.1.3, cap `game_fallback`): the
launchers' sockets reached each other, but a firewall on one PC drops what
arrives for `t5dr.exe` itself. After 15 s of "nothing arrived yet" in its log
the launcher sends `nat_fallback`; the server moves the running match onto the
relay (`nat_relay` with `fallback: true`: both launchers bind a new socket with
the match's token, keep it as the relay bridge) and sends a second
`match_start` for the same match -- the games start its session again, talking
only to 127.0.0.1. Once per match, within `T5L_GAME_FALLBACK` seconds of the
start, before any result (docs/NETPLAY.md "When Windows Firewall blocks the
game").

Not handled: UDP blocked entirely (the match is cancelled with
`udp_unreachable` and the player is told to check the firewall; the Online tab
shows its firewall hint); IPv6 (the netplay layer is IPv4-only too); two
symmetric NATs with random ports and no router forward on either side (relay).

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
(`relay_rtt {rtts: {id: ms}}`); its round trip to the server itself is its `udp_rtt`. A changed list
(`relays` pushed by the server) is measured again, one measurement at a time and at most one per 5 s, and
only entries with an IP address and a port 1-65535 are pinged: a server cannot make the launcher send
pings wherever and as often as it likes (1.1.2). When a match
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

## Rooms

(Code: `server/rooms.py`, `client.py`, the launcher's `tk_rooms.py`. Private and community rooms: 1.1.3, capability
and feature `private_rooms`.) A room is where players meet by choice instead of by the queue. Three kinds:

**Classic room** (2 players; what every launcher before 1.1.3 makes, and still the default). The match starts when the
second player joins (with the ready check; right after a friend accepted an invite into it, without one). Afterwards
the two pick **Rematch** (the running games go on) or one presses Ready again for a new match. Ranked rooms are
classic rooms.

**Community room** (3 to 8 players, `T5L_ROOM_MAX_SIZE`). The room keeps a **line**, the turn order: the first two in it
play (with the ready check, always), the others wait in the room. When a match has a result the line moves on by the
room's rule and the next match starts by itself after `T5L_ROOM_NEXT_SECONDS` (8 s) -- nobody votes for a rematch:

| rule (Create room -> Turns) | after a match |
|---|---|
| **Winner stays** (`winner`, default) | the loser goes to the back of the line, the next one plays the winner. No winner (void, draw): both go to the back |
| **Everyone in turn** (`queue`) | whoever wins, the player who was at the table longer goes to the back and the other plays the next one in line: everyone plays two in a row, against both neighbours in the line (with three players everyone meets everyone) |

Who declines the ready check or lets it run out **sits out**: they stay in the room, the line skips them, they are
told ("you sit out in the room; press Back in line to play again"). **Sit out** does the same on purpose, **Back in
line** puts a player at the end of the line again. A connection that cannot be set up puts both players at the back.
With only two in the line it is the same two again after the pause.

Why this model: rooms already were "the players chose each other" (no queue, a ready check, rematches inside the
running games); a community room keeps all of that and only adds who plays next. The server decides it (one line per
room, the same for everyone, shown to every member), so no launcher can skip the line, and an AFK member does not
stop the room (the ready check finds them). Rematch votes would let two members keep the table for ever, so a
community room has none.

**Private room** (a classic or a community room). Locked with a **password** (4-64 characters, any script, no space
at either end) or an **invite code** the server makes (`XXXX-XXXX-XXXX`, ~59 bits, no 0/O/1/I/L). The room list shows
it locked: its name, host, players and "private", with the lock icon -- or, **hidden**, not at all (its members show
as "in a room", not which one). Joining needs the password (Join room asks for it, in a masked field) or the code
(Join room with no room selected asks for one; a hidden room is found by its code alone). A friend's **invite** into
the room (Friends -> Invite to my room, any member can send one) is the key: the friend joins without the password,
and no secret is sent to them. Only the room's **members can watch** its match (also not the players' friends);
locking a room sends the spectators who are not members away. Private and community rooms are **casual** (who plays
whom is the room's business -- what ranked keeps out). The host's **Room settings...** changes the password, makes
a new invite code (the old one stops working), removes the lock, hides or shows the room, and **removes a player**:
not while they play the room's running match; they cannot come back into that room (with the password, the code or an
invite). When the host leaves, the member who came next is the host (a code room's new host makes a new code).

**Copy invite code** (in the room's row under the rooms list) puts the code into the launcher's own field next to the
button and selects it there -- nothing goes to the system clipboard by itself; the player presses Ctrl+C when they want
it (the field does not export its selection either). The code is shown only after that press, and only the host's
launcher (the one that made it) and launchers that joined with it know it.

**Security** (the patterns of lobby.py's accounts, invites and ready checks):

- The password is kept only as a **salted scrypt hash** (`store.hash_password`, 16-byte salt, on a worker thread behind
  `T5L_PW_CONCURRENCY`), **in memory** (never in the database), checked with a **constant-time compare**
  (`hmac.compare_digest`). An invite code is kept only as its HMAC-SHA256 under a key made when the server starts
  (the index that finds a room by its code); a server restart ends all rooms anyway.
- **Wrong guesses** (a wrong password, a wrong code, a malformed one) are limited per player (5, then one per
  `T5L_ROOM_GUESS_SECONDS`, 30 s), per internet address (10, then one per 15 s; IPv6 per /64, and 20 per /56 and 40
  per /48 around it, so the 256 /64s of one /56 are not 256 budgets) and per room. A room's budget comes in two parts
  (hardening 1.1.4): every network that guesses -- an IPv4 address, an IPv6 /48 -- has its own lane at that room
  (`T5L_ROOM_LANE_GUESSES` 3, then one per `T5L_ROOM_LANE_SECONDS`, 20 minutes), spent first; only then comes the
  room's shared budget (20, then one per 10 s). Guessers from many addresses can use up the shared budget, never
  another network's lane: a member who types the right password gets in while the room is being guessed at (in
  1.1.3 the empty shared budget answered everybody "try again in N s"), and a friend's invite and an invite code
  work as always. Brute force stays bounded per room: the shared budget, plus three guesses per network and 20
  minutes. The host of a password room sees under the room "Wrong passwords in the last 10 minutes: N (networks: M)"
  (never who or from where) and **Room settings -> Turn away the guessers** (`room_bar`): from then on every network
  that typed a wrong password in those 10 minutes is refused at once ("the room's host turned away password guesses
  from your network; ask the host for an invite"), before its guess costs the room anything, so the shared budget
  fills up again; members stay, an invite still brings anybody in. Considered and not taken: weighting accounts
  over the room (accounts cost no more than the addresses they are made from), proof of work per guess (graphics
  cards are far faster than a launcher; the server pays to check each one), a slower hash (the server's cost, not
  the guesser's), accounts only (turns guests away and makes guessing no dearer). A guess is counted
  before the slow check and given back when it was right, so parallel tries on several connections cannot all pass
  while the first is hashed. The refusal says how long to wait (`rate_limited` "... try again in N s" with `retry`
  N, like a held-back invite). Setting a password costs a hash: limited like a password change (per player), and
  to 10, then one per 6 s, per address.
- Passwords: Unicode NFC (the same password however it was typed), printable characters only (no control, format or
  surrogate code points), 4-64 characters, at most 256 bytes of UTF-8. The launcher checks the same rules
  (`proto.clean_room_password`) before it sends anything.
- The password is **never logged, never sent to anybody** (the server's log names the room and who guessed wrong,
  never what was typed), never in the lobby list, a room's view, the status JSON (`/status` counts rooms only), an
  event or an error message. The launcher sends it once, over the lobby connection, and keeps it nowhere.
- The controller's early-press guard (`BAR_ARM_S`) covers the room's ready checks and a friend's room invite like any
  other question; the password and code prompts are keyboard dialogs.

**Older launchers** (no `private_rooms` cap) never see a locked room: the server sends them a lobby list without it
(two lists, one per kind of launcher, each with its own deltas). A join by id is refused with "private rooms need a
newer launcher; update it"; a friend's invite still brings them in. Community rooms work for them like any room: they
get the ready check when it is their turn, and their result card simply has no Rematch button. A new launcher on an
older server finds no `private_rooms` feature: Create room makes a classic room at once, as before.

| Limit | Default | Variable |
|---|---|---|
| most players in a community room | 8 | `T5L_ROOM_MAX_SIZE` |
| pause between a community room's matches | 8 s | `T5L_ROOM_NEXT_SECONDS` |
| wrong passwords / codes per player, then one per | 5, 30 s | `T5L_ROOM_GUESSES`, `T5L_ROOM_GUESS_SECONDS` |
| ... per internet address | 10, then one per 15 s | (2 x the above) |
| ... per room, all players together | 20, then one per 10 s | (4 x, 3 x as often) |

Tests: `lobby/tests/test_private_rooms.py` (create, join with the right and a wrong password, the limits with their
wait, kick, password change, hidden vs listed, older launcher and server, the spectating rule, community rooms,
nothing secret in the log, events or status), `lobby/tests/test_tk_rooms.py` (the launcher: windows, masked prompt,
the code field, the clipboard untouched), `lobby/tools/room_session.py` (N players with stub games taking turns in a
private room, the rule checked match by match), e2e `private_room_turns` (three launchers, stub games) and
`private_room` (a real-game match in a private room, rollback).

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
a room invite can be -- then the room's match keeps its ready check, which says "ranked": the invite named only the
room, and a ranked room's match is rated). After a **Decline** (or when you take your own invite back) you can invite
that friend again after 30 seconds; challenges work the same way. Meanwhile both invite buttons are off for that
friend and the one you would use (in a room: **Invite to my room**) counts the seconds down -- "Invite in 27 s"
(1.1.3). The seconds are the server's (`retry` in `invite_update`, in the friends list and `friend_status`, and with
the refusal of an invite sent anyway); the launcher only counts them down, and the server still refuses an invite
it holds back. An older server says the wait only in its refusal, so there the countdown starts after a refused try.
Friend requests: asking again within a day of
taking a request back puts it in their list without the "wants to be your friend" message.

**Limits** (against spam, all in `server/config.py`):

| | Default | Variable |
|---|---|---|
| friends per account | 100 | `T5L_MAX_FRIENDS` |
| friend requests an account sends per 24 hours (answered or not) | 20 | `T5L_FRIEND_REQUESTS_DAY` |
| requests waiting for an answer, sent by one account, and to one account | 30 | `T5L_FRIEND_PENDING` |
| friend requests from one internet address per 24 hours, all its accounts together | 60 | `T5L_FRIEND_REQUESTS_ADDRESS` |
| an unanswered request runs out after | 14 days | `T5L_FRIEND_REQUEST_DAYS` |
| after a decline, the same request again only after | 7 days | `T5L_FRIEND_RETRY_DAYS` |
| an invite waits for an answer | 60 s | `T5L_INVITE_SECONDS` |
| invites | one at a time per player, one per 2 s, at most 3 waiting for one player | |
| after a declined or taken-back invite (or challenge), the same two again only after | 30 s | `T5L_INVITE_RETRY_SECONDS` |

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

## Spectating

Friends of a player in a match, and anybody for a room's match, can watch it live in their own game, a few
seconds behind (launcher 1.1.3, cap and feature `spectate`): one player's launcher sends the session's live
stream (the replay's data) while somebody watches, the server keeps it from the session's start and sends it
to every spectator. Both players must allow it (Settings -> Spectators; ranked off by default). Messages
`spec_prefs`, `watch`, `unwatch`, `spec_data`, `spec_fail` (client) and `watching`, `spec_want`, `spec_stop`,
`spec_data`, `spec_end`, `spectators` (server); `match_start.stream`, friends' `watch`, rooms' `watch`. All of
it, with the limits and the reasons: [SPECTATE.md](SPECTATE.md).

## Discord Rich Presence

Optional, **off by default**, and offered only by a launcher that has a Discord application id (see "The application
id" below; the 1.1.2 release has none yet, so its Settings show no Discord box): launcher **Settings -> Discord ->
"Show what I play in my Discord status"**. Then the
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
release; empty = no Rich Presence, and Settings does not show the Discord box at all), overridden per player by
`"discord_app_id"` in launcher.json, and by the environment variable `T5_DISCORD_APP_ID` (either one shows the box).

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

## Chime and taskbar flash

(1.1.4; code: `notify.py`, the hooks in `tk_tab.py`, Settings -> "Sound and taskbar flash when a match is found or
someone joins my room", launcher.json `"notify"`, on by default.) Players wait for a match in another window, so the
tab tells them when something needs them -- one chime and the launcher's taskbar button flashing until its window is
in front (FlashWindowEx, `FLASHW_TRAY | FLASHW_TIMERNOFG`; it also ends when the launcher brings itself forward after
a match):

| Event | When |
|---|---|
| match found | `match_found` that shows Accept (quick, ranked, a room's pair, a tournament's next game); not a match that starts by itself (an accepted invite, a ranked set's next game) |
| someone joined | a new member in the room this player hosts (a visitor is not told who comes and goes) |
| your turn | in a community room, the countdown to a match with this player began |
| invite | `invited`: a friend's invite to a casual match or a room |
| tournament set | `tour_call`: "Your tournament set is ready" |
| rematch | the opponent's rematch question |

Not for a challenge from a stranger in the lobby (anybody could ring the bell), chat, friend requests or any lobby
update. Only while the player is elsewhere: another program (or a launcher dialog) in front, the launcher minimized,
or another tab shown; never for a window that was never shown. At most once per event (the match id, the invite id,
the tournament set -- a room's news is found by comparing one `room` message with the one before), and events within
3 seconds of a chime make no second one (someone joins a classic room and the match starts: one chime).

The sound is made in code: two soft bell tones (E5, then B5), about half a second, a 16-bit mono WAV built in memory --
no game audio, no file. winsound cannot play a memory image asynchronously, so a daemon thread plays it and the Tk
thread never waits; if Windows refuses it (no sound card), the system's "SystemAsterisk" plays instead. `T5_NOTIFY=0`
turns the real sound and flash off (every test sets it; the tests give the tab a fake player and a fake flash).

## Protocol reference

### Control channel

TCP (optionally TLS), one JSON object per line, UTF-8, at most 8 KiB per line
from a client. Every message has `"t"`. A request may carry `"rid"` (integer);
the reply carries it back as `"re"` (`{"t":"ok"}` when there is nothing else to
say, `{"t":"error","code":...,"msg":...}` on refusal).

Client to server:

| t | fields | reply / effect |
|---|---|---|
| `hello` | `proto`, `client`, `build: {elf, code, net, release, id}`, `caps` (optional: `delta`, `blind_ready`, `notices`, `ingame_pick`, `sets`, `nat2`, `relays`, `friends`, `tournaments`, `spectate`, `game_fallback`, `private_rooms`) | `welcome {server, proto, udp_port, udp_port2, build, accounts, guests, motd, ip, time, ..., caps, relay_only}`; with the `private_rooms` cap also `room_limits {max_size, next_seconds}`; with the `relays` cap also `relays [{id, name, host, port}]` (regional relays); with the `friends` cap also `friend_limits {max, per_day, invite_seconds}`; with the `tournaments` cap also `tournaments {noshow, organizers}` (the `tour_*` messages: docs/TOURNAMENTS.md "Protocol") |
| `login` | `mode: guest\|account\|register\|resume`, `name`, `password`, `token` | `login_ok {you, token, resumed?}` |
| `ping` | | `pong {time}` (keepalive; silent clients are dropped after 90 s) |
| `udp_rtt` | `ms` | the client's UDP ping to the server (lobby list, matchmaking) |
| `relay_rtt` | `rtts {id: ms}` (`relays` cap) | none: the client's UDP round trips to the regional relays; one it could not reach is left out (and never chosen for its matches) |
| `lobby` | | `lobby_state` now |
| `leaderboard` | `limit` | `leaderboard {rows}` |
| `chat` | `text` (200 chars) | `chat` to everyone |
| `queue` / `unqueue` | `mode: quick\|ranked`, `char`, `strict` (ranked) | `queued {mode, strict}` |
| `room_create` | `name`, `ranked`; with `private_rooms`: `size` (2..`T5L_ROOM_MAX_SIZE`), `rotation: winner\|queue`, `private: password\|code`, `password`, `hidden` | `room {room, code}` (`code`: the invite code, to the host only) |
| `room_join` | `room`; `password` (a locked room); or `code` (the room id optional) | `room {room}`; a classic room's two members start a ready check, a community room's line its next match. Wrong: `auth_failed` "wrong room password" / "no room has that invite code"; too many: `rate_limited` with `retry` |
| `room_leave` / `rematch` | (`rematch` without `match`: Ready again; in a community room: back in line) | `room {room}` |
| `room_lock` | (`private_rooms`, the host) `lock: password\|code\|none`, `password`, `hidden` | `room {room, code}` -- `code` again makes a new invite code (the old one stops working) |
| `room_kick` | (`private_rooms`, the host) `player` (id) | `room {room}`; refused while they play the room's match; they get `notice room_kicked` and cannot come back |
| `room_line` | `in: true\|false` (community rooms) | `room {room}`: sit out / back in line |
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
| `nat_fallback` | `match` (`game_fallback` cap on both clients) | `nat_fallback {match, ok, why}`: this player's game heard nothing at all on the direct path; ok -> both get `nat_relay` (`fallback: true`) and a second `match_start` for the same match on the relay. Refused (`why`): not a new direct match, already on the relay, too late (`T5L_GAME_FALLBACK`), a result is in, not supported |
| `friends` | (`friends` cap, accounts) | `friends {friends [{name, status: online\|in_match\|offline, activity, invite: ok\|busy\|offline\|update\|version, retry, since, last_seen, rating, rank, tier, ...}], incoming [{name, time}], outgoing [{name, time}], max, requests_left}`; `retry` (1.1.3): whole seconds until this player may invite that friend again (0 = now) |
| `friend_add` | `name` (an account) | `friend_added {name, state: pending\|friends}`; the other side gets `friend_request {name, time}` |
| `friend_answer` | `name`, `accept` | `ok`; the asker gets `friend_update {name, state: accepted\|declined}` |
| `friend_cancel` / `friend_remove` | `name` | `ok` (take back a request / end a friendship) |
| `invite` | `name` (a friend online), `kind: casual\|room` | `invite_sent {invite, name, kind, expires}`; the friend gets `invited`. Held back after a no or a take-back (`T5L_INVITE_RETRY_SECONDS`): `error` `rate_limited` "... try again in N s" with `retry` N (1.1.3) |
| `invite_answer` | `invite`, `accept` | accepted: casual -> `match_found` (origin `invite`, no ready check) for both; room -> `room {room}` and the room's match starts (origin `invite`, no ready check) |
| `invite_cancel` | `invite` | `ok`; both get `invite_update` |
| `logout` | | `bye`, connection closed |

Server to client (pushed):

| t | fields |
|---|---|
| `lobby_state` | `players [{id, name, guest, status, rating, rd, record, room, rtt, build, release}]` (`room` null for a hidden room), `rooms [{id, name, owner, members, ranked, build, status, watch, size, rotation, private, lock}]` (a client without `private_rooms` gets no locked room; nobody a hidden one), `queue {quick, ranked}` |
| `lobby_delta` | only to clients with `caps: ["delta"]`, after one `lobby_state`: `players` (changed or new), `gone` (ids), `rooms` (changed or new), `rooms_gone`, `queue` -- each only when it changed. The client library merges it and emits a complete `lobby_state` |
| `chat` | `from`, `text`, `time` |
| `challenged` / `challenge_update` | `challenge`, `from` / `state: accepted\|declined\|cancelled\|expired` |
| `match_found` | `match`, `ranked`, `origin: queue\|room\|challenge`, `role`, `slot`, `opponent`, `ready_check`, `ready_timeout`, `ping {ms, kind: estimate, known}` (the best relay path, docs/RANKED.md "Found match"), `set`. A blind check (queue match, client with `blind_ready`) has `blind: true`, `opponent: null` and no `role` / `slot` |
| `match_reveal` | blind checks only, once both accepted: `match`, `role`, `slot`, `opponent`, `you` |
| `opponent_ready` | `match` |
| `nat_begin` | `match`, `token` (hex, secret), `tag` (hex, shared by both players), `side`, `udp_port`, `udp_port2`, `nat2` (the server plans the punch) |
| `nat_punch` | `match`, `candidates [{ip, port, kind: local\|mapped\|public}]`, `timeout`; to a `nat2` client also `plan {start_at, start_in, window, interval, slow_start, ttl_open, wait_peer, scan [{ip, ports}]}` (docs/NETPLAY.md "Getting a direct connection"); `retry` on the one second chance |
| `nat_peer_punching` | `match`: the opponent's planned punch has started (its NAT is open toward us) |
| `nat_relay` | `match`, `udp_port`, `reason`, `bridge` (both clients `nat2`: keep the game socket in the launcher and upgrade to the direct path when it works); on a regional relay (both clients `relays`) also `relay {id, name, host, port}` and `relay_token` (hex: bind there with it instead of the match token); `fallback: true` when a running direct match moves onto the relay (`nat_fallback`: the launcher opens a new socket, its game holds the old one) |
| `relays` | `relays [{id, name, host, port}]`: the regional relays changed (clients with the `relays` cap measure them again) |
| `match_start` | `match`, `role`, `slot`, `path`, `peer`, `relay_port`, `relay {id, name, host, port}` (a regional relay), `rtt_ms`, `jitter_ms`, `delay`, `rounds`, `ranked`, `build`, `opponent`, `seed`, `fight {p1, p2, stage, rounds, pick}` |
| `match_cancel` | `match`, `reason: declined\|ready_timeout\|opponent_left\|udp_unreachable\|no_connection\|relay_full`, `you` (true = because of you) |
| `match_result` | `match`, `status`, `winner`, `score`, `ranked`, `rating {before, after, delta}`, `you` |
| `set_end` | `set`, `reason: declined\|left\|lag\|expired\|cancelled`, `by: you\|opponent\|null` |
| `lag_check` | after a match, to both players: ping, expected and observed frames behind, verdict, cause, a sentence (RANKED.md) |
| `server_notice` | `id`, `text`, `expires`, `cleared` -- a message from the admin tool (clients without the `notices` cap get a `notice` instead) |
| `notice` | `code`, `msg` (never contains an IP address) |
| `friends` | clients with the `friends` cap: the whole list (as the `friends` reply) after login and whenever it changed |
| `friend_status` | `name`, `status`, `activity`, `invite`, `retry` (1.1.3, as in `friends`): a friend came online, went into a match, went offline ... |
| `friend_request` / `friend_update` | someone asks you; the answer to your request (`state: accepted\|declined`) |
| `invited` | `invite`, `from` (brief), `kind: casual\|room`, `room {id, name, ranked}`, `expires` |
| `invite_update` | `invite`, `state: accepted\|declined\|cancelled\|expired`, `name` (the other side), `kind`; to the inviter also `retry` (1.1.3): whole seconds until the next invite to that friend (30 after a no or a take-back, else 0) |
| `kicked` | `reason` |
| `room` | `room`: this player's room as its members see it -- the list entry plus `size`, `rotation`, `lock`, `hidden`, `owner_id`, `players [{brief, state: playing\|line\|away}]`, `line` (ids in turn order), `playing` (ids), `next {at, players}` (a community room's countdown, server time), `watch` (this member may watch its match). Pushed when it changes; never a password or a code |

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
- **Room passwords** (private rooms): a salted scrypt hash in memory only, a constant-time check, wrong guesses
  limited per player, address and room with the wait in the refusal, never logged or sent to anybody
  ([Rooms](#rooms), "Security").
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
| `T5L_READY_TIMEOUT`, `T5L_PUNCH_TIMEOUT`, `T5L_RELAY_TIMEOUT`, `T5L_RESULT_TIMEOUT` | 15, 6, 10, 90 s | (the punch window was 3 s up to 1.1.0; the relay setup 6 s up to 1.1.2 -- shorter than a client's own bind + measure) |
| `T5L_GAME_FALLBACK` | `90` | seconds after a direct match's start in which a game that heard nothing at all (a firewall blocking it) may move the match onto the relay (`nat_fallback`; `0` = off) |
| `T5L_PUNCH_TTL_OPEN` / `T5L_PREDICT_PORTS` / `T5L_RELAY_UPGRADE` | `0.5` / `24` / `1` | low-TTL opening of each side's own NAT (s), ports tried after a symmetric NAT's last one, relayed matches of two new clients move onto the direct path when it works (docs/NETPLAY.md "Getting a direct connection") |
| `T5L_BLIND_READY` | `1` | queue matches show only the ping until both accepted |
| `T5L_INGAME_PICK` | `30` | seconds to pick the fighter on the game's own select screen (both clients must be able to); `0` = the launchers' characters |
| `T5L_OLD_STAGES` | `0` | `1` = the stage drawn for a match may also be one of the Tekken 5 stages (both clients must announce `old_stages`; docs/RANKED.md "Characters and stages") |
| `T5L_PING_START` / `T5L_PING_WIDEN` / `T5L_PING_ANY_SECONDS` | `80` / `10` / `60` | ranked queue: the estimated ping a pair may have at first (ms), how fast that grows while both wait (ms per s), and after how long any ping goes (0 = never) |
| `T5L_QUICK_PING_WIDEN` / `T5L_QUICK_PING_ANY_SECONDS` | `20` / `30` | the same for the quick queue (it starts at `T5L_PING_START` too) |
| `T5L_STRICT_RANGE` / `T5L_PAIR_COOLDOWN` / `T5L_MAX_BLOCKS` | `150` / `30` / `200` | strict matchmaking range, same-opponent cooldown (s), blocks per player |
| `T5L_MAX_FRIENDS` / `T5L_FRIEND_REQUESTS_DAY` / `T5L_FRIEND_PENDING` | `100` / `20` / `30` | friends per account, requests sent per 24 h, requests waiting per sender and per receiver ("Friends and invites") |
| `T5L_FRIEND_REQUEST_DAYS` / `T5L_FRIEND_RETRY_DAYS` / `T5L_INVITE_SECONDS` | `14` / `7` / `60` | an unanswered request runs out; a declined one may be repeated after; an invite waits |
| `T5L_INVITE_RETRY_SECONDS` | `30` | after a declined (or taken-back) invite or challenge, the same player asks the same player again only after this (0 = off) |
| `T5L_FRIEND_REQUESTS_ADDRESS` | `60` | friend requests per 24 h from one internet address, all its accounts together (0 = no limit) |
| `T5L_LAG_TOLERANCE` / `T5L_LAG_WAIT` | `1` / `6` | post-game lag check: extra frames allowed, seconds to wait for the second report |
| `T5L_ACCEPT_ONESIDED` | `1` | count a lone result report when the other player left |
| `T5L_LOG_LEVEL` | `INFO` | |
| `T5L_LOG_FILE`, `T5L_LOG_MAX_MB`, `T5L_LOG_BACKUPS` | , `10`, `5` | also log to a file, rotated (Windows hosts) |
| `T5L_CONN_RATE` / `T5L_CONN_BURST` | `0.5` / `10` | new connections per address per second, after a burst |
| `T5L_MAX_PENDING_KB` | `1024` | unread output per connection before it is dropped |
| `T5L_LOBBY_INTERVAL` | `0.3` | seconds between lobby list updates (at most) |
| `T5L_UDP_CTL_PPS` | `5000` | server-addressed UDP packets per second, all senders together |
| `T5L_NAME_BLOCKLIST` | | file with extra words refused in new names |
| `T5L_STATUS_HOST` / `T5L_STATUS_PORT` | `127.0.0.1` / `7780` | HTTP /health, /status, /metrics, /tournaments; `0` = off |
| `T5L_TOUR_*` | | tournaments: who may organize, the no-show time, limits, rated or not (docs/TOURNAMENTS.md "Server settings") |
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

**Chime and taskbar flash** (`tests/test_notify.py`: the generated WAV -- format, softness, two tones, no file -- the
playing thread and its fallback, the FlashWindowEx flags, the once-per-event and 3-second rules, what a room's messages
make new, the Settings checkbox; `test_tk_notify.py`: each event in the tab against a real server with a fake player and
a fake flash, the setting, the tab's own "player is elsewhere" rule).

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
- Xbox pads and XInput-mode sticks are read with XInput. DualShock 4, DualSense and DualSense Edge (since
  1.1.2) as HID devices, exactly as the game reads them (ps3recomp patch 0042): USB, Bluetooth short and full
  ("extended") report -- the one Steam and DS4Windows switch a Bluetooth pad to, which the Windows joystick
  API and DirectInput cannot read -- with the same parser rules (`tests/test_ps_hid.py` compares the two on
  2,000 reports) and the names DirectInput gives these pads (B2 = Cross). Opened for reading only, shared (the
  game and other programs read it at the same time), closed again whenever the launcher leaves the front;
  nothing is ever sent to the pad (no output or feature report, which would switch its mode). A pad Steam
  Input hands out as a virtual Xbox pad (Steam started the launcher, the pad is in Steam's list) is left to
  that virtual pad while there is one, as in the game (`steam_input = 0` reads it anyway); `hid = 0` in
  `controls.ini` leaves these pads to the joystick API, as the game then does. Everything else (PS3/PS4-mode
  sticks and hitboxes, generic pads) with the Windows joystick API (WinMM, `joyGetPosEx`): the same button
  numbers as the game's DirectInput side (B1..B32, the hat), no packages. A pad that Windows shows through
  more than one is read once (XInput, else HID). Devices get the ports in the game's order (XInput, the
  PlayStation pads, the rest), so `[portN.dinput]` layers match. Test hook: the game's `PS3_PAD_HID_FAKE`
  (`lobby/tests/test_padnav_hid.py`). Plain `ctypes`, one thread, 60 polls a second while the launcher is in
  front (measured with a real XInput pad: 0.7% of one core), 20 looks at the foreground window a second while
  it is not (0.01%).
- **The game's window comes forward when a match starts** in a game that is already running (a rematch, the
  next opponent) if the launcher is the window in front at that moment -- you just clicked Accept or Rematch
  there. The game reads the keyboard only while its own window has the focus (pads work either way). Never
  while another program is in front, once per match.
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

The launcher and the Online tab speak English, German, Spanish, Korean, Japanese, Brazilian Portuguese and
French (Settings -> Language, each listed in its own name: English, Deutsch, Español, 한국어, 日本語, Português
(Brasil), Français). Auto follows Windows' user interface language when the launcher has it (any Spanish,
French or German Windows; any Portuguese one gets Brazilian Portuguese), else English; `T5_LANG=<code>`
overrides it for development.

`lobby/t5lobby/i18n.py` has the lookup: `t("English text", name=value)`; the English text is the key. One
catalog per language with the same keys: `i18n_de.py`, `i18n_es.py`, `i18n_ko.py`, `i18n_ja.py`,
`i18n_pt_br.py`, `i18n_fr.py`. Names players know from the game and the lobby stay as they are in every
language: Quick Match, Ranked, BUILD GAME, Rematch, Rollback, the character and rank names. Numbers use a
decimal comma in German, Portuguese and French. Korean and Japanese use a Windows font with their glyphs
(Malgun Gothic; Yu Gothic UI, else Meiryo UI / Meiryo / MS UI Gothic) instead of Segoe UI and Bahnschrift,
which have none: Tk's own fallback would draw kanji in a Chinese font.

**The Spanish, Korean, Japanese, Brazilian Portuguese and French texts are machine-assisted translations and
have not been read by native speakers yet. Corrections are welcome:** an issue with the text as shown and what
it should say, or a change to the catalog (`lobby/t5lobby/i18n_<lang>.py`, keep the `{placeholders}`).

The lobby server stays English and sends English: its error texts, notices and kick reasons carry a `code`
or a fixed sentence, and the client puts the sentences it knows into the player's language
(`i18n.translate_message`, the list is `i18n_known.py`; an unknown sentence is shown as it came). The lag
check is built on the client from the numbers in the `lag_check` event (`lag.describe_event`), not from its
`text`. A new text, server message, client error or build-tool error needs an entry in every catalog (and
the messages one in `i18n_known.py`): `python tools/i18n_extract.py` lists what is missing (`--skeleton
--lang ko` prints the lines to paste) and `tests/test_i18n.py` fails until it is there.

Long texts: `tests/test_i18n.py` builds the launcher, every screen of the Online tab and the Controls, report
and update windows in each language at 100 %, 133 % and 150 % display scaling (windows withdrawn, nothing on
screen) and fails for a text cut off (`python tests/i18n_layout.py [lang]` prints the list); the walk also
scrolls to the bottom of the Settings tab and checks that all of it can be scrolled to. Labels that can be long in other languages wrap or get room for every language.

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
