"""'Check my problem' (launcher/problem_check.py, problem_check_ui.py, 1.1.5): each known case from the logs and
this PC's facts, nothing from a build that went well, the window in English and German."""
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import problem_check as pc  # noqa: E402

try:
    import tkinter as tk
    import problem_check_ui as ui
except ImportError:      # pragma: no cover
    tk = None

FOUR = {"cores": 4, "logical": 8, "wine": None}
SFO_0101 = "  PARAM.SFO: TEKKEN 5: DARK RESURRECTION ONLINE / NPUB30009 / version 01.01\n"


def no_fw(exe):
    return types.SimpleNamespace(state="allowed", blocked=[])


class Base(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="t5dr-check")
        self.addCleanup(shutil.rmtree, self.out, True)
        os.makedirs(os.path.join(self.out, "logs"))

    def build_log(self, text, code=2):
        with open(os.path.join(self.out, "build.log"), "w", encoding="utf-8") as f:
            f.write("== Unpack the package ==\n" + text + f"\n# exit code {code}\n")

    def game_log(self, text, name="game-20261027-120000.log", age=0):
        p = os.path.join(self.out, "logs", name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        if age:
            t = time.time() - age
            os.utime(p, (t, t))

    def keys(self, facts=FOUR, fw=no_fw):
        return [f.key for f in pc.check(self.out, facts, fw)]


class BuildTest(Base):
    def test_v0101_package(self):
        self.build_log(SFO_0101 + "ERROR: The license (.rap) does not belong to this package.")
        found = pc.check(self.out, FOUR, no_fw)
        self.assertEqual([f.key for f in found], ["package_version"])
        title, seen, fix = found[0].text()
        self.assertEqual(title, "Your game package is version 01.01")
        self.assertIn("619,430,240", fix)
        self.assertIn("UP0700-NPUB30009_00-UPDATE0000010000.rap", fix)
        self.assertIn("01.01", seen)
        self.assertTrue(pc.help_url(found[0]).endswith("#this-copy-is-a-different-version-of-the-game"))

    def test_the_messages_of_1_1_5_and_before(self):
        self.build_log("ERROR: This package is version 01.01 of the game (program content ID "
                       "UP0700-NPUB30009_00-0000000000000000). The port supports only version 01.00")
        self.assertEqual(self.keys(), ["package_version"])
        self.build_log('ERROR: This copy is a different version of the game: "TEKKEN 5" version 01.01, content ID x')
        self.assertEqual(self.keys(), ["package_version"])
        self.build_log("  program content ID: UP0700-NPUB30009_00-0000000000000000 (its license: ...)\nERROR: x")
        self.assertEqual(self.keys(), ["package_version"])

    def test_a_build_that_went_well_says_nothing(self):
        self.build_log(SFO_0101.replace("01.01", "01.00") + "MemoryError (an old attempt)", code=0)
        self.assertEqual(self.keys(), [])
        self.build_log(SFO_0101.replace("01.01", "01.00") + "  program OK", code=2)
        self.assertEqual(self.keys(), [])                       # failed, but for none of the known reasons

    def test_unpack_out_of_memory(self):
        self.build_log("Traceback (most recent call last):\n  File \"pkg_extract.py\", line 300, in main\n"
                       "MemoryError\nERROR: step 'Unpack' failed")
        self.assertEqual(self.keys(), ["unpack_memory"])

    def test_package_cut_short(self):
        self.build_log("ERROR: The package is 600,000,000 bytes, the supported one is 619,430,240 bytes: the "
                       "download is incomplete or it is a different file. Download it again.")
        self.assertEqual(self.keys(), ["package_damaged"])


class GameLogTest(Base):
    def test_corrupted_data_box(self):
        self.game_log("[cellMsgDialog] Open2(type=0x00000001, msg='The installed game data is corrupted.\n"
                      "Delete it and install again.')\n[DIALOG] The installed game data is corrupted.\n")
        found = pc.check(self.out, FOUR, no_fw)
        self.assertEqual([f.key for f in found], ["package_damaged"])
        self.assertIn('"The installed game data is corrupted."', found[0].text()[1])

    def test_only_the_newest_game_log(self):
        self.game_log("[DIALOG] The installed game data is corrupted.\n", "game-1.log", age=3600)
        self.game_log("[gpu] adapter: X (vendor 10DE, 2048 MB, feature level 11_0, resource binding tier 2, x)\n",
                      "game-2.log")
        self.assertEqual(self.keys(), [])

    def test_old_graphics_card(self):
        self.game_log("[gpu] adapter: NVIDIA GeForce GT 730 (vendor 10DE, 4096 MB, feature level 11_0, resource "
                      "binding tier 1, dedicated)\n")
        found = pc.check(self.out, FOUR, no_fw)
        self.assertEqual([(f.key, f.kind) for f in found], [("gpu_tier1", "hint")])
        self.assertIn("NVIDIA GeForce GT 730", found[0].text()[2])


class PcTest(Base):
    def test_two_cores_and_wine(self):
        found = pc.check(self.out, {"cores": 2, "logical": 4, "wine": "Wine 9.0"}, no_fw)
        self.assertEqual([f.key for f in found], ["two_cores", "wine"])
        self.assertEqual(found[0].text()[1], "This PC: 2 cores, 4 logical processors.")
        self.assertEqual(found[1].text()[1], "This PC: Wine 9.0.")

    def test_wine_from_the_game_log(self):
        self.game_log("[wine] Wine 9.0 (Proton) Proton: GE-Proton10-4 on Linux -- RSX_VERTEX_THREADS=0 PS3_LWM_FAST=0\n")
        self.assertEqual(self.keys(), ["wine"])

    def test_firewall(self):
        fw = lambda exe: types.SimpleNamespace(state="blocked", blocked=["game"], exe=exe)   # noqa: E731
        found = pc.check(self.out, FOUR, fw)
        self.assertEqual([f.key for f in found], ["firewall"])
        self.assertIn(os.path.join(self.out, "build", "cmake"), found[0].text()[2])
        self.assertEqual(self.keys(fw=lambda exe: types.SimpleNamespace(state="blocked", blocked=["launcher"])), [])
        self.assertEqual(self.keys(fw=lambda exe: 1 / 0), [])                       # a failing look: nothing

    def test_problems_before_hints(self):
        self.build_log("MemoryError while unpacking")
        found = pc.check(self.out, {"cores": 2, "logical": 2, "wine": None}, no_fw)
        self.assertEqual([f.key for f in found], ["unpack_memory", "two_cores"])

    def test_facts_of_this_pc(self):
        f = pc.system_facts()
        self.assertEqual(set(f), {"cores", "logical", "wine"})
        self.assertIsNone(f["wine"])                    # (the tests run on Windows itself)

    def test_command_line(self):
        import contextlib
        import io
        from unittest import mock
        # this PC's facts and firewall stand in fixed (a 2-processor CI runner is itself a finding: "few cores")
        real = pc.check
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf),                 mock.patch.object(pc, "check", lambda out: real(out, FOUR, no_fw)):
            self.assertEqual(pc.main(["--out", self.out]), 0)
        self.assertIn("No known problem found.", buf.getvalue())


