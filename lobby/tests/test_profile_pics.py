"""Profile pictures (docs/ONLINE.md "Profile picture"; t5lobby/picfmt.py, server/profile_pics.py, client.py).

Covers: the picture format (round trip, the same bytes from the same pixels, every file that is not the strict
format refused: other chunks / text, alpha, palette, interlacing, 16 bits, a size outside the limits, bytes after
the end, a wrong checksum, packed data that is more or less than the pixels, a small file that unpacks huge);
upload -> the profile lists it -> another player in the lobby gets exactly the server's clean file; the stored
bytes are the server's own (metadata a modified client sends never arrives); accounts only; size, count
(the oldest goes), per-hour and whole-store limits; parts out of order; a wrong hash; not before login; not for a
client without the cap (no `pics` field, requests refused) -- an older launcher sees what it always saw; a server
with the feature off; a blocked player gets no picture; "Remove my data", the admin tool's delete and the sweep
remove the pictures; the status port has no picture route.
"""
import asyncio
import base64
import contextlib
import hashlib
import io
import json
import os
import random
import struct
import tempfile
import unittest
import unittest.mock
import zlib

import util
from t5lobby import picfmt, proto
from t5lobby.proto import LobbyError
from t5lobby.server import profile_pics
from test_friends import Base


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


async def raw_put(c, fighter, costume, data, digest=None, size=None, order=None, chunk_size=4096):
    """An upload as a modified launcher could send it (no check on this side)."""
    r = await c._request({"t": "pic_put", "fighter": fighter, "costume": costume,
                          "size": len(data) if size is None else size,
                          "sha256": digest or hashlib.sha256(data).hexdigest()})
    offs = list(range(0, len(data), chunk_size))
    last = None
    for off in (order(offs) if order else offs):
        last = await c._request({"t": "pic_part", "id": r["id"], "off": off,
                                 "data": base64.b64encode(data[off:off + chunk_size]).decode("ascii")})
    return last


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


class PicBase(Base):
    def aid(self, name):
        return self.s.call(lambda: self.s.srv.store.account(name)["id"])


