"""Message boxes and a text prompt whose buttons follow the chosen language.

Windows' own message boxes use the language of Windows, and tkinter.simpledialog always says "OK" and
"Cancel". The launcher lets the player pick Deutsch or English independent of Windows, so its questions,
messages and password prompts come from here: same calls, same results, buttons from t5lobby.i18n.

    ask_yes_no(title, message, parent=None) -> bool
    show_info(title, message, parent=None)
    show_error(title, message, parent=None)
    ask_string(title, prompt, parent=None, show=None, initialvalue=None) -> str | None   (None = cancelled)

All of them block until the box is closed, on the Tk thread (a nested event loop, like the system's boxes).
"""
import tkinter as tk
from tkinter import ttk

from .i18n import t


def _root(parent):
    if parent is not None:
        return parent.winfo_toplevel()
    return tk._default_root       # noqa: SLF001 -- the one Tk() of the launcher


def _show(parent, title, message, buttons, default, cancel, entry=False, show=None, initial=None):
    """-> (value of the pressed button, text typed). buttons: [(label, value)], left to right."""
    root = _root(parent)
    w = tk.Toplevel(root)
    w.title(title)
    w.resizable(False, False)
    try:
        if root.winfo_viewable():
            w.transient(root)
    except tk.TclError:
        pass
    out = {"value": cancel}
    body = ttk.Frame(w, padding=(18, 14, 18, 6))
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=message, wraplength=440, justify="left").pack(anchor="w")
    var = tk.StringVar(value=initial or "")
    field = None
    if entry:
        field = ttk.Entry(body, textvariable=var, show=show or "", width=44)
        field.pack(fill="x", pady=(10, 0))
    bar = ttk.Frame(w, padding=(18, 6, 18, 14))
    bar.pack(fill="x")

    def finish(value):
        out["value"] = value
        w.destroy()
    buttons_by_value = {}
    for label, value in reversed(buttons):
        b = ttk.Button(bar, text=label, command=lambda v=value: finish(v))
        b.pack(side="right", padx=(8, 0))
        buttons_by_value[value] = b
    w.bind("<Escape>", lambda _e: finish(cancel))
    w.bind("<Return>", lambda _e: finish(default))
    w.protocol("WM_DELETE_WINDOW", lambda: finish(cancel))
    w.update_idletasks()
    try:                                  # centered over the launcher
        x = root.winfo_rootx() + (root.winfo_width() - w.winfo_reqwidth()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - w.winfo_reqheight()) // 3
        w.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass
    try:
        w.grab_set()
    except tk.TclError:
        pass
    (field or buttons_by_value.get(default) or w).focus_set()
    w.wait_window()
    return out["value"], var.get()


def ask_yes_no(title, message, parent=None, **_ignored):
    value, _text = _show(parent, title, message, [(t("Yes"), True), (t("No"), False)], True, False)
    return bool(value)


def show_info(title, message, parent=None, **_ignored):
    _show(parent, title, message, [(t("OK"), True)], True, True)


def show_error(title, message, parent=None, **_ignored):
    _show(parent, title, message, [(t("OK"), True)], True, True)


def ask_string(title, prompt, parent=None, show=None, initialvalue=None, **_ignored):
    value, text = _show(parent, title, prompt, [(t("OK"), True), (t("Cancel"), False)], True, False,
                        entry=True, show=show, initial=initialvalue)
    return text if value else None
