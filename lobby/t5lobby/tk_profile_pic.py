"""The profile card's picture (docs/ONLINE.md "Profile picture"): a player's customized fighter.

Showing: a profile from a server that keeps pictures lists them (`pics`); the card shows one -- of the fighter the
account plays most if there is one, else the newest -- fetched over the lobby connection (client.pic_get, which
checks the file and writes it anew) and never kept on disk.

Taking and sending this player's own: `upkeep()` runs when the tab is idle (logged in with an account, nothing
searched or played). It asks the launcher (`app.profile_picture`, launcher/t5dr_launcher.pyw ->
launcher/profile_pic.py) for the pictures of the fighter picked in the lobby and sends the ones the server does
not have yet. The launcher answers from its cache; only a changed customization starts its short hidden game.
Without that hook (the lobby's own CLI, tests), with the setting off, or on a server without the feature: nothing.
"""
import base64
import hashlib
import time
import tkinter as tk
from tkinter import ttk

from . import fighters, picfmt
from .i18n import t
from .proto import LobbyError

CARD_SIZE = (150, 200)       # the picture on the card at 100 % (a click shows all 240 x 320 pixels)
UPKEEP_SECONDS = 45.0        # between two looks at this player's own picture
RETRY_SECONDS = 600.0        # after a failed attempt for a fighter


def choose(profile):
    """The picture of a profile to show: the most played fighter's, else the newest -> its `pics` row or None."""
    pics = [p for p in profile.get("pics") or () if isinstance(p, dict) and p.get("fighter") and p.get("sha")]
    if not pics:
        return None
    main = profile.get("main")
    for p in pics:
        if main and p["fighter"] == main:
            return p
    return pics[0]


def _fetch(client, name, row, size):
    """Worker: (row, the picture's bytes, the same picture shrunk to the card's `size`), or (row, None, None) (no
    error text: a missing picture is not a problem to report)."""
    try:
        png = client.pic_get(name, row["fighter"], row["costume"], row.get("sha"))
        w, h, rgb = picfmt.decode(png)
        small = png if (w, h) == tuple(size) else picfmt.encode(*picfmt.portrait(w, h, rgb, size[0], size[1]))
        return row, png, small
    except Exception:      # noqa: BLE001
        return row, None, None


def _upkeep(client, take, fighter, fighter_id, opponent_id, enabled):
    """Worker: this player's pictures of `fighter` -> ("sent" | "same" | "none" | "off" | "busy" | "failed", text)."""
    try:
        if not enabled:
            n = client.pic_del()
            return "off", f"{n} removed"
        r = take(fighter, fighter_id, opponent_id)
        if r is None:
            return "busy", ""
        if r.get("state") == "none":
            client.pic_del(fighter)
            return "none", ""
        if r.get("state") != "ok":
            # ended because the player started a game: no failure, the next quiet moment tries again
            return ("busy" if r.get("error") == "stopped" else "failed"), str(r.get("error") or "")
        sent = 0
        for costume, png in r.get("pics") or ():
            if not client.pic_put(fighter, costume, png).get("same"):
                sent += 1
        return ("sent" if sent else "same"), str(r.get("ran", 0))
    except LobbyError as e:
        return "failed", f"{e.code}: {e.msg}"
    except Exception as e:      # noqa: BLE001 -- the profile picture must never disturb the lobby
        return "failed", f"{type(e).__name__}: {e}"


def _pics_ok(client):
    """This client and its server both do profile pictures (a client object without the calls: no)."""
    ok = getattr(client, "pics_ok", None)
    try:
        return bool(ok is not None and ok())
    except Exception:      # noqa: BLE001
        return False


