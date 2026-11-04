"""A chime and a flashing taskbar button when the Online tab has something for a player who looks elsewhere.

Players wait for an opponent in another window ("a sound effect when you find a match, or someone joins your
room. Most of us play while alt-tabbing"). The tab calls Notifier.notify() for the moments a person has to act:

    match       a match was found and asks for Accept (quick, ranked, a room's pair, a tournament's next game)
    challenge   another player challenges this one (1.1.7)
    join        someone joined the room this player hosts
    turn        it is this player's turn in a community room (the countdown to their match began)
    invite      a friend invites this player (to a casual match or to a room)
    tour        "Your tournament set is ready"
    rematch     the opponent asks for a rematch
    mention     public chat mentions this player (server-resolved player IDs, 1.2.0)

Only when the player is not looking: another program is in front, the launcher is minimized, or its Online tab is
not the one shown (tk_tab.OnlineTab._notify_away). Settings "Sound and taskbar flash ..." (launcher.json "notify",
on by default) switches it off. Ordinary chat and lobby updates do not ring. At most once per event: a key (the match
id, the challenge id, the invite id, ...) is told once; the news of a room (join / turn) comes from RoomWatch,
which compares one `room` message with the one before. Events that come close together (a join and the match it
starts, a turn and its first countdown tick) make one chime: nothing is played within COALESCE_S of the last one.

The sound is made here, from nothing: two soft bell tones in a 16-bit mono WAV that is built in memory (chime_wav),
no game audio and no file anywhere. A found match and a tournament set (VOICE_KINDS) use the game's own
announcer by default: "Get ready for the next battle!". Challenges and invites use their own
"Sound for a challenge" setting (notify_challenge_sound): New challenger (default, "A new challenger!"), chime,
own WAV or off. Their custom WAV is stored separately as CHALLENGE_WAV_NAME.
announcer.py reads each pinned line from the player's own unpacked game when it is needed; without it (before BUILD GAME,
a European program, other data) the chime plays. Settings "Sound when a match is found" (launcher.json "notify_sound",
1.2.0) picks that sound: the announcer (default), the beep (the chime), a WAV file of the player's own (copied into the
launcher's settings folder as CUSTOM_WAV_NAME; plain PCM WAV, at most CUSTOM_MAX_S seconds and CUSTOM_MAX_BYTES; a file
that is gone or no longer fits rings the chime and says so in launcher.log) or none (the taskbar still flashes).
winsound cannot play a memory image asynchronously, so a daemon thread plays it
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
CHALLENGE = "challenge"
VOICE_KINDS = (MATCH, TOUR)              # found matches and tournament sets use the match sound setting
CHALLENGE_KINDS = (CHALLENGE, INVITE)

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


def _voice_now(out_dir):
    """Runs on its own thread: the announcer's line from the player's game files, else the chime."""
    try:
        from . import announcer
        wav = announcer.next_battle_wav(out_dir)
    except Exception:                 # noqa: BLE001 -- whatever the files hold, the chime still rings
        wav = None
    _play_now(wav or chime_wav())


def play_voice(out_dir):
    """Start "Get ready for the next battle!" (or the chime when the game's files do not have it) and return at
    once: the files are read and the sound plays on a daemon thread. -> True when it was started."""
    if winsound is None or os.name != "nt" or _off():
        return False
    try:
        threading.Thread(target=_voice_now, args=(out_dir,), daemon=True, name="notify-voice").start()
        return True
    except (RuntimeError, OSError, MemoryError):
        return False


# ---------------------------------------------------------------------- the sound for a found match (Settings)
ANNOUNCER, BEEP, CUSTOM, OFF = "announcer", "beep", "custom", "off"
MATCH_SOUNDS = (ANNOUNCER, BEEP, CUSTOM, OFF)      # launcher.json "notify_sound"; ANNOUNCER is the default
CHIME = "chime"
CHALLENGE_SOUNDS = (ANNOUNCER, CHIME, CUSTOM, OFF)  # ANNOUNCER = "A new challenger!", the default
CUSTOM_WAV_NAME = "match_sound.wav"                # the player's WAV, copied next to launcher.json
CHALLENGE_WAV_NAME = "challenge_sound.wav"
CUSTOM_MAX_BYTES = 2 * 1024 * 1024
CUSTOM_MAX_S = 5.0
CUSTOM_MIN_RATE, CUSTOM_MAX_RATE = 8000, 192000

# why a WAV file is refused (the launcher's Settings turn these into sentences)
WAV_NOT_WAV, WAV_TOO_LONG, WAV_TOO_BIG, WAV_UNREADABLE, WAV_MISSING = (
    "not_wav", "too_long", "too_big", "unreadable", "missing")


def match_sound_choice(settings):
    """The player's choice from the launcher settings (any mapping): "notify_sound", else the 1.2.0 test builds'
    "notify_voice" (False = the beep), else the announcer."""
    try:
        choice = settings.get("notify_sound")
        if choice in MATCH_SOUNDS:
            return choice
        if settings.get("notify_voice") is False:
            return BEEP
    except AttributeError:
        pass
    return ANNOUNCER


def challenge_sound_choice(settings):
    """Independent of the match sound and legacy notify_voice; missing/invalid means "A new challenger!"."""
    try:
        choice = settings.get("notify_challenge_sound")
        if choice in CHALLENGE_SOUNDS:
            return choice
    except AttributeError:
        pass
    return ANNOUNCER


def check_wav(data):
    """None when `data` (bytes) is a WAV file the launcher plays as a match sound, else the reason (WAV_*): plain PCM
    (what winsound plays from memory on every Windows), 1-2 channels, 8-32 bit, 8-192 kHz, some sound, at most
    CUSTOM_MAX_S seconds and CUSTOM_MAX_BYTES."""
    if len(data) > CUSTOM_MAX_BYTES:
        return WAV_TOO_BIG
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return WAV_NOT_WAV
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            got = len(w.readframes(frames))
    except (wave.Error, EOFError, struct.error, ValueError, OverflowError):
        return WAV_NOT_WAV
    if not (1 <= channels <= 2 and 1 <= width <= 4 and CUSTOM_MIN_RATE <= rate <= CUSTOM_MAX_RATE) or frames <= 0:
        return WAV_NOT_WAV
    if got < frames * channels * width:
        return WAV_NOT_WAV                          # the header promises more sound than the file holds
    if frames > CUSTOM_MAX_S * rate + 0.5:
        return WAV_TOO_LONG
    return None


def custom_wav_path(folder, *, challenge=False):
    name = CHALLENGE_WAV_NAME if challenge else CUSTOM_WAV_NAME
    return os.path.join(folder, name) if folder else None


def install_custom_wav(src, folder, *, challenge=False):
    """Copy the player's WAV `src` into `folder` (the launcher's settings folder) as CUSTOM_WAV_NAME, after
    check_wav. -> None when it is in place, else the reason (WAV_*); the copy there before stays when refused."""
    try:
        if os.path.getsize(src) > CUSTOM_MAX_BYTES:
            return WAV_TOO_BIG
        with open(src, "rb") as f:
            data = f.read(CUSTOM_MAX_BYTES + 1)
    except (OSError, ValueError, TypeError):
        return WAV_UNREADABLE
    problem = check_wav(data)
    if problem:
        return problem
    dest = custom_wav_path(folder, challenge=challenge)
    if not dest:
        return WAV_UNREADABLE
    tmp = dest + ".tmp"
    try:
        os.makedirs(folder, exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except (OSError, ValueError, TypeError):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return WAV_UNREADABLE
    return None


def custom_wav(folder, *, challenge=False):
    """(WAV bytes, None) of the player's copied sound, or (None, reason): gone, damaged, or larger / longer than
    allowed (somebody replaced the file)."""
    path = custom_wav_path(folder, challenge=challenge)
    if not path or not os.path.isfile(path):
        return None, WAV_MISSING
    try:
        with open(path, "rb") as f:
            data = f.read(CUSTOM_MAX_BYTES + 1)
    except OSError:
        return None, WAV_UNREADABLE
    problem = check_wav(data)
    return (None, problem) if problem else (data, None)


def match_sound_wav(choice, out_dir=None, folder=None, *, challenge=False):
    """What a found match/tournament set or (challenge=True) challenge/invite rings: (WAV bytes, or None for silence;
    note). note: "" as chosen; "no_game" the announcer
    without the player's unpacked game (the chime instead); a WAV_* reason for the custom sound (the chime
    instead)."""
    if choice == OFF:
        return None, ""
    if choice == CUSTOM:
        wav, problem = custom_wav(folder, challenge=challenge)
        return (wav, "") if wav else (chime_wav(), problem)
    if choice == ANNOUNCER:
        try:
            from . import announcer
            wav = announcer.new_challenger_wav(out_dir) if challenge else announcer.next_battle_wav(out_dir)
        except Exception:             # noqa: BLE001 -- whatever the files hold, the chime still rings
            wav = None
        return (wav, "") if wav else (chime_wav(), "no_game")
    return chime_wav(), ""


def _match_sound_now(choice, out_dir, folder, log, challenge=False):
    """Runs on its own thread: the chosen sound (match_sound_wav); a line in the log when the chime stands in for
    the player's own WAV."""
    try:
        wav, note = match_sound_wav(choice, out_dir, folder, challenge=challenge)
    except Exception:                 # noqa: BLE001 -- the chime is the fallback
        wav, note = chime_wav(), "error"
    if note and note != "no_game" and log is not None:
        try:
            kind = "challenge" if challenge else "match"
            log(f"notify: the custom {kind} sound cannot be played ({note}), the chime instead")
        except Exception:             # noqa: BLE001 -- the log is best effort
            pass
    if wav:
        _play_now(wav)


