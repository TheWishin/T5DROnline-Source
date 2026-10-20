"""The game thread's own time (ps3recomp patch 0061, docs/RENDER_PERF.md "The game thread's own time").

* tests/c/lwm_fast_test.cpp against runtime/ppu/ppu_lwm_fast.h -- the guest lwmutex's host lock without a
  system call while it is free -- taken from the patch itself (the header is a new file of 0061, so no
  patched tree is needed): mutual exclusion under every lock path, hand-over to a waiter, unlock by any
  thread, timeouts, over-release. Windows only; skipped without clang-cl and the Visual Studio build tools.
* What the patch must keep: each change has its switch, the icall hook still sees every indirect call (the
  rollback draw cut), the first registered HLE handler of a NID still wins, the series order.
* tools/game_thread_times.py and tools/host_prof.py on made-up logs.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0061-game-thread-cpu.patch")
LLVM = r"C:\Program Files\LLVM"
sys.path.insert(0, os.path.join(ROOT, "tools"))
import game_thread_times  # noqa: E402
import host_prof  # noqa: E402


def patch_text():
    with open(PATCH, encoding="utf-8") as f:
        return f.read()


def new_file_from_patch(text, path):
    """The content of a file the patch adds (all of it is in the patch as + lines)."""
    m = re.search(r"^diff --git a/%s b/%s\n(?:.*\n)*?\+\+\+ b/%s\n@@ -0,0 \+1,(\d+) @@\n" %
                  ((re.escape(path),) * 3), text, re.M)
    if not m:
        return None
    lines = text[m.end():].split("\n")[:int(m.group(1))]
    assert all(ln.startswith("+") for ln in lines), "not a new file"
    return "\n".join(ln[1:] for ln in lines) + "\n"


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def added(text, path):
    """The + lines of one file's diff."""
    out, cur = [], None
    for ln in text.split("\n"):
        if ln.startswith("diff --git "):
            cur = ln.split(" b/")[-1]
        elif cur == path and ln.startswith("+") and not ln.startswith("+++"):
            out.append(ln[1:])
    return "\n".join(out)


class LwmFastLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with clang-cl")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (os.path.join(LLVM, "bin", "clang-cl.exe")
                                             if os.path.isfile(os.path.join(LLVM, "bin", "clang-cl.exe")) else None)
        if not vcvars or not clang:
            raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
        hdr = new_file_from_patch(patch_text(), "runtime/ppu/ppu_lwm_fast.h")
        if not hdr:
            raise AssertionError("patch 0061 does not add runtime/ppu/ppu_lwm_fast.h")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        with open(os.path.join(cls.tmp.name, "ppu_lwm_fast.h"), "w", encoding="utf-8") as f:
            f.write(hdr)
        exe = os.path.join(cls.tmp.name, "lwm_fast_test.exe")
        src = os.path.join(ROOT, "tests", "c", "lwm_fast_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O1 /W3 /I"{cls.tmp.name}" "{src}" '
               f'/Fe:"{exe}" /Fo:"{os.path.join(cls.tmp.name, "lwm_fast_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/lwm_fast_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_lock(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=300, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", r.stdout[-3000:])


class PatchContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = patch_text()

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertIn("0059-weak-pc-fps.patch", names)
        self.assertGreater(names.index("0061-game-thread-cpu.patch"), names.index("0059-weak-pc-fps.patch"))

    def test_switches(self):
        for sw in ("PS3_LWM_FAST", "PS3_ICALL_HOOK_FAST", "PS3_GAME_THREAD_LOG", "PS3_HOST_PROF_DEPTH"):
            self.assertIn(sw, self.text)

    def test_icall_hook_sees_every_call(self):
        add = added(self.text, "runtime/ppu/ppu_loader.cpp")
        # the fast path consults the hook with the resolved target, honours the one-shot bypass
        self.assertIn("else if (ps3_icall_hook(ctx, addr)) return;", add)
        self.assertIn("if (g_icall_nohook) g_icall_nohook = 0;", add)

    def test_first_registered_handler_wins(self):
        add = added(self.text, "runtime/ppu/ppu_hle.cpp")
        self.assertIn("a later registration: the first stays", add)
        self.assertIn("hle_ctx_find(nid)", add)

    def test_lwmutex_uses_the_fast_lock(self):
        add = added(self.text, "runtime/ppu/ppu_sysprx.cpp")
        self.assertIn('#include "ppu_lwm_fast.h"', add)
        for fn in ("lwm_fast_acquire", "lwm_fast_try", "lwm_fast_release"):
            self.assertIn(fn, add)

    def test_no_guest_state_or_fp_change(self):
        # nothing in the patch touches the lifter, the FP helpers or the VMX ops
        files = re.findall(r"^diff --git a/(\S+)", self.text, re.M)
        for f in files:
            self.assertNotIn("ppu_lifter", f)
            self.assertNotIn("ppu_fp_det", f)
            self.assertNotIn("ppu_vmx", f)


class Tools(unittest.TestCase):
    def test_game_thread_times(self):
        d = tempfile.mkdtemp(prefix="t5dr-gt")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "game_thread.log")
        qf, tf = 10_000_000, 4_000_000_000
        lines = ["# qpc_frequency=%d tsc_frequency=%d" % (qf, tf)]
        req, cyc = 1_000_000, 0
        for seq in range(1, 101):
            rel = req + 166_667 - 50_000            # released 11.67 ms after the last request
            req += 166_667                          # a request every 16.67 ms
            cyc += 20_000_000                       # 5 ms of thread time per frame
            lines.append("%d %d %d %d 7" % (seq, req, rel, cyc))
        write(p, "\n".join(lines) + "\n")
        rows = game_thread_times.read(p)
        self.assertEqual(len(rows), 99)
        self.assertAlmostEqual(rows[5][1], 5.0, places=3)        # CPU ms
        self.assertAlmostEqual(rows[5][2], 5.0, places=3)        # game part: release -> request
        self.assertAlmostEqual(rows[5][3], 16.6667, places=3)    # interval

    def test_host_prof_demangle_and_kinds(self):
        self.assertEqual(host_prof.demangle("?func_00165BD0@@YAXPEAUppu_context@@@Z"), "func_00165BD0")
        self.assertEqual(host_prof.demangle("ps3_hle_call"), "ps3_hle_call")
        self.assertEqual(host_prof.classify_frame("func_00355C70", "ppu_recomp_011.cpp.obj"), "lifted")
        self.assertEqual(host_prof.classify_frame("rb::state_commit", "rb_state.cpp.obj"), "src")
        self.assertEqual(host_prof.classify_frame("sys_lwmutex_lock", "ppu_sysprx.cpp.obj"), "runtime")

    def test_host_prof_report(self):
        d = tempfile.mkdtemp(prefix="t5dr-hp")
        self.addCleanup(shutil.rmtree, d, True)
        mp = os.path.join(d, "t5dr.map")
        write(mp, 
            " t5dr\n\n Preferred load address is 0000000140000000\n\n"
            "  Address         Publics by Value              Rva+Base               Lib:Object\n\n"
            " 0001:00000000       main                       0000000140001000     boot_main.cpp.obj\n"
            " 0001:00001000       ?func_00010000@@YAXPEAUppu_context@@@Z 0000000140002000     ppu_recomp_000.cpp.obj\n"
            " 0001:00002000       sys_lwmutex_lock           0000000140003000     ppu_sysprx.cpp.obj\n")
        pf = os.path.join(d, "prof.txt")
        write(pf, "# stacks samples=3\nM 0 ntdll.dll\n"
                            "S 7 2 2010 1010\n"
                            "S 7 3 3010 2020 1010\n"
                            "S 7 3 M0+1234 3020 1010\n")
        js = os.path.join(d, "out.json")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "host_prof.py"), pf, "--map", mp,
                            "--json", js], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(js, encoding="utf-8") as f:
            out = json.load(f)
        self.assertEqual(out["samples"], 3)
        inc = dict(out["inclusive"])
        self.assertEqual(inc["main"], 3)
        self.assertEqual(inc["sys_lwmutex_lock"], 2)
        selfc = dict(out["self"])
        self.assertEqual(selfc["func_00010000"], 1)


if __name__ == "__main__":
    unittest.main()
