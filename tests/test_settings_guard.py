"""The player's settings file is only for the player's launcher (launcher/core.py shared_settings_refusal).

Every case runs launcher/core.py in a child process that is NOT a unittest run and has none of the folder variables
(T5_SETTINGS_DIR, T5_ONLINE_DIR, T5_SETTINGS_SHARED) unless the case sets one: the situation of a launcher that a tool
starts as its own process. The child's APPDATA is a folder of this test, the stand-in for the player's real one, so
nothing here can reach a real %APPDATA%\\T5DROnline; launcher.json and launcher.log are stand-ins too.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

CHILD = r"""
import json, os, sys
sys.path.insert(0, sys.argv[1])
import core
case = json.loads(sys.argv[2])
assert "unittest" not in sys.modules and not core._TEST_RUN
core.SETTINGS_FILE = os.path.join(case["install"], "launcher.json")
core.LAUNCHER_LOG = os.path.join(case["install"], "launcher.log")
if case.get("root"):
    core.ROOT = case["root"]
if "declare" in case:
    core.declare_launcher(testing=case["declare"])
out = {"dir": core.shared_settings_dir(), "why": core.shared_settings_refusal()}
s = core.Settings()
s["display"] = "borderless"
s.save()
out["store"] = s._store is not None
print(json.dumps(out))
"""
DROPPED = ("T5_SETTINGS_DIR", "T5_ONLINE_DIR", "T5_SETTINGS_SHARED", "T5DR_TESTING", "CI", "GITHUB_ACTIONS",
           "PYTEST_CURRENT_TEST", "T5_FW_CHECK", "T5DR_FW_CHECK", "TMPDIR")


class ChildProcess(unittest.TestCase):
    def setUp(self):
        self.dir = self.enterContext(tempfile.TemporaryDirectory())
        self.real = os.path.join(self.dir, "appdata", "T5DROnline")        # stands in for the player's folder
        self.install = os.path.join(self.dir, "T5DR-Online-1.2.3")         # looks like an unpacked release
        self.tmp = os.path.join(self.dir, "tmp")                           # the child's temporary folder
        for d in (self.install, self.tmp, os.path.dirname(self.real)):
            os.makedirs(d)

    def child(self, env=None, **case):
        clean = {k: v for k, v in os.environ.items() if k.upper() not in DROPPED}
        clean.update(APPDATA=os.path.dirname(self.real), TEMP=self.tmp, TMP=self.tmp, PYTHONIOENCODING="utf-8")
        clean.update(env or {})
        case.setdefault("install", self.install)
        r = subprocess.run([sys.executable, "-B", "-c", CHILD, os.path.join(ROOT, "launcher"), json.dumps(case)],
                           env=clean, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        with open(os.path.join(case["install"], "launcher.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["display"], "borderless")        # its own file is always written
        return json.loads(r.stdout.strip().splitlines()[-1])

    def refused(self, out, word):
        self.assertIsNone(out["dir"])
        self.assertFalse(out["store"])
        self.assertIn(word, out["why"] or "")
        self.assertFalse(os.path.exists(self.real), os.listdir(os.path.dirname(self.real)))

    def test_a_process_that_only_imports_the_module_never_writes_the_players_file(self):
        self.refused(self.child(), "not the launcher itself")

    def test_a_launcher_started_with_a_testing_option_never_writes_it(self):
        self.refused(self.child(declare=True, root=self.install), "not the launcher itself")

    def test_a_launcher_in_the_source_tree_never_writes_it(self):
        self.refused(self.child(declare=False), "source tree")             # ROOT = this checkout
        fake = os.path.join(self.dir, "checkout")
        os.makedirs(os.path.join(fake, ".git"))
        self.refused(self.child(declare=False, root=fake), "source tree")

    def test_a_launcher_unpacked_in_the_temporary_folder_never_writes_it(self):
        inside = os.path.join(self.tmp, "smoke", "T5DR-Online-1.2.3")
        os.makedirs(inside)
        self.refused(self.child(declare=False, root=inside), "temporary folder")

    def test_a_launcher_started_by_a_test_or_ci_never_writes_it(self):
        for env in ({"CI": "true"}, {"T5DR_TESTING": "1"}, {"T5_FW_CHECK": "0"}, {"T5DR_FW_CHECK": "0"},
                    {"PYTEST_CURRENT_TEST": "x"}):
            with self.subTest(env=env):
                self.refused(self.child(env, declare=False, root=self.install), next(iter(env)))

    def test_the_refusal_is_in_the_launchers_log(self):
        self.child()
        with open(os.path.join(self.install, "launcher.log"), encoding="utf-8") as f:
            self.assertIn("shared settings file is not used", f.read())

    def test_the_players_own_launcher_uses_it(self):
        out = self.child(declare=False, root=self.install)                 # (the guard is not "never")
        self.assertIsNone(out["why"])
        self.assertTrue(out["store"])
        self.assertEqual(os.path.normcase(out["dir"]), os.path.normcase(self.real))
        self.assertTrue(os.path.isfile(os.path.join(self.real, "settings.json")))

    def test_a_named_folder_is_used_by_any_process_and_the_players_stays_untouched(self):
        own = os.path.join(self.dir, "own")
        for name in ("T5_SETTINGS_DIR", "T5_ONLINE_DIR"):
            with self.subTest(name=name):
                out = self.child({name: own})
                self.assertTrue(out["store"])
                self.assertEqual(os.path.normcase(out["dir"]), os.path.normcase(own))
                self.assertFalse(os.path.exists(self.real))
        self.assertTrue(os.path.isfile(os.path.join(own, "settings.json")))

    def test_switched_off_wins_over_everything(self):
        out = self.child({"T5_SETTINGS_SHARED": "0"}, declare=False, root=self.install)
        self.assertFalse(out["store"])
        self.assertFalse(os.path.exists(self.real))


class Entry(unittest.TestCase):
    def test_the_launchers_main_declares_itself_before_the_window_is_made(self):
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            main = f.read().split("\ndef main():", 1)[1].split("\ndef ", 1)[0]
        call = re.search(r"core\.declare_launcher\(testing=bool\(([^)]*)\)\)", main, re.S)
        self.assertTrue(call)
        self.assertLess(main.index("core.declare_launcher"), main.index("App("))
        for option in ("screenshots", "build_steps", "low_priority", "play_seconds", "force"):
            self.assertIn("a." + option, call.group(1))

    def test_nothing_else_declares_a_launcher(self):
        hits = []
        for folder in ("launcher", "tools", "lobby"):
            for base, _dirs, files in os.walk(os.path.join(ROOT, folder)):
                for name in files:
                    if name.endswith((".py", ".pyw")):
                        with open(os.path.join(base, name), encoding="utf-8", errors="replace") as f:
                            if "declare_launcher(" in f.read():
                                hits.append(name)
        self.assertEqual(sorted(hits), ["core.py", "t5dr_launcher.pyw"])


if __name__ == "__main__":
    unittest.main()
