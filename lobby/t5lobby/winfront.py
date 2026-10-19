"""Bring the launcher's window forward: once, when a match is over and the game waits for the player.

After a match the game stays open at character select with its pads held neutral (the persistent game,
docs/DIRECTFIGHT.md): it waits for the launcher's next command, so nothing moves in it. Players took that
for a hang. The Online tab therefore brings its window to the front at that moment -- the result card
with Rematch / Next game / Leave -- and when the opponent asks for a rematch. Never during a fight, and
not when a ranked set's next game starts by itself (tk_tab.OnlineTab._come_forward decides).

Windows only lets the foreground program (here: the game, which the launcher started) hand the
foreground to another window. The launcher's thread joins the foreground thread's input for the moment of
the switch (AttachThreadInput), which is what makes SetForegroundWindow take; if Windows still refuses,
the launcher's taskbar button flashes instead.
"""
import ctypes
import os
import tkinter as tk

from . import padnav

SW_RESTORE = 9


def raise_window(widget):
    """Restore the widget's top-level window if minimized and bring it to the front. A withdrawn window
    (never shown on purpose) stays hidden. -> True when it is the foreground window afterwards."""
    try:
        top = widget.winfo_toplevel()
        state = top.state()
    except tk.TclError:
        return False
    if state == "withdrawn":
        return False
    if os.name != "nt":
        try:
            top.deiconify()
            top.lift()
            top.focus_force()
        except tk.TclError:
            return False
        return True
    hwnd = padnav.toplevel_hwnd(top)
    if not hwnd:
        return False
    try:
        user32 = ctypes.WinDLL("user32")
        kernel32 = ctypes.WinDLL("kernel32")
        for name, res, args in (("GetForegroundWindow", ctypes.c_void_p, []),
                                ("GetWindowThreadProcessId", ctypes.c_ulong, [ctypes.c_void_p, ctypes.c_void_p]),
                                ("AttachThreadInput", ctypes.c_int, [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int]),
                                ("IsIconic", ctypes.c_int, [ctypes.c_void_p]),
                                ("ShowWindow", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
                                ("BringWindowToTop", ctypes.c_int, [ctypes.c_void_p]),
                                ("SetForegroundWindow", ctypes.c_int, [ctypes.c_void_p]),
                                ("FlashWindow", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int])):
            fn = getattr(user32, name)
            fn.restype = res
            fn.argtypes = args
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        fg = user32.GetForegroundWindow()
        if fg == hwnd:
            return True
        me = kernel32.GetCurrentThreadId()
        other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = bool(other and other != me and user32.AttachThreadInput(me, other, 1))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(me, other, 0)
        if user32.GetForegroundWindow() == hwnd:
            return True
        user32.FlashWindow(hwnd, 1)          # Windows said no: at least the taskbar button asks for attention
        return False
    except (AttributeError, OSError):
        return False
