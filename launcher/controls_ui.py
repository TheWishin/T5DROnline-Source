"""The launcher's Controls screen: Settings -> "Set up controllers...".

Players with pads, arcade sticks and hitboxes set their buttons here instead of editing controls.ini:

* every controller the game would see, on the player port it would get, with a live "press a button" test;
* the Tekken buttons (1 2 3 4, 1+2, 3+4, 1+2+3+4 and the other macros, Start, Select, the directions): "Press
  the button for 1 (Left Punch)..." one at a time, with Skip and Clear, or one button on its own;
* layout presets (Xbox, PlayStation, Switch, Vewlix 8 buttons, Noir / Sega Astro 6 buttons, hitbox), the stick
  mode and the SOCD mode of the player's port, which player a controller is, and Reset to defaults;
* Save writes the controls.ini the game reads (launcher/controls_edit.py keeps its comments and other keys).

It works with the controller itself: once a controller has been touched (or chosen), Up / Down move through
the buttons, Cross sets one, Triangle clears it, Start saves and Circle closes -- by the controller's own
buttons as controls.ini defines them (lobby/t5lobby/padnav.py rules: only while this window is in front).

Reading the devices is DevicePoller: the same XInput / WinMM sources as the Online tab's PadNav, on its own
thread. Nothing here touches Tk from that thread. Tests give it fake sources and a fake clock.
"""
import os
import queue
import re
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import namedtuple
from tkinter import ttk

import controls_edit as ce
from controls_edit import N_, t  # noqa: F401  (N_ marks texts for translation)
from controls_edit import DeviceRef
from t5lobby import dialogs, padmap, padnav, theme
from t5lobby.i18n import ui_family
from t5lobby.padmap import DINPUT, XINPUT

POLL_HZ = 60
SCAN_S = 1.0
IDLE_S = 0.05
SETTLE_S = 0.08            # presses this close together are one press of several buttons
PAD_TIMEOUT_S = 8.0        # a capture started with the controller gives up (skips) after this
REPEAT_DELAY_S, REPEAT_S = 0.45, 0.12
COLORS = {"ok": "#1a7f37", "muted": "#57606a", "live": "#dafbe1", "warn": "#9a6700", "error": "#cf222e"}

Edge = namedtuple("Edge", "t key source")
OK, WARN, ERROR, MUTED = "ok", "warn", "error", "muted"      # the colour of a status line


# ---------------------------------------------------------------------- reading the controllers

def is_axis_source(src):
    """DirectInput axis directions (X+ RZ-): a trigger or stick can rest at one end of its range."""
    return re.fullmatch(r"[A-Z0-9]+[+-]", src) is not None


class DevicePoller:
    """Reads every controller about 60 times a second while `foreground()` says this window is in front (and
    nothing at all otherwise: no device is touched while the game or another program has the focus).

    After a poll: `devices` (every controller found, as padnav.Device), `held[key]` (the sources held now), and
    `edges` -- one Edge for every source that went down since the previous poll, in order. Sources that are
    held when the window comes forward do not make an edge. An axis that rests at one end (a trigger at -32768)
    is not a press until it has been seen let go."""

    def __init__(self, sources, foreground=None, clock=time.monotonic, hz=POLL_HZ, scan_s=SCAN_S):
        self.sources = list(sources)
        self.foreground = foreground or (lambda: True)
        self.clock = clock
        self.hz = hz
        self.scan_s = scan_s
        self.enabled = True
        self.devices = ()
        self.held = {}
        self.edges = queue.SimpleQueue()
        self.error = ""
        self.polls = 0
        self._active = False
        self._next_scan = 0.0
        self._prev = {}              # key -> frozenset held at the previous poll (rest axes left out)
        self._rest = {}              # key -> axis sources that rest held
        self._thread = None
        self._stop = threading.Event()

    # ---------------------------------------------------------------- one poll
    def step(self, now):
        """One cycle. Returns None to be called again at the poll rate, or the seconds to wait."""
        try:
            front = bool(self.foreground())
        except Exception:               # noqa: BLE001 -- a window that is gone is not in front
            front = False
        if not (self.enabled and front):
            if self._active:
                self._forget()
            return IDLE_S
        if not self._active:
            self._active = True
            self._next_scan = 0.0
        if now >= self._next_scan:
            self._next_scan = now + self.scan_s
            for s in self.sources:
                try:
                    s.scan()
                except Exception as e:      # noqa: BLE001
                    self.error = f"{type(s).__name__}.scan: {e}"
        found = []
        for s in self.sources:
            try:
                found += s.read()
            except Exception as e:          # noqa: BLE001
                self.error = f"{type(s).__name__}.read: {e}"
        held = {}
        keys = set()
        for d in found:
            keys.add(d.key)
            cur = frozenset(d.pressed)
            first = d.key not in self._prev
            if first:
                self._rest[d.key] = {x for x in cur if is_axis_source(x)}
            else:
                self._rest[d.key] &= cur
            eff = cur - self._rest[d.key]
            if not first:
                for src in sorted(eff - self._prev[d.key]):
                    self.edges.put(Edge(now, d.key, src))
            self._prev[d.key] = eff
            held[d.key] = eff
        for k in list(self._prev):
            if k not in keys:
                del self._prev[k]
                self._rest.pop(k, None)
        self.devices = tuple(found)
        self.held = held
        self.polls += 1
        return None

    def _forget(self):
        """The window left the front: no button is known to be up any more."""
        self._active = False
        self._prev.clear()
        self._rest.clear()
        self.held = {}

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.edges.get_nowait())
            except queue.Empty:
                return out

    # ---------------------------------------------------------------- the thread
    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="controls-poll", daemon=True)
        self._thread.start()

    def stop(self, wait=1.0):
        th, self._thread = self._thread, None
        self._stop.set()
        if th is not None and th is not threading.current_thread():
            th.join(wait)

    def _run(self):
        period = 1.0 / self.hz
        due = self.clock()
        while not self._stop.is_set():
            try:
                wait = self.step(self.clock())
            except Exception as e:           # noqa: BLE001 -- the thread must outlive a bad device
                self.error = f"step: {e}"
                wait = 0.5
            if wait is None:
                due += period
                now = self.clock()
                if due < now:
                    due = now + period
                wait = due - now
            else:
                due = self.clock() + wait
            time.sleep(max(wait, 0.0))


