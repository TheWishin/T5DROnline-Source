"""Load test for the lobby server: what N players and K relayed matches cost.

Starts `python -m t5lobby.server` from a lobby folder as a child process (so its CPU time and
memory can be read from outside), then

  --players N    N lobby clients speaking the raw protocol (hello, guest login, keepalive and a
                 UDP RTT report every 30 s like the real client, and a status change -- queue /
                 unqueue -- every 20-40 s per player), each from its own loopback address
                 (127.0.x.y) so the per-address limits stay at their defaults;
  --relay K      K matches forced through the relay (T5L_FORCE_RELAY=1) with real LobbyClients,
                 then the game's traffic simulated on the handed-over ports: 60 packets/s of
                 180 bytes each way (what netplay sends, ~85 kbit/s).

and prints the server's CPU use, memory and the bytes it sent to the lobby clients.

    python lobby/tools/load_test.py --players 100 --seconds 60
    python lobby/tools/load_test.py --relay 25 --seconds 30
    python lobby/tools/load_test.py --lobby-dir C:/other/checkout/lobby --players 100   # compare builds
"""
import argparse
import asyncio
import json
import os
import random
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)


# ----------------------------------------------------------------------------- process stats
def proc_stats(pid):
    """(cpu seconds, resident MB) of a process, Windows or Linux."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000 | 0x0010, False, pid)   # QUERY_LIMITED_INFORMATION | VM_READ
        if not h:
            return 0.0, 0.0
        try:
            ft = [wintypes.FILETIME() for _ in range(4)]
            k32.GetProcessTimes(h, *[ctypes.byref(f) for f in ft])
            cpu = sum((f.dwHighDateTime << 32 | f.dwLowDateTime) for f in ft[2:]) / 1e7

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
                           [(n, ctypes.c_size_t) for n in ("Peak", "WorkingSetSize", "QPP", "QP", "QNPP", "QNP",
                                                           "Pagefile", "PeakPagefile")]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(pmc)
            psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
            return cpu, pmc.WorkingSetSize / 1e6
        finally:
            k32.CloseHandle(h)
    with open(f"/proc/{pid}/stat") as f:
        parts = f.read().rsplit(")", 1)[1].split()
    tick = os.sysconf("SC_CLK_TCK")
    cpu = (int(parts[11]) + int(parts[12])) / tick
    rss = int(parts[21]) * os.sysconf("SC_PAGE_SIZE") / 1e6
    return cpu, rss


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(lobby_dir, env_extra):
    port = free_port()
    udp = free_port()
    env = dict(os.environ, T5L_HOST="127.0.0.1", T5L_PORT=str(port), T5L_UDP_PORT=str(udp), T5L_UDP_PORT2="0",
               T5L_DB=":memory:", T5L_LOG_LEVEL="WARNING", T5L_STATUS_PORT="0", PYTHONPATH=lobby_dir,
               **env_extra)
    proc = subprocess.Popen([sys.executable, "-m", "t5lobby.server"], cwd=lobby_dir, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    line = proc.stdout.readline()
    if "TCP" not in line:
        proc.kill()
        raise SystemExit(f"server did not start: {line}{proc.stdout.read()}")
    threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()   # drain
    return proc, port, udp


# ----------------------------------------------------------------------------- lobby clients
BUILD = {"elf": "be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "code": "0123456789abcdef", "net": 1,
         "release": "load"}


class Stats:
    def __init__(self):
        self.rx = 0
        self.msgs = {}
        self.connected = 0
        self.errors = 0


async def lobby_client(i, port, stats, stop, churn):
    src = f"127.0.{1 + i // 250}.{1 + i % 250}"
    try:
        r, w = await asyncio.open_connection("127.0.0.1", port, local_addr=(src, 0), limit=1 << 20)
    except OSError:
        stats.errors += 1
        return

    async def reader():
        try:
            while True:
                line = await r.readuntil(b"\n")
                stats.rx += len(line)
                t = json.loads(line).get("t")
                stats.msgs[t] = stats.msgs.get(t, 0) + 1
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass

    def send(m):
        w.write((json.dumps(m) + "\n").encode())

    rt = asyncio.ensure_future(reader())
    send({"t": "hello", "proto": 1, "client": "load", "build": BUILD, "caps": ["delta"]})
    send({"t": "login", "mode": "guest", "name": f"Load{i:04d}"})
    stats.connected += 1
    rtt = random.uniform(15, 120)
    t_next_keep = time.monotonic() + random.uniform(0, 30)
    t_next_churn = time.monotonic() + random.uniform(5, 40)
    in_room = False
    try:
        while not stop.is_set():
            await asyncio.sleep(0.5)
            now = time.monotonic()
            if now >= t_next_keep:
                t_next_keep = now + 30
                send({"t": "ping"})
                send({"t": "udp_rtt", "ms": round(rtt * random.uniform(0.9, 1.1), 2)})
            if churn and now >= t_next_churn:
                # A status change every 20-40 s: open a room for 5 s, then leave it (idle -> room -> idle).
                send({"t": "room_leave"} if in_room else {"t": "room_create", "name": f"r{i}"})
                t_next_churn = now + (random.uniform(20, 40) if in_room else 5.0)
                in_room = not in_room
            await w.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        rt.cancel()
        w.close()


async def run_lobby(port, n, seconds, churn, proc):
    stats = Stats()
    stop = asyncio.Event()
    tasks = []
    for i in range(n):
        tasks.append(asyncio.ensure_future(lobby_client(i, port, stats, stop, churn)))
        if i % 20 == 19:
            await asyncio.sleep(0.05)
    await asyncio.sleep(5)          # settle: logins, first snapshots
    cpu0, _ = proc_stats(proc.pid)
    rx0, t0 = stats.rx, time.monotonic()
    msgs0 = dict(stats.msgs)
    await asyncio.sleep(seconds)
    cpu1, rss = proc_stats(proc.pid)
    rx1, t1 = stats.rx, time.monotonic()
    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    dt = t1 - t0
    msgs = {k: v - msgs0.get(k, 0) for k, v in stats.msgs.items()}
    return {"players": n, "connected": stats.connected, "errors": stats.errors, "seconds": round(dt, 1),
            "server_cpu_pct": round(100 * (cpu1 - cpu0) / dt, 1), "server_rss_mb": round(rss, 1),
            "lobby_out_kbit_s": round(8 * (rx1 - rx0) / dt / 1000, 1),
            "lobby_out_per_player_kbit_s": round(8 * (rx1 - rx0) / dt / 1000 / max(1, n), 2),
            "messages": msgs}


# ----------------------------------------------------------------------------- relayed matches
def run_relay(port, k, seconds, proc):
    sys.path.insert(0, LOBBY)
    from t5lobby.buildid import BuildInfo
    from t5lobby.client import LobbyClient
    build = BuildInfo(BUILD["elf"], BUILD["code"], "load")
    clients, tickets = [], []
    for i in range(k):
        a = LobbyClient(f"127.0.0.1:{port}", build, auto_ready=True)
        b = LobbyClient(f"127.0.0.1:{port}", build, auto_ready=True)
        for c, nm in ((a, f"A{i:03d}"), (b, f"B{i:03d}")):
            c.connect()
            c.login_guest(nm)
            clients.append(c)
        a.quick_match()
        b.quick_match()
        for c in (a, b):
            ev = c.next_event(20, ("match_start", "match_cancel"))
            if not ev or ev["t"] != "match_start":
                raise SystemExit(f"pair {i}: no match ({ev})")
            tickets.append(ev["ticket"])
    paths = {t.path for t in tickets}
    socks = []
    for t in tickets:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("0.0.0.0", t.local_port))
        s.setblocking(False)
        socks.append((s, t.peer))
    payload = b"T5NP" + os.urandom(176)                       # 180 bytes, like netplay's input packets
    sent = recv = 0
    cpu0, _ = proc_stats(proc.pid)
    t0 = time.monotonic()
    tick = 1 / 60.0
    nxt = t0
    while time.monotonic() - t0 < seconds:
        for s, peer in socks:
            try:
                s.sendto(payload, peer)
                sent += 1
            except OSError:
                pass
        for s, _ in socks:
            while True:
                try:
                    s.recvfrom(2048)
                    recv += 1
                except (BlockingIOError, OSError):
                    break
        nxt += tick
        d = nxt - time.monotonic()
        if d > 0:
            time.sleep(d)
    dt = time.monotonic() - t0
    cpu1, rss = proc_stats(proc.pid)
    for s, _ in socks:
        s.close()
    for c in clients:
        c.close()
    return {"relayed_matches": k, "relayed_players": 2 * k, "paths": sorted(paths), "seconds": round(dt, 1),
            "packets_sent": sent, "packets_received": recv,
            "delivered_pct": round(100 * recv / max(1, sent), 1),
            "send_rate_pps": round(sent / dt), "server_cpu_pct": round(100 * (cpu1 - cpu0) / dt, 1),
            "server_rss_mb": round(rss, 1),
            "relay_kbit_s_each_direction": round(8 * 180 * sent / dt / 1000, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lobby-dir", default=LOBBY, help="lobby folder whose server to start")
    ap.add_argument("--players", type=int, default=0)
    ap.add_argument("--relay", type=int, default=0, help="relayed matches")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--no-churn", action="store_true", help="players never change status")
    a = ap.parse_args()
    env = {"T5L_MAX_CLIENTS": "5000"}
    if a.relay:
        env.update(T5L_FORCE_RELAY="1", T5L_MAX_PER_IP="1000", T5L_CONN_BURST="1000", T5L_CONN_RATE="100",
                   T5L_MAX_RELAYS=str(max(100, a.relay)))
    proc, port, _udp = start_server(a.lobby_dir, env)
    try:
        if a.players:
            res = asyncio.run(run_lobby(port, a.players, a.seconds, not a.no_churn, proc))
            print(json.dumps(res, indent=1))
        if a.relay:
            print(json.dumps(run_relay(port, a.relay, a.seconds, proc), indent=1))
    finally:
        proc.terminate()
        proc.wait(10)


if __name__ == "__main__":
    main()
