"""The launcher's Online tab driven like a player would, against a real server and a second
(plain) client: guest login, quick match, accept, the game starts with the handed-over
environment, the game closes, "I won", and the confirmed result shows up. TkT6Test: the Tekken 6
style extras in the tab (blind accept with the ping, strict option, block button and list,
lag check with its way out, server notice in the status bar, no IP address in a status line)."""
import gc
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

    def stop(self):
        self.done = True


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
        self.reports = 0

    def game_state(self):
        return {"ok": True}

    def start_game(self, env):
        g = FakeGame(env)
        self.games.append(g)
        return g

    def set_status(self, text):
        self.statuses.append(text)

    def report_problem(self):                    # the launcher's "Report a problem" window
        self.reports += 1


def hidden_window(parent):
    """A Toplevel that is never shown (the tests read and click its widgets all the same)."""
    w = tk.Toplevel(parent)
    w.withdraw()
    return w


@unittest.skipIf(tk is None, "no tkinter")
class TkBase(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        import tempfile
        self.s = ServerThread(**self.server_cfg).start()
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.s.stop()
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        # Never the real Windows clipboard: "Host for friends" copies the server line to it, and the person
        # at this PC may be copying something of their own. The root gets an in-memory clipboard.
        self._clip = []
        self.root.clipboard_clear = lambda **kw: self._clip.clear()
        self.root.clipboard_append = lambda text, **kw: self._clip.append(text)
        self.root.clipboard_get = lambda **kw: "".join(self._clip)
        self.dir = tempfile.mkdtemp()
        os.environ["T5_ONLINE_DIR"] = os.path.join(self.dir, "user")   # per-user settings: a fresh folder
        self.app = FakeApp(self.dir)
        self.tab = OnlineTab(self.root, self.app)
        self.tab._build_info = lambda: (BUILD, None)
        # Nothing appears on the screen: the tab's own windows (recovery codes, blocked players) are made
        # hidden, and its questions are answered here unless a test answers them itself.
        self.tab.new_window = hidden_window
        self.tab.ask_string = lambda *a, **k: None
        self.tab.ask_yes_no = lambda *a, **k: False
        self.fronted = []                       # the window never really comes forward in a test
        self.tab.bring_forward = lambda w: self.fronted.append(w)
        self.game_fronted = []                  # nor the game's
        self.tab.bring_game_forward = lambda pid: self.game_fronted.append(pid)
        self.other = None

    def tearDown(self):
        self.tab.on_close()
        if self.other:
            self.other.close()
        self.root.destroy()
        self.s.stop()
        # Drop every Tk object here, on the main thread: otherwise the cyclic GC may finalize the
        # previous test's Tk interpreter on a lobby worker thread, and Tcl aborts the process
        # ("Tcl_AsyncDelete: async handler deleted by the wrong thread").
        self.tab = self.root = None
        gc.collect()

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



@unittest.skipIf(tk is None, "no tkinter")
class TkTabTest(TkBase):
    def test_quick_match_flow(self):
        tab = self.tab
        self.assertEqual(tab.name_var.get(), "TabUser")       # from the launcher's nickname
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: str(tab.actions["quick"].cget("state")) == "normal")
        self.assertEqual(str(tab.actions["ranked"].cget("state")), "disabled")   # guests: no ranked
        self.assertEqual(tab.report_btn.winfo_manager(), "")       # "Report a problem" comes after a match

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
        self.assertEqual(tab.report_btn.winfo_manager(), "pack")   # now offered, next to the match line
        tab.report_btn.invoke()
        self.assertEqual(self.app.reports, 1)

    def test_the_connection_ends_in_the_middle_of_the_events(self):
        """The lobby drops the tab while more events wait in its queue (build/e2e finding, old UI): the poll
        stops at "disconnected" instead of reading the next event from a client that is gone, and the tab
        shows the login screen with the error."""
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        c = tab.client
        try:
            c.events.put({"t": "disconnected", "reason": "test"})
            c.events.put({"t": "chat", "from": {"name": "Late"}, "text": "still here?"})
            tab._poll()                                     # (an exception here is what the launcher logged)
            self.assertIsNone(tab.client)
            self.assertIn("Lost the connection to the lobby server", tab.view.err_var.get())
            self.root.update()
            self.assertEqual(tab.view.scr_login.winfo_manager(), "grid")
            tab._poll()                                     # and the next poll is quiet too
        finally:
            c.close()

    def texts_under(self, widget):
        out = []
        for w in widget.winfo_children():
            try:
                out.append(str(w.cget("text")))
            except tk.TclError:
                pass
            out += self.texts_under(w)
        return out

    def test_after_the_match_the_window_comes_forward_once(self):
        """The game waits at character select after a match (pads neutral, for the launcher's next command):
        the launcher comes forward with the result card, which says so -- once, never during the match;
        the opponent's rematch question brings it forward again."""
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        tab.actions["quick"].invoke()
        self.other.quick_match()
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        self.pump(lambda: tab.view._stage == "match")
        self.assertEqual(self.fronted, [])                                    # not during the match
        g = self.app.games[0]
        slot = 0 if g.env["T5_NET_MODE"] == "host" else 1
        import json
        with open(g.env["T5_NET_RESULT_FILE"], "w") as f:                    # the game writes its result and
            json.dump({"winner": slot, "score": [3, 1] if slot == 0 else [1, 3]}, f)   # stays open (waits)
        self.other.report_result(slot, [3, 1] if slot == 0 else [1, 3])
        self.pump(lambda: tab.last_result is not None)
        self.root.update()
        self.assertEqual(self.fronted, [tab.parent])                          # once
        self.assertTrue(tab.view.game_waits())
        self.assertIn("The game waits here for your next match: Rematch, Next game or Leave.",
                      self.texts_under(tab.view.bar_visual))
        for _ in range(5):
            tab._poll()
        self.assertEqual(len(self.fronted), 1)                                # still once
        ev = expect(self.other, "match_result")
        self.other.rematch(ev["match"], True)                                 # the opponent asks: a decision
        self.pump(lambda: len(self.fronted) == 2)

    def test_the_game_comes_forward_when_its_match_starts_and_the_launcher_is_in_front(self):
        tab = self.tab

        class Game:
            proc = type("P", (), {"pid": 4242})()

            def running(self):
                return True
        self.app.game = Game()
        front = [True]
        tab.launcher_in_front = lambda: front[0]
        tab.on_driver({"kind": "game_state", "state": "title", "match": 1})
        self.assertEqual(self.game_fronted, [])                       # booting: not yet
        tab.on_driver({"kind": "game_state", "state": "pick", "match": 1})
        tab.on_driver({"kind": "game_state", "state": "loading", "match": 1})
        tab.on_driver({"kind": "game_state", "state": "fight", "match": 1})
        self.assertEqual(self.game_fronted, [4242])                   # once per match
        front[0] = False
        tab.on_driver({"kind": "game_state", "state": "loading", "match": 2})
        self.assertEqual(self.game_fronted, [4242])                   # another program in front: never
        front[0] = True
        self.app.settings["background"] = True
        tab.on_driver({"kind": "game_state", "state": "fight", "match": 3})
        self.assertEqual(self.game_fronted, [4242])                   # "start minimized" (tests): never
        self.app.settings["background"] = False
        tab.on_driver({"kind": "game_state", "state": "pick", "match": 4})
        self.assertEqual(self.game_fronted, [4242, 4242])

    def test_never_forward_while_a_match_is_on(self):
        import types
        tab = self.tab
        tab.driver = types.SimpleNamespace(ticket=object(), game_state="fight", close=lambda: None)
        tab._come_forward(("result", "m1"))
        tab.driver.game_state = "loading"
        tab._come_forward(("result", "m1"))
        self.assertEqual(self.fronted, [])
        tab.driver.ticket = None                                              # the match is over
        tab._come_forward(("result", "m1"))
        tab._come_forward(("result", "m1"))
        self.assertEqual(self.fronted, [tab.parent])
        tab.driver = None

    def test_a_withdrawn_window_is_not_shown(self):
        from t5lobby import winfront
        w = hidden_window(self.root)
        self.assertFalse(winfront.raise_window(w))
        self.assertEqual(w.state(), "withdrawn")
        w.destroy()

    def test_the_tests_never_touch_the_real_clipboard(self):
        for name in ("clipboard_clear", "clipboard_append", "clipboard_get"):
            self.assertIn(name, vars(self.root), f"{name} must be the in-memory stand-in (TkBase.setUp)")

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

    def test_host_for_friends(self):
        import tempfile
        tab = self.tab
        tab.host_args = ["--data", tempfile.mkdtemp(), "--port", "0", "--status-port", "0"]
        tab.do_host()
        self.pump(lambda: tab.host_info is not None, timeout=60)
        server = tab.server_var.get()
        self.assertTrue(server.startswith("127.0.0.1:") and "#" in server, server)   # pinned TLS to itself
        self.assertIn(tab.host_info["fingerprint"], self.root.clipboard_get())
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        tab.do_logout()
        tab.do_host()                                         # the same button stops it
        self.pump(lambda: tab.host_proc is None, timeout=20)
        self.assertEqual(str(tab.b_host.cget("text")), "Host for friends")


