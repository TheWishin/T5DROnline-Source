"""The driver's rematch question in the game (docs/REMATCH_1.2.0.md) without a process, a game, or a server: a fake
clock, a fake client, the real IngameUI channel (no worker thread; the test stands in for the game)."""
import tempfile
import unittest
from unittest import mock

import util  # noqa: F401
from t5lobby.ingame_ui import HEALTH_SECONDS, IngameUI
from t5lobby.match_driver import (CLOSE_SECONDS, VOTE_GRACE_SECONDS, GameLog, MatchDriver, fight_rules,
                                  ingame_rematch_wanted)


class Client:
    def __init__(self):
        self.calls = []
        self.my_room = None
        self.match = None
        self.me = {"id": "p1"}
        self.fail = False

    def rematch(self, *args):
        self.calls.append(("rematch",) + args)
        if self.fail:
            raise ValueError("test rejection")

    def leave_match(self, mid):
        self.calls.append(("leave_match", mid))

    def game_started(self, mid):
        pass


class Game:
    def __init__(self):
        self.alive = True

    def running(self):
        return self.alive

    def stop(self):
        self.alive = False


LABELS = {"title": "Rematch?", "won": "You won.", "lost": "You lost.", "draw": "Draw.",
          "opp_deciding": "{name} is deciding...", "opp_accept": "{name} wants a rematch!",
          "opp_decline": "{name} does not want a rematch.", "me_accept": "You want a rematch. Waiting for {name}...",
          "starting": "Rematch! Starting...", "me_declined": "No rematch. Back to the lobby.",
          "back_to_lobby": "No rematch. Back to the lobby.", "expired": "Time is up. Back to the lobby.",
          "auto": "Rematch starts in {seconds} s unless you decline.", "confirm": "Rematch", "cancel": "No thanks",
          "take_back": "Take it back", "key_confirm": "Z", "key_cancel": "X", "result_void": "No result"}


def result(policy="both_confirm", timeout=10, mid="m1", **extra):
    ev = {"t": "match_result", "match": mid, "status": "confirmed", "winner": 0, "rematch_window": timeout,
          "rematch_ui": {"v": 1, "kind": "rematch", "policy": policy, "timeout": timeout, "auto_after": 5,
                         "room_mode": "casual", "actions": ["accept", "decline"]}}
    ev.update(extra)
    return ev


