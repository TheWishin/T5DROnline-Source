"""Controller navigation for the launcher: A / Cross accepts, B / Circle declines, without mouse or keyboard.

A background thread reads the pads at ~60 Hz and turns presses of the three face buttons
(Cross, Circle, Triangle) into events for the Tk thread, which drains `PadNav.events` from its own
timer. Nothing here touches Tk, so no Tcl object can be released from this thread.

Devices (ctypes only, no packages), found in the game's order (XInput, PlayStation pads, the rest):
  XInput   Xbox pads and XInput-mode arcade sticks.
  HID      DualShock 4, DualSense and DualSense Edge, read as HID devices in every report mode over USB and
           Bluetooth -- also the Bluetooth "extended" report Steam / DS4Windows switch these pads to, of which
           WinMM sees nothing -- exactly as the game reads them (ps3recomp patch 0042). Read only (nothing is
           ever sent to the pad), shared with the game, and only while the launcher is in front.
  WinMM    every other game controller (PS3/PS4-mode sticks and hitboxes, generic USB pads) through
           joyGetPosEx. The game reads these through DirectInput; WinMM has the same button order (B1..B32)
           and hat, needs no COM, and is plain ctypes. Devices Windows also exposes through XInput are skipped
           (their HID path has "IG_"), and so are the PlayStation pads the HID reader has.
Which button is Cross is the game's own controls.ini (padmap.py): a remapped stick works the same in
the launcher and in the game.

Rules (the point of this module):
* Only while the launcher's window is the foreground window. While anything else is in front -- the
  game above all -- nothing is read at all (no device polling) and every button is forgotten.
* A press counts only after the button was up for `arm_s` (0.3 s) with the launcher in front. A button
  that is held when the window comes forward, or that is mashed (up for less than that between two
  presses), never fires. So the end of a fight does nothing in the launcher.
* Two face buttons pressed in the same instant are no press at all.

Test hooks: T5_PAD_FILE=<file> makes a virtual pad of the buttons named in the file (the held
sources, e.g. "A", or "dinput B2"); with it, physical pads are ignored (T5_PAD_DEVICES=1: both).
PS3_PAD_HID_FAKE=<ds4|dualsense|edge>,<usb|bt>,<file> is the game's fake PlayStation pad (input reports
in hex appended to the file, tools/ps_hid_reports.py); the launcher reads it the same way (and no real
PlayStation pad then). T5_PAD_NAV=0 turns the whole feature off.
"""
import ctypes
import os
import queue
import threading
import time
from collections import namedtuple

from . import padmap
from .i18n import t
from .padmap import DINPUT, KEYS, KEYS1, KEYS2, XINPUT

BUTTONS = ("cross", "circle", "triangle")
ARM_S = 0.30            # a button must have been up this long (launcher in front) before a press counts
POLL_HZ = 60
SCAN_S = 1.0            # look for plugged / unplugged devices this often (only while active)
IDLE_S = 0.05           # launcher not in front: look at the foreground window this often, nothing else

# kind, key (stable while plugged in), name, USB ids (WinMM; 0 for XInput), XInput slot, held sources
Device = namedtuple("Device", "kind key name vid pid slot pressed")
PadEvent = namedtuple("PadEvent", "button t key source")


class PadSource:
    """One way of reading controllers. scan(): find devices (about once a second); read(): the
    devices known after the last scan, each with the set of sources held right now. configure(): the
    controls.ini the game reads (padmap.Controls), before each scan. pause(): nothing will be read for a
    while (the window left the front): let go of what is open."""

    def scan(self):
        pass

    def read(self):
        return []

    def configure(self, controls):
        pass

    def pause(self):
        pass


# ---------------------------------------------------------------------- XInput

XI_BUTTONS = ((0x0001, "DUP"), (0x0002, "DDOWN"), (0x0004, "DLEFT"), (0x0008, "DRIGHT"), (0x0010, "START"),
              (0x0020, "BACK"), (0x0040, "LS"), (0x0080, "RS"), (0x0100, "LB"), (0x0200, "RB"),
              (0x1000, "A"), (0x2000, "B"), (0x4000, "X"), (0x8000, "Y"))
XI_TRIGGER_THRESHOLD = 30
XI_SUBTYPES = {1: "gamepad", 2: "wheel", 3: "arcade stick", 4: "flight stick", 5: "dance pad", 6: "guitar",
               7: "guitar", 8: "drum kit", 11: "guitar", 19: "arcade pad"}


def xi_stick(raw):
    """The left-stick deadzone (7849) rescaled so the travel stays full -- as the game does."""
    dz = 7849
    if raw > dz:
        return (raw - dz) * 32767 // (32767 - dz)
    if raw < -dz:
        return -((-raw - dz) * 32768 // (32768 - dz))
    return 0


def xinput_sources(buttons, lt, rt, lx, ly, rx, ry):
    """The controls.ini source names held in one XInput packet. Stick directions count past half
    deflection; the PS3 way round, up is negative, so 'DOWN' is positive Y."""
    held = {name for bit, name in XI_BUTTONS if buttons & bit}
    if lt > XI_TRIGGER_THRESHOLD:
        held.add("LT")
    if rt > XI_TRIGGER_THRESHOLD:
        held.add("RT")
    for pre, x, y in (("L", lx, ly), ("R", rx, ry)):
        sx, sy = xi_stick(x), -xi_stick(y)
        if sx > 16384:
            held.add(pre + "RIGHT")
        if sx < -16384:
            held.add(pre + "LEFT")
        if sy > 16384:
            held.add(pre + "DOWN")
        if sy < -16384:
            held.add(pre + "UP")
    return held


class XInputSource(PadSource):
    def __init__(self):
        self.dll = None
        self.slots = {}                 # slot -> name
        self._load()

    def _load(self):
        if os.name != "nt":
            return
        for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                self.dll = ctypes.WinDLL(name)
                break
            except OSError:
                continue
        if self.dll is None:
            return

        class Gamepad(ctypes.Structure):
            _fields_ = [("wButtons", ctypes.c_uint16), ("bLeftTrigger", ctypes.c_uint8),
                        ("bRightTrigger", ctypes.c_uint8), ("sThumbLX", ctypes.c_int16),
                        ("sThumbLY", ctypes.c_int16), ("sThumbRX", ctypes.c_int16),
                        ("sThumbRY", ctypes.c_int16)]

        class State(ctypes.Structure):
            _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("Gamepad", Gamepad)]

        class Caps(ctypes.Structure):
            _fields_ = [("Type", ctypes.c_uint8), ("SubType", ctypes.c_uint8), ("Flags", ctypes.c_uint16),
                        ("Gamepad", Gamepad), ("Vibration", ctypes.c_uint16 * 2)]
        self._State, self._Caps = State, Caps

    def scan(self):
        if self.dll is None:
            return
        for slot in range(4):               # (an empty slot costs ~0.1 ms, once a second)
            if slot in self.slots:
                continue
            st = self._State()
            if self.dll.XInputGetState(slot, ctypes.byref(st)) != 0:
                continue
            caps = self._Caps()
            self.dll.XInputGetCapabilities(slot, 0, ctypes.byref(caps))
            self.slots[slot] = XI_SUBTYPES.get(caps.SubType, "controller")

    def read(self):
        out = []
        if self.dll is None:
            return out
        for slot in sorted(self.slots):
            st = self._State()
            if self.dll.XInputGetState(slot, ctypes.byref(st)) != 0:
                del self.slots[slot]        # unplugged
                continue
            g = st.Gamepad
            out.append(Device(XINPUT, f"xinput:{slot}", f"XInput #{slot + 1} ({self.slots[slot]})", 0, 0, slot,
                              frozenset(xinput_sources(g.wButtons, g.bLeftTrigger, g.bRightTrigger,
                                                       g.sThumbLX, g.sThumbLY, g.sThumbRX, g.sThumbRY))))
        return out


