"""The launcher's Online tab (tkinter): accounts, lobby, ranked play, leaderboard, profiles.

It implements the contract of launcher/online.py:

    OnlineTab(parent, app)   app.settings, app.game_state(), app.start_game(env) -> GameRun|None,
                             app.game, app.set_status(text) (optional)
    .on_show() / .on_close()

launcher/online.py imports it (see that file). Matches run through
t5lobby.match_driver.MatchDriver: the game starts by itself when a match is found,
its result is reported by itself, rematches continue in the running game.

Per-user settings (server, name, character, and the remembered login -- a token from
the server, never the password) live in %APPDATA%\\T5DROnline\\online.json (or
$T5_ONLINE_DIR), outside the program folder.

    python -m t5lobby.tk_tab --server 127.0.0.1:7781     # standalone window, stub game (testing)
"""
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import fighters, ranks
from .buildid import BuildInfo
from .client import LobbyClient
from .match_driver import MatchDriver, fps_from_logs
from .proto import DEFAULT_PORT, LobbyError

AVAILABLE = True
DEFAULT_SERVER = f"127.0.0.1:{DEFAULT_PORT}"
STATUS_TEXT = {"idle": "in lobby", "room": "in a room", "queue": "searching", "match": "matching",
               "playing": "playing"}
RESULT_TEXT = {"confirmed": "Result confirmed", "onesided": "Result recorded (your opponent did not report)",
               "forfeit": "Match decided by forfeit", "resolved": "Result decided by the games' state",
               "disputed": "You and your opponent reported different results -- not counted",
               "void": "No result"}
REASON_TEXT = {"desync": "the two games went out of sync", "too_short": "too short to count",
               "disputed": "the reports disagreed", "crash": "a game crashed", "early_quit": "left right away",
               "quit": "a player left", "disconnect": "a player lost the connection",
               "connection": "the connection between the games failed", "no_report": "a player did not report",
               "both_left": "both players left", "timeout": "no result in time",
               "crash_repeat": "repeated crashes count as losses", "early_quit_repeat": "repeated early quits",
               "no_report_repeat": "repeated missing reports", "score_mismatch": "scores differed",
               "no_result": "the fight ended without a winner"}


def _work(results, key, fn, args):
    """Worker thread body for OnlineTab.call (a module function: it must not reference the tab)."""
    try:
        results.put((key, True, fn(*args)))
    except LobbyError as e:
        results.put((key, False, f"Lobby: {e.msg or e.code}"))
    except Exception as e:   # noqa: BLE001 -- shown to the player, not swallowed
        results.put((key, False, f"Lobby error: {e}"))


def online_dir():
    """Per-user folder for the Online tab's settings (never inside the program folder)."""
    d = os.environ.get("T5_ONLINE_DIR")
    if not d:
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
        d = os.path.join(base, "T5DROnline")
    return d


def rank_text(p):
    if p.get("guest"):
        return "guest"
    return ranks.label(p)


