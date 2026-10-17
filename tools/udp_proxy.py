#!/usr/bin/env python3
"""A UDP proxy on localhost that adds latency and packet loss between two game
instances, to see how the game's own netcode copes.

    python tools/udp_proxy.py --a 3658 --b 3659 --pa 4658 --pb 4659 --delay 50 --loss 1

Instance A has its P2P socket on port --a and is told (PS3_NP_PEER_OVERRIDE=
127.0.0.1:<pb>) that its peer is at port --pb; instance B is on --b and is told
its peer is at --pa. The proxy's socket on --pb takes A's packets and sends
them to B from the socket on --pa, and the other way round, so each side sees
its traffic come from the port it was told about (the game drops packets from
anyone else). --delay is the one-way delay in ms (RTT is twice that), --loss
the percentage of packets dropped, --jitter extra random delay in ms.
"""
import argparse
import heapq
import random
import socket
import sys
import threading
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=int, default=3658, help="instance A's P2P port")
    ap.add_argument("--b", type=int, default=3659, help="instance B's P2P port")
    ap.add_argument("--pa", type=int, default=4658, help="proxy port that stands in for A")
    ap.add_argument("--pb", type=int, default=4659, help="proxy port that stands in for B")
    ap.add_argument("--delay", type=float, default=0.0, help="one-way delay, ms")
    ap.add_argument("--jitter", type=float, default=0.0, help="extra random delay, 0..jitter ms")
    ap.add_argument("--loss", type=float, default=0.0, help="packet loss, percent")
    ap.add_argument("--stats", type=float, default=5.0, help="print counters every N s")
    a = ap.parse_args()

    sa = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # stands in for A: B sends here
    sb = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # stands in for B: A sends here
    sa.bind(("127.0.0.1", a.pa))
    sb.bind(("127.0.0.1", a.pb))
    if sys.platform == "win32":
        for s in (sa, sb):
            try:
                s.ioctl(socket.SIO_UDP_CONNRESET, False)
            except OSError:
                pass
    to_a = ("127.0.0.1", a.a)
    to_b = ("127.0.0.1", a.b)

    lock = threading.Lock()
    queue = []          # (deliver_at, seq, sock, data, dst)
    seq = [0]
    stats = {"a2b": 0, "b2a": 0, "dropped": 0, "bytes": 0}

    def reader(src, out, dst, key):
        while True:
            data, _ = src.recvfrom(65535)
            stats["bytes"] += len(data)
            if a.loss and random.random() * 100.0 < a.loss:
                stats["dropped"] += 1
                continue
            delay = (a.delay + random.random() * a.jitter) / 1000.0
            with lock:
                seq[0] += 1
                heapq.heappush(queue, (time.monotonic() + delay, seq[0], out, data, dst))
            stats[key] += 1

    threading.Thread(target=reader, args=(sb, sa, to_b, "a2b"), daemon=True).start()
    threading.Thread(target=reader, args=(sa, sb, to_a, "b2a"), daemon=True).start()
    print(f"proxy: A :{a.a} <-> :{a.pb} | :{a.pa} <-> B :{a.b}  delay {a.delay} ms (+{a.jitter}) loss {a.loss}%",
          flush=True)
    last = time.monotonic()
    while True:
        now = time.monotonic()
        with lock:
            while queue and queue[0][0] <= now:
                _, _, out, data, dst = heapq.heappop(queue)
                try:
                    out.sendto(data, dst)
                except OSError:
                    pass
            wait = (queue[0][0] - now) if queue else 0.002
        if now - last >= a.stats:
            print(f"proxy: a->b {stats['a2b']} b->a {stats['b2a']} dropped {stats['dropped']} "
                  f"({stats['bytes']} B)", flush=True)
            last = now
        time.sleep(min(max(wait, 0.0), 0.002))


if __name__ == "__main__":
    main()
