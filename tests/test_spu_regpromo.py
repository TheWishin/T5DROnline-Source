"""1.2.1: SPU register promotion in the SPU lifter (ps3recomp patch 0113: tools/spu_regpromo.py, spu_lifter.py
--regpromo; docs/RENDER_PERF.md "SPU registers in host registers"). No game needed.

* The patch: the lifter's option (default on, --regpromo off = the old output), spu_helpers.h's known-clean forms
  (spu_fa_k ...) and their plain fallback, build_game.py's SPU stamp names the lifter (a new lifter lifts the sound
  core and the jobs again).
* promote() on lifted-style lines: locals loaded at entry, written back at every exit and barrier, barrier lines
  unchanged on ctx->gpr with a reload after them, known-clean marks only on near-float results of the same
  straight line, unknown shapes are barriers.
* With a ps3recomp tree (PS3RECOMP_DIR or deps/ps3recomp, patch 0113 applied) and clang-cl: tools/spu_regpromo_diff.py
  runs synthetic lifted functions as written and promoted on random inputs (0 differences; a dropped write-back is
  caught), and tests/c/spu_clean_float_test.c shows the near-float results are never denormal or -0.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0113-spu-regpromo.patch")


def find_tree():
    for c in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        if c and os.path.isfile(os.path.join(c, "tools", "spu_regpromo.py")):
            return c
    return None


def clang():
    c = shutil.which("clang-cl")
    if not c and os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe"):
        c = r"C:\Program Files\LLVM\bin\clang-cl.exe"
    return c


def regpromo_module():
    """spu_regpromo.py from the tree, or from the patch text when no tree is there."""
    tree = find_tree()
    if tree:
        sys.path.insert(0, os.path.join(tree, "tools"))
        import spu_regpromo
        return spu_regpromo
    with open(PATCH, encoding="utf-8") as f:
        patch = f.read()
    part = patch[patch.index("+++ b/tools/spu_regpromo.py"):]
    part = part[part.index("\n@@"):]
    end = part.find("\ndiff --git")
    lines = [ln[1:] for ln in (part if end < 0 else part[:end]).splitlines()[2:] if ln.startswith("+")]
    mod = type(sys)("spu_regpromo")
    exec(compile("\n".join(lines) + "\n", "spu_regpromo.py", "exec"), mod.__dict__)
    return mod


# lifted-style functions (the shapes spu_lifter.py writes), with a loop, an exit behind an if, a call barrier
SAMPLE = {
    "loop": [
        "loc_00000100:",
        "ctx->gpr[5] = spu_ai(ctx->gpr[5], 1);",
        "ctx->gpr[2] = spu_ls_read128(ctx, ctx->gpr[3]._u32[0] + 0x0);",
        "ctx->gpr[4] = spu_fa(ctx->gpr[2], ctx->gpr[6]);",
        "ctx->gpr[7] = spu_fma(ctx->gpr[4], ctx->gpr[8], ctx->gpr[4]);",
        "ctx->gpr[9] = spu_shufb(ctx->gpr[7], ctx->gpr[7], ctx->gpr[10]);",
        "ctx->gpr[11] = spu_fm(ctx->gpr[9], ctx->gpr[7]);",
        "spu_ls_write128(ctx, ctx->gpr[12]._u32[0] + 0x10, ctx->gpr[11]);",
        "ctx->gpr[3] = spu_ai(ctx->gpr[3], 16);",
        "ctx->gpr[13] = spu_ceq(ctx->gpr[5], ctx->gpr[14]);",
        "if (ctx->gpr[13]._u32[0] == 0) goto loc_00000100;",
        "{ ctx->pc = 0x140; g_spu_trampoline_fn = t_spu_func_00000140; return; }",
    ],
    "call": [
        "ctx->gpr[3] = spu_ori(ctx->gpr[80], 0);",
        "ctx->gpr[4] = spu_fs(ctx->gpr[3], ctx->gpr[5]);",
        "ctx->gpr[6] = spu_fa(ctx->gpr[4], ctx->gpr[4]);",
        "ctx->gpr[7] = spu_ai(ctx->gpr[6], 3);",
        "ctx->gpr[8] = spu_il(7);",
        "ctx->gpr[9] = spu_fm(ctx->gpr[6], ctx->gpr[8]);",
        "if (ctx->gpr[7]._u32[0] != 0) { ctx->pc = 0x230; g_spu_trampoline_fn = t_spu_func_00000230; return; }",
        "ctx->gpr[0] = spu_link(0x220); { int32_t _si = (int32_t)ctx->image_id; ctx->host_depth++; "
        "t_spu_func_00000300(ctx); spu_drain_call(ctx, 0x220); ctx->host_depth--; spu_img_restore(ctx, _si); }",
        "ctx->gpr[10] = spu_fa(ctx->gpr[3], ctx->gpr[9]);",
        "ctx->gpr[11] = spu_fma(ctx->gpr[10], ctx->gpr[10], ctx->gpr[6]);",
        "spu_ls_write128(ctx, 0x3FF0, ctx->gpr[11]);",
        "ctx->gpr[12] = spu_a(ctx->gpr[11], ctx->gpr[3]);",
        "spu_ls_write128(ctx, 0x3FE0, ctx->gpr[12]);",
        "ctx->gpr[13] = spu_selb(ctx->gpr[12], ctx->gpr[11], ctx->gpr[10]);",
        "spu_ls_write128(ctx, 0x3FD0, ctx->gpr[13]);",
        "ctx->gpr[14] = spu_xor(ctx->gpr[13], ctx->gpr[12]);",
        "spu_ls_write128(ctx, 0x3FC0, ctx->gpr[14]);",
        "ctx->gpr[15] = spu_or(ctx->gpr[14], ctx->gpr[3]);",
        "SPU_RET(ctx);",
    ],
}


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0113 in this checkout")
        with open(PATCH, encoding="utf-8") as f:
            self.patch = f.read()

    def test_files(self):
        self.assertEqual(sorted(set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M))),
                         ["runtime/spu/spu_helpers.h", "tools/spu_lifter.py", "tools/spu_regpromo.py"])

    def test_option_and_fallback(self):
        self.assertIn('p.add_argument("--regpromo", choices=("on", "off"), default="on"', self.patch)
        self.assertIn("+#ifndef spu_fa_k", self.patch)           # the plain forms in every other float mode
        self.assertIn("+#define spu_fma_k(a, b, c, ka, kb, kc)  spu_fma(a, b, c)", self.patch)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0113-spu-regpromo.patch"), names.index("0112-always-left-copy-any-unit.patch"))

    def test_build_game_relifts_on_a_new_lifter(self):
        with open(os.path.join(ROOT, "tools", "build_game.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"spu_lifter.py", "spu_regpromo.py"', src)
        self.assertIn("lifter_new = os.path.exists(stamp) and stamp_lifter(stamp) != spu_lifter_id()", src)
        self.assertIn('(["--relift"] if a.force or lifter_new else [])', src)


class Promote(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rp = regpromo_module()

    def test_loop(self):
        out = self.rp.promote(SAMPLE["loop"])
        self.assertIsNotNone(out)
        self.assertTrue(out[0].startswith("u128 s2 = ctx->gpr[2], s3 = ctx->gpr[3]"))
        body = "\n".join(out[1:])
        self.assertNotIn("ctx->gpr[5] = spu_ai", body)           # the loop works on locals
        self.assertIn("s4 = spu_fa_k(s2, s6, 0, 0);", body)       # loaded / unknown: flushed
        self.assertIn("s7 = spu_fma_k(s4, s8, s4, 1, 0, 1);", body)
        self.assertIn("s11 = spu_fm_k(s9, s7, 0, 1);", body)       # shufb result: not known-clean
        exit_line = [x for x in out if "g_spu_trampoline_fn" in x][0]
        self.assertTrue(exit_line.startswith("{ ctx->gpr[2] = s2;"), exit_line)
        self.assertNotIn("ctx->gpr[6] = s6", exit_line)           # only read: never written back

    def test_barrier(self):
        out = self.rp.promote(SAMPLE["call"])
        self.assertIsNotNone(out)
        i = next(k for k, x in enumerate(out) if "spu_drain_call" in x)
        self.assertIn("ctx->gpr[0] = spu_link(0x220)", out[i])     # the barrier line as lifted
        self.assertTrue(out[i - 1].startswith("{ ctx->gpr["))        # written registers back before it
        self.assertIn(" s3 = ctx->gpr[3];", out[i + 1])                # every local again after it
        self.assertIn("s10 = spu_fa_k(s3, s9, 0, 0);", out)           # nothing known-clean across a call
        ret = [x for x in out if "SPU_RET(ctx);" in x][0]
        self.assertTrue(ret.startswith("{ ctx->gpr["), ret)

    def test_unknown_shape_keeps_ctx(self):
        body = ["ctx->gpr[3] = spu_ai(ctx->gpr[3], 1);"] * 8 + ["frobnicate(ctx, 3);"]
        out = self.rp.promote(body)
        k = out.index("frobnicate(ctx, 3);")
        self.assertIn("ctx->gpr[3] = s3;", out[k - 1])
        self.assertIn("s3 = ctx->gpr[3];", out[k + 1])

    def test_too_many_barriers_stays_as_is(self):
        body = ["ctx->gpr[3] = spu_ai(ctx->gpr[3], 1);", "spu_wrch(ctx, MFC_Cmd, ctx->gpr[3]);"] * 3
        self.assertIsNone(self.rp.promote(body))


class Differential(unittest.TestCase):
    """The promoted functions against the lifted ones in tools/spu_regpromo_diff.py's harness."""

    @classmethod
    def setUpClass(cls):
        cls.tree = find_tree()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0113 (PS3RECOMP_DIR)")
        if os.name != "nt" or not clang():
            raise unittest.SkipTest("Windows + clang-cl test")
        sys.path.insert(0, os.path.join(cls.tree, "tools"))
        import spu_regpromo
        cls.rp = spu_regpromo

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name
        self.addCleanup(self._td.cleanup)

    def lift_files(self, mutate=None):
        old, new = [], []
        names = {"loop": 0x100, "call": 0x200}
        for key, body in SAMPLE.items():
            name = "t_spu_func_%08X" % names[key]
            p = self.rp.promote(body)
            if mutate:
                p = mutate(p)
            old.append(f"void {name}(spu_context* ctx) {{\n" + "".join(f"    {b}\n" for b in body) + "}\n")
            new.append(f"void {name}(spu_context* ctx) {{\n" + "".join(
                b + "\n" if b.endswith(":") else f"    {b}\n" for b in p) + "}\n")
        extra = "".join(f"void t_spu_func_{a:08X}(spu_context* ctx) {{\n    ctx->pc = 0x{a:X}u;\n}}\n"
                        for a in (0x140, 0x230, 0x300))
        paths = []
        for tag, funcs in (("old", old), ("new", new)):
            p = os.path.join(self.tmp, tag + ".c")
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(funcs) + extra)
            paths.append(p)
        return paths

    def run_diff(self, paths, *defs):
        cmd = [sys.executable, os.path.join(ROOT, "tools", "spu_regpromo_diff.py"), "--old", paths[0], "--new", paths[1],
               "--ps3recomp", self.tree, "--cases", "400", "--clang", clang()]
        for d in defs:
            cmd += ["--define", d]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=900)

    def test_same_results(self):
        for defs in ((), ("SPU_NEAR_FLOAT",)):
            r = self.run_diff(self.lift_files(), *defs)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"2 function\(s\), \d+ case\(s\) compared, \d+ stopped at the step limit, "
                                       r"0 differ")

    def test_a_dropped_write_back_is_caught(self):
        def drop(lines):
            return [x.replace("ctx->gpr[11] = s11; ", "", 1) if "g_spu_trampoline_fn" in x else x for x in lines]
        r = self.run_diff(self.lift_files(drop), "SPU_NEAR_FLOAT")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("DIFFER t_spu_func_00000100", r.stdout)

    def test_near_float_results_are_clean(self):
        exe = os.path.join(self.tmp, "clean.exe")
        spu = os.path.join(self.tree, "runtime", "spu")
        r = subprocess.run([clang(), "/nologo", "/O2", "/W0", "-msse4.1", "/clang:-ffp-contract=off", "/DSPU_NEAR_FLOAT",
                            "/DSPU_LS_NO_HOOKS", "/I", spu, "/I", os.path.join(self.tree, "runtime"), "/I",
                            os.path.join(self.tree, "include"), os.path.join(ROOT, "tests", "c", "spu_clean_float_test.c"),
                            "/Fe:" + exe, "/Fo:" + os.path.join(self.tmp, "clean.obj")],
                           capture_output=True, text=True, timeout=600, cwd=self.tmp)
        if not os.path.isfile(exe):
            self.skipTest("spu_clean_float_test did not build: " + (r.stdout + r.stderr)[-400:])
        r = subprocess.run([exe, "3000000"], capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 unclean lanes", r.stdout)


if __name__ == "__main__":
    unittest.main()
