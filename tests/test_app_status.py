import unittest

from core.app_status import AppState, RuntimeInfo, StatusBus


class StatusBusTests(unittest.TestCase):
    def test_subscriber_receives_replay_and_transition(self):
        bus = StatusBus()
        snapshots = []

        listener_id = bus.subscribe(snapshots.append)
        changed = bus.set(AppState.READY, "ready")
        bus.unsubscribe(listener_id)
        bus.set(AppState.ERROR, "ignored")

        self.assertTrue(changed)
        self.assertEqual(
            [snapshot.state for snapshot in snapshots],
            [AppState.STARTING, AppState.READY],
        )

    def test_runtime_info_only_notifies_on_change(self):
        info = RuntimeInfo()
        names = []
        info.subscribe(names.append, replay=False)

        self.assertTrue(info.set_microphone("USB Mic"))
        self.assertFalse(info.set_microphone("USB Mic"))
        self.assertEqual(names, ["USB Mic"])


if __name__ == "__main__":
    unittest.main()
