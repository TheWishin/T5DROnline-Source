"""When Windows Firewall blocks the game (docs/NETPLAY.md "When Windows Firewall blocks the game").

Covers: the test switch T5_NET_TEST_INBOUND in the launcher's UDP sockets (nat.InboundFilter: "stateful" = Windows
for a blocked program, only replies get in; "block" = nothing but 127.0.0.1), the read-only firewall check behind
the Online tab's hint (t5lobby.fwcheck: the rules as Windows stores them, the network's profile from netsh in any
language), the hint itself, and the relay fallback for a game that hears nothing at all on the direct path
(nat_fallback: the server moves the running match onto the relay, both launchers bind a new socket to it and give
their games the relay bridge; the match driver asks for it). The real firewall is never read for a decision in a
test and never changed anywhere."""
import os
import socket
import tempfile
import time
import unittest
from unittest import mock

import util  # noqa: F401 -- sys.path, T5_PORTMAP=0
from util import ServerThread, client, expect
from t5lobby import fwcheck, nat, proto
from t5lobby.match_driver import FALLBACK_NOTHING_SECONDS, GameLog, MatchDriver

GAME = r"C:\Games\T5DR Online 1.1.3\native\build\cmake\t5dr.exe"
PY = r"C:\Games\T5DR Online 1.1.3\python\pythonw.exe"
ON = {p: True for p in fwcheck.PROFILES}


def rule(action, app, profile=None, protocol="17", active="TRUE", direction="In", extra=""):
    s = f"v2.10|Action={action}|Active={active}|Dir={direction}|"
    if protocol:
        s += f"Protocol={protocol}|"
    if profile:
        for p in profile.split(","):
            s += f"Profile={p}|"
    return s + f"App={app}|Name=t5dr|Desc=t5dr|{extra}"


# ============================================================================== the test switch
class InboundFilterTest(unittest.TestCase):
    def test_stateful_lets_in_replies_only(self):
        f = nat.InboundFilter("stateful")
        self.assertFalse(f.passes(("203.0.113.5", 7000)))           # unsolicited: dropped
        f.sent_to(("203.0.113.5", 7000))
        self.assertTrue(f.passes(("203.0.113.5", 7000)))            # a reply
        self.assertFalse(f.passes(("203.0.113.5", 7001)))           # the same address, another port: not a reply
        self.assertEqual(f.dropped, 2)
        self.assertEqual(f.first_drops, [("203.0.113.5", 7000), ("203.0.113.5", 7001)])

    def test_block_lets_in_only_this_pc(self):
        f = nat.InboundFilter("block")
        f.sent_to(("203.0.113.5", 7000))
        self.assertFalse(f.passes(("203.0.113.5", 7000)))           # not even replies
        self.assertTrue(f.passes(("127.0.0.1", 50000)))             # the relay bridge
        f.local = frozenset()                                       # (the NAT simulator: everything is "internet")
        self.assertFalse(f.passes(("127.0.0.1", 50000)))

    def test_mode_from_value_or_environment(self):
        self.assertEqual(nat.test_inbound_mode("Stateful "), "stateful")
        self.assertIsNone(nat.test_inbound_mode(""))
        self.assertIsNone(nat.test_inbound_mode("on"))
        with mock.patch.dict(os.environ, {"T5_NET_TEST_INBOUND": "block"}):
            self.assertEqual(nat.test_inbound_mode(), "block")
            self.assertIsNone(nat.make_inbound_filter(""))          # "" = off, whatever the environment says
            self.assertEqual(nat.make_inbound_filter(None).mode, "block")
        with mock.patch.dict(os.environ, {"T5_NET_TEST_INBOUND": ""}):
            self.assertIsNone(nat.make_inbound_filter(None))

    def test_game_socket_drops_what_it_never_asked_for(self):
        loop = proto.new_event_loop()
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.bind(("127.0.0.1", 0))
        peer.settimeout(1.0)
        peer_addr = peer.getsockname()
        try:
            async def run():
                gs = await nat.GameSocket.open(0, ("127.0.0.1", 9), 0, b"t" * 16, b"g" * 8, 0, inbound="stateful")
                me = ("127.0.0.1", gs.port)
                punch = proto.pk_punch(b"g" * 8, 1, 0, 1)
                peer.sendto(punch, me)                              # unsolicited: the "firewall" drops it
                await __import__("asyncio").sleep(0.2)
                first = (gs.stats["rx"], dict(gs.heard))
                gs.send(proto.pk_punch(b"g" * 8, 0, 0, 2), peer.getsockname())     # now this socket sent there
                peer.recvfrom(100)
                peer.sendto(punch, me)                              # a reply: it gets in
                await __import__("asyncio").sleep(0.2)
                second = (gs.stats["rx"], dict(gs.heard))
                await gs.close()
                return first, second, gs.inbound.dropped
            (rx1, heard1), (rx2, heard2), dropped = loop.run_until_complete(run())
        finally:
            peer.close()
            loop.close()
        self.assertEqual((rx1, heard1), (0, {}))
        self.assertEqual(rx2, 1)
        self.assertIn(peer_addr, heard2)
        self.assertEqual(dropped, 1)

    def test_client_takes_the_switch_from_the_environment(self):
        s = ServerThread().start()
        try:
            with mock.patch.dict(os.environ, {"T5_NET_TEST_INBOUND": "stateful"}):
                c = client(s, "Fw")
            try:
                self.assertEqual(c.test_inbound, "stateful")
            finally:
                c.close()
            c = client(s, "Fw2", test_inbound="")
            try:
                self.assertEqual(c.test_inbound, "")
            finally:
                c.close()
        finally:
            s.stop()


