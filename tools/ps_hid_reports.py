#!/usr/bin/env python3
"""Input reports of DualShock 4 and DualSense pads, built from a pad state, for tests of the game's own
HID reading of these pads (ps3recomp patch 0042, libs/input/pad_host_win32.c "PlayStation pads read
directly"). Written from the public descriptions of the formats (the Linux hid-playstation driver and
SDL's HIDAPI drivers as references), not from their code.

    from ps_hid_reports import PadState, report, padded, expected_raw
    s = PadState(buttons={"cross", "l1"}, hat=2, lx=0, l2=255)
    rep = report("dualsense", "bt-ext", s, counter=7)   # 78 bytes, CRC filled in
    buf = padded("dualsense", "bt-ext", rep)            # as Windows' ReadFile hands it over

    python tools/ps_hid_reports.py dualsense bt-ext cross l1 hat=2 lx=0      # print one report in hex

Models: ds4 (054C:09CC), dualsense (054C:0CE6), edge (DualSense Edge, 054C:0DF2).
Modes:  usb      report 0x01, 64 bytes (the only one over USB)
        bt-simple  report 0x01, 10 bytes (Bluetooth, before anything asked the pad for more)
        bt-ext   DS4 report 0x11 / DualSense report 0x31, 78 bytes with a CRC-32 (Bluetooth after Steam,
                 DS4Windows, ...)
        bt-audio DS4 report 0x14 (270 bytes, the extended report while audio streams to the pad)

Buttons, in DirectInput's order (B1..B19): square cross circle triangle l1 r1 l2 r2 share options l3 r3
ps touchpad mute fn_left fn_right paddle_left paddle_right ("create" = share). The hat is 0 (up) to 7
(up-left) clockwise, None = centred. Sticks and triggers 0..255, sticks centre 128, up/left 0.
"""
import random
import sys
import zlib

MODELS = {"ds4": 0x09CC, "dualsense": 0x0CE6, "edge": 0x0DF2}
MODES = ("usb", "bt-simple", "bt-ext", "bt-audio")
BUTTONS = ("square", "cross", "circle", "triangle", "l1", "r1", "l2", "r2", "share", "options", "l3", "r3",
           "ps", "touchpad", "mute", "fn_left", "fn_right", "paddle_left", "paddle_right")
ALIASES = {"create": "share", "select": "share", "start": "options"}
CRC_SEED_INPUT = 0xA1          # Bluetooth HID header byte "DATA | INPUT", part of the CRC

# The game's raw ids (pad_host_win32.c): buttons 0..127, hat directions 128 + {up right down left},
# axis directions 144 + axis * 2 + {0 positive, 1 negative}.
CID_HAT, CID_AXIS = 128, 144


class PadState:
    def __init__(self, buttons=(), hat=None, lx=128, ly=128, rx=128, ry=128, l2=0, r2=0):
        self.buttons = {ALIASES.get(b, b) for b in buttons}
        unknown = self.buttons - set(BUTTONS)
        if unknown:
            raise ValueError(f"unknown buttons {sorted(unknown)}")
        self.hat = hat
        self.lx, self.ly, self.rx, self.ry, self.l2, self.r2 = lx, ly, rx, ry, l2, r2

    @classmethod
    def random(cls, rnd):
        return cls(buttons={b for b in BUTTONS if rnd.random() < 0.3}, hat=rnd.choice([None] + list(range(8))),
                   lx=rnd.choice((0, 1, 63, 64, 127, 128, 129, 191, 192, 254, 255, rnd.randrange(256))),
                   ly=rnd.randrange(256), rx=rnd.randrange(256), ry=rnd.randrange(256),
                   l2=rnd.choice((0, 255, rnd.randrange(256))), r2=rnd.randrange(256))


def carried(model, mode):
    """The buttons a report of this kind carries (mute only in a DualSense's full reports, the Edge's four
    extra buttons only in its full reports)."""
    out = set(BUTTONS[:14])
    full = mode in ("usb", "bt-ext")
    if model in ("dualsense", "edge") and full:
        out.add("mute")
    if model == "edge" and full:
        out |= {"fn_left", "fn_right", "paddle_left", "paddle_right"}
    return out


def _button_bytes(model, mode, s, counter):
    b = set(s.buttons) & carried(model, mode)
    hat = 8 if s.hat is None else s.hat
    b0 = hat | sum(1 << (4 + i) for i, n in enumerate(("square", "cross", "circle", "triangle")) if n in b)
    b1 = sum(1 << i for i, n in enumerate(("l1", "r1", "l2", "r2", "share", "options", "l3", "r3")) if n in b)
    b2 = (1 if "ps" in b else 0) | (2 if "touchpad" in b else 0)
    if model == "ds4" or mode in ("bt-simple",):
        b2 |= (counter & 0x3F) << 2                          # a report counter in the upper six bits
    else:
        b2 |= 4 if "mute" in b else 0
        b2 |= sum(1 << (4 + i) for i, n in enumerate(("fn_left", "fn_right", "paddle_left", "paddle_right"))
                  if n in b)
    return bytes((b0, b1, b2))


