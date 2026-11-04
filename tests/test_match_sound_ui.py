"""Settings "Sound when a match is found" in the launcher (t5dr_launcher.App._match_sound_*): the Windows file dialog
(faked), the copy next to launcher.json, a refused file -> the beep and why, Cancel keeps the choice, Play. No Tk
window, no sound, nothing outside a temporary folder."""
import importlib.machinery
import importlib.util
import io
import os
import sys
import tempfile
import types
import unittest
import wave
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
os.environ["T5_NOTIFY"] = "0"
import core  # noqa: E402
from t5lobby import notify  # noqa: E402


def load_launcher():
    loader = importlib.machinery.SourceFileLoader("match_sound_launcher", os.path.join(
        ROOT, "launcher", "t5dr_launcher.pyw"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def make_wav(seconds, rate=8000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(bytes(128 for _ in range(int(seconds * rate))))
    return out.getvalue()


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Widget:
    def __init__(self):
        self.options = {}

    def configure(self, **kw):
        self.options.update(kw)


class MatchSoundUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = load_launcher()

    def setUp(self):
        os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)     # (a fresh checkout, e.g. CI, has no build/)
        self.temp = tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build"))
        self.addCleanup(self.temp.cleanup)
        self.settings = core.Settings(os.path.join(self.temp.name, "settings ü", "launcher.json"))
        self.settings["out"] = os.path.join(self.temp.name, "native")
        self.saved = []
        self.app = types.SimpleNamespace(
            readonly=False, settings=self.settings, match_sound_var=Var(self.settings["notify_sound"]),
            _match_sound_last=self.settings["notify_sound"], match_sound_hint=Widget(), match_sound_play=Widget(),
            save_settings=lambda: self.saved.append(self.app.match_sound_var.get()))
        for name in ("_match_sound_folder", "_match_sound_problem", "_match_sound_status", "_match_sound_set",
                     "_match_sound_changed", "_choose_match_sound", "_preview_match_sound"):
            setattr(self.app, name, types.MethodType(getattr(self.launcher.App, name), self.app))
        log = mock.patch.object(core, "log")
        self.log = log.start()
        self.addCleanup(log.stop)

    def file(self, name, data):
        path = os.path.join(self.temp.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def pick(self, path):
        return mock.patch.object(self.launcher.filedialog, "askopenfilename", return_value=path)

    def copy(self):
        return os.path.join(self.settings.settings_dir, notify.CUSTOM_WAV_NAME)

    def test_choosing_custom_opens_the_dialog_and_copies_the_file(self):
        data = make_wav(1.5)
        self.app.match_sound_var.set("custom")
        with self.pick(self.file("bell 日本.wav", data)) as dialog:
            self.app._match_sound_changed()
        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.kwargs["filetypes"], [("WAV sound", "*.wav")])
        with open(self.copy(), "rb") as f:
            self.assertEqual(f.read(), data)
        self.assertEqual((self.settings["notify_sound"], self.saved[-1]), ("custom", "custom"))
        self.assertEqual(self.settings["notify_sound_name"], "bell 日本.wav")
        self.assertEqual(self.app.match_sound_hint.options["text"], "Your sound: bell 日本.wav")
        self.app.match_sound_var.set("beep")                     # back to custom later: no dialog, the copy is there
        self.app._match_sound_changed()
        self.app.match_sound_var.set("custom")
        with self.pick("") as dialog:
            self.app._match_sound_changed()
        dialog.assert_not_called()
        self.assertEqual(self.settings["notify_sound"], "custom")

    def test_a_refused_file_is_the_beep_and_says_why(self):
        self.app.match_sound_var.set("custom")
        with self.pick(self.file("long.wav", make_wav(6))):
            self.app._match_sound_changed()
        self.assertEqual((self.settings["notify_sound"], self.app.match_sound_var.get()), ("beep", "beep"))
        self.assertEqual(self.app.match_sound_hint.options["text"],
                         "That sound is longer than 5 seconds. The beep is used instead.")
        self.assertFalse(os.path.exists(self.copy()))
        for name, data, why in (("a.mp3", b"ID3" + bytes(64), "not a WAV sound"),
                                ("big.wav", b"RIFF" + bytes(notify.CUSTOM_MAX_BYTES), "larger than 2 MB")):
            with self.pick(self.file(name, data)):
                self.app._choose_match_sound()
            self.assertIn(why, self.app.match_sound_hint.options["text"])
            self.assertEqual(self.settings["notify_sound"], "beep")

    def test_cancel_keeps_the_choice_before(self):
        self.app._match_sound_set("off")
        self.app.match_sound_var.set("custom")
        with self.pick(""):
            self.app._match_sound_changed()
        self.assertEqual((self.settings["notify_sound"], self.app.match_sound_var.get()), ("off", "off"))
        self.assertEqual(self.app.match_sound_play.options["state"], "disabled")

    def test_play_tells_why_the_beep_stands_in(self):
        self.app.match_sound_var.set("announcer")
        with mock.patch.object(notify, "preview_match_sound", return_value="no_game") as preview:
            self.app._preview_match_sound()
        preview.assert_called_once_with("announcer", self.settings.out_dir, self.settings.settings_dir, challenge=False)
        self.assertIn("BUILD GAME", self.app.match_sound_hint.options["text"])
        self.app._match_sound_set("custom")                       # chosen earlier, the file deleted since
        self.app._match_sound_status()
        self.assertEqual(self.app.match_sound_hint.options["text"],
                         "Your WAV file is gone. The beep is used instead.")
        self.assertEqual(self.app.match_sound_play.options["state"], "normal")

    def challenge_controls(self):
        self.app.challenge_sound_var = Var(self.settings["notify_challenge_sound"])
        self.app._challenge_sound_last = self.settings["notify_challenge_sound"]
        self.app.challenge_sound_hint = Widget()
        self.app.challenge_sound_play = Widget()

    def test_challenge_defaults_to_new_challenger_and_previews_separately(self):
        self.challenge_controls()
        self.assertEqual(self.app.challenge_sound_var.get(), "announcer")
        self.assertEqual(list(core.CHALLENGE_SOUNDS.items()), [
            ("announcer", "New challenger (default)"), ("chime", "Chime"),
            ("custom", "Your own WAV file"), ("off", "Off")])
        with mock.patch.object(notify, "preview_match_sound", return_value="no_game") as preview:
            self.app._preview_match_sound(True)
        preview.assert_called_once_with("announcer", self.settings.out_dir, self.settings.settings_dir, challenge=True)
        self.assertEqual(self.app.challenge_sound_hint.options["text"],
                         "The announcer needs your built game (BUILD GAME): until then the chime plays.")
        self.assertEqual(self.app.match_sound_hint.options, {})

    def test_challenge_wav_and_choice_are_saved_separately(self):
        self.challenge_controls()
        match = make_wav(0.2)
        challenge = make_wav(0.4)
        with self.pick(self.file("match.wav", match)):
            self.app._choose_match_sound()
        self.app.challenge_sound_var.set("custom")
        with self.pick(self.file("invite.wav", challenge)):
            self.app._match_sound_changed(True)
        self.settings.save()
        loaded = core.Settings(self.settings.path)
        self.assertEqual((loaded["notify_sound"], loaded["notify_challenge_sound"]), ("custom", "custom"))
        self.assertEqual(loaded["notify_challenge_sound_name"], "invite.wav")
        self.assertEqual(notify.custom_wav(loaded.settings_dir)[0], match)
        self.assertEqual(notify.custom_wav(loaded.settings_dir, challenge=True)[0], challenge)
        with mock.patch.object(notify, "preview_match_sound", return_value="") as preview:
            self.app._preview_match_sound(True)
        preview.assert_called_once_with("custom", loaded.out_dir, loaded.settings_dir, challenge=True)
        self.app._match_sound_set("off", True)
        self.app._match_sound_status(challenge=True)
        self.assertEqual(self.app.challenge_sound_play.options["state"], "disabled")
        self.assertEqual(self.settings["notify_sound"], "custom")

    def test_challenge_cancel_and_invalid_wav(self):
        self.challenge_controls()
        self.app._match_sound_set("off", True)
        self.app.challenge_sound_var.set("custom")
        with self.pick(""):
            self.app._match_sound_changed(True)
        self.assertEqual(self.app.challenge_sound_var.get(), "off")
        with self.pick(self.file("broken.wav", b"not WAV")):
            self.app._choose_match_sound(True)
        self.assertEqual(self.settings["notify_challenge_sound"], "chime")
        self.assertIn("The chime is used instead.", self.app.challenge_sound_hint.options["text"])
        self.assertEqual(self.settings["notify_sound"], "announcer")


if __name__ == "__main__":
    unittest.main()
