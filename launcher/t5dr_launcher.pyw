"""T5DR Online launcher: build the game from your own copy, then play.

    pythonw launcher/t5dr_launcher.pyw            (the release starts it through "T5DR Online.exe")
    python  launcher/t5dr_launcher.pyw --screenshots DIR   (docs: save a PNG of every tab, then exit)

Tabs: Build (choose .pkg + .rap, check the build tools, BUILD GAME with live
progress and log), Play, Settings, Online (placeholder; see online.py).
"""
import argparse
import ctypes
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core    # noqa: E402
import online  # noqa: E402

APP_TITLE = "T5DR Online"
COLORS = {"ok": "#1a7f37", "warn": "#9a6700", "error": "#cf222e", "muted": "#57606a",
          "accent": "#0b5cad", "accent_hover": "#094a8c", "log_bg": "#0d1117", "log_fg": "#c9d1d9"}
GLYPH = {"pending": "○", "running": "◔", "done": "✔", "skip": "✔", "failed": "✖"}

CONTROLS = [
    # action, PS3, keyboard, Xbox controller
    ("Left punch (1)", "Square", "A", "X"),
    ("Right punch (2)", "Triangle", "S", "Y"),
    ("Left kick (3)", "Cross", "Z", "A"),
    ("Right kick (4)", "Circle", "X", "B"),
    ("Move / menus", "D-pad, left stick", "Arrow keys", "D-pad, left stick"),
    ("L1 / R1", "L1 / R1", "Q / W", "LB / RB"),
    ("L2 / R2", "L2 / R2", "1 / 2", "LT / RT"),
    ("Start / pause", "START", "Enter", "Start"),
    ("Select", "SELECT", "Tab", "Back"),
    ("Quit the game", "", "Esc", ""),
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
    def __init__(self, offscreen=False):
        super().__init__()
        self.readonly = offscreen
        self.settings = core.Settings()
        self.info = core.release_info()
        self.build = None
        self.game = None
        self.step_state = {s: "pending" for s in core.build_game.STEPS}
        self.step_t0 = None
        self.cur_step = None
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
                  text=f"   native Windows build  ·  launcher {self.info.get('version', '?')}").pack(side="left")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(4, 0))
        self.tabs = {}
        for key, label in (("build", "  Build  "), ("play", "  Play  "), ("settings", "  Settings  "),
                           ("online", "  Online  ")):
            f = ttk.Frame(self.nb)
            self.nb.add(f, text=label)
            self.tabs[key] = f
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
                  text=f"Output: {self.settings.out_dir}").pack(side="right")

    def _build_tab(self, tab):
        tab.columnconfigure(0, weight=1)
        # your files
        files = ttk.LabelFrame(tab, text="  Your game  ", padding=(12, 6))
        files.grid(row=0, column=0, sticky="we", padx=8, pady=(8, 4))
        files.columnconfigure(1, weight=1)
        self.pkg_var = tk.StringVar(value=self.settings["pkg"])
        self.rap_var = tk.StringVar(value=self.settings["rap"])
        self.pkg_info, self.rap_info = tk.StringVar(), tk.StringVar()
        self.pkg_lbl = self.rap_lbl = None
        for row, (label, var, info, kind) in enumerate((
                ("Package (.pkg)", self.pkg_var, self.pkg_info, "pkg"),
                ("License (.rap)", self.rap_var, self.rap_info, "rap"))):
            ttk.Label(files, text=label).grid(row=row * 2, column=0, sticky="w", padx=(0, 8))
            e = ttk.Entry(files, textvariable=var)
            e.grid(row=row * 2, column=1, sticky="we")
            e.bind("<FocusOut>", lambda _e: self.refresh_inputs())
            ttk.Button(files, text="Browse…", command=lambda k=kind: self.browse(k)).grid(
                row=row * 2, column=2, padx=(8, 0))
            lbl = ttk.Label(files, textvariable=info, style="Muted.TLabel")
            lbl.grid(row=row * 2 + 1, column=1, columnspan=2, sticky="w", pady=(0, 4))
            if kind == "pkg":
                self.pkg_lbl = lbl
            else:
                self.rap_lbl = lbl
        ttk.Label(files, style="Muted.TLabel", wraplength=820, justify="left", text=(
            "Supported: Tekken 5: Dark Resurrection Online, PS3 PSN (US), NPUB30009 version 01.00 -- the package "
            "file and the license (.rap) from your own account. Nothing leaves this PC.")).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # build tools
        tools = ttk.LabelFrame(tab, text="  Build tools on this PC  ", padding=(12, 6))
        tools.grid(row=1, column=0, sticky="we", padx=8, pady=4)
        tools.columnconfigure(0, weight=1)
        self.tools_tv = ttk.Treeview(tools, columns=("state", "detail"), show="tree headings", height=7,
                                     selectmode="none")
        self.tools_tv.heading("#0", text="Needed")
        self.tools_tv.heading("state", text="")
        self.tools_tv.heading("detail", text="Found")
        self.tools_tv.column("#0", width=230, stretch=False)
        self.tools_tv.column("state", width=70, stretch=False, anchor="center")
        self.tools_tv.column("detail", width=520)
        self.tools_tv.tag_configure("bad", foreground=COLORS["error"])
        self.tools_tv.tag_configure("good", foreground="#24292f")
        self.tools_sum = tk.StringVar(value="Checking…")
        self.tools_sum_lbl = ttk.Label(tools, textvariable=self.tools_sum)
        self.tools_sum_lbl.grid(row=0, column=0, sticky="w")
        btns = ttk.Frame(tools)
        btns.grid(row=0, column=1, sticky="e")
        self.details_btn = ttk.Button(btns, text="Details", command=self.toggle_tools)
        self.details_btn.pack(side="left")
        ttk.Button(btns, text="Check again", command=self.refresh_prereqs).pack(side="left", padx=(8, 0))
        self.install_btn = ttk.Button(btns, text="Install missing…", command=self.install_missing)
        self.install_btn.pack(side="left", padx=(8, 0))
        self.tools_shown = False

        # build
        b = ttk.LabelFrame(tab, text="  Build  ", padding=(12, 6))
        b.grid(row=2, column=0, sticky="we", padx=8, pady=4)
        b.columnconfigure(0, weight=1)
        strip = ttk.Frame(b)
        strip.grid(row=0, column=0, columnspan=3, sticky="w")
        self.step_lbls = {}
        for i, s in enumerate(core.build_game.STEPS):
            lbl = ttk.Label(strip, text=f"{GLYPH['pending']} {core.STEP_TITLES[s]}", style="Step.TLabel")
            lbl.grid(row=0, column=i)
            self.step_lbls[s] = lbl
        self.progress = ttk.Progressbar(b, maximum=1000)
        self.progress.grid(row=1, column=0, columnspan=3, sticky="we", pady=(6, 2))
        self.detail = tk.StringVar(value="Press BUILD GAME. It takes a few minutes; the game data stays in this folder.")
        ttk.Label(b, textvariable=self.detail, style="Muted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w")
        row = ttk.Frame(b)
        row.grid(row=3, column=0, columnspan=3, sticky="we", pady=(8, 2))
        self.build_btn = self.big_button(row, "BUILD GAME", self.start_build)
        self.build_btn.pack(side="left")
        self.cancel_btn = ttk.Button(row, text="Cancel", command=self.cancel_build, state="disabled")
        self.cancel_btn.pack(side="left", padx=8)
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Redo every step", variable=self.force_var).pack(side="left", padx=8)
        self.lowprio_var = tk.BooleanVar(value=self.settings["low_priority"])
        ttk.Checkbutton(row, text="Keep the PC responsive (slower)", variable=self.lowprio_var,
                        command=self.save_settings).pack(side="left", padx=8)
        ttk.Button(row, text="Open build.log",
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
        ttk.Label(box, text="Play", style="H1.TLabel").pack(anchor="w")
        self.state_var = tk.StringVar(value="Checking the build…")
        self.state_lbl = ttk.Label(box, textvariable=self.state_var, wraplength=820, justify="left")
        self.state_lbl.pack(anchor="w", pady=(6, 14))
        nick = ttk.Frame(box)
        nick.pack(anchor="w", pady=(0, 14))
        ttk.Label(nick, text="Your name (shown in the game)").pack(side="left")
        self.nick_var = tk.StringVar(value=self.settings["nickname"])
        ttk.Entry(nick, textvariable=self.nick_var, width=20).pack(side="left", padx=8)
        row = ttk.Frame(box)
        row.pack(anchor="w")
        self.play_btn = self.big_button(row, "PLAY", self.play)
        self.play_btn.pack(side="left")
        self.stop_btn = ttk.Button(row, text="Stop game", command=self.stop_game, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        self.run_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.run_var, style="H2.TLabel").pack(anchor="w", pady=(14, 4))
        links = ttk.Frame(box)
        links.pack(anchor="w", pady=(4, 0))
        ttk.Button(links, text="Open newest game log", command=self.open_game_log).pack(side="left")
        ttk.Button(links, text="Open saves folder",
                   command=lambda: core.open_path(os.path.join(self.settings.out_dir, "gamedata"))).pack(
            side="left", padx=8)
        ttk.Label(box, style="Muted.TLabel", wraplength=820, justify="left", text=(
            "The game opens in its own window (DirectX 12). Keyboard and Xbox-style controllers both work; "
            "see Settings for the keys. Esc closes the game. START skips the intro movie.")).pack(
            anchor="w", pady=(22, 0))

    def _settings_tab(self, tab):
        box = ttk.Frame(tab, padding=(24, 16))
        box.pack(fill="both", expand=True)
        disp = ttk.LabelFrame(box, text="  Display  ", padding=(12, 6))
        disp.grid(row=0, column=0, sticky="nwe", padx=(0, 12))
        self.display_var = tk.StringVar(value=self.settings["display"])
        for key, label in core.DISPLAY_MODES:
            ttk.Radiobutton(disp, text=label, value=key, variable=self.display_var,
                            command=self.save_settings).pack(anchor="w", pady=1)
        ttk.Label(disp, style="Muted.TLabel", wraplength=300, justify="left", text=(
            "The game renders at 1280 x 720 and is scaled to the window. You can also drag the window's "
            "edges. The runtime has no exclusive fullscreen yet.")).pack(anchor="w", pady=(6, 0))

        other = ttk.LabelFrame(box, text="  Sound and start  ", padding=(12, 6))
        other.grid(row=0, column=1, sticky="nwe")
        self.mute_var = tk.BooleanVar(value=self.settings["mute"])
        self.bg_var = tk.BooleanVar(value=self.settings["background"])
        ttk.Checkbutton(other, text="Mute sound", variable=self.mute_var, command=self.save_settings).pack(anchor="w")
        ttk.Checkbutton(other, text="Start minimized, without taking focus (for testing)", variable=self.bg_var,
                        command=self.save_settings).pack(anchor="w", pady=(4, 0))
        ttk.Label(other, text="Advanced: extra settings, one NAME=VALUE per line").pack(anchor="w", pady=(10, 2))
        self.env_text = tk.Text(other, height=4, width=44, font=("Consolas", 9))
        self.env_text.insert("1.0", self.settings["extra_env"])
        self.env_text.pack(anchor="w", fill="x")
        self.env_text.bind("<FocusOut>", lambda _e: self.save_settings())

        ctl = ttk.LabelFrame(box, text="  Controls  ", padding=(12, 6))
        ctl.grid(row=1, column=0, columnspan=2, sticky="nwe", pady=(14, 0))
        tv = ttk.Treeview(ctl, columns=("ps3", "kb", "pad"), show="tree headings", height=len(CONTROLS),
                          selectmode="none")
        tv.heading("#0", text="Action (Tekken default)")
        tv.heading("ps3", text="PS3 button")
        tv.heading("kb", text="Keyboard")
        tv.heading("pad", text="Xbox controller")
        tv.column("#0", width=210, stretch=False)
        for c in ("ps3", "kb", "pad"):
            tv.column(c, width=190)
        for a, p, k, x in CONTROLS:
            tv.insert("", "end", text=a, values=(p, k, x))
        tv.pack(fill="x")
        ttk.Label(ctl, style="Muted.TLabel", wraplength=860, justify="left", text=(
            "Keyboard and the first XInput controller both drive player 1 (they are combined). The keyboard "
            "only counts while the game window has focus. Button layout inside the game can be changed in its "
            "own Options menu.")).pack(anchor="w", pady=(6, 0))
        box.columnconfigure(0, weight=1)
        box.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------ inputs
    def browse(self, kind):
        if kind == "pkg":
            p = filedialog.askopenfilename(title="Choose your Tekken 5 DR Online package",
                                           filetypes=[("PS3 package", "*.pkg"), ("All files", "*.*")])
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
            p = filedialog.askopenfilename(title="Choose your license (.rap)",
                                           filetypes=[("PS3 license", "*.rap"), ("All files", "*.*")])
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
        self.status.set("Checking build tools…")

        def work():
            items = core.prereqs.check()
            self.after(0, lambda: self._show_prereqs(items))
        threading.Thread(target=work, daemon=True).start()

    def _show_prereqs(self, items):
        self.prereq_items = items
        self.tools_tv.delete(*self.tools_tv.get_children())
        for it in items:
            self.tools_tv.insert("", "end", text=it["name"],
                                 values=("✔ ok" if it["ok"] else "✖ missing", it["detail"]),
                                 tags=("good" if it["ok"] else "bad",))
        missing = [it for it in items if not it["ok"]]
        self.install_btn.configure(state="normal" if any(it["install"] for it in missing) else "disabled")
        if missing:
            self.tools_sum.set("✖ Missing: " + ", ".join(it["name"] for it in missing))
            self.tools_sum_lbl.configure(style="error.TLabel")
            self.toggle_tools(True)
        else:
            self.tools_sum.set("✔ Everything the build needs is installed.")
            self.tools_sum_lbl.configure(style="ok.TLabel")
        self.status.set("All build tools found." if not missing else
                        f"{len(missing)} build tool(s) missing -- click 'Install missing…'.")

    def toggle_tools(self, show=None):
        self.tools_shown = (not self.tools_shown) if show is None else show
        if self.tools_shown:
            self.tools_tv.grid(row=1, column=0, columnspan=2, sticky="we", pady=(6, 0))
            self.details_btn.configure(text="Hide details")
        else:
            self.tools_tv.grid_remove()
            self.details_btn.configure(text="Details")

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
                lines.append("• Microsoft Visual Studio 2022 Build Tools: the C++ compiler parts only "
                             "(MSVC x64, Windows SDK, CMake, Clang). Download about 2.5 GB, about 7 GB on disk, "
                             "10-20 minutes. You accept Microsoft's license terms for the Build Tools "
                             "(visualstudio.microsoft.com/license-terms).")
            elif i == "Git.Git":
                lines.append("• Git for Windows (about 70 MB download).")
            else:
                lines.append(f"• {i}")
        if not messagebox.askyesno(
                "Install build tools",
                "The build needs these free tools from their makers, installed with Windows' own installer "
                "(winget):\n\n" + "\n\n".join(lines) +
                "\n\nWindows will ask for administrator permission. A console window shows the progress.\n\n"
                "Install now?", icon="question"):
            return
        cmds = [core.prereqs.install_command(i) for i in ids]

        def work():
            for c in cmds:
                try:
                    import subprocess
                    subprocess.run(c, creationflags=0x00000010)   # CREATE_NEW_CONSOLE: the player sees it
                except OSError as e:
                    self.after(0, lambda e=e: messagebox.showerror(
                        "Install failed", f"Could not start the installer:\n{e}\n\nIs winget (App Installer) "
                        "available? On Windows 10 install 'App Installer' from the Microsoft Store."))
                    return
            self.after(0, self.refresh_prereqs)
        threading.Thread(target=work, daemon=True).start()
        self.status.set("Installer running in its own window…")

    # ------------------------------------------------------------------ build
    def start_build(self, steps=None, force_allowed=False):
        if self.build or (self.readonly and not force_allowed):
            return
        if self.game and self.game.running():
            messagebox.showinfo(APP_TITLE, "Close the game first.")
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
            self.error.set(f"Could not start the build: {e}")
            return
        self.build_t0 = time.time()
        set_big_state(self.build_btn, False)
        self.cancel_btn.configure(state="normal")
        self.status.set("Building…")

    def cancel_build(self):
        if self.build:
            self.build.cancel()

    def _paint_step(self, s):
        st = self.step_state[s]
        style = {"running": "StepRun.TLabel", "done": "StepDone.TLabel", "skip": "StepDone.TLabel",
                 "failed": "StepFail.TLabel"}.get(st, "Step.TLabel")
        self.step_lbls[s].configure(text=f"{GLYPH[st]} {core.STEP_TITLES[s]}", style=style)

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
                self.error.set(val)
            elif ev == "end":
                ended = val
        if self.cur_step and self.step_state.get(self.cur_step) == "running":
            n = core.build_game.STEPS.index(self.cur_step) + 1
            el = int(time.time() - self.step_t0)
            self.detail.set(f"Step {n} of {len(core.build_game.STEPS)}: {core.STEP_TITLES[self.cur_step]}"
                            f"  —  {el // 60}:{el % 60:02d}"
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
            self.detail.set(f"Done in {el // 60}:{el % 60:02d}. Open the Play tab.")
            self.status.set("Build finished.")
        else:
            if self.cur_step and self.step_state.get(self.cur_step) == "running":
                self.step_state[self.cur_step] = "failed"
                self._paint_step(self.cur_step)
            if code == -1:
                self.detail.set("Cancelled. BUILD GAME continues where it stopped.")
                self.error.set("")
            else:
                self.detail.set("The build stopped. The message below says why; build.log has the details.")
                if not self.error.get():
                    self.error.set("The build failed. See the log above and build.log.")
            self.status.set("Build stopped.")
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
        self.settings["mute"] = bool(self.mute_var.get())
        self.settings["background"] = bool(self.bg_var.get())
        self.settings["extra_env"] = self.env_text.get("1.0", "end").strip()
        self.settings["nickname"] = self.nick_var.get().strip()
        self.settings["low_priority"] = bool(self.lowprio_var.get())
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
            pid = g.start(env)
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"Could not start the game:\n{e}")
            return None
        self.game = g
        self.status.set(f"Game started (process {pid}). Log: native\\logs\\{os.path.basename(g.log_path)}")
        self._update_play_buttons()
        return g

    def play(self):
        self.start_game()

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
                fps = f"{self.game.fps:.0f} fps" if self.game.fps else "starting…"
                self.run_var.set(f"Running — {el // 60}:{el % 60:02d} — {fps}")
            elif self.run_var.get().startswith("Running"):
                code = self.game.proc.returncode
                crashed = any("[CRASH]" in l for l in self.game.last_lines[-50:])
                self.run_var.set("The game closed." if code == 0 and not crashed else
                                 f"The game stopped (exit code {code}){' after a crash' if crashed else ''}. "
                                 "The game log has the details.")
                self._update_play_buttons()
        self.after(150, self._tick)

    def _on_tab(self, _e=None):
        tab = self.nb.tab(self.nb.select(), "text").strip()
        if tab == "Play":
            self.refresh_game_state()
        elif tab == "Online":
            self.online.on_show()
        self.save_settings()

    def on_close(self):
        if self.build and not messagebox.askyesno(APP_TITLE, "A build is running. Stop it and quit?"):
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


if __name__ == "__main__":
    main()
