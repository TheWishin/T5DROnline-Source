"""Source guards for Unicode replay paths, without a compiler or game data.

The Windows executable still needs a real recording/playback test in a folder
with spaces and characters outside the Windows ANSI code page. These guards
catch narrow file/environment APIs reappearing in that path; they do not run
the C++ code or prove its compilation.
"""
import os
import re
import unittest

from helpers import ROOT


def source(relative):
    with open(os.path.join(ROOT, relative), encoding="utf-8") as f:
        return f.read()


class UnicodeReplayPaths(unittest.TestCase):
    def test_recording_and_playback_have_no_ansi_file_boundaries(self):
        code = source("src/netplay/replay.cpp")
        # Recording, rollback header detection, playback and its verdict must
        # all reach the wide wrappers, including temporary-file replacement.
        self.assertNotRegex(code, r"\bfopen\s*\(")
        self.assertNotRegex(code, r"\bCreateDirectoryA\s*\(")
        self.assertNotRegex(code, r"\bt5p_replace_file\s*\(")
        self.assertNotRegex(code, r'(?<![:\w])env\("T5_REPLAY_(?:DIR|RESULT|STATUS)"\)')

    def test_both_playback_entry_points_read_unicode_environment(self):
        core = source("src/netplay/netplay_core.cpp")
        rollback = source("src/rollback/rb_net.cpp")
        self.assertNotRegex(core, r'(?<!\w)env\("T5_REPLAY_FILE"\)')
        self.assertNotIn('getenv("T5_REPLAY_FILE")', rollback)
        # The process fallback must not discard a persistent game's overlay:
        # that overlay already contains UTF-8 and may explicitly unset a key.
        helper = re.search(r"std::string path_env\(const char\* k\)\s*\{(.*?)\n\}", core, re.S)
        self.assertIsNotNone(helper)
        self.assertIn("g_env_over.find(env_key(k))", helper.group(1))
        self.assertIn("it->second.first ? it->second.second", helper.group(1))
        self.assertIn("replay_paths::env(k)", helper.group(1))

    def test_windows_conversions_preserve_utf8_and_use_wide_io(self):
        code = source("src/netplay/replay_paths.h")
        for api in ("GetEnvironmentVariableW", "MultiByteToWideChar", "WideCharToMultiByte",
                    "_wfopen", "CreateDirectoryW", "MoveFileExW"):
            self.assertIn(api + "(", code)
        self.assertIn("CP_UTF8, MB_ERR_INVALID_CHARS", code)
        self.assertIn("CP_UTF8, WC_ERR_INVALID_CHARS", code)
        self.assertIn("MOVEFILE_REPLACE_EXISTING", code)
        self.assertNotRegex(code, r"\b(?:GetEnvironmentVariableA|MoveFileExA|CP_ACP)\b")

    def test_posix_file_operations_keep_the_platform_boundary(self):
        code = source("src/netplay/replay_paths.h")
        self.assertRegex(code, r"#else\s+const char\* value = getenv\(key\)")
        self.assertRegex(code, r"#else\s+return path \? fopen\(path, mode\) : nullptr;")
        self.assertRegex(code, r"#else\s+return t5p_replace_file\(from, to\);")


if __name__ == "__main__":
    unittest.main()
