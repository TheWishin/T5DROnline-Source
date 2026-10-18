"""The launcher's Controls screen (launcher/controls_edit.py, launcher/controls_ui.py) without a real controller.

* the controls.ini editor keeps comments, unknown keys, spacing and line endings, and after every edit the
  bindings that padmap.py (= the game's parser) computes from the text are exactly what the edit meant -- a
  randomized comparison against a plain model of the game's rules;
* presets, reset to defaults, port options, pinning a controller to a player, save / load / backup;
* the names and rules it relies on are the runtime's (patches/ps3recomp/0009-controls.patch);
* capture, pad navigation and the whole screen with fake devices (the second half of this file).
"""
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))

import controls_edit as ce  # noqa: E402
from controls_edit import DeviceRef, IniDoc, ControlsEditor  # noqa: E402
from t5lobby import padmap  # noqa: E402
from t5lobby.padmap import DINPUT, XINPUT  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0009-controls.patch")


def sample_text():
    with open(os.path.join(ROOT, "docs", "controls.ini"), encoding="latin-1") as f:
        return f.read()


def added(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return "\n".join(l[1:] for l in f.read().splitlines() if l.startswith("+") and not l.startswith("+++"))


DI = DeviceRef(DINPUT, 0, 0x0F0D, 0x00EE)         # a stick on player 1
DI2 = DeviceRef(DINPUT, 1, 0x054C, 0x09CC)         # a DualShock 4 on player 2
XI = DeviceRef(XINPUT, 0, 0, 0)

HAND_MADE = """\
; my own file
[general]
socd = last            ; hitbox
foo = bar              ; a key nobody knows

[port1]
device = auto
stick = analog
macros = tekken

[dinput]
preset = ps
; global tweak
START = B9 ; start on the share button

[dinput.0F0D:00EE]
unknown_key = 12
2 = B3  ; right punch on the third button

[port1.dinput]
1 = B8
"""


class IniDocTest(unittest.TestCase):
    def test_untouched_text_comes_out_byte_for_byte(self):
        s = sample_text()
        for variant in (s, s.replace("\n", "\r\n"), s.rstrip("\n"), s + "\n\n\n", "", "\n", HAND_MADE,
                        "no section\nkey = 1\n[a\nk = 2\n[b]\n k  =  v  # c\n"):
            self.assertEqual(IniDoc(variant).render(), variant)

    def test_bom_is_dropped(self):
        # the game would not see the first section behind a BOM
        self.assertEqual(IniDoc("\xef\xbb\xbf[general]\nsocd = up\n").render(), "[general]\nsocd = up\n")

    def test_value_change_keeps_key_spelling_spacing_and_comment(self):
        d = IniDoc(HAND_MADE)
        d.set_value("dinput", "start", "B10")
        self.assertIn("START = B10 ; start on the share button", d.render())
        d.set_value("general", "SOCD", "up")
        self.assertIn("socd = up            ; hitbox", d.render().replace("up           ;", "up            ;"))
        d.set_value("dinput.0F0D:00EE", "2", "")
        self.assertRegex(d.render(), r"\n2 =\s+; right punch on the third button\n")

    def test_new_line_goes_after_the_last_key_and_its_comment_block(self):
        d = IniDoc("[a]\nx = 1\n; about x\n; more\n\n[b]\ny = 2\n")
        d.add_kv("a", "z", "3")
        self.assertEqual(d.render(), "[a]\nx = 1\n; about x\n; more\nz = 3\n\n[b]\ny = 2\n")
        d.add_kv("b", "w", "4")
        self.assertTrue(d.render().endswith("[b]\ny = 2\nw = 4\n"))

    def test_new_section_at_the_end_with_the_launchers_note(self):
        d = IniDoc("[a]\nx = 1")
        d.add_kv("new", "k", "v")
        self.assertEqual(d.render(), "[a]\nx = 1\n\n[new]\n" + ce.NOTE + "\nk = v\n")

    def test_only_the_first_section_of_a_name_counts_like_in_the_game(self):
        d = IniDoc("[a]\nx = 1\n[a]\nx = 2\n")
        self.assertEqual(d.get("a", "x"), "1")
        d.set_value("a", "x", "9")
        self.assertEqual(d.render(), "[a]\nx = 9\n[a]\nx = 2\n")

    def test_prune_removes_only_a_section_with_nothing_but_the_note(self):
        d = IniDoc("[a]\nx = 1\n")
        d.add_kv("n", "k", "v")
        d.remove_key("n", "k")
        self.assertTrue(d.prune_section("n"))
        self.assertEqual(d.render(), "[a]\nx = 1\n")
        d2 = IniDoc("[keep]\n; my comment\n")
        self.assertFalse(d2.prune_section("keep"))

    def test_the_parser_agrees_with_padmap_on_what_is_a_value(self):
        # padmap is the port of the game's parser: the same sections, keys and values
        for text in (sample_text(), HAND_MADE):
            c = padmap.Controls(text)
            d = IniDoc(text)
            for name, kvs in c.sections:
                if d.find_section(name) is None:
                    continue
                got = [(d.lines[i].key, d.lines[i].val) for i in d.kv_indices(name)]
                if c._section(name) is kvs:
                    self.assertEqual(got, kvs, name)


def mask_pairs(table):
    return frozenset((s, m) for s, m in table.binds)


class Reference:
    """The game's binding rules, written the plain way: the model the editor is compared with."""

    def __init__(self, pairs):
        self.b = dict(pairs)                    # source -> mask

    def bind(self, mask, srcs):
        self.b = {s: m for s, m in self.b.items() if s not in srcs and m != mask}
        for s in srcs:
            self.b[s] = mask

    def clear(self, mask):
        self.b = {s: m for s, m in self.b.items() if m != mask}

    def pairs(self):
        return frozenset(self.b.items())


SOURCES = {
    DINPUT: ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10", "B13", "HAT_UP", "HAT_LEFT", "X-", "Y+", "Z+"],
    XINPUT: ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "BACK", "START", "DUP", "LLEFT", "LUP"],
}


