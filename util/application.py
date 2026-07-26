"""High-level orchestration for the client, server and tray."""

from __future__ import annotations

import multiprocessing
import threading
import traceback
from pathlib import Path
from typing import Optional

from config import ClientConfig
from util.app_runtime import ServerSupervisor, SingleInstance
from util.app_status import AppState, app_status


class CapsWriterApplication:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self._instance = SingleInstance()
        self._exit_requested = threading.Event()
        self._client_stop = threading.Event()
        self._client_thread: Optional[threading.Thread] = None
        self._client_start_lock = threading.Lock()
        self._restart_lock = threading.Lock()
        self._server_ready = False
        self._supervisor = ServerSupervisor(
            multiprocessing.get_context("spawn"),
            self.base_dir,
            self._server_event,
        )

    def acquire_instance(self) -> bool:
        return self._instance.acquire()

    def _server_event(self, event: dict[str, str]) -> None:
        event_type = event.get("type")
        message = event.get("message")
        if event_type == "loading":
            app_status.set(AppState.LOADING, message)
        elif event_type == "ready":
            self._server_ready = True
            self._start_client_once()
        elif event_type == "error":
            self._server_ready = False
            app_status.set(AppState.ERROR, message)

    def _start_client_once(self) -> None:
        with self._client_start_lock:
            if self._client_thread and self._client_thread.is_alive():
                return
            self._client_thread = threading.Thread(
                target=self._run_client,
                name="CapsWriter-Client",
                daemon=True,
            )
            self._client_thread.start()

    def _run_client(self) -> None:
        try:
            from core_client import init_mic

            init_mic(stop_event=self._client_stop)
            if not self._exit_requested.is_set():
                app_status.set(
                    AppState.ERROR,
                    "客户端意外停止，请查看 client_log.txt。",
                )
        except BaseException as exc:
            with (self.base_dir / "client_log.txt").open(
                "a", encoding="utf-8"
            ) as log_file:
                traceback.print_exc(file=log_file)
            if not self._exit_requested.is_set():
                app_status.set(AppState.ERROR, f"客户端启动失败：{exc}")

    def request_exit(self) -> None:
        self._exit_requested.set()
        app_status.set(AppState.STOPPING, notify=False)

    def restart_server(self) -> None:
        if not self._restart_lock.acquire(blocking=False):
            return

        def restart_worker() -> None:
            try:
                self._server_ready = False
                app_status.set(AppState.LOADING, "正在重新启动本地语音服务。")
                self._supervisor.restart()
            finally:
                self._restart_lock.release()

        threading.Thread(
            target=restart_worker,
            name="CapsWriter-Server-Restart",
            daemon=True,
        ).start()

    def run(self) -> None:
        from util.client_tray import TrayController

        shortcut = ClientConfig.shortcut.title()
        app_status.set(
            AppState.STARTING,
            f"正在启动客户端和服务端；就绪后可使用 {shortcut}。",
            force=True,
        )
        tray = TrayController(
            on_exit=self.request_exit,
            on_restart_server=self.restart_server,
            base_dir=self.base_dir,
        )
        try:
            self._supervisor.start()
            tray.run()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._exit_requested.set()
        self._client_stop.set()
        try:
            from core_client import request_stop

            request_stop()
        except Exception:
            pass
        self._supervisor.stop()
        if self._client_thread:
            self._client_thread.join(timeout=5.0)
        self._instance.release()
