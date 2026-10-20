"""The launcher and its Online tab walked through every state of the online flow -- and the launcher's
log stays clean: not one "error in the launcher" (an exception in a Tk callback) in any state.

A local lobby server, two CLI clients (python -m t5lobby.cli: a room owner, and a quick-match
opponent whose stand-in game plays against the tab's) and scripted clients: login errors, guest, the
lobby, searching, match found, accepted, in match, result, rematch (both ways), lag check, next
game, room, challenge, a game that closed without a result, errors, server notice, log out and in,
an account with its recovery codes, rank badge, ranked match and promotion, the ranked set's second
game, blocking, leaderboard, profile, the server going away, switching tabs all along, closing.
Also: the Play tab says that it is for offline play and leads to the Online tab.

Nothing is shown on the screen: the launcher window is withdrawn, the tab's own windows are hidden
ones, message boxes, file dialogs and the tab's questions are answered by the test.

    T5_UI_SHOTS=<dir>  also save a PNG of the launcher in each state (the window is then mapped, fully
                       transparent: run it on a desktop nobody looks at)
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOBBY = os.path.join(ROOT, "lobby")
if os.path.join(ROOT, "launcher") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "launcher"))
for p in (LOBBY, os.path.join(LOBBY, "tests")):          # appended: lobby/run.py must not hide tools' run modules
    if p not in sys.path:
        sys.path.append(p)
os.environ["T5_PAD_NAV"] = "0"                   # never this PC's controllers
os.environ["T5_FW_CHECK"] = "0"                  # never this PC's firewall (the hint's check: test_firewall.py)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ImportError:      # pragma: no cover
    tk = None

SHOTS = os.environ.get("T5_UI_SHOTS")
STUB = os.path.join(LOBBY, "tools", "stub_game.py")
NOWIN = 0x08000000 | 0x00004000                  # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS (Windows)


def load_launcher():
    path = os.path.join(ROOT, "launcher", "t5dr_launcher.pyw")
    spec = importlib.util.spec_from_loader("t5dr_launcher_walk", importlib.machinery.SourceFileLoader(
        "t5dr_launcher_walk", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeGame:
    """The game for scripted opponents: runs until the test ends it (with or without a result file).
    It looks like core.GameRun to the launcher (process exit code, last lines, fps)."""
    log_path = None
    fps = None
    last_lines = ()

    def __init__(self, env):
        self.env = env
        self.done = False
        self.started = time.time()
        self.proc = types.SimpleNamespace(returncode=0, pid=0)

    def running(self):
        return not self.done

    def stop(self):
        self.done = True

    def finish(self, winner_slot, score):
        with open(self.env["T5_NET_RESULT_FILE"], "w") as f:
            json.dump({"winner": winner_slot, "score": score}, f)
        self.done = True


class StubGame:
    """lobby/tools/stub_game.py: the netplay handshake with the opponent's stub, then a result file."""
    fps = None
    last_lines = ()

    def __init__(self, env, logdir):
        self.env = env
        self.started = time.time()
        self.log_path = os.path.join(logdir, f"stub-{time.time():.0f}.log")
        self._lf = open(self.log_path, "w")
        e = dict(os.environ, T5_STUB_SECONDS="4", T5_STUB_LINGER="20", **env)
        self.proc = subprocess.Popen([sys.executable, STUB], env=e, stdout=self._lf, stderr=self._lf,
                                     creationflags=NOWIN if os.name == "nt" else 0)

    def running(self):
        return self.proc.poll() is None

    def stop(self):
        if self.running():
            self.proc.kill()
        self._lf.close()


