"""Online boot presentation launch policy, without a game or a server."""
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lobby"))
from t5lobby import spectate


class OnlineBootLaunchTest(unittest.TestCase):
    def test_live_spectator_explicitly_enables_online_cover(self):
        env = spectate.watch_env("stream.t5r", controls=False, buffer_frames=120)
        self.assertEqual(env["T5_ONLINE_FAST_BOOT"], "1")
        self.assertEqual(env["T5_NET_MODE"], "replay")
        self.assertEqual(env["T5_REPLAY_FILE"], os.path.abspath("stream.t5r"))
        self.assertEqual(env["T5_REPLAY_CONTROLS"], "0")
        self.assertEqual(env["T5_REPLAY_LIVE_BUFFER"], "120")

    def test_saved_replay_does_not_opt_into_online_cover(self):
        # Inspect the launcher env factory without reading a replay or starting
        # its UI. The shared replay mode alone must not imply an online boot.
        import ast
        source = (ROOT / "launcher/replays.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        factory = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "playback_env")
        strings = {n.value for n in ast.walk(factory) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertNotIn("T5_ONLINE_FAST_BOOT", strings)


if __name__ == "__main__":
    unittest.main()
