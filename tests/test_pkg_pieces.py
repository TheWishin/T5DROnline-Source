"""The unpack decrypts and writes each package file in 16 MB pieces (ps3recomp patch 0074; a player's unpack of
T55DATA1.BIN, ~600 MB in one piece, stopped with MemoryError). No game needed: a synthetic finalized package (the
public PS3 package key, random contents) goes through the patched pkg_extract.py, and every file must come out with
the same bytes (hashes) -- across piece borders, at odd offsets and sizes, with --only, and for a package cut short
(which now says so and exits with an error instead of leaving short files without a word).

The ps3recomp tree: PS3RECOMP_DIR, else deps/ps3recomp (of this checkout, or of the main checkout for a worktree);
skipped without one that has patch 0074.
"""
import contextlib
import gc
import hashlib
import importlib.util
import io
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_pkg_extract(marker="def write_item("):
    """ps3recomp's tools/pkg_extract.py that contains `marker` (patch 0074's function by default), or None."""
    cands = [os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")]
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--git-common-dir"], capture_output=True, text=True,
                           timeout=20)
        if r.returncode == 0:
            common = os.path.normpath(os.path.join(ROOT, r.stdout.strip()))
            cands.append(os.path.join(os.path.dirname(common), "deps", "ps3recomp"))
    except (OSError, subprocess.SubprocessError):
        pass
    for c in cands:
        p = os.path.join(c or "", "tools", "pkg_extract.py")
        if c and os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                if marker in f.read():
                    return p
    return None


