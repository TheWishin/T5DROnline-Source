#!/usr/bin/env python3
"""Measure what the lobby's UDP relay adds to the round trip, on this PC.

    python lobby/tools/relay_latency.py [--n 3000] [--size 64]

Starts a lobby server in its own process (T5L_FORCE_RELAY=1), pairs two
clients through it exactly as the launcher would, then plays "game": a socket
on each handed-over port, one echoing, the other sending timestamped packets
(starting with the netplay magic T5NP) to its T5_NET_PEER -- the relay. The same
ping-pong between two plain localhost sockets is the direct baseline.
Localhost numbers isolate the relay's processing cost; over the internet the
relay also adds the detour via the server's location.
"""
import argparse
import os
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time

# Both games of a local pair talk over 127.0.0.1: bind there, not on every interface (no Windows Firewall
# prompt for each build folder's t5dr.exe; docs/NETPLAY.md "Bind address"). An explicit T5_NET_BIND wins.
os.environ.setdefault("T5_NET_BIND", "127.0.0.1")

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
sys.path.insert(0, LOBBY)

from t5lobby import proto  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402


def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def echo(sock, stop):
    sock.settimeout(0.2)
    while not stop.is_set():
        try:
            data, src = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            return
        sock.sendto(data, src)


def pingpong(tx, dst, n, size, rate, warm=200):
    """n timed round trips tx -> dst -> back, at most `rate` per second. -> (list of ms, lost)."""
    tx.settimeout(1.0)
    pad = b"\0" * max(0, size - 4 - 12)
    out = []
    lost = 0
    t_next = time.perf_counter()
    for i in range(n + warm):
        while time.perf_counter() < t_next:
            pass                       # busy-wait: sleep() granularity on Windows is ~1 ms or worse
        t_next += 1.0 / rate
        t = time.perf_counter()
        tx.sendto(b"T5NP" + struct.pack("!Id", i, t) + pad, dst)
        while True:
            try:
                data, _ = tx.recvfrom(2048)
            except socket.timeout:
                lost += 1
                break
            seq, t0 = struct.unpack_from("!Id", data, 4)
            if seq == i:
                if i >= warm:
                    out.append((time.perf_counter() - t0) * 1000.0)
                break
    return out, lost


def stats(xs):
    xs = sorted(xs)
    q = lambda f: xs[min(len(xs) - 1, int(f * (len(xs) - 1)))]  # noqa: E731
    return {"n": len(xs), "median": statistics.median(xs), "p90": q(0.9), "p99": q(0.99), "min": xs[0]}


def bind(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((os.environ["T5_NET_BIND"], port))
    proto.disable_udp_connreset(s)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--size", type=int, default=64, help="packet size in bytes (netplay input packets: ~40-80)")
    ap.add_argument("--rate", type=float, default=250.0,
                    help="round trips per second; the relay caps each player at T5L_RELAY_PPS (400) packets/s, "
                         "the game sends ~60")
    a = ap.parse_args()

    tcp, udp, udp2 = free_port(), free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
    env = dict(os.environ, T5L_FORCE_RELAY="1", T5L_DB=":memory:", T5L_LOG_LEVEL="WARNING",
               PYTHONPATH=LOBBY)
    srv = subprocess.Popen([sys.executable, "-m", "t5lobby.server", "--host", "127.0.0.1", "--port", str(tcp),
                            "--udp-port", str(udp), "--udp-port2", str(udp2)], env=env, cwd=LOBBY,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    clients = []
    socks = []
    stop = threading.Event()
    try:
        line = srv.stdout.readline()
        if "t5lobby:" not in line:
            sys.exit("server did not start: " + line)
        build = BuildInfo("0" * 40, "relay-latency")
        for name in ("Host", "Joiner"):
            c = LobbyClient(f"127.0.0.1:{tcp}", build, auto_ready=True)
            c.connect()
            c.login_guest(name)
            c.quick_match()
            clients.append(c)
        tickets = []
        for c in clients:
            ev = c.next_event(20, ("match_start", "match_cancel"))
            if not ev or ev["t"] != "match_start":
                sys.exit(f"no match: {ev}")
            tickets.append(ev["ticket"])
        host = [t for t in tickets if t.role == "host"][0]
        join = [t for t in tickets if t.role == "join"][0]
        print(f"paired via {host.path}: host port {host.local_port}, join port {join.local_port}, "
              f"relay {join.peer[0]}:{join.peer[1]}; lobby's own RTT estimate {host.rtt_ms:.2f} ms, "
              f"suggested delay {host.delay}")

        # relay: the joiner speaks first (as netplay does), the host echoes to whoever spoke
        h, j = bind(host.local_port), bind(join.local_port)
        socks += [h, j]
        th = threading.Thread(target=echo, args=(h, stop), daemon=True)
        th.start()
        relay, lost_r = pingpong(j, join.peer, a.n, a.size, a.rate)

        # direct baseline: two plain sockets on this PC
        d1, d2 = bind(0), bind(0)
        socks += [d1, d2]
        th2 = threading.Thread(target=echo, args=(d2, stop), daemon=True)
        th2.start()
        direct, lost_d = pingpong(d1, ("127.0.0.1", d2.getsockname()[1]), a.n, a.size, a.rate)
    finally:
        stop.set()
        for c in clients:
            c.close()
        for s in socks:
            s.close()
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()

    sd, sr = stats(direct), stats(relay)
    print(f"{a.n} round trips of {a.size}-byte packets at {a.rate:.0f}/s on localhost (ms):")
    print(f"  direct : median {sd['median']:.3f}  p90 {sd['p90']:.3f}  p99 {sd['p99']:.3f}  min {sd['min']:.3f}"
          f"  lost {lost_d}")
    print(f"  relay  : median {sr['median']:.3f}  p90 {sr['p90']:.3f}  p99 {sr['p99']:.3f}  min {sr['min']:.3f}"
          f"  lost {lost_r}")
    print(f"  added by the relay: median {sr['median'] - sd['median']:+.3f} ms per round trip "
          f"(p99 {sr['p99'] - sd['p99']:+.3f}); one frame is {proto.FRAME_MS:.2f} ms")


if __name__ == "__main__":
    main()
