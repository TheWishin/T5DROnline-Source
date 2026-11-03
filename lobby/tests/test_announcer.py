"""The game's announcer for the Online tab's notification (t5lobby/announcer.py, notify.py VOICE_KINDS) with made-up
data -- no game file is needed or used: a fake program with the data table, a fake T55DATA1.BIN holding a made-up
sound bank whose "line" is a tone coded as PlayStation ADPCM here. Nothing makes a sound: winsound is a fake."""
import io
import os
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import wave
import zlib
from unittest import mock

import util  # noqa: F401  (sets sys.path)
from t5lobby import announcer as A
from t5lobby import notify
from t5lobby import rank_art as RA

SECTOR = 5
KEY = 0x0BADC0DE
COEF = A.COEF


def adpcm_encode(samples):
    """A plain PlayStation ADPCM encoder (filter 0..4 and shift picked per frame, best error): the test's own,
    independent of announcer.adpcm_decode, so the decoder is checked against the format and not against itself."""
    out = bytearray()
    s1 = s2 = 0
    n = (len(samples) + 27) // 28
    for fi in range(n):
        block = list(samples[fi * 28:fi * 28 + 28]) + [0] * (28 - len(samples[fi * 28:fi * 28 + 28]))
        best = None
        for flt in range(5):
            c1, c2 = COEF[flt]
            for shift in range(13):
                a, b, err, nib = s1, s2, 0, []
                for x in block:
                    pred = (a * c1 + b * c2) >> 6
                    q = (x - pred) * (1 << shift)
                    q = int(round(q / 4096.0))
                    q = max(-8, min(7, q))
                    v = ((q << 12) >> shift) + pred
                    v = max(-32768, min(32767, v))
                    err += (v - x) ** 2
                    nib.append(q & 0xF)
                    b, a = a, v
                if best is None or err < best[0]:
                    best = (err, flt, shift, nib, a, b)
        _err, flt, shift, nib, s1, s2 = best
        flags = 1 if fi == n - 1 else 0
        out += bytes((shift | flt << 4, flags)) + bytes(nib[i] | nib[i + 1] << 4 for i in range(0, 28, 2))
    return bytes(out)


def tone(n=2800, freq=440, rate=A.SAMPLE_RATE, amp=12000):
    import math
    return [int(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)]


def bank(samples, bank_id=A.BANK_ID, rate=A.SAMPLE_RATE, count=A.BANK_COUNT):
    """A sound bank as the game's: header, record offsets, 0xC0-byte "vag" records, the data."""
    data = bytearray()
    recs = []
    for k in range(count):
        s = samples.get(k, b"\x00\x01" + bytes(14))
        recs.append((len(data), len(s)))
        data += s
    head = 0x20 + 4 * count
    head = (head + 0x3F) // 0x40 * 0x40
    data_off = head + A.RECORD * count
    out = bytearray(data_off)
    out[:4] = b"\x00\x02\x01\x00"
    struct.pack_into(">4I", out, 8, bank_id, count, data_off, len(data))
    for k, (off, size) in enumerate(recs):
        r = head + A.RECORD * k
        struct.pack_into(">I", out, 0x20 + 4 * k, r)
        out[r:r + 4] = b"vag\0"
        struct.pack_into(">II", out, r + 0x14, size, off)
        struct.pack_into(">I", out, r + 0xBC, rate)
    return bytes(out + data)


