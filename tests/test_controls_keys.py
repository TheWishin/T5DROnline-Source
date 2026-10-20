"""Every PS3 button on the keyboard and on a pad (owner, 1.1.2: "keybinds must work, also online -- R2 and L2
should have their own binds too"): the launcher's Controls window and its editor bind L1 R1 L2 R2 L3 R3 Start
Select, the four attack buttons and every Tekken combo (1+2, 3+4, 1+3, 2+4, 1+2+3+4 ...) to their own key or
button; the keyboard is a controller of the window like a pad ([keys1] / [keys2] in controls.ini, the runtime's
CLS_KEYS rules: one section, presets classic / tekken / wasd / numpad, no macro overlay, [general] keyboard =
its player). What is written is checked against lobby/t5lobby/padmap.py (= the game's parser), whose keyboard
tables tests/test_padmap_sync.py compares with the runtime's."""
import os
import re
import sys
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "lobby"))
sys.path.insert(0, os.path.join(ROOT, "launcher"))
from t5lobby import padmap  # noqa: E402
from t5lobby.padmap import DINPUT, KEYS1, KEYS2, XINPUT, Controls  # noqa: E402
import controls_edit as ce  # noqa: E402
from controls_edit import ControlsEditor, DeviceRef  # noqa: E402

import test_controls_ui as tcu  # noqa: E402

KB = DeviceRef(KEYS1, 0, 0, 0)
KB2 = DeviceRef(KEYS2, 1, 0, 0)
DS = DeviceRef(DINPUT, 0, 0x054C, 0x0CE6)
XI = DeviceRef(XINPUT, 0, 0, 0)
EVERY_PS3 = ("L1", "R1", "L2", "R2", "L3", "R3", "START", "SELECT")
COMBOS = ("1+2", "3+4", "1+3", "2+4", "1+2+3+4")


class KeyboardTablesTest(unittest.TestCase):
    def test_the_keyboard_player_defaults(self):
        c = Controls("")
        self.assertEqual(c.table(KEYS1).mask_of("Z"), padmap.PS3_BIT["CROSS"])          # classic
        self.assertEqual(c.table(KEYS1).mask_of("1"), padmap.PS3_BIT["L2"])
        self.assertEqual(c.keyboard_port(KEYS1), 0)
        self.assertEqual(c.keyboard_port(KEYS2), -1)                                    # nothing bound: off
        c = Controls("[keys2]\npreset = numpad\n[general]\nkeyboard2 = 3\nkeyboard = off\n")
        self.assertEqual((c.keyboard_port(KEYS1), c.keyboard_port(KEYS2)), (-1, 2))
        self.assertEqual(c.table(KEYS2).mask_of("NUM6"), padmap.target_mask("1+2"))
        c = Controls("[keys1]\npreset = wasd\nmacros = tekken\n")
        self.assertEqual(c.table(KEYS1).mask_of("O"), padmap.target_mask("1+2"))
        self.assertNotIn("tekken macros", c.table(KEYS1).desc)                        # no macro overlay on keys

    def test_key_names_have_one_spelling(self):
        for raw, want in (("a", "A"), ("return", "ENTER"), ("Escape", "ESC"), ("f5", "F5"), ("F24", "F24"),
                          ("vk_bf", "SLASH"), ("0x41", "A"), ("VK_E2", "VK_E2"), ("num4", "NUM4"), ("lshift", "LSHIFT"),
                          ("7", "7"), ("F25", None), ("nope", None), ("", None)):
            self.assertEqual(padmap.canon_source(KEYS1, raw), want, raw)


