"""The 'Report a problem' window of the launcher: tkinter front end of problem_report.py.

    ReportDialog(parent, make_context, dest_dir, reveal=..., issues_url=..., sender=report_send.Sender | None)

One click for the player: the window opens with "What happened?" (optional), a contact field (optional) and
"Send to the developer" already focused. Send makes the zip (the same cleaned zip as Save, made small enough for the
developer's Discord) on a worker thread and uploads it to the project's lobby server (report_send.py), then says
"Sent, thanks (report #ID)". "Save on the Desktop instead" makes the zip and opens its folder, as before. What goes
into the zip (one line per part, with check marks) and the privacy promise are below the buttons.

Without a sender (no lobby files, or the server takes no reports: an older server answers the window's check that
way) the window offers Save only. Nothing is sent before the player presses Send.

make_context() -> report.Context is called on the Tk thread (for the list) and on the worker thread (for the zip).
"""
import os
import queue
import shutil
import sys
import tempfile
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
CONTACT_MAX = 80
PRIVACY = N_(
    "Before the zip is made, your Windows user name in file paths becomes <user>, internet IP addresses "
    "become <ip> (addresses of your own network stay), lobby player names (yours and your opponents') "
    "become <player>, and passwords, tokens and match keys are left out. "
    "Your game files, keys, .pkg and .rap are never included.")
SEND_NOTICE = N_("Sends your logs to the developer with your lobby name. No game files, no keys, no passwords.")


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


