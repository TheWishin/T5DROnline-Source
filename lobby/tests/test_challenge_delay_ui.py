"""1.2.0 challenge delay: offline client and picker checks, with no socket or game.

The wider choices and Auto curve require the negotiated input_delay8 cap. An older server keeps its old choices,
including when this launcher remembered a high setting from another server. Settings and ranked are separate.
"""
import asyncio
from types import SimpleNamespace
import unittest
from unittest import mock

import util  # noqa: F401  (lobby import path only; no ServerThread is started)
from t5lobby import proto, tk_challenges
from t5lobby.client import LobbyClient


def welcome(extended=True):
    return {"features": ["challenges2"] + (["input_delay8"] if extended else []),
            "caps": ["input_delay8"] if extended else []}


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class ChallengeDelayClient(unittest.TestCase):
    def client(self, extended=True, **kw):
        c = LobbyClient("127.0.0.1:1", SimpleNamespace(as_wire=lambda: {}), **kw)
        c.welcome = welcome(extended)
        c._pmap = {"opponent": {"id": "opponent", "input_delay8": True}}
        c._call = mock.Mock(side_effect=lambda msg: msg)
        return c

    def test_manual_zero_through_eight(self):
        c = self.client()
        self.assertEqual(c.challenge_delay_max(), 8)
        for n in range(9):
            self.assertEqual(c.send_challenge("opponent", n), {"t": "challenge", "player": "opponent", "delay": n})
        self.assertNotIn("delay", c.send_challenge("opponent"))

    def test_old_server_and_missing_negotiation(self):
        for w in (welcome(False), {"features": ["challenges2", "input_delay8"], "caps": []},
                  {"features": ["challenges2"], "caps": ["input_delay8"]}):
            c = self.client()
            c.welcome = w
            self.assertEqual(c.challenge_delay_max(), 2)
            self.assertEqual(c.send_challenge("opponent", 2)["delay"], 2)
            c._call.reset_mock()
            with self.assertRaises(proto.LobbyError) as caught:
                c.send_challenge("opponent", 8)
            self.assertEqual(caught.exception.code, proto.E_NOT_ALLOWED)
            c._call.assert_not_called()
        c = self.client(input_delay8=False)
        self.assertEqual(c.challenge_delay_max(), 2)
        c = self.client()
        c.welcome = {"features": [], "caps": []}       # before challenge delay choices existed
        self.assertNotIn("delay", c.send_challenge("opponent", 2))
        with self.assertRaises(proto.LobbyError):
            c.send_challenge("opponent", 8)

    def test_old_or_unknown_opponent_keeps_two(self):
        c = self.client()
        for peer in ({"id": "opponent"}, {"id": "opponent", "input_delay8": False},
                     {"id": "opponent", "input_delay8": 1}):
            c._pmap["opponent"] = peer
            self.assertEqual(c.challenge_delay_max(), 8)
            self.assertEqual(c.challenge_delay_max("opponent"), 2)
            with self.assertRaises(proto.LobbyError):
                c.send_challenge("opponent", 8)
        self.assertEqual(c.challenge_delay_max("missing"), 2)
        c._pmap["opponent"]["input_delay8"] = True
        self.assertEqual(c.challenge_delay_max("opponent"), 8)
        self.assertEqual(c.send_challenge("opponent", 8)["delay"], 8)

    def test_invalid_delay_precedes_cap_check(self):
        for extended in (True, False):
            c = self.client(extended)
            c._pmap.clear()
            for n in (-1, 9):
                with self.assertRaises(proto.LobbyError) as caught:
                    c.send_challenge("opponent", n)
                self.assertEqual(caught.exception.code, proto.E_BAD_REQUEST)
                self.assertEqual(caught.exception.msg, "bad field: delay")
            c._call.assert_not_called()

    def test_hello_cap_and_old_cap_order_without_connecting(self):
        async def say_hello(enabled):
            c = self.client(input_delay8=enabled, blind_ready=True, ingame_pick=True, sets=True, friends=True,
                            tournaments=True, spectate=True, match_rules=True, life150=True)
            writer = mock.Mock()
            writer.get_extra_info.side_effect = lambda key: ("127.0.0.1", 1) if key == "peername" else None
            c._read_loop = mock.AsyncMock()
            c._request = mock.AsyncMock(return_value=welcome())
            with mock.patch("t5lobby.client.asyncio.open_connection", new=mock.AsyncMock(return_value=(None, writer))):
                await c._connect(1)
                await asyncio.gather(*c._tasks)
            return c._request.call_args.args[0]["caps"]

        old_caps = asyncio.run(say_hello(False))
        caps = asyncio.run(say_hello(True))
        self.assertEqual([cap for cap in caps if cap != "input_delay8"], old_caps)
        self.assertEqual(caps.count("input_delay8"), 1)
        self.assertLess(caps.index("input_delay8"), 32)
        self.assertEqual(caps[:16], old_caps[:16])


