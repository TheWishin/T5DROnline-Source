"""Auto-watch uses the ordinary watch gate, including when lobby flags are stale.

These are policy unit tests: no server, sockets, game process or event loop starts.
The existing network tests in test_spectate_limits.py cover the transport path.
"""
import unittest
from types import SimpleNamespace

import util  # noqa: F401 -- sets the repository's lobby import path
from t5lobby import proto
from t5lobby.server.spectating import SpectateMixin


class Player:
    def __init__(self, name, guest=False, ip="192.0.2.1"):
        self.name = name
        self.guest = guest
        self.account_id = None if guest else name
        self.friends = set()
        self.spec_allow = True
        self.spec_ranked = False
        self.match = None
        self.build_id = "build"
        self.conn = SimpleNamespace(ip=ip, caps={"spectate"})
        self.watching = None
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class Gate(SpectateMixin):
    def __init__(self):
        self.cfg = SimpleNamespace(max_spectators=8, max_streams=50,
                                   spec_reserved_streams=10, spec_guest_share=0.5,
                                   spec_per_address=2, spec_per_net=4)
        self.streams = {}
        self.blocked = set()

    @staticmethod
    def _can(player, cap):
        return player.conn is not None and cap in player.conn.caps

    def _is_blocked(self, viewer, player):
        return (viewer.name, player.name) in self.blocked

    @staticmethod
    def akey(ip):
        return proto.address_key(ip)


def match(room_private=False, ranked=False):
    a, b = Player("Alice"), Player("Bob")
    room = SimpleNamespace(private=room_private, members=[a, b])
    return SimpleNamespace(players=[a, b], room=room, ranked=ranked,
                           state="playing", stream_id="session", build_id="build")


def stream(m, *viewers):
    return SimpleNamespace(match=m, viewers=dict.fromkeys(viewers, 0), ended=None)


class AutoWatchGateTest(unittest.TestCase):
    def setUp(self):
        self.gate = Gate()
        self.viewer = Player("Viewer")
        self.match = match()

    def refusal(self, code):
        why = self.gate._spec_refusal(self.viewer, self.match)
        self.assertIsNotNone(why)
        self.assertEqual(why.code, code)

    def test_stale_public_flag_never_overrides_privacy_blocks_or_build(self):
        # Public room flags are broadcast hints, not viewer-specific authority.
        self.assertTrue(self.gate._spec_watchable(self.match))
        self.match.players[1].spec_allow = False
        self.refusal(proto.E_NOT_ALLOWED)
        self.match.players[1].spec_allow = True
        self.gate.blocked.add(("Viewer", "Alice"))
        self.refusal(proto.E_NOT_ALLOWED)
        self.gate.blocked.clear()
        self.viewer.build_id = "other-build"
        self.refusal(proto.E_VERSION)

    def test_private_room_requires_membership_even_for_a_friend(self):
        self.match.room.private = True
        self.viewer.friends.add("Alice")
        self.refusal(proto.E_NOT_ALLOWED)
        self.match.room.members.append(self.viewer)
        self.assertIsNone(self.gate._spec_refusal(self.viewer, self.match))

    def test_ranked_requires_both_consents(self):
        self.match.ranked = True
        self.match.players[0].spec_ranked = True
        self.refusal(proto.E_NOT_ALLOWED)
        self.match.players[1].spec_ranked = True
        self.assertIsNone(self.gate._spec_refusal(self.viewer, self.match))

    def test_old_clients_and_own_ready_check_cannot_watch(self):
        self.viewer.conn.caps.clear()
        self.refusal(proto.E_NOT_ALLOWED)
        self.viewer.conn.caps.add("spectate")
        self.viewer.match = SimpleNamespace(state="ready")
        self.refusal(proto.E_BUSY)
        self.viewer.match = None
        self.match.players = [self.viewer, self.match.players[1]]
        self.refusal(proto.E_STATE)

    def test_guest_share_and_reserved_stream_slots_are_not_auto_watch_exempt(self):
        self.viewer.guest, self.viewer.account_id = True, None
        guests = [Player("G%d" % i, guest=True, ip="192.0.2.%d" % (i + 10)) for i in range(4)]
        self.gate.streams["session"] = stream(self.match, *guests)
        self.refusal(proto.E_FULL)
        self.gate.streams = {"s%d" % i: stream(match()) for i in range(25)}
        self.refusal(proto.E_FULL)  # half the server's streams are already occupied
        self.viewer.guest, self.viewer.account_id = False, "Viewer"
        self.gate.streams = {"s%d" % i: stream(match()) for i in range(40)}
        self.refusal(proto.E_FULL)  # final ten slots are reserved for close viewers

    def test_per_address_limit_is_rechecked_after_public_advertisement(self):
        self.assertTrue(self.gate._spec_watchable(self.match))
        self.gate.streams = {"s%d" % i: stream(match(), Player("V%d" % i)) for i in range(2)}
        self.refusal(proto.E_RATE)
        # Membership retains the established close-viewer exemption; auto-watch
        # adds no additional exception to this policy.
        self.match.room.members.append(self.viewer)
        self.assertIsNone(self.gate._spec_refusal(self.viewer, self.match))

    def test_full_match_is_still_refused_to_an_unrelated_account(self):
        viewers = [Player("V%d" % i, ip="198.51.100.%d" % i) for i in range(8)]
        self.gate.streams["session"] = stream(self.match, *viewers)
        self.refusal(proto.E_FULL)


if __name__ == "__main__":
    unittest.main()
