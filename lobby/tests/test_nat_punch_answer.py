"""Hole punching: an answer to a punch is never answered without end (review 1.2.0, the punch-answer loop; the same
fix as OpenRecomp's T4 client 1ec3e9d).

Every punch was answered with a punch carrying its seq and F_HEARD, answers included, so one punch kept one packet
circling between the two sockets for as long as they lived -- a relay bridge keeps its game socket through the whole
match. Now one answer per (sender, seq): one punch makes at most three packets, the handshake still completes, a
new punch is answered again, and an older peer that answers everything gets one answer per seq. Two game sockets on
127.0.0.1 only (nothing leaves this PC). The relay bridge's direct-path tests (test_nat2, test_relays) and the e2e
relay scenarios cover the path switch on top of this."""
import asyncio
import os
import unittest
from unittest import mock

import util  # noqa: F401 -- sys.path, T5_PORTMAP=0
from t5lobby import nat, proto

TAG = b"m" * 8


class PunchAnswers(unittest.TestCase):
    def test_one_punch_is_answered_once_and_the_traffic_stops(self):
        async def run():
            with mock.patch.dict(os.environ, {"T5_NET_BIND": "127.0.0.1"}):
                server = ("127.0.0.1", 9)
                a = await nat.GameSocket.open(0, server, 0, b"t" * 16, TAG, 0)
                b = await nat.GameSocket.open(0, server, 0, b"u" * 16, TAG, 1)
            try:
                to_b, to_a = ("127.0.0.1", b.port), ("127.0.0.1", a.port)
                a._punch_to(to_b)
                await asyncio.sleep(0.3)
                first = (a.stats["tx"], b.stats["tx"])
                await asyncio.sleep(0.4)
                self.assertEqual((a.stats["tx"], b.stats["tx"]), first)      # nothing circling
                self.assertLessEqual(sum(first), 3)
                self.assertIn(to_b, a.confirmed)                            # the handshake still completes
                a._punch_to(to_b)                                           # a new punch is answered again
                await asyncio.sleep(0.3)
                self.assertIn(to_a, b.confirmed)
                self.assertGreater(b.stats["tx"], first[1])
                ok_before = a.last_ok[to_b]
                await asyncio.sleep(0.05)
                a._punch_to(to_b)                                           # the bridge's keepalive punch
                await asyncio.sleep(0.3)
                self.assertGreater(a.last_ok[to_b], ok_before)              # ... still refreshes the direct path
                # an older peer that answers every punch, answers included: still one answer per seq here
                before = b.stats["tx"]
                for _ in range(5):
                    b.datagram_received(proto.pk_punch(TAG, 0, proto.F_HEARD, 4242), to_a)
                self.assertEqual(b.stats["tx"], before + 1)
            finally:
                await a.close()
                await b.close()
        asyncio.run(run())

    def test_the_answered_list_stays_small(self):
        async def run():
            with mock.patch.dict(os.environ, {"T5_NET_BIND": "127.0.0.1"}):
                a = await nat.GameSocket.open(0, ("127.0.0.1", 9), 0, b"t" * 16, TAG, 0)
            sent = []
            a.send = lambda data, addr, ttl=None: sent.append(addr)        # nothing on the wire
            try:
                for seq in range(2000):
                    a.datagram_received(proto.pk_punch(TAG, 1, 0, seq), ("127.0.0.1", 9999))
                self.assertLessEqual(len(a.answered), nat.GameSocket.ANSWERED_MAX)
                self.assertEqual(len(sent), 2000)                           # every new punch answered
            finally:
                await a.close()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
