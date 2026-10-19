"""The central server's side of the regional relays (docs/ONLINE.md "Regional relays", docs/HOSTING.md
"Adding a relay server").

Relay-only nodes (server/relaynode.py) run the lobby's UDP relay in other regions. This module keeps their
list (T5L_RELAYS: a relays.json file, re-read when it changes, or the JSON itself), checks every node's
health over the authenticated control channel (relayctl.py) every T5L_RELAY_CHECK_SECONDS, and opens,
renews, inspects and closes relay sessions on them for LobbyServer. A node that has not answered for
T5L_RELAY_DEAD_SECONDS is "down": it is not offered for new matches until it answers again.

relays.json:

    {
      "format": "t5dr-relays/1",
      "relays": [
        {"id": "usw",                         short key (a-z 0-9 - _, at most 16; "main" is the central's own)
         "name": "Oregon (US West)",          what players see ("Relay (Oregon (US West))")
         "host": "203.0.113.7",               the node's IPv4 address or DNS name (players get the address)
         "port": 7781,                        its relay port (default 7781)
         "secret_file": "relay-usw.secret",   the secret shared with that node (relative: next to relays.json;
                                              default: T5L_RELAY_SECRET_FILE)
         "enabled": true}                     false: not offered for new matches (maintenance); running
      ]                                       sessions on it go on
    }
"""
import asyncio
import ipaddress
import json
import logging
import os
import re
import socket
import time

from .. import proto, relayctl

log = logging.getLogger("t5lobby.relays")

MAIN = "main"                  # the central server's own relay in lists, RTT reports and choices
FORMAT = "t5dr-relays/1"
MAX_RELAYS = 32
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")


class RelayNodeRef:
    """One relay node as the central server knows it."""

    def __init__(self, rid, name, host, port, secret, enabled=True):
        self.id = rid
        self.name = name
        self.host = host
        self.port = port
        self.secret = secret
        self.enabled = enabled
        self.ip = None                 # resolved IPv4 address (what the players get)
        self.secret_path = None        # the file the secret came from (a new secret there is picked up)
        self.resolve_at = 0.0          # an unresolvable host name is tried again from this time (monotonic)
        self.alive = False             # answered a health check within T5L_RELAY_DEAD_SECONDS
        self.last_seen = None          # time.monotonic() of the last answer
        self.since = time.monotonic()  # of the last up / down change
        self.stats = {}                # the last status answer
        self.ctl_rtt = None            # ms, the control channel's round trip
        self.error = None              # why it is down, when it said ("clock", ...)
        self.checking = False
        self.warned_plain = False      # logged once: an older node gets the bind tokens readable
        self.opened = 0
        self.open_failed = 0

    @property
    def addr(self):
        return (self.ip, self.port) if self.ip else None

    def same(self, other):
        return (self.id, self.name, self.host, self.port, self.secret, self.enabled) == \
               (other.id, other.name, other.host, other.port, other.secret, other.enabled)

    def public(self):
        return {"id": self.id, "name": self.name, "host": self.ip, "port": self.port}

    def status(self, now=None):
        now = time.monotonic() if now is None else now
        st = self.stats
        return {"id": self.id, "name": self.name, "enabled": self.enabled, "alive": self.alive,
                "resolved": self.ip is not None, "error": self.error,
                "last_seen_s": None if self.last_seen is None else round(now - self.last_seen, 1),
                "ctl_rtt_ms": None if self.ctl_rtt is None else round(self.ctl_rtt, 1),
                "sessions": st.get("sessions"), "bound": st.get("bound"), "max": st.get("max"),
                "kbit_s": st.get("kbit_s"), "bytes_total": st.get("bytes_total"),
                "dropped_total": st.get("dropped_total"), "uptime_s": st.get("uptime_s"),
                "version": st.get("version"), "opened": self.opened, "open_failed": self.open_failed}


