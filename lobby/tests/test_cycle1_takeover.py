"""Account takeover preserves a running connection until its replacement is valid."""
from types import SimpleNamespace
import unittest
from unittest import mock

import util  # noqa: F401 (sets sys.path)
from t5lobby import proto
from t5lobby.server.lobby import LobbyServer


def immediate(coro):
    """These login paths do no I/O and need no event loop or sockets."""
    try:
        coro.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coro.close()
    raise AssertionError("handler unexpectedly waited for I/O")


class RunningTakeoverTest(unittest.TestCase):
    def fixture(self, between_games=False):
        srv = object.__new__(LobbyServer)
        srv.cfg = SimpleNamespace(accounts=True, session_days=30)
        srv.login_fail = mock.Mock()
        srv.store = mock.Mock()
        srv.store.session_account.return_value = {"id": 1, "name": "Alice"}
        srv._refuse_banned = mock.Mock()
        srv._good_login = mock.Mock()
        srv._between_set_games = mock.Mock(return_value=between_games)
        live = SimpleNamespace(player=None, close=mock.Mock())
        player = SimpleNamespace(account_id=1, match=None if between_games else SimpleNamespace(state="playing"),
                                 conn=live, build_id="same-build", compat_group="approved", token="resume-token",
                                 session="old-session", send=mock.Mock())
        live.player = player
        srv.by_name = {"alice": player}
        srv.sessions = {player.token: player}
        replacement = SimpleNamespace(helloed=True, closed=False, player=None, akey="fake-address",
                                      build_id="same-build", compat_group="approved")
        return srv, player, live, replacement

    def test_rejected_replacement_does_not_kick_running_player(self):
        for between_games in (False, True):
            for build, group in (("other-build", "approved"), ("same-build", "")):
                with self.subTest(between_games=between_games, build=build, group=group):
                    srv, player, live, replacement = self.fixture(between_games)
                    replacement.build_id, replacement.compat_group = build, group
                    with self.assertRaises(proto.LobbyError) as caught:
                        immediate(srv.h_login(replacement, {"mode": "session", "session": "saved-token"}))
                    self.assertEqual(caught.exception.code, proto.E_VERSION)
                    self.assertIs(player.conn, live)
                    self.assertIs(live.player, player)
                    live.close.assert_not_called()
                    player.send.assert_not_called()
                    self.assertEqual(player.session, "old-session")
                    self.assertIsNone(replacement.player)

    def test_valid_takeover_still_closes_previous_connection(self):
        srv, player, live, replacement = self.fixture()
        srv._resume = mock.Mock(return_value={"t": "login_ok"})
        result = immediate(srv.h_login(replacement, {"mode": "session", "session": "saved-token"}))
        self.assertEqual(result["t"], "login_ok")
        self.assertEqual(result["session"], "saved-token")
        player.send.assert_called_once_with({"t": "kicked", "reason": "logged in from another place"})
        live.close.assert_called_once_with()
        self.assertIsNone(live.player)
        srv._resume.assert_called_once_with(replacement, "resume-token")


if __name__ == "__main__":
    unittest.main()
