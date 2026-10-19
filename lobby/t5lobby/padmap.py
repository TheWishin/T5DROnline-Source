"""controls.ini for the launcher: which controller button is Cross, Circle, Triangle.

The game reads its pads through ps3recomp's host input layer (patch 0009,
libs/input/pad_host_win32.c, documented in docs/controls.ini). The launcher must agree with
it: a stick whose buttons were remapped in controls.ini has to accept a match with the same
button that is Cross in the game. This module is a port of that file's parser and binding
rules (presets, `[xinput]` / `[dinput]` / `[dinput.VVVV:PPPP]` / `[portN.xinput]` layers,
`TARGET = SOURCE ...` lines that replace the preset's binding and take their sources away
from other targets, `macros = tekken`, `[portN] device = ...`), reduced to what the launcher
needs. tests/test_padmap_sync.py compares the preset tables below with the ones in the patch,
so the two cannot drift apart unnoticed.

Sources are named the way controls.ini names them, in upper case:
  XInput   A B X Y LB RB LT RT BACK START LS RS DUP DDOWN DLEFT DRIGHT, LUP LDOWN LLEFT LRIGHT
           RUP RDOWN RLEFT RRIGHT (stick directions past half deflection)
  DInput   B1..B128, HAT_UP/HAT_RIGHT/HAT_DOWN/HAT_LEFT (HAT2_... for more hats),
           X+ X- Y+ Y- Z+ Z- RX+ RX- RY+ RY- RZ+ RZ- S0+ S0- S1+ S1-

Only the face buttons matter here. A source counts as Cross only when the binding is exactly
Cross: a macro such as `3+4 = B8` presses Cross and Circle together in the game and is never
Cross (or Circle) for the launcher, so one press cannot accept and decline at once.
"""
import os
import re

# Bit values of CELL_PAD_CTRL_* in the order the patch's mask_names() lists them.
PS3_BIT = {name: 1 << i for i, name in enumerate((
    "SELECT", "L3", "R3", "START", "UP", "RIGHT", "DOWN", "LEFT",
    "L2", "R2", "L1", "R1", "TRIANGLE", "CIRCLE", "CROSS", "SQUARE"))}
CROSS, CIRCLE, TRIANGLE = PS3_BIT["CROSS"], PS3_BIT["CIRCLE"], PS3_BIT["TRIANGLE"]
# Target names of controls.ini: PS3 buttons, plus the Tekken names for the face buttons
# (1 2 3 4 = Square Triangle Cross Circle, the game's default button setting).
TARGET_NAMES = dict(PS3_BIT)
TARGET_NAMES.update({"1": PS3_BIT["SQUARE"], "2": PS3_BIT["TRIANGLE"], "3": PS3_BIT["CROSS"],
                     "4": PS3_BIT["CIRCLE"], "LP": PS3_BIT["SQUARE"], "RP": PS3_BIT["TRIANGLE"],
                     "LK": PS3_BIT["CROSS"], "RK": PS3_BIT["CIRCLE"], "TRI": PS3_BIT["TRIANGLE"],
                     "SQR": PS3_BIT["SQUARE"]})
AXIS_TARGETS = ("LX", "LY", "RX", "RY")
FACE = {"cross": CROSS, "circle": CIRCLE, "triangle": TRIANGLE}

XINPUT = "xinput"
DINPUT = "dinput"
MAX_PORTS = 7           # PADH_MAX_PORTS: [port1] .. [port7]

XINPUT_SOURCES = ("DUP", "DDOWN", "DLEFT", "DRIGHT", "START", "BACK", "LS", "RS", "LB", "RB", "A", "B",
                  "X", "Y", "LT", "RT", "LRIGHT", "LLEFT", "LDOWN", "LUP", "RRIGHT", "RLEFT", "RDOWN", "RUP")
DINPUT_AXES = ("X", "Y", "Z", "RX", "RY", "RZ", "S0", "S1")
HAT_DIRS = ("UP", "RIGHT", "DOWN", "LEFT")

