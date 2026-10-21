"""Lifted code with register promotion (ps3recomp patch 0066, docs/RENDER_PERF.md "Lifted code: register
promotion", branch lifter-regpromo). No game needed.

* The patch changes the lifter's tools only (ppu_lifter.py, its tests, the differential harness): the runtime is
  untouched, and the lifted code computes exactly what it did (proof in the docs).
* Register promotion is the lifter's default; `--regpromo off` lifts the old way, and tools/build_game.py takes
  T5DR_LIFT_REGPROMO=0 (recorded in the lift's stamp, so switching lifts again).
* With a patched ps3recomp tree (PS3RECOMP_DIR or deps/ps3recomp): the pass's own shape tests
  (tools/test_ppu_regpromo.py --shapes-only), and the real lifter on a raw image of small copy loops, with and
  without the pass.
"""
import importlib.util
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0066-lifter-regpromo.patch")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0066 in this checkout")
        self.patch = text("patches", "ps3recomp", "0066-lifter-regpromo.patch")

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0066-lifter-regpromo.patch"), names.index("0064-spu-perf.patch"))

    def test_lifter_tools_only(self):
        files = sorted(set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M)))
        self.assertEqual(files, ["tools/ppu_lifter.py", "tools/regpromo_diff.py", "tools/test_ppu_lift.py",
                                 "tools/test_ppu_regpromo.py"])

    def test_on_by_default_with_a_switch(self):
        self.assertIn("+REGPROMO_DEFAULT = True", self.patch)
        self.assertIn('+    parser.add_argument("--regpromo", choices=("on", "off")', self.patch)

    def test_no_lifted_game_code(self):
        # the release scan (tools/package_release.py) flags >= 100 func_XXXXXXXX names in one file
        self.assertLess(len(re.findall(r"func_[0-9A-Fa-f]{8}", self.patch)), 100)

    def test_build_game_switch(self):
        bg = text("tools", "build_game.py")
        self.assertIn('os.environ.get("T5DR_LIFT_REGPROMO", "1") != "0"', bg)
        self.assertIn('":regpromo=off"', bg)          # in the lift stamp: switching lifts again
        self.assertIn('["--regpromo", "off"]', bg)
        self.assertRegex(bg, r"CODE_VERSION = 6\b")


def find_tree():
    for c in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        p = os.path.join(c or "", "tools", "ppu_lifter.py")
        if c and os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                if "def _regpromo(" in f.read():
                    return c
    return None


class Lifter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = find_tree()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0066 (PS3RECOMP_DIR)")
        cls.tools = os.path.join(cls.tree, "tools")

    def test_shapes(self):
        r = subprocess.run([sys.executable, os.path.join(self.tools, "test_ppu_regpromo.py"), "--shapes-only"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr[-2000:])
        self.assertIn("all checks passed", r.stdout)

    def test_copy_loops(self):
        # 40 copies of a 16-byte copy loop (the shape of the draw packet writers):
        #   li r5,16; mtctr r5; L: lbz r11,0(r4); stb r11,0(r3); addi r3,r3,1; addi r4,r4,1; bdnz L; li r3,0; blr
        words = [0x38A00010, 0x7CA903A6, 0x89640000, 0x99630000, 0x38630001, 0x38840001, 0x4200FFF0,
                 0x38600000, 0x4E800020]
        n, base, size = 40, 0x10000, 4 * len(words)
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "image.bin"), "wb") as f:
                f.write(b"".join(struct.pack(">%dI" % len(words), *words) for _ in range(n)))
            with open(os.path.join(d, "functions.json"), "w") as f:
                f.write("[" + ",".join(f'{{"start": "{base + size * i:#x}", "end": "{base + size * (i + 1):#x}"}}'
                                       for i in range(n)) + "]")
            out = {}
            for name, args in (("default", []), ("off", ["--regpromo", "off"])):
                o = os.path.join(d, name)
                r = subprocess.run([sys.executable, os.path.join(self.tools, "ppu_lifter.py"),
                                    os.path.join(d, "image.bin"), "--raw", "--base", hex(base),
                                    "--functions", os.path.join(d, "functions.json"), "--jobs", "1", "-o", o] + args,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   env=dict(os.environ, PYTHONUTF8="1"), timeout=300)
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
                src = ""
                for fn in sorted(os.listdir(o)):
                    if fn.endswith((".c", ".cpp")):
                        with open(os.path.join(o, fn), encoding="utf-8") as f:
                            src += f.read()
                out[name] = (src, r.stdout)
        on, log = out["default"]
        off = out["off"][0]
        self.assertIn("register promotion: on", log)
        self.assertIn(f"register promotion: {n} functions promoted", log)
        self.assertNotIn("_pr_", off)
        fn = re.search(r"void func_00010000\(ppu_context\* ctx\) \{\n(.*?)\n\}", on, re.S).group(1)
        loop = fn[fn.index("loc_00010008:"):fn.index("goto loc_00010008;")]
        self.assertNotIn("ctx->", loop)                      # the loop runs in locals only
        self.assertIn("--_pr_ctr", fn)
        self.assertIn("ctx->gpr[3] = _pr_g3;", fn)           # written back at the return
        # the same function without the pass keeps every register in the context
        fo = re.search(r"void func_00010000\(ppu_context\* ctx\) \{\n(.*?)\n\}", off, re.S).group(1)
        self.assertIn("--ctx->ctr", fo)


if __name__ == "__main__":
    unittest.main()
