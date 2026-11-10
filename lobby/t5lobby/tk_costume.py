"""The ranked costume in the Online tab (1.2.3, owner 2026-11-10; docs/RANKED.md "Costumes in ranked").

Ranked: the player chooses fighter AND costume here, and every game of a ranked set starts with them (no select screen;
the server's `buttons` on the fight line, the costume = the button that confirms the fighter, fighters.costume_buttons).
The customization of that costume comes from the player's offline save as before (docs/DIRECTFIGHT.md "Custom costumes
online"). Casual matches keep the game's own select screen (the confirm button is the costume there).

Where: the character select grid (tk_charsel.py) has a "Costume (ranked)" row under the fighters with the current
fighter's costumes; the fighter button shows the costume's number ("Jin · 3"). No space of its own in the play card.

Remembered per fighter in online.json `costumes` {fighter key: button}; a pick on the game's select screen (casual)
is remembered the same way (remember_pick), so choosing that fighter for ranked later starts on that costume. A fighter
nobody chose a costume for starts on costume 1. Random has no costume choice (the game's default for whoever is drawn).
On a server that takes no costume (an older lobby: ranked game 1 is picked in the game there) the row is greyed.
"""
import tkinter as tk
from tkinter import ttk

from . import fighters
from .i18n import t


def label(n, button):
    """'Costume 2 (LK)': the costume's number (the game's model order) and the button that confirms it."""
    return t("Costume {n} ({button})", n=n, button=fighters.BUTTON_NAMES.get(button, "?"))


def labels(key):
    return [label(i + 1, b) for i, b in enumerate(fighters.costume_buttons(key))]


def remembered(cfg, key):
    """The costume (confirm button) remembered for fighter `key`, its costume 1 when there is none; 0 for Random."""
    saved = (cfg or {}).get("costumes")
    b = saved.get(key) if isinstance(saved, dict) else None
    return fighters.costume_button(key, b if isinstance(b, int) and not isinstance(b, bool) else 0)


def number(key, button):
    """The costume's number (1-4) for fighter `key`, 0 when it is none of its costumes."""
    buttons = fighters.costume_buttons(key)
    return buttons.index(button) + 1 if button in buttons else 0


def remember(cfg, key, button):
    """Keep `button` as fighter `key`'s costume in cfg (online.json); False when nothing changed or it is none of
    its costumes."""
    buttons = fighters.costume_buttons(key)
    if not buttons or button not in buttons:
        return False
    saved = cfg.get("costumes")
    if not isinstance(saved, dict):
        saved = cfg["costumes"] = {}
    if saved.get(key) == button:
        return False
    saved[key] = button
    return True


def suffix(tab):
    """' · 3' for the fighter button: the current fighter's remembered costume (nothing for one costume / Random)."""
    char_key = getattr(tab, "_char_key", None)
    if not callable(char_key):
        return ""                          # (a stand-in tab in tests)
    key = char_key()
    if len(fighters.costume_buttons(key)) < 2:
        return ""
    return f" · {number(key, remembered(getattr(tab, 'cfg', None), key))}"


def client_takes_it(c):
    """Does this client send a costume (LobbyClient.costume_ok: its game and the server take one)?"""
    ok = getattr(c, "costume_ok", None)
    return callable(ok) and ok() is True


def server_takes_it(tab):
    """None before a login (the choice is kept for later), else whether the server and this game take a costume."""
    c = getattr(tab, "client", None)
    if c is None or not getattr(c, "me", None):
        return None
    return client_takes_it(c)


def build_row(sel, parent):
    """The grid's 'COSTUME (RANKED)' row: one button per costume of the current fighter, the remembered one lit.
    -> the frame, or None for a fighter with nothing to choose."""
    tab, px = sel.tab, sel.px
    key = tab._char_key()
    buttons = fighters.costume_buttons(key)
    sel.costume_buttons = []
    if len(buttons) < 2:
        return None
    row = sel.view.body(parent)
    ttk.Label(row, text=t("Costume (ranked)").upper(), style="Card.Caps.TLabel").pack(side="left", padx=(0, px(10)))
    current = remembered(tab.cfg, key)
    off = server_takes_it(tab) is False
    for i, b in enumerate(buttons):
        w = ttk.Button(row, text=label(i + 1, b), style="Card.Accent.TButton" if b == current
                       else "Card.TButton", command=lambda x=b: pick(sel, x),
                       state="disabled" if off else "normal")
        w.pack(side="left", padx=(0, px(6)))
        w.bind("<Escape>", sel._escape)
        sel.costume_buttons.append((b, w))
    if off:
        ttk.Label(row, text=t("This server picks ranked costumes in the game."), style="Card.Faint.TLabel").pack(
            side="left", padx=(px(6), 0))
    return row


def pick(sel, button):
    """A costume button in the grid: remembered for the current fighter, sent with it when logged in, grid closed."""
    tab = sel.tab
    key = tab._char_key()
    if remember(tab.cfg, key, button):
        tab._save_cfg()
    c = getattr(tab, "client", None)
    if c is not None and getattr(c, "me", None) and client_takes_it(c):
        tab.call(c.set_char, key, remembered(tab.cfg, key))
    sel._label()
    sel.close()


def sync(tab):
    """The fighter button's text again (its costume number) after a login, a lock or a remembered pick."""
    sel = getattr(tab, "charsel", None)
    if sel is not None:
        sel._label()


def remember_pick(tab, own_pick):
    """A pick on the game's select screen (casual): its button becomes that fighter's remembered costume."""
    if not own_pick or len(own_pick) != 2:
        return
    key, button = own_pick
    if remember(tab.cfg, key, button):
        tab._save_cfg()
        sync(tab)
