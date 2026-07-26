import unittest
from unittest.mock import patch

from config import ClientConfig
from util.app_info import app_info

try:
    import util.client_stream as client_stream
except ImportError:
    client_stream = None


@unittest.skipIf(client_stream is None, "client audio dependencies aren't installed")
class ClientStreamTests(unittest.TestCase):
    def tearDown(self):
        ClientConfig.mic_device = None
        app_info.set_microphone("正在检测…")

    def test_uses_default_input_device(self):
        devices = [{"name": "USB microphone", "max_input_channels": 2}]
        with patch.object(
            client_stream.sd,
            "query_devices",
            side_effect=[devices, devices[0]],
        ):
            selected, device, available = client_stream._select_input_device()

        self.assertIsNone(selected)
        self.assertEqual(device["name"], "USB microphone")
        self.assertEqual(available, [(0, devices[0])])

    def test_falls_back_when_default_input_is_missing(self):
        devices = [
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "UGREEN USB MIC-CM769", "max_input_channels": 2},
        ]
        with patch.object(
            client_stream.sd,
            "query_devices",
            side_effect=[
                devices,
                client_stream.sd.PortAudioError("no default input"),
            ],
        ):
            selected, device, available = client_stream._select_input_device()

        self.assertEqual(selected, 1)
        self.assertEqual(device["name"], "UGREEN USB MIC-CM769")
        self.assertEqual(available, [(1, devices[1])])

    def test_selects_configured_device_by_name(self):
        ClientConfig.mic_device = "UGREEN"
        devices = [
            {"name": "UGREEN USB MIC-CM769", "max_input_channels": 2},
            {"name": "Built-in microphone", "max_input_channels": 1},
        ]
        with patch.object(client_stream.sd, "query_devices", return_value=devices):
            selected, device, _available = client_stream._select_input_device()

        self.assertEqual(selected, 0)
        self.assertEqual(device["name"], "UGREEN USB MIC-CM769")

    def test_open_stream_publishes_actual_microphone_name(self):
        device = {"name": "UGREEN USB MIC-CM769", "max_input_channels": 2}

        class FakeStream:
            def start(self):
                pass

        with (
            patch.object(
                client_stream,
                "_select_input_device",
                return_value=(3, device, [(3, device)]),
            ),
            patch.object(client_stream.sd, "InputStream", return_value=FakeStream()),
        ):
            client_stream.stream_open()

        self.assertEqual(app_info.microphone, "UGREEN USB MIC-CM769")
