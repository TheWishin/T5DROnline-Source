"""Soak test for the lobby server: many simulated players doing what real players (and some bad
ones) do, for a long time, while the server's CPU, memory, threads, handles and response latency
are sampled.

Starts `python -m t5lobby.server` from a lobby folder as a child process (file database, accounts,
TLS off, automatic backups every few minutes) -- optionally pinned to two CPUs, like a 2 vCPU VPS --
then runs N players in this process. Every player speaks the raw protocol from its own loopback
address (127.1.x.y), so the per-address limits stay at their defaults.

What the players do (shares are of N):
    regular      log in (account or guest), chat now and then, look at the leaderboard and profiles,
                 queue quick or ranked, open and join rooms, accept the ready check, do the NAT
                 steps (UDP registration, punch or relay bind), "play" 35-90 s -- relayed matches
                 send the game's 60 packets/s of 180 bytes each way through the server -- report the
                 same result from both sides, sometimes ask for a rematch, then start over
    dropper  8%  like regular, but loses the lobby connection mid-match and resumes 3-15 s later
                 (one in five never comes back: the grace period settles the match)
    slowreader 3%  logs in and stops reading its socket for minutes (the server must drop it at
                 T5L_MAX_PENDING_KB instead of buffering for ever), then reconnects
    malformed 3% sends broken JSON, wrong types, unknown messages, huge numbers, every few seconds
    oversized 2% sends lines far above the 8 KB limit, then reconnects
    flooder   1% sends 60 messages a second (the server slows it down, then bans the address)
    churner   3% connects, logs in, logs out, again and again

Every player measures the round trip of a `ping` request every 5 s: that is the response latency.

    python lobby/tools/soak_test.py --players 150 --minutes 30 --out build/ls/out/soak.jsonl
    python lobby/tools/soak_test.py --lobby-dir C:/other/checkout/lobby ...      # compare builds

One JSON line every --interval seconds (server process numbers, latency percentiles, what the
players saw) and a summary at the end. Nothing is written into the repository.
"""
import argparse
import asyncio
import ctypes
import hashlib
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
sys.path.insert(0, LOBBY)

from t5lobby import proto  # noqa: E402

BUILD = {"elf": "be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "code": "0123456789abcdef", "net": 1,
         "release": "soak"}


# ----------------------------------------------------------------------------- process numbers
def proc_stats(pid):
    """{cpu_s, rss_mb, private_mb, threads, handles} of a process (Windows or Linux)."""
    if os.name == "nt":
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000 | 0x0010, False, pid)
        if not h:
            return None
        try:
            ft = [wintypes.FILETIME() for _ in range(4)]
            k32.GetProcessTimes(h, *[ctypes.byref(f) for f in ft])
            cpu = sum((f.dwHighDateTime << 32 | f.dwLowDateTime) for f in ft[2:]) / 1e7

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
                           [(n, ctypes.c_size_t) for n in ("Peak", "WorkingSetSize", "QPP", "QP", "QNPP", "QNP",
                                                           "Pagefile", "PeakPagefile", "Private")]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(pmc)
            psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
            handles = wintypes.DWORD()
            k32.GetProcessHandleCount(h, ctypes.byref(handles))
        finally:
            k32.CloseHandle(h)
        return {"cpu_s": cpu, "rss_mb": pmc.WorkingSetSize / 1e6, "private_mb": pmc.Private / 1e6,
                "threads": _threads_nt(pid), "handles": handles.value}
    with open(f"/proc/{pid}/stat") as f:
        parts = f.read().rsplit(")", 1)[1].split()
    tick = os.sysconf("SC_CLK_TCK")
    return {"cpu_s": (int(parts[11]) + int(parts[12])) / tick,
            "rss_mb": int(parts[21]) * os.sysconf("SC_PAGE_SIZE") / 1e6, "private_mb": None,
            "threads": int(parts[17]), "handles": len(os.listdir(f"/proc/{pid}/fd"))}


def _threads_nt(pid):
    from ctypes import wintypes

    class TE32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                    ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x4, 0)
    n = 0
    te = TE32()
    te.dwSize = ctypes.sizeof(te)
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            n += 1
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return n


PRIORITY = {"below": 0x4000, "normal": 0x20, "above": 0x8000}