def fake_install(root, content, packed=True):
    """<root>/game/EBOOT.elf (data table entry A.ENTRY) and game/pkg/USRDIR/T55DATA1.BIN with `content` in it."""
    stored = zlib.compress(content) if packed else content
    coded, _ = RA.t55_decode(stored, KEY)
    words = struct.unpack("<%dI" % (len(stored) // 4), stored[:len(stored) // 4 * 4])
    entry = struct.pack(">7I", SECTOR, len(stored), len(content), sum(words) & 0xFFFFFFFF, 0, KEY, 0)
    table = bytearray(28 * RA.TOC_LEN)
    table[28 * A.ENTRY:28 * A.ENTRY + 28] = entry
    seg_off = 0x100
    hdr = bytearray(64)
    hdr[:6] = b"\x7fELF\x02\x02"
    struct.pack_into(">Q", hdr, 0x20, 64)
    struct.pack_into(">HH", hdr, 0x36, 56, 1)
    ph = struct.pack(">IIQQQQQQ", 1, 4, seg_off, RA.TOC_VA, RA.TOC_VA, len(table), len(table), 16)
    elf = bytes(hdr) + ph
    elf += bytes(seg_off - len(elf)) + bytes(table)
    os.makedirs(os.path.join(root, "game", "pkg", "USRDIR"), exist_ok=True)
    with open(os.path.join(root, "game", "EBOOT.elf"), "wb") as f:
        f.write(elf)
    with open(os.path.join(root, "game", "pkg", "USRDIR", "T55DATA1.BIN"), "wb") as f:
        f.write(bytes(SECTOR * 0x800) + coded + bytes(64))


def pcm_of(wav):
    with wave.open(io.BytesIO(wav)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), \
            list(struct.unpack("<%dh" % w.getnframes(), w.readframes(w.getnframes())))


class DecoderTests(unittest.TestCase):
    def test_decodes_what_an_independent_encoder_made(self):
        src = tone()
        dec = A.adpcm_decode(adpcm_encode(src))
        self.assertEqual(len(dec), (len(src) + 27) // 28 * 28)
        err = max(abs(a - b) for a, b in zip(src, dec))
        self.assertLess(err, 600)                                     # 4-bit ADPCM of a clean tone: close

    def test_end_flag_stops(self):
        frames = adpcm_encode(tone(280))                              # 10 frames, the last flagged
        dec = A.adpcm_decode(frames + bytes((0x0C, 0)) + bytes([0x77] * 14) * 1)
        self.assertEqual(len(dec), 280)

    def test_filters_use_the_previous_samples(self):
        # one frame, filter 1 (60/64 of the last sample), shift 12: nibble 1 then zeros -> 1, 0.94, 0.88 ...
        frame = bytes((0x1C, 1, 0x01)) + bytes(13)
        dec = A.adpcm_decode(frame)
        self.assertEqual(dec[:4], [1, 0, 0, 0])
        frame = bytes((0x10, 1, 0x07)) + bytes(13)                    # shift 0: 7 << 12 = 28672
        dec = A.adpcm_decode(frame)
        self.assertEqual(dec[0], 28672)
        self.assertEqual(dec[1], (28672 * 60) >> 6)


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t5announcer")
        self.addCleanup(shutil.rmtree, self.dir, True)
        A._cached.cache_clear()
        self.addCleanup(A._cached.cache_clear)
        self.line = adpcm_encode(tone())
        import hashlib
        self.size, self.sha = len(self.line), hashlib.sha256(self.line).hexdigest()

    def known(self):
        return mock.patch.multiple(A, SAMPLE_SIZE=self.size, SAMPLE_SHA256=self.sha)

    def test_reads_the_line_from_the_game_files(self):
        fake_install(self.dir, bank({A.SAMPLE: self.line, 0: adpcm_encode(tone(560, 220))}))
        with self.known():
            wav = A.next_battle_wav(self.dir)
        self.assertIsNotNone(wav)
        rate, ch, width, pcm = pcm_of(wav)
        self.assertEqual((rate, ch, width), (A.SAMPLE_RATE, 1, 2))
        self.assertEqual(len(pcm), len(A.adpcm_decode(self.line)))
        self.assertAlmostEqual(max(abs(v) for v in pcm) / 32767, A.PEAK, delta=0.01)   # brought to PEAK

    def test_uncompressed_entry_too(self):
        fake_install(self.dir, bank({A.SAMPLE: self.line}), packed=False)
        with self.known():
            self.assertIsNotNone(A.next_battle_wav(self.dir))

    def test_another_sound_is_never_played(self):
        fake_install(self.dir, bank({A.SAMPLE: adpcm_encode(tone(2800, 330))}))   # same size, other bytes
        with self.known():
            self.assertIsNone(A.next_battle_wav(self.dir))

    def test_the_line_this_launcher_knows_only(self):
        fake_install(self.dir, bank({A.SAMPLE: self.line}))
        self.assertIsNone(A.next_battle_wav(self.dir))               # the real game's size/hash: not this fake

    def test_other_banks_rates_and_damage(self):
        cases = {"bank id": bank({A.SAMPLE: self.line}, bank_id=3),
                 "count": bank({A.SAMPLE: self.line}, count=A.BANK_COUNT - 1),
                 "rate": bank({A.SAMPLE: self.line}, rate=22050),
                 "magic": b"\x00\x02\x02\x00" + bank({A.SAMPLE: self.line})[4:],
                 "cut": bank({A.SAMPLE: self.line})[:0x30]}
        for what, content in cases.items():
            with self.subTest(what):
                A._cached.cache_clear()
                d = os.path.join(self.dir, what.replace(" ", "_"))
                fake_install(d, content)
                with self.known():
                    self.assertIsNone(A.next_battle_wav(d))

    def test_no_game_or_european_program(self):
        with self.known():
            self.assertIsNone(A.next_battle_wav(self.dir))           # nothing unpacked
            self.assertIsNone(A.next_battle_wav(None))
            fake_install(self.dir, bank({A.SAMPLE: self.line}))
            elf = os.path.join(self.dir, "game", "EBOOT.elf")
            with open(elf, "r+b") as f:                               # e_entry of NPEA00019 v02.00
                f.seek(0x18)
                f.write(struct.pack(">Q", 0x457898))
            self.assertIsNone(A.next_battle_wav(self.dir))

    def test_broken_checksum(self):
        fake_install(self.dir, bank({A.SAMPLE: self.line}))
        p = os.path.join(self.dir, "game", "pkg", "USRDIR", "T55DATA1.BIN")
        with open(p, "r+b") as f:
            f.seek(SECTOR * 0x800 + 9)
            b = f.read(1)
            f.seek(SECTOR * 0x800 + 9)
            f.write(bytes((b[0] ^ 0x40,)))
        with self.known():
            self.assertIsNone(A.next_battle_wav(self.dir))

    def test_read_once_and_again_after_a_new_build(self):
        fake_install(self.dir, bank({A.SAMPLE: self.line}))
        with self.known(), mock.patch.object(A, "voice_from", wraps=A.voice_from) as vf:
            A.next_battle_wav(self.dir)
            A.next_battle_wav(self.dir)
            self.assertEqual(vf.call_count, 1)
            p = os.path.join(self.dir, "game", "EBOOT.elf")
            st = os.stat(p)
            os.utime(p, (st.st_atime, st.st_mtime + 10))             # BUILD GAME again
            A.next_battle_wav(self.dir)
            self.assertEqual(vf.call_count, 2)

    def test_command_line(self):
        fake_install(self.dir, bank({A.SAMPLE: self.line}))
        out = os.path.join(self.dir, "line.wav")
        with self.known(), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(A.main(["--out", self.dir, "--wav", out]), 0)
        self.assertTrue(os.path.getsize(out) > 44)
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(A.main(["--out", os.path.join(self.dir, "none")]), 1)


class FakeWinsound:
    SND_MEMORY, SND_NODEFAULT, SND_ALIAS, SND_ASYNC = 4, 2, 0x10000, 1

    def __init__(self):
        self.calls = []
        self.done = threading.Event()

    def PlaySound(self, sound, flags):
        self.calls.append((sound, flags))
        self.done.set()


class NotifierVoiceTests(unittest.TestCase):
    def notifier(self, voice):
        self.played, self.voiced = [], []
        return notify.Notifier(enabled=lambda: True, away=lambda: True, play=lambda: self.played.append(1),
                               flash=lambda: None, clock=lambda: self.clock, voice=voice)

    def setUp(self):
        self.clock = 100.0

    def test_match_challenge_and_tournament_say_the_line(self):
        n = self.notifier(lambda: self.voiced.append(1) or True)
        for kind in (notify.MATCH, notify.CHALLENGE, notify.TOUR):
            self.clock += 10
            self.assertTrue(n.notify(kind, kind))
        self.assertEqual((len(self.voiced), len(self.played)), (3, 0))

    def test_other_kinds_chime(self):
        n = self.notifier(lambda: self.voiced.append(1) or True)
        for kind in (notify.JOIN, notify.TURN, notify.INVITE, notify.REMATCH, "mention"):
            self.clock += 10
            n.notify(kind, kind)
        self.assertEqual((len(self.voiced), len(self.played)), (0, 5))

    def test_the_chime_when_the_voice_is_off_or_fails(self):
        for voice in (lambda: False, lambda: None, mock.Mock(side_effect=RuntimeError("x"))):
            n = self.notifier(voice)
            self.assertTrue(n.notify(notify.MATCH, "m"))
            self.assertEqual(self.played, [1])

    def test_no_voice_hook_is_the_old_chime(self):
        n = notify.Notifier(enabled=lambda: True, away=lambda: True, play=lambda: self.played.append(1),
                            flash=lambda: None, clock=lambda: 1.0)
        self.played = []
        n.notify(notify.CHALLENGE, "c")
        self.assertEqual(self.played, [1])


@unittest.skipUnless(os.name == "nt", "the sound is Windows only")
class PlayVoiceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t5announcer")
        self.addCleanup(shutil.rmtree, self.dir, True)
        A._cached.cache_clear()
        self.addCleanup(A._cached.cache_clear)

    def play(self):
        ws = FakeWinsound()
        with mock.patch.dict(os.environ, {"T5_NOTIFY": "1"}), mock.patch.object(notify, "winsound", ws):
            self.assertTrue(notify.play_voice(self.dir))
            self.assertTrue(ws.done.wait(10))
        return ws.calls[0][0]

    def test_plays_the_line_from_the_files(self):
        line = adpcm_encode(tone())
        import hashlib
        fake_install(self.dir, bank({A.SAMPLE: line}))
        with mock.patch.multiple(A, SAMPLE_SIZE=len(line), SAMPLE_SHA256=hashlib.sha256(line).hexdigest()):
            sound = self.play()
        self.assertNotEqual(sound, notify.chime_wav())
        self.assertEqual(pcm_of(sound)[0], A.SAMPLE_RATE)

    def test_the_chime_without_the_game(self):
        self.assertEqual(self.play(), notify.chime_wav())

    def test_silent_with_t5_notify_0(self):
        ws = FakeWinsound()
        with mock.patch.dict(os.environ, {"T5_NOTIFY": "0"}), mock.patch.object(notify, "winsound", ws):
            self.assertFalse(notify.play_voice(self.dir))
        self.assertEqual(ws.calls, [])


class SettingTests(unittest.TestCase):
    TEXT = "Use the game's announcer for matches and challenges (\"Get ready for the next battle\")"

    def test_default_on_and_the_text_in_every_language(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "launcher"))
        import core
        from t5lobby import i18n
        self.assertIs(core.DEFAULTS["notify_voice"], True)
        for lang in ("de", "es", "fr", "ja", "ko", "pt-BR"):
            self.assertNotEqual(i18n.catalog(lang).get(self.TEXT, self.TEXT), self.TEXT, lang)


if __name__ == "__main__":
    unittest.main()
