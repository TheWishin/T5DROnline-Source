"""LobbyClient: the launcher's side of the lobby.

It runs its own thread with an asyncio loop, so a tkinter (or any) UI can call
its methods from the UI thread and poll `client.events` (a queue.Queue) for
what the server says. Every event is a dict with "t" -- the server's message
types (lobby_state, chat, challenged, match_found, match_cancel, match_result,
notice, ...) plus the client's own:

    {"t": "match_start", "ticket": MatchTicket, ...}   both players are connected: start the game
    {"t": "nat_status", "match": id, "phase": "register"|"punch"|"relay"|"measure", "text": ...}
    {"t": "nat_upgrade", "match": id, "path": "direct"|"relay", "text": ...}   a relayed match moved onto
                                           the direct path (or back to the relay); see RelayBridge
    {"t": "relay_rtts", "rtts": {id: ms}}  round trips to the server's regional relays were measured
                                           (relays=True; the server picks a relay per match from them)
    {"t": "reconnecting", "reason": str}   the connection broke; resuming the session in the background
    {"t": "reconnected"}                   ... and it worked (a running match carries on)
    {"t": "disconnected", "reason": str}   gone for good (log in again)
    {"t": "match_reveal", ...}             a blind ready check ended: both accepted, now the opponent's
                                           name and the sides are known (blind_ready=True, see below)
    {"t": "server_notice", "id", "text", "expires", "cleared"}   a message from the server's admin
    {"t": "lag_check", ...}                after a match: "ping X ms should mean about Y frames behind, it was Z"
    {"t": "set_end", "set", "reason", "by"} the games in a row with one opponent are over (characters unlock);
                                           a ranked set (sets=True, below) adds its result and the rating change

Texts that reach a player (notice, nat_status, disconnected, ...) never contain an IP address:
proto.scrub_addresses is applied to them here, and the server does the same before it sends them.

Passwords and remembered logins are credentials: the client refuses to send them over
a plain (non-TLS) connection unless the server is on this PC or the local network
(password_ok()). Guests need no credentials and work everywhere.

Usage:

    c = LobbyClient("lobby.example.org:7781", BuildInfo.from_out_dir(out))
    c.connect()
    c.login_guest("Kazuya")
    c.quick_match()
    ... event match_found -> c.ready()      (or auto_ready=True)
    ... event match_start -> launch t5dr.exe with ev["ticket"].game_env()
    ... after the game:    c.report_result(winner=0, score=[3, 1])
"""
import asyncio
import hashlib
import ipaddress
import queue
import socket
import ssl
import threading
import time

from . import proto
from .handover import MatchTicket
from .i18n import t
from .nat import GameSocket, RelayBridge, local_ipv4s, server_rtt
from .proto import LobbyError

CLIENT_NAME = "t5lobby-client/0.1"


