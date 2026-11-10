#!/usr/bin/env python3
"""Black flashes, counted from the game's own flash check (ps3recomp patch 0124).

    python tools/flash_stats.py FLASH.csv [LAT.log]

The game measures every picture it presents when it runs with RSX_FLASH_CHECK=<folder> (a player can leave
that on while playing: launcher Settings -> Extra settings) and writes <folder>/flash.csv; a test sets the
pieces one by one (LD_FRAME_DUMP=<dir> LD_FRAME_DUMP_EVERY=1 LD_FRAME_DUMP_ASYNC=1 LD_FRAME_DUMP_ASYNC_BB=1
LD_FRAME_DUMP_STATS=<csv>, with LD_FRAME_DUMP_GATE=<file> for a part of a run). Two pictures per frame:
the game's display buffer ("game") and the window's back buffer after the present copy and the overlay
("window", names ending in _bb). A line is "name,qpc,middle,whole,black": the mean of the 3D picture's
middle as tools/flicker_check.py measures it, the mean of the whole picture, the share of black pixels.

Counted: dark = middle under 45 and under half of both neighbours (flicker_check's rule: a frame that lost
its 3D picture); dip = under 60 % of both neighbours. With the game's PS3_LATENCY_LOG as the second
argument every dark frame gets the rollbacks around it (M = restore at boundary f back to frame g, Q = the
rollback is done), in ms from the picture's copy.

A rollback pair with it (two games, every frame of the fight):

    python tools/rollback_net_test.py --out NAME --fight ask,lil,20,3 --rtt 100 --jitter 10 --loss 2 \\
        --mash --latlog --polite --env RSX_TEST_DISPLAY_HZ=240 \\
        --env1 RSX_FLASH_CHECK=<dir>/host --env2 RSX_FLASH_CHECK=<dir>/join
    python tools/flash_stats.py <dir>/host/flash.csv build/rollback-net-runs/NAME/host/lat.log

Exit code: 0 no dark frame, 1 dark frames, 2 nothing to read. docs/RENDER_PERF.md "Black flashes on fast
displays (1.2.3)".
"""
import bisect
import re
import sys

NAME = re.compile(r"frame_(\d+)(?:_flip(\d+))?(_bb)?")


def read_stats(path):
    """{"game": [...], "window": [...]} of (frame, flip, qpc, middle, whole, black), sorted by frame."""
    kinds = {"game": [], "window": []}
    with open(path, errors="replace") as f:
        for line in f:
            p = line.strip().split(",")
            m = NAME.match(p[0]) if len(p) == 5 else None
            if not m:
                continue
            try:
                row = (int(m.group(1)), int(m.group(2) or 0), int(p[1]), float(p[2]), float(p[3]), float(p[4]))
            except ValueError:
                continue
            kinds["window" if m.group(3) else "game"].append(row)
    for rows in kinds.values():
        rows.sort()
    return kinds


def read_rollbacks(path):
    """(qpc frequency, [(qpc, kind, text)]) of the M and Q lines of a latency log."""
    qpf, events = 10000000.0, []
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                m = re.search(r"qpc_frequency=(\d+)", line)
                if m:
                    qpf = float(m.group(1))
                continue
            p = line.split()
            if len(p) >= 2 and p[0] in ("M", "Q"):
                try:
                    events.append((int(p[1]), p[0], " ".join(p[2:])))
                except ValueError:
                    pass
    events.sort()
    return qpf, events


def classify(rows):
    """(dark, dips, not read back): the rows of each kind and how many frame numbers are missing."""
    dark, dips = [], []
    for i in range(1, len(rows) - 1):
        a, r, b = rows[i - 1][3], rows[i][3], rows[i + 1][3]
        if r < 45 and r < 0.5 * min(a, b):
            dark.append(rows[i])
        elif r < 0.6 * min(a, b):
            dips.append(rows[i])
    missing = sum(b[0] - a[0] - 1 for a, b in zip(rows, rows[1:]))
    return dark, dips, missing


def near(row, events, qpf):
    """The rollback events around a picture: the two before and the one after its copy."""
    k = bisect.bisect([e[0] for e in events], row[2])
    return " ".join(f"{events[j][1]}{(events[j][0] - row[2]) * 1000 / qpf:+.1f}ms({events[j][2]})"
                    for j in (k - 2, k - 1, k) if 0 <= j < len(events))


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    kinds = read_stats(argv[1])
    qpf, events = read_rollbacks(argv[2]) if len(argv) > 2 else (10000000.0, [])
    rollbacks = sum(1 for e in events if e[1] == "M")
    total = found = 0
    for kind, rows in kinds.items():
        if not rows:
            continue
        dark, dips, missing = classify(rows)
        total += len(rows)
        found += len(dark)
        secs = max((rows[-1][2] - rows[0][2]) / qpf, 1.0)
        print(f"{kind:6s}: {len(rows)} pictures ({missing} not read back), {secs:.0f} s"
              + (f", {rollbacks} rollbacks" if events else "")
              + f": {len(dark)} dark ({60 * len(dark) / secs:.2f} a minute), {len(dips)} dips")
        for r in (dark + dips)[:25]:
            print(f"    {'dark' if r in dark else 'dip '} frame {r[0]} flip {r[1]}: middle {r[3]:.1f}, whole {r[4]:.1f}, "
                  f"black {r[5]:.2f}" + (f" | {near(r, events, qpf)}" if events else ""))
    if not total:
        print("no pictures in " + argv[1])
        return 2
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
