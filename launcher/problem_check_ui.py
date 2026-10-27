"""The 'Check my problem' window (1.1.5): problem_check.py's findings in the player's language, each with what was
found, how to fix it and a link to the help; nothing found -> a pointer to 'Report a problem'.

    open_for(app)       the launcher's buttons (Build and Play tab)
    CheckDialog(parent, out_dir, report=None, visible=True, facts=None, fw=None)

The check runs on a worker thread (the firewall look asks netsh, a second or two); the window shows "Looking..."
until it is back. Nothing is changed and nothing is sent.
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

import problem_check as pc

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lobby"))
try:
    from t5lobby import i18n
    from t5lobby.i18n import t
except ImportError:     # lobby/ is missing from this copy: English only
    i18n = None

    def t(text, /, **values):
        return text.format(**values) if values else text


def _work(q, out_dir, facts, fw):
    try:
        q.put(("ok", pc.check(out_dir, facts, fw)))
    except Exception as e:      # noqa: BLE001 -- shown in the window
        q.put(("err", e))


class CheckDialog:
    WRAP = 600

    def __init__(self, parent, out_dir, report=None, visible=True, facts=None, fw=None, open_url=None, themed=None):
        self.parent = parent
        self.out_dir = out_dir
        self.report = report
        self.facts, self.fw = facts, fw
        self.open_url = open_url or self._browser
        self.themed = bool(getattr(parent, "theme", None)) if themed is None else themed
        self.findings = None
        self.error = None
        self.q = queue.Queue()
        self.top = tk.Toplevel(parent)
        if not visible:
            self.top.withdraw()              # tests: never mapped, never takes the focus
        self.top.title(t("Check my problem"))
        self.top.minsize(560, 360)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.body = ttk.Frame(self.top, padding=16)
        self.body.pack(fill="both", expand=True)
        self.body.columnconfigure(0, weight=1)
        ttk.Label(self.body, text=t("Check my problem"), style="H1.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.body, wraplength=self.WRAP, justify="left", style="Muted.TLabel", text=t(
            "The launcher looks in this PC's logs and settings for the problems other players had, and says how "
            "to fix them. Nothing is changed and nothing is sent.")).grid(row=1, column=0, sticky="w", pady=(4, 10))
        self.list = ttk.Frame(self.body)
        self.list.grid(row=2, column=0, sticky="nsew")
        self.list.columnconfigure(0, weight=1)
        self.body.rowconfigure(2, weight=1)
        row = ttk.Frame(self.body)
        row.grid(row=3, column=0, sticky="we", pady=(12, 0))
        self.again_btn = ttk.Button(row, text=t("Check again"), command=self.run)
        self.again_btn.pack(side="left")
        if report is not None:
            ttk.Button(row, text=t("Report a problem..."), command=self._report).pack(side="left", padx=(8, 0))
        ttk.Button(row, text=t("Close"), command=self.close).pack(side="right")
        self.run()

    # ---------------------------------------------------------------- the check
    def run(self):
        self.again_btn.configure(state="disabled")
        self._clear()
        ttk.Label(self.list, text=t("Looking…"), style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        threading.Thread(target=_work, args=(self.q, self.out_dir, self.facts, self.fw), daemon=True).start()
        self.top.after(50, self._poll)

    def _poll(self):
        try:
            if not self.top.winfo_exists():
                return                          # (closed while it looked)
        except tk.TclError:
            return
        try:
            kind, value = self.q.get_nowait()
        except queue.Empty:
            try:
                self.top.after(100, self._poll)
            except tk.TclError:
                pass
            return
        if kind == "ok":
            self.findings, self.error = value, None
        else:
            self.findings, self.error = [], value
        self.show()

    def _clear(self):
        for w in self.list.winfo_children():
            w.destroy()

    def show(self):
        self._clear()
        self.again_btn.configure(state="normal")
        if self.error is not None:
            ttk.Label(self.list, text=t("Could not look at the files: {error}", error=self.error), wraplength=self.WRAP,
                      justify="left").grid(row=0, column=0, sticky="w")
            return
        if not self.findings:
            ttk.Label(self.list, text=t("No known problem found."), style="H2.TLabel").grid(row=0, column=0,
                                                                                         sticky="w")
            ttk.Label(self.list, wraplength=self.WRAP, justify="left", text=t(
                "If something still goes wrong, \"Report a problem...\" makes one zip with your logs to send to "
                "whoever helps you.")).grid(row=1, column=0, sticky="w", pady=(4, 0))
            return
        for i, f in enumerate(self.findings):
            self._finding(i, f)

    def _finding(self, i, f):
        title, found, fix = f.text(t)
        card = ttk.Frame(self.list, style="Card.TFrame" if self.themed else "TFrame",
                         padding=0 if self.themed else (0, 4))
        card.grid(row=i, column=0, sticky="we", pady=(0, 8))
        card.columnconfigure(0, weight=1)
        pre = "Card." if self.themed else ""
        head = ttk.Frame(card, style="CardBody.TFrame" if self.themed else "TFrame")
        head.grid(row=0, column=0, sticky="we")
        head.columnconfigure(1, weight=1)
        mark = ttk.Label(head, text=t("Problem") if f.kind == "problem" else t("Note"),
                         style=(pre + ("PillBad" if f.kind == "problem" else "PillWarn") + ".TLabel") if self.themed
                         else "TLabel")
        mark.grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(head, text=title, style=pre + "H2.TLabel").grid(row=0, column=1, sticky="w")
        if f.help:
            ttk.Button(head, text=t("Help"), style="Card.Small.TButton" if self.themed else "TButton",
                       command=lambda u=pc.help_url(f): self.open_url(u)).grid(row=0, column=2, sticky="e")
        if found:
            ttk.Label(card, text=found, style=pre + "Faint.TLabel" if self.themed else "TLabel",
                      wraplength=self.WRAP, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(card, text=fix, style=pre + "TLabel" if self.themed else "TLabel", wraplength=self.WRAP,
                  justify="left").grid(row=2, column=0, sticky="w", pady=(4, 0))

    # ---------------------------------------------------------------- buttons
    @staticmethod
    def _browser(url):
        import webbrowser
        webbrowser.open(url)

    def _report(self):
        if self.report is not None:
            self.report()

    def close(self):
        try:
            self.top.destroy()
        except tk.TclError:
            pass


def open_for(app):
    """The launcher's 'Check my problem...' buttons: one window at a time."""
    dlg = getattr(app, "_check_dlg", None)
    try:
        if dlg is not None and dlg.top.winfo_exists():
            dlg.top.lift()
            return dlg
    except tk.TclError:
        pass
    out = app.settings.out_dir
    app._check_dlg = CheckDialog(app, out, report=getattr(app, "report_problem", None))
    return app._check_dlg
