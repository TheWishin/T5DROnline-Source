"""Private relay regressions with fake connections: no listener, network, game or build."""
import asyncio
import copy
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import util  # noqa: F401 -- local import path, does not start a server
from t5lobby import proto
from t5lobby.proto import LobbyError
from t5lobby.server.config import Config
from t5lobby.server.private_chat import CAP, PrivateChatMixin, RECEIPT_SECONDS
from t5lobby.server.store import Store


class Peer:
    def __init__(self, name, number, caps=(CAP,)):
        self.id, self.name, self.guest = "p" + str(number), name, False
        self.account_id, self.blocks, self.messages = number, {}, []
        self.conn = SimpleNamespace(player=self, caps=set(caps), closed=False, akey="addr" + str(number))

    def send(self, msg):
        self.messages.append(msg)


class Relay(PrivateChatMixin):
    def __init__(self):
        self.cfg = Config(db=":memory:")
        self.store = Store(":memory:")
        self.players, self.by_name = {}, {}
        self._private_init()

    def add(self, name, number, **kw):
        p = Peer(name, number, **kw)
        self.players[p.id], self.by_name[p.name.lower()] = p, p
        return p

    @staticmethod
    def _block_key(p):
        return "a:" + str(p.account_id)

    @staticmethod
    def _can(p, cap):
        return p is not None and p.conn is not None and not p.conn.closed and cap in p.conn.caps

    def _is_blocked(self, a, b):
        return self._block_key(a) in b.blocks or self._block_key(b) in a.blocks


class PrivateRelayTest(unittest.TestCase):
    def setUp(self):
        self.s = Relay()
        self.a, self.b, self.other = (self.s.add("Alice", 1), self.s.add("Bob", 2), self.s.add("Cara", 3))

    def tearDown(self):
        self.s.store.close()

    def call(self, method, p, **msg):
        return asyncio.run(getattr(self.s, "h_" + method)(p.conn, msg))

    def send(self, text="chosen line"):
        return self.call("private_message", self.a, player=self.b.id, text=text)["message"]

    def test_relay_has_sender_view_and_no_broadcast_or_unreported_store(self):
        before = self.s.store.writes
        line = self.send("private marker 84329")
        self.assertEqual(self.b.messages, [dict(line, t="private_message")])
        self.assertFalse(self.a.messages)
        self.assertFalse(self.other.messages)
        self.assertEqual(self.s.store.writes, before)
        self.assertNotIn("private marker 84329", "\n".join(self.s.store.db.iterdump()))
        self.assertEqual(self.s.store.private_reports(), [])

    def test_both_capabilities_and_server_switch_are_required(self):
        for p in (self.a, self.b):
            p.conn.caps.clear()
            with self.assertRaises(LobbyError) as got:
                self.send()
            self.assertEqual(got.exception.code, "private_unavailable")
            p.conn.caps.add(CAP)
        self.s.cfg.private_chat = False
        with self.assertRaises(LobbyError):
            self.send()
        self.assertFalse(self.b.messages)

    def test_block_in_either_direction_prevents_delivery(self):
        for owner, target in ((self.a, self.b), (self.b, self.a)):
            owner.blocks[self.s._block_key(target)] = {}
            with self.assertRaises(LobbyError) as got:
                self.send()
            self.assertEqual(got.exception.code, "private_unavailable")
            owner.blocks.clear()
        self.assertFalse(self.b.messages)

    def test_mute_blocks_incoming_and_unmutes_after_peer_goes_offline(self):
        self.call("private_mute", self.b, player=self.a.id, muted=True)
        with self.assertRaises(LobbyError):
            self.send()
        del self.s.players[self.a.id]
        del self.s.by_name["alice"]
        result = self.call("private_mute", self.b, name="Alice", muted=False)
        self.assertFalse(result["muted"])
        self.assertFalse(self.b.private_mutes)

    def test_sender_and_address_limits_apply_to_failed_and_successful_attempts(self):
        for _ in range(5):
            self.send()
        with self.assertRaises(LobbyError) as got:
            self.send()
        self.assertEqual(got.exception.code, proto.E_RATE)
        self.assertEqual(len(self.b.messages), 5)
        self.s._private_address.b[self.a.conn.akey].tokens = 0
        self.s._private_send.b[self.s._block_key(self.a)].tokens = 5
        with self.assertRaises(LobbyError) as got:
            self.send()
        self.assertEqual(got.exception.code, proto.E_RATE)

    def test_reports_store_only_explicitly_chosen_authenticated_lines(self):
        selected = self.send("selected marker 85323")
        self.send("unselected marker 33582")
        reply = self.call("private_report", self.b, player=self.a.id, lines=[selected], reason="abuse")
        report = self.s.store.private_reports()[0]
        self.assertEqual(reply["lines"], 1)
        self.assertEqual(report["reporter_name"], "Bob")
        self.assertEqual(report["peer_name"], "Alice")
        self.assertEqual(report["lines"][0]["text"], "selected marker 85323")
        self.assertNotIn("receipt", report["lines"][0])
        self.assertNotIn("unselected marker 33582", "\n".join(self.s.store.db.iterdump()))

    def test_forged_and_third_party_lines_are_refused(self):
        original = self.send()
        forged = copy.deepcopy(original)
        forged["text"] = "forged allegation"
        for p, line in ((self.b, forged), (self.other, original)):
            with self.assertRaises(LobbyError) as got:
                self.call("private_report", p, lines=[line])
            self.assertEqual(got.exception.code, "private_receipt")
        self.assertEqual(self.s.store.private_reports(), [])

    def test_old_and_previous_server_receipts_are_refused(self):
        line = self.send()
        with mock.patch("t5lobby.server.private_chat.time.time", return_value=time.time() + RECEIPT_SECONDS + 1):
            self.assertIsNone(self.s._private_report_line(self.b, line))
        self.s._private_init()  # server process restart: no transcript or signing key persisted
        self.assertIsNone(self.s._private_report_line(self.b, line))

    def test_five_full_unicode_lines_fit_wire_limit_and_report_count_is_bounded(self):
        lines = [self.send("\U0001f600" * 200) for _ in range(5)]
        request = dict(t="private_report", player=self.a.id, lines=lines, reason="r" * 200)
        self.assertLessEqual(len(proto.encode(request)), proto.MAX_LINE)
        with self.assertRaises(LobbyError) as got:
            self.call("private_report", self.b, lines=lines + lines[:1])
        self.assertEqual(got.exception.code, "private_report_limit")

    def test_report_inbox_capacity_and_retention_are_bounded(self):
        st = self.s.store
        for n in range(3):
            st.add_private_report("Alice", 1, "Bob", [], str(n), maximum=2)
        self.assertEqual([r["reason"] for r in st.private_reports()], ["2", "1"])
        st.prune_private_reports(days=30, now=time.time() + 31 * 86400)
        self.assertEqual(st.private_reports(), [])


if __name__ == "__main__":
    unittest.main()
