"""Spectator process ownership without a game, Tk window, worker thread or server."""
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import util  # noqa: F401 (sets sys.path)
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
    def __init__(self):
        self.me = {"id": "me", "status": "idle"}
        self.match = None
        self.ticket = None
        self.my_room = None
        self.spec_watch = {"stream": "stream", "path": "not-opened.t5live"}
        self.spec_generation = 0
        self.cancels = 0

    def has_spectate(self):
        return True

    def watch(self, *args):
        raise AssertionError("test must never execute a client call")

    def cancel_watch(self):
        self.cancels += 1
        self.spec_generation += 1

    def set_spectate_prefs(self, *args):
        pass


class Tab:
    def __init__(self):
        self.client = Client()
        self.driver = None
        self.match = None
        self.calls = []
        self.boots = []
        self.app = NS(game=None, settings={}, start_game=self.start_game)

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


def watching(tab, state="playing", automatic=False):
    game = Game()
    return {"stream": "stream", "state": state, "game": game, "client": tab.client,
            "automatic": automatic, "end": None, "result": "not-opened.json"}


class SpectateLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tab = Tab()
        self.spec = Spectating(self.tab)

    def begin(self, **kw):
        self.spec._watch(room="room", **kw)
        return self.tab.calls[-1][2]["then"]

    def test_late_watch_reply_after_match_does_not_boot_or_stop_own_game(self):
        done = self.begin()
        self.spec.before_event({"t": "match_found", "ready_check": True})
        own = Game()
        self.tab.driver = NS(ticket=object(), game=own, game_running=own.running)
        self.tab.app.game = own
        done({"stream": "stream"})
        self.assertEqual(self.tab.boots, [])
        self.assertEqual(own.stops, 0)
        self.assertIsNone(self.spec.w)
        self.assertEqual(self.tab.client.cancels, 1)

    def test_stop_invalidates_pending_reply_and_duplicate_watch(self):
        done = self.begin()
        self.spec._watch(room="other")
        self.assertEqual(len(self.tab.calls), 1)
        self.spec.stop()
        done({"stream": "stream"})
        self.assertIsNone(self.spec.w)
        self.assertEqual(self.tab.boots, [])

    def test_old_client_reply_is_ignored(self):
        done = self.begin()
        self.tab.client = Client()
        done({"stream": "stream"})
        self.assertIsNone(self.spec.w)
        self.assertEqual(self.tab.boots, [])

    def test_client_match_arriving_before_ui_callback_blocks_boot(self):
        done = self.begin()
        self.tab.client.match = {"state": "ready"}
        done({"stream": "stream"})
        self.assertEqual(self.tab.boots, [])
        self.assertEqual(self.tab.client.cancels, 1)

    def test_parallel_table_selector_and_generation_reach_client_worker(self):
        self.spec._watch(room="room", table=2)
        fn, args, _ = self.tab.calls[-1]
        self.assertEqual(fn, self.tab.client.watch)
        self.assertEqual(args, (None, "room", None, None, 2, self.tab.client.spec_generation))

    def test_parallel_table_countdown_before_watch_reply_prevents_boot(self):
        done = self.begin()
        self.tab.client.my_room = {"mode": "tables", "playing": [], "next": None,
                                   "tables": [{"id": 2, "next": {"players": ["me", "other"]}}]}
        done({"stream": "stream"})
        self.assertEqual(self.tab.boots, [])
        self.assertEqual(self.tab.client.cancels, 1)

    def test_preemption_in_every_visible_phase_and_attention_event(self):
        for state in ("waiting", "starting", "playing"):
            for kind in ("match_found", "match_reveal", "match_start", "challenged", "invited", "tour_call",
                         "disconnected", "reconnecting", "kicked"):
                with self.subTest(state=state, kind=kind):
                    tab = Tab()
                    spec = Spectating(tab)
                    w = spec.w = watching(tab, state)
                    ev = {"t": kind}
                    spec.before_event(ev)
                    spec.on_event(ev)        # the tab also calls it directly; cleanup is idempotent
                    self.assertEqual(w["game"].stops, 1)
                    self.assertEqual(tab.client.cancels, 1)
                    self.assertEqual(w["state"], "over")

    def test_ready_data_cannot_claim_an_existing_game(self):
        w = self.spec.w = watching(self.tab, "waiting")
        w["game"] = None
        own = self.tab.app.game = Game()
        self.spec.on_event({"t": "spec_ready", "stream": "stream", "path": "unused"})
        self.assertEqual(self.tab.boots, [])
        self.assertEqual(own.stops, 0)
        self.assertEqual(w["state"], "over")

    def test_watch_does_not_evict_even_an_idle_persistent_game(self):
        game = self.tab.app.game = Game()
        self.tab.driver = NS(ticket=None, game=game, game_running=game.running)
        self.spec._watch(room="room", automatic=True)
        self.assertEqual(self.tab.calls, [])
        self.assertEqual(game.stops, 0)

    def test_stop_over_card_still_closes_its_owned_process(self):
        w = self.spec.w = watching(self.tab, "over")
        self.spec.stop()
        self.assertEqual(w["game"].stops, 1)
        self.assertEqual(self.tab.client.cancels, 1)
        self.assertIsNone(self.spec.w)

    def test_stale_reference_never_stops_driver_process(self):
        w = self.spec.w = watching(self.tab)
        self.tab.driver = NS(ticket=object(), game=w["game"], game_running=w["game"].running)
        self.spec.stop()
        self.assertEqual(w["game"].stops, 0)

    def test_privacy_stops_now_but_normal_end_can_drain_received_match(self):
        w = self.spec.w = watching(self.tab)
        self.spec.on_event({"t": "spec_end", "stream": "stream", "reason": "over", "ready": True})
        self.assertEqual(w["game"].stops, 0)
        self.spec.on_event({"t": "spec_end", "stream": "stream", "reason": "not_allowed", "ready": True})
        self.assertEqual(w["game"].stops, 1)
        self.assertEqual(w["state"], "over")

    def test_window_close_releases_watch_and_marks_card_over(self):
        w = self.spec.w = watching(self.tab)
        w["game"].live = False
        with mock.patch("builtins.open", side_effect=OSError):
            self.spec.poll()
        self.assertEqual(w["state"], "over")
        self.assertEqual(w["end"], "stopped")
        self.assertEqual(self.tab.client.cancels, 1)

    def test_disabling_setting_cancels_pending_automatic_watch(self):
        self.tab.app.settings["auto_spectate"] = True
        done = self.begin(automatic=True)
        self.tab.app.settings["auto_spectate"] = False
        self.spec.poll()
        done({"stream": "stream"})
        self.assertIsNone(self.spec.w)
        self.assertEqual(self.tab.boots, [])
        self.assertEqual(self.tab.client.cancels, 1)

    def test_last_completed_client_ticket_does_not_block_later_watch(self):
        self.tab.client.ticket = object()       # LobbyClient keeps its last ticket after match_result
        self.spec._watch(room="room")
        self.assertEqual(len(self.tab.calls), 1)

    def test_stream_end_before_worker_callback_cannot_leave_waiting_card(self):
        for reason in ("over", "not_allowed", "bumped", "your_match", "damaged"):
            with self.subTest(reason=reason):
                tab = Tab()
                spec = Spectating(tab)
                spec._watch(room="room")
                done = tab.calls[-1][2]["then"]
                spec.on_event({"t": "spec_ready", "stream": "stream", "path": "unused"})
                tab.client.spec_watch = None
                spec.on_event({"t": "spec_end", "stream": "stream", "reason": reason, "ready": True})
                done({"stream": "stream"})
                self.assertEqual(tab.boots, [])
                self.assertEqual(spec.w["state"], "over")
                self.assertEqual(spec.w["end"], reason)

    def test_room_turn_and_pending_outgoing_challenge_preempt_in_poll(self):
        for condition in ("turn", "table_turn", "outgoing", "incoming", "ready"):
            with self.subTest(condition=condition):
                tab = Tab()
                spec = Spectating(tab)
                w = spec.w = watching(tab)
                if condition == "turn":
                    tab.client.my_room = {"next": {"players": ["me", "other"]}}
                elif condition == "table_turn":
                    tab.client.my_room = {"mode": "tables", "next": None,
                                          "tables": [{"next": {"players": ["me", "other"]}}]}
                elif condition == "ready":
                    tab.ready_sent = True
                else:
                    tab.chal = NS(**{"out" if condition == "outgoing" else "incoming": {"c": {}}})
                spec.poll()
                self.assertEqual(w["game"].stops, 1)
                self.assertEqual(w["state"], "over")
