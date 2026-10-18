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
from .i18n import N_, t
from .lag import describe_event as describe_lag
from .theme import C

# column headings of the lists, by column id (shown in capitals)
HEADINGS = {"player": N_("Player"), "rank": N_("Rank"), "rating": N_("Rating"), "record": N_("Record"),
            "main": N_("Main"), "status": N_("Status"), "ping": N_("Ping"), "room": N_("Room"),
            "owner": N_("Owner"), "state": N_("State"), "place": N_("Place"), "when": N_("When"),
            "result": N_("Result"), "opponent": N_("Opponent"), "chars": N_("Characters"), "score": N_("Score")}

# What the player can do about an error: words to look for in the message (lower case; the English words of the
# server's / client's message and the German ones of its translation, i18n_known.py), and the tip. The same
# tips in both languages are in the catalog; tests/test_i18n.py checks that each pair of words belongs together.
ERROR_HELP = (
    (("cannot reach", "ist nicht erreichbar"),
     N_("Check the server address and your internet connection, then try again.")),
    (("did not answer", "nicht geantwortet"), N_("Check your internet connection, then try again.")),
    (("no answer to", "keine antwort auf"), N_("The server is slow or gone; try again in a minute.")),
    (("not connected to the lobby", "nicht mit der lobby verbunden"), N_("Log in again.")),
    (("certificate does not match", "zertifikat des servers passt nicht"),
     N_("Ask whoever runs the server for its current fingerprint (\"Server certificate...\").")),
    (("wrong name or password", "name oder passwort falsch"),
     N_("Check the spelling, or use \"Forgot password...\".")),
    (("wrong name or recovery code", "name oder wiederherstellungs-code falsch"),
     N_("Check the name and the code; each code works once.")),
    (("someone with that name is online", "jemand mit diesem namen ist online"),
     N_("Pick another name, or wait a minute if that was you.")),
    (("that name belongs to an account", "dieser name gehört zu einem konto"),
     N_("Log in with that account's password, or pick another name.")),
    (("that name is taken", "dieser name ist schon vergeben"), N_("Pick another name.")),
    (("that name is reserved", "dieser name ist reserviert"), N_("Pick another name.")),
    (("not accepted by this server", "akzeptiert den build"),
     N_("Update the game to the release this server asks for.")),
    (("different build", "anderen build", "anderer build"), N_("You both need the same release of the game.")),
    (("lobby protocol", "lobby-protokoll"), N_("Update the launcher to the newest release.")),
    (("ranked needs an account", "ranked braucht ein konto"), N_("Create an account (free) to play ranked.")),
    (("room is full", "raum ist voll"), N_("Pick another room or create your own.")),
    (("saved login has expired", "gespeicherte anmeldung ist abgelaufen"), N_("Log in with your password.")),
    (("session expired", "sitzung abgelaufen"), N_("Log in with your password.")),
    (("not built", "nicht gebaut"), N_("Build the game on the Build tab first.")),
    (("no udp connection", "keine udp-verbindung"),
     N_("Allow T5DR Online through the Windows firewall, then search again.")),
    (("not even through the relay", "auch nicht über das relay"),
     N_("Try again; if it keeps failing, check your firewall or router.")),
    (("lost the lobby connection", "verbindung zur lobby verloren", "lost the connection to the lobby server",
      "verbindung zum lobby-server verloren"),
     N_("Log in again; your settings are kept.")),
    (("passwords differ", "passwörter sind verschieden"), N_("Type the same password twice.")),
    (("no longer available", "nicht mehr da"), N_("Find a new opponent.")),
    (("that match is over", "match ist vorbei"), N_("Find a new opponent.")),
    (("could not start", "nicht gestartet werden", "nicht starten"), N_("Check the Play offline tab: does the game start there?")),
)


