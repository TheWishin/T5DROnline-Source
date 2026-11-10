"""The profile card's picture (docs/ONLINE.md "Profile picture"): this player's customized fighter, on this PC only.

Nothing of a picture leaves the PC: it is not sent to the lobby server, the server keeps none, and no other
player sees it. The card shows one on this player's OWN profile only -- of the fighter the account plays most when
the launcher has that one, else of the fighter picked in the lobby.

Taking it: `upkeep()` runs when the tab is idle (logged in with an account, nothing searched or played). It asks
the launcher (`app.profile_picture`, launcher/t5dr_launcher.pyw -> launcher/profile_pic.py) for the pictures of the
fighter picked in the lobby and keeps them in memory for the card. The launcher answers from its cache
(`<out>/profile-pics`); only a changed customization starts its short hidden game. Without that hook (the lobby's
own CLI, tests) or with the setting off: nothing is taken and nothing is shown.
"""
import base64
import hashlib
import time
import tkinter as tk
from tkinter import ttk

from . import fighters, picfmt
from .i18n import t

CARD_SIZE = (150, 200)       # the picture on the card at 100 % (a click shows all 240 x 320 pixels)
UPKEEP_SECONDS = 45.0        # between two looks at this player's own picture
RETRY_SECONDS = 600.0        # after a failed attempt for a fighter


def choose(local, main=None, picked=None):
    """The picture to show from `local` {fighter: [(costume, png), ...]}: the most played fighter's, else the
    picked fighter's, else any -> (fighter, costume, png) or None."""
    for key in (main, picked, *local):
        rows = local.get(key) if key else None
        if rows:
            return key, rows[0][0], rows[0][1]
    return None


def _shrink(png, size):
    """Worker: the picture shrunk to the card's `size` (or None: not a picture)."""
    try:
        png = picfmt.clean(png)
        w, h, rgb = picfmt.decode(png)
        return png if (w, h) == tuple(size) else picfmt.encode(*picfmt.portrait(w, h, rgb, size[0], size[1]))
    except Exception:      # noqa: BLE001
        return None


def _upkeep(take, fighter, fighter_id, opponent_id):
    """Worker: this player's pictures of `fighter` -> ("ok" | "none" | "busy" | "failed", text, pictures)."""
    try:
        r = take(fighter, fighter_id, opponent_id)
        if r is None:
            return "busy", "", None
        if r.get("state") == "none":
            return "none", "", []
        if r.get("state") != "ok":
            # ended because the player started a game: no failure, the next quiet moment tries again
            return ("busy" if r.get("error") == "stopped" else "failed"), str(r.get("error") or ""), None
        return "ok", str(r.get("ran", 0)), [(int(c), bytes(png)) for c, png in r.get("pics") or ()]
    except Exception as e:      # noqa: BLE001 -- the profile picture must never disturb the lobby
        return "failed", f"{type(e).__name__}: {e}", None


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
        self.local = {}              # fighter -> [(costume, png), ...]: this PC's pictures (never sent anywhere)
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
        """A profile was just put on the card: this player's own gets this PC's picture, any other none."""
        pick = None
        if profile.get("self") and self.enabled():
            pick = choose(self.local, profile.get("main"), self.tab._char_key())
        if pick is None:
            self.clear()
            return
        fighter, costume, png = pick
        sha = hashlib.sha256(png).hexdigest()
        if sha == self.shown_sha and self._want == (profile.get("name"), sha):
            return
        self.clear()
        self._want = (profile.get("name"), sha)
        self.tab.call(_shrink, png, self.card_size(),
                      then=lambda small, want=self._want: self._got(want, {"fighter": fighter, "costume": costume},
                                                                    png if small else None, small))

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
        if self._running or now < self._next or client is None or not getattr(client, "connected", False):
            return False
        me = client.me or {}
        if me.get("guest", True) or me.get("status") != "idle" or tab.match is not None:
            return False
        take = getattr(tab.app, "profile_picture", None)
        if take is None:
            return False
        self._next = now + UPKEEP_SECONDS
        if not self.enabled():
            if self.local or self.image is not None:
                self.local = {}              # switched off: nothing is taken, nothing is shown
                self.clear()
            return False
        key = tab._char_key()
        f = tab.table.fighter(key) if key != fighters.RANDOM else None
        if f is None:
            return False
        state, at = self._done.get(key, ("", 0.0))
        if state == "failed" and now - at < RETRY_SECONDS:
            return False
        opp = next((x for x in tab.table.fighters if x["key"] == ("law" if key == "paul" else "paul")), None)
        self._running = True
        tab.call(_upkeep, take, key, f["id"], (opp or {"id": 0})["id"],
                 then=lambda r, key=key: self._upkeep_done(key, r))
        return True

    def _upkeep_done(self, key, result):
        self._running = False
        state, text, pics = result
        self.last = (state, text)
        self._done[key] = (state, time.monotonic())
        changed = False
        if pics is not None:
            changed = self.local.get(key, []) != pics
            if pics:
                self.local[key] = pics
            else:
                self.local.pop(key, None)
        if state == "failed" or (state == "ok" and text not in ("", "0")):
            log = getattr(self.tab, "launcher_log", None)
            if log is not None:
                log(f"profile picture ({key}): {state} {text}".rstrip())
        if changed and self.tab.profile_name and self.tab.client is not None                 and (self.tab.client.me or {}).get("name") == self.tab.profile_name:
            self.shown_sha = None            # this player's own card is open: show the new picture
            self.tab.show_profile(self.tab.profile_name)
