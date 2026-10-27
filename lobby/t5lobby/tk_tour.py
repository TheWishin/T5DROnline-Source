"""The Online tab's tournaments (docs/TOURNAMENTS.md): the Tournaments page (the list -- upcoming, running, finished --,
the selected tournament with Sign up / Check in / Withdraw and the organizer's buttons, its bracket with the live
sets and results), the "Create tournament" window, and the card "Your tournament set is ready" with Accept (A).

    TourController(tab)       the state and the actions (tab.tours); tk_tab.py feeds it the tour_* events and polls it
    build_page(view, page)    the page's widgets (tk_views.py calls it for its notebook page)
    visual_call(view, frame)  the call card in the tab's question bar
    BracketView               the bracket on a canvas: one column per round, winners on top, losers below, the grand
                              final on the right; a click selects a set (the organizer's buttons act on it)

Nothing here talks to the network on the Tk thread: every lobby call goes through tab.call() (a worker thread).
"""
import time
import tkinter as tk
from tkinter import ttk

from . import theme, tour_text
from .i18n import N_, stamp, t
from .tour_text import tr
from .theme import C

# create window choices: (label, value)
START_CHOICES = ((N_("in 5 minutes"), 5), (N_("in 10 minutes"), 10), (N_("in 15 minutes"), 15),
                 (N_("in 30 minutes"), 30), (N_("in 1 hour"), 60), (N_("in 2 hours"), 120), (N_("in 3 hours"), 180),
                 (N_("in 6 hours"), 360), (N_("in 12 hours"), 720), (N_("in 24 hours"), 1440))
FORMAT_CHOICES = ((N_("Single elimination"), "single"), (N_("Double elimination"), "double"))
SET_CHOICES = ((N_("First to 2 games (best of 3)"), 2), (N_("First to 3 games (best of 5)"), 3))
PLAYER_CHOICES = (8, 16, 32, 64)
CHECKIN_CHOICES = ((N_("No check-in"), 0), (N_("Check-in 5 minutes before"), 5), (N_("Check-in 10 minutes before"), 10),
                   (N_("Check-in 15 minutes before"), 15), (N_("Check-in 30 minutes before"), 30),
                   (N_("Check-in 60 minutes before"), 60))
SEED_CHOICES = ((N_("Random seeding"), "random"), (N_("Seeded by rating"), "rating"))
LIST_COLUMNS = (("tour", N_("Tournament"), 150), ("tstate", N_("State"), 104), ("players", N_("Players"), 92),
                ("when", N_("When"), 168))


def parse_clock(text, now=None):
    """'21:30' -> the next unix time with that local time of day (today, or tomorrow when it has passed); None when
    the text is not a time."""
    text = (text or "").strip().replace(".", ":")
    if not text:
        return None
    try:
        hh, mm = (int(x) for x in text.split(":"))
    except ValueError:
        return None
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    now = time.time() if now is None else now
    lt = time.localtime(now)
    when = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))
    if when <= now + 30:
        when = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + 1, hh, mm, 0, 0, 0, -1))
    return when


