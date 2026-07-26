import tempfile
import threading
import unittest
from pathlib import Path

from util.application import CapsWriterApplication


class FakeSupervisor:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class ApplicationTests(unittest.TestCase):
    def test_ready_server_starts_client_once(self):
        with tempfile.TemporaryDirectory() as directory:
            application = CapsWriterApplication(Path(directory))
            started = threading.Event()

            def client():
                started.set()
                application._client_stop.wait(2)

            application._run_client = client

            application._server_event({"type": "ready", "message": "ready"})
            self.assertTrue(started.wait(2))
            first_thread = application._client_thread
            application._server_event({"type": "ready", "message": "ready"})

            self.assertIs(application._client_thread, first_thread)
            application.shutdown()

    def test_shutdown_signals_client_and_stops_server(self):
        with tempfile.TemporaryDirectory() as directory:
            application = CapsWriterApplication(Path(directory))
            supervisor = FakeSupervisor()
            application._supervisor = supervisor
            client_stopped = threading.Event()

            def client():
                application._client_stop.wait(2)
                client_stopped.set()

            application._client_thread = threading.Thread(target=client)
            application._client_thread.start()
            application.shutdown()

            self.assertTrue(client_stopped.is_set())
            self.assertTrue(supervisor.stopped)


if __name__ == "__main__":
    unittest.main()
