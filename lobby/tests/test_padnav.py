"""Controller navigation for the launcher without a real pad: controls.ini -> Cross / Circle / Triangle
(padmap.py), the polling rules (padnav.py: only with the launcher in front, a press counts only after the
button was up for a moment, mashing and held buttons are ignored) driven by a fake pad source and a fake
clock, the pure parts of the XInput / WinMM readers, and the polling thread with the real clock."""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import padmap, padnav  # noqa: E402
from t5lobby.padmap import DINPUT, XINPUT, Controls  # noqa: E402
from t5lobby.padnav import Device, PadNav  # noqa: E402


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakePad(padnav.PadSource):
    """A controller that does what the test says; counts how often it was looked at."""

    def __init__(self, kind=XINPUT, key="fake:0", name="Fake pad", vid=0, pid=0, slot=0):
        self.kind, self.key, self.name, self.vid, self.pid, self.slot = kind, key, name, vid, pid, slot
        self.held = set()
        self.plugged = True
        self.reads = 0
        self.scans = 0

    def scan(self):
        self.scans += 1

    def read(self):
        self.reads += 1
        if not self.plugged:
            return []
        return [Device(self.kind, self.key, self.name, self.vid, self.pid, self.slot, frozenset(self.held))]


class Rig:
    """A navigator on a fake clock: `run(seconds)` polls at 60 Hz, `tap(button)` is a clean press."""

    def __init__(self, *pads, ini=None, arm_s=padnav.ARM_S):
        self.clock = FakeClock()
        self.front = True
        self.pads = list(pads) or [FakePad()]
        path = None
        if ini is not None:
            fd, path = tempfile.mkstemp(suffix=".ini")
            os.close(fd)
            with open(path, "w") as f:
                f.write(ini)
            self.path = path
        self.nav = PadNav(self.pads, controls=padmap.ControlsFile(lambda: path),
                          foreground=lambda: self.front, arm_s=arm_s, clock=self.clock)

    def close(self):
        if getattr(self, "path", None):
            os.remove(self.path)

    def run(self, seconds):
        end = self.clock.t + seconds
        while self.clock.t < end - 1e-9:
            self.nav.step(self.clock.t)
            self.clock.t += 1 / 60

    def events(self):
        out = []
        while not self.nav.events.empty():
            out.append(self.nav.events.get_nowait())
        return out

    def hold(self, src, seconds, pad=None):
        pad = pad or self.pads[0]
        pad.held.add(src)
        self.run(seconds)
        pad.held.discard(src)

    def tap(self, src, pad=None, before=0.5, hold=0.1):
        """Wait with everything up, press `src` for `hold` seconds, let go."""
        self.run(before)
        self.hold(src, hold, pad)
        self.run(1 / 30)
        return self.events()


