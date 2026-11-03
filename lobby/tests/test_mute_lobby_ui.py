"""Lobby mute controls exercised without Tk, sockets, game data or a server.

The real controller methods are compiled from their AST so these tests also work
on headless Python installations without tkinter.
"""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import time
from unittest.mock import Mock


SOURCE = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
SPEC = importlib.util.spec_from_file_location("mute_ui_proto", SOURCE.with_name("proto.py"))
PROTO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROTO)


def controller():
    source = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    wanted = {"chat_line", "_mute_content_tag", "_is_muted", "toggle_mute", "on_player_mute_click",
              "_mutes_changed", "do_muted", "_muted_window", "_chat_moderation_notice"}
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    errors = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "lobby_error_text")
    namespace = {"t": lambda text, **kw: text.format(**kw), "time": time, "translate_message": lambda msg: msg, "LobbyError": PROTO.LobbyError, "proto": PROTO,
                 "tk": SimpleNamespace(TclError=RuntimeError, Listbox=Mock()),
                 "ttk": SimpleNamespace(Label=Mock(), Button=Mock())}
    exec(compile(ast.Module(body=[cls, errors], type_ignores=[]), str(SOURCE), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.client = SimpleNamespace(me={"id": "me", "name": "Tester", "guest": False},
                                 players=[{"id": "rival-id", "name": "Rival"}],
                                 is_muted=Mock(return_value=False), mute=Mock(), unmute=Mock(), mutes=Mock())
    tab.chat_log = Mock()
    tab.chat_log.tag_names.return_value = []
    tab.view = SimpleNamespace(chat_name_tag=Mock(return_value="chat_name_rival"),
                               _update_profile_mute=Mock(), px=lambda n: n, card=Mock(return_value=Mock()))
    tab.call = Mock()
    tab.status = Mock()
    tab.relist = Mock()
    tab.rooms_ui = SimpleNamespace(refresh=Mock())
    tab.private_chat = SimpleNamespace(refresh=Mock())
    tab._save_cfg = Mock()
    tab._server_key = lambda: "server-a"
    tab.cfg = {"guest_mutes": {"server-b": ["Other"]}}
    tab.parent = Mock()
    tab.new_window = Mock(return_value=Mock())
    return tab, namespace


class LobbyMuteControls(unittest.TestCase):
    def test_chat_header_mutes_raw_sender_with_one_click_and_self_has_no_action(self):
        tab, _ = controller()
        tab.chat_line("hello", sender="Rival", badge="dev", mentioned=True)
        bind = tab.chat_log.tag_bind.call_args
        self.assertEqual(bind.args[1], "<Button-1>")
        with unittest.mock.patch.object(tab, "toggle_mute") as toggle:
            bind.args[2](Mock())
            toggle.assert_called_once_with("Rival")
        tag = tab._mute_content_tag("Rival")
        for call in tab.chat_log.insert.call_args_list:
            self.assertIn(tag, call.args[2])
        tab.chat_log.reset_mock()
        tab.chat_line("own", sender="Tester")
        tab.chat_log.tag_bind.assert_not_called()

    def test_muted_chat_never_reaches_text_widget(self):
        tab, _ = controller()
        tab.client.is_muted.return_value = True
        tab.chat_line("hidden", sender="Rival", mentioned=True)
        tab.chat_log.insert.assert_not_called()
        tab.chat_line("system notice")
        tab.chat_log.insert.assert_called_once_with("end", "system notice\n", ("chat_sys",))

    def test_mute_cell_resolves_identity_and_leaves_other_cells_alone(self):
        tab, _ = controller()
        class PlayerTable:
            def __getitem__(self, key):
                return ("name", "ping", "mute")
            identify_region = Mock(return_value="cell")
            identify_column = Mock(return_value="#3")
            identify_row = Mock(return_value="rival-id")
        tab.tv_players = PlayerTable()
        event = SimpleNamespace(x=100, y=5)
        with unittest.mock.patch.object(tab, "toggle_mute") as toggle:
            self.assertEqual(tab.on_player_mute_click(event), "break")
            toggle.assert_called_once_with("Rival")
            toggle.reset_mock()
            tab.tv_players.identify_column.return_value = "#1"
            self.assertIsNone(tab.on_player_mute_click(event))
            toggle.assert_not_called()

    def test_toggle_waits_for_success_and_refreshes_every_surface(self):
        tab, _ = controller()
        tab.toggle_mute("Rival")
        tab.call.assert_called_once()
        self.assertEqual(tab.call.call_args.args, (tab.client.mute, "Rival", True))
        tab.status.assert_not_called()
        tab.call.call_args.kwargs["then"]({"mutes": []})
        tab.relist.assert_called_once_with()
        tab.rooms_ui.refresh.assert_called_once_with()
        tab.private_chat.refresh.assert_called_once_with()
        tab.view._update_profile_mute.assert_called_once_with()
        tab.status.assert_called_once_with("Muted Rival.")
        tab.call.reset_mock()
        tab.toggle_mute("tester")
        tab.call.assert_not_called()

    def test_existing_chat_is_hidden_and_restored_and_guest_names_are_saved_per_server(self):
        tab, _ = controller()
        tag = tab._mute_content_tag("Rival")
        tab.chat_log.tag_names.return_value = [tag, "chat_msg", "mute_content_invalid"]
        tab.client.me["guest"] = True
        tab.client.mute_rows = [{"name": "Rival"}]
        tab.client.is_muted.return_value = True
        tab._mutes_changed()
        tab.chat_log.tag_configure.assert_called_once_with(tag, elide=True)
        self.assertEqual(tab.cfg["guest_mutes"], {"server-b": ["Other"], "server-a": ["Rival"]})
        tab._save_cfg.assert_called_once_with()
        tab.client.is_muted.return_value = False
        tab._mutes_changed()
        self.assertEqual(tab.chat_log.tag_configure.call_args.kwargs, {"elide": False})

    def test_account_mutes_are_not_copied_into_guest_preferences(self):
        tab, _ = controller()
        tab._mutes_changed()
        tab._save_cfg.assert_not_called()
        self.assertEqual(tab.cfg["guest_mutes"], {"server-b": ["Other"]})

    def test_timed_admin_mute_renders_deadline_and_permanent_mute_remains_plain(self):
        _, namespace = controller()
        error = PROTO.LobbyError("not_allowed", "Chat is muted for this account.", muted_until=1700000000)
        self.assertEqual(namespace["lobby_error_text"](error), "Lobby: Chat is muted until 2023-11-14 22:13 UTC.")
        for until in (32503680000, float("inf"), float("nan"), True, None):
            error.extra["muted_until"] = until
            self.assertEqual(namespace["lobby_error_text"](error), "Lobby: Chat is muted for this account.")

    def test_login_notice_shows_active_admin_mute_without_sending_chat(self):
        tab, _ = controller()
        tab._chat_moderation_notice(32503680000)
        tab.status.assert_called_once_with("Lobby: Chat is muted for this account.")
        tab.call.assert_not_called()
        tab.status.reset_mock()
        for until in (None, True, float("inf"), float("nan"), time.time() - 1):
            tab._chat_moderation_notice(until)
        tab.status.assert_not_called()

    def test_muted_manager_unmutes_only_selected_name_after_success(self):
        tab, namespace = controller()
        tab._muted_window({"t": "mutes", "rows": [{"name": "Rival"}, {"name": "Other"}]})
        lb = namespace["tk"].Listbox.return_value
        lb.curselection.return_value = [1]
        button = namespace["ttk"].Button.call_args_list[0]
        self.assertEqual(button.kwargs["text"], "Unmute")
        button.kwargs["command"]()
        self.assertEqual(tab.call.call_args.args, (tab.client.unmute, "Other"))
        lb.delete.assert_not_called()
        tab.call.call_args.kwargs["then"]({})
        lb.delete.assert_called_once_with(1)
        tab.status.assert_called_once_with("Unmuted Other.")


if __name__ == "__main__":
    unittest.main()