"""System tray UI for the unified CapsWriter application."""

from __future__ import annotations

import os
from platform import system
from pathlib import Path
import subprocess
from threading import RLock
import time
from typing import Callable, Dict, Optional

from PIL import Image, ImageDraw
import pystray

from util.app_info import RuntimeInfo, app_info
from util.app_status import AppState, StatusBus, StatusSnapshot, app_status


STATE_COLORS: Dict[AppState, str] = {
    AppState.STARTING: "#F59E0B",
    AppState.LOADING: "#F59E0B",
    AppState.READY: "#22C55E",
    AppState.RECORDING: "#EF4444",
    AppState.PROCESSING: "#3B82F6",
    AppState.DISCONNECTED: "#F97316",
    AppState.ERROR: "#DC2626",
    AppState.STOPPING: "#94A3B8",
}


def create_status_icon(state: AppState, size: int = 64) -> Image.Image:
    """Draw a clear tray icon that remains legible at Windows tray sizes."""

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = max(3, size // 16)
    draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill="#172033",
        outline="#E2E8F0",
        width=max(2, size // 16),
    )
    color = STATE_COLORS[state]
    if state == AppState.ERROR:
        width = max(4, size // 10)
        pad = size // 3
        draw.line((pad, pad, size - pad, size - pad), fill=color, width=width)
        draw.line((size - pad, pad, pad, size - pad), fill=color, width=width)
    elif state == AppState.PROCESSING:
        width = max(4, size // 12)
        pad = size // 4
        draw.arc((pad, pad, size - pad, size - pad), 25, 300, fill=color, width=width)
    else:
        pad = size // 3
        draw.ellipse((pad, pad, size - pad, size - pad), fill=color)
    return image


class TrayController:
    """Render status transitions as icon, tooltip, menu text and notification."""

    def __init__(
        self,
        *,
        status_bus: StatusBus = app_status,
        runtime_info: RuntimeInfo = app_info,
        on_exit: Callable[[], None],
        on_restart_server: Optional[Callable[[], None]] = None,
        base_dir: Optional[Path] = None,
        path_opener: Optional[Callable[[Path], None]] = None,
    ) -> None:
        self._status_bus = status_bus
        self._runtime_info = runtime_info
        self._on_exit_requested = on_exit
        self._on_restart_server = on_restart_server
        self._base_dir = Path(base_dir or Path.cwd()).resolve()
        self._config_path = self._base_dir / "config.py"
        self._client_log_path = self._base_dir / "client_log.txt"
        self._path_opener = path_opener or self._open_path
        self._lock = RLock()
        self._ready = False
        self._last_rendered: Optional[StatusSnapshot] = None
        self._pending = status_bus.current
        self._icons = {state: create_status_icon(state) for state in AppState}

        menu_items = [
            pystray.MenuItem(self._status_text, None, enabled=False),
            pystray.MenuItem(self._microphone_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._config_text, self._open_config),
            pystray.MenuItem(self._save_directory_text, self._open_save_directory),
            pystray.MenuItem(self._client_log_text, self._open_client_log),
            pystray.Menu.SEPARATOR,
        ]
        if on_restart_server is not None:
            menu_items.append(pystray.MenuItem("重新启动服务", self._restart_server))
        menu_items.append(pystray.MenuItem("退出 CapsWriter", self._exit))
        self.icon = pystray.Icon(
            "CapsWriter",
            self._icons[self._pending.state],
            self._tooltip(self._pending),
            pystray.Menu(*menu_items),
        )
        self._listener_id = status_bus.subscribe(self._status_changed)
        self._info_listener_id = runtime_info.subscribe(self._microphone_changed)

    @staticmethod
    def _tooltip(snapshot: StatusSnapshot) -> str:
        if system() == "Windows":
            return f"CapsWriter · {snapshot.title}"
        # pystray's Xorg backend writes WM_NAME as latin-1.
        return f"CapsWriter - {snapshot.state.value}"

    def _status_text(self, _item) -> str:
        return f"状态：{self._status_bus.current.title}"

    def _microphone_text(self, _item) -> str:
        return f"当前麦克风：{self._runtime_info.microphone}"

    def _config_text(self, _item) -> str:
        return f"配置文件：{self._config_path}"

    def _save_directory(self) -> Path:
        now = time.localtime()
        return self._base_dir / time.strftime("%Y", now) / time.strftime("%m", now)

    def _save_directory_text(self, _item) -> str:
        return f"保存目录：{self._save_directory()}"

    def _client_log_text(self, _item) -> str:
        return f"客户端日志：{self._client_log_path}"

    @staticmethod
    def _open_path(path: Path) -> None:
        if os.name == "nt":
            getattr(os, "startfile")(str(path))
        elif system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _show_open_error(self, path: Path, exc: Exception) -> None:
        try:
            self.icon.notify(f"无法打开：{path}\n{exc}", "CapsWriter")
        except (NotImplementedError, AttributeError, RuntimeError):
            pass

    def _open_config(self, _icon, _item) -> None:
        try:
            self._path_opener(self._config_path)
        except Exception as exc:
            self._show_open_error(self._config_path, exc)

    def _open_save_directory(self, _icon, _item) -> None:
        path = self._save_directory()
        try:
            path.mkdir(parents=True, exist_ok=True)
            self._path_opener(path)
        except Exception as exc:
            self._show_open_error(path, exc)

    def _open_client_log(self, _icon, _item) -> None:
        try:
            if not self._client_log_path.exists():
                raise FileNotFoundError("日志尚未生成")
            self._path_opener(self._client_log_path)
        except Exception as exc:
            self._show_open_error(self._client_log_path, exc)

    def _status_changed(self, snapshot: StatusSnapshot) -> None:
        with self._lock:
            self._pending = snapshot
            if not self._ready:
                return
        self._render(snapshot)

    def _microphone_changed(self, _name: str) -> None:
        with self._lock:
            if not self._ready:
                return
        try:
            self.icon.update_menu()
        except (NotImplementedError, AttributeError, RuntimeError):
            pass

    def _render(self, snapshot: StatusSnapshot) -> None:
        with self._lock:
            if snapshot == self._last_rendered:
                return
            self._last_rendered = snapshot
        try:
            self.icon.icon = self._icons[snapshot.state]
            self.icon.title = self._tooltip(snapshot)
            self.icon.update_menu()
            if snapshot.notify:
                try:
                    self.icon.remove_notification()
                except (NotImplementedError, AttributeError):
                    pass
                self.icon.notify(snapshot.message, snapshot.title)
        except (NotImplementedError, AttributeError, RuntimeError):
            # Some Linux tray backends don't support notifications. The icon and
            # application lifecycle should continue to function there.
            pass

    def _setup(self, icon) -> None:
        # pystray only makes the icon visible automatically when no custom
        # setup callback is supplied.
        icon.visible = True
        with self._lock:
            self._ready = True
            snapshot = self._pending
        self._render(snapshot)

    def _restart_server(self, _icon, _item) -> None:
        if self._on_restart_server is not None:
            self._on_restart_server()

    def _exit(self, icon, _item) -> None:
        self._on_exit_requested()
        icon.stop()

    def run(self) -> None:
        try:
            self.icon.run(setup=self._setup)
        finally:
            self._status_bus.unsubscribe(self._listener_id)
            self._runtime_info.unsubscribe(self._info_listener_id)

    def stop(self) -> None:
        self.icon.stop()
