"""单一桌面 App 的客户端、服务端与托盘生命周期管理。"""

from __future__ import annotations

import os
import tempfile
import threading
from multiprocessing.context import BaseContext
from pathlib import Path
from queue import Empty
from typing import Callable, Optional

from core.app_status import AppState, app_status


RuntimeEvent = dict[str, str]
RuntimeCallback = Callable[[RuntimeEvent], None]


class SingleInstance:
    """避免重复启动两套本地服务和托盘。"""

    def __init__(self, name: str = "CapsWriter-Offline") -> None:
        self.name = name
        self._handle = None
        self._lock_file = None

    def acquire(self) -> bool:
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
            if not handle:
                return False
            self._handle = handle
            if kernel32.GetLastError() == 183:
                self.release()
                return False
            return True

        import fcntl

        path = Path(tempfile.gettempdir()) / f"{self.name}.lock"
        self._lock_file = path.open("a+")
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock_file.close()
            self._lock_file = None
            return False
        return True

    def release(self) -> None:
        if os.name == "nt":
            if self._handle is not None:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(self._handle)
                self._handle = None
            return

        if self._lock_file is not None:
            import fcntl

            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_file.close()
                self._lock_file = None


def run_server_process(stop_event, status_queue, base_dir: str) -> None:
    """在独立进程中启动上游 Server，并把加载状态回传给托盘。"""

    os.chdir(base_dir)
    os.environ["CAPSWRITER_UNIFIED_SERVER"] = "1"
    log_path = Path(base_dir) / "logs" / "server_launcher.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8", buffering=1) as log_file:
        import sys
        import traceback

        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = log_file
        sys.stderr = log_file
        try:
            from config_server import ServerConfig
            from core.server.app import CapsWriterServer

            ServerConfig.enable_tray = False
            server = CapsWriterServer(status_callback=status_queue.put)

            def watch_stop() -> None:
                stop_event.wait()
                if server.loop.is_running():
                    server.loop.call_soon_threadsafe(server.stop)
                else:
                    server.stop()

            threading.Thread(
                target=watch_stop,
                name="CapsWriter-Server-Stop",
                daemon=True,
            ).start()
            server.start()
        except BaseException as exc:
            traceback.print_exc()
            try:
                detail = str(exc) or type(exc).__name__
                status_queue.put(
                    {"type": "error", "message": f"服务端启动失败：{detail}"}
                )
            except Exception:
                pass
            raise
        finally:
            # multiprocessing 会在 target 返回后刷新标准流，不能留下已关闭文件。
            sys.stdout = original_stdout
            sys.stderr = original_stderr


class ServerSupervisor:
    def __init__(
        self,
        context: BaseContext,
        base_dir: Path,
        callback: RuntimeCallback,
        process_target=run_server_process,
    ) -> None:
        self._context = context
        self._base_dir = Path(base_dir)
        self._callback = callback
        self._process_target = process_target
        self._lock = threading.RLock()
        self._process = None
        self._stop_event = None
        self._status_queue = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._generation = 0
        self._stopping = False

    @property
    def is_alive(self) -> bool:
        with self._lock:
            return bool(self._process and self._process.is_alive())

    def start(self) -> None:
        with self._lock:
            if self._process and self._process.is_alive():
                return
            self._generation += 1
            generation = self._generation
            self._stopping = False
            self._stop_event = self._context.Event()
            self._status_queue = self._context.Queue()
            self._process = self._context.Process(
                name="CapsWriter-Server",
                target=self._process_target,
                args=(self._stop_event, self._status_queue, str(self._base_dir)),
            )
            self._process.start()
            self._monitor_thread = threading.Thread(
                target=self._monitor,
                args=(generation,),
                name="CapsWriter-Server-Monitor",
                daemon=True,
            )
            self._monitor_thread.start()

    def _monitor(self, generation: int) -> None:
        error_reported = False
        while True:
            with self._lock:
                if generation != self._generation:
                    return
                process = self._process
                status_queue = self._status_queue
            if process is None or status_queue is None:
                return

            try:
                event = status_queue.get(timeout=0.2)
            except (Empty, EOFError, OSError):
                event = None
            if event:
                error_reported = error_reported or event.get("type") == "error"
                self._callback(event)

            if not process.is_alive():
                process.join(timeout=0)
                # 子进程可能在退出前连续写入 loading/error；先排空队列，
                # 避免只看到 loading 后用笼统的退出码覆盖真正原因。
                while True:
                    try:
                        pending = status_queue.get_nowait()
                    except (Empty, EOFError, OSError):
                        break
                    if pending:
                        error_reported = (
                            error_reported or pending.get("type") == "error"
                        )
                        self._callback(pending)
                with self._lock:
                    stopping = self._stopping or generation != self._generation
                if not stopping and not error_reported:
                    self._callback(
                        {
                            "type": "error",
                            "message": f"服务端意外退出（代码 {process.exitcode}）。",
                        }
                    )
                return

    def stop(self, timeout: float = 8.0) -> None:
        with self._lock:
            process = self._process
            stop_event = self._stop_event
            status_queue = self._status_queue
            monitor_thread = self._monitor_thread
            self._stopping = True
        if process is None:
            return
        if stop_event is not None:
            stop_event.set()
        process.join(timeout=timeout)
        if process.is_alive():
            process.terminate()
            process.join(timeout=3.0)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=2.0)
        if monitor_thread and monitor_thread is not threading.current_thread():
            monitor_thread.join(timeout=1.0)
        if status_queue is not None:
            try:
                status_queue.close()
                status_queue.join_thread()
            except (AttributeError, OSError, ValueError):
                pass
        with self._lock:
            if self._process is process:
                self._process = None
                self._stop_event = None
                self._status_queue = None
                self._monitor_thread = None

    def restart(self) -> None:
        self.stop()
        self.start()


