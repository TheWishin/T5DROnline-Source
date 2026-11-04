"""Settings "Sound when a match is found" (launcher.json "notify_sound"; t5lobby/notify.py "the sound for a found
match"): the announcer, the beep, the player's own WAV file (checked, copied next to launcher.json) or nothing, for
a found match; challenges and invites have an independent setting. Made-up WAV files only; nothing is played on this PC (fake
winsound), nothing is written outside a temporary folder."""
import io
import os
import shutil
import struct
import sys
import tempfile
import types
import unittest
import wave
from unittest import mock

import util  # noqa: F401  (sets sys.path)
from t5lobby import announcer as A
from t5lobby import notify
from test_announcer import FakeWinsound, adpcm_encode, bank, fake_install, tone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core  # noqa: E402


def make_wav(seconds=1.0, rate=22050, channels=1, width=2, frames=None):
    n = int(round(seconds * rate)) if frames is None else frames
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes((i * 7) & 0xFF for i in range(n * channels * width)))
    return out.getvalue()


class CheckWavTests(unittest.TestCase):
    def test_plain_pcm_short_files_pass(self):
        for args in (dict(), dict(rate=8000, width=1), dict(rate=48000, channels=2), dict(rate=44100, width=3),
                     dict(seconds=notify.CUSTOM_MAX_S, rate=44100)):
            self.assertIsNone(notify.check_wav(make_wav(**args)), args)
        self.assertIsNone(notify.check_wav(notify.chime_wav()))

    def test_longer_than_five_seconds(self):
        self.assertEqual(notify.check_wav(make_wav(frames=int(notify.CUSTOM_MAX_S * 8000) + 1, rate=8000, width=1)),
                         notify.WAV_TOO_LONG)
        self.assertEqual(notify.check_wav(make_wav(seconds=6, rate=11025)), notify.WAV_TOO_LONG)

    def test_larger_than_two_mb(self):
        data = make_wav(seconds=2, rate=192000, channels=2, width=4)          # 3 MB, 2 s
        self.assertGreater(len(data), notify.CUSTOM_MAX_BYTES)
        self.assertEqual(notify.check_wav(data), notify.WAV_TOO_BIG)

    def test_not_a_wav_the_launcher_plays(self):
        good = make_wav()
        cut = good[:len(good) // 2]                                              # header promises more than there is
        adpcm = bytearray(good)
        adpcm[20:22] = struct.pack("<H", 2)                                       # MS ADPCM, not PCM
        for data in (b"", b"RIFF", b"ID3\x03" + bytes(100), b"OggS" + bytes(100), cut, bytes(adpcm),
                     make_wav(frames=0), make_wav(rate=4000), make_wav(channels=3), good.replace(b"WAVE", b"AVI ", 1)):
            self.assertEqual(notify.check_wav(data), notify.WAV_NOT_WAV, data[:16])


class CustomFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t5matchsound")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.folder = os.path.join(self.dir, "launcher folder ü 日本")

    def src(self, data, name="my sound.wav"):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_a_good_file_is_copied_byte_for_byte(self):
        data = make_wav(seconds=2)
        self.assertIsNone(notify.install_custom_wav(self.src(data), self.folder))
        with open(os.path.join(self.folder, notify.CUSTOM_WAV_NAME), "rb") as f:
            self.assertEqual(f.read(), data)
        self.assertEqual(notify.custom_wav(self.folder), (data, None))
        self.assertEqual(sorted(os.listdir(self.folder)), [notify.CUSTOM_WAV_NAME])     # no temporary file left

    def test_a_refused_file_keeps_the_copy_before(self):
        first = make_wav(seconds=1)
        self.assertIsNone(notify.install_custom_wav(self.src(first), self.folder))
        self.assertEqual(notify.install_custom_wav(self.src(make_wav(seconds=7), "long.wav"), self.folder),
                         notify.WAV_TOO_LONG)
        self.assertEqual(notify.install_custom_wav(self.src(b"not a sound", "x.wav"), self.folder), notify.WAV_NOT_WAV)
        self.assertEqual(notify.custom_wav(self.folder), (first, None))

    def test_too_big_is_refused_by_its_size(self):
        path = self.src(b"RIFF" + bytes(notify.CUSTOM_MAX_BYTES + 10))
        with mock.patch("builtins.open", side_effect=AssertionError("read")):
            self.assertEqual(notify.install_custom_wav(path, self.folder), notify.WAV_TOO_BIG)
        self.assertFalse(os.path.exists(self.folder))

    def test_unreadable_source(self):
        self.assertEqual(notify.install_custom_wav(os.path.join(self.dir, "gone.wav"), self.folder),
                         notify.WAV_UNREADABLE)

    def test_gone_or_replaced_later(self):
        self.assertEqual(notify.custom_wav(self.folder), (None, notify.WAV_MISSING))
        self.assertEqual(notify.custom_wav(None), (None, notify.WAV_MISSING))
        os.makedirs(self.folder)
        with open(os.path.join(self.folder, notify.CUSTOM_WAV_NAME), "wb") as f:
            f.write(make_wav(seconds=9, rate=8000))                              # somebody put another file there
        self.assertEqual(notify.custom_wav(self.folder), (None, notify.WAV_TOO_LONG))


class ChoiceTests(unittest.TestCase):
    def test_choice_from_the_settings(self):
        c = notify.match_sound_choice
        self.assertEqual(c({}), notify.ANNOUNCER)
        for key in notify.MATCH_SOUNDS:
            self.assertEqual(c({"notify_sound": key}), key)
        self.assertEqual(c({"notify_sound": "loud"}), notify.ANNOUNCER)
        self.assertEqual(c({"notify_voice": False}), notify.BEEP)              # a 1.2.0 test build, box unticked
        self.assertEqual(c({"notify_voice": False, "notify_sound": "custom"}), notify.CUSTOM)
        self.assertEqual(c(None), notify.ANNOUNCER)

    def test_launcher_settings(self):
        self.assertEqual(list(core.MATCH_SOUNDS), list(notify.MATCH_SOUNDS))
        self.assertEqual(set(core.MATCH_SOUND_PROBLEMS), {notify.WAV_NOT_WAV, notify.WAV_TOO_LONG, notify.WAV_TOO_BIG,
                                                         notify.WAV_UNREADABLE, notify.WAV_MISSING})
        d = tempfile.mkdtemp(prefix="t5matchsound")
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "launcher.json")
        cases = (({}, "announcer", True), ({"notify_voice": False}, "beep", False),
                 ({"notify_voice": True}, "announcer", True), ({"notify_sound": "off", "notify_voice": True}, "off", False),
                 ({"notify_sound": "custom"}, "custom", False), ({"notify_sound": 3}, "announcer", True))
        for saved, choice, voice in cases:
            with open(path, "w", encoding="utf-8") as f:
                import json
                json.dump(dict(saved, settings_version=core.SETTINGS_VERSION), f)
            s = core.Settings(path)
            self.assertEqual((s["notify_sound"], s["notify_voice"]), (choice, voice), saved)
            self.assertEqual(s.settings_dir, d)
        s["notify_sound"] = "beep"
        s.save()                                                                # an older launcher reads notify_voice
        with open(path, encoding="utf-8") as f:
            import json
            back = json.load(f)
        self.assertEqual((back["notify_sound"], back["notify_voice"]), ("beep", False))

    def test_texts_in_every_language(self):
        from t5lobby import i18n
        texts = list(core.MATCH_SOUNDS.values()) + list(core.MATCH_SOUND_PROBLEMS.values()) + [
            core.MATCH_SOUND_HELP, "Sound when a match is found:", "{problem} The beep is used instead."]
        for lang in ("de", "es", "fr", "ja", "ko", "pt-BR"):
            cat = i18n.catalog(lang)
            for text in texts:
                self.assertIn(text, cat, (lang, text))


class WhatRingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t5matchsound")
        self.addCleanup(shutil.rmtree, self.dir, True)
        A._cached.cache_clear()
        self.addCleanup(A._cached.cache_clear)

    def test_challenge_custom_playback_uses_its_own_copy_and_fallback(self):
        match = make_wav(seconds=0.2)
        challenge = make_wav(seconds=0.4)
        for name, data in ((notify.CUSTOM_WAV_NAME, match), (notify.CHALLENGE_WAV_NAME, challenge)):
            with open(os.path.join(self.dir, name), "wb") as f:
                f.write(data)
        self.assertEqual(notify.match_sound_wav(notify.CUSTOM, folder=self.dir), (match, ""))
        self.assertEqual(notify.match_sound_wav(notify.CUSTOM, folder=self.dir, challenge=True), (challenge, ""))
        os.remove(os.path.join(self.dir, notify.CHALLENGE_WAV_NAME))
        self.assertEqual(notify.match_sound_wav(notify.CUSTOM, folder=self.dir, challenge=True),
                         (notify.chime_wav(), notify.WAV_MISSING))
        self.assertEqual(notify.match_sound_wav(notify.CUSTOM, folder=self.dir), (match, ""))

    def test_each_choice(self):
        self.assertEqual(notify.match_sound_wav(notify.OFF, self.dir, self.dir), (None, ""))
        self.assertEqual(notify.match_sound_wav(notify.BEEP, self.dir, self.dir), (notify.chime_wav(), ""))
        self.assertEqual(notify.match_sound_wav(notify.ANNOUNCER, self.dir, self.dir), (notify.chime_wav(), "no_game"))
        self.assertEqual(notify.match_sound_wav(notify.CUSTOM, self.dir, self.dir),
                         (notify.chime_wav(), notify.WAV_MISSING))
        mine = make_wav(seconds=0.5)
        with open(os.path.join(self.dir, notify.CUSTOM_WAV_NAME), "wb") as f:
            f.write(mine)
        self.assertEqual(notify.match_sound_wav(notify.CUSTOM, self.dir, self.dir), (mine, ""))

    def test_the_announcer_from_the_game(self):
        import hashlib
        line = adpcm_encode(tone())
        fake_install(self.dir, bank({A.SAMPLE: line}))
        with mock.patch.multiple(A, SAMPLE_SIZE=len(line), SAMPLE_SHA256=hashlib.sha256(line).hexdigest()):
            wav, note = notify.match_sound_wav(notify.ANNOUNCER, self.dir, self.dir)
        self.assertEqual(note, "")
        self.assertNotEqual(wav, notify.chime_wav())
        self.assertIsNone(notify.check_wav(wav))

    def test_the_right_sample_for_each_event_and_a_wrong_hash_chimes(self):
        from t5lobby import tk_tab
        import hashlib
        battle = adpcm_encode(tone(280, 440))
        challenger = adpcm_encode(tone(560, 660))
        fake_install(self.dir, bank({A.SAMPLE: battle, A.NEW_CHALLENGER_SAMPLE: challenger}))
        settings = types.SimpleNamespace(get=lambda key, default=None: default,
                                         path=os.path.join(self.dir, "launcher.json"), out_dir=self.dir)
        tab = types.SimpleNamespace(app=types.SimpleNamespace(settings=settings))
        pins = dict(SAMPLE_SIZE=len(battle), SAMPLE_SHA256=hashlib.sha256(battle).hexdigest(),
                    NEW_CHALLENGER_SIZE=len(challenger),
                    NEW_CHALLENGER_SHA256=hashlib.sha256(challenger).hexdigest())
        for wrong_hash in (False, True):
            with self.subTest(wrong_challenger_hash=wrong_hash):
                A._cached.cache_clear()
                expected_battle = A.wav_bytes(A.adpcm_decode(battle), A.SAMPLE_RATE)
                expected_challenger = (notify.chime_wav() if wrong_hash else
                                       A.wav_bytes(A.adpcm_decode(challenger), A.NEW_CHALLENGER_RATE))
                patched_pins = dict(pins)
                if wrong_hash:
                    patched_pins["NEW_CHALLENGER_SHA256"] = "0" * 64
                for kind, expected in ((notify.MATCH, expected_battle), (notify.TOUR, expected_battle),
                                       (notify.CHALLENGE, expected_challenger), (notify.INVITE, expected_challenger)):
                    played = []

                    def sound(choice, out_dir, folder, log=None, *, challenge=False):
                        wav, _note = notify.match_sound_wav(choice, out_dir, folder, challenge=challenge)
                        played.append(wav)
                        return True

                    n = notify.Notifier(play=lambda: played.append(notify.chime_wav()),
                                        voice=lambda: tk_tab.OnlineTab._notify_voice(tab),
                                        challenge=lambda: tk_tab.OnlineTab._notify_challenge(tab))
                    with mock.patch.multiple(A, **patched_pins), mock.patch.object(notify, "play_match_sound", sound):
                        self.assertTrue(n.notify(kind, "event"))
                    self.assertEqual(played, [expected], kind)