# ---------------------------------------------------------------------- WinMM joysticks

JOY_RETURNALL = 0xFF
JOY_RETURNPOVCTS = 0x200
JOYCAPS_HASZ, JOYCAPS_HASR, JOYCAPS_HASU, JOYCAPS_HASV = 0x1, 0x2, 0x4, 0x8
# WinMM's six axes in the names the game's DirectInput side uses (HID usage order: the 4th axis is Rz,
# then Rx and Ry). Not checked against more than one real pad: buttons and the hat are what matters here.
WINMM_AXES = (("X", "dwXpos", "wXmin", "wXmax", 0), ("Y", "dwYpos", "wYmin", "wYmax", 0),
              ("Z", "dwZpos", "wZmin", "wZmax", JOYCAPS_HASZ), ("RZ", "dwRpos", "wRmin", "wRmax", JOYCAPS_HASR),
              ("RX", "dwUpos", "wUmin", "wUmax", JOYCAPS_HASU), ("RY", "dwVpos", "wVmin", "wVmax", JOYCAPS_HASV))


def hat_sources(pov):
    """WinMM dwPOV (hundredths of a degree, low word 0xFFFF = centred) -> HAT_* names, like the game."""
    if (pov & 0xFFFF) == 0xFFFF:
        return set()
    pov %= 36000
    held = set()
    if pov >= 31500 or pov <= 4500:
        held.add("HAT_UP")
    if 4500 <= pov <= 13500:
        held.add("HAT_RIGHT")
    if 13500 <= pov <= 22500:
        held.add("HAT_DOWN")
    if 22500 <= pov <= 31500:
        held.add("HAT_LEFT")
    return held


def axis_sources(name, value, lo, hi):
    """An axis position past half deflection -> 'X+' / 'X-'. The range is the device's own."""
    if hi <= lo:
        return set()
    v = (value - lo) * 65535 // (hi - lo) - 32768
    if v > 16384:
        return {name + "+"}
    if v < -16384:
        return {name + "-"}
    return set()


def winmm_sources(buttons, nbuttons, pov, axes):
    """B1..Bn held, the hat and the axes past half deflection. axes: [(name, value, lo, hi)]"""
    held = {f"B{i + 1}" for i in range(min(max(nbuttons, 0), 32)) if buttons >> i & 1}
    held |= hat_sources(pov)
    for name, value, lo, hi in axes:
        held |= axis_sources(name, value, lo, hi)
    return held


def parse_hid_path(path):
    """'\\\\?\\HID#VID_045E&PID_028E&IG_00#...' -> (vid, pid, is_xinput); (0, 0, False) if it has no ids."""
    import re
    up = path.upper()
    m = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", up)
    if not m:
        return 0, 0, False
    return int(m.group(1), 16), int(m.group(2), 16), "&IG_" in up or "#IG_" in up


def xinput_hid_ids():
    """{(vid, pid)} of the HID devices Windows exposes through XInput as well. None: cannot tell."""
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetRawInputDeviceList.restype = ctypes.c_uint
        user32.GetRawInputDeviceList.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint), ctypes.c_uint]
        user32.GetRawInputDeviceInfoW.restype = ctypes.c_uint
        user32.GetRawInputDeviceInfoW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
                                                  ctypes.POINTER(ctypes.c_uint)]

        class RawList(ctypes.Structure):
            _fields_ = [("hDevice", ctypes.c_void_p), ("dwType", ctypes.c_uint32)]
        n = ctypes.c_uint(0)
        if user32.GetRawInputDeviceList(None, ctypes.byref(n), ctypes.sizeof(RawList)) == 0xFFFFFFFF:
            return None
        arr = (RawList * max(n.value, 1))()
        got = user32.GetRawInputDeviceList(arr, ctypes.byref(n), ctypes.sizeof(RawList))
        if got == 0xFFFFFFFF:
            return None
        ids = set()
        for i in range(got):
            if arr[i].dwType != 2:                          # RIM_TYPEHID
                continue
            size = ctypes.c_uint(0)
            user32.GetRawInputDeviceInfoW(arr[i].hDevice, 0x20000007, None, ctypes.byref(size))   # RIDI_DEVICENAME
            if not size.value:
                continue
            buf = ctypes.create_unicode_buffer(size.value + 1)
            if user32.GetRawInputDeviceInfoW(arr[i].hDevice, 0x20000007, buf, ctypes.byref(size)) == 0xFFFFFFFF:
                continue
            vid, pid, ig = parse_hid_path(buf.value)
            if ig:
                ids.add((vid, pid))
        return ids
    except (OSError, AttributeError):
        return None


