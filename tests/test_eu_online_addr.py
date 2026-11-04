"""1.2.1: the EU Online address table (src/platform/t5_addr.h, t5_addr_eu_online.inc; docs/EU.md "EU Online").

* The table is sorted, its spans do not overlap, every region has a length.
* Every US address src/ hands to T5A() / T5R() / T5REG() has a span (or a region) for the EU Online program: a missing
  one would stop the game with a FATAL line the first time it is asked for.
* The modules that run for EU Online use no game address outside T5A(): a bare US address in them would touch some
  other variable of the EU program (the developer tracers that are US-only say so with t5game::us_only()).
* tests/c/eu_addr_test.cpp: the lookup itself (identity for the US program, spans, regions, the abort)."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars

LLVM = r"C:\Program Files\LLVM"
INC = os.path.join(ROOT, "src", "platform", "t5_addr_eu_online.inc")
STRIP = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
# modules that know only the US program (t5game::us_only) or hold no game address
US_ONLY = {"rb_ktrace.cpp", "rb_shadowtrace.cpp", "rb_test.cpp", "rb_measure.cpp", "rb_wft.cpp", "rb_rft.cpp",
           "rb_trace.cpp", "rb_sample.cpp"}
# constants in game-address ranges that are no addresses (lengths, masks, bounds of the data segment)
NOT_ADDRESSES = {0x10000, 0x10094, 0x10098, 0x1009C, 0x11000, 0x17000, 0x20000, 0x218C0, 0x30000, 0x58000, 0x6E000,
                 0xF0000, 0x100000, 0x10FFFF, 0x19660D, 0x340000, 0x400000, 0x710000, 0x770000, 0x800000,
                 0x447690, 0x457898, 0x356980, 0x10000000, 0x10050000, 0x10760000}


def table():
    spans, regions = [], []
    text = open(INC, encoding="utf-8").read()
    body, _, rest = text.partition("kEuOnlineRegions")
    for m in re.finditer(r"\{ 0x([0-9A-F]+)u, 0x([0-9A-F]+)u, 0x([0-9A-F]+)u \}", body):
        spans.append(tuple(int(x, 16) for x in m.groups()))
    for m in re.finditer(r"\{ 0x([0-9A-F]+)u, 0x([0-9A-F]+)u, 0x([0-9A-F]+)u, 0x([0-9A-F]+)u \}", rest):
        regions.append(tuple(int(x, 16) for x in m.groups()))
    return spans, regions


def sources():
    for dp, _, fns in os.walk(os.path.join(ROOT, "src")):
        for n in fns:
            if n.endswith((".cpp", ".h", ".c")):
                p = os.path.join(dp, n)
                yield n, STRIP.sub("", open(p, encoding="utf-8").read())


class Table(unittest.TestCase):
    def test_sorted_without_overlap(self):
        spans, regions = table()
        self.assertGreater(len(spans), 100)
        self.assertGreater(len(regions), 0)
        for (a, n, e), (b, m, f) in zip(spans, spans[1:]):
            self.assertLess(a, b)
            self.assertLessEqual(a + n, b, "spans 0x%08X and 0x%08X overlap" % (a, b))
        for a, n, e in spans:
            self.assertGreater(n, 0)
            self.assertLess(a + n, 1 << 32)
        for us, ul, eu, el in regions:
            self.assertTrue(ul and el)

    def test_every_address_src_uses_has_an_eu_online_counterpart(self):
        spans, regions = table()
        starts = [s[0] for s in spans]
        import bisect

        def covered(a, n):
            i = bisect.bisect_right(starts, a) - 1
            return i >= 0 and a + n <= spans[i][0] + spans[i][1]
        missing, uses = [], 0
        for name, code in sources():
            for m in re.finditer(r"T5A\(\s*(0x[0-9A-Fa-f]+)[uUlL]*(?:\s*([+-])\s*(0x[0-9A-Fa-f]+)[uUlL]*)?\s*\)", code):
                a = int(m.group(1), 16)
                if m.group(2):
                    a = a + int(m.group(3), 16) if m.group(2) == "+" else a - int(m.group(3), 16)
                uses += 1
                if not covered(a, 1):
                    missing.append("%s: T5A(0x%08X)" % (name, a))
            for m in re.finditer(r"(?:T5(R|REG)|t5game::(region))\(\s*(0x[0-9A-Fa-f]+)[uUlL]*\s*,\s*(0x[0-9A-Fa-f]+|\d+)"
                                 r"[uUlL]*\s*\)", code):
                kind = m.group(1) or "REG"
                a, n = int(m.group(3), 16), int(m.group(4), 0)
                uses += 1
                if kind == "REG" and any(r[0] == a and r[1] == n for r in regions):
                    continue
                if not covered(a, n):
                    missing.append("%s: T5%s(0x%08X, 0x%X)" % (name, kind, a, n))
        self.assertGreater(uses, 200)
        self.assertEqual(missing, [])

    def test_no_bare_game_address_in_the_modules_that_run_for_eu_online(self):
        bad = []
        for name, code in sources():
            if name in US_ONLY or name in ("t5_addr.h", "t5_addr_eu_online.inc", "t5_game.h"):
                continue
            code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
            code = re.sub(r"(?:T5(?:A|R|REG|_US)|t5game::region)\(\s*0x[0-9A-Fa-f]+[uUlL]*", "T5A(", code)
            for m in re.finditer(r"\b0x([0-9A-Fa-f]{5,8})[uUlL]*\b", code):
                v = int(m.group(1), 16)
                if v in NOT_ADDRESSES:
                    continue
                if 0x10000 <= v < 0x500000 or 0x10000000 <= v < 0x10770000:
                    bad.append("%s: 0x%X" % (name, v))
        self.assertEqual(bad, [])

    def test_the_us_only_modules_say_so(self):
        for rel in ("src/rollback/rb_ktrace.cpp", "src/rollback/rb_shadowtrace.cpp"):
            self.assertIn("t5game::us_only(", open(os.path.join(ROOT, rel), encoding="utf-8").read(), rel)
        src = open(os.path.join(ROOT, "src", "rollback", "rb_hooks.cpp"), encoding="utf-8").read()
        self.assertIn('us_only("rollback test/measure modes")', src)


class Lookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with clang-cl")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (os.path.join(LLVM, "bin", "clang-cl.exe")
                                             if os.path.isfile(os.path.join(LLVM, "bin", "clang-cl.exe")) else None)
        if not vcvars or not clang:
            raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "eu_addr_test.exe")
        src = os.path.join(ROOT, "tests", "c", "eu_addr_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W3 /D_CRT_SECURE_NO_WARNINGS '
               f'"{src}" /Fe:"{exe}" /Fo:"{os.path.join(cls.tmp.name, "eu_addr_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=900)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/eu_addr_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_lookup(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$")

    def test_eu_online_program_and_a_missing_address(self):
        subprocess.run([self.exe], capture_output=True, timeout=120, cwd=self.tmp.name)    # writes the stand-ins
        r = subprocess.run([self.exe, "eu_online.elf"], capture_output=True, text=True, timeout=60, cwd=self.tmp.name)
        self.assertIn("game 3 eu 0x00481130 hooks on", r.stdout)                # the TOC, from the table
        self.assertIn("addresses from src/platform/t5_addr.h", r.stderr)
        r = subprocess.run([self.exe, "eu_online.elf", "missing"], capture_output=True, text=True, timeout=60,
                           cwd=self.tmp.name)
        self.assertNotEqual(r.returncode, 0)                                     # stops: never the US address
        self.assertIn("FATAL: no NPEA00019 v02.00/v02.01 Online (EU) address for the US address 0x00000004",
                      r.stderr)
        self.assertNotIn("reached", r.stdout)
        r = subprocess.run([self.exe, "us.elf"], capture_output=True, text=True, timeout=60, cwd=self.tmp.name)
        self.assertIn("game 1 eu 0x00470540 hooks on", r.stdout)                 # the US program: the US address
        self.assertEqual(r.stderr, "")


if __name__ == "__main__":
    unittest.main()
