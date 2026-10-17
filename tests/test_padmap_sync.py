"""The launcher's copy of the game's controller presets (lobby/t5lobby/padmap.py) must stay the same as
the one in the runtime (patches/ps3recomp/0009-controls.patch, libs/input/pad_host_win32.c). If the
game's presets change, this fails and says which table to update; if a later patch edits one, too."""
import glob
import os
import re
import sys
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "lobby"))
from t5lobby import padmap  # noqa: E402

PATCHES = os.path.join(ROOT, "patches", "ps3recomp")
CONTROLS_PATCH = os.path.join(PATCHES, "0009-controls.patch")

# patch array -> our table
PRESETS = {
    "k_xinput_standard": padmap.PRESETS[(padmap.XINPUT, "standard")],
    "k_dinput_ps": padmap.PRESETS[(padmap.DINPUT, "ps")],
    "k_dinput_switch": padmap.PRESETS[(padmap.DINPUT, "switch")],
    "k_dinput_xbox": padmap.PRESETS[(padmap.DINPUT, "xbox")],
    "k_macros_tekken_xinput": padmap.MACROS_TEKKEN[padmap.XINPUT],
    "k_macros_tekken_dinput": padmap.MACROS_TEKKEN[padmap.DINPUT],
}


def read_patch(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "replace")


def added_text(patch):
    """The text a patch adds (hunk lines starting with '+'), without the marker."""
    return "\n".join(l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))


def c_arrays(source):
    """{name: [string literals]} for every `static const char* const k_x[] = { "...", NULL };`."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    out = {}
    for m in re.finditer(r"static const char\* const (k_\w+)\[\]\s*=\s*\{(.*?)\};", source, flags=re.S):
        out[m.group(1)] = re.findall(r'"([^"]*)"', m.group(2))
    return out


class PresetSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arrays = c_arrays(added_text(read_patch(CONTROLS_PATCH)))

    def test_the_patch_has_the_tables(self):
        for name in PRESETS:
            self.assertIn(name, self.arrays, f"{name} not found in {os.path.basename(CONTROLS_PATCH)}")

    def test_presets_are_the_same_as_the_games(self):
        for name, ours in PRESETS.items():
            self.assertEqual(list(ours), self.arrays[name],
                             f"lobby/t5lobby/padmap.py is out of date: {name} differs from the runtime's table")

    def test_default_presets_per_device(self):
        # build_table() in the patch: XInput -> standard; Nintendo -> switch; Microsoft HID -> xbox; else ps
        src = added_text(read_patch(CONTROLS_PATCH))
        self.assertRegex(src, r'pname = "standard"')
        self.assertRegex(src, r'vid == 0x057E\) pname = "switch"')
        self.assertRegex(src, r'vid == 0x045E\) pname = "xbox"')
        self.assertRegex(src, r'else pname = "ps"')
        self.assertEqual(padmap.default_preset(padmap.XINPUT), "standard")
        self.assertEqual(padmap.default_preset(padmap.DINPUT, 0x057E), "switch")
        self.assertEqual(padmap.default_preset(padmap.DINPUT, 0x045E), "xbox")
        self.assertEqual(padmap.default_preset(padmap.DINPUT, 0x054C), "ps")

    def test_face_button_names_are_the_games(self):
        src = added_text(read_patch(CONTROLS_PATCH))
        for name, bit in padmap.TARGET_NAMES.items():
            if name in ("1", "2", "3", "4"):
                continue
            self.assertIn(f'"{name}"', src, f"{name} is not a target name in the runtime")
        # the Tekken names 1 2 3 4 = Square Triangle Cross Circle
        self.assertRegex(src, r'\{"1", CELL_PAD_CTRL_SQUARE\}, \{"2", CELL_PAD_CTRL_TRIANGLE\}')
        self.assertRegex(src, r'\{"3", CELL_PAD_CTRL_CROSS\},\s+\{"4", CELL_PAD_CTRL_CIRCLE\}')
        self.assertEqual((padmap.TARGET_NAMES["1"], padmap.TARGET_NAMES["2"], padmap.TARGET_NAMES["3"],
                          padmap.TARGET_NAMES["4"]),
                         (padmap.PS3_BIT["SQUARE"], padmap.PS3_BIT["TRIANGLE"], padmap.PS3_BIT["CROSS"],
                          padmap.PS3_BIT["CIRCLE"]))

    def test_the_bit_order_is_the_games(self):
        # mask_names() in the patch lists the 16 buttons by bit number
        m = re.search(r"static const char\* const n\[16\]\s*=\s*\{(.*?)\};", added_text(read_patch(CONTROLS_PATCH)),
                      flags=re.S)
        names = re.findall(r'"([A-Z0-9]+)"', m.group(1))
        self.assertEqual(names, sorted(padmap.PS3_BIT, key=padmap.PS3_BIT.get))

    def test_xinput_source_names_are_the_games(self):
        src = added_text(read_patch(CONTROLS_PATCH))
        m = re.search(r"k_xinput_src\[\]\s*=\s*\{(.*?)\};", src, flags=re.S)
        names = re.findall(r'\{"([A-Z]+)",', m.group(1))
        self.assertEqual(sorted(names), sorted(padmap.XINPUT_SOURCES))

    def test_no_later_patch_edits_a_preset(self):
        for path in sorted(glob.glob(os.path.join(PATCHES, "*.patch"))):
            if path == CONTROLS_PATCH:
                continue
            text = read_patch(path)
            if "pad_host_win32.c" not in text:
                continue
            for line in text.splitlines():
                if line[:1] in "+-" and re.search(r"k_(xinput|dinput|macros)_\w+\[\]|\"(CROSS|CIRCLE|TRIANGLE)=", line):
                    self.fail(f"{os.path.basename(path)} changes the game's controller presets ({line.strip()!r}); "
                              "update lobby/t5lobby/padmap.py and this test")


if __name__ == "__main__":
    unittest.main()
