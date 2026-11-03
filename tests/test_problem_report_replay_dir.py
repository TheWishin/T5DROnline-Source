"""Chosen replay folders in reports; synthetic files only, no game or network."""
import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
import zipfile
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import problem_report as report


class ReplayFolderReports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix="test-report-folder-")
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.out = os.path.join(self.root, "native")
        self.chosen = os.path.join(self.root, "Private collection \u65e5\u672c [replays]")
        os.makedirs(os.path.join(self.out, "replays"))
        os.makedirs(self.chosen)

    def put(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        return path

    def test_report_selects_newest_from_chosen_folder_only(self):
        old_default = self.put(os.path.join(self.out, "replays", "default.t5replay"), "synthetic")
        older = self.put(os.path.join(self.chosen, "older.t5replay"), "synthetic")
        newest = self.put(os.path.join(self.chosen, "newest.t5replay"), "synthetic")
        os.utime(older, (10, 10))
        os.utime(newest, (20, 20))
        os.utime(old_default, (30, 30))
        ctx = report.Context(self.out, replay_dir=self.chosen)
        items = [i for g in report.discover(ctx) if g.key == "replay" for i in g.items]
        self.assertEqual([i.path for i in items], [newest])
        self.assertEqual(items[0].arcname, "replay/newest.t5replay")

    def test_chosen_and_unavailable_saved_paths_are_private_in_report_text(self):
        unavailable = "D:\\Private person\\Replay \u65e5\u672c folder"
        self.put(os.path.join(self.root, "launcher.json"), json.dumps({"replay_dir": unavailable}))
        ctx = report.Context(self.out, root=self.root, replay_dir=self.chosen, user_names=[], pc_names=[])
        text = "\n".join((self.chosen, self.chosen.replace("\\", "/"),
                           json.dumps({"T5_REPLAY_DIR": unavailable}), unavailable))
        groups = [report.Group("fixture", "Synthetic text", [report.Item("fixture.txt", text=text)])]
        result = report.build(ctx, os.path.join(self.root, "report"), groups=groups)
        with zipfile.ZipFile(result.path) as z:
            clean = z.read("fixture.txt").decode("utf-8")
        self.assertEqual(clean, "\n".join(("<replays>", "<replays>",
                                          '{"T5_REPLAY_DIR": "<replays>"}', "<replays>")))

    def test_cli_resolves_saved_folder_and_missing_folder_falls_back(self):
        for choice, expected in ((self.chosen, self.chosen),
                                 (os.path.join(self.root, "missing"), os.path.join(self.out, "replays"))):
            with self.subTest(choice=choice):
                self.put(os.path.join(self.root, "launcher.json"), json.dumps({"replay_dir": choice}))
                captured = []

                def fake_build(ctx, *args, **kwargs):
                    captured.append(ctx.replay_dir)
                    return types.SimpleNamespace(path="synthetic.zip", zip_size=0, members=[], skipped=[])

                with mock.patch.object(report, "build", side_effect=fake_build), \
                        mock.patch.object(report, "build_info_for", return_value={}), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(report.main(["--out", self.out, "--root", self.root]), 0)
                self.assertEqual(captured, [expected])

    def test_relative_choice_does_not_scrub_every_dot(self):
        self.put(os.path.join(self.root, "launcher.json"), json.dumps({"replay_dir": "."}))
        ctx = report.Context(self.out, root=self.root)
        sc = report.Scrubber(replay_paths=ctx.replay_paths(), user_names=[], pc_names=[])
        self.assertEqual(sc.text("synthetic.t5replay: 1.0"), "synthetic.t5replay: 1.0")

    def test_unavailable_relative_choice_is_scrubbed_from_settings_folder(self):
        chosen = "private missing collection"
        self.put(os.path.join(self.root, "launcher.json"), json.dumps({"replay_dir": chosen}))
        ctx = report.Context(self.out, root=self.root)
        with mock.patch.object(report.os, "getcwd", return_value=self.out):
            sc = report.Scrubber(replay_paths=ctx.replay_paths(), user_names=[], pc_names=[])
        self.assertEqual(sc.text(os.path.join(self.root, chosen)), "<replays>")


if __name__ == "__main__":
    unittest.main()
