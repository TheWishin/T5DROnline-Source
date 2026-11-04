"""The practice suite (1.2.1, docs/TRAINING.md "Practice menu").

* tests/c/practice_test.cpp, built against src/training/practice_logic.h and the patched runtime's
  libs/video/rsx_overlay.c (ps3recomp patch 0045, without Direct3D), must print PASS: the menu's navigation, its
  texts (a glyph for every character, every line fits the panel), the settings and recordings files, P1's input
  delay, the dummy's counter-attack, random playback, the restart places and the movement loops.
* practice.cpp keeps everything new behind the gate the practice tools always had: the menu is opened, drawn and
  read only in offline Practice; its files are host files; online code paths are untouched.
* The launcher passes T5_PRACTICE_DIR (its own folder) and the practice help names the menu.

The C part needs a ps3recomp tree with patch 0045 (PS3RECOMP_DIR, deps/ps3recomp) and a Windows C compiler; it is
skipped without them.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

for _sub in ("launcher", "lobby"):
    if os.path.join(ROOT, _sub) not in sys.path:
        sys.path.append(os.path.join(ROOT, _sub))

from test_training import code_only, find_ps3recomp, find_vcvars  # noqa: E402

TRAINING = os.path.join(ROOT, "src", "training")


class PracticeLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows compiler")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0045 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "practice_test.exe")
        inc = [os.path.join(cls.tree, "libs", "video"), TRAINING]
        srcs = [os.path.join(ROOT, "tests", "c", "practice_test.cpp"),
                os.path.join(cls.tree, "libs", "video", "rsx_overlay.c")]
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 /EHsc /std:c++17 /DRSX_OVERLAY_NO_D3D {flags} '
               + " ".join(f'"{s}"' for s in srcs) + f' /Fe:"{exe}" /Fo:"{cls.tmp.name}\\\\"'
               + " gdi32.lib user32.lib")
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600, cwd=cls.tmp.name)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/practice_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_c_unit_test_passes(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        tail = r.stdout[-3000:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", tail)


class PracticeMenuGateTest(unittest.TestCase):
    """The menu and everything new in practice.cpp stay offline, in Practice."""

    def setUp(self):
        with open(os.path.join(TRAINING, "practice.cpp"), encoding="utf-8") as f:
            self.raw = f.read()
        self.src = code_only(self.raw)
        with open(os.path.join(TRAINING, "training.cpp"), encoding="utf-8") as f:
            self.training = code_only(f.read())

    def pads_body(self):
        return self.src.split("void t5_practice_pads(")[1].split("\nextern \"C\" int t5_practice_status(")[0]

    def test_menu_after_the_gate(self):
        body = self.pads_body()
        gate = body.index("if (!allowed())")
        for what in ("g_menu.show(", "g_menu.frame(", "g_delay.frame(", "g_counter.frame(", "g_start_tap = 3"):
            self.assertGreater(body.index(what), gate, what)

    def test_menu_shown_only_in_practice(self):
        self.assertRegex(self.src, r"int t5_practice_menu_open\(void\)\s*\{\s*return g_cfg\.on && g_in_practice && "
                                   r"g_menu\.open\(\) \? 1 : 0;")
        # training.cpp draws it only offline, in Practice
        self.assertRegex(self.training, r"const bool menu = !online && gt == kGtPractice && t5_practice_menu_open\(\);")
        draw = self.src.split("void t5_practice_menu_draw(void)")[1]
        self.assertTrue(draw.lstrip().startswith("{\n    if (!t5_practice_menu_open()) return;"))

    def test_training_display_setter_is_host_state(self):
        body = self.training.split('void t5_training_display_set(int mode)')[1].split("\n}\n")[0]
        self.assertNotIn("vm_base", body)
        self.assertIn("g_f2_mode = mode;", body)

    def test_no_new_guest_writes(self):
        """practice.cpp still stores into guest memory only through put32 (and its callers)."""
        stmts = [x.strip() for x in re.split(r"[;{}]", self.src) if "vm_base" in x]
        allowed = (r"^memcpy\(\s*&v\s*,\s*vm_base\s*\+\s*a\s*,\s*[24]\s*\)$",
                   r"^return\s+vm_base\[a\]$",
                   r"^memcpy\(\s*vm_base\s*\+\s*a\s*,\s*&v\s*,\s*4\s*\)$")
        for st in stmts:
            self.assertTrue(any(re.match(a, st) for a in allowed), st)
        with open(os.path.join(TRAINING, "practice_logic.h"), encoding="utf-8") as f:
            self.assertNotIn("vm_base", code_only(f.read()))

    def test_files_are_the_practice_folder(self):
        self.assertIn('getenv("T5_PRACTICE_DIR")', self.raw)
        self.assertIn('"settings.txt"', self.raw)
        self.assertIn('"char%02d.txt"', self.raw)

    def test_documented(self):
        with open(os.path.join(ROOT, "docs", "TRAINING.md"), encoding="utf-8") as f:
            doc = f.read()
        self.assertIn("## Practice menu (1.2.1)", doc)
        for env in ("T5_PRACTICE_MENU", "T5_PRACTICE_DIR"):
            self.assertIn(env, doc)


class LauncherTest(unittest.TestCase):
    def setUp(self):
        import core
        self.core = core
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def settings(self, **kw):
        s = self.core.Settings(os.path.join(self.tmp.name, "launcher.json"))
        s.update(kw)
        return s

    def test_practice_dir_is_the_launchers_folder(self):
        s = self.settings()
        env = s.env_overrides()
        self.assertEqual(env["T5_PRACTICE_DIR"], os.path.join(s.out_dir, "practice"))
        self.assertNotIn("T5_PRACTICE_DIR", self.settings(practice=False).env_overrides())

    def test_new_dummy_choices(self):
        for key in ("dash", "backdash", "kbd", "wavedash"):
            self.assertIn(key, self.core.PRACTICE_DUMMY)
            self.assertEqual(self.settings(practice_dummy=key).env_overrides()["T5_PRACTICE_DUMMY"], key)

    def test_help_names_the_menu(self):
        self.assertIn("START", self.core.PRACTICE_HELP)


if __name__ == "__main__":
    unittest.main()
