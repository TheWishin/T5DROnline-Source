"""The Online tab's chime and taskbar flash (lobby/t5lobby/notify.py): the sound is made in code and plays without
holding anyone up, FlashWindowEx gets the flags that keep the button flashing until the window is in front, the
Notifier chimes once per event and only for a player who is elsewhere, RoomWatch finds what is new in a room, and
Settings has the checkbox ("notify", on by default). Nothing here makes a sound or flashes a window: winsound and
user32 are fakes, the Settings tab is built withdrawn. The events of the tab itself: lobby/tests/test_tk_notify.py."""
import ctypes
import io
import json
import math
import os
import struct
import sys
import threading
import unittest
import wave
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("lobby", "launcher", "tests"):
    if os.path.join(ROOT, sub) not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, sub))
os.environ["T5_NOTIFY"] = "0"                # (switched on only inside the tests that fake winsound / user32)

try:
    import tkinter as tk
except ImportError:      # pragma: no cover
    tk = None

from t5lobby import notify  # noqa: E402

SOUND_ON = {"T5_NOTIFY": "1"}


def goertzel(samples, rate, freq):
    """The strength of one frequency in `samples` (a plain Goertzel filter: no numpy here)."""
    k = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    for x in samples:
        s1, s2 = x + k * s1 - s2, s1
    return s1 * s1 + s2 * s2 - k * s1 * s2


class ChimeTests(unittest.TestCase):
    def read(self):
        wav = notify.chime_wav()
        with wave.open(io.BytesIO(wav)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, notify.RATE))
            n = w.getnframes()
            return n, struct.unpack("<%dh" % n, w.readframes(n))

    def test_a_short_soft_wav_made_in_memory(self):
        wav = notify.chime_wav()
        self.assertIsInstance(wav, bytes)
        self.assertEqual(wav[:4], b"RIFF")
        n, samples = self.read()
        self.assertTrue(0.3 < n / notify.RATE < 0.8, n / notify.RATE)        # about half a second
        self.assertLess(len(wav), 64 * 1024)                                  # tiny
        peak = max(abs(s) for s in samples)
        self.assertGreater(peak, 0.2 * 32767)                                 # audible ...
        self.assertLessEqual(peak, 0.31 * 32767)                              # ... and soft: never loud, never clipped
        self.assertLess(abs(samples[0]), 300)                                 # no click at the start ...
        self.assertLess(abs(samples[-1]), 300)                                # ... nor at the end
        self.assertIs(notify.chime_wav(), wav)                                # built once

    def test_two_tones_the_second_one_higher(self):
        n, samples = self.read()
        rate = notify.RATE
        first, second = notify.TONES[0][1], notify.TONES[1][1]

        def window(a, b):
            return [s / 32768.0 for s in samples[int(a * rate):int(b * rate)]]
        early, late = window(0.02, 0.11), window(0.25, 0.40)
        self.assertGreater(goertzel(early, rate, first), 20 * goertzel(early, rate, second))   # E5 first ...
        self.assertGreater(goertzel(late, rate, second), 20 * goertzel(late, rate, first))     # ... then B5
        self.assertGreater(second, first)

    def test_no_game_audio_and_no_file(self):
        with mock.patch("builtins.open", side_effect=AssertionError("the chime must not touch a file")):
            notify.chime_wav.cache_clear()
            try:
                notify.chime_wav()
            finally:
                notify.chime_wav.cache_clear()


class FakeWinsound:
    SND_MEMORY, SND_NODEFAULT, SND_ALIAS, SND_ASYNC = 4, 2, 0x10000, 1

    def __init__(self, fail_memory=False, block=None):
        self.calls = []
        self.fail_memory = fail_memory
        self.block = block                 # an Event the first PlaySound waits for (a chime that takes its time)
        self.done = threading.Event()

    def PlaySound(self, sound, flags):
        self.calls.append((sound, flags))
        try:
            if self.block is not None and flags & self.SND_MEMORY:
                self.block.wait(5)
            if self.fail_memory and flags & self.SND_MEMORY:
                raise RuntimeError("Failed to play sound")
        finally:
            self.done.set()


