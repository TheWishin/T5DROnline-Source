"""Render translation CPU (ps3recomp patch 0062, docs/RENDER_PERF.md "Translation CPU", branch xlat-cpu).
No game needed.

* The patch changes only the renderer's host side (libs/video: the live D3D12 engine, the NV4097
  dispatcher, the FIFO walker): no guest memory is written, so two players of a match may run different
  builds (lockstep and rollback pairs in sync, docs).
* Every change has its switch (RSX_STATE_CACHE, RSX_RING_VIEWS, RSX_DISPATCH_SPANS, PS3_GCM_HEADER_RUN).
* tests/c/xlat_dispatch_test.c, built against the patched runtime source: the span dispatch leaves the
  dispatcher in exactly the state the per-word loop does and makes the same sink calls (random method
  streams). Skipped without a patched ps3recomp tree (PS3RECOMP_DIR) or a C compiler.
* tools/fight_bench.py reports the slow end (p99) of the renderer's per-frame columns; tools/thread_profile.py
  reads lld-link maps.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import fight_bench  # noqa: E402
import thread_profile  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0062-xlat-cpu.patch")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0062 in this checkout")
        self.patch = text("patches", "ps3recomp", "0062-xlat-cpu.patch")

    def added(self):
        return "\n".join(ln[1:] for ln in self.patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))

    def test_only_the_renderer(self):
        files = sorted(set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M)))
        self.assertEqual(files, ["libs/video/cellGcmSys.c", "libs/video/rsx_dispatch.c", "libs/video/rsx_live_draw.c"])

    def test_host_side_only(self):
        # nothing the patch adds writes guest memory: the game runs the same frames with or without it
        add = self.added()
        for word in ("vm_write", "write_be", "wr32(", "vm_write32", "guest_write"):
            self.assertNotIn(word, add, word)

    def test_every_change_has_its_switch(self):
        add = self.added()
        for env in ("RSX_STATE_CACHE", "RSX_RING_VIEWS", "RSX_DISPATCH_SPANS", "PS3_GCM_HEADER_RUN"):
            self.assertIn('getenv("%s")' % env, add, env)

    def test_state_cache_is_forgotten_by_every_other_pass(self):
        # every list reset and every pass that records its own pipeline state forgets the cached bindings
        add = self.added()
        self.assertGreaterEqual(add.count("ld_bound_invalidate();"), 7)
        for marker in ("g_ld_copy.rootsig", "g_ld_gview.rootsig", "g_ldp.heap", "g.depth_snapshot_pso"):
            i = self.patch.find(marker)
            self.assertGreater(i, 0, marker)

    def test_pso_keys_unchanged(self):
        # the memo returns the key the byte-wise FNV computed for the same inputs: no new key function
        add = self.added()
        self.assertIn("memcmp(&kmemo->in, &kin, sizeof(kin)) == 0", add)
        self.assertNotIn("static u64 fnv1a(", add)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertEqual(names[-1], "0062-xlat-cpu.patch")
        self.assertGreater(names.index("0062-xlat-cpu.patch"), names.index("0059-weak-pc-fps.patch"))


class FightBenchSplit(unittest.TestCase):
    def test_p99_columns(self):
        rows = []
        for i in range(200):
            rows.append({"fifo_cpu_us": str(2000 + i), "xlat_us": str(2100 + i), "draw_us": "1400", "draws": "830",
                         "ph_layout_us": "1", "ph_fetch_us": "1", "ph_upload_us": "1", "ph_pso_us": "100",
                         "ph_const_us": "1", "ph_texbind_us": "400", "texhash_us": "200",
                         "present_flush_us": "100", "present_call_us": "180", "flush_wait_us": "0",
                         "ph_desc_us": "100", "ph_cbcopy_us": "70", "ph_api_us": "200", "ph_post_us": "50"})
        s = fight_bench.renderer_split(rows)
        self.assertAlmostEqual(s["fifo_cpu_ms"], 2.0995, places=3)
        self.assertAlmostEqual(s["p99"]["fifo_cpu_ms"], fight_bench.pct([2000 + i for i in range(200)], 99) / 1000.0)
        self.assertAlmostEqual(s["p99"]["d3d_ms"], 0.35)
        self.assertAlmostEqual(s["d3d_ms"], 0.35)


class ThreadProfileMap(unittest.TestCase):
    def test_reads_publics_and_statics(self):
        d = tempfile.mkdtemp(prefix="t5dr-map")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "t.map")
        with open(p, "w") as f:
            f.write(" t5dr\n\n Preferred load address is 0000000140000000\n\n"
                    "  Address         Publics by Value              Rva+Base               Lib:Object\n"
                    " 0001:00000010       main                       0000000140001010     a.obj\n"
                    " 0001:00000200       sink_end_impl              0000000140001200     r.obj\n"
                    " 0003:00000010       some_data                  0000000140200010     r.obj\n"
                    " Static symbols\n"
                    " 0001:00000100       blk_span                   0000000140001100     d.obj\n")
        syms = thread_profile.load_map(p)
        self.assertEqual(syms, [(0x1010, "main"), (0x1100, "blk_span"), (0x1200, "sink_end_impl")])


def find_ps3recomp():
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
        p = os.path.join(c or "", "libs", "video", "rsx_dispatch.c")
        if c and os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                if "blk_span(" in f.read():
                    return c
    return None


def find_vcvars():
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = os.path.join(pf86, "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if os.path.isfile(vswhere):
        r = subprocess.run([vswhere, "-latest", "-products", "*", "-property", "installationPath"],
                           capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            p = os.path.join(line.strip(), "VC", "Auxiliary", "Build", "vcvars64.bat")
            if os.path.isfile(p):
                return p
    return None


class SpanDispatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows C compiler")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0062 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "xlat_dispatch_test.exe")
        inc = [os.path.join(cls.tree, *p) for p in (("libs", "video"), ("libs",), ("runtime",), ("include",))]
        src = os.path.join(ROOT, "tests", "c", "xlat_dispatch_test.c")
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 {flags} "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "xlat_dispatch_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/xlat_dispatch_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_spans_equal_the_per_word_loop(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=300, cwd=self.tmp.name)
        tail = r.stdout[-3000:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", tail)
        self.assertRegex(r.stdout, r"(?m)^\d+ blocks, .* 0 state mismatches$", tail)


if __name__ == "__main__":
    unittest.main()
