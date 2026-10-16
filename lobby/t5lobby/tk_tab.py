"""The launcher's Online tab (tkinter), built on LobbyClient.

It implements the contract of launcher/online.py (branch `launcher`):

    OnlineTab(parent, app)   app.settings, app.game_state(), app.start_game(env) -> GameRun|None,
                             app.game, app.set_status(text) (optional)
    .on_show() / .on_close()

To use it, launcher/online.py becomes:

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lobby"))
    from t5lobby.tk_tab import OnlineTab, AVAILABLE  # noqa: E402,F401

Its own settings (server address, last login name) live in online.json next to the
launcher's settings file; passwords are never stored.

    python -m t5lobby.tk_tab --server 127.0.0.1:7781     # standalone window, stub game (testing)
"""
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .buildid import BuildInfo
from .client import LobbyClient
from .handover import read_result_file
from .proto import DEFAULT_PORT, LobbyError

AVAILABLE = True
DEFAULT_SERVER = f"127.0.0.1:{DEFAULT_PORT}"
STATUS_TEXT = {"idle": "in lobby", "room": "in a room", "queue": "searching", "match": "matching",
               "playing": "playing"}


class OnlineTab:
    def __init__(self, parent, app):
        self.app = app
        self.parent = parent
        self.client = None
        self.ui_q = queue.Queue()        # callables from worker threads, run on the Tk thread
        self.cfg_path = os.path.join(os.path.dirname(getattr(app.settings, "path", "") or os.getcwd()),
                                     "online.json")
        self.cfg = self._load_cfg()
        self.match = None                # match_found event
        self.ticket = None
        self.game = None
        self.result_file = None
        self.challenge = None            # pending incoming challenge
        self._build_ui()
        self.parent.after(100, self._poll)

    # ------------------------------------------------------------------ settings
    def _load_cfg(self):
        try:
            with open(self.cfg_path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_cfg(self):
        self.cfg["server"] = self.server_var.get().strip()
        self.cfg["name"] = self.name_var.get().strip()
        try:
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=1)
        except OSError:
            pass

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        box = ttk.Frame(self.parent, padding=16)
        box.pack(fill="both", expand=True)
        box.columnconfigure(0, weight=3)
        box.columnconfigure(1, weight=2)
        box.rowconfigure(2, weight=1)

        login = ttk.LabelFrame(box, text="  Lobby  ", padding=10)
        login.grid(row=0, column=0, columnspan=2, sticky="we")
        self.server_var = tk.StringVar(value=self.cfg.get("server") or DEFAULT_SERVER)
        self.name_var = tk.StringVar(value=self.cfg.get("name") or self.app.settings.get("nickname") or "")
        self.pw_var = tk.StringVar()
        for col, (label, var, width, show) in enumerate((("Server", self.server_var, 24, None),
                                                         ("Name", self.name_var, 16, None),
                                                         ("Password", self.pw_var, 14, "*"))):
            ttk.Label(login, text=label).grid(row=0, column=col * 2, sticky="w", padx=(0 if col == 0 else 10, 4))
            e = ttk.Entry(login, textvariable=var, width=width, show=show or "")
            e.grid(row=0, column=col * 2 + 1, sticky="w")
        btns = ttk.Frame(login)
        btns.grid(row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))
        self.b_guest = ttk.Button(btns, text="Play as guest", command=lambda: self.do_login("guest"))
        self.b_login = ttk.Button(btns, text="Log in", command=lambda: self.do_login("account"))
        self.b_register = ttk.Button(btns, text="Create account", command=lambda: self.do_login("register"))
        self.b_logout = ttk.Button(btns, text="Leave lobby", command=self.do_logout, state="disabled")
        for b in (self.b_guest, self.b_login, self.b_register, self.b_logout):
            b.pack(side="left", padx=(0, 8))
        self.me_var = tk.StringVar(value="Not connected. Password is only needed for an account (ranked).")
        ttk.Label(login, textvariable=self.me_var, style="Muted.TLabel").grid(row=2, column=0, columnspan=6,
                                                                            sticky="w", pady=(6, 0))

        act = ttk.Frame(box)
        act.grid(row=1, column=0, columnspan=2, sticky="we", pady=(10, 4))
        self.actions = {}
        for key, label, cmd in (("quick", "Quick match", lambda: self.call(self.client.quick_match)),
                                ("ranked", "Ranked match", lambda: self.call(self.client.ranked_match)),
                                ("cancel", "Stop searching", lambda: self.call(self.client.cancel_queue)),
                                ("room", "Create room", lambda: self.call(self.client.create_room, None)),
                                ("join", "Join room", self.do_join),
                                ("leave", "Leave room", lambda: self.call(self.client.leave_room)),
                                ("challenge", "Challenge", self.do_challenge)):
            b = ttk.Button(act, text=label, command=cmd, state="disabled")
            b.pack(side="left", padx=(0, 6))
            self.actions[key] = b

        # match / challenge bar (shown when something needs an answer)
        self.bar = ttk.Frame(box, padding=(8, 6))
        self.bar_text = tk.StringVar()
        ttk.Label(self.bar, textvariable=self.bar_text, style="H2.TLabel").pack(side="left")
        self.bar_buttons = ttk.Frame(self.bar)
        self.bar_buttons.pack(side="right")

        lists = ttk.Frame(box)
        lists.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        lists.rowconfigure(0, weight=3)
        lists.rowconfigure(1, weight=1)
        lists.columnconfigure(0, weight=1)
        cols = ("player", "status", "rating", "ping")
        self.tv_players = ttk.Treeview(lists, columns=cols, show="headings", height=8, selectmode="browse")
        for c, w in zip(cols, (180, 110, 70, 70)):
            self.tv_players.heading(c, text=c.capitalize())
            self.tv_players.column(c, width=w, anchor="w")
        self.tv_players.grid(row=0, column=0, sticky="nsew")
        cols = ("room", "owner", "state")
        self.tv_rooms = ttk.Treeview(lists, columns=cols, show="headings", height=4, selectmode="browse")
        for c, w in zip(cols, (180, 140, 90)):
            self.tv_rooms.heading(c, text=c.capitalize())
            self.tv_rooms.column(c, width=w, anchor="w")
        self.tv_rooms.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        chat = ttk.LabelFrame(box, text="  Chat  ", padding=6)
        chat.grid(row=2, column=1, sticky="nsew", padx=(10, 0), pady=(6, 0))
        chat.rowconfigure(0, weight=1)
        chat.columnconfigure(0, weight=1)
        self.chat_log = tk.Text(chat, height=10, width=36, state="disabled", wrap="word", font=("Segoe UI", 9))
        self.chat_log.grid(row=0, column=0, sticky="nsew")
        self.chat_var = tk.StringVar()
        ce = ttk.Entry(chat, textvariable=self.chat_var)
        ce.grid(row=1, column=0, sticky="we", pady=(4, 0))
        ce.bind("<Return>", lambda _e: self.do_chat())

        self.status_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.status_var, style="Muted.TLabel").grid(row=3, column=0, columnspan=2,
                                                                              sticky="w", pady=(8, 0))

    def _set_actions(self):
        me = self.client.me if self.client and self.client.connected else None
        st = (me or {}).get("status")
        guest = (me or {}).get("guest", True)
        busy = self.match is not None or self.game is not None
        on = {
            "quick": me and st == "idle" and not busy,
            "ranked": me and st == "idle" and not busy and not guest,
            "cancel": me and st == "queue",
            "room": me and st == "idle" and not busy,
            "join": me and st == "idle" and not busy,
            "leave": me and st == "room" and not busy,
            "challenge": me and st in ("idle", "queue") and not busy,
        }
        for k, b in self.actions.items():
            b.configure(state="normal" if on[k] else "disabled")
        connected = me is not None
        for b in (self.b_guest, self.b_login, self.b_register):
            b.configure(state="disabled" if connected else "normal")
        self.b_logout.configure(state="normal" if connected else "disabled")

    def status(self, text):
        self.status_var.set(text)
        if hasattr(self.app, "set_status"):
            try:
                self.app.set_status(text)
            except Exception:
                pass

    def show_bar(self, text, buttons):
        self.bar_text.set(text)
        for w in self.bar_buttons.winfo_children():
            w.destroy()
        for label, cmd in buttons:
            ttk.Button(self.bar_buttons, text=label, command=cmd).pack(side="left", padx=(6, 0))
        self.bar.grid(row=4, column=0, columnspan=2, sticky="we", pady=(8, 0))

    def hide_bar(self):
        self.bar.grid_forget()

    def chat_line(self, text):
        self.chat_log.configure(state="normal")
        self.chat_log.insert("end", text + "\n")
        self.chat_log.see("end")
        self.chat_log.configure(state="disabled")

    # ------------------------------------------------------------------ background calls
    def call(self, fn, *args, then=None):
        """Run a (blocking) client call on a worker thread; errors go to the status line."""
        def work():
            try:
                r = fn(*args)
                if then:
                    self.ui_q.put(lambda: then(r))
            except LobbyError as e:
                text = f"Lobby: {e.msg or e.code}"       # (e is unbound once the except block ends)
                self.ui_q.put(lambda: self.status(text))
            except Exception as e:   # noqa: BLE001 -- shown to the player, not swallowed
                text = f"Lobby error: {e}"
                self.ui_q.put(lambda: self.status(text))
            self.ui_q.put(self._set_actions)
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                self.ui_q.get_nowait()()
        except queue.Empty:
            pass
        if self.client is not None:
            try:
                while True:
                    self.on_event(self.client.events.get_nowait())
            except queue.Empty:
                pass
        self._watch_game()
        try:
            self.parent.after(100, self._poll)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ actions
    def _build_info(self):
        st = self.app.game_state()
        if not st.get("ok"):
            return None, st.get("text") or "The game is not built."
        try:
            rel = "dev"
            try:
                import core   # the launcher's module, when we run inside it
                rel = core.release_info().get("version", "dev")
            except Exception:
                pass
            return BuildInfo.from_out_dir(self.app.settings.out_dir, rel), None
        except (OSError, ValueError) as e:
            return None, f"Cannot read the build's identity: {e}"

    def do_login(self, mode):
        name, pw = self.name_var.get().strip(), self.pw_var.get()
        server = self.server_var.get().strip() or DEFAULT_SERVER
        build, err = self._build_info()
        if build is None:
            self.status(err)
            return
        if mode != "guest" and not pw:
            self.status("Enter a password (6 characters or more), or play as a guest.")
            return
        self._save_cfg()
        self.status(f"Connecting to {server}...")
        client = LobbyClient(server, build, game_port=int(self.cfg.get("game_port", 0) or 0))

        def work():
            w = client.connect()
            if mode == "guest":
                me = client.login_guest(name)
            elif mode == "account":
                me = client.login(name, pw)
            else:
                me = client.register(name, pw)
            return w, me

        def done(r):
            w, me = r
            self.client = client
            self.pw_var.set("")
            self.me_var.set(f"{me['name']} -- {'guest' if me['guest'] else 'rating %d' % me['rating']}"
                            f" -- server ping {client.server_rtt or 0:.0f} ms" + (f" -- {w['motd']}" if w.get("motd")
                                                                                  else ""))
            self.status("In the lobby.")
            self._set_actions()

        def work_guarded():
            try:
                return work()
            except Exception:
                client.close()
                raise
        self.call(work_guarded, then=done)

    def do_logout(self):
        c, self.client = self.client, None
        if c:
            threading.Thread(target=c.close, daemon=True).start()
        self.match = None
        self.hide_bar()
        self.tv_players.delete(*self.tv_players.get_children())
        self.tv_rooms.delete(*self.tv_rooms.get_children())
        self.me_var.set("Not connected.")
        self._set_actions()

    def do_join(self):
        sel = self.tv_rooms.selection()
        if not sel:
            self.status("Select a room first.")
            return
        self.call(self.client.join_room, sel[0])

    def do_challenge(self):
        sel = self.tv_players.selection()
        if not sel or (self.client.me and sel[0] == self.client.me["id"]):
            self.status("Select an opponent in the list first.")
            return
        self.call(self.client.challenge, sel[0], then=lambda _r: self.status("Challenge sent."))

    def do_chat(self):
        text = self.chat_var.get().strip()
        if text and self.client:
            self.chat_var.set("")
            self.call(self.client.chat, text)

    # ------------------------------------------------------------------ server events
    def on_event(self, ev):
        t = ev["t"]
        c = self.client
        if t == "lobby_state":
            self._fill_lists(ev)
        elif t == "chat":
            self.chat_line(f"{ev['from']['name']}: {ev['text']}")
        elif t == "challenged":
            self.challenge = ev["challenge"]
            self.show_bar(f"{ev['from']['name']} ({ev['from']['rating']}) challenges you",
                          [("Accept", lambda: self._answer(True)), ("Decline", lambda: self._answer(False))])
        elif t == "challenge_update":
            if ev["state"] != "accepted":
                self.status(f"Challenge {ev['state']}.")
            if ev["challenge"] == self.challenge:
                self.challenge = None
                self.hide_bar()
        elif t == "match_found":
            self.match = ev
            opp = ev["opponent"]
            text = (f"Opponent: {opp['name']} ({'guest' if opp['guest'] else opp['rating']})"
                    f"{' -- ranked' if ev['ranked'] else ''}")
            if ev["ready_check"]:
                self.show_bar(text, [("Accept", lambda: self._ready(True)), ("Decline", lambda: self._ready(False))])
            else:
                self.show_bar(text + " -- connecting...", [])
        elif t == "opponent_ready":
            self.status("Your opponent accepted.")
        elif t == "nat_status":
            self.status(ev["text"])
        elif t == "match_cancel":
            self.match = None
            self.hide_bar()
            self.status({"declined": "Match declined.", "ready_timeout": "Nobody accepted in time.",
                         "opponent_left": "Your opponent left.",
                         "udp_unreachable": "No UDP connection to the lobby server (firewall?).",
                         "no_connection": "Could not connect the two PCs, not even through the relay."
                         }.get(ev["reason"], f"Match cancelled ({ev['reason']})."))
        elif t == "match_start":
            self.start_game(ev)
        elif t == "match_result":
            self._show_result(ev)
        elif t == "notice":
            self.status(ev.get("msg", ""))
        elif t == "disconnected":
            self.status(f"Lost the lobby connection: {ev.get('reason')}")
            self.client = None
            self.do_logout()
        elif t == "kicked":
            self.status(f"Removed from the lobby: {ev.get('reason')}")
        if c is not None:
            self._set_actions()

    def _fill_lists(self, ev):
        me = self.client.me if self.client else None
        mine = self.client.build.build_id if self.client else None
        my_rtt = (self.client.server_rtt if self.client else None) or 0.0
        keep = self.tv_players.selection()
        self.tv_players.delete(*self.tv_players.get_children())
        for p in ev.get("players", []):
            status = STATUS_TEXT.get(p["status"], p["status"])
            if p["build"] != mine:
                status += " (other version)"
            ping = "" if p["rtt"] is None or (me and p["id"] == me["id"]) else f"~{p['rtt'] + my_rtt:.0f} ms"
            rating = "guest" if p["guest"] else p["rating"]
            name = p["name"] + ("  (you)" if me and p["id"] == me["id"] else "")
            self.tv_players.insert("", "end", iid=p["id"], values=(name, status, rating, ping))
        for iid in keep:
            if self.tv_players.exists(iid):
                self.tv_players.selection_set(iid)
        keep = self.tv_rooms.selection()
        self.tv_rooms.delete(*self.tv_rooms.get_children())
        for r in ev.get("rooms", []):
            state = r["status"] + (" (other version)" if r["build"] != mine else "") + (" ranked" if r["ranked"]
                                                                                        else "")
            self.tv_rooms.insert("", "end", iid=r["id"], values=(r["name"], r["owner"]["name"], state))
        for iid in keep:
            if self.tv_rooms.exists(iid):
                self.tv_rooms.selection_set(iid)
        q = ev.get("queue", {})
        if self.client and self.client.me and self.client.me.get("status") == "queue":
            self.status(f"Searching... ({q.get('quick', 0)} quick, {q.get('ranked', 0)} ranked in the queue)")

    def _answer(self, accept):
        cid, self.challenge = self.challenge, None
        self.hide_bar()
        if cid:
            self.call(self.client.answer_challenge, cid, accept)

    def _ready(self, accept):
        m = self.match
        if not m:
            return
        self.show_bar(self.bar_text.get() + (" -- waiting for the opponent..." if accept else ""), [])
        self.call(self.client.ready, accept, m["match"])

    # ------------------------------------------------------------------ the game
    def start_game(self, ev):
        t = ev.get("ticket")
        if t is None:      # resumed session: the game is already running
            return
        self.ticket = t
        self.hide_bar()
        out = getattr(self.app.settings, "out_dir", os.getcwd())
        self.result_file = os.path.join(out, "logs", f"result-{t.match_id}.json")
        os.makedirs(os.path.dirname(self.result_file), exist_ok=True)
        env = t.game_env(result_file=self.result_file)
        game = self.app.start_game(env)
        if game is None:
            self.status("The game could not start; leaving the match.")
            self.call(self.client.leave_match, t.match_id)
            self.match = None
            return
        if t._dup_socket is not None and getattr(game, "proc", None) is not None:
            t.share_socket(game.proc.pid)
        self.game = game
        self.game_t0 = time.time()
        self.status(f"Playing against {t.summary()}")
        self.call(self.client.game_started, t.match_id)

    def _watch_game(self):
        g = self.game
        if g is None or g.running():
            return
        self.game = None
        t = self.ticket
        res = read_result_file(self.result_file) if self.result_file else None
        if res is not None and self.client:
            self.call(self.client.report_result, res[0], res[1], t.match_id)
            self.status("Game over; result sent.")
            return
        if not self.client:
            return
        me = t.slot
        self.show_bar(f"Game closed. How did the match against {t.opponent.get('name', '?')} end?", [
            ("I won", lambda: self._report(me)),
            ("I lost", lambda: self._report(1 - me)),
            ("Draw", lambda: self._report(None)),
            ("Not finished", lambda: self._report("quit")),
        ])

    def _report(self, winner):
        t = self.ticket
        self.hide_bar()
        if winner == "quit":
            self.call(self.client.leave_match, t.match_id)
        else:
            self.call(self.client.report_result, winner, None, t.match_id)
        self.status("Result sent; waiting for your opponent's report...")

    def _show_result(self, ev):
        self.match = None
        self.ticket = None
        st = ev["status"]
        text = {"confirmed": "Result confirmed", "onesided": "Result recorded (opponent did not report)",
                "disputed": "You and your opponent reported different results -- not counted",
                "void": "No result"}.get(st, st)
        r = ev.get("rating")
        if r:
            text += f"; rating {r['after']['r']:.0f} ({r['delta']:+.0f})"
        self.status(text + ".")
        self.hide_bar()
        if self.client and self.client.me:
            me = self.client.me
            self.me_var.set(f"{me['name']} -- {'guest' if me['guest'] else 'rating %d' % me['rating']}"
                            f" -- {me['record'][0]}W {me['record'][1]}L")

    # ------------------------------------------------------------------ launcher hooks
    def on_show(self):
        if self.client:
            self._set_actions()

    def on_close(self):
        if self.client:
            self.client.close()
            self.client = None


# ---------------------------------------------------------------------- standalone (testing)
class _FakeSettings(dict):
    path = os.path.join(os.getcwd(), "launcher.json")
    out_dir = os.getcwd()


class _StubGame:
    def __init__(self, env):
        import subprocess
        import sys
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.proc = subprocess.Popen([sys.executable, os.path.join(here, "tools", "stub_game.py")],
                                     env=dict(os.environ, **env))

    def running(self):
        return self.proc.poll() is None


class _FakeApp:
    """Enough of the launcher to run the tab alone: a test build id and the stub game."""

    def __init__(self):
        self.settings = _FakeSettings(nickname="")
        self.game = None

    def game_state(self):
        return {"ok": True}

    def start_game(self, env):
        self.game = _StubGame(env)
        return self.game

    def set_status(self, text):
        print("[status]", text)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=DEFAULT_SERVER)
    a = ap.parse_args()
    root = tk.Tk()
    root.title("T5DR Online -- lobby (standalone)")
    app = _FakeApp()
    tab = OnlineTab(root, app)
    tab.server_var.set(a.server)
    tab._build_info = lambda: (BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "standalone", "dev"), None)
    root.protocol("WM_DELETE_WINDOW", lambda: (tab.on_close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
