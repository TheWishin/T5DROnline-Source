"""The profile picture's file format (lobby/t5lobby/picfmt.py, docs/ONLINE.md "Profile picture"): a strict subset of
PNG, checked and written anew before a picture is kept or shown on this PC."""
import random
import struct
import unittest
import zlib

import util  # noqa: F401 -- (the lobby package on the path)
from t5lobby import picfmt


def pixels(w=96, h=128, seed=1):
    rnd = random.Random(seed)
    base = [rnd.randrange(256) for _ in range(3)]
    out = bytearray()
    for y in range(h):
        for x in range(w):
            out += bytes(((base[0] + x * 2) & 255, (base[1] + y) & 255, (base[2] + x + y) & 255))
    return w, h, bytes(out)


def png(seed=1, w=96, h=128):
    return picfmt.encode(*pixels(w, h, seed))


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def header(w, h, depth=8, colour=2, lace=0):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, colour, 0, 0, lace))


def raw_png(w, h, body, depth=8, colour=2, lace=0, extra=b"", tail=b""):
    return (picfmt.SIGNATURE + header(w, h, depth, colour, lace) + extra
            + chunk(b"IDAT", zlib.compress(body)) + chunk(b"IEND", b"") + tail)


def plain_rows(w, h, rgb):
    return b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))


def zero_rows(row_bytes, rows):
    return b"".join(b"\0" + bytes(row_bytes) for _ in range(rows))


class FormatTest(unittest.TestCase):
    def test_round_trip_and_same_bytes(self):
        w, h, rgb = pixels()
        data = picfmt.encode(w, h, rgb)
        self.assertEqual(picfmt.decode(data), (w, h, rgb))
        self.assertEqual(picfmt.encode(w, h, rgb), data)
        self.assertEqual(picfmt.clean(data), data)
        for word in (b"tEXt", b"iTXt", b"zTXt", b"tIME", b"eXIf", b"iCCP", b"pHYs"):
            self.assertNotIn(word, data)

    def test_every_row_filter_decodes(self):
        w, h, rgb = pixels(64, 64, 5)
        stride = w * 3
        rnd = random.Random(3)
        body, prev = bytearray(), bytes(stride)
        for y in range(h):
            row = rgb[y * stride:(y + 1) * stride]
            kind, line = list(picfmt._filters(row, prev))[rnd.randrange(5) if y > 4 else y]
            body.append(kind)
            body += line
            prev = row
        data = raw_png(w, h, bytes(body))
        self.assertEqual(picfmt.decode(data), (w, h, rgb))
        self.assertEqual(picfmt.clean(data), picfmt.encode(w, h, rgb))

    def test_metadata_never_survives(self):
        w, h, rgb = pixels(64, 64)
        body = plain_rows(w, h, rgb)
        for extra in (chunk(b"tEXt", b"Comment\0C:\\Users\\somebody\\save"), chunk(b"tIME", b"\x07\xea\x0b\x0a\0\0\0"),
                      chunk(b"eXIf", b"II*\0"), chunk(b"iTXt", b"x\0\0\0\0\0y"), chunk(b"pHYs", bytes(9)),
                      chunk(b"prIv", b"secret")):
            with self.assertRaises(picfmt.PicError):
                picfmt.clean(raw_png(w, h, body, extra=extra))
        self.assertEqual(picfmt.clean(raw_png(w, h, body)), picfmt.encode(w, h, rgb))

    def test_refused_files(self):
        w, h, rgb = pixels(64, 64)
        body = plain_rows(w, h, rgb)
        good = raw_png(w, h, body)
        bad = {
            "not png": b"GIF89a" + good[6:],
            "empty": b"",
            "tail": raw_png(w, h, body, tail=b"hidden"),
            "second picture after the end": good + good,
            "alpha": raw_png(w, h, zero_rows(w * 4, h), colour=6),
            "palette": raw_png(w, h, zero_rows(w, h), colour=3),
            "grey": raw_png(w, h, zero_rows(w, h), colour=0),
            "16 bit": raw_png(w, h, zero_rows(w * 6, h), depth=16),
            "interlaced": raw_png(w, h, body, lace=1),
            "too wide": raw_png(picfmt.MAX_W + 1, 64, zero_rows((picfmt.MAX_W + 1) * 3, 64)),
            "too high": raw_png(64, picfmt.MAX_H + 1, zero_rows(192, picfmt.MAX_H + 1)),
            "too small": raw_png(8, 8, zero_rows(24, 8)),
            "short pixels": raw_png(w, h, body[:-10]),
            "long pixels": raw_png(w, h, body + b"more"),
            "bad filter": raw_png(w, h, b"\x07" + body[1:]),
            "bad crc": good[:40] + bytes([good[40] ^ 1]) + good[41:],
            "cut": good[:-5],
            "no data": picfmt.SIGNATURE + header(w, h) + chunk(b"IEND", b""),
            "garbage data": picfmt.SIGNATURE + header(w, h) + chunk(b"IDAT", b"not zlib at all") + chunk(b"IEND", b""),
        }
        for name, data in bad.items():
            with self.assertRaises(picfmt.PicError, msg=name):
                picfmt.clean(data)
        self.assertEqual(picfmt.clean(good), picfmt.encode(w, h, rgb))

    def test_a_small_file_cannot_unpack_huge(self):
        bomb = zlib.compress(bytes(64 << 20), 9)            # ~64 KB that would unpack to 64 MB
        data = picfmt.SIGNATURE + header(64, 64) + chunk(b"IDAT", bomb) + chunk(b"IEND", b"")
        self.assertLess(len(data), picfmt.MAX_BYTES)
        with self.assertRaises(picfmt.PicError):
            picfmt.decode(data)

    def test_too_big_file(self):
        with self.assertRaises(picfmt.PicError):
            picfmt.decode(png(), max_bytes=100)

    def test_ppm_portrait_fit(self):
        w, h = 320, 180
        rgb = bytearray()
        for y in range(h):
            for x in range(w):
                rgb += bytes((x & 255, y & 255, (x * y) & 255))
        ppm = b"P6\n# a comment\n%d %d\n255\n" % (w, h) + bytes(rgb)
        self.assertEqual(picfmt.read_ppm(ppm), (w, h, bytes(rgb)))
        pw, ph, prgb = picfmt.portrait(w, h, bytes(rgb), 60, 80)
        self.assertEqual((pw, ph, len(prgb)), (60, 80, 60 * 80 * 3))
        mid = prgb[(40 * 60 + 30) * 3]                      # the source's middle column is the portrait's middle
        self.assertTrue(150 <= mid <= 170, mid)
        data = picfmt.fit(pw, ph, prgb)
        self.assertEqual(picfmt.decode(data, min_w=1, min_h=1)[:2], (60, 80))
        rnd = random.Random(7)                              # noise does not pack: colour bits go until it fits
        noise = bytes(rnd.randrange(256) for _ in range(120 * 160 * 3))
        self.assertLessEqual(len(picfmt.fit(120, 160, noise, max_bytes=40_000)), 40_000)
        with self.assertRaises(picfmt.PicError):
            picfmt.fit(120, 160, noise, max_bytes=2_000)
        self.assertLess(picfmt.detail(60, 80, bytes(60 * 80 * 3)), 0.01)
        self.assertGreater(picfmt.detail(pw, ph, prgb), 1.0)
        for junk in (b"", b"P5\n1 1\n255\n\0", b"P6\n2 2\n255\n\0", b"P6\n2 2\n65535\n" + bytes(24)):
            with self.assertRaises(picfmt.PicError):
                picfmt.read_ppm(junk)


if __name__ == "__main__":
    unittest.main()
