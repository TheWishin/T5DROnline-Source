"""T5DR Online launcher: build the game from your own copy, then play.

    pythonw launcher/t5dr_launcher.pyw            (the release starts it through "T5DR Online.exe")
    python  launcher/t5dr_launcher.pyw --screenshots DIR   (docs: save a PNG of every tab, then exit)

Tabs: Build (choose .pkg + .rap, check the build tools, BUILD GAME with live
progress and log), Play, Settings, Online (placeholder; see online.py).
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
import core    # noqa: E402
import online  # noqa: E402
from core import N_, t  # noqa: E402  (English text in, the player's language out; lobby/t5lobby/i18n.py)

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
    btn.configure(state="normal" if enabled else "disabled",
                  bg=COLORS["accent"] if enabled else "#aab4c0", cursor="hand2" if enabled else "arrow")


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

    def big_button(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, font=("Segoe UI", 13, "bold"), fg="white",
                      bg=COLORS["accent"], activebackground=COLORS["accent_hover"], activeforeground="white",
                      relief="flat", padx=28, pady=8, cursor="hand2", disabledforeground="#c8d1dc")
        return b

    # ------------------------------------------------------------------ layout
    def _layout(self):
        head = ttk.Frame(self, padding=(16, 12, 16, 4))
        head.pack(fill="x")
        ttk.Label(head, text="Tekken 5: Dark Resurrection Online", style="H1.TLabel").pack(side="left")
        ttk.Label(head, style="Muted.TLabel",
                  text="   " + t("native Windows build  ·  launcher {version}",
                                 version=self.info.get("version", "?"))).pack(side="left")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(4, 0))
        self.tabs = {}
        for key, label in (("build", t("Build")), ("play", t("Play")), ("settings", t("Settings")),
                           ("online", t("Online"))):
            f = ttk.Frame(self.nb)
            self.nb.add(f, text=f"  {label}  ")
            self.tabs[key] = f
        self.tab_keys = list(self.tabs)
        self._build_tab(self.tabs["build"])
        self._play_tab(self.tabs["play"])
        self._settings_tab(self.tabs["settings"])
        self.online = online.OnlineTab(self.tabs["online"], self)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab)
        self.status = tk.StringVar(value="")
        bar = ttk.Frame(self, padding=(16, 4))
        bar.pack(fill="x")
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
        self.tools_tv.column("#0", width=230, stretch=False)
        self.tools_tv.column("state", width=70, stretch=False, anchor="center")
        self.tools_tv.column("detail", width=520)
        self.tools_tv.tag_configure("bad", foreground=COLORS["error"])
        self.tools_tv.tag_configure("good", foreground="#24292f")
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
        ttk.Label(b, textvariable=self.detail, style="Muted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w")
        row = ttk.Frame(b)
        row.grid(row=3, column=0, columnspan=3, sticky="we", pady=(8, 2))
        self.build_btn = self.big_button(row, t("BUILD GAME"), self.start_build)
        self.build_btn.pack(side="left")
        self.cancel_btn = ttk.Button(row, text=t("Cancel"), command=self.cancel_build, state="disabled")
        self.cancel_btn.pack(side="left", padx=8)
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text=t("Redo every step"), variable=self.force_var).pack(side="left", padx=8)
        self.lowprio_var = tk.BooleanVar(value=self.settings["low_priority"])
        ttk.Checkbutton(row, text=t("Keep the PC responsive (slower)"), variable=self.lowprio_var,
                        command=self.save_settings).pack(side="left", padx=8)
        ttk.Button(row, text=t("Open build.log"),
                   command=lambda: core.open_path(os.path.join(self.settings.out_dir, "build.log"))).pack(side="right")
        self.error = tk.StringVar()
        self.error_lbl = tk.Label(b, textvariable=self.error, fg=COLORS["error"], wraplength=860, justify="left",
                                  font=("Segoe UI", 10, "bold"))
        self.error_lbl.grid(row=4, column=0, columnspan=3, sticky="w")

        # log
        tab.rowconfigure(3, weight=1)
        self.log = ScrolledText(tab, height=8, font=("Consolas", 9), bg=COLORS["log_bg"], fg=COLORS["log_fg"],
                                insertbackground=COLORS["log_fg"], relief="flat", state="disabled", wrap="none")
        self.log.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.log.tag_configure("step", foreground="#58a6ff")
        self.log.tag_configure("err", foreground="#ff7b72")

    def _play_tab(self, tab):
        box = ttk.Frame(tab, padding=24)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=t("Play"), style="H1.TLabel").pack(anchor="w")
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
        self.play_btn = self.big_button(row, t("PLAY"), self.play)
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
        ttk.Label(box, style="Muted.TLabel", wraplength=820, justify="left", text=t(
            "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers both work; "
            "see Settings for the keys. Esc closes the game. START skips the intro movie.")).pack(
            anchor="w", pady=(22, 0))

    def _settings_tab(self, tab):
        box = ttk.Frame(tab, padding=(24, 16))
        box.pack(fill="both", expand=True)
        disp = ttk.LabelFrame(box, text="  " + t("Display") + "  ", padding=(12, 6))
        disp.grid(row=0, column=0, sticky="nwe", padx=(0, 12))
        self.display_var = tk.StringVar(value=self.settings["display"])
        for key, label in core.DISPLAY_MODES:
            ttk.Radiobutton(disp, text=t(label), value=key, variable=self.display_var,
                            command=self.save_settings).pack(anchor="w", pady=1)
        ttk.Label(disp, style="Muted.TLabel", wraplength=300, justify="left", text=t(
            "The game renders at 1280 x 720 and is scaled to the window. You can also drag the window's "
            "edges. The runtime has no exclusive fullscreen yet.")).pack(anchor="w", pady=(6, 0))

        right = ttk.Frame(box)
        right.grid(row=0, column=1, sticky="nwe")
        if core.I18N:
            self._language_box(right)
        other = ttk.LabelFrame(right, text="  " + t("Sound and start") + "  ", padding=(12, 6))
        other.pack(fill="x")
        self.mute_var = tk.BooleanVar(value=self.settings["mute"])
        self.bg_var = tk.BooleanVar(value=self.settings["background"])
        ttk.Checkbutton(other, text=t("Mute sound"), variable=self.mute_var, command=self.save_settings).pack(anchor="w")
        ttk.Checkbutton(other, text=t("Start minimized, without taking focus (for testing)"), variable=self.bg_var,
                        command=self.save_settings).pack(anchor="w", pady=(4, 0))
        ttk.Label(other, text=t("Advanced: extra settings, one NAME=VALUE per line")).pack(anchor="w", pady=(10, 2))
        self.env_text = tk.Text(other, height=3, width=44, font=("Consolas", 9))
        self.env_text.insert("1.0", self.settings["extra_env"])
        self.env_text.pack(anchor="w", fill="x")
        self.env_text.bind("<FocusOut>", lambda _e: self.save_settings())

        # Like Tekken 6 Native Online's "3D resolution": for weaker graphics cards
        # (PS3_RENDER_SCALE, docs/RENDER_PERF.md "Weaker PCs").
        gfx = ttk.LabelFrame(right, text="  " + t("3D resolution") + "  ", padding=(12, 6))
        gfx.pack(fill="x", pady=(6, 0))
        self.render_scale_var = tk.StringVar(value=self.settings["render_scale"]
                                             if self.settings["render_scale"] in core.RENDER_SCALES else "1")
        row = ttk.Frame(gfx)
        row.pack(anchor="w")
        for key, label in core.RENDER_SCALES.items():
            ttk.Radiobutton(row, text=t(label), value=key, variable=self.render_scale_var,
                            command=self.save_settings).pack(side="left", padx=(0, 14))
        ttk.Label(row, style="Muted.TLabel", text=t("for weak graphics cards")).pack(side="left")

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

        ctl = ttk.LabelFrame(box, text="  " + t("Controls") + "  ", padding=(12, 6))
        ctl.grid(row=1, column=0, columnspan=2, sticky="nwe", pady=(14, 0))
        tv = ttk.Treeview(ctl, columns=("ps3", "kb", "pad"), show="tree headings", height=len(CONTROLS),
                          selectmode="none")
        tv.heading("#0", text=t("Action (Tekken default)"))
        tv.heading("ps3", text=t("PS3 button"))
        tv.heading("kb", text=t("Keyboard"))
        tv.heading("pad", text=t("Xbox controller"))
        tv.column("#0", width=210, stretch=False)
        for c in ("ps3", "kb", "pad"):
            tv.column(c, width=190)
        for a, p, k, x in CONTROLS:
            tv.insert("", "end", text=t(a), values=(t(p), t(k), t(x)))
        tv.pack(fill="x")
        ttk.Label(ctl, style="Muted.TLabel", wraplength=860, justify="left", text=t(
            "Keyboard and the first XInput controller both drive player 1 (they are combined). The keyboard "
            "only counts while the game window has focus. Button layout inside the game can be changed in its "
            "own Options menu.")).pack(anchor="w", pady=(6, 0))
        ttk.Label(ctl, style="Muted.TLabel", wraplength=860, justify="left", text=t(
            "In this window, on the Online tab, a controller or arcade stick works without mouse or keyboard: "
            "Cross / A accepts a match or rematch and starts a search, Circle / B declines, leaves or stops the "
            "search. It only counts while this window is in front, and only after the button was let go for a "
            "moment. Which stick button is Cross follows your controls.ini.")).pack(anchor="w", pady=(4, 0))
        box.columnconfigure(0, weight=1)
        box.columnconfigure(1, weight=1)

    def _language_box(self, right):
        """Auto / Deutsch / English. The texts are built once, so a change applies after a restart."""
        lang = ttk.LabelFrame(right, text="  " + t("Language") + "  ", padding=(12, 6))
        lang.pack(fill="x", pady=(0, 6))
        self.language_choice = self.settings["language"]         # what this run was started with
        self.language_var = tk.StringVar(value=self.language_choice)
        row = ttk.Frame(lang)
        row.pack(anchor="w")
        for key, label in core.LANGUAGE_CHOICES:
            ttk.Radiobutton(row, text=t(label), value=key, variable=self.language_var,
                            command=self.language_changed).pack(side="left", padx=(0, 14))
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
            elif ev == "end":
                ended = val
        if self.cur_step and self.step_state.get(self.cur_step) == "running":
            n = core.build_game.STEPS.index(self.cur_step) + 1
            el = int(time.time() - self.step_t0)
            self.detail.set(t("Step {n} of {total}: {title}  —  {elapsed}", n=n, total=len(core.build_game.STEPS),
                              title=t(core.STEP_TITLES[self.cur_step]), elapsed=core.clock(el))
                            + (f"  ({int(self.sub * 100)}%)" if self.sub else ""))
        self.progress["value"] = int(self._overall() * 1000)
        if ended is not None:
            self._build_finished(ended)

    def _build_finished(self, code):
        el = int(time.time() - self.build_t0)
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
        set_big_state(self.play_btn, self.game_state().get("ok") and not running)
        self.stop_btn.configure(state="normal" if running else "disabled")

    def save_settings(self):
        if self.readonly:
            return
        self.settings["display"] = self.display_var.get()
        self.settings["render_scale"] = self.render_scale_var.get()
        self.settings["input_delay"] = self.input_delay_var.get()
        self.settings["mute"] = bool(self.mute_var.get())
        self.settings["background"] = bool(self.bg_var.get())
        self.settings["extra_env"] = self.env_text.get("1.0", "end").strip()
        self.settings["nickname"] = self.nick_var.get().strip()
        self.settings["low_priority"] = bool(self.lowprio_var.get())
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
        self.status.set(t("Game started (process {pid}). Log: {log}", pid=pid,
                          log="native\\logs\\" + os.path.basename(g.log_path)))
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
                self.run_var.set(why or t("The game closed."))
                self._update_play_buttons()
        self.after(150, self._tick)

    def _on_tab(self, _e=None):
        tab = self.tab_keys[self.nb.index(self.nb.select())]
        if tab == "play":
            self.refresh_game_state()
        elif tab == "online":
            self.online.on_show()
        self.save_settings()

    def on_close(self):
        if self.build and not dialogs.ask_yes_no(APP_TITLE, t("A build is running. Stop it and quit?"), parent=self):
            return
        if self.build:
            self.build.cancel()
        self.save_settings()
        self.online.on_close()
        self.destroy()


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
