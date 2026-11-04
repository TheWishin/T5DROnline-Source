"""The launcher's Replays tab (docs/REPLAYS.md): every recorded online match, Watch plays it in the game.

The game writes the files (src/netplay/replay.cpp) into the chosen replay folder while a session runs; this
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
import replay_library
from core import t


class ReplaysTab:
    def __init__(self, parent, app):
        self.app = app
        self.parent = parent
        self.entries = []
        self.watching = None          # (GameRun, result path, Entry) while a replay plays
        self._sort_newest = True
        self.channel = None
        self.viewer_status = {}
        self.viewer_widgets = []
        self._seeking = False
        box = ttk.Frame(parent, padding=(24, 16))
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=t("Replays"), style="H1.TLabel").pack(anchor="w")
        ttk.Label(box, style="Muted.TLabel", wraplength=860, justify="left", text=t(
            "Every online match is saved here. Watch plays it back in the game exactly as it was played: the same "
            "inputs frame by frame, checked against the live match while it plays.")).pack(anchor="w", pady=(2, 10))

        filters = ttk.Frame(box)
        filters.pack(fill="x", pady=(0, 8))
        self.fighter_filter = tk.StringVar(value="")
        self.opponent_filter = tk.StringVar(value="")
        self.mode_filter = tk.StringVar(value=t("All"))
        self.favourites_filter = tk.BooleanVar(value=False)
        for label, variable in ((t("Fighter"), self.fighter_filter), (t("Opponent"), self.opponent_filter)):
            ttk.Label(filters, text=label).pack(side="left", padx=(0, 4))
            entry = ttk.Entry(filters, textvariable=variable, width=14)
            entry.pack(side="left", padx=(0, 12))
            variable.trace_add("write", lambda *_: self._filter())
        mode = ttk.Combobox(filters, textvariable=self.mode_filter, state="readonly", width=12,
                            values=(t("All"), t("Rollback"), t("Lockstep")))
        mode.pack(side="left", padx=(0, 12))
        mode.bind("<<ComboboxSelected>>", lambda _e: self._filter())
        ttk.Checkbutton(filters, text=t("Favourites only"), variable=self.favourites_filter,
                        command=self._filter).pack(side="left")

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
        self.favourite_btn = ttk.Button(row, text=t("Favourite"), command=self.favourite, state="disabled")
        self.favourite_btn.pack(side="left", padx=(10, 0))
        ttk.Button(row, text=t("Open replays folder"), command=self.open_folder).pack(side="right")

        controls = ttk.Frame(box)
        controls.pack(fill="x", pady=(6, 2))
        self.pause_btn = ttk.Button(controls, text=t("Pause"), command=self.pause)
        self.pause_btn.pack(side="left")
        self.viewer_widgets.append(self.pause_btn)
        for label, command in ((t("Back 10 s"), lambda: self.seek_relative(-600)),
                               (t("Forward 10 s"), lambda: self.seek_relative(600)),
                               (t("Frame step"), lambda: self.command("step"))):
            button = ttk.Button(controls, text=label, command=command)
            button.pack(side="left", padx=(6, 0))
            self.viewer_widgets.append(button)
        ttk.Label(controls, text=t("Speed")).pack(side="left", padx=(12, 4))
        self.speed_var = tk.StringVar(value="1")
        speed = ttk.Combobox(controls, textvariable=self.speed_var, values=("0.25", "0.5", "1", "2", "4"),
                             width=5, state="disabled")
        speed.pack(side="left")
        speed.bind("<<ComboboxSelected>>", lambda _e: self.command("speed " + self.speed_var.get()))
        self.viewer_widgets.append(speed)
        self._viewer_combos = [speed]

        timeline = ttk.Frame(box)
        timeline.pack(fill="x", pady=(4, 2))
        self.seek_var = tk.DoubleVar(value=0)
        self.seek_bar = ttk.Scale(timeline, variable=self.seek_var, from_=0, to=1)
        self.seek_bar.pack(side="left", fill="x", expand=True)
        self.seek_bar.bind("<ButtonPress-1>", lambda _e: setattr(self, "_seeking", True))
        self.seek_bar.bind("<ButtonRelease-1>", lambda _e: self._seek_release())
        self.seek_bar.bind("<KeyRelease>", lambda _e: self.seek(int(self.seek_var.get())))
        self.viewer_widgets.append(self.seek_bar)
        self.round_var = tk.StringVar(value="")
        self.round_box = ttk.Combobox(timeline, textvariable=self.round_var, width=14, state="disabled")
        self.round_box.pack(side="left", padx=(8, 0))
        self.round_box.bind("<<ComboboxSelected>>", lambda _e: self.seek_round())
        self.viewer_widgets.append(self.round_box)
        self._viewer_combos.append(self.round_box)
        for side in (1, 2):
            button = ttk.Button(timeline, text=t("Take P{side}", side=side),
                                command=lambda side=side: self.command("control " + str(side)))
            button.pack(side="left", padx=(6, 0))
            self.viewer_widgets.append(button)
        self.position_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.position_var, style="Muted.TLabel").pack(anchor="w")

        self.verdict = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.verdict, style="H2.TLabel", wraplength=860, justify="left").pack(
            anchor="w", pady=(6, 2))
        ttk.Label(box, style="Muted.TLabel", wraplength=860, justify="left", text=t(
            "START (Enter) pauses or resumes; SELECT (Tab) ends playback. Taking control uses the local pad and "
            "marks playback unverified from that frame. Older replays may need earlier matches to play first.")).pack(
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
        self.folder_warning = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.folder_warning, style="warn.TLabel", wraplength=860,
                  justify="left").pack(anchor="w", pady=(4, 0))
        self._buttons()

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
        folder, warning = self.app.settings.replay_dir_status()
        self.folder_warning.set(warning)
        entries = replays.list_replays(folder) if os.path.isdir(folder) else []
        self._listed, self._listed_folder, self._read_at = entries, folder, time.time()
        self.library = replay_library.Library(folder)
        self._filter()

    def _filter(self):
        if not hasattr(self, "library"):
            return
        selected = self.selected()
        mode = {t("Rollback"): "rollback", t("Lockstep"): "lockstep"}.get(self.mode_filter.get(), "")
        self.entries = self.library.filter(self._listed, self.fighter_filter.get(), self.opponent_filter.get(),
                                           mode, self.favourites_filter.get())
        self.tv.delete(*self.tv.get_children())
        for i, e in enumerate(self.entries):
            self.tv.insert("", "end", iid=str(i), values=(
                ("★ " if self.library.favourite(e) else "") + (e.when.strftime("%Y-%m-%d %H:%M") if e.when else "?"),
                e.fighters,
                self._result_text(e),
                e.opponent or t("(name not saved)"),
                (t("Rollback") if e.mode == "rollback" else t("Lockstep")) + ("  ·  " + t("rematch") if e.rematch else ""),
            ))
            if selected is not None and e.path == selected.path and e.index == selected.index:
                self.tv.selection_set(str(i))
        files = len({e.path for e in self.entries})
        self.count_var.set(t("{matches} match(es) in {files} file(s) in {folder}", matches=len(self.entries), files=files,
                             folder=self.folder) if self._listed else t("No replays yet. Play an online match: it is saved here."))
        self._buttons()

    def favourite(self):
        entry = self.selected()
        if entry is None or self.app.readonly:
            return
        try:
            self.library.toggle(entry)
        except OSError as err:
            self.verdict.set(str(err))
            return
        self._filter()

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
        self.favourite_btn.configure(state="normal" if have and not self.app.readonly else "disabled")
        for widget in self.viewer_widgets:
            widget.configure(state=("readonly" if widget in self._viewer_combos else "normal") if busy else "disabled")

    def command(self, text):
        if self.watching is not None and self.channel is not None:
            try:
                self.channel.send(text)
            except OSError as err:
                self.verdict.set(str(err))

    def pause(self):
        self.command("resume" if self.viewer_status.get("paused") else "pause")

    def seek(self, frame):
        start, end = self.viewer_status.get("start", 0), self.viewer_status.get("end", 0)
        self.command("seek " + str(max(start, min(end, frame))))

    def seek_relative(self, delta):
        self.seek(self.viewer_status.get("frame", 0) + delta)

    def _seek_release(self):
        self._seeking = False
        self.seek(int(self.seek_var.get()))

    def seek_round(self):
        index = self.round_box.current()
        rounds = self.viewer_status.get("rounds", [])
        if 0 <= index < len(rounds):
            self.seek(rounds[index])

    def _viewer_poll(self):
        if self.channel is None:
            return
        try:
            status = self.channel.read()
        except OSError as err:
            self.verdict.set(str(err))
            return
        if status is None:
            return
        self.viewer_status = status
        self.pause_btn.configure(text=t("Resume") if status.get("paused") else t("Pause"))
        self.seek_bar.configure(from_=status["start"], to=max(status["start"] + 1, status["end"]))
        if not self._seeking:
            self.seek_var.set(status["frame"])
        self.speed_var.set(str(status.get("speed", 1)))
        self.round_box.configure(values=[t("Round {n}", n=n) for n in range(1, len(status["rounds"]) + 1)])
        self.position_var.set(t("Frame {frame} / {end}", frame=status["frame"], end=status["end"]) + "  ·  " +
                              (t("Verified playback") if status.get("verified", True) else t("Unverified: player control")))
        if status.get("error"):
            self.verdict.set(t("This replay command is unavailable at the current frame."))

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

    # ------------------------------------------------------------------ the Online tab's match history (1.1.5)
    def entries_now(self, max_age=10.0):
        """Every replay on this PC, read again when the last reading is older than max_age seconds."""
        folder = self.folder
        if folder != getattr(self, "_listed_folder", None) or time.time() - getattr(self, "_read_at", 0.0) > max_age:
            self._listed = replays.list_replays(folder) if os.path.isdir(folder) else []
            self._listed_folder = folder
            self._read_at = time.time()
        return self._listed

    def for_history(self, h, ids):
        """The replay of a row of the profile's match history (server history: time, you_char, opp_char, opponent,
        score), or None. ids: fighter key -> the replay's fighter id."""
        try:
            return replays.for_history(self.entries_now(), h["time"], ids.get(h.get("you_char")),
                                       ids.get(h.get("opp_char")), h.get("opponent"), h.get("score"))
        except (KeyError, TypeError, AttributeError):
            return None

    def watch_entry(self, e):
        """Watch `e` from elsewhere (the profile's Watch replay): the Replays tab comes to the front with its row
        selected, and plays it as WATCH would."""
        nb, tabs = getattr(self.app, "nb", None), getattr(self.app, "tabs", None)
        if nb is not None and tabs and "replays" in tabs:
            nb.select(tabs["replays"])
        self.fighter_filter.set("")
        self.opponent_filter.set("")
        self.mode_filter.set(t("All"))
        self.favourites_filter.set(False)
        self.refresh()
        for i, x in enumerate(self.entries):
            if x.path == e.path and x.index == e.index:
                self.tv.selection_set(str(i))
                self.tv.see(str(i))
                break
        else:
            self.verdict.set(t("This replay is no longer on this PC."))
            return
        self.watch()

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
        try:
            self.channel = replay_library.ViewerChannel(result + ".command", result + ".status")
        except OSError as err:
            self.verdict.set(str(err))
            return
        env.update(T5_REPLAY_COMMAND=self.channel.command, T5_REPLAY_STATUS=self.channel.status, T5_REPLAY_CAPSULES="1")
        self.viewer_status = {}
        self.position_var.set("")
        self.speed_var.set("1")
        self.round_var.set("")
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
            game = self.watching[0]
            self.channel.pending.clear()
            self.command("quit")
            self.parent.after(2000, lambda: self._stop_if_running(game))

    def _stop_if_running(self, game):
        if self.watching is not None and self.watching[0] is game and game.running():
            game.stop()

    def _poll(self):
        if self.watching is None:
            return
        game, result, e, t0 = self.watching
        if game.running():
            self._viewer_poll()
            self.parent.after(500, self._poll)
            return
        self.watching = None
        v = replays.read_result(result)
        if v is None:
            self.verdict.set(t("The replay ended before the end of the match."))
        elif v.get("error"):
            self.verdict.set(t("This replay cannot be played: {why}", why=v["error"]))
        elif v.get("unverified_from") is not None:
            self.verdict.set(t("Replay over: unverified from frame {frame} (player control).", frame=v["unverified_from"]))
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
        others = [x for x in self._listed if x.path == e.path]
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
        folder, warning = self.app.settings.replay_dir_status()
        self.folder_warning.set(warning)
        if os.path.isdir(folder):
            core.open_path(folder)