class IniTest(unittest.TestCase):
    """controls.ini: the same buttons as in the game (patch 0009's rules)."""

    def faces(self, text="", kind=DINPUT, port=-1, vid=0, pid=0):
        return Controls(text).face_sources(kind, port, vid, pid)

    def test_xinput_default_is_a_b_y(self):
        self.assertEqual(self.faces(kind=XINPUT), {"cross": ["A"], "circle": ["B"], "triangle": ["Y"]})

    def test_playstation_layout_is_the_default_for_other_devices(self):
        self.assertEqual(self.faces(vid=0x054C, pid=0x09CC), {"cross": ["B2"], "circle": ["B3"], "triangle": ["B4"]})

    def test_nintendo_and_microsoft_devices_get_their_own_presets(self):
        self.assertEqual(self.faces(vid=0x057E)["cross"], ["B1"])
        self.assertEqual(self.faces(vid=0x057E)["circle"], ["B2"])
        self.assertEqual(self.faces(vid=0x045E)["circle"], ["B2"])

    def test_a_remapped_stick_follows_controls_ini(self):
        ini = "[dinput]\nCROSS = B1\nCIRCLE = B4\n"
        f = self.faces(ini)
        self.assertEqual(f["cross"], ["B1"])       # B2 is Cross no more, and B1 is no longer Square
        self.assertEqual(f["circle"], ["B4"])
        self.assertEqual(f["triangle"], [])        # B4 was Triangle: an explicit binding takes it away

    def test_tekken_names_and_aliases(self):
        f = self.faces("[dinput]\n3 = B7\n4 = B8\n2 = B9\n")
        self.assertEqual((f["cross"], f["circle"], f["triangle"]), (["B7"], ["B8"], ["B9"]))
        f = self.faces("[dinput]\nLK = B7\n")
        self.assertEqual(f["cross"], ["B7"])

    def test_one_model_only(self):
        ini = "[dinput.0F0D:00EE]\n3 = B1\n"
        self.assertEqual(self.faces(ini, vid=0x0F0D, pid=0x00EE)["cross"], ["B1"])
        self.assertEqual(self.faces(ini, vid=0x0F0D, pid=0x00EF)["cross"], ["B2"])

    def test_port_sections_apply_to_the_device_on_that_port(self):
        ini = "[port2.dinput]\nCROSS = B5\n"
        self.assertEqual(self.faces(ini, port=1)["cross"], ["B5"])
        self.assertEqual(self.faces(ini, port=0)["cross"], ["B2"])
        self.assertEqual(self.faces(ini, port=-1)["cross"], ["B2"])

    def test_xinput_sections(self):
        f = self.faces("[xinput]\nCROSS = X\n[port1.xinput]\nCIRCLE = RB\n", kind=XINPUT, port=0)
        self.assertEqual(f["cross"], ["X"])
        self.assertEqual(f["circle"], ["RB"])

    def test_a_macro_button_is_never_cross_or_circle(self):
        # 3+4 on one button presses Cross AND Circle in the game; for the launcher it is neither
        f = self.faces("[dinput]\n3+4 = B2\n")
        self.assertEqual(f["cross"], [])
        self.assertEqual(f["circle"], ["B3"])
        f = self.faces("[port1]\nmacros = tekken\n", port=0)
        self.assertNotIn("B6", f["cross"] + f["circle"] + f["triangle"])
        self.assertEqual(f["cross"], ["B2"])

    def test_unbinding_and_presets(self):
        self.assertEqual(self.faces("[dinput]\nCROSS =\n")["cross"], [])
        self.assertEqual(self.faces("[dinput]\npreset = switch\n")["cross"], ["B1"])
        self.assertEqual(self.faces("[xinput]\npreset = none\n", kind=XINPUT)["cross"], [])

    def test_comments_case_and_junk(self):
        ini = ("; a comment\n# another\n[DInput]\ncross = b1   ; inline comment\n  CIRCLE=B2#not a comment\n"
               "garbage line\n[unfinished\nTRIANGLE = B9\n")
        c = Controls(ini)
        f = c.face_sources(DINPUT)
        self.assertEqual(f["cross"], ["B1"])
        self.assertEqual(f["circle"], [])           # 'B2#not a comment' is one unknown source name
        self.assertTrue(any("B2#not" in w for w in c.warnings))
        self.assertEqual(f["triangle"], ["B4"])     # lines under a broken section header are not applied

    def test_unknown_names_warn_and_do_not_crash(self):
        c = Controls("[dinput]\nCROSS = B999 NOPE\nWHAT = B3\n[xinput]\npreset = nonsense\n")
        c.face_sources(DINPUT)
        c.face_sources(XINPUT)
        self.assertGreaterEqual(len(c.warnings), 3)

    def test_hat_and_axis_names_have_one_spelling(self):
        self.assertEqual(padmap.canon_source(DINPUT, "hat1_up"), "HAT_UP")
        self.assertEqual(padmap.canon_source(DINPUT, "HAT2_LEFT"), "HAT2_LEFT")
        self.assertEqual(padmap.canon_source(DINPUT, "rz-"), "RZ-")
        self.assertIsNone(padmap.canon_source(DINPUT, "B0"))
        self.assertEqual(padmap.canon_source(XINPUT, "lt"), "LT")

    def test_triggers_and_hat_can_be_cross(self):
        self.assertEqual(self.faces("[xinput]\nCROSS = RT\n", kind=XINPUT)["cross"], ["RT"])
        self.assertEqual(self.faces("[dinput]\nCROSS = HAT_DOWN\n")["cross"], ["HAT_DOWN"])

    def test_where_the_file_is(self):
        with tempfile.TemporaryDirectory() as d:
            exe_dir = os.path.join(d, "build", "cmake")
            os.makedirs(exe_dir)
            self.assertIsNone(padmap.find_controls_ini(d, {}) if "PS3_CONTROLS" not in os.environ else None)
            cwd_file = os.path.join(d, "controls.ini")
            open(cwd_file, "w").close()
            env = {"PS3_CONTROLS": ""}
            self.assertEqual(padmap.find_controls_ini(d, env), cwd_file)      # the game's working directory
            exe_file = os.path.join(exe_dir, "controls.ini")
            open(exe_file, "w").close()
            self.assertEqual(padmap.find_controls_ini(d, env), exe_file)      # next to t5dr.exe first
            explicit = os.path.join(d, "mine.ini")
            open(explicit, "w").close()
            self.assertEqual(padmap.find_controls_ini(d, {"PS3_CONTROLS": explicit}), explicit)
            self.assertIsNone(padmap.find_controls_ini(d, {"PS3_CONTROLS": os.path.join(d, "missing.ini")}))

    def test_file_is_read_again_when_it_changes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "controls.ini")
            f = padmap.ControlsFile(lambda: p)
            self.assertEqual(f.refresh().face_sources(DINPUT)["cross"], ["B2"])      # no file: defaults
            with open(p, "w") as fh:
                fh.write("[dinput]\nCROSS = B1\n")
            self.assertEqual(f.refresh().face_sources(DINPUT)["cross"], ["B1"])
            n = f.changed
            f.refresh()
            self.assertEqual(f.changed, n)                                           # unchanged: not parsed again
            with open(p, "w") as fh:
                fh.write("[dinput]\nCROSS = B6 ; moved\n")
            self.assertEqual(f.refresh().face_sources(DINPUT)["cross"], ["B6"])