@unittest.skipUnless(os.name == "nt", "the sound is Windows only")
class PlayTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t5matchsound")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.logged = []

    def play(self, choice):
        ws = FakeWinsound()
        with mock.patch.dict(os.environ, {"T5_NOTIFY": "1"}), mock.patch.object(notify, "winsound", ws):
            self.assertTrue(notify.play_match_sound(choice, self.dir, self.dir, log=self.logged.append))
            self.assertTrue(ws.done.wait(10))
        return ws.calls[0][0]

    def test_my_own_sound(self):
        mine = make_wav(seconds=0.3)
        with open(os.path.join(self.dir, notify.CUSTOM_WAV_NAME), "wb") as f:
            f.write(mine)
        self.assertEqual(self.play(notify.CUSTOM), mine)
        self.assertEqual(self.logged, [])

    def test_a_broken_own_sound_rings_the_beep_and_says_so(self):
        with open(os.path.join(self.dir, notify.CUSTOM_WAV_NAME), "wb") as f:
            f.write(b"RIFF....WAVEjunk")
        self.assertEqual(self.play(notify.CUSTOM), notify.chime_wav())
        self.assertEqual(len(self.logged), 1)
        self.assertIn("not_wav", self.logged[0])

    def test_beep_and_announcer_without_the_game(self):
        self.assertEqual(self.play(notify.BEEP), notify.chime_wav())
        self.assertEqual(self.play(notify.ANNOUNCER), notify.chime_wav())
        self.assertEqual(self.logged, [])

    def test_off_is_handled_and_silent(self):
        ws = FakeWinsound()
        with mock.patch.dict(os.environ, {"T5_NOTIFY": "1"}), mock.patch.object(notify, "winsound", ws):
            self.assertTrue(notify.play_match_sound(notify.OFF, self.dir, self.dir))
            self.assertFalse(ws.done.wait(0.3))
        self.assertEqual(ws.calls, [])

    def test_silent_with_t5_notify_0(self):
        ws = FakeWinsound()
        with mock.patch.dict(os.environ, {"T5_NOTIFY": "0"}), mock.patch.object(notify, "winsound", ws):
            self.assertFalse(notify.play_match_sound(notify.BEEP, self.dir, self.dir))
            self.assertEqual(notify.preview_match_sound(notify.CUSTOM, self.dir, self.dir), notify.WAV_MISSING)
        self.assertEqual(ws.calls, [])

    def test_preview_plays_and_tells_why_the_beep_stands_in(self):
        ws = FakeWinsound()
        with mock.patch.dict(os.environ, {"T5_NOTIFY": "1"}), mock.patch.object(notify, "winsound", ws):
            self.assertEqual(notify.preview_match_sound(notify.ANNOUNCER, self.dir, self.dir), "no_game")
            self.assertTrue(ws.done.wait(10))
        self.assertEqual(ws.calls[0][0], notify.chime_wav())

    def test_challenge_preview_uses_new_challenger_and_its_fallback(self):
        line = make_wav(seconds=0.2)
        for wav, note in ((line, ""), (None, "no_game")):
            with self.subTest(available=wav is not None):
                ws = FakeWinsound()
                with mock.patch.dict(os.environ, {"T5_NOTIFY": "1"}), mock.patch.object(notify, "winsound", ws), \
                        mock.patch.object(A, "new_challenger_wav", return_value=wav) as challenger, \
                        mock.patch.object(A, "next_battle_wav") as battle:
                    self.assertEqual(notify.preview_match_sound(notify.ANNOUNCER, self.dir, self.dir, challenge=True),
                                     note)
                    self.assertTrue(ws.done.wait(10))
                challenger.assert_called_once_with(self.dir)
                battle.assert_not_called()
                self.assertEqual(ws.calls[0][0], wav or notify.chime_wav())