# --- presets: the same "TARGET=SOURCE SOURCE ..." lines as k_xinput_standard, k_dinput_ps,
# --- k_dinput_switch, k_dinput_xbox and the macro overlays in the patch (tests/test_padmap_sync.py).
PRESETS = {
    (XINPUT, "standard"): (
        "UP=DUP", "DOWN=DDOWN", "LEFT=DLEFT", "RIGHT=DRIGHT",
        "CROSS=A", "CIRCLE=B", "SQUARE=X", "TRIANGLE=Y",
        "L1=LB", "R1=RB", "L2=LT", "R2=RT", "L3=LS", "R3=RS", "START=START", "SELECT=BACK",
        "LX=LX", "LY=LY", "RX=RX", "RY=RY"),
    (DINPUT, "ps"): (
        "SQUARE=B1", "CROSS=B2", "CIRCLE=B3", "TRIANGLE=B4",
        "L1=B5", "R1=B6", "L2=B7", "R2=B8", "SELECT=B9", "START=B10", "L3=B11", "R3=B12",
        "UP=HAT_UP", "DOWN=HAT_DOWN", "LEFT=HAT_LEFT", "RIGHT=HAT_RIGHT",
        "LX=X", "LY=Y", "RX=Z", "RY=RZ"),
    (DINPUT, "switch"): (
        "CROSS=B1", "CIRCLE=B2", "SQUARE=B3", "TRIANGLE=B4",
        "L1=B5", "R1=B6", "L2=B7", "R2=B8", "SELECT=B9", "START=B10", "L3=B11", "R3=B12",
        "UP=HAT_UP", "DOWN=HAT_DOWN", "LEFT=HAT_LEFT", "RIGHT=HAT_RIGHT",
        "LX=X", "LY=Y", "RX=RX", "RY=RY"),
    (DINPUT, "xbox"): (
        "CROSS=B1", "CIRCLE=B2", "SQUARE=B3", "TRIANGLE=B4",
        "L1=B5", "R1=B6", "SELECT=B7", "START=B8", "L3=B9", "R3=B10", "L2=Z+", "R2=Z-",
        "UP=HAT_UP", "DOWN=HAT_DOWN", "LEFT=HAT_LEFT", "RIGHT=HAT_RIGHT",
        "LX=X", "LY=Y", "RX=RX", "RY=RY"),
}
MACROS_TEKKEN = {
    XINPUT: ("1+2=RB", "3+4=RT", "1+3=LB", "2+4=LT"),
    DINPUT: ("1+2=B6", "3+4=B8", "1+3=B5", "2+4=B7"),
}
VID_NINTENDO, VID_MICROSOFT = 0x057E, 0x045E


def default_preset(kind, vid=0):
    """The preset the game picks for a device that no section names one for."""
    if kind == XINPUT:
        return "standard"
    if vid == VID_NINTENDO:
        return "switch"
    if vid == VID_MICROSOFT:          # a Microsoft pad that is not an XInput device
        return "xbox"
    return "ps"


def canon_source(kind, token):
    """A controls.ini source name in its one canonical spelling, or None if it is not one."""
    s = token.strip().upper()
    if kind == XINPUT:
        return s if s in XINPUT_SOURCES else None
    m = re.fullmatch(r"B(\d{1,3})", s)
    if m:
        n = int(m.group(1))
        return f"B{n}" if 1 <= n <= 128 else None
    m = re.fullmatch(r"HAT([1-4]?)_?(UP|RIGHT|DOWN|LEFT)", s)
    if m:
        return hat_name(int(m.group(1) or 1) - 1, m.group(2))
    m = re.fullmatch(r"(X|Y|Z|RX|RY|RZ|S0|S1)([+-])", s)
    if m:
        return s
    return None


def hat_name(hat, direction):
    return f"HAT_{direction}" if hat == 0 else f"HAT{hat + 1}_{direction}"


