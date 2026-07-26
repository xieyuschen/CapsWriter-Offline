import multiprocessing
import os
import socket
import threading
import unittest
from pathlib import Path

from util.app_runtime import ServerSupervisor


@unittest.skipUnless(
    os.environ.get("CAPSWRITER_RUN_MODEL_TEST") == "1",
    "set CAPSWRITER_RUN_MODEL_TEST=1 to load the real models",
)
class ServerIntegrationTests(unittest.TestCase):
    def test_supervisor_reports_ready_and_releases_port_on_stop(self):
        ready = threading.Event()
        errors = []

        def callback(event):
            if event["type"] == "ready":
                ready.set()
            elif event["type"] == "error":
                errors.append(event["message"])
                ready.set()

        supervisor = ServerSupervisor(
            multiprocessing.get_context("spawn"),
            Path(__file__).resolve().parents[1],
            callback,
        )
        try:
            supervisor.start()
            self.assertTrue(ready.wait(90), "server didn't report ready")
            self.assertEqual(errors, [])
            with socket.create_connection(("127.0.0.1", 6016), timeout=2):
                pass
        finally:
            supervisor.stop(timeout=10)

        with socket.socket() as probe:
            probe.settimeout(1)
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", 6016)), 0)


if __name__ == "__main__":
    unittest.main()
