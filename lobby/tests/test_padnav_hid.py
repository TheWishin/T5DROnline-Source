"""The launcher's own reading of DualShock 4 / DualSense / DualSense Edge pads as HID devices (padnav.HidSource),
without a controller: input reports of every mode built from the published formats by tools/ps_hid_reports.py
(the writer the game's tests use, ps3recomp patch 0042), fed through a fake device API or the game's own test
hook (PS3_PAD_HID_FAKE: reports appended to a file). tests/test_ps_hid.py also compares this parser with the
game's on thousands of random reports when the patched runtime source is there."""
import os
import random
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ps_hid_reports as phr  # noqa: E402
from t5lobby import padmap, padnav  # noqa: E402
from t5lobby.padmap import DINPUT, XINPUT, Controls  # noqa: E402
from t5lobby.padnav import Device, HidInfo, PadNav  # noqa: E402

COMBOS = [("ds4", "usb"), ("ds4", "bt-simple"), ("ds4", "bt-ext"), ("ds4", "bt-audio"), ("dualsense", "usb"),
          ("dualsense", "bt-simple"), ("dualsense", "bt-ext"), ("edge", "usb"), ("edge", "bt-simple"), ("edge", "bt-ext")]
AXES = ("X", "Y", "Z", "RX", "RY", "RZ", "S0", "S1")


