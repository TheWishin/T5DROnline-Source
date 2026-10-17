"""Controller navigation for the launcher: A / Cross accepts, B / Circle declines, without mouse or keyboard.

A background thread reads the pads at ~60 Hz and turns presses of the three face buttons
(Cross, Circle, Triangle) into events for the Tk thread, which drains `PadNav.events` from its own
timer. Nothing here touches Tk, so no Tcl object can be released from this thread.

Devices (ctypes only, no packages):
  XInput   Xbox pads and XInput-mode arcade sticks.
  WinMM    every other game controller (PS3/PS4-mode sticks and hitboxes, DualShock 4, generic USB
           pads) through joyGetPosEx. The game reads these through DirectInput; WinMM has the same
           button order (B1..B32) and hat, needs no COM, and is plain ctypes. Devices Windows also
           exposes through XInput are skipped (their HID path has "IG_").
Which button is Cross is the game's own controls.ini (padmap.py): a remapped stick works the same in
the launcher and in the game.

Rules (the point of this module):
* Only while the launcher's window is the foreground window. While anything else is in front -- the
  game above all -- nothing is read at all (no device polling) and every button is forgotten.
* A press counts only after the button was up for `arm_s` (0.3 s) with the launcher in front. A button
  that is held when the window comes forward, or that is mashed (up for less than that between two
  presses), never fires. So the end of a fight does nothing in the launcher.
* Two face buttons pressed in the same instant are no press at all.

Test hook: T5_PAD_FILE=<file> makes a virtual pad of the buttons named in the file (the held
sources, e.g. "A", or "dinput B2"); with it, physical pads are ignored (T5_PAD_DEVICES=1: both).
T5_PAD_NAV=0 turns the whole feature off.
"""
import ctypes
import os
import queue
import threading
import time
from collections import namedtuple

from . import padmap
from .padmap import DINPUT, XINPUT

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
    devices known after the last scan, each with the set of sources held right now."""

    def scan(self):
        pass

    def read(self):
        return []


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
    def __init__(self, hid_ids=xinput_hid_ids):
        self.dll = None
        self.devs = {}                  # joystick id -> dict(name, vid, pid, caps, nbuttons)
        self.skipped = {}               # joystick id -> (vid, pid): an XInput device seen through WinMM
        self.hid_ids = hid_ids
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


class FileSource(PadSource):
    """T5_PAD_FILE: one virtual pad holding the sources named in a file. 'A B' = an XInput pad with A and
    B held; 'dinput B2' or 'dinput:054C:09CC B2' = a DirectInput-style stick. Read at every poll."""

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
        held = {padmap.canon_source(kind, t) for t in toks}
        held.discard(None)
        return [Device(kind, "file", "scripted pad (T5_PAD_FILE)", vid, pid, 0 if kind == XINPUT else None,
                       frozenset(held))]


def default_sources(env=None):
    """The sources for this PC: physical pads, or the T5_PAD_FILE pad (physical pads only with T5_PAD_DEVICES=1)."""
    env = os.environ if env is None else env
    out = []
    f = env.get("T5_PAD_FILE")
    if f:
        out.append(FileSource(f))
    if os.name == "nt" and (not f or env.get("T5_PAD_DEVICES") == "1"):
        out += [XInputSource(), WinMMSource()]
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
        """The launcher left the front (or the tab was hidden): no button is known to be up any more."""
        self._active = False
        self._up_since = {b: None for b in BUTTONS}
        self._last_held = {}

    def _scan(self, now):
        self._next_scan = now + self.scan_s
        self.controls_file.refresh()
        for s in self.sources:
            try:
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
                summary += f" (+{len(devs) - 1} more)"
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
