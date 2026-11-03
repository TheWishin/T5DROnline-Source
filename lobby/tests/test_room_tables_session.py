"""Offline stub-client acceptance session; no listener, sockets or game processes."""
import importlib.util
import os
import sys
import unittest
from unittest.mock import patch

LOBBY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LOBBY)
SPEC = importlib.util.spec_from_file_location(
    "room_tables_session", os.path.join(LOBBY, "tools", "room_tables_session.py"))
SESSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SESSION)


class RoomTablesSessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_stub_clients_exercise_two_tables_without_network_or_game(self):
        forbidden = AssertionError("offline room session attempted network/process startup")
        # The test's asyncio loop already exists before these guards are set.
        # No local server is started: these guards cover accidental regressions
        # towards the process/socket harness used by room_session.py.
        with patch("socket.socket", side_effect=forbidden), \
                patch("socket.create_connection", side_effect=forbidden), \
                patch("socket.getaddrinfo", side_effect=forbidden), \
                patch("subprocess.Popen", side_effect=forbidden), \
                patch.object(SESSION.LobbyServer, "start", side_effect=forbidden):
            summary = await SESSION.run_session()
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["confirmed_games"], 3)
        self.assertEqual(summary["tables"], 3)
        self.assertEqual(summary["members"], 5)
        self.assertEqual(summary["network"], "none")
        self.assertEqual(summary["game_processes"], 0)
        self.assertEqual(len(summary["checks"]), 6)


if __name__ == "__main__":
    unittest.main()