class EditorTest(unittest.TestCase):
    def check(self, ed, dev, ref, what=""):
        self.assertEqual(mask_pairs(ed.table(dev)), ref.pairs(), what)

    def test_bind_steals_the_button_from_whatever_had_it(self):
        ed = ControlsEditor("")
        self.assertEqual(ed.sources(DI, "3"), ["B2"])
        ed.bind(DI, ce.SCOPE_MODEL, "1", ["B2"])
        self.assertEqual(ed.sources(DI, "1"), ["B2"])
        self.assertEqual(ed.sources(DI, "3"), [])         # B2 was Cross = 3: now unassigned
        self.assertEqual(ed.sources(DI, "2"), ["B4"])     # the others are untouched
        self.assertIn("[dinput.0F0D:00EE]", ed.doc.render())

    def test_clear_where_the_preset_had_a_binding_writes_an_empty_line(self):
        ed = ControlsEditor("")
        ed.clear(DI, ce.SCOPE_MODEL, "4")
        self.assertEqual(ed.sources(DI, "4"), [])
        self.assertRegex(ed.doc.render(), r"\n4 =\r?\n")
        ed.bind(DI, ce.SCOPE_MODEL, "4", ["B3"])
        self.assertEqual(ed.sources(DI, "4"), ["B3"])
        self.assertNotIn("4 =\n", ed.doc.render())

    def test_clear_of_something_unbound_writes_nothing(self):
        ed = ControlsEditor("")
        ed.clear(DI, ce.SCOPE_MODEL, "1+2")
        self.assertEqual(ed.doc.render().count("1+2"), 0)

    def test_bind_add_keeps_the_old_button(self):
        ed = ControlsEditor("")
        ed.bind(DI, ce.SCOPE_MODEL, "START", ["B13"], add=True)
        self.assertEqual(sorted(ed.sources(DI, "START")), ["B10", "B13"])

    def test_a_button_bound_to_a_macro_is_stolen_by_a_single_button(self):
        ed = ControlsEditor("[port1]\nmacros = tekken\n")
        self.assertEqual(ed.sources(DI, "1+2"), ["B6"])
        ed.bind(DI, ce.SCOPE_MODEL, "1", ["B6"])
        self.assertEqual(ed.sources(DI, "1+2"), [])
        self.assertEqual(ed.sources(DI, "1"), ["B6"])

    def test_wrong_input_names_are_refused(self):
        ed = ControlsEditor("")
        with self.assertRaises(ValueError):
            ed.bind(DI, ce.SCOPE_MODEL, "1", ["A"])           # an XInput name on a DirectInput stick
        with self.assertRaises(ValueError):
            ed.bind(DI, ce.SCOPE_MODEL, "FIRE", ["B1"])
        self.assertFalse(ed.dirty)

    def test_unknown_keys_comments_and_spacing_survive_edits(self):
        ed = ControlsEditor(HAND_MADE)
        before = [l for l in HAND_MADE.splitlines()]
        ed.bind(DI, ce.SCOPE_MODEL, "1", ["B9"])
        ed.bind(DI, ce.SCOPE_MODEL, "3+4", ["B13"])
        ed.apply_recipe(DI2, ce.SCOPE_KIND, "default")
        ed.set_port_option(0, "socd", "up")
        out = ed.doc.render().splitlines()
        for keep in ("; my own file", "foo = bar              ; a key nobody knows", "; global tweak",
                     "unknown_key = 12", "device = auto"):
            self.assertIn(keep, out)
        self.assertIn("socd = last            ; hitbox", out)       # [general] is not [port1]
        # every comment line of the original is still there, in order
        comments = [l for l in before if l.strip().startswith(";")]
        it = iter(out)
        for c in comments:
            self.assertTrue(any(c == o for o in it), c)

    def test_a_more_specific_section_that_would_override_is_cleaned(self):
        ed = ControlsEditor(HAND_MADE)
        self.assertEqual(ed.sources(DI, "1"), ["B8"])               # [port1.dinput] says 1 = B8
        ed.bind(DI, ce.SCOPE_MODEL, "1", ["B1"])
        self.assertEqual(ed.sources(DI, "1"), ["B1"])
        self.assertTrue(ed.notes)
        self.assertNotIn("1 = B8", ed.doc.render())

    def test_random_edits_do_what_the_game_would(self):
        rng = random.Random(5)
        keys = [s.key for s in ce.SLOTS]
        bases = [("", DI), ("", XI), (sample_text(), DI), (sample_text(), DI2), (HAND_MADE, DI),
                 ("[port1]\nmacros = tekken\n[port1.dinput]\n1 = B3\n[dinput]\nL1 = B13\n", DI),
                 ("[xinput]\nmacros = tekken\n[port1.xinput]\nSTART = Y\n", XI)]
        for base, dev in bases:
            for _round in range(25):
                ed = ControlsEditor(base)
                ref = Reference(mask_pairs(ed.table(dev)))
                scopes = ed.scopes(dev)
                for _step in range(14):
                    key = rng.choice(keys)
                    mask = padmap.target_mask(key)
                    scope = rng.choice(scopes)
                    r = rng.random()
                    if r < 0.6:
                        srcs = rng.sample(SOURCES[dev.kind], rng.choice((1, 1, 1, 2)))
                        add = rng.random() < 0.15
                        if add:
                            srcs = ed.sources(dev, key) + [s for s in srcs if s not in ed.sources(dev, key)]
                        ed.bind(dev, scope, key, srcs, add=False)
                        ref.bind(mask, srcs)
                    elif r < 0.85:
                        ed.clear(dev, scope, key)
                        ref.clear(mask)
                    else:
                        continue
                    self.check(ed, dev, ref, f"{base[:20]!r} {dev} {key} {scope}\n{ed.doc.render()}")
                # the text is still a valid file: no warnings the editor made
                self.assertEqual([w for w in ed.controls().warnings if "unknown" in w and "preset" in w], [])

    def test_every_preset_round_trips(self):
        for kind, dev in ((DINPUT, DI), (XINPUT, XI)):
            for r in ce.recipes_for(kind):
                for scope in ControlsEditor("").scopes(dev):
                    for base in ("", sample_text(), HAND_MADE):
                        ed = ControlsEditor(base)
                        ed.bind(dev, scope, "1", [SOURCES[kind][5]])           # something of their own first
                        ok = ed.apply_recipe(dev, scope, r.id)
                        where = f"{r.id} {kind} {scope} {base[:12]!r}"
                        if kind == DINPUT and base == HAND_MADE and scope != ce.SCOPE_KIND:
                            # the shared [dinput] section of that file moves START: the screen says so
                            self.assertFalse(ok, where)
                            self.assertTrue(any("[dinput]" in n for n in ed.notes), where)
                            continue
                        self.assertTrue(ok, where)
                        self.assertEqual(mask_pairs(ed.table(dev)), ce.recipe_pairs(kind, r.specs[kind]), where)
                        # ... and once more from the file as it was written
                        self.assertEqual(ControlsEditor(ed.doc.render()).detect_recipe(dev), r.id, where)

    def test_the_presets_say_what_they_say(self):
        ed = ControlsEditor("")
        ed.apply_recipe(DI, ce.SCOPE_MODEL, "vewlix")
        self.assertEqual([ed.sources(DI, k) for k in ("1", "2", "3", "4", "1+2", "3+4", "1+3", "2+4")],
                         [["B1"], ["B4"], ["B2"], ["B3"], ["B6"], ["B8"], ["B5"], ["B7"]])
        ed.apply_recipe(DI, ce.SCOPE_MODEL, "astro")
        self.assertEqual([ed.sources(DI, k) for k in ("1+2", "3+4", "1+3", "2+4")], [["B6"], ["B8"], [], []])
        self.assertEqual(padmap.target_mask("L1"), padmap.target_mask("L1"))
        self.assertEqual(ed.table(DI).mask_of("B5"), padmap.target_mask("L1"))
        ed.apply_recipe(XI, ce.SCOPE_KIND, "vewlix")
        self.assertEqual([ed.sources(XI, k) for k in ("1", "2", "3", "4", "1+2", "3+4", "1+3", "2+4")],
                         [["X"], ["Y"], ["A"], ["B"], ["RB"], ["RT"], ["LB"], ["LT"]])

    def test_hitbox_sets_the_stick_mode_and_socd_of_the_port(self):
        ed = ControlsEditor(sample_text())
        ed.apply_recipe(DI, ce.SCOPE_MODEL, "hitbox")
        self.assertEqual((ed.stick_of(0), ed.socd_of(0)), ("dpad", "neutral"))
        self.assertEqual((ed.stick_of(1), ed.socd_of(1)), ("analog", "neutral"))

    def test_applying_a_preset_without_macros_turns_the_ports_macros_off(self):
        ed = ControlsEditor("[port1]\nmacros = tekken\n")
        self.assertTrue(ed.macros_on(DI))
        ed.apply_recipe(DI, ce.SCOPE_MODEL, "default")
        self.assertFalse(ed.macros_on(DI))
        self.assertEqual(ed.detect_recipe(DI), "default")

    def test_detect_recipe_says_none_for_an_own_layout(self):
        ed = ControlsEditor("")
        self.assertEqual(ed.detect_recipe(DI), "default")
        ed.bind(DI, ce.SCOPE_MODEL, "1", ["B13"])
        self.assertIsNone(ed.detect_recipe(DI))

    def test_reset_goes_back_to_the_defaults_and_keeps_the_rest(self):
        for base in ("", sample_text(), HAND_MADE):
            ed = ControlsEditor(base)
            default = mask_pairs(ControlsEditor("").table(DI))
            ed.apply_recipe(DI, ce.SCOPE_MODEL, "hitbox")
            ed.bind(DI, ce.SCOPE_PORT, "START", ["B13"])
            ed.set_port_option(0, "socd", "last")
            ed.reset(DI, shared=base == HAND_MADE)
            if base != HAND_MADE:
                self.assertEqual(mask_pairs(ed.table(DI)), default, base[:15])
            self.assertEqual((ed.stick_of(0), ed.socd_of(0)), ("analog", ed.controls()._get("general", "socd") or "neutral"))
            out = ed.doc.render()
            self.assertNotIn("[dinput.0F0D:00EE]\n" + ce.NOTE, out) if base == "" else None
            for line in base.splitlines():
                if line.strip().startswith(";"):
                    self.assertIn(line, out.splitlines())
        # `shared` also empties [dinput]; without it the shared lines stay
        ed = ControlsEditor(HAND_MADE)
        ed.reset(DI, shared=False)
        self.assertIn("START = B9 ; start on the share button", ed.doc.render())
        self.assertIn("unknown_key = 12", ed.doc.render())
        self.assertNotIn("1 = B8", ed.doc.render())

    def test_reset_of_an_untouched_file_changes_nothing(self):
        ed = ControlsEditor(sample_text())
        ed.reset(DI)
        self.assertEqual(ed.doc.render(), sample_text())

    def test_port_options(self):
        ed = ControlsEditor(sample_text())
        ed.set_port_option(0, "stick", "dpad")
        ed.set_port_option(0, "socd", "up")
        self.assertEqual((ed.stick_of(0), ed.socd_of(0)), ("dpad", "up"))
        self.assertEqual(ed.socd_of(1), "neutral")
        ed.set_port_option(1, "socd", "last")
        self.assertEqual(ed.socd_of(1), "last")
        for bad in (("stick", "left"), ("socd", "x"), ("speed", "1")):
            with self.assertRaises(ValueError):
                ed.set_port_option(0, *bad)

    def test_assign_port_pins_one_controller_and_frees_the_other_port(self):
        ed = ControlsEditor(sample_text())
        ed.assign_port("dinput:0F0D:00EE", 1)
        self.assertEqual(ed.pinned(1), "dinput:0F0D:00EE")
        ed.assign_port("dinput:0F0D:00EE", 0)
        self.assertEqual((ed.pinned(0), ed.pinned(1)), ("dinput:0F0D:00EE", "auto"))
        ed.assign_port("dinput:0F0D:00EE", None)
        self.assertEqual((ed.pinned(0), ed.pinned(1)), ("auto", "auto"))
        # the game's rules agree: the pinned stick takes the pinned port
        ed.assign_port("dinput:0F0D:00EE", 1)

        class D:
            kind, slot, vid, pid, name = DINPUT, None, 0x0F0D, 0x00EE, "stick"
        self.assertTrue(ed.controls().port_matches(1, D))
        self.assertFalse(ed.controls().port_matches(0, D))

    def test_default_scope_follows_where_the_buttons_already_are(self):
        self.assertEqual(ControlsEditor("").default_scope(DI), ce.SCOPE_MODEL)
        self.assertEqual(ControlsEditor("").default_scope(XI), ce.SCOPE_KIND)
        self.assertEqual(ControlsEditor(sample_text()).default_scope(DI), ce.SCOPE_MODEL)
        self.assertEqual(ControlsEditor(sample_text()).default_scope(XI), ce.SCOPE_KIND)
        self.assertEqual(ControlsEditor(HAND_MADE).default_scope(DI), ce.SCOPE_PORT)
        self.assertEqual(ControlsEditor(HAND_MADE).default_scope(DI2), ce.SCOPE_KIND)   # [dinput] has START = B9
        self.assertEqual(ControlsEditor(HAND_MADE).default_scope(DeviceRef(DINPUT, -1, 0, 0)), ce.SCOPE_KIND)

    def test_new_file_starts_with_a_header_and_no_other_defaults_change(self):
        ed = ControlsEditor("")
        ed.bind(DI, ce.SCOPE_MODEL, "1", ["B13"])
        text = ed.doc.render()
        self.assertTrue(text.startswith("; T5DR Online controls.ini"))
        self.assertNotIn("[dinput]", text)                  # a Switch pad still gets its own default preset
        sw = DeviceRef(DINPUT, 0, 0x057E, 0x2009)
        self.assertEqual(ed.preset_name(sw), "switch")

    def test_limits_of_the_games_tables_are_checked(self):
        ed = ControlsEditor("[a]\n" + "k = 1\n" * 767)
        self.assertEqual(ed.validate(), [])
        ed = ControlsEditor("[a]\n" + "k = 1\n" * 768)
        self.assertTrue(ed.validate())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                ed.save(os.path.join(d, "controls.ini"))


class SaveLoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "out", "controls.ini")

    def test_new_file_is_created_with_its_folder(self):
        ed = ControlsEditor.load(self.path)
        self.assertFalse(ed.exists)
        ed.apply_recipe(DI, ce.SCOPE_MODEL, "vewlix")
        ed.save()
        self.assertTrue(os.path.isfile(self.path))
        back = ControlsEditor.load(self.path)
        self.assertEqual(back.detect_recipe(DI), "vewlix")
        self.assertEqual(mask_pairs(back.table(DI)), mask_pairs(ed.table(DI)))
        self.assertFalse(back.dirty)
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["controls.ini"])      # no temp file left

    def test_existing_file_is_kept_and_backed_up_once(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "wb") as f:
            f.write(HAND_MADE.replace("\n", "\r\n").encode("latin-1"))
        ed = ControlsEditor.load(self.path)
        ed.bind(DI, ce.SCOPE_MODEL, "3", ["B13"])
        ed.save()
        with open(self.path + ".bak", "rb") as f:
            self.assertEqual(f.read(), HAND_MADE.replace("\n", "\r\n").encode("latin-1"))
        ed.bind(DI, ce.SCOPE_MODEL, "4", ["B14"])
        ed.save()
        with open(self.path + ".bak", "rb") as f:
            bak = f.read()
        self.assertIn(b"foo = bar", bak)
        self.assertNotIn(b"B13", bak)                                                    # still the first original
        with open(self.path, "rb") as f:
            data = f.read()
        self.assertIn(b"\r\n", data)
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))                              # CRLF kept everywhere
        self.assertIn(b"3 = B13", data)

    def test_a_file_changed_on_disk_is_not_overwritten_by_surprise(self):
        ed = ControlsEditor("")
        ed.apply_recipe(DI, ce.SCOPE_MODEL, "vewlix")
        ed.save(self.path)
        ed.bind(DI, ce.SCOPE_MODEL, "1", ["B13"])
        with open(self.path, "ab") as f:
            f.write(b"; someone edited this\n")
        with self.assertRaises(ce.FileChanged):
            ed.save()
        ed.save(force=True)
        with open(self.path, "rb") as f:
            self.assertNotIn(b"someone edited", f.read())
        with open(self.path + ".bak", "rb") as f:                                        # what was overwritten is kept
            self.assertIn(b"someone edited", f.read())

    def test_non_ascii_bytes_in_comments_survive(self):
        os.makedirs(os.path.dirname(self.path))
        raw = "; Taste für Läufer \xe9\n[dinput]\nstart = B9\n".encode("latin-1")
        with open(self.path, "wb") as f:
            f.write(raw)
        ed = ControlsEditor.load(self.path)
        ed.bind(DI, ce.SCOPE_MODEL, "1", ["B13"])
        ed.save()
        with open(self.path, "rb") as f:
            self.assertTrue(f.read().startswith(raw))

    def test_path_is_the_one_the_game_reads(self):
        out = os.path.join(self.tmp.name, "native")
        os.makedirs(os.path.join(out, "build", "cmake"))
        self.assertEqual(ce.controls_path(out, {}), os.path.join(out, "controls.ini"))
        open(os.path.join(out, "controls.ini"), "w").close()
        self.assertEqual(ce.controls_path(out, {}), os.path.join(out, "controls.ini"))
        open(os.path.join(out, "build", "cmake", "controls.ini"), "w").close()      # next to t5dr.exe wins
        self.assertEqual(ce.controls_path(out, {}), os.path.join(out, "build", "cmake", "controls.ini"))
        forced = os.path.join(self.tmp.name, "mine.ini")
        self.assertEqual(ce.controls_path(out, {"PS3_CONTROLS": forced}), forced)


