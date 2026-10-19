"""DualShock 4 and DualSense read by the game as HID devices (ps3recomp patch 0042, libs/input/pad_host_win32.c
"PlayStation pads read directly"), without a controller.

* tools/ps_hid_reports.py builds the pads' input reports (USB 0x01, Bluetooth simple 0x01, Bluetooth extended
  0x11 / 0x31 with their CRC-32) from a pad state; checked here against a plain bitwise CRC and the formats.
* tests/c/ps_hid_test.c, built against the patched runtime source, checks every report mode, the "ps" layout,
  the tap memory, the CRC rules, Steam Input's device list and the fake pad; it must print PASS.
* The same runtime parser gets a few thousand random reports from the Python builder (a second, independent
  writer of the formats) and must report what DirectInput reports for that pad state.

The C parts need the patched ps3recomp tree (PS3RECOMP_DIR, deps/ps3recomp) and a Windows C compiler; they are
skipped without them.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import ps_hid_reports as phr  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0042-playstation-hid.patch")


def crc32_bitwise(data, crc=0):
    crc ^= 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


class ReportBuilderTest(unittest.TestCase):
    """The report builder the other tests (and tools/tap_latch_test.py --hid) rely on."""

    def test_lengths_and_ids(self):
        s = phr.PadState()
        want = {("ds4", "usb"): (0x01, 64), ("ds4", "bt-simple"): (0x01, 10), ("ds4", "bt-ext"): (0x11, 78),
                ("ds4", "bt-audio"): (0x14, 270), ("dualsense", "usb"): (0x01, 64),
                ("dualsense", "bt-simple"): (0x01, 10), ("dualsense", "bt-ext"): (0x31, 78),
                ("edge", "usb"): (0x01, 64), ("edge", "bt-ext"): (0x31, 78)}
        for (model, mode), (rid, n) in want.items():
            rep = phr.report(model, mode, s)
            self.assertEqual((rep[0], len(rep)), (rid, n), (model, mode))
            self.assertEqual(len(phr.padded(model, mode, rep)), phr.in_len(model, mode))
        self.assertEqual(phr.in_len("ds4", "bt-ext"), 547)
        self.assertEqual(phr.in_len("dualsense", "bt-simple"), 78)

    def test_crc_is_the_bluetooth_one(self):
        self.assertEqual(crc32_bitwise(b"123456789"), 0xCBF43926)
        for model, mode in (("ds4", "bt-ext"), ("ds4", "bt-audio"), ("dualsense", "bt-ext"), ("edge", "bt-ext")):
            rep = phr.report(model, mode, phr.PadState(buttons={"cross"}), counter=3)
            self.assertEqual(int.from_bytes(rep[-4:], "little"), crc32_bitwise(b"\xA1" + rep[:-4]), (model, mode))

    def test_fields(self):
        s = phr.PadState(buttons={"square", "r2", "options", "ps", "mute", "paddle_right"}, hat=3,
                         lx=1, ly=2, rx=3, ry=4, l2=5, r2=6)
        u = phr.report("dualsense", "usb", s, counter=9)
        self.assertEqual(u[1:8], bytes((1, 2, 3, 4, 5, 6, 9)))
        self.assertEqual(u[8:11], bytes((0x13, 0x28, 0x05)))          # hat 3 + square, R2 + options, PS + mute
        e = phr.report("edge", "bt-ext", s, counter=9)
        self.assertEqual(e[2:9], bytes((1, 2, 3, 4, 5, 6, 9)))
        self.assertEqual(e[9:12], bytes((0x13, 0x28, 0x85)))          # + right paddle
        d4 = phr.report("ds4", "bt-ext", s, counter=9)
        self.assertEqual(d4[1] & 0x80, 0x80)
        self.assertEqual(d4[3:12], bytes((1, 2, 3, 4, 0x13, 0x28, 0x01 | 9 << 2, 5, 6)))
        simple = phr.report("dualsense", "bt-simple", s, counter=9)
        self.assertEqual(simple, bytes((0x01, 1, 2, 3, 4, 0x13, 0x28, 0x01 | 9 << 2, 5, 6)))

    def test_expected_state(self):
        bits, axes = phr.expected_raw("ds4", "usb", phr.PadState(buttons={"cross", "touchpad", "mute"}, hat=1,
                                                                   lx=0, ly=255, l2=255))
        self.assertEqual(bits[0], (1 << 1) | (1 << 13))                  # no mute on a DS4
        self.assertEqual(bits[4] & 0xF, 0b0011)                          # up + right
        self.assertEqual(axes, [-32768, 32767, 128, 32767, -32768, 128, 0, 0])


def find_ps3recomp():
    cands = [os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")]
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--git-common-dir"], capture_output=True, text=True,
                           timeout=20)
        if r.returncode == 0:
            common = os.path.normpath(os.path.join(ROOT, r.stdout.strip()))
            cands.append(os.path.join(os.path.dirname(common), "deps", "ps3recomp"))
    except (OSError, subprocess.SubprocessError):
        pass
    for c in cands:
        p = os.path.join(c or "", "libs", "input", "pad_host_win32.c")
        if c and os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                if "ps_parse(" in f.read():
                    return c
    return None


def find_vcvars():
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = os.path.join(pf86, "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if os.path.isfile(vswhere):
        r = subprocess.run([vswhere, "-latest", "-products", "*", "-property", "installationPath"],
                           capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            p = os.path.join(line.strip(), "VC", "Auxiliary", "Build", "vcvars64.bat")
            if os.path.isfile(p):
                return p
    return None


class RuntimeParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("the runtime's pad layer is Windows only")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0042 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "ps_hid_test.exe")
        inc = [os.path.join(cls.tree, *p) for p in (("libs", "input"), ("libs",), ("runtime",), ("include",))]
        src = os.path.join(ROOT, "tests", "c", "ps_hid_test.c")
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 {flags} "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "ps_hid_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/ps_hid_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_c_unit_test_passes(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        tail = r.stdout[-3000:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", tail)

    def run_vectors(self, cases):
        """cases: [(model, bt, bytes)] -> [(mode, crc, bits[5], axes[8])]"""
        path = os.path.join(self.tmp.name, f"vec{random.random():.9f}.txt")
        with open(path, "w") as f:
            for model, bt, data in cases:
                f.write(f"{model} {bt} {data.hex()}\n")
        r = subprocess.run([self.exe, f"vectors={path}"], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = []
        for line in r.stdout.splitlines():
            if not line.startswith("R "):
                continue
            f = line.split()
            out.append((int(f[1]), int(f[2]), [int(x, 16) for x in f[3:8]], [int(x) for x in f[8:16]]))
        self.assertEqual(len(out), len(cases))
        return out

    def test_random_reports_from_an_independent_writer(self):
        rnd = random.Random(42)
        cases, want = [], []
        combos = [("ds4", "usb"), ("ds4", "bt-simple"), ("ds4", "bt-ext"), ("ds4", "bt-audio"),
                  ("dualsense", "usb"), ("dualsense", "bt-simple"), ("dualsense", "bt-ext"),
                  ("edge", "usb"), ("edge", "bt-simple"), ("edge", "bt-ext")]
        for model, mode in combos:
            for i in range(300):
                s = phr.PadState.random(rnd)
                rep = phr.padded(model, mode, phr.report(model, mode, s, counter=i, seed=rnd.randrange(1 << 30)))
                bt = 0 if mode == "usb" else 1
                cases.append((model, bt, rep))
                want.append((model, mode, s))
        got = self.run_vectors(cases)
        bad = []
        for (model, mode, s), (psr, crc, bits, axes) in zip(want, got):
            wbits, waxes = phr.expected_raw(model, mode, s)
            wcrc = 1 if mode in ("bt-ext", "bt-audio") else -1
            if (psr, crc, bits, axes) != (phr.report_mode_name(model, mode), wcrc, wbits, waxes):
                bad.append(f"{model} {mode} {sorted(s.buttons)} hat={s.hat}: got mode {psr} crc {crc} "
                           f"bits {[hex(x) for x in bits]} axes {axes}; want {[hex(x) for x in wbits]} {waxes}")
        self.assertFalse(bad, f"{len(bad)} of {len(cases)} reports parsed wrong:\n" + "\n".join(bad[:8]))

    def test_damaged_and_foreign_reports(self):
        s = phr.PadState(buttons={"cross"})
        rep = bytearray(phr.padded("dualsense", "bt-ext", phr.report("dualsense", "bt-ext", s)))
        rep[30] ^= 1
        no_flag = phr.padded("ds4", "bt-ext", phr.report("ds4", "bt-ext", s, hid_flag=False))
        cut = phr.report("dualsense", "usb", s)[:9]
        (psr1, crc1, _b, _a), (psr2, crc2, b2, _a2), (psr3, _c3, _b3, _a3) = self.run_vectors(
            [("dualsense", 1, bytes(rep)), ("ds4", 1, no_flag), ("dualsense", 0, cut)])
        self.assertEqual(crc1, 0, "a damaged extended report fails its CRC (the reader then drops it)")
        self.assertEqual(psr2, 0, "a DS4 extended report without input data holds no state")
        self.assertEqual(crc2, 1)
        self.assertEqual(psr3, 0, "a cut report is not parsed")


class PatchTest(unittest.TestCase):
    """What the patch must and must not do (read from patches/ps3recomp/0042-playstation-hid.patch)."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(PATCH):
            raise unittest.SkipTest("no patch 0042 in this tree")
        with open(PATCH, encoding="utf-8", errors="replace") as f:
            cls.added = "\n".join(l[1:] for l in f.read().splitlines() if l.startswith("+") and not l.startswith("+++"))

    def test_nothing_is_ever_sent_to_a_pad(self):
        # Sending an output report, or reading a feature report, would switch a Bluetooth pad into its extended
        # mode and break it for every DirectInput program after the game -- the very problem this fixes.
        for call in ("WriteFile(", "HidD_SetOutputReport", "HidD_GetFeature", "HidD_SetFeature",
                     "HidD_GetInputReport", "DeviceIoControl("):
            self.assertNotIn(call, self.added, f"the HID path must not call {call}")

    def test_the_pads_it_takes(self):
        for pid in ("0x05C4", "0x09CC", "0x0CE6", "0x0DF2"):
            self.assertIn(f"case {pid}", self.added)
        self.assertIn("#define PS_VID 0x054C", self.added)

    def test_documented_settings_exist(self):
        with open(os.path.join(ROOT, "docs", "controls.ini"), encoding="latin-1") as f:
            sample = f.read()
        for key in ("hid", "steam_input"):
            self.assertRegex(sample, rf"(?m)^{key}\s*=\s*1\b", f"docs/controls.ini lacks {key}")
            self.assertIn(f'"{key}"', self.added, f"the runtime does not read [general] {key}")
        for env in ("PS3_PAD_HID", "PS3_PAD_STEAM_INPUT", "PS3_PAD_HID_FAKE"):
            self.assertIn(f'"{env}"', self.added)


if __name__ == "__main__":
    unittest.main()
