"""Pure policy regressions: no Tk window, subprocess, sockets or game."""
import unittest
from types import SimpleNamespace as NS

import util  # noqa: F401 (sets sys.path)
from t5lobby.auto_spectate import Policy, candidates, idle


def tab(enabled=True):
    c = NS(me={"id": "me", "status": "idle"}, match=None, connected=True,
           has_spectate=lambda: True, my_room=None, rooms=[], players=[], friend_list=None)
    return NS(client=c, app=NS(settings={"auto_spectate": enabled}, game=None), driver=None)


class AutoSpectatePolicyTest(unittest.TestCase):
    def test_off_by_default_and_waits_fifteen_seconds(self):
        t = tab()
        t.app.settings.clear()
        t.client.rooms = [{"id": "r", "watch": True}]
        p = Policy()
        self.assertIsNone(p.due(t, 0))
        self.assertIsNone(p.due(t, 100))
        t.app.settings["auto_spectate"] = True
        self.assertIsNone(p.due(t, 100))
        self.assertIsNone(p.due(t, 114.9))
        self.assertEqual(p.due(t, 115), {"room": "r"})

    def test_own_room_then_friends_then_highest_known_public_rank(self):
        t = tab()
        c = t.client
        c.me["status"] = "room"
        c.my_room = {"id": "own", "watch": True, "private": "password"}
        c.friend_list = {"friends": [{"name": "Friend", "watch": True, "tier": 1}]}
        c.players = [{"id": "high", "tier": 20, "rating": 2100}, {"id": "low", "tier": 2}]
        c.rooms = [{"id": "low", "members": ["low"], "watch": True},
                   {"id": "high", "members": ["high"], "watch": True},
                   {"id": "own", "watch": True}, {"id": "hidden", "hidden": True, "watch": True},
                   {"id": "locked", "private": "password", "watch": True},
                   {"id": "no", "watch": False}]
        self.assertEqual(candidates(c), [{"room": "own"}, {"name": "Friend"},
                                         {"room": "high"}, {"room": "low"}])

    def test_ties_and_old_servers_have_stable_fallback(self):
        t = tab()
        t.client.rooms = [{"id": "z", "watch": True}, {"id": "a", "watch": True}, {"id": "old"}]
        self.assertEqual(candidates(t.client), [{"room": "a"}, {"room": "z"}])
        t.client.has_spectate = lambda: False
        self.assertFalse(idle(t))

    def test_parallel_rooms_watch_only_advertised_tables(self):
        t = tab()
        t.client.me["status"] = "room"
        t.client.my_room = {"id": "own", "mode": "tables", "watch": True,
                            "tables": [{"id": 1, "watch": False}, {"id": 2, "watch": True}]}
        t.client.rooms = [{"id": "public", "mode": "tables", "watch": True,
                           "tables": [{"id": 1, "watch": True}, {"id": 2, "watch": False}]},
                          {"id": "missing-tables", "mode": "tables", "watch": True}]
        self.assertEqual(candidates(t.client), [{"room": "own", "table": 2},
                                               {"room": "public", "table": 1}])

    def test_parallel_table_countdown_prevents_idle_watch(self):
        t = tab()
        t.client.my_room = {"mode": "tables", "playing": [], "next": None,
                            "tables": [{"id": 1, "next": {"players": ["me", "other"]}}]}
        self.assertFalse(idle(t))
        t.client.my_room["tables"][0]["next"]["players"] = ["other", "third"]
        self.assertTrue(idle(t))

    def test_each_attention_or_match_guard_prevents_a_boot(self):
        for field in ("match", "challenge", "invite", "outgoing_invite", "ready_deadline", "set_bar", "rematch_bar"):
            with self.subTest(field=field):
                t = tab()
                setattr(t, field, {})
                self.assertFalse(idle(t))
        for status in ("queue", "match", "playing", None):
            t = tab()
            t.client.me["status"] = status
            self.assertFalse(idle(t))
        for field in ("ready_sent", "set_locked", "bar_spec"):
            t = tab()
            setattr(t, field, True)
            self.assertFalse(idle(t))
        t = tab()
        t.client.match = {"state": "ready"}
        self.assertFalse(idle(t))
        t = tab()
        t.chal = NS(out={"pending": {}}, incoming={})
        self.assertFalse(idle(t))
        t.chal = NS(out={}, incoming={"pending": "Rival"})
        self.assertFalse(idle(t))
        t = tab()
        t.tours = NS(call={})
        self.assertFalse(idle(t))

    def test_never_evicts_any_existing_game_or_upcoming_room_player(self):
        t = tab()
        t.app.game = NS(running=lambda: True)
        self.assertFalse(idle(t))
        t.app.game = None
        t.driver = NS(ticket=None, game_running=lambda: True)
        self.assertFalse(idle(t))
        t.driver = NS(ticket=object(), game_running=lambda: False)
        self.assertFalse(idle(t))
        t.driver = None
        for room in ({"playing": ["me"]}, {"next": {"players": ["me"]}}):
            t.client.my_room = room
            self.assertFalse(idle(t))

    def test_refusal_backoff_tries_another_target_and_manual_stop_waits(self):
        t = tab()
        t.client.rooms = [{"id": "a", "watch": True}, {"id": "b", "watch": True}]
        p = Policy()
        self.assertIsNone(p.due(t, 0))
        self.assertEqual(p.due(t, 15), {"room": "a"})
        p.attempted(15)
        self.assertIsNone(p.due(t, 44))
        self.assertEqual(p.due(t, 45), {"room": "b"})
        p.attempted(45)
        p.pause(46)
        self.assertIsNone(p.due(t, 165))
        self.assertEqual(p.due(t, 166), {"room": "a"})

    def test_busy_or_new_connection_restarts_idle_wait(self):
        t = tab()
        t.client.rooms = [{"id": "r", "watch": True}]
        p = Policy()
        p.due(t, 0)
        t.challenge = "incoming"
        self.assertIsNone(p.due(t, 14))
        t.challenge = None
        self.assertIsNone(p.due(t, 15))
        self.assertEqual(p.due(t, 30), {"room": "r"})
        t.client = tab().client
        t.client.rooms = [{"id": "r", "watch": True}]
        self.assertIsNone(p.due(t, 31))
        self.assertEqual(p.due(t, 46), {"room": "r"})
