"""Automatic watch dismissal refreshes the tab without Tk, processes or sockets."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import util  # noqa: F401 -- sets the repository's lobby import path
from t5lobby.tk_spectate import Spectating


def controller():
    client = NS(me={"id": "me", "status": "idle"}, match=None, my_room=None,
                cancel_watch=Mock())
    tab = NS(client=client, driver=None, app=NS(settings={"auto_spectate": True}, game=None))
    spec = Spectating(tab)
    spec._auto = Mock()
    spec._auto.due.return_value = None
    visible = []
    tab._set_actions = Mock(side_effect=lambda: visible.append(spec.active))
    return tab, spec, visible


class AutomaticWatchDismissalTest(unittest.TestCase):
    def test_finished_process_refreshes_after_automatic_card_is_removed(self):
        tab, spec, visible = controller()
        game = NS(running=lambda: False)
        spec.w = {"state": "playing", "automatic": True, "game": game,
                  "client": tab.client, "end": None, "result": "not-opened.json"}
        with patch("builtins.open", side_effect=OSError):
            spec.poll()
        self.assertEqual(spec.w["state"], "over")
        tab.client.cancel_watch.assert_called_once_with()
        tab._set_actions.assert_not_called()

        spec.poll()

        self.assertIsNone(spec.w)
        tab._set_actions.assert_called_once_with()
        self.assertEqual(visible, [False])

    def test_already_ended_automatic_watch_refreshes_without_another_event(self):
        for reason in ("over", "not_allowed", "stopped"):
            with self.subTest(reason=reason):
                tab, spec, visible = controller()
                spec.w = {"state": "over", "automatic": True, "game": None,
                          "client": tab.client, "end": reason}

                spec.poll()

                self.assertIsNone(spec.w)
                tab._set_actions.assert_called_once_with()
                self.assertEqual(visible, [False])

    def test_manual_ended_card_remains_available_to_close(self):
        tab, spec, visible = controller()
        card = spec.w = {"state": "over", "automatic": False, "game": None,
                         "client": tab.client, "end": "over"}

        spec.poll()

        self.assertIs(spec.w, card)
        tab._set_actions.assert_not_called()
        self.assertEqual(visible, [])


if __name__ == "__main__":
    unittest.main()
