"""Exercise the test harness entry point without creating a lobby server.

The event loop and worker thread are real. Only the server constructor is
replaced, so a failed startup must still cross the actual thread boundary.
"""
import asyncio
import threading
import unittest
from unittest import mock

import util


class ServerThreadLifecycleTest(unittest.TestCase):
    def make_thread(self):
        harness = util.ServerThread()
        self.addCleanup(self.cleanup_thread, harness)
        return harness

    @staticmethod
    def cleanup_thread(harness):
        # Keep the old, failing implementation from leaking a loop during the
        # regression demonstration; this is independent of util.stop().
        if harness.thread.is_alive():
            harness.loop.call_soon_threadsafe(harness.loop.stop)
            harness.thread.join(2)
        if not harness.thread.is_alive() and not harness.loop.is_closed():
            harness.loop.close()

    def assert_startup_failure(self, factory, error):
        harness = self.make_thread()
        thread_errors = []
        with mock.patch.object(util, "LobbyServer", factory), \
                mock.patch.object(threading, "excepthook", thread_errors.append):
            with self.assertRaisesRegex(RuntimeError, str(error)) as raised:
                harness.start()
        self.assertIs(raised.exception.__cause__, error)
        self.assertFalse(harness.thread.is_alive())
        self.assertTrue(harness.loop.is_closed())
        self.assertEqual(thread_errors, [])

    def test_constructor_failure_reaches_start_with_its_cause(self):
        error = ValueError("synthetic constructor rejection")
        self.assert_startup_failure(mock.Mock(side_effect=error), error)

    def test_async_start_failure_reaches_start_with_its_cause(self):
        error = OSError("synthetic startup rejection")

        class FailedServer:
            def __init__(self, cfg):
                pass

            async def start(self):
                await asyncio.sleep(0)
                raise error

        self.assert_startup_failure(FailedServer, error)

    def test_success_still_serves_calls_and_stops_cleanly(self):
        lifecycle = []

        class SuccessfulServer:
            def __init__(self, cfg):
                lifecycle.append(("construct", threading.get_ident()))

            async def start(self):
                await asyncio.sleep(0)
                lifecycle.append(("start", threading.get_ident()))

            async def stop(self):
                lifecycle.append(("stop", threading.get_ident()))

        harness = self.make_thread()
        with mock.patch.object(util, "LobbyServer", SuccessfulServer):
            self.assertIs(harness.start(), harness)
            worker = harness.call(threading.get_ident)
            self.assertNotEqual(worker, threading.get_ident())
            self.assertEqual(harness.call(lambda a, b: a + b, 19, 23), 42)
            harness.stop()
        self.assertEqual(lifecycle, [("construct", worker), ("start", worker), ("stop", worker)])
        self.assertFalse(harness.thread.is_alive())
        self.assertTrue(harness.loop.is_closed())

    def test_shutdown_failure_still_closes_the_worker_and_loop(self):
        error = OSError("synthetic shutdown rejection")

        class FailedShutdownServer:
            def __init__(self, cfg):
                pass

            async def start(self):
                await asyncio.sleep(0)

            async def stop(self):
                await asyncio.sleep(0)
                raise error

        harness = self.make_thread()
        with mock.patch.object(util, "LobbyServer", FailedShutdownServer):
            harness.start()
            with self.assertRaises(OSError) as raised:
                harness.stop()
        self.assertIs(raised.exception, error)
        self.assertFalse(harness.thread.is_alive())
        self.assertTrue(harness.loop.is_closed())


if __name__ == "__main__":
    unittest.main()