class RemoteRelay:
    """A match's relay session on a node: what LobbyServer reads of a udp.RelaySession (ep, pings, pongs, pkts,
    dropped -- for _setup_culprit), filled in from the node's `info` / `close` answers."""
    remote = True
    __slots__ = ("node", "sid", "tokens", "ep", "pings", "pongs", "pkts", "bytes", "dropped", "closed", "created")

    def __init__(self, node, sid, tokens):
        self.node = node
        self.sid = sid
        self.tokens = list(tokens)
        self.ep = [None, None]
        self.pings = [0, 0]
        self.pongs = [0, 0]
        self.pkts = [0, 0]
        self.bytes = [0, 0]
        self.dropped = [0, 0]
        self.closed = False
        self.created = time.monotonic()

    def update(self, info):
        def two(k):
            v = info.get(k)
            return [int(v[0]), int(v[1])] if isinstance(v, list) and len(v) == 2 else None
        b = info.get("bound")
        if isinstance(b, list) and len(b) == 2:
            self.ep = ["bound" if x else None for x in b]
        for k in ("pings", "pongs", "pkts", "bytes", "dropped"):
            v = two(k)
            if v is not None:
                setattr(self, k, v)

    def bound(self):
        return self.ep[0] is not None and self.ep[1] is not None

    def stats(self):
        return {"pkts": list(self.pkts), "bytes": list(self.bytes), "dropped": list(self.dropped),
                "relay": self.node.id}


class _Ctl(asyncio.DatagramProtocol):
    def __init__(self, pool):
        self.pool = pool

    def connection_made(self, transport):
        sock = transport.get_extra_info("socket")
        if sock is not None:
            proto.disable_udp_connreset(sock)

    def datagram_received(self, data, addr):
        try:
            self.pool.datagram(data, addr)
        except Exception:      # noqa: BLE001 -- one bad answer must not stop the channel
            log.exception("relay control answer from %s", addr)

    def error_received(self, exc):
        log.debug("relay control: %s", exc)


def _resolve(host):
    """IPv4 address of a relay's host (an address stays as it is) or None."""
    try:
        return str(ipaddress.IPv4Address(host))
    except ValueError:
        pass
    try:
        for ai in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM):
            return ai[4][0]
    except OSError as e:
        log.warning("relay host %s: %s", host, e)
    return None


def parse(text, base_dir, default_secret_file=""):
    """relays.json text -> [RelayNodeRef] (secrets loaded, addresses not resolved yet). Raises ValueError with a
    sentence an operator can act on."""
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise ValueError(f"relays.json is not valid JSON: {e}") from None
    if isinstance(doc, dict):
        if doc.get("format", FORMAT) != FORMAT:
            raise ValueError(f"relays.json: unknown format {doc.get('format')!r} (this server reads {FORMAT})")
        items = doc.get("relays", [])
    else:
        items = doc
    if not isinstance(items, list) or len(items) > MAX_RELAYS:
        raise ValueError(f"relays.json: \"relays\" must be a list of at most {MAX_RELAYS} entries")
    out, ids = [], set()
    for i, e in enumerate(items):
        if not isinstance(e, dict):
            raise ValueError(f"relays.json entry {i + 1}: not an object")
        rid = str(e.get("id", "")).strip().lower()
        if not _ID_RE.match(rid) or rid == MAIN:
            raise ValueError(f"relays.json entry {i + 1}: id {rid!r} -- a-z, 0-9, - and _, at most 16, not \"{MAIN}\"")
        if rid in ids:
            raise ValueError(f"relays.json: id {rid!r} twice")
        ids.add(rid)
        host = str(e.get("host", "")).strip()
        if not host or len(host) > 253 or any(c.isspace() for c in host):
            raise ValueError(f"relays.json {rid}: \"host\" is the node's address")
        port = e.get("port", proto.DEFAULT_PORT)
        if not isinstance(port, int) or not 0 < port < 65536:
            raise ValueError(f"relays.json {rid}: bad port {port!r}")
        name = proto.clean_text(e.get("name") or rid, 40) or rid
        sf = str(e.get("secret_file") or default_secret_file or "")
        if not sf:
            raise ValueError(f"relays.json {rid}: no \"secret_file\" and no T5L_RELAY_SECRET_FILE")
        if not os.path.isabs(sf) and base_dir:
            sf = os.path.join(base_dir, sf)
        secret = relayctl.load_secret(sf)
        n = RelayNodeRef(rid, name, host, port, secret, enabled=e.get("enabled", True) is not False)
        n.secret_path = sf
        out.append(n)
    return out


