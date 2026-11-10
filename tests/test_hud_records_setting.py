"""Settings -> "Show win records in online matches" (1.2.3, lobby/t5lobby/server/records.py): on by default, saved,
wired into the settings page, and sent to the server by the Online tab when it changes."""
import ast
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("launcher", "lobby"):
    if os.path.join(ROOT, sub) not in sys.path:
        sys.path.append(os.path.join(ROOT, sub))
import core  # noqa: E402
from t5lobby import tk_tab  # noqa: E402

TEXT = "Show win records in online matches (wins, losses and win rate on the select and VS screens)"


class SettingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "launcher.json")

    def test_on_by_default_and_saved(self):
        self.assertIs(core.Settings(self.path)["hud_records"], True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"spectators": False}, f)                    # an older launcher's file
        self.assertIs(core.Settings(self.path)["hud_records"], True)
        s = core.Settings(self.path)
        s["hud_records"] = False
        s.save()
        self.assertIs(core.Settings(self.path)["hud_records"], False)

    def test_settings_page_offers_and_saves_it(self):
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        texts = [n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "t" and n.args and isinstance(n.args[0], ast.Constant)]
        self.assertIn(TEXT, texts)
        save = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "save_settings")
        self.assertTrue(any(isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store)
                            and isinstance(n.slice, ast.Constant) and n.slice.value == "hud_records"
                            for n in ast.walk(save)))


class FakeClient:
    def __init__(self):
        self.sent = []

    def set_record_prefs(self, show):
        self.sent.append(show)


class TabTickTests(unittest.TestCase):
    """OnlineTab._records_tick without a window: the choice goes to the client once per change."""

    def tab(self, settings):
        t = tk_tab.OnlineTab.__new__(tk_tab.OnlineTab)
        t.app = type("App", (), {"settings": settings})()
        t.client = FakeClient()
        t._record_pref = True
        t.call = lambda fn, *a, **kw: fn(*a)
        return t

    def test_change_is_sent_once(self):
        s = {"hud_records": True}
        t = self.tab(s)
        t._records_tick()
        self.assertEqual(t.client.sent, [])
        s["hud_records"] = False
        t._records_tick()
        t._records_tick()
        self.assertEqual(t.client.sent, [False])
        s.pop("hud_records")                                         # (missing = on)
        t._records_tick()
        self.assertEqual(t.client.sent, [False, True])


if __name__ == "__main__":
    unittest.main()
