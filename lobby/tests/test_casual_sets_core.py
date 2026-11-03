"""Casual first-to regressions, entirely in memory: no sockets, games or server process.

Run from the repository with: python -m unittest discover -s lobby/tests -p test_casual_sets_core.py
"""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import proto
from t5lobby.server.lobby import CAPS, FEATURES, GameSet, LobbyServer, Match
from t5lobby.server.config import Config


def player(name, caps=("sets", "casual_sets", "ingame_pick")):
    p = SimpleNamespace(id=name, name=name, char="jin", account_id=None, guest=True,
                        build_id="test", online=True, conn=SimpleNamespace(caps=set(caps)),
                        set=None, match=None, room=None, status="idle", record=[0, 0, 0])
    p.send = Mock()
    p.brief = lambda: {"id": name, "name": name}
    p.public = p.brief
    return p


def server():
    """Instantiate no server services: only the methods under test have real behavior."""
    s = object.__new__(LobbyServer)
    s.cfg = Config()
    s.store = Mock()
    s.tours = Mock()
    s.note = Mock()
    s._count = Mock()
    s.matches = {}
    s.recent = {}
    s.rooms = {}
    s.dirty = False
    return s


class CasualSetCoreTest(unittest.TestCase):
    def test_challenge_offer_and_acceptance_preserve_selected_target(self):
        for target, peer_caps, effective in ((5, ("sets", "casual_sets"), 5),
                                             (10, ("sets",), 1)):
            with self.subTest(peer_caps=peer_caps):
                s = server()
                a, b = player("A"), player("B", peer_caps)
                a.last_challenge = 0
                s.players = {a.id: a, b.id: b}
                s.challenges = {}
                s.draining = False
                s._refuse_draining = Mock()
                s._is_blocked = Mock(return_value=False)
                s._retry_left = Mock(return_value=0)
                s._ping_info = Mock(return_value={"known": False})
                s._casual_wish = Mock(return_value={"side": None, "stage": "random"})
                s._casual_sides = lambda x, y: (x, y)
                s._abandon_set = Mock()
                s._leave_queue = Mock()
                s.create_match = Mock(return_value=SimpleNamespace(casual_delay=None))

                async def challenge_and_accept():
                    reply = await s.h_challenge(SimpleNamespace(player=a), {"player": b.id, "first_to": target})
                    self.assertEqual(reply["first_to"], effective)
                    self.assertEqual(b.send.call_args.args[0]["first_to"], effective)
                    await s.h_challenge_reply(SimpleNamespace(player=b),
                                              {"challenge": reply["challenge"], "accept": True})

                asyncio.run(challenge_and_accept())
                self.assertEqual(s.create_match.call_args.kwargs["first_to"], effective)

    def test_capability_and_effective_target(self):
        self.assertIn("casual_sets", CAPS)
        self.assertIn("casual_sets", FEATURES)
        a, b = player("A"), player("B")
        for target in (1, 2, 3, 5, 10):
            self.assertEqual(LobbyServer._casual_target(a, b, target), target)
        for caps in ((), ("sets",), ("casual_sets",)):
            b.conn.caps = set(caps)
            self.assertEqual(LobbyServer._casual_target(a, b, 10), 1)
        for bad in (True, False, None, "3", 3.0, 0, 4, -1, 11):
            with self.subTest(bad=bad), self.assertRaises(proto.LobbyError):
                LobbyServer._casual_target(a, b, bad)

    def test_targets_and_wire_are_unrated_including_ft1(self):
        a, b = player("A"), player("B")
        for target in (1, 2, 3, 5, 10):
            gs = GameSet(a, b, False, first_to=target)
            self.assertTrue(gs.automatic)
            self.assertFalse(gs.rated)
            self.assertFalse(gs.locked)
            self.assertEqual(gs.info()["first_to"], target)
            self.assertEqual(gs.info()["wins_needed"], target)
            self.assertEqual(gs.info()["best_of"], 2 * target - 1)
            self.assertFalse(gs.info()["rated"])
            self.assertTrue(gs.view(a)["casual"])
            self.assertFalse(gs.view(a)["rated"])

    def test_join_set_legacy_quick_training_and_ranked_keep_their_rules(self):
        s = server()
        a, b = player("A"), player("B")
        for origin, ranked, training, expected in (
                ("challenge", False, False, True), ("invite", False, False, True),
                ("room", False, False, True), ("queue", False, False, False),
                ("room", False, True, False), ("queue", True, False, False)):
            m = Match(a, b, ranked, origin)
            m.training = training
            s._join_set(m, None, None, 5)
            self.assertEqual(m.set.casual, expected)
            if ranked:
                self.assertTrue(m.set.rated)
                self.assertTrue(m.set.locked)
                self.assertEqual(m.set.wins_needed, s.cfg.ranked_set_wins)
        b.conn.caps = {"sets"}
        m = Match(a, b, False, "challenge")
        s._join_set(m, None, None, 10)
        self.assertFalse(m.set.automatic)
        self.assertNotIn("casual", m.set.info())

    def test_all_targets_stop_exactly_and_keep_per_game_character_choice(self):
        for target in (1, 2, 3, 5, 10):
            with self.subTest(first_to=target):
                s = server()
                s._set_schedule_next = Mock()
                a, b = player("A"), player("B")
                gs = GameSet(a, b, False, first_to=target)
                a.set = b.set = gs
                for number in range(1, target + 1):
                    a.char = "paul" if number % 2 else "jin"
                    m = Match(a, b, False, "challenge" if number == 1 else "set")
                    s._join_set(m, None, gs, target)
                    self.assertEqual(m.picks[0], a.char)
                    self.assertTrue(s._picks_in_game(m))
                    self.assertEqual(s._pick_seconds(m), int(s.cfg.ingame_pick))
                    gs.games += 1
                    gs.current = None
                    gs.last = m
                    s._set_game_over(gs, m, "confirmed", 0, [3, 1], None, None)
                    self.assertEqual(gs.score(), [number, 0])
                    if number < target:
                        self.assertIsNone(gs.outcome)
                    else:
                        self.assertEqual(gs.outcome["status"], "confirmed")
                        self.assertIs(gs.outcome["winner"], a)
                        self.assertEqual(gs.state, "ended")
                self.assertEqual(s._set_schedule_next.call_count, target - 1)
                s.store.add_unranked_game.assert_not_called()
                s.store.set_rating.assert_not_called()
                self.assertEqual(a.record, [0, 0, 0])  # conclusion adds no extra result
                self.assertIsNone(a.set)

    def test_leave_between_games_voids_unfinished_set_without_forfeit(self):
        s = server()
        a, b = player("A"), player("B")
        gs = GameSet(a, b, False, first_to=3)
        a.set = b.set = gs
        gs.wins[a.id] = 2
        gs.games = 2
        gs.next_timer = Mock()
        timer = gs.next_timer
        s._end_set(gs, "left", by=b)
        self.assertEqual(gs.outcome["status"], "void")
        self.assertIsNone(gs.outcome["winner"])
        self.assertIs(gs.outcome["blame"], b)
        self.assertEqual(gs.score(), [2, 0])
        timer.cancel.assert_called_once()
        s.store.add_unranked_game.assert_not_called()
        s.store.set_rating.assert_not_called()
        event = a.send.call_args.args[0]
        self.assertTrue(event["casual"])
        self.assertFalse(event["rated"])
        self.assertIsNone(event["result"])

    def test_split_score_waits_for_either_players_target(self):
        s = server()
        s._set_schedule_next = Mock()
        a, b = player("A"), player("B")
        gs = GameSet(a, b, False, first_to=2)
        m = Match(a, b, False, "challenge")
        for winner in (1, 0):
            s._set_game_over(gs, m, "confirmed", winner, [3, 1], None, None)
        self.assertEqual(gs.score(), [1, 1])
        self.assertIsNone(gs.outcome)
        s._set_game_over(gs, m, "confirmed", 1, [1, 3], None, None)
        self.assertEqual(gs.score(), [1, 2])
        self.assertIs(gs.outcome["winner"], b)
        self.assertEqual(gs.view(a)["wins"], [1, 2])
        self.assertEqual(gs.view(b)["wins"], [2, 1])

    def test_quit_keeps_game_forfeit_but_awards_no_set(self):
        s = server()
        a, b = player("A"), player("B")
        gs = GameSet(a, b, False, first_to=3)
        m = Match(a, b, False, "set")
        gs.wins[a.id] = 1
        s._set_game_over(gs, m, "forfeit", 1, [0, 3], "quit", 0)
        self.assertEqual(gs.outcome["status"], "void")
        self.assertIsNone(gs.outcome["winner"])
        self.assertEqual(gs.score(), [1, 0])
        self.assertEqual(gs.log[-1]["status"], "forfeit")
        self.assertEqual(gs.log[-1]["winner"], 1)
        s.store.set_rating.assert_not_called()

    def test_replays_bounded_and_desync_requires_fresh_connection(self):
        s = server()
        s.cfg.set_replays = 2
        s._set_schedule_next = Mock()
        a, b = player("A"), player("B")
        gs = GameSet(a, b, False, first_to=2)
        m = Match(a, b, False, "challenge")
        for _ in range(3):
            s._set_game_over(gs, m, "void", None, None, "desync", None)
        self.assertEqual(s._set_schedule_next.call_count, 2)
        self.assertEqual(gs.score(), [0, 0])
        self.assertEqual(gs.number, 1)
        self.assertTrue(gs.fresh)
        self.assertEqual(gs.outcome["status"], "void")

    def test_finish_records_every_casual_game_once(self):
        s = server()
        s._cancel_timers = Mock()
        s._rules_finish = lambda m, *args: args
        s._picked = Mock(return_value=None)
        s._release = Mock()
        s._save = Mock()
        s._set_schedule_next = Mock()
        a, b = player("A"), player("B")
        a.account_id, b.account_id = 1, 2
        gs = GameSet(a, b, False, first_to=2)
        a.set = b.set = gs
        for number in range(1, 3):
            m = Match(a, b, False, "challenge" if number == 1 else "set")
            s._join_set(m, None, gs, 2)
            gs.games += 1
            m.chars, m.stage, m.path = ["jin", "paul"], "s20", "direct"
            a.match = b.match = m
            with patch("t5lobby.server.lobby.asyncio.get_running_loop", return_value=Mock()):
                s._finish(m, "confirmed", 0, [3, 1])
            self.assertEqual(a.record, [number, 0, 0])
            self.assertEqual(b.record, [0, number, 0])
        self.assertEqual(s.store.add_unranked_game.call_count, 4)
        s.store.set_rating.assert_not_called()
        self.assertEqual(gs.outcome["status"], "confirmed")
        self.assertEqual(a.send.call_args.args[0]["t"], "set_end")

    def test_expiring_rematch_entry_cannot_end_countdown(self):
        s = server()
        a, b = player("A"), player("B")
        gs = GameSet(a, b, False, first_to=10)
        m = Match(a, b, False, "challenge")
        m.set = gs
        gs.last = m
        s.recent[m.id] = m
        s._expire_recent(m)
        self.assertEqual(gs.state, "active")
        self.assertNotIn(m.id, s.recent)

    def test_set_next_accepts_casual_keep_report(self):
        s = server()
        a, b = player("A"), player("B")
        gs = GameSet(a, b, False, first_to=2)
        a.set = b.set = gs
        gs.next_timer = Mock()
        result = asyncio.run(s.h_set_next(SimpleNamespace(player=a), {"keep": True}))
        self.assertEqual(result["state"], "waiting")
        self.assertTrue(gs.next_keep[a.id])


if __name__ == "__main__":
    unittest.main()
