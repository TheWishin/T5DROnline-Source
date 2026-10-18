#!/usr/bin/env python3
"""Diff two games' desync dumps: the rollback loop's rb_desync_f<frame>.bin or the lockstep's
np_desync_f<frame>.bin (T5_NET_DESYNC_DUMP=1; the gameplay-hash bytes in region order).

    python tools/rb_desync_diff.py DIR_A DIR_B      (e.g. run1 run2 of tools/fight_flow_test.py)

Lists, per common frame, the differing 32-bit words as address:A/B, then the words that differ
most often. The rollback dump's regions are src/rollback/rb_state.cpp kGame (skipped words zeroed)."""
import glob
import os
import struct
import sys

REGIONS = [(0x10099F24, 0x70), (0x104CCDFC, 0x40), (0x106D4D88, 0x8), (0x10095168, 0x9C0), (0x10053578, 0x4),
           (0x10076920, 0x4), (0x1074F218, 0x10C), (0x1008E000, 0x4000), (0x10099600, 0x600), (0x100A0900, 0x200),
           (0x100A3B00, 0x300)]


def addr_of(off):
    base = 0
    for a, n in REGIONS:
        if off < base + n:
            return a + (off - base)
        base += n
    return None


def dumps(d):
    return {os.path.basename(p): p for p in glob.glob(os.path.join(d, "*_desync_f*.bin"))}


def main():
    a, b = dumps(sys.argv[1]), dumps(sys.argv[2])
    common = sorted(set(a) & set(b))
    print(f"{len(a)} / {len(b)} dumps, {len(common)} common frames")
    agg = {}
    for name in common[:20]:
        x, y = open(a[name], "rb").read(), open(b[name], "rb").read()
        n = min(len(x), len(y))
        diffs = [i for i in range(0, n - 3, 4) if x[i:i + 4] != y[i:i + 4]]
        words = []
        for i in diffs[:16]:
            ad = addr_of(i)
            words.append(f"{ad:08X}:{struct.unpack('>I', x[i:i + 4])[0]:08X}/{struct.unpack('>I', y[i:i + 4])[0]:08X}")
        for i in diffs:
            ad = addr_of(i)
            agg[ad] = agg.get(ad, 0) + 1
        print(f"{name}: {len(diffs)} differing words: {' '.join(words)}")
    print("words differing most often:", " ".join(f"{k:08X}x{v}" for k, v in sorted(agg.items(), key=lambda kv: -kv[1])[:24]))


if __name__ == "__main__":
    main()
