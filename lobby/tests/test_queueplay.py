"""Queue-to-Practice and challenger state machines: fake game, clock and lobby, no network."""
import json
import os
import tempfile
import types
import unittest
from unittest import mock

import util  # noqa: F401
from t5lobby import match_driver, tk_tab, tk_views
from t5lobby.ingame_ui import IngameUI
from test_driver_persistent import FakeClient, FakeGame, start_event


class QueueClient(FakeClient):
    def ready(self, accept, mid):
        self.calls.append(("ready", accept, mid))


class QueueplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.now = 100.0
        patch = mock.patch.object(match_driver.time, "monotonic", side_effect=lambda: self.now)
        patch.start()
        self.addCleanup(patch.stop)
        self.launched = []
        self.client = QueueClient()
        self.driver = match_driver.MatchDriver(self.client, self.launch, self.directory.name,
                                               mode="persistent", queueplay=True)
        real_ui = IngameUI
        patch = mock.patch.object(match_driver, "IngameUI", side_effect=lambda directory, session:
                                  real_ui(directory, session, worker=False, clock=lambda: self.now))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.cleanup_game)
        self.ready = mock.Mock()

    def cleanup_game(self):
        # A fake game cannot acknowledge quit; avoid stop_game's deliberate real-time grace period.
        if self.driver.ui:
            self.driver.ui.close()
        for game in self.launched:
            game.stop()

    def launch(self, env):
        game = FakeGame(env)
        self.launched.append(game)
        return game

    def command(self):
        with open(os.path.join(self.directory.name, "ctl", "cmd.json")) as stream:
            return json.load(stream)

    def state(self, state="practice", seq=None):
        with open(os.path.join(self.directory.name, "ctl", "state.json"), "w") as stream:
            json.dump({"ctl": 1, "seq": seq or self.command()["seq"], "state": state}, stream)

    def practice(self):
        self.driver.start_queueplay("law", self.ready)
        self.state()
        self.driver.poll()

    def found(self, **extra):
        event = dict(t="match_found", match="m1", blind=True, ready_check=True, ready_timeout=15)
        event.update(extra)
        self.driver.on_event(event)
        ui = self.driver.ui
        ui.ready_at = self.now
        ui.ready_revision = ui.document["rev"]

    def press(self, name="accept", sequence=1, **extra):
        ui = self.driver.ui
        value = dict(ui._base(), seq=sequence, match=ui.document["match"],
                     prompt=ui.document["prompt"], action=name)
        value.update(extra)
        ui.receive(value)
        self.driver.poll()
        return value

    def test_search_waits_for_actual_practice_not_command_ack(self):
        self.driver.start_queueplay("law", self.ready)
        self.assertEqual(self.command()["cmd"], "practice")
        self.assertTrue(self.command()["env"]["T5_FIGHT"].startswith("1,"))
        self.assertNotIn("T5_NET_MODE", self.launched[0].env)
        self.assertIn("T5_UI_GENERATION", self.launched[0].env)
        self.state("loading")
        self.driver.poll()
        self.ready.assert_not_called()
        self.state("practice", seq=0)
        # Explicitly stale command acknowledgement must not join a queue.
        with open(os.path.join(self.directory.name, "ctl", "state.json"), "w") as stream:
            json.dump({"seq": 0, "state": "practice"}, stream)
        self.driver.poll()
        self.ready.assert_not_called()
        self.state()
        self.driver.poll()
        self.driver.poll()
        self.ready.assert_called_once_with()

    def test_accept_reuses_same_game_then_sends_normal_fight(self):
        self.practice()
        self.found()
        ui = self.driver.ui
        self.assertEqual(ui.document["kind"], "challenger")
        self.assertEqual(ui.snapshot()["countdown_ms"], 15000)
        self.assertEqual(self.command()["cmd"], "practice")
        self.press()
        self.assertEqual(self.client.calls, [("ready", True, "m1")])
        self.assertFalse(self.driver.challenger_ready(True))
        self.driver.on_event(start_event())
        self.assertEqual(len(self.launched), 1)
        self.assertEqual((self.command()["cmd"], self.command()["match"]), ("fight", "m1"))
        self.assertNotIn("T5_QUEUEPLAY", self.command()["env"])
        self.assertEqual(ui.document["kind"], "hidden")

    def test_new_search_cancels_previous_match_return_without_hiding_practice(self):
        self.practice()
        self.driver.on_event({"t": "match_result", "match": "previous", "status": "confirmed"})
        self.assertTrue(self.driver.returning_to_lobby)
        ready = mock.Mock()
        self.driver.start_queueplay("jin", ready)
        self.assertFalse(self.driver.returning_to_lobby)
        self.assertEqual(len(self.launched), 1)
        self.assertEqual(self.driver.ui.document["kind"], "hidden")
        self.state()
        self.now += match_driver.RETURN_SECONDS + 1
        notes = self.driver.poll()
        ready.assert_called_once_with()
        self.assertNotIn("return_to_lobby", [note["kind"] for note in notes])
        self.assertEqual(self.command()["cmd"], "practice")

    def test_disconnect_clears_challenger_before_showing_return_notice(self):
        self.practice()
        self.found()
        self.driver.on_event({"t": "disconnected"})
        self.assertIsNone(self.driver._challenger)
        self.assertIsNone(self.driver._practice_wait)
        self.assertTrue(self.driver.returning_to_lobby)
        self.assertEqual(self.driver.ui.document["kind"], "notice")
        self.assertFalse(self.driver.challenger_ready(True))
        self.assertEqual(self.client.calls, [])

    def test_decline_cancel_and_reoffer_keep_practice(self):
        self.practice()
        self.found()
        old = self.press("decline")
        self.assertEqual(self.client.calls, [("ready", False, "m1")])
        self.driver.on_event({"t": "match_cancel", "match": "m1"})
        self.found(match="m2")
        self.driver.ui.receive(old)
        self.driver.poll()
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.command()["cmd"], "practice")
        self.assertTrue(self.launched[0].running())

    def test_timeout_never_accepts_and_stale_pad_cannot_vote(self):
        self.practice()
        self.found(ready_timeout=40)
        self.assertEqual(self.driver.ui.snapshot()["countdown_ms"], 15000)
        self.now += 15
        self.press()
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.driver.ui.document["kind"], "hidden")

    def test_overlay_failure_has_launcher_fallback(self):
        self.practice()
        self.found()
        self.driver.ui.ready_at = None
        self.assertTrue(self.driver.ingame_ui_pending)
        self.now += 3.1
        notes = self.driver.poll()
        self.assertIn("ingame_ui_fallback", [n["kind"] for n in notes])
        self.assertTrue(self.driver.challenger_ready(False))
        self.assertEqual(self.client.calls, [("ready", False, "m1")])

    def test_rejected_pad_vote_is_acknowledged_and_can_retry(self):
        self.practice()
        self.found()
        self.client.ready = mock.Mock(side_effect=ValueError("test rejection"))
        self.press()
        self.driver.poll()  # asynchronous completion queue, also used by synchronous tests
        self.assertEqual(self.driver.ui.document["ack_status"], "rejected")
        self.assertFalse(self.driver._challenger["sent"])
        self.assertEqual(self.driver.ui.document["allowed"], ["accept", "decline"])
        self.client.ready.side_effect = None
        self.press(sequence=2)
        self.driver.poll()
        self.assertEqual(self.driver.ui.document["ack_status"], "ok")

    def test_rejected_launcher_votes_release_reservation_and_restore_fallback(self):
        self.practice()
        for accept in (True, False):
            with self.subTest(accept=accept):
                self.found()
                self.client.ready = mock.Mock(side_effect=ValueError("test rejection"))
                self.assertTrue(self.driver.challenger_ready(accept))
                self.assertFalse(self.driver.challenger_ready(accept))
                notes = self.driver.poll()
                self.assertFalse(self.driver._challenger["sent"])
                self.assertEqual(self.driver.ui.document["allowed"], ["accept", "decline"])
                self.assertIn("challenger_vote_rejected", [n["kind"] for n in notes])
                self.assertEqual(self.driver.ui.document["ack_seq"], 0)

    def test_late_vote_failure_cannot_reset_a_new_prompt(self):
        self.practice()
        self.found()
        self.client.ready = mock.Mock(side_effect=ValueError("test rejection"))
        self.driver.challenger_ready(True)
        self.found(match="m2")
        notes = self.driver.poll()
        self.assertNotIn("challenger_vote_rejected", [n["kind"] for n in notes])
        self.assertEqual(self.driver.ui.document["match"], "m2")

    def test_boot_failure_timeout_and_cancel_never_search(self):
        for reason in ("timeout", "crash", "cancel", "disconnect"):
            with self.subTest(reason=reason):
                self.driver.start_queueplay("jin", self.ready)
                if reason == "timeout":
                    self.now += 91
                elif reason == "crash":
                    self.launched[-1].stop()
                elif reason == "cancel":
                    self.driver.cancel_queueplay_search()
                    self.state()
                else:
                    self.driver.on_event({"t": "disconnected"})
                    self.state()
                self.driver.poll()
                self.ready.assert_not_called()

    def test_old_game_uses_existing_search_flow(self):
        self.driver.queueplay = False
        self.driver.start_queueplay("jin", self.ready)
        self.ready.assert_called_once_with()
        self.assertFalse(self.launched)

    def test_existing_game_without_ui_channel_is_replaced_before_practice(self):
        game = FakeGame({})
        game.running = mock.Mock(side_effect=[True, False, False])
        self.driver.game = game
        self.driver.start_queueplay("jin", self.ready)
        self.assertEqual(len(self.launched), 1)
        self.assertIn("T5_UI_GENERATION", self.launched[0].env)
        self.assertEqual(self.command()["cmd"], "practice")