@unittest.skipIf(tk is None, "no tkinter")
class OnlineUiWalk(unittest.TestCase):
    def setUp(self):
        self._path = list(sys.path)            # (launcher/online.py puts lobby/ first: put the path back after)
        import util
        from t5lobby import dialogs, i18n
        self.util = util
        self.i18n = i18n
        self._lang = os.environ.get("T5_LANG")
        os.environ["T5_LANG"] = "en"                  # (the texts below are the English ones, whatever Windows says)
        self.dir = tempfile.mkdtemp(prefix="t5ui-walk-")
        os.environ["T5_ONLINE_DIR"] = os.path.join(self.dir, "online")    # never the player's online.json
        self.L = L = load_launcher()
        self._settings = real_settings = L.core.Settings          # (core is shared: put it back in tearDown)
        L.core.Settings = lambda: real_settings(os.path.join(self.dir, "launcher.json"))
        self._log = L.core.LAUNCHER_LOG
        L.core.LAUNCHER_LOG = os.path.join(self.dir, "launcher.log")
        # no worker threads looking at this PC (build tools, the user's Downloads folder, the build)
        L.App.refresh_prereqs = lambda app: None
        L.App.refresh_inputs = lambda app: None
        L.App.refresh_game_state = lambda app: app._show_game_state({"ok": True, "text": "Ready (test)."})
        # no dialog ever shows up
        self._patched = []
        for mod, names in ((messagebox, ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
                                         "askquestion", "askretrycancel", "askyesnocancel")),
                           (filedialog, ("askopenfilename", "asksaveasfilename", "askdirectory")),
                           (dialogs, ("ask_yes_no", "ask_yes_no_cancel", "show_info", "show_error", "ask_string"))):
            for n in names:
                self._patched.append((mod, n, getattr(mod, n)))
                setattr(mod, n, (lambda *a, **k: "") if mod is filedialog else (lambda *a, **k: False))
        try:
            self.app = L.App(offscreen=False)
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        if SHOTS:
            self.app.attributes("-alpha", 0.0)       # mapped (PrintWindow needs it) but invisible
        else:
            self.app.withdraw()
        # never the real clipboard ("Host for friends" copies to it)
        self._clip = []
        self.app.clipboard_clear = lambda **kw: self._clip.clear()
        self.app.clipboard_append = lambda text, **kw: self._clip.append(text)
        self.games = []
        self.game_kind = "fake"
        self.app.start_game = self.start_game
        self.app.game_state = lambda: {"ok": True}
        self.tab = self.app.online
        self.tab._build_info = lambda: (util.BUILD, None)
        self.tab.new_window = self.window
        self.tab.bring_forward = lambda w: None       # (the window never comes forward in a test)
        self.asked = []
        self.tab.ask_yes_no = lambda *a, **k: self.asked.append(a) or True
        self.tab.ask_string = lambda *a, **k: "secret-pw1"
        self.procs = []
        self.others = []
        self.files = []
        self.s = util.ServerThread(blind_ready=True, ready_timeout=15.0, rematch_window=40.0, result_timeout=3.0,
                                   lag_wait=3.0, reconnect_grace=1.0, set_next_seconds=5.0).start()
        self.n_shot = 0

    def tearDown(self):
        L = self.L
        for c in self.others:
            try:
                c.close()
            except Exception:
                pass
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait(10)
        for f in self.files:
            f.close()
        for g in self.games:
            g.stop()
        self.stop_server()
        try:                                     # no timer may fire into a window that is gone
            for aid in self.app.tk.splitlist(self.app.tk.call("after", "info")):
                self.app.tk.call("after", "cancel", aid)
        except tk.TclError:
            pass
        try:
            if self.app.winfo_exists():
                self.app.destroy()
        except tk.TclError:
            pass
        for mod, n, fn in self._patched:
            setattr(mod, n, fn)
        L.core.LAUNCHER_LOG = self._log
        L.core.Settings = self._settings
        if self._lang is None:
            os.environ.pop("T5_LANG", None)
        else:
            os.environ["T5_LANG"] = self._lang
        self.i18n.set_language("en")
        sys.path[:] = self._path
        self.app = self.tab = None
        import gc
        gc.collect()

    # ------------------------------------------------------------------ helpers
    def stop_server(self):
        if self.s is not None:
            s, self.s = self.s, None
            s.stop()

    def window(self, parent):
        w = tk.Toplevel(parent)
        if SHOTS:
            w.attributes("-alpha", 0.0)
        else:
            w.withdraw()
        return w

    def start_game(self, env):
        g = StubGame(env, self.dir) if self.game_kind == "stub" else FakeGame(env)
        self.games.append(g)
        self.app.game = g
        return g

    def pump(self, cond, timeout=20.0, what=""):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            self.app.update()
            try:
                if cond():
                    return
            except Exception:
                pass
            time.sleep(0.02)
        self.fail(f"timed out: {what}; status {self.tab.status_var.get()!r}")

    def wait(self, seconds):
        t_end = time.monotonic() + seconds
        while time.monotonic() < t_end:
            self.app.update()
            time.sleep(0.02)

    def shot(self, name, widget=None):
        if not SHOTS:
            self.app.update()
            return
        self.wait(0.4)
        self.n_shot += 1
        os.makedirs(SHOTS, exist_ok=True)
        try:
            self.L.capture_window(widget or self.app, os.path.join(SHOTS, f"{self.n_shot:02d}_{name}.png"))
        except Exception as e:      # noqa: BLE001 -- a picture is a bonus, the walk is the test
            print(f"shot {name} failed: {e}", file=sys.stderr)

    def bar_button(self, prefix):
        for w in self.tab.bar_buttons.winfo_children():
            if str(w.cget("text")).startswith(prefix):
                return w
        return None

    def status_of(self, name):
        return self.s.call(lambda: self.s.srv.by_name[name.lower()].status)

    def client(self, name, **kw):
        c = self.util.client(self.s, name, **kw)
        self.others.append(c)
        return c

    def cli(self, name, *args, env=None):
        b = self.util.BUILD
        lf = open(os.path.join(self.dir, f"cli-{name}.log"), "w")
        self.files.append(lf)
        cmd = [sys.executable, "-m", "t5lobby.cli", "--server", self.s.addr, "--name", name, "--code-id", b.code_id,
               "--elf-sha1", b.elf_sha1] + list(args)
        p = subprocess.Popen(cmd, cwd=LOBBY, stdout=lf, stderr=lf, creationflags=NOWIN if os.name == "nt" else 0,
                             env=dict(os.environ, PYTHONPATH=LOBBY, **(env or {})))
        self.procs.append(p)
        return p

    def flip_tabs(self):
        """Switch through every launcher tab and the Online tab's own tabs (while things are loading)."""
        app = self.app
        for key in ("build", "play", "settings", "online"):
            app.nb.select(app.tabs[key])
            app.update()
        for i in (1, 2, 0):
            self.tab.nb.select(i)
            app.update()

    def errors(self):
        try:
            with open(self.L.core.LAUNCHER_LOG, encoding="utf-8") as f:
                return [ln for ln in f.read().splitlines() if "error in the launcher" in ln or "Traceback" in ln]
        except OSError:
            return []

    def found(self, kind="ready"):
        return self.tab.view._stage == "bar" and self.tab.view._bar_kind == kind

    def finish_fake(self, winner_is_me, other, score_me=3, score_them=1):
        g = self.games[-1]
        slot = 0 if g.env["T5_NET_MODE"] == "host" else 1
        win = slot if winner_is_me else 1 - slot
        a, b = (score_me, score_them) if winner_is_me else (score_them, score_me)
        score = [a, b] if slot == 0 else [b, a]
        g.finish(win, score)
        other.report_result(win, score)

    # ------------------------------------------------------------------ the Play tab
    def test_play_tab_says_offline_and_leads_to_the_online_tab(self):
        app = self.app
        self.assertEqual(app.nb.tab(app.tabs["play"], "text").strip(), "Play offline")
        self.assertEqual(app.nb.tab(app.tabs["online"], "text").strip(), "Play online")
        self.assertEqual(str(app.play_btn.cget("text")), "PLAY OFFLINE")
        app.nb.select(app.tabs["play"])
        app.update()
        app.to_online_btn.invoke()
        app.update()
        self.assertEqual(app.nb.select(), str(app.tabs["online"]))
        self.assertEqual(self.errors(), [])

    # ------------------------------------------------------------------ the walk
    def test_every_state_and_the_log_stays_clean(self):
        app, tab, s = self.app, self.tab, self.s
        from test_padnav import FakeClock, FakePad
        app.nb.select(app.tabs["online"])
        app.update()
        self.flip_tabs()
        tab.server_var.set(s.addr)
        tab.name_var.set("Kaze")
        self.shot("login")
        tab.view.mode_var.set("register")
        tab.view._mode_changed()
        tab.pw_var.set("secret-pw1")
        tab.view.pw2_var.set("secret-pw")
        self.shot("create_account_rules")
        tab.view.mode_var.set("login")
        tab.view._mode_changed()

        # errors before logging in: a wrong password, a server that is not there
        tab.name_var.set("Ghost")
        tab.pw_var.set("not-my-pw")
        tab.do_login("account")
        self.flip_tabs()                                         # (switching tabs while it connects)
        self.pump(lambda: "wrong name or password" in tab.status_var.get(), 15, "wrong password")
        self.assertIn("Forgot password", tab.view.err_var.get())          # what to do
        self.shot("error_wrong_password")
        tab.server_var.set("127.0.0.1:1")
        tab.view.mode_var.set("guest")
        tab.view._mode_changed()
        tab.name_var.set("Kaze")
        tab.do_login("guest")
        self.pump(lambda: "cannot reach" in tab.status_var.get().lower(), 30, "connect error")
        self.assertIn("Check the server address", tab.view.err_var.get())
        self.shot("error_cannot_reach_server")
        tab.view.clear_error()
        tab.server_var.set(s.addr)
        self.shot("guest_login")

        # the lobby: a CLI room owner, players, a full room (the lock), another version
        mika = self.cli("Mika", "--room", "Friday night")
        dragon = self.client("Dragon", auto_ready=True)
        self.client("Oldie", build=self.util.OTHER_BUILD)
        nina = self.client("Nina", auto_ready=True)
        dragon.create_room("Late night")
        self.pump(lambda: s.call(lambda: any(r.name == "Late night" for r in s.srv.rooms.values())), 10)
        nina.join_room(s.call(lambda: [r.id for r in s.srv.rooms.values() if r.name == "Late night"][0]))
        self.pump(lambda: s.call(lambda: any(r.name == "Friday night" for r in s.srv.rooms.values())), 90,
                  "the CLI client's room (exit %s, log %s)" % (mika.poll(), os.path.join(self.dir, "cli-Mika.log")))
        tab.do_login("guest")
        self.flip_tabs()
        self.pump(lambda: tab.client is not None and tab.client.me is not None, 20, "guest login")
        clock, pad = FakeClock(), FakePad(name="Xbox controller")   # a fake pad: the (A) / (B) on the buttons
        tab.pad = None
        tab.pad_visible = lambda: True                           # (the window is withdrawn in the test)
        nav = tab.start_pad([pad], foreground=lambda: True, clock=clock, thread=False)
        for _ in range(30):
            nav.step(clock.t)
            clock.t += 1 / 60
        tab._pad_tick()
        self.pump(lambda: len(tab.tv_players.get_children()) >= 5 and len(tab.tv_rooms.get_children()) >= 2, 20,
                  "lobby lists (%d players, %d rooms)" % (len(tab.tv_players.get_children()),
                                                          len(tab.tv_rooms.get_children())))
        self.assertEqual(str(tab.actions["quick"].cget("text")), "Quick match (A)")
        tab.chat_line("Mika: anyone up for a few games?")
        self.shot("lobby_guest")

        # searching, a CLI opponent with the stand-in game: found, accepted, in match, result, rematch bar
        self.game_kind = "stub"
        tab.actions["quick"].invoke()
        self.pump(lambda: tab.view._stage == "search", 15, "searching")
        self.flip_tabs()
        self.wait(1.2)
        self.shot("searching")
        self.cli("Rival", "--quick", "--", sys.executable, STUB, env={"T5_STUB_SECONDS": "4"})
        self.pump(lambda: self.found("ready"), 90, "match found (the CLI client starts slowly on a busy PC)")
        self.assertIsNotNone(tab.view.ring)
        self.assertIn("Accept (A)", [str(w.cget("text")) for w in tab.bar_buttons.winfo_children()])
        self.wait(1.0)
        self.shot("match_found")
        self.bar_button("Accept").invoke()
        self.pump(lambda: tab.view.revealed is not None or tab.view._stage == "match", 20, "reveal")
        self.shot("accepted_connecting")
        self.pump(lambda: tab.view._stage == "match", 30, "in match")
        self.flip_tabs()
        self.wait(1.0)
        self.shot("in_match")
        self.pump(lambda: tab.last_result is not None, 60, "result")
        self.pump(lambda: self.bar_button("Rematch") is not None, 15, "rematch bar")
        self.shot("result_with_rematch")
        self.bar_button("Leave").invoke()
        self.pump(lambda: tab.view._stage == "result", 10, "result card")
        self.shot("result_card")

        # a scripted opponent: next game, waiting after accepting, lag check, rematch both ways
        self.game_kind = "fake"
        lee = self.client("Lee", auto_ready=False)
        tab.view._next_game()
        self.pump(lambda: self.status_of("kaze") == "queue", 15, "next game")
        lee.quick_match()
        self.pump(lambda: self.found("ready"), 20, "found 2")
        self.bar_button("Accept").invoke()
        self.pump(lambda: tab.ready_sent, 5)
        self.shot("accepted_waiting_for_opponent")
        ev = self.util.expect(lee, "match_found")
        lee.ready(True, ev["match"])
        self.pump(lambda: tab.view._stage == "match", 30, "in match 2")
        self.finish_fake(False, lee)
        self.pump(lambda: self.bar_button("Rematch") is not None, 20, "result 2")
        mid = tab.driver.last["match"]
        tab.client.report_lag(mid, 3000, 3000 * 40.0, 60.0)
        lee.report_lag(mid, 3000, 3000 * 40.0, 60.0)
        self.pump(lambda: tab.lag is not None and self.bar_button("Leave: too laggy") is not None, 15, "lag check")
        self.shot("result_loss_lag_check")
        self.bar_button("Rematch").invoke()
        self.pump(lambda: tab.view._stage == "result" and tab.view.rematch_pending, 10, "rematch offered")
        self.shot("rematch_offered_waiting")
        ev = self.util.expect(lee, "rematch")
        lee.auto_ready = True
        lee.rematch(ev["match"], True)
        self.pump(lambda: tab.view._stage == "match", 30, "rematch in match")
        self.shot("rematch_in_match")
        self.finish_fake(True, lee, 3, 2)
        self.pump(lambda: self.bar_button("Rematch") is not None, 20, "result 3")
        lee.rematch(tab.driver.last["match"], True)                 # the opponent asks first this time
        self.pump(lambda: "wants a rematch" in tab.bar_text.get(), 15, "rematch offer")
        self.shot("opponent_wants_rematch")
        self.bar_button("No thanks").invoke()
        self.pump(lambda: tab.view._stage in ("result", "play"), 10)
        tab.view.dismiss_result()

        # a room, a challenge, a game that closed without a result
        tab.actions["room"].invoke()
        tab.rooms_ui.window.create_button.invoke()           # (Create room's window: an open room for two)
        self.pump(lambda: self.status_of("kaze") == "room", 10, "room")
        self.shot("in_own_room")
        lee.auto_ready = False
        lee.join_room(s.call(lambda: s.srv.by_name["kaze"].room.id))
        self.pump(lambda: self.found("ready"), 20, "room ready check")
        self.shot("room_match_ready_check")
        self.bar_button("Decline").invoke()
        self.pump(lambda: tab.view._stage != "bar", 10)
        self.pump(lambda: str(tab.actions["leave"].cget("state")) == "normal", 10, "leave room enabled")
        tab.actions["leave"].invoke()
        self.pump(lambda: self.status_of("kaze") == "idle", 10, "left room")
        try:
            lee.leave_room()
        except Exception:
            pass
        lee.auto_ready = True
        self.wait(0.5)
        lee.challenge(s.call(lambda: s.srv.by_name["kaze"].id))
        self.pump(lambda: self.found("challenge"), 15, "challenge")
        self.shot("challenge")
        self.bar_button("Accept").invoke()
        self.pump(lambda: tab.view._stage == "match", 30, "challenge match")
        self.games[-1].done = True                                   # closed without a result file
        self.pump(lambda: self.bar_button("I won") is not None, 20, "how did it end")
        self.shot("game_closed_ask_result")
        slot = tab.driver.session_ticket.slot
        before = tab.last_result
        self.bar_button("I lost").invoke()
        lee.report_result(1 - slot, None)
        self.pump(lambda: tab.last_result is not before, 20, "result 4")
        b = self.bar_button("Leave")
        if b is not None:
            b.invoke()
        tab.view.dismiss_result()

        # errors while logged in, the server's notice
        tab.on_event({"t": "match_cancel", "reason": "no_connection"})
        self.assertIn("firewall or router", tab.view.err_var.get())
        s.call(lambda: s.srv.store.add_notice("Server restart at 23:00 (about 5 minutes).", time.time() + 600))
        s.call(lambda: s.srv.poll_notices())
        self.pump(lambda: tab.notice_var.get() != "", 10, "notice")
        self.shot("error_no_connection_and_server_notice")
        tab.view.clear_error()
        s.call(lambda: s.srv.store.clear_notices())
        s.call(lambda: s.srv.poll_notices())

        # log out and in again, then an account: recovery codes, rank badge, ranked, promotion, the set
        tab.do_logout()
        self.flip_tabs()
        self.pump(lambda: tab.client is None, 10, "logged out")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None, 20, "back in")
        tab.do_logout()
        self.pump(lambda: tab.client is None, 10, "logged out 2")
        tab.view.mode_var.set("register")
        tab.view._mode_changed()
        tab.name_var.set("Kaze_R")
        tab.pw_var.set("secret-pw1")
        tab.view.pw2_var.set("secret-pw1")
        self.shot("create_account_ready")
        tab.do_login("register")
        self.pump(lambda: tab.codes_window is not None, 20, "recovery codes")
        self.shot("recovery_codes", tab.codes_window)
        tab.codes_window.destroy()
        rival = self.client("Rival_R", password="rival-pw1", register=True, auto_ready=True)

        def seed():
            from t5lobby import ranks as rk
            from t5lobby.rating import Rating
            p = s.srv.by_name["kaze_r"]
            p.rating = Rating(1592, 70, 0.06)
            p.rank = rk.RankState(tier=11, games=14, since_change=6, peak=11, floor=6)
            p.record = [9, 5, 0]
            q = s.srv.by_name["rival_r"]
            q.rating = Rating(1650, 60, 0.06)
            q.rank = rk.RankState(tier=13, games=30, since_change=8, peak=13, floor=8)
            q.record = [21, 9, 0]
            s.srv._broadcast_lobby()
        s.call(seed)
        self.pump(lambda: (tab.client.me or {}).get("tier") == 11, 10, "rank shown")
        tab.char_var.set("Lili")
        tab.on_char()
        self.shot("lobby_account_rank_badge")
        tab.actions["ranked"].invoke()
        self.pump(lambda: tab.view._stage == "search", 10, "ranked search")
        self.shot("searching_ranked")
        rival.ranked_match()
        self.pump(lambda: self.found("ready"), 30, "ranked found")
        self.shot("ranked_match_found")
        self.bar_button("Accept").invoke()
        self.pump(lambda: tab.view._stage == "match", 30, "ranked in match")
        self.shot("ranked_in_match")
        self.finish_fake(True, rival, 3, 1)
        self.pump(lambda: self.bar_button("Rematch") is not None, 20, "ranked result")
        r = (tab.last_result or {}).get("rating") or {}
        self.assertEqual(r.get("event"), "promoted")
        self.shot("ranked_result_promoted")
        self.bar_button("Rematch").invoke()
        rival.rematch(self.util.expect(rival, "rematch")["match"], True)
        self.pump(lambda: tab.view._stage == "match", 30, "set game 2")
        self.assertEqual(str(tab.char_cb.cget("state")), "disabled")       # the set locks the character
        self.assertIn("GAME 2", tab.view.set_text(tab.view.match_ev))     # "SET, GAME 2" on the card
        self.shot("ranked_set_game2_in_match")
        self.finish_fake(False, rival, 3, 2)
        self.pump(lambda: self.bar_button("Rematch") is not None, 20, "set game 2 result")
        self.shot("ranked_set_game2_result")
        self.bar_button("Block").invoke()
        self.pump(lambda: tab.view._stage != "bar", 10)
        tab.do_blocked()
        self.pump(lambda: tab.blocks_window is not None, 10, "blocked players")
        self.shot("blocked_players", tab.blocks_window)
        tab.blocks_window.destroy()
        tab.view.dismiss_result()

        # a ranked set (best of 3) against a client that knows sets: the countdown to game 2, then the set's end
        rs = self.client("Rival_S", password="rival-pw1", register=True, auto_ready=True, sets=True)
        self.pump(lambda: str(tab.actions["ranked"].cget("state")) == "normal", 20, "ranked again")
        tab.actions["ranked"].invoke()
        self.pump(lambda: self.status_of("kaze_r") == "queue", 10, "set search")
        rs.ranked_match()
        self.pump(lambda: self.found("ready"), 30, "set found")
        self.bar_button("Accept").invoke()
        self.pump(lambda: tab.view._stage == "match", 30, "set game 1")
        self.finish_fake(True, rs, 3, 0)
        self.pump(lambda: tab.view.set_ring is not None, 20, "set countdown")
        self.assertIn("starts in", tab.bar_text.get())
        self.wait(1.0)
        self.shot("ranked_set_countdown")
        self.pump(lambda: tab.view._stage == "match", 30, "set game 2 (by itself)")
        self.shot("ranked_set_game2_by_itself")
        self.finish_fake(True, rs, 3, 1)
        self.pump(lambda: (tab.view.result_info or {}).get("set_end") is not None, 20, "set result")
        self.pump(lambda: tab.view._outcome()[0] == "win", 5, "SET WON")
        self.shot("ranked_set_won")
        b = self.bar_button("Leave")
        if b is not None:
            b.invoke()
        tab.view.dismiss_result()

        # leaderboard, profile
        tab.nb.select(1)
        self.pump(lambda: len(tab.tv_board.get_children()) >= 2, 10, "leaderboard")
        self.shot("leaderboard")
        tab.show_profile(None)
        self.pump(lambda: len(tab.tv_hist.get_children()) >= 1, 10, "profile")
        self.shot("profile")
        tab.nb.select(0)

        # the server goes away; then the launcher closes
        tab.client.reconnect_window = 2.0                         # (60 s for players)
        self.stop_server()
        self.pump(lambda: tab.client is None, 60, "disconnected")
        self.assertIn("Log in again", tab.view.err_var.get())
        self.flip_tabs()
        self.shot("error_lost_connection")
        self.app.on_close()
        self.assertEqual(self.errors(), [], "the launcher logged errors")


if __name__ == "__main__":
    unittest.main()