class ServerTest(PicBase):
    server_cfg = dict(pic_uploads_hour=100)

    def test_upload_profile_and_fetch(self):
        a, b, g = self.acc("Alice"), self.acc("Bob"), self.guest("Gus")
        self.assertIn("profile_pics", a.welcome["features"])
        self.assertTrue(a.pics_ok())
        self.assertEqual(a.pic_limits()["max_bytes"], 200_000)
        data = png(1)
        r = a.pic_put("kazuya", 2, data)
        self.assertEqual((r["t"], r["sha"], r["size"]), ("pic_ok", hashlib.sha256(data).hexdigest(), len(data)))
        self.assertTrue(a.pic_put("kazuya", 2, data).get("same"))            # again: nothing is sent
        for viewer in (a, b, g):                                             # everybody in the lobby, guests too
            prof = viewer.profile("Alice")
            self.assertEqual(prof["pics"], [{"fighter": "kazuya", "costume": 2, "sha": r["sha"], "size": len(data)}])
            self.assertEqual(viewer.pic_get("Alice", "kazuya", 2, r["sha"]), data)
        self.assertEqual(b.profile("Bob")["pics"], [])
        with self.assertRaises(LobbyError) as e:
            b.pic_get("Alice", "kazuya", 1)
        self.assertEqual(e.exception.code, proto.E_NOT_FOUND)
        with self.assertRaises(LobbyError):
            b.pic_get("Nobody", "kazuya", 2)
        a.pic_put("kazuya", 1, png(2))                                       # a second costume, another fighter
        a.pic_put("lili", 3, png(3))
        self.assertEqual([(p["fighter"], p["costume"]) for p in b.profile("Alice")["pics"]],
                         [("lili", 3), ("kazuya", 1), ("kazuya", 2)])        # the newest first
        new = png(9)
        a.pic_put("kazuya", 2, new)                                          # replaced
        self.assertEqual(b.pic_get("Alice", "kazuya", 2), new)
        self.assertEqual(a.pic_del("kazuya", 2), 1)                          # removed by its owner
        self.assertEqual(a.pic_del("lili"), 1)
        self.assertEqual([(p["fighter"], p["costume"]) for p in b.profile("Alice")["pics"]], [("kazuya", 1)])
        self.assertEqual(a.pic_del(), 1)
        self.assertEqual(b.profile("Alice")["pics"], [])

    def test_what_is_stored_is_the_servers_own_file(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        w, h, rgb = pixels(64, 80, 4)
        body = plain_rows(w, h, rgb)
        other = raw_png(w, h, body)                          # the same pixels, packed another way
        self.assertNotEqual(other, picfmt.encode(w, h, rgb))
        r = a._run(raw_put(a, "jin", 1, other))
        self.assertEqual(r["t"], "pic_ok")
        self.assertEqual(b.pic_get("Alice", "jin", 1), picfmt.encode(w, h, rgb))
        self.assertEqual(r["sha"], hashlib.sha256(picfmt.encode(w, h, rgb)).hexdigest())
        marked = raw_png(w, h, body, extra=chunk(b"tEXt", b"Author\0C:\\Users\\alice"))
        with self.assertRaises(LobbyError) as e:             # a text chunk (a path, a name): refused whole
            a._run(raw_put(a, "jin", 2, marked))
        self.assertEqual(e.exception.code, profile_pics.E_PIC_BAD)
        self.assertEqual([p["costume"] for p in b.profile("Alice")["pics"]], [1])
        blobs = self.s.call(lambda: [bytes(r[0]) for r in self.s.srv._pics.db.execute("SELECT png FROM pics")])
        self.assertTrue(blobs and all(b"alice" not in x and b"tEXt" not in x for x in blobs))

    def test_refusals(self):
        a, g = self.acc("Alice"), self.guest("Gus")
        data = picfmt.encode(96, 128, random.Random(5).randbytes(96 * 128 * 3))     # ~37 KB: several parts
        self.assertGreater(len(data), 20_000)
        digest = hashlib.sha256(data).hexdigest()
        with self.assertRaises(LobbyError) as e:                 # guests keep nothing on the server
            g.pic_put("kazuya", 1, data)
        self.assertEqual(e.exception.code, proto.E_NOT_ALLOWED)
        for fighter, costume in (("nobody", 1), ("random", 1), ("kazuya", 0), ("kazuya", 4), ("../x", 1),
                                 ("KAZUYA", 1), ("kazuya", "1"), ("kazuya", True)):
            with self.assertRaises(LobbyError, msg=(fighter, costume)):
                a._call({"t": "pic_put", "fighter": fighter, "costume": costume, "size": len(data), "sha256": digest})
        for size in (0, 10, 200_001, 10 ** 9, "5", True, None):
            with self.assertRaises(LobbyError, msg=size):
                a._call({"t": "pic_put", "fighter": "kazuya", "costume": 1, "size": size, "sha256": digest})
        with self.assertRaises(LobbyError):                      # a part with no upload
            a._call({"t": "pic_part", "id": "x", "off": 0, "data": "AAAA"})
        with self.assertRaises(LobbyError) as e:                 # the bytes are not what was announced
            a._run(raw_put(a, "kazuya", 1, data, digest="0" * 64))
        self.assertEqual(e.exception.code, profile_pics.E_PIC_BAD)
        with self.assertRaises(LobbyError):                      # parts out of order
            a._run(raw_put(a, "kazuya", 1, data, order=lambda o: list(reversed(o)), chunk_size=1024))
        with self.assertRaises(LobbyError):                      # more than announced
            a._run(raw_put(a, "kazuya", 1, data, size=len(data) - 100, digest=digest, chunk_size=1024))
        with self.assertRaises(LobbyError) as e:                 # not a picture
            a._run(raw_put(a, "kazuya", 1, b"MZ" + os.urandom(3000)))
        self.assertEqual(e.exception.code, profile_pics.E_PIC_BAD)
        with self.assertRaises(LobbyError):                      # a part bigger than a part may be
            a._run(raw_put(a, "kazuya", 1, data + bytes(6000), chunk_size=5000))
        self.assertEqual(a.profile("Alice")["pics"], [])
        self.assertEqual(self.s.call(lambda: tuple(self.s.srv._pics.total())), (0, 0))
        a.pic_put("kazuya", 1, data)                             # and the connection still works
        self.assertEqual(len(a.profile("Alice")["pics"]), 1)

    def test_not_before_login(self):
        a = self.acc("Alice")
        a.pic_put("kazuya", 1, png(1))

        async def ask():
            host, port = self.s.addr.rsplit(":", 1)
            r, w = await asyncio.open_connection(host, int(port))
            out = []
            for msg in ({"t": "hello", "proto": proto.PROTO_VERSION, "client": "t", "build": util.BUILD.as_wire(),
                         "caps": ["profile_pics"], "rid": 1},
                        {"t": "pic_get", "name": "Alice", "fighter": "kazuya", "costume": 1, "rid": 2},
                        {"t": "profile", "name": "Alice", "rid": 3}):
                w.write((json.dumps(msg) + "\n").encode())
                await w.drain()
                out.append(json.loads(await asyncio.wait_for(r.readline(), 5)))
            w.close()
            return out
        hello, pic, prof = asyncio.run(ask())
        self.assertEqual(hello["t"], "welcome")
        self.assertEqual((pic["t"], pic["code"]), ("error", proto.E_STATE))
        self.assertEqual((prof["t"], prof["code"]), ("error", proto.E_STATE))
        self.assertNotIn("data", pic)

    def test_blocked_player_gets_no_picture(self):
        a, b, c = self.acc("Alice"), self.acc("Bob"), self.acc("Cara")
        a.pic_put("kazuya", 1, png(1))
        a.block("Bob")
        self.assertNotIn("pics", b.profile("Alice"))
        with self.assertRaises(LobbyError) as e:
            b.pic_get("Alice", "kazuya", 1)
        self.assertEqual(e.exception.code, proto.E_NOT_FOUND)
        self.assertEqual(len(c.profile("Alice")["pics"]), 1)
        self.assertEqual(len(a.profile("Alice")["pics"]), 1)


class OldClientTest(PicBase):
    def test_a_launcher_without_the_cap_sees_what_it_always_saw(self):
        a = self.acc("Alice")
        a.pic_put("kazuya", 1, png(1))
        old = self.acc("Olda", profile_pics=False)
        self.assertNotIn("profile_pics", old.welcome["caps"])
        self.assertNotIn("profile_pics", old.welcome)
        self.assertFalse(old.pics_ok())
        prof = old.profile("Alice")
        self.assertNotIn("pics", prof)
        self.assertEqual(prof["name"], "Alice")
        for msg in ({"t": "pic_get", "name": "Alice", "fighter": "kazuya", "costume": 1},
                    {"t": "pic_put", "fighter": "kazuya", "costume": 1, "size": 100, "sha256": "0" * 64},
                    {"t": "pic_del"}):
            with self.assertRaises(LobbyError) as e:
                old._call(msg)
            self.assertEqual(e.exception.code, profile_pics.E_PICS_OFF)
        with self.assertRaises(LobbyError):
            old.pic_put("kazuya", 1, png(2))                     # the client itself does not even ask


class OffTest(PicBase):
    server_cfg = dict(profile_pics=False)

    def test_feature_off(self):
        a = self.acc("Alice")
        self.assertNotIn("profile_pics", a.welcome["features"])
        self.assertFalse(a.pics_ok())
        self.assertNotIn("pics", a.profile("Alice"))
        with self.assertRaises(LobbyError) as e:
            a._call({"t": "pic_put", "fighter": "kazuya", "costume": 1, "size": 100, "sha256": "0" * 64})
        self.assertEqual(e.exception.code, profile_pics.E_PICS_OFF)


class LimitTest(PicBase):
    server_cfg = dict(pic_max=3, pic_uploads_hour=5, pic_max_kb=20)

    def test_count_rate_and_size(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.assertEqual(a.pic_limits()["max_bytes"], 20_000)
        big = picfmt.encode(200, 300, os.urandom(200 * 300 * 3))
        self.assertGreater(len(big), 20_000)
        with self.assertRaises((LobbyError, picfmt.PicError)):
            a.pic_put("kazuya", 1, big)
        with self.assertRaises(LobbyError) as e:
            a._call({"t": "pic_put", "fighter": "kazuya", "costume": 1, "size": len(big),
                     "sha256": hashlib.sha256(big).hexdigest()})
        self.assertEqual(e.exception.code, profile_pics.E_PIC_SIZE)
        for i, (f, k) in enumerate((("kazuya", 1), ("kazuya", 2), ("lili", 1), ("jin", 1))):
            a.pic_put(f, k, png(i))
        got = [(p["fighter"], p["costume"]) for p in b.profile("Alice")["pics"]]
        self.assertEqual(got, [("jin", 1), ("lili", 1), ("kazuya", 2)])          # three kept, the oldest gone
        a.pic_put("jin", 2, png(7))                                              # the fifth this hour
        with self.assertRaises(LobbyError) as e:
            a.pic_put("jin", 3, png(8))
        self.assertEqual(e.exception.code, proto.E_RATE)
        self.assertGreater(e.exception.extra.get("retry", 0), 0)
        b.pic_put("paul", 1, png(1))                                             # another account is not held up


class FullTest(PicBase):
    server_cfg = dict(pic_total_mb=0)

    def test_store_full(self):
        a = self.acc("Alice")
        with self.assertRaises(LobbyError) as e:
            a.pic_put("kazuya", 1, png(1))
        self.assertEqual(e.exception.code, profile_pics.E_PIC_FULL)


class RemovalTest(PicBase):
    def test_remove_my_data_takes_the_pictures(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.pic_put("kazuya", 1, png(1))
        a.pic_put("lili", 2, png(2))
        b.pic_put("paul", 1, png(3))
        aid = self.aid("Alice")
        self.assertEqual(a.forget_me("alice-pw1", dry_run=True)["counts"]["pictures"], 2)
        r = a.forget_me("alice-pw1")
        self.assertEqual(r["counts"]["pictures"], 2)
        self.assertEqual(self.s.call(lambda: self.s.srv._pics.list(aid)), [])
        self.assertEqual(self.s.call(lambda: self.s.srv._pics.total()[0]), 1)
        with self.assertRaises(LobbyError):
            b.pic_get("Alice", "kazuya", 1)
        c = self.acc("Alice")                                    # the name registered again: no picture
        self.assertEqual(c.profile("Alice")["pics"], [])

    def test_sweep_after_another_process_removed_the_account(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.pic_put("kazuya", 1, png(1))
        b.pic_put("paul", 1, png(3))
        bid = self.aid("Bob")
        a.close()

        def remove():
            srv = self.s.srv
            srv.store.delete_account("Alice")          # as the admin tool does, behind the server's back
            srv._pic_swept = -1e9
            srv._pics_tick()
            return srv._pics.total()[0], srv._pics.accounts()
        self.assertEqual(self.s.call(remove), (1, [bid]))

    def test_stalled_upload_is_dropped(self):
        a = self.acc("Alice")
        data = png(1)
        r = a._call({"t": "pic_put", "fighter": "kazuya", "costume": 1, "size": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()})

        def age():
            for c in self.s.srv.conns:
                if getattr(c, "pic_up", None):
                    c.pic_up["t"] -= 1000
            self.s.srv._pics_tick()
            return [x for x in (getattr(c, "pic_up", None) for c in self.s.srv.conns) if x]
        self.assertEqual(self.s.call(age), [])
        with self.assertRaises(LobbyError):
            a._call({"t": "pic_part", "id": r["id"], "off": 0, "data": base64.b64encode(data[:1000]).decode()})


class StoreTest(unittest.TestCase):
    def test_file_store_and_admin(self):
        from t5lobby.server import admin
        from t5lobby.server.store import Store, hash_password

        class Args:
            pass
        # (the admin commands leave their database open, as a tool that exits does)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            db = os.path.join(d, "lobby.db")
            st = Store(db)
            st.create_account("Alice", hash_password("alice-pw1", 1 << 10))
            st.create_account("Bob", hash_password("bob-pw1", 1 << 10))
            aid, bid = st.account("Alice")["id"], st.account("Bob")["id"]
            st.flush()
            st.close()
            path = profile_pics.pic_db_path("", db)
            self.assertEqual(path, db + "-pics")
            self.assertEqual(profile_pics.pic_db_path("", ":memory:"), ":memory:")
            self.assertEqual(profile_pics.pic_db_path("x.db", db), "x.db")
            ps = profile_pics.PicStore(path)
            ps.put(aid, "kazuya", 1, png(1), 9)
            ps.put(aid, "kazuya", 2, png(2), 9)
            ps.put(bid, "paul", 1, png(3), 9)
            self.assertEqual(ps.total()[0], 3)
            ps.close()
            a = Args()
            a.db, a.name, a.delete, a.fighter, a.costume, a.export = db, "Alice", False, None, None, os.path.join(d, "x")
            out = io.StringIO()
            with contextlib.redirect_stdout(out), unittest.mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("T5L_PIC_DB", None)
                admin.cmd_pics(a)
            self.assertIn("kazuya costume 2", out.getvalue())
            self.assertEqual(sorted(os.listdir(a.export)), [f"{aid}-kazuya-1.png", f"{aid}-kazuya-2.png"])
            with open(os.path.join(a.export, f"{aid}-kazuya-1.png"), "rb") as f:
                self.assertEqual(f.read(), png(1))
            a.delete, a.fighter, a.costume, a.export = True, "kazuya", 1, None
            with contextlib.redirect_stdout(io.StringIO()):
                admin.cmd_pics(a)
            ps = profile_pics.PicStore(path)
            self.assertEqual([(r["fighter"], r["costume"]) for r in ps.list(aid)], [("kazuya", 2)])
            ps.close()
            a.name, a.yes = "Alice", True                       # delete-user takes the pictures along
            with contextlib.redirect_stdout(io.StringIO()):
                admin.cmd_delete_user(a)
            ps = profile_pics.PicStore(path)
            self.assertEqual((ps.list(aid), ps.total()[0]), ([], 1))
            ps.close()


class StatusPortTest(unittest.TestCase):
    def test_the_status_port_code_knows_no_pictures(self):
        # the HTTP status endpoint is all a player outside the lobby can reach: it has no picture route
        here = os.path.dirname(os.path.abspath(profile_pics.__file__))
        with open(os.path.join(here, "status.py"), encoding="utf-8") as f:
            text = f.read()
        for word in ("_pics", "pic_get", "profile_pics", "PicStore"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
