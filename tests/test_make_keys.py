"""tools/make_keys.py against a fake key vault in RPCS3's source layout
(--source, so no network), and its output read back by unself.load_keys."""
import os
import subprocess
import tempfile
import unittest

from helpers import PY, TOOLS, fake_keys, get, load_tool, put


def c_array(name, val):
    body = ", ".join(f"0x{b:02X}" for b in val)
    return f"constexpr u8 {name}[0x{len(val):X}] = {{\n\t{body}\n}};\n"


def vault(keys, revisions):
    """key_vault.h / key_vault.cpp text shaped like RPCS3's, holding fake values."""
    h = "#pragma once\n\n"
    for name in ("NP_KLIC_KEY", "RAP_KEY", "RAP_PBOX", "RAP_E1", "RAP_E2"):
        h += c_array(name, keys[name]) + "\n"
    h += c_array("NP_UNRELATED", keys["RAP_E1"][::-1])
    cpp = "void KeyVault::LoadSelfAPPKeys()\n{\n\tsk_APP_arr.clear();\n" \
          '\tsk_APP_arr.emplace_back(0x0000009200000000, 0x0000, 0x0001, KEY_APP,\n' \
          f'\t\t"{"AB" * 32}",\n\t\t"{"CD" * 16}",\n\t\t"00",\n\t\t"00",\n\t\t0x11);\n}}\n\n'
    cpp += "void KeyVault::LoadSelfNPDRMKeys()\n{\n\tsk_NPDRM_arr.clear();\n"
    for rev in revisions:
        erk, riv = keys[f"NPDRM_{rev:04X}_ERK"], keys[f"NPDRM_{rev:04X}_RIV"]
        cpp += (f"\tsk_NPDRM_arr.emplace_back(0x0001000000000000, 0x0001000000000000, 0x{rev:04X}, KEY_NPDRM,\n"
                f'\t\t"{erk.hex().upper()}",\n\t\t"{riv.hex().upper()}",\n\t\t"00",\n\t\t"00",\n\t\t0x11);\n')
    cpp += "}\n\nvoid KeyVault::LoadSelfUNK7Keys()\n{\n}\n"
    return h, cpp


class MakeKeys(unittest.TestCase):
    def test_from_local_source(self):
        keys = {**fake_keys(1), **fake_keys(4)}
        with tempfile.TemporaryDirectory() as d:
            h, cpp = vault(keys, [1, 4])
            put(os.path.join(d, "key_vault.h"), h)
            put(os.path.join(d, "key_vault.cpp"), cpp)
            out = os.path.join(d, "out", "ps3.keys")
            r = subprocess.run([PY, os.path.join(TOOLS, "make_keys.py"), "--source", d, "--out", out],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("9 entries", r.stdout)
            text = get(out).decode()
            self.assertTrue(text.startswith("# Local only. Never commit."))
            got = load_tool("unself").load_keys(out)
            # Exactly the five named keys plus ERK/RIV per NPDRM revision --
            # not the APP keys, not unrelated arrays.
            self.assertEqual(got, keys)

    def test_missing_key_fails(self):
        keys = fake_keys(1)
        with tempfile.TemporaryDirectory() as d:
            h, cpp = vault(keys, [1])
            put(os.path.join(d, "key_vault.h"), h.replace("RAP_E2", "RAP_XX"))
            put(os.path.join(d, "key_vault.cpp"), cpp)
            r = subprocess.run([PY, os.path.join(TOOLS, "make_keys.py"), "--source", d,
                                "--out", os.path.join(d, "ps3.keys")], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("RAP_E2 not found", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(d, "ps3.keys")))


if __name__ == "__main__":
    unittest.main()
