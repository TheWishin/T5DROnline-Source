"""Login flood against a lobby server: wrong passwords for real account names from many addresses at
once, while a few honest players measure the server's response time.

Starts the server from a lobby folder (file database, default scrypt cost, optionally pinned to two
CPUs like a 2 vCPU VPS), registers --accounts accounts, then for --seconds runs --attackers
connections (each from its own loopback address, 127.2.x.y) that send wrong passwords as fast as the
answers come, and --players honest guests that ping every second. Prints the server's peak memory and
threads, CPU, how many password checks it ran, and the honest players' ping times.

    python lobby/tools/login_flood.py --attackers 150 --seconds 60
    python lobby/tools/login_flood.py --lobby-dir C:/other/checkout/lobby ...     # compare builds
"""
import argparse
import asyncio
import json
import os
import random
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from t5lobby import proto  # noqa: E402
from soak_test import BUILD, pct, pin, proc_stats, server_status, start_server  # noqa: E402


async def conn(ip, port):
    r, w = await asyncio.open_connection("127.0.0.1", port, local_addr=(ip, 0), limit=1 << 21)

    async def req(msg, timeout=30):
        w.write(proto.encode(msg))
        await w.drain()
        while True:
            line = await asyncio.wait_for(r.readuntil(b"\n"), timeout)
            m = json.loads(line)
            if m.get("t") not in ("lobby_state", "lobby_delta", "notice", "server_notice", "chat"):
                return m
    hello = await req({"t": "hello", "proto": 1, "client": "flood", "build": BUILD})
    if hello.get("t") != "welcome":
        w.close()
        raise ConnectionError(str(hello.get("msg")))
    return r, w, req


async def run(a, port, status_port, proc):
    names = [f"Acct{i:03d}" for i in range(a.accounts)]
    for i, n in enumerate(names):
        _r, w, req = await conn(f"127.3.0.{i + 1}", port)
        m = await req({"t": "login", "mode": "register", "name": n, "password": "right-password"})
        assert m.get("t") == "login_ok", m
        w.close()
    stop = asyncio.Event()
    lat, codes = [], {}

    async def honest(i):
        try:
            _r, w, req = await conn(f"127.4.0.{i + 1}", port)
            await req({"t": "login", "mode": "guest", "name": f"Honest{i:02d}"})
            while not stop.is_set():
                t0 = time.perf_counter()
                await req({"t": "ping"}, 60)
                lat.append((time.perf_counter() - t0) * 1000)
                await asyncio.sleep(1.0)
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError) as e:
            codes["honest_" + type(e).__name__] = codes.get("honest_" + type(e).__name__, 0) + 1

    async def attacker(i):
        ip = f"127.2.{1 + i // 250}.{1 + i % 250}"
        while not stop.is_set():
            try:
                _r, w, req = await conn(ip, port)
                while not stop.is_set():
                    m = await req({"t": "login", "mode": "account", "name": random.choice(names),
                                   "password": "guess-%d" % random.randrange(10 ** 6)}, 60)
                    k = m.get("code") or m.get("t")
                    codes[k] = codes.get(k, 0) + 1
            except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError,
                    asyncio.LimitOverrunError, ValueError) as e:
                codes["conn_" + type(e).__name__] = codes.get("conn_" + type(e).__name__, 0) + 1
                await asyncio.sleep(0.5)

    tasks = [asyncio.ensure_future(honest(i)) for i in range(a.players)]
    await asyncio.sleep(1.0)
    st0 = proc_stats(proc.pid)
    t0 = time.monotonic()
    tasks += [asyncio.ensure_future(attacker(i)) for i in range(a.attackers)]
    peak = {"rss_mb": 0, "threads": 0, "private_mb": 0}
    while time.monotonic() - t0 < a.seconds:
        await asyncio.sleep(0.5)
        s = await asyncio.to_thread(proc_stats, proc.pid)
        if s is None:
            break
        for k in peak:
            peak[k] = max(peak[k], s[k] or 0)
    st1 = proc_stats(proc.pid)
    srv = await asyncio.to_thread(server_status, status_port)
    stop.set()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    c = (srv or {}).get("counters", {})
    return {"attackers": a.attackers, "seconds": a.seconds,
            "server_alive": proc.poll() is None,
            "cpu_pct": round(100 * (st1["cpu_s"] - st0["cpu_s"]) / (time.monotonic() - t0), 1) if st1 else None,
            "peak_rss_mb": round(peak["rss_mb"], 1), "peak_private_mb": round(peak["private_mb"], 1),
            "peak_threads": peak["threads"],
            "password_checks_failed": c.get("login_failures"), "pw_busy": c.get("pw_busy"),
            "ping_n": len(lat), "ping_p50": pct(lat, 50), "ping_p99": pct(lat, 99),
            "ping_max": round(max(lat), 1) if lat else None, "answers": codes}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lobby-dir", default=os.path.dirname(HERE))
    ap.add_argument("--attackers", type=int, default=150)
    ap.add_argument("--accounts", type=int, default=20)
    ap.add_argument("--players", type=int, default=20)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--cpus", default="2,3")
    ap.add_argument("--priority", default="above")
    a = ap.parse_args()
    work = tempfile.mkdtemp(prefix="t5flood-")
    proc, port, _udp, status, slog = start_server(a.lobby_dir, work, {"T5L_MAX_CLIENTS": "1000"})
    try:
        pin(proc.pid, [int(c) for c in a.cpus.split(",") if c], a.priority)
        loop = proto.new_event_loop()
        print(json.dumps(loop.run_until_complete(run(a, port, status, proc))))
        loop.close()
    finally:
        proc.terminate()
        proc.wait(15)
        slog.close()


if __name__ == "__main__":
    main()