class PortTest(unittest.TestCase):
    def dev(self, kind, key, vid=0, pid=0, slot=None, name=""):
        return Device(kind, key, name, vid, pid, slot, frozenset())

    def test_devices_take_the_lowest_free_port_in_order(self):
        pm = padmap.PortMap(Controls())
        a, b = self.dev(XINPUT, "x0", slot=0), self.dev(DINPUT, "w0", 0x0F0D, 0x00EE)
        self.assertEqual(pm.update([a, b]), {"x0": 0, "w0": 1})
        self.assertEqual(pm.update([b]), {"w0": 1})                  # unplugging one frees its port, the other stays
        c = self.dev(DINPUT, "w1", 0x054C, 0x09CC)
        self.assertEqual(pm.update([b, c])["w1"], 0)

    def test_a_pinned_port(self):
        pm = padmap.PortMap(Controls("[port1]\ndevice = dinput:0F0D:00EE\n[port2]\ndevice = xinput\n"))
        x = self.dev(XINPUT, "x0", slot=0)
        s = self.dev(DINPUT, "w0", 0x0F0D, 0x00EE)
        self.assertEqual(pm.update([x, s]), {"x0": 1, "w0": 0})
        pm = padmap.PortMap(Controls("[port1]\ndevice = dinput:hori\n"))
        h = self.dev(DINPUT, "w0", 1, 2, name="HORI Fighting Stick")
        self.assertEqual(pm.update([self.dev(DINPUT, "w9", 3, 4, name="Other"), h])["w0"], 0)

    def test_kinds_switched_off_in_general_are_not_read(self):
        pm = padmap.PortMap(Controls("[general]\nxinput = 0\n"))
        pm.update([self.dev(XINPUT, "x0", slot=0), self.dev(DINPUT, "w0")])
        self.assertFalse(pm.reads("x0"))
        self.assertTrue(pm.reads("w0"))


