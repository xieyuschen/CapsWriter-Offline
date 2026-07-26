"""Application status shared by the client and the system tray.

The status bus is intentionally independent from GUI libraries.  Client code may
publish a state before the tray icon is ready; the tray subscribes later and
receives the latest state immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Callable, Dict, Optional


class AppState(str, Enum):
    STARTING = "starting"
    LOADING = "loading"
    READY = "ready"
    RECORDING = "recording"
    PROCESSING = "processing"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass(frozen=True)
class StatusSnapshot:
    state: AppState
    title: str
    message: str
    notify: bool = True


DEFAULT_STATUS: Dict[AppState, tuple[str, str]] = {
    AppState.STARTING: ("正在启动", "正在启动客户端和服务端，请稍候。"),
    AppState.LOADING: ("正在加载模型", "离线语音模型正在加载，完成后会再次通知。"),
    AppState.READY: ("已就绪", "使用 Caps Lock 开始语音输入。"),
    AppState.RECORDING: ("正在录音", "再次操作 Caps Lock 后开始识别。"),
    AppState.PROCESSING: ("正在识别", "录音结束，正在生成文字。"),
    AppState.DISCONNECTED: ("服务未连接", "暂时无法连接语音服务，程序会自动重试。"),
    AppState.ERROR: ("运行异常", "程序遇到错误，请查看日志后重试。"),
    AppState.STOPPING: ("正在退出", "正在关闭客户端和服务端。"),
}

StatusListener = Callable[[StatusSnapshot], None]


class StatusBus:
    """Thread-safe, transition-driven application status publisher."""

    def __init__(self) -> None:
        title, message = DEFAULT_STATUS[AppState.STARTING]
        self._snapshot = StatusSnapshot(AppState.STARTING, title, message)
        self._listeners: Dict[int, StatusListener] = {}
        self._next_listener_id = 0
        self._lock = RLock()

    @property
    def current(self) -> StatusSnapshot:
        with self._lock:
            return self._snapshot

    def set(
        self,
        state: AppState,
        message: Optional[str] = None,
        *,
        title: Optional[str] = None,
        notify: bool = True,
        force: bool = False,
    ) -> bool:
        default_title, default_message = DEFAULT_STATUS[state]
        snapshot = StatusSnapshot(
            state=state,
            title=title or default_title,
            message=message or default_message,
            notify=notify,
        )
        with self._lock:
            if not force and snapshot == self._snapshot:
                return False
            self._snapshot = snapshot
            listeners = tuple(self._listeners.values())

        for listener in listeners:
            try:
                listener(snapshot)
            except Exception:
                # A GUI backend failure must never break recording or shutdown.
                continue
        return True

    def subscribe(self, listener: StatusListener, *, replay: bool = True) -> int:
        with self._lock:
            listener_id = self._next_listener_id
            self._next_listener_id += 1
            self._listeners[listener_id] = listener
            snapshot = self._snapshot
        if replay:
            listener(snapshot)
        return listener_id

    def unsubscribe(self, listener_id: int) -> None:
        with self._lock:
            self._listeners.pop(listener_id, None)


app_status = StatusBus()
