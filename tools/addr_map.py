#!/usr/bin/env python3
"""Map guest addresses of the US program to another build of the game (docs/EU.md "Porting the rest").

    python tools/addr_map.py --us <US EBOOT.elf> --us-functions <functions.json>
                             --other <EU EBOOT.elf> --other-functions <functions.json>
                             [--out map.json] [ADDR ...]

Developer tool, 1.1.9. The function lists are find_functions.py's output for each program (build_game.py's lift
step writes build/out/functions.json). Everything it reads and writes is game-derived: keep it in a scratch folder.

Functions: each function's instruction stream with the parts a relink changes masked (branch targets, the
16-bit immediates of D-form instructions: addresses, TOC offsets, struct offsets) is hashed; hashes unique in both
programs are anchors, then matches spread through the call lists of matched pairs (the n-th call of a pair calls
a pair) and to the neighbours of matched pairs, as long as the masked streams are equal.

Data: walking each matched pair of functions instruction by instruction, every absolute address both compute
(lis/addis + addi/ori/load/store displacement, lwz from a TOC slot) is paired; the pairing seen most often for a
US address wins. A US address without a pair of its own gets the delta of the nearest pair below it -- only a
hint: where a structure's layout changed (docs/EU.md) the fields must be checked one by one.

ADDR: US addresses to look up (hex). Prints, per address: the function or data mapping and how it was found.
"""
import argparse
import bisect
import collections
import hashlib
import json
import struct
import sys

D_FORM = {7, 8, 10, 11, 12, 13, 14, 15, 24, 25, 26, 27, 28, 29} | set(range(32, 56)) | {58, 62}
LOADS = set(range(32, 36)) | {40, 41, 42, 43, 48, 49, 50, 51, 58}


class Program:
    def __init__(self, elf, functions):
        d = open(elf, "rb").read()
        if d[:4] != b"\x7fELF":
            sys.exit(f"{elf}: not a decrypted ELF")
        phoff, = struct.unpack_from(">Q", d, 0x20)
        phnum, = struct.unpack_from(">H", d, 0x38)
        self.entry, = struct.unpack_from(">Q", d, 0x18)
        self.segs = []
        for i in range(phnum):
            t, _fl, off, va, _pa, fs, _ms, _al = struct.unpack_from(">IIQQQQQQ", d, phoff + 56 * i)
            if t == 1 and fs:
                self.segs.append((va, va + fs, d[off:off + fs]))
        self.toc = struct.unpack(">II", self.read(self.entry, 8))[1]        # the entry's OPD: {code, toc}
        self.funcs = sorted((int(f["start"], 16), int(f["end"], 16)) for f in json.load(open(functions)))
        self.starts = [s for s, _ in self.funcs]
        self.end = dict(self.funcs)
        self.info = {}
        for s, e in self.funcs:
            n = (e - s) // 4
            b = self.read(s, e - s) if n > 0 else None
            if not b:
                continue
            ws = struct.unpack(">%dI" % n, b)
            calls = [s + 4 * i + ((w & 0x3FFFFFC) - (0x4000000 if w & 0x2000000 else 0))
                     for i, w in enumerate(ws) if w >> 26 == 18 and w & 1]
            h = hashlib.sha1(struct.pack(">%dI" % n, *map(norm, ws))).digest()
            self.info[s] = (n, h, calls)

    def read(self, a, n=4):
        for lo, hi, b in self.segs:
            if lo <= a and a + n <= hi:
                return b[a - lo:a - lo + n]
        return None

    def containing(self, a):
        i = bisect.bisect_right(self.starts, a) - 1
        if i >= 0 and a < self.end[self.starts[i]]:
            return self.starts[i]
        return None


def norm(w):
    op = w >> 26
    if op == 18:
        return (op << 26) | (w & 3)
    if op in D_FORM:
        return w & 0xFFFF0000
    return w


def match_functions(us, ot):
    hu, ho = collections.defaultdict(list), collections.defaultdict(list)
    for a, (n, h, _c) in us.info.items():
        hu[h].append(a)
    for a, (n, h, _c) in ot.info.items():
        ho[h].append(a)
    m = {l[0]: ho[h][0] for h, l in hu.items() if len(l) == 1 and len(ho.get(h, ())) == 1 and us.info[l[0]][0] >= 4}
    su, so = sorted(us.info), sorted(ot.info)
    iu, io = {a: i for i, a in enumerate(su)}, {a: i for i, a in enumerate(so)}
    changed = True
    while changed:
        changed = False
        inv = {v: k for k, v in m.items()}
        for a, b in list(m.items()):
            cu, co = us.info[a][2], ot.info[b][2]
            if len(cu) == len(co):
                for x, y in zip(cu, co):
                    if x not in m and y not in inv and x in us.info and y in ot.info and \
                            us.info[x][1] == ot.info[y][1]:
                        m[x], inv[y], changed = y, x, True
            for d in (-1, 1):
                i, j = iu[a] + d, io[b] + d
                if 0 <= i < len(su) and 0 <= j < len(so):
                    x, y = su[i], so[j]
                    if x not in m and y not in inv and us.info[x][1] == ot.info[y][1]:
                        m[x], inv[y], changed = y, x, True
    return m