class WinMMSource(PadSource):
    def __init__(self, hid_ids=xinput_hid_ids, covered=None):
        """covered(vid, pid): True for a device another source reads (the HID reader's PlayStation pads)."""
        self.dll = None
        self.devs = {}                  # joystick id -> dict(name, vid, pid, caps, nbuttons)
        self.skipped = {}               # joystick id -> (vid, pid): an XInput device seen through WinMM
        self.hid_ids = hid_ids
        self.covered = covered or (lambda vid, pid: False)
        self._load()

    def _load(self):
        if os.name != "nt":
            return
        try:
            self.dll = ctypes.WinDLL("winmm")
        except OSError:
            return

        class Caps(ctypes.Structure):
            _fields_ = [("wMid", ctypes.c_uint16), ("wPid", ctypes.c_uint16), ("szPname", ctypes.c_wchar * 32),
                        ("wXmin", ctypes.c_uint), ("wXmax", ctypes.c_uint), ("wYmin", ctypes.c_uint),
                        ("wYmax", ctypes.c_uint), ("wZmin", ctypes.c_uint), ("wZmax", ctypes.c_uint),
                        ("wNumButtons", ctypes.c_uint), ("wPeriodMin", ctypes.c_uint),
                        ("wPeriodMax", ctypes.c_uint), ("wRmin", ctypes.c_uint), ("wRmax", ctypes.c_uint),
                        ("wUmin", ctypes.c_uint), ("wUmax", ctypes.c_uint), ("wVmin", ctypes.c_uint),
                        ("wVmax", ctypes.c_uint), ("wCaps", ctypes.c_uint), ("wMaxAxes", ctypes.c_uint),
                        ("wNumAxes", ctypes.c_uint), ("wMaxButtons", ctypes.c_uint),
                        ("szRegKey", ctypes.c_wchar * 32), ("szOEMVxD", ctypes.c_wchar * 260)]

        class Info(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint32) for n in (
                "dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos", "dwUpos", "dwVpos", "dwButtons",
                "dwButtonNumber", "dwPOV", "dwReserved1", "dwReserved2")]
        self._Caps, self._Info = Caps, Info

    def scan(self):
        if self.dll is None:
            return
        xi_ids = None
        for jid in range(min(self.dll.joyGetNumDevs(), 16)):
            caps = self._Caps()
            ok = self.dll.joyGetDevCapsW(jid, ctypes.byref(caps), ctypes.sizeof(caps)) == 0
            if not ok:
                self.devs.pop(jid, None)
                self.skipped.pop(jid, None)
                continue
            ids = (caps.wMid, caps.wPid)
            known = self.devs.get(jid)
            if known is not None and (known["vid"], known["pid"], known["raw"]) == (ids[0], ids[1], caps.szPname):
                continue
            if jid in self.skipped and self.skipped[jid] == ids:
                continue
            self.devs.pop(jid, None)            # (another device took this number)
            self.skipped.pop(jid, None)
            if xi_ids is None:
                xi_ids = self.hid_ids()
            # A pad that XInput also reports is read there (its WinMM face has other button numbers).
            if (xi_ids is not None and ids in xi_ids) or (xi_ids is None and caps.wMid == padmap.VID_MICROSOFT):
                self.skipped[jid] = ids
                continue
            self.devs[jid] = dict(name=caps.szPname or f"joystick {jid + 1}", raw=caps.szPname, vid=caps.wMid,
                                  pid=caps.wPid, nbuttons=caps.wNumButtons, caps=caps)

    def read(self):
        out = []
        if self.dll is None:
            return out
        for jid in sorted(self.devs):
            d = self.devs[jid]
            if self.covered(d["vid"], d["pid"]):
                continue                    # read through HID (every report mode): not twice
            info = self._Info()
            info.dwSize = ctypes.sizeof(info)
            info.dwFlags = JOY_RETURNALL | JOY_RETURNPOVCTS
            if self.dll.joyGetPosEx(jid, ctypes.byref(info)) != 0:
                del self.devs[jid]          # unplugged
                continue
            caps = d["caps"]
            axes = [(name, getattr(info, pos), getattr(caps, lo), getattr(caps, hi))
                    for name, pos, lo, hi, flag in WINMM_AXES if not flag or caps.wCaps & flag]
            out.append(Device(DINPUT, f"winmm:{jid}", d["name"], d["vid"], d["pid"], None,
                              frozenset(winmm_sources(info.dwButtons, d["nbuttons"], info.dwPOV, axes))))
        return out


# ---------------------------------------------------------------------- PlayStation pads read directly (HID)
#
# DualShock 4 (054C:05C4, 054C:09CC), DualSense (054C:0CE6) and DualSense Edge (054C:0DF2), as the game reads
# them since 1.1.1 (ps3recomp patch 0042, pad_host_win32.c "PlayStation pads read directly"). Over Bluetooth a
# pad sends a short report 0x01 until a program asks it for more (Steam with "PlayStation Controller Support",
# DS4Windows, ...); from then on, until it is switched off, it sends its extended report (DS4 0x11, DualSense
# 0x31), which the HID descriptor calls vendor-defined: WinMM and DirectInput see the pad but never a button.
# So these pads are opened as HID devices and their input reports parsed here, in every mode:
#
#   ID       pad, link       layout ([0] = report ID)
#   0x01     DS4 USB / BT simple, DS BT simple   [1..4] LX LY RX RY  [5..7] buttons  [8] L2  [9] R2
#   0x11-19  DS4 BT extended   [1] flags (0x80: input data)  [3..6] sticks  [7..9] buttons  [10] L2  [11] R2
#   0x01     DS USB            [1..4] sticks  [5] L2  [6] R2  [8..10] buttons
#   0x31     DS BT extended    [2..5] sticks  [6] L2  [7] R2  [9..11] buttons
#
# Buttons: byte 0 = hat (low nibble, 0 = up clockwise to 7, 8 = centred) + square cross circle triangle; byte 1 =
# L1 R1 L2 R2 share options L3 R3; byte 2 = PS, touchpad, mute (DualSense full reports), Edge Fn/paddles in bits
# 4-7. Bluetooth extended reports end in a CRC-32 of 0xA1 + the report. The result has the names DirectInput
# gives the pad (B1..B14 in that order, B15 mute, B16..B19 the Edge's, HAT_*, X Y = left stick, Z RZ = right
# stick, RX RY = L2 R2), so controls.ini's [dinput] / [dinput.054C:0CE6] / dinput:... pins apply as in the game.
#
# Nothing is ever sent to a pad: no output report, no feature report (asking for one is what switches a
# Bluetooth pad to its extended report), not even the product string. The device is opened for reading with
# read and write sharing (never exclusive), so the game and other programs read it at the same time, and only
# while the launcher is in front (closed again when it leaves the front). A pad Steam Input hands to programs as
# a virtual Xbox pad (Steam started the launcher with Steam Input on and lists it) is left to that pad while one
# is there, as the game does; a pad read here is not read through WinMM as well.

