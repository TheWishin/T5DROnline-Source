# The game's own online mode (NP matchmaking) — evaluation

Tekken 5 DR Online's ONLINE BATTLE menu is a complete PSN client: terms of use,
Play Data, ranking boards, room browser, room creation, room lobby, and its own
UDP netcode. This note maps that flow, records how far it runs on the native
build against a stand-in server (patch `0011-np-online`), and gives the
recommendation: **keep the direct-fight + netplay path as the product; the
native online mode is a second, optional front end at best**, and its in-room
protocol still has one unexplained failure (below).

Everything here was measured on one PC with two instances of the game and a
Python server standing in for PSN (`tools/psnr_server.py`).

## Contents

- [What the game uses](#what-the-game-uses)
- [The flow, call by call](#the-flow-call-by-call)
- [What is implemented (patch 0011)](#what-is-implemented-patch-0011)
- [How far it runs](#how-far-it-runs)
- [Where it stops](#where-it-stops)
- [The game's P2P netcode](#the-games-p2p-netcode)
- [Decision and recommendation](#decision-and-recommendation)
- [Server: psnr protocol, and how the lobby could host it](#server-psnr-protocol-and-how-the-lobby-could-host-it)
- [How to run it](#how-to-run-it)
- [Runtime fixes that came out of this (useful regardless)](#runtime-fixes-that-came-out-of-this-useful-regardless)
- [Open items](#open-items)

## What the game uses

50 `sceNp` imports; all names resolved (16 were unnamed in
`imports_named.json`, resolved by hashing RPCS3's function list):

| Group | Functions (game addresses of the caller in `build/ps/asm/`) |
|---|---|
| Manager | `sceNpInit/Term`, `ManagerGetStatus`, `ManagerGetNpId`, `ManagerGetNetworkTime`, `ManagerGetChatRestrictionFlag`, `ManagerGetContentRatingFlag` |
| Matching (first generation, with system GUI) | `CreateCtx/DestroyCtx`, `CreateRoomGUI`, `JoinRoomGUI`, `SearchJoinRoomGUI`, `QuickMatchGUI`, `GetRoomListLimitGUI`, `SendInvitationGUI`, `AcceptInvitationGUI`, `GetResultGUI`, `GetResult`, `GetRoomInfoNoLimit`, `SetRoomInfoNoLimit`, `SetRoomSearchFlag`, `GetRoomMemberListLocal`, `LeaveRoom`, `KickRoomMember` |
| Signaling | `CreateCtx/DestroyCtx`, `ActivateConnection`, `DeactivateConnection`, `TerminateConnection`, `GetConnectionStatus`, `GetConnectionInfo`, `GetLocalNetInfo` |
| Score | `Init/Term`, `CreateTitleCtx`, `CreateTransactionCtx`, `RecordScore`, `GetRankingByRange`, `GetRankingByNpId`, `AbortTransaction`, `Destroy*` |
| Basic | `RegisterContextSensitiveHandler`, `UnregisterHandler`, `AddFriend`, `AddPlayersHistory`, `GetFriendListEntry(Count)` |
| Util | `CmpNpId`, `CmpNpIdInOrder` |
| sys_net | `socket`, `bind`, `sendto`, `recvfrom`, `shutdown`, `socketclose`, `inet_ntoa` — **UDP only**, one `SOCK_DGRAM_P2P` socket |
| cellNetCtl | `NetStartDialog*`, `GetState`, `GetInfo`, `GetNatInfo` |
| cellHttp | an update check at boot and when entering online (`http://f218update.tekken.bng.jp/dc/UP0700/NPUB-30009/contents2/contents_list_us.dat`) and the online manual (`f218manual.tekken.bng.jp/.../online/index.html`); failure is tolerated |

Communication ID `NPWR00045`. This is the **sceNpMatching v1** API, not
Matching2: psnr's ps3recomp integration (sp00nznet #200) implements Matching2
only, so none of its matching code applied; the psnr *wire protocol* and the
sysNet P2P socket handling did.

## The flow, call by call

Main menu → ONLINE BATTLE (4th item):

1. `cellNetCtlNetStartDialogLoadAsync/UnloadAsync`, `GetState`, then the HTTP
   content-list fetch (fails without the dead server; the game continues).
2. Terms of use (4 pages, X = yes). Accepting saves Play Data: two
   `cellSaveDataAutoSave2` into `NPUB30009-CN<timestamp>` and `NPUB30009-SYSNET`.
   The save-data stat callback allocates its 1 MB work buffer with lv2 syscall
   350 from the container it made with syscall 341 — both were wrong in the
   runtime (see fixes).
3. `sceNpInit`, `sceNpManagerGetNpId`, `sceNpScoreCreateTitleCtx`,
   `sceNpMatchingCreateCtx(handler 0x221578)`, `sceNpSignalingCreateCtx(handler
   0x21B970)`, `sceNpBasicRegisterContextSensitiveHandler(0x21BA38)`; then five
   ranking fetches (`GetRankingByNpId` boards 6 and 3, `GetRankingByRange` boards
   6 and 3, `GetRankingByNpId` 10 ids). A failing fetch shows "Failed to update
   ranking data" and the player is reset to Beginner; a successful one (even
   empty) does not. The menu polls `sceNpManagerGetStatus` every frame.
4. ONLINE BATTLE menu: OPTI MATCH (`GetRoomListLimitGUI` with conditions:
   `GAME_NUM id1 ∉ {1,3}`, `id2 == 1`, `id3 == 1`, `id5 == 81100`), QUICK MATCH
   and CUSTOM MATCH (`GetRoomListLimitGUI` with other conditions), CREATE ROOM
   (settings screen, `CreateRoomGUI` with 11 attributes: BASIC_NUM
   TOTAL_SLOT=6, PRIVATE_SLOT=0, PRIVILEGE=1; GAME_NUM id1..id5 =
   rank-match, room level 777, 1, 0, **81100 = the title's data version**; GAME_BIN
   id1 52 B / id2 180 B / id3 40 B = host name, profile and settings), FRIEND
   MATCH (`SendInvitationGUI`, friends — unavailable here), ONLINE RANKING,
   PROFILE, EXIT.
5. Room browser (BATTLE LOBBY): the result of `GetRoomListLimitGUI` is a
   `SceNpMatchingRoomList` whose rooms the game validates with
   `0x245E80/0x2462DC`: BASIC_NUM 1 and 2 must exist, GAME_BIN 1/2/3 must be
   exactly 52/180/40 bytes, GAME_NUM 5 lands at room-info +0x64. The game then
   **pings the host of every listed room** through signaling
   (`ActivateConnection(host) → GetConnectionStatus → GetConnectionInfo(RTT) →
   TerminateConnection`) for the antenna icon — before joining, so signaling
   must resolve a room owner who is not yet a room member (the psnr room list
   does not carry addresses; `psnr_server.py` appends them).
6. X on a room: `JoinRoomGUI(room id)`. Host side: matching event 5
   (`ROOM_UPDATE_NEW_MEMBER`), `GetRoomMemberListLocal`, `GetResult`, then two
   `SetRoomInfoNoLimit` (3 attributes) to publish the new member count/state.
7. Both sides: `cellNetCtlGetNatInfo` (**stun_status must be STUN_OK or the
   game refuses to continue** — it read the field and went back to its menu
   without ever calling `CreateRoomGUI`), `sceNpSignalingActivateConnection(peer)`,
   `GetLocalNetInfo`, `socket(AF_INET, SOCK_DGRAM_P2P)`, `bind(port 3658, vport
   12312)`; the peer's address is `GetConnectionStatus` (status 2 = ACTIVE,
   peer addr/port) and the game builds a `sockaddr_in_p2p {len 16, AF_INET,
   port, addr, vport 12312}` for it. `recvfrom` packets are only accepted when
   source address, port **and vport** match that peer (`0x231808`).
8. In the room the host shows "START: START, △ INVITE, SELECT: KICK, □ POSITION
   CHANGE"; the guest "□ POSITION CHANGE, X PROFILE". START on the host is
   meant to begin the match.

## What is implemented (patch 0011)

`patches/ps3recomp/0011-np-online.patch` (applies in name order on the current
series), all in `libs/network/` unless noted:

- `np_psnr.c/.h` — a psnr client: TCP framing, HELLO, request/reply with
  handlers, pushes, heartbeat; pumped from `cellSysutilCheckCallback` so every
  guest callback runs on the title's polling thread. NAT probe/punch on the
  title's P2P socket plus an RTT ping (`PSNR` control packets `0x7E/0x7F`,
  filtered before the title sees them). Environment: `PS3_NET_ONLINE=1`,
  `PSNR_SERVER=host[:port]`, `PS3_NP_ONLINE_ID`, `PS3_NET_P2P_PORT`,
  `PS3_NET_BIND` (default 127.0.0.1), `PS3_NP_PEER_OVERRIDE` (latency proxy),
  `PS3_NP_TRACE`, `PS3_NET_TRACE`.
- `sceNpMatching.c/.h` — the v1 API over psnr rooms: contexts, the GUI
  operations delivering COMMON_LOAD → event → COMMON_UNLOAD through the GUI
  handler exactly as the console's dialogs do, relocatable result images for
  `GetResultGUI`/`GetResult`, room list with client-side condition filtering
  (1-based `start`), quick match = join-or-create-and-wait with the title's
  timeout, room pushes → matching events 5/6/12/14, `SetRoomInfoNoLimit`,
  `GetRoomInfoNoLimit` (from the room or the last list), `SetRoomSearchFlag`,
  `KickRoomMember`, `LeaveRoom`, `GetRoomMemberListLocal`. Attributes travel
  as an opaque blob in psnr's room "external" data. Invitations report
  CANCELED (no friends list).
- `sceNpSignaling.c` — connections to room members (and to listed hosts) are
  ACTIVE at once with the address psnr gave; `GetConnectionInfo` reports the
  measured RTT, peer and mapped addresses; `GetLocalNetInfo` with the real
  28-byte layout (the old stub wrote through the ctx id as an address).
- `sysNet.c` — `SOCK_DGRAM_P2P`: bound to `PS3_NET_P2P_PORT` on `PS3_NET_BIND`,
  the vport remembered and returned in every `recvfrom`, psnr control packets
  consumed, `PS3_NET_TRACE` hex preview, `SIO_UDP_CONNRESET` off.
- `sceNpScore.c` — contexts, record and rankings over psnr leaderboards,
  ported from sp00nznet's implementation (ctx-style handlers for the 13/15
  argument ranking calls; the synchronous calls return 0 on success, which
  this title requires).
- `sceNp.c` — ONLINE when a server is set, identity from `PS3_NP_ONLINE_ID`,
  `GetNpId` writes through the guest address (**the crash QA reported**),
  `GetNetworkTime` from the shared `ps3_wallclock_unix_nsec` clock,
  chat/content-rating flags; `sceNpBasic.c` the context-sensitive handler,
  players history and AddFriend; `sceNpUtil.c` `CmpNpIdInOrder` compared raw
  guest addresses as host pointers (fixed); `cellNetCtl.c` NAT info says STUN
  done; `cellSysutil.c` pumps the client.

Repository side (branch `np-online`): `tools/psnr_server.py` (the stand-in
server, stdlib asyncio), `tools/udp_proxy.py` (latency/loss proxy),
`tools/np_online_test.py` + `tools/np_scripts/` (drives two instances through
the menus by log markers and frame counts), this document.

## How far it runs

Verified on one PC, two instances (`alpha` on P2P port 3658, `bravo` on 3659),
`build/ps/runs/q14` is the reference run:

- Boot, terms of use, Play Data save, online sign-in, all five ranking fetches
  (empty boards), ONLINE BATTLE menu at 60 fps.
- alpha: CREATE ROOM → room on the server, P2P socket bound, NAT probe
  answered.
- bravo: QUICK MATCH → room list with alpha's room (`1/6`, host rank, settings),
  host ping through signaling, X → `JoinRoomGUI` → in the room with both
  members; alpha gets event 5, refreshes the member list, publishes room info.
- Both sides exchange the game's own UDP packets at about 1/s: 42-byte
  `10 01 00 2a 02 00 <type> 00 b4 00 00 <state> 08 77 …` — bravo sends
  `0x3E8` once then `0x3E9`; alpha answers `0x3E9` and sends `0x44D` (room
  state, state byte 06 then 07) twice a second. Both receive what the other
  sends (`PS3_NET_TRACE`).
- The BATTLE ROOM screen renders on both with the right names and ranks
  (`runs/q14/run1/room_host_a.png`, `runs/q14/run2/room_guest_a.png`).

## Where it stops

About 17–20 s after joining, the **guest leaves the room by itself**
(`sceNpMatchingLeaveRoom` from the online state machine, op 10:
`lr=0x221f0c 0x227d38 0x228138 0x21ac7c …`) and shows "A network error
occurred". The host then sees event 6 and stays in its room. START on the host
before that does nothing visible.

What is known: the leave comes from the per-frame online loop `0x226E00`, which
leaves when the "kicked" flag (`obj+0x6CA9`) or the "connection failed" flag
(`obj+0x6CAB`) is set. The guest never acknowledges the host's `0x44D` room
state (`0x44E` is sent only when the self member state is 2/3, a connected
member has sent ≥ `0x44D`, and the flag `obj+0xA24C` is set, which the
socket-setup op writes from `obj+0x6BA0` — 0 on both sides here). The host's
`0x1BF6` resend budget is 1200 frames = 20 s, which matches the timing.
`GetConnectionStatus` stayed ACTIVE throughout, so it is not the signaling
status; the NAT and version checks (`cellNetCtlGetNatInfo`, GAME_NUM 5 ==
81100) pass on both. The remaining suspects are the room-protocol state bytes
the game expects in `0x44D`/`0x3E9` (it compares its own settings bin, which
contains the joiner's identity, with the host's) and the member-count room
attributes the host publishes with `SetRoomInfoNoLimit` that the guest may be
expected to see change. This needs the handlers registered in the table at
`obj+0x1610` traced with the game running, which is where this evaluation
stopped.

## The game's P2P netcode

Only the lobby phase could be observed. Facts from the binary and the traces:

- One UDP `SOCK_DGRAM_P2P` socket, vport 12312, packets to the peer address
  signaling reported; packets from anyone else are dropped.
- Send path `0x231638`: payloads over 255 bytes are compressed (`0x66F18`,
  zlib) and framed `ABBA7650 | original length | checksum (sum of bytes +
  0xDEADBEEF)`; the receive path `0x231890` unframes and inflates. Lobby
  messages are 42 bytes, uncompressed, about one per second per direction.
- Message types seen: 1000/1001 (hello/ack), 1101 (room state); the handler
  table has 16 slots and the state machine knows 0x41A/0x41B and 0x44C–0x456.
- The match netcode (input exchange) was not reached, so **input delay,
  rollback or not, and behaviour under 50/100 ms RTT or 1–2 % loss remain
  unmeasured.** `tools/udp_proxy.py` plus `PS3_NP_PEER_OVERRIDE` are ready for
  that test. Given the 2006 PS3 generation and the per-frame structure of the
  lobby loop, delay-based lockstep with a fixed input delay is the likely
  design; nothing in the binary suggests state saving for rollback.

## Decision and recommendation

**Build on the direct-fight + netplay path (lockstep now, rollback later).**
The native online mode is not the better foundation:

1. It is a large emulation surface (matching v1 + signaling + score + the
   room protocol) to get to a netcode we cannot change: whatever delay the
   game picks is what players get, and there is no rollback.
2. It depends on a matchmaking server speaking PSN-era semantics (rooms,
   attributes, pings to hosts before joining, system-dialog event sequences).
   A stand-in exists now (psnr protocol, Python server, 3.3k lines of runtime)
   but every screen the game has hides another expectation of the real
   service (five found so far: NAT status, Play Data saves, score return
   values, the GUI event order, room-host pings).
3. Even with the lobby reached, the room handshake fails for a reason inside
   the game that costs more reverse engineering, and the fight itself is still
   unproven.

What is worth keeping from it: the online menu, profile and ranking screens
work and look right, and the ranking boards already live on the server
(`RecordScore`/`GetRanking*`); if the project ever wants the game's own ranked
UI, that front end is ~done. The sensible product remains: launcher + lobby
server (`lobby/t5lobby`) → direct fight with our input exchange, where delay
and rollback are ours.

## Server: psnr protocol, and how the lobby could host it

The runtime speaks the psnr wire protocol
(github.com/sp00nznet/psnr `docs/api.md`): `u8 type | u16 len | payload`,
big-endian, requests/replies with a `u32 req` id, pushes `0xA1..0xA5`, UDP
probe on the same port. `tools/psnr_server.py` implements HELLO, rooms
(create/search/join/leave/set-data/message/kick, member pushes), leaderboards
and the probe. Two extensions, announced by HELLO_ACK flags bit 1:

- ROOM_LIST entries end with `owner user u32 | ip[4] | p2p_port u16`, because
  this title pings hosts from the room browser before joining;
- a probe whose local address is 0.0.0.0 falls back to the TCP source.

If the lobby (`lobby/t5lobby/server`) should host it: add a second listener
(TCP+UDP 36100) in `lobby.py` next to `UdpService`, with rooms keyed by the
communication id, identity = the lobby's logged-in name, and the addresses it
already learns from its own NAT probe. The whole room model of
`psnr_server.py` is ~250 lines and has no state of its own worth keeping
(rooms die with the host).

## How to run it

```
# stand-in server (binds 127.0.0.1 by default; --bind 0.0.0.0 for other PCs)
python tools/psnr_server.py -v

# two instances on one PC (each in its own directory, PS3_WINDOW_BACKGROUND=1)
PS3_NET_ONLINE=1 PSNR_SERVER=127.0.0.1 PS3_NP_ONLINE_ID=alpha PS3_NET_P2P_PORT=3658 t5dr.exe …
PS3_NET_ONLINE=1 PSNR_SERVER=127.0.0.1 PS3_NP_ONLINE_ID=bravo PS3_NET_P2P_PORT=3659 t5dr.exe …

# scripted: both instances through the menus (host creates a room, guest quick-matches)
python tools/np_online_test.py --out runs/x --seconds 200 --two --stagger 15 \
    --script1 tools/np_scripts/host_create_room.txt --script2 tools/np_scripts/join_quick_match.txt \
    --env PS3_NET_ONLINE=1 --env PSNR_SERVER=127.0.0.1 --env PS3_NP_TRACE=1 \
    --env1 PS3_NP_ONLINE_ID=alpha --env1 PS3_NET_P2P_PORT=3658 \
    --env2 PS3_NP_ONLINE_ID=bravo --env2 PS3_NET_P2P_PORT=3659
```

`PS3_NP_TRACE=1` logs every NP request, reply, event and a guest backtrace for
`LeaveRoom`; `PS3_NET_TRACE=1` every P2P packet with a hex preview. The
scripts wait on log markers (`[cellVdec] Open` for the movies,
`GetRankingByNpId(board 6, 10 ids)` for the online menu, `in room` / `joined
the room`) and press by frame count, so they survive a loaded machine. Latency
tests: `tools/udp_proxy.py --a 3658 --b 3659 --pa 4658 --pb 4659 --delay 50
--loss 1` with `PS3_NP_PEER_OVERRIDE=127.0.0.1:4659` on alpha and `…:4658` on
bravo.

## Runtime fixes that came out of this (useful regardless)

- `sceNpGetNpId` wrote through an untranslated guest address → crash on
  entering online (QA's critical).
- lv2 341/342 are `sys_memory_container_create/destroy`, not mmapper calls;
  with the old mapping the title passed an address as a container id to
  syscall 350 and "Unable to save Play Data" followed. (Now in 0012 from the
  system agent; my version was dropped in favour of it.)
- `cellNetCtlGetNatInfo` must report a finished STUN check.
- `sceNpUtilCmpNpIdInOrder` used guest addresses as host pointers.
- `sceNpSignalingGetLocalNetInfo` had the wrong signature and wrote to guest
  address 0/1.
- `sceNpManagerGetNetworkTime` follows `PS3_FIXED_TIME`.

## Open items

- The room handshake failure above (guest leaves after ~20 s).
- QuickMatchGUI/SearchJoinRoomGUI are implemented but this title's QUICK MATCH
  button uses the room list; the quick-match wait has no cancel.
- Invitations/friends: none; `FRIEND MATCH` reports CANCELED.
- The screenshot tool restores the minimized window; with the user's own
  windows in front it captures those instead. Several such captures were
  deleted from `runs/`; take screenshots sparingly.
