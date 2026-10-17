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
        os.environ["T5_ONLINE_DIR"] = os.path.join(self.dir, "user")   # per-user settings: a fresh folder
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

    def test_login_error_shows_in_status(self):
        self.other = client(self.s, "TabUser")
        self.tab.server_var.set(self.s.addr)
        self.tab.do_login("guest")
        self.pump(lambda: "someone with that name is online" in self.tab.status_var.get())
        self.assertIsNone(self.tab.client)
        self.assertEqual(str(self.tab.b_guest.cget("state")), "normal")

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

    def test_account_remembered_login_and_ranked(self):
        """Create an account: recovery codes are shown once, the saved login (a token, never the
        password) logs a new launcher session in by itself, ranked is open to accounts."""
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Ranker")
        tab.pw_var.set("secret-pw1")
        tab.ask_string = lambda *a, **k: "secret-pw1"            # "type the password again"
        tab.char_var.set("Lili")
        tab.do_login("register")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: tab.codes_window is not None)
        self.assertEqual(tab.pw_var.get(), "")
        self.pump(lambda: str(tab.actions["ranked"].cget("state")) == "normal")
        self.pump(lambda: self.s.call(lambda: self.s.srv.by_name["ranker"].char) == "lili")
        cfg_path = os.path.join(os.environ["T5_ONLINE_DIR"], "online.json")
        with open(cfg_path) as f:
            saved = f.read()
        self.assertNotIn("secret-pw1", saved)
        self.assertIn('"token"', saved)
        self.assertIn('"char": "lili"', saved)
        tab.codes_window.destroy()
        tab.on_close()
        # a new launcher start: the Online tab logs in with the saved login
        tab2 = OnlineTab(self.root, self.app)
        tab2._build_info = lambda: (BUILD, None)
        tab2.on_show()
        self.pump(lambda: tab2.client is not None and tab2.client.me is not None)
        self.assertEqual(tab2.client.me["name"], "Ranker")
        self.assertIn("saved login", tab2.status_var.get())
        tab2.ask_yes_no = lambda *a, **k: True                  # log out and forget the saved login
        tab2.do_logout()
        with open(cfg_path) as f:
            self.assertNotIn('"token"', f.read())
        self.tab = tab2

    def test_no_password_to_a_public_server_without_tls(self):
        from unittest import mock
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Careful")
        tab.pw_var.set("secret-pw1")
        with mock.patch("t5lobby.client.is_local_address", return_value=False):
            tab.do_login("account")
            self.pump(lambda: "no encryption" in tab.status_var.get())
            self.assertIsNone(tab.client)
            tab.do_login("guest")                                # guests still work
            self.pump(lambda: tab.client is not None and tab.client.me is not None)

    def test_leaderboard_and_profile_tabs(self):
        tab = self.tab
        a = client(self.s, "Champ", password="champ-pw1", register=True, auto_ready=True)
        b = client(self.s, "Chump", password="chump-pw1", register=True, auto_ready=True)
        self.other = a
        try:
            a.ranked_match()
            b.ranked_match()
            ea = expect(a, "match_start")
            a.report_result(ea["slot"], None)
            b.report_result(ea["slot"], None)
            expect(a, "match_result")
        finally:
            b.close()
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Viewer")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        tab.nb.select(1)
        tab.load_leaderboard()
        self.pump(lambda: len(tab.tv_board.get_children()) == 2)
        self.assertEqual(tab.tv_board.item(tab.tv_board.get_children()[0], "values")[1].replace("  *", ""), "Champ")
        tab.show_profile("Champ")
        self.pump(lambda: "Champ" in tab.prof_title.get())
        self.pump(lambda: len(tab.tv_hist.get_children()) == 1)
        self.assertIn("Beginner", tab.prof_title.get())


if __name__ == "__main__":
    unittest.main()
