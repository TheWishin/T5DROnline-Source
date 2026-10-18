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

The Server box lists the servers from servers.json (lobby/servers.json from the release, plus
servers.json in that same per-user folder); anything else can be typed as host:port,
host:port#FINGERPRINT (self-signed TLS, pinned) or tls://host:port. "Host for friends" runs a
lobby server on this PC (t5lobby.server.host) and points the Server box at it; the router is only
asked to forward ports when "Open router ports" is ticked.

Tekken 6 style extras: a match found in the queue shows only the ping at first (accept or decline
within 15 s; the opponent's name comes after both accepted), "Strict" limits ranked matchmaking to
+-150 rating points, the result bar can block the opponent, a ranked set locks the character, the
lag check ("ping X ms should mean about Y frames behind, it was Z") appears after a match with a
way to leave without penalty, and a message from the server's admin shows in the status bar.

    python -m t5lobby.tk_tab --server 127.0.0.1:7781     # standalone window, stub game (testing)
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from . import fighters, padmap, padnav, proto, ranks, servers
from .buildid import BuildInfo
from .client import LobbyClient
from .match_driver import MatchDriver, fps_from_logs
from .proto import DEFAULT_PORT, LobbyError
from . import theme, tk_views

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
PAD_STALE_S = 1.0       # a controller press this old by the time the tab sees it (a dialog held the loop) is dropped
PAD_COOLDOWN_S = 0.6    # after a controller action the next one waits (A and B hit together do only one thing)


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


def _controls_path_for(settings):
    """The controls.ini the game will read (docs/controls.ini), for the controller buttons. Takes the
    launcher's settings only, never the launcher itself: the pad thread calls this, and no Tk object
    may be reachable from it."""
    try:
        env = settings.env_overrides()
    except Exception:       # noqa: BLE001 -- a settings object without it: the process environment only
        env = {}
    return padmap.find_controls_ini(getattr(settings, "out_dir", None), env)


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
        self.user_dir = os.path.dirname(self.cfg_path)
        self.server_list, problems = servers.load(self.user_dir)
        self.host_proc = None            # "Host for friends": the lobby server process
        self.host_info = None
        self.host_args = []              # extra arguments for it (tests)
        self.match = None                # match_found event
        self.challenge = None            # pending incoming challenge
        self.last_result = None
        self.profile_name = None
        self._auto_tried = False
        self.ask_string = theme.ask_string           # dialogs (tests replace them)
        self.ask_yes_no = theme.ask_yes_no
        self.new_window = tk.Toplevel                # the tab's own windows (tests make hidden ones)
        self.codes_window = None
        self.ready_deadline = None       # monotonic time the ready check ends (accepting is still possible)
        self.ready_sent = False          # we accepted: waiting for the opponent
        self.set_locked = False          # a ranked set is running: the character cannot change
        self.rematch_bar = None          # (text, opponent name) while the "Rematch?" bar is up
        self.lag = None                  # the last lag_check event
        self.blocks_window = None        # the "Blocked players..." dialog
        self.blocks_list = None
        self.pad = None                  # padnav.PadNav once the tab has been shown (controller buttons)
        self.pad_visible = self._tab_viewable      # tests replace it (their window is withdrawn)
        self.bar_pad = {}                # controller button -> command of the bar button it presses
        self.bar_spec = []               # (button, text, controller button) of the bar's buttons
        self._pad_gen = -1
        self._pad_until = 0.0            # no controller action before this (pad clock)
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
        self.cfg["strict"] = bool(self.strict_var.get())
        self.cfg["pad"] = bool(self.pad_var.get())
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
        """The tab's state (Tk variables); the widgets come from tk_views.OnlineView (the look: theme.py)."""
        default = servers.default_entry(self.server_list)
        self.server_var = tk.StringVar(value=self.cfg.get("server") or (default.name if default else DEFAULT_SERVER))
        self.name_var = tk.StringVar(value=self.cfg.get("name") or self.app.settings.get("nickname") or "")
        self.pw_var = tk.StringVar()
        self.remember_var = tk.IntVar(value=1 if self.cfg.get("remember", True) else 0)
        self.fp_var = tk.StringVar(value=self.cfg.get("fingerprint", ""))
        self.map_var = tk.BooleanVar(value=False)
        self.me_var = tk.StringVar(value="Not connected. Ranked needs an account; guests play casual matches.")
        self.hint_var = tk.StringVar(value="Passwords are only sent to servers on this PC / your network, or "
                                           "over an encrypted (TLS) connection.")
        self.char_var = tk.StringVar(value=self.table.fighter_name(self.cfg.get("char") or fighters.RANDOM))
        self.strict_var = tk.IntVar(value=1 if self.cfg.get("strict") else 0)
        self.bar_text = tk.StringVar()
        self.match_var = tk.StringVar(value="")
        # A ranked set's score ("Set 1-0, game 2 of 3"): shown as a tag on the match cards when set
        # (empty: the cards say "game N" from the server's set info by themselves).
        self.set_var = tk.StringVar(value="")
        self.chat_var = tk.StringVar()
        self.prof_title = tk.StringVar(value="Double-click a player in the lobby or the leaderboard.")
        self.prof_text = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.notice_var = tk.StringVar(value="")          # a message from the server's admin, until it ends
        # controller: A / Cross accepts, B / Circle declines (padnav.py, docs/ONLINE.md)
        self.pad_var = tk.IntVar(value=1 if self.cfg.get("pad", True) else 0)
        self.pad_info_var = tk.StringVar(value="")
        self.view = tk_views.OnlineView(self)
        self._set_account_view(False)

    def _set_account_view(self, logged_in):
        self.view.set_logged_in(logged_in)

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
        self.char_cb.configure(state="disabled" if self.set_locked else "readonly")
        self.strict_check.configure(state="normal" if me and not guest else "disabled")
        self._pad_relabel()
        self.view.refresh()

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

    def status(self, text, error=False):
        """One line for the player; error=True also puts it on the red banner, with what to do."""
        text = proto.scrub_addresses(str(text))       # no IP address in anything the player reads
        self.status_var.set(text)
        self.view.status_changed(text, error)
        if hasattr(self.app, "set_status"):
            try:
                # the server's notice stays in the launcher's status bar whatever else is said
                self.app.set_status(text + (f"   [Server: {self.notice_var.get()}]" if self.notice_var.get() else ""))
            except Exception:
                pass

    def _show_notice(self):
        """The server admin's message(s), or nothing."""
        texts = self.client.active_notices() if self.client else []
        line = "  |  ".join(texts)
        if line != self.notice_var.get():
            self.notice_var.set(line)
            if line and hasattr(self.app, "set_status"):
                try:
                    self.app.set_status(f"Server notice: {line}")
                except Exception:
                    pass

    def show_bar(self, text, buttons):
        """buttons: (label, command) or (label, command, controller button): 'cross' / 'circle' is the
        controller button that presses it, and its name is added to the label while a pad is plugged in."""
        self.bar_text.set(text)
        for w in self.bar_buttons.winfo_children():
            w.destroy()
        self.bar_spec = []
        self.bar_pad = {}
        for item in buttons:
            label, cmd = item[0], item[1]
            pad = item[2] if len(item) > 2 else None
            b = ttk.Button(self.bar_buttons, text=self._pad_label(label, pad), command=cmd,
                           style=self.view.bar_button_style(label, pad))
            b.pack(side="left", padx=(0, self.view.px(8)))
            self.bar_spec.append((b, label, pad))
            if pad:
                self.bar_pad[pad] = cmd
        self.view.show_bar()
        self._pad_relabel()

    def hide_bar(self):
        self.bar_pad = {}
        self.bar_spec = []
        self.view.hide_bar()
        self._pad_relabel()

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
            alive = bool(self.parent.winfo_exists()) and bool(self.view.box.winfo_exists())
        except tk.TclError:
            alive = False
        if not alive:
            return                                  # the tab's widgets are gone (the launcher closed or rebuilt it)
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
                    self.status(value, error=True)
                    if fail:
                        fail()
                self._set_actions()
        except queue.Empty:
            pass
        c = self.client
        if c is not None:
            try:
                while self.client is c:             # ("disconnected" drops the client: its queue is done)
                    ev = c.events.get_nowait()
                    if self.driver is not None:
                        self.driver.on_event(ev)
                    self.on_event(ev)
            except queue.Empty:
                pass
        if self.driver is not None:
            for n in self.driver.poll():
                self.on_driver(n)
        self._tick_ready()
        self._show_notice()
        self._pad_tick()
        self.view.tick()
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
        fp = self.fp_var.get().strip() or None
        try:      # a servers.json entry by name, or host:port#FINGERPRINT / tls://host:port
            entry = servers.resolve(server, self.server_list)
        except ValueError:
            entry = None
        if entry is not None:
            spec, tls = entry.address, entry.tls == "ca"
            if entry.tls == "pin":
                fp = entry.fingerprint      # the entry's own pin wins over the "Server certificate" box
        elif spec.lower().startswith("tls://"):
            spec, tls = spec[6:], True
        c = LobbyClient(spec, build, tls=tls, tls_fingerprint=fp,
                        game_port=int(self.cfg.get("game_port", 0) or 0),
                        plain_passwords=bool(self.cfg.get("plain_passwords")), blind_ready=True)
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
            self.status(err, error=True)
            return
        if mode in ("account", "register") and not pw:
            self.status("Enter a password (6 characters or more), or play as a guest.", error=True)
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
        again = self.view.repeat_password()           # the "password again" field, if the player filled it
        if again is None:
            again = self.ask_string("Create account", "Type the password again:", show="*", parent=self.parent)
        if again is None:
            return False
        if again != pw:
            self.status("The two passwords differ.", error=True)
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
                                  async_calls=True,
                                  input_delay=(getattr(self.app, "settings", None) or {}).get("input_delay"))

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
        self.ready_deadline = None
        self.set_locked = False
        self.rematch_bar = None
        self.lag = None
        self.notice_var.set("")
        self.view.reset()
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
        def save(w):
            p = filedialog.asksaveasfilename(parent=w, title="Save recovery codes", defaultextension=".txt",
                                             initialfile="t5dr-recovery-codes.txt")
            if p:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(f"T5DR Online recovery codes for {self.client.me['name'] if self.client else ''} "
                            f"on {self.server_var.get()}\n" + "\n".join(codes) + "\n")
        self.codes_window = self.view.codes_window(codes, first, save)

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
        self.cfg["last_search"] = mode           # the controller's A button searches the same way again
        self._save_cfg()
        strict = mode == "ranked" and bool(self.strict_var.get())
        args = (self._char_key(), True) if strict else (self._char_key(),)
        fn = c.ranked_match if mode == "ranked" else c.quick_match
        self.call(fn, *args, then=lambda _r: self.status(
            "Searching for an opponent" + (" (ranked: similar rank and a good connection"
                                           + (", strict: within 150 rating points -- this can take a while" if strict
                                              else "") + ")..." if mode == "ranked" else "...")))

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

    def do_blocked(self):
        """The block list, with Unblock."""
        if not self.client:
            return
        self.call(self.client.blocks, then=self._blocks_window)

    def _blocks_window(self, rows):
        px = self.view.px
        w = self.new_window(self.parent)
        w.title("Blocked players")
        bar = self.view.card(w, pad=16)                  # (the buttons are children of this frame)
        bar.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Blocked players", style="Card.H2.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(bar, wraplength=px(380), justify="left", style="Card.Muted.TLabel", text=(
            "You are never matched with these players (ranked, quick matches, rooms, challenges, rematches). "
            "They are not told. Accounts stay blocked; a guest is blocked until you log out.")).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(px(4), px(10)))
        lb = tk.Listbox(bar, height=max(4, min(12, len(rows))), width=32, activestyle="none")
        for r in rows:
            lb.insert("end", r["name"] + ("  (guest)" if r.get("guest") else ""))
        lb.grid(row=2, column=0, columnspan=2, sticky="we")
        self.blocks_list = lb

        def unblock():
            sel = lb.curselection()
            if not sel:
                return
            name = lb.get(sel[0]).replace("  (guest)", "")
            lb.delete(sel[0])
            self.call(self.client.unblock, name, then=lambda _r: self.status(f"Unblocked {name}."))
        ttk.Button(bar, text="Unblock", style="Card.TButton", command=unblock).grid(row=3, column=0, sticky="w",
                                                                                   pady=(px(12), 0))
        ttk.Button(bar, text="Close", style="Card.Accent.TButton", command=w.destroy).grid(row=3, column=1, sticky="e",
                                                                                          pady=(px(12), 0))
        self.blocks_window = w

    def block_opponent(self, name):
        """After a game: never meet this player again. A running match would end like a quit (not offered here)."""
        if not self.ask_yes_no("Block player", f"Block {name}?\n\nYou will not be matched with them again. "
                                               "They are not told. You can unblock them under "
                                               "\"Blocked players...\".", parent=self.parent):
            return
        self.hide_bar()
        self.rematch_bar = None

        def done(_r):
            self.status(f"Blocked {name}. You will not be matched again.")
        self.call(self.client.block, name, then=done)

    def do_chat(self):
        text = self.chat_var.get().strip()
        if text and self.client:
            self.chat_var.set("")
            self.call(self.client.chat, text)

    # ------------------------------------------------------------------ leaderboard / profile
    def _on_subtab(self):
        try:
            cur = self.nb.index("current")          # 0 lobby, 1 leaderboard, 2 profile (texts may be translated)
        except tk.TclError:
            return                                  # (no tab selected: the tab is being taken down)
        if cur == 1:
            self.load_leaderboard()
        elif cur == 2 and self.client and self.profile_name is None:
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
                    f"{r['wins']}W {r['losses']}L", self.table.fighter_name(r["main"]) if r.get("main") else ""),
                    image=self.view.rank_image(r))
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
            self.view.profile_shown(p)
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
                self.tv_hist.insert("", "end", values=(when, h["result"], h["opponent"], chars, score, delta, st),
                                    tags=(h["result"],) if h.get("result") in ("won", "lost") else ())
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
                          [("Accept", lambda: self._answer(True), "cross"),
                           ("Decline", lambda: self._answer(False), "circle")])
        elif t == "challenge_update":
            if ev["state"] != "accepted":
                self.status(f"Challenge {ev['state']}.")
            if ev["challenge"] == self.challenge:
                self.challenge = None
                self.hide_bar()
        elif t == "match_found":
            self.match = ev
            self.hide_bar()
            self.rematch_bar = None
            self.lag = None
            self.ready_sent = False
            if (ev.get("set") or {}).get("locked"):
                self.set_locked = True
            if ev.get("blind"):
                # a match from the queue: the ping and the rules now, the name after both accepted
                self.ready_deadline = time.monotonic() + float(ev.get("ready_timeout") or 15)
                self.show_bar(self._ready_text(), [("Accept", lambda: self._ready(True), "cross"),
                                                   ("Decline", lambda: self._ready(False), "circle")])
            else:
                opp = ev["opponent"]
                text = (f"Opponent: {opp['name']} ({rank_text(opp)}, {opp['rating'] if not opp['guest'] else 'guest'})"
                        f"{' -- RANKED' if ev['ranked'] else ''}"
                        + (" -- rematch" if ev.get("origin") == "rematch" else ""))
                if ev["ready_check"]:
                    self.ready_deadline = time.monotonic() + float(ev.get("ready_timeout") or 15)
                    self.show_bar(text, [("Accept", lambda: self._ready(True), "cross"),
                                         ("Decline", lambda: self._ready(False), "circle")])
                else:
                    self.show_bar(text + " -- connecting...", [])
        elif t == "match_reveal":
            self.ready_deadline = None
            opp = ev["opponent"]
            self.show_bar(f"Opponent: {opp['name']} ({rank_text(opp)}, "
                          f"{opp['rating'] if not opp['guest'] else 'guest'})"
                          f"{' -- RANKED' if (self.match or {}).get('ranked') else ''} -- connecting...", [])
        elif t == "opponent_ready":
            self.status("Your opponent accepted.")
        elif t == "lag_check":
            self._show_lag(ev)
        elif t == "set_end":
            self._set_ended(ev)
        elif t == "server_notice":
            self._show_notice()
        elif t == "nat_status":
            self.status(ev["text"])
        elif t == "match_cancel":
            self.match = None
            self.ready_deadline = None
            self.hide_bar()
            self.status({"declined": "Match declined.", "ready_timeout": "Nobody accepted in time.",
                         "opponent_left": "Your opponent left.",
                         "udp_unreachable": "No UDP connection to the lobby server (firewall?).",
                         "no_connection": "Could not connect the two PCs, not even through the relay."
                         }.get(ev["reason"], f"Match cancelled ({ev['reason']})."))
        elif t == "match_start":
            self.hide_bar()
            self.ready_deadline = None
            self.rematch_bar = None
            self.lag = None
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
                self.rematch_bar = None
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
        self.view.after_event(ev)
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
            self.show_bar(f"{n['opponent']} wants a rematch", [("Rematch", lambda: self._rematch(True), "cross"),
                                                               ("No thanks", lambda: self._rematch(False),
                                                                "circle")])
        self.view.after_driver(n)

    def _answer_result(self, what):
        self.hide_bar()
        if self.driver:
            self.driver.answer(what)
        self.status("Result sent; waiting for your opponent's report...")

    def _rematch(self, accept):
        self.view.rematch_sent(bool(accept))
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
        rtt_of = {}
        for p in ev.get("players", []):
            status = STATUS_TEXT.get(p["status"], p["status"])
            if p["build"] != mine:
                status += " (other version)"
            ms = None if p["rtt"] is None or (me and p["id"] == me["id"]) else p["rtt"] + my_rtt
            rtt_of[p["id"]] = ms
            ping = "" if ms is None else f"~{ms:.0f} ms"
            rating = "" if p["guest"] else p["rating"]
            rec = p.get("record") or [0, 0, 0]
            name = p["name"] + ("  (you)" if me and p["id"] == me["id"] else "")
            main = self.table.fighter_name(p.get("main")) if p.get("main") else ""
            tags = ("me",) if me and p["id"] == me["id"] else ("other",) if p["build"] != mine else ()
            self.tv_players.insert("", "end", iid=p["id"], values=(name, rank_text(p), rating,
                                                                   f"{rec[0]}W {rec[1]}L", main, status, ping),
                                   image=self.view.ping_image(ms), tags=tags)
        for iid in keep:
            if self.tv_players.exists(iid):
                self.tv_players.selection_set(iid)
        keep = self.tv_rooms.selection()
        self.tv_rooms.delete(*self.tv_rooms.get_children())
        for r in ev.get("rooms", []):
            state = r["status"] + (" (other version)" if r["build"] != mine else "") + (" ranked" if r["ranked"]
                                                                                        else "")
            closed = r["status"] != "open" or r["build"] != mine      # the lock: nobody can join it now
            ms = rtt_of.get(r["owner"].get("id"))
            self.tv_rooms.insert("", "end", iid=r["id"], values=(r["name"], r["owner"]["name"], state,
                                                                 "" if ms is None else f"~{ms:.0f} ms"),
                                 image=self.view.room_image(closed), tags=("closed",) if closed else ())
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

    def _ready_text(self):
        """The blind ready check: only the ping and the rules, and the seconds left."""
        m = self.match or {}
        ping = m.get("ping") or {}
        if ping.get("known"):
            where = f"ping about {ping.get('ms', 0):.0f} ms (through the server; measured directly once you both accept)"
        else:
            where = "ping not known yet"
        left = max(0, int((self.ready_deadline or 0) - time.monotonic() + 0.99)) if self.ready_deadline else 0
        return (f"Opponent found{' -- RANKED' if m.get('ranked') else ''} -- {where} -- accept within {left} s?")

    def _tick_ready(self):
        """Keep the countdown in the ready bar current."""
        if self.ready_deadline is None or self.ready_sent or not self.match or not self.match.get("blind"):
            return
        self.bar_text.set(self._ready_text())

    def _ready(self, accept):
        m = self.match
        if not m:
            return
        self.ready_sent = bool(accept)
        self.show_bar(self.bar_text.get() + (" -- waiting for the opponent..." if accept else ""), [])
        self.call(self.client.ready, accept, m["match"])

    def _show_lag(self, ev):
        """After a match: ping X should mean Y frames behind, it was Z -- and a way out when it was worse."""
        self.lag = ev
        self.match_var.set("Lag check: " + ev["text"])
        self.status("Lag check: " + ev["text"])
        if self.rematch_bar is not None:
            self._show_rematch_bar()

    def _set_ended(self, ev):
        self.set_locked = False
        if self.rematch_bar is not None:
            self.rematch_bar = None
            self.hide_bar()
        reason, by = ev.get("reason"), ev.get("by")
        if reason == "lag":
            self.status("You left after the lag check. No penalty, no rating change." if by == "you" else
                        "Your opponent left after the lag check. No penalty for anyone.")
        elif by == "opponent":
            self.status("Your opponent left. The set is over.")
        if self.client:
            self._set_actions()

    def _show_rematch_bar(self):
        text, opp = self.rematch_bar
        buttons = [(f"Rematch {opp}", lambda: self._rematch(True), "cross"),
                   ("Next game", self._next_game),
                   ("Leave", lambda: self._rematch(False), "circle"),
                   (f"Block {opp}", lambda: self.block_opponent(opp))]
        lag = self.lag
        if lag and lag.get("verdict") == "more_lag" and lag.get("can_leave"):
            buttons.insert(3, ("Leave: too laggy", self._leave_for_lag))
        self.show_bar(text, buttons)

    def _next_game(self):
        """After a game: no rematch, search again the way the player searched last."""
        mode = self._pad_search_mode()
        self.rematch_bar = None
        self._rematch(False)
        if mode:
            self.do_queue(mode)

    def _leave_for_lag(self):
        self.hide_bar()
        self.rematch_bar = None
        self.call(self.client.leave_set, "lag", then=lambda _r: self.status(
            "You left after the lag check. No penalty, no rating change."))

    def _show_result(self, ev):
        self.match = None
        self.last_result = ev
        if hasattr(self.app, "report_problem") and not self.report_btn.winfo_ismapped():
            self.report_btn.pack(side="right")
        st = ev["status"]
        text = RESULT_TEXT.get(st, st)
        if ev.get("reason") and ev["reason"] in REASON_TEXT:
            text += f" ({REASON_TEXT[ev['reason']]})"
        mine = None
        if ev.get("winner") is not None and self.driver is not None and self.driver.session_ticket is not None:
            mine = ev["winner"] == self.driver.session_ticket.slot
        self.view.result(ev, mine, text)              # the result card: banner, score, rating, rank
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
            self.rematch_bar = (text if len(text) < 60 else "Rematch?", opp)
            self._show_rematch_bar()
        if self.client and self.client.me:
            self._show_me()

    # ------------------------------------------------------------------ controller (padnav.py)
    # A pad or arcade stick runs the whole online loop: Cross (A) accepts a found match or a challenge,
    # starts the rematch, and searches; Circle (B) declines, leaves, and stops the search. Which stick
    # button is Cross comes from the game's controls.ini. Triangle (Y) is read but unused: every match
    # gets a random stage from the server (a rematch too), so there is no stage choice to make.
    def _tab_viewable(self):
        return bool(self.parent.winfo_viewable())

    def start_pad(self, sources=None, foreground=None, clock=None, thread=True):
        """Start reading controllers (once). The launcher does it when the tab is first shown. Tests
        pass fake sources and a clock, and drive `tab.pad.step(now)` themselves with thread=False."""
        if self.pad is not None:
            return self.pad
        if sources is None:
            if os.environ.get("T5_PAD_NAV") == "0":
                return None
            sources = padnav.default_sources()
            if not sources:                 # (not Windows, no scripted pad)
                return None
        if foreground is None:
            foreground = padnav.window_foreground_check(padnav.toplevel_hwnd(self.parent.winfo_toplevel()))
        settings = self.app.settings
        files = padmap.ControlsFile(lambda: _controls_path_for(settings))
        self.pad = padnav.PadNav(sources, controls=files, foreground=foreground, **({"clock": clock} if clock else {}))
        self.pad.enabled = bool(self.pad_var.get())
        self.pad.visible = self._safe_visible()
        if thread:
            self.pad.start()
        return self.pad

    def _safe_visible(self):
        try:
            return bool(self.pad_visible())
        except tk.TclError:
            return False

    def _pad_toggle(self):
        self._save_cfg()
        if self.pad is not None:
            self.pad.enabled = bool(self.pad_var.get())
        self._pad_relabel()
        self._pad_info()

    def _pad_on(self):
        return self.pad is not None and bool(self.pad_var.get()) and self.pad.has_devices()

    def _pad_label(self, text, button):
        """'Accept' -> 'Accept (A)' while a pad is plugged in: the controller button that presses it."""
        if button and self._pad_on():
            name = self.pad.label(button)
            if name:
                return f"{text} ({name})"
        return text

    def _pad_search_mode(self):
        """The search the controller's A button starts: the one used last, else ranked (accounts), else quick."""
        on = {k: str(self.actions[k].cget("state")) == "normal" for k in ("ranked", "quick")}
        last = self.cfg.get("last_search")
        for mode in ([last] if last in on else []) + ["ranked", "quick"]:
            if on.get(mode):
                return mode
        return None

    def _pad_plan(self):
        """What the controller buttons do right now: {'cross': (action key or None, command), ...}."""
        plan = {}
        if self.client is None:
            return plan
        if self.bar.winfo_manager():               # a question is up: its own buttons answer, nothing else
            return {b: (None, fn) for b, fn in self.bar_pad.items()}
        if str(self.actions["cancel"].cget("state")) == "normal":
            plan["circle"] = ("cancel", self.actions["cancel"].invoke)
        mode = self._pad_search_mode()
        if mode:
            plan["cross"] = (mode, self.actions[mode].invoke)
        return plan

    def _pad_relabel(self):
        """Put the controller button names on the buttons that the pad presses (and take them off)."""
        if not hasattr(self, "pad_var"):
            return                                   # (the UI is still being built)
        plan = self._pad_plan() if self._pad_on() else {}
        for key, b in self.actions.items():
            pb = next((pb for pb, (k, _fn) in plan.items() if k == key), None)
            text = self._pad_label(self.action_text[key], pb)
            if str(b.cget("text")) != text:
                b.configure(text=text)
        for b, label, pb in self.bar_spec:
            text = self._pad_label(label, pb)
            try:
                if str(b.cget("text")) != text:
                    b.configure(text=text)
            except tk.TclError:
                pass

    def _pad_info(self):
        p = self.pad
        if not self.pad_var.get():
            text = "Controller off."
        elif p is None or not p.stats["polls"]:
            text = ""
        elif not p.has_devices():
            text = "No controller found."
        else:
            text = "Controller: " + p.summary
        if text != self.pad_info_var.get():
            self.pad_info_var.set(text)

    def _pad_tick(self):
        """Every poll: tell the pad thread whether the tab is showing, refresh the names, run the presses."""
        p = self.pad
        if p is None:
            return
        p.visible = self._safe_visible()
        p.enabled = bool(self.pad_var.get())
        if p.generation != self._pad_gen:
            self._pad_gen = p.generation
            self._pad_relabel()
        self._pad_info()
        try:
            while True:
                self._pad_press(p.events.get_nowait())
        except queue.Empty:
            pass

    def _pad_press(self, ev):
        p = self.pad
        now = p.clock()
        if now - ev.t > PAD_STALE_S or now < self._pad_until:
            return
        # The pad thread looked at the foreground window when it saw the press; look again, since a dialog
        # or the game may have come forward since. The same for the tab and the switch.
        if not (self.pad_var.get() and p.foreground_now() and self._safe_visible()):
            return
        act = self._pad_plan().get(ev.button)
        if act is None:
            return
        self._pad_until = now + PAD_COOLDOWN_S
        act[1]()

    # ------------------------------------------------------------------ problem report
    def do_report(self):
        fn = getattr(self.app, "report_problem", None)
        if fn:
            fn()

    def report_info(self):
        """Technical lines about the lobby and the last match for the problem report. No names,
        addresses, keys or tokens: the report tool cleans every file again, this is the first filter."""
        L = []

        def add(label, fn):
            try:
                L.append(f"{label}: {fn()}")
            except Exception as e:      # noqa: BLE001 -- whatever is missing stays out
                L.append(f"{label}: ? ({e})")
        c = self.client
        add("Server", lambda: self._server_key())
        add("Logged in", lambda: "no" if not (c and c.me) else ("as a guest" if c.me.get("guest") else "with an account"))
        add("Encrypted connection", lambda: bool(c and c.tls))
        add("Ping to the server (ms)", lambda: f"{c.server_rtt:.0f}" if c and c.server_rtt else "?")
        add("Game mode setting", lambda: self.cfg.get("game_mode", "auto"))
        d = self.driver
        if d is not None:
            add("Match driver mode", lambda: d.mode)
            add("Games that failed to answer", lambda: d.ctl_failures)
            add("Speed of this PC in its last match (fps)", lambda: d.last_fps)
            add("Matches reported", lambda: [(h[0], h[1].get("source")) for h in d.history[-6:]])
            t = d.session_ticket
            if t is not None:
                add("Last match", lambda: (f"id {t.match_id}, {t.role} slot {t.slot}, path {t.path}, ping {t.rtt_ms:.0f} ms, "
                                           f"jitter {t.jitter_ms:.0f} ms, delay {t.delay}, rounds {t.rounds}, "
                                           f"ranked {t.ranked}, input delay {t.input_delay}, build {t.build}"))
        r = self.last_result
        if r:
            keep = ("match", "status", "reason", "winner", "score", "blame", "ranked", "fight", "rematch_window")
            add("Last result", lambda: {k: r.get(k) for k in keep})
        return "\n".join(L) + "\n"

    # ------------------------------------------------------------------ launcher hooks
    def on_show(self):
        self.start_pad()
        if self.client:
            self._set_actions()
        else:
            self.try_saved_login()

    def on_close(self):
        try:
            self.parent.after_cancel(self._after)
        except (tk.TclError, ValueError):
            pass
        self.view.close()
        if self.pad is not None:
            self.pad.stop()
            self.pad = None
        if self.driver is not None:
            self.driver.close()
            self.driver = None
        if self.client:
            self.client.close()
            self.client = None
        self.stop_hosting(wait=3.0)

    # ------------------------------------------------------------------ Host for friends
    def do_host(self):
        if self.host_proc is not None:
            self.stop_hosting()
            return
        run_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")
        cmd = [sys.executable, "-u", run_py, "host", "--json", "--stdin-control"] + list(self.host_args)
        if self.map_var.get():
            cmd.append("--map-ports")
        try:
            self.host_proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            self.status(f"Cannot start the lobby server: {e}")
            return
        self.b_host.configure(text="Stop hosting")
        self.status("Starting a lobby server on this PC" + (" and asking the router to forward its ports"
                                                           if self.map_var.get() else "") + "...")
        proc = self.host_proc

        def read():
            for line in proc.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                self.ui_q.put(lambda ev=ev: self._host_event(proc, ev))
            self.ui_q.put(lambda: self._host_event(proc, {"event": "exited"}))
        threading.Thread(target=read, daemon=True).start()

    def _host_event(self, proc, ev):
        if proc is not self.host_proc:
            return
        kind = ev.get("event")
        if kind == "ready":
            self.host_info = ev
            self.server_var.set(ev["local"])
            share = ev.get("internet") or f"<your public IP>:{ev['port']}" + (
                f"#{ev['fingerprint']}" if ev.get("fingerprint") else "")
            try:
                self.parent.clipboard_clear()
                self.parent.clipboard_append(share)
            except tk.TclError:
                pass
            self.chat_line(f"Hosting. Friends paste this as their Server (copied to the clipboard):\n  {share}"
                           + (f"\n  same network: {ev['lan']}" if ev.get("lan") else "")
                           + ("" if ev.get("mapped") else "\n  Forward TCP+UDP 7781 and UDP 7782 on your router"
                              " (or tick 'Open router ports')."))
            self.status("Hosting a lobby on this PC. Log in to join it yourself.")
            self.view.hosting(ev)
        elif kind == "error":
            self.status(f"Hosting failed: {ev.get('message')}", error=True)
        elif kind in ("stopped", "exited"):
            self.host_proc = None
            self.host_info = None
            self.view.hosting(None)
            self.b_host.configure(text="Host for friends")
            if kind == "exited" and proc.poll() not in (0, None):
                self.status(f"The lobby server stopped (exit code {proc.returncode}); see its log in "
                            "%LOCALAPPDATA%\\T5DR Online\\lobby-host\\logs.")
            else:
                self.status("Stopped hosting.")

    def stop_hosting(self, wait=0.0):
        proc = self.host_proc
        if proc is None:
            return
        try:
            proc.stdin.write("stop\n")
            proc.stdin.flush()
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        if wait:
            try:
                proc.wait(wait)
            except subprocess.TimeoutExpired:
                proc.kill()


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
    theme.enable_dpi_awareness()
    root = tk.Tk()
    root.title("T5DR Online -- lobby (standalone)")
    root.geometry("1100x780")
    app = _FakeApp()
    tab = OnlineTab(root, app)
    tab.server_var.set(a.server)
    tab._build_info = lambda: (BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "standalone", "dev"), None)
    root.protocol("WM_DELETE_WINDOW", lambda: (tab.on_close(), root.destroy()))
    root.after(200, tab.on_show)        # (the launcher calls this when the tab is selected)
    root.mainloop()


if __name__ == "__main__":
    main()