class TourController:
    """The tab's tournaments: what is shown and what the buttons do."""

    LIST_EVERY = 4.0                # at most one list refresh per this many seconds while the page shows
    DETAIL_EVERY = 1.0              # ... and one of the tournament on the page (the server's rate limits)

    def __init__(self, tab):
        self.tab = tab
        self.rows = []              # tour_list rows (summaries)
        self.can_create = False
        self.create_hint = ""       # the server's line for a player who may not create (T5L_TOUR_HOST_HINT), if any
        self.listed = False         # the server said whether this player may create (tour_list / tour_access)
        self.selected = None        # id of the tournament on the page
        self.detail = None          # its full view (tour_get)
        self.sel_set = None         # the bracket set the organizer clicked
        self.call = None            # the tour_call showing in the bar (None: no call)
        self.call_end = None        # monotonic time its no-show time ends
        self.page_shown = False
        self.page = None            # the page's widgets (build_page)
        self.bracket = None         # BracketView
        self._list_due = None       # monotonic time a list refresh is wanted (throttled)
        self._detail_due = None
        self._list_busy = self._detail_busy = False
        self._last_list = self._last_detail = 0.0
        self.count_var = None
        self._bar_line = None       # what the question bar says while it shows the call
        self.create_win = None

    # ------------------------------------------------------------------ fetching
    def client(self):
        c = self.tab.client
        return c if c is not None and c.connected and c.me is not None else None

    def shown(self):
        """The Tournaments page was selected."""
        self.page_shown = True
        self.want_list(now=True)
        if self.selected:
            self.want_detail(now=True)

    def want_list(self, now=False):
        due = time.monotonic() if now else max(time.monotonic(), self._last_list + self.LIST_EVERY)
        if self._list_due is None or due < self._list_due:
            self._list_due = due

    def want_detail(self, now=False):
        due = time.monotonic() if now else max(time.monotonic(), self._last_detail + self.DETAIL_EVERY)
        if self._detail_due is None or due < self._detail_due:
            self._detail_due = due

    def _fetch_list(self):
        c = self.client()
        if c is None or self._list_busy:
            return
        self._list_busy = True
        self._last_list = time.monotonic()

        def done(r):
            self._list_busy = False
            self.rows = r.get("rows") or []
            self._access(r)
            if self.selected is None and self.rows:
                self.selected = self.rows[0]["id"]
                self.want_detail(now=True)
            self.render_list()

        def fail():
            self._list_busy = False
        self.tab.call(c.tour_list, then=done, fail=fail)

    def _fetch_detail(self):
        c = self.client()
        if c is None or self._detail_busy or not self.selected:
            return
        self._detail_busy = True
        self._last_detail = time.monotonic()
        tid = self.selected

        def done(d):
            self._detail_busy = False
            if tid == self.selected:
                self.detail = d
                self.render_detail()

        def fail():
            self._detail_busy = False
        self.tab.call(c.tour_get, tid, then=done, fail=fail)

    def select(self, tid):
        if tid == self.selected:
            return
        self.selected = tid
        self.detail = None
        self.sel_set = None
        self.render_detail()
        self.want_detail(now=True)

    # ------------------------------------------------------------------ events and polling
    def on_event(self, ev):
        kind = ev.get("t")
        tab = self.tab
        if kind == "tour_call":
            first = self.call is None or self.call["set"]["id"] != ev["set"]["id"] or \
                self.call["tournament"]["id"] != ev["tournament"]["id"]
            self.call = ev
            self.call_end = time.monotonic() + float(ev.get("deadline") or 0)
            self._show_call()
            if first:
                self.selected = ev["tournament"]["id"]
                self.want_detail(now=True)
                tab._come_forward(("tour", ev["tournament"]["id"], ev["set"]["id"], time.monotonic() // 60))
        elif kind == "tour_call_end":
            c = self.call
            if c is not None and c["set"]["id"] == ev.get("set") and c["tournament"]["id"] == ev.get("tournament"):
                self.call = None
                self.call_end = None
                if tab.bar_text.get() == self._bar_line:     # (the bar still shows the call: take it down)
                    tab.hide_bar()
            text = tour_text.call_end_text(ev)
            if text:
                tab.status(text)
            if ev.get("tournament") == self.selected:
                self.want_detail(now=True)
        elif kind == "tour_changed":
            if self.page_shown:
                self.want_list()
            if ev.get("id") == self.selected and (self.page_shown or self.call is not None):
                self.want_detail()
        elif kind == "tour_access":                # the server's owner made this player a host, or took it back
            self._access(ev)
            self.render_list()
            if self.page_shown:
                self.want_list(now=True)
            if self.selected:
                self.want_detail(now=True)             # (an admin manages every tournament)
        elif kind == "tour_notice":
            tab.status(tour_text.notice_text(ev))
            if (ev.get("tournament") or {}).get("id") == self.selected:
                self.want_detail(now=True)
        elif kind == "match_found" and self.call is not None and ev.get("origin") == "tournament":
            self.call = None                    # (the set started: the match card takes over)
            self.call_end = None

    def tick(self):
        now = time.monotonic()
        if self.client() is None:
            return
        if self._list_due is not None and now >= self._list_due and self.page_shown:
            self._list_due = None
            self._fetch_list()
        if self._detail_due is not None and now >= self._detail_due:
            self._detail_due = None
            self._fetch_detail()
        if self.call is not None:
            if self.showing_call():
                self._bar_line = self.call_text()              # (the countdown)
                self.tab.bar_text.set(self._bar_line)
            elif not self.tab.view._bar_on:
                self._show_call()                              # (another question took the bar and is gone now)

    def showing_call(self):
        """Is the tab's question bar showing the call right now (not another question that came after it)?"""
        return self.call is not None and self._bar_line is not None and self.tab.bar_text.get() == self._bar_line

    def _access(self, d):
        """can_create and create_hint of a tour_list or a tour_access (create_hint: servers from 1.1.3 on, optional)."""
        self.can_create = bool(d.get("can_create"))
        hint = d.get("create_hint")
        self.create_hint = "".join(ch for ch in hint if ch.isprintable()).strip()[:200] if isinstance(hint, str) else ""
        self.listed = True

    def create_hint_text(self):
        """The line shown in place of Create... when this player may not create tournaments here: the server's own
        text as it is, else ours. None: no line (may create, a guest, not known yet)."""
        c = self.client()
        if self.can_create or not self.listed or c is None or (c.me or {}).get("guest"):
            return None
        return self.create_hint or t("Only tournament hosts can create tournaments. Ask the server's owner for a host "
                                     "slot.")

    def reset(self):
        """Logged out / disconnected."""
        self.can_create = self.listed = False
        self.create_hint = ""
        self.rows = []
        self.detail = None
        self.selected = None
        self.sel_set = None
        self.call = None
        self.call_end = None
        self.page_shown = False
        self.render_list()
        self.render_detail()

    # ------------------------------------------------------------------ the call ("Your tournament set is ready")
    def left(self):
        return max(0.0, (self.call_end or 0) - time.monotonic()) if self.call_end else 0.0

    def call_text(self):
        ev = self.call or {}
        info = dict(ev.get("set") or {})
        opp = (ev.get("opponent") or {}).get("name") or "?"
        parts = [t("Your tournament set is ready"), (ev.get("tournament") or {}).get("name") or "",
                 tour_text.round_label(info), t("vs {name}", name=opp),
                 t("best of {best}", best=ev.get("best_of", 3))]
        acc = ev.get("accepted") or [False, False]
        if acc[0]:
            parts.append(t("accepted -- waiting for {name}...", name=opp))
        else:
            parts.append(t("accept within {seconds} s", seconds=int(self.left() + 0.99)))
        return " -- ".join(p for p in parts if p)

    def _show_call(self):
        ev = self.call
        acc = (ev.get("accepted") or [False, False])[0]
        buttons = [] if acc else [(t("Accept"), self.accept, "cross")]
        self._bar_line = self.call_text()
        self.tab.show_bar(self._bar_line, buttons)

    def accept(self):
        ev, c = self.call, self.client()
        if ev is None or c is None:
            return
        self.tab.call(c.tour_accept, ev["tournament"]["id"], ev["set"]["id"],
                      then=lambda _r: self.tab.status(t("Accepted. Waiting for your opponent...")))

    # ------------------------------------------------------------------ actions
    def _summary(self):
        if self.detail is not None:
            return self.detail
        return next((r for r in self.rows if r["id"] == self.selected), None)

    def _act(self, fn, *args, done_text=None):
        def done(d):
            if isinstance(d, dict) and d.get("id") == self.selected:
                self.detail = d
                self.render_detail()
            self.want_list(now=True)
            if done_text:
                self.tab.status(done_text)
        self.tab.call(fn, *args, then=done)

    def do_join(self):
        c = self.client()
        if c is not None and self.selected:
            self._act(c.tour_join, self.selected, done_text=t("You are signed up."))

    def do_leave(self):
        c, s = self.client(), self._summary()
        if c is None or s is None:
            return
        if s.get("state") == "running" and not self.tab.ask_yes_no(
                t("Withdraw"), t("Withdraw from {name}? You are out of the tournament.", name=s["name"]),
                parent=self.tab.parent):
            return
        self._act(c.tour_leave, self.selected, done_text=t("You left the tournament."))

    def do_checkin(self):
        c = self.client()
        if c is not None and self.selected:
            self._act(c.tour_checkin, self.selected, done_text=t("You are checked in."))

    def do_start(self):
        c, s = self.client(), self._summary()
        if c is None or s is None:
            return
        if self.tab.ask_yes_no(t("Start now"), t("Start {name} now, with the players who are in?", name=s["name"]),
                               parent=self.tab.parent):
            self._act(c.tour_admin, self.selected, "start")

    def do_cancel(self):
        c, s = self.client(), self._summary()
        if c is None or s is None:
            return
        if self.tab.ask_yes_no(t("Cancel tournament"), t("Cancel {name}? Nobody can play it any more.",
                                                         name=s["name"]), parent=self.tab.parent):
            self._act(c.tour_admin, self.selected, "cancel")

    def _set_row(self):
        b = (self.detail or {}).get("bracket") or {}
        return next((x for x in b.get("sets") or () if x["id"] == self.sel_set), None)

    def do_report(self, side):
        c, row = self.client(), self._set_row()
        if c is None or row is None:
            return
        name = (row.get("p") or ["?", "?"])[side] or "?"
        op = "override" if row.get("state") == "done" else "report"
        if self.tab.ask_yes_no(t("Report a result"), t("{name} wins set {set}?", name=name, set=row["id"]),
                               parent=self.tab.parent):
            tid = self.selected
            self.tab.call(lambda: c.tour_admin(tid, op, set=row["id"], winner=side), then=self._admin_done)

    def do_reset(self):
        c, row = self.client(), self._set_row()
        if c is None or row is None:
            return
        if self.tab.ask_yes_no(t("Reset set"), t("Reset set {set}? It is played again from 0-0.", set=row["id"]),
                               parent=self.tab.parent):
            tid = self.selected
            self.tab.call(lambda: c.tour_admin(tid, "reset", set=row["id"]), then=self._admin_done)

    def do_dq(self):
        c, s = self.client(), self._summary()
        if c is None or s is None:
            return
        row = self._set_row()
        guess = next((n for n in (row or {}).get("p") or () if n), "") if row else ""
        name = self.tab.ask_string(t("Disqualify"), t("Disqualify which player (name)?"), initialvalue=guess,
                                   parent=self.tab.parent)
        if name:
            tid = self.selected
            self.tab.call(lambda: c.tour_admin(tid, "dq", player=name.strip()), then=self._admin_done)

    def _admin_done(self, d):
        if isinstance(d, dict) and d.get("id") == self.selected:
            self.detail = d
            self.render_detail()
        self.want_list(now=True)

    def do_create(self):
        if self.client() is None:
            return
        create_window(self)

    def create(self, fields, window=None):
        """The Create window's values -> tour_create; selects the new tournament."""
        c = self.client()
        if c is None:
            return

        def done(d):
            self.selected = d["id"]
            self.detail = d
            self.render_detail()
            self.want_list(now=True)
            self.tab.status(t("Tournament {name} created.", name=d["name"]))
            if window is not None:
                try:
                    window.destroy()
                except tk.TclError:
                    pass
        self.tab.call(lambda: c.tour_create(fields["name"], fields["format"], fields["set_wins"], fields["start"],
                                            fields["max_players"], fields["checkin_minutes"], fields["seeding"]),
                      then=done)

    def select_set(self, sid):
        self.sel_set = sid if sid != self.sel_set else None
        self.render_detail(redraw=True)

    # ------------------------------------------------------------------ spectating (docs/SPECTATE.md "Tournaments")
    def watchable_set(self):
        """The bracket set clicked on, if its game is being played and can be watched (the server's "watch") and
        this player is not one of its two: its id, else None."""
        s, row = self._summary(), self._set_row()
        if s is None or row is None or s.get("state") != "running" or row.get("live") != "playing" or \
                not row.get("watch"):
            return None
        me = ((self.tab.client.me or {}).get("name") if self.tab.client is not None else None) or ""
        if me and me in (row.get("p") or ()):
            return None
        return row["id"]

    def do_watch(self):
        sid = self.watchable_set()
        if sid and self.selected:
            self.tab.spec.watch_tour(self.selected, sid)

    # ------------------------------------------------------------------ drawing
    def render_list(self):
        pg = self.page
        if pg is None:
            return
        tv = pg["tree"]
        try:
            keep = tv.selection()
            tv.delete(*tv.get_children())
        except tk.TclError:
            return
        for r in self.rows:
            tag = r["state"]
            you = r.get("you") or {}
            name = r["name"] + ("  *" if you.get("entrant") else "")
            tv.insert("", "end", iid=r["id"], values=(name, tour_text.state_text(r["state"]),
                                                      f"{r['players']}/{r['max_players']}", tour_text.when_text(r)),
                      tags=(tag,))
        for iid in keep or ([self.selected] if self.selected else []):
            if tv.exists(iid):
                tv.selection_set(iid)
        if self.count_var is not None:
            self.count_var.set(str(len(self.rows)) if self.rows else t("none yet"))
        state = "normal" if self.can_create else "disabled"
        pg["create"].configure(state=state)
        hint = self.create_hint_text()
        if hint:                                    # (instead of a Create button that can never be used)
            pg["create"].pack_forget()
            pg["hint"].configure(text=hint)
            pg["hint"].grid()
        else:
            pg["hint"].grid_remove()
            if not pg["create"].winfo_manager():
                pg["create"].pack(side="left", before=pg["refresh"])
        self.render_detail()

    def render_detail(self, redraw=True):
        pg = self.page
        if pg is None:
            return
        s = self._summary()
        try:
            self._render_info(pg, s)
            spec = getattr(self.tab, "spec", None)
            if spec is not None:
                spec.set_actions()             # (the Watch button: the selected set's game, if it can be watched)
            if redraw and self.bracket is not None:
                self.bracket.draw(self.detail if s is not None and self.detail is not None else None, self.sel_set)
        except tk.TclError:
            return

    def _render_info(self, pg, s):
        btn = pg["buttons"]
        for b in btn.values():
            b.grid_remove()
        if s is None:
            pg["title"].configure(text=t("No tournament selected"))
            pg["info"].configure(text=t("Pick one in the list, or create one."))
            pg["you"].configure(text="")
            pg["players"].configure(text="")
            pg["standings"].configure(text="")
            return
        pg["title"].configure(text=s["name"])
        lines = [tour_text.format_text(s) + "  ·  " + tour_text.state_text(s["state"]) + "  ·  " +
                 tour_text.when_text(s)]
        extra = [t("organizer {name}", name=s.get("organizer") or "?"),
                 t("{players} of {max} players", players=s["players"], max=s["max_players"]),
                 tour_text.seeding_text(s.get("seeding"))]
        if s.get("checkin_minutes"):
            extra.append(t("check-in from {time}", time=stamp(s.get("checkin_opens") or 0)))
        if s.get("rated"):
            extra.append(t("rated"))
        lines.append("  ·  ".join(extra))
        if s.get("champion"):
            lines.append(t("Champion: {name}", name=s["champion"]))
        pg["info"].configure(text="\n".join(lines))
        you = s.get("you") or {}
        st = s["state"]
        if you.get("entrant"):
            if you.get("dq"):
                ytext = t("You are out: {why}.", why=tour_text.dq_text(you["dq"]))
            elif you.get("place"):
                ytext = t("You finished {place}.", place=tour_text.place_text(you["place"]))
            elif st == "checkin" and not you.get("checked_in"):
                ytext = t("You are signed up. Check in now, or you are not in the bracket.")
            elif st in ("signup", "checkin"):
                ytext = t("You are signed up.") + (" " + t("Checked in.") if you.get("checked_in") else "")
            elif st == "running" and you.get("set"):
                ytext = t("Your next set: {set}.", set=you["set"])
            elif st == "running":
                ytext = t("You are in. Your next set is called here when its players are known.")
            else:
                ytext = ""
        else:
            ytext = "" if st not in ("signup", "checkin") else (
                t("This tournament is for another build of the game.") if not you.get("build_ok", True) else "")
        pg["you"].configure(text=ytext)
        ents = (self.detail or {}).get("entrants") or []
        if ents:
            pg["players"].configure(text=t("Players: {list}", list=", ".join(
                (f"{e['seed']}. " if e.get("seed") else "") + e["name"] + (" (" + tour_text.dq_text(e["dq"]) + ")"
                                                                         if e.get("dq") else "")
                for e in ents)))
        else:
            pg["players"].configure(text="")
        stand = (self.detail or {}).get("standings") or []
        pg["standings"].configure(text="  ".join(f"{r['place']}. {r['name']}" for r in stand[:8]) if stand else "")
        show = []
        if st in ("signup", "checkin"):
            show.append("leave" if you.get("entrant") else "join")
            if st == "checkin" and you.get("entrant") and not you.get("checked_in"):
                show.append("checkin")
        elif st == "running" and you.get("entrant") and not you.get("dq") and not you.get("place"):
            show.append("withdraw")
        if s.get("can_manage") and st in ("signup", "checkin"):
            show.append("start")
        if s.get("can_manage") and st in ("signup", "checkin", "running"):
            show.append("cancel")
        for i, key in enumerate(show):
            btn[key].grid(row=0, column=i, padx=(0, self.tab.view.px(6)), sticky="w")
        row = self._set_row() if st == "running" else None
        manage = bool(s.get("can_manage")) and row is not None
        for key in ("win0", "win1", "reset", "dq"):
            b = pg["set_tools"][key]
            b.configure(state="normal" if manage else "disabled")
        if row is not None:
            names = [n or "-" for n in row.get("p") or ["-", "-"]]
            pg["set_tools"]["win0"].configure(text=t("{name} wins", name=names[0]))
            pg["set_tools"]["win1"].configure(text=t("{name} wins", name=names[1]))
            pg["set_label"].configure(text=tour_text.set_line(row, (self.detail or {}).get("bracket") or {}))
        else:
            pg["set_tools"]["win0"].configure(text=t("Side 1 wins"))
            pg["set_tools"]["win1"].configure(text=t("Side 2 wins"))
            pg["set_label"].configure(text=t("Click a set in the bracket.") if s.get("can_manage") and
                                      st == "running" else "")


# ====================================================================== the page
def build_page(view, page):
    tab, px = view.tab, view.px
    ctl = tab.tours
    ctl.count_var = tk.StringVar(page, value="")
    page.columnconfigure(0, weight=2)
    page.columnconfigure(1, weight=3)
    page.rowconfigure(1, weight=1)
    pg = {}
    lc = view.card(page, pad=12)
    lc.grid(row=0, column=0, sticky="nsew", padx=(0, px(10)))
    lc.columnconfigure(0, weight=1)
    lc.rowconfigure(2, weight=1)
    head, tools = view.section_head(lc, t("Tournaments").upper(), ctl.count_var)
    head.grid(row=0, column=0, sticky="we", pady=(0, px(6)))
    pg["create"] = ttk.Button(tools, text=t("Create..."), style="Card.Small.TButton", state="disabled",
                              command=ctl.do_create)
    pg["create"].pack(side="left")
    pg["refresh"] = ttk.Button(tools, text=t("Refresh"), style="Card.Small.TButton", command=lambda: ctl.shown())
    pg["refresh"].pack(side="left", padx=(px(6), 0))
    # who may not create tournaments here reads why (and how to become a host) where Create... would be
    pg["hint"] = view.wrap(ttk.Label(lc, text="", style="Card.Muted.TLabel", justify="left"), lc, 30)
    pg["hint"].grid(row=1, column=0, sticky="w", pady=(0, px(6)))
    pg["hint"].grid_remove()
    fr = view.body(lc)
    fr.grid(row=2, column=0, sticky="nsew")
    fr.columnconfigure(0, weight=1)
    fr.rowconfigure(0, weight=1)
    tv = ttk.Treeview(fr, columns=[c for c, _h, _w in LIST_COLUMNS], show="headings", height=4,
                      style="Lobby.Treeview", selectmode="browse")
    for c, h, w in LIST_COLUMNS:
        tv.heading(c, text=tr(h).upper(), anchor="w")
        tv.column(c, width=px(w), minwidth=px(min(w, 50)), anchor="w")
    tv.grid(row=0, column=0, sticky="nsew")
    sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview)
    sb.grid(row=0, column=1, sticky="ns", padx=(px(4), 0))
    tv.configure(yscrollcommand=sb.set)
    tv.tag_configure("running", foreground=C["ok"])
    tv.tag_configure("finished", foreground=C["muted"])
    tv.tag_configure("cancelled", foreground=C["faint"])
    tv.bind("<<TreeviewSelect>>", lambda _e: ctl.select(tv.selection()[0]) if tv.selection() else None)
    pg["tree"] = tv

    dc = view.card(page, pad=12)
    dc.grid(row=0, column=1, sticky="nsew")
    dc.columnconfigure(0, weight=1)
    pg["title"] = ttk.Label(dc, text="", style="Card.H2.TLabel")
    pg["title"].grid(row=0, column=0, sticky="w")
    pg["info"] = view.wrap(ttk.Label(dc, text="", style="Card.Muted.TLabel", justify="left"), dc, 30)
    pg["info"].grid(row=1, column=0, sticky="w", pady=(px(2), 0))
    pg["you"] = view.wrap(ttk.Label(dc, text="", style="Card.Accent.TLabel", justify="left"), dc, 30)
    pg["you"].grid(row=2, column=0, sticky="w", pady=(px(4), 0))
    pg["players"] = view.wrap(ttk.Label(dc, text="", style="Card.Faint.TLabel", justify="left"), dc, 30)
    pg["players"].grid(row=3, column=0, sticky="w", pady=(px(4), 0))
    row = view.body(dc)
    row.grid(row=4, column=0, sticky="w", pady=(px(10), 0))
    pg["buttons"] = {}
    for key, label, cmd, style in (
            ("join", t("Sign up"), ctl.do_join, "Card.Accent.TButton"),
            ("leave", t("Leave"), ctl.do_leave, "Card.TButton"),
            ("checkin", t("Check in"), ctl.do_checkin, "Card.Accent.TButton"),
            ("withdraw", t("Withdraw"), ctl.do_leave, "Card.TButton"),
            ("start", t("Start now"), ctl.do_start, "Card.TButton"),
            ("cancel", t("Cancel tournament"), ctl.do_cancel, "Card.Danger.TButton")):
        pg["buttons"][key] = ttk.Button(row, text=label, style=style, command=cmd)

    bc = view.card(page, pad=10)
    bc.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(px(10), 0))
    bc.columnconfigure(0, weight=1)
    bc.rowconfigure(2, weight=1)
    head, tools = view.section_head(bc, t("Bracket").upper())
    head.grid(row=0, column=0, sticky="we")
    # spectating: the clicked set's game, live in this PC's game (docs/SPECTATE.md "Tournaments")
    pg["watch"] = ttk.Button(tools, text=t("Watch"), style="Card.Small.TButton", state="disabled",
                             command=ctl.do_watch)
    pg["watch"].pack(side="left", padx=(px(6), 0))
    pg["set_tools"] = {}
    for key, label, cmd, style in (("win0", t("Side 1 wins"), lambda: ctl.do_report(0), "Card.Small.TButton"),
                                   ("win1", t("Side 2 wins"), lambda: ctl.do_report(1), "Card.Small.TButton"),
                                   ("reset", t("Reset set"), ctl.do_reset, "Card.Small.TButton"),
                                   ("dq", t("Disqualify..."), ctl.do_dq, "Card.Small.TButton")):
        b = ttk.Button(tools, text=label, style=style, state="disabled", command=cmd)
        b.pack(side="left", padx=(px(6), 0))
        pg["set_tools"][key] = b
    sub = view.body(bc)
    sub.grid(row=1, column=0, sticky="we", pady=(px(2), px(4)))
    sub.columnconfigure(1, weight=1)
    pg["set_label"] = ttk.Label(sub, text="", style="Card.Faint.TLabel")
    pg["set_label"].grid(row=0, column=0, sticky="w")
    pg["standings"] = ttk.Label(sub, text="", style="Card.Bold.TLabel")
    pg["standings"].grid(row=0, column=1, sticky="e")
    ctl.bracket = BracketView(view, bc, ctl.select_set)
    ctl.bracket.frame.grid(row=2, column=0, sticky="nsew")
    ctl.page = pg
    ctl.render_list()


