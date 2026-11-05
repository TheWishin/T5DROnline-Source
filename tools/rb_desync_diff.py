#!/usr/bin/env python3
"""Diff two games' desync dumps: the rollback loop's rb_desync_f<frame>.bin or the lockstep's
np_desync_f<frame>.bin (T5_NET_DESYNC_DUMP=1; the gameplay-hash bytes in region order).

    python tools/rb_desync_diff.py DIR_A DIR_B [--first-diff]

Also the per-frame dumps of T5_RB_DUMP_AT (rb_frame_f<frame>.bin, tools/rb_equiv_test.py --dump).

Lists, per common frame, the differing 32-bit words as address:A/B, then the words that differ
most often. New dumps carry .regions.json sidecars describing their actual and
canonical addresses. Old US-only dumps require --legacy-us explicitly; mixed
or unequal layouts must never be guessed or silently truncated."""
import argparse
import glob
import json
import os
from pathlib import Path
import re
import struct
import sys

REGIONS = [(0x10099F24, 0x70), (0x104CCDFC, 0x40), (0x106D4D88, 0x8), (0x10095168, 0x9C0), (0x10053578, 0x4),
           (0x10076920, 0x4), (0x1074F218, 0x10C), (0x1008E000, 0x4000), (0x10099600, 0x600), (0x100A0900, 0x200),
           (0x100A3B00, 0x300)]


def addr_of(off, regions=REGIONS):
    base = 0
    for a, n in regions:
        if off < base + n:
            return a + (off - base)
        base += n
    return None


def dumps(d):
    files = (glob.glob(os.path.join(d, "*_desync_f*.bin")) + glob.glob(os.path.join(d, "rb_frame_f*.bin"))
             + glob.glob(os.path.join(d, "np_hash_f*.bin")) + glob.glob(os.path.join(d, "*_invalid_f*.bin")))
    return {os.path.basename(p): p for p in files}


def frame_order(name):
    match = re.search(r"_f(\d+)\.bin$", name)
    if not match:
        raise ValueError(f"unrecognized frame dump name: {name}")
    return int(match.group(1)), name


def layout(path, size, legacy_us=False):
    sidecar = Path(path).with_suffix(".regions.json")
    if not sidecar.is_file():
        if not legacy_us:
            raise ValueError(f"missing layout sidecar {sidecar}; old US-only dumps need --legacy-us")
        if size != sum(n for _, n in REGIONS):
            raise ValueError(f"legacy US dump {path} has {size} bytes, expected {sum(n for _, n in REGIONS)}")
        return [(a, n, a, None) for a, n in REGIONS], (False, False)
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    if meta.get("schema") != 1 or meta.get("bytes") != size:
        raise ValueError(f"invalid schema or byte count in {sidecar}")
    out, offset = [], 0
    for region in meta.get("ranges", []):
        values = [region.get(k) for k in ("offset", "address", "length", "us_address", "us_length")]
        if any(type(v) is not int or v < 0 for v in values):
            raise ValueError(f"invalid region in {sidecar}")
        start, actual, length, canonical, canonical_length = values
        if start != offset or not length or length % 4 or actual + length > 1 << 32 or canonical + canonical_length > 1 << 32:
            raise ValueError(f"noncontiguous, unaligned or invalid region in {sidecar}")
        # A structure with another size has no per-byte canonical counterpart.
        if length != canonical_length:
            raise ValueError(f"edition-specific region lengths in {sidecar}; per-field mapping required")
        label = None
        if region.get("dynamic"):
            root, field_offset = region.get("root_us"), region.get("object_offset")
            if type(root) is not int or not 0 <= root < 1 << 32 or type(field_offset) is not int or field_offset < 0:
                raise ValueError(f"invalid dynamic root identity in {sidecar}")
            label = (root, field_offset)
        out.append((canonical, length, actual, label))
        offset += length
    if offset != size:
        raise ValueError(f"regions in {sidecar} cover {offset} bytes, dump has {size}")
    return out, (bool(meta.get("mixed")), bool(meta.get("custom_ranges")))


def compared_dump(path_a, path_b, legacy_us=False):
    x, y = Path(path_a).read_bytes(), Path(path_b).read_bytes()
    if len(x) != len(y):
        raise ValueError(f"unequal dump lengths: {path_a} ({len(x)}) / {path_b} ({len(y)}); refusing truncation")
    left, flags_a = layout(path_a, len(x), legacy_us)
    right, flags_b = layout(path_b, len(y), legacy_us)
    if flags_a != flags_b or [(a, n, label) for a, n, _, label in left] != [(a, n, label) for a, n, _, label in right]:
        raise ValueError(f"different hash layouts: {path_a} / {path_b}; per-field mapping required")
    return x, y, left, right


def semantic_address(off, regions):
    base = 0
    for address, length, _, label in regions:
        if off < base + length:
            if label is not None:
                return f"*{label[0]:08X}+{label[1] + off - base:X}"
            return f"{address + off - base:08X}"
        base += length
    raise ValueError("offset outside validated regions")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory_a")
    parser.add_argument("directory_b")
    parser.add_argument("--first-diff", action="store_true")
    parser.add_argument("--legacy-us", action="store_true", help="explicitly interpret old sidecar-free dumps as the US hash layout")
    args = parser.parse_args(argv)
    a, b = dumps(args.directory_a), dumps(args.directory_b)
    common = sorted(set(a) & set(b), key=frame_order)
    print(f"{len(a)} / {len(b)} dumps, {len(common)} common frames")
    pairs = {}
    try:
        for name in common:
            pairs[name] = compared_dump(a[name], b[name], args.legacy_us)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.first_diff:
        common = [n for n in common if pairs[n][0] != pairs[n][1]]
        print(f"{len(common)} of them differ" + (f", first {common[0]}" if common else ""))
    agg = {}
    for name in common[:20]:
        x, y, left, right = pairs[name]
        n = len(x)
        diffs = [i for i in range(0, n - 3, 4) if x[i:i + 4] != y[i:i + 4]]
        words = []
        for i in diffs[:16]:
            ad = semantic_address(i, left)
            actual_a = addr_of(i, [(p, n) for _, n, p, _ in left])
            actual_b = addr_of(i, [(p, n) for _, n, p, _ in right])
            location = ad + (f"[A={actual_a:08X},B={actual_b:08X}]" if actual_a != actual_b else "")
            words.append(f"{location}:{struct.unpack('>I', x[i:i + 4])[0]:08X}/{struct.unpack('>I', y[i:i + 4])[0]:08X}")
        for i in diffs:
            ad = semantic_address(i, left)
            agg[ad] = agg.get(ad, 0) + 1
        print(f"{name}: {len(diffs)} differing words: {' '.join(words)}")
    print("words differing most often:", " ".join(f"{k}x{v}" for k, v in sorted(agg.items(), key=lambda kv: -kv[1])[:24]))


if __name__ == "__main__":
    main()