class LobbyClient:
    def __init__(self, server, build, on_event=None, tls=False, tls_fingerprint=None, game_port=0,
                 auto_ready=False, handover="port", block_direct=False, request_timeout=10.0,
                 reconnect=60.0, plain_passwords=False, blind_ready=False, ingame_pick=False, sets=False,
                 port_mapping=False, nat2=True, relay_bridge=True, relays=True):
        """server: "host[:port]". build: BuildInfo. on_event: optional callable(event) run on the
        client thread (use the `events` queue from a UI). game_port: local UDP port for the game
        (0 = any free one; set it when the player forwarded a port on the router).
        handover: "port" (close the socket, the game binds the same port) or "share" (keep a duplicate
        socket for MatchTicket.share_socket). block_direct: testing only -- ignore the peer's direct
        packets so that punching fails and the relay is used. reconnect: seconds to keep trying to
        resume the session after the connection breaks (0 = off). plain_passwords: allow passwords
        over a plain connection to a server that is not on the local network (not recommended).
        blind_ready: take part in the blind ready check -- a match found in the queue shows only the
        ping at first (`match_found` has `opponent: None`, `blind: True`) and the opponent's name and
        side arrive in `match_reveal` once both accepted. Off by default: `match_found` then names the
        opponent as it always did (the launcher and the CLI turn it on).
        ingame_pick: this player's game can pick the character on its own select screen (docs/RANKED.md,
        "Character select in the game"); the server then sends `fight.pick` when both players' can.
        sets: play ranked sets (docs/RANKED.md "Ranked sets"): a ranked set against another client that
        knows them is best of 3 and rated once at its end; `match_result` then carries `set` {wins, number,
        next {in}, result}, the next game starts by itself (call set_next(), the match driver does), and
        `set_end` has the set's result and rating change. Off by default: every ranked game is rated on its
        own, as before (the launcher turns it on).
        port_mapping: forward the game socket's port on the home router (PCP / NAT-PMP / UPnP) for each
        match, so the opponent's punches get in whatever its NAT does (docs/NETPLAY.md "Getting a direct
        connection"). Off by default (the launcher's setting turns it on; T5_PORTMAP=0 always wins).
        nat2: speak the planned hole punching with a server that offers it (all at once, steady, port
        prediction); False behaves exactly like a 1.1.0 client (tests). relay_bridge: on the relay path
        against another nat2 client, keep the game socket here and move the match onto the direct path
        when it starts to work (RelayBridge). relays: measure the UDP round trip to the regional relays a
        server lists (docs/ONLINE.md "Regional relays") and use the one it picks for a relayed match; False
        behaves like a 1.1.0 client there (only the lobby server's own relay)."""
        self.host, self.port = proto.parse_hostport(server)
        self.build = build
        self.on_event = on_event
        self.tls = tls or bool(tls_fingerprint)
        self.tls_fingerprint = (tls_fingerprint or "").replace(":", "").lower() or None
        self.game_port = game_port
        self.auto_ready = auto_ready
        self.handover = handover
        self.block_direct = block_direct
        self.request_timeout = request_timeout
        self.reconnect_window = reconnect
        self.plain_passwords = plain_passwords
        self.blind_ready = blind_ready
        self.ingame_pick = ingame_pick
        self.sets = sets
        self.notices = {}            # id -> {"text", "expires"}: server notices showing now

        self.events = queue.Queue()
        self.session = None          # "remember me" token from a password login (store it, not the password)
        self.recovery_codes = None   # shown once after registering
        self._kicked = False
        self._kick_reason = ""
        self._reconnecting = False
        self.welcome = None
        self.me = None
        self.token = None
        self.players = []
        self.rooms = []
        self.queue_sizes = {}
        self._pmap = {}              # id -> player / room: what lobby_delta updates are merged into
        self._rmap = {}
        self.match = None            # dict: the current match (from match_found, updated as it goes)
        self.ticket = None           # the last MatchTicket
        self.server_ip = None
        self.server_rtt = None
        self.connected = False
        self.perf_fps = None         # this PC's sustained game speed (last match), sent to the server

        self._loop = None
        self._thread = None
        self._reader = self._writer = None
        self._rid = 0
        self._pending = {}
        self._tasks = []
        self._gs = None              # GameSocket of the current match
        self._nat_task = None
        self.port_mapping = port_mapping
        self.nat2 = nat2
        self.relay_bridge = relay_bridge
        self.relays = relays
        self.relay_rtts = {}         # regional relay id -> ms, as last measured and reported
        self._mapper = None          # portmap.GamePortMapper (port_mapping=True)
        self._router_factory = None  # tests / NAT simulator: a fake router for the mapper
        self._bridge = None          # RelayBridge of the running relayed match
        self.upgrades = []           # (match, path) every switch of a relay bridge, for tools and tests
        self.clock_offset = None     # server time - this PC's time (seconds), for the punch's common start
        self._closing = False

    # ================================================================ thread plumbing
    def _ensure_loop(self):
        if self._loop is not None:
            return
        self._loop = proto.new_event_loop()
        ready = threading.Event()

        def run():
            asyncio.set_event_loop(self._loop)
            self._loop.call_soon(ready.set)
            self._loop.run_forever()
            self._loop.close()
        self._thread = threading.Thread(target=run, name="t5lobby-client", daemon=True)
        self._thread.start()
        ready.wait()

    def _run(self, coro, timeout=None):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return fut.result(timeout or self.request_timeout + 5)
        except TimeoutError:
            fut.cancel()
            raise LobbyError("timeout", "the lobby server did not answer") from None

    # Event types whose text a player reads as a message about the connection. The server scrubs the
    # same fields before sending; this is the second line (client-side exceptions have addresses too).
    _SCRUBBED = ("notice", "nat_status", "disconnected", "reconnecting", "kicked", "error")

    def _emit(self, ev):
        if ev.get("t") in self._SCRUBBED:
            for k in ("msg", "text", "reason"):
                if isinstance(ev.get(k), str):
                    ev[k] = proto.scrub_addresses(ev[k])
        self.events.put(ev)
        if self.on_event is not None:
            try:
                self.on_event(ev)
            except Exception:   # a UI callback must not kill the client thread
                pass

    # ================================================================ connection
    def connect(self, timeout=10.0):
        """Open the control connection and say hello. -> the server's welcome dict."""
        self._ensure_loop()
        try:
            return self._run(self._connect(timeout), timeout + 2)
        except BaseException:
            self.close()            # no thread or socket left behind by a failed attempt
            raise

    async def _connect(self, timeout):
        ctx = None
        if self.tls:
            ctx = ssl.create_default_context()
            if self.tls_fingerprint:          # self-signed server certificate pinned by its SHA-256
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, ssl=ctx, limit=proto.MAX_LINE_FROM_SERVER,
                                        server_hostname=self.host if ctx else None), timeout)
        except (OSError, asyncio.TimeoutError) as e:
            # (the exception names every address it tried, the lobby's included: say what was typed, not that)
            raise LobbyError("connect_failed", f"cannot reach {self.host}:{self.port} "
                                               f"({proto.scrub_addresses(str(e))})") from None
        if self.tls_fingerprint:
            der = self._writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
            if hashlib.sha256(der).hexdigest() != self.tls_fingerprint:
                self._writer.close()
                try:
                    await asyncio.wait_for(self._writer.wait_closed(), 2)
                except (OSError, asyncio.TimeoutError, ssl.SSLError):
                    pass
                raise LobbyError("tls_mismatch", "the server's certificate does not match the pinned one")
        self.server_ip = self._writer.get_extra_info("peername")[0]
        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.connected = True
        reader_task = asyncio.ensure_future(self._read_loop())
        self._tasks.append(reader_task)
        try:
            self.welcome = await self._request({"t": "hello", "proto": proto.PROTO_VERSION,
                                                "client": CLIENT_NAME, "build": self.build.as_wire(),
                                                "caps": ["delta", "notices"] + (["blind_ready"] if self.blind_ready else [])
                                                + (["ingame_pick"] if self.ingame_pick else [])
                                                + (["sets"] if self.sets else [])
                                                + (["nat2"] if self.nat2 else [])
                                                + (["relays"] if self.relays else [])})
        except LobbyError:
            # Refused (version) or no answer (e.g. TLS on one side only): leave nothing half open.
            closing, self._closing = self._closing, True
            reader_task.cancel()
            self._writer.close()
            await asyncio.gather(reader_task, return_exceptions=True)
            self.connected = False
            self._closing = closing
            raise
        return self.welcome

    async def _send(self, msg):
        if not self.connected:
            raise LobbyError("not_connected", "not connected to the lobby")
        self._writer.write(proto.encode(msg))
        await self._writer.drain()

    async def _request(self, msg, timeout=None):
        self._rid += 1
        rid = msg["rid"] = self._rid
        fut = self._loop.create_future()
        self._pending[rid] = fut
        try:
            await self._send(msg)
            return await asyncio.wait_for(fut, timeout or self.request_timeout)
        except asyncio.TimeoutError:
            raise LobbyError("timeout", f"no answer to {msg['t']}") from None
        finally:
            self._pending.pop(rid, None)

    async def _read_loop(self):
        reason = "connection closed"
        try:
            while True:
                line = await self._reader.readuntil(b"\n")
                try:
                    msg = proto.decode(line)
                except ValueError:
                    continue
                await self._dispatch(msg)
        except asyncio.IncompleteReadError:
            reason = "the lobby server closed the connection"      # (not asyncio's "0 bytes read on a total of ...")
        except ConnectionError:
            # (not "[WinError 10054] <the message in the Windows language>": a player reads this)
            reason = "the connection to the lobby server was cut"
        except OSError as e:
            reason = str(e) or reason
        except asyncio.LimitOverrunError:
            reason = "message too long"
        except asyncio.CancelledError:
            reason = "closed"
        finally:
            self.connected = False
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(LobbyError("disconnected", reason))
            await self._drop_game_socket()
            if self._kicked and self._kick_reason:
                reason = f"removed from the lobby: {self._kick_reason}"   # e.g. logged in from another place
            if not self._closing and not self._reconnecting:
                if self.token and self.me and not self._kicked and self.reconnect_window > 0:
                    self._tasks.append(asyncio.ensure_future(self._reconnect(reason)))
                else:
                    self._emit({"t": "disconnected", "reason": reason})

    async def _reconnect(self, reason):
        """The control connection broke: resume the session (the server keeps it, and a running
        match, for a while). The game is not touched; it talks to the opponent directly."""
        self._reconnecting = True
        self._emit({"t": "reconnecting", "reason": reason})
        t_end = time.monotonic() + self.reconnect_window
        delay = 0.5
        try:
            while not self._closing and time.monotonic() < t_end:
                await asyncio.sleep(delay)
                delay = min(5.0, delay * 2)
                try:
                    await self._connect(min(10.0, max(1.0, t_end - time.monotonic())))
                except (LobbyError, OSError):
                    continue
                try:
                    r = await self._request({"t": "login", "mode": "resume", "token": self.token},
                                            self.request_timeout)
                except LobbyError as e:
                    if e.code == proto.E_AUTH:
                        break       # the server forgot the session (restart, or too late)
                    continue
                self.me = r["you"]
                self._start_keepalive()
                self._emit({"t": "reconnected"})
                return
        finally:
            self._reconnecting = False
        if not self._closing:
            self.connected = False
            if self._writer is not None:
                self._writer.close()
            self._emit({"t": "disconnected", "reason": reason})

    async def _dispatch(self, msg):
        t = msg["t"]
        rid = msg.get("re")
        if rid is not None and rid in self._pending:
            fut = self._pending.get(rid)
            if not fut.done():
                if t == "error":
                    fut.set_exception(LobbyError(msg.get("code", "error"), proto.scrub_addresses(msg.get("msg", ""))))
                else:
                    fut.set_result(msg)
            if t in ("error", "ok", "welcome", "login_ok", "queued", "result_ack", "pong", "challenge",
                     "leaderboard", "bye", "profile", "history", "passwd_ok", "recovered", "recovery_codes",
                     "rematch", "blocked", "unblocked", "blocks", "set_next"):
                return
        handler = getattr(self, "_on_" + t, None)
        if handler is not None:
            if await handler(msg) is False:
                return
        self._emit(msg)

    # ================================================================ server events
    async def _on_lobby_state(self, msg):
        self.players = msg.get("players", [])
        self.rooms = msg.get("rooms", [])
        self.queue_sizes = msg.get("queue", {})
        self._pmap = {p["id"]: p for p in self.players}
        self._rmap = {r["id"]: r for r in self.rooms}
        if self.me:
            for p in self.players:
                if p["id"] == self.me["id"]:
                    self.me = p

    async def _on_kicked(self, msg):
        self._kicked = True
        self._kick_reason = str(msg.get("reason") or "")

    async def _on_lobby_delta(self, msg):
        """What changed since the last update (the server sends whole lists only now and then):
        merge it and hand the UI a complete lobby_state, exactly as before."""
        pmap, rmap = self._pmap, self._rmap
        for pid in msg.get("gone", ()):
            pmap.pop(pid, None)
        for p in msg.get("players", ()):
            pmap[p["id"]] = p
        for rid in msg.get("rooms_gone", ()):
            rmap.pop(rid, None)
        for r in msg.get("rooms", ()):
            rmap[r["id"]] = r
        full = {"t": "lobby_state", "players": list(pmap.values()), "rooms": list(rmap.values()),
                "queue": msg.get("queue", self.queue_sizes)}
        await self._on_lobby_state(full)
        self._emit(full)
        return False

    async def _on_match_found(self, msg):
        self.match = dict(msg, state="ready")
        self.ticket = None
        if self.auto_ready and msg.get("ready_check"):
            asyncio.ensure_future(self._safe(self._send({"t": "ready", "match": msg["match"], "accept": True})))

    async def _on_match_reveal(self, msg):
        """Both accepted a blind match: now the opponent and the side are known."""
        if self.match and self.match["match"] == msg["match"]:
            self.match.update(opponent=msg.get("opponent"), role=msg.get("role"), slot=msg.get("slot"),
                              blind=False)

    async def _on_server_notice(self, msg):
        nid = msg.get("id")
        if msg.get("cleared") or not msg.get("text"):
            self.notices.pop(nid, None)
        else:
            self.notices[nid] = {"text": str(msg["text"]), "expires": float(msg.get("expires") or 0)}

    def active_notices(self):
        """Texts of the server notices that are still showing, oldest first."""
        now = time.time()
        return [n["text"] for _i, n in sorted(self.notices.items())
                if not n["expires"] or n["expires"] > now]

    async def _on_relays(self, msg):
        """The server's list of regional relays changed: measure the new list."""
        if self.welcome is not None and isinstance(msg.get("relays"), list):
            self.welcome["relays"] = msg["relays"]
            self._tasks.append(asyncio.ensure_future(self._measure_relays()))
        return False

    async def _on_match_cancel(self, msg):
        if self.match and self.match["match"] == msg["match"]:
            self.match = None
        await self._drop_game_socket()

    async def _on_match_result(self, msg):
        if self.match and self.match["match"] == msg["match"]:
            self.match = None
        if msg.get("you"):
            self.me = msg["you"]

    async def _on_nat_begin(self, msg):
        if not self.match or self.match["match"] != msg["match"]:
            return False
        self.match["state"] = "nat"
        self._nat_phase(self._nat_register(msg))

    async def _on_nat_punch(self, msg):
        if not self._gs or not self.match or self.match["match"] != msg["match"]:
            return False
        self._nat_phase(self._nat_punch(msg))
        return False

    async def _on_nat_peer_punching(self, msg):
        """The opponent's launcher has started its punch (nat2): our low-TTL opening may end."""
        if self.match and self.match["match"] == msg.get("match") and self.match.get("peer_open") is not None:
            self.match["peer_open"].set()
        return False

    async def _on_nat_relay(self, msg):
        if not self._gs or not self.match or self.match["match"] != msg["match"]:
            return False
        self._nat_phase(self._nat_relay(msg))
        return False

    async def _on_match_start(self, msg):
        gs = self._gs
        if msg.get("continue") and self.match and self.match["match"] == msg["match"] and \
                self.match.get("state") != "playing":
            # Rematch inside the running games: no new socket, no new ticket.
            self.match["state"] = "playing"
            self._emit(dict(msg, ticket=None))
            return False
        if gs is None and (not self.match or self.match["match"] != msg["match"]):
            # Resumed session: the game is already running; remember the match for the result report.
            self.match = dict(msg, state="playing")
            self._emit(dict(msg, ticket=None, resumed=True))
            return False
        if gs is None or not self.match or self.match["match"] != msg["match"]:
            return False
        if self._nat_task is not None:
            self._nat_task.cancel()
        local_port = gs.port
        if msg["path"] == "relay":
            peer = self.relay_address(self._relay_of(msg, "relay_port"))
            if self.match.get("bridge") and self._bridge is None:
                b = await self._open_bridge(msg["match"], peer, msg.get("start_time"))
                if b is not None:
                    gs = None
                    peer, local_port = ("127.0.0.1", b.port), b.game_port
        else:
            peer = tuple(msg["peer"])
        if msg.get("build") and msg["build"] != self.build.build_id:
            # Should never happen (the server pairs equal builds only) -- refuse rather than desync.
            await self._safe(self._send({"t": "leave_match", "match": msg["match"]}))
            self._emit({"t": "notice", "code": "version_mismatch", "msg": "opponent runs a different build"})
            return False
        ticket = MatchTicket(match_id=msg["match"], role=msg["role"], slot=msg["slot"], local_port=local_port,
                             peer=peer, path=msg["path"], rtt_ms=msg.get("rtt_ms", 0.0),
                             jitter_ms=msg.get("jitter_ms", 0.0), delay=msg.get("delay", 3),
                             rounds=msg.get("rounds", 3), ranked=msg.get("ranked", False),
                             opponent=msg.get("opponent", {}), build=msg.get("build", ""), seed=msg.get("seed", 0),
                             key=str(msg.get("key") or ""), input_delay=msg.get("input_delay"))
        if self.handover == "share" and gs is not None and gs.dup is not None:
            ticket._dup_socket = gs.dup
            gs.dup = None
        if gs is not None:
            # A last round of punches refreshes both NATs' mappings for the moment the game takes over.
            for addr in {peer} | set(gs.confirmed):
                gs._punch_to(addr)
        await self._drop_game_socket()          # the port is free for the game from here on
        self.ticket = ticket
        self.match["state"] = "playing"
        self._emit(dict(msg, ticket=ticket))
        return False

    # ================================================================ NAT traversal
    def _nat_phase(self, coro):
        if self._nat_task is not None and not self._nat_task.done():
            self._nat_task.cancel()
        self._nat_task = asyncio.ensure_future(self._guard(coro))

    async def _guard(self, coro):
        try:
            await coro
        except asyncio.CancelledError:
            pass
        except Exception as e:   # report, never crash the client loop
            self._emit({"t": "notice", "code": "nat_error", "msg": f"{type(e).__name__}: {e}"})

    async def _safe(self, coro):
        try:
            await coro
        except (LobbyError, ConnectionError, OSError):
            pass

    def _status(self, mid, phase, text):
        self._emit({"t": "nat_status", "match": mid, "phase": phase, "text": text})

    def _server_nat2(self):
        return bool(self.nat2 and self.welcome and "nat2" in (self.welcome.get("caps") or ()))

    def _start_port_mapper(self):
        if not self.port_mapping or self._mapper is not None:
            return
        if self._router_factory is None and is_local_address(self.server_ip or self.host):
            return      # a lobby on this PC or the LAN: no router between the players, nothing to forward
        from .portmap import GamePortMapper
        self._mapper = GamePortMapper(backend_factory=self._router_factory).start()

    async def _map_port(self, port, timeout=1.0):
        """The game socket's port forwarded on the router -> [ip, port] (ip None when unknown), or None."""
        m = self._mapper
        if m is None or not m.ready():
            return None
        try:
            got = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(None, m.map, port), timeout)
        except (asyncio.TimeoutError, OSError):
            return None
        return [got[0], int(got[1])] if got else None

    async def _nat_register(self, msg):
        await self._drop_game_socket()
        await self._drop_bridge()
        mid = msg["match"]
        self._status(mid, "register", t("Contacting the lobby server over UDP..."))
        gs = await GameSocket.open(self.game_port, (self.server_ip, int(msg["udp_port"])),
                                   int(msg.get("udp_port2") or 0), bytes.fromhex(msg["token"]),
                                   bytes.fromhex(msg["tag"]), int(msg["side"]),
                                   block_direct=self.block_direct, keep_dup=self.handover == "share")
        self._gs = gs
        v2 = self.nat2 and bool(msg.get("nat2"))
        self.match["peer_open"] = asyncio.Event()    # set by nat_peer_punching (the opponent started)
        # Before the socket sends anything: a forward made now usually carries its outgoing packets too, so
        # the endpoint the server sees below is the forwarded one.
        mapped = await self._map_port(gs.port) if v2 or self.port_mapping else None
        reg = await gs.register()
        if reg is None:
            self._status(mid, "register", t("UDP to the lobby server is blocked (firewall?)"))
            return
        public, probe = reg
        nat = "unknown" if probe is None else ("eim" if probe[1] == public[1] else "symmetric")
        addrs = [[ip, gs.port] for ip in local_ipv4s(self.server_ip)]
        self.match.update(public=public, nat=nat, local_port=gs.port, nat2=v2)
        out = {"t": "nat_local", "match": mid, "addrs": addrs, "nat": nat, "port": gs.port}
        if mapped and v2:
            out["mapped"] = [mapped[0] or public[0], mapped[1]]
        await self._send(out)

    async def _nat_punch(self, msg):
        mid, phase = msg["match"], "punch"
        gs = self._gs
        cands = [(c["ip"], int(c["port"]), c.get("kind", "public")) for c in msg.get("candidates", [])]
        plan = msg.get("plan") if self.nat2 else None
        if isinstance(plan, dict):
            # Planned by the server: start at the same moment as the opponent, punch at a steady rate for the
            # whole window, walk the predicted ports of a NAT that maps every destination anew.
            scan = []
            for sc in plan.get("scan") or ():
                try:
                    scan.append((str(sc["ip"]), [int(p) for p in sc["ports"]][:64]))
                except (KeyError, TypeError, ValueError):
                    continue
            start_in = float(plan.get("start_in", 0)) / 1000.0
            if self.clock_offset is not None and isinstance(plan.get("start_at"), (int, float)):
                at = float(plan["start_at"]) - self.clock_offset - time.time()
                if -5.0 < at < 5.0:
                    start_in = at            # the same moment as the opponent, however late this message came
            window = min(20.0, max(1.0, float(plan.get("window", msg.get("timeout", 3.0)))))
            ttl_open = min(2.0, max(0.0, float(plan.get("ttl_open", 0.0))))
            late = max(0.0, -start_in)       # the opponent started this much earlier: keep to its schedule
            self._status(mid, "punch", t("Connecting to your opponent..."))
            if start_in > 0:
                await asyncio.sleep(min(3.0, start_in))
            peer_open = None
            if self.match is not None:
                self.match["punch_t0"] = time.time()
                if plan.get("wait_peer"):
                    # tell the opponent (through the server) that this side's NAT is opening now
                    await self._safe(self._send({"t": "nat_punching", "match": mid}))
                    peer_open = self.match.get("peer_open")
            got = await gs.punch(cands, timeout=max(1.0, window - late), interval=float(plan.get("interval", 0.05)),
                                 scan=scan, slow_start=float(plan.get("slow_start", 0.6)),
                                 ttl_open=min(ttl_open, 0.15) if peer_open else max(0.0, ttl_open - late),
                                 peer_open=peer_open)
        else:
            self._status(mid, "punch", t("Connecting to your opponent..."))
            got = await gs.punch(cands, timeout=float(msg.get("timeout", 3.0)))
        if got is None:
            await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": False})
            return
        addr, kind = got
        self._status(mid, "measure", t("Measuring the connection..."))
        m = await gs.measure(addr)
        if m is None:
            await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": False})
            return
        rtt, jitter, _n = m
        await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": True, "peer": list(addr), "kind": kind,
                          "rtt_ms": round(rtt, 3), "jitter_ms": round(jitter, 3)})
        # Keep answering the peer's pings until match_start arrives.

    def relay_address(self, relay):
        """(ip, port) to send to for a relay entry {id, host, port} (the lobby server's own relay is id "main").
        One place for it, so that a test can put a simulated network in between (lobby/tools/relay_e2e.py)."""
        return relay["host"], int(relay["port"])

    def _relay_of(self, msg, port_key):
        """The relay a nat_relay / match_start names: a regional one ("relay") or the lobby server's own."""
        r = msg.get("relay") if self.relays else None
        if isinstance(r, dict) and r.get("host") and r.get("port"):
            return r
        return {"id": "main", "name": "", "host": self.server_ip, "port": int(msg[port_key])}

    async def _nat_relay(self, msg):
        mid, phase = msg["match"], "relay"
        gs = self._gs
        entry = self._relay_of(msg, "udp_port")
        relay = self.relay_address(entry)
        token = bytes.fromhex(msg["relay_token"]) if entry["id"] != "main" and msg.get("relay_token") else None
        if self.match is not None:
            self.match["bridge"] = bool(msg.get("bridge")) and self.nat2 and self.relay_bridge and \
                self.handover == "port"
            self.match["relay_name"] = entry.get("name") if entry["id"] != "main" else None
        if entry["id"] != "main":
            self._status(mid, "relay", t("Direct connection not possible; using the relay server {name}...",
                                         name=entry.get("name") or entry["id"]))
        else:
            self._status(mid, "relay", t("Direct connection not possible; using the lobby server's relay..."))
        if not await gs.relay_bind(relay, token=token):
            await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": False})
            return
        m = await gs.measure(relay, timeout=4.0)
        if m is None:
            await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": False})
            return
        rtt, jitter, _n = m
        await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": True, "peer": list(relay), "kind": "relay",
                          "rtt_ms": round(rtt, 3), "jitter_ms": round(jitter, 3)})

    async def _open_bridge(self, mid, relay, start_time=None):
        """Relay play through this launcher (RelayBridge): the game gets a local port and 127.0.0.1 as its
        peer; the punched socket stays here, on the relay until the direct path works."""
        gs, self._gs = self._gs, None

        name = (self.match or {}).get("relay_name")

        def switched(path, addr, mid=mid):
            self.upgrades.append((mid, path))
            if name:
                text = t("Direct connection found: the match no longer goes through the relay server {name}.",
                         name=name) if path == "direct" else \
                    t("The direct connection was lost; back on the relay server {name}.", name=name)
            else:
                text = t("Direct connection found: the match no longer goes through the lobby server.") \
                    if path == "direct" else t("The direct connection was lost; back on the lobby server's relay.")
            self._emit({"t": "nat_upgrade", "match": mid, "path": path, "text": text})
            if self._server_nat2():
                self._tasks.append(asyncio.ensure_future(self._report_upgrade(mid, path, addr)))
        first = None
        if self.clock_offset is not None and isinstance(start_time, (int, float)):
            # the same server time on both PCs: the match's start + 35 s
            first = time.monotonic() + (float(start_time) + RelayBridge.FIRST_BURST - self.clock_offset - time.time())
            if not time.monotonic() + 5.0 < first < time.monotonic() + 120.0:
                first = None
        try:
            self._bridge = await RelayBridge.open(gs, relay, on_switch=switched, first_burst=first)
        except OSError:
            self._gs = gs
            return None
        return self._bridge

    async def _report_upgrade(self, mid, path, addr):
        msg = {"t": "nat_upgrade", "match": mid, "path": path}
        if path == "direct" and self._bridge is not None:
            m = await self._bridge.gs.measure(addr, n=6, timeout=2.0, need=2)
            if m is not None:
                msg["rtt_ms"] = round(m[0], 3)
        await self._safe(self._send(msg))

    async def _drop_bridge(self):
        b, self._bridge = self._bridge, None
        if b is not None:
            await b.close()

    async def _drop_game_socket(self):
        gs, self._gs = self._gs, None
        if self._nat_task is not None and not self._nat_task.done() and \
                self._nat_task is not asyncio.current_task():
            self._nat_task.cancel()
        if gs is not None:
            if gs.dup is not None:
                gs.dup.close()
                gs.dup = None
            try:
                await gs.close()
            except (asyncio.TimeoutError, OSError):
                pass

    # ================================================================ background upkeep
    def _start_keepalive(self):
        old = getattr(self, "_keepalive_task", None)
        if old is not None and not old.done():
            old.cancel()
        self._keepalive_task = asyncio.ensure_future(self._keepalive())
        self._tasks.append(self._keepalive_task)

    async def _keepalive(self):
        """Control-channel keepalive (the server drops silent clients) and a fresh UDP RTT to the
        server every 30 s (the lobby shows it and the ranked queue matches on it)."""
        while self.connected:
            for _ in range(30):
                await asyncio.sleep(1.0)
                if not self.connected:
                    return
            await self._safe(self._send({"t": "ping"}))
            self._keep_n = getattr(self, "_keep_n", 0) + 1
            if self._gs is None and self._bridge is None:
                await self._measure_server()
                if self._keep_n % 10 == 0:          # every 5 minutes, between matches
                    await self._measure_relays()
            if self._mapper is not None and self._mapper.current is not None:
                # renewed while a match (or its relay bridge) is on; two minutes without one: closed
                busy = self.match is not None or self._bridge is not None
                self._map_idle = 0 if busy else getattr(self, "_map_idle", 0) + 1
                fn = self._mapper.renew if self._map_idle < 4 else self._mapper.unmap
                await asyncio.get_running_loop().run_in_executor(None, fn)

    async def _measure_server(self):
        if not self.welcome:
            return
        try:
            rtt = await server_rtt(self.relay_address({"id": "main", "host": self.server_ip,
                                                       "port": int(self.welcome["udp_port"])}))
        except OSError:
            rtt = None
        if rtt is not None:
            self.server_rtt = rtt
            await self._safe(self._send({"t": "udp_rtt", "ms": round(rtt, 2)}))

    def _server_relays(self):
        return bool(self.relays and self.welcome and "relays" in (self.welcome.get("caps") or ()))

    async def _measure_relays(self):
        """UDP round trip to each regional relay the server listed (all at once, in the background), reported
        to the server as `relay_rtt`: it picks the relay with the smallest sum of both players' round trips
        when a match needs one. A relay that does not answer is left out (never chosen for this player)."""
        if not self._server_relays():
            return
        lst = [r for r in self.welcome.get("relays") or () if isinstance(r, dict) and r.get("id") and r.get("host")]
        if not lst and not self.relay_rtts:
            return                                  # (no regional relays on this server: nothing to say)

        async def one(r):
            try:
                return r["id"], await server_rtt(self.relay_address(r))
            except (OSError, ValueError, TypeError, KeyError):
                return r.get("id"), None
        got = await asyncio.gather(*(one(r) for r in lst[:32]))
        rtts = {rid: round(ms, 2) for rid, ms in got if ms is not None}
        self.relay_rtts = rtts
        await self._safe(self._send({"t": "relay_rtt", "rtts": rtts}))
        self._emit({"t": "relay_rtts", "rtts": dict(rtts)})

    # ================================================================ public API (any thread)
    def _call(self, msg, timeout=None):
        return self._run(self._request(msg, timeout), (timeout or self.request_timeout) + 2)

    def _fire(self, msg):
        self._run(self._send(msg))

    def _login(self, msg):
        r = self._run(self._login_async(msg), self.request_timeout + 10)
        return r

    async def _login_async(self, msg):
        r = await self._request(msg, self.request_timeout + 5)
        self.me = r["you"]
        self.token = r["token"]
        if r.get("session"):
            self.session = r["session"]
        elif msg.get("mode") == "session":
            self.session = msg.get("session")
        self.recovery_codes = r.get("recovery_codes")
        self._kicked = False
        if self.perf_fps:
            await self._safe(self._send({"t": "perf", "fps": self.perf_fps}))
        await self._measure_server()
        if self._server_relays():
            self._tasks.append(asyncio.ensure_future(self._measure_relays()))
        self._start_keepalive()
        self._start_port_mapper()
        if self.nat2:
            self._tasks.append(asyncio.ensure_future(self._clock_sync()))
        return self.me

    async def _clock_sync(self, n=3):
        """The server's clock against ours (the ping that answers with the server's time, the fastest of n):
        a planned punch starts at a server time, so a message that TCP had to send twice still starts on time."""
        best = None
        for _ in range(n):
            t0 = time.time()
            try:
                r = await self._request({"t": "ping"}, 5.0)
            except (LobbyError, ConnectionError, OSError):
                return
            t1 = time.time()
            st = r.get("time")
            if isinstance(st, (int, float)) and (best is None or t1 - t0 < best[0]):
                best = (t1 - t0, float(st) - (t0 + t1) / 2.0)
            await asyncio.sleep(0.05)
        if best is not None:
            self.clock_offset = best[1]

    # ---------------------------------------------------------------- credentials
    def password_ok(self):
        """May credentials (password, remembered login) go to this server? Yes over TLS, and over a
        plain connection only to this PC or the local network (or when plain_passwords is set)."""
        if self.tls or self.plain_passwords:
            return True
        return is_local_address(self.server_ip or self.host)

    def _need_secure(self):
        if not self.password_ok():
            raise LobbyError(proto.E_INSECURE,
                             "this server has no encryption (TLS): a password would cross the internet readable. "
                             "Play as a guest, or ask the server's host to set up TLS and give you its fingerprint.")

    def login_guest(self, name):
        return self._login({"t": "login", "mode": "guest", "name": name})

    def login(self, name, password, remember=False):
        self._need_secure()
        return self._login({"t": "login", "mode": "account", "name": name, "password": password,
                            "remember": bool(remember)})

    def register(self, name, password, remember=False):
        """Create the account and log in. The one-time recovery codes are in .recovery_codes afterwards:
        show them to the player once (they are the only way back in without the password)."""
        self._need_secure()
        return self._login({"t": "login", "mode": "register", "name": name, "password": password,
                            "remember": bool(remember)})

    def login_session(self, session):
        """Log in with a remembered login (the token a password login with remember=True returned)."""
        self._need_secure()
        return self._login({"t": "login", "mode": "session", "session": session})

    def resume(self, token=None):
        return self._login({"t": "login", "mode": "resume", "token": token or self.token})

    def change_password(self, old, new, remember=False):
        """Every remembered login of the account ends; with remember, this one gets a new token."""
        self._need_secure()
        r = self._call({"t": "passwd", "old": old, "new": new, "remember": bool(remember)})
        self.session = r.get("session")
        return r

    def recover(self, name, code, new_password):
        """Forgotten password: a recovery code + a new password (connect() first, no login needed)."""
        self._need_secure()
        return self._call({"t": "recover", "name": name, "code": code, "password": new_password})

    def new_recovery_codes(self, password):
        self._need_secure()
        return self._call({"t": "recovery_codes", "password": password})["codes"]

    def logout(self, forget=False):
        """Leave the lobby; forget=True also ends the remembered login on the server."""
        if forget and self.connected:
            try:
                self._run(self._send({"t": "logout", "forget": True, "session": self.session}))
            except LobbyError:
                pass
            self.session = None
        self.close()

    # ---------------------------------------------------------------- profiles and characters
    def profile(self, name=None, history=10):
        return self._call({"t": "profile", "name": name, "history": history})["profile"]

    def history(self, name=None, limit=20, offset=0):
        return self._call({"t": "history", "name": name, "limit": limit, "offset": offset})["rows"]

    def set_char(self, char):
        return self._call({"t": "set_char", "char": char})

    def report_perf(self, fps):
        """This PC's sustained game speed (frames per second, from the last match): the server
        warns both players before a match with a slow PC and keeps PCs below its minimum out of
        ranked (lockstep plays at the slower PC's speed). Remembered and re-sent after a login."""
        try:
            fps = round(float(fps), 1)
        except (TypeError, ValueError):
            return
        if not 0 < fps < 1000:
            return
        self.perf_fps = fps
        if self.me is not None and self.connected:
            self._fire({"t": "perf", "fps": fps})

    def quick_match(self, char=None):
        msg = {"t": "queue", "mode": "quick"}
        if char:
            msg["char"] = char
        return self._call(msg)

    def ranked_match(self, char=None, strict=False):
        """Queue for a ranked match. strict=True: only opponents within the server's strict range
        (150 rating points) -- the wait can be long."""
        msg = {"t": "queue", "mode": "ranked"}
        if char:
            msg["char"] = char
        if strict:
            msg["strict"] = True
        return self._call(msg)

    # ---------------------------------------------------------------- blocking, sets, lag check
    def block(self, name):
        """Never be matched with this player again (accounts: kept on the account; guests: this session).
        A running match with them ends like a quit. -> {"name", "blocks", "left_match"}"""
        return self._call({"t": "block", "name": name})

    def unblock(self, name):
        return self._call({"t": "unblock", "name": name})

    def blocks(self):
        """[{"name", "guest", "since"}, ...]"""
        return self._call({"t": "blocks"})["rows"]

    def leave_set(self, reason=None):
        """Leave the games in a row with this opponent, between two games. No penalty, no rating change
        (a game already played keeps its result). reason="lag": after the lag check."""
        msg = {"t": "leave_set"}
        if reason:
            msg["reason"] = reason
        return self._call(msg)

    def set_next(self, match_id=None, keep=False):
        """Between two games of a ranked set (the next one starts by itself after a countdown): keep=True
        when this player's game still runs connected to the opponent's, so the next game continues in the
        running games. -> {"state": waiting|started, "in": seconds}"""
        return self._call({"t": "set_next", "match": match_id, "keep": bool(keep)})

    def report_lag(self, match_id, frames, waited_ms, pc_fps=None, fps=None):
        """The game's own numbers for a finished match: frames played, milliseconds spent waiting for
        the opponent's input, this PC's speed without those waits. Both players then get `lag_check`.
        A refusal (match too old, too few frames) is not an error worth showing."""
        msg = {"t": "lag", "match": match_id, "frames": int(frames), "waited_ms": round(float(waited_ms), 1)}
        if pc_fps:
            msg["pc_fps"] = round(float(pc_fps), 1)
        if fps:
            msg["fps"] = round(float(fps), 1)
        try:
            return self._call(msg)
        except LobbyError:
            return None

    def cancel_queue(self):
        return self._call({"t": "unqueue"})

    def create_room(self, name=None, ranked=False):
        return self._call({"t": "room_create", "name": name, "ranked": ranked})["room"]

    def join_room(self, room_id):
        return self._call({"t": "room_join", "room": room_id})["room"]

    def leave_room(self):
        return self._call({"t": "room_leave"})

    def rematch(self, match_id=None, accept=True, keep=False):
        """Rooms: rematch() starts the next match in the room. After any other match: the finished
        match's id; keep=True when this player's game still runs connected to the opponent's."""
        if match_id is None:
            return self._call({"t": "rematch"})
        return self._call({"t": "rematch", "match": match_id, "accept": bool(accept), "keep": bool(keep)})

    def challenge(self, player_id):
        return self._call({"t": "challenge", "player": player_id})["challenge"]

    def answer_challenge(self, challenge_id, accept=True):
        return self._call({"t": "challenge_reply", "challenge": challenge_id, "accept": bool(accept)})

    def cancel_challenge(self, challenge_id):
        return self._call({"t": "challenge_cancel", "challenge": challenge_id})

    def ready(self, accept=True, match_id=None):
        mid = match_id or (self.match or {}).get("match")
        return self._call({"t": "ready", "match": mid, "accept": bool(accept)})

    def chat(self, text):
        self._fire({"t": "chat", "text": text})

    def game_started(self, match_id=None):
        mid = match_id or (self.ticket.match_id if self.ticket else None)
        return self._call({"t": "game_started", "match": mid})

    def report_result(self, winner, score=None, match_id=None, source=None, desync=None, hash=None,
                      frames=None, reason=None, chars=None, costumes=None):
        """winner: 0 (P1 = host) or 1 (P2 = join) or None (draw / no result); score: [P1 rounds, P2 rounds].
        source: game (read from the game) | manual (the player said) | quit | crash | disconnect.
        desync / hash / frames: the netplay layer's evidence when there is any (docs/RANKED.md).
        chars: [P1 fighter, P2 fighter] the game fought with (keys; in-game select); costumes: their confirm
        buttons [P1, P2] (1-4 = LP, RP, LK, RK; 0 = the default), which a ranked set keeps."""
        mid = match_id or (self.ticket.match_id if self.ticket else None) or (self.match or {}).get("match")
        msg = {"t": "result", "match": mid, "winner": winner, "score": score}
        for k, v in (("source", source), ("desync", desync), ("hash", hash), ("frames", frames),
                     ("reason", reason), ("chars", chars), ("costumes", costumes)):
            if v is not None:
                msg[k] = v
        return self._call(msg)

    def leave_match(self, match_id=None):
        mid = match_id or (self.match or {}).get("match") or (self.ticket.match_id if self.ticket else None)
        return self._call({"t": "leave_match", "match": mid})

    def leaderboard(self, limit=20, offset=0):
        return self._call({"t": "leaderboard", "limit": limit, "offset": offset})["rows"]

    def refresh(self):
        return self._call({"t": "lobby"})

    def next_event(self, timeout=None, types=None):
        """Block for the next event (optionally of the given types); None on timeout."""
        t_end = None if timeout is None else time.monotonic() + timeout
        while True:
            left = None if t_end is None else max(0.0, t_end - time.monotonic())
            try:
                ev = self.events.get(timeout=left)
            except queue.Empty:
                return None
            if types is None or ev["t"] in types:
                return ev

    def close(self):
        if self._loop is None:
            return
        self._closing = True

        async def shutdown():
            if self.connected:
                try:
                    self._writer.write(proto.encode({"t": "logout"}))
                    await asyncio.wait_for(self._writer.drain(), 1)
                except (OSError, ConnectionError, asyncio.TimeoutError):
                    pass
            await self._drop_game_socket()
            await self._drop_bridge()
            if self._mapper is not None:
                await asyncio.get_running_loop().run_in_executor(None, self._mapper.unmap)
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            if self._writer is not None:
                self._writer.close()
                try:
                    await asyncio.wait_for(self._writer.wait_closed(), 1)
                except Exception:   # noqa: BLE001 -- closing anyway
                    pass
            self.connected = False
        try:
            asyncio.run_coroutine_threadsafe(shutdown(), self._loop).result(5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._loop = None


def is_local_address(host):
    """True for this PC and private (LAN) addresses: where a plain connection does not cross the
    internet. Host names are resolved."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        try:
            addr = ipaddress.ip_address(socket.gethostbyname(host))
        except (OSError, ValueError):
            return False
    return addr.is_loopback or addr.is_private or addr.is_link_local
