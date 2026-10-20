"""T5DR Online launcher: build the game from your own copy, then play.

    pythonw launcher/t5dr_launcher.pyw            (the release starts it through "T5DR Online.exe")
    python  launcher/t5dr_launcher.pyw --screenshots DIR   (docs: save a PNG of every tab, then exit)

Tabs: Build (choose .pkg + .rap, check the build tools, BUILD GAME with live
progress and log), Play, Settings, Online (online.py), Replays (replays_ui.py).
"""
import argparse
import ctypes
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Every Python program the launcher starts (build tools, match driver, lobby helpers) reads and writes its
# files in UTF-8, not in Windows' code page: a Korean (cp949) Windows broke the build on a non-ASCII character.
os.environ["PYTHONUTF8"] = "1"
import core    # noqa: E402
import online  # noqa: E402
from core import N_, t  # noqa: E402  (English text in, the player's language out; lobby/t5lobby/i18n.py)
import problem_report as report  # noqa: E402
import problem_report_ui as report_ui  # noqa: E402
import replays  # noqa: E402
import replays_ui  # noqa: E402
import updater  # noqa: E402
try:
    import controls_ui  # noqa: E402  (needs lobby/t5lobby; without it the Settings tab has no button for it)
except ImportError:
    controls_ui = None

if core.I18N:
    from t5lobby import dialogs  # noqa: E402  (message boxes whose buttons follow the chosen language)
else:
    class dialogs:  # noqa: N801 -- lobby/ is missing from this copy: the system's own boxes, in English
        show_info = staticmethod(lambda title, msg, parent=None: messagebox.showinfo(title, msg, parent=parent))
        show_error = staticmethod(lambda title, msg, parent=None: messagebox.showerror(title, msg, parent=parent))
        ask_yes_no = staticmethod(lambda title, msg, parent=None: messagebox.askyesno(title, msg, parent=parent))

APP_TITLE = "T5DR Online"
COLORS = {"ok": "#1a7f37", "warn": "#9a6700", "error": "#cf222e", "muted": "#57606a",
          "accent": "#0b5cad", "accent_hover": "#094a8c", "log_bg": "#0d1117", "log_fg": "#c9d1d9"}
GLYPH = {"pending": "○", "running": "◔", "done": "✔", "skip": "✔", "failed": "✖"}

CONTROLS = [
    # action, PS3, keyboard, Xbox controller (English; t() where the table is shown)
    (N_("Left punch (1)"), N_("Square"), N_("A"), N_("X")),
    (N_("Right punch (2)"), N_("Triangle"), N_("S"), N_("Y")),
    (N_("Left kick (3)"), N_("Cross"), N_("Z"), N_("A")),
    (N_("Right kick (4)"), N_("Circle"), N_("X"), N_("B")),
    (N_("Move / menus"), N_("D-pad, left stick"), N_("Arrow keys"), N_("D-pad, left stick")),
    (N_("L1 / R1"), N_("L1 / R1"), N_("Q / W"), N_("LB / RB")),
    (N_("L2 / R2"), N_("L2 / R2"), N_("1 / 2"), N_("LT / RT")),
    (N_("Start / pause"), N_("START"), N_("Enter"), N_("Start")),
    (N_("Select"), N_("SELECT"), N_("Tab"), N_("Back")),
    (N_("Quit the game"), "", N_("Esc"), ""),
    (N_("Online tab: accept / decline"), N_("Cross / Circle"), N_("Mouse"), N_("A / B")),
]


def set_big_state(btn, enabled):
    if isinstance(btn, ttk.Button):          # the dark theme's big button (theme.py draws its states)
        btn.configure(state="normal" if enabled else "disabled", cursor="hand2" if enabled else "arrow")
        return
    btn.configure(state="normal" if enabled else "disabled",
                  bg=COLORS["accent"] if enabled else "#aab4c0", cursor="hand2" if enabled else "arrow")


class VScroll:
    """A frame (`inner`) that scrolls up and down inside `parent` when it is taller than the room it gets: the
    Settings tab at 133 % display scaling and more, or in a small window. The mouse wheel anywhere over it scrolls
    it, and a control that gets the focus (Tab, or anything else that moves it) is scrolled into view. Never
    sideways: `inner` is as wide as the visible area, and the area asks for `inner`'s natural width, so the window's
    usual width check still covers it."""

    def __init__(self, parent, px=int):
        bg = ttk.Style(parent).lookup("TFrame", "background") or parent.winfo_toplevel().cget("background")
        # (no yscrollincrement: with one, Tk keeps the view on whole steps and the last few pixels of the content
        # could never be scrolled to)
        self.canvas = tk.Canvas(parent, background=bg, highlightthickness=0, borderwidth=0, takefocus=0,
                                height=px(200))
        self.bar = ttk.Scrollbar(parent, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self.item = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.margin = px(24)                 # what is shown above / below a control scrolled into view
        self.step = px(60)                   # one notch of the mouse wheel
        self.tag = f"VScroll{id(self)}"      # every widget in `inner` gets it (adopt): the wheel and the focus
        self.canvas.bind_class(self.tag, "<MouseWheel>", self._wheel)
        self.canvas.bind_class(self.tag, "<FocusIn>", self._focus, add="+")
        self.inner.bind("<Configure>", lambda _e: self.refresh(), add="+")
        self.canvas.bind("<Configure>", self._resized, add="+")
        for w in (self.canvas, self.bar):
            w.bindtags((self.tag,) + w.bindtags())

    def adopt(self, widget=None):
        """Give `widget` and everything in it (default: all of `inner`) the wheel and the focus handling; call it
        after building the content, and again for widgets added later."""
        w = self.inner if widget is None else widget
        if self.tag not in w.bindtags():
            w.bindtags((self.tag,) + w.bindtags())
        for c in w.winfo_children():
            self.adopt(c)

    def refresh(self):
        """The scrolled region from what `inner` asks for: all of its height can be scrolled to, and the area is as
        wide as `inner` wants to be."""
        w, h = self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, w, h), width=w)

    def _resized(self, e):
        self.canvas.itemconfigure(self.item, width=e.width)     # (as wide as the area: no sideways scrolling)

    def _wheel(self, e):
        if e.delta:
            notches = -e.delta // 120 if abs(e.delta) >= 120 else (-1 if e.delta > 0 else 1)
            self.scroll_to(self.canvas.canvasy(0) + notches * self.step)
        return "break"                       # (the page scrolls, not the small text box or table under the mouse)

    def scroll_to(self, y):
        """Put the content's pixel row `y` at the top of the view (as far as the content goes)."""
        content_h = self.inner.winfo_reqheight()
        if content_h > 0:
            self.canvas.yview_moveto(max(0.0, min(y, content_h - self.canvas.winfo_height())) / content_h)

    def _focus(self, e):
        try:
            self.see(e.widget)
        except (tk.TclError, AttributeError):
            pass

    def see(self, widget):
        """Scroll so that `widget` (in `inner`) is in view, with a little room around it; nothing if it is."""
        view_h = self.canvas.winfo_height()
        if view_h <= 1:
            return
        y = widget.winfo_rooty() - self.inner.winfo_rooty()
        h = widget.winfo_height()
        top = self.canvas.canvasy(0)
        if y - self.margin < top:
            self.scroll_to(y - self.margin)
        elif y + h + self.margin > top + view_h:
            self.scroll_to(y + h + self.margin - view_h)


def load_theme():
    """The dark theme shared with the Online tab (lobby/t5lobby/theme.py; online.py put lobby/ on the
    path). None in a copy without lobby/: the launcher then keeps the plain Windows look."""
    try:
        from t5lobby import theme
        return theme
    except ImportError:
        return None


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