class LauncherQueueTests(unittest.TestCase):
    def test_preparing_practice_shows_search_card_with_stop_button(self):
        view = object.__new__(tk_views.OnlineView)
        view._bar_on = False
        view.tab = types.SimpleNamespace(client=types.SimpleNamespace(me={"status": "idle"}),
                                         driver=types.SimpleNamespace(ticket=None, _practice_wait=(1, 190, None)),
                                         spec=types.SimpleNamespace(active=False))
        view.result_info, view.result_dismissed = None, False
        self.assertEqual(view._pick_stage(), "search")
        view.tab.driver._practice_wait = None
        self.assertEqual(view._pick_stage(), "play")

    def test_rejected_same_match_vote_restores_buttons_and_stale_notes_do_not(self):
        tab = object.__new__(tk_tab.OnlineTab)
        tab.driver = None
        tab.match = {"match": "m1"}
        tab.ready_sent = True
        tab.ready_deadline = 120
        tab.view = mock.Mock()
        tab._notify_driver = mock.Mock()
        tab.show_bar = mock.Mock()
        tab._ready_text = lambda: "Opponent found"
        tab._ready = mock.Mock()
        with mock.patch.object(tk_tab.time, "monotonic", return_value=100):
            tab.on_driver({"kind": "challenger_vote_rejected", "match": "old"})
            tab.show_bar.assert_not_called()
            tab.on_driver({"kind": "challenger_vote_rejected", "match": "m1"})
            self.assertFalse(tab.ready_sent)
            buttons = tab.show_bar.call_args.args[1]
            self.assertEqual(len(buttons), 2)
            buttons[0][1]()
            buttons[1][1]()
            self.assertEqual(tab._ready.call_args_list, [mock.call(True), mock.call(False)])
            tab.show_bar.reset_mock()
            tab.ready_deadline = None   # match_start arrived before a queued rejection note
            tab.on_driver({"kind": "challenger_vote_rejected", "match": "m1"})
            tab.show_bar.assert_not_called()

    def test_both_search_modes_join_only_after_practice_ready(self):
        for mode in ("quick", "ranked"):
            with self.subTest(mode=mode):
                tab = object.__new__(tk_tab.OnlineTab)
                tab.client = mock.Mock()
                tab.client.has_feature.return_value = False
                tab.driver = mock.Mock()
                tab.cfg = {}
                tab._closed = False
                tab.strict_var = mock.Mock(get=lambda: False)
                for name in ("_save_cfg", "_queue_status", "_set_actions", "call"):
                    setattr(tab, name, mock.Mock())
                tab._char_key = lambda: "jin"
                tab._game_elsewhere = lambda: False
                tab.do_queue(mode)
                tab.call.assert_not_called()
                args = tab.driver.start_queueplay.call_args.args
                self.assertEqual(args[0], "jin")
                args[1]()
                tab.call.assert_called_once()
                tab.call.call_args.args[0]()
                fn = tab.client.ranked_match if mode == "ranked" else tab.client.quick_match
                fn.assert_called_once_with("jin", options=None)
                tab.client = None
                args[1]()
                self.assertEqual(tab.call.call_count, 1)

    def test_stop_search_cancels_pending_boot_callback(self):
        tab = object.__new__(tk_tab.OnlineTab)
        tab.driver, tab.client, tab.call, tab._set_actions = mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock()
        tab.do_cancel_queue()
        tab.driver.cancel_queueplay_search.assert_called_once_with()
        tab.call.assert_called_once_with(tab.client.cancel_queue)


if __name__ == "__main__":
    unittest.main()
