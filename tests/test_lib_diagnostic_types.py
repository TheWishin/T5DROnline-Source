"""Check printf argument types in runtime diagnostics without building the runtime."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AudioDiagnosticTypes(unittest.TestCase):
    def test_hresult_hex_argument_matches_unsigned_long_format(self):
        patch = ROOT / "patches" / "ps3recomp" / "0026-audio-device-retry.patch"
        additions = "\n".join(
            line[1:] for line in patch.read_text(encoding="utf-8").splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        calls = re.findall(r'\b(?:f?printf)\([^;]*;', additions, re.DOTALL)
        init_failure = [call for call in calls if "CoInitializeEx failed:" in call]
        self.assertEqual(len(init_failure), 1)
        # HRESULT is signed LONG. %lX consumes unsigned long; the explicit cast
        # also keeps the diagnostic consistent with the other WASAPI failures.
        self.assertIn("%08lX", init_failure[0])
        self.assertRegex(init_failure[0], r",\s*\(unsigned long\)\s*hr\s*\);")


if __name__ == "__main__":
    unittest.main()
