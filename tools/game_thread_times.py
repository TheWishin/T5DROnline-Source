#!/usr/bin/env python3
"""Per-frame times of the game's main thread from PS3_GAME_THREAD_LOG (ps3recomp patch 0061).

    python tools/game_thread_times.py LOG [LOG ...] [--skip-frames N] [--frames N] [--json FILE]

Each line of the log is one flip request of the game ("seq request_qpc
release_qpc cycles tid"). Per displayed frame this prints the main thread's
CPU time (its thread cycles between two flip requests: the frame's work with
re-simulated frames and rollback snapshots, without the time it waited) and
the game part in wall time (release of the frame -> its flip request: what
the frame's translation waits for), median, p90, p99 and mean, in ms.
--skip-frames leaves out the first N frames (boot, menus, loading), --frames
takes N frames after them.
"""
import argparse
import json


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def read(path):
    lines = open(path).read().splitlines()
    hdr = dict(kv.split("=") for kv in lines[0][1:].split())
    qf, tf = float(hdr["qpc_frequency"]), float(hdr["tsc_frequency"])
    rows = []
    prev = None
    for ln in lines[1:]:
        f = ln.split()
        if len(f) < 5:
            continue
        seq, req, rel, cyc, tid = int(f[0]), int(f[1]), int(f[2]), int(f[3]), int(f[4])
        if prev and prev[4] == tid and seq == prev[0] + 1:
            part = 1000.0 * (req - rel) / qf if prev[1] <= rel <= req else None
            rows.append((seq, 1000.0 * (cyc - prev[3]) / tf, part, 1000.0 * (req - prev[1]) / qf))
        prev = (seq, req, rel, cyc, tid)
    return rows


def stats(xs):
    return {"n": len(xs), "p50": pct(xs, 50), "p90": pct(xs, 90), "p99": pct(xs, 99),
            "mean": sum(xs) / len(xs) if xs else float("nan")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--skip-frames", type=int, default=0)
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    out = {}
    for p in a.logs:
        rows = read(p)[a.skip_frames:]
        if a.frames:
            rows = rows[:a.frames]
        cpu = stats([r[1] for r in rows])
        part = stats([r[2] for r in rows if r[2] is not None])
        dt = stats([r[3] for r in rows])
        out[p] = {"cpu": cpu, "part": part, "interval": dt}
        print("%s: %d frames; CPU ms p50 %.2f p90 %.2f p99 %.2f mean %.2f | game part p50 %.2f p90 %.2f p99 %.2f | "
              "frame interval p50 %.2f p99 %.2f" % (p, cpu["n"], cpu["p50"], cpu["p90"], cpu["p99"], cpu["mean"],
                                                     part["p50"], part["p90"], part["p99"], dt["p50"], dt["p99"]))
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
