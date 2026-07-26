import multiprocessing
import os
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from util.app_runtime import ServerSupervisor, SingleInstance, run_server_process


def fake_server(stop_event, status_queue, _base_dir):
    status_queue.put({"type": "loading", "message": "loading"})
    status_queue.put({"type": "ready", "message": "ready"})
    while not stop_event.wait(0.05):
        pass


def failing_server(_stop_event, _status_queue, _base_dir):
    raise SystemExit(7)


class SingleInstanceTests(unittest.TestCase):
    def test_only_one_instance_can_hold_lock(self):
        name = f"CapsWriter-Test-{uuid.uuid4()}"
        first = SingleInstance(name)
        second = SingleInstance(name)
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()


class ServerSupervisorTests(unittest.TestCase):
    def test_server_process_restores_standard_streams_after_failure(self):
        class Queue:
            def __init__(self):
                self.events = []

            def put(self, event):
                self.events.append(event)

        original_stdout = sys.stdout
        original_stderr = sys.stderr
        original_directory = Path.cwd()
        queue = Queue()
        try:
            with tempfile.TemporaryDirectory() as directory:
                with patch("core_server.init", side_effect=RuntimeError("boom")):
                    with self.assertRaises(RuntimeError):
                        run_server_process(None, queue, directory)
        finally:
            os.chdir(original_directory)

        self.assertIs(sys.stdout, original_stdout)
        self.assertIs(sys.stderr, original_stderr)
        self.assertTrue(queue.events)

    def test_reports_status_and_stops_child(self):
        ready = threading.Event()
        events = []

        def callback(event):
            events.append(event)
            if event["type"] == "ready":
                ready.set()

        with tempfile.TemporaryDirectory() as directory:
            supervisor = ServerSupervisor(
                multiprocessing.get_context("spawn"),
                Path(directory),
                callback,
                process_target=fake_server,
            )
            supervisor.start()
            self.assertTrue(ready.wait(5))
            self.assertTrue(supervisor.is_alive)
            supervisor.stop(timeout=2)
            self.assertFalse(supervisor.is_alive)

        self.assertEqual([event["type"] for event in events], ["loading", "ready"])

    def test_reports_unexpected_process_exit(self):
        failed = threading.Event()
        events = []

        def callback(event):
            events.append(event)
            if event["type"] == "error":
                failed.set()

        with tempfile.TemporaryDirectory() as directory:
            supervisor = ServerSupervisor(
                multiprocessing.get_context("spawn"),
                Path(directory),
                callback,
                process_target=failing_server,
            )
            supervisor.start()
            self.assertTrue(failed.wait(5))
            supervisor.stop(timeout=1)

        self.assertIn("意外退出", events[-1]["message"])


if __name__ == "__main__":
    unittest.main()
