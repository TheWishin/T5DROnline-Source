"""A relay-only server: the lobby's UDP relay alone, in another region, for one central lobby server.

    python run.py relay --secret-file /etc/t5lobby/relay.secret [--id usw] [--udp-port 7781]
    python run.py relay --gen-secret FILE           make a secret file (copy the same file to the central server)

(= python -m t5lobby.server.relaynode). Lobby, accounts and ranking stay on the central server; a node has no
database and no TCP port. It does three things on one UDP port (T5L_UDP_PORT, default 7781):

* answers the players' UDP pings (SPING): each launcher measures its round trip to every relay the central
  server lists, and the central server picks, for each match that needs a relay, the one with the smallest
  sum of both players' round trips (docs/ONLINE.md "Regional relays");
* takes the central server's control requests (relayctl.py: HMAC-SHA256 under the shared secret, fresh
  timestamp and id) -- open a session for a match with its two bind tokens, renew, report, close -- and
  answers its health checks with the numbers the admin tool shows (sessions, kbit/s);
* relays the two games' packets of each open session, with the central relay's rules (server/udp.py):
  only the game's packets and the lobby's peer packets, at most T5L_RELAY_MAX_BYTES each, per-player
  packet and bandwidth caps, T5L_MAX_RELAYS sessions and T5L_MAX_RELAYS_PER_IP per internet address.
  A bind token works only for T5L_RELAY_BIND_SECONDS after its session opened, a session lives as long as
  the central server's lease (renewed for a rematch inside the running games, never more than
  T5L_RELAY_MAX_SECONDS at a time) and closes after 120 s without a packet. Nobody without a session the
  central server opened can use the node as a proxy.

Status: http://127.0.0.1:7780/ (/health, /status, /metrics), as on the central server; `t5lobby-admin
status` / `health` work against it."""
import argparse
import asyncio
import ipaddress
import logging
import os
import signal
import socket
import sys
import time

from .. import __version__, proto, relayctl
from .config import Config
from .udp import UdpService

log = logging.getLogger("t5lobby.relaynode")

SERVER_NAME = "t5relay/0.1"
IDLE = 120.0               # seconds without a packet before a session is swept up (as on the central relay)
CLOSED_KEEP = 3600.0       # a closed session's id cannot be opened again for this long


def _norm_ip(text):
    try:
        return str(ipaddress.ip_address(str(text).strip().split("%", 1)[0]))
    except ValueError:
        return None


def resolve_hosts(names):
    """Addresses of the central server(s) for T5L_RELAY_CENTRAL: IPs as they are, names resolved once."""
    out = set()
    for n in names:
        ip = _norm_ip(n)
        if ip:
            out.add(ip)
            continue
        try:
            for ai in socket.getaddrinfo(n, None, socket.AF_UNSPEC, socket.SOCK_DGRAM):
                out.add(_norm_ip(ai[4][0]))
        except OSError as e:
            log.warning("T5L_RELAY_CENTRAL: cannot resolve %s (%s)", n, e)
    out.discard(None)
    return out


