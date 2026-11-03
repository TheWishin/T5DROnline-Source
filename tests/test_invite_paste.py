"""Launcher editing shortcuts, without a server, mainloop or system clipboard.

All key input here is SYNTHETIC, not a real keyboard-layout test. Feed independent key
substitutions through the real Tk bind scripts: event_generate cannot
produce a Cyrillic keysym on Windows without installing / switching the keyboard layout.
Substitution tests exercise the generic Control-KeyPress fallback, not Tk's physical-event
matching. The generated-Latin test also uses Tk's event matcher, with synthetic events.
The resulting virtual events run Tk's real TEntry / Text editing bindings.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "lobby"))

try:
    import tkinter as tk
    from tkinter import ttk
    from t5lobby import theme
    from t5lobby.tk_rooms import RoomsUI
except ImportError:      # pragma: no cover
    tk = None

CODE = "ABCD-EFGH-JKLM"


@unittest.skipIf(tk is None, "no tkinter")
class InvitePasteTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        if self.root.tk.call("tk", "windowingsystem") != "win32":
            self.skipTest("Windows virtual keycodes")
        # Tk accesses the clipboard in Tcl. Replace reads AND writes so copy/cut
        # tests cannot touch this PC's clipboard either.
        self.root.tk.eval("""
            set test_clipboard ABCD-EFGH-JKLM
            rename ::tk::GetSelection ::tk::SavedGetSelection
            proc ::tk::GetSelection {w selection} {return $::test_clipboard}
            rename ::clipboard ::SavedClipboard
            proc ::clipboard {operation args} {
                switch -- $operation {
                    clear {set ::test_clipboard ""}
                    append {append ::test_clipboard [lindex $args end]}
                    default {error "unexpected clipboard operation: $operation"}
                }
            }
        """)
        # Also cover widgets created before theme.apply. Skip only the expensive
        # theme drawing/fonts/disk cache; use the production apply/binding code.
        self.existing_entry = ttk.Entry(self.root)
        self.existing_text = tk.Text(self.root)
        with mock.patch.object(theme, "Theme", return_value=SimpleNamespace(root=self.root)):
            theme.apply(self.root)

    def dialog(self, parent, title):
        # Keep all windows withdrawn and avoid theme drawing / disk caches.
        win = tk.Toplevel(parent)
        win.withdraw()
        body = ttk.Frame(win)
        body.pack()
        return SimpleNamespace(px=lambda x: x), win, body

    def synthetic_control_key(self, entry, keysym, keycode, state=4):
        # Tk substitutes %K (keysym), %k (keycode), etc. before executing each
        # binding. Supply these independently, as a real non-Latin key event can.
        values = dict(zip(entry._subst_format, (
            "0", "0", "0", "0", str(keycode), str(state), "0", "0", "0", "0",
            "{}", "0", keysym, "0", str(entry), "2", "0", "0", "0")))
        for tag in entry.bindtags():
            script = entry.bind_class(tag, "<Control-KeyPress>")
            for field, value in values.items():
                script = script.replace(field, value)
            # catch preserves Tk's 'break' propagation without an outer event loop.
            result = int(entry.tk.call("catch", script, "key_result"))
            self.assertIn(result, (0, 3), entry.tk.getvar("key_result"))
            if result == 3:
                return "break"

    def prompt(self, exercise, selected=False, **kwargs):
        def modal(win, parent, entry):
            try:
                self.assertEqual(str(entry.cget("state")), "normal")
                self.assertEqual(str(entry.cget("validate")), "none")
                exercise(entry)
                # Press the actual OK button without waiting for a user / mainloop.
                body = win.winfo_children()[0]
                row = body.winfo_children()[-1]
                row.winfo_children()[-1].invoke()
            finally:
                if win.winfo_exists():
                    win.destroy()

        with mock.patch.object(theme, "_dialog", self.dialog), mock.patch.object(theme, "_modal", modal):
            if kwargs:
                return theme.ask_string("Test", "Prompt", parent=self.root, **kwargs)
            client = SimpleNamespace(connected=True, private_rooms_ok=lambda: True,
                                     rooms=[{"id": "room", "private": True, "lock": "code"}],
                                     join_room=mock.Mock())
            tab = SimpleNamespace(parent=self.root, client=client, ask_string=theme.ask_string,
                                  tv_rooms=SimpleNamespace(selection=lambda: ("room",) if selected else ()),
                                  call=mock.Mock())
            RoomsUI(tab).join_selected()
            tab.call.assert_called_once_with(client.join_room, "room" if selected else None, None, CODE)

    def test_synthetic_non_latin_ctrl_v_joins_by_invite_code(self):
        def paste(entry):
            entry.insert(0, "replace me")
            entry.select_range(0, "end")
            self.assertEqual(entry.bind("<Control-KeyPress>"), "")
            consumed = self.synthetic_control_key(entry, "Cyrillic_em", 0x56)
            self.assertEqual(entry.get(), CODE)
            self.assertEqual(consumed, "break")
        for selected in (False, True):
            with self.subTest(selected=selected):
                self.prompt(paste, selected=selected)

    def test_synthetic_english_ctrl_v_pastes_once(self):
        def paste(entry):
            self.assertEqual(self.synthetic_control_key(entry, "v", 0x56), "break")
            self.assertEqual(entry.get(), CODE)
        self.prompt(paste)

    def test_synthetic_other_control_keys_and_altgr_are_left_to_tk(self):
        def keys(entry):
            for keysym, keycode, state in (("q", 0x51, 4), ("Cyrillic_em", 0x56, 0x20004)):
                self.assertIsNone(self.synthetic_control_key(entry, keysym, keycode, state))
                self.assertEqual(entry.get(), "")
            entry.event_generate("<<Paste>>")
        self.prompt(keys)

    def test_synthetic_shared_password_prompt_keeps_mask_and_selection(self):
        def paste(entry):
            self.assertEqual(entry.cget("show"), "*")
            self.assertTrue(entry.selection_present())
            self.synthetic_control_key(entry, "Cyrillic_em", 0x56)
        self.assertEqual(self.prompt(paste, show="*", initialvalue="old"), CODE)

    def content(self, widget):
        return widget.get("1.0", "end-1c") if isinstance(widget, tk.Text) else widget.get()

    def insert(self, widget, value):
        widget.insert("1.0" if isinstance(widget, tk.Text) else 0, value)

    def select_all(self, widget):
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
        else:
            widget.selection_range(0, "end")

    def test_synthetic_paste_in_existing_and_future_widgets_and_toplevels(self):
        win = tk.Toplevel(self.root)
        win.withdraw()
        card = ttk.Frame(win)
        # Shared TEntry class covers chat, friends, room/server/account fields and
        # paths, independent of style, parent, masking or creation time. Text is
        # used by the problem description and the environment settings field.
        widgets = (self.existing_entry, self.existing_text, ttk.Entry(self.root),
                   ttk.Entry(card, style="Card.TEntry"), ttk.Entry(card, show="*"), tk.Text(card))
        for widget in widgets:
            for keysym, state in (("Cyrillic_em", 4), ("v", 4), ("V", 5), ("V", 6)):
                with self.subTest(widget=widget.winfo_class(), keysym=keysym, state=state):
                    self.root.tk.setvar("test_clipboard", CODE)
                    self.insert(widget, "replace me")
                    self.select_all(widget)
                    events = []
                    binding = widget.bind("<<Paste>>", lambda e: events.append(e.type))
                    try:
                        self.assertEqual(self.synthetic_control_key(widget, keysym, 0x56, state), "break")
                        self.assertEqual(self.content(widget), CODE)
                        self.assertEqual(len(events), 1)
                    finally:
                        widget.unbind("<<Paste>>", binding)

    def test_synthetic_copy_cut_select_all_have_the_same_layout_fix(self):
        for cls in (ttk.Entry, tk.Text):
            for keysym in ("Cyrillic_es", "c"):
                with self.subTest(widget=cls.__name__, keysym=keysym):
                    widget = cls(self.root)
                    self.insert(widget, "keep SELECT tail")
                    if isinstance(widget, tk.Text):
                        widget.tag_add("sel", "1.5", "1.11")
                    else:
                        widget.selection_range(5, 11)
                    self.assertEqual(self.synthetic_control_key(widget, keysym, 0x43), "break")
                    self.assertEqual(self.root.tk.getvar("test_clipboard"), "SELECT")
                    self.assertEqual(self.content(widget), "keep SELECT tail")
                    self.assertEqual(self.synthetic_control_key(widget, "Cyrillic_che", 0x58), "break")
                    self.assertEqual(self.root.tk.getvar("test_clipboard"), "SELECT")
                    self.assertEqual(self.content(widget), "keep  tail")
                    self.assertEqual(self.synthetic_control_key(widget, "Cyrillic_ef", 0x41), "break")
                    if isinstance(widget, tk.Text):
                        selected = widget.get("sel.first", "sel.last").rstrip("\n")
                    else:
                        selected = widget.get()[widget.index("sel.first"):widget.index("sel.last")]
                    self.assertEqual(selected, "keep  tail")
                    widget.destroy()

    def test_generated_latin_shortcuts_and_alternate_paste_run_once(self):
        # Unlike the substitution tests, exercise Tk's actual binding selection:
        # its specific Latin virtual mappings can win over our generic fallback.
        # Key events require a mapped, focused widget. Keep this test window
        # transparent, offscreen and without decorations; no real keys are sent.
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0.0)
        self.root.geometry("1x1+30000+30000")
        self.root.deiconify()
        for cls in (ttk.Entry, tk.Text):
            with self.subTest(widget=cls.__name__):
                widget = cls(self.root)
                widget.pack()
                self.root.update()
                widget.focus_force()
                self.root.update()
                self.assertEqual(self.root.focus_get(), widget)
                self.root.tk.setvar("test_clipboard", CODE)
                events = []
                for virtual in ("<<Paste>>", "<<Copy>>", "<<Cut>>", "<<SelectAll>>"):
                    widget.bind(virtual, lambda e, v=virtual: events.append(v))
                self.insert(widget, "replace me")
                self.select_all(widget)
                widget.event_generate("<Control-KeyPress-v>")
                self.assertEqual(self.content(widget), CODE)
                widget.event_generate("<Control-KeyPress-a>")
                widget.event_generate("<Control-KeyPress-c>")
                copied = CODE + "\n" if isinstance(widget, tk.Text) else CODE
                self.assertEqual(self.root.tk.getvar("test_clipboard"), copied)
                widget.event_generate("<Control-KeyPress-x>")
                self.assertEqual(self.content(widget), "")
                self.assertEqual(events, ["<<Paste>>", "<<SelectAll>>", "<<Copy>>", "<<Cut>>"])
                self.root.tk.setvar("test_clipboard", CODE)
                for sequence in ("<Shift-KeyPress-Insert>", "<<Paste>>"):
                    widget.event_generate(sequence)
                self.assertEqual(self.content(widget), CODE * 2)
                self.assertEqual(events[-2:], ["<<Paste>>", "<<Paste>>"])
                widget.destroy()

    def test_synthetic_altgr_ctrl_alt_and_unrelated_keys_are_untouched(self):
        for widget in (ttk.Entry(self.root), tk.Text(self.root)):
            self.insert(widget, "unchanged")
            self.select_all(widget)
            events = []
            for virtual in ("<<Paste>>", "<<Copy>>", "<<Cut>>", "<<SelectAll>>"):
                widget.bind(virtual, lambda e: events.append(e.type))
            for keycode in (0x56, 0x43, 0x58, 0x41):
                # Ctrl+Alt and Ctrl+Alt+Shift (also AltGr's Windows state).
                for state in (0x20004, 0x20005):
                    self.assertIsNone(self.synthetic_control_key(widget, "Cyrillic_em", keycode, state))
            self.assertIsNone(self.synthetic_control_key(widget, "q", 0x51))
            # A Latin keysym alone must not trigger the virtual-key fallback.
            self.assertIsNone(self.synthetic_control_key(widget, "v", 0x51))
            self.assertEqual(self.content(widget), "unchanged")
            self.assertEqual(events, [])
            self.assertEqual(self.root.tk.getvar("test_clipboard"), CODE)

    def test_synthetic_paste_and_cut_preserve_readonly_and_disabled_fields(self):
        for widget, state in ((ttk.Entry(self.root), "readonly"),
                              (ttk.Entry(self.root), "disabled"), (tk.Text(self.root), "disabled")):
            with self.subTest(widget=widget.winfo_class(), state=state):
                self.insert(widget, "protected")
                self.select_all(widget)
                widget.configure(state=state)
                for keycode in (0x56, 0x58):
                    self.assertEqual(self.synthetic_control_key(widget, "Cyrillic_em", keycode), "break")
                    self.assertEqual(self.content(widget), "protected")

    def test_theme_apply_installs_class_bindings_only_once(self):
        scripts = {cls: self.root.bind_class(cls, "<Control-KeyPress>") for cls in ("TEntry", "Text")}
        win = tk.Toplevel(self.root)
        win.withdraw()
        with mock.patch.object(theme, "Theme") as constructor:
            for parent in (self.root, win, ttk.Frame(win)):
                theme.apply(parent)
            constructor.assert_not_called()
        for cls, script in scripts.items():
            self.assertEqual(self.root.bind_class(cls, "<Control-KeyPress>"), script)
        entry = ttk.Entry(win)
        self.assertEqual(self.synthetic_control_key(entry, "Cyrillic_em", 0x56), "break")
        self.assertEqual(entry.get(), CODE)

    def test_non_windows_keeps_tk_class_bindings(self):
        root = mock.Mock()
        root.tk.call.return_value = "x11"
        theme._bind_edit_shortcuts(root)
        root.bind_class.assert_not_called()


if __name__ == "__main__":
    unittest.main()
