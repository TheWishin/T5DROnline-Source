"""The profile's match history with a replay button (1.1.5): on your own profile, a row of the lobby's history that
has a replay on this PC (docs/REPLAYS.md: every online match is saved in native\\replays) is marked with a play
sign, and Watch replay (or a double click) plays it -- on the launcher's Replays tab, which shows how it went.

The history comes from the lobby server, the replays from this PC; they are matched by the time (a few minutes
apart at most: the server's clock), both fighters and, where the replay kept them, the opponent's name
(launcher/replays.py for_history). The launcher's Replays tab (launcher/replays_ui.py) does the reading and the
playing; without it (the Online tab on its own, tests) the row of buttons stays hidden."""
import tkinter as tk
from tkinter import ttk

from .i18n import t

MARK = "▶ "          # a replay of this match is on this PC
RESULT_TAG = {"win": "won", "loss": "lost"}


class HistoryReplays:
    def __init__(self, view):
        self.view = view
        self.tab = tab = view.tab
        px = view.px
        self.rows = {}        # Treeview iid -> the server's history row
        self.found = {}       # iid -> replays.Entry
        tv = tab.tv_hist
        tv.configure(selectmode="browse")
        try:          # room for the play mark in front of the date (taken from the wide status column)
            extra = px(16)
            tv.column("when", width=int(tv.column("when", "width")) + extra)
            tv.column("status", width=max(px(200), int(tv.column("status", "width")) - extra))
        except (tk.TclError, ValueError):
            pass
        card = tv.master.master
        self.bar = view.body(card)
        self.bar.grid(row=3, column=0, columnspan=2, sticky="we", pady=(px(8), 0))
        self.btn = ttk.Button(self.bar, text=t("Watch replay"), style="Card.Small.TButton", command=self.watch,
                              state="disabled")
        self.btn.pack(side="left")
        self.hint = tk.StringVar(value="")
        lab = ttk.Label(self.bar, textvariable=self.hint, style="Card.Faint.TLabel", justify="left")
        lab.pack(side="left", padx=(px(10), 0))
        view.wrap(lab, card, 190)
        self.bar.grid_remove()
        tv.bind("<<TreeviewSelect>>", lambda _e: self._update(), add="+")
        tv.bind("<Double-1>", lambda _e: self.watch(), add="+")
        tv.bind("<Return>", lambda _e: self.watch(), add="+")

    def _replays(self):
        return getattr(getattr(self.tab, "app", None), "replays", None)

    def shown(self, p):
        """The profile `p` was just put into the list (OnlineTab.show_profile): colour the results, find the replays
        of your own matches."""
        tv = self.tab.tv_hist
        self.rows = dict(zip(tv.get_children(), p.get("history") or []))
        self.found = {}
        for iid, h in self.rows.items():
            tag = RESULT_TAG.get(h.get("result"))
            tv.item(iid, tags=(tag,) if tag else ())
        rp = self._replays()
        if not (p.get("self") and rp is not None and hasattr(rp, "for_history")):
            self.bar.grid_remove()
            return
        ids = {f["key"]: f["id"] for f in self.tab.table.fighters if "id" in f}
        for iid, h in self.rows.items():
            e = rp.for_history(h, ids)
            if e is not None:
                self.found[iid] = e
                vals = list(tv.item(iid, "values"))
                if vals:
                    vals[0] = MARK + str(vals[0])
                    tv.item(iid, values=vals)
        self.bar.grid()
        self._update()

    def selected(self):
        sel = self.tab.tv_hist.selection()
        return (sel[0], self.found.get(sel[0])) if sel else (None, None)

    def _update(self):
        iid, e = self.selected()
        self.btn.configure(state="normal" if e is not None else "disabled")
        if not self.rows:
            self.hint.set("")
        elif iid is None:
            self.hint.set(t("{count} of these matches have a replay on this PC ({mark}). Select one to watch it.",
                            count=len(self.found), mark=MARK.strip()) if self.found else
                          t("None of these matches has a replay on this PC (replays are saved on the PC that "
                            "played, while \"Save online matches as replays\" is on)."))
        elif e is None:
            self.hint.set(t("No replay of this match on this PC."))
        else:
            self.hint.set(t("{fighters}, saved on this PC.", fighters=e.fighters))

    def watch(self):
        _iid, e = self.selected()
        rp = self._replays()
        if e is None or rp is None:
            return
        rp.watch_entry(e)


def attach(view):
    """The profile page's replay row (tk_views._build_lobby, after the profile page)."""
    view.tab.history = HistoryReplays(view)
    return view.tab.history
