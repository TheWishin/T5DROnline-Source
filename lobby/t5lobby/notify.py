"""A chime and a flashing taskbar button when the Online tab has something for a player who looks elsewhere.

Players wait for an opponent in another window ("a sound effect when you find a match, or someone joins your
room. Most of us play while alt-tabbing"). The tab calls Notifier.notify() for the moments a person has to act:

    match       a match was found and asks for Accept (quick, ranked, a room's pair, a tournament's next game)
    join        someone joined the room this player hosts
    turn        it is this player's turn in a community room (the countdown to their match began)
    invite      a friend invites this player (to a casual match or to a room)
    tour        "Your tournament set is ready"
    rematch     the opponent asks for a rematch

Only when the player is not looking: another program is in front, the launcher is minimized, or its Online tab is
not the one shown (tk_tab.OnlineTab._notify_away). Settings "Sound and taskbar flash ..." (launcher.json "notify",
on by default) switches it off. Not on lobby updates, chat or the like, and at most once per event: a key (the match
id, the invite id, ...) is told once; the news of a room (join / turn) comes from RoomWatch, which compares one
`room` message with the one before. Events that come close together (a join and the match it starts, a turn and its
first countdown tick) make one chime: nothing is played within COALESCE_S of the last one.

The sound is made here, from nothing: two soft bell tones in a 16-bit mono WAV that is built in memory (chime_wav),
no game audio and no file anywhere. winsound cannot play a memory image asynchronously, so a daemon thread plays it
(the Tk thread never waits); if Windows refuses, the system sound "SystemAsterisk" plays instead. The taskbar button
flashes with FlashWindowEx (FLASHW_TRAY | FLASHW_TIMERNOFG): until the window comes to the front, which also ends
it when winfront brings the launcher forward by itself.

T5_NOTIFY=0 in the environment turns the real sound and flash off (the tests; the hooks of a test are its own).
"""
import collections
import ctypes
import functools
import io
import math
import os
import struct
import threading
import time
import wave

try:
    import winsound
except ImportError:                      # not Windows
    winsound = None

MATCH, JOIN, TURN, INVITE, TOUR, REMATCH = "match", "join", "turn", "invite", "tour", "rematch"

COALESCE_S = 3.0          # a second notification this soon after one that went out makes no second chime
SEEN_MAX = 128            # keys of events told so far (a long session must not grow without end)

FLASHW_TRAY = 0x2
FLASHW_TIMERNOFG = 0xC    # flash until the window comes to the foreground
FLASHW_STOP = 0x0


def _off():
    return os.environ.get("T5_NOTIFY") == "0"


# ---------------------------------------------------------------------- the sound
RATE = 22050
# (start s, frequency Hz, length s, decay time constant s, level): E5, then B5 a fifth above, rung while the first
# still sounds; each with a 2nd partial, so it is a soft bell and not a beep.
TONES = ((0.00, 659.26, 0.30, 0.075, 1.0),
         (0.13, 987.77, 0.42, 0.110, 0.85))
PEAK = 0.30               # of full scale: soft, not startling next to a game or a video call


@functools.lru_cache(maxsize=1)
def chime_wav():
    """The chime as a WAV file image (bytes): 16-bit mono, 22.05 kHz, about half a second."""
    total = max(start + length for start, _f, length, _d, _l in TONES)
    n = int(RATE * total) + 1
    mix = [0.0] * n
    for start, freq, length, tau, level in TONES:
        first = int(RATE * start)
        count = int(RATE * length)
        for i in range(count):
            t = i / RATE
            env = min(1.0, t / 0.006) * math.exp(-t / tau)           # a 6 ms attack (no click), then a bell's decay
            env *= min(1.0, (length - t) / 0.02)                      # ... and 20 ms to silence at the end
            w = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t)
            if first + i < n:
                mix[first + i] += level * env * w
    top = max(abs(v) for v in mix) or 1.0
    scale = PEAK * 32767 / top
    frames = struct.pack("<%dh" % n, *(int(round(v * scale)) for v in mix))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    return out.getvalue()


def _play_now(wav):
    """Runs on its own thread: the chime, or, when Windows refuses it, the system's asterisk."""
    try:
        winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        return
    except (RuntimeError, OSError):
        pass
    try:
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except (RuntimeError, OSError):
        pass


