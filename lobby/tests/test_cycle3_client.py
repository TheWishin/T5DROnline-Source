"""Concurrent personal mute actions without sockets, a server or a game."""
import threading
import unittest
from unittest.mock import Mock

import util  # noqa: F401 -- import path only
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient


class ConcurrentGuestMuteTest(unittest.TestCase):
    def apply_overlapping_actions(self, names, first, second):
        client = LobbyClient("127.0.0.1:7781", BuildInfo("test", "test", "test"), nat2=False)
        client.me = {"name": "Tester", "guest": True}
        client.welcome = {"caps": ["mutes"], "features": ["mutes"]}
        client._set_mute_rows(names, emit=False)
        first_request = threading.Event()
        second_started = threading.Event()
        second_request = threading.Event()
        release_first = threading.Event()
        errors = []

        def request(message):
            if message["name"] == first[0]:
                first_request.set()
                if not release_first.wait(3):
                    raise AssertionError("first action was not released")
            else:
                second_request.set()
            return {"t": "muted"}

        client._call = Mock(side_effect=request)

        def action(args, started=None):
            if started is not None:
                started.set()
            try:
                client.mute(*args)
            except BaseException as error:
                errors.append(error)

        worker1 = threading.Thread(target=action, args=(first,), daemon=True)
        worker2 = threading.Thread(target=action, args=(second, second_started), daemon=True)
        worker1.start()
        try:
            self.assertTrue(first_request.wait(3))
            worker2.start()
            self.assertTrue(second_started.wait(3))
            # The second action must wait before it snapshots the mute list.
            self.assertFalse(second_request.wait(0.1))
        finally:
            release_first.set()
            worker1.join(3)
            if worker2.ident is not None:
                worker2.join(3)
        self.assertFalse(worker1.is_alive())
        self.assertFalse(worker2.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(second_request.is_set())
        return client

    def test_overlapping_unmutes_do_not_restore_removed_names(self):
        client = self.apply_overlapping_actions(["Rival", "Other"],
                                                ("Rival", False), ("Other", False))
        self.assertEqual(client._guest_mutes, [])

    def test_overlapping_mutes_keep_both_choices(self):
        client = self.apply_overlapping_actions([], ("Rival", True), ("Other", True))
        self.assertEqual(client._guest_mutes, ["Rival", "Other"])


if __name__ == "__main__":
    unittest.main()
