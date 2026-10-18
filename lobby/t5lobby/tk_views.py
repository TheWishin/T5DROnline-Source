"""The Online tab's screens: the widgets of tk_tab.OnlineTab and how each state of the online flow looks.

The tab (tk_tab.py) keeps the logic and the state -- the lobby client, the match driver, the controller,
the questions it asks. This module builds the widgets it drives (under the same attribute names:
tab.actions, tab.bar, tab.bar_buttons, tab.tv_players ...) and draws the state as one card at a time:

    login       server, name, then Log in / Create account (with the password rules) / Guest
    play        your profile card, Ranked match and Quick match, the character
    search      a turning ring, the time searching, the queue, Stop searching (B)
    bar         a question with its buttons: the found match (ping bars, 15 s ring, Accept (A) /
                Decline (B), the opponent shown after both accepted), a challenge, the result with the
                rematch buttons, "How did the match end?"
    match       in a match: the opponent, ping, input delay, connection, "Your game is running"
    result      the result (win / loss banner, score, rating change, rank up / down, lag check)
    errors      one line on a red banner: what went wrong and what to do

The tab calls refresh() whenever its state may have changed (after every event and server answer),
show_bar() / hide_bar() around its questions, after_event() / after_driver() with what it got.
Colours, fonts and the drawn pieces come from theme.py.
"""
import time
import tkinter as tk
from tkinter import ttk

from . import proto, ranks, theme
from .theme import C

# What the player can do about an error (plain words; matched on the message, lower case).
ERROR_HELP = (
    ("cannot reach", "Check the server address and your internet connection, then try again."),
    ("did not answer", "Check your internet connection, then try again."),
    ("no answer to", "The server is slow or gone; try again in a minute."),
    ("not connected to the lobby", "Log in again."),
    ("certificate does not match", "Ask whoever runs the server for its current fingerprint "
                                   "(\"Server certificate...\")."),
    ("wrong name or password", "Check the spelling, or use \"Forgot password...\"."),
    ("wrong name or recovery code", "Check the name and the code; each code works once."),
    ("someone with that name is online", "Pick another name, or wait a minute if that was you."),
    ("that name belongs to an account", "Log in with that account's password, or pick another name."),
    ("that name is taken", "Pick another name."),
    ("that name is reserved", "Pick another name."),
    ("not accepted by this server", "Update the game to the release this server asks for."),
    ("different build", "You both need the same release of the game."),
    ("lobby protocol", "Update the launcher to the newest release."),
    ("ranked needs an account", "Create an account (free) to play ranked."),
    ("room is full", "Pick another room or create your own."),
    ("saved login has expired", "Log in with your password."),
    ("session expired", "Log in with your password."),
    ("not built", "Build the game on the Build tab first."),
    ("no udp connection", "Allow T5DR Online through the Windows firewall, then search again."),
    ("not even through the relay", "Try again; if it keeps failing, check your firewall or router."),
    ("lost the lobby connection", "Log in again; your settings are kept."),
    ("passwords differ", "Type the same password twice."),
    ("no longer available", "Find a new opponent."),
    ("that match is over", "Find a new opponent."),
    ("could not start", "Check the Play tab: does the game start there?"),
)


def friendly_error(text):
    """'Lobby: wrong name or password' -> 'Wrong name or password. Check the spelling, or use ...'"""
    msg = proto.scrub_addresses(str(text or "")).strip()
    for prefix in ("Lobby error: ", "Lobby: "):
        if msg.startswith(prefix):
            msg = msg[len(prefix):]
    if not msg:
        return ""
    msg = msg[0].upper() + msg[1:]
    low = msg.lower()
    tip = next((t for k, t in ERROR_HELP if k in low), "")
    if tip and tip.lower() not in low:
        msg = msg.rstrip(".") + ". " + tip
    return msg


def _tier_of(info):
    """Tier index of a player / profile / leaderboard row (None for a guest)."""
    if not info or info.get("guest") or (info.get("rank") == "Guest"):
        return None
    t = info.get("tier")
    if isinstance(t, int):
        return t
    return ranks.index(info.get("rank") or "")


