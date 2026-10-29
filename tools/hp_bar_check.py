#!/usr/bin/env python3
"""HP bars under rollback: the joiner's presented frames of a rollback pair with an unsteady ping against the
same match without rollbacks -- the health bars must look the same, frame for frame.

    python tools/hp_bar_check.py [--exe build/cmake/t5dr.exe] [--rtt 120] [--jitter 20] [--dir DIR] [--keep]
    python tools/hp_bar_check.py --analyze DIR       # the pictures of an earlier --keep run again

Made for 1.1.9's "HP bars flicker online when the ping is unsteady" (docs/ROLLBACK.md "HUD health bars"):
the draw cut skipped 0x1357A0 in re-simulated frames, and that pass also moves the orange part of a bar that
drains after a hit; a rollback put the drain back and nothing moved it on, so it stalled and stepped back.
Both runs are tools/rollback_net_test.py pairs (direct fight lil,ask,20,3; the same seeded --mash input, so
the same match): one at RTT 0 (no rollbacks), one at --rtt/--jitter (~1,100 rollbacks). 20 s of the joiner's
frames are read back (LD_FRAME_DUMP_ASYNC) 25 s into the fight. Per frame and bar: the dark (empty) run from
the bar's outer end and the orange (draining) run after it. The sequences are aligned (the dump starts a few
frames apart) and compared. Before the fix: 116 of 1,196 frames differed, 15 reversals (the bar's end moving
back out) against 2 without rollbacks (the KO light at the round's end); after: 0 differing frames, 2.
The pictures are game art: a temporary folder (or --dir), deleted unless --keep.
Exit code: 0 the bars match, 1 they differ, 2 a run failed.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BARS = {"P1": (58, 578), "P2": (706, 1224)}      # x range of each bar at 1280x720; P1 empties from the left


def load_ppm(path):
    import numpy as np
    with open(path, "rb") as f:
        data = f.read()
    parts = data.split(maxsplit=4)
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(parts[4][:w * h * 3], dtype=np.uint8).reshape(h, w, 3)


def bar_runs(img):
    """{bar: (empty run from the outer end, orange run after it)} in pixels (rows 60-64, 1280x720)."""
    out = {}
    for k, (a, b) in BARS.items():
        row = img[60:65, a + 4:b - 4].astype(int).mean(axis=0)
        if k == "P2":
            row = row[::-1]
        r, g, bl = row[:, 0], row[:, 1], row[:, 2]
        empty = (r > 15) & (r < 130) & (g < 45) & (bl < 45)
        orange = (r > 160) & (g > 60) & (bl < 120) & (r > g + 20)
        e = 0
        while e < len(row) and empty[e]:
            e += 1
        o = e
        while o < len(row) and orange[o]:
            o += 1
        out[k] = (e, o - e)
    return out


def measure(folder):
    seq = []
    for n in sorted(f for f in os.listdir(folder) if f.endswith(".ppm") and "_s" not in f):
        try:
            seq.append(bar_runs(load_ppm(os.path.join(folder, n))))
        except (ValueError, IndexError):
            pass                                   # the last frame, cut off when the game was stopped
    return seq


def reversals(seq):
    """Frames where a bar grew again: its empty end or its teal end moved back out (not a round's refill)."""
    n = 0
    for k in BARS:
        for p, q in zip(seq, seq[1:]):
            (e0, o0), (e1, o1) = p[k], q[k]
            if (e1 <= e0 - 2 and e1 > 5) or (e1 + o1 <= e0 + o0 - 2 and e1 + o1 > 5 and e1 >= e0):
                n += 1
    return n


def compare(test, base):
    """(frames of `test` that differ from `base` at the best alignment, frames compared)"""
    def key(s):
        return tuple(s[k] for k in BARS)
    a, b = [key(s) for s in test], [key(s) for s in base]
    best = max(range(-40, 41), key=lambda o: sum(1 for i in range(len(a)) if 0 <= i + o < len(b) and a[i] == b[i + o]))
    pairs = [(a[i], b[i + best]) for i in range(len(a)) if 0 <= i + best < len(b)]
    return sum(1 for x, y in pairs if x != y), len(pairs)


def run_pair(a, name, rtt, jitter, work):
    frames, runs = os.path.join(work, "frames_" + name), os.path.join(work, "runs")
    shutil.rmtree(frames, ignore_errors=True)
    os.makedirs(frames)
    gate = os.path.join(runs, name, "gate")

    def opener():
        status, t0 = os.path.join(runs, name, "join", "status.json"), time.time()
        while time.time() - t0 < 400:
            try:
                with open(status) as f:
                    if json.load(f).get("state") == "fight":
                        break
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        else:
            return
        time.sleep(25)
        open(gate, "w").close()
        time.sleep(20)
        os.remove(gate)
    t = threading.Thread(target=opener, daemon=True)
    t.start()
    cmd = [sys.executable, os.path.join(HERE, "rollback_net_test.py"), "--out", name, "--runs", runs, "--exe", a.exe,
           "--fight", "lil,ask,20,3", "--rtt", str(rtt), "--jitter", str(jitter), "--mash", "--mash-gap", "20",
           "--matches", "1", "--seconds", "150", "--mute",
           "--env2", "LD_FRAME_DUMP=" + frames, "--env2", "LD_FRAME_DUMP_EVERY=1", "--env2", "LD_FRAME_DUMP_ASYNC=1",
           "--env2", "LD_FRAME_DUMP_GATE=" + gate]
    if a.vfs:
        cmd += ["--vfs", a.vfs]
    r = subprocess.run(cmd, capture_output=True, text=True)
    t.join(timeout=60)
    summary = os.path.join(runs, name, "summary.txt")
    sync = open(summary).read() if os.path.exists(summary) else r.stdout[-2000:]
    return frames, sync


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default="")
    ap.add_argument("--rtt", type=float, default=120)
    ap.add_argument("--jitter", type=float, default=20)
    ap.add_argument("--dir", default="", help="work folder (default: a temporary one)")
    ap.add_argument("--keep", action="store_true", help="keep the pictures")
    ap.add_argument("--analyze", default="", help="only compare DIR/frames_jitter with DIR/frames_base")
    a = ap.parse_args()
    if a.analyze:
        work = a.analyze
        fj, fb = os.path.join(work, "frames_jitter"), os.path.join(work, "frames_base")
    else:
        work = os.path.abspath(a.dir) if a.dir else tempfile.mkdtemp(prefix="t5dr-hpbar-")
        os.makedirs(work, exist_ok=True)
        fb, sb = run_pair(a, "base", 0, 0, work)
        fj, sj = run_pair(a, "jitter", a.rtt, a.jitter, work)
        for name, s in (("base", sb), ("jitter", sj)):
            print(f"== {name}")
            for line in s.splitlines():
                if "sync through" in line or "rollback loop" in line:
                    print("  " + line.strip()[:200])
    base, jit = measure(fb), measure(fj)
    if len(base) < 300 or len(jit) < 300:
        print(f"too few frames read back ({len(base)} / {len(jit)})")
        return 2
    diff, n = compare(jit, base)
    print(f"no rollbacks: {len(base)} frames, {reversals(base)} bar reversals")
    print(f"RTT {a.rtt:g} +-{a.jitter:g}: {len(jit)} frames, {reversals(jit)} bar reversals; "
          f"{diff} of {n} frames differ from the run without rollbacks")
    if not a.keep and not a.analyze:
        shutil.rmtree(fb, ignore_errors=True)
        shutil.rmtree(fj, ignore_errors=True)
    print("RESULT:", "PASS" if diff == 0 else "FAIL")
    return 0 if diff == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
