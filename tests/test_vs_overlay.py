"""The input display in offline Versus and the players' own button names (docs/TRAINING.md "Offline Versus",
"Your own button names").

* tests/c/button_names_test.cpp, built against src/training/button_names.h, must print PASS: controls.ini text ->
  names, the defaults when nothing is named, the runtime's ini rules, the other buttons of the pad mask, the text of
  a row, and who gets the display in which offline mode.
* The game side keeps the rules that make it an offline feature: names and Versus display only when the fight is
  not online, never in a replay, and the input ring is only read.
* The launcher's setting (off by default) reaches the game as T5_VS_OVERLAY=1; its texts are in every catalog.
* docs/controls.ini documents the [names] sections and, as shipped, names nothing.

The C part needs a Windows C++ compiler; it is skipped without one.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT
from test_training import code_only, find_vcvars

for _sub in ("launcher", "lobby"):
    if os.path.join(ROOT, _sub) not in sys.path:
        sys.path.append(os.path.join(ROOT, _sub))

TRAINING = os.path.join(ROOT, "src", "training")
TEXTS = ("Input display in offline Versus",
         "Offline Versus: both players' inputs, with your own button names from controls.ini ([names]). "
         "Never online. F2 in the game switches it.")


class ButtonNamesLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows compiler")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "button_names_test.exe")
        cc = f'"{clang}"' if clang else "cl"
        src = os.path.join(ROOT, "tests", "c", "button_names_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 /EHsc /std:c++17 /I "{TRAINING}" "{src}" '
               f'/Fe:"{exe}" /Fo:"{cls.tmp.name}\\\\"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600, cwd=cls.tmp.name)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/button_names_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_c_unit_test_passes(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", r.stdout[-3000:])


class GameSideRulesTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(TRAINING, "training.cpp"), encoding="utf-8") as f:
            self.src = code_only(f.read())
        with open(os.path.join(TRAINING, "button_names.h"), encoding="utf-8") as f:
            self.names = code_only(f.read())

    def test_names_are_offline_only(self):
        # the lists use the players' names only when the fight is not an online one
        self.assertRegex(self.src, r"g_named\s*=\s*!online\s*&&")
        # ... and the input ring is read only for them
        self.assertRegex(self.src, r"if\s*\(g_named\s*&&[^)]*extras")

    def test_versus_display_is_offline_only(self):
        # decided in the branch that is not the online one, by the tested rule
        m = re.search(r"if \(online\) \{(.*?)\} else \{(.*?)\n    \}", self.src, re.S)
        self.assertTrue(m)
        self.assertNotIn("offline_show", m.group(1))
        self.assertIn("offline_show(", m.group(2))
        self.assertIn("g_cfg.vs", m.group(2))
        # never in a replay or a spectated match
        self.assertRegex(self.src, r'_stricmp\(nm, ""\)\)\)\s*\{\s*g_cfg\.vs = false;\s*g_cfg\.replay = true;')
        self.assertRegex(self.src, r"versus_own\s*=\s*!w\.online\s*&&\s*!g_cfg\.replay\s*&&")

    def test_switches_work_while_every_display_is_off(self):
        # report 2026-11-11: F2 did nothing in offline Versus. With the training overlay Off and the Versus
        # setting off, the frame hook returned before it looked at F2 at all.
        m = re.search(r"if \(g_cfg\.mode == kOff && g_f2_mode < 0 && g_f2_vs < 0 && !g_cfg\.vs[^{]*\{(.*?)\n    \}", self.src, re.S)
        self.assertTrue(m, "the all-off path of t5_training_frame")
        self.assertIn("hotkeys();", m.group(1))
        self.assertRegex(m.group(1), r"if \(g_f2_mode < 0 && g_f2_vs < 0\) return;")
        # F2 in Versus: the tested rule, from the setting; it prepares the overlay it switches on
        m = re.search(r"if \(pressed && versus_own\) \{(.*?)\}", self.src, re.S)
        self.assertTrue(m)
        self.assertIn("versus_switch_pressed(g_cfg.vs, g_f2_vs)", m.group(1))
        self.assertIn("rsx_overlay_prepare()", m.group(1))

    def test_overlay_button_is_offline_and_read_only(self):
        # the pad's button comes from the input ring (read only), in an offline fight only: online the ring
        # also holds the other player's buttons
        m = re.search(r"if \((g_toggle && [^{]*)\) \{(.*?)\}", self.src, re.S)
        self.assertTrue(m)
        for need in ("!w.online", "!g_cfg.replay", "w.phase == 17", "kGtDemo"):
            self.assertIn(need, m.group(1))
        self.assertIn("overlay_toggle_held(g_toggle, rd16(kRing + slot), rd16(kRing +", m.group(2))
        # one press, one switch
        self.assertRegex(self.src, r"poll_hotkey\(w\.versus_own, held && !g_pad_down\);\s*g_pad_down = held;")
        self.assertRegex(self.src, r"g_toggle = parse_overlay_toggle\(text, len, &ok\)")

    def test_the_ring_is_only_read(self):
        for name, text in (("training.cpp", self.src), ("button_names.h", self.names)):
            self.assertNotRegex(text, r"\bwr(8|16|32|64)\s*\(", name)
            self.assertNotRegex(text, r"gcall\s*\(|ppu_guest_call", name)
        uses = re.findall(r"[^\n]*\bkRing(?:WriteIdx)?\b[^\n]*", self.src)
        self.assertGreaterEqual(len(uses), 3)
        for line in uses:
            self.assertTrue("rd16(" in line or "rd32(" in line or "const uint32_t kRing" in line, line)

    def test_default_off(self):
        # without T5_VS_OVERLAY nothing new is on
        self.assertRegex(self.src, r"bool\s+vs\s*=\s*false")


class LauncherSettingTest(unittest.TestCase):
    def setUp(self):
        saved = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved))
        import core
        self.core = core
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def settings(self, **kw):
        s = self.core.Settings(os.path.join(self.tmp.name, "launcher.json"))
        s.update(kw)
        return s

    def test_off_by_default(self):
        s = self.settings()
        self.assertIs(s["vs_overlay"], False)
        self.assertNotIn("T5_VS_OVERLAY", s.env_overrides())

    def test_on_reaches_the_game(self):
        env = self.settings(vs_overlay=True).env_overrides()
        self.assertEqual(env["T5_VS_OVERLAY"], "1")
        # its own setting: also with the training overlay Off, at the chosen position
        env = self.settings(vs_overlay=True, training="off", training_pos="bottom").env_overrides()
        self.assertEqual((env["T5_VS_OVERLAY"], env["T5_TRAINING"], env["T5_TRAINING_POS"]), ("1", "off", "bottom"))
        # and it does not switch on "the other offline modes"
        self.assertNotIn("T5_TRAINING_ALL", env)

    def test_junk_in_the_saved_file(self):
        path = os.path.join(self.tmp.name, "launcher.json")
        with open(path, "w") as f:
            f.write('{"vs_overlay": "yes"}')
        self.assertIs(self.core.Settings(path)["vs_overlay"], False)

    def test_texts_in_every_catalog(self):
        import importlib
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            ui = f.read()
        self.assertIn('t("Input display in offline Versus")', ui)
        self.assertIn("vs_overlay_var", ui)
        for lang in ("de", "es", "fr", "ja", "ko", "pt_br"):
            cat = importlib.import_module("t5lobby.i18n_" + lang).MESSAGES
            for text in TEXTS:
                self.assertIn(text, cat, lang)
                self.assertTrue(cat[text].strip() and cat[text] != text, lang)
                self.assertIn("[names]", cat[TEXTS[1]], lang)


class SampleFileTest(unittest.TestCase):
    def test_sample_documents_names_and_sets_none(self):
        with open(os.path.join(ROOT, "docs", "controls.ini"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("[names]", text)
        self.assertIn("[names1]", text)
        # as shipped every value is the default: no names section that is not a comment
        for line in text.splitlines():
            self.assertFalse(line.strip().lower().startswith("[names"), line)
            self.assertFalse(line.strip().lower().startswith("[overlay"), line)
        # the overlay button is documented there, with its default
        self.assertIn(";[overlay]", text)
        self.assertIn(";toggle = R3", text)


if __name__ == "__main__":
    unittest.main()