class BracketView:
    """The bracket on a canvas (see the module doc)."""

    def __init__(self, view, parent, on_click):
        self.view = view
        self.px = view.px
        self.on_click = on_click
        self.th = view.th
        self.frame = view.body(parent)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self.frame, bg=C["surface"], highlightthickness=0, height=self.px(260), takefocus=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(self.frame, orient="vertical", command=self.canvas.yview)
        ys.grid(row=0, column=1, sticky="ns")
        xs = ttk.Scrollbar(self.frame, orient="horizontal", command=self.canvas.xview)
        xs.grid(row=1, column=0, sticky="we")
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.boxes = {}                 # set id -> (x0, y0, x1, y1): what was drawn where (tests, clicks)
        self.texts = []                 # every text drawn (tests)

    def _text(self, x, y, text, **kw):
        self.texts.append(text)
        return self.canvas.create_text(x, y, text=text, **kw)

    def draw(self, full, selected=None):
        cv, px = self.canvas, self.px
        cv.delete("all")
        self.boxes = {}
        self.texts = []
        fonts = self.th.fonts
        if not full:
            self._text(px(12), px(14), t("Pick a tournament to see its bracket."), anchor="w", fill=C["faint"],
                       font=fonts["body"])
            cv.configure(scrollregion=(0, 0, px(300), px(40)))
            return
        b = full.get("bracket")
        if not b:
            text = t("The bracket is drawn when the tournament starts.") if full.get("state") in ("signup", "checkin") \
                else t("This tournament had no bracket.")
            self._text(px(12), px(14), text, anchor="w", fill=C["faint"], font=fonts["body"])
            cv.configure(scrollregion=(0, 0, px(300), px(40)))
            return
        info = {"format": b["format"], "rounds": b["rounds"], "losers_rounds": b["losers_rounds"]}
        sets = {s["id"]: s for s in b["sets"]}
        W, H, gx, gy = px(178), px(44), px(34), px(12)
        top = px(26)
        ys = {}

        def src_y(s, bracket):
            refs = [ref for kind, ref in s.get("src") or () if kind == "win"]
            return [ys[r] for r in refs if r in ys and sets.get(r, {}).get("bracket") == bracket]

        # sources are not in the public view: rebuild the layout from the ids (round, index)
        def layout(bracket, rounds):
            out = {}
            for r in range(1, rounds + 1):
                col = sorted((s for s in sets.values() if s["bracket"] == bracket and s["round"] == r),
                             key=lambda s: s["index"])
                prev = sorted((s for s in sets.values() if s["bracket"] == bracket and s["round"] == r - 1),
                              key=lambda s: s["index"])
                for s in col:
                    i = s["index"]
                    if r == 1 or not prev:
                        y = (i - 1) * (H + gy)
                    elif len(prev) == 2 * len(col):            # two sources each: centred between them
                        y = (out[prev[2 * i - 2]["id"]] + out[prev[2 * i - 1]["id"]]) / 2.0
                    else:                                      # one source in this bracket (a losers drop-in round)
                        y = out[prev[i - 1]["id"]]
                    out[s["id"]] = y
            return out
        wy = layout("W", b["rounds"])
        ly = layout("L", b["losers_rounds"]) if b["losers_rounds"] else {}
        w_height = (max(wy.values()) + H) if wy else 0
        l_top = top + w_height + px(42)
        col_x = lambda r: px(8) + (r - 1) * (W + gx)          # noqa: E731
        double = b["format"] == "double"
        # round names over the columns
        for r in range(1, b["rounds"] + 1):
            self._text(col_x(r), px(10), tour_text.round_label(dict(info, bracket="W", round=r)).upper(),
                       anchor="w", fill=C["muted"], font=fonts["caps"])
        if double:
            for r in range(1, b["losers_rounds"] + 1):
                self._text(col_x(r), l_top - px(16), tour_text.round_label(dict(info, bracket="L", round=r)).upper(),
                           anchor="w", fill=C["muted"], font=fonts["caps"])
            gx0 = b["rounds"] + 1
            self._text(col_x(gx0), px(10), t("Grand final").upper(), anchor="w", fill=C["gold"], font=fonts["caps"])
        pos = {}
        for sid, y in wy.items():
            pos[sid] = (col_x(sets[sid]["round"]), top + y)
        for sid, y in ly.items():
            pos[sid] = (col_x(sets[sid]["round"]), l_top + y)
        if double:
            fy = top + wy.get(f"W{b['rounds']}-1", 0)
            pos["GF1"] = (col_x(b["rounds"] + 1), fy)
            pos["GF2"] = (col_x(b["rounds"] + 2), fy)
        # connectors: each set to the set its winner goes to (same bracket, next round)
        for sid, (x, y) in pos.items():
            s = sets[sid]
            nxt = self._next_of(s, sets, b)
            if nxt is None or nxt not in pos or self._hidden(s):
                continue
            nx, ny = pos[nxt]
            mx = x + W + gx / 2.0
            cv.create_line(x + W, y + H / 2.0, mx, y + H / 2.0, mx, ny + H / 2.0, nx, ny + H / 2.0,
                           fill=C["line_hi"], width=1)
        for sid, (x, y) in pos.items():
            s = sets[sid]
            if self._hidden(s):
                continue
            self._box(s, x, y, W, H, selected == sid, info)
        bbox = cv.bbox("all") or (0, 0, px(300), px(100))
        cv.configure(scrollregion=(0, 0, bbox[2] + px(10), bbox[3] + px(10)))

    @staticmethod
    def _hidden(s):
        """A first-round bye or an empty set is not drawn (the player simply starts in the next round)."""
        return s["state"] == "done" and (s.get("reason") in ("empty", "skipped") or (
            s.get("reason") == "bye" and s["round"] == 1 and s["bracket"] in ("W", "L")))

    @staticmethod
    def _next_of(s, sets, b):
        """The set this set's winner plays next (drawing only)."""
        if s["bracket"] == "W":
            if s["round"] < b["rounds"]:
                return f"W{s['round'] + 1}-{(s['index'] + 1) // 2}"
            return "GF1" if b["format"] == "double" else None
        if s["bracket"] == "L":
            r = s["round"]
            if r == b["losers_rounds"]:
                return "GF1"
            if r % 2 == 1:                       # into the drop-in round: the same index
                return f"L{r + 1}-{s['index']}"
            return f"L{r + 1}-{(s['index'] + 1) // 2}"
        if s["id"] == "GF1" and sets.get("GF2", {}).get("state") != "done":
            return "GF2"
        return None

    def _box(self, s, x, y, W, H, selected, info):
        cv, px, fonts = self.canvas, self.px, self.th.fonts
        live = s.get("live")
        border = {"playing": C["accent"], "called": C["warn"], "attention": C["bad"]}.get(live, C["line_hi"])
        if selected:
            border = C["info"]
        fill = C["raised"] if s["state"] != "pending" else C["surface"]
        tag = "set:" + s["id"]
        cv.create_rectangle(x, y, x + W, y + H, fill=fill, outline=border, width=3 if selected or live else 1,
                            tags=("set", tag))
        self.boxes[s["id"]] = (x, y, x + W, y + H)
        half = H / 2.0
        names = s.get("p") or [None, None]
        seeds = s.get("seeds") or [None, None]
        known = s.get("known") or [False, False]
        score = s.get("score")
        wins = s.get("wins")
        for side in (0, 1):
            yy = y + half * side + half / 2.0
            n = names[side]
            if n is None:
                n = t("bye") if known[side] else t("waiting")
                col = C["faint"]
            elif s["state"] == "done" and s.get("winner") is not None:
                col = C["text"] if s["winner"] == side else C["faint"]
            else:
                col = C["text"]
            text = (f"{seeds[side]}  " if seeds[side] else "") + n
            self._text(x + px(8), yy, text, anchor="w", fill=col, font=fonts["bold"] if col == C["text"]
                       else fonts["body"], tags=("set", tag))
            val = None
            if isinstance(wins, list) and live == "playing":
                val = str(wins[side])
            elif isinstance(score, list) and len(score) == 2:
                val = str(score[side])
            elif s["state"] == "done" and s.get("winner") is not None:
                val = "✓" if s["winner"] == side else "-"      # (a walkover / organizer's result: no score)
            if val is not None:
                win = s["state"] == "done" and s.get("winner") == side
                self._text(x + W - px(8), yy, val, anchor="e", fill=C["ok"] if win else C["muted"],
                           font=fonts["num"], tags=("set", tag))
        cv.create_line(x + px(4), y + half, x + W - px(4), y + half, fill=C["line"], tags=("set", tag))
        badge = {"playing": t("LIVE"), "called": t("CALLED"), "attention": t("NEEDS THE ORGANIZER")}.get(live)
        if badge is None and s["state"] == "done" and s.get("reason") in ("no_show", "dq", "organizer", "forfeit",
                                                                            "bye"):
            badge = tour_text.set_reason_text(s["reason"]).upper()
        if badge:
            col = {"playing": C["accent"], "called": C["warn"], "attention": C["bad"]}.get(live, C["faint"])
            self._text(x + W, y - px(2), badge, anchor="se", fill=col, font=fonts["caps"])
        cv.tag_bind(tag, "<Button-1>", lambda _e, sid=s["id"]: self.on_click(sid))


