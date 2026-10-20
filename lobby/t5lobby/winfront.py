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

The other way round (raise_game_window): when a match starts in the game that is already running (a
rematch, the next opponent) while the launcher is in front -- the player just clicked Accept or Rematch
there -- the game's window comes to the front, as it does when the launcher starts the game. The game reads
the keyboard only while its window has the focus (pads work either way), so a keyboard player would
otherwise press keys into the launcher. tk_tab.OnlineTab._game_forward decides.
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
    return _raise_hwnd(hwnd)


def _raise_hwnd(hwnd):
    """Restore a top-level window if minimized and make it the foreground window (see the top). -> True when it is
    the foreground window afterwards."""
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


def find_process_window(pid, prefix="ps3recomp"):
    """The game's top-level window (its window class starts with "ps3recomp"), or None."""
    if os.name != "nt" or not pid:
        return None
    try:
        user32 = ctypes.WinDLL("user32")
        found = []
        proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(hwnd, _):
            p = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(p))
            if p.value == pid:
                cls = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(ctypes.c_void_p(hwnd), cls, 64)
                if cls.value.startswith(prefix):
                    found.append(hwnd)
            return True
        user32.EnumWindows(proc(cb), 0)
        return found[0] if found else None
    except (AttributeError, OSError):
        return None


def raise_game_window(pid):
    """The game's window (process `pid`) to the front. -> True when it is the foreground window afterwards."""
    hwnd = find_process_window(pid)
    return bool(hwnd) and _raise_hwnd(hwnd)