class RelayPool:
    def __init__(self, cfg, on_change=None):
        self.cfg = cfg
        self.on_change = on_change         # called (no arguments) when the list players get has changed
        self.nodes = {}                    # id -> RelayNodeRef
        self.pending = {}                  # request id -> (RelayNodeRef, Future)
        self.transport = None
        self._stamp = None                 # modification times of relays.json and the secret files it names
        self._task = None
        self._spawned = set()
        self.error = None                  # why relays.json could not be used (status, log)

    # ------------------------------------------------------------------ lifecycle
    @property
    def configured(self):
        return bool(self.cfg.relays.strip())

    async def start(self):
        if not self.configured:
            return
        loop = asyncio.get_running_loop()
        bind = "0.0.0.0" if ":" not in self.cfg.host else "::"
        self.transport, _p = await loop.create_datagram_endpoint(lambda: _Ctl(self), local_addr=(bind, 0),
                                                                 family=socket.AF_INET if bind == "0.0.0.0" else 0)
        await self.reload(force=True)
        self._task = asyncio.ensure_future(self._health_loop())

    async def stop(self):
        tasks = [t for t in (self._task, *self._spawned) if t is not None]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    def _spawn(self, coro):
        t = asyncio.ensure_future(coro)
        self._spawned.add(t)
        t.add_done_callback(self._spawned.discard)
        return t

    # ------------------------------------------------------------------ the list
    def _source(self):
        """-> (text, base dir, mtime) of T5L_RELAYS: inline JSON, or a file."""
        src = self.cfg.relays.strip()
        if src[:1] in ("[", "{"):
            return src, os.getcwd(), 0
        st = os.stat(src)
        with open(src, encoding="utf-8") as f:
            return f.read(), os.path.dirname(os.path.abspath(src)), st.st_mtime_ns

    def _stamp_now(self, secret_paths=None):
        """What reload() compares: the modification times of relays.json and of the secret files."""
        def mt(path):
            try:
                return os.stat(path).st_mtime_ns
            except OSError:
                return None
        src = self.cfg.relays.strip()
        if secret_paths is None:
            secret_paths = sorted({n.secret_path for n in self.nodes.values() if n.secret_path})
        return (None if src[:1] in ("[", "{") else mt(src)), tuple((sp, mt(sp)) for sp in secret_paths)

    async def reload(self, force=False):
        """Read relays.json again when it (or a secret file it names) changed. -> True when the list players get
        changed. A broken file keeps the last good list (and says why in the log and the status)."""
        if not self.configured:
            return False
        if not force and self._stamp == self._stamp_now():
            return False
        try:
            text, base, _mtime = self._source()
            fresh = parse(text, base, self.cfg.relay_secret_file)
        except (OSError, ValueError) as e:
            msg = str(e)
            if msg != self.error:
                log.error("regional relays: %s -- %s", msg,
                          "keeping the last good list" if self.nodes else "no regional relays")
            self.error = msg
            self._stamp = None        # (tried again every check: a secret file copied over after it is found)
            return False
        self.error = None
        self._stamp = self._stamp_now(sorted({n.secret_path for n in fresh if n.secret_path}))
        loop = asyncio.get_running_loop()
        before = self.public_list()
        nodes = {}
        news = False
        for n in fresh:
            old = self.nodes.get(n.id)
            if old is not None and old.same(n):
                nodes[n.id] = old               # keeps its health
                continue
            news = True
            n.ip = await loop.run_in_executor(None, _resolve, n.host)
            n.resolve_at = time.monotonic() + 60.0
            nodes[n.id] = n
        for rid in set(self.nodes) - set(nodes):
            news = True
            log.info("relay %s removed from the list", rid)
        self.nodes = nodes
        if news or force:
            log.info("regional relays: %s", ", ".join(f"{n.id} ({n.name}, {n.ip or 'unresolved'}:{n.port}"
                                                        f"{'' if n.enabled else ', disabled'})" for n in nodes.values())
                     or "none")
        for n in nodes.values():
            if n.ip is not None and n.enabled and n.last_seen is None and self.transport is not None:
                self._spawn(self._check(n))
        changed = self.public_list() != before
        if changed and self.on_change is not None:
            self.on_change()
        return changed

    def public_list(self):
        """What a client with the "relays" cap gets: every enabled node with an address (up or not: the client
        measures them all in the background; the server picks among the ones that are up)."""
        return [n.public() for n in self.nodes.values() if n.enabled and n.ip is not None]

    def usable(self):
        return [n for n in self.nodes.values() if n.enabled and n.alive and n.ip is not None]

    def get(self, rid):
        return self.nodes.get(rid)

    # ------------------------------------------------------------------ control channel
    def datagram(self, data, addr):
        if not relayctl.is_control(data):
            return
        tried = set()
        for rid, (node, fut) in list(self.pending.items()):
            if node.addr != (addr[0], addr[1]) or id(node.secret) in tried:
                continue
            tried.add(id(node.secret))
            got = relayctl.unpack(node.secret, data)
            if got is None or got[0] != relayctl.REPLY:
                continue
            msg = got[1]
            hit = self.pending.get(msg.get("re"))
            if hit is not None and hit[0] is node and not hit[1].done():
                hit[1].set_result(msg)
            return

    async def request(self, node, op, timeout=1.5, tries=3, bind_tokens=None, **fields):
        """One control request -> the node's answer (dict) or None. Each try is a new datagram with a new id
        (the node refuses an id it has seen); the operations are idempotent. bind_tokens (open): sealed
        under each datagram's id for a node that understands it (relayctl "etokens"), else readable."""
        if self.transport is None or node.addr is None:
            return None
        fut = asyncio.get_running_loop().create_future()
        ids = []
        try:
            for _ in range(max(1, tries)):
                msg = relayctl.request(op, node.id, **fields)
                if bind_tokens is not None:
                    if "etokens" in (node.stats.get("caps") or ()):
                        msg["etokens"] = relayctl.seal_tokens(node.secret, msg["id"], bind_tokens)
                    else:
                        msg["tokens"] = [t.hex() for t in bind_tokens]
                ids.append(msg["id"])
                self.pending[msg["id"]] = (node, fut)
                data = relayctl.pack(node.secret, relayctl.REQUEST, msg)
                try:
                    self.transport.sendto(data, node.addr)
                except OSError as e:
                    log.debug("relay %s: %s", node.id, e)
                try:
                    return await asyncio.wait_for(asyncio.shield(fut), timeout / max(1, tries))
                except asyncio.TimeoutError:
                    continue
            return None
        finally:
            for i in ids:
                self.pending.pop(i, None)
            if not fut.done():
                fut.cancel()

    # ------------------------------------------------------------------ health
    async def _health_loop(self):
        while True:
            await asyncio.sleep(max(0.05, self.cfg.relay_check_seconds))
            try:
                await self.reload()
                await self._resolve_again()
                for n in list(self.nodes.values()):
                    if n.ip is not None and n.enabled and not n.checking:
                        self._spawn(self._check(n))
            except Exception:
                log.exception("relay health check")

    async def _resolve_again(self):
        """A node whose host name did not resolve: try again once a minute (DNS may come later than the file)."""
        now = time.monotonic()
        loop = asyncio.get_running_loop()
        got = False
        for n in list(self.nodes.values()):
            if n.ip is None and n.enabled and now >= n.resolve_at:
                n.resolve_at = now + 60.0
                n.ip = await loop.run_in_executor(None, _resolve, n.host)
                if n.ip is not None:
                    log.info("relay %s: %s is %s", n.id, n.host, n.ip)
                    got = True
        if got and self.on_change is not None:
            self.on_change()

    async def _check(self, n):
        n.checking = True
        try:
            t0 = time.monotonic()
            r = await self.request(n, "status", timeout=min(2.0, max(0.2, self.cfg.relay_check_seconds)), tries=2)
            now = time.monotonic()
            if r is not None and r.get("ok"):
                n.ctl_rtt = (now - t0) * 1000.0
                n.stats = r
                n.last_seen = now
                n.error = None
                if not n.alive:
                    n.alive, n.since = True, now
                    log.info("relay %s (%s) is up: %s sessions, control round trip %.0f ms", n.id, n.name,
                             r.get("sessions"), n.ctl_rtt)
                return
            if r is not None and r.get("error") == "clock":
                skew = float(r.get("ts", 0) or 0) - time.time()
                if n.error != "clock":
                    log.error("relay %s refuses requests: its clock and this server's differ by %.0f s (NTP: "
                              "timedatectl on both)", n.id, skew)
                n.error = "clock"
                self._down(n, now, "clock")
                return
            if n.alive and (n.last_seen is None or now - n.last_seen > self.cfg.relay_dead_seconds):
                self._down(n, now, f"no answer for {self.cfg.relay_dead_seconds:.0f} s")
        finally:
            n.checking = False

    def _down(self, n, now, why):
        if n.alive:
            n.alive, n.since = False, now
            log.warning("relay %s (%s) is down: %s -- not used for new matches", n.id, n.name, why)

    # ------------------------------------------------------------------ sessions
    async def open(self, node, sid, tokens, lease):
        """-> (RemoteRelay or None, error). A node that does not answer is marked down at once."""
        if "etokens" not in (node.stats.get("caps") or ()) and not getattr(node, "warned_plain", False):
            node.warned_plain = True
            log.warning("relay %s runs an older version: its sessions' bind tokens cross the control channel "
                        "readable -- update the node (docs/HOSTING.md, Running relay nodes)", node.id)
        r = await self.request(node, "open", timeout=1.5, tries=3, sid=sid, bind_tokens=list(tokens),
                               lease=round(lease))
        if r is not None and r.get("ok"):
            node.opened += 1
            return RemoteRelay(node, sid, tokens), None
        node.open_failed += 1
        if r is None:
            self._down(node, time.monotonic(), "no answer to a session request")
            return None, "no_answer"
        return None, str(r.get("error") or "refused")

    def close(self, rr):
        """Close a session on its node (in the background, retried); its final numbers land in `rr`."""
        if rr.closed:
            return
        rr.closed = True

        async def go():
            r = await self.request(rr.node, "close", timeout=3.0, tries=4, sid=rr.sid)
            if r is not None:
                rr.update(r)
        self._spawn(go())

    def renew(self, rr, lease):
        async def go():
            await self.request(rr.node, "renew", timeout=3.0, tries=4, sid=rr.sid, lease=round(lease))
        if not rr.closed:
            self._spawn(go())

    async def info(self, rr, timeout=1.5):
        """Refresh `rr` from the node (bound sides, packets, peer pings). -> True when it answered."""
        r = await self.request(rr.node, "info", timeout=timeout, tries=3, sid=rr.sid)
        if r is not None and r.get("ok"):
            rr.update(r)
            return True
        return False

    def status(self):
        now = time.monotonic()
        return [n.status(now) for n in self.nodes.values()]