PS_VID = 0x054C
PS_MODELS = {0x05C4: "ds4", 0x09CC: "ds4", 0x0CE6: "dualsense", 0x0DF2: "edge"}
PS_MODEL_NAMES = {"ds4": "DualShock 4", "dualsense": "DualSense", "edge": "DualSense Edge"}
PS_FAKE_PIDS = {"ds4": 0x09CC, "dualsense": 0x0CE6, "edge": 0x0DF2}
BT_HID_UUID = "00001124-0000-1000-8000-00805f9b34fb"     # the Bluetooth HID profile, in a Bluetooth pad's path
CRC_RUN_NEVER_GOOD, CRC_RUN_WAS_GOOD = 25, 200           # as the game: when bad CRCs are used anyway
_HAT_DIRS = (("UP",), ("UP", "RIGHT"), ("RIGHT",), ("RIGHT", "DOWN"), ("DOWN",), ("DOWN", "LEFT"), ("LEFT",),
             ("LEFT", "UP"))


def ps_model(vid, pid):
    """'ds4' / 'dualsense' / 'edge' for a PlayStation pad the game reads directly, else None."""
    return PS_MODELS.get(pid) if vid == PS_VID else None


def ps_crc_len(model, rid):
    """Length of a Bluetooth extended report (its last 4 bytes are the CRC); 0 = a report without one."""
    if model == "ds4" and 0x11 <= rid <= 0x19:
        return 547 if rid == 0x19 else 78 + 64 * (rid - 0x11)
    if model in ("dualsense", "edge") and rid == 0x31:
        return 78
    return 0


def ps_crc_ok(model, data):
    """True / False: the report's CRC is right / wrong; None: nothing to check."""
    import zlib
    n = ps_crc_len(model, data[0]) if data else 0
    if not n or len(data) < n:
        return None
    return zlib.crc32(bytes(data[:n - 4]), zlib.crc32(b"\xA1")) & 0xFFFFFFFF == int.from_bytes(data[n - 4:n], "little")


class CrcGate:
    """Reports with a wrong CRC: dropped once the pad has sent a good one (a damaged report is input nobody gave),
    unless 200 come in a row; used when 25 came and never a good one (pads that do not fill it in)."""

    def __init__(self):
        self.good = self.bad = self.run = 0
        self.lenient = False

    def passes(self, ok):
        if ok is None:
            return True
        if ok:
            self.good += 1
            self.run = 0
            self.lenient = False
            return True
        self.bad += 1
        self.run += 1
        if self.run >= (CRC_RUN_WAS_GOOD if self.good else CRC_RUN_NEVER_GOOD):
            self.lenient = True
        return self.lenient


def _ps_sources(st, b, b2mask, l2, r2):
    held = set()
    h = b[0] & 0x0F
    if h < 8:
        held |= {"HAT_" + d for d in _HAT_DIRS[h]}
    x = b[2] & b2mask
    bits = (b[0] >> 4) | (b[1] << 4) | ((x & 7) << 12) | ((x >> 4) << 15)
    held |= {f"B{i + 1}" for i in range(19) if bits >> i & 1}
    for name, v in (("X", st[0]), ("Y", st[1]), ("Z", st[2]), ("RZ", st[3]), ("RX", l2), ("RY", r2)):
        a = v * 257 - 32768
        if a > 16384:
            held.add(name + "+")
        elif a < -16384:
            held.add(name + "-")
    return held


def ps_parse(model, bt, data):
    """One input report of a pad of `model` (as ReadFile hands it over: padded to the device's longest report)
    -> (mode, held sources), mode 'usb' / 'bt-simple' / 'bt-ext'; (None, None) for a report without input.
    bt: True on Bluetooth, False on USB, None not known (then a 64-byte report is a USB one)."""
    p = bytes(data)
    n = len(p)
    if n < 10:
        return None, None
    rid = p[0]
    simple = bt is True or (bt is None and n != 64)
    if model == "ds4":
        if rid == 0x01:
            return ("bt-simple" if simple else "usb"), _ps_sources(p[1:5], p[5:8], 0x03, p[8], p[9])
        if 0x11 <= rid <= 0x19 and n >= 12 and p[1] & 0x80:
            return "bt-ext", _ps_sources(p[3:7], p[7:10], 0x03, p[10], p[11])
        return None, None
    if model in ("dualsense", "edge"):
        full = 0xF7 if model == "edge" else 0x07
        if rid == 0x01:
            if simple:
                return "bt-simple", _ps_sources(p[1:5], p[5:8], 0x03, p[8], p[9])
            return "usb", _ps_sources(p[1:5], p[8:11], full, p[5], p[6])
        if rid == 0x31 and n >= 12:
            return "bt-ext", _ps_sources(p[2:6], p[9:12], full, p[6], p[7])
    return None, None


def ps_neutral():
    """What a pad at rest holds (before its first report): the triggers at their end, nothing else."""
    return frozenset({"RX-", "RY-"})


def _vidpid_list(value):
    """SDL's "0xAAAA/0xBBBB,..." (Steam sets it; "@file" = read from that file) -> {(vid, pid)}, or None if unset."""
    if not value:
        return None
    text = value
    if value.startswith("@"):
        try:
            with open(value[1:], encoding="latin-1") as f:
                text = f.read(4096)
        except OSError:
            text = ""
    out = set()
    for tok in text.replace(",", " ").split():
        a, _, b = tok.partition("/")
        try:
            v, p = int(a, 16), int(b, 16)
        except ValueError:
            continue
        if 0 <= v <= 0xFFFF and 0 <= p <= 0xFFFF:
            out.add((v, p))
    return out


def steam_virtual_ids(path):
    """{(vid, pid)} of the real pads behind Steam's virtual pads (the SteamVirtualGamepadInfo file)."""
    out, vid, pid = set(), None, None
    if not path:
        return out
    try:
        with open(path, encoding="latin-1") as f:
            for raw in f:
                s = raw.strip()
                if s.startswith("["):
                    vid = pid = None
                    continue
                k, _, v = s.partition("=")
                try:
                    if k.strip().upper() == "VID":
                        vid = int(v.strip(), 0)
                    elif k.strip().upper() == "PID":
                        pid = int(v.strip(), 0)
                    else:
                        continue
                except ValueError:
                    continue
                if vid is not None and pid is not None:
                    out.add((vid, pid))
    except OSError:
        pass
    return out


def steam_lists(vid, pid, env=None):
    """Does Steam hand programs a virtual pad for this one and ask them to leave it alone? (SDL's variables,
    which Steam sets for a program it starts with Steam Input on, and its virtual pad list.)"""
    env = os.environ if env is None else env
    ignore = _vidpid_list(env.get("SDL_GAMECONTROLLER_IGNORE_DEVICES"))
    if ignore and (vid, pid) in ignore:
        return True
    except_ = _vidpid_list(env.get("SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT"))
    if except_ and (vid, pid) not in except_:
        return True
    return (vid, pid) in steam_virtual_ids(env.get("SteamVirtualGamepadInfo"))


