"""Driver menu dispatch without a process, a game, or a server."""
import tempfile
import unittest
from unittest import mock

import util  # noqa: F401
from t5lobby.ingame_ui import IngameUI
from t5lobby.match_driver import GameLog, MatchDriver, fight_rules


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

    def ready(self, *args):
        self.calls.append(("ready",) + args)

    def quick_match(self):
        self.calls.append(("quick_match",))

    def room_line(self, back):
        self.calls.append(("room_line", back))

    def leave_match(self, mid):
        self.calls.append(("leave_match", mid))


class Game:
    def __init__(self):
        self.alive = True

    def running(self):
        return self.alive

    def stop(self):
        self.alive = False


def result(policy="both_confirm"):
    return {"t": "match_result", "match": "m1", "status": "ok", "rematch_window": 20,
            "rematch_ui": {"v": 1, "policy": policy, "timeout": 20, "auto_after": 5,
                           "room_mode": "classic", "actions": ["accept", "decline"]}}


class DriverIngameUITest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = Client()
        self.driver = MatchDriver(self.client, lambda env: self.fail("must not launch"), self.directory.name,
                                  mode="process", ingame_rematch=False)
        self.driver.game = Game()
        self.driver.glog = GameLog(None)
        self.driver.glog.connected = True
        self.now = 100.0
        self.driver.ui = IngameUI(self.directory.name, "m1", clock=lambda: self.now, worker=False)
        self.addCleanup(self.driver.ui.close)
        self.clock_patch = mock.patch("t5lobby.match_driver.time.monotonic", side_effect=lambda: self.now)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.driver.on_event(result())
        self.mark_ready()

    def mark_ready(self):
        self.driver.ui.ready_at = self.now
        self.driver.ui.ready_revision = self.driver.ui.document["rev"]

    def request(self, name="accept", sequence=1):
        ui = self.driver.ui
        action = dict(ui._base(), seq=sequence, prompt=ui.document["prompt"],
                      match=ui.document["match"], action=name)
        ui.receive(action)
        return action

    def test_accept_uses_existing_vote_and_waits_for_server_start(self):
        self.request()
        self.driver._watch_ingame_ui()
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])
        self.assertEqual(self.driver.ui.document["kind"], "waiting")
        self.assertEqual(self.driver.ui.document["ack_status"], "ok")
        self.assertTrue(self.driver.game.running())
        self.assertIsNone(self.driver.ticket)       # only match_start can start a fight

    def test_duplicate_is_reserved_before_asynchronous_lobby_call(self):
        self.driver.async_calls = True
        pending = []

        class Thread:
            def __init__(self, target, args, daemon):
                pending.append((target, args))

            def start(self):
                pass

        action = self.request()
        with mock.patch("t5lobby.match_driver.threading.Thread", Thread):
            self.driver._watch_ingame_ui()
            self.driver.ui.receive(action)
            self.driver._watch_ingame_ui()
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.client.calls, [])
        pending[0][0](*pending[0][1])
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])
        self.assertEqual(self.driver.ui.document["ack_seq"], 1)

    def test_failed_async_request_gets_rejected_ack_and_launcher_fallback(self):
        self.client.fail = True
        self.request()
        self.driver._watch_ingame_ui()
        self.driver._watch_ingame_ui()
        self.assertEqual(self.driver.ui.document["ack_status"], "rejected")
        self.assertEqual(self.driver.ui.document["kind"], "hidden")
        self.assertIn("ingame_ui_fallback", [n["kind"] for n in self.driver.poll()])

    def test_prompt_superseded_between_worker_receive_and_dispatch_is_rejected(self):
        self.request()
        self.driver.ui.offer("m2", "ready", ["ready"], 15)
        self.mark_ready()
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.driver.ui.document["ack_status"], "rejected")

    def test_decline_keeps_capable_process_and_next_private_room_stays_private(self):
        self.client.my_room = {"id": "r1", "size": 2, "private": "password"}
        self.request("decline")
        self.driver._watch_ingame_ui()
        self.driver._watch_ingame_ui()
        self.assertTrue(self.driver.game.running())
        self.assertEqual(self.driver.ui.document["kind"], "next")
        self.mark_ready()
        self.request("next", 2)
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("rematch", "m1", False, False), ("rematch",)])
        self.assertNotIn(("quick_match",), self.client.calls)

    def test_next_menu_replaces_the_finished_rematch_question(self):
        self.driver._ui_labels.update(title="Rematch?", body="Both players must confirm.",
                                      next="Next game", confirm="Rematch", cancel="No thanks")
        self.driver._offer_next_ui()
        document = self.driver.ui.document
        self.assertEqual(document["title"], "Next game")
        self.assertEqual(document["body"], "")
        self.assertEqual(document["next"], "Next game")
        self.assertEqual(document["allowed"], ["next"])
        self.driver.offer_ingame_ui({"t": "rematch", "match": "m1", "state": "declined"})
        self.assertEqual(self.driver.ui.document["title"], "Next game")
        self.assertEqual(self.driver.ui.document["body"], "")

    def test_casual_next_queues_only_after_previous_match_cleanup(self):
        self.driver._offer_next_ui()
        self.mark_ready()
        self.client.match = {"match": "old"}
        self.request("next")
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.driver.ui.document["ack_status"], "rejected")
        self.client.match = None
        self.request("next", 2)
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("quick_match",)])

    def test_community_next_only_returns_to_line(self):
        self.client.my_room = {"id": "r1", "size": 4}
        self.driver._offer_next_ui()
        self.mark_ready()
        self.request("next")
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("room_line", True)])

    def community(self, in_line=True):
        room = {"id": "r1", "size": 4, "rotation": "winner", "line": ["p1", "p2"] if in_line else ["p2"]}
        self.client.my_room = room
        event = {"t": "match_result", "match": "m2", "status": "confirmed", "rematch_window": 0,
                 "rematch_ui": {"v": 1, "kind": "community", "policy": "both_confirm", "timeout": 25,
                                "room_mode": "community", "room": "r1", "rotation": "winner",
                                "actions": ["sit_out"] if in_line else ["back_to_line"]}}
        self.driver.offer_ingame_ui(event, {"community_waiting": "Wait for your turn.",
                                            "community_sitting_out": "Sitting out.", "rotation": "Winner stays"})
        self.mark_ready()
        return event, room

    def test_community_result_exposes_line_actions_without_match_vote(self):
        self.community()
        self.assertEqual(self.driver.ui.document["kind"], "community")
        self.request("sit_out")
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("room_line", False)])
        self.assertEqual(self.driver.rematch_sent, set())

    def test_community_room_updates_preserve_ready_check(self):
        _event, room = self.community()
        self.driver.offer_ingame_ui({"t": "match_found", "match": "m3", "ready_check": True,
                                     "ready_timeout": 15})
        prompt = self.driver.ui.document["prompt"]
        self.driver.offer_ingame_ui({"t": "room", "room": room})
        self.assertEqual(self.driver.ui.document["kind"], "ready")
        self.assertEqual(self.driver.ui.document["prompt"], prompt)
        self.mark_ready()
        self.request("ready")
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("ready", True, "m3")])

    def test_community_away_and_leave_invalidate_old_line_action(self):
        _event, room = self.community(in_line=False)
        self.request("back_to_line")
        self.client.my_room = None
        self.driver.offer_ingame_ui({"t": "room", "room": None})
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.driver.ui.document["ack_status"], "rejected")
        self.assertEqual(self.driver.ui.document["kind"], "hidden")

    def test_community_rotation_body_and_countdown_follow_server_clock(self):
        _event, room = self.community()
        self.client.clock_offset = 20
        room["next"] = {"at": 1025, "players": ["p1", "p2"]}
        with mock.patch("t5lobby.match_driver.time.time", return_value=1000):
            self.driver.offer_ingame_ui({"t": "room", "room": room}, {"community_next": "Next in {seconds} s."})
        self.mark_ready()
        self.driver._watch_ingame_ui()
        self.assertIn("Winner stays", self.driver.ui.document["body"])
        self.assertIn("Next in 5 s.", self.driver.ui.document["body"])

    def test_negotiated_rule_overrides_legacy_scripted_auto_rematch_counter(self):
        self.driver.auto_rematch = 9
        self.driver.on_event(result())
        self.assertEqual(self.client.calls, [])

    def test_ready_answers_actual_ready_check(self):
        self.driver.offer_ingame_ui({"t": "match_found", "match": "m2", "ready_check": True,
                                     "ready_timeout": 15})
        self.mark_ready()
        self.request("ready")
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("ready", True, "m2")])

    def test_ranked_and_old_server_never_offer_game_votes(self):
        self.driver.ui.hide()
        self.assertFalse(self.driver.offer_ingame_ui(dict(result(), ranked=True)))
        old = result()
        del old["rematch_ui"]
        self.assertFalse(self.driver.offer_ingame_ui(old))
        self.assertEqual(self.driver.ui.document["kind"], "hidden")

    def test_automatic_rule_defers_own_vote_until_cancellable_countdown(self):
        self.driver._ui_event = None
        self.driver.offer_ingame_ui(result("auto_unless_declined"), {"auto": "Starts in {seconds}"})
        self.mark_ready()
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [])
        self.now += 4
        self.mark_ready()
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [])
        self.now += 1
        self.mark_ready()
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])

    def test_decline_and_capability_loss_cancel_automatic_vote(self):
        self.driver._ui_event = None
        self.driver.offer_ingame_ui(result("auto_unless_declined"))
        self.mark_ready()
        self.request("decline")
        self.driver._watch_ingame_ui()
        self.driver._watch_ingame_ui()
        self.now += 6
        self.mark_ready()
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("rematch", "m1", False, False)])
        self.driver.rematch_sent.clear()
        self.driver._ui_event = None
        self.driver.offer_ingame_ui(result("auto_unless_declined"))
        self.driver.ui.ready_at = None
        self.driver._watch_ingame_ui()
        self.now += 3
        self.driver._watch_ingame_ui()      # missing readiness has reached fallback timeout
        self.now += 3
        self.mark_ready()
        self.driver._watch_ingame_ui()
        self.assertEqual(self.client.calls, [("rematch", "m1", False, False)])

    def test_overlay_timeout_returns_to_launcher_without_voting(self):
        self.now += 21
        self.driver.ui.pump()
        self.driver._watch_ingame_ui()
        notes = self.driver.poll()
        self.assertIn("ingame_ui_fallback", [n["kind"] for n in notes])
        self.assertEqual(self.client.calls, [])

    def test_old_launcher_rematch_method_still_sends_vote(self):
        self.driver.rematch("m1", True)
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])

    def test_skip_fight_line_only_from_authoritative_server_true(self):
        self.assertEqual(fight_rules({"auto_skip_after_round": True}), " auto_skip_after_round=1")
        for value in (False, 1, "true", None):
            self.assertEqual(fight_rules({"auto_skip_after_round": value}), "")

    def test_old_game_cannot_silently_ignore_agreed_skip_rule(self):
        self.driver._auto_skip_supported = False
        self.driver._start({"match": "m2", "fight": {"auto_skip_after_round": True}})
        self.assertEqual(self.client.calls, [("leave_match", "m2")])


if __name__ == "__main__":
    unittest.main()
