"""Probe sse2-probe-018: an x86-64 build without SSE4.1 (docs/SSE2_BASELINE.md; ps3recomp patch 0126). No game needed.

* The switches: CMake T5DR_X86_BASELINE (runtime and lifted SPU code without -msse4.1, lifted PPU code for the x86-64
  baseline, no SSE4.1 start-up check), tools/build_game.py T5DR_X86_BASELINE=1, tools/build_game_dll.py --simd sse2.
* The patch: spu_helpers.h gets SSE2 forms of everything its SSE4.1 path used (pshufb, pblendvb, pabsd, pcmpeqq,
  ptest); PS3RECOMP_X86_BASELINE drops -msse4.1.
* tests/c/spu_sse2_cross_test.c, built with and without -msse4.1 in each float mode (exact, SPU_NEAR_FLOAT = the sound
  core, SPU_FAST_FLOAT = the skinning jobs) against a ps3recomp tree with the patch (PS3RECOMP_DIR or deps/ps3recomp):
  the same digests from both builds, the integer forms equal to the scalar loops, and the baseline object holds no
  instruction above SSE2 (tools/isa_audit.py). The old fallback (scalar helpers) gives other float bits for the
  sound core: that is why dropping the flag alone was not enough. Skipped without a tree or clang-cl.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT, load_tool

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0126-sse2-baseline.patch")
ABOVE_SSE2 = re.compile(r"_mm_(shuffle_epi8|blendv_\w+|blend_\w+|abs_ep\w+|cmpeq_epi64|test[czn]\w*|alignr\w+|round_\w+|"
                        r"extract_epi(8|32|64)|insert_epi(8|32|64)|mullo_epi32|min_ep[iu](8|16|32)|packus_epi32|cvtep[iu]\w+)")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8", errors="replace") as f:
        return f.read()


def find_tree():
    for c in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        h = os.path.join(c, "runtime", "spu", "spu_helpers.h") if c else ""
        if c and os.path.isfile(h):
            with open(h, encoding="utf-8", errors="replace") as f:
                if "SPU_X86_SSE2_ISA" in f.read():
                    return c
    return None


class Switches(unittest.TestCase):
    def test_cmake(self):
        cm = read("CMakeLists.txt")
        self.assertIn('option(T5DR_X86_BASELINE', cm)
        self.assertRegex(cm, r"if\(T5DR_X86_BASELINE\)\s+set\(PS3RECOMP_X86_BASELINE ON CACHE BOOL")
        self.assertRegex(cm, r'if\(T5DR_X86_BASELINE\)\s+set\(_lifted_arch "none"\)')
        self.assertIn("COMPILE_DEFINITIONS T5DR_X86_BASELINE", cm)
        self.assertEqual(read("CMakeLists.txt").count("option(T5DR_X86_BASELINE"), 1)

    def test_default_is_unchanged(self):
        self.assertRegex(read("CMakeLists.txt"), r'option\(T5DR_X86_BASELINE "[^"]+" OFF\)')
        dll = read("tools", "build_game_dll.py")
        self.assertIn('ap.add_argument("--simd", choices=("sse41", "sse2"), default="sse41"', dll)
        self.assertRegex(dll, r'if a\.simd == "sse41":\s+cmd \+= \["-msse4\.1"\]')

    def test_cpu_check_keeps_its_message(self):
        src = read("src", "platform", "cpu_check.cpp")
        self.assertIn("#ifdef T5DR_X86_BASELINE", src)
        self.assertIn("ExitProcess(14)", src)
        self.assertLess(src.index("#ifdef T5DR_X86_BASELINE"), src.index("__cpuid(r, 1)"))

    def test_build_game_env(self):
        bg = read("tools", "build_game.py")
        self.assertIn('"-DT5DR_X86_BASELINE=ON"] if os.environ.get("T5DR_X86_BASELINE") == "1"', bg)


class Patch(unittest.TestCase):
    def setUp(self):
        self.patch = read("patches", "ps3recomp", "0126-sse2-baseline.patch")
        self.added = "\n".join(ln[1:] for ln in self.patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))

    def test_files(self):
        self.assertEqual(sorted(set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M))),
                         ["CMakeLists.txt", "runtime/spu/spu_helpers.h", "runtime/spu/tests/test_spu_float_neon.c",
                          "runtime/spu/tests/test_spu_int_sse.c", "runtime/spu/tests/test_spu_shufb.c"])

    def test_last_in_series(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0126-sse2-baseline.patch"), names.index("0113-old-pcs.patch")
                           if "0113-old-pcs.patch" in names else -1)

    def test_sse2_forms_use_sse2_only(self):
        # every newer intrinsic the patch adds sits behind the SSE4.1 side of an #if (the wrappers' first branch)
        depth_sse41 = False
        for ln in self.added.splitlines():
            s = ln.strip()
            if s.startswith("#if defined(__SSE4_1__)"):
                depth_sse41 = True
            elif s.startswith(("#else", "#elif", "#endif")):
                depth_sse41 = False
            if ABOVE_SSE2.search(ln) and not s.startswith(("/*", "*", "//")):
                self.assertTrue(depth_sse41, ln)

    def test_no_guest_memory_no_env(self):
        for word in ("vm_write", "vm_read", "ctx->", "getenv"):
            self.assertNotIn(word, self.added, word)

    def test_flag_is_optional(self):
        self.assertIn('option(PS3RECOMP_X86_BASELINE', self.added)
        self.assertIn("NOT PS3RECOMP_X86_BASELINE", self.added)


class Bits(unittest.TestCase):
    N = "400000"

    @classmethod
    def setUpClass(cls):
        cls.tree = find_tree()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0126 (PS3RECOMP_DIR)")
        if os.name != "nt":
            raise unittest.SkipTest("Windows test (clang-cl)")
        cls.clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                                 if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not cls.clang:
            raise unittest.SkipTest("no clang-cl")
        cls._td = tempfile.TemporaryDirectory()
        cls.tmp = cls._td.name
        cls.out = {}
        for mode, define in (("exact", []), ("near", ["/DSPU_NEAR_FLOAT"]), ("fast", ["/DSPU_FAST_FLOAT"])):
            for isa, flags in (("sse41", ["-msse4.1"]), ("sse2", [])):
                cls.out[mode, isa] = cls.run_one(f"{mode}_{isa}", define + flags)
        cls.out["near", "scalar"] = cls.run_one("near_scalar", ["/DSPU_NEAR_FLOAT", "/DSPU_SCALAR_HELPERS"])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_td", None):
            cls._td.cleanup()

    @classmethod
    def run_one(cls, name, flags):
        exe = os.path.join(cls.tmp, name + ".exe")
        cmd = [cls.clang, "/nologo", "/O2", "/W0", "/std:c17", "/clang:-ffp-contract=off",
               "/I" + os.path.join(cls.tree, "include"), "/I" + os.path.join(cls.tree, "runtime", "spu")] + flags + \
              [os.path.join(ROOT, "tests", "c", "spu_sse2_cross_test.c"), "/Fe:" + exe,
               "/Fo:" + os.path.join(cls.tmp, name + ".obj")]
        b = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if b.returncode:
            raise AssertionError(f"{name} did not build:\n{(b.stdout + b.stderr)[-3000:]}")
        r = subprocess.run([exe, cls.N], capture_output=True, text=True, errors="replace", timeout=600)
        head = r.stdout.splitlines()[0] if r.stdout else ""
        return dict(rc=r.returncode, head=head, digests=dict(ln.split()[1:3] for ln in r.stdout.splitlines()
                                                              if ln.startswith("digest ")), text=r.stdout[-2000:])

    def test_each_build_is_what_it_says(self):
        for (mode, isa), o in self.out.items():
            self.assertEqual(o["rc"], 0, o["text"])
            self.assertIn(f"isa {isa} float {mode} ", o["head"])
            self.assertIn("ref-failures 0", o["head"])
            self.assertEqual(len(o["digests"]), 33, o["text"])

    def test_same_bits_with_and_without_sse41(self):
        for mode in ("exact", "near", "fast"):
            a, b = self.out[mode, "sse41"]["digests"], self.out[mode, "sse2"]["digests"]
            self.assertEqual({k for k in a if a[k] != b.get(k)}, set(), mode)

    def test_the_test_sees_a_difference(self):
        # the pre-0126 fallback of a build without SSE4.1: the exact scalar float path, other bits for the sound core
        a, b = self.out["near", "sse41"]["digests"], self.out["near", "scalar"]["digests"]
        diff = {k for k in a if a[k] != b[k]}
        self.assertTrue({"fa", "fs", "fm", "fma", "fms", "fnms"} <= diff, diff)
        self.assertFalse({"shufb", "rotqby", "cwd", "fsmb"} & diff, diff)      # integer forms: the same either way

    def test_baseline_object_has_nothing_above_sse2(self):
        audit = load_tool("isa_audit")
        objdump = os.path.join(os.path.dirname(self.clang), "llvm-objdump.exe")
        if not os.path.isfile(objdump):
            self.skipTest("no llvm-objdump next to clang-cl")
        for name, want in (("near_sse2", False), ("exact_sse2", False), ("fast_sse2", False), ("near_sse41", True)):
            d = subprocess.run([objdump, "-d", "--no-show-raw-insn", os.path.join(self.tmp, name + ".obj")],
                               capture_output=True, text=True, errors="replace").stdout
            # ppu_fma_hw (ppu_fp_det.h, target("fma")) is the one function above SSE2 by design: it runs only when
            # CPUID reports FMA (ppu_fp_cpu_fma), the software fma otherwise
            d = re.sub(r"^[0-9a-f]+ <ppu_fma_hw>:\n(?:.+\n)+", "", d, flags=re.M)
            hits = [m.group(1) for m in re.finditer(r"^\s*[0-9a-f]+:\s+([a-z][a-z0-9]*)", d, re.M)
                    if audit.level_of(m.group(1)) not in (None, "tzcnt")]
            self.assertGreater(len(d), 100000, name)
            self.assertEqual(bool(hits), want, (name, sorted(set(hits))[:10]))


if __name__ == "__main__":
    unittest.main()
