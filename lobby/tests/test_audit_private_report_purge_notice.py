"""The guest-match purge must not claim guest report content is never stored."""
import contextlib
import io
import unittest
from unittest import mock

import util  # noqa: F401 -- adds the lobby import path only
from t5lobby.server import admin


class GuestPurgeNoticeTest(unittest.TestCase):
    def test_match_purge_discloses_separate_private_report_retention(self):
        store = mock.Mock()
        store.purge_guest_matches.return_value = 3
        output = io.StringIO()
        with mock.patch.object(admin, "_open", return_value=store), contextlib.redirect_stdout(output):
            self.assertEqual(admin.main(["purge-guests", "--days", "14"]), 0)
        store.purge_guest_matches.assert_called_once_with(14)
        self.assertIn("deleted 3 guest-only match record(s)", output.getvalue())
        self.assertIn("private reports are retained separately", output.getvalue())
        self.assertNotIn("guests themselves are never stored", output.getvalue())


if __name__ == "__main__":
    unittest.main()
