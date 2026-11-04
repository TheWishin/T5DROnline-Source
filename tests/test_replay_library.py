"""Replay library preferences, combined filters and ordered viewer commands."""
import json
import os
import shutil
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import replay_library
import replays


class ReplayLibraryTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="replay-library-")
        self.addCleanup(shutil.rmtree, self.folder)
        self.entries = [self.entry("one.t5replay", 1, "rollback", 9, 33, "Rival"),
                        self.entry("one.t5replay", 2, "rollback", 33, 9, "Rival"),
                        self.entry("two.t5replay", 1, "lockstep", 0, 1, "Other")]

    def entry(self, filename, index, mode, p1, p2, opponent):
        match = {"p1": p1, "p2": p2, "names": ["Me", opponent]}
        return replays.Entry(os.path.join(self.folder, filename),
                             {"slot": 0, "mode": mode, "matches": [match] * index}, index)

    def test_favourite_is_per_match_and_survives_folder_move(self):
        lib = replay_library.Library(self.folder)
        lib.toggle(self.entries[1])
        self.assertFalse(lib.favourite(self.entries[0]))
        self.assertTrue(replay_library.Library(self.folder).favourite(self.entries[1]))
        moved = self.entry("one.t5replay", 2, "rollback", 33, 9, "Rival")
        moved.path = os.path.join("another", "one.t5replay")
        self.assertTrue(lib.favourite(moved))
        lib.toggle(self.entries[1])
        self.assertFalse(replay_library.Library(self.folder).favourite(moved))

    def test_filters_combine_case_insensitively_and_match_either_side(self):
        lib = replay_library.Library(self.folder)
        self.assertEqual(lib.filter(self.entries, fighter=" lIlI ", opponent="RIV", mode="rollback"), self.entries[:2])
        self.assertEqual(lib.filter(self.entries, fighter="Paul", mode="rollback"), [])
        lib.toggle(self.entries[1])
        self.assertEqual(lib.filter(self.entries, fighter="Jin", favourites=True), [self.entries[1]])
        self.assertEqual(lib.filter(self.entries, opponent="", mode="lockstep"), self.entries[2:])

    def test_bad_preferences_are_ignored(self):
        for data in ("not json", "[]", '{"favourites": null}'):
            with open(os.path.join(self.folder, ".replay-library.json"), "w") as f:
                f.write(data)
            self.assertEqual(replay_library.Library(self.folder).favourites, set())

    def test_channel_does_not_overwrite_unconsumed_commands(self):
        command, status = (os.path.join(self.folder, n) for n in ("command", "status"))
        channel = replay_library.ViewerChannel(command, status)
        channel.send("pause")
        channel.send("seek 100")
        with open(command) as f:
            self.assertEqual(f.read(), "pause\n")
        os.remove(command)
        channel.flush()
        with open(command) as f:
            self.assertEqual(f.read(), "seek 100\n")
        self.assertEqual(channel.pending, [])

    def test_status_is_bounded_and_rounds_are_validated(self):
        channel = replay_library.ViewerChannel(os.path.join(self.folder, "command"), os.path.join(self.folder, "status"))
        self.assertIsNone(channel.read())
        with open(channel.status, "w") as f:
            json.dump({"frame": 25, "start": 10, "end": 100, "rounds": [10, 50, "bad", 101, -1]}, f)
        self.assertEqual(channel.read()["rounds"], [10, 50])
        for status in ([], {"frame": "x"}, {"start": 100, "end": 10}, {"end": 1 << 40}):
            with open(channel.status, "w") as f:
                json.dump(status, f)
            self.assertIsNone(channel.read())


class ViewerUiTest(unittest.TestCase):
    def setUp(self):
        from test_replays import ReplaysTabTest
        self.base = ReplaysTabTest("test_german")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.app = self.base.launcher("en")
        self.tab = self.app.replays
        self.tab.refresh()

    def test_favourites_and_filters_keep_history_watch_available(self):
        tab = self.tab
        tab.tv.selection_set("0")
        entry = tab.selected()
        with open(entry.path, "rb") as f:
            original = f.read()
        tab.favourite()
        with open(entry.path, "rb") as f:
            self.assertEqual(f.read(), original)
        tab.favourites_filter.set(True)
        tab._filter()
        self.assertEqual(len(tab.entries), 1)
        self.assertEqual(tab.entries[0].index, entry.index)
        self.assertTrue(tab.tv.item("0", "values")[0].startswith("★ "))
        tab.opponent_filter.set("other")
        self.assertEqual(tab.entries, [])
        self.app.game_state = lambda: {"ok": False}
        tab.watch_entry(entry)
        self.assertEqual(len(tab.entries), 2)
        self.assertEqual(tab.selected().index, entry.index)

    def test_watch_commands_status_and_unverified_verdict(self):
        tab = self.tab
        class Game:
            active = True
            def running(self): return self.active
        game = Game()
        started = {}
        self.app.start_game = lambda env: (started.update(env), game)[1]
        self.app.game_state = lambda: {"ok": True}
        tab.tv.selection_set("0")
        tab.watch()
        self.assertEqual(started["T5_REPLAY_COMMAND"], tab.channel.command)
        self.assertEqual(started["T5_REPLAY_STATUS"], tab.channel.status)
        self.assertEqual(started["T5_REPLAY_CAPSULES"], "1")
        with open(tab.channel.status, "w") as f:
            json.dump({"frame": 32, "start": 25, "end": 45, "paused": True, "speed": 0.5,
                       "verified": False, "rounds": [25, 35]}, f)
        tab._viewer_poll()
        self.assertEqual(tab.pause_btn.cget("text"), "Resume")
        self.assertIn("Unverified", tab.position_var.get())
        tab.seek_relative(-600)
        with open(tab.channel.command) as f:
            self.assertEqual(f.read(), "seek 25\n")
        os.remove(tab.channel.command)
        tab.round_box.current(1)
        tab.seek_round()
        with open(tab.channel.command) as f:
            self.assertEqual(f.read(), "seek 35\n")
        os.remove(tab.channel.command)
        tab.stop()
        with open(tab.channel.command) as f:
            self.assertEqual(f.read(), "quit\n")
        with open(started["T5_REPLAY_RESULT"], "w") as f:
            json.dump({"identical": False, "unverified_from": 32}, f)
        game.active = False
        tab._poll()
        self.assertIn("unverified from frame 32", tab.verdict.get())

    def test_refresh_keeps_selected_match_when_rows_reorder(self):
        from unittest import mock
        tab = self.tab
        tab.tv.selection_set("0")
        chosen = tab.selected()
        with mock.patch.object(replays, "list_replays", return_value=list(reversed(tab.entries))):
            tab.refresh()
        self.assertEqual((tab.selected().path, tab.selected().index), (chosen.path, chosen.index))

    def test_controls_remain_reachable_in_short_window(self):
        self.app.geometry("1000x680")
        self.app.nb.select(self.app.tabs["replays"])
        self.app.update_idletasks()
        scroll = self.app.replays_scroll
        scroll.refresh()
        scroll.see(self.tab.favourite_btn)
        scroll.scroll_to(10 ** 6)
        self.app.update_idletasks()
        self.assertGreaterEqual(scroll.canvas.yview()[1], 0.999)


if __name__ == "__main__":
    unittest.main()
