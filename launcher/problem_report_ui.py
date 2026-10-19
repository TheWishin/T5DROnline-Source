"""The 'Report a problem' window of the launcher: tkinter front end of problem_report.py.

    ReportDialog(parent, make_context, dest_dir, reveal=..., issues_url=...)

The window shows what would go into the zip (one line per part, with check marks), a box for
"What happened?" and the privacy promise. "Save report" makes the zip on a worker thread (reading
and cleaning a few MB of logs takes a second or two), then shows what is inside and what was
removed, and opens the folder with the zip selected.

make_context() -> report.Context is called on the Tk thread (for the list) and on the worker
thread (for the zip). Nothing is uploaded, ever.
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

import problem_report as report

# The player's language (lobby/t5lobby/i18n.py). The zip's own files stay English: they are for whoever reads the
# report.
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lobby"))
try:
    from t5lobby import i18n
    from t5lobby.i18n import N_, t, translate_message
except ImportError:     # lobby/ is missing from this copy: English only
    i18n = None

    def N_(text):
        return text

    def t(text, /, **values):
        return text.format(**values) if values else text

    def translate_message(msg):
        return msg

NOTE_MAX = 2000
PRIVACY = N_(
    "Before the zip is made, your Windows user name in file paths becomes <user>, internet IP addresses "
    "become <ip> (addresses of your own network stay), lobby player names (yours and your opponents') "
    "become <player>, and passwords, tokens and match keys are left out. "
    "Your game files, keys, .pkg and .rap are never included. Nothing is uploaded: you send the zip yourself.")


def human(n):
    """A size for reading (report.human with the language's decimal sign)."""
    if n < 1024:
        return t("{count} bytes", count=n)
    if n < 1 << 20:
        return f"{n / 1024:.0f} KB"
    return (i18n.num(n / (1 << 20), 1) if i18n else f"{n / (1 << 20):.1f}") + " MB"


def _work(q, make_context, dest_dir, note, enabled):
    """Worker thread body (a module function: it holds no Tk object)."""
    try:
        q.put(("ok", report.build(make_context(), dest_dir, note, enabled)))
    except Exception as e:      # noqa: BLE001 -- shown to the player
        q.put(("err", e))


class ReportDialog:
    def __init__(self, parent, make_context, dest_dir, reveal=None, issues_url="", log=None, visible=True):
        self.parent = parent
        self.make_context = make_context
        self.dest_dir = dest_dir
        self.reveal = reveal
        self.issues_url = issues_url
        self.log = log or (lambda _m: None)
        self.result = None
        self.error = None
        self.opened = 0                      # how many times the folder was opened (tests read it)
        self.q = queue.Queue()
        self.vars = {}
        self.top = tk.Toplevel(parent)
        if not visible:
            self.top.withdraw()              # tests: never mapped, never takes the focus
        self.top.title(t("Report a problem"))
        self.top.minsize(640, 520)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.body = ttk.Frame(self.top, padding=16)
        self.body.pack(fill="both", expand=True)
        try:
            self.groups = report.discover(self.make_context(), "")
        except Exception as e:      # noqa: BLE001 -- the window must open even when a folder is odd
            self.groups = []
            self.error = e
        self._form()

    # ---------------------------------------------------------------- form
    def _form(self):
        b = self.body
        b.columnconfigure(0, weight=1)
        ttk.Label(b, text=t("Report a problem"), style="H1.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(b, wraplength=600, justify="left", text=t(
            "This makes one zip file on your Desktop with the logs and settings that help to find the "
            "problem. Send the zip to the person who gave you the game, or attach it to an issue.")).grid(
            row=1, column=0, sticky="w", pady=(4, 10))

        ttk.Label(b, text=t("What happened? (optional)"), style="H2.TLabel").grid(row=2, column=0, sticky="w")
        self.note = tk.Text(b, height=4, width=70, wrap="word",
                            font=(i18n.ui_family() if i18n else "Segoe UI", 10))
        self.note.grid(row=3, column=0, sticky="we", pady=(2, 10))

        box = ttk.LabelFrame(b, text="  " + t("What goes into the zip") + "  ", padding=(10, 6))
        box.grid(row=4, column=0, sticky="we")
        box.columnconfigure(0, weight=1)
        for r, g in enumerate(self.groups):
            v = tk.BooleanVar(value=True if not g.can_untick else g.default_on)
            self.vars[g.key] = v
            names = ", ".join(i.arcname for i in g.items)
            cb = ttk.Checkbutton(box, text=f"{translate_message(g.title)}  ({human(g.size)})", variable=v,
                                 command=self._total)
            if not g.can_untick:
                cb.state(["disabled"])
            cb.grid(row=r * 2, column=0, sticky="w")
            ttk.Label(box, text=(names if len(names) < 110 else names[:107] + "..."), style="Muted.TLabel").grid(
                row=r * 2 + 1, column=0, sticky="w", padx=(24, 0), pady=(0, 3))
        if not self.groups:
            ttk.Label(box, text=t("Nothing found yet: no game log, no build log.") if not self.error else
                      t("Could not look at the files: {error}", error=self.error)).grid(row=0, column=0, sticky="w")
        self.total_var = tk.StringVar()
        ttk.Label(b, textvariable=self.total_var, style="Muted.TLabel").grid(row=5, column=0, sticky="w", pady=(4, 0))
        ttk.Label(b, wraplength=600, justify="left", text=t(PRIVACY)).grid(row=6, column=0, sticky="w", pady=(8, 8))

        self.status_var = tk.StringVar()
        ttk.Label(b, textvariable=self.status_var, style="Muted.TLabel", wraplength=600, justify="left").grid(
            row=7, column=0, sticky="w")
        row = ttk.Frame(b)
        row.grid(row=8, column=0, sticky="we", pady=(6, 0))
        self.save_btn = ttk.Button(row, text=t("Save report on the Desktop"), command=self.save)
        self.save_btn.pack(side="left")
        self.cancel_btn = ttk.Button(row, text=t("Cancel"), command=self.close)
        self.cancel_btn.pack(side="left", padx=8)
        self._total()

    def enabled(self):
        return {k: bool(v.get()) for k, v in self.vars.items()}

    def _total(self):
        on = self.enabled()
        size = sum(g.size for g in self.groups if on.get(g.key))
        txt = t("About {size} before it is packed (a zip is smaller).", size=human(size))
        if size > report.DEFAULT_CAP:
            txt = t("About {size}; the limit is {limit}, so the biggest logs are shortened in the middle.",
                    size=human(size), limit=human(report.DEFAULT_CAP))
        self.total_var.set(txt)

    # ---------------------------------------------------------------- save
    def save(self):
        note = self.note.get("1.0", "end").strip()[:NOTE_MAX]
        self.save_btn.configure(state="disabled")
        self.status_var.set(t("Making the report..."))
        threading.Thread(target=_work, args=(self.q, self.make_context, self.dest_dir, note, self.enabled()),
                         daemon=True).start()
        self.top.after(100, self._poll)

    def _poll(self):
        try:
            kind, val = self.q.get_nowait()
        except queue.Empty:
            try:
                self.top.after(100, self._poll)
            except tk.TclError:
                pass                              # the window was closed meanwhile
            return
        if kind == "err":
            self.error = val
            self.status_var.set(t("The report could not be made: {error}", error=val))
            self.save_btn.configure(state="normal")
            self.log(f"report failed: {val}")
            return
        self.result = val
        self.log(f"report saved: {val.path} ({report.human(val.zip_size)}), {len(val.members)} files, "
                 f"removed {dict(val.counts)}")
        self._done(val)
        self.open_folder()

    # ---------------------------------------------------------------- done
    def _done(self, res):
        for w in self.body.winfo_children():
            w.destroy()
        b = self.body
        b.columnconfigure(0, weight=1)
        ttk.Label(b, text=t("Report saved"), style="H1.TLabel").grid(row=0, column=0, sticky="w")
        e = ttk.Entry(b, width=80)
        e.insert(0, res.path)
        e.configure(state="readonly")
        e.grid(row=1, column=0, sticky="we", pady=(6, 2))
        ttk.Label(b, style="Muted.TLabel", text=t("{size}. Its folder is open.", size=human(res.zip_size))).grid(
            row=2, column=0, sticky="w")
        ttk.Label(b, wraplength=600, justify="left", text=(
            t("Send this zip to the person who gave you the game, or attach it to an issue at {url}.",
              url=self.issues_url) if self.issues_url
            else t("Send this zip to the person who gave you the game."))).grid(
            row=3, column=0, sticky="w", pady=(8, 8))
        lines = []
        for m in res.members:
            lines.append(f"{m['name']}   {human(m['size'])}"
                         + ("   " + t("(shortened in the middle)") if m["removed"] else ""))
        lines += [t("{name}   left out: {reason}", name=n, reason=translate_message(why)) for n, why in res.skipped]
        c = res.counts
        lines += ["", t("Removed from the text files: {user} user or PC names, {ip} IP addresses, {secret} "
                        "passwords, tokens or keys, {email} e-mail addresses.", user=c["user"], ip=c["ip"],
                        secret=c["secret"], email=c["email"])]
        box = tk.Text(b, height=14, width=80, wrap="none", font=("Consolas", 9))
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")
        box.grid(row=4, column=0, sticky="nsew")
        b.rowconfigure(4, weight=1)
        row = ttk.Frame(b)
        row.grid(row=5, column=0, sticky="we", pady=(8, 0))
        ttk.Button(row, text=t("Open folder"), command=self.open_folder).pack(side="left")
        ttk.Button(row, text=t("Close"), command=self.close).pack(side="left", padx=8)

    def open_folder(self):
        if self.result and self.reveal:
            try:
                self.reveal(self.result.path)
                self.opened += 1
            except OSError as e:
                self.log(f"could not open the folder: {e}")

    def close(self):
        try:
            self.top.destroy()
        except tk.TclError:
            pass
