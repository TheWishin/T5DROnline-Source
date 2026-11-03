"""Casual FT targets: pure protocol checks, with no game or server connection."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t5lobby import proto


class FirstToValidation(unittest.TestCase):
    def test_exact_supported_targets(self):
        self.assertEqual(proto.CASUAL_FIRST_TO, (1, 2, 3, 5, 10))
        for value in proto.CASUAL_FIRST_TO:
            with self.subTest(value=value):
                self.assertEqual(proto.casual_first_to(value), value)

    def test_rejects_unsupported_or_coerced_targets(self):
        for value in (None, False, True, 0, -1, 4, 6, 11, 1000000, 1.0, 2.5, "2", [], {}):
            with self.subTest(value=value):
                with self.assertRaises(proto.LobbyError) as raised:
                    proto.casual_first_to(value)
                self.assertEqual(raised.exception.code, proto.E_BAD_REQUEST)


if __name__ == "__main__":
    unittest.main()