class ReaderTest(unittest.TestCase):
    """The parts of the XInput / WinMM readers that need no hardware."""

    def test_xinput_packet(self):
        self.assertEqual(padnav.xinput_sources(0x1000 | 0x0100, 0, 0, 0, 0, 0, 0), {"A", "LB"})
        self.assertEqual(padnav.xinput_sources(0, 31, 30, 0, 0, 0, 0), {"LT"})        # past 30 of 255
        self.assertEqual(padnav.xinput_sources(0, 0, 0, 0, 0, 0, 0), set())

    def test_stick_directions_need_half_deflection(self):
        self.assertEqual(padnav.xinput_sources(0, 0, 0, 32767, 0, 0, 0), {"LRIGHT"})
        self.assertEqual(padnav.xinput_sources(0, 0, 0, 0, 32767, 0, 0), {"LUP"})       # XInput Y up = positive
        self.assertEqual(padnav.xinput_sources(0, 0, 0, 0, -32768, 0, 0), {"LDOWN"})
        self.assertEqual(padnav.xinput_sources(0, 0, 0, 0, 0, -32768, 0), {"RLEFT"})
        self.assertEqual(padnav.xinput_sources(0, 0, 0, 12000, 0, 0, 0), set())         # a bump in the deadzone range

    def test_winmm_buttons_hat_axes(self):
        self.assertEqual(padnav.winmm_sources(0b1010, 12, 0xFFFF, []), {"B2", "B4"})
        self.assertEqual(padnav.winmm_sources(1 << 13, 12, 0xFFFF, []), set())        # beyond the device's buttons
        self.assertEqual(padnav.hat_sources(0), {"HAT_UP"})
        self.assertEqual(padnav.hat_sources(4500), {"HAT_UP", "HAT_RIGHT"})
        self.assertEqual(padnav.hat_sources(18000), {"HAT_DOWN"})
        self.assertEqual(padnav.hat_sources(27000), {"HAT_LEFT"})
        self.assertEqual(padnav.hat_sources(0xFFFFFFFF), set())
        self.assertEqual(padnav.hat_sources(0xFFFF), set())
        self.assertEqual(padnav.axis_sources("X", 65535, 0, 65535), {"X+"})
        self.assertEqual(padnav.axis_sources("RZ", 0, 0, 65535), {"RZ-"})
        self.assertEqual(padnav.axis_sources("Y", 32767, 0, 65535), set())
        self.assertEqual(padnav.axis_sources("Y", 255, 0, 255), {"Y+"})                # a device with its own range

    def test_hid_path_tells_xinput_devices(self):
        self.assertEqual(padnav.parse_hid_path(r"\\?\HID#VID_045E&PID_02FF&IG_00#9&1d0a#{4d1e55b2}"),
                         (0x045E, 0x02FF, True))
        self.assertEqual(padnav.parse_hid_path(r"\\?\HID#VID_054C&PID_09CC#7&2b3c#{4d1e55b2}"),
                         (0x054C, 0x09CC, False))
        self.assertEqual(padnav.parse_hid_path(r"\\?\ACPI#PNP0303#4&1"), (0, 0, False))

    def test_the_virtual_pad_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "pad.txt")
            src = padnav.FileSource(p)
            self.assertEqual(src.read()[0].pressed, frozenset())                       # no file: nothing held
            with open(p, "w") as f:
                f.write("A lb nonsense")
            dev = src.read()[0]
            self.assertEqual((dev.kind, dev.pressed), (XINPUT, frozenset({"A", "LB"})))
            with open(p, "w") as f:
                f.write("dinput:054C:09CC b2 HAT1_DOWN")
            dev = src.read()[0]
            self.assertEqual((dev.kind, dev.vid, dev.pid, dev.pressed), (DINPUT, 0x054C, 0x09CC,
                                                                          frozenset({"B2", "HAT_DOWN"})))

    def test_default_sources_honour_the_test_hook(self):
        kinds = lambda env: [type(s).__name__ for s in padnav.default_sources(env)]       # noqa: E731
        real = ["XInputSource", "HidSource", "WinMMSource"] if os.name == "nt" else []
        self.assertEqual(kinds({}), real)
        self.assertEqual(kinds({"T5_PAD_FILE": "x"}), ["FileSource"])
        self.assertEqual(kinds({"T5_PAD_FILE": "x", "T5_PAD_DEVICES": "1"}), ["FileSource"] + real)

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_the_real_readers_run_without_a_pad(self):
        # Whatever is plugged into this PC: scanning and reading must not raise or hang.
        for src in (padnav.XInputSource(), padnav.WinMMSource()):
            src.scan()
            for d in src.read():
                self.assertIsInstance(d.pressed, frozenset)
        ids = padnav.xinput_hid_ids()
        self.assertTrue(ids is None or isinstance(ids, set))


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)

    def test_a_clean_press_fires_once(self):
        ev = self.rig.tap("A")
        self.assertEqual([e.button for e in ev], ["cross"])
        self.assertEqual(ev[0].source, "A")

    def test_holding_fires_once_and_the_release_arms_it_again(self):
        r = self.rig
        r.run(0.5)
        r.hold("A", 2.0)
        self.assertEqual(len(r.events()), 1)
        r.run(0.2)
        r.hold("A", 0.1)                       # let go for 0.2 s only: too soon
        self.assertEqual(r.events(), [])
        r.run(0.5)
        r.hold("A", 0.1)
        self.assertEqual(len(r.events()), 1)

    def test_all_three_face_buttons(self):
        r = self.rig
        got = [r.tap(s)[0].button for s in ("A", "B", "Y")]
        self.assertEqual(got, ["cross", "circle", "triangle"])

    def test_other_buttons_do_nothing(self):
        for s in ("X", "LB", "START", "DUP", "RT"):
            self.assertEqual(self.rig.tap(s), [])

    def test_a_press_right_at_the_start_is_not_a_press(self):
        r = self.rig
        r.hold("A", 0.1)                       # the pad was never seen up
        self.assertEqual(r.events(), [])
        r.run(0.1)
        r.hold("A", 0.1)                       # 0.1 s up is not enough either
        self.assertEqual(r.events(), [])

    def test_a_button_held_when_the_window_comes_forward_must_be_let_go_first(self):
        r = self.rig
        r.front = False
        r.pads[0].held.add("A")
        r.run(1.0)
        r.front = True
        r.run(2.0)                             # still holding
        self.assertEqual(r.events(), [])
        r.pads[0].held.clear()
        r.run(0.5)
        r.hold("A", 0.1)
        self.assertEqual(len(r.events()), 1)

    def test_mashing_does_nothing(self):
        r = self.rig
        r.run(1.0)
        for _ in range(40):                    # ~7 presses a second, 0.07 s up between them
            r.hold("A", 0.07)
            r.run(0.07)
        self.assertEqual(len(r.events()), 1)   # the first press after a quiet second; the other 39 are mashing
        r.run(0.4)                             # stop mashing, let go
        r.hold("A", 0.1)
        self.assertEqual(len(r.events()), 1)

    def test_the_release_must_last_the_full_time(self):
        r = Rig(arm_s=0.30)
        self.addCleanup(r.close)
        r.run(1.0)
        r.hold("A", 0.1)
        r.events()
        r.run(0.25)
        r.hold("A", 0.1)
        self.assertEqual(r.events(), [])
        r.run(0.35)
        r.hold("A", 0.1)
        self.assertEqual(len(r.events()), 1)

    def test_nothing_is_read_while_the_launcher_is_not_in_front(self):
        r = self.rig
        r.run(1.0)
        n = r.pads[0].reads
        r.front = False
        r.run(2.0)
        self.assertEqual(r.pads[0].reads, n)           # not even looked at
        r.pads[0].held.add("A")
        r.run(0.5)
        self.assertEqual(r.events(), [])

    def test_the_game_in_front_then_back_to_the_launcher_while_mashing(self):
        r = self.rig
        r.run(1.0)
        r.front = False                                # the game window
        for _ in range(60):
            r.hold("A", 0.05)
            r.run(0.05)
        r.front = True                                 # the fight is over, the launcher comes forward
        for _ in range(60):
            r.hold("A", 0.05)
            r.run(0.05)
        self.assertEqual(r.events(), [])
        r.run(0.4)
        r.hold("A", 0.1)
        self.assertEqual(len(r.events()), 1)

    def test_leaving_the_front_forgets_that_the_button_was_up(self):
        r = self.rig
        r.run(1.0)                                     # armed
        r.front = False
        r.run(0.1)
        r.front = True
        r.hold("A", 0.1)                               # pressed the moment the window is back
        self.assertEqual(r.events(), [])

    def test_hidden_tab_and_the_switch(self):
        r = self.rig
        r.run(1.0)
        r.nav.visible = False
        r.run(0.1)
        r.nav.visible = True
        r.hold("A", 0.1)
        self.assertEqual(r.events(), [])               # same as leaving the front
        r.run(0.5)
        r.nav.enabled = False
        r.hold("A", 0.1)
        self.assertEqual(r.events(), [])
        r.nav.enabled = True
        r.run(0.5)
        r.hold("A", 0.1)
        self.assertEqual(len(r.events()), 1)

    def test_two_buttons_in_the_same_instant_are_no_press(self):
        r = self.rig
        r.run(1.0)
        r.pads[0].held.update({"A", "B"})
        r.run(0.1)
        r.pads[0].held.clear()
        self.assertEqual(r.events(), [])

    def test_the_buttons_are_armed_one_by_one(self):
        r = self.rig
        r.run(1.0)
        r.hold("A", 0.1)                               # A was just used ...
        r.hold("B", 0.1)                               # ... B was up all along
        self.assertEqual([e.button for e in r.events()], ["cross", "circle"])

    def test_a_pad_that_is_unplugged_and_plugged_in_again(self):
        r = self.rig
        r.run(1.0)
        r.pads[0].plugged = False
        r.run(0.2)
        r.pads[0].plugged = True
        r.pads[0].held.add("A")                        # held while plugging in
        r.run(0.3)
        r.pads[0].held.clear()
        self.assertEqual(r.events(), [])
        self.assertEqual(len(r.tap("A")), 1)

    def test_a_poll_error_does_not_stop_the_navigator(self):
        r = self.rig

        class Broken(padnav.PadSource):
            def read(self):
                raise OSError("device gone")
            def scan(self):
                raise OSError("device gone")
        r.nav.sources.append(Broken())
        self.assertEqual(len(r.tap("A")), 1)
        self.assertIn("device gone", r.nav.error)

    def test_a_foreground_check_that_raises_means_not_in_front(self):
        nav = PadNav([FakePad()], foreground=lambda: 1 / 0, clock=FakeClock())
        self.assertEqual(nav.step(0.0), padnav.IDLE_S)
        self.assertFalse(nav.foreground_now())