class UnifiedCapsWriterApplication:
    """以一个入口统一启动上游 Client、Server 和系统托盘。"""

    def __init__(
        self,
        base_dir: Path,
        *,
        context: Optional[BaseContext] = None,
        client_factory=None,
    ) -> None:
        if context is None:
            import multiprocessing

            context = multiprocessing.get_context("spawn")
        self.base_dir = Path(base_dir)
        self._instance = SingleInstance()
        self._exit_requested = threading.Event()
        self._server_ready = threading.Event()
        self._server_error: Optional[str] = None
        self._client = None
        self._client_started = False
        self._stop_lock = threading.Lock()
        self._restart_lock = threading.Lock()
        self._client_factory = client_factory
        self._supervisor = ServerSupervisor(
            context,
            self.base_dir,
            self._server_event,
        )

    def acquire_instance(self) -> bool:
        return self._instance.acquire()

    def _server_event(self, event: RuntimeEvent) -> None:
        event_type = event.get("type")
        message = event.get("message")
        if event_type == "loading":
            app_status.set(AppState.LOADING, message)
        elif event_type == "ready":
            self._server_error = None
            self._server_ready.set()
            app_status.set(
                AppState.STARTING,
                "本地语音服务已就绪，正在启动麦克风客户端。",
            )
        elif event_type == "error":
            self._server_error = message or "未知服务端错误"
            self._server_ready.set()
            app_status.set(AppState.ERROR, self._server_error)

    def restart_server(self) -> None:
        if not self._restart_lock.acquire(blocking=False):
            return

        def restart() -> None:
            try:
                self._server_ready.clear()
                self._server_error = None
                app_status.set(AppState.LOADING, "正在重新启动本地语音服务。")
                self._supervisor.restart()
            finally:
                self._restart_lock.release()

        threading.Thread(
            target=restart,
            name="CapsWriter-Server-Restart",
            daemon=True,
        ).start()

    def run(self) -> None:
        if self._client_factory is None:
            from core.client import CapsWriterClient

            client_factory = CapsWriterClient
        else:
            client_factory = self._client_factory

        self._client = client_factory()
        self._client.exit_callback = self.stop
        self._client.restart_server_callback = self.restart_server

        app_status.set(
            AppState.STARTING,
            "正在启动客户端和本地语音服务。",
            force=True,
        )
        # 模型加载期间也要立即显示托盘，而不是等加载完成才出现。
        self._client.tray.start()
        app_status.set(AppState.LOADING)
        self._supervisor.start()

        while not self._server_ready.wait(0.1):
            if self._exit_requested.is_set():
                return
        if self._server_error:
            raise RuntimeError(self._server_error)
        if self._exit_requested.is_set():
            return

        self._client_started = True
        self._client.start()

    def stop(self) -> None:
        if not self._stop_lock.acquire(blocking=False):
            return
        try:
            if self._exit_requested.is_set():
                return
            self._exit_requested.set()
            app_status.set(AppState.STOPPING, notify=False)
            if self._client is not None:
                if self._client_started:
                    self._client.stop()
                else:
                    self._client.tray.stop()
            self._supervisor.stop()
            self._instance.release()
        finally:
            self._stop_lock.release()


def show_already_running_message() -> None:
    message = "CapsWriter 已在运行，请查看右下角系统托盘。"
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "CapsWriter", 64)
            return
        except Exception:
            pass
    print(message)
