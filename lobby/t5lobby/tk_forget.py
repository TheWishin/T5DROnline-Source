"""Remove my data (docs/ONLINE.md "Remove my data"): the Online tab's window.

Two parts, each chosen in the window:
  * the account on the server the player is logged in to (accounts only): the password, then what the server would
    remove (a dry run), then "this cannot be undone" -- two confirmations before the server is asked;
  * what this PC keeps for online play, listed with its size: the Online tab's settings and saved logins
    (online.json), the replays, the game's logs, the save the game uses online, the measured rollback cost. Removed
    only after the same confirmations, and only what is ticked. The game build, the offline save and launcher.json
    stay (they are not online data; the build is deleted with the folder).
"""
import glob
import os
import shutil
import tkinter as tk
from tkinter import ttk

from .i18n import t
from .theme import C

REPLAY_EXT = ".t5replay"


def _size(path):
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def human(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def local_items(online_json, out_dir, replay_dir):
    """[(key, label, [paths], bytes)] of what exists on this PC. Replays: only the replay files of the folder (a
    folder the player chose may hold other files); logs: the .log files of <out>/logs."""
    items = []
    if online_json and os.path.isfile(online_json):
        items.append(("online", t("Online tab settings and saved logins"), [online_json], _size(online_json)))
    if replay_dir and os.path.isdir(replay_dir):
        files = glob.glob(os.path.join(glob.escape(replay_dir), "*" + REPLAY_EXT))
        if files:
            items.append(("replays", t("Replays ({count} files)", count=len(files)), files, sum(map(_size, files))))
    logs = os.path.join(out_dir, "logs") if out_dir else ""
    if logs and os.path.isdir(logs):
        files = glob.glob(os.path.join(glob.escape(logs), "*.log"))
        if files:
            items.append(("logs", t("Game logs ({count} files)", count=len(files)), files, sum(map(_size, files))))
    save = os.path.join(out_dir, "gamedata-online") if out_dir else ""
    if save and os.path.isdir(save):
        items.append(("save", t("The save the game uses online"), [save], _size(save)))
    pics = os.path.join(out_dir, "profile-pics") if out_dir else ""     # (launcher/profile_pic.py's cache)
    if pics and os.path.isdir(pics):
        items.append(("pics", t("Profile pictures of your fighters"), [pics], _size(pics)))
    cost = os.path.join(out_dir, "rb_cost.txt") if out_dir else ""
    if cost and os.path.isfile(cost):
        items.append(("cost", t("This PC's measured rollback cost"), [cost], _size(cost)))
    return items


def remove_paths(paths):
    """-> (removed, failed paths)."""
    removed, failed = 0, []
    for p in paths:
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            removed += 1
        except OSError:
            failed.append(p)
    return removed, failed


class ForgetUI:
    def __init__(self, tab):
        self.tab = tab
        self.window = None

    def _paths(self):
        tab = self.tab
        settings = getattr(tab.app, "settings", None)
        out = getattr(settings, "out_dir", "") if settings is not None else ""
        try:
            replays = settings.replay_dir if settings is not None else ""
        except Exception:          # noqa: BLE001 -- (a launcher without replays)
            replays = ""
        return tab.cfg_path, out, replays

    def open(self):
        tab = self.tab
        if self.window is not None:
            try:
                self.window.lift()
                return self.window
            except tk.TclError:
                self.window = None
        view = tab.view
        px = view.px
        c = tab.client
        me = c.me if c is not None and c.connected else None
        account = bool(me) and not me.get("guest", True)
        w = tab.new_window(tab.parent)
        w.title(t("Remove my data"))
        w.configure(bg=C["bg"])
        self.window = w
        w.bind("<Destroy>", lambda e: setattr(self, "window", None) if e.widget is w else None)
        card = view.card(w, pad=16)
        card.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        ttk.Label(card, text=t("Remove my data"), style="Card.H2.TLabel").pack(anchor="w")
        ttk.Label(card, wraplength=px(460), justify="left", style="Card.Muted.TLabel", text=t(
            "Choose what goes. Nothing is removed before you confirm twice.")).pack(anchor="w", pady=(px(4), px(10)))
        self.account_var = tk.BooleanVar(value=account)
        server = tab.server_var.get().strip()
        acc = ttk.Checkbutton(card, variable=self.account_var, style="Card.TCheckbutton", text=t(
            "My account {name} on {server}: profile, rating, friends, blocks, saved logins. Your matches stay in "
            "other players' history as \"deleted player\".", name=(me or {}).get("name", ""), server=server))
        acc.pack(anchor="w")
        if not account:
            self.account_var.set(False)
            acc.configure(state="disabled", text=t(
                "My account on the server: log in with your account first (a guest has nothing on the server)."))
        ttk.Label(card, text=t("On this PC"), style="Card.TLabel").pack(anchor="w", pady=(px(12), px(2)))
        self.items = local_items(*self._paths())
        self.item_vars = {}
        for key, label, _paths, size in self.items:
            var = tk.BooleanVar(value=True)
            self.item_vars[key] = var
            ttk.Checkbutton(card, variable=var, style="Card.TCheckbutton",
                            text=f"{label} -- {human(size)}").pack(anchor="w")
        if not self.items:
            ttk.Label(card, style="Card.Faint.TLabel", text=t("Nothing of the online play is stored on this PC.")).pack(
                anchor="w")
        ttk.Label(card, wraplength=px(460), justify="left", style="Card.Faint.TLabel", text=t(
            "The game build, your offline save and the launcher's settings stay.")).pack(anchor="w", pady=(px(8), 0))
        bar = view.body(card)
        bar.pack(fill="x", pady=(px(12), 0))
        ttk.Button(bar, text=t("Cancel"), style="Card.TButton", command=w.destroy).pack(side="right")
        ttk.Button(bar, text=t("Remove..."), style="Card.Accent.TButton", command=self.start).pack(
            side="right", padx=(0, px(8)))
        return w

    def chosen_local(self):
        return [(key, label, paths) for key, label, paths, _s in self.items if self.item_vars[key].get()]

    def start(self):
        tab = self.tab
        local = self.chosen_local()
        account = bool(self.account_var.get())
        if not local and not account:
            tab.status(t("Nothing chosen."))
            return
        what = "\n".join([t("- your account on the server")] * account + ["- " + label for _k, label, _p in local])
        if not tab.ask_yes_no(t("Remove my data"), t("Remove this?\n\n{what}", what=what), parent=self.window):
            return
        if not account:
            self._confirm_and_remove_local(local)
            return
        c = tab.client
        pw = tab.ask_string(t("Remove my data"), t("Your password:"), show="*", parent=self.window)
        if not pw or tab.client is not c:
            return

        def counted(r):
            n = (r or {}).get("counts") or {}
            text = t("This cannot be undone. The server removes your account {name} now: {matches} match(es) and "
                     "{sets} set(s) keep their result under \"deleted player\", {friends} friend(s) lose you from "
                     "their list.\n\nRemove it?", name=(c.me or {}).get("name", ""), matches=n.get("matches", 0),
                     sets=n.get("sets", 0), friends=n.get("friends", 0))
            if not tab.ask_yes_no(t("Remove my data"), text, parent=self.window):
                return
            tab.call(c.forget_me, pw, then=lambda _r: self._account_gone(local))
        tab.call(c.forget_me, pw, True, then=counted)

    def _account_gone(self, local):
        tab = self.tab
        tab.account_removed()
        if local:
            self._remove_local(local)
        else:
            tab.status(t("Your account and its data were removed from the server."))
        try:
            self.window.destroy()
        except (tk.TclError, AttributeError):
            pass

    def _confirm_and_remove_local(self, local):
        tab = self.tab
        if not tab.ask_yes_no(t("Remove my data"), t("This cannot be undone. Remove the chosen files from this PC?"),
                              parent=self.window):
            return
        self._remove_local(local)
        try:
            self.window.destroy()
        except (tk.TclError, AttributeError):
            pass

    def _remove_local(self, local):
        tab = self.tab
        paths = [p for _k, _l, ps in local for p in ps]
        if any(k == "online" for k, _l, _p in local):
            tab.cfg.clear()              # (the tab would write its settings back when it closes)
            tab._cfg_removed = True
        removed, failed = remove_paths(paths)
        if failed:
            tab.status(t("Removed {removed} item(s); {failed} could not be removed (in use?): {first}",
                         removed=removed, failed=len(failed), first=failed[0]))
        else:
            tab.status(t("Removed: {what}.", what=", ".join(label for _k, label, _p in local)))