def _send_work(q, make_context, sender, note, contact, enabled):
    """Make the zip in a folder of its own, send it, remove it. Puts ("sent", (Result, reply)) or ("send_err", e)."""
    tmp = tempfile.mkdtemp(prefix="t5dr-report-")
    try:
        res = report.build_for_send(make_context(), tmp, note, enabled)
        q.put(("progress", (0, res.zip_size)))
        reply = sender.send(res.path, note, contact, progress=lambda a, b: q.put(("progress", (a, b))))
        q.put(("sent", (res, reply)))
    except Exception as e:      # noqa: BLE001 -- shown to the player, who can still save it
        q.put(("send_err", e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _probe_work(q, sender):
    try:
        q.put(("probe", sender.probe()))
    except Exception:          # noqa: BLE001 -- offline now: Send stays, sending says what is wrong
        q.put(("probe", None))


def send_error_text(e):
    """What the player reads when sending did not work (report_upload.ReportError codes)."""
    code = getattr(e, "code", "")
    if code == "unsupported" or code == "reports_off":
        return t("The server cannot take reports yet. Save the zip and send it yourself.")
    if code == "rate_limited":
        return t("Enough reports from this PC for today. Save the zip and send it yourself.")
    if code in ("report_size",):
        return t("The report is too big to send. Save the zip and send it yourself.")
    if code in ("connect_failed", "timeout", "disconnected", "tls_mismatch"):
        return t("The server could not be reached. Check the internet connection, or save the zip.")
    return t("The report could not be sent: {error}", error=getattr(e, "msg", "") or e)


class ReportDialog:
    def __init__(self, parent, make_context, dest_dir, reveal=None, issues_url="", log=None, visible=True,
                 discord_url="", sender=None):
        self.parent = parent
        self.discord_url = discord_url
        self.make_context = make_context
        self.dest_dir = dest_dir
        self.reveal = reveal
        self.issues_url = issues_url
        self.log = log or (lambda _m: None)
        self.sender = sender
        self.result = None
        self.error = None
        self.sent = None                     # the server's reply after Send: {"id", "webhook"}
        self.send_error = None
        self.opened = 0                      # how many times the folder was opened (tests read it)
        self.q = queue.Queue()
        self.pending = 0                     # worker threads whose last message has not come yet
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
        if self.sender is not None:
            self.pending += 1
            threading.Thread(target=_probe_work, args=(self.q, self.sender), daemon=True).start()
            self._start_poll()

    # ---------------------------------------------------------------- form
    def _form(self):
        b = self.body
        b.columnconfigure(0, weight=1)
        ttk.Label(b, text=t("Report a problem"), style="H1.TLabel").grid(row=0, column=0, sticky="w")
        self.lead = ttk.Label(b, wraplength=600, justify="left", text=self._lead())
        self.lead.grid(row=1, column=0, sticky="w", pady=(4, 10))

        ttk.Label(b, text=t("What happened? (optional)"), style="H2.TLabel").grid(row=2, column=0, sticky="w")
        self.note = tk.Text(b, height=2, width=70, wrap="word",
                            font=(i18n.ui_family() if i18n else "Segoe UI", 10))
        self.note.grid(row=3, column=0, sticky="we", pady=(2, 6))
        crow = self.contact_row = ttk.Frame(b)
        crow.grid(row=4, column=0, sticky="we", pady=(0, 8))
        ttk.Label(crow, text=t("Contact (optional, e.g. your Discord name):")).pack(side="left")
        self.contact = ttk.Entry(crow, width=32)
        self.contact.pack(side="left", padx=(8, 0))

        self.notice = ttk.Label(b, wraplength=600, justify="left", style="Muted.TLabel", text=t(SEND_NOTICE))
        self.notice.grid(row=5, column=0, sticky="w")
        self.status_var = tk.StringVar()
        ttk.Label(b, textvariable=self.status_var, style="Muted.TLabel", wraplength=600, justify="left").grid(
            row=6, column=0, sticky="w")
        row = ttk.Frame(b)
        row.grid(row=7, column=0, sticky="we", pady=(6, 10))
        self.send_btn = ttk.Button(row, text=t("Send to the developer"), command=self.send, default="active")
        self.save_btn = ttk.Button(row, text=t("Save on the Desktop instead") if self.sender else
                                   t("Save report on the Desktop"), command=self.save)
        self.cancel_btn = ttk.Button(row, text=t("Cancel"), command=self.close)
        if self.sender is not None:
            self.send_btn.pack(side="left")
            self.save_btn.pack(side="left", padx=8)
        else:
            self.save_btn.pack(side="left")
            self.notice.grid_remove()
            crow.grid_remove()
        self.cancel_btn.pack(side="left", padx=8)
        self.top.bind("<Return>", self._enter)
        self.top.bind("<Escape>", lambda _e: self.close())
        (self.send_btn if self.sender is not None else self.save_btn).focus_set()

        box = ttk.LabelFrame(b, text="  " + t("What goes into the zip") + "  ", padding=(10, 6))
        box.grid(row=8, column=0, sticky="we")
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
        ttk.Label(b, textvariable=self.total_var, style="Muted.TLabel").grid(row=9, column=0, sticky="w", pady=(4, 0))
        ttk.Label(b, wraplength=600, justify="left", text=t(PRIVACY)).grid(row=10, column=0, sticky="w", pady=(8, 0))
        self._total()

    def _lead(self):
        if self.sender is not None:
            return t("Press Send: your logs and settings go straight to the developer. Or save the zip and send it "
                     "yourself.")
        return t("This makes one zip file on your Desktop with the logs and settings that help to find the "
                 "problem. Send the zip to the person who gave you the game, or attach it to an issue.")

    def _enter(self, event):
        if isinstance(event.widget, tk.Text):
            return None                      # (a new line in the note)
        (self.send if self.sender is not None and str(self.send_btn.cget("state")) != "disabled" else self.save)()
        return "break"

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

    def _busy(self, on):
        for w in (self.send_btn, self.save_btn):
            try:
                w.configure(state="disabled" if on else "normal")
            except tk.TclError:
                pass

    # ---------------------------------------------------------------- send
    def _note(self):
        return self.note.get("1.0", "end").strip()[:NOTE_MAX]

    def send(self):
        if self.sender is None:
            return self.save()
        self._busy(True)
        self.send_error = None
        self.status_var.set(t("Making the report and sending it..."))
        self.pending += 1
        threading.Thread(target=_send_work, args=(self.q, self.make_context, self.sender, self._note(),
                                                  self.contact.get().strip()[:CONTACT_MAX], self.enabled()),
                         daemon=True).start()
        self._start_poll()

    def _hide_send(self, why):
        """The server takes no reports: Save is the way (the window keeps its fields)."""
        self.send_btn.pack_forget()
        self.notice.grid_remove()
        self.contact_row.grid_remove()
        self.save_btn.configure(text=t("Save report on the Desktop"))
        self.save_btn.focus_set()
        self.lead.configure(text=why)

    # ---------------------------------------------------------------- save
    def save(self):
        self._busy(True)
        self.status_var.set(t("Making the report..."))
        self.pending += 1
        threading.Thread(target=_work, args=(self.q, self.make_context, self.dest_dir, self._note(), self.enabled()),
                         daemon=True).start()
        self._start_poll()

    def _start_poll(self):
        if not getattr(self, "_polling", False):
            self._polling = True
            self.top.after(100, self._poll)

    def _poll(self):
        self._polling = False
        while True:
            try:
                kind, val = self.q.get_nowait()
            except queue.Empty:
                break
            if self._handle(kind, val):
                return
        try:
            if self.pending > 0:
                self._start_poll()
        except tk.TclError:
            pass                              # the window was closed meanwhile

    def _handle(self, kind, val):
        """One message from a worker; True: the window changed to its end page (no more polling)."""
        if kind != "progress":
            self.pending = max(0, self.pending - 1)
        try:
            if not self.top.winfo_exists():
                return True
        except tk.TclError:
            return True
        if kind == "probe":
            if val == 0 and self.sent is None:
                self._hide_send(t("The server cannot take reports yet. Save the zip and send it yourself: to the "
                                  "person who gave you the game, or attach it to an issue."))
            return False
        if kind == "progress":
            done, total = val
            if total:
                self.status_var.set(t("Sending... {done} of {total}", done=human(done), total=human(total)))
            return False
        if kind == "send_err":
            self.send_error = val
            self.status_var.set(send_error_text(val))
            self._busy(False)
            self.save_btn.focus_set()
            self.log(f"report not sent: {getattr(val, 'code', '')} {val}")
            if getattr(val, "code", "") in ("unsupported", "reports_off"):
                self._hide_send(send_error_text(val))
            return False
        if kind == "sent":
            res, reply = val
            self.sent = reply
            self.log(f"report sent: #{reply.get('id')} ({report.human(res.zip_size)}), {len(res.members)} files, "
                     f"removed {dict(res.counts)}")
            self._done_sent(res, reply)
            return True
        if kind == "err":
            self.error = val
            self.status_var.set(t("The report could not be made: {error}", error=val))
            self._busy(False)
            self.log(f"report failed: {val}")
            return False
        self.result = val
        self.log(f"report saved: {val.path} ({report.human(val.zip_size)}), {len(val.members)} files, "
                 f"removed {dict(val.counts)}")
        self._done(val)
        self.open_folder()
        return True

    # ---------------------------------------------------------------- done
    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.top.unbind("<Return>")
        b = self.body
        b.columnconfigure(0, weight=1)
        return b

    def _member_lines(self, res):
        lines = []
        for m in res.members:
            lines.append(f"{m['name']}   {human(m['size'])}"
                         + ("   " + t("(shortened in the middle)") if m["removed"] else ""))
        lines += [t("{name}   left out: {reason}", name=n, reason=translate_message(why)) for n, why in res.skipped]
        c = res.counts
        lines += ["", t("Removed from the text files: {user} user or PC names, {ip} IP addresses, {secret} "
                        "passwords, tokens or keys, {email} e-mail addresses.", user=c["user"], ip=c["ip"],
                        secret=c["secret"], email=c["email"])]
        return lines

    def _done_sent(self, res, reply):
        b = self._clear()
        ttk.Label(b, text=t("Sent, thanks (report #{id})", id=reply.get("id", "?")), style="H1.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(b, wraplength=600, justify="left", text=(
            t("The developer has your report ({size}). If you asked for an answer, it comes to the contact you gave.",
              size=human(res.zip_size))
            + ("\n" + t("Questions? Ask the players in the OpenRecomp-FGC Discord: {url}", url=self.discord_url)
               if self.discord_url else ""))).grid(row=1, column=0, sticky="w", pady=(8, 8))
        box = tk.Text(b, height=12, width=80, wrap="none", font=("Consolas", 9))
        box.insert("1.0", "\n".join(self._member_lines(res)))
        box.configure(state="disabled")
        box.grid(row=2, column=0, sticky="nsew")
        b.rowconfigure(2, weight=1)
        self.close_btn = ttk.Button(b, text=t("Close"), command=self.close)
        self.close_btn.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.close_btn.focus_set()
        self.top.bind("<Return>", lambda _e: self.close())

    def _done(self, res):
        b = self._clear()
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
            else t("Send this zip to the person who gave you the game."))
            + ("\n" + t("Questions? Ask the players in the OpenRecomp-FGC Discord: {url}", url=self.discord_url)
               if self.discord_url else "")).grid(
            row=3, column=0, sticky="w", pady=(8, 8))
        box = tk.Text(b, height=14, width=80, wrap="none", font=("Consolas", 9))
        box.insert("1.0", "\n".join(self._member_lines(res)))
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