@unittest.skipIf(tk is None, "no tkinter")
class WindowTest(Base):
    def setUp(self):
        super().setUp()
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def dialog(self, facts, **kw):
        opened = []
        d = ui.CheckDialog(self.root, self.out, visible=False, facts=facts, fw=no_fw, open_url=opened.append, **kw)
        t_end = time.monotonic() + 10
        while d.findings is None and time.monotonic() < t_end:
            self.root.update()
            time.sleep(0.02)
        self.root.update()
        return d, opened

    def texts(self, w):
        out = []
        for c in w.winfo_children():
            try:
                out.append(str(c.cget("text")))
            except tk.TclError:
                pass
            out += self.texts(c)
        return out

    def test_findings_and_help(self):
        self.build_log(SFO_0101 + "ERROR: x")
        reports = []
        d, opened = self.dialog({"cores": 2, "logical": 4, "wine": None}, report=lambda: reports.append(1))
        texts = self.texts(d.top)
        self.assertIn("Your game package is version 01.01", texts)
        self.assertIn("Your processor has 2 cores", texts)
        helps = [w for w in d.list.winfo_children()[0].winfo_children()[0].winfo_children()
                 if isinstance(w, tk.ttk.Button)]
        helps[0].invoke()
        self.assertTrue(opened[0].endswith("#this-copy-is-a-different-version-of-the-game"))
        d._report()
        self.assertEqual(reports, [1])
        d.close()

    def test_nothing_found_in_german(self):
        from t5lobby import i18n
        i18n.set_language("de")
        self.addCleanup(i18n.set_language, "en")
        d, _ = self.dialog(FOUR)
        texts = self.texts(d.top)
        self.assertIn("Kein bekanntes Problem gefunden.", texts)
        self.assertIn("Mein Problem prüfen", texts)
        self.assertEqual(i18n.missing(), [])
        d.close()


if __name__ == "__main__":
    unittest.main()