@unittest.skipIf(tk is None, "no tkinter")
class TkT6Test(TkBase):
    server_cfg = {"blind_ready": True, "ready_timeout": 8.0}

    def login_guest(self, name="TabUser"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)

    def login_account(self, name="Ranker"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.pw_var.set("secret-pw1")
        tab.ask_string = lambda *a, **k: "secret-pw1"
        tab.do_login("register")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: tab.codes_window is not None)
        tab.codes_window.destroy()
        self.pump(lambda: str(tab.actions["ranked"].cget("state")) == "normal")

    def ranked_result(self):
        """The tab (an account) and Rival play one ranked match; the bar then offers the rematch."""
        tab = self.tab
        self.login_account()
        self.other = client(self.s, "Rival", password="rival-pw1", register=True, auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        tab.char_var.set("Lili")
        tab.on_char()
        tab.actions["ranked"].invoke()
        self.other.ranked_match()
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.assertEqual(str(tab.char_cb.cget("state")), "disabled")        # a ranked set locks the character
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        slot = 0 if self.app.games[0].env["T5_NET_MODE"] == "host" else 1
        self.app.games[0].done = True
        self.pump(lambda: self.bar_button("I won") is not None)
        self.bar_button("I won").invoke()
        self.other.report_result(slot, None)
        self.pump(lambda: self.bar_button("Rematch Rival") is not None)

    def test_blind_accept_shows_the_ping_then_the_name(self):
        tab = self.tab
        self.login_guest()
        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        tab.actions["quick"].invoke()
        self.other.quick_match()
        self.pump(lambda: self.bar_button("Accept") is not None)
        text = tab.bar_text.get()
        self.assertNotIn("Rival", text)                                      # the name is still hidden
        self.assertRegex(text, r"ping about \d+ ms")
        self.assertRegex(text, r"accept within \d+ s")
        self.pump(lambda: tab.bar_text.get() != text, timeout=3)             # the countdown runs
        self.bar_button("Accept").invoke()
        self.pump(lambda: "Opponent: Rival" in tab.bar_text.get())           # revealed after both accepted
        self.pump(lambda: len(self.app.games) == 1)
        self.assertIn("Rival", tab.match_var.get())

    def test_decline_in_the_blind_bar(self):
        tab = self.tab
        self.login_guest()
        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        tab.actions["quick"].invoke()
        self.other.quick_match()
        self.pump(lambda: self.bar_button("Decline") is not None)
        self.bar_button("Decline").invoke()
        self.pump(lambda: "declined" in tab.status_var.get().lower())
        self.assertNotIn("Rival", tab.status_var.get())

    def test_strict_checkbox_goes_with_the_ranked_request(self):
        tab = self.tab
        self.login_account()
        tab.strict_check.invoke()                                            # on (and saved)
        self.assertTrue(tab.cfg["strict"])
        path = os.path.join(os.environ["T5_ONLINE_DIR"], "online.json")
        for _ in range(5):                                                   # (a virus scanner can hold the file for a moment)
            with open(path) as f:
                if '"strict": true' in f.read():
                    break
            time.sleep(0.2)
            tab._save_cfg()
        else:
            self.fail("the strict option was not saved")
        tab.actions["ranked"].invoke()
        self.pump(lambda: self.s.call(lambda: self.s.srv.by_name["ranker"].strict))
        self.pump(lambda: str(tab.actions["cancel"].cget("state")) == "normal")      # (once the lobby list says "searching")
        tab.actions["cancel"].invoke()
        self.pump(lambda: str(tab.actions["ranked"].cget("state")) == "normal")
        tab.strict_check.invoke()                                            # off again
        tab.actions["ranked"].invoke()
        self.pump(lambda: self.s.call(lambda: self.s.srv.by_name["ranker"].status) == "queue")
        self.assertFalse(self.s.call(lambda: self.s.srv.by_name["ranker"].strict))

    def test_block_the_opponent_after_the_game_and_unblock_in_the_list(self):
        tab = self.tab
        self.ranked_result()
        asked = []
        tab.ask_yes_no = lambda *a, **k: asked.append(a) or True
        self.bar_button("Block Rival").invoke()
        self.pump(lambda: [r["name"] for r in tab.client.blocks()] == ["Rival"])
        self.assertIn("Block Rival?", asked[0][1])
        self.assertEqual(tab.bar.winfo_manager(), "")                        # the rematch bar is gone
        self.pump(lambda: str(tab.char_cb.cget("state")) == "readonly")      # ... and so is the set: the character is free
        # the list under "Blocked players..." and Unblock
        tab.do_blocked()
        self.pump(lambda: tab.blocks_window is not None)
        tab.blocks_list.selection_set(0)
        unblock = [w for f in tab.blocks_window.winfo_children() for w in f.winfo_children()
                   if getattr(w, "cget", None) and w.winfo_class() == "TButton" and w.cget("text") == "Unblock"]
        unblock[0].invoke()
        self.pump(lambda: tab.client.blocks() == [])
        tab.blocks_window.destroy()

    def test_lag_check_in_the_tab_and_leaving_without_penalty(self):
        tab = self.tab
        self.ranked_result()
        mid = tab.driver.last["match"]
        rating = self.s.call(lambda: self.s.srv.by_name["ranker"].rating.r)
        # both games report; the lobby answers with the same numbers for both players
        tab.client.report_lag(mid, 3000, 3000 * 40.0, 60.0)
        self.other.report_lag(mid, 3000, 3000 * 40.0, 60.0)
        self.pump(lambda: "Lag check: Ping" in tab.match_var.get())
        self.assertIn("should mean about", tab.match_var.get())
        self.assertIn("more than the ping explains", tab.match_var.get())
        leave = self.bar_button("Leave: too laggy")                          # only offered when it was worse
        self.assertIsNotNone(leave)
        self.assertIsNotNone(self.bar_button("Rematch Rival"))               # ... next to the rematch: nothing ends by itself
        leave.invoke()
        self.pump(lambda: "No penalty" in tab.status_var.get())
        self.assertEqual(self.s.call(lambda: self.s.srv.by_name["ranker"].rating.r), rating)
        self.assertEqual(str(tab.char_cb.cget("state")), "readonly")

    def test_a_good_lag_check_offers_no_way_out(self):
        tab = self.tab
        self.ranked_result()
        mid = tab.driver.last["match"]
        tab.client.report_lag(mid, 3000, 3000 * 1.0, 60.0)
        self.other.report_lag(mid, 3000, 3000 * 1.0, 60.0)
        self.pump(lambda: "That is what the ping explains" in tab.match_var.get())
        self.assertIsNone(self.bar_button("Leave: too laggy"))

    def test_server_notice_stays_in_the_status_bar(self):
        tab = self.tab
        self.login_guest()
        text = "server restart in 20 min"
        self.s.call(lambda: self.s.srv.store.add_notice(text, time.time() + 600))
        self.s.call(lambda: self.s.srv.poll_notices())
        self.pump(lambda: text in tab.notice_var.get())
        self.assertTrue(any(text in st for st in self.app.statuses))
        tab.status("Searching for an opponent...")                           # other messages do not push it out
        self.assertIn(f"[Server: {text}]", self.app.statuses[-1])
        self.s.call(lambda: self.s.srv.store.clear_notices())
        self.s.call(lambda: self.s.srv.poll_notices())
        self.pump(lambda: tab.notice_var.get() == "")
        tab.status("Searching for an opponent...")
        self.assertNotIn("Server:", self.app.statuses[-1])

    def test_no_address_in_a_status_line(self):
        tab = self.tab
        tab.status("could not reach 203.0.113.7:61000 or 2001:db8::7")
        for shown in (tab.status_var.get(), self.app.statuses[-1]):
            self.assertNotIn("203.0.113", shown)
            self.assertNotIn("2001:db8", shown)
            self.assertIn("(address hidden)", shown)
        self.login_guest()
        tab.on_event({"t": "notice", "code": "nat_error", "msg": "OSError: sendto 198.51.100.4 failed"})
        self.assertNotIn("198.51.100.4", tab.status_var.get())


if __name__ == "__main__":
    unittest.main()