class ShippingTest(unittest.TestCase):
    def test_the_screen_ships_in_the_release(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import package_release
        import smoke_release
        for f in ("launcher/controls_ui.py", "launcher/controls_edit.py"):
            self.assertIn(f, package_release.OUR_FILES)
            self.assertIn(f, smoke_release.REQUIRED)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, *f.split("/"))))

    def test_the_launcher_has_the_button_and_hands_over_to_the_module(self):
        path = os.path.join(ROOT, "launcher", "t5dr_launcher.pyw")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        for needle in ("import controls_ui", "def open_controls(self)", "controls_ui.open_dialog(self)",
                       "controls_ui.close_for_app(self)", "Set up controllers"):
            self.assertIn(needle, src)
        compile(src, path, "exec")


class RuntimeAgreementTest(unittest.TestCase):
    """What the editor writes only uses names and rules the runtime has (patches/ps3recomp/0009)."""

    @classmethod
    def setUpClass(cls):
        cls.src = added(PATCH)

    def test_runtime_has_every_preset_name_the_screen_writes(self):
        found = {(m.group(1).lower(), m.group(2)) for m in re.finditer(r'\{\s*"(\w+)",\s*(CLS_\w+),\s*k_\w+\s*\}',
                                                                     self.src)}
        cls_of = {XINPUT: "CLS_XINPUT", DINPUT: "CLS_DINPUT"}
        for r in ce.RECIPES:
            for kind, spec in r.specs.items():
                self.assertIn((spec.preset, cls_of[kind]), found, f"{r.id}: preset {spec.preset}")
                if spec.macros:
                    self.assertRegex(self.src, rf'name_eq\(macros, "{spec.macros}"\)')

    def test_runtime_has_the_port_options_and_their_values(self):
        for key in ("stick", "socd", "device", "macros"):
            self.assertRegex(self.src, rf'"{key}"')
        self.assertRegex(self.src, r'name_eq\(st, "dpad"\)')
        for mode in ce.SOCD_MODES:
            self.assertRegex(self.src, rf'name_eq\(v, "{mode}"\)')

    def test_section_names_of_the_layers_are_the_runtimes(self):
        self.assertIn('"dinput.%04X:%04X"', self.src)
        self.assertIn('"port%d.%s"', self.src)
        self.assertIn('k_cls_name[] = { "keys", "xinput", "dinput" }', self.src.replace("[]  =", "[] ="))
        self.assertEqual([n for _s, n in ControlsEditor("").layers(DI)],
                         ["dinput", "dinput.0F0D:00EE", "port1.dinput"])
        self.assertEqual([n for _s, n in ControlsEditor("").layers(XI)], ["xinput", "port1.xinput"])

    def test_tables_limits_are_the_runtimes(self):
        self.assertIn(f"#define INI_MAX_KV  {ce.MAX_KV}", self.src)
        self.assertIn(f"#define INI_MAX_SEC {ce.MAX_SECTIONS}", self.src)
        self.assertIn(f"int srcs[{ce.MAX_SOURCES}]", self.src)

    def test_every_source_the_screen_can_write_is_one_the_runtime_parses(self):
        # DirectInput: B1..B128, HAT[n]_dir, axis+/-; XInput: the k_xinput_src table (padmap test_padmap_sync checks it)
        self.assertRegex(self.src, r"n >= 1 && n <= 128")
        for name in ("HAT_UP", "X-", "RZ+", "S1-", "B128", "HAT4_LEFT"):
            self.assertIsNotNone(padmap.canon_source(DINPUT, name), name)
        for name in padmap.XINPUT_SOURCES:
            self.assertIsNotNone(padmap.canon_source(XINPUT, name), name)
        self.assertIsNone(padmap.canon_source(DINPUT, "B129"))
        self.assertIsNone(padmap.canon_source(DINPUT, "LT"))


def find_ps3recomp():
    """A ps3recomp tree that has the controls patch applied (PS3RECOMP_DIR, ./deps/ps3recomp, or the main
    checkout's deps/ps3recomp when this is a git worktree)."""
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
        if c and os.path.isfile(os.path.join(c, "libs", "input", "pad_host_win32.c")):
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


