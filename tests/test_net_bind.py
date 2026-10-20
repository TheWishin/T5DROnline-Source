"""The address the netplay socket binds (docs/NETPLAY.md "Bind address", src/netplay/net_bind.h).

Windows Firewall asks once per exe path when a program binds a non-loopback address; test runs start t5dr.exe
from many build folders with both games on 127.0.0.1, so they bind 127.0.0.1. A player's game binds every
interface, as before.

* tests/c/net_bind_test.cpp, built against src/netplay/net_bind.h, must print PASS: T5_NET_BIND wins (an invalid
  value is noted and every interface is used); unset, a loopback T5_NET_PEER outside a lobby match binds
  127.0.0.1, everything else every interface.
* The environment a real lobby match hands the game (handover.MatchTicket.game_env: direct, LAN, relay and the
  launcher's relay bridge on 127.0.0.1) goes through the same rule: every interface.
* netplay_core.cpp binds what the rule chose and logs it; the launcher never sets T5_NET_BIND; the test tools
  that start local pairs set it with setdefault (an explicit value wins).
* The lobby client's game socket (t5lobby/nat.py) follows T5_NET_BIND too and binds every interface without it.

The C++ part needs a Windows C++ compiler (clang-cl + Visual Studio build tools); it is skipped without one.
"""
import ast
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT

if os.path.join(ROOT, "lobby") not in sys.path:
    sys.path.append(os.path.join(ROOT, "lobby"))

from t5lobby import nat  # noqa: E402
from t5lobby.handover import MatchTicket  # noqa: E402

# Tools that start games for local pairs (host + joiner on this PC, or a lobby on this PC).
LOCAL_PAIR_TOOLS = [
    "tools/e2e/e2e_harness.py", "tools/rollback_net_test.py", "tools/netplay_test.py", "tools/fight_flow_test.py",
    "tools/pick_flow_test.py", "tools/rb_equiv_test.py", "tools/replay_play.py", "tools/latency_test.py",
    "tools/tap_latch_test.py", "tools/training_check.py", "tools/cross_build_test.py", "tools/reset_cycle_test.py",
    "tools/soak/rtt_fight.py", "lobby/tools/two_players.py", "lobby/tools/relay_e2e.py",
    "lobby/tools/ranked_session.py", "lobby/tools/set_session.py", "lobby/tools/relay_latency.py",
    "lobby/tools/load_test.py",
]
SETDEFAULT = 'os.environ.setdefault("T5_NET_BIND", "127.0.0.1")'


def read(rel):
    with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


def ticket(path, peer, role="join"):
    return MatchTicket(match_id="m6208516c8782", role=role, slot=0 if role == "host" else 1, local_port=51000,
                       peer=peer, path=path, rtt_ms=31.0, jitter_ms=1.0, delay=1, seed=0x1234, build="b",
                       key="k" * 32)


class RuleTest(unittest.TestCase):
    """The C++ rule itself (the game's code, built on this PC)."""

    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows compiler")
        from test_ps_hid import find_vcvars
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not clang:
            raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
        cls.tmp = tempfile.mkdtemp(prefix="t5dr-netbind")
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        exe = os.path.join(cls.tmp, "net_bind_test.exe")
        src = os.path.join(ROOT, "tests", "c", "net_bind_test.cpp")
        inc = os.path.join(ROOT, "src", "netplay")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /O1 /EHsc /std:c++17 /W3 /WX /D_CRT_SECURE_NO_WARNINGS '
               f'/I "{inc}" "{src}" /Fe:"{exe}" /Fo:"{cls.tmp}\\\\"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600, cwd=cls.tmp)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/net_bind_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def choose(self, env):
        args = [env.get(k) or "-" for k in ("T5_NET_BIND", "T5_NET_PEER", "T5_NET_MATCH")]
        r = subprocess.run([self.exe, *args], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout)
        m = re.match(r"BIND (\S+) (.*)", r.stdout.strip())
        self.assertIsNotNone(m, r.stdout)
        return m.group(1)

    def test_cases_pass(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=30)
        self.assertEqual((r.returncode, r.stdout.strip().splitlines()[-1]), (0, "PASS"), r.stdout[-3000:])

    def test_real_lobby_match_binds_every_interface(self):
        for path, peer in (("direct", ("198.51.100.23", 51234)), ("lan", ("192.168.1.30", 51234)),
                           ("relay", ("46.224.146.6", 7781)), ("relay", ("127.0.0.1", 61000))):  # relay bridge
            for role in ("host", "join"):
                env = ticket(path, peer, role).game_env()
                self.assertNotIn("T5_NET_BIND", env)
                self.assertEqual(self.choose(env), "0.0.0.0", (path, peer, role))

    def test_test_pairs_bind_loopback(self):
        host = {"T5_NET_MODE": "host", "T5_NET_PORT": "7000", "T5_NET_BIND": "127.0.0.1"}
        join = {"T5_NET_MODE": "join", "T5_NET_PORT": "0", "T5_NET_PEER": "127.0.0.1:7000", "T5_NET_BIND": "127.0.0.1"}
        self.assertEqual((self.choose(host), self.choose(join)), ("127.0.0.1", "127.0.0.1"))
        # a local lobby test: the tool's T5_NET_BIND reaches the game through the launcher's environment
        env = dict(ticket("lan", ("127.0.0.1", 52001)).game_env(), T5_NET_BIND="127.0.0.1")
        self.assertEqual(self.choose(env), "127.0.0.1")
        # without T5_NET_BIND only the joiner of a plain pair knows the peer is local
        self.assertEqual(self.choose({"T5_NET_PEER": "127.0.0.1:7000"}), "127.0.0.1")
        self.assertEqual(self.choose({}), "0.0.0.0")
        self.assertEqual(self.choose({"T5_NET_BIND": "nonsense", "T5_NET_PEER": "127.0.0.1:7000"}), "0.0.0.0")