def play_chime():
    """Start the chime and return at once (it plays on a daemon thread). -> True when it was started."""
    if winsound is None or os.name != "nt" or _off():
        return False
    try:
        threading.Thread(target=_play_now, args=(chime_wav(),), daemon=True, name="notify-chime").start()
        return True
    except (RuntimeError, OSError, MemoryError):
        return False


# ---------------------------------------------------------------------- the taskbar button
class FLASHWINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]


def flash_window(hwnd, flags=FLASHW_TRAY | FLASHW_TIMERNOFG):
    """FlashWindowEx on a top-level window: by default the taskbar button, until the window is in front.
    flags=FLASHW_STOP ends it. -> True when the call was made."""
    if os.name != "nt" or not hwnd or _off():
        return False
    try:
        user32 = ctypes.WinDLL("user32")
        user32.FlashWindowEx.argtypes = [ctypes.POINTER(FLASHWINFO)]
        user32.FlashWindowEx.restype = ctypes.c_int
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, flags, 0xFFFFFFFF if flags else 0, 0)
        user32.FlashWindowEx(ctypes.byref(info))
        return True
    except (AttributeError, OSError, ValueError, ctypes.ArgumentError):
        return False


# ---------------------------------------------------------------------- the rules
class Notifier:
    """When to chime and flash. The hooks are plain attributes: the Online tab sets them (its settings, its window),
    a test sets its own fakes.

        enabled()   the setting is on                              -> bool
        away()      the player is probably not looking at the tab  -> bool
        play()      start the chime (must not wait for it)
        flash()     flash the taskbar button
        log(text)   one line for launcher.log (optional)
    """

    def __init__(self, enabled=None, away=None, play=play_chime, flash=None, log=None, clock=time.monotonic):
        self.enabled = enabled or (lambda: True)
        self.away = away or (lambda: True)
        self.play = play
        self.flash = flash or (lambda: False)
        self.log = log
        self.clock = clock
        self._seen = collections.OrderedDict()
        self._last = None             # when the last chime went out

    def notify(self, kind, key=None):
        """Something happened that wants this player. `key` names the event (a match id, an invite id): the same
        (kind, key) is told once, whatever else is true. -> True when the chime and the flash went out."""
        if key is not None:
            ident = (kind, str(key)[:200])        # (a text: whatever the server sent as an id is hashable)
            if ident in self._seen:
                return False
            self._seen[ident] = True
            while len(self._seen) > SEEN_MAX:
                self._seen.popitem(last=False)
        try:
            if not self.enabled() or not self.away():
                return False
        except Exception:             # noqa: BLE001 -- a window that is gone is no reason to break the tab
            return False
        now = self.clock()
        if self._last is not None and 0 <= now - self._last < COALESCE_S:
            return False
        self._last = now
        for hook in (self.play, self.flash):
            try:
                hook()
            except Exception:         # noqa: BLE001 -- no sound card, no window: the tab goes on
                pass
        if self.log is not None:
            try:
                self.log(f"notify: {kind}")
            except Exception:         # noqa: BLE001 -- the log is best effort
                pass
        return True


class RoomWatch:
    """What a player's own room has new, from one `room` message to the next (LobbyClient's "room" event): someone
    joined a room this player hosts, and the countdown to this player's turn began in a community room. The first
    message of a room is only the baseline (joining or creating it is not news)."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Not in a room (any more)."""
        self.room_id = None
        self.members = set()
        self.turn = False

    def update(self, room, me_id):
        """-> [(kind, name or None)] for JOIN (one per newcomer) and TURN, in the order they happened."""
        if not isinstance(room, dict) or me_id is None:
            return []
        listed = room.get("players") if isinstance(room.get("players"), (list, tuple)) else ()
        players = {p.get("id"): p.get("name") for p in listed if isinstance(p, dict) and isinstance(p.get("id"), (int, str))}
        news = []
        same = room.get("id") == self.room_id
        if same and room.get("owner_id") == me_id:
            news += [(JOIN, name) for pid, name in players.items() if pid not in self.members and pid != me_id]
        nxt = room.get("next") if isinstance(room.get("next"), dict) else {}
        pair = nxt.get("players") if isinstance(nxt.get("players"), (list, tuple)) else ()
        turn = me_id in pair
        if turn and not self.turn:
            news.append((TURN, None))
        self.room_id, self.members, self.turn = room.get("id"), set(players), turn
        return news
