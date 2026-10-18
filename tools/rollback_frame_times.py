#!/usr/bin/env python3
"""What the player sees of a rollback game, from its latency log.

    python tools/rollback_frame_times.py RUN/host/lat.log [RUN/join/lat.log ...] [--over 20] [--hz 144]

Reads a PS3_LATENCY_LOG (ps3recomp patch 0034; rollback events from
src/rollback/rb_net.cpp): P presents, C the display's vblank clock (DWM),
N boundaries (frame, re-simulated, early, fighting), M / Q a rollback's start
and end, S time-sync sleeps, T waits for the peer's input. Over the frames
of the fight (N lines with the fighting flag):

  - present-to-present intervals: p50 / p95 / p99 / max;
  - the long ones (over --over ms), each put down to what happened between
    its two presents: a time-sync sleep, a wait for the peer, a rollback (and
    its depth), or nothing the loop logged (the machine);
  - display refreshes per new frame on the vblank grid of the C lines (1 at
    60 Hz is perfect; at 144 Hz a 59.94 Hz game alternates 2 and 3) --
    with --hz the grid of a simulated display (RSX_TEST_DISPLAY_HZ) instead;
  - p95 / p99 without the intervals that hold a time-sync sleep (what the
    rollbacks leave).
"""
import argparse
import bisect


def load(path):
    freq = 10_000_000
    ev = []
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("# qpc_frequency="):
                freq = int(line.split("=")[1])
                continue
            p = line.split()
            if len(p) < 2 or p[0].startswith("#"):
                continue
            try:
                ev.append((int(p[1]), p[0], p[2:]))
            except ValueError:
                pass
    ev.sort(key=lambda e: e[0])
    return freq, ev


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))] if xs else float("nan")


def analyze(path, over, hz):
    freq, ev = load(path)
    ms = 1000.0 / freq
    fight = False
    P = []
    C = []
    for t, k, a in ev:
        if k == "N" and len(a) >= 4 and a[1] == "0":
            fight = a[3] == "1"
        elif k == "P":
            P.append((t, fight))
        elif k == "C" and len(a) >= 2:
            C.append((t, int(a[0]), int(a[1])))
    T = [e[0] for e in ev]
    rows = []
    for i in range(len(P) - 1):
        (a, fa), (b, fb) = P[i], P[i + 1]
        if not (fa and fb):
            continue
        kinds, depth = set(), 0
        for t, k, x in ev[bisect.bisect_right(T, a):bisect.bisect_right(T, b)]:
            if k == "S":
                kinds.add("sleep")
            elif k == "T":
                kinds.add("stall")
            elif k == "M":
                kinds.add("rollback")
                depth = max(depth, int(x[0]) - int(x[1]))
        rows.append(((b - a) * ms, kinds, depth, a, b))
    if not rows:
        print(f"{path}: no fight frames (an older build without the fighting flag?)")
        return None
    xs = [r[0] for r in rows]
    res = {"n": len(xs), "p50": pct(xs, .5), "p95": pct(xs, .95), "p99": pct(xs, .99), "max": max(xs)}
    print(f"{path}: {len(xs)} present-to-present intervals while fighting: p50 {res['p50']:.1f} p95 {res['p95']:.1f} "
          f"p99 {res['p99']:.1f} max {res['max']:.1f} ms")
    cat = {}
    for d, kinds, depth, _, _ in rows:
        if d <= over:
            continue
        key = ("time-sync sleep" if "sleep" in kinds else "wait for the peer" if "stall" in kinds
               else f"rollback, depth {depth}" if "rollback" in kinds else "nothing logged")
        cat.setdefault(key, []).append(d)
    n_over = sum(len(v) for v in cat.values())
    print(f"  over {over:.0f} ms: {n_over} ({100.0 * n_over / len(xs):.2f} %)")
    for k in sorted(cat, key=lambda k: -len(cat[k])):
        v = cat[k]
        print(f"    {k:<22} {len(v):5d}  median {pct(v, .5):.1f} max {max(v):.1f} ms")
    ys = [r[0] for r in rows if "sleep" not in r[1]]
    res["p95_nosleep"], res["p99_nosleep"] = pct(ys, .95), pct(ys, .99)
    print(f"  without the intervals that hold a time-sync sleep: p95 {res['p95_nosleep']:.1f} p99 {res['p99_nosleep']:.1f} ms")
    # refreshes per new frame
    gaps = []
    if hz:
        per = 1000.0 / hz
        slots = [round(r[4] * ms / per) for r in rows]
        gaps = [round((r[4] - r[3]) * ms / per) for r in rows]
        label = f"simulated {hz:g} Hz display"
    elif C:
        Cq = [c[0] for c in C]
        gpu = freq // 2000
        ids = []
        for _, _, _, a, b in rows:
            out = []
            for p_ in (a, b):
                k = bisect.bisect_right(Cq, p_) - 1
                if k < 0:
                    break
                vb, prd = C[k][1], C[k][2]
                out.append(((vb + -(-(p_ + gpu - vb) // prd) * prd), prd))
            if len(out) == 2:
                gaps.append(round((out[1][0] - out[0][0]) / out[0][1]))
        per_ms = pct([c[2] for c in C], .5) * ms
        label = f"display {1000.0 / per_ms:.2f} Hz (DWM clock)"
    if gaps:
        hist = {}
        for g in gaps:
            hist[g] = hist.get(g, 0) + 1
        res["refreshes"] = hist
        print(f"  refreshes per new frame, {label}: " + ", ".join(f"{k}: {hist[k]}" for k in sorted(hist)))
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--over", type=float, default=20.0, help="threshold for the long intervals, ms")
    ap.add_argument("--hz", type=float, default=0.0, help="refresh grid of a simulated display (RSX_TEST_DISPLAY_HZ)")
    a = ap.parse_args()
    for p in a.logs:
        analyze(p, a.over, a.hz)


if __name__ == "__main__":
    main()