def expected_sources(model, mode, state):
    """The controls.ini names DirectInput (and the game) give this pad state: from the game's raw ids
    (ps_hid_reports.expected_raw), translated the way the game names them."""
    words, _axes = phr.expected_raw(model, mode, state)
    out = set()
    for cid in range(160):
        if not words[cid // 32] >> (cid % 32) & 1:
            continue
        if cid < 128:
            out.add(f"B{cid + 1}")
        elif cid < 144:
            out.add("HAT_" + ("UP", "RIGHT", "DOWN", "LEFT")[(cid - 128) % 4])
        else:
            a = (cid - 144) // 2
            out.add(AXES[a] + ("-" if (cid - 144) % 2 else "+"))
    return out


def report(model, mode, state, counter=0, seed=None):
    return phr.padded(model, mode, phr.report(model, mode, state, counter=counter, seed=seed))


class ParseTest(unittest.TestCase):
    def test_every_model_and_mode(self):
        rnd = random.Random(5)
        for model, mode in COMBOS:
            for i in range(300):
                s = phr.PadState.random(rnd)
                rep = report(model, mode, s, counter=i, seed=rnd.randrange(1 << 30))
                bt = mode != "usb"
                got_mode, held = padnav.ps_parse(model, bt, rep)
                self.assertEqual(got_mode, "bt-ext" if mode == "bt-audio" else mode, (model, mode))
                self.assertEqual(held, expected_sources(model, mode, s),
                                 f"{model} {mode} {sorted(s.buttons)} hat={s.hat} lx={s.lx} ly={s.ly}")
                self.assertEqual(padnav.ps_crc_ok(model, rep), True if mode in ("bt-ext", "bt-audio") else None)

    def test_the_layout_names(self):
        s = phr.PadState(buttons={"square", "cross", "circle", "triangle", "l1", "options", "ps", "mute"}, hat=1,
                         lx=0, ry=255, l2=255)
        _mode, held = padnav.ps_parse("dualsense", True, report("dualsense", "bt-ext", s))
        self.assertEqual(held, {"B1", "B2", "B3", "B4", "B5", "B10", "B13", "B15", "HAT_UP", "HAT_RIGHT", "X-", "RZ+",
                                "RX+", "RY-"})
        _mode, held = padnav.ps_parse("edge", False, report("edge", "usb", phr.PadState(
            buttons={"fn_left", "paddle_right"})))
        self.assertEqual(held - {"RX-", "RY-"}, {"B16", "B19"})
        self.assertEqual(padmap.Controls().face_sources(DINPUT, -1, 0x054C, 0x0CE6)["cross"], ["B2"])   # "ps" layout

    def test_the_link_decides_a_dualsense_report_1(self):
        s = phr.PadState(buttons={"cross"})
        simple = report("dualsense", "bt-simple", s)        # 78 bytes: Windows pads it to the longest report
        self.assertEqual(padnav.ps_parse("dualsense", True, simple)[0], "bt-simple")
        self.assertEqual(padnav.ps_parse("dualsense", None, simple)[0], "bt-simple")   # not known: not 64 bytes
        usb = report("dualsense", "usb", s)
        self.assertEqual(padnav.ps_parse("dualsense", False, usb), ("usb", expected_sources("dualsense", "usb", s)))
        self.assertEqual(padnav.ps_parse("dualsense", None, usb)[0], "usb")

    def test_reports_without_input(self):
        s = phr.PadState(buttons={"cross"})
        self.assertEqual(padnav.ps_parse("ds4", True, report("ds4", "bt-ext", s)[:9]), (None, None))   # cut
        no_flag = phr.padded("ds4", "bt-ext", phr.report("ds4", "bt-ext", s, hid_flag=False))
        self.assertEqual(padnav.ps_parse("ds4", True, no_flag), (None, None))
        self.assertEqual(padnav.ps_parse("dualsense", True, bytes([0x05]) + bytes(77)), (None, None))   # other ID
        bad = bytearray(report("dualsense", "bt-ext", s))
        bad[20] ^= 1
        self.assertIs(padnav.ps_crc_ok("dualsense", bytes(bad)), False)

    def test_crc_gate(self):
        g = padnav.CrcGate()
        self.assertTrue(all(g.passes(False) is False for _ in range(24)))
        self.assertTrue(g.passes(False))                    # the 25th bad one from a pad never seen good: used
        self.assertTrue(g.passes(True))
        self.assertFalse(g.passes(False))                   # after a good one: dropped
        self.assertTrue(g.passes(None))                     # nothing to check

    def test_the_models(self):
        self.assertEqual([padnav.ps_model(0x054C, p) for p in (0x05C4, 0x09CC, 0x0CE6, 0x0DF2, 0x0268)],
                         ["ds4", "ds4", "dualsense", "edge", None])
        self.assertIsNone(padnav.ps_model(0x045E, 0x0CE6))

    def test_steam_lists(self):
        self.assertTrue(padnav.steam_lists(0x054C, 0x0CE6, {"SDL_GAMECONTROLLER_IGNORE_DEVICES": "0x054C/0x0CE6"}))
        self.assertFalse(padnav.steam_lists(0x054C, 0x0CE6, {"SDL_GAMECONTROLLER_IGNORE_DEVICES": "0x054C/0x09CC"}))
        self.assertTrue(padnav.steam_lists(0x054C, 0x0CE6, {"SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT": "0x28DE/0x1205"}))
        self.assertFalse(padnav.steam_lists(0x054C, 0x0CE6, {"SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT": "0x054C/0x0CE6"}))
        self.assertFalse(padnav.steam_lists(0x054C, 0x0CE6, {}))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "svg.txt")
            with open(p, "w") as f:
                f.write("[slot 0]\nslot=0\ntype=xbox360\nVID=0x054C\nPID=0x0CE6\n[slot 1]\nVID=0x045E\n")
            self.assertTrue(padnav.steam_lists(0x054C, 0x0CE6, {"SteamVirtualGamepadInfo": p}))
            self.assertFalse(padnav.steam_lists(0x054C, 0x09CC, {"SteamVirtualGamepadInfo": p}))


class FakeReader:
    def __init__(self, api, info):
        self.api, self.info = api, info
        self.queue = []
        self.failed = False
        self.closed = False

    def reads(self):
        out, self.queue = self.queue, []
        return out

    def close(self):
        self.closed = True


class FakeApi:
    """Stands in for setupapi / hid.dll: pads by path; open() records what was opened."""

    def __init__(self, *infos):
        self.infos = list(infos)
        self.readers = {}
        self.opens = []
        self.refuse = set()

    def enumerate(self):
        return list(self.infos)

    def open(self, info):
        self.opens.append(info.path)
        if info.path in self.refuse:
            return None
        r = self.readers[info.path] = FakeReader(self, info)
        return r

    def push(self, path, model, mode, state, n=1):
        for i in range(n):
            self.readers[path].queue.append(report(model, mode, state, counter=i))


DS_BT = HidInfo(r"\\?\hid#{00001124-0000-1000-8000-00805f9b34fb}_vid&0002054c_pid&0ce6#a", 0x054C, 0x0CE6,
                "dualsense", True, 78)
DS4_USB = HidInfo(r"\\?\hid#vid_054c&pid_09cc&mi_03#b", 0x054C, 0x09CC, "ds4", False, 64)


