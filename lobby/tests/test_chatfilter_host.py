"""Host startup configuration errors use the existing launcher error event; no sockets."""
import unittest
from types import SimpleNamespace
from unittest import mock

import util  # noqa: F401 (sets sys.path)
from t5lobby.server import host


class HostPolicyErrorTest(unittest.TestCase):
    def make_host(self):
        return host.Host(SimpleNamespace(data="test-host-data", json=True, no_tls=True,
                                         port=7781, udp_port2=None, status_port=0,
                                         motd="", guests_only=False))

    def test_invalid_or_missing_policy_reports_error_without_starting(self):
        for failure in (ValueError("invalid chat filter policy"),
                        OSError("missing chat filter policy")):
            with self.subTest(failure=type(failure).__name__):
                instance = self.make_host()
                loop = mock.Mock()
                with mock.patch.object(host.os, "makedirs"), \
                     mock.patch.object(host.Config, "from_env", return_value=SimpleNamespace()), \
                     mock.patch("t5lobby.server.__main__.setup_logging"), \
                     mock.patch.object(host.proto, "new_event_loop", return_value=loop), \
                     mock.patch.object(host.asyncio, "set_event_loop"), \
                     mock.patch.object(host, "LobbyServer", side_effect=failure) as server, \
                     mock.patch.object(instance, "say") as say, \
                     mock.patch.object(instance, "event") as event:
                    self.assertEqual(instance.run(), 2)
                server.assert_called_once()
                loop.run_until_complete.assert_not_called()
                loop.close.assert_called_once_with()
                event.assert_called_once_with("error", message=str(failure))
                say.assert_called_once_with(str(failure))

    def test_invalid_environment_reports_error_before_creating_loop(self):
        instance = self.make_host()
        failure = ValueError("invalid configuration value")
        with mock.patch.object(host.os, "makedirs"), \
             mock.patch.object(host.Config, "from_env", side_effect=failure), \
             mock.patch.object(host.proto, "new_event_loop") as loop, \
             mock.patch.object(host, "LobbyServer") as server, \
             mock.patch.object(instance, "say") as say, \
             mock.patch.object(instance, "event") as event:
            self.assertEqual(instance.run(), 2)
        loop.assert_not_called()
        server.assert_not_called()
        event.assert_called_once_with("error", message=str(failure))
        say.assert_called_once_with(str(failure))


class HostWithoutTermListTest(unittest.TestCase):
    """The player's release zip has no lobby/t5lobby/server/data/chat_filter_terms.json (package_release leaves it
    out): Host for friends must still start there (1.2.0's release zip: 'Cannot load the chat filter', exit 2)."""

    def make_host(self):
        return host.Host(SimpleNamespace(data="test-host-data", json=True, no_tls=True, port=7781, udp_port2=None,
                                         status_port=0, motd="", guests_only=False))

    def test_no_list_in_the_release_runs_without_the_filter(self):
        h = self.make_host()
        with mock.patch.object(host.os.path, "isfile", return_value=False), mock.patch.object(h, "say") as say:
            self.assertEqual(h.chat_filter_policy({}), {"chat_filter": False})
        say.assert_called_once()

    def test_list_present_keeps_the_default(self):
        h = self.make_host()
        with mock.patch.object(host.os.path, "isfile", return_value=True):
            self.assertEqual(h.chat_filter_policy({}), {})

    def test_asked_for_explicitly_still_fails_closed(self):
        h = self.make_host()
        for env in ({"T5L_CHAT_FILTER": "1"}, {"T5L_CHAT_FILTER_PATH": "missing.json"}):
            with self.subTest(env=env), mock.patch.object(host.os.path, "isfile", return_value=False):
                self.assertEqual(h.chat_filter_policy(env), {})

    def test_server_starts_with_the_policy(self):
        """The policy reaches Config: a LobbyServer with a missing list path and the policy applied constructs."""
        from t5lobby.server.config import Config
        from t5lobby.server.lobby import LobbyServer
        cfg = Config(db=":memory:", chat_filter_path="no-such-dir/none.json", chat_filter=False)
        srv = LobbyServer(cfg)
        self.assertFalse(srv.chat_filter.blocked("anything"))
        srv.store.close()
        with self.assertRaises(ValueError):
            LobbyServer(Config(db=":memory:", chat_filter_path="no-such-dir/none.json"))


if __name__ == "__main__":
    unittest.main()
