"""Room tables launcher regressions with fake calls and widgets; no sockets, server or game."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import util  # noqa: F401 -- repository import path; no ServerThread is started
from t5lobby import i18n, proto, tk_rooms
from t5lobby.client import LobbyClient
from t5lobby.tk_rooms import RoomsUI
from t5lobby.tk_spectate import Spectating


class Var:
    def __init__(self, _parent=None, value=""):
        self.value = value
        self.trace = None

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        if self.trace:
            self.trace()

    def trace_add(self, _kind, callback):
        self.trace = callback


class Widget:
    def __init__(self, *_a, **kw):
        self.options = {"font": "TkTextFont", **kw}

    def grid(self, **_kw):
        pass

    def pack(self, **_kw):
        pass

    def configure(self, **kw):
        self.options.update(kw)

    def cget(self, key):
        return self.options[key]

    def invoke(self):
        if self.options.get("state") != "disabled":
            self.options["command"]()


class RoomTablesClientTest(unittest.TestCase):
    def client(self, **kw):
        c = LobbyClient("127.0.0.1:1", util.BUILD, sets=True, **kw)
        c.welcome = {"features": ["room_tables", "private_rooms", "casual_sets"],
                     "caps": ["room_tables", "private_rooms", "casual_sets", "sets"]}
        c._call = mock.Mock(return_value={"room": {"id": "r1"}})
        return c

    def test_create_tables_preserves_first_to_and_host_pair_selector(self):
        c = self.client()
        c.create_room(size=8, mode="tables", first_to=5)
        msg = c._call.call_args.args[0]
        self.assertEqual((msg["mode"], msg["size"], msg["first_to"]), ("tables", 8, 5))
        c.room_pair(2, ["p3", "p4"])
        self.assertEqual(c._call.call_args.args[0], {"t": "room_pair", "table": 2, "players": ["p3", "p4"]})

    def test_old_server_and_disabled_cap_refuse_tables_without_a_call(self):
        for c in (self.client(room_tables=False), self.client(private_rooms=False), self.client()):
            if c.room_tables:
                c.welcome["caps"].remove("room_tables")
            self.assertFalse(c.room_tables_ok())
            with self.assertRaisesRegex(proto.LobbyError, "no simultaneous room tables"):
                c.create_room(mode="tables")
            with self.assertRaises(proto.LobbyError):
                c.room_pair(1, ["p1", "p2"])
            c._call.assert_not_called()

    def test_line_room_keeps_original_message_and_watch_selector_is_optional(self):
        c = self.client()
        c.create_room()
        self.assertNotIn("mode", c._call.call_args.args[0])
        async def request(msg):
            return msg

        c._request = mock.Mock(side_effect=request)
        c._run = lambda coro, timeout: asyncio.run(coro)
        self.assertEqual(c.watch(room="r1", table=2), {"t": "watch", "room": "r1", "table": 2})
        self.assertEqual(c.watch(room="r1"), {"t": "watch", "room": "r1"})


class RoomTablesPresentationTest(unittest.TestCase):
    def setUp(self):
        self.old_language = i18n.language()
        i18n.set_language("en")
        self.room = {"id": "r1", "name": "Parallel", "mode": "tables", "size": 8,
                     "owner_id": "p1", "line": ["p1", "p2", "p3", "p4"],
                     "players": [{"id": "p1", "name": "Alice", "state": "playing"},
                                 {"id": "p2", "name": "Bob", "state": "playing"},
                                 {"id": "p3", "name": "Carol", "state": "line"},
                                 {"id": "p4", "name": "Dan", "state": "line"},
                                 {"id": "p5", "name": "Eve", "state": "away"}],
                     "tables": [{"id": 1, "players": ["p1", "p2"], "match": "m1", "watch": True,
                                 "set": {"casual": True, "first_to": 3, "wins": [1, 2]}},
                                {"id": 2, "players": [], "match": None, "watch": False}]}
        self.client = SimpleNamespace(me={"id": "p1", "status": "room"}, my_room=self.room,
                                      players=[], rooms=[], room_pair=mock.Mock(), room_line=mock.Mock())
        self.tab = SimpleNamespace(client=self.client, call=mock.Mock(), status=mock.Mock(),
                                   actions={"room_line": object()}, action_text={}, match=None, driver=None,
                                   set_bar=None, spec=SimpleNamespace(ok=lambda: True, w=None, _watch=mock.Mock()))
        self.ui = RoomsUI(self.tab)

    def tearDown(self):
        i18n.set_language(self.old_language)

    def test_each_table_score_and_available_away_members_are_shown(self):
        text = self.ui.summary(self.room)
        self.assertIn("Table 1: Alice vs Bob -- FT3 -- Set 1-2", text)
        self.assertIn("Table 2: Empty table", text)
        self.assertIn("Available: Carol, Dan", text)
        self.assertIn("Away: Eve", text)
        self.assertNotIn("Winner stays", text)
        self.assertNotIn("Line:", text)

    def test_table_countdown_uses_server_clock_offset(self):
        self.client.clock_offset = 3
        table = {"id": 2, "players": ["p3", "p4"], "next": {"at": 110}}
        with mock.patch.object(tk_rooms.time, "time", return_value=100):
            self.assertEqual(self.ui.table_summary(self.room, table), "Table 2: Carol vs Dan -- starts in 7 s")

    def test_availability_uses_server_line_and_clear_table_text(self):
        self.client.me = {"id": "p5", "status": "room"}
        self.ui.toggle_line()
        self.assertEqual(self.tab.call.call_args.args, (self.client.room_line, True))
        self.tab.call.call_args.kwargs["then"](self.room)
        self.tab.status.assert_called_with("You are available for a free table.")
        self.room["line"].append("p5")
        self.ui.toggle_line()
        self.assertEqual(self.tab.call.call_args.args, (self.client.room_line, False))
        self.tab.call.call_args.kwargs["then"](self.room)
        self.tab.status.assert_called_with("You are away until you press Available to play.")

    def window(self):
        self.tab.view = SimpleNamespace(px=lambda n: n, body=lambda _w: Widget())
        w = SimpleNamespace(destroy=mock.Mock())
        with mock.patch.object(tk_rooms, "_window", return_value=(w, Widget())), \
                mock.patch.object(tk_rooms.tk, "StringVar", Var), \
                mock.patch.multiple(tk_rooms.ttk, Label=Widget, Combobox=Widget, Button=Widget):
            self.ui.window = tk_rooms.tables_window(self.ui, self.room)
        return self.ui.window

    def test_host_selects_idle_table_and_distinct_available_players(self):
        w = self.window()
        self.assertEqual(w.pair_button.options["state"], "disabled")
        w.table_var.set("2")
        w.player_vars[0].set("Carol")
        w.player_vars[1].set("Carol")
        w.pair_button.invoke()
        self.assertEqual(w.err.options["text"], "Select two different available players.")
        self.tab.call.assert_not_called()
        w.player_vars[1].set("Dan")
        w.pair_button.invoke()
        self.assertEqual(self.tab.call.call_args.args, (self.client.room_pair, 2, ["p3", "p4"]))

    def test_table_watch_uses_selected_table_and_refresh_drops_stale_pair(self):
        w = self.window()
        w.watch_button.invoke()
        self.tab.spec._watch.assert_called_once_with(room="r1", table=1)
        w = self.window()
        w.table_var.set("2")
        w.player_vars[0].set("Carol")
        self.room["line"].remove("p3")
        w.refresh_tables()
        self.assertEqual(w.player_vars[0].get(), "")
        self.assertEqual(w.pair_button.options["state"], "disabled")

    def test_host_can_rearrange_two_countdown_reservations(self):
        self.room["tables"] = [
            {"id": 1, "players": ["p1", "p2"], "match": None, "set": None,
             "next": {"at": 2000000000, "players": ["p1", "p2"]}},
            {"id": 2, "players": ["p3", "p4"], "match": None, "set": None,
             "next": {"at": 2000000000, "players": ["p3", "p4"]}}]
        self.assertEqual(self.ui.free_players(self.room), [])
        w = self.window()
        self.assertEqual(w.pair_button.options["state"], "normal")
        w.player_vars[0].set("Alice")
        w.player_vars[1].set("Carol")
        w.pair_button.invoke()
        self.assertEqual(self.tab.call.call_args.args, (self.client.room_pair, 1, ["p1", "p3"]))
        # An unfinished set holds its table even when it has no current game.
        self.room["tables"][0]["set"] = {"state": "active", "casual": True}
        w.refresh_tables()
        self.assertEqual(w.pair_button.options["state"], "disabled")
        self.assertEqual(w.player_vars[0].get(), "")

    def create_window(self):
        self.client.welcome = {"room_limits": {"max_size": 8}}
        self.client.training_ok = lambda: True
        self.client.room_tables_ok = lambda: True
        self.client.casual_sets_ok = lambda: True
        self.client.ingame_rematch_ok = lambda: True
        self.client.auto_skip_ok = lambda: True
        self.client.create_room = mock.Mock()
        self.tab.view = SimpleNamespace(px=lambda n: n, body=lambda _w: Widget())
        w = SimpleNamespace(destroy=mock.Mock())
        with mock.patch.object(tk_rooms, "_window", return_value=(w, Widget())), \
                mock.patch.multiple(tk_rooms.tk, StringVar=Var, IntVar=Var), \
                mock.patch.object(tk_rooms.tkfont, "Font", return_value=SimpleNamespace(
                    measure=lambda text: 8 * len(text))), \
                mock.patch.multiple(tk_rooms.ttk, Label=Widget, Entry=Widget, Combobox=Widget,
                                    Button=Widget, Checkbutton=Widget):
            self.ui.window = tk_rooms.create_window(self.ui)
        return self.ui.window

    def dispatch_create(self):
        fn, *args = self.tab.call.call_args.args
        # Exercise the submitted callable exactly as OnlineTab's worker does, without a thread or socket.
        fn(*args)
        return self.client.create_room.call_args

    def test_classic_create_keeps_first_to_and_rematch_rules_as_keywords(self):
        w = self.create_window()
        w.vars["name"].set("Combined")
        w.vars["first_to"].set("FT5")
        w.vars["rematch_policy"].set("Start automatically unless declined")
        w.vars["auto_skip_after_round"].set(1)
        w.create_button.invoke()
        call = self.dispatch_create()
        self.assertEqual(call.args, ("Combined", False, 2, "winner", None, None, False, False))
        self.assertEqual(call.kwargs, {"first_to": 5, "mode": "line",
                                       "rematch_policy": "auto_unless_declined", "auto_skip_after_round": True})

    def test_two_seat_tables_keep_first_to_and_drop_stale_classic_controls(self):
        w = self.create_window()
        w.vars["first_to"].set("FT3")
        w.vars["rematch_policy"].set("Start automatically unless declined")
        w.vars["auto_skip_after_round"].set(1)
        w.vars["mode"].set("Several matches at once")
        self.assertEqual(w.widgets["rematch_policy"].options["state"], "disabled")
        self.assertEqual(w.widgets["auto_skip_after_round"].options["state"], "disabled")
        w.create_button.invoke()
        call = self.dispatch_create()
        self.assertEqual(call.args[2], 2)
        self.assertEqual(call.kwargs, {"first_to": 3, "mode": "tables"})

    def test_room_watch_opens_table_selector(self):
        spec = Spectating(self.tab)
        spec._selected_room = lambda: self.room
        self.tab.rooms_ui = SimpleNamespace(tables=mock.Mock())
        spec._watch = mock.Mock()
        spec.watch_room()
        self.tab.rooms_ui.tables.assert_called_once_with(self.room)
        spec._watch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