class SourceTest(unittest.TestCase):
    def test_reads_every_report_and_keeps_taps(self):
        api = FakeApi(DS_BT)
        src = padnav.HidSource(api=api, env={})
        src.scan()
        self.assertEqual(api.opens, [DS_BT.path])
        d = src.read()[0]
        self.assertEqual((d.kind, d.key, d.name, d.vid, d.pid, d.slot), (DINPUT, "hid:" + DS_BT.path,
                                                                          "DualSense (Bluetooth)", 0x054C, 0x0CE6, None))
        self.assertEqual(d.pressed, frozenset({"RX-", "RY-"}))                       # at rest: the triggers' ends
        api.push(DS_BT.path, "dualsense", "bt-ext", phr.PadState(buttons={"cross"}))
        api.push(DS_BT.path, "dualsense", "bt-ext", phr.PadState())
        self.assertIn("B2", src.read()[0].pressed)                                    # pressed and let go in one poll
        self.assertNotIn("B2", src.read()[0].pressed)                                 # ... reported once
        api.push(DS_BT.path, "dualsense", "bt-simple", phr.PadState(buttons={"circle"}, hat=4))
        self.assertTrue({"B3", "HAT_DOWN"} <= src.read()[0].pressed)                 # the mode may change any time
        self.assertTrue({"B3", "HAT_DOWN"} <= src.read()[0].pressed)                 # held
        self.assertEqual(src.pads[DS_BT.path]["mode"], "bt-simple")

    def test_bad_crcs_after_good_ones_are_dropped(self):
        api = FakeApi(DS_BT)
        src = padnav.HidSource(api=api, env={})
        src.scan()
        api.push(DS_BT.path, "dualsense", "bt-ext", phr.PadState())
        src.read()
        bad = bytearray(report("dualsense", "bt-ext", phr.PadState(buttons={"triangle"})))
        bad[40] ^= 0x10
        api.readers[DS_BT.path].queue.append(bytes(bad))
        self.assertNotIn("B4", src.read()[0].pressed)

    def test_steam_input_pads_are_left_to_steams_virtual_pad(self):
        env = {"SDL_GAMECONTROLLER_IGNORE_DEVICES": "0x054C/0x0CE6"}
        xi = [True]
        api = FakeApi(DS_BT, DS4_USB)
        src = padnav.HidSource(api=api, env=env, xinput_present=lambda: xi[0])
        src.scan()
        self.assertEqual(api.opens, [DS4_USB.path])                                  # the listed one is Steam's
        self.assertEqual([d.pid for d in src.read()], [0x09CC])
        xi[0] = False
        src.pause()
        api.opens.clear()
        src.scan()
        self.assertEqual(sorted(api.opens), sorted([DS_BT.path, DS4_USB.path]))      # no virtual pad: read it
        src.pause()
        src.configure(Controls("[general]\nsteam_input = 0\n"))
        xi[0] = True
        api.opens.clear()
        src.scan()
        self.assertIn(DS_BT.path, api.opens)                                          # steam_input = 0: always

    def test_hid_off_in_controls_ini(self):
        api = FakeApi(DS_BT)
        src = padnav.HidSource(api=api, env={})
        for text in ("[general]\nhid = 0\n", "[general]\ndinput = 0\n"):
            src.configure(Controls(text))
            src.scan()
            self.assertEqual(api.opens, [], text)
        src.configure(Controls("[general]\ndinput = 0\nhid = 1\n"))
        src.scan()
        self.assertEqual(api.opens, [DS_BT.path])
        src.configure(Controls("[general]\nhid = 0\n"))
        self.assertEqual(src.pads, {})                                                # closed at once

    def test_pause_closes_and_unplug_drops(self):
        api = FakeApi(DS_BT)
        src = padnav.HidSource(api=api, env={})
        src.scan()
        r = api.readers[DS_BT.path]
        src.pause()
        self.assertTrue(r.closed)
        self.assertEqual(src.read(), [])
        src.scan()
        self.assertEqual(len(src.read()), 1)
        api.infos = []
        src.scan()
        self.assertTrue(api.readers[DS_BT.path].closed)
        self.assertEqual(src.read(), [])
        api.infos = [DS_BT]
        src.scan()
        api.readers[DS_BT.path].failed = True                                         # reading failed: gone
        self.assertEqual(src.read(), [])
        self.assertTrue(api.readers[DS_BT.path].closed)

    def test_a_pad_another_program_holds_exclusively(self):
        api = FakeApi(DS_BT)
        api.refuse.add(DS_BT.path)
        src = padnav.HidSource(api=api, env={})
        src.scan()
        src.scan()
        self.assertEqual(api.opens, [DS_BT.path])                                     # tried once while plugged in
        self.assertEqual(src.read(), [])
        self.assertFalse(src.covers(0x054C, 0x0CE6))                                  # WinMM may still try it

    def test_winmm_leaves_a_pad_read_here_alone(self):
        api = FakeApi(DS_BT)
        src = padnav.HidSource(api=api, env={})
        src.scan()
        self.assertTrue(src.covers(0x054C, 0x0CE6))
        self.assertFalse(src.covers(0x054C, 0x09CC))
        w = padnav.WinMMSource(hid_ids=lambda: set(), covered=src.covers)
        import ctypes

        class Info(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint32) for n in (
                "dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos", "dwUpos", "dwVpos", "dwButtons",
                "dwButtonNumber", "dwPOV", "dwReserved1", "dwReserved2")]
        w.dll = type("D", (), {"joyGetPosEx": staticmethod(lambda jid, info: 0)})()
        w._Info = Info
        caps = type("C", (), {"wCaps": 0, "wXmin": 0, "wXmax": 65535, "wYmin": 0, "wYmax": 65535})()
        w.devs = {0: dict(name="Wireless Controller", raw="", vid=0x054C, pid=0x0CE6, nbuttons=14, caps=caps),
                  1: dict(name="Hori", raw="", vid=0x0F0D, pid=0x00EE, nbuttons=14, caps=caps)}
        self.assertEqual([d.vid for d in w.read()], [0x0F0D])

    def test_the_games_fake_pad_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "hid.txt")
            src = padnav.HidSource(env={"PS3_PAD_HID_FAKE": f"dualsense,bt,{p}"})
            src.scan()
            self.assertEqual(src.read(), [])                                         # no file: no pad
            with open(p, "w") as f:
                f.write(report("dualsense", "bt-ext", phr.PadState(buttons={"cross"})).hex() + "\n")
            src.scan()
            self.assertEqual(src.read()[0].pressed, frozenset({"RX-", "RY-"}))       # older reports are history
            with open(p, "a") as f:
                f.write("# a comment\n" + report("dualsense", "bt-ext", phr.PadState(buttons={"square"})).hex()
                        + "\n" + report("dualsense", "bt-ext", phr.PadState()).hex() + "\n")
            dev = src.read()[0]
            self.assertIn("B1", dev.pressed)
            self.assertEqual(dev.name, "DualSense (Bluetooth)")
            os.remove(p)
            self.assertEqual(src.read(), [])                                         # the file gone: unplugged
        self.assertFalse(padnav.FakeHid("dualsense,serial,x").ok)

    def test_default_sources_in_the_games_order(self):
        if os.name != "nt":
            self.skipTest("Windows only")
        kinds = [type(s).__name__ for s in padnav.default_sources({})]
        self.assertEqual(kinds, ["XInputSource", "HidSource", "WinMMSource"])

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_the_real_reader_runs_without_a_pad(self):
        # Whatever is plugged into this PC: enumerating, opening and reading must not raise or hang.
        src = padnav.HidSource(env={})
        self.assertIsInstance(src.api, padnav._Win32Hid)
        for _ in range(3):
            src.scan()
            for dev in src.read():
                self.assertIsInstance(dev.pressed, frozenset)
        src.pause()
        self.assertEqual(src.pads, {})


