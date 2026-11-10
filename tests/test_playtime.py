"""launcher/playtime.py: the time-played counter (start, stop, a killed game, a sleeping PC, a damaged file).

Every test writes into its own temporary folder; none touches a launcher's real playtime.json."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(os.path.dirname(HERE), "launcher", "playtime.py")
spec = importlib.util.spec_from_file_location("playtime_under_test", MODULE)
playtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(playtime)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def go(self, seconds):
        self.now += seconds


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "playtime.json")
        self.store = playtime.Store(self.path)
        self.clock = Clock()

    def session(self, game="game", **kw):
        return playtime.Session(self.store, game, clock=self.clock, **kw)

    def on_disk(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)


class TextTest(Base):
    def test_format(self):
        self.assertEqual(playtime.text(0), "Playtime: 0 h 0 min")
        self.assertEqual(playtime.text(59.9), "Playtime: 0 h 0 min")
        self.assertEqual(playtime.text(60), "Playtime: 0 h 1 min")
        self.assertEqual(playtime.text(3600 * 12 + 5 * 60 + 59), "Playtime: 12 h 5 min")
        self.assertEqual(playtime.text(3600 * 1234), "Playtime: 1234 h 0 min")
        self.assertEqual(playtime.text(7260, "Spielzeit: {hours} h {minutes} min"), "Spielzeit: 2 h 1 min")

    def test_bad_numbers(self):
        for bad in (-5, None, "x", float("nan"), float("inf")):
            self.assertEqual(playtime.split(bad), (0, 0))

    def test_default_path_and_override(self):
        name = "PLAYTIME_TEST_FILE_VAR"
        os.environ.pop(name, None)
        self.assertEqual(playtime.default_path(self.tmp.name, name), self.path)
        os.environ[name] = os.path.join(self.tmp.name, "other.json")
        self.addCleanup(os.environ.pop, name, None)
        self.assertEqual(playtime.default_path(self.tmp.name, name), os.environ[name])


class SessionTest(Base):
    def test_start_beats_stop(self):
        s = self.session()
        s.start()
        self.assertEqual(self.store.sessions("game"), 1)
        for _ in range(4):
            self.clock.go(30)
            s.beat()
        self.assertEqual(self.store.seconds("game"), 120)       # saved at every beat
        self.clock.go(12.5)
        self.assertEqual(s.unsaved(), 12.5)
        self.assertEqual(s.stop(), 132.5)
        self.assertEqual(self.store.seconds("game"), 132.5)
        self.assertFalse(s.running())
        self.assertEqual(self.on_disk()["version"], playtime.VERSION)

    def test_stop_twice_and_beat_after_stop_add_nothing(self):
        s = self.session()
        s.start()
        self.clock.go(20)
        s.stop()
        self.clock.go(500)
        s.beat()
        s.stop()
        self.assertEqual(self.store.seconds("game"), 20)
        self.assertEqual(self.store.sessions("game"), 1)

    def test_two_sessions_add_up(self):
        for seconds in (40, 50):
            s = self.session()
            s.start()
            self.clock.go(seconds)
            s.stop()
        self.assertEqual(self.store.seconds("game"), 90)
        self.assertEqual(self.store.sessions("game"), 2)

    def test_games_are_separate(self):
        a, b = self.session("t5dr"), self.session("t4")
        a.start()
        b.start()
        self.clock.go(60)
        a.stop()
        self.clock.go(30)
        b.stop()
        self.assertEqual(self.store.seconds("t5dr"), 60)
        self.assertEqual(self.store.seconds("t4"), 90)

    def test_launcher_crash_keeps_what_was_saved(self):
        s = self.session()
        s.start()
        self.clock.go(30)
        s.beat()
        self.clock.go(30)
        s.beat()
        self.clock.go(25)                  # the launcher dies here: no stop()
        del s
        self.assertEqual(playtime.Store(self.path).seconds("game"), 60)

    def test_sleep_gap_is_not_played(self):
        s = self.session()
        s.start()
        self.clock.go(30)
        s.beat()
        self.clock.go(8 * 3600)            # the PC slept with the game open
        self.assertEqual(s.unsaved(), 0)
        s.beat()
        self.clock.go(30)
        s.beat()
        self.assertEqual(s.stop(), 60)
        self.assertEqual(self.store.seconds("game"), 60)

    def test_gap_at_the_stop_is_not_played(self):
        s = self.session()
        s.start()
        self.clock.go(30)
        s.beat()
        self.clock.go(5 * 3600)            # slept, then the game was gone
        self.assertEqual(s.stop(), 30)
        self.assertEqual(self.store.seconds("game"), 30)

    def test_gap_limit_is_inclusive(self):
        s = self.session(max_gap=120)
        s.start()
        self.clock.go(120)
        s.beat()
        self.clock.go(120.5)
        s.beat()
        self.assertEqual(s.stop(), 120)

    def test_clock_going_back_adds_nothing(self):
        s = self.session()
        s.start()
        self.clock.go(-50)
        s.beat()
        self.clock.go(10)
        self.assertEqual(s.stop(), 10)

    def test_killed_game_is_cut_to_its_lifetime(self):
        s = self.session()
        s.start()
        self.clock.go(30)
        s.beat()
        self.clock.go(100)                 # the game died 5 s after the beat; the launcher saw it late
        self.assertEqual(s.stop(lifetime=35), 35)
        self.assertEqual(self.store.seconds("game"), 35)

    def test_lifetime_longer_than_counted_changes_nothing(self):
        s = self.session()
        s.start()
        self.clock.go(30)
        s.beat()
        self.clock.go(9 * 3600)            # slept: the process lived 9 h, played 30 s
        self.assertEqual(s.stop(lifetime=9 * 3600 + 30), 30)
        self.assertEqual(self.store.seconds("game"), 30)

    def test_lifetime_cut_never_takes_older_time(self):
        self.store.add("game", 500)
        s = self.session()
        s.start()
        self.clock.go(100)
        s.beat()
        s.stop(lifetime=0)
        self.assertEqual(self.store.seconds("game"), 500)

    def test_max_session(self):
        s = self.session(max_session=100)
        s.start()
        for _ in range(10):
            self.clock.go(30)
            s.beat()
        self.assertEqual(s.stop(), 100)
        self.assertEqual(self.store.seconds("game"), 100)

    def test_failed_write_is_made_up_later(self):
        s = self.session()
        s.start()
        real, self.store._write = self.store._write, lambda *a, **k: False
        self.clock.go(30)
        s.beat()
        self.assertEqual(self.store.seconds("game"), 0)
        self.assertEqual(s.unsaved(), 30)
        self.store._write = real
        self.clock.go(30)
        s.beat()
        self.assertEqual(self.store.seconds("game"), 60)

    def test_session_count_made_up_after_failed_first_write(self):
        s = self.session()
        real, self.store._write = self.store._write, lambda *a, **k: False
        s.start()
        self.store._write = real
        self.clock.go(10)
        s.stop()
        self.assertEqual(self.store.sessions("game"), 1)
        self.assertEqual(self.store.seconds("game"), 10)


class FileTest(Base):
    def write(self, text, path=None):
        with open(path or self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_missing_file(self):
        self.assertEqual(self.store.seconds("game"), 0)
        self.assertEqual(self.store.games(), {})
        self.assertFalse(os.path.exists(self.path))             # reading creates nothing

    def test_corrupted_file_without_copy_starts_at_zero_and_is_kept(self):
        for junk in ("", "{\"games\": {\"game\": {\"seco", "[1, 2]", "\x00\x00\x00", "{\"games\": 5}"):
            with self.subTest(junk=junk):
                self.write(junk)
                self.assertEqual(self.store.seconds("game"), 0)
                self.assertTrue(os.path.exists(self.path + ".bad"))
                self.store.add("game", 10)
                self.assertEqual(self.store.seconds("game"), 10)
                os.remove(self.path)
                os.remove(self.path + ".bad")

    def test_corrupted_file_falls_back_to_the_copy(self):
        self.store.add("game", 7200)
        s = self.session()
        s.start()                          # keeps playtime.json.bak
        self.clock.go(60)
        s.beat()
        self.write("{\"version\": 1, \"games\": {\"game\": {\"sec")     # cut short
        self.assertEqual(self.store.seconds("game"), 7200)
        self.clock.go(30)
        s.stop()
        self.assertEqual(self.store.seconds("game"), 7230)
        with open(self.path + ".bad", encoding="utf-8") as f:
            self.assertIn("sec", f.read())

    def test_damaged_copy_too(self):
        self.write("nonsense")
        self.write("more nonsense", self.path + ".bak")
        self.assertEqual(self.store.seconds("game"), 0)
        self.assertTrue(self.store.add("game", 5))
        self.assertEqual(self.store.seconds("game"), 5)

    def test_backup_never_copies_a_damaged_file(self):
        self.store.add("game", 100)
        self.assertTrue(self.store.backup())
        self.write("broken")
        self.assertFalse(self.store.backup())
        with open(self.path + ".bak", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["games"]["game"]["seconds"], 100)

    def test_bad_values_inside_a_good_file(self):
        self.write(json.dumps({"version": 1, "games": {
            "game": {"seconds": -4, "sessions": "many"}, "t4": {"seconds": True}, "x": 3,
            "ok": {"seconds": 90, "sessions": 2, "last_played": "2026-11-10T10:00:00"}}}))
        games = self.store.games()
        self.assertEqual(games["game"], {"seconds": 0.0, "sessions": 0, "last_played": ""})
        self.assertEqual(games["t4"]["seconds"], 0.0)
        self.assertNotIn("x", games)
        self.assertEqual(games["ok"]["seconds"], 90)

    def test_crash_in_the_middle_of_a_write_leaves_the_old_file(self):
        self.store.add("game", 300)
        real = os.replace

        def dying(src, dst):
            raise OSError("power cut before the rename")
        os.replace = dying
        try:
            self.assertFalse(self.store.add("game", 30))
        finally:
            os.replace = real
        self.assertEqual(self.store.seconds("game"), 300)
        self.assertEqual(self.on_disk()["games"]["game"]["seconds"], 300)
        self.assertEqual([n for n in os.listdir(self.tmp.name) if n.endswith(".tmp")], [])

    def test_leftover_temporary_file_is_harmless(self):
        self.write("{\"half", os.path.join(self.tmp.name, ".playtime-abc.tmp"))
        self.store.add("game", 15)
        self.assertEqual(self.store.seconds("game"), 15)

    def test_unwritable_place_never_raises(self):
        self.write("{}")
        store = playtime.Store(os.path.join(self.path, "under-a-file", "playtime.json"))
        self.assertFalse(store.add("game", 5))
        self.assertEqual(store.seconds("game"), 0)

    def test_two_launchers_add_up(self):
        other = playtime.Store(self.path)
        self.store.add("game", 10)
        other.add("game", 20)
        self.store.add("game", 5)
        self.assertEqual(other.seconds("game"), 35)

    def test_threads(self):
        def work():
            for _ in range(25):
                self.store.add("game", 1)
        threads = [threading.Thread(target=work) for _ in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        self.assertEqual(self.store.seconds("game"), 100)


class TrackTest(Base):
    """track() on a real process (a Python that sleeps): counted from the launcher's own process handle."""

    def child(self, seconds):
        return subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(%s)" % seconds])

    def test_process_that_ends_by_itself(self):
        proc = self.child(1.2)
        s = playtime.track(proc, self.store, "game", beat=0.25)
        s.thread.join(20)
        self.assertFalse(s.thread.is_alive())
        self.assertFalse(s.running())
        played = self.store.seconds("game")
        self.assertGreater(played, 0.8)
        self.assertLess(played, 6)
        self.assertEqual(self.store.sessions("game"), 1)
        life = playtime.process_lifetime(proc)
        if life is not None:
            self.assertLessEqual(played, life + 0.11)

    def test_killed_process_stops_the_count(self):
        proc = self.child(60)
        s = playtime.track(proc, self.store, "game", beat=0.2)
        threading.Event().wait(1.0)
        proc.kill()
        s.thread.join(20)
        self.assertFalse(s.thread.is_alive())
        played = self.store.seconds("game")
        self.assertGreater(played, 0.5)
        self.assertLess(played, 10)

    def test_lifetime_of_a_running_process(self):
        proc = self.child(30)
        try:
            life = playtime.process_lifetime(proc)
            self.assertTrue(life is None or life >= 0)
        finally:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    unittest.main()
