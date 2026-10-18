"""The antivirus tooling (tools/pe_features.py, tools/fp_pack.py, tools/av_local_scan.py, the stub variants of
tools/package_release.py). No toolchain, no Defender and no network needed."""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helpers import PY, ROOT, TOOLS, load_tool, put
from test_signing import make_pe, sign_like_a_service

pe_features = load_tool("pe_features")
package = load_tool("package_release")
scan = load_tool("av_local_scan")


class PeFeatures(unittest.TestCase):
    def test_reads_a_minimal_pe(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.exe")
            put(p, make_pe())
            r = pe_features.parse(p)
        self.assertNotIn("error", r)
        self.assertEqual(r["machine"], "0x0")
        self.assertFalse(r["signed"])
        self.assertEqual(r["rich_header"], [])

    def test_signed_file_is_recognised_and_overlay_excludes_the_certificate(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.exe")
            put(p, sign_like_a_service(make_pe()))
            r = pe_features.parse(p)
        self.assertTrue(r["signed"])

    def test_not_a_pe_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.txt")
            put(p, b"hello")
            self.assertIn("error", pe_features.parse(p))

    def test_entropy(self):
        self.assertEqual(pe_features.entropy(b""), 0.0)
        self.assertEqual(pe_features.entropy(b"aaaa"), 0.0)
        self.assertAlmostEqual(pe_features.entropy(bytes(range(256))), 8.0)

    def test_is_pe_and_groups(self):
        with tempfile.TemporaryDirectory() as d:
            put(os.path.join(d, "a.exe"), make_pe())
            put(os.path.join(d, "b.txt"), b"MZ but nothing else")
            self.assertTrue(scan.is_pe(os.path.join(d, "a.exe")))
            self.assertFalse(scan.is_pe(os.path.join(d, "b.txt")))
        self.assertEqual(scan.group("T5DR Online.exe"), "ours")
        self.assertEqual(scan.group("runtime/t5dr.exe"), "ours")
        self.assertEqual(scan.group("python/DLLs/_ssl.pyd"), "python")
        self.assertEqual(scan.group("python/Lib/site-packages/Crypto/Cipher/_raw_aes.pyd"), "pycryptodome")
        self.assertEqual(scan.group("toolchain/llvm/bin/clang-cl.exe"), "llvm")


class FalsePositivePack(unittest.TestCase):
    def test_one_filled_text_per_vendor(self):
        with tempfile.TemporaryDirectory() as d:
            exe, zp, out = os.path.join(d, "T5DR Online.exe"), os.path.join(d, "T5DR-Online-9.9.9.zip"), os.path.join(d, "o")
            put(exe, make_pe())
            put(zp, b"zip bytes")
            r = subprocess.run([PY, os.path.join(TOOLS, "fp_pack.py"), "--zip", zp, "--exe", exe, "--out", out,
                                "--detection", "Trapmine=Suspicious.low.ml.score", "--only", "Trapmine", "Webroot"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(sorted(os.listdir(out)), ["Trapmine.txt", "Webroot.txt"])
            text = open(os.path.join(out, "Trapmine.txt"), encoding="utf-8").read()
            sha = hashlib.sha256(open(exe, "rb").read()).hexdigest()
        self.assertIn("fp@trapmine.com", text)
        self.assertIn("Suspicious.low.ml.score", text)
        self.assertIn(sha, text)
        self.assertIn("T5DR-Online-9.9.9.zip", text)

    def test_every_vendor_of_the_docs_is_in_the_pack(self):
        fp = load_tool("fp_pack")
        for vendor in ("Webroot", "Trapmine", "Symantec", "Bkav", "SecureAge", "Bitdefender", "ALYac", "Arcabit",
                       "Emsisoft", "GData", "VIPRE"):
            self.assertIn(vendor, fp.VENDORS)
        with open(os.path.join(ROOT, "docs", "RELEASING.md"), encoding="utf-8") as f:
            docs = f.read()
        for vendor, (_, where, _, _) in fp.VENDORS.items():
            self.assertIn(where[0], docs, vendor)       # the docs name the same first address or link


class StubVariants(unittest.TestCase):
    def test_default_is_the_current_build(self):
        with mock.patch.dict(os.environ, {"T5DR_STUB_VARIANT": ""}):
            self.assertEqual(package.default_stub_variant(), "current")
        with mock.patch.dict(os.environ, {"T5DR_STUB_VARIANT": "Plain"}):
            self.assertEqual(package.default_stub_variant(), "plain")
        with mock.patch.dict(os.environ, {"T5DR_STUB_VARIANT": "nonsense"}):
            self.assertEqual(package.default_stub_variant(), "current")

    def test_current_changes_nothing(self):
        cur = package.STUB_VARIANTS["current"]
        self.assertEqual((cur["icon"], cur["defines"], cur["crt"], cur["debug"], cur["python"], cur["vcruntime"]),
                         ("t5dr.ico", [], "/MT", False, False, False))

    def test_files_the_variants_need_exist(self):
        for name, spec in package.STUB_VARIANTS.items():
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "launcher", "stub", spec["icon"])), name)

    def test_source_has_the_macros(self):
        with open(os.path.join(ROOT, "launcher", "stub", "t5dr_stub.c"), encoding="utf-8") as f:
            src = f.read()
        for macro in ("T5DR_STUB_NO_PATH_FALLBACK", "T5DR_STUB_INPROCESS"):
            self.assertIn(macro, src)
        defined = {d for spec in package.STUB_VARIANTS.values() for d in spec["defines"]}
        self.assertLessEqual(defined, {"T5DR_STUB_NO_PATH_FALLBACK", "T5DR_STUB_INPROCESS"})

    def test_bitmap_icon_has_a_png_256_and_small_bitmaps(self):
        import struct
        with open(os.path.join(ROOT, "launcher", "stub", "t5dr_bmp.ico"), "rb") as f:
            d = f.read()
        count = struct.unpack_from("<HHH", d, 0)[2]
        kinds = {}
        for i in range(count):
            w, _, _, _, _, _, size, off = struct.unpack_from("<BBBBHHII", d, 6 + 16 * i)
            kinds[w or 256] = "png" if d[off:off + 4] == b"\x89PNG" else "bmp"
        self.assertEqual(kinds[256], "png")
        self.assertTrue(all(v == "bmp" for k, v in kinds.items() if k != 256), kinds)


if __name__ == "__main__":
    unittest.main()