# ============================================================================== the read-only check
class FirewallCheckTest(unittest.TestCase):
    def ev(self, rules, current=None, enabled=ON, **kw):
        return fwcheck.evaluate(rules, {"game": GAME, "launcher": PY}, enabled, current, **kw)

    def test_parse_rule(self):
        r = fwcheck.parse_rule(rule("Block", GAME, "Private,Public", extra="RA4=LocalSubnet|"))
        self.assertEqual((r["action"], r["active"], r["dir"], r["protocol"], r["profiles"], r["app"], r["scoped"]),
                         ("block", True, "in", "17", {"private", "public"}, GAME, True))

    def test_cancel_on_windows_question(self):
        # what Windows writes when Cancel is clicked on a public network: block rules for TCP and UDP, public only
        rules = [rule("Block", GAME, "Public", "6"), rule("Block", GAME, "Public", "17")]
        st = self.ev(rules, ["public"])
        self.assertEqual((st.state, st.blocked, st.programs["game"]), ("blocked", ["game"], "blocked"))
        self.assertEqual(st.paths["game"], GAME)
        st = self.ev(rules, ["private"])                         # another network: Windows will ask there
        self.assertEqual((st.state, st.blocked), ("ask", []))
        self.assertEqual(self.ev(rules).state, "blocked")       # profile unknown: every profile counts

    def test_allowed(self):
        rules = [rule("Allow", GAME, "Public,Private"), rule("Allow", PY)]
        self.assertEqual(self.ev(rules, ["public"]).state, "allowed")
        self.assertEqual(self.ev(rules, ["domain"]).state, "ask")

    def test_block_beats_allow_and_paths_match_like_windows(self):
        rules = [rule("Allow", GAME), rule("Allow", PY),
                 rule("Block", r"%SystemDrive%\Games\T5DR Online 1.1.3\NATIVE\build\cmake\T5DR.EXE")]
        with mock.patch.dict(os.environ, {"SystemDrive": "C:"}):
            st = self.ev(rules, ["public"])
        self.assertEqual(st.blocked, ["game"])

    def test_rules_that_do_not_count(self):
        rules = [rule("Block", GAME, protocol="6"),                     # TCP only: the game's UDP is not blocked
                 rule("Block", GAME, active="FALSE"),                   # switched off
                 rule("Block", GAME, direction="Out"),                  # outbound
                 rule("Block", r"C:\elsewhere\t5dr.exe"),               # another copy of the game
                 rule("Allow", GAME, protocol=None), rule("Allow", PY)]  # any protocol: allowed
        self.assertEqual(self.ev(rules, ["public"]).state, "allowed")
        scoped = [rule("Allow", GAME, extra="LPort=7000|"), rule("Allow", PY)]
        self.assertEqual(self.ev(scoped, ["public"]).state, "ask")     # one port only: not "the program is allowed"

    def test_no_rule_and_no_question(self):
        rules = [rule("Allow", PY)]
        st = self.ev(rules, ["public"], notify_off={"public": True})
        self.assertEqual(st.blocked, ["game"])                          # Windows will not ask: unsolicited is dropped
        st = self.ev([rule("Allow", GAME), rule("Allow", PY)], ["public"], block_all={"public": True})
        self.assertEqual(st.blocked, ["game", "launcher"])              # "Block all incoming connections"

    def test_firewall_off(self):
        rules = [rule("Block", GAME)]
        off = {p: False for p in fwcheck.PROFILES}
        self.assertEqual(self.ev(rules, ["public"], off).state, "off")
        self.assertEqual(self.ev(rules, ["public"], dict(off, private=True)).state, "off")   # on, but not here

    def test_current_profile_in_any_language(self):
        out = {"domainprofile": "Domänenprofil-Einstellungen:", "privateprofile": "Privates Profil-Einstellungen:",
               "publicprofile": "Öffentliches Profil-Einstellungen:", "currentprofile": "Öffentliches Profil-Einstellungen:"}

        def run(argv, **kw):
            text = "\r\n" + out[argv[-1]] + "\r\n" + "-" * 70 + "\r\nStatus                                   EIN\r\n"
            return mock.Mock(stdout=text.encode("cp850"))
        with mock.patch.object(fwcheck.subprocess, "run", run):
            self.assertEqual(fwcheck.current_profiles(), ["public"])
        with mock.patch.object(fwcheck.subprocess, "run", side_effect=OSError("no netsh")):
            self.assertIsNone(fwcheck.current_profiles())

    def test_check_reads_and_never_raises(self):
        with mock.patch.object(fwcheck, "read_registry", side_effect=PermissionError("denied")):
            st = fwcheck.check(GAME, launcher=PY, profiles=None)
        self.assertEqual(st.state, "off" if os.name != "nt" else "unknown")
        if os.name == "nt":
            got = ([rule("Block", GAME, "Public")], ON, {}, {})
            with mock.patch.object(fwcheck, "read_registry", return_value=got):
                st = fwcheck.check(GAME, launcher=PY, profiles=["public"])
            self.assertEqual(st.blocked, ["game"])
            self.assertEqual(st.programs["launcher"], "ask")


    def test_only_reads(self):
        """Nothing in the check can change a rule: netsh is only ever asked to "show", the registry only opened."""
        calls = []

        def run(argv, **kw):
            calls.append(list(argv))
            return mock.Mock(stdout=b"")
        with mock.patch.object(fwcheck.subprocess, "run", run):
            fwcheck.current_profiles()
        self.assertTrue(calls)
        self.assertTrue(all(c[:3] == ["netsh", "advfirewall", "show"] for c in calls), calls)
        with open(fwcheck.__file__, encoding="utf-8") as f:
            src = f.read()
        for word in ("SetValue", "CreateKey", "DeleteValue", "DeleteKey", "runas", "add rule", "set rule", "delete rule"):
            self.assertNotIn(word, src)


