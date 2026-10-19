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

Friends (docs/ONLINE.md "Friends and invites", accounts on a server that has them): the Friends page lists them with who is
online / in a match / offline, sends and answers requests, removes, and invites a friend to a casual match or to
this player's room; an invite from a friend comes up like a challenge, Accept (A) starts it with one click.

Discord Rich Presence (optional, launcher Settings, off by default): t5lobby.discord_rpc shows "In lobby",
"Searching ranked" or "In match: Jin vs Kazuya (Ranked, Set 1-0)" with a timer in the player's Discord status,
through the Discord app on this PC; without Discord running it does nothing.

Ranked sets (docs/RANKED.md "Ranked sets"): a ranked set is best of 3 and rated once at its end. One label
shows where it stands ("Set 1-0 -- game 2 of 3", t5lobby.sets.status_text); between two games the bar
counts down to the next game (it starts by itself) and offers "Leave set" (a loss); the set's result and
its one rating change come with set_end (t5lobby.sets.result_text).

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

from . import discord_rpc, fighters, lag, padmap, padnav, proto, ranks, servers, sets
from .buildid import BuildInfo
from .client import LobbyClient
from .i18n import N_, stamp, t, translate_message
from .match_driver import MatchDriver, fps_from_logs, game_supports_pick
from .proto import DEFAULT_PORT, LobbyError
from . import theme, tk_views, winfront
from .ranks import record_label as _record

AVAILABLE = True
DEFAULT_SERVER = f"127.0.0.1:{DEFAULT_PORT}"
# What the server's codes mean, in English; shown through _word() (t() on the text, the code itself if unknown).
STATUS_TEXT = {"idle": N_("in lobby"), "room": N_("in a room"), "queue": N_("searching"), "match": N_("matching"),
               "playing": N_("playing")}
ROOM_STATE_TEXT = {"open": N_("open"), "full": N_("full"), "playing": N_("playing")}
RESULT_TEXT = {"confirmed": N_("Result confirmed"), "onesided": N_("Result recorded (your opponent did not report)"),
               "forfeit": N_("Match decided by forfeit"), "resolved": N_("Result decided by the games' state"),
               "disputed": N_("You and your opponent reported different results -- not counted"),
               "void": N_("No result")}
RESULT_WORD = {"confirmed": N_("confirmed"), "onesided": N_("one-sided"), "forfeit": N_("forfeit"),
               "resolved": N_("resolved"), "disputed": N_("disputed"), "void": N_("void")}
OUTCOME_WORD = {"win": N_("win"), "loss": N_("loss"), "draw": N_("draw")}
REASON_TEXT = {"desync": N_("the two games went out of sync"), "too_short": N_("too short to count"),
               "disputed": N_("the reports disagreed"), "crash": N_("a game crashed"),
               "early_quit": N_("left right away"),
               "quit": N_("a player left"), "disconnect": N_("a player lost the connection"),
               "connection": N_("the connection between the games failed"), "no_report": N_("a player did not report"),
               "both_left": N_("both players left"), "timeout": N_("no result in time"),
               "crash_repeat": N_("repeated crashes count as losses"), "early_quit_repeat": N_("repeated early quits"),
               "no_report_repeat": N_("repeated missing reports"), "score_mismatch": N_("scores differed"),
               "no_result": N_("the fight ended without a winner")}
CANCEL_TEXT = {"declined": N_("Match declined."), "ready_timeout": N_("Nobody accepted in time."),
               "opponent_left": N_("Your opponent left."),
               "udp_unreachable": N_("No UDP connection to the lobby server (firewall?)."),
               "no_connection": N_("Could not connect the two PCs, not even through the relay."),
               "relay_full": N_("The lobby server's relay is full; try again in a moment.")}
CHALLENGE_TEXT = {"declined": N_("Challenge declined."), "cancelled": N_("Challenge cancelled."),
                  "expired": N_("Challenge expired.")}
# A friend's state in the Friends list: the lobby status when online (STATUS_TEXT), else these.
FRIEND_STATE_TEXT = {"in_match": N_("in a match"), "offline": N_("offline")}
FRIEND_INVITE_TEXT = {"update": N_("(older launcher: no invites)"), "version": N_("(other version)")}
PATH_TEXT = {"direct": N_("direct"), "lan": N_("local network"), "relay": N_("via the lobby server's relay")}
PAD_STALE_S = 1.0       # a controller press this old by the time the tab sees it (a dialog held the loop) is dropped
PAD_COOLDOWN_S = 0.6    # after a controller action the next one waits (A and B hit together do only one thing)


def _word(table, key):
    """The text for a code the server sent: translated when it is in `table`, else the code itself."""
    return t(table[key]) if key in table else str(key)


def lobby_error_text(e):
    """What a player reads for a failed lobby request: the server's (or client's) English message in the
    player's language when it is a known one, else as it came."""
    return t("Lobby: {message}", message=translate_message(e.msg or e.code))


def _work(results, key, fn, args):
    """Worker thread body for OnlineTab.call (a module function: it must not reference the tab)."""
    try:
        results.put((key, True, fn(*args)))
    except LobbyError as e:
        results.put((key, False, lobby_error_text(e)))
    except Exception as e:   # noqa: BLE001 -- shown to the player, not swallowed
        results.put((key, False, t("Lobby error: {error}", error=e)))


def online_dir():
    """Per-user folder for the Online tab's settings (never inside the program folder)."""
    d = os.environ.get("T5_ONLINE_DIR")
    if not d:
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
        d = os.path.join(base, "T5DROnline")
    return d


