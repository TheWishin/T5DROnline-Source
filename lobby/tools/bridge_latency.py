"""What the launcher's relay bridge adds to each game packet, with and without its pump (relay-smooth, 1.1.4;
docs/ONLINE.md "Regional relays", nat.RelayBridge "The pump").

    python tools/bridge_latency.py                       # both ways, quiet PC
    python tools/bridge_latency.py --hog 2 --cpus 2      # the bridge on 2 processors kept busy by a "game"
    python tools/bridge_latency.py --py-load             # ... and a launcher thread busy in Python

A stand-in game (its own process, like t5dr.exe) sends 60 packets/s to a RelayBridge on 127.0.0.1; the bridge
sends them to a stand-in relay that echoes each one at once; the bridge hands the echo to the game -- two passes
through the bridge per sample, as on a relayed match (one per PC). --hog N: N processes that keep processors busy
the way the game's own threads do (THREAD_PRIORITY_HIGHEST, 14 ms of every 16.7 ms frame); --cpus K: this process
(the launcher) and the hogs on the last K processors of the PC only, the stand-ins wherever Windows likes.
--py-load: a thread of this process busy in Python half of the time (a launcher thread at work).
Prints p50 / p95 / p99 / max of the extra round trip, per mode (T5_RELAY_PUMP=0 is the old way)."""
import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
sys.path.insert(0, LOBBY)

from t5lobby import nat, proto  # noqa: E402

IS_WIN = os.name == "nt"

PEER = r'''
import ctypes, json, select, socket, struct, sys, time
if sys.platform == "win32":
    ctypes.WinDLL("winmm").timeBeginPeriod(1)
    k = ctypes.windll.kernel32
    k.SetThreadPriority(ctypes.c_void_p(-2), 2)           # (-2: GetCurrentThread(), typed)
game = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); game.bind(("127.0.0.1", int(sys.argv[1])))
relay = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); relay.bind(("127.0.0.1", 0))
bridge = ("127.0.0.1", int(sys.argv[2])); seconds = float(sys.argv[3])
print(relay.getsockname()[1], flush=True)
sys.stdin.readline()                      # the bridge is open on the relay address
rtts, seq, nxt, t_end = [], 0, time.perf_counter(), time.perf_counter() + seconds
while time.perf_counter() < t_end:
    now = time.perf_counter()
    if now >= nxt:
        seq += 1
        game.sendto(b"T5NP" + struct.pack("<Id", seq, now) + b"\0" * 80, bridge)
        nxt += 1 / 60.0
    r, _, _ = select.select([game, relay], [], [], max(0.0, min(0.002, nxt - now)))
    for s in r:
        data, addr = s.recvfrom(4096)
        if s is relay:
            relay.sendto(data, addr)          # the opponent's game answering at once
        else:
            rtts.append((time.perf_counter() - struct.unpack("<Id", data[4:16])[1]) * 1000.0)
print(json.dumps({"sent": seq, "rtts": rtts}), flush=True)
'''

HOG = r'''
import ctypes, sys, time
k = ctypes.windll.kernel32
assert k.SetThreadPriority(ctypes.c_void_p(-2), 2)      # the game's threads: THREAD_PRIORITY_HIGHEST
if int(sys.argv[1]):
    assert k.SetProcessAffinityMask(ctypes.c_void_p(-1), ctypes.c_size_t(int(sys.argv[1])))
ctypes.WinDLL("winmm").timeBeginPeriod(1)
t_end = time.perf_counter() + float(sys.argv[2])
while time.perf_counter() < t_end:
    t = time.perf_counter() + 0.014
    while time.perf_counter() < t:
        pass
    time.sleep(0.0027)
'''


def cpu_mask(k):
    n = os.cpu_count() or 1
    k = max(1, min(k, n))
    return sum(1 << i for i in range(n - k, n))


def py_load(stop):
    while not stop.is_set():
        t = time.perf_counter() + 0.008
        x = 0
        while time.perf_counter() < t:
            x += 1
        time.sleep(0.008)


def one(pump, seconds, hogs, mask, load):
    if pump:
        os.environ.pop("T5_RELAY_PUMP", None)
    else:
        os.environ["T5_RELAY_PUMP"] = "0"
    loop = proto.new_event_loop()
    th = threading.Thread(target=loop.run_forever, daemon=True)
    th.start()

    def call(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result(10)

    async def make_gs():
        return await nat.GameSocket.open(0, ("127.0.0.1", 9), 0, b"x" * 16, 1, 0)

    gs = call(make_gs())
    game_port = nat.free_udp_port()
    holder = {}

    async def open_bridge():
        # (the stand-in relay's port is known only once the stand-in runs, and that needs the bridge's port)
        holder["b"] = await nat.RelayBridge.open(gs, ("127.0.0.1", 9), game_port=game_port,
                                                 first_burst=time.monotonic() + 3600)

    call(open_bridge())
    b = holder["b"]
    peer = subprocess.Popen([sys.executable, "-c", PEER, str(game_port), str(b.port), str(seconds)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    relay_port = int(peer.stdout.readline())
    b.relay = b.upstream = ("127.0.0.1", relay_port)
    procs = [subprocess.Popen([sys.executable, "-c", HOG, str(mask), str(seconds + 2)]) for _ in range(hogs)]
    stop = threading.Event()
    if load:
        threading.Thread(target=py_load, args=(stop,), daemon=True).start()
    peer.stdin.write("go\n")
    peer.stdin.flush()
    out = json.loads(peer.stdout.readline())
    stop.set()
    for p in procs:
        p.wait()
    peer.wait()
    pumped = b.pump is not None
    raised = pumped and b.pump.raised
    call(b.close())
    loop.call_soon_threadsafe(loop.stop)
    th.join(5)
    rt = sorted(out["rtts"])

    def q(x):
        return rt[min(len(rt) - 1, int(x * (len(rt) - 1)))] if rt else float("nan")
    return {"mode": ("pump (raised)" if raised else "pump") if pumped else "event loop", "sent": out["sent"], "got": len(rt),
            "p50": round(q(0.5), 2), "p95": round(q(0.95), 2), "p99": round(q(0.99), 2), "max": round(q(1.0), 2),
            "over_5ms": sum(1 for x in rt if x > 5.0)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--hog", type=int, default=0)
    ap.add_argument("--cpus", type=int, default=0, help="the launcher and the hogs on the last K processors")
    ap.add_argument("--py-load", action="store_true")
    ap.add_argument("--rounds", type=int, default=1, help="old / new alternately, this many times each")
    a = ap.parse_args()
    mask = cpu_mask(a.cpus) if a.cpus else 0
    if IS_WIN:
        import ctypes
        ctypes.WinDLL("winmm").timeBeginPeriod(1)
        if mask:
            k = ctypes.windll.kernel32
            assert k.SetProcessAffinityMask(ctypes.c_void_p(-1), ctypes.c_size_t(mask))
    print(f"hogs {a.hog} at THREAD_PRIORITY_HIGHEST, cpus {'all' if not mask else hex(mask)}, "
          f"python load {a.py_load}, {a.seconds:g} s each, extra round trip through two bridge passes (ms):")
    for _ in range(a.rounds):
        for pump in (False, True):
            r = one(pump, a.seconds, a.hog, mask, a.py_load)
            print(f"  {r['mode']:13s} p50 {r['p50']:6.2f}  p95 {r['p95']:6.2f}  p99 {r['p99']:6.2f}  max {r['max']:7.2f}  "
                  f"> 5 ms: {r['over_5ms']:4d} of {r['got']} ({r['sent']} sent)", flush=True)


if __name__ == "__main__":
    main()