class GameSourceTest(unittest.TestCase):
    def test_netplay_binds_the_rule_and_logs_it(self):
        src = read("src/netplay/netplay_core.cpp")
        self.assertIn('choose_bind(env("T5_NET_BIND"), env("T5_NET_PEER"), env("T5_NET_MATCH"))', src)
        self.assertIn("local.sin_addr.s_addr = htonl(bc.addr);", src)
        self.assertNotIn("htonl(INADDR_ANY)", src)
        self.assertRegex(src, r'note\("hosting on UDP %s:%d \(bind: %s\)", bind_ip, port, bc\.why\)')
        self.assertRegex(src, r'note\("joining %s from UDP %s:%d \(bind: %s\)", peer, bind_ip, port, bc\.why\)')

    def test_no_other_socket_in_src(self):
        """The netplay socket is the game's only one (replay playback and local mode open none)."""
        hits = []
        for d, _dirs, files in os.walk(os.path.join(ROOT, "src")):
            for f in files:
                if f.endswith((".c", ".cpp", ".h")):
                    with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                        if re.search(r"\b(bind|listen|WSASocketW?)\s*\(", fh.read()):
                            hits.append(os.path.relpath(os.path.join(d, f), ROOT).replace("\\", "/"))
        self.assertEqual(hits, ["src/netplay/netplay_core.cpp"])


class ToolsTest(unittest.TestCase):
    def test_local_pair_tools_set_it_with_setdefault(self):
        for rel in LOCAL_PAIR_TOOLS:
            src = read(rel)
            self.assertIn(SETDEFAULT, src, rel)
            tree = ast.parse(src)
            top = [ast.unparse(n) for n in tree.body if isinstance(n, ast.Expr)]
            self.assertIn(ast.unparse(ast.parse(SETDEFAULT).body[0]), top, f"{rel}: not at module level")

    def test_dryrun_sets_it_only_for_a_local_lobby(self):
        src = read("tools/dryrun_online.py")
        i = src.index('os.environ.setdefault("T5_NET_BIND", "127.0.0.1")')
        self.assertIn('if host == "localhost" or host.startswith("127."):', src[max(0, i - 600):i])

    def test_launcher_never_sets_it(self):
        for rel in ("launcher/core.py", "tools/run_game.py", "lobby/t5lobby/handover.py", "lobby/t5lobby/client.py",
                    "lobby/t5lobby/match_driver.py", "launcher/t5dr_launcher.pyw"):
            self.assertNotIn("T5_NET_BIND", read(rel), rel)
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        try:
            import run_game
        finally:
            sys.path.pop(0)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("T5_NET_BIND", None)
            _cmd, env, _cwd = run_game.game_command(ROOT, {"T5_NET_MODE": "host"})
        self.assertNotIn("T5_NET_BIND", env)

    def test_stub_game_binds_loopback(self):
        sys.path.insert(0, os.path.join(ROOT, "lobby", "tools"))
        try:
            import stub_game
        finally:
            sys.path.pop(0)
        self.assertEqual(stub_game.bind_ip({}), "127.0.0.1")
        self.assertEqual(stub_game.bind_ip({"T5_NET_BIND": "bad"}), "127.0.0.1")
        self.assertEqual(stub_game.bind_ip({"T5_NET_BIND": "127.0.0.2"}), "127.0.0.2")
        self.assertNotIn('"0.0.0.0"', read("lobby/tools/stub_game.py"))


class LobbyClientSocketTest(unittest.TestCase):
    def test_bind_ip(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("T5_NET_BIND", None)
            self.assertEqual(nat.bind_ip(), "0.0.0.0")             # players: every interface, as before
            for v, want in (("127.0.0.1", "127.0.0.1"), (" 127.0.0.1 ", "127.0.0.1"), ("0.0.0.0", "0.0.0.0"),
                            ("localhost", "0.0.0.0"), ("127.0.0.1:7000", "0.0.0.0"), ("", "0.0.0.0")):
                os.environ["T5_NET_BIND"] = v
                self.assertEqual(nat.bind_ip(), want, v)

    def test_game_socket_on_loopback(self):
        with mock.patch.dict(os.environ, {"T5_NET_BIND": "127.0.0.1"}):
            s = nat.open_udp_socket(0)
            try:
                self.assertEqual(s.getsockname()[0], "127.0.0.1")
            finally:
                s.close()
            self.assertEqual(nat.local_ipv4s("127.0.0.1"), ["127.0.0.1"])   # the only address a peer can reach
            port = nat.free_udp_port()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.bind(("127.0.0.1", port))
            finally:
                s.close()


if __name__ == "__main__":
    unittest.main()
