"""Source mirror guards for patch 0104; numeric proof is tests/c/vmx_soft2_test.c.
No game or external runtime is required for these guards. Native tests must be
built/run by the maintainer separately; neither source inspection nor default-off
status establishes bit identity or a speedup.
"""
from pathlib import Path
import ast
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "ps3recomp" / "0104-low-end.patch"


class ExperimentalVmx(unittest.TestCase):
    def setUp(self):
        self.patch = PATCH.read_text(encoding="utf-8")
        self.added = "\n".join(line[1:] for line in self.patch.splitlines()
                               if line.startswith("+") and not line.startswith("+++"))

    def test_default_off_and_baseline_only(self):
        self.assertIn("#define PPU_VMX_SOFT2 0", self.added)
        self.assertEqual(self.added.count("#if PPU_VMX_SOFT2 && defined(PPU_FP_X64) && !defined(__FMA__)"), 2)
        self.assertIn("finite && (_mm_getcsr() & PPU_MXCSR_CTRL) == PPU_MXCSR_CANON", self.added)

    def test_preserves_old_scalar_fallback_and_guest_semantics(self):
        self.assertIn("ppu_fmaf_det(x, z, y)", self.patch)
        self.assertIn("vmx_flush(vmx_fix(vmx_u(out4[i])), vscr)", self.added)
        self.assertIn("ppu_fmaf_soft2_finite(out4, x4, z4, y4)", self.added)
        self.assertIn("_mm_mul_pd(dx, dy)", self.added)
        self.assertIn("if (!(u & 1))", self.added)
        files = re.findall(r"^diff --git a/(\S+)", self.patch, re.M)
        self.assertEqual(files, ["runtime/ppu/ppu_fp_det.h", "runtime/ppu/ppu_vmx.h"])
        for unsafe in ("vm_write", "guest_write", "_mm_fmadd", "_mm_rcp", "_mm_rsqrt"):
            self.assertNotIn(unsafe, self.added)

    def test_hunks_have_correct_counts(self):
        chunks = re.split(r"(?m)^@@ ", self.patch)[1:]
        for chunk in chunks:
            head, body = chunk.split("\n", 1)
            match = re.match(r"-\d+,(\d+) \+\d+,(\d+) @@", head)
            self.assertIsNotNone(match, head)
            lines = body.split("\ndiff --git", 1)[0].splitlines()
            self.assertEqual(sum(line.startswith((" ", "-")) for line in lines), int(match[1]))
            self.assertEqual(sum(line.startswith((" ", "+")) for line in lines), int(match[2]))

    def test_numeric_harness_exercises_actual_new_helper(self):
        harness = (ROOT / "tests" / "c" / "vmx_soft2_test.c").read_text(encoding="utf-8")
        self.assertIn("#ifndef PPU_VMX_SOFT2_IMPLEMENTED", harness)
        self.assertIn("ppu_fmaf_soft2_finite(out, fx, fy, fz)", harness)
        self.assertIn("vmx_vmaddfp(dst, aa, bb, cc, vscr)", harness)
        self.assertIn("alias < 4", harness)
        self.assertIn("nj < 2", harness)
        self.assertIn("0x7f800001u", harness)
        self.assertIn("0x3f800002u", harness)

    def test_native_runner_requires_the_opt_in_numeric_comparison(self):
        tree = ast.parse((ROOT / "tests" / "run_ps3recomp_tests.py").read_text(encoding="utf-8"))
        declaration = next(node for node in tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "TESTS"
                                   for target in node.targets))
        entry = next(node for node in declaration.value.elts
                     if isinstance(node, ast.Tuple) and ast.literal_eval(node.elts[0]) == "vmx_soft2")
        self.assertEqual(ast.literal_eval(entry.elts[1]), ["@c/vmx_soft2_test.c"])
        self.assertIn("/DPPU_VMX_SOFT2=1", ast.literal_eval(entry.elts[3]))
        self.assertIn("/clang:-ffp-contract=off", ast.literal_eval(entry.elts[3]))


if __name__ == "__main__":
    unittest.main()
