"""Patch 0126 (branch t5-perf-019): a check of the texture units patch 0081's tier-1 path binds.

* tests/c/fp_tex_mask_test.c: the texture units a fragment program samples (rsx_fp_texture_mask), against
  the HLSL the decompiler makes of it (30,000 random programs), and two narrowed analyses it must catch.
* The runtime: RSX_FP_TEX_MASK_CHECK=1 checks every program in game; the path's default is unchanged (tier 1 only).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0126-tier1-mask-check.patch")


def added():
    with open(PATCH, encoding="utf-8") as f:
        return "\n".join(l[1:] for l in f.read().splitlines() if l.startswith("+") and not l.startswith("+++"))


def find_tree():
    """A ps3recomp tree with patch 0126 (PS3RECOMP_DIR, else deps/ps3recomp)."""
    for d in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        f = d and os.path.join(d, "libs", "video", "rsx_live_draw.c")
        if f and os.path.isfile(f):
            with open(f, encoding="utf-8", errors="replace") as fh:
                if "RSX_FP_TEX_MASK_CHECK" in fh.read():
                    return d
    return None


class TexMask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows C compiler")
        cls.tree = find_tree()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0126 (PS3RECOMP_DIR)")
        sys.path.insert(0, os.path.dirname(__file__))
        from test_xlat_cpu import find_vcvars
        vcvars = find_vcvars()
        llvm = os.path.join("C:" + os.sep, "Program Files", "LLVM", "bin", "clang-cl.exe")
        clang = shutil.which("clang-cl") or (llvm if os.path.isfile(llvm) else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "fp_tex_mask_test.exe")
        inc = [os.path.join(cls.tree, *p) for p in (("libs", "video"), ("libs",), ("runtime",), ("include",))]
        src = os.path.join(ROOT, "tests", "c", "fp_tex_mask_test.c")
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 {flags} "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "fp_tex_mask_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/fp_tex_mask_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_mask_covers_every_sample(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=300, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$")
        for m in re.finditer(r"differs (\d+) caught (\d+)", r.stdout):
            self.assertGreater(int(m.group(2)), 0, r.stdout)


class Runtime(unittest.TestCase):
    def test_check_only(self):
        p = added()
        self.assertNotIn("g_ld_t1 =", p)          # the tier-1 path's default is not changed
        self.assertIn('getenv("RSX_FP_TEX_MASK_CHECK")', p)
        self.assertIn("if (fi > 0) ld_fp_tex_mask_check(fp_uc, fp_size, ps_hlsl);", p)


if __name__ == "__main__":
    unittest.main()
