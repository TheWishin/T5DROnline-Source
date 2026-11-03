"""Exercise the tournament fixture's signup barrier without starting a server.

The existing fixture and production create/join/tick handlers run with an
in-memory store. Only transport, player notifications and the clock are fakes.
"""
import asyncio
from types import SimpleNamespace
import unittest
from unittest import mock

import test_tournaments as tournaments_test
from t5lobby.server import Config
from t5lobby.server.store import Store
from t5lobby.server.tournaments import CAP, TourManager


class SignupFixtureTest(unittest.TestCase):
    def setUp(self):
        self.now = 1_000_000.0
        self.loop = asyncio.new_event_loop()
        self.addCleanup(self.loop.close)
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        cfg = Config(tour_organizers="any", tour_max_days=14)
        srv = SimpleNamespace(cfg=cfg, store=self.store, by_name={}, players={},
                              name_blocked=lambda name: False, _count=mock.Mock())
        self.manager = TourManager(srv)
        srv.tours = self.manager
        # Calls and announcements leave the handler boundary. No player is
        # connected; the real bracket and tournament state still run.
        self.manager._call_open = mock.Mock()
        self.manager._announce = mock.Mock()
        self.fixture = tournaments_test.TourBase()
        self.fixture.s = SimpleNamespace(cfg=cfg, srv=srv, call=lambda fn: fn())
        self.fixture.f = SimpleNamespace(c={})
        owner = self

        class OfflineClient:
            def __init__(self, number, name):
                self.conn = SimpleNamespace(
                    player=SimpleNamespace(account_id=number, name=name, build_id="synthetic"), caps={CAP})

            def tour_create(self, name, fmt="single", **kw):
                msg = dict(kw, name=name, format=fmt)
                return owner.loop.run_until_complete(owner.manager.h_create(self.conn, msg))["tournament"]

            def tour_join(self, tid):
                # Simulate serial RPCs taking longer than the original entire
                # half-second signup window, without relying on wall-clock load.
                owner.now += 0.3
                owner.manager.tick()
                msg = {"tournament": tid}
                return owner.loop.run_until_complete(owner.manager.h_join(self.conn, msg))["tournament"]

        for number, name in enumerate(self.fixture.names, 1):
            self.fixture.f.c[name] = OfflineClient(number, name)
        self.fixture.org = self.fixture.f.c[self.fixture.names[0]]

        def wait_state(tid, state):
            tour = self.manager.tours[tid]
            self.assertEqual(set(tour.entrants), {1, 2, 3, 4})
            self.now = tour.start_time
            self.manager.tick()
            self.assertEqual(tour.state, state)

        self.fixture.wait_state = mock.Mock(side_effect=wait_state)
        patch = mock.patch.object(tournaments_test.time, "time", lambda: self.now)
        patch.start()
        self.addCleanup(patch.stop)
        # Event-loop construction above may use an internal socket pair on
        # Windows; no transport/socket can be opened by the actual handlers.
        patch = mock.patch("socket.socket.__init__", side_effect=AssertionError("unexpected socket"))
        patch.start()
        self.addCleanup(patch.stop)

    def check_deadline(self, start_in, wait=False, **kw):
        began = self.now
        tid = self.fixture.create(start_in=start_in, wait=wait, **kw)
        tour = self.manager.tours[tid]
        self.assertEqual(set(tour.entrants), {1, 2, 3, 4})
        # All four slow joins precede the unchanged requested countdown.
        self.assertAlmostEqual(tour.start_time, began + 1.2 + start_in)
        row = self.store._x("SELECT start_time FROM tournaments WHERE id = ?", (tid,)).fetchone()
        self.assertEqual(row["start_time"], tour.start_time)
        if wait and start_in < 5:
            self.fixture.wait_state.assert_called_once_with(tid, "running")
            self.assertEqual(tour.state, "running")
        else:
            self.fixture.wait_state.assert_not_called()
            self.assertEqual(tour.state, "checkin" if kw.get("checkin_minutes") else "signup")
            self.now = tour.start_time - 0.001
            self.manager.tick()
            self.assertNotEqual(tour.state, "running")
            self.now = tour.start_time
            self.manager.tick()
            self.assertEqual(tour.state, "running")
        return tour

    def test_slow_signup_finishes_before_the_default_countdown(self):
        self.check_deadline(0.5, wait=True)

    def test_wait_false_preserves_automatic_start(self):
        self.check_deadline(2.0)

    def test_long_countdown_remains_unwaited(self):
        self.check_deadline(600.0)

    def test_joining_inside_the_checkin_window_still_checks_in(self):
        tour = self.check_deadline(0.5, checkin_minutes=5)
        self.assertTrue(all(e.checked_in is not None for e in tour.entrants.values()))


if __name__ == "__main__":
    unittest.main()
