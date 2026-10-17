"""tools/audio_device_check.py on synthetic runs: the log lines of the audio
device thread (ps3recomp patch 0026) and the two block-aligned f32 captures
(AUDIO_WAV, PS3_AUDIO_DEVICE_WAV). The real thing needs the game; see
docs/SMOKE.md, "Audio device"."""
import array
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

from helpers import ROOT

spec = importlib.util.spec_from_file_location("audio_device_check", os.path.join(ROOT, "tools", "audio_device_check.py"))
adc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adc)

BLOCK_S = adc.BLOCK / adc.RATE
FLOATS = adc.FLOATS


def block(v):
    return array.array("f", [v] * FLOATS)


def write_run(d, seconds, taken, log_lines, mix_value=0.1, dev_override=None):
    """Mix: constant sound. Device: the same block where taken(t) is true, silence elsewhere,
    dev_override(i) -> value to put instead."""
    n = int(seconds / BLOCK_S)
    mix, dev = array.array("f"), array.array("f")
    for i in range(n):
        t = i * BLOCK_S
        mix.extend(block(mix_value))
        v = dev_override(i) if dev_override and dev_override(i) is not None else (mix_value if taken(t) else 0.0)
        dev.extend(block(v))
    with open(os.path.join(d, "audio_mix.f32"), "wb") as f:
        mix.tofile(f)
    with open(os.path.join(d, "audio_dev.f32"), "wb") as f:
        dev.tofile(f)
    with open(os.path.join(d, "game.log"), "w") as f:
        f.write("\n".join(log_lines) + "\n[fps] 59.9 (frames 1..300 over 5.0s)\n[fps] 59.9 (frames 1..300 over 5.0s)\n"
                "[fps] 59.9 (frames 1..300 over 5.0s)\n")


WAIT = "[cellAudio] audio device waiting: no audio device (E_NOTFOUND) (0x80070490); the game runs silent, retrying every 2 s [t=0.00s]"


def opened(t):
    return f'[cellAudio] audio device opened "Speakers" at 48000 Hz (device mix 48000 Hz, 2400 frames, event driven) [t={t:.2f}s]'


def lost(t):
    return f"[cellAudio] audio device lost: AUDCLNT_E_DEVICE_INVALIDATED (0x88890004) in GetCurrentPadding after 3.0 s of sound (simulated) [t={t:.2f}s]"


def check(d, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = adc.main([d, *args])
    return code, out.getvalue()


class AudioDeviceCheck(unittest.TestCase):
    def run_case(self, seconds, taken, log, *args, **kw):
        with tempfile.TemporaryDirectory() as d:
            write_run(d, seconds, taken, log, **kw)
            return check(d, *args)

    def test_no_device_then_device(self):
        code, out = self.run_case(12, lambda t: t >= 5.0, [WAIT, opened(5.0)], "--first-sound-after", "4.9")
        self.assertEqual(code, 0, out)
        self.assertIn("all checks passed", out)

    def test_sound_reaches_the_device_before_one_is_open(self):
        code, out = self.run_case(12, lambda t: t >= 2.0, [WAIT, opened(5.0)])
        self.assertEqual(code, 1, out)
        self.assertIn("nothing reaches the device while none is open", out)

    def test_loss_and_reopen_within_a_second(self):
        taken = lambda t: not (6.0 <= t < 6.4)
        code, out = self.run_case(12, taken, [opened(0.03), lost(6.0), opened(6.4)], "--losses", "1")
        self.assertEqual(code, 0, out)
        self.assertIn("open again after 0.40 s", out)

    def test_default_device_change_make_before_break(self):
        switch = "[cellAudio] default audio device changed, switching [t=6.00s]"
        code, out = self.run_case(12, lambda t: True, [opened(0.03), switch, opened(6.01)], "--changes", "1")
        self.assertEqual(code, 0, out)
        self.assertIn("default change at t=6.00 s: device open again after 0.01 s", out)

    def test_wrong_number_of_changes(self):
        code, out = self.run_case(12, lambda t: True, [opened(0.03)], "--changes", "2")
        self.assertEqual(code, 1, out)
        self.assertIn("0 default-device change(s) logged, expected 2", out)

    def test_reopen_too_late(self):
        taken = lambda t: not (6.0 <= t < 8.5)
        code, out = self.run_case(12, taken, [opened(0.03), lost(6.0), opened(8.5)])
        self.assertEqual(code, 1, out)
        self.assertIn("open again after 2.50 s", out)

    def test_never_reopened(self):
        taken = lambda t: t < 6.0
        code, out = self.run_case(12, taken, [opened(0.03), lost(6.0)])
        self.assertEqual(code, 1, out)
        self.assertIn("never followed by an open device", out)

    def test_block_that_is_not_the_mix_block(self):
        code, out = self.run_case(12, lambda t: True, [opened(0.03)], dev_override=lambda i: 0.2 if i == 300 else None)
        self.assertEqual(code, 1, out)
        self.assertIn("music stays in step", out)

    def test_first_device_inside_the_fake_window(self):
        code, out = self.run_case(12, lambda t: t >= 2.0, [WAIT, opened(2.0)], "--first-sound-after", "5")
        self.assertEqual(code, 1, out)
        self.assertIn("first device opened at t=2.00 s", out)

    def test_missing_files(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "game.log"), "w") as f:
                f.write("x\n")
            with self.assertRaises(SystemExit):
                check(d)


if __name__ == "__main__":
    unittest.main()