@unittest.skipUnless(os.name == "nt", "the chime is Windows only")
class PlayTests(unittest.TestCase):
    def test_plays_the_memory_image_on_a_thread_and_returns_at_once(self):
        gate = threading.Event()
        ws = FakeWinsound(block=gate)
        with mock.patch.dict(os.environ, SOUND_ON), mock.patch.object(notify, "winsound", ws):
            self.assertTrue(notify.play_chime())              # returns while the "sound card" is still busy
            self.assertFalse(ws.done.is_set())                # (the chime is still "playing" on its thread)
            gate.set()
            self.assertTrue(ws.done.wait(5))
        sound, flags = ws.calls[0]
        self.assertEqual(sound, notify.chime_wav())
        self.assertTrue(flags & ws.SND_MEMORY)
        self.assertFalse(flags & ws.SND_ASYNC)                # (winsound refuses a memory image with SND_ASYNC)

    def test_the_system_sound_when_windows_refuses_the_image(self):
        ws = FakeWinsound(fail_memory=True)
        with mock.patch.dict(os.environ, SOUND_ON), mock.patch.object(notify, "winsound", ws):
            notify._play_now(notify.chime_wav())
        self.assertEqual(len(ws.calls), 2)
        self.assertEqual(ws.calls[1][0], "SystemAsterisk")
        self.assertTrue(ws.calls[1][1] & ws.SND_ALIAS and ws.calls[1][1] & ws.SND_ASYNC)

    def test_no_sound_card_is_no_error(self):
        ws = FakeWinsound()
        ws.PlaySound = mock.Mock(side_effect=RuntimeError("no device"))
        with mock.patch.dict(os.environ, SOUND_ON), mock.patch.object(notify, "winsound", ws):
            notify._play_now(notify.chime_wav())               # (both tries fail: nothing is raised)
        self.assertEqual(ws.PlaySound.call_count, 2)

    def test_t5_notify_0_is_silent(self):
        ws = FakeWinsound()
        with mock.patch.dict(os.environ, {"T5_NOTIFY": "0"}), mock.patch.object(notify, "winsound", ws):
            self.assertFalse(notify.play_chime())
        self.assertEqual(ws.calls, [])

    def test_without_winsound(self):
        with mock.patch.dict(os.environ, SOUND_ON), mock.patch.object(notify, "winsound", None):
            self.assertFalse(notify.play_chime())


class FlashTests(unittest.TestCase):
    def fake_user32(self):
        seen = []

        def flash_window_ex(ref):
            info = ref._obj                                   # (the struct behind ctypes.byref)
            seen.append((info.cbSize, info.hwnd, info.dwFlags, info.uCount, info.dwTimeout))
            return 0
        return SimpleNamespace(FlashWindowEx=flash_window_ex), seen

    @unittest.skipUnless(os.name == "nt", "FlashWindowEx is Windows only")
    def test_taskbar_button_until_the_window_is_in_front(self):
        user32, seen = self.fake_user32()
        with mock.patch.dict(os.environ, SOUND_ON), mock.patch.object(notify.ctypes, "WinDLL", lambda name: user32):
            self.assertTrue(notify.flash_window(0x1234))
            self.assertTrue(notify.flash_window(0x1234, notify.FLASHW_STOP))
        (size, hwnd, flags, count, timeout), stop = seen
        self.assertEqual(size, ctypes.sizeof(notify.FLASHWINFO))
        self.assertEqual(hwnd, 0x1234)
        self.assertEqual(flags, 0x2 | 0xC)                    # FLASHW_TRAY | FLASHW_TIMERNOFG
        self.assertGreater(count, 0)
        self.assertEqual(stop[2], 0)                          # FLASHW_STOP

    def test_the_struct_is_the_win32_one(self):
        # UINT cbSize; HWND hwnd; DWORD dwFlags; UINT uCount; DWORD dwTimeout
        self.assertEqual(ctypes.sizeof(notify.FLASHWINFO), 32 if ctypes.sizeof(ctypes.c_void_p) == 8 else 20)

    def test_nothing_without_a_window_or_when_off(self):
        user32, seen = self.fake_user32()
        with mock.patch.dict(os.environ, SOUND_ON), mock.patch.object(notify.ctypes, "WinDLL", lambda name: user32):
            self.assertFalse(notify.flash_window(0))
            self.assertFalse(notify.flash_window(None))
        with mock.patch.dict(os.environ, {"T5_NOTIFY": "0"}), mock.patch.object(notify.ctypes, "WinDLL",
                                                                                 lambda name: user32):
            self.assertFalse(notify.flash_window(0x1234))
        self.assertEqual(seen, [])