def target_mask(text):
    """'CROSS', '3', '1+2', 'SQUARE+CROSS' -> button mask; 0 if any part is unknown."""
    mask = 0
    for tok in text.strip().split("+"):
        m = TARGET_NAMES.get(tok.strip().upper())
        if not m:
            return 0
        mask |= m
    return mask


class Table:
    """The effective bindings of one device: source -> PS3 button mask (BindTable in the patch)."""

    def __init__(self):
        self.binds = []         # [source, mask], in binding order
        self.desc = []

    def add(self, src, mask):
        for b in self.binds:
            if b[0] == src:
                b[1] |= mask
                return
        self.binds.append([src, mask])

    def mask_of(self, src):
        for s, m in self.binds:
            if s == src:
                return m
        return 0

    def sources_exactly(self, mask):
        """Sources whose whole binding is this one button."""
        return [s for s, m in self.binds if m == mask]


def _bind_line(t, kind, target, sources, replace, where, warn):
    """One `TARGET = SOURCES` line (bind_line in the patch). replace: an explicit binding drops what the
    target had and takes the sources away from whatever they did before."""
    tg = target.strip()
    if tg.lower() in ("preset", "macros"):
        return
    if tg.upper() in AXIS_TARGETS:
        return                      # sticks: the launcher only reads buttons
    mask = target_mask(tg)
    if not mask:
        warn(f"{where}: unknown PS3 button '{tg}'")
        return
    srcs = []
    for tok in re.split(r"[ ,\t]+", sources.strip()):
        if not tok or tok.lower() == "none":
            continue
        src = canon_source(kind, tok)
        if src is None:
            warn(f"{where}: unknown {kind} input '{tok}' (for {tg})")
            continue
        if len(srcs) < 16 and src not in srcs:
            srcs.append(src)
    if replace:
        # the new sources lose what they did before, and the target's old sources lose it
        kept = []
        for s, m in t.binds:
            if s in srcs or m == mask:
                continue
            kept.append([s, m])
        t.binds = kept
    for s in srcs:
        t.add(s, mask)


def _apply_lines(t, kind, lines, replace, where, warn):
    for line in lines:
        k, _, v = line.partition("=")
        _bind_line(t, kind, k, v, replace, where, warn)


