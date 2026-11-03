"""Room settings retain their opening room, with fake widgets only."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import util  # noqa: F401 -- local package path only; no server helper is invoked
from t5lobby import tk_rooms, tk_tab


class Variable:
    def __init__(self, _master, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *_args):
        pass


class RoomSettingsOwnershipTest(unittest.TestCase):
    def window(self):
        room = {"id": "original", "players": [], "lock": None}
        client = SimpleNamespace(my_room=room, me={"id": "host", "status": "room"})
        tab = SimpleNamespace(client=client, view=SimpleNamespace(px=lambda value: value, body=Mock()),
                              status=Mock())
        ui = SimpleNamespace(tab=tab, close_window=Mock(), kick=Mock(), bar_guessers=Mock())
        window = Mock()

        def button(*_args, **kwargs):
            widget = Mock()
            widget.command = kwargs.get("command")
            return widget

        def combobox(*_args, **kwargs):
            options = {"font": "TkDefaultFont", **kwargs}
            widget = Mock()
            widget.cget.side_effect = options.__getitem__
            widget.configure.side_effect = lambda **changes: options.update(changes)
            return widget

        with patch.object(tk_rooms, "_window", return_value=(window, Mock())), \
                patch.object(tk_rooms, "_room_rules_supported", return_value=False), \
                patch.object(tk_rooms.tk, "StringVar", Variable), \
                patch.object(tk_rooms.tk, "IntVar", Variable), \
                patch.object(tk_rooms.tk, "Listbox"), \
                patch.object(tk_rooms.ttk, "Label"), patch.object(tk_rooms.ttk, "Entry"), \
                patch.object(tk_rooms.ttk, "Combobox", side_effect=combobox), \
                patch.object(tk_rooms.tkfont, "Font", return_value=SimpleNamespace(measure=lambda text: 8 * len(text))), \
                patch.object(tk_rooms.ttk, "Checkbutton"), \
                patch.object(tk_rooms.ttk, "Button", side_effect=button):
            tk_rooms.settings_window(ui, room)
        return tab, window

    def test_stale_room_cannot_send_saved_settings_or_rotate_another_rooms_code(self):
        for replacement in (None, {"id": "different"}):
            with self.subTest(room=replacement):
                tab, window = self.window()
                tab.client.my_room = replacement
                with patch.object(tk_rooms, "_save_settings") as save:
                    window.save_button.command()
                    window.code_button.command()
                save.assert_not_called()

    def test_replacement_session_with_same_room_id_cannot_use_old_controls(self):
        tab, window = self.window()
        tab.client = SimpleNamespace(my_room={"id": "original"}, me={"id": "host"})
        with patch.object(tk_rooms, "_save_settings") as save:
            window.save_button.command()
        save.assert_not_called()

    def test_current_room_still_saves_and_rotates_its_code(self):
        tab, window = self.window()
        with patch.object(tk_rooms, "_save_settings") as save:
            window.save_button.command()
            self.assertEqual(save.call_args.args[1:5], (None, None, False, {}))
            window.code_button.command()
            self.assertEqual(save.call_args.args[1:5], ("code", None, False, {}))
        self.assertEqual(save.call_count, 2)
        self.assertIs(save.call_args.args[0], tab)


class ServerNoticeTranslationTest(unittest.TestCase):
    def test_known_notice_is_translated_and_unknown_admin_text_kept(self):
        tab = tk_tab.OnlineTab.__new__(tk_tab.OnlineTab)
        tab.client = SimpleNamespace(active_notices=lambda: ["known release notice", "custom admin text"])
        tab.notice_var = Variable(None, value="")
        tab.app = SimpleNamespace()
        translated = {"known release notice": "translated release notice"}
        with patch.object(tk_tab, "translate_message", side_effect=lambda text: translated.get(text, text)) as tr:
            tab._show_notice()
        self.assertEqual(tab.notice_var.get(), "translated release notice  |  custom admin text")
        self.assertEqual([call.args for call in tr.call_args_list],
                         [("known release notice",), ("custom admin text",)])


if __name__ == "__main__":
    unittest.main()