def pin(pid, cpus, priority=None):
    """CPU affinity (two CPUs: a 2 vCPU VPS) and priority class of one of our processes. On a busy
    development PC (other agents' games) "above" keeps the measurement about the server, not about
    who else wants the CPU; the server needs well under a core either way."""
    if os.name != "nt":
        if cpus:
            os.sched_setaffinity(pid, set(cpus))
        return
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.GetPriorityClass.argtypes = [wintypes.HANDLE]
    k32.GetPriorityClass.restype = wintypes.DWORD
    k32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k32.OpenProcess(0x0200 | 0x0400, False, pid)      # SET_INFORMATION | QUERY_INFORMATION
    if not h:
        raise SystemExit(f"cannot open process {pid} to set its CPUs/priority")
    try:
        if cpus and not k32.SetProcessAffinityMask(h, sum(1 << c for c in cpus)):
            raise SystemExit(f"SetProcessAffinityMask failed for {pid}")
        if priority:
            k32.SetPriorityClass(h, PRIORITY[priority])
            got = k32.GetPriorityClass(h)
            if got != PRIORITY[priority]:            # never run with a priority we did not mean
                raise SystemExit(f"priority class of {pid} is {got:#x}, not {priority}: aborting")
    finally:
        k32.CloseHandle(h)


def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PROFILE_WRAPPER = """
import asyncio, cProfile, sys
secs, out = float(sys.argv[1]), sys.argv[2]
from t5lobby.server import lobby as L
orig = L.LobbyServer.start
pr = cProfile.Profile()
async def start(self):
    await orig(self)
    def dump():
        pr.disable()
        pr.dump_stats(out)
    pr.enable()                                   # the event loop's thread, from now on
    asyncio.get_running_loop().call_later(secs, dump)
L.LobbyServer.start = start
from t5lobby.server.__main__ import main
sys.exit(main([]))
"""


MEMTRACE_WRAPPER = """
import asyncio, sys, tracemalloc
every, out = float(sys.argv[1]), sys.argv[2]
tracemalloc.start(12)
from t5lobby.server import lobby as L
orig = L.LobbyServer.start
async def start(self):
    await orig(self)
    n = [0]
    def snap():
        n[0] += 1
        tracemalloc.take_snapshot().dump(f"{out}-{n[0]:03d}.snap")
        asyncio.get_running_loop().call_later(every, snap)
    asyncio.get_running_loop().call_later(every, snap)
L.LobbyServer.start = start
from t5lobby.server.__main__ import main
sys.exit(main([]))
"""


def start_server(lobby_dir, workdir, env_extra, profile=0.0, memtrace=0.0):
    port, udp, status = free_port(), free_port(socket.SOCK_DGRAM), free_port()
    env = dict(os.environ, T5L_HOST="127.0.0.1", T5L_PORT=str(port), T5L_UDP_PORT=str(udp), T5L_UDP_PORT2="0",
               T5L_DB=os.path.join(workdir, "soak.db"), T5L_LOG_LEVEL="WARNING", T5L_STATUS_PORT=str(status),
               T5L_BACKUP_DIR=os.path.join(workdir, "backups"), T5L_BACKUP_HOURS="0.1", T5L_BACKUP_KEEP="3",
               T5L_STATUS_LOG_MINUTES="0", PYTHONPATH=lobby_dir, PYTHONDONTWRITEBYTECODE="1")
    env.update(env_extra)
    log = open(os.path.join(workdir, "server.log"), "w", encoding="utf-8", errors="replace")
    cmd = [sys.executable, "-m", "t5lobby.server"]
    if profile:
        cmd = [sys.executable, "-c", PROFILE_WRAPPER, str(profile), os.path.join(workdir, "server.prof")]
    elif memtrace:
        cmd = [sys.executable, "-c", MEMTRACE_WRAPPER, str(memtrace), os.path.join(workdir, "mem")]
    proc = subprocess.Popen(cmd, cwd=lobby_dir, env=env, stdout=subprocess.PIPE, stderr=log, text=True)
    line = proc.stdout.readline()
    if "TCP" not in line:
        proc.kill()
        raise SystemExit(f"server did not start: {line}")
    threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()
    return proc, port, udp, status, log


def server_status(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=3) as r:
            return json.loads(r.read())
    except Exception:       # noqa: BLE001 -- the sample just has no status then
        return None


# ----------------------------------------------------------------------------- shared numbers
class Stats:
    def __init__(self):
        self.lat = []                 # ping round trips (ms) since the last sample
        self.lat_all = []
        self.c = {}                   # counters
        self.errs = {}                # error texts the players got -> count
        self.server = None            # the server's own counters at the end

    def inc(self, k, n=1):
        self.c[k] = self.c.get(k, 0) + n


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p / 100.0 * len(xs)))], 2)


