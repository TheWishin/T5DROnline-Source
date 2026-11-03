"""Offline layout-client integration: real walk/event/list code, no Tk rendering.

The subprocess supplies inert Tk import names and recording widget boundaries.
It stops at the first lobby screen, before the walk's later assets/dialogs.
Actual launcher construction, geometry and Tk lifetime still need Tk tests.
"""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import sys
import types
from pathlib import Path
from unittest import mock

root = Path(sys.argv[1])
sys.path[:0] = [str(root / "tests"), str(root / "lobby")]

class NoWidget:
    def __init__(self, *args, **kwargs):
        raise AssertionError("this offline contract test must not construct Tk widgets")

# Import complete source modules; these names supply no Tcl interpreter or UI.
tk = types.ModuleType("tkinter")
tk.__path__ = []
tk.Canvas = NoWidget
tk.TclError = type("TclError", (Exception,), {})
for name in ("font", "ttk", "filedialog"):
    module = types.ModuleType("tkinter." + name)
    setattr(tk, name, module)
    sys.modules[module.__name__] = module
sys.modules["tkinter"] = tk

with mock.patch("socket.socket", side_effect=AssertionError("no networking")):
    import i18n_layout as layout
    from t5lobby import fighters, tk_tab, tk_challenges

    rows = {}
    players_widget, rooms_widget = object(), mock.Mock()
    rooms_widget.selection.return_value = ()

    def record(widget, values):
        rows[widget] = list(values)

    tab = tk_tab.OnlineTab.__new__(tk_tab.OnlineTab)
    tab.client = None
    tab.table = fighters.table()
    tab.tv_players, tab.tv_rooms = players_widget, rooms_widget
    tab.spec = mock.Mock()
    tab.spec.on_event.return_value = False
    tab.private_chat = mock.Mock()
    tab.rooms_ui = mock.Mock()
    tab.rooms_ui.list_state.return_value = []
    tab.view = mock.Mock()
    tab.view.plates_on.return_value = False
    tab.view.player_image.return_value = None
    tab.view.room_image.return_value = None
    tab.chal = tk_challenges.ChallengesUI.__new__(tk_challenges.ChallengesUI)
    tab.chal.sort = ("name", False)
    tab.chal.on_event = mock.Mock()
    tab.chal.challenged_ids = lambda: set()
    for name in ("_set_account_view", "_offer_ingame_ui", "_notify_event", "_show_me", "_set_actions"):
        setattr(tab, name, mock.Mock())
    tab._player_badge = lambda player: None
    tab._you_suffix = lambda: " (you)"
    tab._is_muted = lambda name: False

    walk = layout.Walk("en", 100)
    walk.app = types.SimpleNamespace(nb=mock.Mock(), tabs={"online": "online"}, online=tab)
    screens = []
    class LobbyReached(Exception):
        pass
    def screen(name):
        screens.append(name)
        if name == "online lobby":
            raise LobbyReached
    walk.screen = screen
    with mock.patch.object(tk_tab.tklist, "sync", side_effect=record):
        try:
            walk._online()
        except LobbyReached:
            pass
        else:
            raise AssertionError("walk did not reach the first lobby screen")

        if sys.argv[2] == "german":
            # Import the complete German test fixture too. Its rendering tests
            # cannot run with these inert Tk names; the actual event handler can.
            import test_i18n
            tab.client = test_i18n.FakeClient()
            tab.client.players = layout.PLAYERS
            tab.on_event({"t": "lobby_state", "players": layout.PLAYERS,
                          "rooms": layout.ROOMS, "queue": {"ranked": 3, "quick": 1}})

    assert screens == ["online login", "online lobby"], screens
    player_rows = {row[0]: row for row in rows[players_widget]}
    for player in layout.PLAYERS:
        row = player_rows[player["id"]]
        same = player["build"] == tab.client.build.build_id
        assert ("other" in row[3]) == (not same), row
        assert (row[1][5] == "other version") == (not same), row
    room_rows = {row[0]: row for row in rows[rooms_widget]}
    for room in layout.ROOMS:
        row = room_rows[room["id"]]
        same = room["build"] == tab.client.build.build_id
        assert ("(other version)" in row[1][2]) == (not same), row
        if not same:
            assert "closed" in row[3], row
    assert any(p["build"] == "b1" for p in layout.PLAYERS)
    assert any(p["build"] != "b1" for p in layout.PLAYERS)
    assert any(r["build"] == "b1" for r in layout.ROOMS)
    assert any(r["build"] != "b1" for r in layout.ROOMS)
print("actual Walk._online -> OnlineTab.on_event -> _fill_lists passed")
if sys.argv[2] == "german":
    print("actual German FakeClient -> OnlineTab.on_event -> _fill_lists passed")
'''


class LayoutClientContract(unittest.TestCase):
    def test_walk_dispatches_lobby_players_and_rooms(self):
        self.run_probe("layout", "actual Walk._online -> OnlineTab.on_event -> _fill_lists passed")

    def test_german_fixture_dispatches_lobby_players_and_rooms(self):
        self.run_probe("german", "actual German FakeClient -> OnlineTab.on_event -> _fill_lists passed")

    def run_probe(self, fixture, message):
        result = subprocess.run(
            [sys.executable, "-B", "-c", PROBE, str(ROOT), fixture],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(message, result.stdout)


if __name__ == "__main__":
    unittest.main()
