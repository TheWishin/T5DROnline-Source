"""Watching the room's table while waiting (1.2.0, docs/SPECTATE.md "Automatically watch your room's table").

No Tk window, subprocess, socket or game: the policy and the Spectating controller with fakes.
"""
import unittest
from types import SimpleNamespace as NS

import util  # noqa: F401 (sets sys.path)
from t5lobby import auto_spectate
from t5lobby.auto_spectate import TablePolicy, table_blocker, table_targets
from t5lobby.tk_spectate import Spectating


class Game:
    def __init__(self):
        self.live = True
        self.stops = 0

    def running(self):
        return self.live

    def stop(self):
        self.stops += 1
        self.live = False


class Client:
    def __init__(self, room):
        self.me = {"id": "me", "status": "room"}
        self.match = None
        self.ticket = None
        self.connected = True
        self.my_room = room
        self.rooms = []
        self.players = []
        self.friend_list = None
        self.spec_watch = None
        self.spec_generation = 0
        self.cancels = 0

    def has_spectate(self):
        return True

    def watch(self, *args):
        raise AssertionError("a test never runs a client call")

    def cancel_watch(self):
        self.cancels += 1
        self.spec_generation += 1
        self.spec_watch = None

    def set_spectate_prefs(self, *args):
        pass


class Tab:
    def __init__(self, room):
        self.client = Client(room)
        self.driver = None
        self.match = None
        self.calls = []
        self.boots = []
        self.hints = []
        self.app = NS(game=None, settings={}, start_game=self.start_game, build=None)
        self.rooms_ui = NS(autowatch_hint=self.hints.append)

    def start_game(self, env):
        self.boots.append(env)
        self.app.game = Game()
        return self.app.game

    def call(self, fn, *args, **kw):
        self.calls.append((fn, args, kw))

    def status(self, *args, **kw):
        pass

    def _set_actions(self):
        pass


def line_room(watch=True, playing=("a", "b"), nxt=None, private=False):
    return {"id": "r1", "size": 4, "members": ["a", "b", "me", "d"], "line": ["a", "b", "me", "d"],
            "playing": list(playing), "next": nxt, "watch": watch, "lock": "password" if private else None}


def tables_room(tables):
    return {"id": "r2", "size": 6, "mode": "tables", "members": ["a", "b", "c", "d", "me", "f"],
            "line": [], "playing": [], "next": None, "watch": any(t.get("watch") for t in tables),
            "tables": tables}