class DevicesTest(unittest.TestCase):
    def test_a_remapped_stick(self):
        stick = FakePad(DINPUT, "winmm:1", "Fight Stick", 0x0F0D, 0x00EE, None)
        r = Rig(stick, ini="[dinput]\nCROSS = B1\nCIRCLE = B4\n")
        self.addCleanup(r.close)
        self.assertEqual(r.tap("B2", stick), [])                    # the preset's Cross is nothing now
        self.assertEqual([e.button for e in r.tap("B1", stick)], ["cross"])
        self.assertEqual([e.button for e in r.tap("B4", stick)], ["circle"])
        self.assertEqual(r.tap("B3", stick), [])

    def test_the_stick_hat_can_be_cross(self):
        stick = FakePad(DINPUT, "winmm:1", "Fight Stick", 1, 2, None)
        r = Rig(stick, ini="[dinput]\nCROSS = HAT_DOWN\n")
        self.addCleanup(r.close)
        self.assertEqual([e.button for e in r.tap("HAT_DOWN", stick)], ["cross"])

    def test_two_pads_either_one_presses(self):
        xbox, stick = FakePad(), FakePad(DINPUT, "winmm:1", "Fight Stick", 0x0F0D, 0x00EE, None)
        r = Rig(xbox, stick)
        self.addCleanup(r.close)
        self.assertEqual([e.button for e in r.tap("A", xbox)], ["cross"])
        self.assertEqual([e.button for e in r.tap("B2", stick)], ["cross"])
        self.assertEqual([e.button for e in r.tap("B3", stick)], ["circle"])

    def test_names_for_the_buttons_follow_the_pad_used_last(self):
        xbox, stick = FakePad(), FakePad(DINPUT, "winmm:1", "Fight Stick", 0x0F0D, 0x00EE, None)
        r = Rig(xbox, stick)
        self.addCleanup(r.close)
        self.assertIsNone(r.nav.label("cross"))                    # nothing seen yet
        r.run(0.2)
        self.assertEqual(r.nav.label("cross"), "A")
        self.assertEqual(r.nav.label("circle"), "B")
        self.assertEqual(r.nav.label("triangle"), "Y")
        g = r.nav.generation
        r.tap("B2", stick)                                          # the stick is used now
        self.assertEqual(r.nav.label("cross"), "B2")
        self.assertGreater(r.nav.generation, g)
        self.assertIn("Fight Stick", r.nav.summary)
        self.assertIn("Cross = B2", r.nav.summary)
        r.tap("A", xbox)
        self.assertEqual(r.nav.label("cross"), "A")

    def test_no_pad_no_labels(self):
        pad = FakePad()
        r = Rig(pad)
        self.addCleanup(r.close)
        r.run(0.2)
        pad.plugged = False
        r.run(0.2)
        self.assertIsNone(r.nav.label("cross"))
        self.assertFalse(r.nav.has_devices())

    def test_a_changed_controls_ini_changes_the_names(self):
        stick = FakePad(DINPUT, "winmm:1", "Fight Stick", 1, 2, None)
        r = Rig(stick, ini="")
        self.addCleanup(r.close)
        r.run(0.2)
        self.assertEqual(r.nav.label("cross"), "B2")
        with open(r.path, "w") as f:
            f.write("[dinput]\nCROSS = B7 B8\n")
        r.run(padnav.SCAN_S + 0.2)                                  # (the file is looked at once a second)
        self.assertEqual(r.nav.label("cross"), "B7/B8")
        self.assertEqual([e.button for e in r.tap("B8", stick)], ["cross"])