HidInfo = namedtuple("HidInfo", "path vid pid model bt in_len")


class _Win32Hid:
    """The few Windows calls the HID source needs (setupapi, hid.dll, kernel32), ctypes only. Enumerating opens a
    device with no access at all (reads nothing); reading opens it for reading, shared, overlapped."""

    GENERIC_READ = 0x80000000
    FILE_SHARE_RW = 0x1 | 0x2
    OPEN_EXISTING = 3
    FILE_FLAG_OVERLAPPED = 0x40000000
    INVALID = ctypes.c_void_p(-1).value
    ERROR_IO_PENDING, ERROR_IO_INCOMPLETE = 997, 996

    def __init__(self):
        from ctypes import wintypes as w
        self.w = w
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.hid = ctypes.WinDLL("hid")
        self.sa = ctypes.WinDLL("setupapi", use_last_error=True)

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                        ("Data4", ctypes.c_uint8 * 8)]

        class IfData(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint32), ("InterfaceClassGuid", GUID), ("Flags", ctypes.c_uint32),
                        ("Reserved", ctypes.c_size_t)]

        class Attrs(ctypes.Structure):
            _fields_ = [("Size", ctypes.c_uint32), ("VendorID", ctypes.c_uint16), ("ProductID", ctypes.c_uint16),
                        ("VersionNumber", ctypes.c_uint16)]

        class Caps(ctypes.Structure):
            _fields_ = [("Usage", ctypes.c_uint16), ("UsagePage", ctypes.c_uint16),
                        ("InputReportByteLength", ctypes.c_uint16), ("OutputReportByteLength", ctypes.c_uint16),
                        ("FeatureReportByteLength", ctypes.c_uint16), ("Reserved", ctypes.c_uint16 * 17),
                        ("Rest", ctypes.c_uint16 * 10)]

        class Overlapped(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t), ("Offset", ctypes.c_uint32),
                        ("OffsetHigh", ctypes.c_uint32), ("hEvent", ctypes.c_void_p)]

        self.GUID, self.IfData, self.Attrs, self.Caps, self.Overlapped = GUID, IfData, Attrs, Caps, Overlapped
        k, h, s = self.k32, self.hid, self.sa
        k.CreateFileW.restype = ctypes.c_void_p
        k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.c_void_p]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.CreateEventW.restype = ctypes.c_void_p
        k.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
        k.ResetEvent.argtypes = [ctypes.c_void_p]
        k.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        k.GetOverlappedResult.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(w.DWORD), w.BOOL]
        k.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        h.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
        h.HidD_GetAttributes.argtypes = [ctypes.c_void_p, ctypes.POINTER(Attrs)]
        h.HidD_GetAttributes.restype = ctypes.c_ubyte
        h.HidD_GetPreparsedData.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        h.HidD_GetPreparsedData.restype = ctypes.c_ubyte
        h.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
        h.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(Caps)]
        h.HidP_GetCaps.restype = ctypes.c_long
        h.HidD_SetNumInputBuffers.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        s.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        s.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), w.LPCWSTR, ctypes.c_void_p, w.DWORD]
        s.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), w.DWORD,
                                                  ctypes.POINTER(IfData)]
        s.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(IfData), ctypes.c_void_p,
                                                       w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
        s.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

    def enumerate(self):
        """[HidInfo] of the PlayStation pads' game pad collections now present."""
        return [i for i in (self._probe(p) for p in self.paths()) if i is not None]

    def paths(self):
        """The device paths of every HID collection now present."""
        out = []
        g = self.GUID()
        self.hid.HidD_GetHidGuid(ctypes.byref(g))
        devs = self.sa.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x2 | 0x10)   # PRESENT | DEVICEINTERFACE
        if not devs or devs == self.INVALID:
            return out
        try:
            for i in range(256):
                ifd = self.IfData()
                ifd.cbSize = ctypes.sizeof(ifd)
                if not self.sa.SetupDiEnumDeviceInterfaces(devs, None, ctypes.byref(g), i, ctypes.byref(ifd)):
                    break
                need = self.w.DWORD(0)
                self.sa.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
                if not need.value or need.value > 4096:
                    continue
                buf = ctypes.create_string_buffer(need.value + 4)
                ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6   # cbSize
                if not self.sa.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(ifd), buf, need.value, None, None):
                    continue
                out.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
        finally:
            self.sa.SetupDiDestroyDeviceInfoList(devs)
        return out

    def _probe(self, path):
        f = self.k32.CreateFileW(path, 0, self.FILE_SHARE_RW, None, self.OPEN_EXISTING, 0, None)   # no access asked
        if not f or f == self.INVALID:
            return None
        try:
            at = self.Attrs()
            at.Size = ctypes.sizeof(at)
            if not self.hid.HidD_GetAttributes(f, ctypes.byref(at)):
                return None
            model = ps_model(at.VendorID, at.ProductID)
            if not model:
                return None
            pp = ctypes.c_void_p()
            if not self.hid.HidD_GetPreparsedData(f, ctypes.byref(pp)):   # the report descriptor Windows already has
                return None
            caps = self.Caps()
            try:
                ok = self.hid.HidP_GetCaps(pp, ctypes.byref(caps)) == 0x00110000
            finally:
                self.hid.HidD_FreePreparsedData(pp)
            if not ok or caps.UsagePage != 0x01 or caps.Usage not in (0x04, 0x05):     # the game pad collection
                return None
            low = path.lower()
            bt = True if BT_HID_UUID in low else False if "hid#vid_" in low else None
            return HidInfo(path, at.VendorID, at.ProductID, model, bt, caps.InputReportByteLength or 64)
        finally:
            self.k32.CloseHandle(f)

    def open(self, info):
        """A reader of the pad's input reports, or None when it cannot be opened (an exclusive owner)."""
        h = self.k32.CreateFileW(info.path, self.GENERIC_READ, self.FILE_SHARE_RW, None, self.OPEN_EXISTING,
                                 self.FILE_FLAG_OVERLAPPED, None)
        if not h or h == self.INVALID:
            return None
        self.hid.HidD_SetNumInputBuffers(h, 64)        # room for a poll's worth of reports (our handle's queue only)
        return _Win32Reader(self, h, max(int(info.in_len), 10))


