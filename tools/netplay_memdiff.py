#!/usr/bin/env python3
"""Compare guest memory dumps from two netplay instances (T5_NET_DUMP).

    python tools/netplay_memdiff.py RUN1 RUN2 [--base 1008E000] [--line 64]

RUN1/RUN2 are the two instances' working directories (np_dump_f<frame>_<addr>.bin
files, same frames and ranges on both). For every dumped range it reports, per
4 KB page:

  live      bytes that change between the first and last dumped frame and are
            equal on both PCs at every dumped frame -- state that follows from
            the inputs (what the desync detector should hash);
  differ    bytes that differ between the PCs at some frame -- either a desync
            or memory that is not part of the match state (timers, sound,
            render buffers, pointers into differently ordered heaps).

With --words it also lists every differing 32-bit word (for T5_NET_HASH_SKIP).
Needs numpy.
"""
import argparse
import glob
import os
import re
import sys

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run1")
    ap.add_argument("run2")
    ap.add_argument("--base", help="only the range starting at this hex address")
    ap.add_argument("--words", action="store_true", help="list differing 32-bit words")
    ap.add_argument("--min-live", type=int, default=1, help="hide pages with fewer live bytes")
    a = ap.parse_args()

    ranges = {}
    for f in glob.glob(os.path.join(a.run1, "np_dump_f*_*.bin")):
        fr, base = re.findall(r"np_dump_f(\d+)_([0-9A-Fa-f]+)\.bin$", f)[0]
        if a.base and int(base, 16) != int(a.base, 16):
            continue
        other = os.path.join(a.run2, os.path.basename(f))
        if os.path.exists(other):
            ranges.setdefault(int(base, 16), []).append((int(fr), f, other))
    if not ranges:
        sys.exit("no matching dumps")

    for base, items in sorted(ranges.items()):
        items.sort()
        frames = [fr for fr, _, _ in items]
        A = [np.fromfile(x, dtype=np.uint8) for _, x, _ in items]
        B = [np.fromfile(y, dtype=np.uint8) for _, _, y in items]
        n = min(min(len(x) for x in A), min(len(y) for y in B))
        A = np.stack([x[:n] for x in A])
        B = np.stack([y[:n] for y in B])
        equal = np.all(A == B, axis=0)
        changing = np.any(A != A[0], axis=0)
        live = equal & changing
        differ = ~equal
        print(f"range {base:08X} +{n:X}, frames {frames}")
        print("  page      live  differ")
        for pg in range(0, n, 0x1000):
            lv = int(live[pg:pg + 0x1000].sum())
            df = int(differ[pg:pg + 0x1000].sum())
            if lv >= a.min_live or df:
                print(f"  {base + pg:08X} {lv:5d} {df:7d}")
        if a.words:
            words = sorted(set(int(i) // 4 * 4 for i in np.nonzero(differ)[0]))
            print("  differing words:", ",".join(f"{base + w:08X}:4" for w in words))


if __name__ == "__main__":
    main()