class ProfilePicture:
    def __init__(self, view, card):
        self.view, self.tab = view, view.tab
        self.frame = view.body(card)
        # the card's right edge, over all its rows: small enough (CARD_SIZE) for the card at the smallest window
        self.frame.grid(row=0, column=2, rowspan=5, sticky="ne", padx=(view.px(12), 0))
        self.label = ttk.Label(self.frame, style="Card.TLabel", cursor="hand2")
        self.label.pack(anchor="e")
        self.label.bind("<Button-1>", lambda _e: self.show_full())
        self.caption = ttk.Label(self.frame, text="", style="Card.Muted.TLabel", justify="right")
        self.caption.pack(anchor="e")
        self.frame.grid_remove()
        self.image = None            # the PhotoImage shown (a reference must stay)
        self.full = None             # the whole picture's bytes (for the click)
        self.full_image = None
        self.shown_sha = None
        self._want = None            # (profile name, sha) asked for
        self._next = 0.0             # upkeep: not before this
        self._running = False
        self._done = {}              # fighter -> (state, monotonic time) of this session's last attempt
        self._off_sent = False
        self.last = None             # (state, text) of the last upkeep, for the log and tests

    # ------------------------------------------------------------------ showing
    def clear(self):
        self._want = None
        self.shown_sha = None
        self.image = self.full = None
        try:
            self.label.configure(image="")
            self.caption.configure(text="")
            self.frame.grid_remove()
        except tk.TclError:
            pass

    def shown(self, profile):
        """A profile was just put on the card."""
        client = self.tab.client
        row = choose(profile) if _pics_ok(client) else None
        if row is None:
            self.clear()
            return
        if row["sha"] == self.shown_sha and self._want == (profile.get("name"), row["sha"]):
            return
        self.clear()
        self._want = (profile.get("name"), row["sha"])
        self.tab.call(_fetch, client, profile.get("name"), row, self.card_size(),
                      then=lambda r, want=self._want: self._got(want, *r))

    def card_size(self):
        """The picture's size on the card at this display's scale (never more pixels than it has)."""
        w = max(60, min(picfmt.MAX_W, self.view.px(CARD_SIZE[0])))
        return w, w * picfmt.MAX_H // picfmt.MAX_W

    def _got(self, want, row, png, small):
        if png is None or want != self._want or getattr(self.view, "_closed", False):
            return
        try:
            image = tk.PhotoImage(master=self.label, data=base64.b64encode(small))
            self.label.configure(image=image)
            self.caption.configure(text=t("{fighter}, costume {number}",
                                          fighter=self.tab.table.fighter_name(row["fighter"]), number=row["costume"]))
            self.frame.grid()
        except tk.TclError:
            return
        self.image, self.full = image, png
        self.shown_sha = hashlib.sha256(png).hexdigest()

    def show_full(self):
        """A click on the card's picture: all of it, in a small window of its own."""
        if self.full is None:
            return None
        try:
            win = self.tab.new_window(self.label.winfo_toplevel())
            win.title(self.caption.cget("text"))
            win.resizable(False, False)
            self.full_image = tk.PhotoImage(master=win, data=base64.b64encode(self.full))
            ttk.Label(win, image=self.full_image).pack()
            ttk.Label(win, text=self.caption.cget("text")).pack(pady=(self.view.px(4), self.view.px(6)))
            win.bind("<Escape>", lambda _e: win.destroy())
            win.bind("<Button-1>", lambda _e: win.destroy())
            return win
        except tk.TclError:
            return None

    # ------------------------------------------------------------------ this player's own picture
    def enabled(self):
        app = self.tab.app
        try:
            return bool(app.settings.get("profile_pic", True))
        except AttributeError:
            return True

    def upkeep(self, now=None):
        """Called often (OnlineTab._poll): starts at most one background look every UPKEEP_SECONDS."""
        tab = self.tab
        now = time.monotonic() if now is None else now
        client = tab.client
        if self._running or now < self._next or client is None or not _pics_ok(client):
            return False
        if not getattr(client, "connected", False):
            return False
        me = client.me or {}
        if me.get("guest", True) or me.get("status") != "idle" or tab.match is not None:
            return False
        take = getattr(tab.app, "profile_picture", None)
        if take is None:
            return False
        self._next = now + UPKEEP_SECONDS
        on = self.enabled()
        if not on:
            if self._off_sent:
                return False
            self._off_sent = True            # switched off: this account's pictures leave the server, once
            self._start(client, take, None, 0, 0, False)
            return True
        self._off_sent = False
        key = tab._char_key()
        f = tab.table.fighter(key) if key != fighters.RANDOM else None
        if f is None:
            return False
        state, at = self._done.get(key, ("", 0.0))
        if state == "failed" and now - at < RETRY_SECONDS:
            return False
        opp = next((x for x in tab.table.fighters if x["key"] == ("law" if key == "paul" else "paul")), None)
        self._start(client, take, key, f["id"], (opp or {"id": 0})["id"], True)
        return True

    def _start(self, client, take, key, fid, opp, on):
        self._running = True
        self.tab.call(_upkeep, client, take, key, fid, opp, on, then=lambda r, key=key: self._upkeep_done(key, r))

    def _upkeep_done(self, key, result):
        self._running = False
        self.last = result
        if key:
            self._done[key] = (result[0], time.monotonic())
        if result[0] in ("sent", "failed", "off"):
            log = getattr(self.tab, "launcher_log", None)
            if log is not None:
                log(f"profile picture ({key or 'all'}): {result[0]} {result[1]}".rstrip())
        if result[0] == "sent" and self.tab.profile_name and self.tab.client is not None \
                and (self.tab.client.me or {}).get("name") == self.tab.profile_name:
            self.shown_sha = None            # this player's own card is open: show the new picture
            self.tab.show_profile(self.tab.profile_name)