try:
    import tkinter as tk
    from tkinter import ttk
    from t5lobby import tk_tab
except ImportError:      # pragma: no cover
    tk = None


@unittest.skipIf(tk is None, "no tkinter")
class FirewallHintTest(unittest.TestCase):
    def setUp(self):
        from test_tk_tab import FakeApp
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.dir = tempfile.mkdtemp()
        os.environ["T5_ONLINE_DIR"] = os.path.join(self.dir, "user")
        self.app = FakeApp(self.dir)
        frame = ttk.Frame(self.root)
        frame.pack()
        self.tab = tk_tab.OnlineTab(frame, self.app)
        self.seen = []
        self.tab.fw_check = lambda exe: (self.seen.append(exe), self.status)[1]

    def tearDown(self):
        self.tab.on_close()
        self.root.destroy()

    def settle(self, cond, timeout=5.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            self.root.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def test_blocked_game_shows_the_hint_with_how_to_fix(self):
        self.status = fwcheck.Status("blocked", ["game"], {"game": "blocked", "launcher": "allowed"}, ["public"])
        self.tab.check_firewall(force=True)
        self.assertTrue(self.settle(lambda: self.tab.fw_hint_var.get()))
        text = self.tab.fw_hint_var.get()
        self.assertIn("t5dr.exe", text)
        self.assertEqual(self.seen, [os.path.join(self.dir, "build", "cmake", "t5dr.exe")])   # the path the app runs
        self.assertTrue(self.settle(lambda: self.tab.view.fw_frame.winfo_manager() == "grid"))
        with mock.patch("webbrowser.open") as wb:
            self.tab.fw_fix_btn.invoke()
        wb.assert_called_once_with(tk_tab.FW_HELP_URL)
        self.assertTrue(tk_tab.FW_HELP_URL.endswith("TROUBLESHOOTING.md#the-firewall-blocks-the-game"))
        self.tab.dismiss_fw_hint()
        self.assertEqual(self.tab.fw_hint_var.get(), "")
        self.assertTrue(self.settle(lambda: self.tab.view.fw_frame.winfo_manager() == ""))
        self.assertIn("Windows Firewall: blocked, blocks game", self.tab.report_info())

    def test_allowed_or_off_shows_nothing(self):
        for st in ("allowed", "off", "ask", "unknown"):
            self.status = fwcheck.Status(st)
            self.tab._fw_checked = -1e9
            self.tab.check_firewall()
            self.settle(lambda: not self.tab._fw_busy)
            self.assertEqual(self.tab.fw_hint_var.get(), "", st)

    def test_what_a_match_showed(self):
        self.status = fwcheck.Status("off")
        self.tab.on_event({"t": "match_cancel", "match": "m1", "reason": "udp_unreachable", "you": True})
        self.assertEqual(self.tab.fw_seen, "udp")
        self.assertIn("firewall seems to block", self.tab.fw_hint_var.get())
        self.tab.fw_seen = None
        self.tab._fw_update()
        self.tab.on_event({"t": "nat_status", "match": "m2", "phase": "register", "text": "x", "udp_blocked": True})
        self.assertEqual(self.tab.fw_seen, "udp")              # (the server never answered: the cancel says no_connection)
        self.tab.fw_seen = None
        self.tab._fw_update()
        self.tab.on_driver({"t": "driver", "kind": "firewall_suspect", "reason": "no_peer", "path": "direct"})
        self.assertEqual(self.tab.fw_seen, "no_peer")
        self.assertIn("firewall seems to block", self.tab.fw_hint_var.get())


# ============================================================================== the relay fallback
class FallbackTest(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def pair(self, a=None, b=None):
        ca = client(self.s, "Alice", auto_ready=True, **dict({"relay_bridge": True}, **(a or {})))
        cb = client(self.s, "Bob", auto_ready=True, **dict({"relay_bridge": True}, **(b or {})))
        self.clients += [ca, cb]
        with mock.patch("t5lobby.client.local_ipv4s", lambda ip: []):
            ca.quick_match()
            cb.quick_match()
            ta = expect(ca, "match_start", 30)["ticket"]
            tb = expect(cb, "match_start", 30)["ticket"]
        return ca, cb, ta, tb

    def test_a_game_that_hears_nothing_moves_the_match_onto_the_relay(self):
        ca, cb, ta, tb = self.pair()
        self.assertEqual(ta.path, "direct")
        self.assertIn("game_fallback", ca.welcome["caps"])
        self.assertTrue(ca.nat_fallback(ta.match_id))
        a2 = expect(ca, "match_start", 20)
        b2 = expect(cb, "match_start", 20)
        for ev, c in ((a2, ca), (b2, cb)):
            self.assertEqual((ev["match"], ev["path"]), (ta.match_id, "relay"))
            self.assertEqual(ev["ticket"].peer[0], "127.0.0.1")           # the relay bridge on this PC
            self.assertIsNotNone(c._bridge)
        self.assertNotEqual(a2["ticket"].local_port, ta.local_port)      # (the old game still holds that one)
        from test_lobby import game_link
        host, join = (a2["ticket"], b2["ticket"]) if a2["ticket"].role == "host" else (b2["ticket"], a2["ticket"])
        heard, _answered = game_link(host, join)
        self.assertEqual(heard[0], "127.0.0.1")
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["game_fallbacks"]), 1)
        m = self.s.call(lambda: self.s.srv.by_name["alice"].match)
        self.assertEqual((m.state, m.path, m.fallback), ("playing", "relay", True))
        self.assertFalse(cb.nat_fallback(ta.match_id))                   # once per match
        ca.report_result(0, [3, 1], match_id=ta.match_id, source="game")
        cb.report_result(0, [3, 1], match_id=ta.match_id, source="game")
        r = expect(ca, "match_result", 15)
        self.assertEqual(r["status"], "confirmed")

    def test_a_fight_being_played_is_not_restarted(self):
        # (security review 3) nat_fallback starts the match's session again. Within T5L_GAME_FALLBACK (90 s) of the
        # start a player losing round 1 could ask for it -- the server took the word "my game heard nothing" -- and the
        # opponent's game began the match anew. Once a launcher has said its game played the fight for a while (600
        # lockstep frames: they only run with the opponent's inputs), the server refuses.
        ca, cb, ta, tb = self.pair()
        self.assertEqual(ta.path, "direct")
        cb.game_playing(tb.match_id)                                       # Bob's game is in the fight
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.by_name["bob"].match.game_playing[1]))
        self.assertFalse(ca.nat_fallback(ta.match_id))                     # Alice's "heard nothing": not believed
        m = self.s.call(lambda: self.s.srv.by_name["alice"].match)
        self.assertEqual((m.state, m.path, m.fallback), ("playing", "direct", False))
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["game_fallbacks"]), 0)
        self.assertIsNone(ca.next_event(1.0, ("match_start",)))            # nobody got a second match_start
        cb.game_playing("m000000000000")                                   # (another match: ignored, no error)
        cb.game_playing(tb.match_id)                                       # (twice: no harm)
        self.assertIsNone(cb.next_event(0.5, ("error",)))

    def test_refused(self):
        ca, cb, ta, tb = self.pair(b={"relay_bridge": False})                # Bob's launcher cannot bridge
        self.assertNotIn("game_fallback", cb.welcome["caps"])
        self.assertFalse(cb.nat_fallback(ta.match_id))                     # (the client does not even ask)
        self.assertFalse(ca.nat_fallback(ta.match_id))                     # the server: not both
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["game_fallbacks"]), 0)