class TablePolicyTest(unittest.TestCase):
    def test_line_room_is_watched_at_once_and_on_by_default(self):
        tab = Tab(line_room())
        self.assertIsNone(table_blocker(tab))
        target = TablePolicy().due(tab, now=0.0)
        self.assertEqual(target[0], {"room": "r1"})
        self.assertEqual(target[1], ("r1", None, ("a", "b")))

    def test_nothing_while_off_not_in_a_room_or_not_watchable(self):
        tab = Tab(line_room())
        tab.app.settings["auto_watch_table"] = False
        self.assertEqual(table_blocker(tab), "off")
        self.assertIsNone(TablePolicy().due(tab, 0.0))
        tab = Tab(line_room(watch=False))           # privacy prefs, private room for others, nothing played
        self.assertIsNone(TablePolicy().due(tab, 0.0))
        tab = Tab(dict(line_room(), size=2))        # a classic room has no one waiting
        self.assertEqual(table_blocker(tab), "room")
        tab = Tab(line_room())
        tab.client.me["status"] = "queue"
        self.assertEqual(table_blocker(tab), "room")

    def test_my_turn_build_and_own_game_block(self):
        tab = Tab(line_room(nxt={"at": 1.0, "players": ["d", "me"]}))
        self.assertEqual(table_blocker(tab), "turn")
        tab = Tab(line_room(playing=("me", "a")))
        self.assertEqual(table_blocker(tab), "turn")
        tab = Tab(line_room())
        tab.ready_deadline = 5.0
        self.assertEqual(table_blocker(tab), "turn")
        tab = Tab(line_room())
        tab.app.build = object()
        self.assertEqual(table_blocker(tab), "build")
        tab = Tab(line_room())
        game = Game()
        tab.driver = NS(ticket=None, game=game, game_running=game.running)   # a persistent game kept open
        self.assertEqual(table_blocker(tab), "game")
        self.assertIsNone(TablePolicy().due(tab, 0.0))

    def test_tables_prefer_my_table_and_wait_for_its_next_pair(self):
        t1 = {"id": 1, "players": ["a", "b"], "match": "m1", "watch": True}
        t2 = {"id": 2, "players": ["c", "d"], "match": "m2", "watch": True}
        self.assertEqual([kw for kw, _ in table_targets(tables_room([t1, t2]))],
                         [{"room": "r2", "table": 1}, {"room": "r2", "table": 2}])
        self.assertEqual([kw for kw, _ in table_targets(tables_room([t1, t2]), prefer=2)][0],
                         {"room": "r2", "table": 2})
        waiting = {"id": 2, "players": ["c", "f"], "match": None, "watch": False, "next": {"at": 9.0}}
        self.assertEqual(table_targets(tables_room([t1, waiting]), prefer=2), [])
        idle = {"id": 2, "players": [], "match": None, "watch": False}
        self.assertEqual([kw for kw, _ in table_targets(tables_room([t1, idle]), prefer=2)],
                         [{"room": "r2", "table": 1}])

    def test_the_table_i_played_at_becomes_mine(self):
        room = tables_room([{"id": 1, "players": ["a", "b"], "match": "m1", "watch": True},
                            {"id": 2, "players": ["me", "c"], "match": "m2", "watch": False}])
        tab = Tab(room)
        p = TablePolicy()
        self.assertIsNone(p.due(tab, 0.0))            # playing at table 2 myself
        self.assertEqual(p.prefer, 2)
        room["tables"][1] = {"id": 2, "players": ["d", "f"], "match": None, "watch": False, "next": {"at": 3.0}}
        self.assertIsNone(p.due(tab, 1.0))            # my table's next pair comes: wait for it
        room["tables"][1] = {"id": 2, "players": ["d", "f"], "match": "m3", "watch": True}
        self.assertEqual(p.due(tab, 2.0)[0], {"room": "r2", "table": 2})

    def test_retry_spacing_and_stop_skips_only_this_turn(self):
        room = line_room()
        tab = Tab(room)
        p = TablePolicy()
        target = p.due(tab, 0.0)
        p.attempted(target, 0.0)
        self.assertIsNone(p.due(tab, 0.5))            # one request a second at most
        self.assertIsNone(p.due(tab, 4.0))            # the same table again after 5 s
        self.assertEqual(p.due(tab, 5.1), target)
        p.stopped(target[1])
        self.assertIsNone(p.due(tab, 20.0))
        room["playing"] = ["a", "d"]                  # the next pair: a new turn at the table
        self.assertEqual(p.due(tab, 21.0)[1], ("r1", None, ("a", "d")))

    def test_lobby_wide_policy_leaves_my_room_to_the_table(self):
        tab = Tab(line_room())
        tab.client.rooms = [{"id": "other", "watch": True}]
        self.assertEqual(auto_spectate.candidates(tab.client, own_room=False), [{"room": "other"}])
        self.assertEqual(auto_spectate.candidates(tab.client)[0], {"room": "r1"})