def friendly_error(text):
    """'Lobby: wrong name or password' -> 'Wrong name or password. Check the spelling, or use ...'
    (the same in German: 'Lobby: Name oder Passwort falsch' -> 'Name oder Passwort falsch. Prüfe ...')."""
    msg = proto.scrub_addresses(str(text or "")).strip()
    for prefix in (t("Lobby error: {error}", error="\0").split("\0")[0], t("Lobby: {message}", message="\0").split("\0")[0],
                   "Lobby error: ", "Lobby: "):
        if prefix and msg.startswith(prefix):
            msg = msg[len(prefix):]
    if not msg:
        return ""
    msg = msg[0].upper() + msg[1:]
    low = msg.lower()
    tip = next((tip_text for words, tip_text in ERROR_HELP if any(w in low for w in words)), "")
    tip = t(tip) if tip else ""
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
        self._wrap_after = None
        self.revealed = None               # the opponent once both accepted (match_reveal)
        self.challenger = None
        self.match_ev = None               # match_start of the match being played
        self.game_phase = None
        self.fighters = None               # (p1, p2) once the game says who fights
        self.result_info = None
        self.result_dismissed = True
        self.queue_counts = {}
        self.search_t0 = None
        self.rematch_pending = False       # we offered a rematch and wait for the opponent
        self.err_var = tk.StringVar(tab.parent, value="")
        self.pw2_var = tk.StringVar(tab.parent, value="")
        self.host_var = tk.StringVar(tab.parent, value="")
        self.ring = None
        self.bar_spinner = None
        self._build()
        tab.set_var.trace_add("write", lambda *_: self.refresh())

    # ------------------------------------------------------------------ helpers
    def card(self, parent, style="Card.TFrame", pad=14):
        return ttk.Frame(parent, style=style, padding=self.px(pad))

    def body(self, parent, style="CardBody.TFrame"):
        return ttk.Frame(parent, style=style)

    def wrap(self, label, container, margin=0):
        """The label wraps at the container's width (less `margin` pixels at 96 DPI). It starts narrow,
        so it never makes its container wider than the window gives it; widths are applied once the
        layout has settled (debounced), and small changes are ignored (no relayout ping-pong)."""
        self._wraps.append((label, container, margin))
        try:
            label.configure(wraplength=self.px(300))
        except tk.TclError:
            pass
        key = str(container)
        if key not in self._wrap_bound:
            self._wrap_bound.add(key)
            container.bind("<Configure>", lambda _e: self._on_resize(), add="+")
        return label

    def _on_resize(self, _e=None):
        if self._wrap_after is None:
            try:
                self._wrap_after = self.box.after(60, self._apply_wraps)
            except tk.TclError:
                self._wrap_after = None

    def _apply_wraps(self):
        self._wrap_after = None
        slack = self.px(8)
        for label, cont, margin in self._wraps:
            try:
                if not label.winfo_exists():
                    continue
                w = cont.winfo_width()
                if w <= 50:
                    continue
                want = max(self.px(120), w - self.px(margin))
                cur = int(float(str(label.cget("wraplength") or 0)))
                if abs(cur - want) > slack:
                    label.configure(wraplength=want)
            except (tk.TclError, ValueError):
                pass

    def tree(self, parent, cols, widths, height=6, image_col=True, select="browse"):
        frame = self.body(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tv = ttk.Treeview(frame, columns=cols, show="tree headings" if image_col else "headings", height=height,
                          style="Lobby.Treeview",
                          selectmode=select)
        if image_col:
            tv.heading("#0", text="")
            tv.column("#0", width=self.px(36), minwidth=self.px(36), stretch=False, anchor="center")
        for c, w in zip(cols, widths):
            tv.heading(c, text=t(HEADINGS[c]).upper(), anchor="w")
            tv.column(c, width=self.px(w), minwidth=self.px(min(w, 50)), anchor="w")
        tv.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        sb.grid(row=0, column=1, sticky="ns", padx=(self.px(4), 0))
        tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("me", font=self.th.fonts["bold"])
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
        ttk.Label(head, text=t("Play online"), style="H1.TLabel").pack(anchor="w")
        ttk.Label(head, style="Muted.TLabel", text=t(
            "Against other players over the internet. Log in or play as a guest; the game starts by itself, "
            "straight into the fight, and the result comes back here.")).pack(anchor="w")

        card = self.card(scr, pad=18)
        card.grid(row=1, column=0, sticky="nsew", padx=(0, px(12)))
        card.columnconfigure(0, weight=1)
        tab.acc = card
        ttk.Label(card, text=t("Server").upper(), style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        srow = self.body(card)
        srow.grid(row=1, column=0, sticky="we", pady=(px(4), px(10)))
        srow.columnconfigure(0, weight=1)
        self.server_cb = ttk.Combobox(srow, textvariable=tab.server_var, style="Card.TCombobox",
                                      values=[x.name for x in tab.server_list])
        self.server_cb.grid(row=0, column=0, sticky="we")
        tab.b_tls = ttk.Button(srow, text=t("Server certificate..."), style="Card.Ghost.TButton",
                               command=tab.do_fingerprint)
        tab.b_tls.grid(row=0, column=1, padx=(px(6), 0))
        ttk.Label(card, text=t("Name").upper(), style="Card.Caps.TLabel").grid(row=2, column=0, sticky="w")
        self.name_entry = ttk.Entry(card, textvariable=tab.name_var, style="Card.TEntry")
        self.name_entry.grid(row=3, column=0, sticky="we", pady=(px(4), px(14)))
        self.name_entry.bind("<Return>", lambda _e: self._name_return())

        seg = ttk.Frame(card, style="SegTrack.TFrame", padding=px(3))
        seg.grid(row=4, column=0, sticky="w", pady=(0, px(12)))
        mode = tab.cfg.get("login_mode")
        self.mode_var = tk.StringVar(card, value=mode if mode in ("login", "register", "guest") else "login")
        self.seg_buttons = {}
        for key, text in (("login", t("Log in")), ("register", t("Create account")), ("guest", t("Guest"))):
            b = ttk.Radiobutton(seg, text=text, value=key, variable=self.mode_var, style="Seg.TRadiobutton",
                                command=self._mode_changed)
            b.pack(side="left")
            self.seg_buttons[key] = b

        # account: log in / create
        pa = self.body(card)
        pa.columnconfigure(0, weight=1, uniform="pw")
        pa.columnconfigure(1, weight=1, uniform="pw")
        self.pane_account = pa
        self.pw_label = ttk.Label(pa, text=t("Password").upper(), style="Card.Caps.TLabel")
        self.pw_entry = ttk.Entry(pa, textvariable=tab.pw_var, show="•", style="Card.TEntry")
        self.pw_entry.bind("<Return>", lambda _e: self._pw_return())
        self.pw2_label = ttk.Label(pa, text=t("Password again").upper(), style="Card.Caps.TLabel")
        self.pw2_entry = ttk.Entry(pa, textvariable=self.pw2_var, show="•", style="Card.TEntry")
        self.pw2_entry.bind("<Return>", lambda _e: tab.do_login("register"))
        self.rules = self.body(pa)
        self.rule_labels = {}
        for i, (key, text) in enumerate((
                ("name", t("Name: 2 to 16 letters, digits, spaces or _-.[]()!?")),
                ("length", t("Password: 6 to 128 characters")),
                ("same", t("Both passwords the same")),
                ("codes", t("You get recovery codes once: the only way back in if you forget the password")))):
            lab = ttk.Label(self.rules, text="•  " + text, style="Card.Small.TLabel")
            lab.grid(row=i, column=0, sticky="w")
            self.rule_labels[key] = (lab, text)
        for var in (tab.name_var, tab.pw_var, self.pw2_var):
            var.trace_add("write", lambda *_: self._check_rules())
        act = self.body(pa)
        act.grid(row=5, column=0, columnspan=2, sticky="we", pady=(px(4), 0))
        act.columnconfigure(1, weight=1)
        ttk.Checkbutton(act, text=t("Remember me"), variable=tab.remember_var, style="Card.TCheckbutton").grid(
            row=0, column=0, sticky="w")
        tab.b_forgot = ttk.Button(act, text=t("Forgot password..."), style="Card.Link.TButton",
                                  command=tab.do_forgot)
        tab.b_forgot.grid(row=0, column=1, sticky="w", padx=(px(10), 0))
        tab.b_login = ttk.Button(act, text=t("Log in"), style="Card.Accent.TButton",
                                 command=lambda: tab.do_login("account"))
        tab.b_register = ttk.Button(act, text=t("Create account"), style="Card.Accent.TButton",
                                    command=lambda: tab.do_login("register"))
        self.act_row = act

        # guest
        pg = self.body(card)
        pg.columnconfigure(0, weight=1)
        self.pane_guest = pg
        self.wrap(ttk.Label(pg, style="Card.Muted.TLabel", justify="left", text=t(
            "Casual matches with the name above, no account and no password. Ranked matches, the "
            "leaderboard and your match history need an account.")), card, 40).grid(row=0, column=0, sticky="w")
        tab.b_guest = ttk.Button(pg, text=t("Play as guest"), style="Card.Accent.TButton",
                                 command=lambda: tab.do_login("guest"))
        tab.b_guest.grid(row=1, column=0, sticky="e", pady=(px(12), 0))
        self.wrap(ttk.Label(card, style="Card.Faint.TLabel", justify="left", text=t(
            "Passwords are only sent to servers on this PC / your network, or over an encrypted (TLS) connection.")),
                  card, 40).grid(row=6, column=0, sticky="w", pady=(px(14), 0))

        # side: host for friends, how it works
        side = ttk.Frame(scr)
        side.grid(row=1, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        hc = self.card(side, pad=16)
        hc.grid(row=0, column=0, sticky="we")
        hc.columnconfigure(0, weight=1)
        ttk.Label(hc, text=t("Host for friends").upper(), style="Card.Caps.TLabel").grid(row=0, column=0,
                                                                                         sticky="w")
        self.wrap(ttk.Label(hc, style="Card.Muted.TLabel", justify="left", text=t(
            "Runs a lobby on this PC. Your friends type the address it shows into their Server box.")),
                  hc, 36).grid(row=1, column=0, sticky="w", pady=(px(4), px(8)))
        hrow = self.body(hc)
        hrow.grid(row=2, column=0, sticky="w")
        tab.b_host = ttk.Button(hrow, text=t("Host for friends"), style="Card.TButton", command=tab.do_host)
        tab.b_host.pack(side="left")
        ttk.Checkbutton(hc, text=t("Open router ports (UPnP)"), variable=tab.map_var,
                        style="Card.TCheckbutton").grid(
            row=3, column=0, sticky="w", pady=(px(8), 0))
        self.host_label = self.wrap(ttk.Label(hc, textvariable=self.host_var, style="Card.Accent.TLabel",
                                              justify="left"), hc, 36)

        how = self.card(side, pad=16)
        how.grid(row=1, column=0, sticky="we", pady=(px(12), 0))
        how.columnconfigure(1, weight=1)
        ttk.Label(how, text=t("How it works").upper(), style="Card.Caps.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, px(6)))
        for i, text in enumerate((t("Quick match (casual) or Ranked match (account)."),
                                  t("An opponent is found: accept within 15 seconds."),
                                  t("The game opens straight into the fight."),
                                  t("The result comes back here: rematch or next game."))):
            ttk.Label(how, text=str(i + 1), style="Card.Accent.TLabel").grid(row=i + 1, column=0, sticky="nw",
                                                                            padx=(0, px(10)), pady=px(2))
            self.wrap(ttk.Label(how, text=text, style="Card.TLabel", justify="left"), how, 60).grid(
                row=i + 1, column=1, sticky="w", pady=px(2))
        ttk.Label(how, text=t("With a controller: A accepts, B declines."), style="Card.Faint.TLabel").grid(
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
            for w in (self.pw_label, self.pw_entry, self.pw2_label, self.pw2_entry, self.rules):
                w.grid_forget()
            if reg:                         # the two password boxes side by side (the card stays short)
                self.pw_label.grid(row=0, column=0, sticky="w")
                self.pw_entry.grid(row=1, column=0, sticky="we", padx=(0, px(6)), pady=(px(4), px(8)))
                self.pw2_label.grid(row=0, column=1, sticky="w", padx=(px(6), 0))
                self.pw2_entry.grid(row=1, column=1, sticky="we", padx=(px(6), 0), pady=(px(4), px(8)))
                self.rules.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, px(6)))
            else:
                self.pw_label.grid(row=0, column=0, columnspan=2, sticky="w")
                self.pw_entry.grid(row=1, column=0, columnspan=2, sticky="we", pady=(px(4), px(8)))
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
        nb.add(lobby, text=t("Lobby"))
        nb.add(board, text=t("Leaderboard"))
        nb.add(prof, text=t("Profile"))
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
        tab.b_myprofile = ttk.Button(row, text=t("My profile"), style="Card.Small.TButton",
                                     command=lambda: tab.show_profile(None))
        tab.b_myprofile.pack(side="left")
        tab.b_logout = ttk.Button(row, text=t("Log out"), style="Card.Small.TButton", command=tab.do_logout)
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
        ttk.Label(top, text=t("Find an opponent online").upper(), style="Card.Caps.TLabel").grid(
            row=0, column=0, sticky="w")
        self.room_label = ttk.Label(top, text="", style="Card.Accent.TLabel")
        self.room_label.grid(row=1, column=0, sticky="w")
        ttk.Label(top, text=t("Character"), style="Card.Muted.TLabel").grid(row=0, column=1, rowspan=2, sticky="e",
                                                                          padx=(0, px(8)))
        names = [t("Random")] + [x["name"] for x in tab.table.selectable()]
        cb = ttk.Combobox(top, textvariable=tab.char_var, values=names, state="readonly", width=15,
                          style="Card.TCombobox")
        cb.grid(row=0, column=2, rowspan=2, sticky="e")
        cb.bind("<<ComboboxSelected>>", lambda _e: tab.on_char())
        tab.char_cb = cb
        self.lock_label = ttk.Label(top, text=t("Locked for this ranked set"), style="Card.Faint.TLabel")
        tab.actions = {}
        tab.action_text = {}
        b = ttk.Button(f, text=t("Ranked match"), style="Card.Hero.TButton", state="disabled",
                       command=lambda: tab.do_queue("ranked"))
        b.grid(row=1, column=0, sticky="we", padx=(0, px(6)))
        tab.actions["ranked"], tab.action_text["ranked"] = b, t("Ranked match")
        b = ttk.Button(f, text=t("Quick match"), style="Card.HeroAlt.TButton", state="disabled",
                       command=lambda: tab.do_queue("quick"))
        b.grid(row=1, column=1, sticky="we", padx=(px(6), 0))
        tab.actions["quick"], tab.action_text["quick"] = b, t("Quick match")
        self.ranked_sub = ttk.Label(f, text="", style="Card.Small.TLabel")
        self.ranked_sub.grid(row=2, column=0, sticky="w", pady=(px(5), 0))
        self.quick_sub = ttk.Label(f, text=t("Casual: the lowest ping first"), style="Card.Small.TLabel")
        self.quick_sub.grid(row=2, column=1, sticky="w", padx=(px(6), 0), pady=(px(5), 0))
        tab.strict_check = ttk.Checkbutton(f, text=t("Strict (ranked: +-150 rating)"), variable=tab.strict_var,
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
        ttk.Label(head, text=t("Searching").upper(), style="Card.Caps.TLabel").pack(side="left")
        self.search_pill = ttk.Label(head, text=t("RANKED"), style="Card.PillAccent.TLabel")
        self.search_pill.pack(side="left", padx=(px(8), 0))
        self.search_title = ttk.Label(f, text=t("Looking for an opponent"), style="Card.H2.TLabel")
        self.search_title.grid(row=1, column=1, sticky="w", pady=(px(2), 0))
        self.search_rules = self.wrap(ttk.Label(f, text="", style="Card.Muted.TLabel", justify="left"), card, 160)
        self.search_rules.grid(row=2, column=1, sticky="w")
        self.search_queue = ttk.Label(f, text="", style="Card.Faint.TLabel")
        self.search_queue.grid(row=3, column=1, sticky="w")
        clock = self.body(f)
        clock.grid(row=0, column=2, rowspan=3, sticky="ne")
        self.search_time = ttk.Label(clock, text="0:00", style="Card.Big.TLabel")
        self.search_time.pack(anchor="e")
        ttk.Label(clock, text=t("Searching for").upper(), style="Card.Caps.TLabel").pack(anchor="e")
        b = ttk.Button(f, text=t("Stop searching"), style="Card.TButton", state="disabled",
                       command=lambda: tab.call(tab.client.cancel_queue))
        b.grid(row=4, column=1, sticky="w", pady=(px(12), 0))
        tab.actions["cancel"], tab.action_text["cancel"] = b, t("Stop searching")
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
        ttk.Label(head, text=t("In match").upper(), style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.m_pill = ttk.Label(head, text=t("CASUAL"), style="Card.Pill.TLabel")
        self.m_pill.grid(row=0, column=1, sticky="w", padx=(px(8), 0))
        self.m_set = ttk.Label(head, text="", style="Card.PillGold.TLabel")
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
        ttk.Label(t1, text=t("Ping").upper(), style="Tile.Caps.TLabel").grid(row=0, column=0, columnspan=2,
                                                                              sticky="w")
        self.m_bars = theme.PingBars(t1, bg=C["raised"])
        self.m_bars.grid(row=1, column=0, sticky="w", padx=(0, px(8)))
        self.m_ping = ttk.Label(t1, text="", style="Tile.Num.TLabel")
        self.m_ping.grid(row=1, column=1, sticky="w")
        t2 = self.card(tiles, "Tile.TFrame", 10)
        t2.grid(row=0, column=1, sticky="nsew", padx=px(3))
        ttk.Label(t2, text=t("Input delay").upper(), style="Tile.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.m_delay = ttk.Label(t2, text="", style="Tile.Num.TLabel")
        self.m_delay.grid(row=1, column=0, sticky="w")
        t3 = self.card(tiles, "Tile.TFrame", 10)
        t3.grid(row=0, column=2, sticky="nsew", padx=(px(6), 0))
        ttk.Label(t3, text=t("Connection").upper(), style="Tile.Caps.TLabel").grid(row=0, column=0, sticky="w")
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
        page.rowconfigure(1, weight=1)
        pc = self.card(page, pad=12)
        pc.grid(row=0, column=0, sticky="nsew")
        pc.columnconfigure(0, weight=1)
        pc.rowconfigure(1, weight=1)
        self.players_count = tk.StringVar(page, value="")
        head, tools = self.section_head(pc, t("Players online").upper(), self.players_count)
        head.grid(row=0, column=0, sticky="we", pady=(0, px(6)))
        b = ttk.Button(tools, text=t("Challenge"), style="Card.Small.TButton", state="disabled",
                       command=tab.do_challenge)
        b.pack(side="left")
        tab.actions["challenge"], tab.action_text["challenge"] = b, t("Challenge")
        ttk.Button(tools, text=t("Profile"), style="Card.Small.TButton", command=tab._profile_of_selected).pack(
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
        head, tools = self.section_head(rc, t("Rooms").upper(), self.rooms_count)
        head.grid(row=0, column=0, sticky="we", pady=(0, px(6)))
        for key, label, cmd in (("room", t("Create room"), lambda: tab.call(tab.client.create_room, None)),
                                ("join", t("Join room"), tab.do_join),
                                ("leave", t("Leave room"), lambda: tab.call(tab.client.leave_room))):
            b = ttk.Button(tools, text=label, style="Card.Small.TButton", state="disabled", command=cmd)
            b.pack(side="left", padx=(px(6), 0))
            tab.actions[key], tab.action_text[key] = b, label
        fr, tab.tv_rooms = self.tree(rc, ("room", "owner", "state", "ping"), (190, 140, 140, 70), height=2)
        fr.grid(row=1, column=0, sticky="nsew")
        tab.tv_rooms.bind("<Double-1>", lambda _e: tab.do_join() if str(tab.actions["join"].cget("state")) ==
                          "normal" else None)

        cc = self.card(page, pad=12)
        cc.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(px(10), 0))
        cc.columnconfigure(0, weight=1)
        cc.rowconfigure(1, weight=1)
        head, _tools = self.section_head(cc, t("Chat").upper())
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
        ttk.Button(row, text=t("Send"), style="Card.TButton", command=tab.do_chat).grid(row=0, column=1,
                                                                                        padx=(px(6), 0))

    def _build_board_page(self, page):
        tab, px = self.tab, self.px
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        card = self.card(page, pad=12)
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)
        head, tools = self.section_head(card, t("Leaderboard").upper())
        head.grid(row=0, column=0, sticky="we")
        ttk.Button(tools, text=t("Refresh"), style="Card.Small.TButton", command=tab.load_leaderboard).pack(
            side="left")
        ttk.Label(card, style="Card.Faint.TLabel", text=t(
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
        ttk.Label(acc, text=t("Your account").upper(), style="Caps.TLabel").pack(side="left", padx=(0, px(10)))
        tab.b_blocked = ttk.Button(acc, text=t("Blocked players..."), style="Small.TButton", command=tab.do_blocked)
        tab.b_passwd = ttk.Button(acc, text=t("Change password..."), style="Small.TButton", command=tab.do_passwd)
        tab.b_codes = ttk.Button(acc, text=t("New recovery codes..."), style="Small.TButton",
                                 command=tab.do_new_codes)
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
        err = self.card(box, "Err.TFrame", 6)
        err.columnconfigure(1, weight=1)
        icon = tk.Canvas(err, width=px(20), height=px(20), bg=C["err_bg"], highlightthickness=0, takefocus=0)
        icon.create_oval(1, 1, px(20) - 1, px(20) - 1, fill=C["bad"], outline="")
        icon.create_text(px(10), px(10), text="!", fill="#1a0707", font=(self.th.fonts["h3"].actual("family"), 10,
                                                                         "bold"))
        icon.grid(row=0, column=0, sticky="nw", padx=(0, px(10)))
        self.err_label = self.wrap(ttk.Label(err, textvariable=self.err_var, style="Err.TLabel", justify="left"),
                                   box, 140)
        self.err_label.grid(row=0, column=1, sticky="w")
        ttk.Button(err, text=t("Dismiss"), style="Err.Ghost.TButton", command=self.clear_error).grid(
            row=0, column=2, sticky="e")
        self.err_frame = err
        note = self.card(box, "Note.TFrame", 6)
        note.columnconfigure(1, weight=1)
        ttk.Label(note, text=t("Server").upper(), style="Note.Caps.TLabel").grid(row=0, column=0, sticky="nw",
                                                                                  padx=(0, px(10)))
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
        self.box.after_idle(self._place_status)
        rep = ttk.Frame(st)
        rep.grid(row=0, column=1, sticky="e", padx=(px(10), px(10)))
        # after a match: the launcher's "Report a problem" window (tk_tab packs it into this frame)
        tab.report_btn = ttk.Button(rep, text=t("Report a problem..."), style="Small.TButton",
                                    command=tab.do_report)
        pad = ttk.Frame(st)
        pad.grid(row=0, column=2, sticky="e")
        ttk.Label(pad, textvariable=tab.pad_info_var, style="Faint.TLabel").pack(side="left", padx=(0, px(10)))
        tab.pad_check = ttk.Checkbutton(pad, text=t("Use a controller here"), variable=tab.pad_var,
                                        command=tab._pad_toggle)
        tab.pad_check.pack(side="left")

    def _place_status(self):
        """The tab's own status line, unless the launcher shows the same line in its status bar."""
        try:
            if isinstance(getattr(self.tab.app, "status", None), tk.StringVar):
                self.status_label.grid_remove()
        except tk.TclError:
            pass

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
        before, _x, after = t("Block {name}", name="\0").partition("\0")
        if label.startswith(before) and label.endswith(after) and len(label) > len(before) + len(after):
            return "Card.Danger.TButton"             # ("Block Rival" / "Rival blockieren")
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
        kind = ev.get("t")
        tab = self.tab
        if kind == "lobby_state":
            self.queue_counts = ev.get("queue") or {}
            players = ev.get("players", [])
            rooms = ev.get("rooms", [])
            self.players_count.set(f"{len(players)}")
            self.rooms_count.set(f"{len(rooms)}" if rooms else t("none open"))
            room = None
            me = tab.client.me if tab.client else None
            for r in rooms:
                if me and me.get("id") in (r.get("members") or []):
                    room = r
            if room is not None:
                text = (t("In your room “{name}”. Waiting for a second player...", name=room["name"])
                        if len(room.get("members") or []) < 2 else
                        t("In the room “{name}”. The match starts when you are both ready.", name=room["name"]))
            else:
                text = ""
            self.room_label.configure(text=text)
        elif kind == "challenged":
            self.challenger = ev.get("from")
        elif kind == "match_found":
            self.revealed = None
            self.rematch_pending = False
            self.clear_error()
            self.result_dismissed = True
        elif kind == "rematch" and ev.get("state") == "declined":
            self.rematch_pending = False
            self._res_sig = None
        elif kind == "set_end":
            self.rematch_pending = False
            self._res_sig = None
        elif kind == "match_reveal":
            self.revealed = ev.get("opponent")
        elif kind == "match_start":
            self.match_ev = ev
            self.game_phase = None
            self.fighters = None
            self.result_dismissed = True
        elif kind in ("match_cancel", "disconnected"):
            self.revealed = None
        if kind == "disconnected":                          # (the reason is technical: the status line has it)
            self.show_error(t("Lost the connection to the lobby server."))
        elif (kind == "match_cancel" and ev.get("reason") in ("udp_unreachable", "no_connection")) or kind == "kicked":
            self.show_error(tab.status_var.get())          # the tab has just said what happened
        self.refresh()

    def rematch_sent(self, accept):
        self.rematch_pending = bool(accept)
        self._res_sig = None

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
        share = info.get("internet") or f"{t('<your public IP>')}:{info.get('port')}" + (
            f"#{info['fingerprint']}" if info.get("fingerprint") else "")
        text = t("Hosting. Friends type this as their Server:\n{share}", share=share)
        if info.get("lan"):
            text += "\n" + t("Same network: {lan}", lan=str(info["lan"]))
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
            self.me_rank.configure(text=t("Guest · casual matches"), foreground=C["muted"])
            self.me_stats.configure(text=t("{record} this session", record=ranks.record_label(rec)))
            self.me_main.configure(text="")
        else:
            self.me_rank.configure(text=ranks.label(me), foreground=theme.mix(theme.tier_color(tier), "#ffffff", 0.25))
            self.me_stats.configure(text=t("Rating {rating}  ·  {record}", rating=me.get("rating"),
                                           record=ranks.record_label(rec, draws=True)))
            self.me_main.configure(text=t("Main: {character}", character=tab.table.fighter_name(me["main"]))
                                   if me.get("main") else "")
        conn = t("Server ping {ms} ms", ms=f"{c.server_rtt or 0:.0f}")
        if c.tls:
            conn += "  ·  " + t("encrypted")
        self.me_conn.configure(text=conn)

    def _update_play(self):
        tab = self.tab
        me = tab.client.me if tab.client is not None and tab.client.me else None
        guest = (me or {}).get("guest", True)
        self.ranked_sub.configure(text=t("Create an account to play ranked") if me and guest else
                                  t("Rated: close to your rank, good connection"))
        if tab.set_locked and not self.lock_label.winfo_manager():
            self.lock_label.grid(row=2, column=1, columnspan=2, sticky="e")
        elif not tab.set_locked and self.lock_label.winfo_manager():
            self.lock_label.grid_forget()

    # --- searching
    def _update_search(self):
        tab = self.tab
        mode = tab.cfg.get("last_search") or "quick"
        strict = mode == "ranked" and bool(tab.strict_var.get())
        self.search_pill.configure(text=t("RANKED") if mode == "ranked" else t("CASUAL"),
                                   style="Card.PillAccent.TLabel" if mode == "ranked" else "Card.Pill.TLabel")
        self.search_title.configure(text=t("Ranked match") if mode == "ranked" else t("Quick match"))
        if mode == "ranked":
            rules = (t("Similar rank and a good connection, strict: within 150 rating points (this can take a "
                       "while).") if strict else t("Similar rank and a good connection."))
        else:
            rules = t("The opponent with the lowest ping first.")
        self.search_rules.configure(text=rules)
        q = self.queue_counts or {}
        self.search_queue.configure(text=t("{ranked} in the ranked queue  ·  {quick} in quick match",
                                           ranked=q.get("ranked", 0), quick=q.get("quick", 0)))
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
        set_text = self.set_text(ev)
        sig = (id(ev), running, phase, self.fighters, set_text)
        if sig == self._match_sig:
            return
        self._match_sig = sig
        if set_text:
            self.m_set.configure(text=set_text)
            self.m_set.grid(row=0, column=2, sticky="w", padx=(self.px(6), 0))
        else:
            self.m_set.grid_forget()
        opp = ev.get("opponent") or (getattr(drv.ticket, "opponent", None) if drv and drv.ticket else None) or {}
        ranked = ev.get("ranked")
        self.m_pill.configure(text=(t("RANKED") if ranked else t("CASUAL")) + (
            "  ·  " + t("rematch").upper() if ev.get("origin") == "rematch" else ""),
                              style="Card.PillAccent.TLabel" if ranked else "Card.Pill.TLabel")
        state = {"title": t("The game is starting..."), "select": t("Character select"),
                 "stage": t("Stage select"), "loading": t("Loading the fight..."), "fight": t("Fight!"),
                 "over": t("Match over"), "neutral": t("Waiting for the next match")}.get(phase)
        if running:
            text, col = t("Your game is running") + (f"  ·  {state}" if state else ""), C["ok"]
        elif ev:
            text, col = t("Starting the game..."), C["warn"]
        else:
            text, col = t("Waiting for the game..."), C["warn"]
        self.m_state.configure(text=text)
        self.m_dot.delete("all")
        d = self.px(10)
        self.m_dot.create_oval(1, 1, d - 1, d - 1, fill=col, outline="")
        guest = opp.get("guest")
        self.m_badge.set(None if guest else _tier_of(opp), bool(opp.get("provisional")) and not guest)
        self.m_name.configure(text=t("vs {name}", name=opp["name"]) if opp.get("name") else t("vs your opponent"))
        if guest:
            self.m_rank.configure(text=t("Guest"))
        elif opp:
            self.m_rank.configure(text=t("{rank}  ·  rating {rating}", rank=ranks.label(opp),
                                         rating=opp.get("rating", "?")))
        else:
            self.m_rank.configure(text="")
        rtt = ev.get("rtt_ms")
        self.m_bars.set(rtt)
        self.m_ping.configure(text=f"{rtt:.0f} ms" if rtt is not None else "?",
                              foreground=theme.ping_color(rtt))
        delay = ev.get("delay")
        self.m_delay.configure(text=(t("{count} frame  ({ms} ms)", count=delay, ms=f"{delay * 16.7:.0f}")
                                     if delay == 1 else t("{count} frames  ({ms} ms)", count=delay,
                                                          ms=f"{delay * 16.7:.0f}"))
                               if isinstance(delay, int) else "?")
        self.m_path.configure(text={"direct": t("Direct"), "lan": t("Local network"),
                                    "relay": t("Relay (lobby server)")}.get(ev.get("path"), ev.get("path") or "?"))

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
               tab.rematch_bar, lag, id(self.result_info), str(tab.bar_text.get()) if kind == "question" else None,
               tab.set_var.get())
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
        sub = t("Guest") if guest else t("{rank}  ·  rating {rating}", rank=ranks.label(opp),
                                          rating=opp.get("rating", "?"))
        ttk.Label(parent, text=sub, style="Card.Muted.TLabel").grid(row=row + 1, column=1, sticky="nw")

    def set_text(self, ev=None):
        """The ranked set on a card: tab.set_var when the set code fills it ("Set 1-0, game 2 of 3"),
        else "SET, GAME n" from the server's set info from the second game on."""
        own = self.tab.set_var.get().strip()
        if own:
            return own.upper()
        st = (ev or {}).get("set") or {}
        if st.get("ranked") and int(st.get("game") or 0) > 1:
            return t("SET · GAME {game}", game=st["game"])
        return ""

    def _head(self, parent, caps, ranked, extra=None, ev=None):
        px = self.px
        head = self.body(parent)
        ttk.Label(head, text=caps, style="Card.Caps.TLabel").pack(side="left")
        ttk.Label(head, text=t("RANKED") if ranked else t("CASUAL"),
                  style="Card.PillAccent.TLabel" if ranked else "Card.Pill.TLabel").pack(side="left", padx=(px(8), 0))
        if extra:
            ttk.Label(head, text=extra, style="Card.Pill.TLabel").pack(side="left", padx=(px(6), 0))
        st = self.set_text(ev)
        if st:
            ttk.Label(head, text=st, style="Card.PillGold.TLabel").pack(side="left", padx=(px(6), 0))
        return head

    def _visual_ready(self, v):
        tab, px = self.tab, self.px
        m = tab.match or {}
        v.columnconfigure(0, weight=1)
        left = self.body(v)
        left.grid(row=0, column=0, sticky="nw")
        left.columnconfigure(1, weight=1)
        self._head(left, t("Opponent found").upper(), m.get("ranked"),
                   t("rematch").upper() if m.get("origin") == "rematch" else None, m).grid(
            row=0, column=0, columnspan=2, sticky="w")
        opp = self.revealed or (None if m.get("blind") else m.get("opponent"))
        if opp:
            self._opponent_row(left, opp, 1)
        else:
            ttk.Label(left, text=t("Opponent hidden"), style="Card.H2.TLabel").grid(row=1, column=0, columnspan=2,
                                                                                  sticky="w", pady=(px(8), 0))
            ttk.Label(left, text=t("Name and side are shown once you both accept."),
                      style="Card.Muted.TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
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
            ttk.Label(prow, text="  " + t("(estimate through the server)"), style="Card.Faint.TLabel").pack(
                side="left")
        if tab.ready_sent:
            ttk.Label(left, text=t("Accepted. Waiting for your opponent..."), style="Card.Accent.TLabel").grid(
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
        self._head(left, t("Match ready").upper(), m.get("ranked"),
                   t("rematch").upper() if m.get("origin") == "rematch" else None, m).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, px(8)))
        opp = self.revealed or m.get("opponent")
        if opp:
            self._opponent_row(left, opp, 1)
        row = self.body(left)
        row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(px(12), 0))
        self.bar_spinner = theme.Spinner(row, size=22, width=3)
        self.bar_spinner.pack(side="left", padx=(0, px(10)))
        ttk.Label(row, text=t("Connecting the two games..."), style="Card.Bold.TLabel").pack(side="left")

    def _visual_challenge(self, v):
        px = self.px
        ch = self.challenger or {}
        left = self.body(v)
        left.grid(row=0, column=0, sticky="nw")
        ttk.Label(left, text=t("Challenge").upper(), style="Card.Caps.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, px(8)))
        if ch:
            self._opponent_row(left, ch, 1)
        ttk.Label(left, text=t("wants to play you. Accept to start the match."), style="Card.TLabel").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(px(10), 0))

    # --- the result
    def _outcome(self):
        info = self.result_info or {}
        ev = info.get("ev") or {}
        st = ev.get("status")
        counted = st in ("confirmed", "onesided", "forfeit", "resolved")
        mine = info.get("mine")
        if counted and mine is True:
            return "win", t("YOU WIN"), "Win."
        if counted and mine is False:
            return "loss", t("YOU LOSE"), "Loss."
        if counted and ev.get("winner") is None:
            return "draw", t("DRAW"), "Even."
        if counted:
            return "over", t("MATCH OVER"), "Even."
        return "void", t("NO CONTEST"), "Even."

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
        if info.get("opp"):
            sub = (t("Ranked match vs {name}", name=info["opp"]) if info.get("ranked")
                   else t("Casual match vs {name}", name=info["opp"]))
        else:
            sub = t("Ranked match") if info.get("ranked") else t("Casual match")
        set_text = self.set_text(ev)
        if set_text:
            sub += "  \u00b7  " + set_text[:1].upper() + set_text[1:]
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
            ttk.Label(sc, text=t("ROUNDS  (YOU – THEM)") if slot is not None else t("ROUNDS  (P1 – P2)"),
                      style=pre + "Caps.TLabel").pack(anchor="e")
        row = 1
        r = ev.get("rating")
        if r:
            rr = self.body(v)
            rr.grid(row=row, column=0, sticky="w", pady=(px(10), 0))
            row += 1
            after = r.get("after") or {}
            ttk.Label(rr, text=t("Rating {rating}", rating=f"{after.get('r', 0):.0f}"),
                      style="Card.Num.TLabel").pack(side="left")
            d = r.get("delta") or 0
            ttk.Label(rr, text=f"  {d:+.0f}", style="Card.Num.TLabel",
                      foreground=C["ok"] if d > 0 else C["bad"] if d < 0 else C["muted"]).pack(side="left")
            rank_after = r.get("rank_after") or {}
            evn = r.get("event")
            pill = {"promoted": (t("PROMOTED"), "Card.PillGold.TLabel"),
                    "demoted": (t("DEMOTED"), "Card.PillBad.TLabel"),
                    "placed": (t("PLACED"), "Card.PillAccent.TLabel")}.get(evn)
            if pill:
                ttk.Label(rr, text=pill[0], style=pill[1]).pack(side="left", padx=(px(16), px(8)))
                bd = theme.Badge(rr, size=26)
                bd.set(_tier_of(rank_after), rank_after.get("provisional"))
                bd.pack(side="left", padx=(0, px(6)))
                ttk.Label(rr, text=rank_after.get("rank", ""), style="Card.Bold.TLabel").pack(side="left")
            elif rank_after.get("placement"):
                n, k = rank_after["placement"]
                ttk.Label(rr, text="   " + t("Placement match {done} of {total}", done=n, total=k),
                          style="Card.Muted.TLabel").pack(side="left")
        lag = tab.lag
        if lag and lag.get("text"):
            bad = lag.get("verdict") == "more_lag"
            lr = self.body(v)
            lr.grid(row=row, column=0, sticky="we", pady=(px(8), 0))
            lr.columnconfigure(1, weight=1)
            ttk.Label(lr, text=t("Lag check").upper(),
                      style="Card.PillWarn.TLabel" if bad else "Card.Pill.TLabel").grid(
                row=0, column=0, sticky="nw", padx=(0, px(8)))
            self.wrap(ttk.Label(lr, text=describe_lag(lag), style="Card.warn.TLabel" if bad else "Card.Small.TLabel",
                                justify="left"), self.stage_card, 150).grid(row=0, column=1, sticky="w")

    def _render_result_card(self):
        tab, px = self.tab, self.px
        sig = (id(self.result_info), (tab.lag or {}).get("text"), tab.client is not None, tab.set_var.get(),
               self.rematch_pending)
        if sig == self._res_sig:
            return
        self._res_sig = sig
        for w in self.res_visual.winfo_children():
            w.destroy()
        for w in self.res_buttons.winfo_children():
            w.destroy()
        self._visual_result(self.res_visual)
        info = self.result_info or {}
        self.res_spinner = None
        if self.rematch_pending:
            row = self.body(self.res_visual)
            row.grid(row=9, column=0, sticky="w", pady=(px(10), 0))
            self.res_spinner = theme.Spinner(row, size=20, width=3)
            self.res_spinner.pack(side="left", padx=(0, px(8)))
            ttk.Label(row, text=t("Rematch offered. Waiting for {opp}...", opp=info.get("opp") or t("your opponent")),
                      style="Card.Accent.TLabel").pack(side="left")
        ttk.Button(self.res_buttons, text=t("Next game"), style="Card.Accent.TButton",
                   command=self._next_game).pack(side="left")
        ttk.Button(self.res_buttons, text=t("Back to the lobby"), style="Card.TButton",
                   command=self.dismiss_result).pack(side="left", padx=(px(8), 0))
        opp = info.get("opp")
        if opp and tab.client is not None:
            ttk.Button(self.res_buttons, text=t("Block {name}", name=opp), style="Card.Danger.TButton",
                       command=lambda: tab.block_opponent(opp)).pack(side="left", padx=(px(8), 0))
        if hasattr(tab.app, "report_problem"):
            ttk.Button(self.res_buttons, text=t("Report a problem..."), style="Card.Link.TButton",
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
        if self._stage == "result" and getattr(self, "res_spinner", None) is not None:
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
            if self._stage == "result" and getattr(self, "res_spinner", None) is not None and shown:
                self.res_spinner.step(dt)
        except tk.TclError:
            return
        if self._anim_needed():
            try:
                self._anim_id = self.box.after(33 if shown else 250, self._anim)
            except tk.TclError:
                self._anim_id = None

    def close(self):
        for attr in ("_anim_id", "_wrap_after"):
            aid = getattr(self, attr)
            if aid is not None:
                try:
                    self.box.after_cancel(aid)
                except (tk.TclError, ValueError):
                    pass
                setattr(self, attr, None)

    # ------------------------------------------------------------------ windows
    def codes_window(self, codes, first, save):
        """The recovery codes, once: big, numbered, with 'Save to a file...' and 'I have saved them'."""
        px = self.px
        w = self.tab.new_window(self.tab.parent)
        w.title(t("Recovery codes"))
        w.configure(bg=C["bg"])
        card = self.card(w, pad=20)
        card.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=t("Your account is ready") if first else t("New recovery codes"),
                  style="Card.H2.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, wraplength=px(440), justify="left", style="Card.Muted.TLabel", text=t(
            "These codes are the only way back into your account if you forget the password (there is no "
            "e-mail). Each code works once. Write them down or save them somewhere safe -- they are not shown "
            "again.")).grid(row=1, column=0, sticky="w", pady=(px(6), px(12)))
        grid = self.body(card)
        grid.grid(row=2, column=0, sticky="w")
        for i, code in enumerate(codes):
            tile = self.card(grid, "Tile.TFrame", 8)
            tile.grid(row=i // 2, column=i % 2, sticky="we", padx=(0, px(8)), pady=(0, px(8)))
            ttk.Label(tile, text=f"{i + 1:>2}", style="Tile.Faint.TLabel").pack(side="left", padx=(0, px(10)))
            ttk.Label(tile, text=code, style="Tile.TLabel", font=self.th.fonts["code"]).pack(side="left")
        bar = self.body(card)
        bar.grid(row=3, column=0, sticky="we", pady=(px(8), 0))
        ttk.Button(bar, text=t("Save to a file..."), style="Card.TButton", command=lambda: save(w)).pack(
            side="left")
        done = ttk.Button(bar, text=t("I have saved them"), style="Card.Accent.TButton", command=w.destroy)
        done.pack(side="right")
        try:
            done.focus_set()
        except tk.TclError:
            pass
        return w
