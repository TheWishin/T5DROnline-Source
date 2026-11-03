"""Guest mute preferences retain the login server while its UI selection changes."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def controller():
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in {"_new_client", "_mutes_changed"}]
    client = SimpleNamespace(me={"guest": True}, mute_rows=[{"name": "Rival"}])
    factory = Mock(return_value=client)
    namespace = {"LobbyClient": factory, "servers": SimpleNamespace(resolve=Mock(return_value=None)),
                 "DEFAULT_SERVER": "default"}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.cfg = {"guest_mutes": {"server-a": ["Rival"], "server-b": ["Other"]}, "last_fps": 60}
    tab.fp_var = SimpleNamespace(get=lambda: "")
    tab._server_key = lambda: "server-b"
    tab.server_list = []
    tab.app = SimpleNamespace(settings={})
    tab.spec, tab.casual = Mock(), Mock()
    tab.spec.client_kw.return_value = {}
    for name in ("_game_can_pick", "_game_has_rules", "_game_has_life150", "_game_has_ingame_ui",
                 "_game_has_auto_skip", "_game_has_auto_skip_intro"):
        setattr(tab, name, lambda: False)
    tab._save_cfg = Mock()
    tab.chat_log = Mock()
    tab.chat_log.tag_names.return_value = []
    tab.relist, tab.rooms_ui, tab.private_chat, tab.view = Mock(), Mock(), Mock(), Mock()
    return tab, factory


class GuestMuteServerOwnershipTest(unittest.TestCase):
    def test_loading_uses_requested_server_instead_of_changed_selection(self):
        tab, factory = controller()
        tab._new_client("Server-A", None)
        self.assertEqual(factory.call_args.kwargs["guest_mutes"], ["Rival"])

    def test_saving_after_selection_changes_does_not_overwrite_another_server(self):
        tab, _factory = controller()
        tab._server_key = lambda: "server-a"
        tab.client = tab._new_client("Server-A", None)
        tab._server_key = lambda: "server-b"
        tab.client.mute_rows = [{"name": "New Rival"}]
        tab._mutes_changed()
        self.assertEqual(tab.cfg["guest_mutes"], {"server-a": ["New Rival"], "server-b": ["Other"]})
        tab._save_cfg.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
