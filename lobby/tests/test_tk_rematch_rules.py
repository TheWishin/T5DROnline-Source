"""Room rule requests and save acknowledgements with fake clients, without Tk windows or a server."""
import unittest
from types import SimpleNamespace

import util  # noqa: F401 -- sets the local package path; does not start a server
from t5lobby import tk_rooms


def client(rematch=True, skip=True):
    return SimpleNamespace(ingame_rematch_ok=lambda: rematch, auto_skip_ok=lambda: skip)


class RoomRuleValuesTest(unittest.TestCase):
    def test_default_is_both_confirm_and_skipping_off(self):
        self.assertEqual(tk_rooms._room_rule_values(client()),
                         {"rematch_policy": "both_confirm", "auto_skip_after_round": False})

    def test_host_can_request_cancellable_automatic_rematch(self):
        self.assertEqual(tk_rooms._room_rule_values(client(), policy="auto_unless_declined",
                                                   auto_skip_after_round=True),
                         {"rematch_policy": "auto_unless_declined", "auto_skip_after_round": True})

    def test_old_server_or_game_drops_stale_controls(self):
        self.assertEqual(tk_rooms._room_rule_values(client(rematch=False), policy="auto_unless_declined",
                                                   auto_skip_after_round=True), {})
        self.assertEqual(tk_rooms._room_rule_values(SimpleNamespace()), {})

    def test_ranked_and_community_rooms_keep_existing_rules(self):
        for size, ranked in ((2, True), (3, False), (8, False)):
            self.assertEqual(tk_rooms._room_rule_values(client(), size=size, ranked=ranked,
                                                       policy="auto_unless_declined", auto_skip_after_round=True), {})

    def test_tables_never_inherit_classic_rematch_rules_even_with_two_seats(self):
        for size in (2, 4, 8):
            with self.subTest(size=size):
                self.assertFalse(tk_rooms._room_rules_supported(client(), size=size, mode="tables"))
                self.assertEqual(tk_rooms._room_rule_values(client(), size=size, mode="tables",
                                                           policy="auto_unless_declined",
                                                           auto_skip_after_round=True), {})

    def test_skip_capability_is_separate_from_rematch(self):
        self.assertEqual(tk_rooms._room_rule_values(client(skip=False), auto_skip_after_round=True),
                         {"rematch_policy": "both_confirm"})

    def test_unknown_policy_falls_back_to_explicit_confirmation(self):
        self.assertEqual(tk_rooms._room_rule_values(client(), policy="always_start")["rematch_policy"],
                         "both_confirm")

    def test_both_translated_choices_map_to_wire_ids(self):
        for label, policy in tk_rooms.REMATCH_CHOICES:
            self.assertEqual(tk_rooms._pick(tk_rooms.REMATCH_CHOICES, tk_rooms.t(label)), policy)


class RoomRuleSaveTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.done = []
        self.tab = SimpleNamespace(client=SimpleNamespace(room_lock=object(), room_rules=object()),
                                   call=lambda fn, *args, then=None: self.calls.append((fn, args, then)))

    def test_success_waits_for_both_server_acknowledgements(self):
        tk_rooms._save_settings(self.tab, "password", "not-retained", True,
                                {"rematch_policy": "auto_unless_declined", "auto_skip_after_round": True},
                                self.done.append)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][:2], (self.tab.client.room_lock, ("password", "not-retained", True)))
        self.assertEqual(self.done, [])
        self.calls[0][2]({"room": "lock accepted"})
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[1][:2], (self.tab.client.room_rules, ("auto_unless_declined", True)))
        self.assertEqual(self.done, [])
        self.calls[1][2]({"room": "rules accepted"})
        self.assertEqual(self.done, [{"room": "rules accepted"}])

    def test_rejected_lock_does_not_dispatch_rules_or_report_success(self):
        tk_rooms._save_settings(self.tab, "none", None, False, {"rematch_policy": "both_confirm"}, self.done.append)
        # A failed tab.call never invokes its success callback.
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.done, [])

    def test_old_server_and_unchanged_rules_only_use_existing_lock_call(self):
        tk_rooms._save_settings(self.tab, None, None, False, {}, self.done.append)
        self.calls[0][2]({"room": "accepted"})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.done, [{"room": "accepted"}])

    def test_changing_only_skip_does_not_rewrite_the_policy(self):
        tk_rooms._save_settings(self.tab, None, None, False, {"auto_skip_after_round": False}, self.done.append)
        self.calls[0][2]({})
        self.assertEqual(self.calls[1][:2], (self.tab.client.room_rules, (None, False)))


if __name__ == "__main__":
    unittest.main()