class FallbackLateTest(FallbackTest):
    server_cfg = {"game_fallback": 0.5}

    def test_a_game_that_hears_nothing_moves_the_match_onto_the_relay(self):
        ca, cb, ta, tb = self.pair()
        time.sleep(1.0)
        self.assertFalse(ca.nat_fallback(ta.match_id))                     # too late: the games had their chance

    test_refused = None
    test_a_fight_being_played_is_not_restarted = None


# ============================================================================== the match driver
class _Client:
    def __init__(self):
        self.asked = []
        self.playing = []

    def nat_fallback(self, mid):
        self.asked.append(mid)
        return True

    def game_started(self, mid=None):
        return {}

    def game_playing(self, mid):
        self.playing.append(mid)


class _Game:
    def __init__(self, log_path):
        self.log_path = log_path
        self.proc = None

    def running(self):
        return True

    def stop(self):
        pass


class DriverFallbackTest(unittest.TestCase):
    def test_game_log(self):
        g = GameLog(None)
        g.line("[netplay] waiting for the opponent's game to answer (9s, nothing arrived yet)...")
        self.assertEqual(g.nothing_s, 9)
        g.line("[netplay] waiting for the opponent's game to answer (14s, packets arrive)...")
        self.assertEqual(g.nothing_s, 9)
        g.line("[netplay] cannot connect (no_peer): no answer from the opponent's game within 60 s "
               "(203.0.113.5:7000; nothing arrived)")
        self.assertEqual((g.fail_reason, g.fail_nothing), ("no_peer", True))
        g.line("[netplay] session 2 set up")
        self.assertEqual((g.nothing_s, g.fail_nothing), (0, False))
        g.line("[netplay] cannot connect (no_peer): no answer from the opponent's game within 60 s "
               "(203.0.113.5:7000; packets arrived, none completed the handshake)")
        self.assertFalse(g.fail_nothing)

    def test_driver_asks_once_and_holds_the_report(self):
        from t5lobby.handover import MatchTicket
        d = tempfile.mkdtemp()
        log = os.path.join(d, "game.log")
        with open(log, "w") as f:
            f.write("[netplay] waiting for the opponent's game to answer (4s, nothing arrived yet)...\n")
        c = _Client()
        drv = MatchDriver(c, launch=lambda env: _Game(log), workdir=d, async_calls=False)
        drv.game = _Game(log)
        drv.glog = GameLog(log)
        t = MatchTicket(match_id="m1", role="host", slot=0, local_port=7000, peer=("203.0.113.5", 7000), path="direct",
                        rtt_ms=10.0, jitter_ms=1.0, delay=2)
        drv.ticket = t
        drv.poll()
        self.assertEqual(c.asked, [])                                 # 4 s: not yet
        with open(log, "a") as f:
            f.write(f"[netplay] waiting for the opponent's game to answer ({FALLBACK_NOTHING_SECONDS}s, "
                    "nothing arrived yet)...\n")
        notes = drv.poll()
        self.assertEqual(c.asked, ["m1"])
        self.assertTrue(any(n["kind"] == "firewall_suspect" and n.get("fallback") for n in notes))
        self.assertIsNotNone(drv.fallback_wait)
        drv.poll()
        self.assertEqual(c.asked, ["m1"])                             # once
        relay = MatchTicket(match_id="m1", role="host", slot=0, local_port=7001, peer=("127.0.0.1", 7100), path="relay",
                            rtt_ms=10.0, jitter_ms=1.0, delay=2)
        with mock.patch.object(drv, "launch", return_value=_Game(log)):
            drv.on_event({"t": "match_start", "match": "m1", "ticket": relay, "opponent": {"name": "Bob"}})
        self.assertIsNone(drv.fallback_wait)
        self.assertIs(drv.ticket, relay)

    def test_driver_says_once_when_the_fight_runs(self):
        # (security review 3) the launcher tells the lobby when its game has played the fight for a while -- the first
        # netplay speed or sync line after FIGHT START -- so that the opponent's launcher cannot restart it by asking for
        # the relay; once per match, never before the fight
        import json
        from t5lobby.handover import MatchTicket
        d = tempfile.mkdtemp()
        log = os.path.join(d, "game.log")
        st = os.path.join(d, "status.json")
        with open(log, "w") as f:
            f.write("[netplay] connected (host, P1), delay 2, peer 203.0.113.5:7000\n"
                    "[netplay] speed: 59.9 fps, this PC 60.0 fps without the waits for the peer (waited 0.1 s of 10.0 s)\n")
        c = _Client()
        drv = MatchDriver(c, launch=lambda env: _Game(log), workdir=d, async_calls=False)
        drv.game = _Game(log)
        drv.glog = GameLog(log)
        drv.status_path = st
        drv.ticket = MatchTicket(match_id="m3", role="host", slot=0, local_port=7000, peer=("203.0.113.5", 7000),
                                 path="direct", rtt_ms=10.0, jitter_ms=1.0, delay=2)
        drv.poll()
        self.assertEqual(c.playing, [])                               # a speed line from before the fight: not this
        with open(st, "w") as f:
            json.dump({"state": "fight", "match": 1, "p1": 1, "p2": 2}, f)
        drv.poll()
        self.assertEqual(c.playing, [])                               # FIGHT START: not yet
        with open(log, "a") as f:
            f.write("[netplay] sync check through frame 599: 0 mismatching frame(s)\n")
        drv.poll()
        self.assertEqual(c.playing, ["m3"])
        with open(log, "a") as f:
            f.write("[netplay] speed: 59.9 fps, this PC 60.0 fps without the waits for the peer (waited 0.1 s of 10.0 s)\n")
        drv.poll()
        self.assertEqual(c.playing, ["m3"])                           # once

    def test_relay_path_never_asks(self):
        from t5lobby.handover import MatchTicket
        d = tempfile.mkdtemp()
        log = os.path.join(d, "game.log")
        with open(log, "w") as f:
            f.write("[netplay] waiting for the opponent's game to answer (30s, nothing arrived yet)...\n")
        c = _Client()
        drv = MatchDriver(c, launch=lambda env: _Game(log), workdir=d, async_calls=False)
        drv.game = _Game(log)
        drv.glog = GameLog(log)
        drv.ticket = MatchTicket(match_id="m2", role="join", slot=1, local_port=7000, peer=("127.0.0.1", 7100),
                                 path="relay", rtt_ms=10.0, jitter_ms=1.0, delay=2)
        drv.poll()
        self.assertEqual(c.asked, [])


if __name__ == "__main__":
    unittest.main()
