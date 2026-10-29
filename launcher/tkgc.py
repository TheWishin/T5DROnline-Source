"""Python's cyclic garbage collector, run on the Tk thread only (the launcher, 1.1.9).

Left to itself the collector runs in whichever thread happens to allocate when its counters overflow: the lobby
client's thread, a download, a picture reader, the update check. Whatever garbage is waiting is then freed in that
thread -- and the launcher's garbage is full of Tk objects (a closed window's widgets, its pictures, variables and
fonts all point at each other). Tk must only be touched from the thread that made it: a Tk interpreter freed
elsewhere aborts the process ("Tcl_AsyncDelete: async handler deleted by the wrong thread", 1.1.7's release check),
and a picture, variable or font freed elsewhere has to ask the Tk thread to delete it while that thread may be
waiting for the very thread that is collecting.

install(root) switches the automatic collection off for the whole process and collects from root.after() instead,
on the Tk thread, with the collector's own thresholds (a young-generation pass costs well under a millisecond);
nothing else changes. Garbage made while the main loop is busy waits until it is free again.
"""
import gc

TICK_MS = 100           # how often the counters are looked at
FULL_EVERY_S = 60       # the oldest generation at least this often (long-lived cycles: closed windows)

_state = {"root": None, "after": None, "since_full": 0}


def install(root, tick_ms=TICK_MS):
    """Collect garbage only on root's thread from now on (root: the Tk root, on the thread that made it). A
    second call (a new root: the tests) moves the collection to the new root."""
    gc.disable()
    old = _state["root"]
    if old is not None and _state["after"] is not None:
        try:
            old.after_cancel(_state["after"])
        except Exception:      # noqa: BLE001 -- the old root is gone
            pass
    _state.update(root=root, after=None, since_full=0, tick_ms=tick_ms)
    _schedule()


def installed_on(root):
    return _state["root"] is root and not gc.isenabled()


def _schedule():
    root = _state["root"]
    try:
        _state["after"] = root.after(_state["tick_ms"], _tick)
    except Exception:          # noqa: BLE001 -- the window is gone: nothing left to collect for
        _state["after"] = None


def _tick():
    _state["after"] = None
    collect_due()
    _state["since_full"] += _state["tick_ms"]
    if _state["since_full"] >= FULL_EVERY_S * 1000:
        _state["since_full"] = 0
        gc.collect()
    _schedule()


def collect_due():
    """One collection like the automatic one would have made by now: the oldest generation whose counter is over
    its threshold (gc.get_threshold), or none. -> the generation collected, or None."""
    t0, t1, t2 = gc.get_threshold()
    c0, c1, c2 = gc.get_count()
    gen = 2 if c2 > t2 else 1 if c1 > t1 else 0 if c0 > t0 else None
    if gen is not None:
        if gen == 2:
            _state["since_full"] = 0
        gc.collect(gen)
    return gen
