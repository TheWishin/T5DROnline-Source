"""Test helpers: a lobby server on its own thread (localhost, ephemeral ports, in-memory DB)
and clients with test builds."""
import asyncio
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from t5lobby import proto  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.server import Config, LobbyServer  # noqa: E402

BUILD = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "0123456789abcdef", "test")
OTHER_BUILD = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "fedcba9876543210", "test-other")

FAST = dict(host="127.0.0.1", port=0, udp_port=0, udp_port2=-1, db=":memory:", scrypt_n=1 << 10,
            ready_timeout=5.0, register_timeout=4.0, punch_timeout=1.5, relay_timeout=5.0,
            result_timeout=2.0, log_level="WARNING", min_match_seconds=0.0, reconnect_grace=2.0)


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