class RelayNode:
    def __init__(self, cfg, secret):
        self.cfg = cfg
        self.secret = secret
        self.udp = UdpService(self, cfg)
        self.started = time.time()
        self.seen = relayctl.SeenIds()
        self.meta = {}          # sid -> {"bind_until", "deadline"} (monotonic)
        self.closed = {}        # sid -> monotonic time until which it stays closed
        self.central = resolve_hosts(cfg.relay_central)
        self.counters = dict.fromkeys(("ctl_requests", "ctl_refused", "ctl_clock", "sessions_opened",
                                       "sessions_closed", "sessions_expired", "sessions_idle", "sessions_unbound",
                                       "binds_refused", "sessions_refused_full"), 0)
        self.last_central = None    # monotonic time of the last valid request
        self._samples = []          # (monotonic, bytes relayed so far)
        self._last_status_log = time.monotonic()
        self.status_http = None
        self.tasks = []

    # ------------------------------------------------------------------ lifecycle
    async def start(self):
        loop = asyncio.get_running_loop()
        await self.udp.start(loop)
        if self.cfg.status_port:
            from .status import StatusHttp
            self.status_http = StatusHttp(self)
            try:
                await self.status_http.start(self.cfg.status_host, max(0, self.cfg.status_port))
            except OSError as e:
                log.warning("status endpoint %s:%s unavailable (%s)", self.cfg.status_host, self.cfg.status_port, e)
                self.status_http = None
        self.tasks = [asyncio.ensure_future(self._tick())]
        log.info("relay node %s listening: UDP %s:%d%s%s", self.cfg.relay_id or "(no id)", self.cfg.host,
                 self.udp.port, f", control only from {sorted(self.central)}" if self.central else "",
                 f", status http://{self.cfg.status_host}:{self.status_http.port}/" if self.status_http else "")

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.status_http:
            await self.status_http.stop()
        self.udp.close()

    @property
    def port(self):
        return self.udp.port

    # ------------------------------------------------------------------ UdpService hooks
    def udp_register(self, token, addr, probe):
        return False            # registration and the NAT probe belong to the central server

    def udp_relay_bound(self, sid, side, addr):
        log.debug("session %s: side %d bound", sid, side)

    def relay_bind_allowed(self, s, side, addr):
        """A RELAY_BIND with a session's token: only while its tokens are fresh, and not from an address that
        already holds T5L_MAX_RELAYS_PER_IP other sessions."""
        meta = self.meta.get(s.match_id)
        now = time.monotonic()
        if meta is None or now > meta["bind_until"]:
            self.counters["binds_refused"] += 1
            return False
        cap = self.cfg.max_relays_per_ip
        if cap > 0 and s.ep[side] is None:
            key = proto.address_key(addr[0], self.cfg.ipv6_prefix)
            n = sum(1 for o in self.udp.relays.values() if o is not s and any(
                ep is not None and proto.address_key(ep[0], self.cfg.ipv6_prefix) == key for ep in o.ep))
            if n >= cap:
                self.counters["binds_refused"] += 1
                log.info("session %s: bind refused (%d sessions from that address)", s.match_id, n)
                return False
        return True

    def relay_control(self, data, addr, transport):
        """One control datagram from the central server (relayctl.py). Anything that is not a fresh, authentic
        request gets no answer."""
        if self.central and _norm_ip(addr[0]) not in self.central:
            self.counters["ctl_refused"] += 1
            return
        got = relayctl.unpack(self.secret, data)
        if got is None or got[0] != relayctl.REQUEST:
            self.counters["ctl_refused"] += 1
            return
        msg = got[1]
        rid, ts, op = msg.get("id"), msg.get("ts"), msg.get("op")
        if not (isinstance(rid, str) and 8 <= len(rid) <= 64 and isinstance(ts, (int, float))
                and op in relayctl.OPS):
            self.counters["ctl_refused"] += 1
            return
        if self.cfg.relay_id and msg.get("node") != self.cfg.relay_id:
            self.counters["ctl_refused"] += 1        # meant for another node that shares the secret
            return
        if not self.seen.add(rid):
            self.counters["ctl_refused"] += 1        # played back
            return
        now = time.time()
        if abs(ts - now) > relayctl.CLOCK_SKEW:
            # (authentic and new, so worth one answer: the central server logs the clock difference)
            self.counters["ctl_clock"] += 1
            reply = {"ok": False, "error": "clock"}
        else:
            self.counters["ctl_requests"] += 1
            try:
                reply = getattr(self, "op_" + op)(msg)
            except (KeyError, TypeError, ValueError) as e:
                reply = {"ok": False, "error": "bad_request", "detail": str(e)[:80]}
        self.last_central = time.monotonic()
        reply.update(re=rid, ts=round(time.time(), 3))
        out = relayctl.pack(self.secret, relayctl.REPLY, reply)
        if len(out) <= relayctl.MAX_PACKET:
            transport.sendto(out, addr)

    # ------------------------------------------------------------------ control operations
    def _lease(self, msg):
        lease = float(msg.get("lease") or 0)
        cap = self.cfg.relay_max_seconds
        if lease <= 0:
            lease = cap if cap > 0 else 3 * 3600.0
        return min(lease, cap) if cap > 0 else lease

    @staticmethod
    def _sid(msg):
        sid = msg["sid"]
        if not (isinstance(sid, str) and 8 <= len(sid) <= 32 and all(c in "0123456789abcdef" for c in sid)):
            raise ValueError("bad sid")
        return sid

    def op_status(self, msg):
        st = self.status()
        return {"ok": True, "server": SERVER_NAME, "version": __version__, "id": self.cfg.relay_id,
                "sessions": st["relay"]["sessions"], "bound": st["relay"]["bound"], "max": st["relay"]["max"],
                "kbit_s": st["relay"]["kbit_s"], "bytes_total": st["relay"]["bytes_total"],
                "packets_total": st["relay"]["packets_total"], "dropped_total": st["relay"]["dropped_total"],
                "uptime_s": st["uptime_s"]}

    def op_open(self, msg):
        sid = self._sid(msg)
        toks = msg["tokens"]
        if not (isinstance(toks, list) and len(toks) == 2):
            raise ValueError("tokens")
        tokens = [bytes.fromhex(str(t)) for t in toks]
        if any(len(t) != proto.TOKEN_LEN for t in tokens) or tokens[0] == tokens[1]:
            raise ValueError("tokens")
        s = self.udp.relays.get(sid)
        if s is not None:
            # a retry of the same request (its answer was lost): fine; anything else under that id: no
            return {"ok": True} if s.tokens == tokens else {"ok": False, "error": "exists"}
        if sid in self.closed:
            return {"ok": False, "error": "closed"}
        if any(t in self.udp.relay_tokens for t in tokens):
            return {"ok": False, "error": "exists"}
        if len(self.udp.relays) >= self.cfg.max_relays:
            self.counters["sessions_refused_full"] += 1
            return {"ok": False, "error": "full"}
        s = self.udp.open_relay(sid, tokens)
        if s is None:
            self.counters["sessions_refused_full"] += 1
            return {"ok": False, "error": "full"}
        now = time.monotonic()
        self.meta[sid] = {"bind_until": now + max(0.1, self.cfg.relay_bind_seconds),
                          "deadline": now + self._lease(msg)}
        self.counters["sessions_opened"] += 1
        log.info("session %s opened (%d open)", sid, len(self.udp.relays))
        return {"ok": True}

    def op_renew(self, msg):
        sid = self._sid(msg)
        meta = self.meta.get(sid)
        if meta is None:
            return {"ok": False, "error": "unknown"}
        meta["deadline"] = time.monotonic() + self._lease(msg)
        return {"ok": True}

    def _session_info(self, s):
        return {"bound": [ep is not None for ep in s.ep], "pkts": list(s.pkts), "bytes": list(s.bytes),
                "dropped": list(s.dropped), "pings": list(s.pings), "pongs": list(s.pongs),
                "age_s": round(time.monotonic() - s.created, 1)}

    def op_info(self, msg):
        s = self.udp.relays.get(self._sid(msg))
        if s is None:
            return {"ok": False, "error": "unknown"}
        return dict(self._session_info(s), ok=True)

    def op_close(self, msg):
        sid = self._sid(msg)
        s = self.udp.relays.get(sid)
        info = self._session_info(s) if s is not None else None
        self._close(sid, "closed by the lobby")
        if info is None:
            return {"ok": False, "error": "unknown"}
        return dict(info, ok=True)

    def _close(self, sid, why):
        self.closed[sid] = time.monotonic() + CLOSED_KEEP
        self.meta.pop(sid, None)
        if sid in self.udp.relays:
            self.udp.close_relay(sid)
            self.counters["sessions_closed"] += 1
            log.info("session %s: %s", sid, why)

    # ------------------------------------------------------------------ upkeep
    def sweep(self, now=None):
        """Sessions past their lease, never bound in time, or idle -> closed."""
        now = time.monotonic() if now is None else now
        for sid, s in list(self.udp.relays.items()):
            meta = self.meta.get(sid)
            if meta is None or now > meta["deadline"]:
                self.counters["sessions_expired"] += 1
                self._close(sid, "lease over")
            elif not s.bound() and now > meta["bind_until"]:
                self.counters["sessions_unbound"] += 1
                self._close(sid, "not bound in time")
            elif now - max(s.last_rx[0], s.last_rx[1], s.created) > IDLE:
                self.counters["sessions_idle"] += 1
                self._close(sid, "idle")
        self.closed = {k: t for k, t in self.closed.items() if t > now}
        self.seen.prune()
        self.udp.ctl_buckets.prune()

    async def _tick(self):
        while True:
            await asyncio.sleep(2.5)
            try:
                self.sweep()
                now = time.monotonic()
                self._samples.append((now, self.udp.stats["relayed_bytes"]))
                del self._samples[:-25]          # one minute of 2.5 s samples
                every = self.cfg.status_log_minutes * 60
                if every > 0 and now - self._last_status_log >= every:
                    self._last_status_log = now
                    st = self.status()["relay"]
                    log.info("status: %d sessions (%d bound), relay %.0f kbit/s, %.1f MB since start",
                             st["sessions"], st["bound"], st["kbit_s"], st["bytes_total"] / 1e6)
            except Exception:
                log.exception("relay node upkeep")

    def kbit_s(self):
        s = self._samples
        if len(s) < 2 or s[-1][0] <= s[0][0]:
            return 0.0
        return 8 * (s[-1][1] - s[0][1]) / (s[-1][0] - s[0][0]) / 1000.0

    def status(self):
        """The status endpoint's JSON (no names, no addresses)."""
        from .status import process_info
        st = self.udp.stats
        last = self.last_central
        return {
            "server": SERVER_NAME, "role": "relay", "id": self.cfg.relay_id, "time": round(time.time()),
            "uptime_s": round(time.time() - self.started),
            "relay": {"sessions": len(self.udp.relays), "bound": sum(1 for s in self.udp.relays.values() if s.bound()),
                      "max": self.cfg.max_relays, "kbit_s": round(self.kbit_s(), 1),
                      "bytes_total": st["relayed_bytes"], "packets_total": st["relayed"],
                      "dropped_total": st["dropped"], "refused_total": st["relay_refused"]},
            "central": {"last_request_s": None if last is None else round(time.monotonic() - last, 1),
                        "allowed": len(self.central)},
            "counters": dict(self.counters),
            "process": process_info(),
        }

    def metrics(self):
        st = self.status()
        r = st["relay"]
        lines = []

        def g(name, val, help_):
            if val is None:
                return
            kind = "counter" if name.endswith("_total") else "gauge"
            lines.extend((f"# HELP t5relay_{name} {help_}", f"# TYPE t5relay_{name} {kind}", f"t5relay_{name} {val}"))
        g("up", 1, "1 while the relay node runs")
        g("uptime_seconds", st["uptime_s"], "seconds since start")
        g("sessions", r["sessions"], "relay sessions open")
        g("sessions_bound", r["bound"], "relay sessions with both players bound")
        g("kbit_per_second", r["kbit_s"], "relay throughput over the last minute, both directions")
        g("bytes_total", r["bytes_total"], "bytes forwarded")
        g("dropped_total", r["dropped_total"], "UDP packets dropped (caps, strangers)")
        g("central_last_request_seconds", st["central"]["last_request_s"], "seconds since the central server's last request")
        for k, v in st["counters"].items():
            g(f"{k}_total", v, k.replace("_", " "))
        p = st["process"]
        g("process_cpu_seconds_total", p.get("cpu_s"), "CPU time used")
        g("process_resident_megabytes", p.get("rss_mb"), "resident memory")
        return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python run.py relay", description="T5DR Online relay-only server")
    ap.add_argument("--secret-file", help="the secret shared with the central server ($T5L_RELAY_SECRET_FILE)")
    ap.add_argument("--id", dest="relay_id", help="this node's id in the central's relays.json ($T5L_RELAY_ID)")
    ap.add_argument("--host", help="bind address (default 0.0.0.0)")
    ap.add_argument("--udp-port", type=int, help="relay port (default 7781)")
    ap.add_argument("--central", help="the central server's address(es), comma separated: control requests from "
                                      "anywhere else are dropped ($T5L_RELAY_CENTRAL)")
    ap.add_argument("--status-port", type=int, help="local status endpoint (default 7780, 0 = off)")
    ap.add_argument("--log-level")
    ap.add_argument("--gen-secret", metavar="FILE", help="write a new secret file (mode 0600) and exit; an existing "
                                                         "one is kept unless --force")
    ap.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.gen_secret:
        existed = os.path.exists(a.gen_secret)
        try:
            relayctl.write_secret(a.gen_secret, force=a.force)
        except (OSError, ValueError) as e:
            print(f"cannot write {a.gen_secret}: {e}", file=sys.stderr)
            return 1
        print(("kept the existing secret in " if existed and not a.force else "new secret in ") + a.gen_secret
              + " -- the central server needs the same file (relays.json \"secret_file\")")
        return 0
    over = {"udp_port2": 0}
    if a.secret_file:
        over["relay_secret_file"] = a.secret_file
    if a.relay_id:
        over["relay_id"] = a.relay_id
    if a.host:
        over["host"] = a.host
    if a.udp_port is not None:
        over["udp_port"] = a.udp_port
    if a.central is not None:
        over["relay_central"] = [x.strip() for x in a.central.split(",") if x.strip()]
    if a.status_port is not None:
        over["status_port"] = a.status_port
    if a.log_level:
        over["log_level"] = a.log_level
    cfg = Config.from_env(**over)
    from .__main__ import setup_logging
    setup_logging(cfg)
    if not cfg.relay_secret_file:
        print("a relay node needs --secret-file (or T5L_RELAY_SECRET_FILE)", file=sys.stderr)
        return 2
    try:
        secret = relayctl.load_secret(cfg.relay_secret_file)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    loop = proto.new_event_loop()
    asyncio.set_event_loop(loop)
    node = RelayNode(cfg, secret)
    stop = asyncio.Event()

    async def run():
        await node.start()
        if sys.stdout is not None:
            print(f"t5relay: UDP {node.port}" + (f", status {node.status_http.port}" if node.status_http else ""),
                  flush=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):
                pass
        await stop.wait()
        await node.stop()

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        loop.run_until_complete(node.stop())
    finally:
        loop.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
