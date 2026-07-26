import unittest
from unittest.mock import patch

try:
    from config import ClientConfig
    from util.app_status import AppState, app_status
    from util.client_cosmic import Cosmic
    import util.client_shortcut_handler as shortcut
except ImportError:
    shortcut = None


class FakeFuture:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def done(self):
        return self.cancelled


class FakeQueue:
    async def put(self, _item):
        return None


@unittest.skipIf(shortcut is None, "client dependencies aren't installed")
class ClientStateTests(unittest.TestCase):
    def tearDown(self):
        Cosmic.on = False
        Cosmic.loop = None
        Cosmic.websocket = None
        shortcut.task = None

    @staticmethod
    def fake_submit(coroutine, _loop):
        coroutine.close()
        return FakeFuture()

    def test_recording_finish_and_disconnected_transitions(self):
        Cosmic.loop = object()
        Cosmic.websocket = type("WebSocket", (), {"closed": False})()
        Cosmic.queue_in = FakeQueue()

        with patch.object(
            shortcut.asyncio,
            "run_coroutine_threadsafe",
            side_effect=self.fake_submit,
        ):
            self.assertTrue(shortcut.launch_task())
            self.assertEqual(app_status.current.state, AppState.RECORDING)
            shortcut.finish_task()
            self.assertEqual(app_status.current.state, AppState.PROCESSING)

        Cosmic.websocket.closed = True
        self.assertFalse(shortcut.launch_task())
        self.assertEqual(app_status.current.state, AppState.DISCONNECTED)

    def test_default_short_click_toggles_recording(self):
        self.assertFalse(ClientConfig.hold_mode)
        released = shortcut.Event()
        released.set()

        def launch():
            Cosmic.on = 100.0
            return True

        def finish():
            Cosmic.on = False

        with (
            patch.object(shortcut, "launch_task", side_effect=launch) as launch_mock,
            patch.object(shortcut, "finish_task", side_effect=finish) as finish_mock,
        ):
            shortcut.manage_task(released)
            launch_mock.assert_called_once_with()
            finish_mock.assert_not_called()
            self.assertTrue(Cosmic.on)

            shortcut.manage_task(released)
            finish_mock.assert_called_once_with()
            self.assertFalse(Cosmic.on)


if __name__ == "__main__":
    unittest.main()