class EveryButtonTest(unittest.TestCase):
    """Each PS3 button and each combo can have a key / button of its own, on the keyboard and on pads."""

    def check_all(self, dev, sources):
        ed = ControlsEditor("")
        keys = [s.key for s in ce.SLOTS]
        for key, src in zip(keys, sources):
            got = ed.bind(dev, ed.default_scope(dev), key, [src])
            self.assertEqual(got, [padmap.canon_source(dev.kind, src)], (dev.kind, key))
        table = Controls(ed.doc.render()).table(dev.kind, dev.port, dev.vid, dev.pid)
        for key, src in zip(keys, sources):
            self.assertEqual(table.mask_of(padmap.canon_source(dev.kind, src)), padmap.target_mask(key),
                             f"{dev.kind}: {key} = {src}\n{ed.doc.render()}")
        return ed

    def test_the_keyboard(self):
        keys = "QWERTYUIOPASDFGHJKLZXCVBNM1234567890"
        self.assertGreaterEqual(len(keys), len(ce.SLOTS))
        ed = self.check_all(KB, list(keys[:len(ce.SLOTS)]))
        self.assertIn("[keys1]", ed.doc.render())

    def test_a_playstation_pad(self):
        self.check_all(DS, [f"B{i}" for i in range(1, 20)] + ["HAT_UP", "HAT_DOWN", "HAT_LEFT", "HAT_RIGHT",
                                                              "Z+", "Z-", "RZ+", "RZ-", "X+", "X-"])

    def test_an_xbox_pad(self):
        # 24 XInput inputs for 27 game buttons: the first 24 (attack buttons, every combo, L1..R3, Start, Select)
        self.check_all(XI, ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "BACK", "START", "LS", "RS", "DUP",
                            "DDOWN", "DLEFT", "DRIGHT", "LUP", "LDOWN", "LLEFT", "LRIGHT", "RUP", "RDOWN", "RLEFT",
                            "RRIGHT"])

    def test_the_slots_cover_every_ps3_button_and_combo(self):
        keys = {s.key for s in ce.SLOTS}
        self.assertTrue(set(EVERY_PS3) | set(COMBOS) | {"1", "2", "3", "4", "UP", "DOWN", "LEFT", "RIGHT"} <= keys)
        self.assertTrue(set(EVERY_PS3) <= set(ce.GUIDED_BUTTONS))

    def test_l2_r2_and_a_combo_on_the_keyboard_as_written(self):
        ed = ControlsEditor("")
        for key, src in (("L2", "Q"), ("R2", "E"), ("1+2", "O")):
            ed.bind(KB, ce.SCOPE_KIND, key, [src])
        text = ed.doc.render()
        self.assertRegex(text, r"\[keys1\]")
        for line in ("L2 = Q", "R2 = E", "1+2 = O"):
            self.assertIn(line, text)
        t = Controls(text).table(KEYS1)
        self.assertEqual(t.mask_of("Q"), padmap.PS3_BIT["L2"])
        self.assertEqual(t.mask_of("E"), padmap.PS3_BIT["R2"])
        self.assertEqual(t.mask_of("O"), padmap.PS3_BIT["SQUARE"] | padmap.PS3_BIT["TRIANGLE"])
        self.assertEqual(t.sources_exactly(padmap.PS3_BIT["L1"]), [])                  # Q was L1 (classic)

    def test_keyboard_presets_round_trip(self):
        for r in ce.recipes_for(KEYS1):
            ed = ControlsEditor("")
            ed.bind(KB, ce.SCOPE_KIND, "1", ["F"])
            self.assertTrue(ed.apply_recipe(KB, ce.SCOPE_KIND, r.id), r.id)
            self.assertEqual(ControlsEditor(ed.doc.render()).detect_recipe(KB), r.id)
        self.assertEqual({r.id for r in ce.recipes_for(KEYS1)}, {"keys_classic", "keys_tekken", "keys_numpad"})
        self.assertEqual(ce.recipes_for(DINPUT), [r for r in ce.RECIPES if DINPUT in r.specs])   # pads unchanged

    def test_reset_and_the_player(self):
        ed = ControlsEditor("[port1]\nmacros = tekken\nsocd = up\n")
        ed.apply_recipe(KB, ce.SCOPE_KIND, "keys_tekken")
        ed.bind(KB, ce.SCOPE_KIND, "L3", ["V"])
        self.assertIn("macros = tekken", ed.doc.render())                               # the pad's port: untouched
        ed.reset(KB)
        self.assertNotIn("[keys1]", ed.doc.render())
        self.assertEqual(ed.detect_recipe(KB), "keys_classic")
        self.assertIn("socd = up", ed.doc.render())
        ed.assign_keyboard(KEYS1, 1)
        self.assertEqual(ed.controls().keyboard_port(KEYS1), 1)
        self.assertEqual(ed.keyboard_pinned(KEYS1), 1)
        ed.assign_keyboard(KEYS1, None)
        self.assertIsNone(ed.keyboard_pinned(KEYS1))
        self.assertEqual(ed.controls().keyboard_port(KEYS1), 0)

    def test_a_key_both_keyboard_players_use(self):
        ed = ControlsEditor("[keys2]\npreset = numpad\nL2 = Q\n")
        ed.bind(KB, ce.SCOPE_KIND, "R2", ["Q"])
        self.assertEqual(ed.key_conflicts(KB, "Q"), ["L2"])
        self.assertEqual(ed.key_conflicts(DS, "B1"), [])


