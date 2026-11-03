"""Room table wire values: pure checks, without a game or a server connection."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t5lobby import proto


class RoomTableValidation(unittest.TestCase):
    def test_pairing_modes(self):
        self.assertEqual(proto.ROOM_MODES, ("line", "tables"))
        for value in proto.ROOM_MODES:
            with self.subTest(value=value):
                self.assertEqual(proto.room_mode(value), value)

    def test_pairing_mode_is_not_coerced(self):
        for value in (None, False, True, 0, "", "queue", "TABLES", "winner", [], {}):
            with self.subTest(value=value):
                with self.assertRaises(proto.LobbyError) as caught:
                    proto.room_mode(value)
                self.assertEqual(caught.exception.code, proto.E_BAD_REQUEST)

    def test_table_number_within_room_limit(self):
        for maximum in (1, 2, 4, 16):
            for value in range(1, maximum + 1):
                with self.subTest(maximum=maximum, value=value):
                    self.assertEqual(proto.room_table(value, maximum), value)

    def test_table_number_rejects_invalid_or_coerced_values(self):
        for value in (None, False, True, 0, -1, 5, 1000000, 1.0, 2.5, "1", [], {}):
            with self.subTest(value=value):
                with self.assertRaises(proto.LobbyError) as caught:
                    proto.room_table(value, 4)
                self.assertEqual(caught.exception.code, proto.E_BAD_REQUEST)


if __name__ == "__main__":
    unittest.main()