def play_match_sound(choice, out_dir=None, folder=None, log=None, *, challenge=False):
    """Start the sound chosen for a match/tournament set or (challenge=True) challenge/invite and return at once:
    the files are read and the sound plays on a daemon thread. -> True when it was handled (OFF too: nothing to play),
    False when no sound can be made here (not Windows, T5_NOTIFY=0, no thread)."""
    if choice == OFF:
        return True
    if winsound is None or os.name != "nt" or _off():
        return False
    try:
        threading.Thread(target=_match_sound_now, args=(choice, out_dir, folder, log, challenge), daemon=True,
                         name="notify-match-sound").start()
        return True
    except (RuntimeError, OSError, MemoryError):
        return False


def preview_match_sound(choice, out_dir=None, folder=None, *, challenge=False):
    """Settings' Play button: the sound a match or (challenge=True) challenge would ring now, started on a daemon thread;
    nothing with T5_NOTIFY=0. -> its note (match_sound_wav): why the chime stands in, or ""."""
    wav, note = match_sound_wav(choice, out_dir, folder, challenge=challenge)
    if wav and winsound is not None and os.name == "nt" and not _off():
        try:
            threading.Thread(target=_play_now, args=(wav,), daemon=True, name="notify-preview").start()
        except (RuntimeError, OSError, MemoryError):
            pass
    return note


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
        voice()     for VOICE_KINDS instead of play(): start the sound chosen for a found match (must not wait)
                    -> True when that was handled (started, or "Off" chosen); None, an answer of False or an
                    error -> play()
        challenge() for CHALLENGE_KINDS: the separately chosen challenge/invite sound, with the same fallback
        flash()     flash the taskbar button
        log(text)   one line for launcher.log (optional)
    """

    def __init__(self, enabled=None, away=None, play=play_chime, flash=None, log=None, clock=time.monotonic,
                 voice=None, challenge=None):
        self.enabled = enabled or (lambda: True)
        self.away = away or (lambda: True)
        self.play = play
        self.voice = voice
        self.challenge = challenge
        self.flash = flash or (lambda: False)
        self.log = log
        self.clock = clock
        self._seen = collections.OrderedDict()
        self._last = None             # when the last chime went out

    def _sound(self, kind):
        """Match and challenge/invite choices have separate hooks; other events keep the chime."""
        hook = self.voice if kind in VOICE_KINDS else self.challenge if kind in CHALLENGE_KINDS else None
        if hook is None:
            return self.play

        def voice_or_chime():
            try:
                started = hook()
            except Exception:         # noqa: BLE001 -- the chime is the fallback
                started = False
            if not started:
                self.play()
        return voice_or_chime

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
        for hook in (self._sound(kind), self.flash):
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