class NothingIsSentTest(unittest.TestCase):
    """Sending an output report or asking for a feature report switches a Bluetooth pad to its extended report
    (the very thing that makes it invisible to WinMM and DirectInput): the launcher never does either, never
    asks for the product string, and never opens a pad for writing or exclusively."""

    def test_no_call_that_talks_to_the_pad(self):
        with open(padnav.__file__, encoding="utf-8") as f:
            text = f.read()
        for call in ("WriteFile", "HidD_SetOutputReport", "HidD_SetFeature", "HidD_GetFeature", "HidD_GetInputReport",
                     "HidD_GetProductString", "HidD_GetSerialNumberString", "DeviceIoControl", "GENERIC_WRITE"):
            self.assertNotIn(call, text, call)

    def test_opened_for_reading_and_shared(self):
        self.assertEqual(padnav._Win32Hid.GENERIC_READ, 0x80000000)
        self.assertEqual(padnav._Win32Hid.FILE_SHARE_RW, 0x3)                     # read and write sharing

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_the_game_can_open_a_device_the_launcher_holds(self):
        # Any HID collection on this PC that can be read stands in for a pad: held open the launcher's way, it
        # still opens the game's way (pad_host_win32.c: GENERIC_READ, read and write sharing, overlapped).
        api = padnav._Win32Hid()
        k = api.k32
        for path in api.paths():
            h = k.CreateFileW(path, api.GENERIC_READ, api.FILE_SHARE_RW, None, api.OPEN_EXISTING,
                              api.FILE_FLAG_OVERLAPPED, None)
            if not h or h == api.INVALID:
                continue                     # keyboards, mice: Windows keeps those for itself
            try:
                g = k.CreateFileW(path, 0x80000000, 0x1 | 0x2, None, 3, 0x40000000, None)
                self.assertTrue(g and g != api.INVALID, path)
                k.CloseHandle(g)
            finally:
                k.CloseHandle(h)
            return
        self.skipTest("no readable HID device on this PC")