# ----------------------------------------------------------------------------- one player
class Gone(Exception):
    pass


class Player:
    def __init__(self, i, h):
        self.i, self.h = i, h
        self.ip = f"127.1.{1 + i // 250}.{1 + i % 250}"
        self.kind = h.kinds[i]
        self.account = self.kind in ("regular", "dropper") and i % 5 != 0     # 4 in 5 have accounts
        self.name = f"{'Soak' if self.account else 'Gst'}{i:04d}"
        self.password = f"pw-{i:04d}-soak"
        self.registered = False
        self.rng = random.Random(i * 7919 + h.seed)
        self.r = self.w = None
        self.rid = 0
        self.pending = {}
        self.token = None
        self.match = None             # current match dict
        self.rooms = {}
        self.events = asyncio.Queue()
        self.gs = None                # UDP game endpoint

    # ---------------------------------------------------------------- connection
    async def connect(self, read=True):
        self.r, self.w = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", self.h.port, local_addr=(self.ip, 0), limit=1 << 21), 10)
        self.pending = {}
        self.events = asyncio.Queue()
        if read:
            self.reader = asyncio.ensure_future(self.read_loop())
        return self

    def spawn(self, coro):
        t = asyncio.ensure_future(coro)
        self.bg = [x for x in getattr(self, "bg", []) if not x.done()] + [t]
        return t

    def close(self):
        for t in getattr(self, "bg", []):
            t.cancel()
        self.bg = []
        if self.w is not None:
            try:
                self.w.close()
            except Exception:       # noqa: BLE001
                pass
        if getattr(self, "reader", None) is not None:
            self.reader.cancel()
        self.w = None

    async def read_loop(self):
        try:
            while True:
                line = await self.r.readuntil(b"\n")
                self.h.st.inc("rx_bytes", len(line))
                try:
                    msg = json.loads(line)
                except ValueError:
                    self.h.st.inc("rx_bad_json")
                    continue
                t = msg.get("t")
                self.h.st.inc("rx_" + str(t))
                if t == "error":
                    self.h.st.errs[str(msg.get("msg"))[:48]] = self.h.st.errs.get(str(msg.get("msg"))[:48], 0) + 1
                fut = self.pending.pop(msg.get("re"), None) if msg.get("re") is not None else None
                if fut is not None and not fut.done():
                    fut.set_result(msg)
                    continue
                if t == "lobby_state":
                    self.rooms = {r["id"]: r for r in msg.get("rooms", [])}
                elif t == "lobby_delta":
                    for rid in msg.get("rooms_gone", ()):
                        self.rooms.pop(rid, None)
                    for r in msg.get("rooms", ()):
                        self.rooms[r["id"]] = r
                elif t in ("match_found", "match_reveal", "nat_begin", "nat_punch", "nat_relay", "match_start",
                           "match_cancel", "match_result", "rematch", "room", "kicked", "error", "notice",
                           "challenged", "set_end", "lag_check"):
                    self.events.put_nowait(msg)
        except (asyncio.IncompleteReadError, ConnectionError, OSError, asyncio.LimitOverrunError):
            pass
        except asyncio.CancelledError:
            raise
        finally:
            for f in self.pending.values():
                if not f.done():
                    f.set_exception(Gone())
            self.events.put_nowait({"t": "_closed"})

    def send(self, msg):
        if self.w is None or self.w.is_closing():
            raise Gone()
        data = proto.encode(msg) if isinstance(msg, dict) else msg
        self.w.write(data)
        self.h.st.inc("tx_bytes", len(data))

    async def req(self, msg, timeout=15.0):
        self.rid += 1
        msg["rid"] = self.rid
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.rid] = fut
        t0 = time.perf_counter()
        self.send(msg)
        await self.w.drain()
        try:
            r = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.pending.pop(self.rid, None)
            self.h.st.inc("req_timeout_" + msg["t"])
            raise Gone()
        ms = (time.perf_counter() - t0) * 1000.0
        if msg["t"] == "ping":
            self.h.st.lat.append(ms)
            self.h.st.lat_all.append(ms)
        return r

    async def hello_login(self):
        w = await self.req({"t": "hello", "proto": 1, "client": "soak", "build": BUILD,
                            "caps": ["delta", "notices", "blind_ready"]})
        if w.get("t") != "welcome":
            self.h.st.inc("hello_refused")
            raise Gone()
        self.udp_port = w["udp_port"]
        if self.account:
            mode = "account" if self.registered else "register"
            r = await self.req({"t": "login", "mode": mode, "name": self.name, "password": self.password}, 30)
            if r.get("t") == "error" and r.get("code") == "name_taken" and mode == "register":
                self.registered = True
                r = await self.req({"t": "login", "mode": "account", "name": self.name, "password": self.password}, 30)
        else:
            r = await self.req({"t": "login", "mode": "guest", "name": self.name})
        if r.get("t") != "login_ok":
            self.h.st.inc("login_refused_" + str(r.get("code")))
            raise Gone()
        self.registered = True
        self.token = r["token"]
        self.h.st.inc("logins")
        return r

    async def resume(self):
        await self.connect()
        w = await self.req({"t": "hello", "proto": 1, "client": "soak", "build": BUILD,
                            "caps": ["delta", "notices", "blind_ready"]})
        r = await self.req({"t": "login", "mode": "resume", "token": self.token})
        ok = r.get("t") == "login_ok"
        self.h.st.inc("resume_ok" if ok else "resume_refused")
        return ok and w.get("t") == "welcome"

    # ---------------------------------------------------------------- background ping (latency)
    async def pinger(self):
        while True:
            await asyncio.sleep(5 + self.rng.random())
            try:
                await self.req({"t": "ping"}, 20)
            except Gone:
                return

    async def next_event(self, types, timeout):
        t_end = time.monotonic() + timeout
        while True:
            left = t_end - time.monotonic()
            if left <= 0:
                return None
            try:
                ev = await asyncio.wait_for(self.events.get(), left)
            except asyncio.TimeoutError:
                return None
            if ev["t"] == "_closed":
                raise Gone()
            if ev["t"] in types:
                return ev

    # ---------------------------------------------------------------- UDP
    async def open_udp(self):
        loop = asyncio.get_running_loop()
        p = self

        class P(asyncio.DatagramProtocol):
            def __init__(self):
                self.waiters = {}
                self.got = 0

            def datagram_received(self, data, addr):
                k = proto.udp_type(data)
                if k is not None and k in self.waiters and not self.waiters[k].done():
                    self.waiters[k].set_result(data)
                elif data[:4] == proto.GAME_MAGIC:
                    self.got += 1
                    p.h.st.inc("game_rx")

            def error_received(self, exc):
                pass
        tr, pr = await loop.create_datagram_endpoint(P, local_addr=(self.ip, 0))
        proto.disable_udp_connreset(tr.get_extra_info("socket"))
        self.gs = (tr, pr)
        return tr.get_extra_info("sockname")[1]

    async def udp_handshake(self, kind, ack, token):
        tr, pr = self.gs
        fut = asyncio.get_running_loop().create_future()
        pr.waiters[ack] = fut
        for _ in range(25):
            tr.sendto(proto.pk_token(kind, token), ("127.0.0.1", self.udp_port))
            try:
                await asyncio.wait_for(asyncio.shield(fut), 0.2)
                return True
            except asyncio.TimeoutError:
                continue
        self.h.st.inc(f"udp_no_ack_{kind}")
        return False

    def close_udp(self):
        if self.gs is not None:
            self.gs[0].close()
            self.gs = None

    async def game_traffic(self, seconds):
        """The game's packets through the relay: 60/s of 180 bytes."""
        tr, pr = self.gs
        payload = proto.GAME_MAGIC + os.urandom(176)
        t_end = time.monotonic() + seconds
        nxt = time.monotonic()
        while time.monotonic() < t_end and self.gs is not None:
            tr.sendto(payload, ("127.0.0.1", self.udp_port))
            self.h.st.inc("game_tx")
            nxt += 1 / 60.0
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))

    # ---------------------------------------------------------------- a match, start to end
    async def play_match(self, found):
        mid = found["match"]
        relay = int(hashlib.sha1(mid.encode()).hexdigest(), 16) % 4 == 0      # both sides agree
        if found.get("ready_check"):
            await asyncio.sleep(self.rng.uniform(0.3, 2.5))
            if self.rng.random() < 0.03:
                self.send({"t": "ready", "match": mid, "accept": False})
                self.h.st.inc("declined")
                return None
            self.send({"t": "ready", "match": mid, "accept": True})
        t_found = time.monotonic()
        ev = await self.next_event(("nat_begin", "match_cancel", "match_start"), 30)
        if ev is None or ev["t"] == "match_cancel":
            self.h.st.inc("match_cancelled_seen")
            return None
        slot = None
        if ev["t"] == "nat_begin":
            token = bytes.fromhex(ev["token"])
            port = await self.open_udp()
            if not await self.udp_handshake(proto.U_REGISTER, proto.U_REG_ACK, token):
                return None
            self.send({"t": "nat_local", "match": mid, "addrs": [[self.ip, port]],
                       "nat": "symmetric" if relay else "eim", "port": port})
            ev = await self.next_event(("nat_punch", "nat_relay", "match_cancel"), 30)
            if ev is None or ev["t"] == "match_cancel":
                return None
            if ev["t"] == "nat_punch":
                await asyncio.sleep(self.rng.uniform(0.1, 0.6))
                c = ev["candidates"][0]
                self.send({"t": "nat_result", "match": mid, "phase": "punch", "ok": True, "kind": "public",
                           "peer": [c["ip"], c["port"]], "rtt_ms": round(self.rng.uniform(15, 70), 2),
                           "jitter_ms": round(self.rng.uniform(0, 4), 2)})
            else:
                if not await self.udp_handshake(proto.U_RELAY_BIND, proto.U_RELAY_ACK, token):
                    return None
                self.send({"t": "nat_result", "match": mid, "phase": "relay", "ok": True, "kind": "relay",
                           "peer": ["127.0.0.1", self.udp_port], "rtt_ms": round(self.rng.uniform(30, 90), 2),
                           "jitter_ms": round(self.rng.uniform(0, 6), 2)})
            ev = await self.next_event(("match_start", "match_cancel"), 30)
            if ev is None or ev["t"] == "match_cancel":
                return None
        self.h.st.inc("match_start_seen")
        self.h.st.inc("setup_ms_sum", int((time.monotonic() - t_found) * 1000))
        slot = ev["slot"]
        path = ev["path"]
        hm = hashlib.sha1(mid.encode()).digest()
        seconds = 35 + hm[2] % 56 if self.h.short is None else self.h.short    # both games end together
        t_play = time.monotonic()
        traffic = None
        if path == "relay" and self.gs is not None:
            traffic = asyncio.ensure_future(self.game_traffic(seconds + 2))
        try:
            dropped = False
            if self.kind == "dropper" and self.rng.random() < 0.5:
                await asyncio.sleep(seconds * self.rng.uniform(0.2, 0.7))
                self.close()
                self.h.st.inc("dropped_mid_match")
                if self.rng.random() < 0.2:
                    self.h.st.inc("dropped_for_good")
                    raise Gone()
                await asyncio.sleep(self.rng.uniform(3, 15))
                if not await self.resume():
                    raise Gone()
                self.spawn(self.pinger())
                dropped = True
                await self.next_event(("match_start",), 10)
            await asyncio.sleep(max(0.5, seconds - (time.monotonic() - t_play)))
            h = hm
            winner = h[0] & 1
            score = [3, h[1] % 3] if winner == 0 else [h[1] % 3, 3]
            await asyncio.sleep(self.rng.uniform(0.1, 1.5))
            self.send({"t": "result", "match": mid, "winner": winner, "score": score, "source": "game",
                       "desync": 0, "hash": h.hex()[:16], "frames": int(seconds * 60)})
            ev = await self.next_event(("match_result",), 200)
            if ev is None:
                self.h.st.inc("no_match_result")
                return None
            self.h.st.inc("result_" + ev["status"])
            if dropped:
                self.h.st.inc("resumed_match_settled")
            if self.rng.random() < 0.5:
                self.send({"t": "lag", "match": mid, "frames": int(seconds * 60), "waited_ms": self.rng.uniform(0, 400)})
            return ev
        finally:
            if traffic is not None:
                traffic.cancel()
            self.close_udp()

    # ---------------------------------------------------------------- behaviours
    async def regular(self):
        await self.connect()
        await self.hello_login()
        self.spawn(self.pinger())
        self.send({"t": "udp_rtt", "ms": round(self.rng.uniform(10, 120), 1)})
        while True:
            await asyncio.sleep(self.rng.uniform(1, 6))
            x = self.rng.random()
            if x < 0.05:
                self.send({"t": "chat", "text": f"gg {self.rng.randrange(1000)}"})
                continue
            if x < 0.10:
                await self.req({"t": "leaderboard", "limit": 20})
                await self.req({"t": "profile", "name": f"Soak{self.rng.randrange(len(self.h.kinds)):04d}"})
                continue
            if x < 0.30 and self.rooms:
                open_ = [r for r in self.rooms.values() if r.get("status") == "open"]
                if open_:
                    r = await self.req({"t": "room_join", "room": self.rng.choice(open_)["id"]})
                    if r.get("t") == "room":
                        await self.room_session(joined=True)
                    continue
            if x < 0.40:
                r = await self.req({"t": "room_create", "name": f"room {self.i}"})
                if r.get("t") == "room":
                    await self.room_session(joined=False)
                continue
            mode = "ranked" if self.account and self.rng.random() < 0.6 else "quick"
            r = await self.req({"t": "queue", "mode": mode, "char": "random"})
            if r.get("t") != "queued":
                continue
            ev = await self.next_event(("match_found",), self.rng.uniform(40, 120))
            if ev is None:
                self.send({"t": "unqueue"})
                self.h.st.inc("queue_gave_up")
                continue
            res = await self.play_match(ev)
            while res is not None and self.rng.random() < 0.3:
                ack = await self.req({"t": "rematch", "match": res["match"], "accept": True})
                if ack.get("state") not in ("accepted", "waiting"):
                    break
                ev = None
                t_end = time.monotonic() + 25
                while time.monotonic() < t_end:
                    ev = await self.next_event(("match_found", "rematch"), t_end - time.monotonic())
                    if ev is None or ev["t"] == "match_found" or ev.get("state") == "declined":
                        break
                if ev is None or ev["t"] != "match_found":
                    break
                res = await self.play_match(ev)

    async def room_session(self, joined):
        """In a room: wait for a second player (owner) or the match (joiner), play, leave."""
        ev = await self.next_event(("match_found",), 45 if not joined else 10)
        if ev is not None:
            res = await self.play_match(ev)
            if res is not None and self.rng.random() < 0.3:
                self.send({"t": "rematch"})
                ev = await self.next_event(("match_found",), 10)
                if ev is not None:
                    await self.play_match(ev)
        for _ in range(3):
            r = await self.req({"t": "room_leave"})
            if r.get("t") != "error" or r.get("code") != "busy":
                return
            # The other player started the next match in the room meanwhile: leave that one first.
            found = None
            while not self.events.empty():
                ev = self.events.get_nowait()
                if ev["t"] == "_closed":
                    raise Gone()
                if ev["t"] == "match_found":
                    found = ev
            if found is not None:
                self.send({"t": "leave_match", "match": found["match"]})
            await asyncio.sleep(1.0)
        self.h.st.inc("room_stuck")

    async def slowreader(self):
        await self.connect()
        await self.hello_login()
        self.w.transport.pause_reading()      # stop reading: the socket buffers fill, then the server's queue
        self.h.st.inc("slowreader_paused")
        t0 = time.monotonic()
        while time.monotonic() - t0 < self.rng.uniform(120, 400):
            await asyncio.sleep(10)
            try:
                self.send({"t": "ping"})      # keep the idle timer happy (the server still reads us)
            except Gone:
                break
        self.close()

    async def malformed(self):
        await self.connect()
        await self.hello_login()
        bad = [b"{nope\n", b"[1,2,3]\n", b'{"t":5}\n', b'{"t":"no_such_thing"}\n', b'{"t":"queue","mode":[1]}\n',
               b'{"t":"chat","text":{"a":1}}\n', b'{"t":"leaderboard","offset":' + b"9" * 40 + b"}\n",
               b'{"t":"profile","history":"x"}\n', b'{"t":"nat_local","match":"m0","addrs":"zz"}\n',
               b'{"t":"result","match":"m0","winner":7}\n', b'\xff\xfe\xfd\n', b'{"t":"room_join","room":{}}\n',
               b'{"t":"udp_rtt","ms":"fast"}\n', b'{"t":"ping","rid":{"deep":[[[[1]]]]}}\n']
        while True:
            await asyncio.sleep(self.rng.uniform(2, 8))
            self.send(self.rng.choice(bad))
            self.h.st.inc("malformed_sent")

    async def oversized(self):
        await self.connect()
        await self.hello_login()
        await asyncio.sleep(self.rng.uniform(5, 30))
        self.send(b'{"t":"chat","text":"' + b"A" * self.rng.choice((9000, 20000, 200000)) + b'"}\n')
        self.h.st.inc("oversized_sent")
        await asyncio.sleep(2)
        self.close()

    async def flooder(self):
        await self.connect()
        await self.hello_login()
        t_end = time.monotonic() + self.rng.uniform(20, 60)
        while time.monotonic() < t_end:
            self.send({"t": "ping"})
            self.h.st.inc("flood_sent")
            await asyncio.sleep(1 / 60.0)
        self.close()

    async def churner(self):
        await self.connect()
        await self.hello_login()
        await asyncio.sleep(self.rng.uniform(1, 10))
        self.send({"t": "logout"})
        await asyncio.sleep(0.2)
        self.close()

    async def run(self, stop):
        fn = getattr(self, self.kind)
        await asyncio.sleep(self.rng.uniform(0, self.h.ramp))
        while not stop.is_set():
            try:
                await fn()
            except (Gone, ConnectionError, OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
                self.h.st.inc("player_restart_" + type(e).__name__)
            except asyncio.CancelledError:
                break
            except Exception as e:      # noqa: BLE001 -- a bug in this tool: count it, keep going
                self.h.st.inc("tool_error_" + type(e).__name__)
            finally:
                self.close()
                self.close_udp()
            await asyncio.sleep(self.rng.uniform(1, 8))


# ----------------------------------------------------------------------------- the run
class Harness:
    def __init__(self, a, port, status_port, proc):
        self.port, self.status_port, self.proc = port, status_port, proc
        self.st = Stats()
        self.seed = a.seed
        self.ramp = a.ramp
        self.short = a.match_seconds
        n = a.players
        shares = [("dropper", 0.08), ("slowreader", 0.03), ("malformed", 0.03), ("oversized", 0.02),
                  ("flooder", 0.01), ("churner", 0.03)]
        kinds = []
        for k, s in shares:
            kinds += [k] * max(1, round(n * s))
        kinds += ["regular"] * (n - len(kinds))
        random.Random(a.seed).shuffle(kinds)
        self.kinds = kinds


async def run(a, proc, port, status_port, out):
    h = Harness(a, port, status_port, proc)
    stop = asyncio.Event()
    players = [Player(i, h) for i in range(a.players)]
    tasks = [asyncio.ensure_future(p.run(stop)) for p in players]
    t0 = time.monotonic()
    last = proc_stats(proc.pid)
    last_t = time.monotonic()
    samples = []
    loop_lag = []

    async def lag_probe():
        while True:
            t = time.perf_counter()
            await asyncio.sleep(0.1)
            loop_lag.append((time.perf_counter() - t - 0.1) * 1000)
    probe = asyncio.ensure_future(lag_probe())
    try:
        while time.monotonic() - t0 < a.minutes * 60:
            await asyncio.sleep(a.interval)
            now = time.monotonic()
            ps = await asyncio.to_thread(proc_stats, proc.pid)
            if ps is None or proc.poll() is not None:
                print(json.dumps({"server_died": True, "code": proc.poll()}), file=out, flush=True)
                break
            stt = await asyncio.to_thread(server_status, status_port)
            lat, h.st.lat = h.st.lat, []
            sample = {"t": round(now - t0), "cpu_pct": round(100 * (ps["cpu_s"] - last["cpu_s"]) / (now - last_t), 1),
                      "rss_mb": round(ps["rss_mb"], 1), "private_mb": ps["private_mb"] and round(ps["private_mb"], 1),
                      "threads": ps["threads"], "handles": ps["handles"],
                      "ping_n": len(lat), "ping_p50": pct(lat, 50), "ping_p95": pct(lat, 95), "ping_p99": pct(lat, 99),
                      "ping_max": round(max(lat), 1) if lat else None,
                      "gen_lag_p99_ms": pct(loop_lag, 99)}
            loop_lag.clear()
            sample["c"] = {k: h.st.c.get(k, 0) for k in ("match_start_seen", "result_confirmed", "logins",
                                                         "queue_gave_up", "room_stuck", "no_match_result")}
            sample["restarts"] = sum(v for k, v in h.st.c.items() if k.startswith("player_restart"))
            if stt:
                sample.update(online=stt["players"]["online"], conns=stt["connections"],
                              playing=stt["players"]["playing"], queued=sum(stt["queue"].values()),
                              rooms=stt["rooms"], matches=stt["matches"]["running"],
                              relays=stt["relay"]["sessions"], relay_kbit_s=stt["relay"]["kbit_s"])
            last, last_t = ps, now
            samples.append(sample)
            print(json.dumps(sample), file=out, flush=True)
    finally:
        probe.cancel()
        stop.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    h.st.server = await asyncio.to_thread(server_status, status_port)
    return samples, h.st


def summarize(samples, st, a):
    if not samples:
        return {}
    warm = [s for s in samples if s["t"] >= min(300, samples[-1]["t"] / 3)]      # after the ramp
    cpu = [s["cpu_pct"] for s in warm]
    rss = [s["rss_mb"] for s in warm]
    # memory trend: least squares slope of RSS over the warm part, MB per hour
    slope = None
    if len(warm) > 2:
        xs = [s["t"] for s in warm]
        mx, my = statistics.mean(xs), statistics.mean(rss)
        den = sum((x - mx) ** 2 for x in xs)
        slope = round(3600 * sum((x - mx) * (y - my) for x, y in zip(xs, rss)) / den, 2) if den else None
    lat = st.lat_all
    c = st.c
    starts = c.get("match_start_seen", 0)
    return {"summary": True, "players": a.players, "minutes": a.minutes,
            "cpu_pct_mean": round(statistics.mean(cpu), 1), "cpu_pct_p95": pct(cpu, 95), "cpu_pct_max": max(cpu),
            "rss_mb_first": warm[0]["rss_mb"], "rss_mb_last": warm[-1]["rss_mb"], "rss_mb_max": max(rss),
            "rss_slope_mb_per_hour": slope,
            "threads_max": max(s["threads"] for s in samples), "threads_last": samples[-1]["threads"],
            "handles_first": warm[0]["handles"], "handles_last": samples[-1]["handles"],
            "handles_max": max(s["handles"] for s in samples),
            "ping_n": len(lat), "ping_p50": pct(lat, 50), "ping_p95": pct(lat, 95), "ping_p99": pct(lat, 99),
            "ping_p999": pct(lat, 99.9), "ping_max": round(max(lat), 1) if lat else None,
            "online_mean": round(statistics.mean(s.get("online", 0) for s in warm), 1),
            "matches_running_mean": round(statistics.mean(s.get("matches", 0) for s in warm), 1),
            "relays_mean": round(statistics.mean(s.get("relays", 0) for s in warm), 1),
            "match_starts_seen": starts, "setup_ms_mean": round(c.get("setup_ms_sum", 0) / max(1, starts)),
            "game_delivered_pct": round(100 * c.get("game_rx", 0) / max(1, c.get("game_tx", 0)), 2),
            "counters": dict(sorted(c.items())),
            "errors_top": dict(sorted(st.errs.items(), key=lambda kv: -kv[1])[:15]),
            "server_counters": (st.server or {}).get("counters"), "server_db": (st.server or {}).get("db")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lobby-dir", default=LOBBY, help="lobby folder whose server to start")
    ap.add_argument("--players", type=int, default=150)
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between samples")
    ap.add_argument("--ramp", type=float, default=60.0, help="players start over this many seconds")
    ap.add_argument("--match-seconds", type=float, default=None, help="fixed match length (default 35-90 s)")
    ap.add_argument("--cpus", default="2,3", help="CPUs the server may use (a 2 vCPU VPS); empty = all")
    ap.add_argument("--priority", choices=sorted(PRIORITY), default=None,
                    help="priority class of the server (it needs well under one core)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=None, help="JSON lines file (default: stdout)")
    ap.add_argument("--env", action="append", default=[], help="extra T5L_X=Y for the server")
    ap.add_argument("--memtrace", type=float, default=0.0, metavar="SECONDS",
                    help="tracemalloc snapshot of the server every SECONDS (work dir: mem-NNN.snap)")
    ap.add_argument("--profile", type=float, default=0.0, metavar="SECONDS",
                    help="profile the server's event loop for this long after start (work dir: server.prof)")
    a = ap.parse_args()
    work = tempfile.mkdtemp(prefix="t5soak-")
    env = dict(kv.split("=", 1) for kv in a.env)
    proc, port, udp, status, slog = start_server(a.lobby_dir, work, env, a.profile, a.memtrace)
    cpus = [int(c) for c in a.cpus.split(",") if c.strip()]
    out = open(a.out, "a", encoding="utf-8") if a.out else sys.stdout
    try:
        pin(proc.pid, cpus, a.priority)
        others = [c for c in range(os.cpu_count() or 1) if c not in cpus] if cpus else []
        pin(os.getpid(), others, None)              # the players never run on the server's CPUs
        print(json.dumps({"start": time.strftime("%Y-%m-%d %H:%M:%S"), "lobby_dir": a.lobby_dir,
                          "players": a.players, "minutes": a.minutes, "cpus": cpus, "priority": a.priority,
                          "work": work}), file=out, flush=True)
        loop = proto.new_event_loop()
        samples, st = loop.run_until_complete(run(a, proc, port, status, out))
        loop.close()
        print(json.dumps(summarize(samples, st, a)), file=out, flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        slog.close()
        if out is not sys.stdout:
            out.close()


if __name__ == "__main__":
    main()
