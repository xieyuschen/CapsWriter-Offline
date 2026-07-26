import unittest

from util.app_status import AppState, StatusBus


class StatusBusTests(unittest.TestCase):
    def test_replays_latest_status_and_deduplicates_identical_transition(self):
        bus = StatusBus()
        seen = []
        listener_id = bus.subscribe(seen.append)

        self.assertFalse(bus.set(AppState.STARTING))
        self.assertTrue(bus.set(AppState.LOADING))
        self.assertFalse(bus.set(AppState.LOADING))
        self.assertEqual(
            [snapshot.state for snapshot in seen],
            [AppState.STARTING, AppState.LOADING],
        )

        late_seen = []
        bus.subscribe(late_seen.append)
        self.assertEqual(late_seen[0].state, AppState.LOADING)

        bus.unsubscribe(listener_id)
        bus.set(AppState.READY)
        self.assertEqual(len(seen), 2)

    def test_listener_failure_does_not_block_other_listeners(self):
        bus = StatusBus()
        seen = []

        def broken_listener(_snapshot):
            raise RuntimeError("GUI backend failed")

        bus.subscribe(broken_listener, replay=False)
        bus.subscribe(seen.append, replay=False)
        bus.set(AppState.ERROR, "test")

        self.assertEqual(seen[0].state, AppState.ERROR)


if __name__ == "__main__":
    unittest.main()
