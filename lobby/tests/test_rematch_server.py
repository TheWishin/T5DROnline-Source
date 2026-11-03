"""Pure in-process rematch policy tests: no listener, client, game or data.

The new tests import the production rule owner and use the real h_rematch
handler with fake players. No sleeps or network helpers are needed.
"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import util  # noqa: F401 -- repository import paths only
from t5lobby.proto import LobbyError
from t5lobby.server.config import Config
from t5lobby.server.lobby import LobbyServer
from t5lobby.server.matchrules import MatchRulesMixin
from t5lobby.server.rematch import CAP, SKIP_CAP, RematchMixin


class Player:
    def __init__(self, name, caps=(CAP, SKIP_CAP)):
        self.name = name
        self.id = name
        self.online = True
        self.status = "idle"
        self.match = self.room = None
        self.auto_skip_after_round = False
        self.conn = NS(caps=set(caps), player=self)
        self.sent = []

    def send(self, event):
        self.sent.append(event)

    def brief(self):
        return {"id": self.id, "name": self.name}


class Server(RematchMixin):
    h_rematch = LobbyServer.h_rematch
    h_casual_prefs = LobbyServer.h_casual_prefs
    _expire_recent = LobbyServer._expire_recent
    _room_owner = LobbyServer._room_owner

    def _room_view(self, room, viewer):
        return {"id": room.id, "rematch_policy": room.rematch_policy,
                "auto_skip_after_round": room.auto_skip_after_round}

    def __init__(self, **settings):
        self.cfg = Config(ingame_rematch=True, **settings)
        self.rooms = {}
        self.recent = {}
        self.created = []
        self.blocked = False

    def _refuse_draining(self):
        pass

    def _is_blocked(self, p, other):
        return self.blocked

    def _rematch_swap(self, prev, msg):
        return bool(msg.get("swap"))

    def _rematch_swapped(self, prev):
        return any((vote or {}).get("swap") for vote in prev.rematch)

    def _ranked_rematch_swap(self, prev):
        return False

    def _ranked_set_going(self, prev):
        return False

    def _direct_again(self, prev):
        return False

    def create_match(self, host, join, **kw):
        self.created.append((host, join, kw))
        return NS(id="next", state="ready")


def match(server):
    a, b = Player("A"), Player("B")
    m = NS(id="old", ranked=False, origin="queue", room=None, set=None,
           players=[a, b], rematch=[None, None], path="direct")
    m.side = lambda p: m.players.index(p) if p in m.players else None
    server.recent[m.id] = m
    return m, a, b


class RematchRuleTest(unittest.IsolatedAsyncioTestCase):
    async def test_configuration_is_off_and_both_confirm_by_default(self):
        cfg = Config()
        self.assertFalse(cfg.ingame_rematch)
        self.assertEqual(cfg.casual_rematch_policy, "both_confirm")
        configured = Config.from_env({"T5L_INGAME_REMATCH": "1",
                                      "T5L_CASUAL_REMATCH_POLICY": "auto_unless_declined"})
        self.assertTrue(configured.ingame_rematch)
        self.assertEqual(configured.casual_rematch_policy, "auto_unless_declined")

    async def test_default_requires_two_explicit_votes_and_keeps_old_button(self):
        s = Server()
        m, a, b = match(s)
        s._rematch_ui_open(m)
        self.assertEqual(s._rematch_ui_result(m)["rematch_ui"]["policy"], "both_confirm")
        self.assertEqual(s.created, [])
        reply = await s.h_rematch(a.conn, {"match": m.id, "keep": True})
        self.assertEqual(reply["state"], "waiting")
        self.assertEqual(s.created, [])
        reply = await s.h_rematch(b.conn, {"match": m.id, "keep": True})
        self.assertEqual(reply["state"], "accepted")
        self.assertTrue(s.created[0][2]["keep"])

    async def test_auto_policy_still_waits_for_both_clients_own_votes(self):
        s = Server(casual_rematch_policy="auto_unless_declined")
        m, a, b = match(s)
        s._rematch_ui_open(m)
        self.assertEqual(s._rematch_ui_result(m)["rematch_ui"]["auto_after"], 5.0)
        self.assertEqual(s.created, [])       # opening the prompt cannot start a match
        await s.h_rematch(a.conn, {"match": m.id, "keep": True})
        self.assertEqual(s.created, [])       # one client's automatic vote is insufficient
        await s.h_rematch(b.conn, {"match": m.id, "keep": True})
        self.assertEqual(len(s.created), 1)
        self.assertTrue(s.created[0][2]["keep"])

    async def test_changed_skip_agreement_forces_new_replay_spectator_session(self):
        for before, after in ((False, True), (True, False), (True, True)):
            s = Server()
            m, a, b = match(s)
            m.auto_skip_after_round = before
            a.auto_skip_after_round = b.auto_skip_after_round = after
            s._rematch_ui_open(m)
            await s.h_rematch(a.conn, {"match": m.id, "keep": True})
            await s.h_rematch(b.conn, {"match": m.id, "keep": True})
            self.assertEqual(s.created[0][2]["keep"], before == after)

    async def test_decline_cancels_automatic_offer_even_after_other_vote(self):
        s = Server(casual_rematch_policy="auto_unless_declined")
        m, a, b = match(s)
        s._rematch_ui_open(m)
        await s.h_rematch(a.conn, {"match": m.id, "keep": True})
        await s.h_rematch(b.conn, {"match": m.id, "accept": False})
        with self.assertRaises(LobbyError):
            await s.h_rematch(a.conn, {"match": m.id})
        self.assertEqual(s.created, [])
        self.assertEqual(a.sent[-1]["state"], "declined")

    async def test_expiry_is_authoritative_and_returns_both_to_lobby(self):
        s = Server(casual_rematch_policy="auto_unless_declined")
        m, a, b = match(s)
        s._rematch_ui_open(m)
        with patch("t5lobby.server.rematch.time.monotonic", return_value=m.ui_deadline):
            with self.assertRaises(LobbyError):
                await s.h_rematch(a.conn, {"match": m.id})
        self.assertEqual(s.created, [])
        self.assertEqual(a.sent[-1]["state"], "expired")
        self.assertEqual(b.sent[-1]["state"], "expired")

    async def test_old_cap_off_ranked_and_community_never_auto_offer(self):
        for excluded in ("off", "old", "ranked", "downgraded_ranked", "community", "tournament"):
            s = Server(casual_rematch_policy="auto_unless_declined")
            m, a, _ = match(s)
            if excluded == "off":
                s.cfg.ingame_rematch = False
            elif excluded == "old":
                a.conn.caps.clear()
            elif excluded == "ranked":
                m.ranked = True
            elif excluded == "downgraded_ranked":
                m.requested_ranked = True
            elif excluded == "tournament":
                m.set = NS(tour=object(), rated=False)
            else:
                m.room = NS(id="r", community=True, ranked=False)
            s._rematch_ui_open(m)
            self.assertEqual(s._rematch_ui_result(m), {}, excluded)

    async def test_changed_room_disconnect_block_and_busy_cannot_start(self):
        for changed in ("room", "offline", "blocked", "busy"):
            s = Server(casual_rematch_policy="auto_unless_declined")
            m, a, b = match(s)
            s._rematch_ui_open(m)
            if changed == "room":
                a.room = object()
            elif changed == "offline":
                b.online = False
            elif changed == "blocked":
                s.blocked = True
            else:
                b.status = "queue"
            with self.assertRaises(LobbyError):
                await s.h_rematch(b.conn, {"match": m.id})
            self.assertEqual(s.created, [], changed)

    async def test_room_policy_is_frozen_for_current_result(self):
        s = Server()
        m, a, b = match(s)
        room = NS(id="private", community=False, ranked=False, rematch_policy="both_confirm")
        s.rooms[room.id] = room
        m.room = a.room = b.room = room
        s._rematch_ui_open(m)
        room.rematch_policy = "auto_unless_declined"
        self.assertEqual(s._rematch_ui_result(m)["rematch_ui"]["policy"], "both_confirm")
        self.assertEqual(s.created, [])

    async def test_community_result_offers_only_authoritative_line_actions(self):
        s = Server(casual_rematch_policy="auto_unless_declined")
        m, a, b = match(s)
        room = NS(id="community", community=True, ranked=False, members=[a, b], line=[a, b], rotation="queue")
        s.rooms[room.id] = room
        m.room = a.room = b.room = room
        s._rematch_ui_open(m)
        self.assertFalse(hasattr(m, "ui_deadline"))
        shown = s._rematch_ui_result(m, a)["rematch_ui"]
        self.assertEqual(shown["kind"], "community")
        self.assertEqual(shown["policy"], "both_confirm")
        self.assertEqual(shown["actions"], ["sit_out"])
        room.line.remove(a)
        self.assertEqual(s._rematch_ui_result(m, a)["rematch_ui"]["actions"], ["back_to_line"])
        with self.assertRaises(LobbyError):
            await s.h_rematch(a.conn, {"match": m.id})

    async def test_round_skip_requires_both_consents_and_caps(self):
        s = Server()
        m, a, b = match(s)
        self.assertFalse(s._rematch_skip_rule(m, a, b, False, "queue"))
        a.auto_skip_after_round = True
        self.assertFalse(s._rematch_skip_rule(m, a, b, False, "queue"))
        b.auto_skip_after_round = True
        self.assertTrue(s._rematch_skip_rule(m, a, b, False, "queue"))
        m.auto_skip_after_round = True
        m.training, m.life = False, None
        self.assertTrue(MatchRulesMixin._rules_fight(m)["auto_skip_after_round"])
        b.conn.caps.remove(SKIP_CAP)
        self.assertFalse(s._rematch_skip_rule(m, a, b, False, "queue"))
        b.conn.caps.add(SKIP_CAP)
        self.assertFalse(s._rematch_skip_rule(m, a, b, True, "queue"))
        self.assertFalse(s._rematch_skip_rule(m, a, b, False, "tournament"))
        m.requested_ranked = True
        self.assertFalse(s._rematch_skip_rule(m, a, b, False, "queue"))
        m.requested_ranked = False
        s.cfg.ingame_rematch = False
        self.assertFalse(s._rematch_skip_rule(m, a, b, False, "queue"))

    async def test_room_skip_requires_room_rule_and_both_consents(self):
        s = Server()
        m, a, b = match(s)
        a.auto_skip_after_round = b.auto_skip_after_round = True
        room = NS(ranked=False, community=False, auto_skip_after_round=False)
        m.room = room
        self.assertFalse(s._rematch_skip_rule(m, a, b, False, "room"))
        room.auto_skip_after_round = True
        self.assertTrue(s._rematch_skip_rule(m, a, b, False, "room"))
        room.community = True
        self.assertFalse(s._rematch_skip_rule(m, a, b, False, "room"))

    async def test_room_rule_update_is_owner_only_and_never_changes_a_running_match(self):
        s = Server()
        _, a, b = match(s)
        room = NS(id="r", owner=a, size=2, ranked=False, community=False, match=None,
                  rematch_policy="both_confirm", auto_skip_after_round=False)
        a.room = b.room = room
        s.rooms[room.id] = room
        with self.assertRaises(LobbyError):
            await s.h_room_rules(b.conn, {"rematch_policy": "auto_unless_declined"})
        reply = await s.h_room_rules(a.conn, {"rematch_policy": "auto_unless_declined"})
        self.assertEqual(reply["room"]["rematch_policy"], "auto_unless_declined")
        self.assertFalse(room.auto_skip_after_round)
        room.match = object()
        with self.assertRaises(LobbyError):
            await s.h_room_rules(a.conn, {"auto_skip_after_round": True})
        self.assertFalse(room.auto_skip_after_round)

    async def test_room_options_validate_types_caps_and_modes(self):
        s = Server()
        a = Player("A")
        for fields in ({"rematch_policy": "anything"}, {"auto_skip_after_round": "false"}):
            with self.assertRaises(LobbyError):
                s._rematch_room_options(a.conn, fields)
        for ranked, size in ((True, 2), (False, 3)):
            with self.assertRaises(LobbyError):
                s._rematch_room_options(a.conn, {"rematch_policy": "auto_unless_declined"}, ranked, size)
        a.conn.caps.remove(SKIP_CAP)
        with self.assertRaises(LobbyError):
            s._rematch_room_options(a.conn, {"auto_skip_after_round": True})

    async def test_skip_preference_is_explicit_validated_and_can_be_revoked(self):
        s = Server()
        a = Player("A")
        a.conn.state = NS(take=lambda: True)
        await s.h_casual_prefs(a.conn, {"auto_skip_after_round": True})
        self.assertTrue(a.auto_skip_after_round)
        await s.h_casual_prefs(a.conn, {})  # changing a side/stage does not erase consent
        self.assertTrue(a.auto_skip_after_round)
        await s.h_casual_prefs(a.conn, {"auto_skip_after_round": False})
        self.assertFalse(a.auto_skip_after_round)
        a.conn.caps.remove(SKIP_CAP)
        with self.assertRaises(LobbyError):
            await s.h_casual_prefs(a.conn, {"auto_skip_after_round": True})
        with self.assertRaises(LobbyError):
            await s.h_casual_prefs(a.conn, {"auto_skip_after_round": "true"})


if __name__ == "__main__":
    unittest.main()
