"""Lifecycle helpers for the unified CapsWriter launcher."""

from __future__ import annotations

import os
import socket
import tempfile
import threading
from multiprocessing.context import BaseContext
from pathlib import Path
from queue import Empty
from typing import Callable, Optional


RuntimeEvent = dict[str, str]
RuntimeCallback = Callable[[RuntimeEvent], None]


class SingleInstance:
    """A small cross-platform process lock for avoiding duplicate tray apps."""

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
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
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

    def __enter__(self) -> "SingleInstance":
        if not self.acquire():
            raise RuntimeError("CapsWriter is already running")
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()


def run_server_process(stop_event, status_queue, base_dir: str) -> None:
    """Multiprocessing target. Imports server dependencies only in the child."""

    os.chdir(base_dir)
    log_path = Path(base_dir) / "server_log.txt"
    try:
        with log_path.open("a", encoding="utf-8", buffering=1) as log_file:
            import sys
            import traceback

            original_stdout = sys.stdout
            original_stderr = sys.stderr
            sys.stdout = log_file
            sys.stderr = log_file
            try:
                import core_server

                core_server.init(stop_event=stop_event, status_queue=status_queue)
            except BaseException as exc:
                traceback.print_exc()
                status_queue.put(
                    {
                        "type": "error",
                        "message": f"服务端启动失败：{exc}",
                    }
                )
                raise
            finally:
                # multiprocessing flushes standard streams after the target
                # returns. Do not leave them pointing at the closed log file.
                sys.stdout = original_stdout
                sys.stderr = original_stderr
    except BaseException as exc:
        try:
            status_queue.put(
                {
                    "type": "error",
                    "message": f"无法启动服务端：{exc}",
                }
            )
        except Exception:
            pass
        raise


class ServerSupervisor:
    """Start, monitor, restart and stop the local server process."""

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
                stopping = self._stopping
            if process is None or status_queue is None:
                return

            try:
                event = status_queue.get(timeout=0.2)
            except Empty:
                event = None
            except (EOFError, OSError):
                event = None

            if event:
                if event.get("type") == "error":
                    error_reported = True
                self._callback(event)

            if not process.is_alive():
                process.join(timeout=0)
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
        if not process:
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
        if (
            monitor_thread is not None
            and monitor_thread is not threading.current_thread()
        ):
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


def run_server_self_test(base_dir: Path, timeout: float = 90.0) -> bool:
    """Exercise the packaged multiprocessing server without starting the GUI."""

    import multiprocessing

    finished = threading.Event()
    errors = []

    def receive(event: RuntimeEvent) -> None:
        if event.get("type") == "ready":
            finished.set()
        elif event.get("type") == "error":
            errors.append(event.get("message", "unknown server error"))
            finished.set()

    supervisor = ServerSupervisor(
        multiprocessing.get_context("spawn"),
        Path(base_dir),
        receive,
    )
    try:
        supervisor.start()
        if not finished.wait(timeout) or errors:
            return False
        with socket.create_connection(("127.0.0.1", 6016), timeout=2):
            return True
    finally:
        supervisor.stop(timeout=10)
