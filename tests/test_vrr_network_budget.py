"""Host-only VRR budget exclusion wiring. No game, socket or compiler is needed.

Behavioral accounting checks also live in tests/c/netplay_fuzz.cpp. These source
checks protect the important ordering before a possibly blocking network wait;
they do not prove runtime scheduling or pair determinism.
"""
import os
import unittest

from helpers import ROOT


def read(relative):
    with open(os.path.join(ROOT, *relative.split("/")), encoding="utf-8") as stream:
        return stream.read()


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    for end in range(opening + 1, len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            return source[opening + 1:end]
    raise AssertionError("unclosed function " + signature)


class NetworkBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read("src/netplay/netplay_core.cpp")

    def test_online_accounting_excludes_even_zero_wait_samples(self):
        body = function(self.source, "void account_frame(uint64_t wait_us)")
        self.assertIn("if (s.mode == Mode::Host || s.mode == Mode::Join) cellGcm_vrr_external_hold();", body)
        self.assertNotIn("if (wait_us)", body)
        self.assertIn("account_frame(wait_us);", function(self.source, "void rb_account_frame(uint64_t wait_us)"))

    def test_lockstep_tags_before_handshake_and_input_waits(self):
        body = function(self.source, "void begin_frame(uint32_t f,")
        marker = body.index("cellGcm_vrr_external_hold();")
        self.assertLess(marker, body.index("wait_connected();"))
        self.assertLess(marker, body.index("WaitForSingleObject(s.rx_event, 4);"))
        self.assertLess(body.index("if (s.mode == Mode::Off) return;"), marker)

    def test_scene_tags_only_after_local_and_replay_paths_before_wait(self):
        body = function(self.source, "uint32_t scene_barrier(uint32_t f)")
        marker = body.index("cellGcm_vrr_external_hold();")
        self.assertLess(body.index("s.mode == Mode::Local || s.mode == Mode::Off"), marker)
        self.assertLess(body.index("if (replay) return rp::play_barrier"), marker)
        self.assertLess(marker, body.index("WaitForSingleObject(s.rx_event, 2);"))

    def test_standalone_parser_test_links_and_checks_runtime_observer(self):
        test = read("tests/c/netplay_fuzz.cpp")
        self.assertIn('extern "C" void cellGcm_vrr_external_hold(void)', test)
        self.assertIn("check_vrr_budget_excludes_online_frames();", test)
        self.assertIn("account_frame(0);", test)
        self.assertIn("rb_account_frame(18000);", test)


if __name__ == "__main__":
    unittest.main()
