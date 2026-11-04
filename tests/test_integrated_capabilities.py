"""Combined 1.2.0 negotiations and commands; fake transport only, no server/game/build."""
import asyncio
import os
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "lobby"))
from t5lobby import proto
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient
from t5lobby.compatibility import BuildGroups
from t5lobby.server.config import Config
from t5lobby.server.lobby import LobbyServer


LEGACY = ["delta", "notices", "blind_ready", "old_stages", "ingame_pick", "sets",
          "nat2", "relays", "friends", "tournaments", "spectate", "private_rooms",
          "game_fallback", "boss_chars", "lag_wait", "match_rules"]
ADDED = ["life150", "input_delay8", "badges", "mentions", "ranked_chars", "casual_sets",
         "room_tables", "ingame_rematch_v1", "auto_skip_after_round_v1", "auto_skip_intro_v1", "compat_groups",
         "private_chat", "mutes"]


def client(**options):
    enabled = dict(blind_ready=True, ingame_pick=True, sets=True, tournaments=True,
                   spectate=True, match_rules=True, life150=True, ingame_rematch=True,
                   auto_skip_after_round=True, auto_skip_intro=True, tcp_fallback_port=443)
    enabled.update(options)
    return LobbyClient("127.0.0.1:7781", BuildInfo("test", "test", "test"), **enabled)


def negotiated(c):
    c.welcome = {"features": ["challenges2", "input_delay8", "casual_sets", "room_tables", "private_rooms"],
                 "caps": ["input_delay8", "sets", "casual_sets", "room_tables", "private_rooms",
                          "ingame_rematch_v1", "auto_skip_after_round_v1"],
                 "ingame_rematch": {"v": 1}}
    c._pmap = {"peer": {"id": "peer", "input_delay8": True}}
    c._call = mock.Mock(return_value={"challenge": "c1", "room": {"id": "r1"}})
    return c


