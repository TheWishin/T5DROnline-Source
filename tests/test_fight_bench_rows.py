"""fight_bench reads the game's frame log after killing the game: a last row cut short must be left out, not crash."""
import importlib.util
import os
import unittest

from helpers import ROOT

spec = importlib.util.spec_from_file_location("fight_bench_rows", os.path.join(ROOT, "tools", "fight_bench.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)


class FrameRowTest(unittest.TestCase):
    def test_num(self):
        self.assertTrue(fb._num("758322437572"))
        self.assertTrue(fb._num("16.5"))
        for v in (None, "", "12x", "0x0000"):
            self.assertFalse(fb._num(v), v)


if __name__ == "__main__":
    unittest.main()
