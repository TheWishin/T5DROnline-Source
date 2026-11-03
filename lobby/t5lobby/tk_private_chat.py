"""Private message window; all content stays in bounded session memory."""
import tkinter as tk
from tkinter import ttk

from .i18n import N_, t
from .private_chat import Conversations, MAX_REPORT_LINES


class PrivateChat:
    def __init__(self, tab):
        self.tab = tab
        self.model = Conversations()
        self.window = None
        self.buttons = []
        self.names = []
        self.name = None
        self._focus_after = None
        self._drawn_name = None
        self._drawn_line_ids = []

    def available(self):
        c = self.tab.client
        return bool(c and c.me and getattr(c, "private_chat_ok", lambda: False)())

    def button(self, parent, command, text=N_("Message player")):
        b = ttk.Button(parent, text=t(text), style="Card.Small.TButton", command=command)
        self.buttons.append(b)
        return b

    def refresh(self):
        if self.sync_mutes() and self.window is not None:
            self.draw()
            return
        on = self.available()
        for b in self.buttons:
            b.configure(state="normal" if on else "disabled")
        if hasattr(self, "inbox"):
            self.inbox.configure(text=t("Private messages ({count})", count=self.model.unread)
                                 if self.model.unread else t("Private messages"))
        if self.window is not None:
            for b in self.controls:
                b.configure(state="normal" if on and self.name else "disabled")
            self.entry.configure(state="normal" if on and self.name else "disabled")

    def sync_mutes(self):
        c = self.tab.client
        is_muted = getattr(c, "is_muted", None)
        changed = False
        if callable(is_muted):
            for row in self.model.rows.values():
                muted = bool(is_muted(row["name"]))
                changed |= row["muted"] != muted
                self.model.set_muted(row["name"], muted)
        if self.window is not None and self.name and hasattr(self, "mute_button"):
            self.mute_button.configure(text=t("Unmute") if self.is_muted(self.name) else t("Mute"))
        return changed

    def is_muted(self, name):
        check = getattr(self.tab.client, "is_muted", None)
        return bool(check(name)) if callable(check) else name.lower() in self.model.muted

    def reset(self):
        self.model = Conversations()
        self._drawn_name, self._drawn_line_ids = None, []
        self.name = None
        if self.window is not None:
            self.close()
        self.refresh()

    def close(self):
        if self.window is not None:
            if self._focus_after is not None:
                try:
                    self.window.after_cancel(self._focus_after)
                except tk.TclError:
                    pass
                self._focus_after = None
            self.window.destroy()
        self.window = None
        self.model.active = None

    def _queue_mark_read(self, window):
        if self.window is not window or self._focus_after is not None:
            return

        def ready():
            if self.window is window:
                self._focus_after = None
                self.mark_read()

        self._focus_after = window.after_idle(ready)

    def selected_player(self):
        tv = self.tab.tv_players
        sel = tv.selection()
        if sel:
            # The table's display name can include a DEV badge or the "you" suffix.
            # Resolve the stable row id through the model, as the profile action does.
            for player in self.tab.client.players if self.tab.client is not None else ():
                if player["id"] == sel[0]:
                    self.show(player["name"])
                    break

    def profile(self):
        self.show(self.tab.profile_name)

    def show(self, name=None):
        if not self.available():
            self.tab.status(t("Private chat is unavailable on this server."), error=True)
            return
        if name and name.lower() == self.tab.client.me["name"].lower():
            name = None
        if self.window is None:
            self.build()
        name = name or self.name
        if name:
            self.model.select(name)
            self.name = name
        self.draw()
        self.window.deiconify()
        self.window.lift()
        self.refresh()

    def build(self):
        w = self.window = self.tab.new_window(self.tab.parent)
        w.title(t("Private messages"))
        w.protocol("WM_DELETE_WINDOW", self.close)
        # FocusIn can arrive before Tk has settled the focused child widget. Recheck
        # at idle, and only update markers (never redraw a report selection).
        w.bind("<FocusIn>", lambda _e: self._queue_mark_read(w), add="+")
        w.columnconfigure(1, weight=1)
        w.rowconfigure(1, weight=1)
        ttk.Label(w, text=t("Private messages are relayed, not saved by the server. Only lines you select are sent "
                            "with a report."), wraplength=650).grid(row=0, column=0, columnspan=2, sticky="we", padx=10,
                                                                 pady=10)
        peer_frame = ttk.Frame(w)
        peer_frame.grid(row=1, column=0, sticky="nsew", padx=10)
        peer_frame.rowconfigure(0, weight=1)
        peer_frame.columnconfigure(0, weight=1)
        self.peers = tk.Listbox(peer_frame, width=22, exportselection=False)
        self.peers.grid(row=0, column=0, sticky="nsew")
        peer_scroll = ttk.Scrollbar(peer_frame, orient="vertical", command=self.peers.yview)
        peer_scroll.grid(row=0, column=1, sticky="ns")
        self.peers.configure(yscrollcommand=peer_scroll.set)
        self.peers.bind("<<ListboxSelect>>", lambda _e: self.choose())
        line_frame = ttk.Frame(w)
        line_frame.grid(row=1, column=1, sticky="nsew", padx=10)
        line_frame.rowconfigure(0, weight=1)
        line_frame.columnconfigure(0, weight=1)
        self.lines = tk.Listbox(line_frame, width=72, height=16, selectmode="extended", exportselection=False)
        self.lines.grid(row=0, column=0, sticky="nsew")
        line_y = ttk.Scrollbar(line_frame, orient="vertical", command=self.lines.yview)
        line_y.grid(row=0, column=1, sticky="ns")
        line_x = ttk.Scrollbar(line_frame, orient="horizontal", command=self.lines.xview)
        line_x.grid(row=1, column=0, sticky="we")
        self.lines.configure(yscrollcommand=line_y.set, xscrollcommand=line_x.set)
        self.text = tk.StringVar(w)
        self.entry = ttk.Entry(w, textvariable=self.text)
        self.entry.grid(row=2, column=1, sticky="we", padx=10, pady=6)
        self.entry.bind("<Return>", lambda _e: self.send())
        bar = ttk.Frame(w)
        bar.grid(row=3, column=0, columnspan=2, sticky="we", padx=10, pady=6)
        self.controls = []
        for key, cmd in ((N_("Send"), self.send), (N_("Mute"), self.mute),
                         (N_("Block player"), self.block), (N_("Report selected lines"), self.report)):
            b = ttk.Button(bar, text=t(key), command=cmd)
            b.pack(side="left", padx=(0, 6))
            self.controls.append(b)
        self.mute_button = self.controls[1]
        ttk.Label(w, text=t("Private messages are kept only until you log out or close the launcher."),
                  wraplength=650).grid(row=4, column=0, columnspan=2, sticky="we", padx=10, pady=8)
        ttk.Label(w, text=t("Mute hides this player's chat, mentions and invites for you. Block also prevents matches "
                            "and private messages."), wraplength=650).grid(row=5, column=0, columnspan=2,
                                                                          sticky="we", padx=10, pady=(0, 8))

    def choose(self):
        sel = self.peers.curselection()
        if sel and sel[0] < len(self.names):
            name = self.names[sel[0]]
            if self.name == name:
                self.mark_read()
                return
            self.name = name
            self.model.select(self.name)
            self.draw()

    def focused(self):
        if self.window is None or self.window.state() != "normal":
            return False
        focus = self.window.focus_get()
        return bool(focus is not None and focus.winfo_toplevel() == self.window)

    def mark_read(self):
        if not self.focused() or not self.name:
            return
        row = self.model.rows.get(self.name.lower())
        if row is None or not row["unread"]:
            return
        self.model.select(self.name)
        if self.name in self.names:
            index = self.names.index(self.name)
            self.peers.delete(index)
            self.peers.insert(index, row["name"])
            self.peers.selection_set(index)
        self.refresh()

    def draw(self):
        if self.window is None:
            return
        self.names = [row["name"] for row in self.model.rows.values()]
        self.peers.delete(0, "end")
        for row in self.model.rows.values():
            self.peers.insert("end", row["name"] + (f" ({row['unread']})" if row["unread"] else ""))
        # Retain the explicit report selection when new traffic refreshes the view.
        selected = set()
        if self._drawn_name == self.name:
            selected = {self._drawn_line_ids[i] for i in self.lines.curselection()
                        if 0 <= i < len(self._drawn_line_ids)}
        self.lines.delete(0, "end")
        self._drawn_name, self._drawn_line_ids = self.name, []
        if self.name and self.name.lower() not in self.model.rows:
            self.name = None
        if self.name and self.name.lower() in self.model.rows:
            row = self.model.rows[self.name.lower()]
            mine = self.tab.client.me["name"].lower() if self.tab.client and self.tab.client.me else ""
            visible_lines = [line for line in row["lines"] if not row["muted"]
                             or line["from"]["name"].lower() == mine]
            for index, line in enumerate(visible_lines):
                self.lines.insert("end", f"{line['from']['name']}: {line['text']}")
                self._drawn_line_ids.append(line.get("id"))
                if line.get("id") in selected:
                    self.lines.selection_set(index)
            self.window.title(t("Message {name}", name=self.name))
            self.mute_button.configure(text=t("Unmute") if self.is_muted(self.name) else t("Mute"))
            if self.name in self.names:
                self.peers.selection_set(self.names.index(self.name))
        self.refresh()

    def event(self, ev):
        if ev.get("t") == "mutes":
            self.refresh()
            return
        if ev.get("t") != "private_message" or not self.available():
            return
        sender = ev.get("from") or {}
        if isinstance(sender, dict) and self.is_muted(str(sender.get("name", ""))):
            return
        self.sync_mutes()
        if self.model.receive(ev, self.tab.client.me["name"], self.focused()):
            self.draw()
            self.refresh()

    def send(self):
        text = self.text.get().strip()
        if not self.available() or not self.name or not text:
            return
        name, c = self.name, self.tab.client

        def done(reply):
            if self.tab.client is not c:
                return
            if self.text.get().strip() == text:
                self.text.set("")
            self.model.receive(reply.get("message"), c.me["name"], True)
            self.draw()
        self.tab.call(c.private_message, name, text, then=done)

    def mute(self):
        if not self.available() or not self.name:
            return
        name, c = self.name, self.tab.client
        muted = not self.is_muted(name)

        def done(reply):
            if self.tab.client is c:
                self.model.set_muted(name, bool(reply.get("muted")))
                self.draw()
        self.tab.call(c.mute, name, muted, then=done)

    def block(self):
        if self.available() and self.name and self.tab.ask_yes_no(
                t("Block player"), t("Block {name}? This also leaves any running match against them.", name=self.name),
                parent=self.window):
            self.tab.call(self.tab.client.block, self.name)

    def report(self):
        if not self.available() or not self.name:
            return
        # Listbox indices can differ from the transcript when muted incoming lines
        # are hidden. Resolve the visible selection back to its original receipts.
        indices = self.lines.curselection()
        if len(indices) > MAX_REPORT_LINES:
            selected = []
        else:
            ids = {self._drawn_line_ids[i] for i in indices if 0 <= i < len(self._drawn_line_ids)}
            row = self.model.rows.get(self.name.lower()) or {"lines": []}
            selected = [dict(line) for line in row["lines"] if line.get("id") in ids]
        if not selected:
            self.tab.status(t("Select up to {count} lines to report.", count=MAX_REPORT_LINES), error=True)
            return
        if self.tab.ask_yes_no(t("Report selected lines"), t("Send selected lines to moderators?"), parent=self.window):
            self.tab.call(self.tab.client.private_report, self.name, selected,
                          then=lambda _r: self.tab.status(t("Report sent to moderators.")))
