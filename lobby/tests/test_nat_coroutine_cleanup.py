"""NAT task cancellation with in-memory coroutines; no sockets or server contact."""
import asyncio
import inspect
import unittest

import util  # noqa: F401 -- shared import path only
from t5lobby.client import LobbyClient


class NatCoroutineCleanupTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = LobbyClient("127.0.0.1:7781", util.BUILD)
        self.client.match = {"match": "offline-match"}
        self.created = []
        self.started = []

        def register(msg):
            async def phase():
                self.started.append(msg["sequence"])

            coro = phase()
            self.created.append(coro)
            return coro

        self.client._nat_register = register

    def tearDown(self):
        # Keep a failing regression from producing its own unawaited-coroutine warning.
        for coro in self.created:
            coro.close()

    def assert_phases_closed(self):
        for coro in self.created:
            self.assertEqual(inspect.getcoroutinestate(coro), inspect.CORO_CLOSED)

    async def test_socket_cleanup_before_phase_starts_leaves_no_unawaited_coroutine(self):
        await self.client._on_nat_begin({"match": "offline-match", "sequence": 1})
        task = self.client._nat_task
        await self.client._drop_game_socket()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(self.started, [])
        self.assert_phases_closed()

    async def test_replacing_a_phase_before_it_starts_leaves_no_unawaited_coroutine(self):
        await self.client._on_nat_begin({"match": "offline-match", "sequence": 1})
        first = self.client._nat_task
        await self.client._on_nat_begin({"match": "offline-match", "sequence": 2})
        await asyncio.gather(first, self.client._nat_task, return_exceptions=True)
        self.assertEqual(self.started, [2])
        self.assert_phases_closed()

    async def test_phase_error_still_reports_nat_error(self):
        async def fail(msg):
            raise OSError("offline failure")

        self.client._nat_register = fail
        await self.client._on_nat_begin({"match": "offline-match"})
        await self.client._nat_task
        self.assertEqual(self.client.events.get_nowait(), {
            "t": "notice", "code": "nat_error", "msg": "OSError: offline failure"})

    async def test_started_phase_cancellation_still_runs_cleanup_without_notice(self):
        started = asyncio.Event()
        cleaned = []

        async def register(msg):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaned.append(True)

        self.client._nat_register = register
        await self.client._on_nat_begin({"match": "offline-match"})
        await started.wait()
        await self.client._drop_game_socket()
        await self.client._nat_task
        self.assertEqual(cleaned, [True])
        self.assertTrue(self.client.events.empty())


if __name__ == "__main__":
    unittest.main()
