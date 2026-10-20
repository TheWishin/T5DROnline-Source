"""Settings -> Discord is shown only when this copy has a Discord application id (lobby/t5lobby/data/discord.json,
or a developer's own: settings "discord_app_id", T5_DISCORD_APP_ID). Without one Rich Presence can do nothing, so
the launcher offers no such setting (no dead switch). The real launcher is built withdrawn (tests/i18n_layout.py).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tests"))

try:
    import tkinter as tk

    import i18n_layout
    from t5lobby import discord_rpc
except ImportError:          # (no tkinter in this Python)
    tk = None

APP = "123456789012345678"


def labelframes(w):
    out = [w] if w.winfo_class() == "TLabelframe" else []
    for c in w.winfo_children():
        out += labelframes(c)
    return out


@unittest.skipIf(tk is None, "no tkinter")
class DiscordSettingTests(unittest.TestCase):
    def settings_tab(self, app_id, env_id=""):
        """The Settings tab's boxes with discord.json holding app_id (and T5_DISCORD_APP_ID = env_id)."""
        d = tempfile.mkdtemp(prefix="t5discord-")
        self.addCleanup(shutil.rmtree, d, True)
        cfg = os.path.join(d, "discord.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"application_id": app_id, "large_image": "", "large_text": "T5DR Online"}, f)
        found = {}

        def look(walk):
            app = walk.app
            boxes = [str(w.cget("text")).strip() for w in labelframes(app.settings_scroll.inner)]
            found.update(boxes=boxes, var=hasattr(app, "discord_var"))

        walk = i18n_layout.Walk("en", 100)
        with mock.patch.object(discord_rpc, "CONFIG_FILE", cfg), \
                mock.patch.dict(os.environ, {"T5_DISCORD_APP_ID": env_id}), \
                mock.patch.object(i18n_layout.Walk, "_launcher", look), \
                mock.patch.object(i18n_layout.Walk, "_online", lambda w: None), \
                mock.patch.object(i18n_layout.Walk, "_windows", lambda w, dd: None):
            try:
                walk.run()
            except tk.TclError as e:
                self.skipTest(f"no display for Tk: {e}")
        self.assertEqual(walk.shown, [])
        self.assertIn("Unlocks", found["boxes"])           # (the tab was really built)
        return found

    def test_no_application_id_no_discord_box(self):
        found = self.settings_tab("")
        self.assertNotIn("Discord", found["boxes"])
        self.assertFalse(found["var"])                      # and nothing saves a value for it

    def test_with_the_release_application_id_the_box_is_there(self):
        found = self.settings_tab(APP)
        self.assertIn("Discord", found["boxes"])
        self.assertTrue(found["var"])

    def test_a_developers_own_id_shows_it_too(self):
        found = self.settings_tab("", env_id=APP)
        self.assertIn("Discord", found["boxes"])


if __name__ == "__main__":
    unittest.main()
