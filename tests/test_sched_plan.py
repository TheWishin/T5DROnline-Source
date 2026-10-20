"""Thread placement (ps3recomp patch 0065, docs/RENDER_PERF.md "Thread placement"). No game needed.

* tests/c/sched_plan_test.c, built against the patched runtime source (runtime/platform/host_sched_plan.h), runs
  the placement rules on made-up processor tables -- the CPUs this PC does not have: Intel hybrid parts (12th-14th
  gen, Core Ultra), two-CCD and X3D Ryzens, 4-core CCX Ryzens, SMT and no SMT, affinity masks -- plus 4,000 random
  tables against the rules every plan must keep (the game thread and the translation only on performance cores of a
  hybrid CPU, never on one core together, workers never on reserved cores, pools within their limits). It must print
  PASS. Skipped without a patched ps3recomp tree (PS3RECOMP_DIR) or a Windows C compiler.
* The patch itself: the placement lines the problem report keeps, the switches the docs name.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import problem_report as report  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0065-thread-placement.patch")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


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
        p = os.path.join(c or "", "runtime", "platform", "host_sched_plan.h")
        if c and os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                if "hsp_make(" in f.read():
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


class PlanRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows toolchain")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0065 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "sched_plan_test.exe")
        src = os.path.join(ROOT, "tests", "c", "sched_plan_test.c")
        cc = f'"{clang}"' if clang else "cl"
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 /I "{os.path.join(cls.tree, "runtime")}" "{src}" '
               f'/Fe:"{exe}" /Fo:"{os.path.join(cls.tmp.name, "sched_plan_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/sched_plan_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_c_unit_test_passes(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=300, cwd=self.tmp.name)
        tail = r.stdout[-3000:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", tail)


class Patch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = text("patches", "ps3recomp", "0065-thread-placement.patch")

    def test_files_it_touches(self):
        files = re.findall(r"(?m)^diff --git a/(\S+)", self.patch)
        self.assertEqual(sorted(files), ["libs/spurs/cellSpurs.c", "libs/video/rsx_live_draw.c",
                                         "runtime/platform/host_sched.c", "runtime/platform/host_sched.h",
                                         "runtime/platform/host_sched_plan.h"])

    def test_switches_and_lines(self):
        for want in ("PS3_SCHED_PLACE", "PS3_SCHED_IDEAL", "PS3_SCHED_PRIO_VERTEX", "[sched] processors:",
                     "[sched] placement:", "SetThreadSelectedCpuSets", "SetThreadIdealProcessor",
                     "ThreadPowerThrottling", "RelationCache", "host_sched_default_threads(HS_ROLE_SPURS)",
                     "host_sched_default_threads(HS_ROLE_VERTEX)", "HS_ROLE_VERTEX"):
            self.assertIn(want, self.patch)

    def test_documented(self):
        doc = text("docs", "RENDER_PERF.md")
        self.assertIn("## Thread placement (patch 0065", doc)
        for want in ("PS3_SCHED_PLACE", "EfficiencyClass", "tools/slow_core.py", "[sched] placement:"):
            self.assertIn(want, doc)

    def test_the_problem_report_keeps_the_placement(self):
        lines = ["[sched] CPU budget: 20 logical processors, 14 cores (affinity mask; PS3_CPUS); sub-ms sleeps: timer",
                 "[sched] processors: 20 logical, 14 cores (of 20), SMT; hybrid: 6 P-cores (12 logical, class 1) + 8 "
                 "E-cores; one cache group",
                 "[sched] placement: game thread, translation, sound core on LP 0-11 (P-cores), ideal LP 2 / 4 / 6; "
                 "game's other threads the same",
                 "[sched] placement: workers on LP 0-1,6-19 (not LP 2-5: the game thread's and translation's cores); "
                 "SPURS 12 at a time, vertex workers 1; priorities: game +2, translation +2, sound +2, workers +1/+1",
                 "[sched] game thread 'main': priority +2, ideal processor LP 2 (ok), CPU set 0-11 (ok), EcoQoS never (ok)",
                 "[sched] translation 'ticker': priority +2, ideal processor LP 4 (ok), CPU set 0-11 (ok), EcoQoS never (ok)",
                 "[sched] sound core 'spu': priority +2, ideal processor LP 6 (ok), CPU set 0-11 (ok), EcoQoS never (ok)"]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "game.log")
            with open(p, "w", encoding="utf-8") as f:
                f.write("[boot] start\n" + "\n".join(lines) + "\n[sched] thread 'x' role=PPU\n")
            facts = report.facts_from_log(p)
        for ln in lines:
            self.assertIn(ln[:200], facts)
        self.assertFalse(any("role=PPU" in x for x in facts))


if __name__ == "__main__":
    unittest.main()