class App(tk.Tk):
    def __init__(self, offscreen=False, settings=None):
        super().__init__()
        self.readonly = offscreen
        self.settings = settings if settings is not None else core.Settings()
        self.language = core.apply_language(self.settings)      # before the first text is built
        self.info = core.release_info()
        self.build = None
        self.game = None
        self.restart_requested = False
        self.step_state = {s: "pending" for s in core.build_game.STEPS}
        self.step_t0 = None
        self.cur_step = None
        self._run_shown = False        # the Play tab shows "Running ..." (the game's end is explained once)
        self.sub = 0.0
        self._last_status = None
        if not offscreen:
            core.log(f"launcher {self.info.get('version', '?')} started, Python {sys.version.split()[0]}, "
                     f"output {self.settings.out_dir}")
            gone = replays.prune(self.settings.replay_dir)       # the newest replays.DEFAULT_KEEP files stay
            if gone:
                core.log(f"replays: {gone} old replay file(s) deleted (the newest {replays.DEFAULT_KEEP} are kept)")
        self.title(f"{APP_TITLE} {self.info.get('version', '')}".strip())
        self.minsize(900, 680)
        self.geometry("1000x780" + ("+60+60" if offscreen else ""))
        if offscreen:
            # docs screenshots: on screen (so Windows paints it) but fully transparent, and
            # every action disabled, so the person at the PC neither sees it nor can trigger it
            self.attributes("-alpha", 0.0)
            self.after(400, self._click_through)
        self._style()
        self._layout()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._tick)
        self.after(200, self.refresh_inputs)
        self.after(300, self.refresh_prereqs)
        self.after(400, self.refresh_game_state)

    def report_callback_exception(self, exc, val, tb):
        """An error inside a button or timer: Tk would only print it (nowhere, under pythonw). It goes
        into launcher.log, so a problem report shows it."""
        import traceback
        if not self.readonly:
            core.log("error in the launcher:\n" + "".join(traceback.format_exception(exc, val, tb)))
        super().report_callback_exception(exc, val, tb)

    def _click_through(self):
        """WS_EX_TRANSPARENT on the (layered) frame: mouse clicks go to the windows below."""
        try:
            self.update_idletasks()
            u = ctypes.windll.user32
            u.GetWindowLongW.restype = ctypes.c_long
            hwnd = u.GetParent(self.winfo_id())
            u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x20)

            class PT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            x, y = self.winfo_rootx() + 200, self.winfo_rooty() + 200
            hit = u.WindowFromPoint(PT(x, y))
            if hit and u.GetAncestor(ctypes.c_void_p(hit), 2) == hwnd:   # GA_ROOT is still us
                print("click-through did not take effect; closing", file=sys.stderr)
                self.destroy()
        except (AttributeError, OSError):
            pass

    # ------------------------------------------------------------------ look
    def _style(self):
        self.theme = load_theme()
        if self.theme is not None:
            self._dark_style()
            return
        st = ttk.Style(self)
        if "vista" in st.theme_names():
            st.theme_use("vista")
        base = ("Segoe UI", 10)
        self.option_add("*Text.Font", ("Consolas", 9))
        st.configure(".", font=base)
        st.configure("H1.TLabel", font=("Segoe UI", 15, "bold"))
        st.configure("H2.TLabel", font=("Segoe UI", 11, "bold"))
        st.configure("Muted.TLabel", foreground=COLORS["muted"])
        for k in ("ok", "warn", "error"):
            st.configure(f"{k}.TLabel", foreground=COLORS[k])
        st.configure("Step.TLabel", font=("Segoe UI", 10), padding=(6, 2))
        st.configure("StepRun.TLabel", font=("Segoe UI", 10, "bold"), foreground=COLORS["accent"], padding=(6, 2))
        st.configure("StepDone.TLabel", foreground=COLORS["ok"], padding=(6, 2))
        st.configure("StepFail.TLabel", foreground=COLORS["error"], font=("Segoe UI", 10, "bold"), padding=(6, 2))
        st.configure("TNotebook.Tab", padding=(16, 6))

    def _dark_style(self):
        th = self.theme.apply(self)
        self.theme.bind_return_on_buttons(self)
        C = self.theme.C
        COLORS.update({"ok": C["ok"], "warn": C["warn"], "error": C["bad"], "muted": C["muted"],
                       "accent": C["accent"], "accent_hover": C["accent_hi"], "log_bg": C["surface"],
                       "log_fg": C["muted"], "text": C["text"], "step": C["info"]})
        if controls_ui is not None:          # the Controls window's colours on the dark background
            controls_ui.COLORS.update({"ok": C["ok"], "muted": C["muted"], "warn": C["warn"], "error": C["bad"],
                                       "live": self.theme.mix(C["ok"], C["surface"], 0.78)})
        st = th.style
        f = th.fonts
        px = th.px
        self.option_add("*Text.Font", f["mono"])
        st.configure("Step.TLabel", font=f["body"], foreground=C["faint"], padding=(px(6), px(2)))
        st.configure("StepRun.TLabel", font=f["bold"], foreground=C["accent_hi"], padding=(px(6), px(2)))
        st.configure("StepDone.TLabel", font=f["body"], foreground=C["ok"], padding=(px(6), px(2)))
        st.configure("StepFail.TLabel", font=f["bold"], foreground=C["bad"], padding=(px(6), px(2)))
        # the same window at any DPI (fonts grow with it), never larger than the screen
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.minsize(min(px(900), sw - 40), min(px(680), sh - 80))
        if not self.readonly:
            self.geometry(f"{min(px(1080), sw - 40)}x{min(px(840), sh - 80)}")
        else:
            self.geometry(f"{px(1080)}x{px(840)}+60+60")

    def px(self, v):
        """A size in pixels at this DPI (the dark theme's scale; 1:1 without it)."""
        theme = getattr(self, "theme", None)
        return theme.apply(self).px(v) if theme is not None else int(v)

    def wrap_style(self, cls, width):
        """A ttk style for check / radio buttons whose text wraps at `width` (pixels at 100 %): a long label in
        another language takes two lines instead of pushing the window wider."""
        name = f"W{width}.{cls}"
        ttk.Style(self).configure(name, wraplength=self.px(width))
        return name

    def big_button(self, parent, text, cmd):
        if getattr(self, "theme", None) is not None:
            return ttk.Button(parent, text=text, command=cmd, style="Hero.TButton", cursor="hand2")
        b = tk.Button(parent, text=text, command=cmd, font=("Segoe UI", 13, "bold"), fg="white",
                      bg=COLORS["accent"], activebackground=COLORS["accent_hover"], activeforeground="white",
                      relief="flat", padx=28, pady=8, cursor="hand2", disabledforeground="#c8d1dc")
        return b

    # ------------------------------------------------------------------ layout
    def _layout(self):
        head = ttk.Frame(self, padding=(16, 12, 16, 4))
        head.pack(fill="x")
        if getattr(self, "theme", None) is not None:
            self.theme.Mark(head, size=30).pack(side="left", padx=(0, 10))
        ttk.Label(head, text="Tekken 5: Dark Resurrection Online", style="H1.TLabel").pack(side="left")
        ttk.Label(head, style="Muted.TLabel",
                  text="   " + t("native Windows build  ·  launcher {version}",
                                 version=self.info.get("version", "?"))).pack(side="left")
        self.updater = updater.attach(self, head)     # "Check for updates", the offer, the update itself
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(4, 0))
        self.tabs = {}
        for key, label in (("build", t("Build")), ("play", t("Play offline")), ("settings", t("Settings")),
                           ("online", t("Play online")), ("replays", t("Replays"))):
            f = ttk.Frame(self.nb)
            self.nb.add(f, text=f"  {label}  ")
            self.tabs[key] = f
        self.tab_keys = list(self.tabs)
        self._build_tab(self.tabs["build"])
        self._play_tab(self.tabs["play"])
        self._settings_tab(self.tabs["settings"])
        self.online = online.OnlineTab(self.tabs["online"], self)
        self.replays = replays_ui.ReplaysTab(self.tabs["replays"], self)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab)
        self.status = tk.StringVar(value="")
        self.status.trace_add("write", self._log_status)
        bar = ttk.Frame(self, padding=(16, 4))
        bar.pack(fill="x", side="bottom", before=self.nb)     # (stays visible when a tab is too tall)
        ttk.Label(bar, textvariable=self.status, style="Muted.TLabel").pack(side="left")
        ttk.Label(bar, style="Muted.TLabel",
                  text=t("Output: {folder}", folder=self.settings.out_dir)).pack(side="right")

    def _build_tab(self, tab):
        tab.columnconfigure(0, weight=1)
        # your files
        files = ttk.LabelFrame(tab, text="  " + t("Your game") + "  ", padding=(12, 6))
        files.grid(row=0, column=0, sticky="we", padx=8, pady=(8, 4))
        files.columnconfigure(1, weight=1)
        self.pkg_var = tk.StringVar(value=self.settings["pkg"])
        self.rap_var = tk.StringVar(value=self.settings["rap"])
        self.pkg_info, self.rap_info = tk.StringVar(), tk.StringVar()
        self.pkg_lbl = self.rap_lbl = None
        for row, (label, var, info, kind) in enumerate((
                (t("Package (.pkg)"), self.pkg_var, self.pkg_info, "pkg"),
                (t("License (.rap)"), self.rap_var, self.rap_info, "rap"))):
            ttk.Label(files, text=label).grid(row=row * 2, column=0, sticky="w", padx=(0, 8))
            e = ttk.Entry(files, textvariable=var)
            e.grid(row=row * 2, column=1, sticky="we")
            e.bind("<FocusOut>", lambda _e: self.refresh_inputs())
            ttk.Button(files, text=t("Browse…"), command=lambda k=kind: self.browse(k)).grid(
                row=row * 2, column=2, padx=(8, 0))
            lbl = ttk.Label(files, textvariable=info, style="Muted.TLabel")
            lbl.grid(row=row * 2 + 1, column=1, columnspan=2, sticky="w", pady=(0, 4))
            if kind == "pkg":
                self.pkg_lbl = lbl
            else:
                self.rap_lbl = lbl
        ttk.Label(files, style="Muted.TLabel", wraplength=820, justify="left", text=t(
            "Supported: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version 01.00 -- the package "
            "file and the license (.rap) from your own account. Nothing leaves this PC.")).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))
        warn = core.install_warnings(core.ROOT, self.settings.out_dir)
        if warn:
            ttk.Label(files, style="warn.TLabel", wraplength=820, justify="left",
                      text="\n".join("⚠ " + w for w in warn)).grid(row=5, column=0, columnspan=3, sticky="w",
                                                                    pady=(4, 0))

        # build tools
        tools = ttk.LabelFrame(tab, text="  " + t("Build tools on this PC") + "  ", padding=(12, 6))
        tools.grid(row=1, column=0, sticky="we", padx=8, pady=4)
        tools.columnconfigure(0, weight=1)
        self.tools_tv = ttk.Treeview(tools, columns=("state", "detail"), show="tree headings", height=7,
                                     selectmode="none")
        self.tools_tv.heading("#0", text=t("Needed"))
        self.tools_tv.heading("state", text="")
        self.tools_tv.heading("detail", text=t("Found"))
        self.tools_tv.column("#0", width=self.px(310), stretch=False)        # (wide enough for every language)
        self.tools_tv.column("state", width=self.px(110), stretch=False, anchor="center")
        self.tools_tv.column("detail", width=self.px(470))
        self.tools_tv.tag_configure("bad", foreground=COLORS["error"])
        self.tools_tv.tag_configure("good", foreground=COLORS.get("text", "#24292f"))
        self.tools_sum = tk.StringVar(value=t("Checking…"))
        self.tools_sum_lbl = ttk.Label(tools, textvariable=self.tools_sum)
        self.tools_sum_lbl.grid(row=0, column=0, sticky="w")
        btns = ttk.Frame(tools)
        btns.grid(row=0, column=1, sticky="e")
        self.details_btn = ttk.Button(btns, text=t("Details"), command=self.toggle_tools)
        self.details_btn.pack(side="left")
        ttk.Button(btns, text=t("Check again"), command=self.refresh_prereqs).pack(side="left", padx=(8, 0))
        self.install_btn = ttk.Button(btns, text=t("Install missing…"), command=self.install_missing)
        self.install_btn.pack(side="left", padx=(8, 0))
        self.tools_shown = False

        # build
        b = ttk.LabelFrame(tab, text="  " + t("Build") + "  ", padding=(12, 6))
        b.grid(row=2, column=0, sticky="we", padx=8, pady=4)
        b.columnconfigure(0, weight=1)
        strip = ttk.Frame(b)
        strip.grid(row=0, column=0, columnspan=3, sticky="w")
        self.step_lbls = {}
        for i, s in enumerate(core.build_game.STEPS):
            lbl = ttk.Label(strip, text=f"{GLYPH['pending']} {t(core.STEP_TITLES[s])}", style="Step.TLabel")
            lbl.grid(row=0, column=i)
            self.step_lbls[s] = lbl
        self.progress = ttk.Progressbar(b, maximum=1000)
        self.progress.grid(row=1, column=0, columnspan=3, sticky="we", pady=(6, 2))
        self.detail = tk.StringVar(value=t("Press BUILD GAME. It takes a few minutes; the game data stays in this folder."))
        ttk.Label(b, textvariable=self.detail, style="Muted.TLabel", wraplength=860,
                  justify="left").grid(row=2, column=0, columnspan=3, sticky="w")
        row = ttk.Frame(b)
        row.grid(row=3, column=0, columnspan=3, sticky="we", pady=(8, 2))
        self.build_btn = self.big_button(row, t("BUILD GAME"), self.start_build)
        self.build_btn.pack(side="left")
        self.cancel_btn = ttk.Button(row, text=t("Cancel"), command=self.cancel_build, state="disabled")
        self.cancel_btn.pack(side="left", padx=8)
        self.force_var = tk.BooleanVar(value=False)
        checks = ttk.Frame(row)             # (one above the other: the row stays narrow enough in every language)
        checks.pack(side="left", padx=8)
        ttk.Checkbutton(checks, text=t("Redo every step"), variable=self.force_var).pack(anchor="w")
        self.lowprio_var = tk.BooleanVar(value=self.settings["low_priority"])
        ttk.Checkbutton(checks, text=t("Keep the PC responsive (slower)"), variable=self.lowprio_var,
                        command=self.save_settings).pack(anchor="w")
        ttk.Button(row, text=t("Open build.log"),
                   command=lambda: core.open_path(os.path.join(self.settings.out_dir, "build.log"))).pack(side="right")
        ttk.Button(row, text=t("Report a problem..."), command=self.report_problem).pack(side="right", padx=8)
        self.error = tk.StringVar()
        self.error_lbl = tk.Label(b, textvariable=self.error, fg=COLORS["error"], wraplength=860, justify="left",
                                  font=(core.ui_family(), 10, "bold"))
        self.error_lbl.grid(row=4, column=0, columnspan=3, sticky="w")

        # log
        tab.rowconfigure(3, weight=1)
        self.log = ScrolledText(tab, height=8, font=("Consolas", 9), bg=COLORS["log_bg"], fg=COLORS["log_fg"],
                                insertbackground=COLORS["log_fg"], relief="flat", state="disabled", wrap="none")
        self.log.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.log.tag_configure("step", foreground=COLORS.get("step", "#58a6ff"))
        self.log.tag_configure("err", foreground="#ff7b72")
        if getattr(self, "theme", None) is not None:
            # the dark theme's thin scroll bar instead of the light Windows one
            self.log.configure(padx=8, pady=6, highlightthickness=0)
            self.log.vbar.pack_forget()
            sb = ttk.Scrollbar(self.log.frame, orient="vertical", command=self.log.yview)
            sb.pack(side="right", fill="y", before=self.log._w)   # (str(self.log) is its frame)
            self.log.configure(yscrollcommand=sb.set)
            self.log.frame.configure(bg=COLORS["log_bg"])

    def _play_tab(self, tab):
        box = ttk.Frame(tab, padding=24)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=t("Play offline"), style="H1.TLabel").pack(anchor="w")
        # what "offline" means, and the way to the Online tab (internet play)
        what = ttk.Frame(box)
        what.pack(anchor="w", pady=(2, 0))
        ttk.Label(what, style="Muted.TLabel", text=t(
            "Arcade, Versus, Practice and the other modes on this PC. To play against people over the "
            "internet, use the")).pack(side="left")
        self.to_online_btn = ttk.Button(what, text=t("Online tab"), style="Link.TButton", cursor="hand2",
                                        command=lambda: self.nb.select(self.tabs["online"]))
        self.to_online_btn.pack(side="left")
        self.state_var = tk.StringVar(value=t("Checking the build…"))
        self.state_lbl = ttk.Label(box, textvariable=self.state_var, wraplength=820, justify="left")
        self.state_lbl.pack(anchor="w", pady=(6, 14))
        nick = ttk.Frame(box)
        nick.pack(anchor="w", pady=(0, 14))
        ttk.Label(nick, text=t("Your name (shown in the game)")).pack(side="left")
        self.nick_var = tk.StringVar(value=self.settings["nickname"])
        ttk.Entry(nick, textvariable=self.nick_var, width=20).pack(side="left", padx=8)
        row = ttk.Frame(box)
        row.pack(anchor="w")
        self.play_btn = self.big_button(row, t("PLAY OFFLINE"), self.play)
        self.play_btn.pack(side="left")
        self.stop_btn = ttk.Button(row, text=t("Stop game"), command=self.stop_game, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        self.run_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.run_var, style="H2.TLabel").pack(anchor="w", pady=(14, 4))
        links = ttk.Frame(box)
        links.pack(anchor="w", pady=(4, 0))
        ttk.Button(links, text=t("Open newest game log"), command=self.open_game_log).pack(side="left")
        ttk.Button(links, text=t("Open saves folder"),
                   command=lambda: core.open_path(os.path.join(self.settings.out_dir, "gamedata"))).pack(
            side="left", padx=8)
        ttk.Button(links, text=t("Report a problem..."), command=self.report_problem).pack(side="left")
        ttk.Label(box, style="Muted.TLabel", wraplength=820, justify="left", text=t(
            "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers both work; "
            "see Settings for the keys. Esc closes the game. START skips the intro movie.")).pack(
            anchor="w", pady=(22, 0))

    def _settings_tab(self, tab):
        # taller than the window at 133 % display scaling and more: it scrolls (wheel, scrollbar, the focus)
        self.settings_scroll = VScroll(tab, self.px)
        box = ttk.Frame(self.settings_scroll.inner, padding=(24, 16))
        box.pack(fill="both", expand=True)
        left = ttk.Frame(box)
        left.grid(row=0, column=0, sticky="nwe", padx=(0, 12))
        disp = ttk.LabelFrame(left, text="  " + t("Display") + "  ", padding=(12, 6))
        disp.pack(fill="x")
        self.display_var = tk.StringVar(value=self.settings["display"])
        for key, label in core.DISPLAY_MODES:
            ttk.Radiobutton(disp, text=t(label), value=key, variable=self.display_var, style=self.wrap_style(
                "TRadiobutton", 400), command=self.save_settings).pack(anchor="w", pady=1)
        ttk.Label(disp, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "The picture is scaled to the window; how sharp it is depends on Internal resolution. "
            "You can also drag the window's edges. Alt+Enter or F11 switches borderless fullscreen "
            "in the game.")).pack(anchor="w", pady=(6, 0))

        # VSync (PS3_VSYNC=0 when off, core.VSYNC_MODES): only how pictures reach the screen. No frame
        # rate choice: the game's simulation is tied to 60 fps like on the PS3, with VSync on or off.
        vs = ttk.LabelFrame(left, text="  " + t("VSync") + "  ", padding=(12, 6))
        vs.pack(fill="x", pady=(6, 0))
        self.vsync_var = tk.StringVar(value=self.settings["vsync"] if self.settings["vsync"] in core.VSYNC_MODES
                                      else "on")
        for key, label in core.VSYNC_MODES.items():
            ttk.Radiobutton(vs, text=t(label), value=key, variable=self.vsync_var, style=self.wrap_style(
                "TRadiobutton", 400), command=self.save_settings).pack(anchor="w", pady=1)
        ttk.Label(vs, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "The game always runs at 60 fps, like on the PS3.")).pack(anchor="w", pady=(4, 0))
        if core.I18N:
            self._language_box(left)        # (the left column has the room; the right one is the taller)

        # Stage blur / glow (PS3_STAGE_BLUR=0 when off, core.STAGE_BLUR_MODES): the soft focus some
        # stages put on the picture and the sun's glow. Picture only, like VSync.
        sb = ttk.LabelFrame(left, text="  " + t("Stage blur / glow") + "  ", padding=(12, 6))
        sb.pack(fill="x", pady=(6, 0))
        self.stage_blur_var = tk.StringVar(value=self.settings["stage_blur"]
                                           if self.settings["stage_blur"] in core.STAGE_BLUR_MODES else "on")
        row = ttk.Frame(sb)
        row.pack(anchor="w")
        for key, label in core.STAGE_BLUR_MODES.items():
            ttk.Radiobutton(row, text=t(label), value=key, variable=self.stage_blur_var,
                            command=self.save_settings).pack(side="left", padx=(0, 14))
        ttk.Label(sb, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "Some stages blur the picture (the misty swamp) or let the sun glow. Off shows them sharp, "
            "without the glow. Only your picture changes: online, both players can choose differently.")).pack(
            anchor="w", pady=(4, 0))

        # Power saving (PS3_LAPTOP, core.POWER_SAVING; docs/RENDER_PERF.md "Laptops, handhelds and 8-core APUs"):
        # less CPU around the same game, so a laptop or handheld keeps its clock and its 60 fps.
        ps = ttk.LabelFrame(left, text="  " + t("Power saving (laptops, handhelds)") + "  ", padding=(12, 6))
        ps.pack(fill="x", pady=(6, 0))
        self.power_var = tk.StringVar(value=self.settings["power_saving"]
                                      if self.settings["power_saving"] in core.POWER_SAVING else "auto")
        for key, label in core.POWER_SAVING.items():
            ttk.Radiobutton(ps, text=t(label), value=key, variable=self.power_var,
                            command=self._power_saving_changed).pack(anchor="w", pady=1)
        self.power_hint = ttk.Label(ps, style="Muted.TLabel", wraplength=300, justify="left")
        self.power_hint.pack(anchor="w", pady=(4, 0))
        self._power_saving_changed(save=False)

        # Training overlay (T5_TRAINING*, core.TRAINING_MODES, docs/TRAINING.md): inputs and frame data
        # drawn over the picture in Practice; it only reads the game, so it never changes a match.
        tr = ttk.LabelFrame(left, text="  " + t("Training overlay") + "  ", padding=(12, 6))
        tr.pack(fill="x", pady=(6, 0))
        self.training_var = tk.StringVar(value=self.settings["training"] if self.settings["training"] in
                                         core.TRAINING_MODES else "frames")
        row = ttk.Frame(tr)
        row.pack(anchor="w")
        for key, label in core.TRAINING_MODES.items():
            ttk.Radiobutton(row, text=t(label), value=key, variable=self.training_var,
                            command=self.save_settings).pack(side="left", padx=(0, 14))
        self.training_all_var = tk.BooleanVar(value=bool(self.settings.get("training_all")))
        self.training_online_var = tk.BooleanVar(value=bool(self.settings.get("training_online")))
        ttk.Checkbutton(tr, text=t("Also in the other offline modes (Arcade, Versus, ...)"),
                        variable=self.training_all_var, command=self.save_settings).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(tr, text=t("Also online (only your own inputs, no frame data)"),
                        variable=self.training_online_var, command=self.save_settings).pack(anchor="w")
        ttk.Label(tr, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "In Practice: your last inputs with how many frames each was held, and after each exchange the "
            "startup of the move and who can act first (+3, -12). F2 in the game switches it.")).pack(
            anchor="w", pady=(4, 0))

        right = ttk.Frame(box)
        right.grid(row=0, column=1, sticky="nwe")
        other = ttk.LabelFrame(right, text="  " + t("Sound and start") + "  ", padding=(12, 6))
        other.pack(fill="x")
        self.mute_var = tk.BooleanVar(value=self.settings["mute"])
        self.bg_var = tk.BooleanVar(value=self.settings["background"])
        ttk.Checkbutton(other, text=t("Mute sound"), variable=self.mute_var, command=self.save_settings).pack(anchor="w")
        ttk.Checkbutton(other, text=t("Start minimized, without taking focus (for testing)"), variable=self.bg_var,
                        style=self.wrap_style("TCheckbutton", 440), command=self.save_settings).pack(anchor="w",
                                                                                                    pady=(4, 0))
        ttk.Label(other, text=t("Advanced: extra settings, one NAME=VALUE per line"), wraplength=self.px(440),
                  justify="left").pack(anchor="w", pady=(10, 2))
        self.env_text = tk.Text(other, height=3, width=44, font=("Consolas", 9))
        self.env_text.insert("1.0", self.settings["extra_env"])
        self.env_text.pack(anchor="w", fill="x")
        self.env_text.bind("<FocusOut>", lambda _e: self.save_settings())

        # One "Internal resolution" like an emulator's (PS3_INTERNAL_RES, docs/RENDER_PERF.md
        # "Internal resolution"): below Native for weak graphics cards, above for big screens.
        gfx = ttk.LabelFrame(right, text="  " + t("Internal resolution") + "  ", padding=(12, 6))
        gfx.pack(fill="x", pady=(6, 0))
        self.internal_res_var = tk.StringVar(value=self.settings["internal_res"]
                                             if self.settings["internal_res"] in core.INTERNAL_RES else "native")
        keys = list(core.INTERNAL_RES)
        for part in (keys[:3], keys[3:]):
            row = ttk.Frame(gfx)
            row.pack(anchor="w")
            for key in part:
                ttk.Radiobutton(row, text=t(core.INTERNAL_RES[key][0]), value=key, variable=self.internal_res_var,
                                command=self._internal_res_changed).pack(side="left", padx=(0, 14))
        self.internal_res_hint = ttk.Label(gfx, style="Muted.TLabel", wraplength=390, justify="left")
        self.internal_res_hint.pack(anchor="w", pady=(4, 0))
        self._internal_res_changed(save=False)

        # Like Tekken 6 Native Online's input delay option (T5_RB_NET_DELAY, docs/NETPLAY.md
        # "Input delay"): Auto follows the ping; a fixed value counts when both players chose it.
        net = ttk.LabelFrame(right, text="  " + t("Online input delay") + "  ", padding=(12, 6))
        net.pack(fill="x", pady=(6, 0))
        self.input_delay_var = tk.StringVar(value=self.settings["input_delay"]
                                            if self.settings["input_delay"] in core.INPUT_DELAYS else "auto")
        row = ttk.Frame(net)
        row.pack(anchor="w")
        for key, label in core.INPUT_DELAYS.items():
            ttk.Radiobutton(row, text=t(label), value=key, variable=self.input_delay_var,
                            command=self.save_settings).pack(side="left", padx=(0, 14))
        ttk.Label(net, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "Frames. Auto: 1 up to about 60 ms ping, 2 above. 0/1/2 count only when your opponent "
            "picked the same, otherwise Auto. Ranked matches always use 2.")).pack(anchor="w", pady=(4, 0))
        # docs/NETPLAY.md "Getting a direct connection": a forwarded game port lets the opponent's punches in
        self.router_ports_var = tk.BooleanVar(value=bool(self.settings.get("router_ports", True)))
        ttk.Checkbutton(net, text=t("Open the game's port on my router during online matches (UPnP / NAT-PMP / PCP)"),
                        variable=self.router_ports_var, style=self.wrap_style("TCheckbutton", 500),
                        command=self.save_settings).pack(anchor="w", pady=(8, 0))
        ttk.Label(net, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "Helps the direct connection when your opponent's router is strict. The port is open only while "
            "you play and is closed again afterwards.")).pack(anchor="w", pady=(2, 0))

        # Discord Rich Presence (lobby/t5lobby/discord_rpc.py, docs/ONLINE.md): off unless the player turns it on
        dc = ttk.LabelFrame(right, text="  " + t("Discord") + "  ", padding=(12, 6))
        dc.pack(fill="x", pady=(6, 0))
        self.discord_var = tk.BooleanVar(value=bool(self.settings.get("discord_presence", False)))
        ttk.Checkbutton(dc, text=t("Show what I play in my Discord status (Rich Presence)"), variable=self.discord_var,
                        command=self.save_settings).pack(anchor="w")
        ttk.Label(dc, style="Muted.TLabel", wraplength=300, justify="left", text=self._discord_hint()).pack(
            anchor="w", pady=(2, 0))

        # Spectators (docs/SPECTATE.md): who may watch this player's online matches, live, a few seconds late
        spc = ttk.LabelFrame(right, text="  " + t("Spectators") + "  ", padding=(12, 6))
        spc.pack(fill="x", pady=(6, 0))
        self.spectators_var = tk.BooleanVar(value=bool(self.settings.get("spectators", True)))
        self.spectators_ranked_var = tk.BooleanVar(value=bool(self.settings.get("spectators_ranked", False)))
        ttk.Checkbutton(spc, text=t("Friends and room visitors may watch my online matches"),
                        variable=self.spectators_var, style=self.wrap_style("TCheckbutton", 440),
                        command=self.save_settings).pack(anchor="w")
        ttk.Checkbutton(spc, text=t("Also my ranked matches"), variable=self.spectators_ranked_var,
                        style=self.wrap_style("TCheckbutton", 440), command=self.save_settings).pack(anchor="w",
                                                                                                    pady=(4, 0))
        ttk.Label(spc, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "They see the match a few seconds late, in their own game. Only when both players allow it; a ranked "
            "match only when both allow ranked too.")).pack(anchor="w", pady=(4, 0))

        # Unlocks (T5_UNLOCK_STAGES / T5_UNLOCK_ITEMS, docs/DIRECTFIGHT.md "Unlocks"): offline only; the game
        # never changes the save for them. An online game answers as a fresh save does, on both PCs.
        unl = ttk.LabelFrame(right, text="  " + t("Unlocks") + "  ", padding=(12, 6))
        unl.pack(fill="x", pady=(6, 0))
        self.unlock_stages_var = tk.BooleanVar(value=bool(self.settings.get("unlock_stages")))
        self.unlock_items_var = tk.BooleanVar(value=bool(self.settings.get("unlock_items")))
        ttk.Checkbutton(unl, text=t("Unlock all stages (the Tekken 5 stages, without clearing Arcade)"),
                        variable=self.unlock_stages_var, style=self.wrap_style("TCheckbutton", 440),
                        command=self.save_settings).pack(anchor="w")
        ttk.Checkbutton(unl, text=t("Unlock all customization items (free in the item shop)"),
                        variable=self.unlock_items_var, style=self.wrap_style("TCheckbutton", 440),
                        command=self.save_settings).pack(anchor="w", pady=(4, 0))
        ttk.Label(unl, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "Offline only (Arcade, VS, Practice and the rest). Your save is not changed; items you take for free "
            "stay yours (the save is backed up first, in save-backups). Online, both players always get the "
            "same stages and the default costumes.")).pack(anchor="w", pady=(4, 0))

        ctl = ttk.LabelFrame(box, text="  " + t("Controls") + "  ", padding=(12, 6))
        ctl.grid(row=1, column=0, columnspan=2, sticky="nwe", pady=(14, 0))
        # Set the buttons of pads, arcade sticks and hitboxes here instead of editing controls.ini (controls_ui.py)
        cbar = ttk.Frame(ctl)
        cbar.pack(fill="x", pady=(0, 6))
        self.controls_btn = ttk.Button(cbar, text=t("Set up controllers…"), command=self.open_controls,
                                       state="normal" if controls_ui else "disabled")
        self.controls_btn.pack(side="left")
        ttk.Label(cbar, style="Muted.TLabel", wraplength=self.px(640), justify="left", text="  " + (
            t("Pick a pad, stick or hitbox, press the buttons you want for 1 2 3 4 and the rest, "
              "or start from a layout.") if controls_ui else t("(needs the lobby files, which are missing)"))).pack(
            side="left")
        tv = ttk.Treeview(ctl, columns=("ps3", "kb", "pad"), show="tree headings", height=len(CONTROLS),
                          selectmode="none")
        tv.heading("#0", text=t("Action (Tekken default)"))
        tv.heading("ps3", text=t("PS3 button"))
        tv.heading("kb", text=t("Keyboard"))
        tv.heading("pad", text=t("Xbox controller"))
        tv.column("#0", width=self.px(260), stretch=False)        # (wide enough for every language)
        for c in ("ps3", "kb", "pad"):
            tv.column(c, width=self.px(190))
        for a, p, k, x in CONTROLS:
            tv.insert("", "end", text=t(a), values=(t(p), t(k), t(x)))
        tv.pack(fill="x")
        ttk.Label(ctl, style="Muted.TLabel", wraplength=860, justify="left", text=t(
            "Keyboard and the first XInput controller both drive player 1 (they are combined). The keyboard "
            "only counts while the game window has focus. The game's own Options menu can change the button "
            "layout for offline play; online games use the launcher's buttons only.")).pack(anchor="w", pady=(6, 0))
        ttk.Label(ctl, style="Muted.TLabel", wraplength=860, justify="left", text=t(
            "In this window, on the Online tab, a controller or arcade stick works without mouse or keyboard: "
            "Cross / A accepts a match or rematch and starts a search, Circle / B declines, leaves or stops the "
            "search. It only counts while this window is in front, and only after the button was let go for a "
            "moment. Which stick button is Cross follows your controls.ini.")).pack(anchor="w", pady=(4, 0))
        box.columnconfigure(0, weight=1)
        box.columnconfigure(1, weight=1)
        self.settings_scroll.adopt()        # (the Restart now button too: it is made already, shown later)

    def _language_box(self, parent):
        """Auto, then every language in its own name (English, Deutsch, Español, 한국어, ...): someone who cannot
        read the current language still finds theirs. The texts are built once, so a change applies after a
        restart."""
        lang = ttk.LabelFrame(parent, text="  " + t("Language") + "  ", padding=(12, 6))
        lang.pack(fill="x", pady=(6, 0))
        self.language_choice = core.i18n.canonical(self.settings["language"]) or "auto"   # what this run started with
        self.language_var = tk.StringVar(value=self.language_choice)
        grid = ttk.Frame(lang)
        grid.pack(anchor="w")
        per_row = 4
        for i, (key, label) in enumerate(core.LANGUAGE_CHOICES):
            text = t(label) if key == "auto" else label          # (a language's own name stays as it is)
            style = "TRadiobutton"
            family = core.i18n.font_of(key)                     # 한국어 / 日本語 in a font made for them
            if family:
                style = f"Lang{key}.TRadiobutton"
                ttk.Style(self).configure(style, font=(family, 10))
            rb = ttk.Radiobutton(grid, text=text, value=key, variable=self.language_var, style=style,
                                 command=self.language_changed)
            if key == "auto":
                rb.grid(row=0, column=0, columnspan=per_row, sticky="w")
            else:
                rb.grid(row=1 + (i - 1) // per_row, column=(i - 1) % per_row, sticky="w", padx=(0, 14))
        self.lang_note = tk.StringVar(value="")
        note = ttk.Frame(lang)
        note.pack(anchor="w", fill="x")
        ttk.Label(note, textvariable=self.lang_note, style="Muted.TLabel", wraplength=300, justify="left").pack(
            side="left")
        self.restart_btn = ttk.Button(note, text=t("Restart now"), command=self.restart_launcher)

    def language_changed(self):
        self.save_settings()
        if self.language_var.get() == self.language_choice:
            self.lang_note.set("")
            self.restart_btn.pack_forget()
        else:
            self.lang_note.set(t("The language changes when the launcher starts again."))
            self.restart_btn.pack(side="left", padx=(8, 0))

    def restart_launcher(self):
        """Close this launcher and start a new one (the new language applies from the first window on)."""
        if self.readonly:
            return
        if self.build:
            dialogs.show_info(APP_TITLE, t("A build is running. Stop it first, or restart the launcher by hand "
                                           "when it is done."), parent=self)
            return
        if self.game and self.game.running():
            dialogs.show_info(APP_TITLE, t("Close the game first."), parent=self)
            return
        self.restart_requested = True
        self.on_close()

    # ------------------------------------------------------------------ inputs
    def browse(self, kind):
        if kind == "pkg":
            p = filedialog.askopenfilename(title=t("Choose your Tekken 5 DR Online package"),
                                           filetypes=[(t("PS3 package"), "*.pkg"), (t("All files"), "*.*")])
            if p:
                self.pkg_var.set(os.path.normpath(p))
                # the .rap usually sits next to the package
                if not self.rap_var.get():
                    d = os.path.dirname(p)
                    raps = [f for f in os.listdir(d) if f.lower().endswith(".rap")]
                    match = [f for f in raps if core.build_game.CONTENT_ID in f] or raps
                    if match:
                        self.rap_var.set(os.path.join(os.path.normpath(d), match[0]))
        else:
            p = filedialog.askopenfilename(title=t("Choose your license (.rap)"),
                                           filetypes=[(t("PS3 license"), "*.rap"), (t("All files"), "*.*")])
            if p:
                self.rap_var.set(os.path.normpath(p))
        self.refresh_inputs()

    def refresh_inputs(self):
        if self.readonly:
            self.settings.save = lambda: None      # screenshots never write settings
        pkg, rap = self.pkg_var.get().strip().strip('"'), self.rap_var.get().strip().strip('"')
        if not pkg and not rap and not self.settings["pkg"]:
            fp, fr = core.find_candidates()
            if fp:
                self.pkg_var.set(fp)
                pkg = fp
            if fr:
                self.rap_var.set(fr)
                rap = fr
        _ok, lvl, txt = core.describe_pkg(pkg)
        self.pkg_info.set(("✔ " if lvl == "ok" else "⚠ " if lvl == "warn" else "") + txt)
        self.pkg_lbl.configure(style=f"{lvl}.TLabel" if pkg else "Muted.TLabel")
        _ok, lvl, txt = core.describe_rap(rap, pkg)
        self.rap_info.set(("✔ " if lvl == "ok" else "⚠ " if lvl == "warn" else "") + txt)
        self.rap_lbl.configure(style=f"{lvl}.TLabel" if rap else "Muted.TLabel")
        self.settings["pkg"], self.settings["rap"] = pkg, rap
        self.settings.save()

    # ------------------------------------------------------------------ prerequisites
    def refresh_prereqs(self):
        self.status.set(t("Checking build tools…"))

        def work():
            items = core.prereqs.check()
            self.after(0, lambda: self._show_prereqs(items))
        threading.Thread(target=work, daemon=True).start()

    def _show_prereqs(self, items):
        self.prereq_items = items
        self.tools_tv.delete(*self.tools_tv.get_children())
        for it in items:
            self.tools_tv.insert("", "end", text=core.translate_message(it["name"]),
                                 values=("✔ " + t("ok") if it["ok"] else "✖ " + t("missing"),
                                         core.translate_message(it["detail"])),
                                 tags=("good" if it["ok"] else "bad",))
        missing = [it for it in items if not it["ok"]]
        self.install_btn.configure(state="normal" if any(it["install"] for it in missing) else "disabled")
        if missing:
            self.tools_sum.set("✖ " + t("Missing: {names}", names=", ".join(
                core.translate_message(it["name"]) for it in missing)))
            self.tools_sum_lbl.configure(style="error.TLabel")
            self.toggle_tools(True)
        else:
            self.tools_sum.set("✔ " + t("Everything the build needs is installed."))
            self.tools_sum_lbl.configure(style="ok.TLabel")
        self.status.set(t("All build tools found.") if not missing else
                        t("{count} build tool(s) missing -- click 'Install missing…'.", count=len(missing)))

    def toggle_tools(self, show=None):
        self.tools_shown = (not self.tools_shown) if show is None else show
        if self.tools_shown:
            self.tools_tv.grid(row=1, column=0, columnspan=2, sticky="we", pady=(6, 0))
            self.details_btn.configure(text=t("Hide details"))
        else:
            self.tools_tv.grid_remove()
            self.details_btn.configure(text=t("Details"))

    def install_missing(self):
        if self.readonly:
            return
        ids = []
        for it in getattr(self, "prereq_items", []):
            if not it["ok"] and it["install"] and it["install"] not in ids:
                ids.append(it["install"])
        if not ids:
            return
        lines = []
        for i in ids:
            if i == "Microsoft.VisualStudio.2022.BuildTools":
                lines.append("• " + t("Microsoft Visual Studio 2022 Build Tools: the C++ compiler parts only "
                                         "(MSVC x64, Windows SDK, CMake, Clang). Download about 2.5 GB, about 7 GB "
                                         "on disk, 10-20 minutes. You accept Microsoft's license terms for the Build "
                                         "Tools (visualstudio.microsoft.com/license-terms)."))
            elif i == "Git.Git":
                lines.append("• " + t("Git for Windows (about 70 MB download)."))
            else:
                lines.append(f"• {i}")
        if not dialogs.ask_yes_no(
                t("Install build tools"),
                t("The build needs these free tools from their makers, installed with Windows' own installer "
                  "(winget):\n\n{tools}\n\nWindows will ask for administrator permission. A console window shows "
                  "the progress.\n\nInstall now?", tools="\n\n".join(lines)), parent=self):
            return
        cmds = [core.prereqs.install_command(i) for i in ids]

        def work():
            for c in cmds:
                try:
                    import subprocess
                    subprocess.run(c, creationflags=0x00000010)   # CREATE_NEW_CONSOLE: the player sees it
                except OSError as e:
                    self.after(0, lambda e=e: dialogs.show_error(
                        t("Install failed"), t("Could not start the installer:\n{error}\n\nIs winget (App "
                                               "Installer) available? On Windows 10 install 'App Installer' from "
                                               "the Microsoft Store.", error=e), parent=self))
                    return
            self.after(0, self.refresh_prereqs)
        threading.Thread(target=work, daemon=True).start()
        self.status.set(t("Installer running in its own window…"))

    # ------------------------------------------------------------------ build
    def start_build(self, steps=None, force_allowed=False):
        if self.build or (self.readonly and not force_allowed):
            return
        if self.game and self.game.running():
            dialogs.show_info(APP_TITLE, t("Close the game first."), parent=self)
            return
        self.refresh_inputs()
        self.error.set("")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        for s in self.step_state:
            self.step_state[s] = "pending" if (not steps or s in steps) else "skip"
            self._paint_step(s)
        self.progress["value"] = 0
        self.build = core.BuildRun(self.settings["pkg"], self.settings["rap"], self.settings.out_dir,
                                   force=self.force_var.get(), steps=steps, low_priority=self.lowprio_var.get())
        try:
            self.build.start()
        except OSError as e:
            self.build = None
            self.error.set(t("Could not start the build: {error}", error=e))
            return
        self.build_t0 = time.time()
        core.log(f"build started: steps {' '.join(steps) if steps else 'all'}, redo {self.force_var.get()}, "
                 f"low priority {self.lowprio_var.get()}, output {self.settings.out_dir}")
        set_big_state(self.build_btn, False)
        self.cancel_btn.configure(state="normal")
        self.status.set(t("Building…"))

    def cancel_build(self):
        if self.build:
            self.build.cancel()

    def _paint_step(self, s):
        st = self.step_state[s]
        style = {"running": "StepRun.TLabel", "done": "StepDone.TLabel", "skip": "StepDone.TLabel",
                 "failed": "StepFail.TLabel"}.get(st, "Step.TLabel")
        self.step_lbls[s].configure(text=f"{GLYPH[st]} {t(core.STEP_TITLES[s])}", style=style)

    def _overall(self):
        total = sum(core.STEP_WEIGHT.values())
        done = sum(core.STEP_WEIGHT[s] for s, st in self.step_state.items() if st in ("done", "skip"))
        if self.cur_step and self.step_state.get(self.cur_step) == "running":
            done += core.STEP_WEIGHT[self.cur_step] * min(self.sub, 0.98)
        return done / total

    def _append_log(self, line, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n", tag or ())
        n = int(self.log.index("end-1c").split(".")[0])
        if n > 3000:
            self.log.delete("1.0", f"{n - 3000}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_build(self):
        b = self.build
        ended = None
        for _ in range(400):
            try:
                ev, val = b.events.get_nowait()
            except Exception:
                break
            if ev == "line":
                tag = "step" if core.RE_STEP.match(val) else "err" if val.startswith("ERROR:") else None
                self._append_log(val, tag)
            elif ev == "step":
                if self.cur_step and self.step_state[self.cur_step] == "running":
                    self.step_state[self.cur_step] = "done"
                    self._paint_step(self.cur_step)
                self.cur_step, self.sub, self.step_t0 = val, 0.0, time.time()
                self.step_state[val] = "running"
                self._paint_step(val)
            elif ev == "skip" and val:
                self.step_state[val] = "skip"
                self._paint_step(val)
            elif ev == "sub":
                self.sub = val
            elif ev == "error":
                self.error.set(core.translate_message(val))
                core.log(f"build error: {val}")
            elif ev == "end":
                ended = val
        if self.cur_step and self.step_state.get(self.cur_step) == "running":
            n = core.build_game.STEPS.index(self.cur_step) + 1
            el = int(time.time() - self.step_t0)
            # a translation step that printed nothing for minutes gets a second line saying so (and what to do)
            hint = b.quiet_hint()
            self.detail.set(t("Step {n} of {total}: {title}  —  {elapsed}", n=n, total=len(core.build_game.STEPS),
                              title=t(core.STEP_TITLES[self.cur_step]), elapsed=core.clock(el))
                            + (f"  ({int(self.sub * 100)}%)" if self.sub else "") + ("\n" + hint if hint else ""))
        self.progress["value"] = int(self._overall() * 1000)
        if ended is not None:
            self._build_finished(ended)

    def _build_finished(self, code):
        el = int(time.time() - self.build_t0)
        core.log(f"build ended: exit code {code} after {el} s" + (f", {self.error.get()}" if self.error.get() else ""))
        if code == 0:
            for s, st in self.step_state.items():
                if st == "running":
                    self.step_state[s] = "done"
                self._paint_step(s)
            self.progress["value"] = 1000
            self.detail.set(t("Done in {elapsed}. Open the Play tab.", elapsed=core.clock(el)))
            self.status.set(t("Build finished."))
        else:
            if self.cur_step and self.step_state.get(self.cur_step) == "running":
                self.step_state[self.cur_step] = "failed"
                self._paint_step(self.cur_step)
            if code == -1:
                self.detail.set(t("Cancelled. BUILD GAME continues where it stopped."))
                self.error.set("")
            else:
                self.detail.set(t("The build stopped. The message below says why; build.log has the details."))
                if not self.error.get():
                    self.error.set(t("The build failed. See the log above and build.log."))
            self.status.set(t("Build stopped."))
        self.build = None
        self.cur_step = None
        set_big_state(self.build_btn, True)
        self.cancel_btn.configure(state="disabled")
        self.refresh_game_state()

    # ------------------------------------------------------------------ play
    def game_state(self):
        return getattr(self, "_game_state", {"ok": False, "text": ""})

    def refresh_game_state(self):
        def work():
            st = core.game_state(self.settings.out_dir)
            self.after(0, lambda: self._show_game_state(st))
        threading.Thread(target=work, daemon=True).start()

    def _show_game_state(self, st):
        self._game_state = st
        self.state_var.set(("✔ " if st["ok"] else "⚠ ") + st["text"])
        self.state_lbl.configure(style="ok.TLabel" if st["ok"] else "warn.TLabel")
        self._update_play_buttons()

    def _update_play_buttons(self):
        running = bool(self.game and self.game.running())
        if self.game_state().get("needs_rebuild"):
            # after an update that changes the game code: "Build the game once" (core.game_state)
            self.play_btn.configure(text=t("BUILD GAME"), command=self.build_from_play)
            set_big_state(self.play_btn, not running and not self.build)
        else:
            self.play_btn.configure(text=t("PLAY OFFLINE"), command=self.play)
            set_big_state(self.play_btn, self.game_state().get("ok") and not running)
        self.stop_btn.configure(state="normal" if running else "disabled")

    def build_from_play(self):
        self.nb.select(self.tabs["build"])
        self.start_build()

    def open_controls(self):
        """Settings -> Set up controllers...: the Controls window (controls_ui.py)."""
        if controls_ui and not self.readonly:
            controls_ui.open_dialog(self)

    def _internal_res_changed(self, save=True):
        key = self.internal_res_var.get()
        text = t(core.INTERNAL_RES_HINTS.get(key, ""))
        size = core.screen_size(core.window_center(self._hwnd()))
        if size:
            match = core.internal_res_for_screen(*size)
            text += "\n" + t("Your screen: {width} x {height}. In fullscreen, {step} matches it.",
                             width=size[0], height=size[1], step=t(core.INTERNAL_RES[match][0]))
        self.internal_res_hint.configure(text=text)
        if save:
            self.save_settings()

    def _discord_hint(self):
        text = t("\"In lobby\", \"Searching ranked\" or your match (fighters, ranked set score) with a timer, through "
                 "the Discord app on this PC. Without Discord running nothing happens.")
        try:
            from t5lobby import discord_rpc
            ready = bool(discord_rpc.load_config(self.settings).get("application_id"))
        except ImportError:
            ready = False
        if not ready:
            text += "\n" + t("This copy has no Discord application id yet, so this does nothing for now.")
        return text

    def power_saving_text(self):
        """What power saving does on this PC with the chosen setting (Settings hint, status line)."""
        key = self.power_var.get() if hasattr(self, "power_var") else self.settings["power_saving"]
        if key == "on":
            return True, t("On for this PC.")
        if key == "off":
            return False, t("Off.")
        on, why = core.power_saving_auto()
        if on:
            return True, t("Auto: on for this PC -- {reason}.", reason=t(why))
        return False, t("Auto: off for this PC (no battery, no mobile processor); the game turns it on "
                        "by itself if it runs on integrated graphics.")

    def _power_saving_changed(self, save=True):
        _on, text = self.power_saving_text()
        self.power_hint.configure(text=t(
            "No busy waiting and fewer worker threads: the processor stays cooler and keeps its speed, "
            "so the game holds 60 fps longer. The game itself is the same, online too.") + "\n" + text)
        if save:
            self.save_settings()

    def save_settings(self):
        if self.readonly:
            return
        self.settings["display"] = self.display_var.get()
        if hasattr(self, "power_var"):
            self.settings["power_saving"] = self.power_var.get()
        self.settings["internal_res"] = self.internal_res_var.get()
        self.settings["vsync"] = self.vsync_var.get()
        if hasattr(self, "stage_blur_var"):
            self.settings["stage_blur"] = self.stage_blur_var.get()
        self.settings["input_delay"] = self.input_delay_var.get()
        if hasattr(self, "training_var"):
            self.settings["training"] = self.training_var.get()
            self.settings["training_all"] = bool(self.training_all_var.get())
            self.settings["training_online"] = bool(self.training_online_var.get())
        if hasattr(self, "router_ports_var"):
            self.settings["router_ports"] = bool(self.router_ports_var.get())
        if hasattr(self, "discord_var"):
            self.settings["discord_presence"] = bool(self.discord_var.get())
        if hasattr(self, "spectators_var"):
            self.settings["spectators"] = bool(self.spectators_var.get())
            self.settings["spectators_ranked"] = bool(self.spectators_ranked_var.get())
        self.settings["mute"] = bool(self.mute_var.get())
        self.settings["background"] = bool(self.bg_var.get())
        self.settings["extra_env"] = self.env_text.get("1.0", "end").strip()
        self.settings["nickname"] = self.nick_var.get().strip()
        self.settings["low_priority"] = bool(self.lowprio_var.get())
        if hasattr(self, "unlock_stages_var"):
            self.settings["unlock_stages"] = bool(self.unlock_stages_var.get())
            self.settings["unlock_items"] = bool(self.unlock_items_var.get())
        if hasattr(self, "language_var"):
            self.settings["language"] = self.language_var.get()
        self.settings.save()

    def start_game(self, env=None):
        if self.readonly:
            return None
        self.save_settings()
        if not self.game_state().get("ok"):
            return None
        if self.game and self.game.running():
            return self.game
        g = core.GameRun(self.settings.out_dir, self.settings)
        try:
            pid = g.start(env, monitor_point=core.window_center(self._hwnd()))
        except OSError as e:
            dialogs.show_error(APP_TITLE, t("Could not start the game:\n{error}", error=e), parent=self)
            return None
        self.game = g
        core.log(f"game started: process {pid}, log {os.path.basename(g.log_path)}, settings give "
                 f"{', '.join(f'{k}={v}' for k, v in sorted(self.settings.env_overrides().items())) or 'nothing'}, "
                 f"asked for by the launcher: {', '.join(sorted(env or {})) or 'nothing'}")
        status = t("Game started (process {pid}). Log: {log}", pid=pid,
                   log="native\\logs\\" + os.path.basename(g.log_path))
        try:
            if self.power_saving_text()[0]:
                status += "  " + t("Power saving is on.")
        except Exception:       # noqa: BLE001 -- a status hint must never stop a game start
            pass
        self.status.set(status)
        self._update_play_buttons()
        return g

    def play(self):
        self.start_game()

    def _hwnd(self):
        try:
            return ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
        except (AttributeError, OSError):
            return None

    def stop_game(self):
        if self.game:
            self.game.stop()

    def open_game_log(self):
        logs = os.path.join(self.settings.out_dir, "logs")
        files = sorted(f for f in os.listdir(logs) if f.endswith(".log")) if os.path.isdir(logs) else []
        if files:
            core.open_path(os.path.join(logs, files[-1]))

    def set_status(self, text):
        self.status.set(text)

    def _log_status(self, *_):
        t = self.status.get()
        if t and t != self._last_status and not self.readonly:
            self._last_status = t
            core.log("status: " + t)

    # ------------------------------------------------------------------ report a problem
    def report_problem(self):
        """Open the 'Report a problem' window (Build and Play tab, and the Online tab after a match).
        Everything the zip needs from the launcher is read here, on the Tk thread; the window's worker
        thread only gets plain values."""
        if self.readonly:
            return None
        dlg = getattr(self, "_report_dlg", None)
        try:
            if dlg is not None and dlg.top.winfo_exists():
                dlg.top.lift()
                return dlg
        except tk.TclError:
            pass
        out = self.settings.out_dir
        labels = {"display": dict(core.DISPLAY_MODES), "internal_res": core.INTERNAL_RES_LABELS,
                  "vsync": core.VSYNC_MODES, "stage_blur": core.STAGE_BLUR_MODES,
                  "input_delay": core.INPUT_DELAYS, "power_saving": core.POWER_SAVING}
        lines = report.settings_lines(self.settings, labels, self.settings.env_overrides(), out)
        info = self.info
        build_problem = True if self.error.get() else None
        try:
            online_info = self.online.report_info()
        except Exception as e:      # noqa: BLE001 -- the report goes on without the lobby part
            online_info = f"(the Online tab could not say: {e})"
        online_dir = getattr(self.online, "user_dir", None)

        def make_context():
            return report.Context(out, root=core.ROOT, launcher_log=core.LAUNCHER_LOG, settings_lines=lines,
                                  release=info, build_info=lambda: report.build_info_for(out, info, core.ROOT),
                                  online_dir=online_dir, online_info=online_info, build_problem=build_problem)
        core.log("report window opened")
        self._report_dlg = report_ui.ReportDialog(self, make_context, core.desktop_dir(), reveal=core.reveal_file,
                                                  issues_url=core.ISSUES_URL, log=core.log)
        return self._report_dlg

    # ------------------------------------------------------------------ loop
    def _tick(self):
        if self.build:
            self._drain_build()
        if self.game:
            if self.game.running():
                el = int(time.time() - self.game.started)
                fps = f"{self.game.fps:.0f} fps" if self.game.fps else t("starting…")
                self.run_var.set(t("Running — {elapsed} — {fps}", elapsed=core.clock(el), fps=fps))
                self._run_shown = True
            elif self._run_shown:
                self._run_shown = False
                why = core.explain_exit(self.game.proc.returncode, self.game.last_lines)
                core.log(f"game ended: exit code {self.game.proc.returncode}" + (", explained to the player"
                                                                               if why else ""))
                self.run_var.set((why + " " + t("Click Report a problem.")) if why else t("The game closed."))
                self._update_play_buttons()
        self.after(150, self._tick)

    def _selected_tab(self):
        """Key of the selected tab ('build', 'play', 'settings', 'online', 'replays'), or None when no tab is selected: Tk
        sends <<NotebookTabChanged>> again while the window is taken apart, with nothing selected."""
        try:
            sel = self.nb.select()
            return self.tab_keys[self.nb.index(sel)] if sel else None
        except (tk.TclError, IndexError):
            return None

    def _on_tab(self, _e=None):
        tab = self._selected_tab()
        if tab is None:
            return
        if tab == "play":
            self.refresh_game_state()
        elif tab == "online":
            self.online.on_show()
        elif tab == "replays":
            self.replays.on_show()
        self.save_settings()

    def on_close(self):
        if self.build and not dialogs.ask_yes_no(APP_TITLE, t("A build is running. Stop it and quit?"), parent=self):
            return
        if controls_ui and not controls_ui.close_for_app(self):
            return                              # unsaved button changes: the person chose to stay
        if self.build:
            self.build.cancel()
        self.save_settings()
        self.nb.unbind("<<NotebookTabChanged>>")          # (destroying the tabs would fire it with none selected)
        self.online.on_close()
        self.destroy()


App.set_big_state = staticmethod(set_big_state)     # (the Replays tab greys its WATCH button the same way)


# ---------------------------------------------------------------------- docs screenshots

def capture_window(widget, path):
    """PNG of the launcher window via PrintWindow (the window must be on screen; it may be transparent)."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    widget.update()
    hwnd = user32.GetParent(widget.winfo_id()) or widget.winfo_id()

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.r - r.l, r.b - r.t
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)              # PW_RENDERFULLCONTENT

    class BMI(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("w", ctypes.c_int32), ("h", ctypes.c_int32),
                    ("planes", ctypes.c_uint16), ("bits", ctypes.c_uint16), ("comp", ctypes.c_uint32),
                    ("img", ctypes.c_uint32), ("xppm", ctypes.c_int32), ("yppm", ctypes.c_int32),
                    ("used", ctypes.c_uint32), ("imp", ctypes.c_uint32)]
    bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    write_png(path, w, h, buf.raw)


def write_png(path, w, h, bgra):
    """Minimal PNG writer (the release's Python has no Pillow)."""
    import struct
    import zlib
    rows = bytearray()
    for y in range(h):
        row = bgra[y * w * 4:(y + 1) * w * 4]
        rgb = bytearray(w * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
        rows += b"\x00" + rgb

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))


def screenshots(app, outdir, prefix="launcher", build_steps=None, play_seconds=0):
    """Docs/test mode (the window is invisible, see App.__init__).
    No options: one PNG per tab. build_steps: run that build, capture the Build tab whenever a
    step starts and at the end. play_seconds: start the game minimized (no focus), capture the
    Play tab while it runs, stop it."""
    os.makedirs(outdir, exist_ok=True)
    app.after(30 * 60 * 1000, app.destroy)            # never outlive a test run

    def cap(name):
        try:
            capture_window(app, os.path.join(outdir, f"{prefix}_{name}.png"))
        except Exception as e:                           # a failed capture must not keep the app open
            print(f"capture {name} failed: {e}", file=sys.stderr)

    def finish_with_play():
        if not play_seconds:
            app.destroy()
            return
        app.nb.select(1)
        app.settings["background"] = True
        app.readonly = False
        g = app.start_game()
        app.readonly = True
        if not g:
            cap("play_failed")
            app.after(1000, app.destroy)
            return
        app.after(play_seconds * 1000, lambda: cap("play_running"))
        app.after(play_seconds * 1000 + 500, lambda: app.stop_game())
        app.after(play_seconds * 1000 + 3500, lambda: (cap("play_stopped"), app.destroy()))

    if not build_steps:
        seq = [("build", 0), ("play", 1), ("settings", 2), ("online", 3)]

        def shot(i=0):
            if i >= len(seq):
                finish_with_play()
                return
            name, idx = seq[i]
            app.nb.select(idx)
            app.after(1500, lambda: (cap(name), shot(i + 1)))
        app.after(2500, shot)
        return

    seen = set()

    def watch():
        if app.cur_step and app.cur_step not in seen:
            seen.add(app.cur_step)
            app.after(2500, lambda s=app.cur_step: cap(f"build_{s}"))
        if app.build is None and getattr(app, "build_t0", None):
            app.after(1000, lambda: cap("build_end"))
            app.after(2000, lambda: app.nb.select(1))
            app.after(4500, lambda: (cap("play_after_build"), finish_with_play()))
            return
        app.after(200, watch)
    app.after(1500, lambda: (app.start_build(build_steps, force_allowed=True), watch()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshots", metavar="DIR", help="save a PNG of each tab into DIR and exit")
    ap.add_argument("--prefix", default="launcher")
    ap.add_argument("--build-steps", nargs="+", help="(testing) start a build of these steps right away")
    ap.add_argument("--low-priority", action="store_true", help="(testing) build at below-normal priority")
    ap.add_argument("--play-seconds", type=int, default=0, help="(testing, with --screenshots) run the game this long")
    ap.add_argument("--force", action="store_true", help="(testing) tick 'Redo every step'")
    a = ap.parse_args()
    enable_dpi_awareness()
    app = App(offscreen=bool(a.screenshots))
    if a.low_priority:
        app.lowprio_var.set(True)
    if a.force:
        app.force_var.set(True)
    if a.screenshots:
        screenshots(app, a.screenshots, a.prefix, a.build_steps, a.play_seconds)
    elif a.build_steps:
        app.after(800, lambda: app.start_build(a.build_steps))
    app.mainloop()
    if app.restart_requested:
        subprocess.Popen([sys.executable] + sys.argv, cwd=os.getcwd())


if __name__ == "__main__":
    main()
