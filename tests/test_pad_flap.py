"""A DirectInput device that is lost again right after it was found (ps3recomp patch 0087,
libs/input/pad_host_win32.c), and controls.ini keys given twice.

A player's Razer Panthera PS4 (1532:0401, PS4 mode) showed two DirectInput devices of that name: the stick and a
phantom that failed its reads at once and was found again every ~0.5 s. Port 2 flipped disconnected / connected
~200 times and the menus got presses nobody made (the Practice menu's TRAINING DUMMY option changed on its own).

* tests/c/pad_flap_test.c runs the runtime's own hot-plug thread, 1 ms sampler and game reads on a fake
  DirectInput with that stick and that phantom; it must print PASS (before patch 0087: the phantom on port 2,
  ghost presses, a held button counted as a press after a re-plug).
* controls.ini: a key given twice in a section is reported, with the value that is used (the last one).

The C part needs the patched ps3recomp tree (PS3RECOMP_DIR, deps/ps3recomp) and a Windows C compiler; it is
skipped without them.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0087-dinput-flap.patch")


def find_tree():
    """A ps3recomp tree whose pad layer has patch 0087 (or PS3RECOMP_DIR as given, to run it on another one)."""
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
        p = os.path.join(c or "", "libs", "input", "pad_host_win32.c")
        if c and os.path.isfile(p):
            if c == os.environ.get("PS3RECOMP_DIR"):
                return c
            with open(p, encoding="utf-8", errors="replace") as f:
                if "di_flap_note(" in f.read():
                    return c
    return None


class PatchTextTest(unittest.TestCase):
    def test_patch_is_in_the_series(self):
        self.assertTrue(os.path.isfile(PATCH))
        with open(PATCH, encoding="utf-8") as f:
            text = f.read()
        for what in ("di_flap_note(", "DI_PROBATION_MS", "di_hold(", "is given more than once", "appears twice"):
            self.assertIn(what, text)


class FlapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("the runtime's pad layer is Windows only")
        cls.tree = find_tree()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0087 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "pad_flap_test.exe")
        inc = [os.path.join(cls.tree, *p) for p in (("libs", "input"), ("libs",), ("runtime",), ("include",))]
        src = os.path.join(ROOT, "tests", "c", "pad_flap_test.c")
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 {flags} "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "pad_flap_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/pad_flap_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_phantom_is_quarantined_and_never_presses(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        out = r.stdout
        self.assertEqual(r.returncode, 0, out[-3000:])
        self.assertRegex(out, r"(?m)^PASS \d+ checks$", out[-3000:])
        self.assertEqual(len(re.findall(r"lost 3 times within 30 s of being found -- ignored from now on", out)), 1,
                         out[-3000:])
        self.assertNotIn("port 2 (player 2)", out)

    def test_key_given_twice(self):
        ini = os.path.join(self.tmp.name, "twice.ini")
        with open(ini, "w") as f:
            f.write("[general]\ntap_latch = 0\nxinput = 1\n; a comment\n"
                    "tap_latch = 1   ; the file's own line further down\n"
                    "[port1]\nsocd = last\n[general]\nhid = 0\n")
        r = subprocess.run([self.exe, f"ini={ini}"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('[general] tap_latch is given more than once (line 2: "0", line 5: "1") -- the last one is used:'
                      ' tap_latch = 1', r.stdout)
        self.assertIn("[general] appears twice (lines 1 and 8) -- the second one is not used", r.stdout)
        self.assertIn("tap_latch = 1", r.stdout.splitlines()[-1])
        self.assertNotIn("xinput is given", r.stdout)


if __name__ == "__main__":
    unittest.main()