class _Win32Reader:
    """One open pad: reads() hands over every report that came since the last call, never waits."""

    def __init__(self, api, handle, in_len):
        self.api, self.h, self.n = api, handle, in_len
        self.buf = ctypes.create_string_buffer(in_len)
        self.ov = api.Overlapped()
        self.ov.hEvent = api.k32.CreateEventW(None, True, False, None)
        self.pending = False
        self.failed = False

    def reads(self, limit=128):
        k, out = self.api.k32, []
        got = self.api.w.DWORD(0)
        for _ in range(limit):
            if not self.pending:
                k.ResetEvent(self.ov.hEvent)
                if not k.ReadFile(self.h, self.buf, self.n, None, ctypes.byref(self.ov)):
                    if ctypes.get_last_error() != self.api.ERROR_IO_PENDING:
                        self.failed = True
                        break
                self.pending = True
            if not k.GetOverlappedResult(self.h, ctypes.byref(self.ov), ctypes.byref(got), False):
                if ctypes.get_last_error() != self.api.ERROR_IO_INCOMPLETE:
                    self.pending = False
                    self.failed = True
                break                           # nothing more yet
            self.pending = False
            out.append(self.buf.raw[:got.value])
        return out

    def close(self):
        k = self.api.k32
        if self.pending:
            k.CancelIoEx(self.h, ctypes.byref(self.ov))
            got = self.api.w.DWORD(0)
            k.GetOverlappedResult(self.h, ctypes.byref(self.ov), ctypes.byref(got), True)   # let go of buf and ov
            self.pending = False
        k.CloseHandle(self.h)
        k.CloseHandle(self.ov.hEvent)


class FakeHid:
    """PS3_PAD_HID_FAKE=<ds4|dualsense|edge>,<usb|bt>,<file> -- the game's test pad: input reports in hex, one per
    line, appended to the file ('#' starts a comment); every line added since the last read is a report, padded
    as Windows pads them. The file gone = unplugged. With it no real pad is touched (as in the game)."""

    def __init__(self, spec):
        parts = spec.split(",", 2)
        self.ok = len(parts) == 3 and parts[0].lower() in PS_FAKE_PIDS and parts[1].lower() in ("usb", "bt")
        if not self.ok:
            return
        self.model, self.bt, self.path = parts[0].lower(), parts[1].lower() == "bt", parts[2]
        self.in_len = (547 if self.model == "ds4" else 78) if self.bt else 64

    def enumerate(self):
        if not self.ok or not os.path.isfile(self.path):
            return []
        return [HidInfo("fake:" + self.path, PS_VID, PS_FAKE_PIDS[self.model], self.model, self.bt, self.in_len)]

    def open(self, info):
        return _FakeReader(self.path, self.in_len)


class _FakeReader:
    def __init__(self, path, in_len):
        self.path, self.n, self.off, self.failed = path, in_len, 0, False
        try:
            self.off = os.path.getsize(path)     # opened now: older reports are history, as with a real pad
        except OSError:
            self.failed = True

    def reads(self, limit=4096):
        try:
            with open(self.path, "rb") as f:
                size = os.fstat(f.fileno()).st_size
                if size < self.off:
                    self.off = 0                 # written anew
                f.seek(self.off)
                data = f.read()
        except OSError:
            self.failed = True
            return []
        end = data.rfind(b"\n") + 1              # complete lines only
        self.off += end
        out = []
        for line in data[:end].splitlines()[:limit]:
            hexs = line.split(b"#", 1)[0].decode("latin-1")
            try:
                rep = bytes.fromhex("".join(hexs.split()))
            except ValueError:
                continue
            if rep:
                out.append(rep[:self.n] + bytes(max(0, self.n - len(rep))))
        return out

    def close(self):
        pass


class HidSource(PadSource):
    """DualShock 4 / DualSense / DualSense Edge read as HID devices (see above). Devices are DirectInput-class for
    controls.ini (kind DINPUT, the pad's USB ids), keyed by their HID path. A device's held sources are the newest
    report's plus everything that was down in any report since the last read (a tap between two polls counts)."""

    def __init__(self, api=None, env=None, xinput_present=None):
        self.env = os.environ if env is None else env
        if api is None:
            fake = self.env.get("PS3_PAD_HID_FAKE")
            try:
                api = FakeHid(fake) if fake else (_Win32Hid() if os.name == "nt" else None)
            except (OSError, AttributeError):        # no hid.dll / setupapi.dll: the pads stay with WinMM
                api = None
        self.api = api
        self.xinput_present = xinput_present or (lambda: False)
        self.on = True                  # [general] hid (follows dinput, as in the game)
        self.steam_input = True         # [general] steam_input
        self.pads = {}                  # path -> dict(info, reader, gate, held, taps, mode)
        self.skipped = set()            # paths left to Steam Input / that could not be opened, until unplugged
        self.notes = []                 # what happened, for a log or a test

    def configure(self, controls):
        self.on = bool(getattr(controls, "use_hid", True))
        self.steam_input = bool(getattr(controls, "steam_input", True))
        if not self.on:
            self.pause()

    def covers(self, vid, pid):
        """True when a pad with these USB ids is read here (WinMM then leaves it alone)."""
        return any(p["info"].vid == vid and p["info"].pid == pid for p in self.pads.values())

    def scan(self):
        if self.api is None or not self.on:
            return
        try:
            found = {i.path: i for i in self.api.enumerate()}
        except OSError:
            return
        for path in list(self.pads):
            if path not in found:
                self._drop(path, "unplugged")
        self.skipped &= set(found)
        for path, info in found.items():
            if path in self.pads or path in self.skipped:
                continue
            if self.steam_input and steam_lists(info.vid, info.pid, self.env) and self.xinput_present():
                self.skipped.add(path)
                self.notes.append(("steam", path))
                continue
            reader = self.api.open(info)
            if reader is None:
                self.skipped.add(path)
                self.notes.append(("open_failed", path))
                continue
            self.pads[path] = dict(info=info, reader=reader, gate=CrcGate(), held=ps_neutral(), taps=set(), mode=None)
            self.notes.append(("open", path))

    def _drop(self, path, why):
        p = self.pads.pop(path, None)
        if p is not None:
            try:
                p["reader"].close()
            except OSError:
                pass
            self.notes.append((why, path))

    def pause(self):
        """Not read for a while (the launcher left the front): close every pad; scan() opens them again."""
        for path in list(self.pads):
            self._drop(path, "closed")
        self.skipped.clear()

    def read(self):
        out = []
        for path in list(self.pads):
            p = self.pads[path]
            info = p["info"]
            reports = p["reader"].reads()
            if p["reader"].failed:
                self._drop(path, "gone")
                continue
            for rep in reports:
                if not p["gate"].passes(ps_crc_ok(info.model, rep)):
                    continue
                mode, held = ps_parse(info.model, info.bt, rep)
                if mode is None:
                    continue
                p["mode"] = mode
                p["held"] = frozenset(held)
                p["taps"] |= held
            pressed = p["held"] | frozenset(p["taps"])
            p["taps"] = set()
            link = "Bluetooth" if info.bt else "USB" if info.bt is False else ("Bluetooth" if info.in_len > 64 else "USB")
            out.append(Device(DINPUT, "hid:" + path, f"{PS_MODEL_NAMES[info.model]} ({link})", info.vid, info.pid,
                              None, pressed))
        return out