class NavTest(unittest.TestCase):
    """The navigator (Online tab) and the port map with a PlayStation pad read here."""

    def test_cross_on_a_dualsense_in_its_extended_mode_accepts(self):
        clock = [1000.0]
        api = FakeApi(DS_BT)
        src = padnav.HidSource(api=api, env={})
        nav = PadNav([src], foreground=lambda: True, clock=lambda: clock[0])

        def run(seconds):
            end = clock[0] + seconds
            while clock[0] < end:
                nav.step(clock[0])
                clock[0] += 1 / 60
        run(0.5)
        api.push(DS_BT.path, "dualsense", "bt-ext", phr.PadState(buttons={"cross"}))
        run(0.1)
        api.push(DS_BT.path, "dualsense", "bt-ext", phr.PadState())
        run(0.5)
        api.push(DS_BT.path, "dualsense", "bt-ext", phr.PadState(buttons={"circle"}))
        api.push(DS_BT.path, "dualsense", "bt-ext", phr.PadState())                  # a tap inside one poll
        run(0.5)
        events = []
        while not nav.events.empty():
            events.append(nav.events.get_nowait())
        self.assertEqual([(e.button, e.source) for e in events], [("cross", "B2"), ("circle", "B3")])
        self.assertEqual(nav.label("cross"), "B2")

    def test_leaving_the_front_closes_the_pad(self):
        api = FakeApi(DS_BT)
        src = padnav.HidSource(api=api, env={})
        front = [True]
        nav = PadNav([src], foreground=lambda: front[0], clock=lambda: 0.0)
        nav.step(0.0)
        self.assertEqual(len(src.pads), 1)
        front[0] = False
        nav.step(0.1)
        self.assertEqual(src.pads, {})
        self.assertTrue(api.readers[DS_BT.path].closed)

    def test_ports_like_the_game(self):
        pm = padmap.PortMap(Controls())
        x = Device(XINPUT, "xinput:0", "XInput", 0, 0, 0, frozenset())
        h = Device(DINPUT, "hid:" + DS_BT.path, "DualSense (Bluetooth)", 0x054C, 0x0CE6, None, frozenset())
        w = Device(DINPUT, "winmm:0", "Hori", 0x0F0D, 0x00EE, None, frozenset())
        self.assertEqual(pm.update([x, h, w]), {"xinput:0": 0, h.key: 1, "winmm:0": 2})   # XInput first, as the game
        pinned = padmap.PortMap(Controls("[port1]\ndevice = dinput:054C:0CE6\n"))
        self.assertEqual(pinned.update([x, h])[h.key], 0)                              # pinned to player 1
        for text, reads in (("[general]\nhid = 0\n", False), ("[general]\ndinput = 0\n", False),
                            ("[general]\ndinput = 0\nhid = 1\n", True)):
            pm = padmap.PortMap(Controls(text))
            pm.update([h, w])
            self.assertEqual(pm.reads(h.key), reads, text)
            self.assertEqual(pm.reads(w.key), "dinput = 0" not in text, text)


if __name__ == "__main__":
    unittest.main()
