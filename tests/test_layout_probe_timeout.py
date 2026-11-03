"""Keep native layout-child hangs bounded and retain every thread's stack."""
import unittest
from unittest import mock

import test_layout_lobby_entry as entry


class LayoutProbeTimeout(unittest.TestCase):
    def test_native_walk_hang_keeps_all_thread_stacks(self):
        original = "    screen(walk, name, top)"
        self.assertEqual(entry.PROBE.count(original), 1)
        blocked = original + r'''
    print("native layout screen reached", flush=True)
    def blocked_layout_worker():
        threading.Event().wait()
    threading.Thread(target=blocked_layout_worker, daemon=True).start()
    threading.Event().wait()
'''
        probe = entry.PROBE.replace(original, blocked)
        case = entry.LobbyLayoutEntry()
        with mock.patch.object(entry, "PROBE", probe), \
                mock.patch.object(entry, "PROBE_TIMEOUT", 20), \
                mock.patch.object(entry, "PROBE_STACK_DELAY", 15):
            with self.assertRaises(AssertionError) as caught:
                case.run_layout("pt-BR", 100)
        output = str(caught.exception)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertIn("native layout screen reached", output)
        self.assertIn("Timeout", output)
        self.assertIn("blocked_layout_worker", output)
        self.assertIn("in observe", output)


if __name__ == "__main__":
    unittest.main()