# ---------------------------------------------------------------------- capture and navigation

class Capture:
    """Waits for one press on one controller. `update(now, edges)` -> None (keep waiting), ("ok", source),
    ("multi", [sources]) when several went down together, or ("timeout", None)."""

    def __init__(self, started, settle_s=SETTLE_S, timeout_s=None):
        self.started = started
        self.settle_s = settle_s
        self.timeout_s = timeout_s
        self.first = None
        self.found = []

    def update(self, now, edges):
        for e in edges:
            if self.first is None:
                self.first = e.t
            if e.t - self.first <= self.settle_s and e.source not in self.found:
                self.found.append(e.source)
        if self.first is not None:
            if now - self.first < self.settle_s:
                return None
            return ("ok", self.found[0]) if len(self.found) == 1 else ("multi", list(self.found))
        if self.timeout_s is not None and now - self.started >= self.timeout_s:
            return ("timeout", None)
        return None


def nav_map(editor, dev):
    """{source: action} for moving through the screen with this controller: the sources that are 3 (Cross)
    accept, 4 (Circle) go back, 2 (Triangle) clear, Start saves, the d-pad / hat and the left stick go up
    and down. A button the person has cleared falls back to the default layout's."""
    cur = editor.table(dev)
    dflt = padmap.Controls("").table(dev.kind, -1, dev.vid, dev.pid)
    bit = padmap.PS3_BIT
    out = {}
    for action, mask in (("accept", bit["CROSS"]), ("back", bit["CIRCLE"]), ("clear", bit["TRIANGLE"]),
                         ("save", bit["START"]), ("up", bit["UP"]), ("down", bit["DOWN"])):
        for s in cur.sources_exactly(mask) or dflt.sources_exactly(mask):
            out.setdefault(s, action)
    for s, a in ((("LUP", "up"), ("LDOWN", "down")) if dev.kind == XINPUT else (("Y-", "up"), ("Y+", "down"))):
        out.setdefault(s, a)
    return out


class PadNavigator:
    """Turns presses of the chosen controller into 'up' 'down' 'accept' 'back' 'clear' 'save'. Up and down
    repeat while held."""

    def __init__(self, delay=REPEAT_DELAY_S, repeat=REPEAT_S):
        self.delay, self.repeat = delay, repeat
        self._rep = {}

    def feed(self, now, edges, held, nav):
        out = []
        for e in edges:
            a = nav.get(e.source)
            if a:
                out.append(a)
                if a in ("up", "down"):
                    self._rep[e.source] = now + self.delay
        for src in list(self._rep):
            if src not in held or nav.get(src) not in ("up", "down"):
                del self._rep[src]
            elif now >= self._rep[src]:
                out.append(nav[src])
                self._rep[src] = now + self.repeat
        return out

    def reset(self):
        self._rep.clear()


# ---------------------------------------------------------------------- the screen

def _ask(kind, title, text, parent):
    if kind == "yesnocancel":
        return dialogs.ask_yes_no_cancel(title, text, parent=parent)      # (buttons in the launcher's language)
    return dialogs.ask_yes_no(title, text, parent=parent)


def _kind_name(kind):
    return t("Xbox pad (XInput)") if kind == XINPUT else t("DirectInput controller")


def game_button_name(slot):
    """A game button's name in the player's language; L1, R2, 1+2 ... are the same in every language (not texts)."""
    return slot.label if slot.label == slot.key else t(slot.label)


