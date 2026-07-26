"""
这个文件仅仅是为了 PyInstaller 打包用
"""

import sys
import threading
import traceback
from pathlib import Path
import typer


def main() -> int:
    from core_client import init_file, init_mic, request_stop

    if sys.argv[1:]:
        typer.run(init_file)
        return 0

    from util.app_status import AppState, app_status
    from util.client_tray import TrayController

    stop_event = threading.Event()

    def request_exit() -> None:
        stop_event.set()
        app_status.set(AppState.STOPPING, notify=False)
        request_stop()

    client_thread = threading.Thread(
        target=init_mic,
        args=(stop_event,),
        name="CapsWriter-Client",
        daemon=True,
    )
    try:
        app_status.set(AppState.STARTING, "正在启动客户端并连接语音服务。")
        client_thread.start()
        TrayController(on_exit=request_exit).run()
        return 0
    except Exception:
        with Path("crash_log.txt").open("a", encoding="utf-8") as log_file:
            traceback.print_exc(file=log_file)
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                "程序启动出错，请查看 crash_log.txt。",
                "启动失败",
                16,
            )
        except Exception:
            pass
        return 1
    finally:
        request_exit()
        client_thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
