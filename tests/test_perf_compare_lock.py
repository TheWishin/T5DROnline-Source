"""perf_compare's heavy lock with several slots (HEAVY.lock,HEAVY2.lock): a timing run holds all of them.

Lock files in a temp folder only; no game, no server.
"""
import importlib.util
import os
import tempfile
import threading
import time
import unittest

from helpers import ROOT


spec = importlib.util.spec_from_file_location("perf_compare_lock", os.path.join(ROOT, "tools", "perf_compare.py"))
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)


def owner(p):
    return open(p, encoding="utf-8").read().split()[0]


class MultiSlotLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = os.path.join(self.tmp.name, "HEAVY.lock")
        self.b = os.path.join(self.tmp.name, "HEAVY2.lock")

    def tearDown(self):
        self.tmp.cleanup()

    def lock(self, paths, name="perfgate"):
        lk = perf.Lock(",".join(paths), name)
        lk.GAP = 0
        return lk

    def test_takes_and_gives_both(self):
        lk = self.lock([self.a, self.b])
        lk.take("offline x")
        self.assertEqual((owner(self.a), owner(self.b)), ("perfgate", "perfgate"))
        lk.give()
        self.assertFalse(os.path.exists(self.a) or os.path.exists(self.b))

    def test_waits_for_a_slot_someone_else_holds_without_sitting_on_the_other(self):
        with open(self.b, "w", encoding="utf-8") as f:
            f.write("other 12:00 e2e\n")
        lk = self.lock([self.a, self.b])
        perf_sleep = perf.time.sleep
        perf.time.sleep = lambda s: perf_sleep(0.05)
        try:
            t = threading.Thread(target=lk.take, args=("rollback 60",))
            t.start()
            time.sleep(0.3)
            self.assertTrue(t.is_alive(), "must wait while HEAVY2.lock is someone else's")
            free = [not os.path.exists(self.a) for _ in range(20) if perf_sleep(0.01) is None]
            self.assertTrue(any(free), "HEAVY.lock is given back while HEAVY2.lock is waited for")
            self.assertEqual(owner(self.b), "other")
            os.remove(self.b)
            t.join(5)
            self.assertFalse(t.is_alive())
            self.assertEqual((owner(self.a), owner(self.b)), ("perfgate", "perfgate"))
        finally:
            perf.time.sleep = perf_sleep
        lk.give()

    def test_any_two_of_three(self):
        c = os.path.join(self.tmp.name, "HEAVY3.lock")
        with open(self.a, "w", encoding="utf-8") as f:
            f.write("other 12:00 e2e\n")
        lk = perf.Lock(",".join([self.a, self.b, c]), "perfgate", 2)
        lk.GAP = 0
        lk.take("x")
        self.assertEqual((owner(self.a), owner(self.b), owner(c)), ("other", "perfgate", "perfgate"))
        lk.give()
        self.assertFalse(os.path.exists(self.b) or os.path.exists(c))
        self.assertEqual(owner(self.a), "other")

    def test_never_removes_a_foreign_lock(self):
        with open(self.a, "w", encoding="utf-8") as f:
            f.write("other 12:00 x\n")
        self.lock([self.a]).give()
        self.assertEqual(owner(self.a), "other")

    def test_single_path_and_none_still_work(self):
        lk = self.lock([self.a])
        lk.take("x")
        self.assertEqual(owner(self.a), "perfgate")
        lk.give()
        self.assertFalse(os.path.exists(self.a))
        none = perf.Lock("", "x")
        none.take("y")
        none.give()


if __name__ == "__main__":
    unittest.main()
