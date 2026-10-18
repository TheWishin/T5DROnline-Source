"""Online tab: the lobby (lobby/t5lobby/tk_tab.py) plugged into the launcher.

The contract the launcher offers the online code:

* `OnlineTab(parent, app)` builds the tab's widgets inside `parent` (a ttk.Frame).
  `app` is the launcher (t5dr_launcher.App); what the online code uses:
    - app.settings            Settings (dict); app.settings["nickname"] is the player's name,
                              app.settings.out_dir the build output (game, logs)
    - app.game_state()        dict(ok=..., text=...) -- only go online when ok is True
    - app.start_game(env)     starts t5dr.exe with the normal settings plus `env` (T5_NET_*,
                              T5_FIGHT, T5_HUD_*, or T5_CTL_DIR); returns the GameRun
                              (core.GameRun) or None if it could not start
    - app.game                the running GameRun or None (.running(), .stop(), .fps, .log_path)
    - app.set_status(text)    one line in the launcher's status bar
* `OnlineTab.on_show()` is called whenever the tab is selected (logs in with a saved login
  the first time, starts reading the controller), `OnlineTab.on_close()` when the launcher exits
  (closes the game it started, leaves the lobby, stops the controller thread).

The controller needs nothing from the launcher but the settings above: the tab finds the top-level
window of its parent to know when the launcher is in front, reads app.settings.out_dir and
app.settings.env_overrides() to find the game's controls.ini, and keeps its on/off switch in
online.json. A pad press counts only while the launcher's window is the foreground window (lobby/t5lobby/
padnav.py, docs/ONLINE.md "Controller in the launcher").

Accounts, ranked play, the match flow and its rules: docs/ONLINE.md and docs/RANKED.md.
"""
import os
import sys

_LOBBY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lobby")
if _LOBBY not in sys.path:
    sys.path.insert(0, _LOBBY)

try:
    from t5lobby.tk_tab import AVAILABLE, OnlineTab  # noqa: E402,F401
except ImportError as _e:      # lobby/ missing from this copy: keep the launcher usable
    import tkinter as tk  # noqa: F401
    from tkinter import ttk

    from core import t  # noqa: E402  (the launcher's own lookup; English only without lobby/)

    AVAILABLE = False
    _why = str(_e)

    class OnlineTab:
        def __init__(self, parent, app):
            box = ttk.Frame(parent, padding=24)
            box.pack(fill="both", expand=True)
            ttk.Label(box, text=t("Online play"), style="H1.TLabel").pack(anchor="w")
            ttk.Label(box, wraplength=640, justify="left", text=t(
                "The lobby files (lobby/t5lobby) are missing from this copy of the launcher, so online play "
                "is not available.\n\n({reason})", reason=_why)).pack(anchor="w", pady=(6, 16))

        def on_show(self):
            pass

        def on_close(self):
            pass