class NotifierTests(unittest.TestCase):
    """The Online tab's hook (tk_tab.OnlineTab._notify_voice) with the setting: Off rings nothing but still flashes,
    Beep is the chime, the rest go to play_match_sound with the launcher's folder."""

    def tab(self, choice, folder):
        settings = types.SimpleNamespace(get=lambda k, d=None: {"notify_sound": choice}.get(k, d),
                                         path=os.path.join(folder, "launcher.json"), out_dir=os.path.join(folder, "out"))
        return types.SimpleNamespace(app=types.SimpleNamespace(settings=settings))

    def test_the_tabs_hook(self):
        from t5lobby import tk_tab
        folder = tempfile.mkdtemp(prefix="t5matchsound")
        self.addCleanup(shutil.rmtree, folder, True)
        for choice in notify.MATCH_SOUNDS:
            played, flashed, calls = [], [], []

            def fake_play(c, out_dir, f, log=None):
                calls.append((c, out_dir, f))
                return True
            tab = self.tab(choice, folder)
            n = notify.Notifier(enabled=lambda: True, away=lambda: True, play=lambda: played.append(1),
                                flash=lambda: flashed.append(1), clock=lambda: 1.0,
                                voice=lambda: tk_tab.OnlineTab._notify_voice(tab))
            with mock.patch.object(notify, "play_match_sound", fake_play):
                self.assertTrue(n.notify(notify.MATCH, "m1"))
            self.assertEqual(flashed, [1], choice)
            if choice == notify.BEEP:
                self.assertEqual((played, calls), ([1], []))
            else:
                self.assertEqual(played, [], choice)
                self.assertEqual(calls, [(choice, os.path.join(folder, "out"), os.path.abspath(folder))])

    def test_other_notifications_keep_the_chime(self):
        played, voiced = [], []
        n = notify.Notifier(enabled=lambda: True, away=lambda: True, play=lambda: played.append(1),
                            flash=lambda: None, clock=lambda: 1.0, voice=lambda: voiced.append(1) or True)
        n.notify(notify.JOIN, "j")
        self.assertEqual((played, voiced), ([1], []))

    def test_event_to_sound_with_independent_settings(self):
        from t5lobby import tk_tab
        for match_choice in notify.MATCH_SOUNDS:
            for challenge_choice in (None,) + notify.CHALLENGE_SOUNDS:
                settings = core.Settings(os.path.join(ROOT, "build", "unused-sound-test.json"))
                settings["notify_sound"] = match_choice
                if challenge_choice is None:
                    settings.pop("notify_challenge_sound")
                else:
                    settings["notify_challenge_sound"] = challenge_choice
                tab = types.SimpleNamespace(app=types.SimpleNamespace(settings=settings))
                for kind in (notify.MATCH, notify.CHALLENGE, notify.INVITE, notify.TOUR, notify.JOIN,
                             notify.TURN, notify.REMATCH, "mention"):
                    with self.subTest(match=match_choice, challenge=challenge_choice, kind=kind):
                        played, flashed = [], []
                        n = notify.Notifier(play=lambda: played.append("chime"),
                                            flash=lambda: flashed.append(1), clock=lambda: 1.0,
                                            voice=lambda: tk_tab.OnlineTab._notify_voice(tab),
                                            challenge=lambda: tk_tab.OnlineTab._notify_challenge(tab))
                        with mock.patch.object(notify, "play_match_sound", return_value=True) as sound:
                            self.assertTrue(n.notify(kind, "event"))
                        choice = (match_choice if kind in (notify.MATCH, notify.TOUR) else
                                  (challenge_choice or notify.ANNOUNCER) if kind in notify.CHALLENGE_KINDS else notify.CHIME)
                        self.assertEqual(flashed, [1])
                        if choice in (notify.CHIME, notify.BEEP):
                            self.assertEqual(played, ["chime"])
                            sound.assert_not_called()
                        else:
                            self.assertEqual(played, [])
                            self.assertEqual(sound.call_args.args[0], choice)
                            self.assertEqual(sound.call_args.kwargs.get("challenge", False), kind in notify.CHALLENGE_KINDS)

    def test_failed_challenge_hook_falls_back_to_chime(self):
        for hook in (lambda: False, mock.Mock(side_effect=OSError("no sound"))):
            for kind in notify.CHALLENGE_KINDS:
                played = []
                n = notify.Notifier(play=lambda: played.append(1), challenge=hook)
                self.assertTrue(n.notify(kind, "c"))
                self.assertEqual(played, [1])


