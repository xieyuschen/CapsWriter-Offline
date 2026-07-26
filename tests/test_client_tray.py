import unittest
import tempfile
from pathlib import Path

try:
    from util.app_info import RuntimeInfo
    from util.app_status import AppState, StatusBus
    from util.client_tray import TrayController
except ImportError:
    TrayController = None


class FakeIcon:
    def __init__(self):
        self.icon = None
        self.title = None
        self.visible = False
        self.menu_updates = 0
        self.removed_notifications = 0
        self.notifications = []

    def update_menu(self):
        self.menu_updates += 1

    def remove_notification(self):
        self.removed_notifications += 1

    def notify(self, message, title):
        self.notifications.append((title, message))


@unittest.skipIf(TrayController is None, "tray dependencies aren't installed")
class TrayControllerTests(unittest.TestCase):
    def test_setup_makes_custom_tray_icon_visible(self):
        info = RuntimeInfo()
        controller = TrayController(
            status_bus=StatusBus(),
            runtime_info=info,
            on_exit=lambda: None,
        )
        fake_icon = FakeIcon()
        controller.icon = fake_icon

        controller._setup(fake_icon)

        self.assertTrue(fake_icon.visible)
        self.assertTrue(controller._ready)
        controller._status_bus.unsubscribe(controller._listener_id)
        info.unsubscribe(controller._info_listener_id)

    def test_status_transition_updates_all_tray_surfaces(self):
        bus = StatusBus()
        info = RuntimeInfo()
        controller = TrayController(
            status_bus=bus,
            runtime_info=info,
            on_exit=lambda: None,
        )
        fake_icon = FakeIcon()
        controller.icon = fake_icon
        controller._ready = True

        bus.set(AppState.RECORDING)

        self.assertIn("CapsWriter", fake_icon.title)
        self.assertEqual(fake_icon.menu_updates, 1)
        self.assertEqual(fake_icon.removed_notifications, 1)
        self.assertEqual(fake_icon.notifications[-1][0], "正在录音")
        bus.unsubscribe(controller._listener_id)
        info.unsubscribe(controller._info_listener_id)

    def test_microphone_name_updates_tray_menu(self):
        info = RuntimeInfo()
        controller = TrayController(
            status_bus=StatusBus(),
            runtime_info=info,
            on_exit=lambda: None,
        )
        fake_icon = FakeIcon()
        controller.icon = fake_icon
        controller._ready = True

        info.set_microphone("UGREEN USB MIC-CM769")

        self.assertEqual(
            controller._microphone_text(None),
            "当前麦克风：UGREEN USB MIC-CM769",
        )
        self.assertEqual(fake_icon.menu_updates, 1)
        controller._status_bus.unsubscribe(controller._listener_id)
        info.unsubscribe(controller._info_listener_id)

    def test_paths_are_displayed_and_can_be_opened(self):
        opened = []
        with tempfile.TemporaryDirectory() as directory:
            info = RuntimeInfo()
            base_dir = Path(directory)
            config_path = base_dir / "config.py"
            config_path.touch()
            client_log_path = base_dir / "client_log.txt"
            client_log_path.touch()
            controller = TrayController(
                status_bus=StatusBus(),
                runtime_info=info,
                on_exit=lambda: None,
                base_dir=base_dir,
                path_opener=opened.append,
            )

            self.assertEqual(
                controller._config_text(None),
                f"配置文件：{config_path}",
            )
            self.assertTrue(
                controller._save_directory_text(None).startswith(
                    f"保存目录：{base_dir}"
                )
            )

            controller._open_config(None, None)
            controller._open_save_directory(None, None)
            controller._open_client_log(None, None)

            self.assertEqual(opened[0], config_path)
            self.assertEqual(opened[1], controller._save_directory())
            self.assertEqual(opened[2], client_log_path)
            self.assertTrue(opened[1].is_dir())
            controller._status_bus.unsubscribe(controller._listener_id)
            info.unsubscribe(controller._info_listener_id)


if __name__ == "__main__":
    unittest.main()
