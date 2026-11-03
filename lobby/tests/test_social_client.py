"""1.2.0 client negotiation and metadata, without sockets, servers or a game."""
import asyncio
import unittest
from unittest import mock

import util  # noqa: F401 -- repository import path only; no server is started
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient


class SocialClientTest(unittest.TestCase):
    def client(self, **kwargs):
        return LobbyClient("127.0.0.1:7781", BuildInfo("test", "test", "test"), **kwargs)

    def test_both_sides_must_negotiate_each_feature(self):
        c = self.client()
        for welcome in (None, {}, {"features": ["badges", "mentions"]},
                        {"caps": ["badges", "mentions"]}):
            c.welcome = welcome
            self.assertFalse(c.badges_ok())
            self.assertFalse(c.mentions_ok())
        c.welcome = {"features": ["badges", "mentions"], "caps": ["badges", "mentions"]}
        self.assertTrue(c.badges_ok())
        self.assertTrue(c.mentions_ok())
        c.badges = c.mentions = False
        self.assertFalse(c.badges_ok())
        self.assertFalse(c.mentions_ok())

    def test_hello_announces_caps_without_changing_legacy_order(self):
        async def hello(**kwargs):
            c = self.client(**kwargs)
            writer = mock.Mock()
            writer.get_extra_info.side_effect = lambda key: ("127.0.0.1", 7781) if key == "peername" else None
            request = mock.AsyncMock(return_value={"t": "welcome"})
            with mock.patch("t5lobby.client.asyncio.open_connection", mock.AsyncMock(return_value=(None, writer))), \
                    mock.patch.object(c, "_read_loop", mock.AsyncMock()), \
                    mock.patch.object(c, "_request", request):
                await c._connect(1)
                await asyncio.gather(*c._tasks)
            return request.call_args.args[0]["caps"]

        enabled = asyncio.run(hello())
        legacy = asyncio.run(hello(badges=False, mentions=False))
        self.assertEqual([cap for cap in enabled if cap not in ("badges", "mentions")], legacy)
        self.assertEqual([cap for cap in enabled if cap in ("badges", "mentions")], ["badges", "mentions"])
        self.assertLessEqual(len(enabled), 32)

    def test_chat_sends_text_only(self):
        c = self.client()
        with mock.patch.object(c, "_fire") as fire:
            c.chat("hi @Rival")
        fire.assert_called_once_with({"t": "chat", "text": "hi @Rival"})

    def test_roster_delta_keeps_server_badge_and_clears_it(self):
        async def updates():
            c = self.client()
            c.me = {"id": "p1"}
            row = {"id": "p1", "name": "Tester", "badge": "dev", "status": "idle"}
            await c._on_lobby_state({"players": [row]})
            self.assertEqual(c.me["badge"], "dev")
            await c._on_lobby_delta({"players": [dict(row, badge="")]})
            self.assertEqual(c.players[0]["badge"], "")
            self.assertEqual(c.me["badge"], "")
        asyncio.run(updates())


if __name__ == "__main__":
    unittest.main()