class RuntimeDifferentialTest(unittest.TestCase):
    """The runtime's own parser (libs/input/pad_host_win32.c, compiled into tests/c/pad_table_dump.c) against
    padmap.py and the editor: for many files and controllers the same bindings and port options. Needs the
    patched ps3recomp tree and a Windows C compiler (clang-cl or cl with the Windows SDK); skipped without."""

    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("the runtime's pad layer is Windows only")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no patched ps3recomp tree (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "pad_table_dump.exe")
        inc = [os.path.join(cls.tree, *p) for p in (("libs", "input"), ("libs",), ("runtime",), ("include",))]
        src = os.path.join(ROOT, "tests", "c", "pad_table_dump.c")
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 {flags} "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "pad_table_dump.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise unittest.SkipTest("could not build tests/c/pad_table_dump.c: " + (r.stdout + r.stderr)[-400:])
        cls.exe = exe
        cls.n = 0

    DEVICES = (
        ("xinput:0", XINPUT, 0, 0, 0),
        ("xinput:1", XINPUT, 1, 0, 0),
        ("dinput:0:0F0D:00EE", DINPUT, 0, 0x0F0D, 0x00EE),
        ("dinput:1:054C:09CC", DINPUT, 1, 0x054C, 0x09CC),
        ("dinput:0:057E:2009", DINPUT, 0, 0x057E, 0x2009),
        ("dinput:2:045E:0B13", DINPUT, 2, 0x045E, 0x0B13),
        ("dinput:-1:0F0D:00EE", DINPUT, -1, 0x0F0D, 0x00EE),
    )

    def dump(self, text):
        self.__class__.n += 1
        path = os.path.join(self.tmp.name, f"c{self.n}.ini")
        with open(path, "wb") as f:
            f.write(text.encode("latin-1"))
        r = subprocess.run([self.exe, f"ini={path}"] + [d[0] for d in self.DEVICES], capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        tables, ports, cur = {}, [], None
        for line in r.stdout.splitlines():
            if line.startswith("TABLE "):
                cur = tables.setdefault(line[6:], [])
            elif line.startswith("BIND ") and cur is not None:
                _b, name, mask = line.split()
                cur.append((re.sub(r"^HAT1_", "HAT_", name), int(mask, 16)))
            elif line.startswith("PORT "):
                ports.append(dict(kv.split("=", 1) for kv in line.split()[2:]))
        return tables, ports

    def compare(self, text, what=""):
        tables, ports = self.dump(text)
        ed = ControlsEditor(text)
        for label, kind, port, vid, pid in self.DEVICES:
            theirs = frozenset(tables[label])
            ours = frozenset((s, m) for s, m in ed.controls().table(kind, port, vid, pid).binds)
            self.assertEqual(ours, theirs, f"{what} {label}\n{text}")
        socd = {"off": "0", "neutral": "1", "up": "2", "last": "3"}
        c = ed.controls()
        for p in range(padmap.MAX_PORTS):
            self.assertEqual(ports[p]["stick"], "1" if ed.stick_of(p) == "dpad" else "0", f"{what} stick port {p + 1}")
            self.assertEqual(ports[p]["socd"], socd[ed.socd_of(p)], f"{what} socd port {p + 1}\n{text}")
            spec = c.ports[p]
            self.assertEqual(int(ports[p]["spec"]), {"auto": 0, "none": 1, XINPUT: 2, DINPUT: 3}[spec["kind"]])
            self.assertEqual(int(ports[p]["slot"]), -1 if spec["slot"] is None else spec["slot"])
            self.assertEqual((int(ports[p]["vid"], 16), int(ports[p]["pid"], 16)), (spec["vid"], spec["pid"]))

    def test_the_files_we_know(self):
        for name, text in (("empty", ""), ("sample", sample_text()), ("hand made", HAND_MADE)):
            self.compare(text, name)

    def test_presets_and_edits(self):
        rng = random.Random(11)
        keys = [s.key for s in ce.SLOTS]
        for base in ("", sample_text(), HAND_MADE):
            for kind, dev in ((DINPUT, DI), (XINPUT, XI), (DINPUT, DI2)):
                for r in ce.recipes_for(kind):
                    for scope in ControlsEditor("").scopes(dev):
                        ed = ControlsEditor(base)
                        ed.apply_recipe(dev, scope, r.id)
                        self.compare(ed.doc.render(), f"{r.id} {scope}")
                for _round in range(6):
                    ed = ControlsEditor(base)
                    for _step in range(10):
                        key, scope = rng.choice(keys), rng.choice(ed.scopes(dev))
                        r = rng.random()
                        if r < 0.55:
                            ed.bind(dev, scope, key, rng.sample(SOURCES[kind], rng.choice((1, 2))))
                        elif r < 0.8:
                            ed.clear(dev, scope, key)
                        elif r < 0.9:
                            ed.set_port_option(dev.port, "socd", rng.choice(ce.SOCD_MODES))
                            ed.set_port_option(dev.port, "stick", rng.choice(ce.STICK_MODES))
                        else:
                            ed.reset(dev, shared=rng.random() < 0.5)
                    self.compare(ed.doc.render(), "random")

    def test_port_options_and_pins(self):
        ed = ControlsEditor(sample_text())
        ed.set_port_option(0, "stick", "dpad")
        for mode in ce.SOCD_MODES:
            ed.set_port_option(1, "socd", mode)
            self.compare(ed.doc.render(), mode)
        ed.assign_port("dinput:0F0D:00EE", 1)
        ed.assign_port("xinput:0", 0)
        self.compare(ed.doc.render(), "pins")
        ed.assign_port("dinput:Hori", 0)
        self.compare(ed.doc.render(), "pin by name")


# ====================================================================== capture, navigation, the screen
# Fake controllers only (no device is ever read), a fake clock, and a withdrawn Tk root: nothing is shown.

try:
    import tkinter as tk
    import controls_ui as cu
except ImportError:                                 # no tkinter in this Python
    tk = cu = None

from t5lobby import padnav  # noqa: E402
from t5lobby.padnav import Device  # noqa: E402


class FakePad(padnav.PadSource):
    """A controller that does what the test says."""

    def __init__(self, kind=DINPUT, key="winmm:0", name="Fake Stick", vid=0x0F0D, pid=0x00EE, slot=None):
        self.kind, self.key, self.name, self.vid, self.pid, self.slot = kind, key, name, vid, pid, slot
        self.held = set()
        self.plugged = True
        self.reads = 0

    def read(self):
        self.reads += 1
        if not self.plugged:
            return []
        return [Device(self.kind, self.key, self.name, self.vid, self.pid, self.slot, frozenset(self.held))]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeSettings:
    def __init__(self, out):
        self.out_dir = out

    def env_overrides(self):
        return {}


def xpad():
    return FakePad(XINPUT, "xinput:0", "XInput #1 (gamepad)", 0, 0, 0)


@unittest.skipIf(cu is None, "no tkinter")
class PollerTest(unittest.TestCase):
    def rig(self, *pads, front=True):
        self.clock = Clock()
        self.front = front
        self.poller = cu.DevicePoller(pads, foreground=lambda: self.front, clock=self.clock)

    def run_for(self, seconds):
        end = self.clock.t + seconds
        while self.clock.t < end - 1e-9:
            self.poller.step(self.clock.t)
            self.clock.t += 1 / 60

    def test_a_press_is_one_edge_and_a_held_button_is_not_repeated(self):
        pad = FakePad()
        self.rig(pad)
        self.run_for(0.1)
        pad.held = {"B2"}
        self.run_for(0.3)
        pad.held = {"B2", "HAT_UP"}
        self.run_for(0.1)
        edges = [(e.key, e.source) for e in self.poller.drain()]
        self.assertEqual(edges, [("winmm:0", "B2"), ("winmm:0", "HAT_UP")])
        self.assertEqual(self.poller.held["winmm:0"], {"B2", "HAT_UP"})

    def test_buttons_held_when_the_window_comes_forward_make_no_edge(self):
        pad = FakePad()
        pad.held = {"B1"}
        self.rig(pad)
        self.run_for(0.2)
        self.assertEqual(self.poller.drain(), [])
        pad.held = set()
        self.run_for(0.1)
        pad.held = {"B1"}
        self.run_for(0.1)
        self.assertEqual([e.source for e in self.poller.drain()], ["B1"])

    def test_an_axis_resting_at_its_end_is_not_a_press_until_it_has_been_let_go(self):
        pad = FakePad()
        pad.held = {"RX-", "RY-"}                       # DualShock triggers rest at -32768
        self.rig(pad)
        self.run_for(0.2)
        self.assertEqual(self.poller.held["winmm:0"], frozenset())
        pad.held = {"RX-", "RY-", "B7"}
        self.run_for(0.1)
        self.assertEqual([e.source for e in self.poller.drain()], ["B7"])
        pad.held = {"RX-", "RY-", "RX+"}                # RX left its end ... and goes to the other
        self.run_for(0.1)
        pad.held = {"RY-"}
        self.run_for(0.1)
        self.poller.drain()
        pad.held = {"RY-", "RX-"}                       # RX- is a real press now
        self.run_for(0.1)
        self.assertEqual([e.source for e in self.poller.drain()], ["RX-"])

    def test_nothing_is_read_while_the_window_is_not_in_front(self):
        pad = FakePad()
        self.rig(pad, front=False)
        self.run_for(1.0)
        self.assertEqual(pad.reads, 0)
        self.assertEqual(self.poller.devices, ())
        self.front = True
        self.run_for(0.1)
        self.assertGreater(pad.reads, 0)
        pad.held = {"B1"}
        self.run_for(0.1)
        self.poller.drain()
        self.front = False
        n = pad.reads
        self.run_for(0.5)
        self.assertEqual(pad.reads, n)
        self.assertEqual(self.poller.held, {})
        self.front = True
        self.run_for(0.2)                               # B1 is still down: forgotten, so it is not a press
        self.assertEqual(self.poller.drain(), [])

    def test_plugging_in_and_out(self):
        pad = FakePad()
        pad.plugged = False
        self.rig(pad)
        self.run_for(0.2)
        self.assertEqual(self.poller.devices, ())
        pad.plugged = True
        pad.held = {"B3"}
        self.run_for(0.2)
        self.assertEqual(len(self.poller.devices), 1)
        self.assertEqual(self.poller.drain(), [])       # held when it appeared: not a press
        pad.plugged = False
        self.run_for(0.2)
        self.assertEqual(self.poller.devices, ())

    def test_a_source_that_raises_does_not_stop_the_others(self):
        class Bad(padnav.PadSource):
            def read(self):
                raise OSError("boom")
        good = FakePad()
        self.rig(Bad(), good)
        self.run_for(0.1)
        self.assertEqual(len(self.poller.devices), 1)
        self.assertIn("boom", self.poller.error)

    def test_the_real_thread_polls(self):
        pad = FakePad()
        poller = cu.DevicePoller([pad], foreground=lambda: True)
        poller.start()
        try:
            time.sleep(0.15)
            pad.held = {"B5"}
            deadline = time.time() + 2
            while time.time() < deadline and not poller.edges.qsize():
                time.sleep(0.02)
            self.assertEqual([e.source for e in poller.drain()], ["B5"])
        finally:
            poller.stop()


@unittest.skipIf(cu is None, "no tkinter")
class CaptureTest(unittest.TestCase):
    E = cu.Edge if cu else None

    def test_one_press_is_taken_after_the_settle_time(self):
        c = cu.Capture(0.0)
        self.assertIsNone(c.update(1.00, [self.E(1.00, "k", "B3")]))
        self.assertIsNone(c.update(1.04, []))
        self.assertEqual(c.update(1.10, []), ("ok", "B3"))

    def test_presses_together_are_several_buttons(self):
        c = cu.Capture(0.0)
        c.update(1.00, [self.E(1.00, "k", "HAT_UP")])
        self.assertEqual(c.update(1.10, [self.E(1.03, "k", "HAT_RIGHT")]), ("multi", ["HAT_UP", "HAT_RIGHT"]))

    def test_a_second_press_after_the_settle_time_is_not_part_of_it(self):
        c = cu.Capture(0.0)
        c.update(1.00, [self.E(1.00, "k", "B1")])
        self.assertEqual(c.update(1.20, [self.E(1.15, "k", "B2")]), ("ok", "B1"))

    def test_timeout_only_when_asked_for(self):
        self.assertIsNone(cu.Capture(0.0).update(100.0, []))
        self.assertEqual(cu.Capture(0.0, timeout_s=8).update(8.5, []), ("timeout", None))
        c = cu.Capture(0.0, timeout_s=8)
        c.update(7.0, [self.E(7.0, "k", "B1")])
        self.assertEqual(c.update(9.0, []), ("ok", "B1"))


@unittest.skipIf(cu is None, "no tkinter")
class NavigationTest(unittest.TestCase):
    def test_the_sources_that_are_cross_circle_triangle_start_up_down(self):
        ed = ControlsEditor("")
        m = cu.nav_map(ed, DI)
        self.assertEqual((m["B2"], m["B3"], m["B4"], m["B10"], m["HAT_UP"], m["HAT_DOWN"]),
                         ("accept", "back", "clear", "save", "up", "down"))
        m = cu.nav_map(ed, XI)
        self.assertEqual((m["A"], m["B"], m["Y"], m["START"], m["DUP"], m["LDOWN"]),
                         ("accept", "back", "clear", "save", "up", "down"))

    def test_it_follows_the_players_own_buttons_and_falls_back_when_cleared(self):
        ed = ControlsEditor("")
        ed.bind(DI, ce.SCOPE_MODEL, "3", ["B13"])
        self.assertEqual(cu.nav_map(ed, DI)["B13"], "accept")
        self.assertNotIn("B2", cu.nav_map(ed, DI))
        ed.clear(DI, ce.SCOPE_MODEL, "3")
        self.assertEqual(cu.nav_map(ed, DI)["B2"], "accept")           # the default layout's Cross

    def test_up_and_down_repeat_while_held(self):
        nav = cu.PadNavigator(delay=0.4, repeat=0.1)
        m = {"HAT_DOWN": "down", "B2": "accept"}
        out = nav.feed(0.0, [cu.Edge(0.0, "k", "HAT_DOWN")], {"HAT_DOWN"}, m)
        self.assertEqual(out, ["down"])
        self.assertEqual(nav.feed(0.3, [], {"HAT_DOWN"}, m), [])
        self.assertEqual(nav.feed(0.45, [], {"HAT_DOWN"}, m), ["down"])
        self.assertEqual(nav.feed(0.6, [], {"HAT_DOWN"}, m), ["down"])
        self.assertEqual(nav.feed(0.7, [], set(), m), [])
        self.assertEqual(nav.feed(2.0, [], set(), m), [])
        self.assertEqual(nav.feed(2.1, [cu.Edge(2.1, "k", "B2")], {"B2"}, m), ["accept"])      # no repeat for accept
        self.assertEqual(nav.feed(3.0, [], {"B2"}, m), [])


@unittest.skipIf(cu is None, "no tkinter")
class DialogBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("no display for Tk")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = self.tmp.name
        self.ini = os.path.join(self.out, "controls.ini")
        self.clock = Clock()
        self.front = True
        self.answer = True
        self.asked = []
        self.dlg = None

    def open(self, *pads, ini=None, running=False):
        if ini is not None:
            with open(self.ini, "wb") as f:
                f.write(ini.encode("latin-1"))
        pads = pads or (FakePad(),)

        def ask(kind, title, text):
            self.asked.append((kind, title, text))
            return self.answer
        self.dlg = cu.ControlsDialog(self.root, FakeSettings(self.out), sources=list(pads),
                                     foreground=lambda: self.front, clock=self.clock, thread=False, ask=ask,
                                     game_running=lambda: running)
        self.addCleanup(self.cleanup_dialog)
        self.run_for(0.2)
        return self.dlg

    def cleanup_dialog(self):
        if self.dlg is not None and self.dlg.alive():
            self.dlg.editor.saved_text = self.dlg.editor.doc.render()        # (nothing to ask on the way out)
            self.dlg.close()

    def run_for(self, seconds):
        end = self.clock.t + seconds
        while self.clock.t < end - 1e-9:
            self.dlg.poller.step(self.clock.t)
            self.dlg.pump()
            self.clock.t += 1 / 60

    def press(self, pad, *srcs, hold=0.15, then=0.25):
        pad.held |= set(srcs)
        self.run_for(hold)
        pad.held -= set(srcs)
        self.run_for(then)

    def values(self, key):
        return self.dlg.tv.item(key, "values")

    def saved(self):
        with open(self.ini, encoding="latin-1") as f:
            return f.read()


class DialogTest(DialogBase):
    def test_it_shows_the_controller_on_its_player_with_its_buttons(self):
        stick = FakePad()
        d = self.open(stick)
        self.assertEqual(d.chosen, "winmm:0")
        rows = {i: d.tv_players.item(i, "values") for i in d.tv_players.get_children()}
        self.assertIn("Fake Stick", rows["p0"][2])
        self.assertIn("0F0D:00EE", rows["p0"][2])
        self.assertEqual(rows["p0"][1], "Player 1")
        self.assertEqual(rows["p1"][2], "no controller")                  # player 2 has none
        self.assertEqual([self.values(k)[0] for k in ("1", "2", "3", "4")], ["B1", "B4", "B2", "B3"])
        self.assertEqual(self.values("1+2")[0], "-")
        self.assertEqual(d.preset_var.get(), "PlayStation pad, default")
        self.assertIn("choose a button", d.intro_var.get())
        self.assertIn("hat up / hat down", d.intro_var.get())
        self.assertFalse(d.editor.dirty)
        self.assertEqual(str(d.btn_save.cget("state")), "disabled")

    def test_the_live_test_lights_the_controller_and_the_game_button(self):
        stick = FakePad()
        d = self.open(stick)
        stick.held = {"B2", "B13"}
        self.run_for(0.2)
        state = d.tv_players.item("p0", "values")
        self.assertEqual(state[0], "●")
        self.assertIn("B2 = 3", state[3])
        self.assertIn("B13", state[3])
        self.assertIn("live", d.tv.item("3", "tags"))
        self.assertNotIn("live", d.tv.item("1", "tags"))
        stick.held = set()
        self.run_for(0.2)
        self.assertEqual(d.tv_players.item("p0", "values")[0], "○")
        self.assertNotIn("live", d.tv.item("3", "tags"))

    def test_press_the_button_for_1_sets_it_and_saves_to_the_file_the_game_reads(self):
        stick = FakePad()
        d = self.open(stick)
        d.begin(["1"])
        self.assertTrue(d.prompt.winfo_manager())
        self.assertEqual(d.prompt_var.get(), "Press the button for 1 (Left Punch)...")
        self.press(stick, "B13")
        self.assertEqual(d.editor.sources(d.dev(), "1"), ["B13"])
        self.assertEqual(self.values("1")[0], "B13")
        self.assertEqual(self.values("1")[1], "yours")
        self.assertEqual(self.values("3")[0], "B2")
        self.assertFalse(d.prompt.winfo_manager())
        self.assertTrue(d.editor.dirty)
        self.assertFalse(os.path.exists(self.ini))                         # nothing written before Save
        self.assertTrue(d.do_save())
        self.assertIn("1 = B13", self.saved())
        self.assertIn("[dinput.0F0D:00EE]", self.saved())
        self.assertIn(self.ini, d.status_var.get())
        # the game's view of the saved file: padmap (the Online tab's PadNav reads the same way)
        c = padmap.Controls.load(self.ini)
        self.assertEqual(c.table(DINPUT, 0, 0x0F0D, 0x00EE).sources_exactly(padmap.target_mask("1")), ["B13"])
        self.assertFalse(d.editor.dirty)

    def test_taking_a_button_from_another_one_says_so(self):
        stick = FakePad()
        d = self.open(stick)
        d.begin(["1"])
        self.press(stick, "B2")                                            # B2 was 3 (Left Kick)
        self.assertIn("B2 was 3 (Left Kick)", d.status_var.get())
        self.assertEqual(self.values("3")[0], "-")

    def test_several_buttons_at_once_are_refused_and_asked_again(self):
        stick = FakePad()
        d = self.open(stick)
        d.begin(["2"])
        self.press(stick, "B13", "B14")
        self.assertIn("several buttons", d.status_var.get())
        self.assertIsNotNone(d.capture)
        self.assertEqual(self.values("2")[0], "B4")
        self.press(stick, "B14")
        self.assertEqual(self.values("2")[0], "B14")

    def test_resting_triggers_do_not_get_in_the_way(self):
        stick = FakePad()
        stick.held = {"RX-", "RY-"}
        d = self.open(stick)
        d.begin(["1+2"])
        self.press(stick, "B6")
        self.assertEqual(d.editor.sources(d.dev(), "1+2"), ["B6"])

    def test_the_guided_run_goes_one_button_at_a_time_with_skip_and_clear(self):
        stick = FakePad()
        d = self.open(stick)
        d.start_all()
        shown = []
        shown.append(d.prompt_var.get())
        self.press(stick, "B9")                                            # 1
        shown.append(d.prompt_var.get())
        d.cap_skip()                                                       # 2: skip, it keeps B4
        shown.append(d.prompt_var.get())
        d.cap_clear()                                                      # 3: clear
        shown.append(d.prompt_var.get())
        self.press(stick, "B12")                                           # 4
        self.assertEqual(shown[0], "Press the button for 1 (Left Punch)...")
        self.assertIn("2 (Right Punch)", shown[1])
        self.assertIn("3 (Left Kick)", shown[2])
        self.assertIn("4 (Right Kick)", shown[3])
        self.assertEqual([self.values(k)[0] for k in ("1", "2", "3", "4")], ["B9", "B4", "-", "B12"])
        self.assertIn("1+2", d.prompt_var.get())
        self.assertIn("5 of 11", d.prompt_hint.get())
        d.cap_stop()
        self.assertIsNone(d.capture)
        self.assertFalse(d.prompt.winfo_manager())
        # the third button stays cleared in the file
        d.do_save()
        self.assertRegex(self.saved(), r"\n3 =\r?\n")

    def test_the_guided_run_ends_after_the_last_button(self):
        stick = FakePad()
        d = self.open(stick)
        d.begin(["START", "SELECT"])
        self.press(stick, "B13")
        self.press(stick, "B14")
        self.assertIsNone(d.capture)
        self.assertEqual(d.editor.sources(d.dev(), "START"), ["B13"])
        self.assertEqual(d.editor.sources(d.dev(), "SELECT"), ["B14"])

    def test_directions_can_be_buttons_of_a_stick_that_sends_them_so(self):
        stick = FakePad()
        d = self.open(stick)
        d.start_directions()
        for src in ("B20", "B21", "B22", "B23"):
            self.press(stick, src)
        self.assertEqual([d.editor.sources(d.dev(), k) for k in ("UP", "DOWN", "LEFT", "RIGHT")],
                         [["B20"], ["B21"], ["B22"], ["B23"]])

    def test_a_row_can_be_set_and_cleared_on_its_own(self):
        stick = FakePad()
        d = self.open(stick)
        d.tv.selection_set("4")
        d.set_selected()
        self.assertEqual(d.cap_key, "4")
        self.press(stick, "B15")
        self.assertEqual(self.values("4")[0], "B15")
        d.tv.selection_set("1")
        d.clear_selected()
        self.assertEqual(self.values("1")[0], "-")

    def test_the_controller_itself_runs_the_screen(self):
        stick = FakePad()
        d = self.open(stick)
        self.assertEqual(d.selected_key(), "1")
        self.press(stick, "HAT_DOWN")                                     # Down
        self.assertEqual(d.selected_key(), "2")
        self.press(stick, "HAT_DOWN")
        self.assertEqual(d.selected_key(), "3")
        self.press(stick, "B2")                                           # Cross: set it
        self.assertEqual(d.cap_key, "3")
        self.assertTrue(d.pad_started)
        self.press(stick, "B13")
        self.assertEqual(self.values("3")[0], "B13")
        self.assertIsNone(d.capture)
        self.press(stick, "HAT_UP")
        self.assertEqual(d.selected_key(), "2")
        self.press(stick, "B4")                                           # Triangle: clear
        self.assertEqual(self.values("2")[0], "-")
        self.assertTrue(d.editor.dirty)
        self.press(stick, "B3")                                           # Circle with unsaved changes: stays
        self.assertTrue(d.alive())
        self.assertIn("unsaved", d.status_var.get())
        self.press(stick, "B10")                                          # Start: save
        self.assertFalse(d.editor.dirty)
        self.assertIn("3 = B13", self.saved())
        self.press(stick, "B3")                                           # Circle: close
        self.assertFalse(d.alive())

    def test_holding_down_moves_on_and_a_capture_started_with_the_pad_gives_up(self):
        stick = FakePad()
        d = self.open(stick)
        stick.held = {"HAT_DOWN"}
        self.run_for(1.0)
        self.assertGreaterEqual([s.key for s in ce.SLOTS].index(d.selected_key()), 4)
        stick.held = set()
        self.run_for(0.3)
        d.set_selected(pad=True)
        self.assertIsNotNone(d.capture)
        self.run_for(cu.PAD_TIMEOUT_S + 1)
        self.assertIsNone(d.capture)                                      # nobody pressed: it skipped
        self.assertIn("skipped", d.status_var.get())
        self.assertFalse(d.editor.dirty)

    def test_the_mouse_ends_a_capture_even_with_no_press(self):
        stick = FakePad()
        d = self.open(stick)
        d.begin(["1"])
        self.run_for(30)                                                   # started by the mouse: no timeout
        self.assertIsNotNone(d.capture)
        d.top.event_generate("<Escape>")
        d._escape()
        self.assertIsNone(d.capture)

    def test_a_press_on_another_controller_selects_it(self):
        stick, ds4 = FakePad(), FakePad(DINPUT, "winmm:1", "Wireless Controller", 0x054C, 0x09CC)
        d = self.open(stick, ds4)
        self.assertEqual(d.chosen, "winmm:0")
        rows = {i: d.tv_players.item(i, "values")[2] for i in d.tv_players.get_children()}
        self.assertIn("Fake Stick", rows["p0"])
        self.assertIn("Wireless Controller", rows["p1"])
        self.press(ds4, "B7")
        self.assertEqual(d.chosen, "winmm:1")
        self.assertEqual(d.dev().port, 1)
        self.assertEqual(d.tv_players.selection(), ("p1",))
        self.assertIn("Wireless Controller", d.head_var.get())
        d.begin(["1"])
        self.press(ds4, "B13")
        self.assertIn("[dinput.054C:09CC]", d.editor.doc.render())
        self.assertEqual(d.editor.sources(DeviceRef(DINPUT, 0, 0x0F0D, 0x00EE), "1"), ["B1"])     # the stick is untouched

    def test_the_mouse_picks_a_controller_too(self):
        stick, ds4 = FakePad(), FakePad(DINPUT, "winmm:1", "Wireless Controller", 0x054C, 0x09CC)
        d = self.open(stick, ds4)
        d.tv_players.selection_set("p1")
        d.top.update_idletasks()
        d._on_player_select()
        self.assertEqual(d.chosen, "winmm:1")

    def test_xinput_pad(self):
        pad = xpad()
        d = self.open(pad)
        self.assertEqual([self.values(k)[0] for k in ("1", "2", "3", "4")], ["X", "Y", "A", "B"])
        self.assertEqual(d.scope_var.get(), ce.SCOPE_KIND)
        d.begin(["1+2"])
        self.press(pad, "RB")
        self.assertEqual(d.editor.sources(d.dev(), "1+2"), ["RB"])
        d.do_save()
        self.assertIn("[xinput]", self.saved())
        self.assertIn("1+2 = RB", self.saved())

    def test_layouts(self):
        stick = FakePad()
        d = self.open(stick)
        titles = list(d.preset_box.cget("values"))
        self.assertIn("Arcade stick, 8 buttons (Vewlix layout)", titles)
        self.assertIn("Hitbox (button-only stick)", titles)
        d.preset_var.set("Arcade stick, 8 buttons (Vewlix layout)")
        d._show_preset_text()
        self.assertIn("1+2", d.preset_text.get())
        d.apply_preset()
        self.assertEqual([self.values(k)[0] for k in ("1+2", "3+4", "1+3", "2+4")], ["B6", "B8", "B5", "B7"])
        self.assertEqual(d.preset_var.get(), "Arcade stick, 8 buttons (Vewlix layout)")
        d.preset_var.set("Hitbox (button-only stick)")
        d.apply_preset()
        self.assertEqual(d.preset_var.get(), "Hitbox (button-only stick)")
        self.assertEqual(d.stick_var.get(), "8-way d-pad presses (hitbox or stick in left-stick mode)")
        d.do_save()
        again = ControlsEditor.load(self.ini)
        self.assertEqual(again.detect_recipe(DI), "hitbox")

    def test_stick_mode_socd_and_player(self):
        stick = FakePad()
        d = self.open(stick)
        d.socd_var.set("The direction pressed last wins")
        d._on_socd()
        d.stick_var.set("8-way d-pad presses (hitbox or stick in left-stick mode)")
        d._on_stick()
        d.do_save()
        text = self.saved()
        self.assertRegex(text, r"\[port1\]\r?\n[^\[]*socd = last")
        self.assertRegex(text, r"stick = dpad")
        d.player_var.set("Player 2")
        d._on_player_opt()
        self.assertEqual(d.editor.pinned(1), "dinput:0F0D:00EE")
        self.run_for(0.2)
        self.assertEqual(d.dev().port, 1)                                  # the game would now give it player 2
        self.assertEqual(d.player_var.get(), "Player 2")
        d.player_var.set("Automatic")
        d._on_player_opt()
        self.run_for(0.2)
        self.assertEqual(d.dev().port, 0)

    def test_reset_to_defaults_asks_and_goes_back(self):
        stick = FakePad()
        d = self.open(stick, ini=sample_text())
        d.preset_var.set("Arcade stick, 8 buttons (Vewlix layout)")
        d.apply_preset()
        d.begin(["1"])
        self.press(stick, "B13")
        d.do_save()
        self.answer = False
        d.reset_defaults()
        self.assertEqual(self.asked[-1][0], "yesno")
        self.assertEqual(self.values("1")[0], "B13")                       # No: nothing happened
        self.answer = True
        d.reset_defaults()
        self.assertEqual([self.values(k)[0] for k in ("1", "2", "3", "4", "1+2")], ["B1", "B4", "B2", "B3", "-"])
        self.assertEqual(d.preset_var.get(), "PlayStation pad, default")
        d.do_save()
        self.assertIn("; ps3recomp controls (Windows)", self.saved())      # the sample's comments are all still there
        self.assertNotIn("B13", self.saved())

    def test_revert_and_close_with_unsaved_changes(self):
        stick = FakePad()
        d = self.open(stick)
        d.begin(["1"])
        self.press(stick, "B13")
        d.do_revert()
        self.assertEqual(self.values("1")[0], "B1")
        self.assertFalse(d.editor.dirty)
        d.begin(["1"])
        self.press(stick, "B13")
        self.answer = None                                                 # Cancel
        self.assertFalse(d.close())
        self.assertTrue(d.alive())
        self.assertEqual(self.asked[-1][0], "yesnocancel")
        self.answer = False                                                # No: leave without saving
        self.assertTrue(d.close())
        self.assertFalse(d.alive())
        self.assertFalse(os.path.exists(self.ini))

    def test_close_can_save(self):
        stick = FakePad()
        d = self.open(stick)
        d.begin(["1"])
        self.press(stick, "B13")
        self.answer = True
        self.assertTrue(d.close())
        self.assertIn("1 = B13", self.saved())

    def test_a_file_changed_by_someone_else_is_asked_about(self):
        stick = FakePad()
        d = self.open(stick, ini="[general]\nsocd = up\n")
        d.begin(["1"])
        self.press(stick, "B13")
        with open(self.ini, "ab") as f:
            f.write(b"; edited meanwhile\n")
        self.answer = False
        self.assertFalse(d.do_save())
        self.assertNotIn("B13", self.saved())
        self.answer = True
        self.assertTrue(d.do_save())
        self.assertIn("1 = B13", self.saved())
        self.assertTrue(os.path.exists(self.ini + ".bak"))

    def test_a_running_game_is_told_it_keeps_the_old_buttons(self):
        stick = FakePad()
        d = self.open(stick, running=True)
        d.begin(["1"])
        self.press(stick, "B13")
        d.do_save()
        self.assertIn("keeps its old buttons", d.status_var.get())

    def test_no_controller(self):
        d = self.open(FakePad())
        d.poller.sources[0].plugged = False
        self.run_for(0.3)
        self.assertIsNone(d.chosen)
        self.assertIn("No controller found", d.pad_note.cget("text"))
        self.assertEqual(str(d.btn_all.cget("state")), "disabled")
        d.begin(["1"])
        self.assertIsNone(d.capture)
        self.assertIn("Press a button on a controller first", d.status_var.get())
        d.poller.sources[0].plugged = True
        self.run_for(0.3)
        self.assertEqual(d.chosen, "winmm:0")
        self.assertEqual(str(d.btn_all.cget("state")), "normal")

    def test_nothing_is_read_while_another_window_is_in_front(self):
        stick = FakePad()
        d = self.open(stick)
        self.front = False
        n = stick.reads
        stick.held = {"B13"}
        d.begin(["1"])
        self.run_for(1.0)
        self.assertEqual(stick.reads, n)
        self.assertIsNotNone(d.capture)                                    # still waiting
        self.assertEqual(self.values("1")[0], "B1")

    def test_scope_choices(self):
        stick = FakePad()
        d = self.open(stick)
        self.assertEqual(d.scope_var.get(), ce.SCOPE_MODEL)
        self.assertEqual(str(d.scope_btns[ce.SCOPE_PORT].cget("state")), "normal")
        d.scope_var.set(ce.SCOPE_KIND)
        d._on_scope()
        d.begin(["1"])
        self.press(stick, "B13")
        self.assertIn("[dinput]", d.editor.doc.render())
        self.assertNotIn("[dinput.0F0D:00EE]", d.editor.doc.render())

    def test_a_scripted_pad_file_keeps_the_real_controllers_out(self):
        # what the launcher does when it builds its readers (T5_PAD_FILE: only the virtual pad, never a real one)
        path = os.path.join(self.out, "pad.txt")
        with open(path, "w") as f:
            f.write("dinput:0F0D:00EE B2")
        old = {k: os.environ.get(k) for k in ("T5_PAD_FILE", "T5_PAD_DEVICES")}
        os.environ["T5_PAD_FILE"] = path
        os.environ.pop("T5_PAD_DEVICES", None)
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None)
                                 for k, v in old.items()])
        sources = padnav.default_sources()
        self.assertEqual([type(s).__name__ for s in sources], ["FileSource"])
        d = cu.ControlsDialog(self.root, FakeSettings(self.out), sources=None, foreground=lambda: True,
                              clock=self.clock, thread=False, ask=lambda *a: True)
        self.dlg = d
        self.addCleanup(self.cleanup_dialog)
        self.assertEqual([type(s).__name__ for s in d.poller.sources], ["FileSource"])
        self.run_for(0.2)
        self.assertEqual(d.chosen, "file")
        self.assertIn("scripted pad", d.head_var.get())

    def test_it_fits_the_window(self):
        d = self.open(FakePad())
        d.top.update_idletasks()
        self.assertLessEqual(d.top.winfo_reqwidth(), 980)
        self.assertLessEqual(d.top.winfo_reqheight(), 720)

    def test_a_file_with_the_players_own_lines_is_edited_where_they_are(self):
        stick = FakePad()
        d = self.open(stick, ini=HAND_MADE)
        self.assertEqual(d.scope_var.get(), ce.SCOPE_PORT)                 # [port1.dinput] already has a line
        d.begin(["START"])
        self.press(stick, "B14")
        text = d.editor.doc.render()
        self.assertIn("unknown_key = 12", text)
        self.assertIn("foo = bar              ; a key nobody knows", text)
        self.assertIn("START = B14", text)




if __name__ == "__main__":
    unittest.main()
