"""Read-only source contracts for replay compatibility/publication audit fixes.

Native behavior lives in c/replay_publish_test.cpp and c/replay_test.cpp; running
those harnesses requires a maintainer-authorized compiler and is not done here.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReplayAuditContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "src/netplay/replay.cpp").read_text(encoding="utf-8-sig")

    def test_new_recordings_always_version_the_changed_input_policy(self):
        self.assertIn("constexpr uint32_t kVersion = 8;", self.source)
        start = self.source.index("uint32_t rules_version(")
        end = self.source.index("std::vector<uint8_t> to_binary", start)
        policy = self.source[start:end]
        self.assertIn("return kVersion;", policy)
        self.assertNotIn("return 5", policy)
        self.assertIn("put32(b, rules_version(d) - 4);", self.source)
        self.assertIn("rules_version(st.d) > st.live_rules_version", self.source)

    def test_legacy_policy_is_captured_per_match_and_normal_play_is_guarded(self):
        self.assertIn("m.soft_reset_guard = ver >= 7;", self.source)
        self.assertIn("m.soft_reset_guard = d.matches[k].soft_reset_guard;", self.source)
        self.assertIn("m.ft.rules = d.matches[k].ft.rules;", self.source)
        start = self.source.index("bool play_soft_reset_guard()")
        end = self.source.index("void play_set_quit_poll", start)
        policy = self.source[start:end]
        self.assertIn("if (!p.on) return true;", policy)
        self.assertIn("return p.d.matches[index].soft_reset_guard;", policy)
        self.assertIn("return p.d.version >= 7;", policy)

    def test_live_upgrades_require_guard_and_never_downgrade(self):
        self.assertIn("if (match_version > p.live_match_version && !p.live_rules_guard) return false;", self.source)
        self.assertIn("if (p.live_rules_guard && match_version <= p.live_match_version) return false;", self.source)
        self.assertIn("if (match_version < p.live_match_version) return false;", self.source)

    def test_all_replay_paths_preserve_overlay_and_unicode_process_environment(self):
        core = (ROOT / "src/netplay/netplay_core.cpp").read_text(encoding="utf-8-sig")
        header = (ROOT / "src/netplay/netplay.h").read_text(encoding="utf-8-sig")
        self.assertIn("std::string path_environment(const char* key);", header)
        self.assertIn("std::string path_environment(const char* key) { return path_env(key); }", core)
        start = core.index("std::string path_env(")
        end = core.index("/* What decides this PC's floating-point results", start)
        accessor = core[start:end]
        self.assertIn("g_env_over.find(env_key(k))", accessor)
        self.assertIn("it->second.first ? it->second.second : std::string()", accessor)
        self.assertIn("return replay_paths::env(k);", accessor)
        for key in ("DIR", "LIVE", "STATUS", "RESULT"):
            self.assertIn('np::path_environment("T5_REPLAY_' + key + '")', self.source)
            self.assertNotIn('t5_env("T5_REPLAY_' + key + '")', self.source)
            self.assertNotIn('replay_paths::env("T5_REPLAY_' + key + '")', self.source)
    def test_live_replay_paths_use_local_wide_shared_handle_wrappers(self):
        paths = (ROOT / "src/netplay/replay_paths.h").read_text(encoding="utf-8-sig")
        self.assertIn("replay_paths::open_read_shared(path)", self.source)
        self.assertIn("replay_paths::create_write_shared(live, &busy)", self.source)
        self.assertNotIn("t5p_open_read_shared(", self.source)
        self.assertNotIn("t5p_create_write_shared(", self.source)
        self.assertIn("HANDLE h = CreateFileW(p.c_str(), GENERIC_READ,", paths)
        self.assertIn("HANDLE h = CreateFileW(p.c_str(), GENERIC_WRITE,", paths)
        self.assertIn("FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE", paths)
        self.assertIn("ERROR_SHARING_VIOLATION", paths)
        self.assertIn("return t5p_open_read_shared(path);", paths)
        self.assertIn("return t5p_create_write_shared(path, busy);", paths)
    def test_replay_write_success_depends_on_atomic_publication(self):
        start = self.source.index("void write_store(")
        end = self.source.index("/* ---- the live stream", start)
        writer = self.source[start:end]
        self.assertIn("if (ok) ok = detail::publish_retry(", writer)
        self.assertIn("return replay_paths::replace(tmp.c_str(), st->path.c_str()) != 0;", writer)
        self.assertLess(writer.index("ok = detail::publish_retry("), writer.index('ok ? "written"'))
        self.assertIn('#include "replay_publish.h"', self.source)


if __name__ == "__main__":
    unittest.main()
