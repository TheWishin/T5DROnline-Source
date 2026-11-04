"""The local viewer probe's isolation, verdict requirements and scenario plan.

No game or network is started by these tests.
"""
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from helpers import ROOT, load_tool

probe_tool = load_tool("replay_viewer_check")


def status(**values):
    return {"frame": 150, "start": 0, "end": 5000, "paused": False, "speed": 1,
            "control": 0, "verified": True, "seeking": False, "seekable": True,
            "rounds": [0], "unverified_from": None, **values}


class ProbePolicyTests(unittest.TestCase):
    def test_status_validation_and_checkpoint_readiness(self):
        self.assertEqual(probe_tool.validate_status(status())["frame"], 150)
        self.assertTrue(probe_tool.seekable(status()))
        self.assertFalse(probe_tool.seekable(status(seekable=False)))
        self.assertFalse(probe_tool.seekable(status(seeking=True)))
        for bad in (status(frame=True), status(start=5001), status(speed=float("nan")),
                    status(control=True), status(unverified_from=-1), status(paused="yes")):
            with self.assertRaises(probe_tool.ProbeError):
                probe_tool.validate_status(bad)

    def test_verdict_must_remain_identical_or_keep_exact_provenance(self):
        probe_tool.verify_verdict({"identical": True, "verified": True}, "controls")
        probe_tool.verify_verdict({"identical": False, "verified": False, "unverified_from": 120}, "take-p1", 120)
        for verdict, scenario, provenance in (({"identical": False}, "controls", None),
                                              ({"identical": True, "unverified_from": 1}, "controls", None),
                                              ({"identical": True, "verified": False, "unverified_from": 120}, "take-p2", 120),
                                              ({"identical": False, "verified": False, "unverified_from": 121}, "take-p1", 120)):
            with self.assertRaises(probe_tool.ProbeError):
                probe_tool.verify_verdict(verdict, scenario, provenance)

    def test_game_environment_has_no_inherited_peers_or_output_paths(self):
        with tempfile.TemporaryDirectory(prefix="viewer-probe-", dir=ROOT) as tmp:
            out = Path(tmp)
            (out / "dev_hdd0").mkdir()
            file = out / "test.t5replay"
            file.write_bytes(probe_tool.replays.MAGIC + b'{"matches": []}\n')
            args = types.SimpleNamespace(out=out, hdd0=out / "dev_hdd0", vfs=out / "vfs", file=file, match=1, build_id="test-build")
            inherited = {"PATH": "system-dll-search", "T5_CTL_DIR": "outside", "T5_NET_PEER": "outside",
                         "T5_FIGHT_FILE": "outside", "PS3_SAVEDATA_DIR": "outside", "T5_REPLAY_DIR": "outside",
                         "OPENRECOMP_HOME": "outside", "APPDATA": "outside", "LOCALAPPDATA": "outside"}
            env = probe_tool.game_env(args, inherited)
            self.assertEqual(env["PATH"], inherited["PATH"])
            for key in ("T5_CTL_DIR", "T5_NET_PEER", "T5_FIGHT_FILE", "T5_REPLAY_DIR"):
                self.assertNotIn(key, env)
            for key in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "PS3_HDD0_ROOT", "PS3_SAVEDATA_DIR"):
                self.assertTrue(Path(env[key]).resolve().is_relative_to(out))
            self.assertEqual(env["T5_NET_MODE"], "replay")
            self.assertEqual(env["T5_NET_BIND"], "127.0.0.1")
            self.assertEqual(env["T5_REPLAY_CAPSULES"], "1")
            self.assertEqual(env["T5_REPLAY_CONTROLS"], "0")
            self.assertEqual(env["T5_NET_BUILD"], "test-build")
            self.assertEqual(env["PS3_AUDIO_MUTE"], "1")
            self.assertEqual(env["PS3_WINDOW_BACKGROUND"], "1")
            self.assertEqual(env["PS3_VM_WRITE_WATCH"], "1")
            args.hdd0 = out.parent
            with self.assertRaises(probe_tool.ProbeError):
                probe_tool.game_env(args, inherited)

    def test_existing_result_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="viewer-probe-", dir=ROOT) as tmp:
            out = Path(tmp)
            result = out / "result.json"
            result.write_text("preserve me", encoding="utf-8")
            with mock.patch.object(probe_tool.subprocess, "Popen") as start, mock.patch("builtins.print"):
                code = probe_tool.main(["--exe", "missing", "--vfs", "missing", "--hdd0", "missing", "--out", tmp,
                                        "--file", "missing", "--match", "1", "--scenario", "controls"])
            self.assertEqual(code, 1)
            self.assertEqual(result.read_text(encoding="utf-8"), "preserve me")
            start.assert_not_called()

    def test_scenarios_step_seek_speed_and_preserve_take_control_provenance(self):
        class FakeProbe:
            def __init__(self):
                self.state = status()
                self.commands = []
                self.speed_checks = []

            def wait(self, label, predicate):
                for _ in range(6000):
                    if predicate(self.state):
                        return dict(self.state)
                    self.state["frame"] += 1
                    if self.state["frame"] >= self.state["end"]:
                        self.state["paused"] = True
                raise AssertionError("unreachable probe predicate: " + label)

            def command(self, command, label, predicate):
                self.commands.append(command)
                op, _, value = command.partition(" ")
                if op == "pause": self.state["paused"] = True
                elif op == "resume": self.state["paused"] = False
                elif op == "speed": self.state["speed"] = float(value)
                elif op == "step": self.state["frame"] += 1
                elif op == "seek": self.state.update(frame=int(value), paused=True)
                elif op == "control":
                    self.state["control"] = int(value)
                    if int(value):
                        self.state.update(verified=False, unverified_from=self.state["frame"])
                return self.wait(label, predicate)

            def pause(self, label="pause"):
                return self.command("pause", label, lambda s: s["paused"])

            def seek(self, frame, label):
                return self.command("seek " + str(frame), label, lambda s: s["paused"] and s["frame"] == frame)

            def quit(self):
                self.commands.append("quit")

        for scenario in ("controls", "take-p1", "take-p2"):
            with self.subTest(scenario=scenario):
                probe = FakeProbe()
                provenance = probe_tool.exercise(probe, scenario)
                self.assertEqual(probe.commands.count("step"), 3)
                self.assertIn("seek 93", probe.commands)
                self.assertIn("seek 183", probe.commands)
                self.assertEqual([v["speed"] for v in probe.speed_checks], [0.25, 0.5, 1, 2, 4])
                self.assertTrue(all(v["to"] - v["from"] >= 60 for v in probe.speed_checks))
                self.assertEqual(probe.commands[-1], "quit")
                if scenario == "controls":
                    self.assertIsNone(provenance)
                    self.assertEqual(probe.state["frame"], probe.state["end"])
                else:
                    self.assertEqual(probe.state["unverified_from"], provenance)
                    self.assertFalse(probe.state["verified"])
                    self.assertEqual(probe.state["control"], 0)
                    self.assertIn("control " + scenario[-1], probe.commands)


if __name__ == "__main__":
    unittest.main()
