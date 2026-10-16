"""LobbyClient: the launcher's side of the lobby.

It runs its own thread with an asyncio loop, so a tkinter (or any) UI can call
its methods from the UI thread and poll `client.events` (a queue.Queue) for
what the server says. Every event is a dict with "t" -- the server's message
types (lobby_state, chat, challenged, match_found, match_cancel, match_result,
notice, ...) plus the client's own:

    {"t": "match_start", "ticket": MatchTicket, ...}   both players are connected: start the game
    {"t": "nat_status", "match": id, "phase": "register"|"punch"|"relay"|"measure", "text": ...}
    {"t": "disconnected", "reason": str}

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
import queue
import socket
import ssl
import threading
import time

from . import proto
from .handover import MatchTicket
from .nat import GameSocket, local_ipv4s, server_rtt
from .proto import LobbyError

CLIENT_NAME = "t5lobby-client/0.1"


class LobbyClient:
    def __init__(self, server, build, on_event=None, tls=False, tls_fingerprint=None, game_port=0,
                 auto_ready=False, handover="port", block_direct=False, request_timeout=10.0):
        """server: "host[:port]". build: BuildInfo. on_event: optional callable(event) run on the
        client thread (use the `events` queue from a UI). game_port: local UDP port for the game
        (0 = any free one; set it when the player forwarded a port on the router).
        handover: "port" (close the socket, the game binds the same port) or "share" (keep a duplicate
        socket for MatchTicket.share_socket). block_direct: testing only -- ignore the peer's direct
        packets so that punching fails and the relay is used."""
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

        self.events = queue.Queue()
        self.welcome = None
        self.me = None
        self.token = None
        self.players = []
        self.rooms = []
        self.queue_sizes = {}
        self.match = None            # dict: the current match (from match_found, updated as it goes)
        self.ticket = None           # the last MatchTicket
        self.server_ip = None
        self.server_rtt = None
        self.connected = False

        self._loop = None
        self._thread = None
        self._reader = self._writer = None
        self._rid = 0
        self._pending = {}
        self._tasks = []
        self._gs = None              # GameSocket of the current match
        self._nat_task = None
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

    def _emit(self, ev):
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
        return self._run(self._connect(timeout), timeout + 2)

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
            raise LobbyError("connect_failed", f"cannot reach {self.host}:{self.port} ({e})") from None
        if self.tls_fingerprint:
            der = self._writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
            if hashlib.sha256(der).hexdigest() != self.tls_fingerprint:
                self._writer.close()
                raise LobbyError("tls_mismatch", "the server's certificate does not match the pinned one")
        self.server_ip = self._writer.get_extra_info("peername")[0]
        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.connected = True
        self._tasks.append(asyncio.ensure_future(self._read_loop()))
        self.welcome = await self._request({"t": "hello", "proto": proto.PROTO_VERSION, "client": CLIENT_NAME,
                                            "build": self.build.as_wire()})
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
        except (asyncio.IncompleteReadError, ConnectionError, OSError) as e:
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
            if not self._closing:
                self._emit({"t": "disconnected", "reason": reason})

    async def _dispatch(self, msg):
        t = msg["t"]
        rid = msg.get("re")
        if rid is not None and rid in self._pending:
            fut = self._pending.get(rid)
            if not fut.done():
                if t == "error":
                    fut.set_exception(LobbyError(msg.get("code", "error"), msg.get("msg", "")))
                else:
                    fut.set_result(msg)
            if t in ("error", "ok", "welcome", "login_ok", "queued", "result_ack", "pong", "challenge",
                     "leaderboard", "bye"):
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
        if self.me:
            for p in self.players:
                if p["id"] == self.me["id"]:
                    self.me = p

    async def _on_match_found(self, msg):
        self.match = dict(msg, state="ready")
        self.ticket = None
        if self.auto_ready and msg.get("ready_check"):
            asyncio.ensure_future(self._safe(self._send({"t": "ready", "match": msg["match"], "accept": True})))

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

    async def _on_nat_relay(self, msg):
        if not self._gs or not self.match or self.match["match"] != msg["match"]:
            return False
        self._nat_phase(self._nat_relay(msg))
        return False

    async def _on_match_start(self, msg):
        gs = self._gs
        if gs is None and (not self.match or self.match["match"] != msg["match"]):
            # Resumed session: the game is already running; remember the match for the result report.
            self.match = dict(msg, state="playing")
            self._emit(dict(msg, ticket=None, resumed=True))
            return False
        if gs is None or not self.match or self.match["match"] != msg["match"]:
            return False
        if self._nat_task is not None:
            self._nat_task.cancel()
        if msg["path"] == "relay":
            peer = (self.server_ip, int(msg["relay_port"]))
        else:
            peer = tuple(msg["peer"])
        if msg.get("build") and msg["build"] != self.build.build_id:
            # Should never happen (the server pairs equal builds only) -- refuse rather than desync.
            await self._safe(self._send({"t": "leave_match", "match": msg["match"]}))
            self._emit({"t": "notice", "code": "version_mismatch", "msg": "opponent runs a different build"})
            return False
        ticket = MatchTicket(match_id=msg["match"], role=msg["role"], slot=msg["slot"], local_port=gs.port,
                             peer=peer, path=msg["path"], rtt_ms=msg.get("rtt_ms", 0.0),
                             jitter_ms=msg.get("jitter_ms", 0.0), delay=msg.get("delay", 3),
                             rounds=msg.get("rounds", 3), ranked=msg.get("ranked", False),
                             opponent=msg.get("opponent", {}), build=msg.get("build", ""), seed=msg.get("seed", 0))
        if self.handover == "share" and gs.dup is not None:
            ticket._dup_socket = gs.dup
            gs.dup = None
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

    async def _nat_register(self, msg):
        await self._drop_game_socket()
        mid = msg["match"]
        self._status(mid, "register", "Contacting the lobby server over UDP...")
        gs = await GameSocket.open(self.game_port, (self.server_ip, int(msg["udp_port"])),
                                   int(msg.get("udp_port2") or 0), bytes.fromhex(msg["token"]),
                                   bytes.fromhex(msg["tag"]), int(msg["side"]),
                                   block_direct=self.block_direct, keep_dup=self.handover == "share")
        self._gs = gs
        reg = await gs.register()
        if reg is None:
            self._status(mid, "register", "UDP to the lobby server is blocked (firewall?)")
            return
        public, probe = reg
        nat = "unknown" if probe is None else ("eim" if probe[1] == public[1] else "symmetric")
        addrs = [[ip, gs.port] for ip in local_ipv4s(self.server_ip)]
        self.match.update(public=public, nat=nat, local_port=gs.port)
        await self._send({"t": "nat_local", "match": mid, "addrs": addrs, "nat": nat, "port": gs.port})

    async def _nat_punch(self, msg):
        mid, phase = msg["match"], "punch"
        gs = self._gs
        cands = [(c["ip"], int(c["port"]), c.get("kind", "public")) for c in msg.get("candidates", [])]
        self._status(mid, "punch", "Connecting to your opponent...")
        got = await gs.punch(cands, timeout=float(msg.get("timeout", 3.0)))
        if got is None:
            await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": False})
            return
        addr, kind = got
        self._status(mid, "measure", "Measuring the connection...")
        m = await gs.measure(addr)
        if m is None:
            await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": False})
            return
        rtt, jitter, _n = m
        await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": True, "peer": list(addr), "kind": kind,
                          "rtt_ms": round(rtt, 3), "jitter_ms": round(jitter, 3)})
        # Keep answering the peer's pings until match_start arrives.

    async def _nat_relay(self, msg):
        mid, phase = msg["match"], "relay"
        gs = self._gs
        relay = (self.server_ip, int(msg["udp_port"]))
        self._status(mid, "relay", "Direct connection not possible; using the lobby server's relay...")
        if not await gs.relay_bind(relay):
            await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": False})
            return
        m = await gs.measure(relay, timeout=4.0)
        if m is None:
            await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": False})
            return
        rtt, jitter, _n = m
        await self._send({"t": "nat_result", "match": mid, "phase": phase, "ok": True, "peer": list(relay), "kind": "relay",
                          "rtt_ms": round(rtt, 3), "jitter_ms": round(jitter, 3)})

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
    async def _keepalive(self):
        """Control-channel keepalive (the server drops silent clients) and a fresh UDP RTT to the
        server every 30 s (the lobby shows it and the ranked queue matches on it)."""
        while self.connected:
            for _ in range(30):
                await asyncio.sleep(1.0)
                if not self.connected:
                    return
            await self._safe(self._send({"t": "ping"}))
            if self._gs is None:
                await self._measure_server()

    async def _measure_server(self):
        if not self.welcome:
            return
        try:
            rtt = await server_rtt((self.server_ip, int(self.welcome["udp_port"])))
        except OSError:
            rtt = None
        if rtt is not None:
            self.server_rtt = rtt
            await self._safe(self._send({"t": "udp_rtt", "ms": round(rtt, 2)}))

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
        await self._measure_server()
        self._tasks.append(asyncio.ensure_future(self._keepalive()))
        return self.me

    def login_guest(self, name):
        return self._login({"t": "login", "mode": "guest", "name": name})

    def login(self, name, password):
        return self._login({"t": "login", "mode": "account", "name": name, "password": password})

    def register(self, name, password):
        return self._login({"t": "login", "mode": "register", "name": name, "password": password})

    def resume(self, token=None):
        return self._login({"t": "login", "mode": "resume", "token": token or self.token})

    def quick_match(self):
        return self._call({"t": "queue", "mode": "quick"})

    def ranked_match(self):
        return self._call({"t": "queue", "mode": "ranked"})

    def cancel_queue(self):
        return self._call({"t": "unqueue"})

    def create_room(self, name=None, ranked=False):
        return self._call({"t": "room_create", "name": name, "ranked": ranked})["room"]

    def join_room(self, room_id):
        return self._call({"t": "room_join", "room": room_id})["room"]

    def leave_room(self):
        return self._call({"t": "room_leave"})

    def rematch(self):
        return self._call({"t": "rematch"})

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

    def report_result(self, winner, score=None, match_id=None):
        """winner: 0 (P1 = host) or 1 (P2 = join) or None (draw); score: [P1 rounds, P2 rounds]."""
        mid = match_id or (self.ticket.match_id if self.ticket else None) or (self.match or {}).get("match")
        return self._call({"t": "result", "match": mid, "winner": winner, "score": score})

    def leave_match(self, match_id=None):
        mid = match_id or (self.match or {}).get("match") or (self.ticket.match_id if self.ticket else None)
        return self._call({"t": "leave_match", "match": mid})

    def leaderboard(self, limit=20):
        return self._call({"t": "leaderboard", "limit": limit})["rows"]

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
            for t in self._tasks:
                t.cancel()
            if self._writer is not None:
                self._writer.close()
            self.connected = False
        try:
            asyncio.run_coroutine_threadsafe(shutdown(), self._loop).result(5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._loop = None