def rank_text(p):
    if p.get("guest"):
        return t("guest")
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
        self.bring_forward = winfront.raise_window    # the launcher's window to the front (tests replace it)
        self._fronted = None                          # what it last came forward for (once per match / question)
        self.codes_window = None
        self.ready_deadline = None       # monotonic time the ready check ends (accepting is still possible)
        self.ready_sent = False          # we accepted: waiting for the opponent
        self.set_locked = False          # a ranked set is running: the character cannot change
        self.rematch_bar = None          # (text, opponent name) while the "Rematch?" bar is up
        self.lag = None                  # the last lag_check event
        self.set_bar = None              # (set info, my slot, monotonic end of the countdown) between two games of a set
        self.blocks_window = None        # the "Blocked players..." dialog
        self.blocks_list = None
        self.pad = None                  # padnav.PadNav once the tab has been shown (controller buttons)
        self.pad_visible = self._tab_viewable      # tests replace it (their window is withdrawn)
        self.invite = None               # an invite from a friend waiting for this player's answer (the `invited` event)
        self.outgoing_invite = None      # this player's own invite waiting for the friend's answer
        self.friend_rows = {}            # Friends page row id -> friend / request
        self.presence = None             # discord_rpc.DiscordPresence while Rich Presence is on
        self.discord_paths = None        # where the Discord app listens (None: its usual pipes; tests: a fake one)
        self._presence_last = None
        self._presence_key = None
        self._presence_t0 = None
        self._match_info = None          # the running match for Rich Presence: ranked, slot, fighters, set
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
        self.me_var = tk.StringVar(value=t("Not connected. Ranked needs an account; guests play casual matches."))
        self.hint_var = tk.StringVar(value=t("Passwords are only sent to servers on this PC / your network, or "
                                             "over an encrypted (TLS) connection."))
        self.char_var = tk.StringVar(value=self.table.fighter_name(self.cfg.get("char") or fighters.RANDOM))
        self.strict_var = tk.IntVar(value=1 if self.cfg.get("strict") else 0)
        self.bar_text = tk.StringVar()
        self.match_var = tk.StringVar(value="")
        # A ranked set's score ("Set 1-0, game 2 of 3"): shown as a tag on the match cards when set
        # (empty: the cards say "game N" from the server's set info by themselves).
        self.set_var = tk.StringVar(value="")
        self.chat_var = tk.StringVar()
        self.prof_title = tk.StringVar(value=t("Double-click a player in the lobby or the leaderboard."))
        self.prof_text = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.notice_var = tk.StringVar(value="")          # a message from the server's admin, until it ends
        # controller: A / Cross accepts, B / Circle declines (padnav.py, docs/ONLINE.md)
        self.pad_var = tk.IntVar(value=1 if self.cfg.get("pad", True) else 0)
        self.pad_info_var = tk.StringVar(value="")
        # friends (the Friends page of tk_views)
        self.friend_name_var = tk.StringVar(value="")
        self.friends_note_var = tk.StringVar(value="")
        self.friends_count_var = tk.StringVar(value="")
        self.requests_count_var = tk.StringVar(value="")
        self.view = tk_views.OnlineView(self)
        self._set_account_view(False)

    def _set_account_view(self, logged_in):
        self.view.set_logged_in(logged_in)

    def _set_actions(self):
        me = self.client.me if self.client and self.client.connected else None
        st = (me or {}).get("status")
        guest = (me or {}).get("guest", True)
        busy = self.match is not None or (self.driver is not None and self.driver.ticket is not None) or \
            self.set_bar is not None          # between two games of a ranked set: the next one comes by itself
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
        self._set_friend_actions()
        self._pad_relabel()
        self.view.refresh()

    def _show_me(self):
        c = self.client
        if not c or not c.me:
            return
        me = c.me
        if me["guest"]:
            parts = [t("{name} (guest, casual matches only)", name=me["name"]),
                     t("{record} this session", record=_record(me["record"]))]
        else:
            parts = [me["name"], rank_text(me), t("rating {rating}", rating=me["rating"]), _record(me["record"])]
            if me.get("main"):
                parts.append(t("main {character}", character=self.table.fighter_name(me["main"])))
        parts.append(t("server ping {ms} ms", ms=f"{c.server_rtt or 0:.0f}"))
        if c.tls:
            parts.append(t("encrypted"))
        self.me_var.set(" -- ".join(parts))

    def status(self, text, error=False):
        """One line for the player; error=True also puts it on the red banner, with what to do."""
        text = proto.scrub_addresses(str(text))       # no IP address in anything the player reads
        self.status_var.set(text)
        self.view.status_changed(text, error)
        if hasattr(self.app, "set_status"):
            try:
                # the server's notice stays in the launcher's status bar whatever else is said
                self.app.set_status(text + ("   " + t("[Server: {notice}]", notice=self.notice_var.get())
                                            if self.notice_var.get() else ""))
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
                    self.app.set_status(t("Server notice: {notice}", notice=line))
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
        self._tick_set()
        self._presence_tick()
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
            return None, st.get("text") or t("The game is not built.")
        try:
            rel = "dev"
            try:
                import core   # the launcher's module, when we run inside it
                rel = core.release_info().get("version", "dev")
            except Exception:
                pass
            return BuildInfo.from_out_dir(self.app.settings.out_dir, rel), None
        except (OSError, ValueError) as e:
            return None, t("Cannot read the build's identity: {error}", error=e)

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
                        plain_passwords=bool(self.cfg.get("plain_passwords")), blind_ready=True,
                        ingame_pick=self._game_can_pick(),
                        sets=bool(self.cfg.get("sets", True)),   # online.json "sets": false: no ranked sets
                        # launcher Settings -> "Open the game's port on my router" (docs/NETPLAY.md)
                        port_mapping=bool(getattr(self.app, "settings", {}).get("router_ports", True)))
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

    def _game_can_pick(self):
        """This PC's game picks the characters on its own select screen (in-game select)."""
        out = getattr(self.app.settings, "out_dir", os.getcwd())
        return game_supports_pick([os.path.join(out, "build", "cmake", "t5dr.exe"),
                                   os.path.join(out, "build", "cmake", "t5dr_game.dll")])

    def do_login(self, mode, session=None):
        name, pw = self.name_var.get().strip(), self.pw_var.get()
        server = self.server_var.get().strip() or DEFAULT_SERVER
        build, err = self._build_info()
        if build is None:
            self.status(err, error=True)
            return
        if mode in ("account", "register") and not pw:
            self.status(t("Enter a password (6 characters or more), or play as a guest."), error=True)
            return
        if mode == "register" and not self._confirm_password(pw):
            return
        remember = bool(self.remember_var.get())
        self._save_cfg()
        self.status(t("Connecting to {server}...", server=server))
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
            hint = t("Pick a character, then Ranked match (accounts) or Quick match.")
            if client.ingame_pick and "ingame_pick" in (w.get("features") or []):
                hint = t("Ranked match (accounts) or Quick match; then pick your fighter in the game (Select = "
                         "random). The character here is used when you do not pick in time.")
            if w.get("motd"):
                hint = w["motd"]
            self.hint_var.set((t("Encrypted connection (TLS).") + " " if client.tls else "") + hint)
            self.status(t("In the lobby.") + (" " + t("(logged in with your saved login)")
                                              if mode == "session" else ""))
            self._set_actions()
            self.on_char()
            if client.recovery_codes:
                self.show_codes(client.recovery_codes, first=True)

        def failed():
            if mode == "session":
                self._remember_session(None, None)
                self.status(t("Your saved login has expired; log in with your password."))

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
            again = self.ask_string(t("Create account"), t("Type the password again:"), show="*", parent=self.parent)
        if again is None:
            return False
        if again != pw:
            self.status(t("The two passwords differ."), error=True)
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
            self.status(t("Closing the running game for the online match..."))
            g.stop()
            t_end = time.monotonic() + 5
            while g.running() and time.monotonic() < t_end:
                time.sleep(0.1)
        return self.app.start_game(env)

    def do_logout(self):
        forget = False
        if self.client and self.client.session:
            forget = self.ask_yes_no(t("Log out"), t("Also forget the saved login on this PC?\n\n"
                                                      "(No = you are logged in automatically next time.)"),
                                     parent=self.parent)
        c, self.client = self.client, None
        if forget:
            self._remember_session(None, None)
        if self.driver is not None:
            self.driver.close()
            self.driver = None
        if c:
            threading.Thread(target=lambda: c.logout(forget=forget), daemon=True).start()
        self._reset_lobby_view()
        self.me_var.set(t("Not connected."))
        self._set_account_view(False)
        self._set_actions()

    def _reset_lobby_view(self):
        self.match = None
        self.invite = None
        self.outgoing_invite = None
        self._match_info = None
        self.friend_rows = {}
        for tv in (self.tv_friends, self.tv_requests):
            tv.delete(*tv.get_children())
        self.friends_count_var.set("")
        self.requests_count_var.set("")
        self._friends_tab_label(0)
        self.ready_deadline = None
        self.set_locked = False
        self.rematch_bar = None
        self.set_bar = None
        self.set_var.set("")
        self.lag = None
        self.notice_var.set("")
        self.view.reset()
        self.hide_bar()
        self.match_var.set("")
        self.tv_players.delete(*self.tv_players.get_children())
        self.tv_rooms.delete(*self.tv_rooms.get_children())

    def do_passwd(self):
        title = t("Change password")
        old = self.ask_string(title, t("Current password:"), show="*", parent=self.parent)
        if not old:
            return
        new = self.ask_string(title, t("New password (6 characters or more):"), show="*", parent=self.parent)
        if not new:
            return
        if self.ask_string(title, t("New password again:"), show="*", parent=self.parent) != new:
            self.status(t("The two new passwords differ."))
            return
        remember = bool(self._saved_session())
        c = self.client

        def done(_r):
            self._remember_session(c.me["name"], c.session if remember else None)
            self.status(t("Password changed. Saved logins on other PCs have ended."))
        self.call(c.change_password, old, new, remember, then=done)

    def do_new_codes(self):
        pw = self.ask_string(t("Recovery codes"), t("Your password (the old codes stop working):"), show="*",
                             parent=self.parent)
        if pw:
            self.call(self.client.new_recovery_codes, pw, then=lambda codes: self.show_codes(codes))

    def show_codes(self, codes, first=False):
        def save(w):
            p = filedialog.asksaveasfilename(parent=w, title=t("Save recovery codes"), defaultextension=".txt",
                                             initialfile="t5dr-recovery-codes.txt")
            if p:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(t("T5DR Online recovery codes for {name} on {server}",
                              name=self.client.me["name"] if self.client else "", server=self.server_var.get())
                            + "\n" + "\n".join(codes) + "\n")
        self.codes_window = self.view.codes_window(codes, first, save)

    def do_forgot(self):
        build, err = self._build_info()
        if build is None:
            self.status(err)
            return
        title = t("Forgot password")
        name = self.ask_string(title, t("Account name:"), initialvalue=self.name_var.get(), parent=self.parent)
        if not name:
            return
        code = self.ask_string(title, t("One of your recovery codes (XXXX-XXXX-XXXX):"), parent=self.parent)
        if not code:
            return
        new = self.ask_string(title, t("New password (6 characters or more):"), show="*", parent=self.parent)
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
            self.status(t("Password reset. {count} recovery code(s) left. Log in with the new password.",
                          count=r["codes_left"]))
        self.call(work, then=done)

    def do_fingerprint(self):
        fp = self.ask_string(
            t("Server certificate"),
            t("For a server with its own (self-signed) certificate: its SHA-256 fingerprint, from whoever runs "
              "it.\nEmpty = no pinning (use tls://host:port for a server with a normal certificate)."),
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
        self.call(fn, *args, then=lambda _r: self.status(self._searching_text(mode, strict)))

    @staticmethod
    def _searching_text(mode, strict):
        if mode != "ranked":
            return t("Searching for an opponent...")
        if strict:
            return t("Searching for an opponent (ranked: similar rank and a good connection, strict: within 150 "
                     "rating points -- this can take a while)...")
        return t("Searching for an opponent (ranked: similar rank and a good connection)...")

    def do_join(self):
        sel = self.tv_rooms.selection()
        if not sel:
            self.status(t("Select a room first."))
            return
        self.call(self.client.join_room, sel[0])

    def do_challenge(self):
        sel = self.tv_players.selection()
        if not sel or (self.client.me and sel[0] == self.client.me["id"]):
            self.status(t("Select an opponent in the list first."))
            return
        self.call(self.client.challenge, sel[0], then=lambda _r: self.status(t("Challenge sent.")))

    def do_blocked(self):
        """The block list, with Unblock."""
        if not self.client:
            return
        self.call(self.client.blocks, then=self._blocks_window)

    def _blocks_window(self, rows):
        px = self.view.px
        w = self.new_window(self.parent)
        w.title(t("Blocked players"))
        bar = self.view.card(w, pad=16)                  # (the buttons are children of this frame)
        bar.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text=t("Blocked players"), style="Card.H2.TLabel").grid(row=0, column=0, columnspan=2,
                                                                              sticky="w")
        ttk.Label(bar, wraplength=px(380), justify="left", style="Card.Muted.TLabel", text=t(
            "You are never matched with these players (ranked, quick matches, rooms, challenges, rematches). "
            "They are not told. Accounts stay blocked; a guest is blocked until you log out.")).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(px(4), px(10)))
        lb = tk.Listbox(bar, height=max(4, min(12, len(rows))), width=32, activestyle="none")
        names = [r["name"] for r in rows]                 # (the list shows more than the name: index -> name)
        for r in rows:
            lb.insert("end", r["name"] + ("  (" + t("guest") + ")" if r.get("guest") else ""))
        lb.grid(row=2, column=0, columnspan=2, sticky="we")
        self.blocks_list = lb

        def unblock():
            sel = lb.curselection()
            if not sel:
                return
            name = names.pop(sel[0])
            lb.delete(sel[0])
            self.call(self.client.unblock, name, then=lambda _r: self.status(t("Unblocked {name}.", name=name)))
        ttk.Button(bar, text=t("Unblock"), style="Card.TButton", command=unblock).grid(row=3, column=0, sticky="w",
                                                                                      pady=(px(12), 0))
        ttk.Button(bar, text=t("Close"), style="Card.Accent.TButton", command=w.destroy).grid(
            row=3, column=1, sticky="e", pady=(px(12), 0))
        self.blocks_window = w

    def block_opponent(self, name):
        """After a game: never meet this player again. A running match would end like a quit (not offered here)."""
        if not self.ask_yes_no(t("Block player"),
                               t("Block {name}?\n\nYou will not be matched with them again. They are not told. You "
                                 "can unblock them under \"Blocked players...\".", name=name),
                               parent=self.parent):
            return
        self.hide_bar()
        self.rematch_bar = None

        def done(_r):
            self.status(t("Blocked {name}. You will not be matched again.", name=name))
        self.call(self.client.block, name, then=done)

    def do_chat(self):
        text = self.chat_var.get().strip()
        if text and self.client:
            self.chat_var.set("")
            self.call(self.client.chat, text)

    # ------------------------------------------------------------------ friends (docs/ONLINE.md "Friends and invites")
    def _friends_ok(self):
        """Logged in with an account on a server that keeps friends."""
        c = self.client
        has = getattr(c, "has_friends", None)
        return bool(c is not None and c.me and not c.me.get("guest") and callable(has) and has())

    def _friends_tab_label(self, waiting):
        try:
            self.nb.tab(self.friends_page, text=t("Friends ({count})", count=waiting) if waiting else t("Friends"))
        except tk.TclError:
            pass

    def _friend_state_text(self, f):
        st = f.get("status")
        text = _word(STATUS_TEXT, f.get("activity") or "idle") if st == "online" else _word(FRIEND_STATE_TEXT, st)
        if st == "offline" and f.get("last_seen"):
            text = t("offline, last seen {when}", when=stamp(f["last_seen"]))
        if f.get("invite") in FRIEND_INVITE_TEXT:
            text += " " + _word(FRIEND_INVITE_TEXT, f["invite"])
        return text

    def _fill_friends(self):
        """The Friends page from the client's list: friends (online first), then the requests both ways."""
        c = self.client
        if not self._friends_ok():
            if c is not None and c.me and c.me.get("guest"):
                self.friends_note_var.set(t("Friends need an account. Log in with one to add friends and invite them."))
            elif c is not None and c.me:
                self.friends_note_var.set(t("This lobby server has no friends list (it needs version 1.1.2 or newer)."))
            self._set_friend_actions()
            return
        fl = getattr(c, "friend_list", None) or {}
        friends = fl.get("friends") or []
        incoming, outgoing = fl.get("incoming") or [], fl.get("outgoing") or []
        order = {"online": 0, "in_match": 1}
        keep = (self.tv_friends.selection(), self.tv_requests.selection())
        self.friend_rows = {}
        self.tv_friends.delete(*self.tv_friends.get_children())
        for f in sorted(friends, key=lambda f: (order.get(f.get("status"), 2), f["name"].lower())):
            iid = "f:" + f["name"]
            self.friend_rows[iid] = f
            self.tv_friends.insert("", "end", iid=iid, values=(f["name"], rank_text(f), self._friend_state_text(f)),
                                   image=self.view.friend_image(f.get("status")),
                                   tags=() if f.get("status") != "offline" else ("closed",))
        self.tv_requests.delete(*self.tv_requests.get_children())
        for r in incoming:
            iid = "in:" + r["name"]
            self.friend_rows[iid] = r
            self.tv_requests.insert("", "end", iid=iid, values=(r["name"], t("wants to be your friend")))
        for r in outgoing:
            iid = "out:" + r["name"]
            self.friend_rows[iid] = r
            self.tv_requests.insert("", "end", iid=iid, values=(r["name"], t("asked: waiting for an answer")),
                                    tags=("closed",))
        for tv, sel in zip((self.tv_friends, self.tv_requests), keep):
            for iid in sel:
                if tv.exists(iid):
                    tv.selection_set(iid)
        online = sum(1 for f in friends if f.get("status") != "offline")
        self.friends_count_var.set(t("{online} online · {count} of {max}", online=online, count=len(friends),
                                     max=fl.get("max") or 100) if friends else "")
        self.requests_count_var.set(str(len(incoming)) if incoming else "")
        self._friends_tab_label(len(incoming))
        if friends or incoming or outgoing:
            self.friends_note_var.set(t("Your friends see when you are online. Invite one who is online to play."))
        else:
            self.friends_note_var.set(t("No friends yet. Add one by account name: they become your friend when they "
                                        "accept."))
        self._set_friend_actions()

    def _selected_friend(self):
        sel = self.tv_friends.selection() if hasattr(self, "tv_friends") else ()
        return self.friend_rows.get(sel[0]) if sel and sel[0].startswith("f:") else None

    def _selected_request(self):
        """('in' | 'out', name) of the selected request, or (None, None)."""
        sel = self.tv_requests.selection() if hasattr(self, "tv_requests") else ()
        if not sel:
            return None, None
        kind, _x, name = sel[0].partition(":")
        return kind, name

    def _set_friend_actions(self):
        acts = getattr(self, "friend_actions", None)
        if not acts:
            return
        ok = self._friends_ok()
        me = (self.client.me or {}) if self.client else {}
        busy = self.match is not None or (self.driver is not None and self.driver.ticket is not None) or             self.set_bar is not None
        f = self._selected_friend() if ok else None
        free = f is not None and f.get("invite") == "ok" and not busy
        my_room = next((r for r in getattr(self.client, "rooms", None) or [] if me.get("id") in (r.get("members") or [])),
                       None)
        pending = self.outgoing_invite is not None
        kind, _name = self._selected_request() if ok else (None, None)
        on = {"add": ok, "remove": f is not None,
              "invite": ok and (pending or (free and me.get("status") in ("idle", "queue"))),
              "invite_room": free and not pending and me.get("status") == "room" and my_room is not None
              and len(my_room.get("members") or []) < 2,
              "accept": kind == "in", "decline": kind == "in", "cancel_request": kind == "out"}
        for key, b in acts.items():
            try:
                b.configure(state="normal" if on.get(key) else "disabled")
            except tk.TclError:
                pass
        text = t("Cancel the invite") if pending else t("Invite to a match")
        try:
            if str(acts["invite"].cget("text")) != text:
                acts["invite"].configure(text=text)
        except tk.TclError:
            pass

    def do_add_friend(self):
        name = self.friend_name_var.get().strip()
        if not name or not self._friends_ok():
            return

        def done(r):
            self.friend_name_var.set("")
            if r.get("state") == "friends":
                self.status(t("You and {name} are friends now.", name=r.get("name")))
            else:
                self.status(t("Friend request sent to {name}. They become your friend when they accept.",
                              name=r.get("name")))
        self.call(self.client.add_friend, name, then=done)

    def do_friend_answer(self, accept):
        kind, name = self._selected_request()
        if kind != "in":
            return
        self.call(self.client.answer_friend, name, bool(accept), then=lambda _r: self.status(
            t("You and {name} are friends now.", name=name) if accept else t("Request from {name} declined.",
                                                                            name=name)))

    def do_cancel_request(self):
        kind, name = self._selected_request()
        if kind == "out":
            self.call(self.client.cancel_friend_request, name,
                      then=lambda _r: self.status(t("Request to {name} taken back.", name=name)))

    def do_remove_friend(self):
        f = self._selected_friend()
        if f is None:
            return
        name = f["name"]
        if not self.ask_yes_no(t("Remove friend"), t("Remove {name} from your friends?\n\nYou can ask again later; "
                                                     "they have to accept again.", name=name), parent=self.parent):
            return
        self.call(self.client.remove_friend, name, then=lambda _r: self.status(t("{name} is no longer your friend.",
                                                                                 name=name)))

    def do_invite(self, kind):
        if self.outgoing_invite is not None:
            inv = self.outgoing_invite
            self.call(self.client.cancel_invite, inv["invite"])
            return
        f = self._selected_friend()
        if f is None:
            self.status(t("Select a friend in the list first."))
            return

        def done(r):
            self.outgoing_invite = r
            self.status(t("Invite sent to {name}; waiting for an answer ({seconds} s)...", name=r.get("name"),
                          seconds=f"{float(r.get('expires') or 60):.0f}"))
            self._set_friend_actions()
        self.call(self.client.invite, f["name"], kind, then=done)

    def _profile_of_friend(self):
        f = self._selected_friend()
        if f is not None:
            self.show_profile(f["name"])

    def _show_invite(self, ev):
        """A friend invites this player: the question in the bar, Accept (A) starts it with one click."""
        frm = ev.get("from") or {}
        self.invite = ev
        if ev.get("kind") == "room":
            text = t("{name} ({rank}) invites you to the room “{room}”", name=frm.get("name"), rank=rank_text(frm),
                     room=(ev.get("room") or {}).get("name") or "?")
        else:
            text = t("{name} ({rank}) invites you to a casual match", name=frm.get("name"), rank=rank_text(frm))
        self.show_bar(text, [(t("Accept"), lambda: self._answer_invite(True), "cross"),
                             (t("Decline"), lambda: self._answer_invite(False), "circle")])
        self.status(text + ".")

    def _answer_invite(self, accept):
        inv, self.invite = self.invite, None
        self.hide_bar()
        if inv:
            self.call(self.client.answer_invite, inv["invite"], bool(accept))

    def _invite_ended(self, ev):
        name, state = ev.get("name"), ev.get("state")
        if self.invite is not None and ev.get("invite") == self.invite.get("invite"):
            self.invite = None
            if self.challenge is None and self.match is None:
                self.hide_bar()
            if state == "expired":
                self.status(t("The invite from {name} ran out.", name=name))
            elif state == "cancelled":
                self.status(t("The invite from {name} ended.", name=name))
        elif self.outgoing_invite is not None and ev.get("invite") == self.outgoing_invite.get("invite"):
            self.outgoing_invite = None
            if state == "declined":
                self.status(t("{name} declined your invite.", name=name))
            elif state == "expired":
                self.status(t("{name} did not answer your invite.", name=name))
            elif state == "cancelled":
                self.status(t("The invite to {name} ended.", name=name))
        self._set_friend_actions()

    # ------------------------------------------------------------------ Discord Rich Presence (discord_rpc.py)
    def _presence_wanted(self):
        """What Discord should show now (an activity dict) or None."""
        c = self.client
        if c is None or not c.connected or not c.me:
            return None
        drv = self.driver
        info = self._match_info
        if drv is not None and drv.ticket is not None and info is not None:
            key = ("match", info.get("match"))
            slot = info.get("slot") or 0
            fight = info.get("fight")
            fighters = None
            if fight and all(x and x != fighters_random() for x in fight):
                names = [self.table.fighter_name(x) for x in fight]
                fighters = (names[0], names[1]) if slot == 0 else (names[1], names[0])
            st = info.get("set") or {}
            score = None
            if st.get("rated"):
                w = st.get("wins") or [0, 0]
                score = (w[0], w[1]) if slot == 0 else (w[1], w[0])
            spec = dict(kind="match", ranked=info.get("ranked"), fighters=fighters, set_score=score)
        elif c.me.get("status") == "queue":
            mode = self.cfg.get("last_search") or "quick"
            key, spec = ("search", mode), dict(kind="search", mode=mode)
        else:
            key, spec = ("lobby",), dict(kind="lobby")
        if key != self._presence_key:
            self._presence_key, self._presence_t0 = key, time.time()
        cfg = getattr(self, "_presence_cfg", None) or {}
        return discord_rpc.activity_for(start=self._presence_t0, large_image=cfg.get("large_image", ""),
                                        large_text=cfg.get("large_text", "T5DR Online"), **spec)

    def _presence_tick(self):
        """Every poll: start / stop Rich Presence with the setting, hand it what to show now."""
        settings = getattr(self.app, "settings", None) or {}
        try:
            on = bool(settings.get("discord_presence"))
        except AttributeError:
            on = False
        if not on:
            self._presence_noid = False
            if self.presence is not None:
                self._stop_presence()
            return
        if self.presence is None:
            if getattr(self, "_presence_noid", False):
                return                       # (no application id in this copy: Settings says so; looked once)
            self._presence_cfg = discord_rpc.load_config(settings)
            app_id = self._presence_cfg.get("application_id")
            if not app_id:
                self._presence_noid = True
                return
            self.presence = discord_rpc.DiscordPresence(app_id, paths=self.discord_paths, log=_launcher_log).start()
            self._presence_last = None
        want = self._presence_wanted()
        if want != self._presence_last:
            self._presence_last = want
            self.presence.update(want)

    def _stop_presence(self, wait=False):
        p, self.presence = self.presence, None
        self._presence_last = None
        if p is None:
            return
        if wait:
            p.close(1.5)
        else:
            threading.Thread(target=p.close, daemon=True).start()       # (it takes the activity down first)

    # ------------------------------------------------------------------ leaderboard / profile
    def _on_subtab(self):
        try:
            sel = self.nb.select()
            tab = self.nb.index(sel) if sel else None      # 0 lobby, 1 leaderboard, 2 profile
        except tk.TclError:
            return                                         # (the tabs are being destroyed)
        if tab == 1:
            self.load_leaderboard()
        elif tab == 2 and self.client and self.profile_name is None:
            self.show_profile(None)
        elif tab == 3:
            self._fill_friends()

    def load_leaderboard(self):
        if not self.client:
            return

        def done(rows):
            self.tv_board.delete(*self.tv_board.get_children())
            for r in rows:
                self.tv_board.insert("", "end", iid="lb:" + r["name"], values=(
                    r["place"], r["name"] + ("  *" if r.get("online") else ""),
                    r["rank"] + ("?" if r.get("provisional") else ""), r["rating"],
                    _record((r["wins"], r["losses"])), self.table.fighter_name(r["main"]) if r.get("main") else ""),
                    image=self.view.rank_image(r))
        self.call(self.client.leaderboard, 50, then=done)

    def _profile_of_selected(self):
        sel = self.tv_players.selection()
        if sel:
            name = self.tv_players.item(sel[0], "values")[0].replace(self._you_suffix(), "")
            self.show_profile(name)

    @staticmethod
    def _you_suffix():
        return "  (" + t("you") + ")"

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
            self.prof_title.set(t("{name} -- {rank}", name=p["name"], rank=rank_text(p))
                                + ("" if p.get("account") else " (" + t("guest") + ")"))
            rating = t("Rating {rating} +/- {rd}", rating=p["rating"], rd=p["rd"])
            if p.get("provisional"):
                rating += " " + t("(provisional)")
            if p.get("place"):
                rating += ", " + t("#{place} on the leaderboard", place=p["place"])
            lines = [rating]
            rec = p.get("record", [0, 0, 0])
            parts = [t("Record {record}", record=_record(rec, draws=True))]
            if p.get("account"):
                parts.append(t("ranked matches {count}", count=p["ranked_games"]))
            if p.get("peak_rank"):
                parts.append(t("highest rank {rank}", rank=p["peak_rank"]))
            lines.append(", ".join(parts))
            if p.get("chars"):
                lines.append(t("Characters: {list}", list=", ".join(
                    f"{self.table.fighter_name(c['char'])} {c['wins']}/{c['games']}" for c in p["chars"])))
            if p.get("voids_24h"):
                lines.append(t("Matches without result caused in the last 24 h: {count}", count=p["voids_24h"]))
            if p.get("self") and p.get("recovery_codes_left") is not None:
                lines.append(t("Recovery codes left: {count}", count=p["recovery_codes_left"]))
            self.prof_text.set("\n".join(lines))
            self.tv_hist.delete(*self.tv_hist.get_children())
            for h in p.get("history", []):
                when = stamp(h["time"])
                chars = t("{you} vs {opponent}", you=self.table.fighter_name(h["you_char"]),
                          opponent=self.table.fighter_name(h["opp_char"]))
                score = f"{h['score'][0]}-{h['score'][1]}" if h.get("score") else ""
                delta = f"{h['delta']:+.0f}" if h.get("delta") is not None else ("" if h["ranked"] else t("casual"))
                st = _word(RESULT_WORD, h["status"]) + (" (" + _word(REASON_TEXT, h["reason"]) + ")"
                                                        if h.get("reason") else "")
                st += sets.history_text(h.get("set"))         # a game of a ranked set: which one, how the set went
                self.tv_hist.insert("", "end", values=(when, _word(OUTCOME_WORD, h["result"]), h["opponent"], chars,
                                                       score, delta, st),
                                    tags=(h["result"],) if h.get("result") in ("won", "lost") else ())
        self.call(self.client.profile, name, 20, then=done)

    # ------------------------------------------------------------------ server events
    def _opponent_text(self, opp, ranked, rematch=False):
        """'Opponent: Name (rank, rating) -- RANKED -- rematch'."""
        rating = opp["rating"] if not opp["guest"] else t("guest")
        parts = [t("Opponent: {name} ({rank}, {rating})", name=opp["name"], rank=rank_text(opp), rating=rating)]
        if ranked:
            parts.append(t("RANKED"))
        if rematch:
            parts.append(t("rematch"))
        return " -- ".join(parts)

    def on_event(self, ev):
        kind = ev["t"]
        c = self.client
        if kind == "lobby_state":
            self._fill_lists(ev)
            self._show_me()
        elif kind == "chat":
            self.chat_line(f"{ev['from']['name']}: {ev['text']}")
        elif kind == "challenged":
            self.challenge = ev["challenge"]
            self.show_bar(t("{name} ({rank}) challenges you", name=ev["from"]["name"], rank=rank_text(ev["from"])),
                          [(t("Accept"), lambda: self._answer(True), "cross"),
                           (t("Decline"), lambda: self._answer(False), "circle")])
        elif kind == "challenge_update":
            if ev["state"] != "accepted":
                self.status(_word(CHALLENGE_TEXT, ev["state"]) if ev["state"] in CHALLENGE_TEXT
                            else t("Challenge {state}.", state=ev["state"]))
            if ev["challenge"] == self.challenge:
                self.challenge = None
                self.hide_bar()
        elif kind in ("friends", "friend_status"):
            self._fill_friends()
        elif kind == "friend_request":
            self.status(t("{name} wants to be your friend: see the Friends tab.", name=ev.get("name")))
        elif kind == "friend_update":
            if ev.get("state") == "accepted":
                self.status(t("{name} accepted your friend request.", name=ev.get("name")))
            elif ev.get("state") == "declined":
                self.status(t("{name} declined your friend request.", name=ev.get("name")))
        elif kind == "invited":
            self._show_invite(ev)
        elif kind == "invite_update":
            self._invite_ended(ev)
        elif kind == "match_found":
            self.match = ev
            self.invite = None
            self.outgoing_invite = None
            self.hide_bar()
            self.rematch_bar = None
            self.set_bar = None
            self.lag = None
            self.ready_sent = False
            if (ev.get("set") or {}).get("locked"):
                self.set_locked = True
            self.set_var.set(sets.status_text(ev.get("set"), ev.get("slot") or 0))
            if ev.get("blind"):
                # a match from the queue: the ping and the rules now, the name after both accepted
                self.ready_deadline = time.monotonic() + float(ev.get("ready_timeout") or 15)
                self.show_bar(self._ready_text(), [(t("Accept"), lambda: self._ready(True), "cross"),
                                                   (t("Decline"), lambda: self._ready(False), "circle")])
            else:
                text = self._opponent_text(ev["opponent"], ev["ranked"], ev.get("origin") == "rematch")
                if ev["ready_check"]:
                    self.ready_deadline = time.monotonic() + float(ev.get("ready_timeout") or 15)
                    self.show_bar(text, [(t("Accept"), lambda: self._ready(True), "cross"),
                                         (t("Decline"), lambda: self._ready(False), "circle")])
                else:
                    self.show_bar(text + " -- " + t("connecting..."), [])
        elif kind == "match_reveal":
            self.ready_deadline = None
            text = self._opponent_text(ev["opponent"], bool((self.match or {}).get("ranked")))
            self.show_bar(text + " -- " + t("connecting..."), [])
        elif kind == "opponent_ready":
            self.status(t("Your opponent accepted."))
        elif kind == "lag_check":
            self._show_lag(ev)
        elif kind == "set_end":
            self._set_ended(ev)
        elif kind == "server_notice":
            self._show_notice()
        elif kind in ("nat_status", "nat_upgrade"):
            self.status(ev["text"])
        elif kind == "match_cancel":
            self.match = None
            self.ready_deadline = None
            self.hide_bar()
            self.status(_word(CANCEL_TEXT, ev["reason"]) if ev["reason"] in CANCEL_TEXT
                        else t("Match cancelled ({reason}).", reason=ev["reason"]))
        elif kind == "match_start":
            self.hide_bar()
            self.ready_deadline = None
            self.rematch_bar = None
            self.set_bar = None
            self.lag = None
            self.set_var.set(sets.status_text(ev.get("set"), ev.get("slot") or 0))
            f = ev.get("fight") or {}
            delay = ev.get("delay") or 0
            self._match_head = (t("Ranked match vs {name}", name=ev["opponent"]["name"]) if ev.get("ranked")
                                else t("Casual match vs {name}", name=ev["opponent"]["name"]))
            regional = (ev.get("relay") or {}).get("name") if ev.get("path") == "relay" else None
            self._match_tail = t("ping {ms} ms ({how}), input delay {frames} frames ({delay_ms} ms)",
                                 ms=f"{ev.get('rtt_ms', 0):.0f}",
                                 how=(t("via the relay server {name}", name=regional) if regional
                                      else _word(PATH_TEXT, ev.get("path"))),
                                 frames=ev.get("delay"), delay_ms=f"{delay * 16.7:.0f}")
            if f.get("pick"):
                # in-game select: the fighters are picked on the game's own select screen
                fighters_text = t("pick your fighter in the game ({secs} s)", secs=f["pick"])
            else:
                fighters_text = t("{p1} vs {p2}", p1=self.table.fighter_name(f.get("p1")),
                                  p2=self.table.fighter_name(f.get("p2")))
                if (ev.get("set") or {}).get("locked") and (ev.get("set") or {}).get("game", 1) > 1:
                    fighters_text += " " + t("(locked for this ranked set)")
            self.match_var.set(" -- ".join((self._match_head, fighters_text, self._match_tail)))
            self._match_info = {"match": ev.get("match"), "ranked": bool(ev.get("ranked")), "slot": ev.get("slot") or 0,
                                "fight": None if f.get("pick") else (f.get("p1"), f.get("p2")), "set": ev.get("set")}
        elif kind == "match_result":
            self._show_result(ev)
        elif kind == "rematch":
            if ev.get("state") == "declined":
                self.rematch_bar = None
                self.hide_bar()
        elif kind == "notice":
            self.status(translate_message(ev.get("msg", "")))
        elif kind == "reconnecting":
            self.status(t("Lost the lobby connection -- reconnecting (your match goes on)..."))
        elif kind == "reconnected":
            self.status(t("Reconnected to the lobby."))
        elif kind == "disconnected":
            self.status(t("Lost the lobby connection: {reason}", reason=translate_message(ev.get("reason"))))
            self.client = None
            if self.driver is not None:
                self.driver.ticket = None
            self._reset_lobby_view()
            self.me_var.set(t("Not connected."))
            self._set_account_view(False)
        elif kind == "kicked":
            self.status(t("Removed from the lobby: {reason}", reason=translate_message(ev.get("reason"))))
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
        elif k == "game_state":
            # the fight started: show who fights (with the in-game select, what the players picked)
            if n.get("state") == "fight" and n.get("chars") and self._match_info is not None:
                self._match_info["fight"] = tuple(n["chars"])
            if n.get("state") == "fight" and n.get("chars") and getattr(self, "_match_head", None):
                p1, p2 = n["chars"]
                self.match_var.set(" -- ".join((self._match_head, t("{p1} vs {p2}", p1=self.table.fighter_name(p1),
                                                                    p2=self.table.fighter_name(p2)), self._match_tail)))
        elif k == "ask_result":
            self.show_bar(t("The game closed. How did the match against {opponent} end?", opponent=n["opponent"]), [
                (t("I won"), lambda: self._answer_result("won")),
                (t("I lost"), lambda: self._answer_result("lost")),
                (t("Draw"), lambda: self._answer_result("draw")),
                (t("I quit"), lambda: self._answer_result("quit")),
            ])
        elif k == "rematch_offer":
            self.show_bar(t("{opponent} wants a rematch", opponent=n["opponent"]),
                          [(t("Rematch"), lambda: self._rematch(True), "cross"),
                           (t("No thanks"), lambda: self._rematch(False), "circle")])
        self.view.after_driver(n)
        if k == "rematch_offer":
            self._come_forward(("rematch", n.get("match")))     # a decision for the player
        elif k == "ask_result":
            self._come_forward(("ask", n.get("match")))

    def _come_forward(self, key):
        """The match is over and the game waits (pads neutral, at character select) for what comes next:
        show this tab and bring the launcher's window to the front -- once per match end or question
        (`key`). Never while a match is being played, and not while a ranked set's next game starts by
        itself. (Players took the waiting game for a hang: build/e2e, GitHub report on 1.0.0.)"""
        if key == self._fronted or self.set_bar is not None:
            return
        drv = self.driver
        if drv is not None and drv.ticket is not None and drv.game_state not in (None, "over", "neutral"):
            return                                  # a match is on (the fight, its loading): never then
        self._fronted = key
        try:
            nb = self.parent.master
            if isinstance(nb, ttk.Notebook) and nb.select() != str(self.parent):
                nb.select(self.parent)              # the launcher's Online tab, with the result card
        except tk.TclError:
            pass
        try:
            self.bring_forward(self.parent)
        except Exception:                           # noqa: BLE001 -- a window that cannot come forward is no error
            pass

    def _answer_result(self, what):
        self.hide_bar()
        if self.driver:
            self.driver.answer(what)
        self.status(t("Result sent; waiting for your opponent's report..."))

    def _rematch(self, accept):
        self.view.rematch_sent(bool(accept))
        self.hide_bar()
        if self.driver:
            self.driver.rematch(None, accept)
        if accept:
            self.status(t("Rematch offered; waiting for your opponent..."))

    def _fill_lists(self, ev):
        me = self.client.me if self.client else None
        mine = self.client.build.build_id if self.client else None
        my_rtt = (self.client.server_rtt if self.client else None) or 0.0
        keep = self.tv_players.selection()
        self.tv_players.delete(*self.tv_players.get_children())
        rtt_of = {}
        for p in ev.get("players", []):
            status = _word(STATUS_TEXT, p["status"])
            if p["build"] != mine:
                status += " " + t("(other version)")
            ms = None if p["rtt"] is None or (me and p["id"] == me["id"]) else p["rtt"] + my_rtt
            rtt_of[p["id"]] = ms
            ping = "" if ms is None else f"~{ms:.0f} ms"
            rating = "" if p["guest"] else p["rating"]
            rec = p.get("record") or [0, 0, 0]
            name = p["name"] + (self._you_suffix() if me and p["id"] == me["id"] else "")
            main = self.table.fighter_name(p.get("main")) if p.get("main") else ""
            tags = ("me",) if me and p["id"] == me["id"] else ("other",) if p["build"] != mine else ()
            self.tv_players.insert("", "end", iid=p["id"], values=(name, rank_text(p), rating,
                                                                   _record(rec), main, status, ping),
                                   image=self.view.ping_image(ms), tags=tags)
        for iid in keep:
            if self.tv_players.exists(iid):
                self.tv_players.selection_set(iid)
        keep = self.tv_rooms.selection()
        self.tv_rooms.delete(*self.tv_rooms.get_children())
        for r in ev.get("rooms", []):
            state = (_word(ROOM_STATE_TEXT, r["status"]) + (" " + t("(other version)") if r["build"] != mine else "")
                     + (" " + t("ranked") if r["ranked"] else ""))
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
            self.status(t("Searching... ({ranked} in the ranked queue, {quick} quick)", ranked=q.get("ranked", 0),
                          quick=q.get("quick", 0)))

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
            where = t("ping about {ms} ms (through the server; measured directly once you both accept)",
                      ms=f"{ping.get('ms', 0):.0f}")
        else:
            where = t("ping not known yet")
        left = max(0, int((self.ready_deadline or 0) - time.monotonic() + 0.99)) if self.ready_deadline else 0
        parts = [t("Opponent found")] + ([t("RANKED")] if m.get("ranked") else []) + [
            where, t("accept within {seconds} s?", seconds=left)]
        return " -- ".join(parts)

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
        self.show_bar(self.bar_text.get() + (" -- " + t("waiting for the opponent...") if accept else ""), [])
        self.call(self.client.ready, accept, m["match"])

    def _show_lag(self, ev):
        """After a match: ping X should mean Y frames behind, it was Z -- and a way out when it was worse."""
        self.lag = ev
        text = lag.describe_event(ev)
        self.match_var.set(t("Lag check: {text}", text=text))
        self.status(t("Lag check: {text}", text=text))
        if self.rematch_bar is not None:
            self._show_rematch_bar()
        elif self.set_bar is not None:
            self._show_set_bar()

    def _set_ended(self, ev):
        self.set_locked = False
        if ev.get("rated") and ev.get("games"):
            # a ranked set is over: its result and its one rating change, on the last game's result card
            self.set_bar = None
            text = sets.result_text(ev)
            w = ev.get("wins") or [0, 0]
            self.set_var.set(t("Set {mine}-{theirs}", mine=w[0], theirs=w[1]))
            self.status(text + ".")
            if self.last_result is not None:
                res = ev.get("result")
                self.view.result(self.last_result, True if res == "win" else False if res == "loss" else None, text,
                                 set_end=ev)
            if ev.get("reason") == "decided" and self.rematch_bar is not None:
                self.rematch_bar = (text if len(text) < 70 else t("Rematch? (a new set)"), self.rematch_bar[1])
                self._show_rematch_bar()          # a rematch is a new set
            else:
                self.rematch_bar = None
                self.hide_bar()
            if self.client:
                self._show_me()
                self._set_actions()
            # the set is over and the game waits for a choice (once: the last game's result may have done it)
            self._come_forward(("result", (self.last_result or {}).get("match")))
            return
        if self.rematch_bar is not None:
            self.rematch_bar = None
            self.hide_bar()
        reason, by = ev.get("reason"), ev.get("by")
        if reason == "lag":
            self.status(t("You left after the lag check. No penalty, no rating change.") if by == "you" else
                        t("Your opponent left after the lag check. No penalty for anyone."))
        elif by == "opponent":
            self.status(t("Your opponent left. The set is over."))
        if self.client:
            self._set_actions()

    def _show_rematch_bar(self):
        text, opp = self.rematch_bar
        buttons = [(t("Rematch {name}", name=opp), lambda: self._rematch(True), "cross"),
                   (t("Next game"), self._next_game),
                   (t("Leave"), lambda: self._rematch(False), "circle"),
                   (t("Block {name}", name=opp), lambda: self.block_opponent(opp))]
        check = self.lag
        if check and check.get("verdict") == "more_lag" and check.get("can_leave"):
            buttons.insert(3, (t("Leave: too laggy"), self._leave_for_lag))
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
        self.set_bar = None
        self.call(self.client.leave_set, "lag", then=lambda _r: self.status(
            t("You left after the lag check. No penalty, no rating change.")))

    # ------------------------------------------------------------------ ranked sets (best of 3)
    def _show_set_bar(self):
        """Between two games of a ranked set: the countdown to the next game (no vote), and a way out."""
        info, slot, _end = self.set_bar
        buttons = [(t("Leave set (counts as a loss)"), self._leave_set, "circle")]
        check = self.lag
        if check and check.get("verdict") == "more_lag" and check.get("can_leave"):
            buttons.insert(0, (t("Leave: too laggy"), self._leave_for_lag))
        self.show_bar(self._set_bar_text(), buttons)

    def _set_bar_text(self):
        info, slot, end = self.set_bar
        nxt = dict(info.get("next") or {}, **{"in": max(0.0, end - time.monotonic())})
        return sets.status_text(dict(info, next=nxt), slot)

    def _tick_set(self):
        """Keep the countdown in the set bar current."""
        if self.set_bar is not None and self.bar_spec:
            self.bar_text.set(self._set_bar_text())

    def _leave_set(self):
        if not self.ask_yes_no(t("Leave the ranked set"),
                               t("Leave this ranked set?\n\nLeaving a ranked set counts as losing it."),
                               parent=self.parent):
            return
        self.hide_bar()
        self.set_bar = None
        self.call(self.client.leave_set)

    def _show_result(self, ev):
        self.match = None
        self.last_result = ev
        if hasattr(self.app, "report_problem") and not self.report_btn.winfo_ismapped():
            self.report_btn.pack(side="right")
        st = ev["status"]
        text = _word(RESULT_TEXT, st)
        if ev.get("reason") and ev["reason"] in REASON_TEXT:
            text += " (" + _word(REASON_TEXT, ev["reason"]) + ")"
        mine = None
        if ev.get("winner") is not None and self.driver is not None and self.driver.session_ticket is not None:
            mine = ev["winner"] == self.driver.session_ticket.slot
        self.view.result(ev, mine, text)              # the result card: banner, score, rating, rank
        if st in ("confirmed", "onesided", "forfeit", "resolved"):
            text = (t("You won.") + " " if mine else t("You lost.") + " " if mine is False else "") + text
        r = ev.get("rating")
        if r:
            text += "; " + t("rating {rating} ({delta})", rating=f"{r['after']['r']:.0f}", delta=f"{r['delta']:+.0f}")
            after = r.get("rank_after") or {}
            if r.get("event") == "promoted":
                text += " -- " + t("PROMOTED to {rank}!", rank=after.get("rank"))
            elif r.get("event") == "demoted":
                text += " -- " + t("demoted to {rank}", rank=after.get("rank"))
            elif r.get("event") == "placed":
                text += " -- " + t("placed at {rank}", rank=after.get("rank"))
            elif after.get("placement"):
                text += " -- " + t("placement {done}/{total}", done=after["placement"][0], total=after["placement"][1])
        self.status(text + ".")
        self.hide_bar()
        s = ev.get("set") or {}
        slot = self.driver.session_ticket.slot if self.driver and self.driver.session_ticket else 0
        if s.get("rated"):
            self.set_var.set(sets.status_text(dict(s, next=None), slot))     # the cards' gold tag (no countdown)
        if s.get("rated") and s.get("next"):
            # the set goes on by itself: count down to the next game
            self.set_bar = (s, slot, time.monotonic() + float(s["next"].get("in") or 0))
            self._show_set_bar()
        elif ev.get("rematch_window"):
            opp = (self.driver.session_ticket.opponent.get("name") if self.driver and self.driver.session_ticket
                   else t("your opponent"))
            self.rematch_bar = (text if len(text) < 60 else t("Rematch?"), opp)
            self._show_rematch_bar()
        if self.client and self.client.me:
            self._show_me()
        self._come_forward(("result", ev.get("match")))

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
            text = t("Controller off.")
        elif p is None or not p.stats["polls"]:
            text = ""
        elif not p.has_devices():
            text = t("No controller found.")
        else:
            text = t("Controller: {summary}", summary=p.summary)
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
        self._stop_presence(wait=True)
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
            self.status(t("Cannot start the lobby server: {error}", error=e))
            return
        self.b_host.configure(text=t("Stop hosting"))
        self.status(t("Starting a lobby server on this PC and asking the router to forward its ports...")
                    if self.map_var.get() else t("Starting a lobby server on this PC..."))
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
            share = ev.get("internet") or f"{t('<your public IP>')}:{ev['port']}" + (
                f"#{ev['fingerprint']}" if ev.get("fingerprint") else "")
            try:
                self.parent.clipboard_clear()
                self.parent.clipboard_append(share)
            except tk.TclError:
                pass
            self.chat_line(t("Hosting. Friends paste this as their Server (copied to the clipboard):\n  {share}",
                             share=share)
                           + (t("\n  same network: {lan}", lan=ev["lan"]) if ev.get("lan") else "")
                           + ("" if ev.get("mapped") else t("\n  Forward TCP+UDP 7781 and UDP 7782 on your router "
                                                            "(or tick 'Open router ports').")))
            self.status(t("Hosting a lobby on this PC. Log in to join it yourself."))
            self.view.hosting(ev)
        elif kind == "error":
            self.status(t("Hosting failed: {message}", message=translate_message(ev.get("message"))), error=True)
        elif kind in ("stopped", "exited"):
            self.host_proc = None
            self.host_info = None
            self.view.hosting(None)
            self.b_host.configure(text=t("Host for friends"))
            if kind == "exited" and proc.poll() not in (0, None):
                self.status(t("The lobby server stopped (exit code {code}); see its log in {folder}.",
                              code=proc.returncode, folder="%LOCALAPPDATA%\\T5DR Online\\lobby-host\\logs"))
            else:
                self.status(t("Stopped hosting."))

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


def fighters_random():
    return fighters.RANDOM


def _launcher_log(text):
    """A line in launcher.log when the launcher runs this tab (Rich Presence notes); nothing otherwise."""
    core = sys.modules.get("core")              # (the launcher's module, imported by the launcher itself)
    if core is not None and hasattr(core, "log"):
        try:
            core.log(text)
        except Exception:       # noqa: BLE001 -- the log is best effort
            pass


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
