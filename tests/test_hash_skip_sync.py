"""The two desync checks leave out the same words (docs/NETPLAY.md, docs/ROLLBACK.md section 21).

The lockstep's state hash (src/netplay/t5_hooks.cpp kDefaultHashSkip) and the rollback loop's gameplay hash
(src/rollback/rb_state.cpp kGameSkip) are kept in sync by hand: a word left out of one but hashed by the other
makes a netcode report a desync the other cannot see. Both lists are parsed from the source (comments removed)
and compared as sets of (address, length). The renderer's projection record 0x100996B4 (the stage-27 shadow box
at the fight's start, 1.1.2) must be in both.
"""
import os
import re
import unittest

from helpers import ROOT


def _strip_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def hooks_skip():
    src = open(os.path.join(ROOT, "src", "netplay", "t5_hooks.cpp"), encoding="utf-8").read()
    m = re.search(r"const char\* kDefaultHashSkip =(.*?);\n", src, re.S)
    text = "".join(re.findall(r'"([^"]*)"', _strip_comments(m.group(1))))
    out = set()
    for item in text.split(","):
        if item.strip():
            addr, length = item.split(":")
            out.add((int(addr, 16), int(length, 16)))
    return out


def state_skip():
    src = open(os.path.join(ROOT, "src", "rollback", "rb_state.cpp"), encoding="utf-8").read()
    m = re.search(r"static const Range kGameSkip\[\] = \{(.*?)\n\};", src, re.S)
    out = set()
    for addr, length in re.findall(r"\{\s*0x([0-9A-Fa-f]+)u,\s*(0x[0-9A-Fa-f]+|\d+)", _strip_comments(m.group(1))):
        out.add((int(addr, 16), int(length, 0)))
    return out


class HashSkipSync(unittest.TestCase):
    def test_same_words_left_out(self):
        a, b = hooks_skip(), state_skip()
        self.assertGreater(len(a), 10)
        self.assertEqual(sorted(a - b), [], "left out by the lockstep's hash only (t5_hooks.cpp)")
        self.assertEqual(sorted(b - a), [], "left out by the rollback's hash only (rb_state.cpp)")

    def test_projection_record_left_out(self):
        for name, s in (("t5_hooks.cpp", hooks_skip()), ("rb_state.cpp", state_skip())):
            self.assertIn((0x100996B4, 0x24), s, name)

    def test_side_flags_stay_in(self):
        """The fighters' side flags are gameplay (desync hunt): no skip may cover them."""
        flags = (0x10090202, 0x10090203, 0x10090AD2, 0x10090AD3)
        for a, n in hooks_skip() | state_skip():
            for f in flags:
                self.assertFalse(a <= f < a + n, f"{f:08X} inside {a:08X}+{n:X}")


if __name__ == "__main__":
    unittest.main()
