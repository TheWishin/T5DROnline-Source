"""The present and the D3D12 calls off the translation's critical path (ps3recomp patch 0067,
docs/RENDER_PERF.md "Overlap: the present and the D3D12 calls", branch xlat-overlap). No game needed.

* The patch changes only the renderer's host side (libs/video, the ticker's pacing statistics in boot_main):
  nothing it adds writes guest memory, so two players of a match may run different builds.
* RSX_XLAT_OVERLAP switches it (0 off, 1 the present on the renderer thread, 2 also the command-list calls,
  the default).
* Every command-list method the translation calls through the recorder (LDL) is recorded and replayed; the
  methods it may not record (Close, Reset, SetName) are only reached with the real list.
* tests/c/xlat_ring_test.c, built against the patched runtime source (rsx_record_ring.h): calls recorded on one
  thread arrive on the other exactly once, in order, with their arguments, across ring wraps and a full ring.
  Skipped without a patched ps3recomp tree (PS3RECOMP_DIR) or a C compiler.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0067-xlat-overlap.patch")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0067 in this checkout")
        self.patch = text("patches", "ps3recomp", "0067-xlat-overlap.patch")

    def added(self):
        return "\n".join(ln[1:] for ln in self.patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))

    def test_only_the_renderer(self):
        files = sorted(set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M)))
        self.assertEqual(files, ["libs/video/cellGcmSys.c", "libs/video/rsx_live_draw.c", "libs/video/rsx_live_draw.h",
                                 "libs/video/rsx_record_ring.h", "runtime/ppu/tests/boot_main.cpp"])

    def test_host_side_only(self):
        # nothing the patch adds writes guest memory: the game runs the same frames with or without it
        add = self.added()
        for word in ("vm_write", "write_be", "wr32(", "guest_write", "vm_memcpy_to", "vm_memset"):
            self.assertNotIn(word, add, word)

    def test_switch(self):
        add = self.added()
        self.assertIn('getenv("RSX_XLAT_OVERLAP")', add)
        self.assertIn("e && *e == '0' ? 0 : e && *e == '1' ? 1 : 2", add)   # default 2, 1 = the present only

    def test_every_recorded_method_is_replayed(self):
        add = self.added()
        recorded = set(re.findall(r"g_rq_vtbl\.(\w+) = rq_\1;", add))
        called = set(re.findall(r"LDL->lpVtbl->(\w+)\(", add))
        # Close/Reset (ld_flush, ld_begin_recording) run with the real list (ld_own_enter); SetName at init
        self.assertEqual(called - recorded, {"Close", "Reset", "SetName"})
        ops = re.search(r"enum \{ (RQ_WRAP = 0,[^}]*)\}", add).group(1)
        ops = [o.strip() for o in ops.replace("RQ_WRAP = 0", "RQ_WRAP").split(",") if o.strip()]
        for op in ops[1:]:
            self.assertRegex(add, r"case %s:" % op, op)         # replayed
            self.assertIn("ld_rq_put(%s," % op, add, op)       # recorded

    def test_owned_list_around_submit_and_reset(self):
        # ld_flush / ld_begin_recording take the real list over before they close, submit, wait or reset
        add = self.added()
        self.assertIn("ld_own_enter();\n    ld_flush_owned(reason);\n    ld_own_leave();", add)
        self.assertIn("ld_own_enter();\n    ld_begin_recording_owned();\n    ld_own_leave();", add)
        self.assertRegex(self.patch, r"\+static void ld_flush_owned\(ld_flush_reason reason\)\n\+\{\n \s+ld_begin_recording\(\);")

    def test_walk_waits_for_the_present(self):
        self.assertIn("if (work) rsx_live_draw_sync();", self.added())

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertIn("0067-xlat-overlap.patch", names)
        self.assertGreater(names.index("0067-xlat-overlap.patch"), names.index("0065-thread-placement.patch"))

    def test_documented(self):
        doc = text("docs", "RENDER_PERF.md")
        self.assertIn("RSX_XLAT_OVERLAP", doc)
        self.assertIn("patch 0067", doc)


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
        if c and os.path.isfile(os.path.join(c, "libs", "video", "rsx_record_ring.h")):
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


class RecordRing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows C compiler (D3D12 headers)")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0067 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "xlat_ring_test.exe")
        src = os.path.join(ROOT, "tests", "c", "xlat_ring_test.c")
        cc = f'"{clang}"' if clang else "cl"
        inc = os.path.join(cls.tree, "libs", "video")
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O2 /W0 /I "{inc}" "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "xlat_ring_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/xlat_ring_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_calls_arrive_once_in_order(self):
        r = subprocess.run([self.exe, "200000"], capture_output=True, text=True, timeout=300, cwd=self.tmp.name)
        tail = r.stdout[-2000:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertRegex(r.stdout, r"(?m)^PASS$", tail)
        self.assertRegex(r.stdout, r"identical, 0 sync failures, 0 unexpected calls", tail)

    def test_a_slow_renderer_thread_changes_nothing(self):
        # 1.1.5 (patch 0070, RSX_XLAT_RENDER_DELAY_US): the renderer thread as slow as under Proton -- every call
        # still arrives once, in order, and every sync waits for it
        env = dict(os.environ, RSX_XLAT_RENDER_DELAY_US="3,1")
        r = subprocess.run([self.exe, "20000"], capture_output=True, text=True, timeout=600, cwd=self.tmp.name, env=env)
        tail = r.stdout[-2000:] + r.stderr[-500:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertIn("RSX_XLAT_RENDER_DELAY_US", r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"identical, 0 sync failures, 0 unexpected calls", tail)


class RingReuseHooks(unittest.TestCase):
    """1.1.5 "vertices freak out for a second" (Proton): the test hooks that showed the overlap does not reuse
    ring memory early (patch 0070; docs/RENDER_PERF.md "Ring reuse")."""

    def test_hooks_in_the_patch_and_documented(self):
        p = os.path.join(ROOT, "patches", "ps3recomp", "0070-ps-triggers-ring-reuse.patch")
        if not os.path.isfile(p):
            self.skipTest("no patch 0070 in this checkout")
        patch = text("patches", "ps3recomp", "0070-ps-triggers-ring-reuse.patch")
        doc = text("docs", "RENDER_PERF.md")
        for name in ("RSX_XLAT_RENDER_DELAY_US", "RSX_RING_GUARD"):
            self.assertIn(name, patch)
            self.assertIn(name, doc)
        # off unless asked for: nothing else changes what the renderer does
        self.assertIn('g_ldg_on = e && *e == \'1\';', patch)


if __name__ == "__main__":
    unittest.main()
