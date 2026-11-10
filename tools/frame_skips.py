#!/usr/bin/env python3
"""Pictures the game lost, from PS3_GAME_THREAD_LOG (docs/RENDER_PERF.md "A frame that ends at the ring's end").

    python tools/frame_skips.py GT_LOG [--from SEQ] [--game-log game.log]

Each line of the log is one flip request of the game's main thread. A request that comes more than 1.6
frames after the one before it is listed with the main thread's processor time in between: about TWO frames
of work there means the game ran two frames for one picture (its flip was made outside the command FIFO --
before ps3recomp patch 0125 that happened when a frame ended in the last 4 KB of the command ring), about one
frame means the frame was only late. With --game-log the runtime's own notes are counted too
("[cellGcmSys] frame ended N bytes before the ring's end: ...").

Exit code 0: no request interval over 1.6 frames with two frames of work; 1: at least one.
"""
import argparse
import sys


def read(path):
    with open(path) as f:
        lines = f.read().splitlines()
    hdr = dict(kv.split("=") for kv in lines[0][1:].split())
    qf, tf = float(hdr["qpc_frequency"]), float(hdr["tsc_frequency"])
    rows = []
    for ln in lines[1:]:
        f = ln.split()
        if len(f) >= 5:
            rows.append(tuple(int(x) for x in f[:5]))
    return qf, tf, rows


def frames(qf, tf, rows, first=0):
    """[(seq, interval_ms, cpu_ms)] of consecutive requests of one thread."""
    out, prev = [], None
    for r in rows:
        if prev and r[0] == prev[0] + 1 and r[4] == prev[4] and r[0] >= first:
            out.append((r[0], 1000.0 * (r[1] - prev[1]) / qf, 1000.0 * (r[3] - prev[3]) / tf))
        prev = r
    return out


def skips(fr, period_ms=16.68):
    """Frames whose request came more than 1.6 periods after the one before: (seq, interval, cpu, cpu / median)."""
    cpus = sorted(f[2] for f in fr)
    med = cpus[len(cpus) // 2] if cpus else 0.0
    return med, [(s, iv, cpu, cpu / med if med > 0 else 0.0) for s, iv, cpu in fr if iv > 1.6 * period_ms]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--from", dest="first", type=int, default=0, help="leave out the requests before this one (boot, menus, loading)")
    ap.add_argument("--game-log", default="")
    a = ap.parse_args()
    qf, tf, rows = read(a.log)
    fr = frames(qf, tf, rows, a.first)
    med, sk = skips(fr)
    two = [s for s in sk if s[3] >= 1.6]
    print("%d frames, main thread %.2f ms a frame (median); %d request(s) over 1.6 frames apart, %d of them with two "
          "frames of work (a lost picture)" % (len(fr), med, len(sk), len(two)))
    for s, iv, cpu, k in sk:
        print("  request %d: %.1f ms after the one before, main thread %.2f ms (%.1f frames of work)%s"
              % (s, iv, cpu, k, " -- two frames, one picture" if k >= 1.6 else ""))
    if a.game_log:
        inside = outside = 0
        for ln in open(a.game_log, errors="replace"):
            if "before the ring's end" in ln:
                if "stays in the FIFO" in ln:
                    inside += 1
                elif "outside the FIFO" in ln:
                    outside += 1
        print("game log: %d note(s) of a frame at the ring's end kept in the FIFO, %d of a flip outside it "
              "(the first 4 and every 100th are written)" % (inside, outside))
    return 1 if two else 0


if __name__ == "__main__":
    sys.exit(main())
