"""Online tab -- placeholder until netplay lands.

This is the one place the netplay work plugs into the launcher. The contract:

* `OnlineTab(parent, app)` builds the tab's widgets inside `parent` (a ttk.Frame).
  `app` is the launcher (t5dr_launcher.App); what the online code may use:
    - app.settings            Settings (dict); app.settings["nickname"] is the player's name
    - app.game_state()        dict(ok=..., text=...) -- only start a match when ok is True
    - app.start_game(env)     starts t5dr.exe with the normal settings plus `env`
                              (e.g. {"T5DR_NET_PEER": "1.2.3.4:7000", "T5DR_NET_SIDE": "1"});
                              returns the GameRun (core.GameRun) or None if it could not start
    - app.game                the running GameRun or None (.running(), .stop(), .fps, .log_path)
    - app.set_status(text)    one line in the launcher's status bar
* `OnlineTab.on_show()` is called whenever the tab is selected,
  `OnlineTab.on_close()` when the launcher exits (close sockets, leave the lobby).

The game-side switches (environment variables read by the runtime's netplay
code) are up to the netplay design; the launcher only passes them through.
"""
import tkinter as tk
from tkinter import ttk

AVAILABLE = False   # set True by the real implementation


class OnlineTab:
    def __init__(self, parent, app):
        self.app = app
        box = ttk.Frame(parent, padding=24)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Online play", style="H1.TLabel").pack(anchor="w")
        ttk.Label(box, wraplength=640, justify="left", text=(
            "Online play between friends is being built: the two PCs exchange controller input every "
            "frame (delay-based first, then rollback), with a lobby on top -- the same model as "
            "Tekken 6 Native Online. Sony's servers for the game's own online mode are gone, so it "
            "cannot be used.")).pack(anchor="w", pady=(6, 16))

        form = ttk.LabelFrame(box, text="Lobby", padding=12)
        form.pack(fill="x")
        ttk.Label(form, text="Name").grid(row=0, column=0, sticky="w")
        self.name = tk.StringVar(value=app.settings.get("nickname") or "")
        ttk.Entry(form, textvariable=self.name, width=24, state="disabled").grid(row=0, column=1, sticky="w", padx=8)
        for i, label in enumerate(("Log in", "Play as guest", "Find opponent", "Direct connect (IP)")):
            ttk.Button(form, text=label, state="disabled").grid(row=1, column=i, padx=(0, 8), pady=(10, 0), sticky="w")
        cols = ("player", "status", "ping")
        tv = ttk.Treeview(form, columns=cols, show="headings", height=5)
        for c, w in zip(cols, (240, 160, 80)):
            tv.heading(c, text=c.capitalize())
            tv.column(c, width=w, anchor="w")
        tv.grid(row=2, column=0, columnspan=4, sticky="we", pady=(12, 0))
        tv.insert("", "end", values=("(the lobby will list players here)", "", ""))
        ttk.Label(box, style="Muted.TLabel", text="Coming in a later version. Offline versus and "
                  "arcade work now from the Play tab.").pack(anchor="w", pady=(12, 0))

    def on_show(self):
        pass

    def on_close(self):
        pass
