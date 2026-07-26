"""统一 App 与系统托盘共享的运行状态。"""

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


DEFAULT_STATUS = {
    AppState.STARTING: ("正在启动", "正在启动 CapsWriter，请稍候。"),
    AppState.LOADING: ("正在加载模型", "离线语音模型正在加载。"),
    AppState.READY: ("已就绪", "可以开始语音输入。"),
    AppState.RECORDING: ("正在录音", "再次操作快捷键后开始识别。"),
    AppState.PROCESSING: ("正在识别", "正在生成文字。"),
    AppState.DISCONNECTED: ("服务未连接", "正在等待本地语音服务。"),
    AppState.ERROR: ("运行异常", "请从托盘打开日志查看详情。"),
    AppState.STOPPING: ("正在退出", "正在关闭客户端和服务端。"),
}

StatusListener = Callable[[StatusSnapshot], None]
InfoListener = Callable[[str], None]


class StatusBus:
    def __init__(self) -> None:
        title, message = DEFAULT_STATUS[AppState.STARTING]
        self._snapshot = StatusSnapshot(AppState.STARTING, title, message)
        self._listeners: Dict[int, StatusListener] = {}
        self._next_id = 0
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
            state,
            title or default_title,
            message or default_message,
            notify,
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
                pass
        return True

    def subscribe(self, listener: StatusListener, *, replay: bool = True) -> int:
        with self._lock:
            listener_id = self._next_id
            self._next_id += 1
            self._listeners[listener_id] = listener
            snapshot = self._snapshot
        if replay:
            listener(snapshot)
        return listener_id

    def unsubscribe(self, listener_id: int) -> None:
        with self._lock:
            self._listeners.pop(listener_id, None)


class RuntimeInfo:
    def __init__(self) -> None:
        self._microphone = "正在检测…"
        self._listeners: Dict[int, InfoListener] = {}
        self._next_id = 0
        self._lock = RLock()

    @property
    def microphone(self) -> str:
        with self._lock:
            return self._microphone

    def set_microphone(self, name: str) -> bool:
        with self._lock:
            if name == self._microphone:
                return False
            self._microphone = name
            listeners = tuple(self._listeners.values())
        for listener in listeners:
            try:
                listener(name)
            except Exception:
                pass
        return True

    def subscribe(self, listener: InfoListener, *, replay: bool = True) -> int:
        with self._lock:
            listener_id = self._next_id
            self._next_id += 1
            self._listeners[listener_id] = listener
            microphone = self._microphone
        if replay:
            listener(microphone)
        return listener_id

    def unsubscribe(self, listener_id: int) -> None:
        with self._lock:
            self._listeners.pop(listener_id, None)


app_status = StatusBus()
app_info = RuntimeInfo()
