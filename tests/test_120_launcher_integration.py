"""Launcher wiring regressions, with all processes and UI calls replaced by fakes.

Written during the no-run review; executing this file is a maintainer step.
"""
import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def method(path, class_name, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    code = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(code, path, "exec"), namespace)
    return namespace[name]


class LauncherIntegration(unittest.TestCase):
    def spawn_block(self):
        tree = ast.parse((ROOT / "launcher/core.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GameRun")
        start = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "start")
        block = next(n for n in start.body if isinstance(n, ast.Try)
                     and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                             and call.func.attr == "pause_all" for call in ast.walk(n)))
        return compile(ast.fix_missing_locations(ast.Module(body=[block], type_ignores=[])),
                       "launcher/core.py", "exec")

    def test_side_migration_keeps_replay_folder_and_autospectate_settings(self):
        # Execute the real Settings class and its literal tables without importing
        # build tools, opening a real settings file or starting a process.
        tree = ast.parse((ROOT / "launcher/core.py").read_text(encoding="utf-8"))
        tables = {"DEFAULTS", "SETTINGS_VERSION", "INTERNAL_RES", "OLD_RENDER_SCALES",
                  "SCREEN_SIDES", "VSYNC_MODES", "POWER_SAVING", "STAGE_BLUR_MODES",
                  "ON_OFF_MODES", "GRAPHICS", "TRAINING_MODES", "TRAINING_POS", "PRACTICE_DUMMY",
                  "DISPLAY_MODES", "TRUE_43", "TRUE_43_ONLINE", "PICTURE_FORMATS", "WINDOW_SIZE_MIN", "WINDOW_SIZE_MAX",
                  "MATCH_SOUNDS", "CHALLENGE_SOUNDS"}
        namespace = {"N_": lambda text: text, "SETTINGS_FILE": "unused", "json": json}
        for node in tree.body:
            if (isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id in tables for target in node.targets)) or (
                    isinstance(node, ast.FunctionDef) and node.name == "window_size"):
                exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                             "launcher/core.py", "exec"), namespace)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings")
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                     "launcher/core.py", "exec"), namespace)
        saved = {"always_left": True, "auto_spectate": True, "replay_dir": "chosen replay folder"}
        namespace["open"] = mock.mock_open(read_data=json.dumps(saved))
        settings = namespace["Settings"]("unused")
        self.assertEqual(settings["screen_side"], "left")
        self.assertIs(settings["auto_spectate"], True)
        self.assertEqual(settings["replay_dir"], saved["replay_dir"])
        settings["screen_side"] = "right"
        temporary = mock.mock_open()
        temporary.return_value.name = "unused.tmp"
        namespace["tempfile"] = SimpleNamespace(NamedTemporaryFile=temporary)
        namespace["os"] = SimpleNamespace(path=os.path, fsync=mock.Mock(),
                                          replace=mock.Mock(), remove=mock.Mock())
        settings.save()
        written = json.loads("".join(call.args[0] for call in temporary().write.call_args_list))
        namespace["os"].replace.assert_called_once_with("unused.tmp", "unused")
        self.assertEqual(written["screen_side"], "right")
        self.assertIs(written["always_left"], False)
        self.assertIs(written["auto_spectate"], True)
        self.assertEqual(written["replay_dir"], saved["replay_dir"])

    def test_playback_stop_retains_bounded_autospectate_handoff(self):
        kill_tree = mock.Mock()
        stop = method("launcher/core.py", "GameRun", "stop",
                      {"kill_tree": kill_tree, "subprocess": SimpleNamespace(TimeoutExpired=TimeoutError)})
        game = SimpleNamespace(_playback=True, PLAYBACK_STOP_WAIT=0.25, proc=mock.Mock(),
                               running=mock.Mock(side_effect=[True, False]))
        self.assertTrue(stop(game))
        game.proc.kill.assert_called_once()
        game.proc.wait.assert_called_once_with(timeout=0.25)
        kill_tree.assert_not_called()

    def test_failed_warmup_stop_prevents_real_process_spawn(self):
        warmup = SimpleNamespace(pause_all=mock.Mock(side_effect=OSError("still active")),
                                 resume_all=mock.Mock())
        process = SimpleNamespace(Popen=mock.Mock())
        logf = mock.Mock()
        namespace = {"self": SimpleNamespace(out="chosen-output", _warmup_lease=None),
                     "warmup": warmup, "subprocess": process, "logf": logf}
        with self.assertRaises(OSError):
            exec(self.spawn_block(), namespace)
        process.Popen.assert_not_called()
        warmup.resume_all.assert_not_called()
        logf.close.assert_called_once()

    def test_failed_real_spawn_releases_only_its_game_hold(self):
        token = object()
        warmup = SimpleNamespace(pause_all=mock.Mock(return_value=token), resume_all=mock.Mock())
        process = SimpleNamespace(Popen=mock.Mock(side_effect=OSError("spawn failed")),
                                  STDOUT=-2, DEVNULL=-3)
        game = SimpleNamespace(out="chosen-output", _warmup_lease=None)
        namespace = {"self": game, "warmup": warmup, "subprocess": process, "logf": mock.Mock(),
                     "cmd": [], "env": {}, "cwd": ".", "si": None, "IS_WIN": False}
        with self.assertRaises(OSError):
            exec(self.spawn_block(), namespace)
        warmup.pause_all.assert_called_once_with("chosen-output")
        warmup.resume_all.assert_called_once_with(token)
        self.assertIsNone(game._warmup_lease)

    def test_tail_releases_its_token_only_after_process_exit(self):
        for running in (True, False):
            with self.subTest(running=running):
                token = object()
                warmup = SimpleNamespace(resume_all=mock.Mock())
                tail = method("launcher/core.py", "GameRun", "_tail", {"warmup": warmup})
                game = SimpleNamespace(_warmup_lease=token, _read_tail=mock.Mock(),
                                       running=mock.Mock(return_value=running))
                tail(game)
                if running:
                    warmup.resume_all.assert_not_called()
                    self.assertIs(game._warmup_lease, token)
                else:
                    warmup.resume_all.assert_called_once_with(token)
                    self.assertIsNone(game._warmup_lease)

    def test_declining_gpu_warning_never_starts_build(self):
        dialogs = SimpleNamespace(ask_yes_no=mock.Mock(return_value=False), show_info=mock.Mock())
        gpu = SimpleNamespace(build_warning=mock.Mock(return_value={
            "title": "warning", "message": "adapter {gpus}", "values": {"gpus": "4400"}}))
        core = SimpleNamespace(BuildRun=mock.Mock())
        start = method("launcher/t5dr_launcher.pyw", "App", "start_build",
                       {"dialogs": dialogs, "gpu_support": gpu, "core": core,
                        "APP_TITLE": "Launcher", "t": lambda text, **kw: text.format(**kw)})
        app = SimpleNamespace(build=None, game=None, readonly=False, settings={},
                              refresh_inputs=mock.Mock())
        start(app)
        dialogs.ask_yes_no.assert_called_once_with("warning", "adapter 4400", parent=app)
        app.refresh_inputs.assert_not_called()
        core.BuildRun.assert_not_called()

    def test_gpu_warning_can_be_disabled_for_known_system(self):
        class ReachedBuild(Exception):
            pass

        gpu = SimpleNamespace(build_warning=mock.Mock())
        app = SimpleNamespace(build=None, game=None, readonly=False,
                              settings={"gpu_build_warning": False},
                              refresh_inputs=mock.Mock(side_effect=ReachedBuild))
        start = method("launcher/t5dr_launcher.pyw", "App", "start_build",
                       {"gpu_support": gpu})
        with self.assertRaises(ReachedBuild):
            start(app)
        gpu.build_warning.assert_not_called()

    def test_released_launcher_contains_all_new_mandatory_imports(self):
        tree = ast.parse((ROOT / "tools/package_release.py").read_text(encoding="utf-8"))
        declaration = next(n for n in tree.body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == "OUR_FILES" for t in n.targets))
        shipped = ast.literal_eval(declaration.value)
        for module in ("warmup", "first_start", "gpu_support"):
            with self.subTest(module=module):
                self.assertIn(f"launcher/{module}.py", shipped)
                self.assertTrue((ROOT / f"launcher/{module}.py").is_file())

    def test_build_worker_does_not_wait_for_shader_queue(self):
        source = (ROOT / "launcher/core.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BuildRun")
        values = [n.value for n in ast.walk(cls) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        self.assertNotIn("--warmup", values)


if __name__ == "__main__":
    unittest.main()