class ControlsDialog:
    """The Controls window. `sources` / `foreground` / `clock` / `thread=False` / `ask` / `path` let a test run it
    with fake controllers and no real devices."""

    def __init__(self, app, settings, sources=None, foreground=None, clock=None, thread=True, path=None,
                 game_running=None, ask=None):
        self.app = app
        self.settings = settings
        self.game_running = game_running or (lambda: False)
        self.top = tk.Toplevel(app)
        try:
            self.top.transient(app)         # stays above the launcher; a hidden launcher hides it too
        except tk.TclError:
            pass
        self._ask = ask or (lambda kind, title, text: _ask(kind, title, text, self.top))
        try:
            env = settings.env_overrides()
        except Exception:               # noqa: BLE001 -- a settings object without it: the process environment only
            env = {}
        self.path = path or ce.controls_path(getattr(settings, "out_dir", os.getcwd()), env)
        self.editor = ce.ControlsEditor.load(self.path)
        if sources is None:
            sources = padnav.default_sources()
        self.no_pads = not sources
        if foreground is None:
            foreground = padnav.window_foreground_check(padnav.toplevel_hwnd(self.top))
        self.poller = DevicePoller(sources, foreground=foreground, **({"clock": clock} if clock else {}))
        self.portmap = padmap.PortMap(self.editor.controls())
        self.nav = PadNavigator()
        self.chosen = None              # key of the controller being set up
        self.scope_of = {}              # device key -> scope
        self._sig = None
        self._rows = {}                 # player-list iid -> device key or None
        self.capture = None
        self.queue = []                 # slot keys still to ask for
        self.cap_key = None
        self.cap_total = 0
        self.pad_started = False
        self._live_sig = None
        self._closed = False
        self._after = None
        self._build()
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.pump()
        if thread:
            self.poller.start()
            self._after = self.top.after(33, self._tick)

    # ---------------------------------------------------------------- layout
    def px(self, v):
        """Pixels at this DPI: the window, its columns and wrap lengths grow with Windows' display scaling."""
        return int(round(v * theme.scale_of(self.top)))

    def chars(self, texts):
        """A Combobox width (in average characters) that shows the longest of `texts` in any language (a Korean or
        Japanese character is about two average ones wide)."""
        try:
            f = tkfont.nametofont("TkTextFont", root=self.top)
            return int(max(f.measure(x) for x in texts) / max(1, f.measure("0"))) + 3
        except (tk.TclError, ValueError):
            return max(len(x) for x in texts) + 2

    def _build(self):
        top, px = self.top, self.px
        top.title(t("Controls - T5DR Online"))
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        w, h = min(px(1040), sw - 40), min(px(880), sh - 80)      # (room for the longer languages)
        top.minsize(min(px(880), w), min(px(640), h))
        try:                                # over the launcher's window, not at the corner of the screen
            top.geometry("%dx%d+%d+%d" % (w, h, max(self.app.winfo_rootx() + 30, 0),
                                          max(self.app.winfo_rooty() + 30, 0)))
        except tk.TclError:
            top.geometry("%dx%d" % (w, h))
        top.columnconfigure(0, weight=1)
        top.rowconfigure(2, weight=1)
        ttk.Label(top, text=t("Controls"), style="H1.TLabel").grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))
        self.intro_var = tk.StringVar(value=t(
            "Press a button on a controller to pick it, then set its buttons. The game reads the file when it starts."))
        ttk.Label(top, textvariable=self.intro_var, style="Muted.TLabel", wraplength=px(900), justify="left").grid(
            row=1, column=0, sticky="we", padx=16, pady=(0, 6))

        body = ttk.Frame(top)
        body.grid(row=2, column=0, sticky="nsew", padx=12)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2, minsize=px(380))
        body.rowconfigure(1, weight=1)

        # --- players
        pl = ttk.LabelFrame(body, text="  " + t("Controllers") + "  ", padding=(8, 4))
        pl.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, 6))
        pl.columnconfigure(0, weight=1)
        self.tv_players = ttk.Treeview(pl, columns=("lamp", "player", "device", "state"), show="headings", height=3,
                                       selectmode="browse")
        for col, head, w, stretch in (("lamp", "", 28, False), ("player", t("Player"), 80, False),
                                      ("device", t("Controller"), 380, True), ("state", t("Pressed now"), 320, True)):
            self.tv_players.heading(col, text=head)
            self.tv_players.column(col, width=px(w), stretch=stretch, anchor="center" if col == "lamp" else "w")
        self.tv_players.tag_configure("lit", foreground=COLORS["ok"])
        self.tv_players.tag_configure("none", foreground=COLORS["muted"])
        self.tv_players.grid(row=0, column=0, sticky="we")
        self.tv_players.bind("<<TreeviewSelect>>", self._on_player_select)
        self.pad_note = ttk.Label(pl, style="Muted.TLabel", wraplength=px(900), justify="left")
        self.pad_note.grid(row=1, column=0, sticky="w", pady=(4, 0))
        # the controller moves through this window (Up / Down, Cross, ...); off: it only lights the lamps
        self.pad_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(pl, text=t("Move through this window with the controller"), variable=self.pad_var,
                        command=lambda: self.pad_hint(self.dev())).grid(row=2, column=0, sticky="w")

        # --- the buttons
        bt = ttk.LabelFrame(body, text="  " + t("Buttons") + "  ", padding=(8, 4))
        bt.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        bt.columnconfigure(0, weight=1)
        bt.rowconfigure(1, weight=1)
        self.head_var = tk.StringVar()
        ttk.Label(bt, textvariable=self.head_var, style="H2.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.tv = ttk.Treeview(bt, columns=("buttons", "note"), show="tree headings", selectmode="browse", height=14)
        self.tv.heading("#0", text=t("Game button"))
        self.tv.heading("buttons", text=t("Controller button"))
        self.tv.heading("note", text="")
        self.tv.column("#0", width=px(280), stretch=False)        # (wide enough for every language)
        self.tv.column("buttons", width=px(160))
        self.tv.column("note", width=px(80), stretch=False)
        self.tv.tag_configure("live", background=COLORS["live"])
        self.tv.tag_configure("own", foreground=COLORS["warn"])
        for gid, glabel in ce.SLOT_GROUPS:
            self.tv.insert("", "end", iid="g:" + gid, text=t(glabel), open=True)
        for s in ce.SLOTS:
            self.tv.insert("g:" + s.group, "end", iid=s.key, text=game_button_name(s), values=("-", ""))
        sb = ttk.Scrollbar(bt, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        sb.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        self.tv.bind("<Double-1>", lambda _e: self.set_selected())
        self.tv.bind("<Return>", lambda _e: self.set_selected())
        self.tv.bind("<Delete>", lambda _e: self.clear_selected())
        row = ttk.Frame(bt)                 # two rows of two: narrow enough in every language
        row.grid(row=2, column=0, columnspan=2, sticky="we", pady=(6, 0))
        self.btn_all = ttk.Button(row, text=t("Set up all buttons"), command=self.start_all)
        self.btn_all.grid(row=0, column=0, sticky="we")
        self.btn_dirs = ttk.Button(row, text=t("Set up directions"), command=self.start_directions)
        self.btn_dirs.grid(row=0, column=1, sticky="we", padx=(6, 0))
        self.btn_one = ttk.Button(row, text=t("Set selected"), command=self.set_selected)
        self.btn_one.grid(row=1, column=0, sticky="we", pady=(4, 0))
        self.btn_clear = ttk.Button(row, text=t("Clear"), command=self.clear_selected)
        self.btn_clear.grid(row=1, column=1, sticky="we", padx=(6, 0), pady=(4, 0))

        # --- options
        op = ttk.Frame(body)
        op.grid(row=1, column=1, sticky="nsew")
        op.columnconfigure(0, weight=1)
        lay = ttk.LabelFrame(op, text="  " + t("Layout") + "  ", padding=(8, 4))
        lay.grid(row=0, column=0, sticky="we")
        lay.columnconfigure(0, weight=1)
        self.preset_var = tk.StringVar()
        self.preset_box = ttk.Combobox(lay, textvariable=self.preset_var, state="readonly",
                                       width=self.chars([t(ce.recipe_title(r, k)) for r in ce.RECIPES
                                                         for k in r.specs]))
        self.preset_box.grid(row=0, column=0, sticky="we")
        self.preset_box.bind("<<ComboboxSelected>>", lambda _e: self._show_preset_text())
        self.preset_text = tk.StringVar()
        ttk.Label(lay, textvariable=self.preset_text, style="Muted.TLabel", wraplength=px(330),
                  justify="left").grid(
            row=1, column=0, sticky="w", pady=(4, 4))
        r2 = ttk.Frame(lay)
        r2.grid(row=2, column=0, sticky="we")
        self.btn_apply = ttk.Button(r2, text=t("Use this layout"), command=self.apply_preset)
        self.btn_apply.pack(side="left")
        self.btn_reset = ttk.Button(r2, text=t("Reset to defaults"), command=self.reset_defaults)
        self.btn_reset.pack(side="left", padx=6)

        sc = ttk.LabelFrame(op, text="  " + t("Your changes apply to") + "  ", padding=(8, 4))
        sc.grid(row=1, column=0, sticky="we", pady=(6, 0))
        self.scope_var = tk.StringVar(value=ce.SCOPE_MODEL)
        self.scope_btns = {}
        ttk.Style(top).configure("W360.TRadiobutton", wraplength=px(360))     # (long in some languages)
        for scope in (ce.SCOPE_MODEL, ce.SCOPE_KIND, ce.SCOPE_PORT):
            b = ttk.Radiobutton(sc, text="", value=scope, variable=self.scope_var, command=self._on_scope,
                                style="W360.TRadiobutton")
            b.pack(anchor="w")
            self.scope_btns[scope] = b

        pt = ttk.LabelFrame(op, text="  " + t("Player and directions") + "  ", padding=(8, 4))
        pt.grid(row=2, column=0, sticky="we", pady=(6, 0))
        pt.columnconfigure(1, weight=1)
        self.player_var = tk.StringVar()
        self.stick_var = tk.StringVar()
        self.socd_var = tk.StringVar()
        self.player_opts = (("auto", t("Automatic")), ("0", t("Player 1")), ("1", t("Player 2")))
        self.stick_opts = (("analog", t("Analog stick")), ("dpad", t("8-way d-pad")))
        self.socd_opts = (("neutral", t("Both cancel (neutral)")), ("up", t("Up wins (Up+Down is Up)")),
                          ("last", t("Last direction wins")), ("off", t("Pass both through")))
        for r, (label, var, opts, cmd) in enumerate((
                (t("This controller is"), self.player_var, self.player_opts, self._on_player_opt),
                (t("Left stick"), self.stick_var, self.stick_opts, self._on_stick),
                (t("Opposite directions"), self.socd_var, self.socd_opts, self._on_socd))):
            ttk.Label(pt, text=label).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
            box = ttk.Combobox(pt, textvariable=var, values=[o[1] for o in opts], state="readonly",
                               width=self.chars([o[1] for o in opts]))
            box.grid(row=r, column=1, sticky="we", pady=2)
            box.bind("<<ComboboxSelected>>", lambda _e, c=cmd: c())
            setattr(self, ("player", "stick", "socd")[r] + "_box", box)
        ttk.Label(pt, style="Muted.TLabel", wraplength=px(340), justify="left", text=t(
            "Left stick, 8-way d-pad: a hitbox or stick in left-stick mode sends the direction as a stick; the "
            "game then reads it as d-pad presses. Left+Right (or Up+Down) at once happens on keyboards and "
            "hitboxes; the game cannot take both. Stick and opposite directions belong to the player's port.")).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # --- prompt (only while a button is being asked for)
        self.prompt = ttk.Frame(top, padding=(16, 6))
        self.prompt.columnconfigure(0, weight=1)
        self.prompt_var = tk.StringVar()
        self.prompt_hint = tk.StringVar()
        tk.Label(self.prompt, textvariable=self.prompt_var, font=(ui_family(), 13, "bold"), fg=COLORS["ok"],
                 anchor="w").grid(row=0, column=0, sticky="we")
        ttk.Label(self.prompt, textvariable=self.prompt_hint, style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        pb = ttk.Frame(self.prompt)
        pb.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(pb, text=t("Skip"), command=self.cap_skip).pack(side="left")
        ttk.Button(pb, text=t("Clear"), command=self.cap_clear).pack(side="left", padx=6)
        ttk.Button(pb, text=t("Stop"), command=self.cap_stop).pack(side="left")
        self.prompt.grid(row=3, column=0, sticky="we")
        self.prompt.grid_remove()

        # --- bottom
        bar = ttk.Frame(top, padding=(16, 6))
        bar.grid(row=4, column=0, sticky="we")
        bar.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="")
        self.status_lbl = ttk.Label(bar, textvariable=self.status_var, style="Muted.TLabel", wraplength=px(640),
                                    justify="left")
        self.status_lbl.grid(row=0, column=0, sticky="w")
        self.btn_save = ttk.Button(bar, text=t("Save"), command=self.do_save)
        self.btn_save.grid(row=0, column=1, padx=4)
        self.btn_revert = ttk.Button(bar, text=t("Revert"), command=self.do_revert)
        self.btn_revert.grid(row=0, column=2, padx=4)
        ttk.Button(bar, text=t("Close"), command=self.close).grid(row=0, column=3, padx=(4, 0))
        top.bind("<Escape>", lambda _e: self._escape())

    # ---------------------------------------------------------------- helpers
    def alive(self):
        if self._closed:
            return False
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    def status(self, text, level="muted"):
        self.status_var.set(text)
        self.status_lbl.configure(foreground=COLORS.get(level, COLORS["muted"]))

    def device(self, key=None):
        key = self.chosen if key is None else key
        for d in self.poller.devices:
            if d.key == key:
                return d
        return None

    def dev(self):
        """The chosen controller as the editor sees it (kind, player port, USB ids), or None."""
        d = self.device()
        if d is None:
            return None
        return DeviceRef(d.kind, self.portmap.port.get(d.key, -1), d.vid, d.pid)

    def scope(self):
        d, dev = self.device(), self.dev()
        if dev is None:
            return ce.SCOPE_KIND
        sc = self.scope_of.get(d.key)
        if sc not in self.editor.scopes(dev):
            sc = self.editor.default_scope(dev)
            self.scope_of[d.key] = sc
        return sc

    def selected_key(self):
        sel = self.tv.selection()
        return sel[0] if sel and sel[0] in ce.SLOT_BY_KEY else None

    def slot_label(self, key):
        return game_button_name(ce.SLOT_BY_KEY[key])

    # ---------------------------------------------------------------- the loop
    def _tick(self):
        if not self.alive():
            return
        try:
            self.pump()
        except Exception as e:                  # noqa: BLE001 -- a bad frame must not end the screen
            self.status(f"{type(e).__name__}: {e}", ERROR)
        self._after = self.top.after(33, self._tick)

    def pump(self):
        """Take what the poller saw: edges, devices. Runs on the Tk thread (tests call it by hand)."""
        if self._closed:
            return
        now = self.poller.clock()
        edges = self.poller.drain()
        devices = self.poller.devices
        self._sync_devices(devices)
        known = {d.key for d in devices}
        if self.capture is None:
            for e in edges:
                if e.key in known and e.key != self.chosen and self.portmap.reads(e.key):
                    self._choose(e.key)
                    edges = [x for x in edges if x.key == self.chosen and x.t > e.t]
                    break
        mine = [e for e in edges if e.key == self.chosen]
        held = self.poller.held
        if self.capture is not None:
            res = self.capture.update(now, mine)
            if res:
                self._capture_result(res)
        else:
            dev = self.dev()
            if dev is not None and self.pad_var.get() and (mine or self.nav._rep):
                for action in self.nav.feed(now, mine, held.get(self.chosen, frozenset()), nav_map(self.editor, dev)):
                    self._do_action(action)
        if not self._closed:
            self._live(held)

    # ---------------------------------------------------------------- devices
    def _sync_devices(self, devices):
        controls = self.editor.controls()
        sig = (tuple((d.key, d.name, d.kind, d.vid, d.pid) for d in devices), id(controls), self.no_pads)
        if sig == self._sig:
            return
        self._sig = sig
        self.portmap.update(list(devices), controls)
        if self.chosen not in {d.key for d in devices}:
            self.chosen = None
        if self.chosen is None:
            self.chosen = self._default_choice(devices)
        self._fill_players(devices)
        self._refresh_all()

    def _default_choice(self, devices):
        by_port = sorted((p, k) for k, p in self.portmap.port.items() if p >= 0 and any(d.key == k for d in devices))
        return by_port[0][1] if by_port else None

    def _fill_players(self, devices):
        tv = self.tv_players
        tv.delete(*tv.get_children())
        self._rows = {}
        by_port = {}
        for d in devices:
            p = self.portmap.port.get(d.key, -1)
            if p >= 0:
                by_port.setdefault(p, d)
        nports = max(2, (max(by_port) + 1) if by_port else 0)
        for p in range(nports):
            d = by_port.get(p)
            iid = f"p{p}"
            self._rows[iid] = d.key if d else None
            tv.insert("", "end", iid=iid, values=("", t("Player {n}", n=p + 1), self._device_text(d) if d else
                                                  t("no controller"), ""), tags=() if d else ("none",))
        for d in devices:
            if self.portmap.port.get(d.key, -1) < 0:
                iid = "u:" + d.key
                self._rows[iid] = d.key
                tv.insert("", "end", iid=iid, values=("", "-", self._device_text(d) + "  (" + self._why_unused(d) + ")",
                                                      ""), tags=("none",))
        tv.configure(height=min(max(len(self._rows), 3), 5))
        self._select_row()
        self._live_sig = None
        if self.no_pads:
            self.pad_note.configure(text=t("Controllers cannot be read on this PC."))
        elif not devices:
            self.pad_note.configure(text=t("No controller found. Plug one in; it shows up here by itself."))
        else:
            self.pad_note.configure(text="")

    def _device_text(self, d):
        ids = f", {d.vid:04X}:{d.pid:04X}" if d.vid else ""
        return f"{d.name}  ({_kind_name(d.kind)}{ids})"

    def _why_unused(self, d):
        c = self.editor.controls()
        if (d.kind == XINPUT and not c.use_xinput) or (d.kind == DINPUT and not c.use_dinput):
            return t("switched off in [general]")
        return t("no free player port")

    def _select_row(self):
        for iid, key in self._rows.items():
            if key is not None and key == self.chosen:
                self._selecting = True
                try:
                    self.tv_players.selection_set(iid)
                finally:
                    self._selecting = False
                return

    _selecting = False

    def _on_player_select(self, _e=None):
        if self._selecting:
            return
        sel = self.tv_players.selection()
        if not sel:
            return
        key = self._rows.get(sel[0])
        if key is not None and key != self.chosen and self.capture is None:
            self._choose(key)
        else:
            self._select_row()                  # an empty row or a capture in progress: the selection stays put

    def _choose(self, key):
        self.chosen = key
        self.nav.reset()
        self._select_row()
        self._refresh_all()

    # ---------------------------------------------------------------- showing the chosen controller
    def _refresh_all(self):
        dev, d = self.dev(), self.device()
        on = dev is not None
        for b in (self.btn_all, self.btn_dirs, self.btn_one, self.btn_clear, self.btn_apply, self.btn_reset):
            b.configure(state="normal" if on else "disabled")
        for b in (self.preset_box, self.player_box, self.stick_box, self.socd_box):
            b.configure(state="readonly" if on else "disabled")
        self._live_sig = None
        if not on:
            self.head_var.set(t("No controller chosen"))
            for s in ce.SLOTS:
                self.tv.item(s.key, values=("-", ""), tags=())
            for b in self.scope_btns.values():
                b.configure(text="", state="disabled")
            self.preset_box.configure(values=[])
            self.preset_var.set("")
            self.preset_text.set("")
            self.player_var.set("")
            self.stick_var.set("")
            self.socd_var.set("")
            self.pad_hint(None)
            self._update_buttons()
            return
        scope = self.scope()
        self.scope_var.set(scope)
        avail = self.editor.scopes(dev)
        names = {ce.SCOPE_MODEL: t("This controller model ({vid}:{pid})", vid=f"{dev.vid:04X}", pid=f"{dev.pid:04X}")
                 if dev.vid else t("This controller model (no USB ID)"),
                 ce.SCOPE_KIND: t("All Xbox pads (XInput)") if dev.kind == XINPUT else t("All DirectInput controllers"),
                 ce.SCOPE_PORT: t("Only the controller on player {n}'s port", n=dev.port + 1)}
        for sc, b in self.scope_btns.items():
            b.configure(text=names[sc], state="normal" if sc in avail else "disabled")
        port_txt = t("player {n}", n=dev.port + 1) if dev.port >= 0 else t("no player")
        self.head_var.set(f"{d.name}  -  {port_txt}")
        own = self.editor.own_masks(dev, scope)
        for s in ce.SLOTS:
            srcs = self.editor.sources(dev, s.key)
            self.tv.item(s.key, values=(" / ".join(srcs) if srcs else "-", t("yours") if s.mask in own else ""),
                         tags=("own",) if s.mask in own else ())
        if self.selected_key() is None:
            self.tv.selection_set(ce.SLOTS[0].key)
        recs = ce.recipes_for(dev.kind)
        self.preset_box.configure(values=[t(ce.recipe_title(r, dev.kind)) for r in recs])
        cur = self.editor.detect_recipe(dev)
        self.preset_var.set(t(ce.recipe_title(ce.RECIPE_BY_ID[cur], dev.kind)) if cur else t("Your own layout"))
        self._show_preset_text(cur)
        if dev.port >= 0:
            self.stick_var.set(self._opt_text(self.stick_opts, self.editor.stick_of(dev.port)))
            self.socd_var.set(self._opt_text(self.socd_opts, self.editor.socd_of(dev.port)))
        else:
            for b in (self.stick_box, self.socd_box):
                b.configure(state="disabled")
        pinned = self._pinned_port(d)
        self.player_var.set(self.player_opts[0][1] if pinned is None else
                            (self.player_opts[pinned + 1][1] if pinned < 2 else t("Player {n}", n=pinned + 1)))
        self.pad_hint(dev)
        self._update_buttons()

    @staticmethod
    def _device_spec(d):
        """How controls.ini names this controller in `[portN] device = ...`."""
        if d.kind == XINPUT:
            return f"xinput:{d.slot}"
        return f"dinput:{d.vid:04X}:{d.pid:04X}" if d.vid else "dinput:" + re.sub(r"[\s;#]+", " ", d.name).strip()

    def _pinned_port(self, d):
        spec = self._device_spec(d).lower()
        for p in range(padmap.MAX_PORTS):
            if self.editor.pinned(p).lower() == spec:
                return p
        return None

    @staticmethod
    def _opt_text(opts, value):
        for k, label in opts:
            if k == value:
                return label
        return opts[0][1]

    def _opt_key(self, opts, text):
        for k, label in opts:
            if label == text:
                return k
        return None

    def _show_preset_text(self, cur=None):
        dev = self.dev()
        if dev is None:
            return
        title = self.preset_var.get()
        for r in ce.recipes_for(dev.kind):
            if t(ce.recipe_title(r, dev.kind)) == title:
                self.preset_text.set(t(r.summary[dev.kind]))
                return
        self.preset_text.set(t("Buttons you set yourself, or a mix. Pick a layout to start from it."))

    def pad_hint(self, dev):
        if dev is None or not self.pad_var.get():
            self.intro_var.set(t("Press a button on a controller to pick it, then set its buttons. "
                                 "The game reads the file when it starts."))
            return
        nav = nav_map(self.editor, dev)
        names = {}
        for src, act in nav.items():
            names.setdefault(act, src)
        if {"up", "down", "accept"} <= set(names):
            nice = {a: ce.describe_source(dev.kind, src) for a, src in names.items()}
            self.intro_var.set(t(
                "On the controller: {up} / {down} choose a button, {accept} sets it, {clear} clears it, {save} saves, "
                "{back} closes. The game reads the file when it starts.", up=nice["up"], down=nice["down"],
                accept=nice["accept"], clear=nice.get("clear", "-"), save=nice.get("save", "-"),
                back=nice.get("back", "-")))

    def _update_buttons(self):
        self.btn_save.configure(state="normal" if self.editor.dirty else "disabled")
        self.btn_revert.configure(state="normal" if self.editor.dirty else "disabled")

    def _live(self, held):
        """The test lamps: which controllers have something pressed, and which game button that is."""
        dev = self.dev()
        sig = (tuple(sorted((k, tuple(sorted(v))) for k, v in held.items())), self.chosen)
        if sig == self._live_sig:
            return
        self._live_sig = sig
        slot_srcs = {}
        if dev is not None:
            for s in ce.SLOTS:
                for src in self.editor.sources(dev, s.key):
                    slot_srcs.setdefault(src, []).append(s.key)
        for iid, key in self._rows.items():
            h = held.get(key, frozenset()) if key else frozenset()
            if key and key == self.chosen and dev is not None:
                parts = []
                for src in sorted(h)[:6]:
                    keys = slot_srcs.get(src)
                    parts.append(f"{src} = {keys[0]}" if keys else (f"{src} " + t("(no game button)")))
                state = ",  ".join(parts)
            else:
                state = ",  ".join(sorted(h)[:6])
            self.tv_players.set(iid, "lamp", "●" if h else "○")
            self.tv_players.set(iid, "state", state)
            tags = ["lit"] if h else ([] if key else ["none"])
            self.tv_players.item(iid, tags=tags)
        if dev is not None:
            h = held.get(self.chosen, frozenset())
            live = {k for src in h for k in slot_srcs.get(src, ())}
            for s in ce.SLOTS:
                tags = set(self.tv.item(s.key, "tags") or ())
                (tags.add if s.key in live else tags.discard)("live")
                self.tv.item(s.key, tags=tuple(tags))

    # ---------------------------------------------------------------- the pad drives the screen
    def _do_action(self, action):
        if action in ("up", "down"):
            keys = [s.key for s in ce.SLOTS]
            cur = self.selected_key()
            i = keys.index(cur) if cur in keys else 0
            i = max(0, i - 1) if action == "up" else min(len(keys) - 1, i + 1)
            self.tv.selection_set(keys[i])
            self.tv.see(keys[i])
        elif action == "accept":
            self.set_selected(pad=True)
        elif action == "clear":
            self.clear_selected()
        elif action == "save":
            self.do_save()
        elif action == "back":
            self.close(from_pad=True)

    # ---------------------------------------------------------------- asking for buttons
    def start_all(self):
        self.begin(ce.GUIDED_BUTTONS)

    def start_directions(self):
        self.begin(ce.GUIDED_DIRECTIONS)

    def set_selected(self, pad=False):
        key = self.selected_key()
        if key:
            self.begin([key], pad=pad)

    def begin(self, keys, pad=False):
        if self.dev() is None:
            self.status(t("Press a button on a controller first, or pick one in the list."), WARN)
            return
        self.queue = list(keys)
        self.cap_total = len(keys)
        self.pad_started = pad
        self.prompt.grid()
        self._next_capture()

    def _next_capture(self):
        if not self.queue:
            self._end_capture()
            return
        self.cap_key = self.queue.pop(0)
        self.capture = Capture(self.poller.clock(), timeout_s=PAD_TIMEOUT_S if self.pad_started else None)
        n = self.cap_total - len(self.queue)
        self.prompt_var.set(t("Press the button for {button}...", button=self.slot_label(self.cap_key)))
        hint = t("Press only that one button on the controller.")
        if self.cap_total > 1:
            hint = t("{n} of {total}.", n=n, total=self.cap_total) + " " + hint
        if self.pad_started:
            hint += " " + t("Wait a few seconds to skip it.")
        self.prompt_hint.set(hint)
        self.tv.selection_set(self.cap_key)
        self.tv.see(self.cap_key)

    def _end_capture(self, message=None):
        self.capture = None
        self.queue = []
        self.cap_key = None
        self.pad_started = False
        self.prompt.grid_remove()
        self.nav.reset()
        self._refresh_all()
        if message:
            self.status(message)

    def _capture_result(self, res):
        kind, payload = res
        key = self.cap_key
        if kind == "ok":
            self._assign(key, payload)
            self._next_capture()
        elif kind == "multi":
            self.status(t("That was several buttons at once ({sources}). Press one button only.",
                          sources=" + ".join(payload)), WARN)
            self.capture = Capture(self.poller.clock(), timeout_s=PAD_TIMEOUT_S if self.pad_started else None)
        else:
            self.status(t("{button}: skipped.", button=self.slot_label(key)))
            self._next_capture()

    def _assign(self, key, src):
        dev, scope = self.dev(), self.scope()
        before = {s.key: self.editor.sources(dev, s.key) for s in ce.SLOTS}
        try:
            self.editor.bind(dev, scope, key, [src])
        except ValueError as e:
            self.status(str(e), ERROR)
            return
        lost = [s.key for s in ce.SLOTS if s.key != key and src in before[s.key] and not self.editor.sources(dev, s.key)]
        msg = t("{button} = {source}.", button=self.slot_label(key), source=src)
        if lost:
            msg += " " + t("{source} was {other}; that one has no button now.", source=src,
                           other=", ".join(self.slot_label(k) for k in lost))
        if self.editor.notes:
            msg += " " + " ".join(self.editor.notes)
        self.status(msg)
        self._refresh_all()

    def cap_skip(self):
        if self.capture is not None:
            self._next_capture()

    def cap_clear(self):
        if self.capture is not None and self.cap_key:
            self.editor.clear(self.dev(), self.scope(), self.cap_key)
            self.status(t("{button}: cleared.", button=self.slot_label(self.cap_key)))
            self._refresh_all()
            self._next_capture()

    def cap_stop(self):
        self._end_capture(t("Stopped."))

    def _escape(self):
        if self.capture is not None:
            self.cap_stop()
        else:
            self.close()

    def clear_selected(self):
        key = self.selected_key()
        dev = self.dev()
        if not key or dev is None:
            return
        self.editor.clear(dev, self.scope(), key)
        self.status(t("{button}: cleared.", button=self.slot_label(key)))
        self._refresh_all()

    # ---------------------------------------------------------------- options
    def _on_scope(self):
        d = self.device()
        if d is not None:
            self.scope_of[d.key] = self.scope_var.get()
            self._refresh_all()

    def apply_preset(self):
        dev = self.dev()
        if dev is None:
            return
        title = self.preset_var.get()
        for r in ce.recipes_for(dev.kind):
            if t(ce.recipe_title(r, dev.kind)) == title:
                ok = self.editor.apply_recipe(dev, self.scope(), r.id)
                msg = t("Layout: {name}.", name=title)
                if self.editor.notes:
                    msg += " " + " ".join(self.editor.notes)
                self.status(msg, MUTED if ok else WARN)
                self._refresh_all()
                return
        self.status(t("Pick a layout in the list first."), WARN)

    def reset_defaults(self):
        dev = self.dev()
        if dev is None:
            return
        shared = self.editor.has_content(dev.kind, preset_counts=False)
        text = t("Put {name} back to the default buttons? Your comments and other settings in controls.ini stay.",
                 name=self.device().name)
        if shared:
            text += "\n\n" + t("The part of the file that is for all {kind} controllers has button lines too. "
                               "Reset those as well?", kind=_kind_name(dev.kind))
            ans = self._ask("yesnocancel", t("Reset to defaults"), text)
            if ans is None:
                return
        else:
            if not self._ask("yesno", t("Reset to defaults"), text):
                return
            ans = False
        self.editor.reset(dev, shared=bool(ans))
        self.scope_of.pop(self.chosen, None)
        self.status(t("Reset to the defaults. Save to keep it."))
        self._refresh_all()

    def _on_player_opt(self):
        dev, d = self.dev(), self.device()
        if dev is None:
            return
        pick = self._opt_key(self.player_opts, self.player_var.get())
        self.editor.assign_port(self._device_spec(d), None if pick == "auto" else int(pick))
        self.status(t("{name} is {player}. Save to keep it.", name=d.name,
                      player=self.player_var.get().lower()))
        self._refresh_all()

    def _on_stick(self):
        dev = self.dev()
        if dev is None or dev.port < 0:
            return
        self.editor.set_port_option(dev.port, "stick", self._opt_key(self.stick_opts, self.stick_var.get()))
        self._refresh_all()

    def _on_socd(self):
        dev = self.dev()
        if dev is None or dev.port < 0:
            return
        self.editor.set_port_option(dev.port, "socd", self._opt_key(self.socd_opts, self.socd_var.get()))
        self._refresh_all()

    # ---------------------------------------------------------------- the file
    def do_save(self):
        if not self.editor.dirty:
            return True
        try:
            self.editor.save()
        except ce.FileChanged:
            if not self._ask("yesno", t("controls.ini changed"), t(
                    "controls.ini was changed by something else since this screen opened. Overwrite it with "
                    "your settings? (The old file is kept as controls.ini.bak.)")):
                return False
            try:
                self.editor.save(force=True)
            except (OSError, ValueError) as e:
                self.status(str(e), ERROR)
                return False
        except (OSError, ValueError) as e:
            self.status(t("Could not save: {error}", error=str(e)), ERROR)
            return False
        msg = t("Saved {path}. The game reads it when it starts.", path=self.editor.path)
        if self.game_running():
            msg += " " + t("The game that is running keeps its old buttons until you start it again.")
        self.status(msg, OK)
        self._refresh_all()
        return True

    def do_revert(self):
        self.editor.revert()
        self.scope_of.clear()
        self.status(t("Changes undone."))
        self._refresh_all()

    def close(self, from_pad=False):
        """Close the window; asks what to do with unsaved changes. Returns False if it stayed open."""
        if self._closed:
            return True
        if self.editor.dirty:
            if from_pad:
                self.status(t("There are unsaved changes. Save them first, or close with the mouse."), WARN)
                return False
            ans = self._ask("yesnocancel", t("Controls"), t("Save the changes to controls.ini?"))
            if ans is None:
                return False
            if ans and not self.do_save():
                return False
        self._closed = True
        self.poller.stop()
        if self._after is not None:
            try:
                self.top.after_cancel(self._after)
            except tk.TclError:
                pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        return True


def open_dialog(app, **kw):
    """Settings -> Set up controllers...: the one Controls window of the launcher."""
    dlg = getattr(app, "_controls_dialog", None)
    if dlg is not None and dlg.alive():
        dlg.top.lift()
        dlg.top.focus_set()
        return dlg

    def running():
        g = getattr(app, "game", None)
        return bool(g and g.running())
    dlg = ControlsDialog(app, app.settings, game_running=running, **kw)
    app._controls_dialog = dlg
    return dlg


def close_for_app(app):
    """The launcher is closing: False if the person kept the Controls window open (unsaved changes)."""
    dlg = getattr(app, "_controls_dialog", None)
    if dlg is not None and dlg.alive():
        return dlg.close()
    return True