class ThreadTest(unittest.TestCase):
    """The polling thread with the real clock."""

    def make(self, front=True):
        self.pad = FakePad()
        self.front = [front]
        nav = PadNav([self.pad], foreground=lambda: self.front[0])
        self.addCleanup(nav.stop)
        return nav

    def wait_event(self, nav, timeout=2.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not nav.events.empty():
                return nav.events.get_nowait()
            time.sleep(0.005)
        return None

    def test_a_press_arrives_and_stop_ends_the_thread(self):
        nav = self.make()
        nav.start()
        time.sleep(0.5)                                  # up for a while
        self.pad.held.add("A")
        ev = self.wait_event(nav)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.button, "cross")
        self.pad.held.clear()
        before = threading.active_count()
        nav.stop()
        self.assertLess(threading.active_count(), before)
        self.assertFalse(any(t.name == "padnav" for t in threading.enumerate()))

    def test_polls_about_sixty_times_a_second_with_little_cpu(self):
        nav = self.make()
        nav.start()
        time.sleep(0.2)
        s0, c0 = nav.stats["polls"], nav.stats["busy_s"]
        t0 = time.monotonic()
        time.sleep(2.0)
        dt = time.monotonic() - t0
        rate = (nav.stats["polls"] - s0) / dt
        busy = (nav.stats["busy_s"] - c0) / dt
        print(f"\n  padnav: {rate:.1f} polls/s, {busy * 100:.2f}% of one core spent polling", file=sys.stderr)
        self.assertGreater(rate, 40)
        self.assertLess(rate, 75)
        self.assertLess(busy, 0.05)

    def test_behind_another_window_it_only_looks_at_the_foreground(self):
        nav = self.make(front=False)
        nav.start()
        time.sleep(1.0)
        self.assertEqual(self.pad.reads, 0)
        self.assertEqual(self.pad.scans, 0)
        self.assertLess(nav.stats["steps"], 40)           # ~20 a second, not 60
        self.front[0] = True
        time.sleep(0.4)
        self.assertGreater(self.pad.reads, 10)

    def test_stop_without_start_and_twice(self):
        nav = self.make()
        nav.stop()
        nav.start()
        nav.start()
        nav.stop()
        nav.stop()


if __name__ == "__main__":
    unittest.main()
