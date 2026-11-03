"""Run the old-stage fixture lifecycle without constructing a lobby server."""
import types
import unittest
from unittest import mock

import test_old_stages as stages


class FixtureIsolationTest(unittest.TestCase):
    def setUp(self):
        class Table:
            def resolve(self, *args, **kwargs):
                return "resolved"

        self.table = Table()
        self.lifecycle = []
        self.threads = []
        owner = self

        class OfflineThread:
            def __init__(self, **cfg):
                self.srv = types.SimpleNamespace(table=owner.table)
                owner.threads.append(self)

            def start(self):
                return self

            def stop(self):
                owner.lifecycle.append("server stopped")

            def call(self, fn):
                raise RuntimeError("synthetic later setup failure")

        patch = mock.patch.object(stages, "ServerThread", OfflineThread)
        patch.start()
        self.addCleanup(patch.stop)

    def run_fixture(self, fixture):
        result = unittest.TestResult()
        fixture.run(result)
        return result

    def test_success_restores_shared_resolver_before_next_fixture(self):
        table = self.table

        class Fixture(stages.ServerTest):
            def runTest(self):
                self.assertEqual(table.resolve(old_stages=True), "resolved")
                self.assertEqual(self.calls, [True])

        first = Fixture()
        first_result = self.run_fixture(first)
        self.assertTrue(first_result.wasSuccessful(), first_result.errors + first_result.failures)
        self.assertNotIn("resolve", vars(table))
        second_result = self.run_fixture(Fixture())
        self.assertTrue(second_result.wasSuccessful(), second_result.errors + second_result.failures)
        self.assertEqual(first.calls, [True])
        self.assertEqual(self.lifecycle, ["server stopped", "server stopped"])

    def test_new_caps_setup_failure_restores_resolver_and_stops_server(self):
        result = self.run_fixture(stages.NewCapsTest("test_hello_keeps_every_cap"))
        self.assertEqual(len(result.errors), 1)
        self.assertIn("synthetic later setup failure", result.errors[0][1])
        self.assertNotIn("resolve", vars(self.table))
        self.assertEqual(self.lifecycle, ["server stopped"])

    def test_later_setup_failure_closes_client_and_server(self):
        lifecycle = self.lifecycle

        class Fixture(stages.ServerTest):
            def setUp(self):
                super().setUp()
                self.acc("Synthetic")
                raise RuntimeError("synthetic setup after client")

            def runTest(self):
                self.fail("setup failure must prevent the body")

        client = types.SimpleNamespace(close=lambda: lifecycle.append("client closed"))
        with mock.patch.object(stages, "client", return_value=client):
            result = self.run_fixture(Fixture())
        self.assertEqual(len(result.errors), 1)
        self.assertIn("synthetic setup after client", result.errors[0][1])
        self.assertNotIn("resolve", vars(self.table))
        self.assertEqual(lifecycle, ["client closed", "server stopped"])


if __name__ == "__main__":
    unittest.main()