def load(marker="def write_item(", what="patch 0074"):
    path = find_pkg_extract(marker)
    if not path:
        raise unittest.SkipTest(f"no ps3recomp tree with {what} (PS3RECOMP_DIR)")
    spec = importlib.util.spec_from_file_location("pkg_extract_" + str(abs(hash(marker))), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not mod._HAVE_PYCRYPTO:
        raise unittest.SkipTest("pycryptodome is missing (the pure-Python AES is too slow for megabytes)")
    return mod


def make_pkg(mod, path, files, cut=0, rev=0x8000):
    """A finalized (retail) package with `files` [(name, bytes)] plus one directory entry; `cut` bytes are taken off
    its end (a download cut short). `mod`: a pkg_extract module (its keystream)."""
    entries = [("USRDIR", b"", 0x04)] + [(n, d, 0x03) for n, d in files]
    table = bytearray()
    names = bytearray()
    body = bytearray()
    n_off = len(entries) * 0x20
    # names after the table, then the files, each 16-byte aligned except where a test wants an odd offset
    for name, _data, _flags in entries:
        names += name.encode() + b"\0" * (16 - len(name) % 16)
    f_off = n_off + len(names)
    layout = []
    for name, data, flags in entries:
        layout.append((name, f_off + len(body) if data else 0, len(data), flags))
        body += data
        body += b"\0" * (-len(body) % 16 + (3 if data else 0))      # odd gaps: the next file starts unaligned
    pos = n_off
    for (name, fo, fs, flags), (nm, _d, _f) in zip(layout, entries):
        table += struct.pack(">IIQQII", pos, len(nm), fo, fs, flags, 0)
        pos += len(nm) + (16 - len(nm) % 16)
    plain = bytes(table + names + body)
    plain += b"\0" * (-len(plain) % 16)
    riv = bytes(random.Random(5).randrange(256) for _ in range(16))
    hdr = bytearray(0xC0)
    hdr[0:4] = b"\x7fPKG"
    struct.pack_into(">H", hdr, 4, rev)                     # 0x8000: finalized
    struct.pack_into(">I", hdr, 0x14, len(entries))
    struct.pack_into(">Q", hdr, 0x20, len(hdr))
    struct.pack_into(">Q", hdr, 0x28, len(plain))
    hdr[0x30:0x30 + 36] = b"UP0000-TEST00000_00-0000000000000000"
    hdr[0x70:0x80] = riv
    ks = mod._keystream("finalized", riv, bytes(hdr[0x60:0xA0]), 0, len(plain) // 16)
    enc = (int.from_bytes(plain, "big") ^ int.from_bytes(ks, "big")).to_bytes(len(plain), "big")
    data = bytes(hdr) + enc
    with open(path, "wb") as f:
        f.write(data[:len(data) - cut] if cut else data)


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Pieces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.M = load()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        rnd = random.Random(115)
        self.files = [("PARAM.SFO", rnd.randbytes(1234)),
                      ("USRDIR/EBOOT.BIN", b"SCE\0" + rnd.randbytes(70001)),
                      ("USRDIR/T55DATA1.BIN", rnd.randbytes(300000 + 7)),
                      ("USRDIR/EMPTY.BIN", b""),
                      ("USRDIR/SMALL.BIN", rnd.randbytes(5))]
        self.pkg = os.path.join(self.tmp.name, "t.pkg")
        self.out = os.path.join(self.tmp.name, "out")

    def run_main(self, *args, piece=None, progress=None):
        argv = ["pkg_extract.py", self.pkg, self.out, *args]
        buf = io.StringIO()
        patches = [mock.patch.object(sys, "argv", argv)]
        if piece:
            patches.append(mock.patch.object(self.M, "PIECE", piece))
        if progress:
            patches.append(mock.patch.object(self.M, "PROGRESS", progress))
        code = 0
        with contextlib.ExitStack() as st:
            for p in patches:
                st.enter_context(p)
            st.enter_context(contextlib.redirect_stdout(buf))
            st.enter_context(warnings.catch_warnings())
            warnings.simplefilter("ignore", ResourceWarning)
            try:
                self.M.main()
            except SystemExit as e:
                code = e.code
            gc.collect()                # main() leaves the package open; closed here, before the folder goes
        return code, buf.getvalue()

    def check_files(self, files):
        for name, data in files:
            p = os.path.join(self.out, *name.split("/"))
            if not data:
                self.assertFalse(os.path.exists(p), name)      # (empty entries were never written, as before)
                continue
            with open(p, "rb") as f:
                self.assertEqual(sha(f.read()), sha(data), name)

    def test_same_bytes_small_pieces(self):
        """Pieces of 4 KB: hundreds of piece borders, files at unaligned offsets, the SELF tag from the first piece."""
        make_pkg(self.M, self.pkg, self.files)
        code, out = self.run_main(piece=4096, progress=64 * 1024)
        self.assertFalse(code, out)
        self.check_files(self.files)
        self.assertIn("USRDIR/EBOOT.BIN  (70005 bytes)  <-- SELF", out)
        self.assertIn("... USRDIR/T55DATA1.BIN: 0 of 0 MB", out)       # progress lines (64 KB steps here)

    def test_same_bytes_real_piece(self):
        """The real piece size: one file of 16 MB + 37 bytes is written in two pieces, one of 16 MB exactly in one."""
        rnd = random.Random(7)
        files = [("USRDIR/BIG.BIN", rnd.randbytes((16 << 20) + 37)), ("USRDIR/EXACT.BIN", rnd.randbytes(16 << 20))]
        make_pkg(self.M, self.pkg, files)
        self.assertEqual(self.M.PIECE, 16 << 20)
        calls = []
        real = self.M.write_item

        def spy(dr, k, fo, fs, op, nm=""):
            def counted(*a):
                calls.append((nm, a[2]))
                return dr(*a)
            return real(counted, k, fo, fs, op, nm)
        with mock.patch.object(self.M, "write_item", spy):
            code, out = self.run_main()
        self.assertFalse(code, out)
        self.check_files(files)
        self.assertEqual([n for nm, n in calls if nm == "USRDIR/BIG.BIN"], [16 << 20, 37])
        self.assertEqual([n for nm, n in calls if nm == "USRDIR/EXACT.BIN"], [16 << 20])

    def test_only(self):
        make_pkg(self.M, self.pkg, self.files)
        code, out = self.run_main("--only", "EBOOT.BIN", piece=4096)
        self.assertFalse(code, out)
        self.check_files([f for f in self.files if f[0].endswith("EBOOT.BIN")])
        self.assertFalse(os.path.exists(os.path.join(self.out, "USRDIR", "T55DATA1.BIN")))

    def test_cut_short(self):
        """A package missing its last 1000 bytes: the bytes that are there come out as before, and it says so."""
        make_pkg(self.M, self.pkg, self.files, cut=1000)
        code, out = self.run_main(piece=4096)
        self.assertIn("cut short", str(code))
        self.assertIn("USRDIR/SMALL.BIN: only 0 of 5 bytes", out)
        self.assertRegex(out, r"USRDIR/T55DATA1.BIN: only \d+ of 300007 bytes")
        with open(os.path.join(self.out, "USRDIR", "T55DATA1.BIN"), "rb") as f:
            got = f.read()
        data = dict(self.files)["USRDIR/T55DATA1.BIN"]
        self.assertLess(len(got), len(data))
        self.assertEqual(got, data[:len(got)])
        self.check_files(self.files[:2])


if __name__ == "__main__":
    unittest.main()
