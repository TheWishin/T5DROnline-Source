"""tools/fight_flow_test.py with a round trip between the two games.

    python tools/soak/rtt_fight.py --rtt 150 [--jitter 5] [--loss 0] <fight_flow_test.py options>

fight_flow_test.py has no network delay of its own; rollback_net_test.py has a
UDP proxy but drives one process per side. This runs the first with the second's
proxy: for every session (its port P, the host's) a proxy listens on P+2 and
the joiner's T5_NET_PEER points at it. Each datagram is delayed by rtt/2
(+-jitter) and dropped with probability loss %, both ways. The host gets no
fixed peer and answers whoever its HELLO came from (the proxy), as in
rollback_net_test.py. T5_NET_RTT_MS (logged only) says the same rtt.

Everything else -- flows, mashing, the per-match result check (same winner and
state hash, 0 mismatching frames), the FIFO scan -- is fight_flow_test.py's.
Proxy counts go to <out>/proxy.log.
"""
import argparse
import os
import sys

# Both games of a local pair talk over 127.0.0.1: bind there, not on every interface (no Windows Firewall
# prompt for each build folder's t5dr.exe; docs/NETPLAY.md "Bind address"). An explicit T5_NET_BIND wins.
os.environ.setdefault("T5_NET_BIND", "127.0.0.1")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import fight_flow_test as ff  # noqa: E402
import rollback_net_test as rn  # noqa: E402


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--rtt", type=float, default=150.0, help="round trip added between the games, ms")
    ap.add_argument("--jitter", type=float, default=0.0, help="+- one-way jitter, ms")
    ap.add_argument("--loss", type=float, default=0.0, help="packet loss, percent")
    a, rest = ap.parse_known_args()
    out = None
    for i, x in enumerate(rest):
        if x == "--out" and i + 1 < len(rest):
            out = rest[i + 1]
        elif x.startswith("--out="):
            out = x.split("=", 1)[1]
    if out:
        os.makedirs(out, exist_ok=True)
    plog = open(os.path.join(out, "proxy.log") if out else os.devnull, "w")
    proxies = {}
    orig = ff.session_env

    def session_env(fa, k, match, game, port0):
        env = orig(fa, k, match, game, port0)
        if port0 not in proxies:
            p = rn.Proxy(port0 + 2, port0, a.rtt, a.jitter, a.loss, plog)
            p.start()
            proxies[port0] = p
            plog.write(f"session {k}: proxy 127.0.0.1:{port0 + 2} -> host 127.0.0.1:{port0}, rtt {a.rtt} ms, "
                       f"jitter +-{a.jitter} ms, loss {a.loss} %\n")
            plog.flush()
        if game.role == "host":
            env.pop("T5_NET_PEER", None)
        else:
            env["T5_NET_PEER"] = f"127.0.0.1:{port0 + 2}"
        env["T5_NET_RTT_MS"] = str(int(a.rtt))
        return env

    ff.session_env = session_env
    sys.argv = [os.path.join(os.path.dirname(HERE), "fight_flow_test.py")] + rest
    try:
        rc = ff.main()
    finally:
        for port0, p in proxies.items():
            p.stop = True
            plog.write(f"proxy for {port0}: {p.stats}\n")
        plog.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