class Hooks:
    """A fake player and a fake flash, a clock the test moves."""

    def __init__(self, **kw):
        self.played, self.flashed, self.logged = [], [], []
        self.now = 1000.0
        self.on, self.away = True, True
        self.notifier = notify.Notifier(enabled=lambda: self.on, away=lambda: self.away,
                                        play=lambda: self.played.append(self.now),
                                        flash=lambda: self.flashed.append(self.now), log=self.logged.append,
                                        clock=lambda: self.now, **kw)

    def wait(self, seconds):
        self.now += seconds


class NotifierTests(unittest.TestCase):
    def test_a_sound_and_a_flash(self):
        h = Hooks()
        self.assertTrue(h.notifier.notify(notify.MATCH, "m1"))
        self.assertEqual((len(h.played), len(h.flashed)), (1, 1))
        self.assertEqual(h.logged, ["notify: match"])

    def test_every_kind_has_its_own_event(self):
        h = Hooks()
        for kind, key in ((notify.MATCH, "m1"), (notify.INVITE, 7), (notify.TOUR, ("t", "s")),
                          (notify.REMATCH, "m1"), (notify.JOIN, None), (notify.TURN, None)):
            h.wait(10)
            self.assertTrue(h.notifier.notify(kind, key), kind)
        self.assertEqual(len(h.played), 6)
        self.assertEqual(len(h.flashed), 6)

    def test_once_per_event(self):
        h = Hooks()
        self.assertTrue(h.notifier.notify(notify.MATCH, "m1"))
        for _ in range(5):
            h.wait(10)
            self.assertFalse(h.notifier.notify(notify.MATCH, "m1"))           # the same match again: nothing
        self.assertEqual(len(h.played), 1)
        h.wait(10)
        self.assertTrue(h.notifier.notify(notify.MATCH, "m2"))                # another match: yes
        h.wait(10)
        self.assertTrue(h.notifier.notify(notify.REMATCH, "m2"))              # the same id, another kind: yes
        self.assertEqual(len(h.played), 3)

    def test_an_event_that_found_the_player_in_front_is_not_told_later(self):
        h = Hooks()
        h.away = False
        self.assertFalse(h.notifier.notify(notify.INVITE, 5))
        h.away = True                                         # alt-tabbed a moment after: it is not news any more
        h.wait(10)
        self.assertFalse(h.notifier.notify(notify.INVITE, 5))
        self.assertEqual((h.played, h.flashed), ([], []))

    def test_not_when_the_player_looks(self):
        h = Hooks()
        h.away = False
        self.assertFalse(h.notifier.notify(notify.MATCH, "m1"))
        self.assertEqual((h.played, h.flashed), ([], []))

    def test_not_when_off_in_settings(self):
        h = Hooks()
        h.on = False
        self.assertFalse(h.notifier.notify(notify.MATCH, "m1"))
        self.assertEqual((h.played, h.flashed), ([], []))
        h.on = True                                           # switched on again: the next event counts
        self.assertTrue(h.notifier.notify(notify.MATCH, "m2"))

    def test_events_close_together_make_one_chime(self):
        h = Hooks()
        self.assertTrue(h.notifier.notify(notify.JOIN))                       # someone joined the room ...
        h.wait(notify.COALESCE_S - 0.5)
        self.assertFalse(h.notifier.notify(notify.MATCH, "m1"))              # ... and the match it starts
        self.assertEqual(len(h.played), 1)
        h.wait(1.0)                                           # (the window runs from the chime, not from the last event)
        self.assertTrue(h.notifier.notify(notify.MATCH, "m2"))
        self.assertEqual(len(h.played), 2)

    def test_a_failing_hook_does_not_break_the_rest(self):
        h = Hooks()

        def boom():
            raise OSError("no sound card")
        h.notifier.play = boom
        self.assertTrue(h.notifier.notify(notify.MATCH, "m1"))
        self.assertEqual(len(h.flashed), 1)                   # the flash still went out
        h.notifier.flash = boom
        h.notifier.log = boom
        h.wait(10)
        self.assertTrue(h.notifier.notify(notify.MATCH, "m2"))

    def test_a_broken_window_is_no_error(self):
        h = Hooks()

        def gone():
            raise RuntimeError("the window is gone")
        h.notifier.away = gone
        self.assertFalse(h.notifier.notify(notify.MATCH, "m1"))
        h.notifier.enabled = gone
        self.assertFalse(h.notifier.notify(notify.MATCH, "m2"))

    def test_whatever_the_server_calls_an_event(self):
        h = Hooks()
        for key in ([1, 2], {"a": 1}, None, 3.5, "x" * 5000):
            h.wait(10)
            h.notifier.notify(notify.INVITE, key)             # (a list is not hashable; the server may send one)
        self.assertEqual(len(h.played), 5)

    def test_it_does_not_remember_without_end(self):
        h = Hooks()
        for i in range(notify.SEEN_MAX * 3):
            h.wait(10)
            h.notifier.notify(notify.MATCH, f"m{i}")
        self.assertLessEqual(len(h.notifier._seen), notify.SEEN_MAX)


