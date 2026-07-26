import unittest
from pathlib import Path

from core.app_runtime import UnifiedCapsWriterApplication
from core.app_status import AppState, app_status


class FakeContext:
    pass


class FakeTray:
    def __init__(self):
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1


class FakeClient:
    def __init__(self):
        self.tray = FakeTray()
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1


class FakeSupervisor:
    def __init__(self, callback, event):
        self.callback = callback
        self.event = event
        self.starts = 0
        self.stops = 0
        self.restarts = 0

    def start(self):
        self.starts += 1
        self.callback(self.event)

    def stop(self):
        self.stops += 1

    def restart(self):
        self.restarts += 1


class UnifiedApplicationTests(unittest.TestCase):
    def make_application(self, event):
        client = FakeClient()
        application = UnifiedCapsWriterApplication(
            Path.cwd(),
            context=FakeContext(),
            client_factory=lambda: client,
        )
        supervisor = FakeSupervisor(application._server_event, event)
        application._supervisor = supervisor
        return application, client, supervisor

    def test_starts_tray_before_client_and_stops_both_sides(self):
        application, client, supervisor = self.make_application(
            {"type": "ready", "message": "ready"}
        )

        application.run()
        application.stop()

        self.assertEqual(client.tray.starts, 1)
        self.assertEqual(client.starts, 1)
        self.assertEqual(client.stops, 1)
        self.assertEqual(supervisor.starts, 1)
        self.assertEqual(supervisor.stops, 1)
        self.assertEqual(app_status.current.state, AppState.STOPPING)

    def test_server_error_does_not_start_microphone_client(self):
        application, client, _supervisor = self.make_application(
            {"type": "error", "message": "missing model"}
        )

        with self.assertRaisesRegex(RuntimeError, "missing model"):
            application.run()
        application.stop()

        self.assertEqual(client.starts, 0)
        self.assertEqual(client.tray.stops, 1)


if __name__ == "__main__":
    unittest.main()