class Controls:
    """A parsed controls.ini (or the built-in defaults when there is none)."""

    def __init__(self, text="", path=None):
        self.path = path
        self.warnings = []
        self.sections = []          # [(name, [(key, value)])] in file order
        self._parse(text)
        g = self._get("general", "xinput")
        self.use_xinput = _flag(g, True)
        self.use_dinput = _flag(self._get("general", "dinput"), True)
        # the PlayStation pads read as HID devices (patch 0042): on unless set, following dinput as in the game;
        # steam_input = 0 reads a pad Steam Input hands out as a virtual Xbox pad anyway
        self.use_hid = _flag(self._get("general", "hid"), self.use_dinput)
        self.steam_input = _flag(self._get("general", "steam_input"), True)
        self.ports = [self._port_spec(p) for p in range(MAX_PORTS)]
        self._tables = {}

    # ------------------------------------------------------------------ file
    @classmethod
    def load(cls, path):
        """The file at `path`; the defaults if it cannot be read (the game does the same)."""
        try:
            with open(path, "rb") as f:
                return cls(f.read().decode("latin-1"), path)    # (bytes, like the game's fopen "rb")
        except OSError:
            c = cls("", None)
            c.warnings.append(f"cannot open {path}, using defaults")
            return c

    def _parse(self, text):
        cur = None
        for raw in text.splitlines():
            s = raw.strip()
            if not s or s[0] in ";#":
                continue
            if s[0] == "[":
                e = s.find("]")
                if e < 0:
                    cur = None
                    continue
                cur = (s[1:e].strip(), [])
                self.sections.append(cur)
                continue
            eq = s.find("=")
            if eq < 0 or cur is None:
                continue
            key, val = s[:eq].strip(), s[eq + 1:]
            for i in range(1, len(val)):                  # an inline comment: whitespace, then ; or #
                if val[i] in ";#" and val[i - 1].isspace():
                    val = val[:i]
                    break
            cur[1].append((key, val.strip()))

    def _section(self, name):
        for n, kv in self.sections:
            if n.lower() == name.lower():
                return kv
        return None

    def _get(self, section, key):
        kv = self._section(section)
        if kv is None:
            return None
        for k, v in reversed(kv):           # the last one wins
            if k.lower() == key.lower():
                return v
        return None

    # ------------------------------------------------------------------ ports
    def _port_spec(self, p):
        v = (self._get(f"port{p + 1}", "device") or "").strip()
        spec = {"kind": "auto", "slot": None, "vid": 0, "pid": 0, "match": ""}
        low = v.lower()
        if not v or low == "auto":
            return spec
        if low == "none":
            spec["kind"] = "none"
        elif low.startswith("xinput"):
            spec["kind"] = XINPUT
            if v[6:7] == ":" and v[7:].strip().isdigit():
                spec["slot"] = int(v[7:])
        elif low.startswith("dinput"):
            spec["kind"] = DINPUT
            rest = v[7:] if v[6:7] == ":" else ""
            m = re.fullmatch(r"([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", rest)
            if m:
                spec["vid"], spec["pid"] = int(m.group(1), 16), int(m.group(2), 16)
            else:
                spec["match"] = rest
        else:
            self.warnings.append(f"unknown device '{v}'")
        return spec

    def reads_kind(self, dev):
        """Does the game read this kind of device at all ([general] xinput / dinput / hid)? dev: .kind .key"""
        if dev.kind == XINPUT:
            return self.use_xinput
        if is_hid_key(getattr(dev, "key", "")):
            return self.use_hid
        return self.use_dinput

    def port_matches(self, p, dev):
        """spec_matches() in the patch. dev needs .kind .slot .vid .pid .name"""
        spec = self.ports[p]
        if spec["kind"] == XINPUT:
            return dev.kind == XINPUT and (spec["slot"] is None or spec["slot"] == dev.slot)
        if spec["kind"] == DINPUT:
            if dev.kind != DINPUT:
                return False
            if spec["vid"]:
                return dev.vid == spec["vid"] and dev.pid == spec["pid"]
            if spec["match"]:
                return spec["match"].lower() in (dev.name or "").lower()
            return True
        return False

    # ------------------------------------------------------------------ tables
    def table(self, kind, port=-1, vid=0, pid=0):
        """The bindings of a device of this kind on this port (port -1: not assigned)."""
        key = (kind, port, vid, pid)
        t = self._tables.get(key)
        if t is None:
            t = self._tables[key] = self._build_table(kind, port, vid, pid)
        return t

    def _build_table(self, kind, port, vid, pid):
        t = Table()
        warn = self.warnings.append
        layers = [self._section(kind),
                  self._section(f"dinput.{vid:04X}:{pid:04X}") if kind == DINPUT else None,
                  self._section(f"port{port + 1}.{kind}") if port >= 0 else None]
        pname = None
        for kv in reversed(layers):
            if kv is None:
                continue
            for k, v in reversed(kv):
                if k.lower() == "preset":
                    pname = v
                    break
            if pname:
                break
        if not pname:
            pname = default_preset(kind, vid)
        preset = PRESETS.get((kind, pname.lower()))
        if preset:
            _apply_lines(t, kind, preset, False, pname, warn)
            t.desc.append(pname.lower())
        elif pname.lower() != "none":
            warn(f"unknown {kind} preset '{pname}'")
        macros = None
        for kv in reversed(layers):
            if kv is None:
                continue
            for k, v in reversed(kv):
                if k.lower() == "macros":
                    macros = v
                    break
            if macros:
                break
        if not macros and port >= 0:
            macros = self._get(f"port{port + 1}", "macros")
        if macros and macros.lower() == "tekken":
            _apply_lines(t, kind, MACROS_TEKKEN[kind], True, "macros", warn)
            t.desc.append("tekken macros")
        for kv in layers:
            if kv:
                for k, v in kv:
                    _bind_line(t, kind, k, v, True, "controls.ini", warn)
        return t

    def face_sources(self, kind, port=-1, vid=0, pid=0):
        """{'cross': ['A'], 'circle': ['B'], 'triangle': ['Y']} -- the sources bound to exactly that button."""
        t = self.table(kind, port, vid, pid)
        return {name: t.sources_exactly(mask) for name, mask in FACE.items()}


