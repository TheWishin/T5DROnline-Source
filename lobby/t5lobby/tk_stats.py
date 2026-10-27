"""The Online tab's Stats page (1.1.5): the community's numbers from the lobby server -- accounts, players, matches,
ranked matches, the last 24 hours -- and every fighter's matches, wins and win rate, all / ranked / casual.

The server answers the read-only `stats` request (server/lobby.py h_stats, store.community_stats) from a cache it
renews every few minutes, so the page asks again at most once a minute by itself (Refresh asks at once). A server
without the request (older than 1.1.5) gets a line saying so. Nothing here changes anything on the server."""
import time
import tkinter as tk
from tkinter import ttk

from . import i18n, tklist
from .i18n import N_, t
from .theme import C

FEW = 30                 # fewer matches than this: the win rate is shown grey (not much to go on yet)
REFRESH_SECONDS = 60.0   # the page asks the server again when shown after this long
MODES = (("all", N_("All")), ("ranked", N_("Ranked")), ("casual", N_("Casual")))
COLUMNS = ("fighter", "matches", "wins", "winrate", "share")
WIDTHS = (170, 90, 80, 110, 90)


def rate(wins, games):
    """Win rate in whole percent, None without games."""
    return round(100 * wins / games) if games else None


def rows_for(fighters, mode, sort="matches"):
    """[(char, games, wins, draws)] of one mode ('all', 'ranked', 'casual'), sorted: 'matches' (most played first),
    'winrate' (best first; fewer than FEW matches after the rest) or 'fighter' (by name, done by the caller)."""
    out = []
    for f in fighters or ():
        try:
            parts = [f["ranked"], f["casual"]] if mode == "all" else [f[mode]]
            g, w, d = (sum(int(p[i]) for p in parts) for i in range(3))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if g:
            out.append((str(f.get("char") or "?"), g, w, d))
    if sort == "winrate":
        out.sort(key=lambda r: (r[1] < FEW, -(r[2] / r[1]), -r[1], r[0]))
    else:
        out.sort(key=lambda r: (-r[1], -r[2], r[0]))
    return out