def addresses(p, s, n):
    """{instruction index: address} of the absolute addresses the function at `s` computes (a small tracker of
    constants per register; a call forgets them all)."""
    out, regs = {}, {}
    for i, w in enumerate(struct.unpack(">%dI" % n, p.read(s, 4 * n))):
        op, rt, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        if op == 15:                                            # addis / lis
            if ra == 0:
                regs[rt] = (simm << 16) & 0xFFFFFFFF
            elif ra in regs:
                regs[rt] = (regs[ra] + (simm << 16)) & 0xFFFFFFFF
            else:
                regs.pop(rt, None)
        elif op == 14:                                          # addi
            if ra in regs:
                regs[rt] = out[i] = (regs[ra] + simm) & 0xFFFFFFFF
            elif ra == 2:
                out[i] = ("toc", (p.toc + simm) & 0xFFFFFFFF)
                regs.pop(rt, None)
            else:
                regs.pop(rt, None)
        elif op == 24:                                          # ori
            if rt in regs:
                regs[ra] = out[i] = regs[rt] | imm
        elif op in D_FORM and op >= 32:                         # loads and stores
            disp = simm & ~3 if op in (58, 62) else simm
            if ra == 2:
                slot = (p.toc + disp) & 0xFFFFFFFF
                b = p.read(slot, 4) if op == 32 else None
                if b:
                    regs[rt] = out[i] = struct.unpack(">I", b)[0]
                    continue
                out[i] = ("toc", slot)
            elif ra in regs:
                out[i] = (regs[ra] + disp) & 0xFFFFFFFF
            if op in LOADS:
                regs.pop(rt, None)
        elif op == 18 and w & 1:
            regs = {}
        elif op == 31:
            regs.pop(rt, None)
            regs.pop(ra, None)
    return out


def pair_data(us, ot, fmap):
    seen = collections.Counter()
    for a, b in fmap.items():
        n = us.info[a][0]
        if ot.info[b][0] != n:
            continue
        wb = addresses(ot, b, n)
        for i, x in addresses(us, a, n).items():
            y = wb.get(i)
            if y is None or isinstance(x, tuple) != isinstance(y, tuple):
                continue
            if isinstance(x, tuple):
                seen[(x[1], y[1])] += 1
            elif x >= 0x10000 and y >= 0x10000:
                seen[(x, y)] += 1
    best = {}
    for (x, y), c in seen.items():
        if x not in best or c > best[x][1]:
            best[x] = (y, c)
    return best


def look(a, us, ot, fmap, dmap, dkeys):
    if a in fmap:
        return f"{a:08X} -> {fmap[a]:08X}  function entry, matched"
    f = us.containing(a)
    if f is not None:
        if f in fmap:
            return f"{a:08X} -> {fmap[f] + a - f:08X}  inside function {f:08X} (+0x{a - f:X}), matched"
        return f"{a:08X} -> ?  inside function {f:08X}, which has no match (other code)"
    if a in dmap:
        return f"{a:08X} -> {dmap[a][0]:08X}  data, paired {dmap[a][1]}x"
    i = bisect.bisect_right(dkeys, a) - 1
    if i < 0:
        return f"{a:08X} -> ?  no data pair below it"
    lo = dkeys[i]
    return (f"{a:08X} -> {a + dmap[lo][0] - lo:08X}?  hint: the delta of the pair {lo:08X} -> {dmap[lo][0]:08X} "
            f"0x{a - lo:X} below it -- check the field")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--us", required=True)
    ap.add_argument("--us-functions", required=True)
    ap.add_argument("--other", required=True)
    ap.add_argument("--other-functions", required=True)
    ap.add_argument("--out", help="write the maps as JSON (game-derived: a scratch folder)")
    ap.add_argument("addr", nargs="*")
    a = ap.parse_args(argv)
    us, ot = Program(a.us, a.us_functions), Program(a.other, a.other_functions)
    fmap = match_functions(us, ot)
    dmap = pair_data(us, ot, fmap)
    total = sum(n for n, _h, _c in us.info.values())
    print(f"functions: {len(fmap)} of {len(us.info)} US functions matched "
          f"({100 * sum(us.info[x][0] for x in fmap) / total:.1f} % of the US code); data pairs: {len(dmap)}; "
          f"TOC {us.toc:08X} -> {ot.toc:08X}")
    if a.out:
        with open(a.out, "w") as f:
            json.dump({"functions": {f"{k:08X}": f"{v:08X}" for k, v in sorted(fmap.items())},
                       "data": {f"{k:08X}": [f"{v[0]:08X}", v[1]] for k, v in sorted(dmap.items())}}, f, indent=0)
    dkeys = sorted(dmap)
    for x in a.addr:
        print(look(int(x, 16), us, ot, fmap, dmap, dkeys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