def is_hid_key(key):
    """A PlayStation pad the launcher reads as a HID device (padnav.HidSource keys them "hid:<path>")."""
    return str(key).startswith("hid:")


def _flag(v, default):
    if v is None or v == "":
        return default
    low = v.lower()
    if low in ("on", "yes", "true"):
        return True
    if low in ("off", "no", "false"):
        return False
    try:
        return int(v) != 0
    except ValueError:
        return False


# ---------------------------------------------------------------------- where the file is

def find_controls_ini(out_dir=None, env=None):
    """The controls.ini the game will use, found the way it finds it: PS3_CONTROLS, else
    controls.ini next to t5dr.exe (<out>/build/cmake), else in its working directory (<out>).
    `env`: the settings' extra environment (it is added to the game's environment). None: no file
    (the game's built-in defaults, which are also this module's defaults)."""
    merged = dict(os.environ)
    merged.update(env or {})
    p = merged.get("PS3_CONTROLS")
    if p:
        return p if os.path.isfile(p) else None
    if out_dir:
        for d in (os.path.join(out_dir, "build", "cmake"), out_dir):
            c = os.path.join(d, "controls.ini")
            if os.path.isfile(c):
                return c
    return None


class ControlsFile:
    """The controls.ini of `finder()`, parsed again when the file or its path changes."""

    def __init__(self, finder):
        self.finder = finder
        self._sig = object()
        self.controls = Controls()
        self.changed = 0                # counts reloads (the UI refreshes its labels)

    def refresh(self):
        try:
            path = self.finder()
        except Exception:               # a settings object that cannot answer: keep what we have
            return self.controls
        try:
            st = os.stat(path) if path else None
            sig = (path, st.st_mtime_ns, st.st_size) if st else (path, None, None)
        except OSError:
            sig = (path, None, None)
        if sig != self._sig:
            self._sig = sig
            self.controls = Controls.load(path) if path else Controls()
            self.changed += 1
        return self.controls


class PortMap:
    """Which port the game would give each device (assign_ports in the patch): ports pinned with
    `[portN] device = ...` first, then the lowest free auto port, in the order the devices appeared
    (XInput slots first). The port picks the `[portN.xinput]` / `[portN.dinput]` layer."""

    def __init__(self, controls):
        self.controls = controls
        self.port = {}          # device key -> port (0-based) or -1
        self.order = {}         # device key -> arrival number
        self._seq = 0

    def update(self, devices, controls=None):
        if controls is not None and controls is not self.controls:
            self.controls = controls
            self.port.clear()               # a new file: assign again
        keys = {d.key for d in devices}
        for k in list(self.port):
            if k not in keys:
                del self.port[k]
                self.order.pop(k, None)
        for d in devices:
            if d.key not in self.order:
                self._seq += 1
                self.order[d.key] = self._seq
        c = self.controls
        for d in sorted((d for d in devices if d.key not in self.port), key=lambda d: self.order[d.key]):
            if not c.reads_kind(d):
                continue                    # the game does not read this kind of device at all
            taken = set(p for p in self.port.values() if p >= 0)
            port = -1
            for p in range(MAX_PORTS):
                if c.port_matches(p, d) and p not in taken:
                    port = p
                    break
            if port < 0:
                for p in range(MAX_PORTS):
                    if c.ports[p]["kind"] == "auto" and p not in taken:
                        port = p
                        break
            if port >= 0:                   # no room: parked, tried again at the next update (as the game does)
                self.port[d.key] = port
        return self.port

    def reads(self, key):
        """True when the game reads this device (it has a port; its kind is not switched off in [general])."""
        return key in self.port
