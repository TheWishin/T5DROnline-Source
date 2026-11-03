"""Offline policy coverage for private chat; no sockets, listeners or game data."""
import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest import mock

import util  # noqa: F401 -- import path only; no ServerThread is started
from t5lobby import proto
from t5lobby.proto import LobbyError
from t5lobby.server.private_chat import CAP, PrivateChatMixin


class PolicyRelay(PrivateChatMixin):
    def __init__(self):
        self.cfg = SimpleNamespace(private_chat=True, max_blocks=100)
        self.players, self.by_name = {}, {}
        self.checks, self.delivered = [], []
        self.admin_muted = set()
        self.personal_mutes = set()
        self.reports = []
        self.store = SimpleNamespace(add_private_report=self.add_report)
        self._private_init()

    def add(self, name, number):
        p = SimpleNamespace(id="p" + str(number), name=name, guest=False,
                            account_id=number, blocks={}, private_mutes={})
        p.conn = SimpleNamespace(player=p, caps={CAP}, closed=False, akey="addr" + str(number))
        p.send = lambda msg: self.delivered.append((p.id, msg))
        self.players[p.id], self.by_name[name.lower()] = p, p
        return p

    @staticmethod
    def _block_key(p):
        return "a:" + str(p.account_id)

    @staticmethod
    def _can(p, cap):
        return p is not None and p.conn is not None and not p.conn.closed and cap in p.conn.caps

    def _is_blocked(self, a, b):
        return self._block_key(a) in b.blocks or self._block_key(b) in a.blocks

    def _is_muted(self, viewer, sender):
        return (viewer.id, sender.id) in self.personal_mutes

    def _check_chat_mute(self, player):
        self.checks.append(("mute", player.id))
        if player.id in self.admin_muted:
            raise LobbyError(proto.E_NOT_ALLOWED, "Chat is muted for this account.", muted_until=12345)

    def _check_filtered_text(self, text, context, player):
        self.checks.append(("filter", text, context, player.id))
        if "badword" in text:
            raise LobbyError(proto.E_NOT_ALLOWED, "Message blocked: hate terms are not allowed.")

    def add_report(self, *args):
        self.reports.append(args)
        return len(self.reports)


class PrivatePolicyTest(unittest.TestCase):
    def setUp(self):
        self.server = PolicyRelay()
        self.alice = self.server.add("Alice", 1)
        self.bob = self.server.add("Bob", 2)
        self.cara = self.server.add("Cara", 3)

    def call(self, kind, player=None, **message):
        return asyncio.run(getattr(self.server, "h_" + kind)((player or self.alice).conn, message))

    def send(self, text="good game", target=None):
        return self.call("private_message", player=self.alice, name=(target or self.bob).name, text=text)

    def test_admin_mute_checked_each_attempt_before_private_delivery(self):
        self.server.admin_muted.add(self.alice.id)
        with self.assertRaises(LobbyError) as refused:
            self.send()
        self.assertEqual(refused.exception.msg, "Chat is muted for this account.")
        self.assertEqual(refused.exception.extra, {"muted_until": 12345})
        self.assertEqual(self.server.delivered, [])
        self.server.admin_muted.clear()
        self.send()
        self.assertEqual(len(self.server.delivered), 1)
        self.assertEqual([check for check in self.server.checks if check[0] == "mute"],
                         [("mute", self.alice.id), ("mute", self.alice.id)])

    def test_muted_failed_attempts_use_sender_budget(self):
        self.server.admin_muted.add(self.alice.id)
        for _ in range(5):
            with self.assertRaises(LobbyError) as refused:
                self.send()
            self.assertEqual(refused.exception.code, proto.E_NOT_ALLOWED)
        with self.assertRaises(LobbyError) as refused:
            self.send()
        self.assertEqual(refused.exception.code, proto.E_RATE)
        self.assertEqual(self.server.delivered, [])

    def test_raw_submission_is_filtered_even_beyond_chat_limit(self):
        with self.assertRaises(LobbyError) as refused:
            self.send("good game " + "x" * 200 + " badword")
        self.assertEqual(refused.exception.msg, "Message blocked: hate terms are not allowed.")
        self.assertEqual(self.server.delivered, [])
        self.assertEqual(self.server.checks[-1][2:], ("chat", self.alice.id))

    def test_cleaned_submission_is_filtered_before_receipt_or_delivery(self):
        with self.assertRaises(LobbyError):
            self.send("bad\x00word")
        self.assertEqual([check[1] for check in self.server.checks if check[0] == "filter"],
                         ["bad\x00word", "badword"])
        self.assertEqual(self.server.delivered, [])

    def test_recipient_uses_shared_personal_mute_policy(self):
        self.server.personal_mutes.add((self.bob.id, self.alice.id))
        self.assertFalse(self.bob.private_mutes)  # no stale session-only cache required
        with self.assertRaises(LobbyError) as refused:
            self.send()
        self.assertEqual(refused.exception.code, "private_unavailable")
        self.assertEqual(self.server.delivered, [])
        self.server.personal_mutes.clear()
        self.send()
        self.assertEqual(len(self.server.delivered), 1)

    def test_legacy_private_mute_delegates_to_shared_persistent_handler(self):
        handler = mock.AsyncMock(return_value={"t": "private_muted", "name": "Bob", "muted": True})
        self.server.h_mute = handler
        message = {"name": "Bob", "muted": True}
        reply = self.call("private_mute", **message)
        handler.assert_awaited_once_with(self.alice.conn, message, legacy=True)
        self.assertEqual(reply["t"], "private_muted")

    def test_policy_storage_or_filter_errors_cannot_deliver_private_text(self):
        for helper in ("_check_chat_mute", "_is_muted", "_check_filtered_text"):
            with self.subTest(helper=helper):
                with mock.patch.object(self.server, helper,
                                       side_effect=RuntimeError("policy unavailable")):
                    with self.assertRaisesRegex(RuntimeError, "policy unavailable"):
                        self.send()
                self.assertEqual(self.server.delivered, [])

    def test_unreported_lines_and_rejected_report_batches_are_never_stored(self):
        first = self.send()["message"]
        other = self.send(target=self.cara)["message"]
        self.assertEqual(self.server.reports, [])
        self.server.cfg.private_report_days, self.server.cfg.max_private_reports = 30, 100
        with self.assertRaises(LobbyError) as refused:
            self.call("private_report", lines=[first, other])
        self.assertEqual(refused.exception.code, "private_receipt")
        self.assertEqual(self.server.reports, [])

    def test_duplicate_selected_lines_and_modified_actors_are_refused(self):
        first = self.send()["message"]
        forged = copy.deepcopy(first)
        forged["from"]["name"] = "SomeoneElse"
        for lines in ([first, first], [forged]):
            with self.subTest(lines=lines):
                with self.assertRaises(LobbyError) as refused:
                    self.call("private_report", lines=lines)
                self.assertEqual(refused.exception.code, "private_receipt")
        self.assertEqual(self.server.reports, [])


if __name__ == "__main__":
    unittest.main()