class StatsPage:
    def __init__(self, view, page):
        self.view = view
        self.tab = tab = view.tab
        px = view.px
        self.data = None
        self.asked = 0.0
        self.sort = "matches"
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        card = view.card(page, pad=12)
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(4, weight=1)
        self.made_var = tk.StringVar(value="")
        head, tools = view.section_head(card, t("Community stats").upper(), self.made_var)
        head.grid(row=0, column=0, sticky="we")
        # the fighters' table's choice (all / ranked / casual) in the card's head row: one row less above the table
        ttk.Label(tools, text=t("Fighters").upper(), style="Card.Caps.TLabel").pack(side="left", padx=(0, px(10)))
        self.mode_var = tk.StringVar(value=MODES[0][0])
        seg = ttk.Frame(tools, style="SegTrack.TFrame", padding=px(3))
        seg.pack(side="left", padx=(0, px(14)))
        for key, text in MODES:
            ttk.Radiobutton(seg, text=t(text), value=key, variable=self.mode_var, style="Seg.TRadiobutton",
                            command=self.fill, takefocus=True).pack(side="left")
        ttk.Button(tools, text=t("Refresh"), style="Card.Small.TButton", command=lambda: self.load(force=True)).pack(
            side="left")

        tiles = view.body(card)
        tiles.grid(row=1, column=0, sticky="we", pady=(px(8), px(8)))
        self.tile_vars = {}
        for i, (key, label) in enumerate((("accounts", N_("Accounts")), ("players", N_("Players")),
                                          ("matches", N_("Matches")), ("ranked", N_("Ranked matches")),
                                          ("day", N_("Last 24 hours")))):
            tiles.columnconfigure(i, weight=1)
            tile = ttk.Frame(tiles, style="Tile.TFrame")
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(4), 0 if i == 4 else px(4)))
            ttk.Label(tile, text=t(label).upper(), style="Tile.Caps.TLabel").pack(anchor="w")
            v = self.tile_vars[key] = tk.StringVar(value="-")
            ttk.Label(tile, textvariable=v, style="Tile.H2.TLabel").pack(anchor="w")
        self.day_sub = tk.StringVar(value="")                 # (the last tile: matches big, players below)
        ttk.Label(tile, textvariable=self.day_sub, style="Tile.Faint.TLabel").pack(anchor="w")

        self.note = ttk.Label(card, style="Card.Faint.TLabel", justify="left", text=t(
            "Win rate per match; a mirror match counts as one win and one loss. Grey: fewer than {count} matches, "
            "not much to go on yet. Click a column to sort.", count=FEW))
        self.note.grid(row=3, column=0, sticky="we", pady=(0, px(6)))
        view.wrap(self.note, card, 30)
        fr, self.tv = view.tree(card, COLUMNS, WIDTHS, height=12, image_col=False, select="none",
                                empty=t("No numbers yet."))
        fr.grid(row=4, column=0, sticky="nsew")
        for c, sort in (("fighter", "fighter"), ("matches", "matches"), ("wins", "matches"), ("winrate", "winrate"),
                        ("share", "matches")):
            self.tv.heading(c, command=lambda s=sort: self.sort_by(s))
            if c != "fighter":
                self.tv.column(c, anchor="e")
                self.tv.heading(c, anchor="e")
        self.tv.tag_configure("few", foreground=C["faint"])

    # ------------------------------------------------------------------ data
    def shown(self):
        """The page came to the front: ask the server unless the numbers are fresh."""
        self.load(force=False)

    def load(self, force=True):
        c = self.tab.client
        if not c:
            return
        if not getattr(c, "has_stats", False):
            self.data = None
            self.made_var.set(t("This lobby server has no stats page yet (it comes with server 1.1.5)."))
            self.fill()
            return
        if not force and self.data is not None and time.monotonic() - self.asked < REFRESH_SECONDS:
            return
        self.asked = time.monotonic()
        self.tab.call(c.stats, then=self._got)

    def _got(self, d):
        if not isinstance(d, dict):
            return
        self.data = d
        self.fill()

    def sort_by(self, sort):
        self.sort = sort
        self.fill()

    def fill(self):
        d = self.data or {}
        try:
            if not self.tv.winfo_exists():
                return
        except tk.TclError:
            return
        n = i18n.num
        for key in ("accounts", "players", "matches", "ranked"):
            self.tile_vars[key].set(n(d[key]) if isinstance(d.get(key), int) else "-")
        if isinstance(d.get("matches_24h"), int):
            self.tile_vars["day"].set(n(d["matches_24h"]))
            self.day_sub.set(t("{matches} matches, {players} players", matches=n(d["matches_24h"]),
                               players=n(d.get("players_24h") or 0)))
        else:
            self.tile_vars["day"].set("-")
            self.day_sub.set("")
        if d.get("made"):
            self.made_var.set(t("as of {when}", when=i18n.stamp(d["made"])))
        mode = self.mode_var.get()
        rows = rows_for(d.get("fighters"), mode, self.sort)
        name = self.tab.table.fighter_name
        if self.sort == "fighter":
            rows.sort(key=lambda r: name(r[0]).lower())
        total = sum(r[1] for r in rows) or 1
        out = []
        for ch, g, w, _d in rows:
            out.append(("st:" + ch, (name(ch), n(g), n(w), f"{rate(w, g)} %", f"{n(100 * g / total, 1)} %"), None,
                        ("few",) if g < FEW else ()))
        tklist.sync(self.tv, out)
        self.view.show_empty(self.tv, not out)


def build_page(view, page):
    """The Stats page in the Online tab's notebook (tk_views._build_lobby)."""
    view.tab.stats = StatsPage(view, page)
    return view.tab.stats