# ---------------------------------------------------------------------- the keyboard (Controls window only)

# Keys the Controls window never reports: the mouse buttons (VK 1 2 4 5 6) and Cancel, the generic Shift / Ctrl /
# Alt (their left and right keys are reported, the names the game uses), the Windows keys.
KEY_SKIP = frozenset((0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x10, 0x11, 0x12, 0x5B, 0x5C, 0xE7, 0xFF))


class KeyboardSource(PadSource):
    """The keyboard as the game reads it (GetAsyncKeyState), for the Controls window -- never for the Online tab's
    navigation, where the keyboard works the window as usual. One device per keyboard player of the game: the
    [keys1] one, and the [keys2] one when that section binds anything. Read only while the window is in front
    (DevicePoller's rule), so no key typed into another program is ever seen."""

    def __init__(self, get_state=None):
        self.get_state = get_state
        if self.get_state is None and os.name == "nt":
            try:
                user32 = ctypes.WinDLL("user32")
                user32.GetAsyncKeyState.restype = ctypes.c_short
                user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
                self.get_state = user32.GetAsyncKeyState
            except (OSError, AttributeError):
                self.get_state = None
        self.second = False

    def configure(self, controls):
        try:
            self.second = bool(controls.table(KEYS2).binds)
        except Exception:               # noqa: BLE001 -- a file the parser cannot read: one keyboard player
            self.second = False

    def held(self):
        if self.get_state is None:
            return frozenset()
        return frozenset(padmap.key_name(vk) for vk in range(1, 255)
                         if vk not in KEY_SKIP and self.get_state(vk) & 0x8000)

    def read(self):
        if self.get_state is None:
            return []
        held = self.held()
        out = [Device(KEYS1, KEYS1, t("Keyboard"), 0, 0, None, held)]
        if self.second:
            out.append(Device(KEYS2, KEYS2, t("Keyboard, second player"), 0, 0, None, held))
        return out


class FileSource(PadSource):
    """T5_PAD_FILE: one virtual pad holding the sources named in a file. 'A B' = an XInput pad with A and
    B held; 'dinput B2' or 'dinput:054C:09CC B2' = a DirectInput-style stick; 'keys Q E' = the keyboard (its
    [keys1] player). Read at every poll."""

    def __init__(self, path):
        self.path = path

    def read(self):
        try:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                toks = f.read().split()
        except OSError:
            toks = []
        kind, vid, pid = XINPUT, 0, 0
        if toks and toks[0].lower().startswith("dinput"):
            kind = DINPUT
            parts = toks.pop(0).split(":")
            if len(parts) == 3:
                try:
                    vid, pid = int(parts[1], 16), int(parts[2], 16)
                except ValueError:
                    pass
        elif toks and toks[0].lower().startswith("xinput"):
            toks.pop(0)
        elif toks and toks[0].lower() in ("keys", KEYS1, KEYS2):
            kind = KEYS2 if toks.pop(0).lower() == KEYS2 else KEYS1
        held = {padmap.canon_source(kind, t) for t in toks}
        held.discard(None)
        key = kind if kind in KEYS else "file"
        return [Device(kind, key, "scripted pad (T5_PAD_FILE)", vid, pid, 0 if kind == XINPUT else None,
                       frozenset(held))]


def default_sources(env=None, keyboard=False):
    """The sources for this PC: physical pads, or the T5_PAD_FILE pad (physical pads only with T5_PAD_DEVICES=1).
    In the game's order: XInput, the PlayStation pads read directly, then WinMM (without those). keyboard: the
    keyboard too (the Controls window; the Online tab never reads it)."""
    env = os.environ if env is None else env
    out = []
    f = env.get("T5_PAD_FILE")
    if f:
        out.append(FileSource(f))
    if os.name == "nt" and (not f or env.get("T5_PAD_DEVICES") == "1"):
        xi = XInputSource()
        hid = HidSource(env=env, xinput_present=lambda: bool(xi.slots))
        out += [xi, hid, WinMMSource(covered=hid.covers)]
        if keyboard:
            out.append(KeyboardSource())
    return out


# ---------------------------------------------------------------------- the foreground rule

def window_foreground_check(hwnd):
    """True while `hwnd` (a top-level window) is the foreground window. A dialog of the same program is
    another window, so while one is open the launcher's window is not 'in front' either. Safe to call from
    any thread: it holds only the number."""
    if os.name != "nt" or not hwnd:
        return lambda: False
    user32 = ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    return lambda: user32.GetForegroundWindow() == hwnd


def toplevel_hwnd(widget):
    """The top-level window handle of a Tk widget (call on the Tk thread); 0 when unknown."""
    if os.name != "nt":
        return 0
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        return user32.GetAncestor(widget.winfo_id(), 2) or 0           # GA_ROOT
    except Exception:                   # noqa: BLE001 -- no window handle: the foreground rule then says no
        return 0


# ---------------------------------------------------------------------- the navigator

