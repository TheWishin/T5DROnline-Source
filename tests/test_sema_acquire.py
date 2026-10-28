"""The FIFO walker waits for the game's semaphore ACQUIRE on every platform (ps3recomp patch 0085; GitHub #12: the
EWGF's lightning ended after a few frames on a slow graphics card), and the rollback keeps the frame counter behind
that acquire live (src/rollback/rb_state.cpp kKeepLive), so re-simulated frames never put an acquire the walker
would wait for in vain. No game needed; the real-game checks are tools/effects_test.py and the rollback test mode
(docs/RENDER_PERF.md "Hit effects on slow graphics cards: the walker passed the game's semaphore")."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0085-sema-acquire-windows.patch")
COUNTER = 0x106D4C8C   # graphics object 0x106D4A00 + 0x28C: the present's frame counter (label 0xFD)


def ranges(src, name):
    body = re.search(r"const Range %s\[\] = \{(.*?)\n\};" % name, src, re.S).group(1)
    return [(int(a, 16), int(n, 16)) for a, n in re.findall(r"\{\s*0x([0-9A-Fa-f]+)u?,\s*0x([0-9A-Fa-f]+)u?\s*\}", body)]


class SemaAcquire(unittest.TestCase):
    def test_patch_makes_the_wait_the_default_everywhere(self):
        self.assertTrue(os.path.exists(PATCH), "patch 0085 missing")
        with open(PATCH, encoding="utf-8") as f:
            p = f.read()
        added = "\n".join(ln[1:] for ln in p.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
        removed = "\n".join(ln[1:] for ln in p.splitlines() if ln.startswith("-") and not ln.startswith("---"))
        self.assertIn('blk = e ? atoi(e) : 1;', added)
        self.assertIn('blk = e ? atoi(e) : 0;', removed)          # the old Windows default
        self.assertNotIn("__APPLE__", added)
        self.assertIn('getenv("GCM_SEMA_ACQUIRE")', p)             # GCM_SEMA_ACQUIRE=0 still passes it
        self.assertEqual(sorted(set(re.findall(r"^diff --git a/(\S+) ", p, re.M))), ["libs/video/cellGcmSys.c"])
        # a title whose label counts up may ask for "at or past the value" (both places the walker compares)
        self.assertIn("void cellGcm_set_sema_acquire_geq(int on)", added)
        self.assertIn("(s32)(label - v) >= 0 : label == v", added)
        self.assertIn("gcm_sema_ok(vm_read32(ea), s_sema_wait_val)", added)
        self.assertIn("gcm_sema_ok(vm_read32(la), v)", added)
        self.assertIn("vm_read32(la) == v", removed)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0085-sema-acquire-windows.patch"), names.index("0083-ci-test-shims.patch"))

    def test_rollback_keeps_the_counter_live(self):
        with open(os.path.join(ROOT, "src", "rollback", "rb_state.cpp"), encoding="utf-8") as f:
            src = f.read()
        # Tekken 5 DR's label 0xFD only counts up: a rollback's re-simulated presents step over values
        self.assertRegex(src, r"struct SemaCount \{ SemaCount\(\) \{ cellGcm_set_sema_acquire_geq\(1\); \} \}")
        live = ranges(src, "kKeepLive")
        self.assertIn((COUNTER, 4), live)
        self.assertEqual(live, sorted(live), "kKeepLive must stay sorted by address")
        save = ranges(src, "kSave")
        self.assertTrue(any(a <= COUNTER < a + n for a, n in save), "the counter's page is in the state")
        # neither hash may read it: its value now depends on how many frames this PC re-simulated
        for a, n in ranges(src, "kGame"):
            self.assertFalse(a <= COUNTER < a + n, "in the rollback's gameplay hash")
        with open(os.path.join(ROOT, "src", "netplay", "t5_hooks.cpp"), encoding="utf-8") as f:
            hooks = f.read()
        spec = re.search(r'const char\* kDefaultHash =(.*?);', hooks, re.S).group(1)
        for a, n in re.findall(r'"?([0-9A-Fa-f]{8}):([0-9A-Fa-f]+)', spec):
            self.assertFalse(int(a, 16) <= COUNTER < int(a, 16) + int(n, 16), "in the netplay desync hash")


if __name__ == "__main__":
    unittest.main()
