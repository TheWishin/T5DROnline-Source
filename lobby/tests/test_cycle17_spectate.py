"""Queueing releases automatic watches without Tk, processes, files or sockets."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

import util  # noqa: F401 -- sets the repository's lobby import path
from t5lobby.tk_spectate import Spectating


def controller():
    client = NS(me={"id": "me", "status": "idle"}, match=None, my_room=None,
                has_spectate=lambda: True, watch=Mock(), cancel_watch=Mock())
    tab = NS(client=client, driver=None, call=Mock(), status=Mock(), _set_actions=Mock(),
             app=NS(settings={"auto_spectate": True}, game=None, start_game=Mock()))
    spec = Spectating(tab)
    spec._auto = Mock()
    spec._auto.due.return_value = None
    return tab, spec


class QueuedAutomaticWatchTest(unittest.TestCase):
    def test_queue_closes_each_active_automatic_phase_and_refreshes_after_dismissal(self):
        for state in ("waiting", "starting", "playing"):
            with self.subTest(state=state):
                tab, spec = controller()
                game = None if state == "waiting" else NS(running=lambda: True, stop=Mock())
                spec.w = {"state": state, "automatic": True, "game": game,
                          "client": tab.client, "end": None, "t_status": float("inf")}
                tab.app.game = game
                tab.client.me["status"] = "queue"
                visible = []
                tab._set_actions.side_effect = lambda: visible.append(spec.active)

                spec.poll()

                self.assertIsNone(spec.w)
                tab.client.cancel_watch.assert_called_once_with()
                if game is not None:
                    game.stop.assert_called_once_with()
                spec._auto.pause.assert_called_once_with()
                tab._set_actions.assert_called_once_with()
                self.assertEqual(visible, [False])

    def test_queue_cancels_pending_automatic_watch_before_its_reply(self):
        tab, spec = controller()
        spec._watch(room="room", automatic=True)
        done = tab.call.call_args.kwargs["then"]
        tab.client.me["status"] = "queue"

        spec.poll()

        self.assertIsNone(spec._pending)
        tab.client.cancel_watch.assert_called_once_with()
        spec._auto.pause.assert_called_once_with()
        done({"stream": "late"})
        self.assertIsNone(spec.w)
        tab.client.cancel_watch.assert_called_once_with()
        tab.app.start_game.assert_not_called()

    def test_queue_does_not_change_a_manual_waiting_watch(self):
        tab, spec = controller()
        card = spec.w = {"state": "waiting", "automatic": False, "game": None,
                         "client": tab.client, "end": None}
        tab.client.me["status"] = "queue"

        spec.poll()

        self.assertIs(spec.w, card)
        self.assertEqual(card["state"], "waiting")
        tab.client.cancel_watch.assert_not_called()
        tab._set_actions.assert_not_called()

    def test_queue_does_not_cancel_a_pending_manual_watch(self):
        tab, spec = controller()
        spec._watch(room="room")
        pending = spec._pending
        tab.client.me["status"] = "queue"

        spec.poll()

        self.assertIs(spec._pending, pending)
        tab.client.cancel_watch.assert_not_called()
        spec._auto.pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