def room(rid="r1", owner=1, members=((1, "Me"),), nxt=None):
    return {"id": rid, "owner_id": owner, "players": [{"id": i, "name": n} for i, n in members], "next": nxt}


class RoomWatchTests(unittest.TestCase):
    def test_the_first_message_of_a_room_is_the_baseline(self):
        w = notify.RoomWatch()
        self.assertEqual(w.update(room(members=((1, "Me"), (2, "Amy"))), 1), [])      # Amy was there when I looked

    def test_someone_joins_the_room_i_host(self):
        w = notify.RoomWatch()
        self.assertEqual(w.update(room(), 1), [])
        self.assertEqual(w.update(room(members=((1, "Me"), (2, "Amy"))), 1), [(notify.JOIN, "Amy")])
        self.assertEqual(w.update(room(members=((1, "Me"), (2, "Amy"))), 1), [])      # the same news twice: once
        two = w.update(room(members=((1, "Me"), (2, "Amy"), (3, "Ben"), (4, "Cy"))), 1)
        self.assertEqual(two, [(notify.JOIN, "Ben"), (notify.JOIN, "Cy")])
        w.update(room(members=((1, "Me"), (3, "Ben"), (4, "Cy"))), 1)                  # Amy left ...
        self.assertEqual(w.update(room(members=((1, "Me"), (2, "Amy"), (3, "Ben"), (4, "Cy"))), 1),
                         [(notify.JOIN, "Amy")])                                       # ... and came back: news again

    def test_a_visitor_is_told_nothing_of_joins(self):
        w = notify.RoomWatch()
        w.update(room(owner=9, members=((9, "Host"), (1, "Me"))), 1)
        self.assertEqual(w.update(room(owner=9, members=((9, "Host"), (1, "Me"), (2, "Amy"))), 1), [])

    def test_my_turn(self):
        w = notify.RoomWatch()
        w.update(room(owner=9, members=((9, "Host"), (1, "Me"), (2, "Amy"))), 1)
        soon = {"at": 5.0, "players": [1, 2]}
        self.assertEqual(w.update(room(owner=9, members=((9, "Host"), (1, "Me"), (2, "Amy")), nxt=soon), 1),
                         [(notify.TURN, None)])
        again = {"at": 6.0, "players": [2, 1]}                                         # the countdown is moved: same turn
        self.assertEqual(w.update(room(owner=9, members=((9, "Host"), (1, "Me"), (2, "Amy")), nxt=again), 1), [])
        self.assertEqual(w.update(room(owner=9, members=((9, "Host"), (1, "Me"), (2, "Amy"))), 1), [])   # my match runs
        self.assertEqual(w.update(room(owner=9, members=((9, "Host"), (1, "Me"), (2, "Amy")), nxt=soon), 1),
                         [(notify.TURN, None)])                                       # the next turn is news again

    def test_somebody_elses_turn_is_not_mine(self):
        w = notify.RoomWatch()
        w.update(room(owner=9, members=((9, "Host"), (1, "Me"), (2, "Amy"))), 1)
        self.assertEqual(w.update(room(owner=9, members=((9, "Host"), (1, "Me"), (2, "Amy")),
                                       nxt={"at": 5.0, "players": [9, 2]}), 1), [])

    def test_the_turn_can_be_in_the_first_message(self):
        w = notify.RoomWatch()
        self.assertEqual(w.update(room(owner=9, members=((9, "Host"), (1, "Me")), nxt={"at": 5, "players": [9, 1]}), 1),
                         [(notify.TURN, None)])

    def test_the_host_who_is_joined_gets_the_join_and_the_turn_together(self):
        w = notify.RoomWatch()
        w.update(room(), 1)
        news = w.update(room(members=((1, "Me"), (2, "Amy")), nxt={"at": 5.0, "players": [1, 2]}), 1)
        self.assertEqual(news, [(notify.JOIN, "Amy"), (notify.TURN, None)])

    def test_another_room_starts_again_and_reset_forgets(self):
        w = notify.RoomWatch()
        w.update(room("r1"), 1)
        self.assertEqual(w.update(room("r2", members=((1, "Me"), (2, "Amy"))), 1), [])      # a new room: baseline
        w.reset()
        self.assertEqual(w.update(room("r2", members=((1, "Me"), (2, "Amy"), (3, "Ben"))), 1), [])

    def test_garbage(self):
        w = notify.RoomWatch()
        for bad in (None, "room", 5, [], {}):
            self.assertEqual(w.update(bad, 1), [])
        self.assertEqual(w.update(room(), None), [])
        self.assertEqual(w.update({"id": "r", "owner_id": 1, "players": "x", "next": "soon"}, 1), [])
        self.assertEqual(w.update({"id": "r", "owner_id": 1, "players": [None, 5, {"id": 1}], "next": {"players": 3}}, 1),
                         [])


