"""Test helpers: a lobby server on its own thread (localhost, ephemeral ports, in-memory DB)
and clients with test builds."""
import asyncio
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
# The Online tab must not start reading this PC's real controllers during a test (a plugged-in pad would put
# "(A)" on the buttons the tests look for by name); the pad tests give the tab fake ones.
os.environ.setdefault("T5_PAD_NAV", "0")
# No chime and no flashing taskbar button from the Online tab on the PC that runs the tests (test_tk_notify.py gives it fakes).
os.environ["T5_NOTIFY"] = "0"
# Never ask the router of the PC that runs the tests for a port forward (port mapping tests use fakes).
os.environ["T5_PORTMAP"] = "0"
# The Online tab's firewall hint does not read this PC's Windows Firewall (test_firewall.py feeds the check its data).
os.environ.setdefault("T5_FW_CHECK", "0")
# Every test player is on this PC: game sockets (the lobby client's, t5lobby/nat.py bind_ip, and the tests'
# stand-ins for the game) bind 127.0.0.1, not every interface -- no Windows Firewall prompt
# (docs/NETPLAY.md "Bind address"). An explicit T5_NET_BIND wins.
os.environ.setdefault("T5_NET_BIND", "127.0.0.1")
GAME_IP = os.environ["T5_NET_BIND"]

from t5lobby import proto  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.server import Config, LobbyServer  # noqa: E402

BUILD = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "0123456789abcdef", "test")
OTHER_BUILD = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "fedcba9876543210", "test-other")

FAST = dict(host="127.0.0.1", port=0, udp_port=0, udp_port2=-1, db=":memory:", scrypt_n=1 << 10,
            ready_timeout=5.0, register_timeout=4.0, punch_timeout=1.5, relay_timeout=5.0,
            result_timeout=2.0, log_level="WARNING", min_match_seconds=0.0, reconnect_grace=2.0,
            status_port=0, pair_cooldown=0.0,       # (the tests of the same-opponent cooldown and of the blind ready check
            blind_ready=False,              # switch these two on; everything older runs the way it always did)
            ranked_same_ip=True,            # every test player is on 127.0.0.1 (test_abuse switches it off)
            max_match_seconds=0.0)          # lone reports are settled after result_timeout (test_abuse: the wait)


def coin_keeps_the_sides():
    """The server's side coin (server/casual.py, 1.1.7) fixed to 0: a ranked rematch keeps P1 and P2, so it may go on
    inside the running games -- for tests of that path (a coin of 1 makes it a new netplay session, test_sides.py)."""
    from unittest import mock
    from t5lobby.server import casual
    return mock.patch.object(casual, "_side_coin", return_value=0)


class ServerThread:
    def __init__(self, **cfg):
        kw = dict(FAST)
        kw.update(cfg)
        self.cfg = Config(**kw)
        self.loop = proto.new_event_loop()
        self.srv = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self._ready = threading.Event()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.srv = LobbyServer(self.cfg)
        self.loop.run_until_complete(self.srv.start())
        self._ready.set()
        self.loop.run_forever()

    def start(self):
        self.thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("server did not start")
        return self

    @property
    def addr(self):
        return f"127.0.0.1:{self.srv.port}"

    def call(self, fn, *args):
        """Run fn(*args) on the server's loop thread and return its result."""
        async def wrap():
            return fn(*args)
        return asyncio.run_coroutine_threadsafe(wrap(), self.loop).result(10)

    def stop(self):
        asyncio.run_coroutine_threadsafe(self.srv.stop(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)
        self.loop.close()

    def wait_for(self, pred, timeout=10.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self.call(pred):
                return True
            time.sleep(0.02)
        return False


def client(server, name=None, build=BUILD, password=None, register=False, **kw):
    # The relay tests check the server's relay itself: the relay bridge (two new clients keep the game socket
    # and talk to the game on 127.0.0.1) has its own tests in test_nat2.py.
    kw.setdefault("relay_bridge", False)
    c = LobbyClient(server.addr, build, **kw)
    c.connect()
    if name:
        if register:
            c.register(name, password)
        elif password:
            c.login(name, password)
        else:
            c.login_guest(name)
    return c


def expect(c, types, timeout=10.0):
    if isinstance(types, str):
        types = (types,)
    ev = c.next_event(timeout, types)
    if ev is None:
        raise AssertionError(f"no {types} event within {timeout}s")
    return ev
