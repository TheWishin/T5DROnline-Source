"""1.2.0 chat filter / admin mute: the launcher's Send must tell the sender why a lobby line was refused.

Before: tk_tab.do_chat sent the line with the fire-and-forget LobbyClient.chat(); the server's refusal came back as
an error without a request id, the launcher never showed it, and the sender's line just vanished (found by the
1.2.0 opt-in check, e2e chat_private_120)."""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import util  # noqa: E402
from t5lobby import tk_tab  # noqa: E402
from t5lobby.proto import LobbyError  # noqa: E402


class ChatRefusalTest(unittest.TestCase):
    def setUp(self):
        self.server = util.ServerThread().start()
        self.addCleanup(self.server.stop)
        self.server.call(lambda: setattr(self.server.srv.chat_filter, "blocked", lambda text: "zzbadword" in text))
        self.a = util.client(self.server, "Alice")
        self.b = util.client(self.server, "Bob")
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)

    def test_refused_line_raises_for_the_sender(self):
        with self.assertRaises(LobbyError) as cm:
            self.a.chat_checked("you zzbadword")
        self.assertIn("blocked", cm.exception.msg.lower())

    def test_accepted_line_still_reaches_the_others(self):
        self.a.chat_checked("hello there")
        ev = util.expect(self.b, "chat")
        self.assertEqual(ev["text"], "hello there")

    def test_send_button_uses_the_checked_request(self):
        src = inspect.getsource(tk_tab.OnlineTab.do_chat)
        self.assertIn("chat_checked", src)
        self.assertNotIn("self.client.chat,", src)


if __name__ == "__main__":
    unittest.main()
