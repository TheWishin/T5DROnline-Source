"""A tiny HTTP endpoint for operations (health checks, monitoring), standard library only.

    GET /health    "ok" (200) while the server runs -- Docker HEALTHCHECK, uptime monitors
    GET /status    JSON: players online, rooms, queues, matches (running, last 24 h), relay
                   bandwidth, counters, certificate expiry, process CPU / memory
    GET /metrics   the same numbers in Prometheus text format

It listens on 127.0.0.1:7780 by default (T5L_STATUS_HOST / T5L_STATUS_PORT): the numbers are not
secret (no names, no addresses), but nothing outside the machine needs them unless you point a
monitor at it -- then open it to that monitor only."""
import asyncio
import json
import logging
import os
import ssl
import sys
import time

log = logging.getLogger("t5lobby.status")


def process_info():
    """CPU seconds and resident memory of this process (Linux, Windows; others: CPU only)."""
    out = {"pid": os.getpid(), "cpu_s": round(time.process_time(), 2), "rss_mb": None,
           "python": sys.version.split()[0]}
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/self/statm") as f:
                out["rss_mb"] = round(int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6, 1)
        elif os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t),
                            ("d", ctypes.c_size_t), ("e", ctypes.c_size_t), ("f", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(pmc)
            k32 = ctypes.WinDLL("kernel32")
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            gpmi = ctypes.WinDLL("psapi").GetProcessMemoryInfo
            gpmi.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
            if gpmi(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                out["rss_mb"] = round(pmc.WorkingSetSize / 1e6, 1)
    except (OSError, ValueError, AttributeError, TypeError, ArithmeticError):
        pass
    return out


def cert_info(path):
    """Subject and expiry of a PEM certificate (to notice a failed renewal before players do)."""
    try:
        d = ssl._ssl._test_decode_cert(path)       # CPython's own PEM parser; no third-party code
        not_after = ssl.cert_time_to_seconds(d["notAfter"])
        subj = dict(x[0] for x in d.get("subject", ()))
        return {"subject": subj.get("commonName", ""), "not_after": d["notAfter"],
                "days_left": round((not_after - time.time()) / 86400.0, 1)}
    except Exception as e:     # noqa: BLE001
        return {"error": str(e)}


def prometheus(st):
    """Flatten the status dict into Prometheus text exposition format."""
    lines = []

    def g(name, val, help_, labels=""):
        if val is None:
            return
        lines.append(f"# HELP t5lobby_{name} {help_}")
        lines.append(f"# TYPE t5lobby_{name} {'counter' if name.endswith('_total') else 'gauge'}")
        lines.append(f"t5lobby_{name}{labels} {val}")

    g("up", 1, "1 while the server runs")
    g("uptime_seconds", st["uptime_s"], "seconds since start")
    g("players_online", st["players"]["online"], "players connected")
    g("players_guests", st["players"]["guests"], "guests connected")
    g("players_playing", st["players"]["playing"], "players in a running game")
    g("players_queued", st["players"]["in_queue"], "players searching")
    g("connections", st["connections"], "open control connections")
    g("connections_prelogin", st.get("connections_prelogin"), "connections that have not logged in yet")
    g("password_checks_waiting", st.get("password_checks_waiting"), "password hashes waiting for a worker")
    g("draining", int(bool(st.get("draining"))), "1 while admin drain holds back new matches")
    g("rooms", st["rooms"], "open rooms")
    g("matches_running", st["matches"]["running"], "matches being set up or played")
    g("relay_sessions", st["relay"]["sessions"], "relayed matches")
    g("relay_kbit_per_second", st["relay"]["kbit_s"], "relay throughput over the last minute, both directions")
    g("relay_bytes_total", st["relay"]["bytes_total"], "bytes forwarded by the relay")
    g("relay_dropped_total", st["relay"]["dropped_total"], "UDP packets dropped (caps, strangers)")
    for k, v in st["counters"].items():
        g(f"{k}_total", v, k.replace("_", " "))
    db = st.get("db") or {}
    for k in ("accounts", "accounts_seen_24h", "accounts_banned", "ip_bans", "matches_24h"):
        if k in db:
            g(k, db[k], k.replace("_", " "))
    if st.get("tls") and "days_left" in st["tls"]:
        g("tls_cert_days_left", st["tls"]["days_left"], "days until the TLS certificate expires")
    p = st.get("process") or {}
    g("process_cpu_seconds_total", p.get("cpu_s"), "CPU time used")
    g("process_resident_megabytes", p.get("rss_mb"), "resident memory")
    nodes = st.get("relays") or []
    for name, key, help_ in (("relay_node_up", "alive", "1 while a regional relay node answers its health checks"),
                             ("relay_node_sessions", "sessions", "relay sessions open on a regional node"),
                             ("relay_node_kbit_per_second", "kbit_s", "a regional node's throughput, last minute"),
                             ("relay_node_last_seen_seconds", "last_seen_s", "seconds since a node's last answer")):
        rows = [(n["id"], int(n[key]) if isinstance(n.get(key), bool) else n.get(key)) for n in nodes]
        rows = [(rid, v) for rid, v in rows if v is not None]
        if rows:
            lines.append(f"# HELP t5lobby_{name} {help_}")
            lines.append(f"# TYPE t5lobby_{name} gauge")
            lines.extend(f't5lobby_{name}{{relay="{rid}"}} {v}' for rid, v in rows)
    return "\n".join(lines) + "\n"


class StatusHttp:
    def __init__(self, lobby):
        self.lobby = lobby
        self.server = None
        self.port = 0

    async def start(self, host, port):
        self.server = await asyncio.start_server(self._handle, host, port, limit=4096)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        if self.server:
            self.server.close()
            try:
                await asyncio.wait_for(self.server.wait_closed(), 2)
            except asyncio.TimeoutError:
                pass

    async def _handle(self, reader, writer):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            parts = head.split(b"\r\n", 1)[0].decode("latin-1").split()
            method, path = (parts + ["", ""])[:2]
            path = path.split("?", 1)[0]
            cors = False
            if method not in ("GET", "HEAD"):
                code, ctype, body = 405, "text/plain", "GET only\n"
            elif path in ("/health", "/healthz", "/"):
                code, ctype, body = 200, "text/plain", "ok\n"
            elif path == "/status":
                code, ctype, body = 200, "application/json", json.dumps(self.lobby.status(), indent=1) + "\n"
            elif (path == "/tournaments" or path.startswith("/tournaments/")) and \
                    getattr(self.lobby, "tours", None) is not None:
                # the brackets, read-only, for streamers' overlays (docs/TOURNAMENTS.md "For streamers")
                code, body = self.lobby.tours.http(path)
                ctype, cors = "application/json", True
            elif path == "/metrics":
                metrics = getattr(self.lobby, "metrics", None)        # (a relay node has its own)
                code, ctype, body = 200, "text/plain; version=0.0.4", (
                    metrics() if metrics is not None else prometheus(self.lobby.status()))
            else:
                code, ctype, body = 404, "text/plain", "not found\n"
            data = body.encode("utf-8")
            reason = {200: "OK", 404: "Not Found", 405: "Method Not Allowed"}[code]
            # (an overlay in a browser source may read the brackets from another origin)
            extra = "Access-Control-Allow-Origin: *\r\n" if cors else ""
            writer.write(f"HTTP/1.0 {code} {reason}\r\nContent-Type: {ctype}\r\nContent-Length: {len(data)}\r\n"
                         f"Cache-Control: no-store\r\n{extra}Connection: close\r\n\r\n".encode("latin-1")
                         + (data if method == "GET" else b""))
            await writer.drain()
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError,
                OSError, UnicodeError):
            pass
        except Exception:     # noqa: BLE001 -- never let a status request hurt the server
            log.exception("status request")
        finally:
            writer.close()