@unittest.skipIf(tk is None, "no tkinter")
class SettingsTests(unittest.TestCase):
    """The Settings tab: the checkbox is there, on by default, and saves "notify" in launcher.json."""
    TEXT = "Sound and taskbar flash when a match is found, I am challenged or invited, or someone joins my room"

    def checkbuttons(self, w):
        out = [w] if w.winfo_class() == "TCheckbutton" else []
        for c in w.winfo_children():
            out += self.checkbuttons(c)
        return out

    def test_the_checkbox(self):
        import i18n_layout
        found = {}

        def look(walk):
            app = walk.app
            box = [c for c in self.checkbuttons(app.settings_scroll.inner) if str(c.cget("text")) == self.TEXT]
            found["count"] = len(box)
            found["default"] = (app.notify_var.get(), app.settings["notify"])
            box[0].invoke()                                   # off
            found["off"] = (app.notify_var.get(), app.settings["notify"])
            with open(app.settings.path, encoding="utf-8") as f:
                found["file_off"] = json.load(f).get("notify")
            box[0].invoke()                                   # on again
            found["on"] = app.settings["notify"]

        walk = i18n_layout.Walk("en", 100)
        with mock.patch.object(i18n_layout.Walk, "_launcher", look), \
                mock.patch.object(i18n_layout.Walk, "_online", lambda w: None), \
                mock.patch.object(i18n_layout.Walk, "_windows", lambda w, dd: None):
            try:
                walk.run()
            except tk.TclError as e:
                self.skipTest(f"no display for Tk: {e}")
        self.assertEqual(walk.shown, [])
        self.assertEqual(found["count"], 1)
        self.assertEqual(found["default"], (True, True))
        self.assertEqual(found["off"], (False, False))
        self.assertIs(found["file_off"], False)
        self.assertIs(found["on"], True)

    def test_the_default_and_the_text_in_every_language(self):
        import core
        from t5lobby import i18n
        self.assertIs(core.DEFAULTS["notify"], True)
        for lang in ("de", "es", "fr", "ja", "ko", "pt-BR"):
            self.assertNotEqual(i18n.catalog(lang).get(self.TEXT, self.TEXT), self.TEXT, lang)


if __name__ == "__main__":
    unittest.main()
