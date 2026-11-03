"""Spectator cancellation races, with an in-memory client and no server or game."""
import asyncio
import os
import tempfile
import unittest
from unittest import mock

import util  # noqa: F401 (sets sys.path; no server is started)
from t5lobby import spectate


class Client(spectate.ClientMixin):
    def __init__(self, folder):
        self._spec_init(True, watch_dir=folder)
        self._loop = None
        self._tasks = []
        self.connected = True
        self.sent = []
        self.events = []
        self.replies = []

    async def _request(self, msg):
        msg["rid"] = len(self.replies) + 1
        reply = asyncio.get_running_loop().create_future()
        self.replies.append(reply)
        self.sent.append(dict(msg))
        return await reply

    async def _send(self, msg):
        self.sent.append(msg)

    async def _safe(self, coro):
        return await coro

    def _emit(self, msg):
        self.events.append(msg)


class WatchCancellationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = Client(self.tmp.name)

    async def asyncTearDown(self):
        await self.c._spec_shutdown()

    async def pending(self):
        task = asyncio.create_task(self.c._spec_request_watch({"t": "watch", "room": "r1"},
                                                              self.c.spec_generation))
        await asyncio.sleep(0)
        return task

    async def reply(self, rid=1):
        return await self.c._on_watching({"t": "watching", "re": rid, "stream": "m0123456789ab"})

    async def test_cancelled_reply_cannot_recreate_receiver(self):
        task = await self.pending()
        self.c.cancel_watch()
        self.assertFalse(await self.reply())
        self.c.replies[0].set_result({"t": "watching"})
        await task
        self.assertIsNone(self.c.spec_watch)
        self.assertEqual(os.listdir(self.tmp.name), [])

    async def test_queued_worker_cancelled_before_it_starts_sends_nothing(self):
        generation = self.c.spec_generation
        self.c.cancel_watch()
        result = await self.c._spec_request_watch({"t": "watch", "room": "r1"}, generation)
        self.assertIsNone(result)
        self.assertEqual(self.c.sent, [])

    async def test_wrong_reply_id_does_not_authorize_file_or_consume_request(self):
        task = await self.pending()
        self.assertFalse(await self.reply(rid=99))
        self.assertIsNone(self.c.spec_watch)
        await self.reply()
        self.assertIsNotNone(self.c.spec_watch)
        self.c.replies[0].set_result({"t": "watching"})
        await task

    async def test_failed_request_revokes_authorization(self):
        task = await self.pending()
        self.c.replies[0].set_exception(TimeoutError())
        with self.assertRaises(TimeoutError):
            await task
        self.assertFalse(await self.reply())
        self.assertEqual(os.listdir(self.tmp.name), [])

    async def test_nonblocking_cancel_closes_receiver_and_sends_unwatch(self):
        task = await self.pending()
        await self.reply()
        self.c.replies[0].set_result({"t": "watching"})
        await task
        old = self.c.spec_watch
        self.c._loop = asyncio.get_running_loop()
        self.c.cancel_watch()
        await asyncio.sleep(0)  # cancellation callback queues its cleanup coroutine
        await asyncio.gather(*self.c._tasks)
        self.assertIsNone(self.c.spec_watch)
        self.assertTrue(old["receiver"].closed)
        self.assertEqual(self.c.sent[-1], {"t": "unwatch"})
        parser = spectate.LiveParser()
        with open(old["path"], "rb") as f:
            parser.feed(f.read())
        self.assertTrue(parser.ended)
        self.assertEqual(parser.end_why, "left")

    async def test_old_cleanup_does_not_close_a_new_receiver(self):
        old = {"receiver": mock.Mock()}
        new = {"receiver": mock.Mock()}
        self.c.spec_watch = new
        await self.c._spec_unwatch(old)
        self.assertIs(self.c.spec_watch, new)
        old["receiver"].close.assert_called_once_with("left")
        new["receiver"].close.assert_not_called()
        self.assertEqual(self.c.sent, [])

    async def test_stream_end_closes_at_a_whole_record_and_rejects_more_data(self):
        task = await self.pending()
        await self.reply()
        self.c.replies[0].set_result({"t": "watching"})
        await task
        old = self.c.spec_watch
        msg = {"t": "spec_end", "stream": old["stream"], "reason": "not_allowed"}
        await self.c._on_spec_end(msg)
        self.assertIsNone(self.c.spec_watch)
        self.assertTrue(old["receiver"].closed)
        self.assertFalse(await self.c._on_spec_data({"stream": old["stream"], "off": 0, "data": ""}))
        parser = spectate.LiveParser()
        with open(old["path"], "rb") as f:
            parser.feed(f.read())
        self.assertTrue(parser.ended)
        self.assertEqual(parser.end_why, "not_allowed")


class ReceiverCloseTest(unittest.TestCase):
    def test_failed_end_write_still_closes_file(self):
        receiver = spectate.Receiver.__new__(spectate.Receiver)
        receiver.closed = False
        receiver.parser = spectate.LiveParser()
        receiver.f = mock.Mock()
        receiver.f.write.side_effect = OSError("disk unavailable")
        receiver.close("left")
        receiver.f.close.assert_called_once_with()


class WatchRequestTest(unittest.TestCase):
    def test_table_selector_and_generation_both_reach_watch_worker(self):
        class Client(spectate.ClientMixin):
            request_timeout = 3

            def _run(self, coro, timeout):
                return asyncio.run(coro)

            async def _request(self, msg):
                return msg

        c = Client()
        c._spec_init(True)
        generation = c.spec_generation
        self.assertEqual(c.watch(room="room", table=2, generation=generation),
                         {"t": "watch", "room": "room", "table": 2})
        c._spec_cancel_state()
        self.assertIsNone(c.watch(room="room", table=2, generation=generation))


if __name__ == "__main__":
    unittest.main()
