"""Thread-safe runtime details displayed by the tray menu."""

from __future__ import annotations

from threading import RLock
from typing import Callable, Dict


InfoListener = Callable[[str], None]


class RuntimeInfo:
    def __init__(self) -> None:
        self._microphone = "正在检测…"
        self._listeners: Dict[int, InfoListener] = {}
        self._next_listener_id = 0
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
                continue
        return True

    def subscribe(self, listener: InfoListener, *, replay: bool = True) -> int:
        with self._lock:
            listener_id = self._next_listener_id
            self._next_listener_id += 1
            self._listeners[listener_id] = listener
            microphone = self._microphone
        if replay:
            listener(microphone)
        return listener_id

    def unsubscribe(self, listener_id: int) -> None:
        with self._lock:
            self._listeners.pop(listener_id, None)


app_info = RuntimeInfo()