# ====================================================================== the call card
def visual_call(view, v):
    """'Your tournament set is ready': the tournament, the round, the opponent, the countdown ring."""
    tab, px = view.tab, view.px
    ctl = tab.tours
    ev = ctl.call or {}
    info = dict(ev.get("set") or {})
    v.columnconfigure(0, weight=1)
    left = view.body(v)
    left.grid(row=0, column=0, sticky="nw")
    left.columnconfigure(1, weight=1)
    head = view.body(left)
    head.grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(head, text=t("Your tournament set is ready").upper(), style="Card.Caps.TLabel").pack(side="left")
    ttk.Label(head, text=t("TOURNAMENT"), style="Card.PillGold.TLabel").pack(side="left", padx=(px(8), 0))
    sub = "  ·  ".join(x for x in ((ev.get("tournament") or {}).get("name"), tour_text.round_label(info),
                                   t("best of {best}", best=ev.get("best_of", 3))) if x)
    ttk.Label(left, text=sub, style="Card.Bold.TLabel").grid(row=1, column=0, columnspan=2, sticky="w",
                                                             pady=(px(4), px(8)))
    opp = dict(ev.get("opponent") or {})
    view._opponent_row(left, opp, 2)
    notes = []
    sc = ev.get("score") or [0, 0]
    if any(sc):
        notes.append(t("The set goes on at {mine}-{theirs}.", mine=sc[0], theirs=sc[1]))
    elif ev.get("replay"):
        notes.append(t("The set is called again."))
    acc = ev.get("accepted") or [False, False]
    if acc[0]:
        notes.append(t("Accepted. Waiting for {name}...", name=opp.get("name") or "?"))
    elif acc[1]:
        notes.append(t("{name} has accepted.", name=opp.get("name") or "?"))
    elif not ev.get("opponent_online", True):
        notes.append(t("{name} is not online yet.", name=opp.get("name") or "?"))
    if notes:
        ttk.Label(left, text="  ".join(notes), style="Card.Accent.TLabel").grid(row=4, column=0, columnspan=2,
                                                                               sticky="w", pady=(px(8), 0))
    view.ring = theme.CountdownRing(v, size=92, width=8)
    view.ring.grid(row=0, column=1, sticky="ne", padx=(px(12), 0))
    view.ring_source = lambda: (ctl.left(), float(ev.get("noshow") or 300))
    view._update_ring()


