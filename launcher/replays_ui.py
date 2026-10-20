"""The launcher's Replays tab (docs/REPLAYS.md): every recorded online match, Watch plays it in the game.

The game writes the files (src/netplay/replay.cpp) into <native folder>/replays while a session runs; this
tab lists one row per match (date, fighters, result, opponent), starts the game in playback mode for the
selected one and shows the game's verdict when it ends: the same as the live match frame for frame (every
recorded state hash and the result), or where it parted.
"""
import os
import time
import tkinter as tk
from tkinter import ttk

import core
import replays
from core import t


class ReplaysTab:
    def __init__(self, parent, app):
        self.app = app
        self.parent = parent
        self.entries = []
        self.watching = None          # (GameRun, result path, Entry) while a replay plays
        self._sort_newest = True
        box = ttk.Frame(parent, padding=(24, 16))
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=t("Replays"), style="H1.TLabel").pack(anchor="w")
        ttk.Label(box, style="Muted.TLabel", wraplength=860, justify="left", text=t(
            "Every online match is saved here. Watch plays it back in the game exactly as it was played: the same "
            "inputs frame by frame, checked against the live match while it plays.")).pack(anchor="w", pady=(2, 10))

        cols = ("when", "fighters", "result", "opponent", "kind")
        frame = ttk.Frame(box)
        frame.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(frame, columns=cols, show="headings", height=12, selectmode="browse")
        for key, label, width in (("when", t("Date"), 150), ("fighters", t("Fighters"), 260), ("result", t("Result"), 130),
                                  ("opponent", t("Opponent"), 170), ("kind", t("Netcode"), 150)):
            self.tv.heading(key, text=label)
            self.tv.column(key, width=width, stretch=key == "fighters")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<Double-1>", lambda _e: self.watch())
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._buttons())

        row = ttk.Frame(box)
        row.pack(fill="x", pady=(10, 4))
        self.watch_btn = app.big_button(row, t("WATCH"), self.watch)
        self.watch_btn.pack(side="left")
        self.stop_btn = ttk.Button(row, text=t("Stop replay"), command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(10, 0))
        ttk.Button(row, text=t("Refresh"), command=self.refresh).pack(side="left", padx=(10, 0))
        self.delete_btn = ttk.Button(row, text=t("Delete"), command=self.delete, state="disabled")
        self.delete_btn.pack(side="left", padx=(10, 0))
        ttk.Button(row, text=t("Open replays folder"), command=self.open_folder).pack(side="right")

        self.verdict = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.verdict, style="H2.TLabel", wraplength=860, justify="left").pack(
            anchor="w", pady=(6, 2))
        ttk.Label(box, style="Muted.TLabel", wraplength=860, justify="left", text=t(
            "While a replay plays: START (Enter) pauses and goes on, SELECT (Tab) ends the replay. A rematch is "
            "played after the matches before it in the same session: it starts from what they left.")).pack(
            anchor="w", pady=(2, 8))

        opts = ttk.Frame(box)
        opts.pack(anchor="w")
        self.rec_var = tk.BooleanVar(value=bool(app.settings["replays"]))
        ttk.Checkbutton(opts, text=t("Save online matches as replays"), variable=self.rec_var,
                        command=self._save).pack(side="left")
        self.names_var = tk.BooleanVar(value=bool(app.settings["replay_names"]))
        ttk.Checkbutton(opts, text=t("Keep the players' names in replays"), variable=self.names_var,
                        command=self._save).pack(side="left", padx=(16, 0))
        self.count_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.count_var, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------------ data
    @property
    def folder(self):
        return self.app.settings.replay_dir

    def _save(self):
        self.app.settings["replays"] = bool(self.rec_var.get())
        self.app.settings["replay_names"] = bool(self.names_var.get())
        if not self.app.readonly:
            self.app.settings.save()

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.entries = replays.list_replays(self.folder) if os.path.isdir(self.folder) else []
        self.tv.delete(*self.tv.get_children())
        for i, e in enumerate(self.entries):
            self.tv.insert("", "end", iid=str(i), values=(
                e.when.strftime("%Y-%m-%d %H:%M") if e.when else "?",
                e.fighters,
                self._result_text(e),
                e.opponent or t("(name not saved)"),
                (t("Rollback") if e.mode == "rollback" else t("Lockstep")) + ("  ·  " + t("rematch") if e.rematch else ""),
            ))
        files = len({e.path for e in self.entries})
        self.count_var.set(t("{matches} match(es) in {files} file(s) in {folder}", matches=len(self.entries), files=files,
                             folder=self.folder) if self.entries else t("No replays yet. Play an online match: it is saved here."))
        self._buttons()

    @staticmethod
    def _result_text(e):
        if not e.complete:
            return t("not finished")
        if e.won is None:
            return t("draw")
        if e.won:
            return t("won {mine}-{theirs}", mine=e.score[0], theirs=e.score[1])
        return t("lost {mine}-{theirs}", mine=e.score[0], theirs=e.score[1])

    def selected(self):
        sel = self.tv.selection()
        if not sel:
            return None
        try:
            return self.entries[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _buttons(self):
        busy = self.watching is not None
        have = self.selected() is not None
        big = getattr(self.app, "set_big_state", None)       # (the launcher's: the hero button's own look)
        if big is not None:
            big(self.watch_btn, have and not busy)
        else:
            self.watch_btn.configure(state="normal" if have and not busy else "disabled")
        self.delete_btn.configure(state="normal" if have and not busy else "disabled")
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def build_id(self):
        """This PC's game build id (the one online matches compare), '' when unknown."""
        if getattr(self, "_build_id", None) is None:
            self._build_id = ""
            try:
                from t5lobby import buildid
                self._build_id = buildid.BuildInfo.from_out_dir(self.app.settings.out_dir).build_id
            except Exception:       # noqa: BLE001 -- not built, or lobby/ missing: no warning then
                pass
        return self._build_id

    # ------------------------------------------------------------------ actions
    def watch(self):
        e = self.selected()
        if e is None or self.watching is not None or self.app.readonly:
            return
        g = getattr(self.app, "game", None)
        if g is not None and g.running():
            self.verdict.set(t("Close the running game first (Stop game on the Play tab)."))
            return
        if not self.app.game_state().get("ok"):
            self.verdict.set(t("Build the game first (Build tab)."))
            return
        result = os.path.join(self.app.settings.out_dir, "logs", "replay-verdict.json")
        os.makedirs(os.path.dirname(result), exist_ok=True)
        try:
            os.remove(result)
        except OSError:
            pass
        try:
            env = replays.playback_env(e.path, e.index, result)
        except replays.ReplayError as err:
            self.verdict.set(t("This replay cannot be played: {why}", why=str(err)))
            return
        here = self.build_id()
        if e.build and here and e.build != here:
            self.verdict.set(t("Recorded with another version of the game: it may not play back the same."))
        game = self.app.start_game(env)
        if game is None:
            return
        self.watching = (game, result, e, time.time())
        if not (e.build and here and e.build != here):
            self.verdict.set(t("Playing {fighters} ({when})...", fighters=e.fighters,
                               when=e.when.strftime("%Y-%m-%d %H:%M") if e.when else "?"))
        core.log(f"replay: watching {os.path.basename(e.path)} match {e.index}")
        self._buttons()
        self.parent.after(500, self._poll)

    def stop(self):
        if self.watching is not None:
            self.watching[0].stop()

    def _poll(self):
        if self.watching is None:
            return
        game, result, e, t0 = self.watching
        if game.running():
            self.parent.after(500, self._poll)
            return
        self.watching = None
        v = replays.read_result(result)
        if v is None:
            self.verdict.set(t("The replay ended before the end of the match."))
        elif v.get("error"):
            self.verdict.set(t("This replay cannot be played: {why}", why=v["error"]))
        elif v.get("identical"):
            self.verdict.set(t("Replay over: identical to the live match ({checks} checks, same result).",
                               checks=v.get("hashes_compared", 0)))
        elif v.get("hash_mismatches"):
            self.verdict.set(t("Replay over, but it went a different way from frame {frame} on (the game or its "
                               "version differs from the one that played it).", frame=v.get("first_mismatch")))
        else:
            self.verdict.set(t("Replay over."))
        core.log(f"replay: {os.path.basename(e.path)} match {e.index}: {v}")
        self._buttons()

    def delete(self):
        e = self.selected()
        if e is None:
            return
        others = [x for x in self.entries if x.path == e.path]
        q = t("Delete this replay file? It holds {n} match(es) against the same opponent.", n=len(others))
        try:
            from t5lobby import dialogs
            ok = dialogs.ask_yes_no(t("Replays"), q, parent=self.parent)
        except ImportError:
            from tkinter import messagebox
            ok = messagebox.askyesno(t("Replays"), q, parent=self.parent)
        if not ok:
            return
        try:
            os.remove(e.path)
        except OSError as err:
            self.verdict.set(str(err))
        self.refresh()

    def open_folder(self):
        os.makedirs(self.folder, exist_ok=True)
        core.open_path(self.folder)
