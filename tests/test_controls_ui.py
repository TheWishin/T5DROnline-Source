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
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
