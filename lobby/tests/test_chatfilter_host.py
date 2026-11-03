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


if __name__ == "__main__":
    unittest.main()