class ChallengeSettingsTests(unittest.TestCase):
    def test_default_validation_and_round_trip(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "launcher.json")
            for value in (None, "wrong", [], {}, 3, *notify.CHALLENGE_SOUNDS):
                saved = {"notify_sound": "off", "notify_voice": False, "notify_challenge_sound": value,
                         "notify_challenge_sound_name": 123, "settings_version": core.SETTINGS_VERSION}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(saved, f)
                settings = core.Settings(path)
                expected = value if value in notify.CHALLENGE_SOUNDS else notify.ANNOUNCER
                self.assertEqual(settings["notify_challenge_sound"], expected)
                self.assertEqual(notify.challenge_sound_choice(saved), expected)
                self.assertEqual(settings["notify_challenge_sound_name"], "")
                settings.save()
                loaded = core.Settings(path)
                self.assertEqual(loaded["notify_challenge_sound"], expected)
                self.assertEqual(loaded["notify_sound"], "off")
            self.assertEqual(notify.challenge_sound_choice({"notify_sound": "off", "notify_voice": False}),
                             notify.ANNOUNCER)
            self.assertEqual(notify.challenge_sound_choice(None), notify.ANNOUNCER)
            self.assertEqual(list(core.CHALLENGE_SOUNDS), list(notify.CHALLENGE_SOUNDS))

    def test_new_texts_in_every_language(self):
        from t5lobby import i18n
        texts = list(core.CHALLENGE_SOUNDS.values()) + [core.CHALLENGE_SOUND_HELP, "Sound for a challenge:",
                "EU edition", "US edition", "{problem} The chime is used instead.",
                "The announcer needs your built game (BUILD GAME): until then the chime plays."]
        for lang in i18n.CATALOGS:
            for text in texts:
                self.assertIn(text, i18n.catalog(lang), (lang, text))


if __name__ == "__main__":
    unittest.main()
