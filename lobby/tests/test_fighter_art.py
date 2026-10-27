"""fighter_art.py (1.1.5): the game's second packing (LZ), a DXT5 square, the cache folder and its checks -- with
stand-in data only (nothing of the game is in the repository)."""
import json
import os
import struct
import tempfile
import unittest
from unittest import mock

import util  # noqa: F401  (lobby/ on the path)
from t5lobby import fighter_art as fa
from t5lobby import rank_art as ra


def pack(items):
    """Items -> the game's LZ: bytes are literals, (length, distance) tuples copies; 7 items to a flag byte."""
    out = bytearray()
    for k in range(0, len(items), 7):
        group = items[k:k + 7]
        flags = 0x80
        body = bytearray()
        for b, it in enumerate(group):
            if isinstance(it, int):
                flags |= 1 << b
                body.append(it)
            else:
                ln, dist = it
                ln = 0 if ln == 32 else ln
                dist = 0 if dist == 2048 else dist
                body += bytes(((ln << 3) | (dist >> 8), dist & 0xFF))
        out.append(flags)
        out += body
    return bytes(out)


class LzTest(unittest.TestCase):
    def test_literals_and_copies(self):
        src = pack([ord(c) for c in "abcd"] + [(4, 4), (3, 1), ord("z")])
        self.assertEqual(bytes(fa.lz_unpack(src)), b"abcdabcddddz")

    def test_exact(self):
        src = pack([1, 2, 3, (6, 3), 9])
        self.assertEqual(bytes(fa.lz_unpack(src)), bytes([1, 2, 3, 1, 2, 3, 1, 2, 3, 9]))

    def test_length_0_is_32_and_distance_0_is_2048(self):
        lit = list(range(1, 33))
        src = pack(lit + [(32, 32)])
        self.assertEqual(bytes(fa.lz_unpack(src)), bytes(lit * 2))
        far = pack([7] + [(32, 2048)])             # before the start: zeros
        self.assertEqual(bytes(fa.lz_unpack(far)), bytes([7]) + bytes(32))

    def test_need_stops_early(self):
        src = pack([5] * 30)
        self.assertLessEqual(len(fa.lz_unpack(src, need=7)), 7 + 7)

    def test_cut_off(self):
        with self.assertRaises(fa.ArtError):
            fa.lz_unpack(bytes([0x80, 0x10]))      # a copy without its second byte


def dxt5_block(alpha, color565):
    """One DXT5 block of a single colour and alpha."""
    return bytes((alpha, alpha)) + bytes(6) + struct.pack("<HH", color565, color565) + bytes(4)


class PictureTest(unittest.TestCase):
    def test_square_of_a_dxt5_picture(self):
        w = 16                                     # 4 x 2 blocks; block (bx, by) red = bx * 8
        data = b"".join(dxt5_block(255, (bx * 8) << 11) for by in range(2) for bx in range(4))
        rgba = fa.dxt5_square(data, w, 4, 4, 4)    # block (1, 1)
        self.assertEqual(len(rgba), 4 * 4 * 4)
        self.assertEqual(rgba[0], 8 * 255 // 31)
        self.assertEqual(rgba[3], 255)

    def ntp3(self, w=fa.TEX_W, h=fa.TEX_H, fmt=2):
        body = bytes(((w + 3) // 4) * ((h + 3) // 4) * 16)
        hdr = bytearray(0x60)
        hdr[0:4] = b"NTP3"
        struct.pack_into(">I", hdr, 0x18, len(body))
        struct.pack_into(">H", hdr, 0x1C, 0x50)
        hdr[0x23] = fmt
        struct.pack_into(">HH", hdr, 0x24, w, h)
        return bytes(hdr) + body

    def test_render_must_be_the_games(self):
        raw = self.ntp3(w=512)
        packed = pack(list(raw[:0x60]))            # (only the header matters for the check)
        with mock.patch.object(ra, "read_entry", return_value=packed):
            with self.assertRaises(fa.ArtError):
                fa.render_dxt("elf", "data", 0, rows=4)
        with self.assertRaises(fa.ArtError):
            fa.render_dxt("elf", "data", fa.COUNT)

    def test_table(self):
        self.assertEqual(len(fa.RENDERS), 36)
        self.assertEqual(len(fa.BOX), 36)
        self.assertEqual(list(fa.RENDERS), sorted(set(fa.RENDERS)))
        for x, y, side in fa.BOX:
            self.assertEqual((x % 4, y % 4, side % 4), (0, 0, 0))
            self.assertTrue(0 <= x and x + side <= fa.TEX_W and 0 <= y and y + side <= fa.TEX_H)


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = os.path.join(self.tmp.name, "cache", "fighters")

    def test_extract_then_sizes(self):
        self.assertFalse(fa.is_ready(self.folder))
        with self.assertRaises(fa.ArtError):
            fa.extract(self.tmp.name)                 # no game: nothing to read
        solid = bytes((200, 30, 30, 255)) * (fa.SIZE * fa.SIZE)
        with mock.patch.object(ra, "find_sources", return_value=("elf", "data")), \
                mock.patch.object(fa, "portrait", return_value=solid) as por:
            self.assertEqual(fa.extract(self.tmp.name), self.folder)
            self.assertEqual(por.call_count, fa.COUNT)
            os.remove(fa.face_path(self.folder, 3))   # a missing file: not ready, made again (only that one)
            self.assertFalse(fa.is_ready(self.folder))
            fa.extract(self.tmp.name)
            self.assertEqual(por.call_count, fa.COUNT + 1)
        self.assertTrue(fa.is_ready(self.folder))
        with open(os.path.join(self.folder, "fighters.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["format"], fa.FORMAT)
        fa.ensure_size(self.folder, 40)
        with open(fa.face_path(self.folder, 0, 40), "rb") as f:
            w, h, rgba = ra.png_rgba(f.read())
        self.assertEqual((w, h), (40, 40))
        self.assertEqual(tuple(rgba[:4]), (200, 30, 30, 255))

    def test_nothing_in_the_repository(self):
        # the pictures live in the player's output folder only: no PNG of a fighter anywhere in the source tree
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        found = [os.path.join(dp, f) for dp, _d, fs in os.walk(os.path.join(root, "lobby")) for f in fs
                 if f.startswith("face_") and f.endswith(".png")]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
