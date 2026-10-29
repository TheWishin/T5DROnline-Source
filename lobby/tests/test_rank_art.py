"""The game's rank plates in the launcher (t5lobby/rank_art.py) with made-up data -- no game file is needed or
used: a fake program with the data table entry, a fake T55DATA1.BIN holding a made-up lobby layout whose plates are
plain colours. Also the official rank names (ranks.py) and the in-place list updates (tklist.py)."""
import os
import shutil
import struct
import tempfile
import unittest
import zlib

import util  # noqa: F401  (sets sys.path)
from t5lobby import rank_art as RA
from t5lobby import ranks

SECTOR = 3
KEY = 0x1234ABCD


def dxt5_block(rgb565, alpha=255):
    """One DXT5 block of a single colour."""
    return bytes((alpha, alpha)) + bytes(6) + struct.pack("<HH", rgb565, rgb565) + bytes(4)


def ntp3(w, h, data, fmt=2):
    head = bytearray(0x60)
    head[:4] = b"NTP3"
    struct.pack_into(">III", head, 0x10, 0x50 + len(data), 0, len(data))
    struct.pack_into(">H", head, 0x1C, 0x50)
    head[0x23] = fmt
    struct.pack_into(">HH", head, 0x24, w, h)
    return bytes(head) + data


def pack(parts):
    out = bytearray(struct.pack("<I", len(parts)))
    off = 4 + 8 * len(parts)
    body = bytearray()
    for p in parts:
        out += struct.pack("<II", off + len(body), len(p))
        body += p
    return bytes(out + body)


def colour(i):
    """A made-up 565 colour per plate."""
    return ((i * 7) % 32) << 11 | ((i * 13) % 64) << 5 | (i * 3) % 32