class DialogKeysTest(tcu.DialogBase):
    """The window with a keyboard (a fake one: what GetAsyncKeyState would say) and a pad."""

    def keyboard(self):
        return tcu.FakePad(kind=KEYS1, key=KEYS1, name="Keyboard", vid=0, pid=0)

    def choose(self, key):
        self.dlg._choose(key)
        self.run_for(0.1)

    def test_the_keyboard_is_a_controller_of_the_window(self):
        kb, pad = self.keyboard(), tcu.FakePad()
        d = self.open(pad, kb)
        rows = {d.tv_players.item(i, "values")[2]: d.tv_players.item(i, "values")[1] for i in d.tv_players.get_children()}
        self.assertIn("Keyboard  ([keys1])", rows)
        self.assertEqual(rows["Keyboard  ([keys1])"], "Player 1")
        self.assertEqual(d.chosen, pad.key)                         # a pad first
        self.press(kb, "Z")
        self.assertEqual(d.chosen, pad.key)                         # keys work the window: never picked by a key
        self.choose(KEYS1)
        self.assertEqual(d.dev().kind, KEYS1)
        self.assertEqual(self.values("3")[0], "Z")                  # classic: Z is 3
        self.assertEqual(str(d.stick_box.cget("state")), "disabled")

    def test_l2_r2_and_a_combo_by_key_with_the_conflicts_said(self):
        kb = self.keyboard()
        d = self.open(tcu.FakePad(), kb)
        self.choose(KEYS1)
        d.begin(["L2"])
        self.assertIn("key", d.prompt_var.get())
        self.press(kb, "Q")
        self.assertEqual(d.editor.sources(d.dev(), "L2"), ["Q"])
        self.assertIn("Q was L1", d.status_var.get())                                   # the conflict is said
        d.begin(["R2", "1+2"])
        self.press(kb, "E")
        self.press(kb, "O")
        self.assertEqual(d.editor.sources(d.dev(), "R2"), ["E"])
        self.assertEqual(d.editor.sources(d.dev(), "1+2"), ["O"])
        d.do_save()
        text = self.saved()
        t = Controls(text).table(KEYS1)
        self.assertEqual((t.mask_of("Q"), t.mask_of("E"), t.mask_of("O")),
                         (padmap.PS3_BIT["L2"], padmap.PS3_BIT["R2"], padmap.target_mask("1+2")))

    def test_the_games_own_keys_are_refused_and_esc_stops(self):
        kb = self.keyboard()
        d = self.open(tcu.FakePad(), kb)
        self.choose(KEYS1)
        d.begin(["L3"])
        self.press(kb, "F11")
        self.assertIsNotNone(d.capture)                                                  # still asking
        self.assertIn("F11", d.status_var.get())
        self.press(kb, "V")
        self.assertEqual(d.editor.sources(d.dev(), "L3"), ["V"])
        d.begin(["R3"])
        self.press(kb, "ESC")
        self.assertIsNone(d.capture)
        self.assertEqual(d.editor.sources(d.dev(), "R3"), [])

    def test_the_keyboard_player_setting(self):
        kb = self.keyboard()
        d = self.open(tcu.FakePad(), kb)
        self.choose(KEYS1)
        d.player_var.set(d.player_opts[2][1])                                            # Player 2
        d._on_player_opt()
        self.assertEqual(d.editor.keyboard_pinned(KEYS1), 1)
        d.do_save()
        self.assertRegex(self.saved(), r"(?m)^keyboard = 2\r?$")

    def test_a_pad_still_binds_every_button(self):
        pad = tcu.FakePad()
        d = self.open(pad)
        for key, src in (("L2", "B5"), ("R2", "B6"), ("3+4", "B14"), ("L3", "B9"), ("SELECT", "B13")):
            d.begin([key])
            self.press(pad, src)
            self.assertEqual(d.editor.sources(d.dev(), key), [src], key)


if __name__ == "__main__":
    unittest.main()
