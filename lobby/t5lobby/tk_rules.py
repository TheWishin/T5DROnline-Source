"""The Online tab's part of training rooms and the health handicap (docs/ONLINE.md "Training rooms and the health
handicap"; the server's side: server/matchrules.py, the games': src/netplay/match_rules.h).

* The health picker ("My health (casual)"), next to Quick match: this player's health in casual matches -- quick
  matches, challenges, invites, rooms -- in percent, 150 down to 30 (1.1.7; up to 100 when the game or the server
  is older); remembered in online.json ("life") and sent to the server after every login (set_life). Ranked and
  tournament matches are always 100 %.
* What a match's rules say, for the ready check and the match card: a training room's match (endless health, hold
  SELECT to pick again, nothing counted) and both players' health when either is not 100 %.

Kept apart from tk_tab.py (several features change that file); the tab calls these few functions."""
import tkinter as tk
from tkinter import ttk

from .i18n import t

LIFE_VALUES = tuple(range(150, 29, -10))      # what the picker may offer (the server takes 30-150 in steps of 10)
LIFE_MAX_OLD = 100                            # the most an older game or server plays (1.1.5, 1.1.6)


def picker_values(top):
    """The picker's choices when this player may pick up to `top` percent (150 or 100)."""
    return [life_label(v) for v in LIFE_VALUES if v <= top]


def picker_top(tab):
    """The most this player may pick now: the server's word once logged in, else what this PC's game can play."""
    c = getattr(tab, "client", None)
    if c is not None and getattr(c, "me", None):
        return c.life_max()
    has = getattr(tab, "_game_has_life150", None)
    try:
        return LIFE_VALUES[0] if has is not None and has() else LIFE_MAX_OLD
    except Exception:  # noqa: BLE001 -- (an unreadable game build: the older range)
        return LIFE_MAX_OLD


def life_label(v):
    return t("{percent} %", percent=int(v))


def parse_life(label):
    """The picker's text -> percent (100 for anything unexpected)."""
    for v in LIFE_VALUES:
        if life_label(v) == label:
            return v
    return 100


def clean_life(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 100
    return v if v in LIFE_VALUES else 100


def rules_parts(ev, slot=None):
    """Texts for a match's rules: from match_found (`training`, `life` {you, opponent}) or, with this player's
    `slot`, from match_start (`fight.training`, `fight.life` [P1, P2]). [] when there are none."""
    if not isinstance(ev, dict):
        return []
    parts = []
    fight = ev.get("fight") if isinstance(ev.get("fight"), dict) else {}
    if ev.get("training") or fight.get("training"):
        parts.append(t("TRAINING: endless health, nothing counted; hold SELECT for 1 s to pick again"))
    you = opp = None
    life = ev.get("life")
    if isinstance(life, dict):
        you, opp = life.get("you"), life.get("opponent")
    elif isinstance(fight.get("life"), list) and len(fight["life"]) == 2 and slot in (0, 1):
        you, opp = fight["life"][slot], fight["life"][1 - slot]
    if isinstance(you, int) and isinstance(opp, int) and (you, opp) != (100, 100):
        parts.append(t("health: you {you} %, opponent {opponent} %", you=you, opponent=opp))
    return parts


def build_life_picker(view, parent, tab):
    """'My health (casual) [100 %]' in the Play card (tab.life_var, tab.on_life); returns its frame."""
    f = view.body(parent)
    ttk.Label(f, text=t("My health (casual)"), style="Card.Muted.TLabel").pack(side="left", padx=(0, view.px(6)))
    cb = ttk.Combobox(f, textvariable=tab.life_var, values=picker_values(picker_top(tab)), state="readonly",
                      width=7, style="Card.TCombobox")
    cb.pack(side="left")
    cb.bind("<<ComboboxSelected>>", lambda _e: tab.on_life())
    tab.life_cb = cb
    return f


def sync_picker(tab):
    """The picker is off while logged in to a server (or with a game) that has no health handicap; it offers
    more than 100 % only when this game and the server can play it (a higher choice then shows as 100 %)."""
    cb = getattr(tab, "life_cb", None)
    c = getattr(tab, "client", None)
    if cb is None:
        return
    off = c is not None and getattr(c, "me", None) and not c.handicap_ok()
    top = picker_top(tab)
    var = getattr(tab, "life_var", None)
    try:
        cb.configure(state="disabled" if off else "readonly", values=picker_values(top))
        if var is not None and parse_life(var.get()) > top:
            var.set(life_label(top))
    except tk.TclError:
        pass


def life_var(cfg):
    return tk.StringVar(value=life_label(clean_life((cfg or {}).get("life", 100))))