def layout(name=RA.LAYOUT_NAME, plate_w=RA.TEX_W):
    texs = [ntp3(8, 8, dxt5_block(0) * 4) for _ in range(RA.TEX_FIRST)]
    blocks = (plate_w // 4) * (RA.TEX_H // 4)
    texs += [ntp3(plate_w, RA.TEX_H, dxt5_block(colour(i), 200) * blocks) for i in range(RA.COUNT)]
    swg = b"SWG\0" + b"\x01\x02\x03\x04" + name + b"\0" + bytes(16)
    return pack([swg, pack(texs), b"\0" * 8])


def code(data, key):
    """The game's XOR coding (its own inverse) and the words' sum of the plain data."""
    out, _ = RA.t55_decode(data, key)
    words = struct.unpack("<%dI" % (len(data) // 4), data[:len(data) // 4 * 4])
    return out, sum(words) & 0xFFFFFFFF


def fake_install(root, lay=None, break_sum=False, packed=True):
    """<root>/game/EBOOT.elf and game/pkg/USRDIR/T55DATA1.BIN as rank_art reads them."""
    lay = lay if lay is not None else layout()
    stored = zlib.compress(lay) if packed else lay
    coded, total = code(stored, KEY)
    if break_sum:
        total ^= 1
    entry = struct.pack(">7I", SECTOR, len(stored), len(lay), total, 0, KEY, 0)
    table = bytearray(28 * RA.TOC_LEN)
    table[28 * RA.ENTRY:28 * RA.ENTRY + 28] = entry
    seg_off = 0x100
    hdr = bytearray(64)
    hdr[:6] = b"\x7fELF\x02\x02"
    struct.pack_into(">Q", hdr, 0x20, 64)                  # program headers right after the header
    struct.pack_into(">HH", hdr, 0x36, 56, 1)
    ph = struct.pack(">IIQQQQQQ", 1, 4, seg_off, RA.TOC_VA, RA.TOC_VA, len(table), len(table), 16)
    elf = bytes(hdr) + ph
    elf += bytes(seg_off - len(elf)) + bytes(table)
    os.makedirs(os.path.join(root, "game", "pkg", "USRDIR"))
    with open(os.path.join(root, "game", "EBOOT.elf"), "wb") as f:
        f.write(elf)
    with open(os.path.join(root, "game", "pkg", "USRDIR", "T55DATA1.BIN"), "wb") as f:
        f.write(bytes(SECTOR * 0x800) + coded + bytes(100))


class RankArtTest(unittest.TestCase):
    def setUp(self):
        self.d = self.tmp()
        self.folder = os.path.join(self.d, "cache", "ranks")

    def tmp(self):
        d = tempfile.mkdtemp(prefix="t5rankart-")
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_european_program_has_no_sources(self):
        # 1.1.9: the European program's table sits elsewhere and is numbered differently (fighter renders one entry
        # sooner, no rank plates): the US offsets must not read it -- the UI draws its own badges
        fake_install(self.d)
        self.assertIsNotNone(RA.find_sources(self.d))
        elf = os.path.join(self.d, "game", "EBOOT.elf")
        with open(elf, "r+b") as f:
            f.seek(0x18)
            f.write(struct.pack(">Q", 0x356980))           # e_entry of NPEA00019 v01.00
        self.assertEqual(RA.other_program(elf), "NPEA00019 v01.00")
        self.assertIsNone(RA.find_sources(self.d))
        with self.assertRaises(RA.ArtError):
            RA.extract(self.d, self.folder)

    def test_extract_and_scale(self):
        fake_install(self.d)
        self.assertEqual(RA.extract(self.d), self.folder)
        self.assertTrue(RA.is_ready(self.folder))
        w, h, rgba = RA.png_rgba(open(RA.plate_path(self.folder, 5), "rb").read())
        self.assertEqual((w, h), (RA.TEX_W, RA.TEX_H))
        c = colour(5)
        want = ((c >> 11) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31, 200)
        self.assertEqual(tuple(rgba[:4]), want)
        self.assertEqual(tuple(rgba[-4:]), want)
        RA.ensure_height(self.folder, 22)
        w, h, rgba = RA.png_rgba(open(RA.plate_path(self.folder, 36, 22), "rb").read())
        self.assertEqual((w, h), (44, 22))                    # twice as wide as high, like the plates
        c = colour(36)
        mid = (11 * w + 22) * 4
        self.assertEqual(tuple(rgba[mid:mid + 4]), ((c >> 11) * 255 // 31, (c >> 5 & 63) * 255 // 63,
                                                    (c & 31) * 255 // 31, 200))

    def test_stored_plain(self):
        fake_install(self.d, packed=False)
        RA.extract(self.d)
        self.assertTrue(RA.is_ready(self.folder))

    def test_refused(self):
        with self.assertRaises(RA.ArtError):           # nothing unpacked yet
            RA.extract(self.d)
        fake_install(self.d, break_sum=True)
        with self.assertRaises(RA.ArtError):
            RA.extract(self.d)
        self.assertFalse(RA.is_ready(self.folder))

    def test_refuses_another_layout(self):
        for lay in (layout(name=b"TK5OL_onlinebattle"), layout(plate_w=RA.TEX_W + 8)):
            d = self.tmp()
            fake_install(d, lay=lay)
            with self.assertRaises(RA.ArtError):
                RA.extract(d)

    def test_dxt5_block(self):
        # colour 0 red, colour 1 blue, every pixel index 1 (blue); alpha 255 / 0, index 1 (0)
        blk = bytes((255, 0)) + int("001" * 16, 2).to_bytes(6, "little") + struct.pack("<HH", 0xF800, 0x001F) + \
            bytes((0x55, 0x55, 0x55, 0x55))
        out = RA.dxt5_rgba(blk, 4, 4)
        self.assertEqual(tuple(out[:4]), (0, 0, 255, 0))
        self.assertEqual(len(out), 64)

    def test_art_without_folder(self):
        art = RA.Art()
        art.folder, art.ready = None, False
        self.assertIsNone(art.image(None, 3, 22))
        self.assertFalse(art.has(22))

    def test_cli(self):
        fake_install(self.d)
        self.assertEqual(RA.main(["--out", self.d, "--heights", "30"]), 0)
        self.assertTrue(os.path.isfile(RA.plate_path(self.folder, 0, 30)))
        self.assertEqual(RA.main(["--out", os.path.join(self.d, "nothing")]), 1)


class RankNamesTest(unittest.TestCase):
    def test_official_names(self):
        self.assertEqual(ranks.name(17), "Shihan")
        self.assertEqual(ranks.name(34), "Dark Lord")
        self.assertEqual(ranks.name(35), "Tekken Lord (Kouryu)")
        self.assertEqual(ranks.name(36), "Tekken Lord (Kirin)")
        self.assertEqual(len(set(ranks.NAMES)), len(ranks.NAMES))      # every tier has a name of its own

    def test_older_servers(self):
        self.assertEqual(ranks.index("Kouryu"), 35)
        self.assertEqual(ranks.index("kirin"), 36)
        self.assertEqual(ranks.display_name({"rank": "Kirin"}), "Tekken Lord (Kirin)")
        self.assertEqual(ranks.display_name({"rank": "Kouryu", "tier": 35}), "Tekken Lord (Kouryu)")
        self.assertEqual(ranks.label({"rank": "Kouryu", "tier": 35, "provisional": True}), "Tekken Lord (Kouryu)?")
        self.assertEqual(ranks.display_name({"rank": "Something new"}), "Something new")

    def test_rating_math_unchanged(self):
        self.assertEqual([t for _, t in ranks.RANKS][-3:], [2500, 2550, 2600])
        self.assertEqual(ranks.tier_for(2560), 35)


class ListSyncTest(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        try:
            self.root = tk.Tk()
        except tk.TclError as e:          # no display
            self.skipTest(str(e))
        self.root.withdraw()
        self.tv = ttk.Treeview(self.root, columns=("a", "b"), show="headings")

    def tearDown(self):
        self.root.destroy()

    def rows(self):
        return [(i, self.tv.item(i, "values")) for i in self.tv.get_children()]

    def test_sync(self):
        from t5lobby import tklist
        tklist.sync(self.tv, [("p1", ("Ann", 1), None, ()), ("p2", ("Bob", 2), None, ("me",))])
        self.tv.selection_set("p2")
        calls = []
        orig = self.tv.item
        self.tv.item = lambda *a, **k: (calls.append(a), orig(*a, **k))[1]
        tklist.sync(self.tv, [("p1", ("Ann", 1), None, ()), ("p2", ("Bob", 2), None, ("me",))])
        self.assertEqual(calls, [])                           # nothing changed: nothing touched
        tklist.sync(self.tv, [("p3", ("Cy", 3), None, ()), ("p2", ("Bob", 5), None, ("me",))])
        self.assertEqual(self.rows(), [("p3", ("Cy", "3")), ("p2", ("Bob", "5"))])
        self.assertEqual(self.tv.selection(), ("p2",))        # the selection stays
        self.assertEqual(self.tv.item("p2", "tags"), ("me",))
        self.tv.delete("p3")                                   # (deleted by someone else)
        tklist.sync(self.tv, [("p3", ("Cy", 3), None, ()), ("p2", ("Bob", 5), None, ())])
        self.assertEqual([r[0] for r in self.rows()], ["p3", "p2"])
        self.assertEqual(self.tv.item("p2", "tags"), "")


if __name__ == "__main__":
    unittest.main()