class IntegratedCapabilities(unittest.IsolatedAsyncioTestCase):
    async def hello(self, c):
        writer = mock.Mock()
        writer.get_extra_info.side_effect = lambda key: ("127.0.0.1", 7781) if key == "peername" else None
        request = mock.AsyncMock(return_value={"t": "welcome", "caps": []})
        with mock.patch("t5lobby.client.asyncio.open_connection", mock.AsyncMock(return_value=(None, writer))), \
                mock.patch.object(c, "_request", request), mock.patch.object(c, "_read_loop", mock.AsyncMock()):
            await c._connect(1)
            await asyncio.gather(*c._tasks)
        return request.call_args.args[0]

    async def test_all_features_survive_the_server_cap_limit_with_legacy_prefix(self):
        hello = await self.hello(client())
        caps = hello["caps"]
        self.assertEqual(caps[:16], LEGACY)
        self.assertEqual(caps[16:], ADDED)
        self.assertEqual(len(caps), len(set(caps)))
        self.assertLessEqual(len(caps), 32)
        # Exercise the actual hello handler without constructing network services.
        server = SimpleNamespace(cfg=Config(ingame_rematch=True, auto_skip=True), latest_release="",
                                 build_groups=BuildGroups(),
                                 release_cache=SimpleNamespace(public=lambda _: None),
                                 udp=SimpleNamespace(port=7781, port2=7782),
                                 relays=SimpleNamespace(public_list=lambda: []),
                                 tours=SimpleNamespace(welcome=lambda: {}),
                                 _casual_welcome=lambda _: {}, _rematch_enabled=lambda: True,
                                 reports_on=lambda: False, reports_welcome=lambda _: {})   # 1.3.0: problem reports (reports.py)
        conn = SimpleNamespace(player=None, ip="127.0.0.1", writer=mock.Mock())
        conn.writer.get_extra_info.return_value = None
        welcome = await LobbyServer.h_hello(server, conn, hello)
        self.assertEqual(set(welcome["caps"]), set(caps))
        self.assertEqual(welcome["ingame_rematch"]["v"], 1)
        # 1.2.0: a default server takes the round-skip consent cap (each match still needs both players' box) and
        # the intro-skip cap; T5L_AUTO_SKIP=0 / T5L_AUTO_SKIP_INTRO=0 drop them.
        server.cfg = Config()
        welcome = await LobbyServer.h_hello(server, SimpleNamespace(player=None, ip="127.0.0.1", writer=conn.writer),
                                            hello)
        self.assertEqual(set(welcome["caps"]), set(caps))
        self.assertEqual(welcome["ingame_rematch"]["v"], 1)            # the in-game rematch question is on
        server.cfg = Config(auto_skip=False, auto_skip_intro=False)
        welcome = await LobbyServer.h_hello(server, SimpleNamespace(player=None, ip="127.0.0.1", writer=conn.writer),
                                            hello)
        self.assertEqual(set(welcome["caps"]), set(caps) - {"auto_skip_after_round_v1", "auto_skip_intro_v1"})

    async def test_optional_caps_can_be_disabled_without_reordering_other_caps(self):
        enabled = (await self.hello(client()))["caps"]
        disabled = (await self.hello(client(input_delay8=False, badges=False, mentions=False,
                                          casual_sets=False, room_tables=False,
                                          ingame_rematch=False, auto_skip_after_round=False,
                                          auto_skip_intro=False, private_chat=False)))["caps"]
        removed = {"input_delay8", "badges", "mentions", "casual_sets", "room_tables",
                   "ingame_rematch_v1", "auto_skip_after_round_v1", "auto_skip_intro_v1", "private_chat"}
        self.assertEqual(disabled, [cap for cap in enabled if cap not in removed])
        self.assertEqual(disabled[:16], LEGACY)

    async def test_version_refusal_retains_release_metadata_and_never_retries_tcp(self):
        c = client(tls=True)
        self.assertEqual(c._tcp_ports(), [7781, 443])
        writer = mock.Mock()
        writer.wait_closed = mock.AsyncMock()
        writer.get_extra_info.side_effect = lambda key: ("127.0.0.1", 7781) if key == "peername" else None
        metadata = {"tag_name": "v1.2.0"}
        refused = proto.LobbyError(proto.E_VERSION, "build refused", latest_release=metadata)
        with mock.patch("t5lobby.client.asyncio.open_connection", mock.AsyncMock(return_value=(None, writer))) as opening, \
                mock.patch("t5lobby.client.ssl.create_default_context", return_value=mock.Mock()), \
                mock.patch.object(c, "_request", mock.AsyncMock(side_effect=refused)), \
                mock.patch.object(c, "_read_loop", mock.AsyncMock()):
            with self.assertRaises(proto.LobbyError) as raised:
                await c._connect(1)
        self.assertIs(raised.exception, refused)
        self.assertEqual(raised.exception.extra["latest_release"], metadata)
        opening.assert_awaited_once()
        writer.close.assert_called_once()
        self.assertFalse(c.connected)


class IntegratedCommands(unittest.TestCase):
    def test_first_to_and_extended_delay_share_one_challenge(self):
        c = negotiated(client())
        c.send_challenge("peer", 8, 5)
        c._call.assert_called_once_with({"t": "challenge", "player": "peer", "delay": 8, "first_to": 5})
        c._call.reset_mock()
        c._pmap["peer"].pop("input_delay8")
        with self.assertRaises(proto.LobbyError):
            c.send_challenge("peer", 8, 5)
        c._call.assert_not_called()
        c.welcome = {"features": ["challenges2"], "caps": []}
        c.send_challenge("peer", 2, 5)
        c._call.assert_called_once_with({"t": "challenge", "player": "peer", "delay": 2})

    def test_table_room_keeps_first_to_and_classic_room_keeps_rematch_options(self):
        c = negotiated(client())
        c.create_room("Tables", size=6, first_to=3, mode="tables")
        message = c._call.call_args.args[0]
        self.assertEqual((message["mode"], message["first_to"], message["size"]), ("tables", 3, 6))
        self.assertNotIn("rematch_policy", message)
        c.create_room("Pair", first_to=5, rematch_policy="auto_unless_declined", auto_skip_after_round=True)
        message = c._call.call_args.args[0]
        self.assertEqual(message["first_to"], 5)
        self.assertEqual(message["rematch_policy"], "auto_unless_declined")
        self.assertTrue(message["auto_skip_after_round"])
        self.assertNotIn("mode", message)


if __name__ == "__main__":
    unittest.main()
