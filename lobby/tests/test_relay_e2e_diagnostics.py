"""Exercise relay E2E child handling without starting a server or opening a socket."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lobby", "tools"))
import relay_e2e


class Client:
    def __init__(self, slot):
        self.me = {"name": "synthetic peer"}
        self.relay_rtts = {}
        ticket = types.SimpleNamespace(slot=slot, game_env=lambda **kw: {})
        self.start = {"t": "match_start", "match": "synthetic", "slot": slot,
                      "relay": {"id": "usw"}, "path": "relay", "rtt_ms": 160,
                      "ticket": ticket}

    def quick_match(self):
        pass

    def next_event(self, *args):
        return self.start


class ChildFailures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="relay-diagnostics-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.args = types.SimpleNamespace(verbose=False, exe=None, seconds=0)

    def write_child(self, source):
        with open(os.path.join(self.temp.name, "stub_game.py"), "w", encoding="utf-8") as f:
            f.write(source)

    def play(self):
        relay_e2e.play_match(None, [Client(0), Client(1)], self.args,
                            os.path.join(self.temp.name, "output"), "usw", 160)

    def test_failed_handshake_reports_exit_codes_and_bounded_log_tails(self):
        self.write_child("import sys\nprint('unneeded prefix ' * 1000)\n"
                         "print('waiting for the opponent: nothing arrived yet')\n"
                         "print('no peer within 20s')\nsys.exit(7)\n")
        out = io.StringIO()
        with mock.patch.object(relay_e2e, "HERE", self.temp.name), \
                contextlib.redirect_stdout(out), \
                self.assertRaisesRegex(AssertionError, "did not connect"):
            self.play()
        text = out.getvalue()
        self.assertIn("exit 7", text)
        self.assertIn("waiting for the opponent: nothing arrived yet", text)
        self.assertIn("no peer within 20s", text)
        self.assertLess(len(text), 10000, "failure output must stay bounded")

    def test_second_launch_failure_reaps_first_child_and_closes_logs(self):
        self.write_child("import time\nprint('synthetic child waiting', flush=True)\ntime.sleep(60)\n")
        real_popen = subprocess.Popen
        children, logs = [], []

        def launch(*args, **kw):
            logs.append(kw["stdout"])
            if children:
                raise OSError("synthetic second launch failure")
            child = real_popen(*args, **kw)
            children.append(child)
            return child

        try:
            with mock.patch.object(relay_e2e, "HERE", self.temp.name), \
                    mock.patch.object(relay_e2e.subprocess, "Popen", side_effect=launch), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    self.assertRaisesRegex(OSError, "synthetic second launch failure"):
                self.play()
            self.assertIsNotNone(children[0].poll(), "first child survived the failed second launch")
            self.assertTrue(all(f.closed for f in logs), "a child log remained open")
        finally:
            # Independent cleanup also bounds the regression against the old implementation.
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)
            for f in logs:
                f.close()


if __name__ == "__main__":
    unittest.main()
