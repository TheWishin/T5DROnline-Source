#!/usr/bin/env python3
"""Summarise an rb_frames.log from T5_RB_MODE=measure (src/rollback/rb_measure.cpp).

    python tools/rollback_measure_analyze.py RUNDIR [--window N]   (N = which 300-frame summary window, default: all)

Prints per window: frames, dirty pages/frame (median), by category, and the
hot runs (pages dirty in >= half the frames) merged by 64 KB neighbourhood,
plus the pages the side threads write while the main thread is parked.
"""
import os
import re
import sys
import statistics


def main():
    d = sys.argv[1]
    want = None
    if "--window" in sys.argv:
        want = int(sys.argv[sys.argv.index("--window") + 1])
    path = os.path.join(d, "rb_frames.log")
    frames = []
    windows = []       # list of dict(frame_runs=[...], park_runs=[...], frames=[...])
    cur = {"frame_runs": [], "park_runs": [], "frames": [], "mb": "", "pmb": ""}
    for line in open(path, errors="replace"):
        if line.startswith("F "):
            kv = line.split()
            rec = {"f": int(kv[1])}
            for i in range(2, len(kv) - 1, 2):
                try:
                    rec[kv[i]] = float(kv[i + 1].rstrip("ms"))
                except ValueError:
                    pass
            cur["frames"].append(rec)
        elif line.startswith("FRAME-RUN"):
            m = re.match(r"FRAME-RUN (\w+) \+(\w+) pages (\d+) avg (\d+)%", line)
            cur["frame_runs"].append((int(m.group(1), 16), int(m.group(2), 16), int(m.group(3)), int(m.group(4))))
        elif line.startswith("PARK-RUN"):
            m = re.match(r"PARK-RUN (\w+) \+(\w+) pages (\d+) avg (\d+)%", line)
            cur["park_runs"].append((int(m.group(1), 16), int(m.group(2), 16), int(m.group(3)), int(m.group(4))))
        elif line.startswith("FRAME-MB"):
            cur["mb"] = line[8:].strip()
        elif line.startswith("PARK-MB"):
            cur["pmb"] = line[7:].strip()
            windows.append(cur)
            cur = {"frame_runs": [], "park_runs": [], "frames": [], "mb": "", "pmb": ""}
    if cur["frames"]:
        windows.append(cur)

    def merge(runs, gap=0x10000):
        out = []
        for a, l, p, avg in sorted(runs):
            if out and a - (out[-1][0] + out[-1][1]) <= gap:
                s, ln, pg, av = out[-1]
                out[-1] = (s, a + l - s, pg + p, (av * pg + avg * p) / (pg + p))
            else:
                out.append((a, l, p, avg))
        return out

    for wi, w in enumerate(windows):
        if want is not None and wi != want:
            continue
        fr = w["frames"]
        if not fr:
            continue
        f0, f1 = fr[0]["f"], fr[-1]["f"]
        med = lambda k: statistics.median(r.get(k, 0) for r in fr)
        print(f"== window {wi}: frames {f0}..{f1}  t {fr[0].get('t', 0):.0f}..{fr[-1].get('t', 0):.0f}s  "
              f"dt median {med('dt'):.1f} ms  dirty median {med('dirty'):.0f} pages "
              f"(main {med('main'):.0f} data {med('data'):.0f} mid {med('mid'):.0f} stack {med('stack'):.0f})")
        print(f"   hot runs (dirty in >= half the frames), merged by 64 KB:")
        tot = 0
        for a, l, p, avg in merge(w["frame_runs"]):
            tot += p
            print(f"     {a:08X} +{l:07X}  {p:5d} pages  avg {avg:3.0f}%")
        print(f"   total hot pages {tot} ({tot * 4} KB)")
        if w["park_runs"]:
            print(f"   side-thread writes while main parked:")
            for a, l, p, avg in merge(w["park_runs"]):
                print(f"     {a:08X} +{l:07X}  {p:5d} pages  avg {avg:3.0f}%")


if __name__ == "__main__":
    main()