class DriverIngameUITest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = Client()
        self.driver = MatchDriver(self.client, lambda env: self.fail("must not launch"), self.directory.name,
                                  mode="persistent", ingame_rematch=True)
        self.driver.game = Game()
        self.driver.glog = GameLog(None)
        self.driver.glog.connected = True
        self.driver.match_ev = {"opponent": {"name": "Bob"}}
        self.driver.session_ticket = mock.Mock(slot=0)
        self.now = 100.0
        self.driver.ui = IngameUI(self.directory.name, "m1", clock=lambda: self.now, worker=False)
        self.addCleanup(self.driver.ui.close)
        self.clock_patch = mock.patch("t5lobby.match_driver.time.monotonic", side_effect=lambda: self.now)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.driver.ingame_labels(LABELS)

    def open(self, **kw):
        self.driver.on_event(result(**kw))
        self.mark_ready()
        self.driver._watch_ingame_ui()
        return self.doc()

    def mark_ready(self):
        """The game drew the question as it is now (ui_ready.json)."""
        self.driver.ui.ready_at = self.now
        self.driver.ui.ready_revision = self.driver.ui.document["rev"]

    def doc(self):
        return self.driver.ui.snapshot()

    def press(self, name="accept", sequence=1):
        ui = self.driver.ui
        action = dict(ui._base(), seq=sequence, prompt=ui.document["prompt"], match=ui.document["match"], action=name)
        ui.receive(action)
        self.driver._watch_ingame_ui()
        self.driver._watch_ingame_ui()      # (the completion of the lobby call)
        return action

    def tick(self, seconds):
        self.now += seconds
        self.mark_ready()
        self.driver.ui.pump()
        self.driver._watch_ingame_ui()

    def kinds(self):
        return [n["kind"] for n in self.driver.poll()]

    # ------------------------------------------------------------------ the question
    def test_question_shows_result_opponent_countdown_and_keys(self):
        d = self.open()
        self.assertEqual(d["kind"], "rematch")
        self.assertEqual(d["allowed"], ["accept", "decline"])
        self.assertEqual((d["title"], d["body"]), ("Rematch?", "You won."))
        self.assertEqual((d["opponent"], d["opp_state"]), ("Bob is deciding...", "deciding"))
        self.assertEqual((d["countdown_ms"], d["total_ms"]), (10000, 10000))
        self.assertEqual(d["remaining_ms"], (10 + CLOSE_SECONDS) * 1000)
        self.assertEqual((d["key_confirm"], d["key_cancel"]), ("Z", "X"))
        self.assertTrue(self.driver.ingame_ui_active)
        self.assertIn("ingame_ui_ready", self.kinds())

    def test_loser_and_other_results(self):
        self.driver.session_ticket.slot = 1
        self.assertEqual(self.open()["body"], "You lost.")
        drv = self.driver
        drv._rq_end(fallback=False)
        drv.on_event(result(mid="m2", status="void", winner=None))
        self.assertEqual(self.doc()["body"], "No result")

    def test_accept_in_game_votes_once_and_waits_for_the_opponent(self):
        self.open()
        self.press("accept")
        self.assertEqual((self.doc()["ack_seq"], self.doc()["ack_status"]), (1, "ok"))
        self.press("accept", 2)
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])
        d = self.doc()
        self.assertEqual(d["allowed"], ["decline"])               # Circle takes it back
        self.assertEqual(d["status"], "You want a rematch. Waiting for Bob...")
        self.assertEqual(d["cancel"], "Take it back")
        self.assertEqual((d["ack_seq"], d["ack_status"]), (2, "rejected"))     # (a second yes is refused)
        self.assertIn("ingame_vote", self.kinds())
        self.assertIsNone(self.driver.ticket)                      # only match_start starts a fight

    def test_opponent_accepts_first_then_both(self):
        self.open()
        self.driver.on_event({"t": "rematch", "match": "m1", "state": "offered", "from": {"name": "Bob"}})
        d = self.doc()
        self.assertEqual((d["opponent"], d["opp_state"]), ("Bob wants a rematch!", "accept"))
        self.press("accept")
        d = self.doc()
        self.assertEqual((d["status"], d["allowed"], d["countdown_ms"]), ("Rematch! Starting...", [], 0))
        self.driver.on_event({"t": "match_start", "match": "m2", "continue": True, "opponent": {"name": "Bob"},
                              "fight": {}})
        self.assertEqual(self.doc()["kind"], "hidden")
        self.assertNotIn("ingame_ui_fallback", self.kinds())     # the game goes on: the launcher stays behind

    def test_decline_in_game_says_so_then_hands_back_to_the_launcher(self):
        self.open()
        self.press("decline")
        self.assertEqual(self.client.calls, [("rematch", "m1", False, False)])
        d = self.doc()
        self.assertEqual((d["status"], d["allowed"]), ("No rematch. Back to the lobby.", []))
        self.assertNotIn("ingame_ui_fallback", self.kinds())
        self.tick(CLOSE_SECONDS)
        self.assertEqual(self.doc()["kind"], "hidden")
        self.assertIn("ingame_ui_fallback", self.kinds())
        self.assertEqual(self.driver.ctl, None)       # (no persistent control channel in this test: nothing sent)

    def test_take_back_after_accept(self):
        self.open()
        self.press("accept")
        self.press("decline", 2)
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True), ("rematch", "m1", False, False)])
        self.press("accept", 3)
        self.assertEqual(len(self.client.calls), 2)

    def test_opponent_declines(self):
        self.open()
        self.driver.on_event({"t": "rematch", "match": "m1", "state": "declined", "from": {"name": "Bob"}})
        d = self.doc()
        self.assertEqual((d["opponent"], d["opp_state"], d["allowed"]), ("Bob does not want a rematch.", "decline", []))
        self.tick(CLOSE_SECONDS)
        self.assertIn("ingame_ui_fallback", self.kinds())

    def test_timeout_without_an_answer(self):
        self.open()
        self.tick(9.9)
        self.assertEqual(self.doc()["allowed"], ["accept", "decline"])
        self.tick(0.2)
        d = self.doc()
        self.assertEqual((d["status"], d["allowed"]), ("Time is up. Back to the lobby.", []))
        self.tick(CLOSE_SECONDS)
        self.assertIn("ingame_ui_fallback", self.kinds())
        self.assertEqual(self.client.calls, [])

    def test_accept_at_the_last_moment_waits_for_the_lobby(self):
        self.open()
        self.tick(9.8)
        self.press("accept")
        self.tick(0.5)                                           # countdown over, our yes sent
        self.assertEqual(self.doc()["status"], "You want a rematch. Waiting for Bob...")
        self.driver.on_event({"t": "match_start", "match": "m2", "continue": True, "opponent": {"name": "Bob"},
                              "fight": {}})
        self.assertEqual(self.doc()["kind"], "hidden")
        self.assertNotIn("ingame_ui_fallback", self.kinds())

    def test_rematch_over_a_new_connection_ends_the_question_quietly(self):
        self.open()
        self.press("accept")
        self.driver.on_event({"t": "rematch", "match": "m1", "state": "accepted"})
        self.now += HEALTH_SECONDS + 1                # (the game resets for the new session: no heartbeat)
        self.driver._watch_ingame_ui()
        self.assertNotIn("ingame_ui_fallback", self.kinds())
        self.driver.ctl = mock.Mock()
        self.driver.on_event({"t": "match_found", "match": "m2", "rematch_of": "m1", "keep": False})
        self.assertEqual(self.doc()["kind"], "hidden")
        self.assertNotIn("ingame_ui_fallback", self.kinds())

    def test_server_expiry_after_our_yes(self):
        self.open()
        self.press("accept")
        self.tick(10 + VOTE_GRACE_SECONDS + 0.1)
        self.assertEqual(self.doc()["status"], "Time is up. Back to the lobby.")

    def test_server_expired_event(self):
        self.open()
        self.driver.on_event({"t": "rematch", "match": "m1", "state": "expired"})
        self.assertEqual(self.doc()["status"], "Time is up. Back to the lobby.")

    def test_lobby_refuses_the_vote(self):
        self.client.fail = True
        self.open()
        self.press("accept")
        self.assertEqual(self.driver.ui.document["ack_status"], "rejected")
        self.assertEqual(self.doc()["status"], "Time is up. Back to the lobby.")

    def test_duplicate_is_reserved_before_asynchronous_lobby_call(self):
        self.open()
        self.driver.async_calls = True
        pending = []

        class Thread:
            def __init__(self, target, args, daemon):
                pending.append((target, args))

            def start(self):
                pass

        ui = self.driver.ui
        action = dict(ui._base(), seq=1, prompt=ui.document["prompt"], match="m1", action="accept")
        with mock.patch("t5lobby.match_driver.threading.Thread", Thread):
            ui.receive(action)
            self.driver._watch_ingame_ui()
            ui.receive(action)
            self.driver._watch_ingame_ui()
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.client.calls, [])
        pending[0][0](*pending[0][1])
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])
        self.assertEqual(ui.document["ack_seq"], 1)

    def test_launcher_button_and_game_share_one_vote(self):
        self.open()
        self.driver.rematch("m1", True)                         # the launcher's Rematch button
        self.press("accept")
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])
        self.assertEqual(self.doc()["allowed"], ["decline"])

    def test_game_that_never_shows_it_falls_back_to_the_launcher(self):
        self.driver.on_event(result())
        self.assertTrue(self.driver.ingame_ui_pending is False)  # (no game answer at all yet: not healthy)
        self.now += HEALTH_SECONDS
        self.driver._watch_ingame_ui()
        self.assertIn("ingame_ui_fallback", self.kinds())
        self.assertFalse(self.driver.ingame_ui_active)
        self.driver.rematch("m1", True)                         # the launcher's question works as before
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])

    def test_game_that_stops_answering_falls_back(self):
        self.open()
        self.now += HEALTH_SECONDS + 0.1
        self.driver._watch_ingame_ui()
        self.assertIn("ingame_ui_fallback", self.kinds())

    def test_auto_policy_votes_when_its_countdown_ends_unless_declined(self):
        d = self.open(policy="auto_unless_declined")
        self.assertEqual(d["countdown_ms"], 5000)
        self.assertEqual(d["status"], "Rematch starts in 5 s unless you decline.")
        self.tick(2)
        self.assertEqual(self.doc()["status"], "Rematch starts in 3 s unless you decline.")
        self.tick(3)
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])
        self.assertEqual(self.doc()["status"], "You want a rematch. Waiting for Bob...")

    def test_auto_policy_decline_cancels(self):
        self.open(policy="auto_unless_declined")
        self.press("decline")
        self.tick(6)
        self.assertEqual(self.client.calls, [("rematch", "m1", False, False)])

    def test_ranked_sets_old_servers_and_rooms_keep_the_launcher(self):
        for ev in (dict(result(), ranked=True), dict(result(), set={"rated": True}), dict(result(), rematch_ui=None),
                   dict(result(), rematch_window=0),
                   dict(result(), rematch_ui={"v": 1, "kind": "community", "policy": "both_confirm",
                                              "timeout": 10, "actions": ["sit_out"]})):
            self.driver._rq = None
            self.assertFalse(self.driver.offer_ingame_ui(ev))
            self.assertIsNone(self.driver._rq)

    def test_no_channel_no_question(self):
        self.driver.ui = None
        self.assertFalse(self.driver.offer_ingame_ui(result()))

    def test_switch(self):
        self.assertTrue(ingame_rematch_wanted({}))
        self.assertTrue(ingame_rematch_wanted({"T5_INGAME_REMATCH": "1"}))
        self.assertFalse(ingame_rematch_wanted({"T5_INGAME_REMATCH": "0"}))

    def test_process_mode_decline_hands_game_to_launcher_after_the_words(self):
        self.driver.mode = "process"
        self.open()
        self.press("decline")
        self.assertTrue(self.driver.game_running())
        self.tick(CLOSE_SECONDS)
        self.assertTrue(self.driver.game_running())
        self.assertIn("return_to_lobby", self.kinds())  # UI captures foreground, then hides/stops it

    def test_process_mode_take_back_racing_a_committed_rematch_keeps_the_game(self):
        # review rematch-ingame-120 P2: accept, the opponent's accept commits the rematch at the server, our take
        # back (decline) arrives too late -- the server's match_found(keep) must not be answered by closing the game
        self.driver.mode = "process"
        self.open()
        self.press("accept")
        self.press("decline", 2)
        self.assertTrue(self.driver._rq["stop_after"])
        self.driver.on_event({"t": "match_found", "match": "m2", "rematch_of": "m1", "keep": True})
        self.assertIsNone(self.driver._rq)
        self.assertTrue(self.driver.game_running())
        self.tick(CLOSE_SECONDS)
        self.assertTrue(self.driver.game_running())
        self.assertEqual(self.doc()["kind"], "hidden")
        # without a new match the take back hands the game back to the launcher after its words
        self.driver._rq = None
        self.driver.rematch_sent.clear()
        self.driver.rematch_declined.clear()
        self.driver.ui.close()
        self.driver.ui = IngameUI(self.directory.name, "m3", clock=lambda: self.now, worker=False)
        self.driver.ingame_labels(LABELS)
        self.open(mid="m3")
        self.press("accept")
        self.press("decline", 2)
        self.tick(CLOSE_SECONDS)
        self.assertTrue(self.driver.game_running())
        self.assertIn("return_to_lobby", self.kinds())

    def test_skip_fight_line_only_from_authoritative_server_true(self):
        self.assertEqual(fight_rules({"auto_skip_after_round": True}), " auto_skip_after_round=1")
        for value in (False, 1, "true", None):
            self.assertEqual(fight_rules({"auto_skip_after_round": value}), "")

    def test_old_game_cannot_silently_ignore_agreed_skip_rule(self):
        self.driver._auto_skip_supported = False
        self.driver._start({"match": "m2", "fight": {"auto_skip_after_round": True}})
        self.assertEqual(self.client.calls, [("leave_match", "m2")])

    def test_intro_skip_fight_line_only_from_authoritative_server_true(self):
        """1.2.0: the server's fight.auto_skip_intro -> the fight line's auto_skip_intro=1 (both launchers write it)"""
        self.assertEqual(fight_rules({"auto_skip_intro": True}), " auto_skip_intro=1")
        self.assertEqual(fight_rules({"auto_skip_after_round": True, "auto_skip_intro": True}),
                         " auto_skip_after_round=1 auto_skip_intro=1")
        for value in (False, 1, "true", None):
            self.assertEqual(fight_rules({"auto_skip_intro": value}), "")

    def test_old_game_cannot_silently_ignore_agreed_intro_rule(self):
        self.driver._auto_skip_intro_supported = False
        self.driver._start({"match": "m3", "fight": {"auto_skip_intro": True}})
        self.assertEqual(self.client.calls, [("leave_match", "m3")])

    def test_game_marker_for_the_intro_rule(self):
        import os
        from t5lobby.match_driver import game_supports_auto_skip_intro
        with tempfile.TemporaryDirectory() as d:
            new, old = os.path.join(d, "new.exe"), os.path.join(d, "old.exe")
            with open(new, "wb") as f:
                f.write(b"\0x line.find(\"auto_skip_intro=\") \0")
            with open(old, "wb") as f:
                f.write(b"\0auto_skip_after_round=\0")
            self.assertTrue(game_supports_auto_skip_intro([new]))
            self.assertFalse(game_supports_auto_skip_intro([old]))


if __name__ == "__main__":
    unittest.main()