# ====================================================================== the create window
def create_window(ctl):
    tab = ctl.tab
    view = tab.view
    px = view.px
    w = tab.new_window(tab.parent)
    w.title(t("Create tournament"))
    try:
        w.configure(bg=C["bg"])
    except tk.TclError:
        pass
    card = view.card(w, pad=18)
    card.pack(fill="both", expand=True, padx=px(10), pady=px(10))
    card.columnconfigure(1, weight=1)
    ttk.Label(card, text=t("Create tournament"), style="Card.H2.TLabel").grid(row=0, column=0, columnspan=2,
                                                                            sticky="w", pady=(0, px(10)))
    me = (tab.client.me or {}) if tab.client else {}
    vars_ = {"name": tk.StringVar(w, value=t("{name}'s tournament", name=me.get("name", "?"))),
             "format": tk.StringVar(w, value=tr(FORMAT_CHOICES[1][0])),
             "sets": tk.StringVar(w, value=tr(SET_CHOICES[0][0])),
             "start": tk.StringVar(w, value=tr(START_CHOICES[2][0])),
             "at": tk.StringVar(w, value=""),
             "players": tk.StringVar(w, value="16"),
             "checkin": tk.StringVar(w, value=tr(CHECKIN_CHOICES[2][0])),
             "seeding": tk.StringVar(w, value=tr(SEED_CHOICES[0][0]))}
    rows = (("name", t("Name"), None), ("format", t("Format"), [tr(x) for x, _v in FORMAT_CHOICES]),
            ("sets", t("Sets"), [tr(x) for x, _v in SET_CHOICES]),
            ("start", t("Starts"), [tr(x) for x, _v in START_CHOICES]),
            ("at", t("or at (HH:MM)"), None),
            ("players", t("Players at most"), [str(x) for x in PLAYER_CHOICES]),
            ("checkin", t("Check-in"), [tr(x) for x, _v in CHECKIN_CHOICES]),
            ("seeding", t("Seeding"), [tr(x) for x, _v in SEED_CHOICES]))
    widgets = {}
    for i, (key, label, values) in enumerate(rows):
        ttk.Label(card, text=label, style="Card.Muted.TLabel").grid(row=i + 1, column=0, sticky="w", pady=px(3),
                                                                   padx=(0, px(10)))
        if values is None:
            e = ttk.Entry(card, textvariable=vars_[key], style="Card.TEntry", width=28)
        else:
            e = ttk.Combobox(card, textvariable=vars_[key], values=values, state="readonly", style="Card.TCombobox",
                             width=30)
        e.grid(row=i + 1, column=1, sticky="we", pady=px(3))
        widgets[key] = e
    note = ttk.Label(card, text=t("A set is played like a casual set with the in-game select; results come from the "
                                  "games. Players who do not accept a called set in time are out."),
                     style="Card.Faint.TLabel", wraplength=px(360), justify="left")
    note.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(px(8), 0))
    err = ttk.Label(card, text="", style="Card.error.TLabel", wraplength=px(360), justify="left")
    err.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="w")

    def pick(choices, key):
        shown = vars_[key].get()
        return next((v for label, v in choices if tr(label) == shown), choices[0][1])

    def fields():
        name = vars_["name"].get().strip()
        if len(name) < 3:
            err.configure(text=t("The name needs 3 characters or more."))
            return None
        start = parse_clock(vars_["at"].get())
        if vars_["at"].get().strip() and start is None:
            err.configure(text=t("Write the start time as HH:MM, e.g. 20:30."))
            return None
        if start is None:
            start = time.time() + 60 * pick(START_CHOICES, "start")
        return {"name": name, "format": pick(FORMAT_CHOICES, "format"), "set_wins": pick(SET_CHOICES, "sets"),
                "start": start, "max_players": int(vars_["players"].get() or 16),
                "checkin_minutes": pick(CHECKIN_CHOICES, "checkin"), "seeding": pick(SEED_CHOICES, "seeding")}

    def create():
        f = fields()
        if f is not None:
            ctl.create(f, w)
    bar = view.body(card)
    bar.grid(row=len(rows) + 3, column=0, columnspan=2, sticky="we", pady=(px(12), 0))
    ttk.Button(bar, text=t("Cancel"), style="Card.TButton", command=w.destroy).pack(side="right")
    ttk.Button(bar, text=t("Create"), style="Card.Accent.TButton", command=create).pack(side="right",
                                                                                        padx=(0, px(8)))
    w.tour_vars = vars_                 # (tests fill them in)
    w.tour_create = create
    w.tour_error = err
    ctl.create_win = w
    return w