def _filler(rnd, n):
    return bytes(rnd.randrange(256) for _ in range(n))


def crc_fill(rep):
    """Bluetooth extended report: the last 4 bytes = CRC-32 of 0xA1 + the rest, little-endian."""
    rep = bytearray(rep)
    rep[-4:] = (zlib.crc32(bytes((CRC_SEED_INPUT,)) + bytes(rep[:-4])) & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(rep)


def report(model, mode, s, counter=0, seed=None, hid_flag=True):
    """One input report (unpadded). Bytes the parser must not read (motion, touch, battery, timestamps)
    are random, from `seed`."""
    if model not in MODELS or mode not in MODES:
        raise ValueError(f"model {model!r} / mode {mode!r}")
    rnd = random.Random(seed if seed is not None else counter)
    sticks = bytes((s.lx, s.ly, s.rx, s.ry))
    btn = _button_bytes(model, mode, s, counter)
    trig = bytes((s.l2, s.r2))
    if mode == "bt-simple":
        return b"\x01" + sticks + btn + trig                           # 10 bytes, DS4 and DualSense alike
    if model == "ds4":
        common = sticks + btn + trig + _filler(rnd, 23)                # 32 bytes: + motion, status
        if mode == "usb":
            return b"\x01" + common + _filler(rnd, 31)                 # 64
        rid, size = (0x11, 78) if mode == "bt-ext" else (0x14, 270)
        flags = 0xC0 if hid_flag else 0x40                             # 0x80: input data present
        body = bytes((rid, flags, 0x00)) + common
        rep = body + _filler(rnd, size - len(body))
        return crc_fill(rep) if mode == "bt-ext" else _crc_long(rep)
    if mode == "bt-audio":
        raise ValueError("bt-audio is a DualShock 4 report")
    # DualSense: LX LY RX RY L2 R2 counter buttons[3] (+1 reserved) ...
    common = sticks + trig + bytes((counter & 0xFF,)) + btn + _filler(rnd, 53)   # 63 bytes
    if mode == "usb":
        return b"\x01" + common                                        # 64
    seq = (counter & 0x0F) << 4
    rep = bytes((0x31, seq)) + common + _filler(rnd, 78 - 2 - len(common))
    return crc_fill(rep)


def _crc_long(rep):
    """The audio-carrying DS4 reports keep their CRC in their own last 4 bytes too."""
    return crc_fill(rep)


def in_len(model, mode):
    """InputReportByteLength Windows reports for the pad: what every ReadFile returns."""
    if mode == "usb":
        return 64
    return 547 if model == "ds4" else 78


def padded(model, mode, rep):
    n = in_len(model, mode)
    return rep + bytes(n - len(rep)) if len(rep) < n else rep


def report_mode_name(model, mode):
    """The runtime's PSR_* number for a report of this kind."""
    base = 0 if model == "ds4" else 3
    return base + {"usb": 1, "bt-simple": 2, "bt-ext": 3, "bt-audio": 3}[mode]


def axis_value(v):
    """What DirectInput gives for a logical 0..255 axis scaled to -32768..32767."""
    return v * 257 - 32768


def expected_raw(model, mode, s):
    """(bits[5], axes[8]) of the runtime's RawState for this report: the state DirectInput reports, with L2 / R2
    travel (RX RY) as half axes."""
    words = [0] * 5
    b = set(s.buttons) & carried(model, mode)
    for i, n in enumerate(BUTTONS):
        if n in b:
            words[i // 32] |= 1 << (i % 32)
    if s.hat is not None:
        dirs = {0: "u", 1: "ur", 2: "r", 3: "dr", 4: "d", 5: "dl", 6: "l", 7: "ul"}[s.hat]
        for k, c in enumerate("urdl"):
            if c in dirs:
                cid = CID_HAT + k
                words[cid // 32] |= 1 << (cid % 32)
    # L2 R2 travel (RX RY) are half axes in the runtime (1.1.5): 0..255 -> 0..32767, released = centre
    axes = [axis_value(v) for v in (s.lx, s.ly, s.rx)] + [s.l2 * 32767 // 255, s.r2 * 32767 // 255,
                                                          axis_value(s.ry)] + [0, 0]
    for a, v in enumerate(axes):
        if v > 16384:
            cid = CID_AXIS + a * 2
            words[cid // 32] |= 1 << (cid % 32)
        if v < -16384:
            cid = CID_AXIS + a * 2 + 1
            words[cid // 32] |= 1 << (cid % 32)
    return words, axes


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    model, mode, rest = argv[0], argv[1], argv[2:]
    kw, buttons = {}, []
    for a in rest:
        if "=" in a:
            k, v = a.split("=", 1)
            kw[k] = None if v.lower() == "none" else int(v, 0)
        else:
            buttons.append(a.lower())
    s = PadState(buttons=buttons, **kw)
    print(padded(model, mode, report(model, mode, s)).hex(" "))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