class PadNav:
    def __init__(self, sources, controls=None, foreground=None, arm_s=ARM_S, clock=time.monotonic, hz=POLL_HZ,
                 scan_s=SCAN_S):
        self.sources = list(sources)
        self.controls_file = controls or padmap.ControlsFile(lambda: None)
        self.foreground = foreground or (lambda: True)
        self.arm_s = arm_s
        self.clock = clock
        self.hz = hz
        self.scan_s = scan_s
        self.events = queue.SimpleQueue()       # PadEvent, for the Tk thread
        self.enabled = True                     # set from any thread
        self.visible = True                     # the Online tab is showing (set by the Tk thread)
        self.generation = 0                     # grows when the devices or the labels change
        self.devices = []                       # [(Device, port)] as of the last poll
        self.labels = {}                        # button -> "A" / "B2/B5" for the device used last
        self.summary = ""
        self.error = ""
        self.stats = dict(steps=0, polls=0, events=0, busy_s=0.0, started=None)
        self._up_since = {b: None for b in BUTTONS}
        self._active = False
        self._next_scan = 0.0
        self._ports = padmap.PortMap(self.controls_file.controls)
        self._last_held = {}                    # device key -> sources held at the last poll
        self._active_key = None
        self._maps = {}                         # device key -> {source: button}
        self._labels_for = None                 # the Controls the labels were made from
        self._thread = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ the thread
    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=_run, args=(self,), name="padnav", daemon=True)
        self._thread.start()

    def stop(self, wait=1.0):
        t, self._thread = self._thread, None
        self._stop.set()
        if t is not None and t is not threading.current_thread():
            t.join(wait)

    # ------------------------------------------------------------------ one poll
    def step(self, now):
        """One cycle. Returns None to be called again at the poll rate, or the seconds to wait."""
        self.stats["steps"] += 1
        try:
            front = bool(self.foreground())
        except Exception:               # noqa: BLE001 -- a window that is gone is not in front
            front = False
        if not (self.enabled and front and self.visible):
            if self._active:
                self._forget()
            return IDLE_S
        if not self._active:
            self._active = True
            self._next_scan = 0.0
        if now >= self._next_scan:
            self._scan(now)
        devices = self._read()
        self.stats["polls"] += 1
        down, sources = self._buttons_down(devices)
        pressed_now = []
        for b in BUTTONS:
            if b in down:
                if self._up_since[b] is not None and now - self._up_since[b] >= self.arm_s:
                    pressed_now.append(b)
                self._up_since[b] = None            # held: it must be let go again before it can count
            elif self._up_since[b] is None:
                self._up_since[b] = now
        if len(pressed_now) == 1:                   # two at once is a chord, not a press
            b = pressed_now[0]
            self.events.put(PadEvent(b, now, self._active_key, sources.get(b)))
            self.stats["events"] += 1
        return None

    def _forget(self):
        """The launcher left the front (or the tab was hidden): no button is known to be up any more, and no
        device stays open."""
        self._active = False
        self._up_since = {b: None for b in BUTTONS}
        self._last_held = {}
        for s in self.sources:
            try:
                s.pause()
            except Exception as e:      # noqa: BLE001
                self.error = f"{type(s).__name__}.pause: {e}"

    def _scan(self, now):
        self._next_scan = now + self.scan_s
        controls = self.controls_file.refresh()
        for s in self.sources:
            try:
                s.configure(controls)
                s.scan()
            except Exception as e:      # noqa: BLE001
                self.error = f"{type(s).__name__}.scan: {e}"

    def _read(self):
        devices = []
        for s in self.sources:
            try:
                devices += s.read()
            except Exception as e:      # noqa: BLE001
                self.error = f"{type(s).__name__}.read: {e}"
        controls = self.controls_file.controls
        ports = self._ports.update(devices, controls)
        devices = [d for d in devices if self._ports.reads(d.key)]
        if [d.key for d in devices] != [d.key for d, _p in self.devices]:
            # A pad was plugged in or unplugged: a button it holds right now was not seen going up.
            self._up_since = {b: None for b in BUTTONS}
            self._last_held = {}
        sig = [(d.key, ports.get(d.key)) for d in devices]
        if sig != [(d.key, p) for d, p in self.devices] or self._labels_for != controls:
            self.devices = [(d, ports[d.key]) for d in devices]
            self._labels_for = controls
            self._maps = {}
            self._set_labels()
        return devices

    def _map_of(self, d, port):
        """{source: button} for this device: the sources that are exactly Cross / Circle / Triangle."""
        m = self._maps.get(d.key)
        if m is None:
            faces = self.controls_file.controls.face_sources(d.kind, port, d.vid, d.pid)
            m = {src: b for b, srcs in faces.items() for src in srcs}
            self._maps[d.key] = m
        return m

    def _buttons_down(self, devices):
        down, sources = set(), {}
        ports = dict((d.key, p) for d, p in self.devices)
        for d in devices:
            held = d.pressed
            if held - self._last_held.get(d.key, frozenset()) and self._active_key != d.key:
                self._active_key = d.key            # the pad used last supplies the button names
                self._set_labels()
            self._last_held[d.key] = held
            m = self._map_of(d, ports.get(d.key, -1))
            for src in held:
                b = m.get(src)
                if b:
                    down.add(b)
                    sources.setdefault(b, src)
        return down, sources

    def _set_labels(self):
        devs = [(d, p) for d, p in self.devices]
        pick = next((x for x in devs if x[0].key == self._active_key), devs[0] if devs else None)
        labels, summary = {}, ""
        if pick:
            d, port = pick
            faces = self.controls_file.controls.face_sources(d.kind, port, d.vid, d.pid)
            for b, srcs in faces.items():
                if srcs:
                    labels[b] = "/".join(srcs[:2])
            summary = f"{d.name}: " + ", ".join(f"{b.capitalize()} = {labels[b]}" for b in BUTTONS if b in labels)
            if len(devs) > 1:
                summary += " " + t("(+{count} more)", count=len(devs) - 1)
        if labels != self.labels or summary != self.summary:
            self.labels, self.summary = labels, summary
            self.generation += 1
        elif self.generation == 0 and devs:
            self.generation += 1

    # ------------------------------------------------------------------ for the UI
    def label(self, button):
        """The name of the controller button for this action ('A', 'B2'), or None without a pad."""
        return self.labels.get(button) if self.devices else None

    def has_devices(self):
        return bool(self.devices)

    def foreground_now(self):
        try:
            return bool(self.foreground())
        except Exception:               # noqa: BLE001
            return False


def _run(nav):
    """The polling thread. Holds the navigator only: no Tk object, no reference to the UI."""
    nav.stats["started"] = time.monotonic()
    period = 1.0 / nav.hz
    due = nav.clock()
    while not nav._stop.is_set():
        t0 = time.perf_counter()
        try:
            wait = nav.step(nav.clock())
        except Exception as e:           # noqa: BLE001 -- the thread must outlive a bad device
            nav.error = f"step: {e}"
            wait = 0.5
        nav.stats["busy_s"] += time.perf_counter() - t0      # (thread CPU time is too coarse on Windows)
        if wait is None:
            due += period
            now = nav.clock()
            if due < now:                # fell behind (a stall): do not catch up with a burst
                due = now + period
            wait = due - now
        else:
            due = nav.clock() + wait
        time.sleep(max(wait, 0.0))       # (Event.wait rounds up to the 15.6 ms timer tick; sleep does not, on 3.11+)