class OnlineView:
    def __init__(self, tab):
        self.tab = tab
        self.th = theme.apply(tab.parent)
        self.px = self.th.px
        theme.bind_return_on_buttons(tab.parent)
        self._logged = None
        self._stage = None
        self._bar_on = False
        self._bar_sig = None
        self._bar_kind = None
        self._res_sig = None
        self._prof_sig = None
        self._match_sig = None
        self._anim_id = None
        self._anim_t = time.monotonic()
        self._wraps = []                   # (label, container, margin): wraplength follows the width
        self._wrap_bound = set()
        self.revealed = None               # the opponent once both accepted (match_reveal)
        self.challenger = None
        self.match_ev = None               # match_start of the match being played
        self.game_phase = None
        self.fighters = None               # (p1, p2) once the game says who fights
        self.result_info = None
        self.result_dismissed = True
        self.queue_counts = {}
        self.search_t0 = None
        self.err_var = tk.StringVar(tab.parent, value="")
        self.pw2_var = tk.StringVar(tab.parent, value="")
        self.host_var = tk.StringVar(tab.parent, value="")
        self.ring = None
        self.bar_spinner = None
        self._build()

    # ------------------------------------------------------------------ helpers
    def card(self, parent, style="Card.TFrame", pad=14):
        return ttk.Frame(parent, style=style, padding=self.px(pad))

    def body(self, parent, style="CardBody.TFrame"):
        return ttk.Frame(parent, style=style)

    def wrap(self, label, container, margin=0):
        """The label wraps at the container's width (less `margin` pixels at 96 DPI)."""
        self._wraps.append((label, container, margin))
        key = str(container)
        if key not in self._wrap_bound:
            self._wrap_bound.add(key)
            container.bind("<Configure>", lambda _e, c=container: self._wrap_in(c), add="+")
        return label

    def _wrap_in(self, container):
        w = container.winfo_width()
        if w <= 50:
            return
        for label, cont, margin in self._wraps:
            if cont is container:
                try:
                    want = max(120, w - self.px(margin))
                    if int(str(label.cget("wraplength") or 0)) != want:
                        label.configure(wraplength=want)
                except (tk.TclError, ValueError):
                    pass

    def _on_resize(self, _e=None):
        for label, cont, margin in self._wraps:
            try:
                w = cont.winfo_width()
                if w > 50:
                    label.configure(wraplength=max(120, w - self.px(margin)))
            except tk.TclError:
                pass

    def tree(self, parent, cols, widths, height=6, image_col=True, select="browse"):
        frame = self.body(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tv = ttk.Treeview(frame, columns=cols, show="tree headings" if image_col else "headings", height=height,
                          selectmode=select)
        if image_col:
            tv.heading("#0", text="")
            tv.column("#0", width=self.px(36), minwidth=self.px(36), stretch=False, anchor="center")
        for c, w in zip(cols, widths):
            tv.heading(c, text=c.upper(), anchor="w")
            tv.column(c, width=self.px(w), minwidth=self.px(min(w, 50)), anchor="w")
        tv.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        sb.grid(row=0, column=1, sticky="ns", padx=(self.px(4), 0))
        tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("me", foreground=C["accent_hi"])
        tv.tag_configure("other", foreground=C["faint"])
        tv.tag_configure("closed", foreground=C["muted"])
        return frame, tv

    def section_head(self, parent, title, count_var=None):
        row = self.body(parent)
        row.columnconfigure(2, weight=1)
        ttk.Label(row, text=title, style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        if count_var is not None:
            ttk.Label(row, textvariable=count_var, style="Card.Faint.TLabel").grid(row=0, column=1, sticky="w",
                                                                               padx=(self.px(8), 0))
        tools = self.body(row)
        tools.grid(row=0, column=3, sticky="e")
        return row, tools

    # ------------------------------------------------------------------ build
    def _build(self):
        tab, px = self.tab, self.px
        self.box = ttk.Frame(tab.parent, padding=(px(18), px(14), px(18), px(8)))
        self.box.pack(fill="both", expand=True)
        self.box.columnconfigure(0, weight=1)
        self.box.rowconfigure(0, weight=1)
        self.scr_login = self._build_login(self.box)
        self.scr_lobby = self._build_lobby(self.box)
        self._build_footer(self.box)
        self.box.bind("<Configure>", self._on_resize, add="+")

    # --- login
    def _build_login(self, parent):
        tab, px = self.tab, self.px
        scr = ttk.Frame(parent)
        scr.columnconfigure(0, weight=3, uniform="login")
        scr.columnconfigure(1, weight=2, uniform="login")
        head = ttk.Frame(scr)
        head.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, px(12)))
        ttk.Label(head, text="Play online", style="H1.TLabel").pack(anchor="w")
        ttk.Label(head, style="Muted.TLabel", text=(
            "Log in or play as a guest. Find an opponent; the game starts by itself, straight into the "
            "fight, and the result comes back here.")).pack(anchor="w")

        card = self.card(scr, pad=18)
        card.grid(row=1, column=0, sticky="nsew", padx=(0, px(12)))
        card.columnconfigure(0, weight=1)
        tab.acc = card
        ttk.Label(card, text="SERVER", style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        srow = self.body(card)
        srow.grid(row=1, column=0, sticky="we", pady=(px(4), px(10)))
        srow.columnconfigure(0, weight=1)
        self.server_cb = ttk.Combobox(srow, textvariable=tab.server_var, style="Card.TCombobox",
                                      values=[x.name for x in tab.server_list])
        self.server_cb.grid(row=0, column=0, sticky="we")
        tab.b_tls = ttk.Button(srow, text="Server certificate...", style="Card.Ghost.TButton",
                               command=tab.do_fingerprint)
        tab.b_tls.grid(row=0, column=1, padx=(px(6), 0))
        ttk.Label(card, text="NAME", style="Card.Caps.TLabel").grid(row=2, column=0, sticky="w")
        self.name_entry = ttk.Entry(card, textvariable=tab.name_var, style="Card.TEntry")
        self.name_entry.grid(row=3, column=0, sticky="we", pady=(px(4), px(14)))
        self.name_entry.bind("<Return>", lambda _e: self._name_return())

        seg = ttk.Frame(card, style="SegTrack.TFrame", padding=px(3))
        seg.grid(row=4, column=0, sticky="w", pady=(0, px(12)))
        mode = tab.cfg.get("login_mode")
        self.mode_var = tk.StringVar(card, value=mode if mode in ("login", "register", "guest") else "login")
        self.seg_buttons = {}
        for key, text in (("login", "Log in"), ("register", "Create account"), ("guest", "Guest")):
            b = ttk.Radiobutton(seg, text=text, value=key, variable=self.mode_var, style="Seg.TRadiobutton",
                                command=self._mode_changed)
            b.pack(side="left")
            self.seg_buttons[key] = b

        # account: log in / create
        pa = self.body(card)
        pa.columnconfigure(0, weight=1)
        self.pane_account = pa
        ttk.Label(pa, text="PASSWORD", style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.pw_entry = ttk.Entry(pa, textvariable=tab.pw_var, show="•", style="Card.TEntry")
        self.pw_entry.grid(row=1, column=0, sticky="we", pady=(px(4), px(8)))
        self.pw_entry.bind("<Return>", lambda _e: self._pw_return())
        self.pw2_label = ttk.Label(pa, text="PASSWORD AGAIN", style="Card.Caps.TLabel")
        self.pw2_entry = ttk.Entry(pa, textvariable=self.pw2_var, show="•", style="Card.TEntry")
        self.pw2_entry.bind("<Return>", lambda _e: tab.do_login("register"))
        self.rules = self.body(pa)
        self.rule_labels = {}
        for i, (key, text) in enumerate((
                ("name", "Name: 2 to 16 letters, digits, spaces or _-.[]()!?"),
                ("length", "Password: 6 to 128 characters"),
                ("same", "Both passwords the same"),
                ("codes", "You get recovery codes once: the only way back in if you forget the password"))):
            lab = ttk.Label(self.rules, text="•  " + text, style="Card.Small.TLabel")
            lab.grid(row=i, column=0, sticky="w")
            self.rule_labels[key] = (lab, text)
        for var in (tab.name_var, tab.pw_var, self.pw2_var):
            var.trace_add("write", lambda *_: self._check_rules())
        act = self.body(pa)
        act.grid(row=5, column=0, sticky="we", pady=(px(4), 0))
        act.columnconfigure(1, weight=1)
        ttk.Checkbutton(act, text="Remember me", variable=tab.remember_var, style="Card.TCheckbutton").grid(
            row=0, column=0, sticky="w")
        tab.b_forgot = ttk.Button(act, text="Forgot password...", style="Card.Link.TButton", command=tab.do_forgot)
        tab.b_forgot.grid(row=0, column=1, sticky="w", padx=(px(10), 0))
        tab.b_login = ttk.Button(act, text="Log in", style="Card.Accent.TButton",
                                 command=lambda: tab.do_login("account"))
        tab.b_register = ttk.Button(act, text="Create account", style="Card.Accent.TButton",
                                    command=lambda: tab.do_login("register"))
        self.act_row = act

        # guest
        pg = self.body(card)
        pg.columnconfigure(0, weight=1)
        self.pane_guest = pg
        self.wrap(ttk.Label(pg, style="Card.Muted.TLabel", justify="left", text=(
            "Casual matches with the name above, no account and no password. Ranked matches, the "
            "leaderboard and your match history need an account.")), card, 40).grid(row=0, column=0, sticky="w")
        tab.b_guest = ttk.Button(pg, text="Play as guest", style="Card.Accent.TButton",
                                 command=lambda: tab.do_login("guest"))
        tab.b_guest.grid(row=1, column=0, sticky="e", pady=(px(12), 0))
        self.wrap(ttk.Label(card, textvariable=tab.hint_var, style="Card.Faint.TLabel", justify="left"),
                  card, 40).grid(row=6, column=0, sticky="w", pady=(px(14), 0))

        # side: host for friends, how it works
        side = ttk.Frame(scr)
        side.grid(row=1, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        hc = self.card(side, pad=16)
        hc.grid(row=0, column=0, sticky="we")
        hc.columnconfigure(0, weight=1)
        ttk.Label(hc, text="HOST FOR FRIENDS", style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.wrap(ttk.Label(hc, style="Card.Muted.TLabel", justify="left", text=(
            "Runs a lobby on this PC. Your friends type the address it shows into their Server box.")),
                  hc, 36).grid(row=1, column=0, sticky="w", pady=(px(4), px(8)))
        hrow = self.body(hc)
        hrow.grid(row=2, column=0, sticky="w")
        tab.b_host = ttk.Button(hrow, text="Host for friends", style="Card.TButton", command=tab.do_host)
        tab.b_host.pack(side="left")
        ttk.Checkbutton(hc, text="Open router ports (UPnP)", variable=tab.map_var, style="Card.TCheckbutton").grid(
            row=3, column=0, sticky="w", pady=(px(8), 0))
        self.host_label = self.wrap(ttk.Label(hc, textvariable=self.host_var, style="Card.Accent.TLabel",
                                              justify="left"), hc, 36)

        how = self.card(side, pad=16)
        how.grid(row=1, column=0, sticky="we", pady=(px(12), 0))
        how.columnconfigure(1, weight=1)
        ttk.Label(how, text="HOW IT WORKS", style="Card.Caps.TLabel").grid(row=0, column=0, columnspan=2, sticky="w",
                                                                          pady=(0, px(6)))
        for i, text in enumerate(("Quick match (casual) or Ranked match (account).",
                                  "An opponent is found: accept within 15 seconds.",
                                  "The game opens straight into the fight.",
                                  "The result comes back here: rematch or next game.")):
            ttk.Label(how, text=str(i + 1), style="Card.Accent.TLabel").grid(row=i + 1, column=0, sticky="nw",
                                                                            padx=(0, px(10)), pady=px(2))
            self.wrap(ttk.Label(how, text=text, style="Card.TLabel", justify="left"), how, 60).grid(
                row=i + 1, column=1, sticky="w", pady=px(2))
        ttk.Label(how, text="With a controller: A accepts, B declines.", style="Card.Faint.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(px(8), 0))
        self._mode_changed(save=False)
        return scr

    def _mode_changed(self, save=True):
        tab, px = self.tab, self.px
        mode = self.mode_var.get()
        self.pane_account.grid_forget()
        self.pane_guest.grid_forget()
        if mode == "guest":
            self.pane_guest.grid(row=5, column=0, sticky="we")
        else:
            self.pane_account.grid(row=5, column=0, sticky="we")
            reg = mode == "register"
            for w in (self.pw2_label, self.pw2_entry, self.rules):
                w.grid_forget()
            if reg:
                self.pw2_label.grid(row=2, column=0, sticky="w")
                self.pw2_entry.grid(row=3, column=0, sticky="we", pady=(px(4), px(8)))
                self.rules.grid(row=4, column=0, sticky="w", pady=(0, px(8)))
            tab.b_login.grid_forget()
            tab.b_register.grid_forget()
            (tab.b_register if reg else tab.b_login).grid(row=0, column=2, sticky="e")
            if reg:
                tab.b_forgot.grid_remove()
            else:
                tab.b_forgot.grid()
        self._check_rules()
        if save and tab.cfg.get("login_mode") != mode:
            tab.cfg["login_mode"] = mode
            tab._save_cfg()

    def _check_rules(self):
        tab = self.tab
        name, pw, pw2 = tab.name_var.get().strip(), tab.pw_var.get(), self.pw2_var.get()
        state = {"name": proto.valid_name(name), "length": 6 <= len(pw) <= 128, "same": bool(pw) and pw == pw2,
                 "codes": None}
        for key, (lab, text) in self.rule_labels.items():
            ok = state[key]
            mark = "✓  " if ok else "•  "
            lab.configure(text=mark + text, style="Card.ok.TLabel" if ok else "Card.Small.TLabel")

    def _name_return(self):
        mode = self.mode_var.get()
        if mode == "guest":
            self.tab.do_login("guest")
        else:
            self.pw_entry.focus_set()

    def _pw_return(self):
        if self.mode_var.get() == "register":
            self.pw2_entry.focus_set()
        else:
            self.tab.do_login("account")

    def repeat_password(self):
        """The 'password again' field when the player is creating an account there (else None: ask)."""
        if self.mode_var.get() == "register" and self.pw2_var.get():
            return self.pw2_var.get()
        return None

    # --- lobby
    def _build_lobby(self, parent):
        tab, px = self.tab, self.px
        scr = ttk.Frame(parent)
        scr.columnconfigure(0, minsize=px(300))
        scr.columnconfigure(1, weight=1)
        scr.rowconfigure(1, weight=1)
        self._build_profile(scr)
        self._build_stage(scr)
        nb = ttk.Notebook(scr)
        nb.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(px(10), 0))
        tab.nb = nb
        lobby = ttk.Frame(nb, padding=(0, px(10), 0, 0))
        board = ttk.Frame(nb, padding=(0, px(10), 0, 0))
        prof = ttk.Frame(nb, padding=(0, px(10), 0, 0))
        nb.add(lobby, text="Lobby")
        nb.add(board, text="Leaderboard")
        nb.add(prof, text="Profile")
        nb.bind("<<NotebookTabChanged>>", lambda _e: tab._on_subtab())
        self._build_lobby_page(lobby)
        self._build_board_page(board)
        self._build_profile_page(prof)
        return scr

    def _build_profile(self, scr):
        tab, px = self.tab, self.px
        card = self.card(scr, pad=16)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
        card.columnconfigure(1, weight=1)
        card.rowconfigure(5, weight=1)
        self.me_badge = theme.Badge(card, size=54)
        self.me_badge.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, px(12)))
        self.me_name = ttk.Label(card, text="", style="Card.H2.TLabel")
        self.me_name.grid(row=0, column=1, sticky="w")
        self.me_rank = ttk.Label(card, text="", style="Card.Bold.TLabel")
        self.me_rank.grid(row=1, column=1, sticky="w")
        self.me_stats = ttk.Label(card, text="", style="Card.Muted.TLabel")
        self.me_stats.grid(row=2, column=1, sticky="w")
        self.me_conn = ttk.Label(card, text="", style="Card.Faint.TLabel")
        self.me_conn.grid(row=3, column=0, columnspan=2, sticky="w", pady=(px(10), 0))
        self.me_main = ttk.Label(card, text="", style="Card.Faint.TLabel")
        self.me_main.grid(row=4, column=0, columnspan=2, sticky="w")
        row = self.body(card)
        row.grid(row=6, column=0, columnspan=2, sticky="we", pady=(px(10), 0))
        tab.b_myprofile = ttk.Button(row, text="My profile", style="Card.Small.TButton",
                                     command=lambda: tab.show_profile(None))
        tab.b_myprofile.pack(side="left")
        tab.b_logout = ttk.Button(row, text="Log out", style="Card.Small.TButton", command=tab.do_logout)
        tab.b_logout.pack(side="left", padx=(px(6), 0))
        tab.me_row = card

    def _build_stage(self, scr):
        px = self.px
        card = self.card(scr, pad=16)
        card.grid(row=0, column=1, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1, minsize=px(182))
        self.stage_card = card
        self.st_play = self._build_play(card)
        self.st_search = self._build_search(card)
        self.tab.bar = self._build_bar(card)
        self.st_match = self._build_match(card)
        self.st_result = self._build_result(card)
        self.stages = {"play": self.st_play, "search": self.st_search, "bar": self.tab.bar,
                       "match": self.st_match, "result": self.st_result}

    def _build_play(self, card):
        tab, px = self.tab, self.px
        f = self.body(card)
        f.columnconfigure(0, weight=1, uniform="hero")
        f.columnconfigure(1, weight=1, uniform="hero")
        top = self.body(f)
        top.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, px(10)))
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="FIND A MATCH", style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.room_label = ttk.Label(top, text="", style="Card.Accent.TLabel")
        self.room_label.grid(row=1, column=0, sticky="w")
        ttk.Label(top, text="Character", style="Card.Muted.TLabel").grid(row=0, column=1, rowspan=2, sticky="e",
                                                                       padx=(0, px(8)))
        names = ["Random"] + [x["name"] for x in tab.table.selectable()]
        cb = ttk.Combobox(top, textvariable=tab.char_var, values=names, state="readonly", width=15,
                          style="Card.TCombobox")
        cb.grid(row=0, column=2, rowspan=2, sticky="e")
        cb.bind("<<ComboboxSelected>>", lambda _e: tab.on_char())
        tab.char_cb = cb
        tab.actions = {}
        tab.action_text = {}
        b = ttk.Button(f, text="Ranked match", style="Card.Hero.TButton", state="disabled",
                       command=lambda: tab.do_queue("ranked"))
        b.grid(row=1, column=0, sticky="we", padx=(0, px(6)))
        tab.actions["ranked"], tab.action_text["ranked"] = b, "Ranked match"
        b = ttk.Button(f, text="Quick match", style="Card.HeroAlt.TButton", state="disabled",
                       command=lambda: tab.do_queue("quick"))
        b.grid(row=1, column=1, sticky="we", padx=(px(6), 0))
        tab.actions["quick"], tab.action_text["quick"] = b, "Quick match"
        self.ranked_sub = ttk.Label(f, text="", style="Card.Small.TLabel")
        self.ranked_sub.grid(row=2, column=0, sticky="w", pady=(px(5), 0))
        self.quick_sub = ttk.Label(f, text="Casual: the lowest ping first", style="Card.Small.TLabel")
        self.quick_sub.grid(row=2, column=1, sticky="w", padx=(px(6), 0), pady=(px(5), 0))
        tab.strict_check = ttk.Checkbutton(f, text="Strict (ranked: +-150 rating)", variable=tab.strict_var,
                                           command=tab._save_cfg, style="Card.TCheckbutton")
        tab.strict_check.grid(row=3, column=0, sticky="w", pady=(px(6), 0))
        self.wrap(ttk.Label(f, textvariable=tab.hint_var, style="Card.Faint.TLabel", justify="left"),
                  card, 40).grid(row=4, column=0, columnspan=2, sticky="w", pady=(px(6), 0))
        return f

    def _build_search(self, card):
        tab, px = self.tab, self.px
        f = self.body(card)
        f.columnconfigure(1, weight=1)
        self.spinner = theme.Spinner(f, size=78, width=7)
        self.spinner.grid(row=0, column=0, rowspan=4, sticky="nw", padx=(0, px(18)))
        head = self.body(f)
        head.grid(row=0, column=1, sticky="w")
        ttk.Label(head, text="SEARCHING", style="Card.Caps.TLabel").pack(side="left")
        self.search_pill = ttk.Label(head, text="RANKED", style="Card.PillAccent.TLabel")
        self.search_pill.pack(side="left", padx=(px(8), 0))
        self.search_title = ttk.Label(f, text="Looking for an opponent", style="Card.H2.TLabel")
        self.search_title.grid(row=1, column=1, sticky="w", pady=(px(2), 0))
        self.search_rules = self.wrap(ttk.Label(f, text="", style="Card.Muted.TLabel", justify="left"), card, 160)
        self.search_rules.grid(row=2, column=1, sticky="w")
        self.search_queue = ttk.Label(f, text="", style="Card.Faint.TLabel")
        self.search_queue.grid(row=3, column=1, sticky="w")
        t = self.body(f)
        t.grid(row=0, column=2, rowspan=3, sticky="ne")
        self.search_time = ttk.Label(t, text="0:00", style="Card.Big.TLabel")
        self.search_time.pack(anchor="e")
        ttk.Label(t, text="SEARCHING FOR", style="Card.Caps.TLabel").pack(anchor="e")
        b = ttk.Button(f, text="Stop searching", style="Card.TButton", state="disabled",
                       command=lambda: tab.call(tab.client.cancel_queue))
        b.grid(row=4, column=1, sticky="w", pady=(px(12), 0))
        tab.actions["cancel"], tab.action_text["cancel"] = b, "Stop searching"
        return f

    def _build_bar(self, card):
        tab, px = self.tab, self.px
        bar = self.body(card)
        bar.columnconfigure(0, weight=1)
        self.bar_visual = self.body(bar)
        self.bar_visual.grid(row=0, column=0, sticky="we")
        self.bar_visual.columnconfigure(0, weight=1)
        self.bar_label = self.wrap(ttk.Label(bar, textvariable=tab.bar_text, style="Card.H3.TLabel",
                                             justify="left"), card, 40)
        tab.bar_buttons = self.body(bar)
        tab.bar_buttons.grid(row=2, column=0, sticky="w", pady=(px(12), 0))
        return bar

    def _build_match(self, card):
        px = self.px
        f = self.body(card)
        f.columnconfigure(1, weight=1)
        head = self.body(f)
        head.grid(row=0, column=0, columnspan=2, sticky="we")
        head.columnconfigure(2, weight=1)
        ttk.Label(head, text="IN MATCH", style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.m_pill = ttk.Label(head, text="CASUAL", style="Card.Pill.TLabel")
        self.m_pill.grid(row=0, column=1, sticky="w", padx=(px(8), 0))
        self.m_dot = tk.Canvas(head, width=px(10), height=px(10), bg=C["surface"], highlightthickness=0, takefocus=0)
        self.m_dot.grid(row=0, column=3, sticky="e", padx=(0, px(6)))
        self.m_state = ttk.Label(head, text="", style="Card.Bold.TLabel")
        self.m_state.grid(row=0, column=4, sticky="e")
        self.m_badge = theme.Badge(f, size=40)
        self.m_badge.grid(row=1, column=0, rowspan=2, sticky="w", pady=(px(10), 0), padx=(0, px(12)))
        self.m_name = ttk.Label(f, text="", style="Card.H2.TLabel")
        self.m_name.grid(row=1, column=1, sticky="sw", pady=(px(10), 0))
        self.m_rank = ttk.Label(f, text="", style="Card.Muted.TLabel")
        self.m_rank.grid(row=2, column=1, sticky="nw")
        tiles = self.body(f)
        tiles.grid(row=3, column=0, columnspan=2, sticky="we", pady=(px(12), 0))
        for i in range(3):
            tiles.columnconfigure(i, weight=1, uniform="tile")
        t1 = self.card(tiles, "Tile.TFrame", 10)
        t1.grid(row=0, column=0, sticky="nsew", padx=(0, px(6)))
        ttk.Label(t1, text="PING", style="Tile.Caps.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.m_bars = theme.PingBars(t1, bg=C["raised"])
        self.m_bars.grid(row=1, column=0, sticky="w", padx=(0, px(8)))
        self.m_ping = ttk.Label(t1, text="", style="Tile.Num.TLabel")
        self.m_ping.grid(row=1, column=1, sticky="w")
        t2 = self.card(tiles, "Tile.TFrame", 10)
        t2.grid(row=0, column=1, sticky="nsew", padx=px(3))
        ttk.Label(t2, text="INPUT DELAY", style="Tile.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.m_delay = ttk.Label(t2, text="", style="Tile.Num.TLabel")
        self.m_delay.grid(row=1, column=0, sticky="w")
        t3 = self.card(tiles, "Tile.TFrame", 10)
        t3.grid(row=0, column=2, sticky="nsew", padx=(px(6), 0))
        ttk.Label(t3, text="CONNECTION", style="Tile.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.m_path = ttk.Label(t3, text="", style="Tile.Num.TLabel")
        self.m_path.grid(row=1, column=0, sticky="w")
        self.m_detail = self.wrap(ttk.Label(f, textvariable=self.tab.match_var, style="Card.Faint.TLabel",
                                            justify="left"), card, 40)
        self.m_detail.grid(row=4, column=0, columnspan=2, sticky="w", pady=(px(8), 0))
        return f

    def _build_result(self, card):
        px = self.px
        f = self.body(card)
        f.columnconfigure(0, weight=1)
        self.res_visual = self.body(f)
        self.res_visual.grid(row=0, column=0, sticky="we")
        self.res_visual.columnconfigure(0, weight=1)
        self.res_buttons = self.body(f)
        self.res_buttons.grid(row=1, column=0, sticky="w", pady=(px(12), 0))
        return f

    def _build_lobby_page(self, page):
        tab, px = self.tab, self.px
        page.columnconfigure(0, weight=3)
        page.columnconfigure(1, weight=2)
        page.rowconfigure(0, weight=3)
        page.rowconfigure(1, weight=2)
        pc = self.card(page, pad=12)
        pc.grid(row=0, column=0, sticky="nsew")
        pc.columnconfigure(0, weight=1)
        pc.rowconfigure(1, weight=1)
        self.players_count = tk.StringVar(page, value="")
        head, tools = self.section_head(pc, "PLAYERS ONLINE", self.players_count)
        head.grid(row=0, column=0, sticky="we", pady=(0, px(6)))
        b = ttk.Button(tools, text="Challenge", style="Card.Small.TButton", state="disabled", command=tab.do_challenge)
        b.pack(side="left")
        tab.actions["challenge"], tab.action_text["challenge"] = b, "Challenge"
        ttk.Button(tools, text="Profile", style="Card.Small.TButton", command=tab._profile_of_selected).pack(
            side="left", padx=(px(6), 0))
        fr, tab.tv_players = self.tree(pc, ("player", "rank", "rating", "record", "main", "status", "ping"),
                                       (130, 120, 60, 72, 86, 104, 68), height=6)
        fr.grid(row=1, column=0, sticky="nsew")
        tab.tv_players.bind("<Double-1>", lambda _e: tab._profile_of_selected())
        tab.tv_players.bind("<Return>", lambda _e: tab._profile_of_selected())

        rc = self.card(page, pad=12)
        rc.grid(row=1, column=0, sticky="nsew", pady=(px(10), 0))
        rc.columnconfigure(0, weight=1)
        rc.rowconfigure(1, weight=1)
        self.rooms_count = tk.StringVar(page, value="")
        head, tools = self.section_head(rc, "ROOMS", self.rooms_count)
        head.grid(row=0, column=0, sticky="we", pady=(0, px(6)))
        for key, label, cmd in (("room", "Create room", lambda: tab.call(tab.client.create_room, None)),
                                ("join", "Join room", tab.do_join),
                                ("leave", "Leave room", lambda: tab.call(tab.client.leave_room))):
            b = ttk.Button(tools, text=label, style="Card.Small.TButton", state="disabled", command=cmd)
            b.pack(side="left", padx=(px(6), 0))
            tab.actions[key], tab.action_text[key] = b, label
        fr, tab.tv_rooms = self.tree(rc, ("room", "owner", "state", "ping"), (190, 140, 140, 70), height=3)
        fr.grid(row=1, column=0, sticky="nsew")
        tab.tv_rooms.bind("<Double-1>", lambda _e: tab.do_join() if str(tab.actions["join"].cget("state")) ==
                          "normal" else None)

        cc = self.card(page, pad=12)
        cc.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(px(10), 0))
        cc.columnconfigure(0, weight=1)
        cc.rowconfigure(1, weight=1)
        head, _tools = self.section_head(cc, "CHAT")
        head.grid(row=0, column=0, sticky="we", pady=(0, px(6)))
        tab.chat_log = tk.Text(cc, height=10, width=30, state="disabled", wrap="word", font=self.th.fonts["body"],
                               bg=C["surface"], fg=C["text"], relief="flat", borderwidth=0, highlightthickness=0,
                               padx=px(2), pady=px(2), cursor="arrow", takefocus=0)
        tab.chat_log.grid(row=1, column=0, sticky="nsew")
        row = self.body(cc)
        row.grid(row=2, column=0, sticky="we", pady=(px(8), 0))
        row.columnconfigure(0, weight=1)
        ce = ttk.Entry(row, textvariable=tab.chat_var, style="Card.TEntry")
        ce.grid(row=0, column=0, sticky="we")
        ce.bind("<Return>", lambda _e: tab.do_chat())
        ttk.Button(row, text="Send", style="Card.TButton", command=tab.do_chat).grid(row=0, column=1,
                                                                                     padx=(px(6), 0))

    def _build_board_page(self, page):
        tab, px = self.tab, self.px
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        card = self.card(page, pad=12)
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)
        head, tools = self.section_head(card, "LEADERBOARD")
        head.grid(row=0, column=0, sticky="we")
        ttk.Button(tools, text="Refresh", style="Card.Small.TButton", command=tab.load_leaderboard).pack(side="left")
        ttk.Label(card, style="Card.Faint.TLabel", text=(
            "Order: rating minus twice its uncertainty (a few matches are needed to climb). "
            "'?' = provisional.")).grid(row=1, column=0, sticky="w", pady=(px(2), px(6)))
        fr, tab.tv_board = self.tree(card, ("place", "player", "rank", "rating", "record", "main"),
                                     (60, 170, 150, 80, 100, 120), height=10)
        fr.grid(row=2, column=0, sticky="nsew")
        tab.tv_board.bind("<Double-1>", lambda _e: tab._profile_of(tab.tv_board))
        tab.tv_board.bind("<Return>", lambda _e: tab._profile_of(tab.tv_board))

    def _build_profile_page(self, page):
        tab, px = self.tab, self.px
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        acc = ttk.Frame(page)
        acc.grid(row=0, column=0, sticky="we", pady=(0, px(8)))
        ttk.Label(acc, text="YOUR ACCOUNT", style="Caps.TLabel").pack(side="left", padx=(0, px(10)))
        tab.b_blocked = ttk.Button(acc, text="Blocked players...", style="Small.TButton", command=tab.do_blocked)
        tab.b_passwd = ttk.Button(acc, text="Change password...", style="Small.TButton", command=tab.do_passwd)
        tab.b_codes = ttk.Button(acc, text="New recovery codes...", style="Small.TButton", command=tab.do_new_codes)
        for b in (tab.b_blocked, tab.b_passwd, tab.b_codes):
            b.pack(side="left", padx=(0, px(6)))
        card = self.card(page, pad=14)
        card.grid(row=1, column=0, sticky="nsew")
        card.columnconfigure(1, weight=1)
        card.rowconfigure(2, weight=1)
        self.prof_badge = theme.Badge(card, size=46)
        self.prof_badge.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, px(12)))
        ttk.Label(card, textvariable=tab.prof_title, style="Card.H2.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(card, textvariable=tab.prof_text, style="Card.Muted.TLabel", justify="left").grid(
            row=1, column=1, sticky="w", pady=(px(2), px(8)))
        fr, tab.tv_hist = self.tree(card, ("when", "result", "opponent", "chars", "score", "rating", "status"),
                                    (110, 60, 120, 180, 60, 64, 170), height=7, image_col=False, select="none")
        fr.grid(row=2, column=0, columnspan=2, sticky="nsew")
        tab.tv_hist.tag_configure("won", foreground=C["ok"])
        tab.tv_hist.tag_configure("lost", foreground=C["bad"])

    def _build_footer(self, box):
        tab, px = self.tab, self.px
        err = self.card(box, "Err.TFrame", 10)
        err.columnconfigure(1, weight=1)
        icon = tk.Canvas(err, width=px(20), height=px(20), bg=C["err_bg"], highlightthickness=0, takefocus=0)
        icon.create_oval(1, 1, px(20) - 1, px(20) - 1, fill=C["bad"], outline="")
        icon.create_text(px(10), px(10), text="!", fill="#1a0707", font=(self.th.fonts["h3"].actual("family"), 10,
                                                                         "bold"))
        icon.grid(row=0, column=0, sticky="nw", padx=(0, px(10)))
        self.err_label = self.wrap(ttk.Label(err, textvariable=self.err_var, style="Err.TLabel", justify="left"),
                                   box, 140)
        self.err_label.grid(row=0, column=1, sticky="w")
        ttk.Button(err, text="Dismiss", style="Err.Ghost.TButton", command=self.clear_error).grid(row=0, column=2,
                                                                                               sticky="e")
        self.err_frame = err
        note = self.card(box, "Note.TFrame", 10)
        note.columnconfigure(1, weight=1)
        ttk.Label(note, text="SERVER", style="Note.Caps.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, px(10)))
        self.wrap(ttk.Label(note, textvariable=tab.notice_var, style="Note.TLabel", justify="left"), box, 120).grid(
            row=0, column=1, sticky="w")
        self.note_frame = note
        tab.notice_var.trace_add("write", lambda *_: self._show_notice())
        st = ttk.Frame(box)
        st.grid(row=3, column=0, sticky="we", pady=(px(8), 0))
        st.columnconfigure(0, weight=1)
        self.status_label = self.wrap(ttk.Label(st, textvariable=tab.status_var, style="Muted.TLabel",
                                                justify="left"), box, 340)
        self.status_label.grid(row=0, column=0, sticky="w")
        rep = ttk.Frame(st)
        rep.grid(row=0, column=1, sticky="e", padx=(px(10), px(10)))
        # after a match: the launcher's "Report a problem" window (tk_tab packs it into this frame)
        tab.report_btn = ttk.Button(rep, text="Report a problem...", style="Small.TButton", command=tab.do_report)
        pad = ttk.Frame(st)
        pad.grid(row=0, column=2, sticky="e")
        ttk.Label(pad, textvariable=tab.pad_info_var, style="Faint.TLabel").pack(side="left", padx=(0, px(10)))
        tab.pad_check = ttk.Checkbutton(pad, text="Use a controller here", variable=tab.pad_var,
                                        command=tab._pad_toggle)
        tab.pad_check.pack(side="left")

    # ------------------------------------------------------------------ screens
    def set_logged_in(self, on):
        on = bool(on)
        if on == self._logged:
            return
        self._logged = on
        if on:
            self.scr_login.grid_forget()
            self.scr_lobby.grid(row=0, column=0, sticky="nsew")
            self.clear_error()
        else:
            self.scr_lobby.grid_forget()
            self.scr_login.grid(row=0, column=0, sticky="nsew")
            self.result_info = None
            self.result_dismissed = True
            self.match_ev = None
        self.refresh()

    def _show_notice(self):
        if self.tab.notice_var.get():
            self.note_frame.grid(row=2, column=0, sticky="we", pady=(self.px(8), 0))
        else:
            self.note_frame.grid_forget()

    def show_error(self, text):
        msg = friendly_error(text)
        if not msg:
            return
        self.err_var.set(msg)
        self.err_frame.grid(row=1, column=0, sticky="we", pady=(self.px(8), 0))
        self._on_resize()

    def clear_error(self):
        self.err_var.set("")
        self.err_frame.grid_forget()

    def status_changed(self, text, error=False):
        if error:
            self.show_error(text)

    def show_bar(self):
        self._bar_on = True
        self._bar_sig = None
        self.refresh()

    def hide_bar(self):
        self._bar_on = False
        self._bar_sig = None
        self.refresh()

    def bar_button_style(self, label, pad):
        if pad == "cross":
            return "Card.Accent.TButton"
        if label.startswith("Block "):
            return "Card.Danger.TButton"
        return "Card.TButton"

    def reset(self):
        self.revealed = None
        self.challenger = None
        self.match_ev = None
        self.result_info = None
        self.result_dismissed = True
        self.search_t0 = None

    # ------------------------------------------------------------------ what the tab tells us
    def after_event(self, ev):
        t = ev.get("t")
        tab = self.tab
        if t == "lobby_state":
            self.queue_counts = ev.get("queue") or {}
            players = ev.get("players", [])
            rooms = ev.get("rooms", [])
            self.players_count.set(f"{len(players)}")
            self.rooms_count.set(f"{len(rooms)}" if rooms else "none open")
            room = None
            me = tab.client.me if tab.client else None
            for r in rooms:
                if me and me.get("id") in (r.get("members") or []):
                    room = r
            if room is not None:
                text = (f"In your room “{room['name']}”. Waiting for a second player..."
                        if len(room.get("members") or []) < 2 else
                        f"In the room “{room['name']}”. The match starts when you are both ready.")
            else:
                text = ""
            self.room_label.configure(text=text)
        elif t == "challenged":
            self.challenger = ev.get("from")
        elif t == "match_found":
            self.revealed = None
            self.clear_error()
            self.result_dismissed = True
        elif t == "match_reveal":
            self.revealed = ev.get("opponent")
        elif t == "match_start":
            self.match_ev = ev
            self.game_phase = None
            self.fighters = None
            self.result_dismissed = True
        elif t in ("match_cancel", "disconnected"):
            self.revealed = None
        self.refresh()

    def after_driver(self, n):
        if n.get("kind") == "game_state":
            self.game_phase = n.get("state")
            if n.get("chars"):
                self.fighters = tuple(n["chars"])
        self.refresh()

    def result(self, ev, mine, text):
        tab = self.tab
        drv = tab.driver
        tk_ = drv.session_ticket if drv is not None else None
        self.result_info = {"ev": ev, "mine": mine, "text": text,
                            "slot": getattr(tk_, "slot", None),
                            "opp": (getattr(tk_, "opponent", None) or {}).get("name"),
                            "ranked": ev.get("ranked", (self.match_ev or {}).get("ranked"))}
        self.result_dismissed = False
        self.match_ev = None
        self._res_sig = None
        self._bar_sig = None

    def profile_shown(self, p):
        self.prof_badge.set(_tier_of(p) if p.get("account", True) else None, p.get("provisional"))

    def hosting(self, info):
        if not info:
            self.host_var.set("")
            self.host_label.grid_forget()
            return
        share = info.get("internet") or f"<your public IP>:{info.get('port')}" + (
            f"#{info['fingerprint']}" if info.get("fingerprint") else "")
        text = "Hosting. Friends type this as their Server:\n" + share
        if info.get("lan"):
            text += "\nSame network: " + str(info["lan"])
        self.host_var.set(text)
        self.host_label.grid(row=4, column=0, sticky="w", pady=(self.px(8), 0))

    # ------------------------------------------------------------------ list helpers (used by the tab)
    def ping_image(self, ms):
        return self.th.ping_icon(ms)

    def room_image(self, closed):
        return self.th.lock_icon() if closed else self.th.empty_icon()

    def rank_image(self, info):
        return self.th.tier_icon(_tier_of(info))

    # ------------------------------------------------------------------ refresh
    def _pick_stage(self):
        tab = self.tab
        if self._bar_on:
            return "bar"
        if tab.client is None:
            return None
        drv = tab.driver
        if drv is not None and drv.ticket is not None:
            return "match"
        me = tab.client.me or {}
        if me.get("status") == "queue":
            return "search"
        if self.result_info is not None and not self.result_dismissed:
            return "result"
        return "play"

    def refresh(self):
        try:
            if not self.box.winfo_exists():
                return
        except tk.TclError:
            return
        self._update_profile()
        self._update_play()
        stage = self._pick_stage()
        if stage == "search" and self.search_t0 is None:
            self.search_t0 = time.monotonic()
            self.result_dismissed = True
            self.clear_error()
        elif stage != "search":
            self.search_t0 = None
        if stage != self._stage:
            for name, w in self.stages.items():
                if name != stage:
                    w.grid_forget()
            if stage is not None:
                self.stages[stage].grid(row=0, column=0, sticky="nsew")
            self._stage = stage
            self._match_sig = None
            self._res_sig = None
        if stage == "bar":
            self._render_bar()
        elif stage == "match":
            self._update_match()
        elif stage == "search":
            self._update_search()
        elif stage == "result":
            self._render_result_card()
        self._ensure_anim()

    def tick(self):
        """Every poll of the tab (10 a second): keep the animation running while one is showing."""
        self._ensure_anim()

    # --- profile card
    def _update_profile(self):
        tab = self.tab
        c = tab.client
        me = c.me if c is not None else None
        if not me:
            return
        sig = (me.get("name"), me.get("tier"), me.get("rank"), me.get("provisional"), me.get("rating"),
               tuple(me.get("record") or ()), me.get("main"), me.get("guest"), round(c.server_rtt or 0), c.tls,
               str(me.get("placement")))
        if sig == self._prof_sig:
            return
        self._prof_sig = sig
        guest = me.get("guest")
        tier = None if guest else _tier_of(me)
        self.me_badge.set(tier, bool(me.get("provisional")) and not guest)
        self.me_name.configure(text=me.get("name", ""))
        rec = me.get("record") or [0, 0, 0]
        if guest:
            self.me_rank.configure(text="Guest · casual matches", foreground=C["muted"])
            self.me_stats.configure(text=f"{rec[0]}W {rec[1]}L this session")
            self.me_main.configure(text="")
        else:
            self.me_rank.configure(text=ranks.label(me), foreground=theme.mix(theme.tier_color(tier), "#ffffff", 0.25))
            self.me_stats.configure(text=f"Rating {me.get('rating')}  ·  {rec[0]}W {rec[1]}L"
                                    + (f" {rec[2]}D" if len(rec) > 2 and rec[2] else ""))
            self.me_main.configure(text=f"Main: {tab.table.fighter_name(me['main'])}" if me.get("main") else "")
        conn = f"Server ping {c.server_rtt or 0:.0f} ms"
        if c.tls:
            conn += "  ·  encrypted"
        self.me_conn.configure(text=conn)

    def _update_play(self):
        tab = self.tab
        me = tab.client.me if tab.client is not None and tab.client.me else None
        guest = (me or {}).get("guest", True)
        self.ranked_sub.configure(text="Create an account to play ranked" if me and guest else
                                  "Rated: close to your rank, good connection")

    # --- searching
    def _update_search(self):
        tab = self.tab
        mode = tab.cfg.get("last_search") or "quick"
        strict = mode == "ranked" and bool(tab.strict_var.get())
        self.search_pill.configure(text="RANKED" if mode == "ranked" else "CASUAL",
                                   style="Card.PillAccent.TLabel" if mode == "ranked" else "Card.Pill.TLabel")
        self.search_title.configure(text="Ranked match" if mode == "ranked" else "Quick match")
        if mode == "ranked":
            rules = "Similar rank and a good connection" + (", strict: within 150 rating points (this can take a "
                                                            "while)" if strict else "") + "."
        else:
            rules = "The opponent with the lowest ping first."
        self.search_rules.configure(text=rules)
        q = self.queue_counts or {}
        self.search_queue.configure(text=f"{q.get('ranked', 0)} in the ranked queue  ·  "
                                         f"{q.get('quick', 0)} in quick match")
        self._update_elapsed()

    def _update_elapsed(self):
        if self.search_t0 is None:
            return
        el = int(time.monotonic() - self.search_t0)
        text = f"{el // 60}:{el % 60:02d}"
        if str(self.search_time.cget("text")) != text:
            self.search_time.configure(text=text)

    # --- in a match
    def _update_match(self):
        tab = self.tab
        ev = self.match_ev or {}
        drv = tab.driver
        running = bool(drv is not None and drv.game_running())
        phase = self.game_phase
        sig = (id(ev), running, phase, self.fighters)
        if sig == self._match_sig:
            return
        self._match_sig = sig
        opp = ev.get("opponent") or (getattr(drv.ticket, "opponent", None) if drv and drv.ticket else None) or {}
        ranked = ev.get("ranked")
        self.m_pill.configure(text=("RANKED" if ranked else "CASUAL") + ("  ·  REMATCH" if ev.get("origin") ==
                                                                          "rematch" else ""),
                              style="Card.PillAccent.TLabel" if ranked else "Card.Pill.TLabel")
        state = {"title": "The game is starting...", "select": "Character select", "stage": "Stage select",
                 "loading": "Loading the fight...", "fight": "Fight!", "over": "Match over",
                 "neutral": "Waiting for the next match"}.get(phase)
        if running:
            text, col = "Your game is running" + (f"  ·  {state}" if state else ""), C["ok"]
        elif ev:
            text, col = "Starting the game...", C["warn"]
        else:
            text, col = "Waiting for the game...", C["warn"]
        self.m_state.configure(text=text)
        self.m_dot.delete("all")
        d = self.px(10)
        self.m_dot.create_oval(1, 1, d - 1, d - 1, fill=col, outline="")
        guest = opp.get("guest")
        self.m_badge.set(None if guest else _tier_of(opp), bool(opp.get("provisional")) and not guest)
        self.m_name.configure(text=("vs " + opp["name"]) if opp.get("name") else "vs your opponent")
        if guest:
            self.m_rank.configure(text="Guest")
        elif opp:
            self.m_rank.configure(text=f"{ranks.label(opp)}  ·  rating {opp.get('rating', '?')}")
        else:
            self.m_rank.configure(text="")
        rtt = ev.get("rtt_ms")
        self.m_bars.set(rtt)
        self.m_ping.configure(text=f"{rtt:.0f} ms" if rtt is not None else "?",
                              foreground=theme.ping_color(rtt))
        delay = ev.get("delay")
        self.m_delay.configure(text=f"{delay} frame{'s' if delay != 1 else ''}  ({delay * 16.7:.0f} ms)"
                               if isinstance(delay, int) else "?")
        self.m_path.configure(text={"direct": "Direct", "lan": "Local network",
                                    "relay": "Relay (lobby server)"}.get(ev.get("path"), ev.get("path") or "?"))

    # --- the bar: questions, found match, result + rematch
    def _bar_kind_now(self):
        tab = self.tab
        if tab.rematch_bar is not None:
            return "result"
        if tab.challenge is not None:
            return "challenge"
        drv = tab.driver
        if drv is not None and drv.ticket is not None:
            return "question"
        if tab.match is not None:
            return "ready" if tab.ready_deadline is not None else "connecting"
        return "question"

    def _render_bar(self):
        tab = self.tab
        kind = self._bar_kind_now()
        lag = (tab.lag or {}).get("text")
        sig = (kind, id(tab.match), (self.revealed or {}).get("name"), tab.ready_sent, tab.challenge,
               tab.rematch_bar, lag, id(self.result_info), str(tab.bar_text.get()) if kind == "question" else None)
        if sig == self._bar_sig:
            return
        self._bar_sig = sig
        self._bar_kind = kind
        for w in self.bar_visual.winfo_children():
            w.destroy()
        self.ring = None
        self.bar_spinner = None
        show_text = kind == "question"
        if kind == "ready":
            self._visual_ready(self.bar_visual)
        elif kind == "connecting":
            self._visual_connecting(self.bar_visual)
        elif kind == "challenge":
            self._visual_challenge(self.bar_visual)
        elif kind == "result":
            self._visual_result(self.bar_visual)
            show_text = tab.rematch_bar is not None and tab.bar_text.get() != tab.rematch_bar[0]
        if show_text:
            self.bar_label.configure(style="Card.H3.TLabel" if kind == "question" else "Card.Accent.TLabel")
            self.bar_label.grid(row=1, column=0, sticky="w", pady=(self.px(10) if kind != "question" else 0, 0))
        else:
            self.bar_label.grid_forget()
        self._on_resize()

    def _opponent_row(self, parent, opp, row, size=40):
        px = self.px
        guest = opp.get("guest")
        b = theme.Badge(parent, size=size)
        b.set(None if guest else _tier_of(opp), bool(opp.get("provisional")) and not guest)
        b.grid(row=row, column=0, rowspan=2, sticky="w", padx=(0, px(12)))
        ttk.Label(parent, text=opp.get("name", "?"), style="Card.H2.TLabel").grid(row=row, column=1, sticky="sw")
        sub = "Guest" if guest else f"{ranks.label(opp)}  ·  rating {opp.get('rating', '?')}"
        ttk.Label(parent, text=sub, style="Card.Muted.TLabel").grid(row=row + 1, column=1, sticky="nw")

    def _head(self, parent, caps, ranked, extra=None):
        px = self.px
        head = self.body(parent)
        ttk.Label(head, text=caps, style="Card.Caps.TLabel").pack(side="left")
        ttk.Label(head, text="RANKED" if ranked else "CASUAL",
                  style="Card.PillAccent.TLabel" if ranked else "Card.Pill.TLabel").pack(side="left", padx=(px(8), 0))
        if extra:
            ttk.Label(head, text=extra, style="Card.Pill.TLabel").pack(side="left", padx=(px(6), 0))
        return head

    def _visual_ready(self, v):
        tab, px = self.tab, self.px
        m = tab.match or {}
        v.columnconfigure(0, weight=1)
        left = self.body(v)
        left.grid(row=0, column=0, sticky="nw")
        left.columnconfigure(1, weight=1)
        self._head(left, "OPPONENT FOUND", m.get("ranked"),
                   "REMATCH" if m.get("origin") == "rematch" else None).grid(row=0, column=0, columnspan=2, sticky="w")
        opp = self.revealed or (None if m.get("blind") else m.get("opponent"))
        if opp:
            self._opponent_row(left, opp, 1)
        else:
            ttk.Label(left, text="Opponent hidden", style="Card.H2.TLabel").grid(row=1, column=0, columnspan=2,
                                                                               sticky="w", pady=(px(8), 0))
            ttk.Label(left, text="Name and side are shown once you both accept.", style="Card.Muted.TLabel").grid(
                row=2, column=0, columnspan=2, sticky="w")
        ping = m.get("ping") or {}
        ms = ping.get("ms") if ping.get("known") else None
        prow = self.body(left)
        prow.grid(row=3, column=0, columnspan=2, sticky="w", pady=(px(10), 0))
        bars = theme.PingBars(prow)
        bars.set(ms)
        bars.pack(side="left", padx=(0, px(10)))
        ttk.Label(prow, text=f"~{ms:.0f} ms" if ms is not None else "? ms", style="Card.Num.TLabel",
                  foreground=theme.ping_color(ms)).pack(side="left")
        ttk.Label(prow, text="  " + theme.ping_word(ms), style="Card.Bold.TLabel").pack(side="left")
        if ms is not None:
            ttk.Label(prow, text="  (estimate through the server)", style="Card.Faint.TLabel").pack(side="left")
        if tab.ready_sent:
            ttk.Label(left, text="Accepted. Waiting for your opponent...", style="Card.Accent.TLabel").grid(
                row=4, column=0, columnspan=2, sticky="w", pady=(px(8), 0))
        self.ring = theme.CountdownRing(v, size=92, width=8)
        self.ring.grid(row=0, column=1, sticky="ne", padx=(px(12), 0))
        self._update_ring()

    def _update_ring(self):
        tab = self.tab
        if self.ring is None:
            return
        total = float((tab.match or {}).get("ready_timeout") or 15)
        left = max(0.0, (tab.ready_deadline or 0) - time.monotonic()) if tab.ready_deadline else 0.0
        try:
            self.ring.set(left, total)
        except tk.TclError:
            self.ring = None

    def _visual_connecting(self, v):
        tab, px = self.tab, self.px
        m = tab.match or {}
        v.columnconfigure(0, weight=1)
        left = self.body(v)
        left.grid(row=0, column=0, sticky="nw")
        self._head(left, "MATCH READY", m.get("ranked"),
                   "REMATCH" if m.get("origin") == "rematch" else None).grid(row=0, column=0, columnspan=2, sticky="w",
                                                                             pady=(0, px(8)))
        opp = self.revealed or m.get("opponent")
        if opp:
            self._opponent_row(left, opp, 1)
        row = self.body(left)
        row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(px(12), 0))
        self.bar_spinner = theme.Spinner(row, size=22, width=3)
        self.bar_spinner.pack(side="left", padx=(0, px(10)))
        ttk.Label(row, text="Connecting the two games...", style="Card.Bold.TLabel").pack(side="left")

    def _visual_challenge(self, v):
        px = self.px
        ch = self.challenger or {}
        left = self.body(v)
        left.grid(row=0, column=0, sticky="nw")
        ttk.Label(left, text="CHALLENGE", style="Card.Caps.TLabel").grid(row=0, column=0, columnspan=2, sticky="w",
                                                                         pady=(0, px(8)))
        if ch:
            self._opponent_row(left, ch, 1)
        ttk.Label(left, text="wants to play you. Accept to start the match.", style="Card.TLabel").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(px(10), 0))

    # --- the result
    def _outcome(self):
        info = self.result_info or {}
        ev = info.get("ev") or {}
        st = ev.get("status")
        counted = st in ("confirmed", "onesided", "forfeit", "resolved")
        mine = info.get("mine")
        if counted and mine is True:
            return "win", "YOU WIN", "Win."
        if counted and mine is False:
            return "loss", "YOU LOSE", "Loss."
        if counted and ev.get("winner") is None:
            return "draw", "DRAW", "Even."
        if counted:
            return "over", "MATCH OVER", "Even."
        return "void", "NO CONTEST", "Even."

    def _visual_result(self, v):
        tab, px = self.tab, self.px
        info = self.result_info or {}
        ev = info.get("ev") or {}
        kind, title, pre = self._outcome()
        v.columnconfigure(0, weight=1)
        banner = self.card(v, pre + "TFrame", 10)
        banner.grid(row=0, column=0, sticky="we")
        banner.columnconfigure(1, weight=1)
        col = {"win": C["ok"], "loss": C["bad"]}.get(kind, C["text"])
        ttk.Label(banner, text=title, style=pre + "Huge.TLabel", foreground=col).grid(row=0, column=0, rowspan=2,
                                                                                       sticky="w")
        sub = ("Ranked" if info.get("ranked") else "Casual") + " match" + (
            f" vs {info['opp']}" if info.get("opp") else "")
        ttk.Label(banner, text=sub, style=pre + "Bold.TLabel").grid(row=0, column=1, sticky="sw", padx=(px(16), 0))
        ttk.Label(banner, text=info.get("text", ""), style=pre + "Small.TLabel").grid(row=1, column=1, sticky="nw",
                                                                                        padx=(px(16), 0))
        score = ev.get("score")
        if isinstance(score, (list, tuple)) and len(score) == 2:
            slot = info.get("slot")
            a, b = (score[0], score[1]) if slot != 1 else (score[1], score[0])
            sc = self.body(banner, pre.rstrip(".") + "Body.TFrame")
            sc.grid(row=0, column=2, rowspan=2, sticky="e", padx=(px(12), px(4)))
            ttk.Label(sc, text=f"{a} – {b}", style=pre + "Big.TLabel").pack(anchor="e")
            ttk.Label(sc, text="ROUNDS  (YOU – THEM)" if slot is not None else "ROUNDS  (P1 – P2)",
                      style=pre + "Caps.TLabel").pack(anchor="e")
        row = 1
        r = ev.get("rating")
        if r:
            rr = self.body(v)
            rr.grid(row=row, column=0, sticky="w", pady=(px(10), 0))
            row += 1
            after = r.get("after") or {}
            ttk.Label(rr, text=f"Rating {after.get('r', 0):.0f}", style="Card.Num.TLabel").pack(side="left")
            d = r.get("delta") or 0
            ttk.Label(rr, text=f"  {d:+.0f}", style="Card.Num.TLabel",
                      foreground=C["ok"] if d > 0 else C["bad"] if d < 0 else C["muted"]).pack(side="left")
            rank_after = r.get("rank_after") or {}
            evn = r.get("event")
            pill = {"promoted": ("PROMOTED", "Card.PillGold.TLabel"), "demoted": ("DEMOTED", "Card.PillBad.TLabel"),
                    "placed": ("PLACED", "Card.PillAccent.TLabel")}.get(evn)
            if pill:
                ttk.Label(rr, text=pill[0], style=pill[1]).pack(side="left", padx=(px(16), px(8)))
                bd = theme.Badge(rr, size=26)
                bd.set(_tier_of(rank_after), rank_after.get("provisional"))
                bd.pack(side="left", padx=(0, px(6)))
                ttk.Label(rr, text=rank_after.get("rank", ""), style="Card.Bold.TLabel").pack(side="left")
            elif rank_after.get("placement"):
                n, k = rank_after["placement"]
                ttk.Label(rr, text=f"   Placement match {n} of {k}", style="Card.Muted.TLabel").pack(side="left")
        lag = tab.lag
        if lag and lag.get("text"):
            bad = lag.get("verdict") == "more_lag"
            lr = self.body(v)
            lr.grid(row=row, column=0, sticky="we", pady=(px(8), 0))
            lr.columnconfigure(1, weight=1)
            ttk.Label(lr, text="LAG CHECK", style="Card.PillWarn.TLabel" if bad else "Card.Pill.TLabel").grid(
                row=0, column=0, sticky="nw", padx=(0, px(8)))
            self.wrap(ttk.Label(lr, text=lag["text"], style="Card.warn.TLabel" if bad else "Card.Small.TLabel",
                                justify="left"), self.stage_card, 150).grid(row=0, column=1, sticky="w")

    def _render_result_card(self):
        tab, px = self.tab, self.px
        sig = (id(self.result_info), (tab.lag or {}).get("text"), tab.client is not None)
        if sig == self._res_sig:
            return
        self._res_sig = sig
        for w in self.res_visual.winfo_children():
            w.destroy()
        for w in self.res_buttons.winfo_children():
            w.destroy()
        self._visual_result(self.res_visual)
        info = self.result_info or {}
        ttk.Button(self.res_buttons, text="Next game", style="Card.Accent.TButton",
                   command=self._next_game).pack(side="left")
        ttk.Button(self.res_buttons, text="Back to the lobby", style="Card.TButton",
                   command=self.dismiss_result).pack(side="left", padx=(px(8), 0))
        opp = info.get("opp")
        if opp and tab.client is not None:
            ttk.Button(self.res_buttons, text=f"Block {opp}", style="Card.Danger.TButton",
                       command=lambda: tab.block_opponent(opp)).pack(side="left", padx=(px(8), 0))
        if hasattr(tab.app, "report_problem"):
            ttk.Button(self.res_buttons, text="Report a problem...", style="Card.Link.TButton",
                       command=tab.do_report).pack(side="left", padx=(px(12), 0))
        self._on_resize()

    def _next_game(self):
        tab = self.tab
        mode = tab._pad_search_mode()
        self.dismiss_result()
        if mode:
            tab.do_queue(mode)

    def dismiss_result(self):
        self.result_dismissed = True
        self.refresh()

    # ------------------------------------------------------------------ animation
    def _anim_needed(self):
        if self._stage == "search":
            return True
        return self._stage == "bar" and (self.ring is not None or self.bar_spinner is not None)

    def _ensure_anim(self):
        if self._anim_id is None and self._anim_needed():
            self._anim_t = time.monotonic()
            try:
                self._anim_id = self.box.after(33, self._anim)
            except tk.TclError:
                self._anim_id = None

    def _anim(self):
        self._anim_id = None
        try:
            shown = bool(self.box.winfo_viewable())
        except tk.TclError:
            return
        now = time.monotonic()
        dt = min(0.2, now - self._anim_t)
        self._anim_t = now
        try:
            if self._stage == "search":
                if shown:
                    self.spinner.step(dt)
                self._update_elapsed()
            if self.ring is not None:
                self._update_ring()
            if self.bar_spinner is not None and shown:
                self.bar_spinner.step(dt)
        except tk.TclError:
            return
        if self._anim_needed():
            try:
                self._anim_id = self.box.after(33 if shown else 250, self._anim)
            except tk.TclError:
                self._anim_id = None

    def close(self):
        if self._anim_id is not None:
            try:
                self.box.after_cancel(self._anim_id)
            except (tk.TclError, ValueError):
                pass
            self._anim_id = None

    # ------------------------------------------------------------------ windows
    def codes_window(self, codes, first, save):
        """The recovery codes, once: big, numbered, with 'Save to a file...' and 'I have saved them'."""
        px = self.px
        w = tk.Toplevel(self.tab.parent)
        w.title("Recovery codes")
        w.configure(bg=C["bg"])
        card = self.card(w, pad=20)
        card.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text="Your account is ready" if first else "New recovery codes",
                  style="Card.H2.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, wraplength=px(440), justify="left", style="Card.Muted.TLabel", text=(
            "These codes are the only way back into your account if you forget the password (there is no "
            "e-mail). Each code works once. Write them down or save them somewhere safe -- they are not "
            "shown again.")).grid(row=1, column=0, sticky="w", pady=(px(6), px(12)))
        grid = self.body(card)
        grid.grid(row=2, column=0, sticky="w")
        for i, code in enumerate(codes):
            tile = self.card(grid, "Tile.TFrame", 8)
            tile.grid(row=i // 2, column=i % 2, sticky="we", padx=(0, px(8)), pady=(0, px(8)))
            ttk.Label(tile, text=f"{i + 1:>2}", style="Tile.Faint.TLabel").pack(side="left", padx=(0, px(10)))
            ttk.Label(tile, text=code, style="Tile.TLabel", font=self.th.fonts["code"]).pack(side="left")
        bar = self.body(card)
        bar.grid(row=3, column=0, sticky="we", pady=(px(8), 0))
        ttk.Button(bar, text="Save to a file...", style="Card.TButton", command=lambda: save(w)).pack(side="left")
        done = ttk.Button(bar, text="I have saved them", style="Card.Accent.TButton", command=w.destroy)
        done.pack(side="right")
        try:
            done.focus_set()
        except tk.TclError:
            pass
        return w