class TableWatchControllerTest(unittest.TestCase):
    def setUp(self):
        self.room = line_room()
        self.tab = Tab(self.room)
        self.spec = Spectating(self.tab)

    def watches(self):
        return [c for c in self.tab.calls if getattr(c[0], "__name__", "") == "watch"]

    def answer(self, stream="s1", match="m1", **extra):
        fn, args, kw = self.watches()[-1]
        self.tab.client.spec_watch = {"stream": stream, "path": "x.t5live"}
        kw["then"](dict({"stream": stream, "match": match, "players": [{"name": "A"}, {"name": "B"}]}, **extra))

    def start_watching(self):
        self.spec.poll()
        self.assertEqual(len(self.watches()), 1)
        self.assertEqual(self.watches()[0][1][:2], (None, "r1"))
        self.answer()
        w = self.spec.w
        self.assertEqual(w["automatic"], "table")
        w["result"] = w["status"] = "not-opened.json"
        w["game"] = self.tab.start_game({})
        w["state"] = "playing"
        w["t_status"] = float("inf")
        return w

    def test_waiting_member_watches_at_once(self):
        w = self.start_watching()
        self.assertEqual(w["seat"], ("r1", None, ("a", "b")))

    def test_my_turn_closes_the_spectator_game_in_the_same_poll(self):
        w = self.start_watching()
        self.room["next"] = {"at": 8.0, "players": ["me", "a"]}
        self.spec.poll()
        self.assertEqual(w["game"].stops, 1)
        self.assertEqual(self.tab.client.cancels, 1)
        self.assertIsNone(self.spec.w)
        self.assertEqual(len(self.watches()), 1)       # and nothing else is watched during my turn

    def test_match_found_closes_it_before_the_driver_sees_the_event(self):
        w = self.start_watching()
        self.spec.before_event({"t": "match_found", "match": "mine"})
        self.assertEqual(w["game"].stops, 1)

    def test_unticking_stops_at_once_and_ticking_again_resumes(self):
        w = self.start_watching()
        self.tab.app.settings["auto_watch_table"] = False
        self.spec.poll()
        self.assertEqual(w["game"].stops, 1)
        self.assertIsNone(self.spec.w)
        self.tab.app.game = None
        self.spec.poll()
        self.assertEqual(len(self.watches()), 1)
        self.tab.app.settings["auto_watch_table"] = True
        self.spec._table._next = 0.0
        self.spec._table._retry.clear()
        self.spec.poll()
        self.assertEqual(len(self.watches()), 2)       # the same match again: unticking is no "skip"

    def test_next_pair_is_picked_up_after_the_stream_ended(self):
        w = self.start_watching()
        self.spec.on_event({"t": "spec_end", "stream": "s1", "reason": "over", "ready": True})
        self.assertEqual(w["game"].stops, 0)           # the end of the match still plays
        self.room.update(playing=[], watch=False)
        self.spec.poll()
        self.assertEqual(len(self.watches()), 1)
        self.room.update(playing=["a", "d"], watch=True)   # the next pair at the table
        self.spec._table._next = 0.0
        self.spec.poll()
        self.assertEqual(w["game"].stops, 0)           # the old match plays to its end first
        self.assertEqual(len(self.watches()), 1)
        w["end_at"] -= auto_spectate.TABLE_END_GRACE + 1
        self.spec.poll()
        self.assertEqual(w["game"].stops, 1)
        self.assertEqual(len(self.watches()), 2)
        self.answer(stream="s2", match="m2")
        self.assertEqual(self.spec.w["seat"], ("r1", None, ("a", "d")))

    def test_stop_watching_skips_this_turn_only(self):
        self.start_watching()
        self.spec.stop()
        self.tab.app.game = None
        self.spec._table._next = 0.0
        self.spec._table._retry.clear()
        self.spec.poll()
        self.assertEqual(len(self.watches()), 1)
        self.room["playing"] = ["b", "d"]
        self.spec.poll()
        self.assertEqual(len(self.watches()), 2)

    def test_closing_the_spectator_window_does_not_reopen_it_for_this_turn(self):
        w = self.start_watching()
        w["game"].live = False                         # the player closed the spectator game's window
        self.spec.poll()
        self.spec.poll()
        self.assertIsNone(self.spec.w)
        self.spec._table._next = 0.0
        self.spec._table._retry.clear()
        self.spec.poll()
        self.assertEqual(len(self.watches()), 1)
        self.room["playing"] = ["a", "d"]              # the next pair: watched again
        self.spec.poll()
        self.assertEqual(len(self.watches()), 2)

    def test_own_open_game_is_never_closed_for_it_and_says_why(self):
        game = self.tab.app.game = Game()
        self.tab.driver = NS(ticket=None, game=game, game_running=game.running)
        self.spec.poll()
        self.assertEqual(self.watches(), [])
        self.assertEqual(game.stops, 0)
        self.assertEqual(len(self.tab.hints), 1)
        self.assertTrue(self.tab.hints[0])

    def test_late_answer_after_my_turn_starts_nothing(self):
        self.spec.poll()
        self.room["next"] = {"at": 8.0, "players": ["me", "a"]}
        self.answer()
        self.assertIsNone(self.spec.w)
        self.assertEqual(self.tab.boots, [])

    def test_manual_watch_is_left_alone(self):
        self.tab.app.settings["auto_watch_table"] = False
        self.spec._watch(room="r1")
        self.answer()
        w = self.spec.w
        self.tab.app.settings["auto_watch_table"] = True
        self.spec.poll()
        self.assertIs(self.spec.w, w)
        self.assertEqual(len(self.watches()), 1)


if __name__ == "__main__":
    unittest.main()
