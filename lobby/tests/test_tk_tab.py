"""The launcher's Online tab driven like a player would, against a real server and a second
(plain) client: guest login, quick match, accept, the game starts with the handed-over
environment, the game closes, "I won", and the confirmed result shows up."""
import os
import time
import unittest

import util
from util import BUILD, ServerThread, client, expect

try:
    import tkinter as tk
    from t5lobby.tk_tab import OnlineTab
except ImportError:      # pragma: no cover
    tk = None


class FakeGame:
    def __init__(self, env):
        self.env = env
        self.done = False
        self.proc = None

    def running(self):
        return not self.done


class FakeSettings(dict):
    def __init__(self, d):
        super().__init__(nickname="TabUser")
        self.path = os.path.join(d, "launcher.json")
        self.out_dir = d


class FakeApp:
    def __init__(self, d):
        self.settings = FakeSettings(d)
        self.games = []
        self.statuses = []

    def game_state(self):
        return {"ok": True}

    def start_game(self, env):
        g = FakeGame(env)
        self.games.append(g)
        return g

    def set_status(self, text):
        self.statuses.append(text)


@unittest.skipIf(tk is None, "no tkinter")
class TkTabTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.s = ServerThread().start()
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.s.stop()
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.dir = tempfile.mkdtemp()
        self.app = FakeApp(self.dir)
        self.tab = OnlineTab(self.root, self.app)
        self.tab._build_info = lambda: (BUILD, None)
        self.other = None

    def tearDown(self):
        self.tab.on_close()
        if self.other:
            self.other.close()
        self.root.destroy()
        self.s.stop()

    def pump(self, cond, timeout=15.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            self.root.update()
            if cond():
                return True
            time.sleep(0.02)
        self.fail(f"timed out; status: {self.tab.status_var.get()!r}")

    def bar_button(self, label):
        for w in self.tab.bar_buttons.winfo_children():
            if w.cget("text") == label:
                return w
        return None

    def test_quick_match_flow(self):
        tab = self.tab
        self.assertEqual(tab.name_var.get(), "TabUser")       # from the launcher's nickname
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: str(tab.actions["quick"].cget("state")) == "normal")
        self.assertEqual(str(tab.actions["ranked"].cget("state")), "disabled")   # guests: no ranked

        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        tab.actions["quick"].invoke()
        self.other.quick_match()
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.assertIn("Rival", tab.bar_text.get())
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        env = self.app.games[0].env
        for k in ("T5_NET_MODE", "T5_NET_PORT", "T5_NET_PEER", "T5_NET_DELAY", "T5_NET_RESULT_FILE"):
            self.assertIn(k, env)
        ev = expect(self.other, "match_start")
        self.assertEqual(env["T5_NET_PORT"], str(ev["ticket"].peer[1]))   # the rival's peer is our port
        my_slot = 0 if env["T5_NET_MODE"] == "host" else 1

        self.app.games[0].done = True                        # the player closes the game
        self.pump(lambda: self.bar_button("I won") is not None)
        self.bar_button("I won").invoke()
        self.other.report_result(my_slot, None)
        self.pump(lambda: "Result confirmed" in tab.status_var.get())
        self.assertIn("1W 0L", tab.me_var.get())

    def test_result_file_is_reported_automatically(self):
        import json
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Filer")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        tab.tv_players.selection_set(self.other.me["id"])
        tab.do_challenge()
        ev = expect(self.other, "challenged")
        self.other.answer_challenge(ev["challenge"], True)
        self.pump(lambda: len(self.app.games) == 1)
        env = self.app.games[0].env
        with open(env["T5_NET_RESULT_FILE"], "w") as f:
            json.dump({"winner": 1, "score": [2, 3]}, f)     # the game says P2 won 3-2
        self.app.games[0].done = True
        self.other.report_result(1, [2, 3])
        self.pump(lambda: "Result confirmed" in tab.status_var.get())


if __name__ == "__main__":
    unittest.main()