class ChallengeDelayPicker(unittest.TestCase):
    def ui(self, extended=True, saved="8"):
        c = LobbyClient("127.0.0.1:1", None)
        c.welcome, c.me = welcome(extended), {"id": "me"}
        c._pmap = {"opponent": {"id": "opponent", "input_delay8": True}}
        tab = SimpleNamespace(cfg={"challenge_delay": saved}, client=c, _save_cfg=mock.Mock(),
                              tv_players=SimpleNamespace(selection=lambda: ("opponent",)),
                              _list_rtt={"opponent": (300, False)}, call=mock.Mock())
        with mock.patch.object(tk_challenges.tk, "StringVar", Var):
            ui = tk_challenges.ChallengesUI(tab)
        ui.delay_cb = mock.Mock()
        return ui

    def test_picker_offers_and_remembers_all_values(self):
        ui = self.ui()
        ui.selection_changed()
        self.assertEqual(ui.delay_choices(), ("auto",) + tuple(str(n) for n in range(9)))
        labels = ui._choice_labels()
        self.assertEqual(labels, ["Delay: auto (6)"] + [f"Delay: {n}" for n in range(9)])
        ui._fill_delay()
        self.assertEqual(ui.delay_var.get(), "Delay: 8")
        ui.delay_cb.cget.return_value = labels
        for n in range(9):
            ui.delay_var.set(f"Delay: {n}")
            ui._delay_chosen()
            self.assertEqual(ui.tab.cfg["challenge_delay"], str(n))
        ui.send()
        self.assertEqual(ui.tab.call.call_args.args[1:], ("opponent", 8, 1))

    def test_legacy_peer_changes_choices_even_at_same_auto_delay(self):
        ui = self.ui()
        ui.tab._list_rtt["opponent"] = (60, False)
        ui.selection_changed()
        self.assertEqual(ui.delay_var.get(), "Delay: 8")
        self.assertEqual(ui._auto_for, 1)
        ui.client._pmap["opponent"].pop("input_delay8")
        ui.selection_changed()
        self.assertEqual(ui._auto_for, 1)
        self.assertEqual(ui.delay_var.get(), "Delay: auto (1)")
        self.assertEqual(ui.delay_cb.configure.call_args.kwargs["values"],
                         ["Delay: auto (1)", "Delay: 0", "Delay: 1", "Delay: 2"])
        ui.send()
        self.assertEqual(ui.tab.call.call_args.args[1:], ("opponent", None, 1))
        self.assertEqual(ui.tab.cfg["challenge_delay"], "8")
        ui.client._pmap["opponent"]["input_delay8"] = True
        ui.selection_changed()
        self.assertEqual(ui.delay_var.get(), "Delay: 8")
        self.assertEqual(len(ui.delay_cb.configure.call_args.kwargs["values"]), 10)

    def test_no_selection_uses_server_choices(self):
        ui = self.ui()
        ui.tab.tv_players.selection = lambda: ()
        self.assertEqual(ui.delay_choices(), tk_challenges.DELAY_CHOICES)

    def test_remembered_high_value_on_old_server_uses_auto(self):
        ui = self.ui(extended=False)
        ui.selection_changed()
        self.assertEqual(ui._choice_labels(), ["Delay: auto (4)", "Delay: 0", "Delay: 1", "Delay: 2"])
        self.assertEqual(ui.delay_var.get(), "Delay: auto (4)")
        ui.send()
        self.assertEqual(ui.tab.call.call_args.args[1:], ("opponent", None, 1))
        self.assertEqual(ui.tab.cfg["challenge_delay"], "8")
        ui.client.welcome = welcome()
        ui.selection_changed()
        ui._fill_delay()
        self.assertEqual(ui.delay_var.get(), "Delay: 8")

    def test_auto_boundaries_and_legacy_curve(self):
        for boundary, below in ((60, 1), (100, 2), (150, 3), (200, 4), (250, 5), (300, 6), (350, 7)):
            self.assertEqual(tk_challenges.auto_delay(boundary, extended=True), below)
            self.assertEqual(tk_challenges.auto_delay(boundary + 0.1, extended=True), below + 1)
        self.assertEqual(tk_challenges.auto_delay(10000, extended=True), 8)
        for ms, expected in ((0, 1), (60, 1), (61, 2), (150, 2), (151, 3), (250, 3), (251, 4), (300, 4)):
            self.assertEqual(tk_challenges.auto_delay(ms), expected)
        self.assertIsNone(tk_challenges.auto_delay(None, extended=True))

    def test_extended_auto_ignores_invalid_ping(self):
        for ms in (True, False, -1, -0.1, float("inf"), float("-inf"), float("nan"), None, "300"):
            with self.subTest(ms=ms):
                self.assertIsNone(tk_challenges.auto_delay(ms, extended=True))


if __name__ == "__main__":
    unittest.main()
