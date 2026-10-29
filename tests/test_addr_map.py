"""tools/addr_map.py without the game (1.1.9, docs/EU.md "Porting the rest"): two small stand-in PPU programs, the
second the first relinked -- functions moved, data moved by another delta, one function changed -- and the map
finds the moved functions and data, and says it cannot map the changed function."""
import json
import os
import struct
import tempfile
import unittest

from helpers import load_tool


def ppc_lis(rt, v):
    return (15 << 26) | (rt << 21) | (v & 0xFFFF)


def ppc_lwz(rt, ra, d):
    return (32 << 26) | (rt << 21) | (ra << 16) | (d & 0xFFFF)


def ppc_stw(rs, ra, d):
    return (36 << 26) | (rs << 21) | (ra << 16) | (d & 0xFFFF)


def ppc_bl(frm, to):
    return (18 << 26) | ((to - frm) & 0x3FFFFFC) | 1


BLR = 0x4E800020
NOP = 0x60000000


def program(base, data, toc, changed=False):
    """{addr: [words]} of five functions; f1 reads and writes the global at `data`, f0 calls f1 and f2, f2..f4 are
    plain. With `changed`, f3 has one more instruction (another build of it)."""
    f = {}
    f[base + 0x000] = [NOP, ppc_bl(base + 0x004, base + 0x100), ppc_bl(base + 0x008, base + 0x200), NOP, BLR]
    f[base + 0x100] = [ppc_lis(9, (data + 0x8000) >> 16), ppc_lwz(3, 9, data & 0xFFFF), ppc_stw(3, 9, (data + 4) & 0xFFFF),
                       NOP, BLR]
    f[base + 0x200] = [0x38600001, 0x38800002, 0x7C632214, NOP, BLR]
    f[base + 0x300] = [0x38600003, 0x7C631A14] + ([0x7C631A14] if changed else []) + [NOP, NOP, BLR]
    f[base + 0x400] = [0x38600005, 0x38800006, 0x7C6321D6, NOP, NOP, BLR]
    return f, toc


def write(d, name, funcs, toc, entry_code):
    """A big-endian ELF64 with a code segment (the functions + the entry OPD) and the functions.json."""
    lo = min(funcs)
    hi = max(a + 4 * len(w) for a, w in funcs.items())
    code = bytearray(hi - lo + 0x10)
    for a, ws in funcs.items():
        code[a - lo:a - lo + 4 * len(ws)] = struct.pack(">%dI" % len(ws), *ws)
    opd = hi - lo + 8
    code[opd - 8:opd] = bytes(8)
    code += struct.pack(">II", entry_code, toc)
    entry = lo + len(code) - 8
    hdr = bytearray(64)
    hdr[:6] = b"\x7fELF\x02\x02"
    struct.pack_into(">QQ", hdr, 0x18, entry, 64)
    struct.pack_into(">HH", hdr, 0x36, 56, 1)
    ph = struct.pack(">IIQQQQQQ", 1, 5, 0x100, lo, lo, len(code), len(code), 16)
    elf = bytes(hdr) + ph
    elf += bytes(0x100 - len(elf)) + bytes(code)
    p = os.path.join(d, name + ".elf")
    with open(p, "wb") as f:
        f.write(elf)
    j = os.path.join(d, name + ".json")
    with open(j, "w") as f:
        json.dump([{"start": "0x%08X" % a, "end": "0x%08X" % (a + 4 * len(w))} for a, w in sorted(funcs.items())], f)
    return p, j


class AddrMap(unittest.TestCase):
    def test_relinked_program(self):
        m = load_tool("addr_map")
        with tempfile.TemporaryDirectory() as d:
            us = write(d, "us", *program(0x10000, 0x10091000, 0x470540), entry_code=0x10000)
            eu = write(d, "eu", *program(0x20000, 0x1007E100, 0x3760E0, changed=True), entry_code=0x20000)
            U, E = m.Program(*us), m.Program(*eu)
            self.assertEqual((U.toc, E.toc), (0x470540, 0x3760E0))
            fmap = m.match_functions(U, E)
            self.assertEqual(fmap[0x10000], 0x20000)
            self.assertEqual(fmap[0x10100], 0x20100)          # through f0's calls
            self.assertEqual(fmap[0x10400], 0x20400)
            self.assertNotIn(0x10300, fmap)                    # another build of it: no match
            dmap = m.pair_data(U, E, fmap)
            self.assertEqual(dmap[0x10091000][0], 0x1007E100)
            self.assertEqual(dmap[0x10091004][0], 0x1007E104)
            keys = sorted(dmap)
            self.assertIn("-> 00020104  inside function 00010100 (+0x4), matched", m.look(0x10104, U, E, fmap, dmap, keys))
            self.assertIn("which has no match", m.look(0x10304, U, E, fmap, dmap, keys))
            self.assertIn("-> 1007E108?  hint", m.look(0x10091008, U, E, fmap, dmap, keys))


if __name__ == "__main__":
    unittest.main()
