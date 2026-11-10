"""The settings T5DR's launcher and OpenRecomp share (launcher/settings_sync.py, docs/SETTINGS_SYNC.md).

Every file is in a temporary folder: a Settings made here names its launcher.json and its shared folder itself, so
neither the checkout's launcher.json nor the player's %APPDATA%\\T5DROnline is ever read or written.

* the file: version, unknown fields kept, folder-only settings never in it, atomic writes, a held file tried again,
  a damaged file moved aside;
* migration: the first start with only launcher.json, with a launcher's own older overrides (the newer file wins,
  both are backed up), a T5DR folder seen for the first time;
* both directions: what this launcher saves is what the other one loads (the other one = the calls OpenRecomp
  makes: sync / mirror / save), and back; a T5DR launcher without the file (1.2.2) changing launcher.json;
* with T5DR_TEST_OPENRECOMP_SRC=<an OpenRecomp checkout> also against OpenRecomp's real settings class.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core  # noqa: E402
import settings_sync as ss  # noqa: E402

OPENRECOMP_SRC = os.environ.get("T5DR_TEST_OPENRECOMP_SRC")


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def raw(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, value, age=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f)
    if age:
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = self.enterContext(tempfile.TemporaryDirectory())
        self.shared = os.path.join(self.dir, "user")
        self.file = os.path.join(self.shared, ss.FILE_NAME)
        self.install = os.path.join(self.dir, "T5DR-Online-1.2.3")
        self.launcher_json = os.path.join(self.install, "launcher.json")
        os.makedirs(self.install)
        self.id = ss.install_id(self.install)

    def store(self, who="test", **kw):
        return ss.Store(self.shared, who=who, sleep=lambda _s: None, **kw)

    def settings(self, install=None):
        return core.Settings(os.path.join(install or self.install, "launcher.json"), shared=self.shared)

    def backups(self):
        folder = os.path.join(self.shared, ss.BACKUP_DIR)
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


class FileTests(Base):
    def test_nothing_is_written_until_something_is_saved(self):
        write(self.launcher_json, {"display": "borderless", "pkg": "p.pkg"})
        result = ss.sync(self.store(), self.id, read(self.launcher_json), self.launcher_json)
        self.assertEqual((result.state, result.values), ("missing", {"display": "borderless"}))
        self.assertFalse(os.path.exists(self.shared))

    def test_first_save_makes_the_file_from_launcher_json_and_backs_it_up(self):
        local = {"display": "borderless", "vsync": "off", "pkg": "p.pkg", "language": "de"}
        write(self.launcher_json, local)
        self.assertTrue(ss.save(self.store("a"), self.id, {"vsync": "on"}, local, self.launcher_json))
        doc = read(self.file)
        self.assertEqual((doc["format"], doc["version"], doc["updated_by"]), ("t5dr-settings", 1, "a"))
        self.assertEqual(doc["values"], {"display": "borderless", "vsync": "on"})       # no pkg, no language
        self.assertEqual(doc["installs"][self.id]["seen"], {"display": "borderless", "vsync": "off"})
        self.assertEqual(len(self.backups()), 1)
        self.assertTrue(self.backups()[0].startswith(f"launcher-{self.id}-"))
        self.assertEqual(os.listdir(self.shared).count(ss.FILE_NAME), 1)
        self.assertFalse([n for n in os.listdir(self.shared) if n.endswith(".tmp")])

    def test_folder_only_settings_never_reach_the_file(self):
        for key in ("pkg", "rap", "out", "language", "background", "clock_hint_shown", "controls_hint_shown",
                    "gpu_build_warning"):
            self.assertIn(key, core.DEFAULTS)
            self.assertFalse(ss.shared_key(key), key)
        ss.save(self.store(), self.id, dict(core.DEFAULTS, pkg="x", language="ja"))
        values = read(self.file)["values"]
        self.assertEqual(set(values), set(core.DEFAULTS) - ss.LOCAL_KEYS)

    def test_unknown_fields_and_a_newer_version_are_kept(self):
        write(self.file, {"format": "t5dr-settings", "version": 7, "later": {"a": 1},
                          "values": {"display": "window", "from_a_later_launcher": [1, 2]}})
        self.assertTrue(ss.save(self.store(), self.id, {"display": "maximized"}))
        doc = read(self.file)
        self.assertEqual(doc["version"], 7)
        self.assertEqual(doc["later"], {"a": 1})
        self.assertEqual(doc["values"], {"display": "maximized", "from_a_later_launcher": [1, 2]})

    def test_a_save_keeps_what_another_launcher_saved_meanwhile(self):
        ss.save(self.store("a"), self.id, {"display": "window", "vsync": "on"})
        ss.save(self.store("b"), "other", {"display": "borderless"})        # the other launcher, while a is open
        ss.save(self.store("a"), self.id, {"vsync": "off"})
        self.assertEqual(read(self.file)["values"], {"display": "borderless", "vsync": "off"})

    def test_a_held_file_is_tried_again(self):
        ss.save(self.store(), self.id, {"display": "window"})
        real, calls = os.replace, []

        def replace(src, dst):
            calls.append(dst)
            if len(calls) <= 3:
                raise PermissionError(13, "held by the antivirus")
            return real(src, dst)

        with mock.patch.object(ss.os, "replace", replace):
            self.assertTrue(ss.save(self.store(), self.id, {"display": "maximized"}))
        self.assertEqual(len(calls), 4)
        self.assertEqual(read(self.file)["values"]["display"], "maximized")

    def test_a_file_held_for_good_is_left_alone_and_reported(self):
        ss.save(self.store(), self.id, {"display": "window"})
        before = raw(self.file)
        store = self.store(seconds=0.0)
        with mock.patch.object(ss.os, "replace", side_effect=PermissionError(13, "held")):
            self.assertFalse(ss.save(store, self.id, {"display": "maximized"}))
        self.assertEqual(raw(self.file), before)
        self.assertEqual(os.listdir(self.shared), [ss.FILE_NAME])           # no temporary file left
        self.assertTrue(store.notes)

    def test_a_file_that_cannot_be_read_now_changes_nothing(self):
        ss.save(self.store(), self.id, {"display": "window"})
        write(self.launcher_json, {"display": "borderless"})
        real = open

        def held(path, *a, **kw):
            if os.path.abspath(path) == os.path.abspath(self.file):
                raise PermissionError(13, "held")
            return real(path, *a, **kw)

        store = self.store(seconds=0.0)
        with mock.patch("builtins.open", held):
            result = ss.sync(store, self.id, read(self.launcher_json), self.launcher_json)
            self.assertFalse(ss.save(store, self.id, {"display": "maximized"}))
        self.assertEqual((result.state, result.values), ("locked", {"display": "borderless"}))
        self.assertEqual(read(self.file)["values"], {"display": "window"})
        self.assertEqual(os.listdir(self.shared), [ss.FILE_NAME])           # not moved aside, not replaced

    def test_a_damaged_file_is_moved_aside(self):
        for content in (b'{"values": {"display": ', b"[]", b"\xff\xfe", b'{"values": 3}'):
            with self.subTest(content=content):
                os.makedirs(self.shared, exist_ok=True)
                for name in os.listdir(self.shared):
                    os.unlink(os.path.join(self.shared, name))
                with open(self.file, "wb") as f:
                    f.write(content)
                write(self.launcher_json, {"display": "borderless"})
                store = self.store()
                result = ss.sync(store, self.id, read(self.launcher_json), self.launcher_json)
                self.assertEqual((result.state, result.values), ("missing", {"display": "borderless"}))
                aside = [n for n in os.listdir(self.shared) if ".corrupt-" in n]
                self.assertEqual(len(aside), 1)
                self.assertEqual(raw(os.path.join(self.shared, aside[0])), content)
                self.assertFalse(os.path.exists(self.file))
                self.assertTrue(ss.save(store, self.id, {"vsync": "off"}, read(self.launcher_json)))
                self.assertEqual(read(self.file)["values"], {"display": "borderless", "vsync": "off"})

    def test_a_file_being_replaced_is_read_again_before_it_counts_as_damaged(self):
        os.makedirs(self.shared)
        with open(self.file, "wb") as f:
            f.write(b'{"values": {"disp')
        good = json.dumps({"values": {"display": "maximized"}}).encode()

        def finish(_seconds):
            with open(self.file, "wb") as f:
                f.write(good)

        doc, state = ss.Store(self.shared, sleep=finish).read()
        self.assertEqual((state, doc["values"]), ("ok", {"display": "maximized"}))
        self.assertEqual(os.listdir(self.shared), [ss.FILE_NAME])

    def test_only_a_few_folders_and_backups_are_remembered(self):
        for n in range(ss.MAX_INSTALLS + 3):
            store = self.store(now=lambda n=n: 1000.0 + n)
            ss.save(store, f"id{n}", {"display": "window"}, mirrored={"display": "window"})
        self.assertEqual(sorted(read(self.file)["installs"]),
                         sorted(f"id{n}" for n in range(3, ss.MAX_INSTALLS + 3)))
        write(self.launcher_json, {"display": "window"})
        store = self.store()
        for _ in range(ss.MAX_BACKUPS + 4):
            store.backup(self.launcher_json, "launcher-x")
        self.assertEqual(len(self.backups()), ss.MAX_BACKUPS)


class MigrationTests(Base):
    """`extra` = what OpenRecomp 0.1.x kept for itself (its overrides file)."""

    def setUp(self):
        super().setUp()
        self.own = os.path.join(self.dir, "openrecomp-home", "settings.json")

    def migrate(self):
        store = self.store("openrecomp")
        result = ss.sync(store, self.id, read(self.launcher_json), self.launcher_json, read(self.own), self.own)
        return result, store

    def test_the_newer_own_file_wins_and_both_are_backed_up(self):
        write(self.launcher_json, {"display": "window", "vsync": "on", "mute": True, "pkg": "p"}, age=3600)
        write(self.own, {"display": "borderless", "training": "off", "pkg": "q"})
        before = raw(self.launcher_json), raw(self.own)
        result, _store = self.migrate()
        self.assertEqual(result.values, {"display": "borderless", "vsync": "on", "mute": True, "training": "off"})
        self.assertEqual(result.migrated, ("display", "training"))
        self.assertEqual(read(self.file)["values"], result.values)
        self.assertEqual((raw(self.launcher_json), raw(self.own)), before)
        names = self.backups()
        self.assertEqual([n.split("-")[0] for n in names], ["launcher", "own"])
        folder = os.path.join(self.shared, ss.BACKUP_DIR)
        self.assertEqual(raw(os.path.join(folder, names[0])), before[0])
        self.assertEqual(raw(os.path.join(folder, names[1])), before[1])

    def test_the_newer_launcher_json_wins_but_values_only_the_own_file_has_stay(self):
        write(self.own, {"display": "borderless", "training": "off"}, age=3600)
        write(self.launcher_json, {"display": "window", "vsync": "on"})
        result, _store = self.migrate()
        self.assertEqual(result.values, {"display": "window", "vsync": "on", "training": "off"})
        self.assertEqual(result.migrated, ("training",))
        self.assertEqual(len(self.backups()), 2)                 # the losing "borderless" is in the backup

    def test_own_overrides_meet_a_file_the_other_launcher_already_made(self):
        ss.save(self.store(now=lambda: time.time() - 600), self.id, {"display": "window", "vsync": "on"})
        write(self.launcher_json, {"display": "window", "vsync": "on"}, age=900)
        write(self.own, {"display": "borderless"})               # edited after the file's stamp: wins
        result, _store = self.migrate()
        self.assertEqual(result.values, {"display": "borderless", "vsync": "on"})
        write(self.own, {"vsync": "off"}, age=3600)             # older than the stamp: the file's value stays
        result, _store = self.migrate()
        self.assertEqual(result.values, {"display": "borderless", "vsync": "on"})

    def test_a_folder_seen_for_the_first_time_takes_the_shared_values(self):
        ss.save(self.store(), "the-old-folder", {"display": "borderless", "vsync": "off"})
        write(self.launcher_json, {"display": "window", "vsync": "off", "training": "inputs"})
        store = self.store()
        result = ss.sync(store, self.id, read(self.launcher_json), self.launcher_json)
        self.assertEqual(result.values, {"display": "borderless", "vsync": "off", "training": "inputs"})
        self.assertEqual(result.imported, ())
        self.assertEqual(len(self.backups()), 1)                 # its "window" is kept in the backup
        self.assertEqual(read(self.file)["installs"][self.id]["seen"],
                         {"display": "window", "vsync": "off", "training": "inputs"})
        ss.sync(self.store(), self.id, read(self.launcher_json), self.launcher_json)
        self.assertEqual(len(self.backups()), 1)                 # once


class LauncherTests(Base):
    """core.Settings with a shared folder; the other launcher is played by the calls OpenRecomp makes."""

    def other_saves(self, **changes):
        store = self.store("openrecomp")
        local = read(self.launcher_json) if os.path.exists(self.launcher_json) else None
        mirrored = changes if ss.mirror(self.launcher_json, changes) else None
        self.assertTrue(ss.save(store, self.id, changes, local, self.launcher_json, mirrored))

    def other_loads(self):
        local = read(self.launcher_json) if os.path.exists(self.launcher_json) else None
        return ss.sync(self.store("openrecomp"), self.id, local, self.launcher_json).values

    def test_a_path_alone_never_uses_a_shared_file(self):
        s = core.Settings(self.launcher_json)
        self.assertIsNone(s._store)
        s["display"] = "borderless"
        s.save()
        self.assertEqual(os.listdir(self.dir), [os.path.basename(self.install)])

    def test_a_test_run_never_finds_the_players_folder(self):
        clean = {k: v for k, v in os.environ.items() if k not in ("T5_SETTINGS_DIR", "T5_ONLINE_DIR",
                                                                  "T5_SETTINGS_SHARED")}
        with mock.patch.dict(os.environ, clean, clear=True):
            self.assertIsNone(core.shared_settings_dir())
        with mock.patch.dict(os.environ, dict(clean, T5_ONLINE_DIR=self.shared), clear=True):
            self.assertEqual(core.shared_settings_dir(), self.shared)
        with mock.patch.dict(os.environ, dict(clean, T5_SETTINGS_DIR=self.shared, T5_SETTINGS_SHARED="0"),
                             clear=True):
            self.assertIsNone(core.shared_settings_dir())

    def test_default_settings_use_the_folder_named_by_the_environment(self):
        with mock.patch.dict(os.environ, T5_SETTINGS_DIR=self.shared), \
                mock.patch.object(core, "SETTINGS_FILE", self.launcher_json):
            os.environ.pop("T5_SETTINGS_SHARED", None)
            s = core.Settings()
            s["display"] = "maximized"
            s.save()
        self.assertEqual(read(self.file)["values"]["display"], "maximized")
        self.assertEqual(read(self.launcher_json)["display"], "maximized")

    def test_what_this_launcher_saves_the_other_one_loads(self):
        s = self.settings()
        self.assertFalse(os.path.exists(self.shared))             # a first start writes nothing
        s["display"] = "borderless"
        s["input_delay"] = "1"
        s["pkg"] = "C:/games/t5.pkg"
        s.save()
        values = self.other_loads()
        self.assertEqual((values["display"], values["input_delay"]), ("borderless", "1"))
        self.assertNotIn("pkg", values)
        self.assertEqual(read(self.launcher_json)["pkg"], "C:/games/t5.pkg")

    def test_what_the_other_one_saves_this_launcher_loads_after_a_restart(self):
        s = self.settings()
        s["display"] = "borderless"
        s.save()
        self.other_saves(display="maximized", vsync="off", screen_side="left")
        s = self.settings()
        self.assertEqual((s["display"], s["vsync"], s["screen_side"], s["always_left"]),
                         ("maximized", "off", "left", True))
        self.assertEqual(read(self.launcher_json)["display"], "maximized")      # also for a 1.2.2 launcher

    def test_the_other_one_changed_it_while_this_launcher_was_open(self):
        s = self.settings()
        s.save()
        self.other_saves(display="maximized")
        s["vsync"] = "off"
        s.save()                                                  # launcher.json gets this launcher's old "window"...
        self.assertEqual(read(self.file)["values"]["display"], "maximized")     # ...the shared file does not
        s = self.settings()
        self.assertEqual((s["display"], s["vsync"]), ("maximized", "off"))

    def test_a_value_this_version_does_not_know_is_not_overwritten(self):
        self.other_saves(input_delay="auto", display="a-later-mode")
        s = self.settings()
        self.assertEqual(s["display"], "window")                  # this launcher's own default
        s["vsync"] = "off"
        s.save()
        self.assertEqual(read(self.file)["values"]["display"], "a-later-mode")
        s["display"] = "borderless"                               # until the player chooses here
        s.save()
        self.assertEqual(read(self.file)["values"]["display"], "borderless")

    def test_a_new_folder_starts_with_the_players_settings(self):
        old = self.settings()
        old["display"] = "borderless"
        old["stage_blur"] = "on"
        old["internal_res"] = "1440p"
        old["internal_res_set"] = True
        old["nickname"] = "Wishin"
        old["pkg"] = "C:/games/t5.pkg"
        old.save()
        new_folder = os.path.join(self.dir, "T5DR-Online-1.2.4")
        os.makedirs(new_folder)
        s = self.settings(new_folder)
        self.assertEqual((s["display"], s["stage_blur"], s["internal_res"], s["internal_res_set"], s["nickname"]),
                         ("borderless", "on", "1440p", True, "Wishin"))
        self.assertEqual(s["pkg"], "")                            # the package belongs to the folder

    def test_a_launcher_without_the_file_changed_launcher_json(self):
        s = self.settings()
        s["display"] = "borderless"
        s.save()
        self.other_saves(vsync="off")
        old = read(self.launcher_json)                            # T5DR 1.2.2: reads and writes only launcher.json
        self.assertEqual(old["vsync"], "off")                     # ... and sees what the other launcher saved
        old["display"] = "maximized"
        write(self.launcher_json, old)
        future = time.time() + 5
        os.utime(self.launcher_json, (future, future))
        self.assertEqual({k: self.other_loads()[k] for k in ("display", "vsync")},
                         {"display": "maximized", "vsync": "off"})
        s = self.settings()
        self.assertEqual((s["display"], s["vsync"]), ("maximized", "off"))

    def test_an_unchanged_old_launcher_json_does_not_undo_a_newer_shared_value(self):
        s = self.settings()
        s.save()
        store = self.store("openrecomp")                          # saved without reaching launcher.json (held)
        self.assertTrue(ss.save(store, self.id, {"display": "maximized"}, read(self.launcher_json)))
        write(self.launcher_json, read(self.launcher_json))       # 1.2.2 saves its unchanged settings on exit
        self.assertEqual(self.other_loads()["display"], "maximized")
        self.assertEqual(self.settings()["display"], "maximized")

    def test_the_1_1_3_migration_reaches_the_shared_file(self):
        write(self.launcher_json, {"stage_blur": "on", "internal_res": "1080p", "display": "window"})
        s = self.settings()
        self.assertEqual((s["stage_blur"], s["internal_res_set"]), ("off", True))
        s.save()
        values = read(self.file)["values"]
        self.assertEqual((values["stage_blur"], values["internal_res_set"], values["settings_version"]),
                         ("off", True, core.SETTINGS_VERSION))
        s = self.settings()
        s["stage_blur"] = "on"
        s.save()
        self.assertEqual(self.settings()["stage_blur"], "on")     # chosen now: stays

    def test_a_held_shared_file_never_stops_the_launcher_and_the_edit_is_not_lost(self):
        s = self.settings()
        s.save()
        s["display"] = "borderless"
        with mock.patch.object(ss, "write_json", return_value=False), mock.patch.object(core, "log"):
            s.save()
        self.assertEqual(read(self.launcher_json)["display"], "borderless")
        self.assertNotEqual(read(self.file)["values"].get("display"), "borderless")
        os.utime(self.launcher_json, (time.time() + 5, time.time() + 5))
        self.assertEqual(self.settings()["display"], "borderless")              # taken from launcher.json
        self.assertEqual(read(self.file)["values"]["display"], "borderless")

    def test_a_broken_shared_folder_falls_back_to_launcher_json(self):
        write(self.launcher_json, {"display": "borderless"})
        with open(self.shared, "w") as f:                         # a file where the folder should be
            f.write("x")
        with mock.patch.object(core, "log"):
            s = self.settings()
            s["vsync"] = "off"
            s.save()
        self.assertEqual((s["display"], read(self.launcher_json)["vsync"]), ("borderless", "off"))

    def test_the_release_carries_the_module(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import package_release
        self.assertIn("launcher/settings_sync.py", package_release.OUR_FILES)


@unittest.skipUnless(OPENRECOMP_SRC, "T5DR_TEST_OPENRECOMP_SRC names no OpenRecomp checkout")
class RealOpenRecompTests(Base):
    """This launcher's real Settings and OpenRecomp's real settings class on one folder (temporary files only)."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.dir, "openrecomp-home")
        env = dict(OPENRECOMP_HOME=self.home, OPENRECOMP_TESTING="1", T5_SETTINGS_DIR=self.shared)
        self.enterContext(mock.patch.dict(os.environ, env))
        sys.path.insert(0, OPENRECOMP_SRC)
        self.addCleanup(sys.path.remove, OPENRECOMP_SRC)
        from openrecomp.adapters import t5_coexist
        self.coexist = t5_coexist
        with open(os.path.join(OPENRECOMP_SRC, "openrecomp", "settings_sync.py"), "rb") as theirs, \
                open(ss.__file__, "rb") as ours:
            self.assertEqual(theirs.read().replace(b"\r\n", b"\n"), ours.read().replace(b"\r\n", b"\n"),
                             "the two copies of settings_sync.py differ")

    def openrecomp(self):
        with mock.patch.object(core, "SETTINGS_FILE", self.launcher_json):
            return self.coexist.load_settings(core, self.install)

    def test_both_directions(self):
        mine = self.settings()
        mine["display"] = "borderless"
        mine["nickname"] = "Wishin"
        mine.save()
        theirs = self.openrecomp()
        self.assertEqual((theirs["display"], theirs["nickname"]), ("borderless", "Wishin"))
        theirs["vsync"] = "off"
        theirs["internal_res"] = "1440p"
        theirs["pkg"] = "D:/other/t5.pkg"
        theirs.save()
        mine = self.settings()
        self.assertEqual((mine["vsync"], mine["internal_res"], mine["display"]), ("off", "1440p", "borderless"))
        self.assertEqual(mine["pkg"], "")                         # OpenRecomp's package choice stays its own
        self.assertEqual(self.openrecomp()["pkg"], "D:/other/t5.pkg")
        mine["vsync"] = "on"
        mine.save()
        self.assertEqual(self.openrecomp()["vsync"], "on")

    def test_openrecomps_old_overrides_move_into_the_shared_file(self):
        write(self.launcher_json, dict(core.DEFAULTS, display="window", settings_version=1), age=3600)
        private = self.coexist.local_path(self.install, "settings.json")
        write(private, {"display": "maximized", "training": "off", "rap": "D:/other/t5.rap"})
        theirs = self.openrecomp()
        self.assertEqual((theirs["display"], theirs["training"], theirs["rap"]),
                         ("maximized", "off", "D:/other/t5.rap"))
        self.assertEqual(read(private), {"rap": "D:/other/t5.rap"})
        self.assertEqual(len(self.backups()), 2)
        mine = self.settings()
        self.assertEqual((mine["display"], mine["training"], mine["rap"]), ("maximized", "off", ""))

    def test_a_choice_this_launcher_does_not_have_is_not_shown_by_openrecomp(self):
        mine = self.settings()
        mine.save()
        ss.save(self.store("later"), "x", {"display": "a-later-mode", "vsync": "off"})
        theirs = self.openrecomp()
        self.assertEqual((theirs["display"], theirs["vsync"]), ("window", "off"))


if __name__ == "__main__":
    unittest.main()