class OnlineTab:
    def __init__(self, parent, app):
        self.app = app
        self.parent = parent
        self.client = None
        self.driver = None
        self.ui_q = queue.Queue()        # callables to run on the Tk thread
        self.results_q = queue.Queue()   # (key, ok, value) from worker threads (see call())
        self._callbacks = {}
        self._cb_seq = 0
        self.table = fighters.table()
        self.cfg_path = os.path.join(online_dir(), "online.json")
        self.cfg = self._load_cfg()
        self.match = None                # match_found event
        self.challenge = None            # pending incoming challenge
        self.last_result = None
        self.profile_name = None
        self._auto_tried = False
        self.ask_string = simpledialog.askstring     # dialogs (tests replace them)
        self.ask_yes_no = messagebox.askyesno
        self.codes_window = None
        self._build_ui()
        self._after = self.parent.after(100, self._poll)

    # ------------------------------------------------------------------ settings
    def _load_cfg(self):
        for path in (self.cfg_path,
                     os.path.join(os.path.dirname(getattr(self.app.settings, "path", "") or os.getcwd()),
                                  "online.json")):     # older launchers kept it next to launcher.json
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    return d
            except (OSError, ValueError):
                continue
        return {}

    def _save_cfg(self):
        self.cfg["server"] = self.server_var.get().strip()
        self.cfg["name"] = self.name_var.get().strip()
        self.cfg["char"] = self._char_key()
        self.cfg["remember"] = bool(self.remember_var.get())
        self.cfg["fingerprint"] = self.fp_var.get().strip()
        try:
            os.makedirs(os.path.dirname(self.cfg_path), exist_ok=True)
            tmp = self.cfg_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=1)
            os.replace(tmp, self.cfg_path)
        except OSError:
            pass

    def _server_key(self):
        return self.server_var.get().strip().lower() or DEFAULT_SERVER

    def _saved_session(self):
        s = (self.cfg.get("sessions") or {}).get(self._server_key())
        return s if isinstance(s, dict) and s.get("token") else None

    def _remember_session(self, name, token):
        sessions = self.cfg.setdefault("sessions", {})
        if token:
            sessions[self._server_key()] = {"name": name, "token": token, "saved": time.time()}
        else:
            sessions.pop(self._server_key(), None)
        self._save_cfg()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        box = ttk.Frame(self.parent, padding=(14, 10))
        box.pack(fill="both", expand=True)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(4, weight=1)

        # --- account
        acc = ttk.LabelFrame(box, text="  Account  ", padding=(10, 6))
        acc.grid(row=0, column=0, sticky="we")
        self.acc = acc
        self.server_var = tk.StringVar(value=self.cfg.get("server") or DEFAULT_SERVER)
        self.name_var = tk.StringVar(value=self.cfg.get("name") or self.app.settings.get("nickname") or "")
        self.pw_var = tk.StringVar()
        self.remember_var = tk.IntVar(value=1 if self.cfg.get("remember", True) else 0)
        self.fp_var = tk.StringVar(value=self.cfg.get("fingerprint", ""))
        self.login_row = ttk.Frame(acc)
        self.login_row.grid(row=0, column=0, sticky="we")
        for col, (label, var, width, show) in enumerate((("Server", self.server_var, 22, None),
                                                         ("Name", self.name_var, 16, None),
                                                         ("Password", self.pw_var, 14, "*"))):
            ttk.Label(self.login_row, text=label).grid(row=0, column=col * 2, sticky="w",
                                                       padx=(0 if col == 0 else 10, 4))
            e = ttk.Entry(self.login_row, textvariable=var, width=width, show=show or "")
            e.grid(row=0, column=col * 2 + 1, sticky="w")
            if label == "Password":
                e.bind("<Return>", lambda _e: self.do_login("account"))
        ttk.Checkbutton(self.login_row, text="Remember me", variable=self.remember_var).grid(row=0, column=6,
                                                                                         padx=(10, 0))
        btns = ttk.Frame(self.login_row)
        btns.grid(row=1, column=0, columnspan=7, sticky="w", pady=(6, 0))
        self.b_login = ttk.Button(btns, text="Log in", command=lambda: self.do_login("account"))
        self.b_register = ttk.Button(btns, text="Create account", command=lambda: self.do_login("register"))
        self.b_guest = ttk.Button(btns, text="Play as guest", command=lambda: self.do_login("guest"))
        self.b_forgot = ttk.Button(btns, text="Forgot password...", command=self.do_forgot)
        self.b_tls = ttk.Button(btns, text="Server certificate...", command=self.do_fingerprint)
        for b in (self.b_login, self.b_register, self.b_guest, self.b_forgot, self.b_tls):
            b.pack(side="left", padx=(0, 6))

        self.me_row = ttk.Frame(acc)
        self.me_var = tk.StringVar(value="Not connected. Ranked needs an account; guests play casual matches.")
        ttk.Label(self.me_row, textvariable=self.me_var, style="H2.TLabel").pack(side="left")
        self.b_logout = ttk.Button(self.me_row, text="Log out", command=self.do_logout)
        self.b_passwd = ttk.Button(self.me_row, text="Change password...", command=self.do_passwd)
        self.b_codes = ttk.Button(self.me_row, text="New recovery codes...", command=self.do_new_codes)
        self.b_myprofile = ttk.Button(self.me_row, text="My profile", command=lambda: self.show_profile(None))
        for b in (self.b_logout, self.b_passwd, self.b_codes, self.b_myprofile):
            b.pack(side="right", padx=(6, 0))
        self.hint_var = tk.StringVar(value="Passwords are only sent to servers on this PC / your network, or "
                                           "over an encrypted (TLS) connection.")
        ttk.Label(acc, textvariable=self.hint_var, style="Muted.TLabel").grid(row=2, column=0, sticky="w",
                                                                           pady=(4, 0))

        # --- play
        play = ttk.Frame(box)
        play.grid(row=1, column=0, sticky="we", pady=(8, 2))
        ttk.Label(play, text="Character").pack(side="left")
        names = ["Random"] + [f["name"] for f in self.table.selectable()]
        self.char_var = tk.StringVar(value=self.table.fighter_name(self.cfg.get("char") or fighters.RANDOM))
        cb = ttk.Combobox(play, textvariable=self.char_var, values=names, state="readonly", width=14)
        cb.pack(side="left", padx=(4, 12))
        cb.bind("<<ComboboxSelected>>", lambda _e: self.on_char())
        self.actions = {}
        for key, label, cmd in (("ranked", "Ranked match", lambda: self.do_queue("ranked")),
                                ("quick", "Quick match", lambda: self.do_queue("quick")),
                                ("cancel", "Stop searching", lambda: self.call(self.client.cancel_queue)),
                                ("room", "Create room", lambda: self.call(self.client.create_room, None)),
                                ("join", "Join room", self.do_join),
                                ("leave", "Leave room", lambda: self.call(self.client.leave_room)),
                                ("challenge", "Challenge", self.do_challenge)):
            b = ttk.Button(play, text=label, command=cmd, state="disabled")
            b.pack(side="left", padx=(0, 5))
            self.actions[key] = b

        # --- bar (match found, rematch, questions)
        self.bar = ttk.Frame(box, padding=(8, 6))
        self.bar_text = tk.StringVar()
        ttk.Label(self.bar, textvariable=self.bar_text, style="H2.TLabel").pack(side="left")
        self.bar_buttons = ttk.Frame(self.bar)
        self.bar_buttons.pack(side="right")
        self.match_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.match_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w")

        # --- notebook: lobby | leaderboard | profile
        nb = ttk.Notebook(box)
        nb.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
        self.nb = nb
        lobby = ttk.Frame(nb, padding=6)
        board = ttk.Frame(nb, padding=6)
        prof = ttk.Frame(nb, padding=6)
        nb.add(lobby, text="  Lobby  ")
        nb.add(board, text="  Leaderboard  ")
        nb.add(prof, text="  Profile  ")
        nb.bind("<<NotebookTabChanged>>", lambda _e: self._on_subtab())

        lobby.columnconfigure(0, weight=3)
        lobby.columnconfigure(1, weight=2)
        lobby.rowconfigure(0, weight=3)
        lobby.rowconfigure(1, weight=1)
        cols = ("player", "rank", "rating", "record", "main", "status", "ping")
        self.tv_players = ttk.Treeview(lobby, columns=cols, show="headings", height=8, selectmode="browse")
        for c, w in zip(cols, (130, 120, 55, 70, 85, 95, 60)):
            self.tv_players.heading(c, text=c.capitalize())
            self.tv_players.column(c, width=w, anchor="w")
        self.tv_players.grid(row=0, column=0, sticky="nsew")
        self.tv_players.bind("<Double-1>", lambda _e: self._profile_of_selected())
        cols = ("room", "owner", "state")
        self.tv_rooms = ttk.Treeview(lobby, columns=cols, show="headings", height=3, selectmode="browse")
        for c, w in zip(cols, (180, 140, 120)):
            self.tv_rooms.heading(c, text=c.capitalize())
            self.tv_rooms.column(c, width=w, anchor="w")
        self.tv_rooms.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        chat = ttk.LabelFrame(lobby, text="  Chat  ", padding=6)
        chat.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(8, 0))
        chat.rowconfigure(0, weight=1)
        chat.columnconfigure(0, weight=1)
        self.chat_log = tk.Text(chat, height=10, width=30, state="disabled", wrap="word", font=("Segoe UI", 9))
        self.chat_log.grid(row=0, column=0, sticky="nsew")
        self.chat_var = tk.StringVar()
        ce = ttk.Entry(chat, textvariable=self.chat_var)
        ce.grid(row=1, column=0, sticky="we", pady=(4, 0))
        ce.bind("<Return>", lambda _e: self.do_chat())

        board.columnconfigure(0, weight=1)
        board.rowconfigure(1, weight=1)
        top = ttk.Frame(board)
        top.grid(row=0, column=0, sticky="we")
        ttk.Button(top, text="Refresh", command=self.load_leaderboard).pack(side="left")
        ttk.Label(top, style="Muted.TLabel", text="  Order: rating minus twice its uncertainty (a few matches are "
                  "needed to climb). '?' = provisional.").pack(side="left")
        cols = ("place", "player", "rank", "rating", "record", "main")
        self.tv_board = ttk.Treeview(board, columns=cols, show="headings", height=12, selectmode="browse")
        for c, w in zip(cols, (50, 150, 130, 70, 90, 110)):
            self.tv_board.heading(c, text=c.capitalize())
            self.tv_board.column(c, width=w, anchor="w")
        self.tv_board.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.tv_board.bind("<Double-1>", lambda _e: self._profile_of(self.tv_board))

        prof.columnconfigure(0, weight=1)
        prof.rowconfigure(2, weight=1)
        self.prof_title = tk.StringVar(value="Double-click a player in the lobby or the leaderboard.")
        ttk.Label(prof, textvariable=self.prof_title, style="H2.TLabel").grid(row=0, column=0, sticky="w")
        self.prof_text = tk.StringVar(value="")
        ttk.Label(prof, textvariable=self.prof_text, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 6))
        cols = ("when", "result", "opponent", "chars", "score", "rating", "status")
        self.tv_hist = ttk.Treeview(prof, columns=cols, show="headings", height=9, selectmode="none")
        for c, w in zip(cols, (110, 50, 110, 170, 55, 60, 160)):
            self.tv_hist.heading(c, text=c.capitalize())
            self.tv_hist.column(c, width=w, anchor="w")
        self.tv_hist.grid(row=2, column=0, sticky="nsew")

        self.status_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.status_var, style="Muted.TLabel").grid(row=5, column=0, sticky="w",
                                                                              pady=(6, 0))
        self._set_account_view(False)

    def _set_account_view(self, logged_in):
        if logged_in:
            self.login_row.grid_forget()
            self.me_row.grid(row=0, column=0, sticky="we")
        else:
            self.me_row.grid_forget()
            self.login_row.grid(row=0, column=0, sticky="we")

    def _set_actions(self):
        me = self.client.me if self.client and self.client.connected else None
        st = (me or {}).get("status")
        guest = (me or {}).get("guest", True)
        busy = self.match is not None or (self.driver is not None and self.driver.ticket is not None)
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
        connected = self.client is not None
        for b in (self.b_guest, self.b_login, self.b_register, self.b_forgot):
            b.configure(state="disabled" if connected else "normal")
        self.b_logout.configure(state="normal" if connected else "disabled")
        for b in (self.b_passwd, self.b_codes):
            b.configure(state="normal" if me and not guest else "disabled")

    def _show_me(self):
        c = self.client
        if not c or not c.me:
            return
        me = c.me
        if me["guest"]:
            text = (f"{me['name']} (guest, casual matches only) -- {me['record'][0]}W {me['record'][1]}L "
                    f"this session")
        else:
            text = (f"{me['name']} -- {rank_text(me)} -- rating {me['rating']} -- "
                    f"{me['record'][0]}W {me['record'][1]}L" + (f" -- main {self.table.fighter_name(me['main'])}"
                                                               if me.get("main") else ""))
        text += f" -- server ping {c.server_rtt or 0:.0f} ms" + (" -- encrypted" if c.tls else "")
        self.me_var.set(text)

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
        self.bar.grid(row=2, column=0, sticky="we", pady=(6, 0))

    def hide_bar(self):
        self.bar.grid_forget()

    def chat_line(self, text):
        self.chat_log.configure(state="normal")
        self.chat_log.insert("end", text + "\n")
        self.chat_log.see("end")
        self.chat_log.configure(state="disabled")

    def _char_key(self):
        name = self.char_var.get()
        for f in self.table.fighters:
            if f["name"] == name:
                return f["key"]
        return fighters.RANDOM

    # ------------------------------------------------------------------ background calls
    def call(self, fn, *args, then=None, fail=None):
        """Run a (blocking) client call on a worker thread; `then(result)` / `fail()` and errors (to
        the status line) are handled on the Tk thread. The worker never holds a reference to the tab
        or any Tk object: if it dropped the last one, Tcl would be torn down from the wrong thread."""
        self._cb_seq += 1
        key = self._cb_seq
        self._callbacks[key] = (then, fail)
        threading.Thread(target=_work, args=(self.results_q, key, fn, args), daemon=True).start()

    def _poll(self):
        try:
            while True:
                self.ui_q.get_nowait()()
        except queue.Empty:
            pass
        try:
            while True:
                key, ok, value = self.results_q.get_nowait()
                then, fail = self._callbacks.pop(key, (None, None))
                if ok:
                    if then:
                        then(value)
                else:
                    self.status(value)
                    if fail:
                        fail()
                self._set_actions()
        except queue.Empty:
            pass
        if self.client is not None:
            try:
                while True:
                    ev = self.client.events.get_nowait()
                    if self.driver is not None:
                        self.driver.on_event(ev)
                    self.on_event(ev)
            except queue.Empty:
                pass
        if self.driver is not None:
            for n in self.driver.poll():
                self.on_driver(n)
        try:
            self._after = self.parent.after(100, self._poll)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ login / account
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

    def _new_client(self, server, build):
        spec = server
        tls = False
        if spec.lower().startswith("tls://"):
            spec, tls = spec[6:], True
        fp = self.fp_var.get().strip() or None
        c = LobbyClient(spec, build, tls=tls, tls_fingerprint=fp,
                        game_port=int(self.cfg.get("game_port", 0) or 0),
                        plain_passwords=bool(self.cfg.get("plain_passwords")))
        # this PC's game speed from its last online match (the lobby warns / keeps slow PCs out of ranked);
        # before the first one, from the newest game log (offline play)
        try:
            c.perf_fps = float(self.cfg["last_fps"]) if self.cfg.get("last_fps") else None
        except (TypeError, ValueError):
            c.perf_fps = None
        if c.perf_fps is None:
            out = getattr(self.app.settings, "out_dir", os.getcwd())
            c.perf_fps = fps_from_logs(os.path.join(out, "logs"))
        return c

    def do_login(self, mode, session=None):
        name, pw = self.name_var.get().strip(), self.pw_var.get()
        server = self.server_var.get().strip() or DEFAULT_SERVER
        build, err = self._build_info()
        if build is None:
            self.status(err)
            return
        if mode in ("account", "register") and not pw:
            self.status("Enter a password (6 characters or more), or play as a guest.")
            return
        if mode == "register" and not self._confirm_password(pw):
            return
        remember = bool(self.remember_var.get())
        self._save_cfg()
        self.status(f"Connecting to {server}...")
        client = self._new_client(server, build)

        def work():
            w = client.connect()
            if mode == "guest":
                me = client.login_guest(name)
            elif mode == "account":
                me = client.login(name, pw, remember=remember)
            elif mode == "session":
                me = client.login_session(session)
            else:
                me = client.register(name, pw, remember=remember)
            return w, me

        def done(r):
            w, me = r
            self.client = client
            self.pw_var.set("")
            self.name_var.set(me["name"])
            if mode in ("account", "register"):
                self._remember_session(me["name"], client.session if remember else None)
            self._make_driver()
            self._set_account_view(True)
            self._show_me()
            hint = "Pick a character, then Ranked match (accounts) or Quick match."
            if w.get("motd"):
                hint = w["motd"]
            self.hint_var.set(("Encrypted connection (TLS). " if client.tls else "") + hint)
            self.status("In the lobby." + (" (logged in with your saved login)" if mode == "session" else ""))
            self._set_actions()
            self.on_char()
            if client.recovery_codes:
                self.show_codes(client.recovery_codes, first=True)

        def failed():
            if mode == "session":
                self._remember_session(None, None)
                self.status("Your saved login has expired; log in with your password.")

        def work_guarded():
            try:
                return work()
            except Exception:
                client.close()
                raise
        self.call(work_guarded, then=done, fail=failed)

    def _confirm_password(self, pw):
        again = self.ask_string("Create account", "Type the password again:", show="*", parent=self.parent)
        if again is None:
            return False
        if again != pw:
            self.status("The two passwords differ.")
            return False
        return True

    def try_saved_login(self):
        """Log in with the remembered login for this server, once, when the tab is first shown."""
        if self._auto_tried or self.client is not None:
            return
        self._auto_tried = True
        s = self._saved_session()
        if s and self.app.game_state().get("ok"):
            self.name_var.set(s.get("name", self.name_var.get()))
            self.do_login("session", session=s["token"])

    def _make_driver(self):
        if self.driver is not None:          # a game left from before a lost connection
            self.driver.close()
        out = getattr(self.app.settings, "out_dir", os.getcwd())
        exe = os.path.join(out, "build", "cmake", "t5dr.exe")
        dll = os.path.join(out, "build", "cmake", "t5dr_game.dll")
        self.driver = MatchDriver(self.client, self._launch, os.path.join(out, "logs", "online"),
                                  table=self.table, mode=self.cfg.get("game_mode", "auto"), game_files=[exe, dll],
                                  async_calls=True)

    def _launch(self, env):
        g = getattr(self.app, "game", None)
        if g is not None and g.running() and (self.driver is None or g is not self.driver.game):
            # An offline game is open: an online match needs its own.
            self.status("Closing the running game for the online match...")
            g.stop()
            t_end = time.monotonic() + 5
            while g.running() and time.monotonic() < t_end:
                time.sleep(0.1)
        return self.app.start_game(env)

    def do_logout(self):
        forget = False
        if self.client and self.client.session:
            forget = self.ask_yes_no("Log out", "Also forget the saved login on this PC?\n\n"
                                         "(No = you are logged in automatically next time.)", parent=self.parent)
        c, self.client = self.client, None
        if forget:
            self._remember_session(None, None)
        if self.driver is not None:
            self.driver.close()
            self.driver = None
        if c:
            threading.Thread(target=lambda: c.logout(forget=forget), daemon=True).start()
        self._reset_lobby_view()
        self.me_var.set("Not connected.")
        self._set_account_view(False)
        self._set_actions()

    def _reset_lobby_view(self):
        self.match = None
        self.hide_bar()
        self.match_var.set("")
        self.tv_players.delete(*self.tv_players.get_children())
        self.tv_rooms.delete(*self.tv_rooms.get_children())

    def do_passwd(self):
        old = self.ask_string("Change password", "Current password:", show="*", parent=self.parent)
        if not old:
            return
        new = self.ask_string("Change password", "New password (6 characters or more):", show="*",
                                     parent=self.parent)
        if not new:
            return
        if self.ask_string("Change password", "New password again:", show="*", parent=self.parent) != new:
            self.status("The two new passwords differ.")
            return
        remember = bool(self._saved_session())
        c = self.client

        def done(_r):
            self._remember_session(c.me["name"], c.session if remember else None)
            self.status("Password changed. Saved logins on other PCs have ended.")
        self.call(c.change_password, old, new, remember, then=done)

    def do_new_codes(self):
        pw = self.ask_string("Recovery codes", "Your password (the old codes stop working):", show="*",
                                    parent=self.parent)
        if pw:
            self.call(self.client.new_recovery_codes, pw, then=lambda codes: self.show_codes(codes))

    def show_codes(self, codes, first=False):
        w = tk.Toplevel(self.parent)
        self.codes_window = w
        w.title("Recovery codes")
        ttk.Label(w, padding=10, wraplength=420, justify="left", text=(
            ("Your account is ready. " if first else "") +
            "These codes are the only way back into your account if you forget the password (there is no "
            "e-mail). Each code works once. Write them down or save them somewhere safe -- they are not shown "
            "again.")).pack(anchor="w")
        txt = tk.Text(w, height=len(codes) + 1, width=24, font=("Consolas", 12))
        txt.insert("1.0", "\n".join(codes))
        txt.configure(state="disabled")
        txt.pack(padx=10)
        bar = ttk.Frame(w, padding=10)
        bar.pack(fill="x")

        def save():
            p = filedialog.asksaveasfilename(parent=w, title="Save recovery codes", defaultextension=".txt",
                                             initialfile="t5dr-recovery-codes.txt")
            if p:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(f"T5DR Online recovery codes for {self.client.me['name'] if self.client else ''} "
                            f"on {self.server_var.get()}\n" + "\n".join(codes) + "\n")
        ttk.Button(bar, text="Save to a file...", command=save).pack(side="left")
        ttk.Button(bar, text="I have saved them", command=w.destroy).pack(side="right")

    def do_forgot(self):
        build, err = self._build_info()
        if build is None:
            self.status(err)
            return
        name = self.ask_string("Forgot password", "Account name:", initialvalue=self.name_var.get(),
                                      parent=self.parent)
        if not name:
            return
        code = self.ask_string("Forgot password", "One of your recovery codes (XXXX-XXXX-XXXX):",
                                      parent=self.parent)
        if not code:
            return
        new = self.ask_string("Forgot password", "New password (6 characters or more):", show="*",
                                     parent=self.parent)
        if not new:
            return
        client = self._new_client(self.server_var.get().strip() or DEFAULT_SERVER, build)

        def work():
            try:
                client.connect()
                return client.recover(name, code, new)
            finally:
                client.close()

        def done(r):
            self.name_var.set(r["name"])
            self.status(f"Password reset. {r['codes_left']} recovery code(s) left. Log in with the new password.")
        self.call(work, then=done)

    def do_fingerprint(self):
        fp = self.ask_string(
            "Server certificate",
            "For a server with its own (self-signed) certificate: its SHA-256 fingerprint, from whoever runs it.\n"
            "Empty = no pinning (use tls://host:port for a server with a normal certificate).",
            initialvalue=self.fp_var.get(), parent=self.parent)
        if fp is not None:
            self.fp_var.set(fp.strip())
            self._save_cfg()

    # ------------------------------------------------------------------ lobby actions
    def on_char(self):
        self._save_cfg()
        if self.client and self.client.me:
            self.call(self.client.set_char, self._char_key())

    def do_queue(self, mode):
        c = self.client
        fn = c.ranked_match if mode == "ranked" else c.quick_match
        self.call(fn, self._char_key(), then=lambda _r: self.status(
            "Searching for an opponent" + (" (ranked: similar rank and a good connection)..." if mode == "ranked"
                                           else "...")))

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

    # ------------------------------------------------------------------ leaderboard / profile
    def _on_subtab(self):
        tab = self.nb.tab(self.nb.select(), "text").strip()
        if tab == "Leaderboard":
            self.load_leaderboard()
        elif tab == "Profile" and self.client and self.profile_name is None:
            self.show_profile(None)

    def load_leaderboard(self):
        if not self.client:
            return

        def done(rows):
            self.tv_board.delete(*self.tv_board.get_children())
            for r in rows:
                self.tv_board.insert("", "end", iid="lb:" + r["name"], values=(
                    r["place"], r["name"] + ("  *" if r.get("online") else ""),
                    r["rank"] + ("?" if r.get("provisional") else ""), r["rating"],
                    f"{r['wins']}W {r['losses']}L", self.table.fighter_name(r["main"]) if r.get("main") else ""))
        self.call(self.client.leaderboard, 50, then=done)

    def _profile_of_selected(self):
        sel = self.tv_players.selection()
        if sel:
            name = self.tv_players.item(sel[0], "values")[0].replace("  (you)", "")
            self.show_profile(name)

    def _profile_of(self, tv):
        sel = tv.selection()
        if sel and sel[0].startswith("lb:"):
            self.show_profile(sel[0][3:])

    def show_profile(self, name):
        if not self.client:
            return
        self.profile_name = name
        self.nb.select(2)

        def done(p):
            self.prof_title.set(f"{p['name']} -- {rank_text(p)}" + ("" if p.get("account") else " (guest)"))
            lines = [f"Rating {p['rating']} +/- {p['rd']}" + (" (provisional)" if p.get("provisional") else "")
                     + (f", #{p['place']} on the leaderboard" if p.get("place") else "")]
            rec = p.get("record", [0, 0, 0])
            lines.append(f"Record {rec[0]}W {rec[1]}L" + (f" {rec[2]}D" if rec[2] else "")
                         + (f", ranked matches {p['ranked_games']}" if p.get("account") else "")
                         + (f", highest rank {p['peak_rank']}" if p.get("peak_rank") else ""))
            if p.get("chars"):
                lines.append("Characters: " + ", ".join(
                    f"{self.table.fighter_name(c['char'])} {c['wins']}/{c['games']}" for c in p["chars"]))
            if p.get("voids_24h"):
                lines.append(f"Matches without result caused in the last 24 h: {p['voids_24h']}")
            if p.get("self") and p.get("recovery_codes_left") is not None:
                lines.append(f"Recovery codes left: {p['recovery_codes_left']}")
            self.prof_text.set("\n".join(lines))
            self.tv_hist.delete(*self.tv_hist.get_children())
            for h in p.get("history", []):
                when = time.strftime("%d %b %H:%M", time.localtime(h["time"]))
                chars = f"{self.table.fighter_name(h['you_char'])} vs {self.table.fighter_name(h['opp_char'])}"
                score = f"{h['score'][0]}-{h['score'][1]}" if h.get("score") else ""
                delta = f"{h['delta']:+.0f}" if h.get("delta") is not None else ("" if h["ranked"] else "casual")
                st = h["status"] + (f" ({REASON_TEXT.get(h['reason'], h['reason'])})" if h.get("reason") else "")
                self.tv_hist.insert("", "end", values=(when, h["result"], h["opponent"], chars, score, delta, st))
        self.call(self.client.profile, name, 20, then=done)

    # ------------------------------------------------------------------ server events
    def on_event(self, ev):
        t = ev["t"]
        c = self.client
        if t == "lobby_state":
            self._fill_lists(ev)
            self._show_me()
        elif t == "chat":
            self.chat_line(f"{ev['from']['name']}: {ev['text']}")
        elif t == "challenged":
            self.challenge = ev["challenge"]
            self.show_bar(f"{ev['from']['name']} ({rank_text(ev['from'])}) challenges you",
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
            text = (f"Opponent: {opp['name']} ({rank_text(opp)}, {opp['rating'] if not opp['guest'] else 'guest'})"
                    f"{' -- RANKED' if ev['ranked'] else ''}" + (" -- rematch" if ev.get("origin") == "rematch" else ""))
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
            self.hide_bar()
            f = ev.get("fight") or {}
            how = {"direct": "direct", "lan": "local network", "relay": "via the lobby server's relay"}
            self.match_var.set(
                f"{'Ranked' if ev.get('ranked') else 'Casual'} match vs {ev['opponent']['name']} -- "
                f"{self.table.fighter_name(f.get('p1'))} vs {self.table.fighter_name(f.get('p2'))} -- "
                f"ping {ev.get('rtt_ms', 0):.0f} ms ({how.get(ev.get('path'), ev.get('path'))}), "
                f"input delay {ev.get('delay')} frames ({ev.get('delay', 0) * 16.7:.0f} ms)")
        elif t == "match_result":
            self._show_result(ev)
        elif t == "rematch":
            if ev.get("state") == "declined":
                self.hide_bar()
        elif t == "notice":
            self.status(ev.get("msg", ""))
        elif t == "reconnecting":
            self.status("Lost the lobby connection -- reconnecting (your match goes on)...")
        elif t == "reconnected":
            self.status("Reconnected to the lobby.")
        elif t == "disconnected":
            self.status(f"Lost the lobby connection: {ev.get('reason')}")
            self.client = None
            if self.driver is not None:
                self.driver.ticket = None
            self._reset_lobby_view()
            self.me_var.set("Not connected.")
            self._set_account_view(False)
        elif t == "kicked":
            self.status(f"Removed from the lobby: {ev.get('reason')}")
        if c is not None:
            self._set_actions()

    def on_driver(self, n):
        k = n["kind"]
        if self.driver is not None and self.driver.last_fps and self.driver.last_fps != self.cfg.get("last_fps"):
            self.cfg["last_fps"] = self.driver.last_fps
            self._save_cfg()
        if k == "status":
            self.status(n["text"])
        elif k == "ask_result":
            self.show_bar(f"The game closed. How did the match against {n['opponent']} end?", [
                ("I won", lambda: self._answer_result("won")),
                ("I lost", lambda: self._answer_result("lost")),
                ("Draw", lambda: self._answer_result("draw")),
                ("I quit", lambda: self._answer_result("quit")),
            ])
        elif k == "rematch_offer":
            self.show_bar(f"{n['opponent']} wants a rematch", [("Rematch", lambda: self._rematch(True)),
                                                               ("No thanks", lambda: self._rematch(False))])

    def _answer_result(self, what):
        self.hide_bar()
        if self.driver:
            self.driver.answer(what)
        self.status("Result sent; waiting for your opponent's report...")

    def _rematch(self, accept):
        self.hide_bar()
        if self.driver:
            self.driver.rematch(None, accept)
        if accept:
            self.status("Rematch offered; waiting for your opponent...")

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
            rating = "" if p["guest"] else p["rating"]
            rec = p.get("record") or [0, 0, 0]
            name = p["name"] + ("  (you)" if me and p["id"] == me["id"] else "")
            main = self.table.fighter_name(p.get("main")) if p.get("main") else ""
            self.tv_players.insert("", "end", iid=p["id"], values=(name, rank_text(p), rating,
                                                                   f"{rec[0]}W {rec[1]}L", main, status, ping))
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
            self.status(f"Searching... ({q.get('ranked', 0)} in the ranked queue, {q.get('quick', 0)} quick)")

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

    def _show_result(self, ev):
        self.match = None
        self.last_result = ev
        st = ev["status"]
        text = RESULT_TEXT.get(st, st)
        if ev.get("reason") and ev["reason"] in REASON_TEXT:
            text += f" ({REASON_TEXT[ev['reason']]})"
        mine = None
        if ev.get("winner") is not None and self.driver is not None and self.driver.session_ticket is not None:
            mine = ev["winner"] == self.driver.session_ticket.slot
        if st in ("confirmed", "onesided", "forfeit", "resolved"):
            text = ("You won. " if mine else "You lost. " if mine is False else "") + text
        r = ev.get("rating")
        if r:
            text += f"; rating {r['after']['r']:.0f} ({r['delta']:+.0f})"
            after = r.get("rank_after") or {}
            if r.get("event") == "promoted":
                text += f" -- PROMOTED to {after.get('rank')}!"
            elif r.get("event") == "demoted":
                text += f" -- demoted to {after.get('rank')}"
            elif r.get("event") == "placed":
                text += f" -- placed at {after.get('rank')}"
            elif after.get("placement"):
                text += f" -- placement {after['placement'][0]}/{after['placement'][1]}"
        self.status(text + ".")
        self.hide_bar()
        if ev.get("rematch_window"):
            opp = (self.driver.session_ticket.opponent.get("name") if self.driver and self.driver.session_ticket
                   else "your opponent")
            self.show_bar(text if len(text) < 60 else "Rematch?", [
                (f"Rematch {opp}", lambda: self._rematch(True)), ("Leave", lambda: self._rematch(False))])
        if self.client and self.client.me:
            self._show_me()

    # ------------------------------------------------------------------ launcher hooks
    def on_show(self):
        if self.client:
            self._set_actions()
        else:
            self.try_saved_login()

    def on_close(self):
        try:
            self.parent.after_cancel(self._after)
        except (tk.TclError, ValueError):
            pass
        if self.driver is not None:
            self.driver.close()
            self.driver = None
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
        os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
        self.log_path = os.path.join(os.getcwd(), "logs", f"stub-{int(time.time())}.log")
        with open(self.log_path, "w") as lf:
            self.proc = subprocess.Popen([sys.executable, os.path.join(here, "tools", "stub_game.py")],
                                         env=dict(os.environ, T5_STUB_SECONDS="35", T5_STUB_LINGER="60", **env),
                                         stdout=lf, stderr=lf)

    def running(self):
        return self.proc.poll() is None

    def stop(self):
        if self.running():
            self.proc.kill()


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
    root.geometry("1000x700")
    app = _FakeApp()
    tab = OnlineTab(root, app)
    tab.server_var.set(a.server)
    tab._build_info = lambda: (BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "standalone", "dev"), None)
    root.protocol("WM_DELETE_WINDOW", lambda: (tab.on_close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
