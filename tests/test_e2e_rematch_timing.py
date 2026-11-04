"""A rematch's input lock starts at its own ready prompt, after the challenger."""
import os
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from helpers import ROOT
sys.path.append(os.path.join(ROOT, "tools", "e2e"))
import e2e_ingame as ingame


class RematchPromptTiming(unittest.TestCase):
    def player(self, name):
        notes = []
        ui = SimpleNamespace(document={})
        ui.snapshot = lambda: dict(ui.document)
        def note(kind, **details):
            notes.append((ingame.time.time(), dict(details, kind=kind)))
        driver = SimpleNamespace(ui=ui, note=note)
        return SimpleNamespace(name=name, notes=notes, tab=SimpleNamespace(driver=driver))

    def ready(self, player, kind, prompt, timestamp):
        player.tab.driver.ui.document = dict(kind=kind, prompt=prompt,
            allowed=["accept", "decline"], countdown_ms=9500, total_ms=10000,
            opponent="Other is deciding", opp_state="deciding")
        with mock.patch.object(ingame.time, "time", return_value=timestamp):
            player.tab.driver.note("ingame_ui_ready", match="m1")

    def context(self, on_wait=None):
        case = self
        def wait(predicate, _timeout, _description):
            if predicate():
                return True
            if on_wait:
                on_wait()
            return predicate()
        def check(_name, condition, *_details):
            case.assertTrue(condition, _name)
        return SimpleNamespace(wait=wait, check=check)

    def test_challenger_ready_cannot_shorten_the_rematch_input_lock(self):
        players = [self.player("A"), self.player("B")]
        ingame._instrument(players)
        for p in players:
            self.ready(p, "challenger", "challenger:m1", 10.0)
        self.ready(players[0], "rematch", "rematch:m1", 100.0)
        self.ready(players[1], "rematch", "rematch:m1", 100.2)
        with mock.patch.object(ingame, "_shown_in_game_log", return_value=True):
            shown = ingame.question(self.context(), players, "m1")
        self.assertEqual(shown, [100.0, 100.2])
        with mock.patch.object(ingame.time, "time", return_value=100.3), \
             mock.patch.object(ingame.time, "sleep") as sleep, \
             mock.patch.object(ingame, "_PickPad"):
            ingame.press(players[0], "CROSS", shown=shown[0])
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], .7)

    def test_waits_for_the_current_rematch_prompt_ready(self):
        players = [self.player("A"), self.player("B")]
        ingame._instrument(players)
        for p in players:
            self.ready(p, "rematch", "old:m1", 10.0)
            p.tab.driver.ui.document["prompt"] = "current:m1"
        published = []
        def publish():
            published.append(True)
            for p in players:
                self.ready(p, "rematch", "current:m1", 100.0)
        with mock.patch.object(ingame, "_shown_in_game_log", return_value=True):
            shown = ingame.question(self.context(publish), players, "m1")
        self.assertEqual(published, [True])
        self.assertEqual(shown, [100.0, 100.0])


if __name__ == "__main__":
    unittest.main()
