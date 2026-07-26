"""Unified CapsWriter entry point.

Double-clicking this entry starts the local recognition server, microphone
client and system tray as one managed application.
"""

from __future__ import annotations


def main() -> int:
    # PyInstaller recommends calling this before imports that pull in heavy
    # modules or create multiprocessing resources.
    from multiprocessing import freeze_support

    freeze_support()

    import os
    import sys
    import traceback
    from pathlib import Path

    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent
    os.chdir(base_dir)

    from util.app_runtime import run_server_self_test, show_already_running_message
    from util.application import CapsWriterApplication

    if sys.argv[1:] == ["--self-test-server"]:
        return 0 if run_server_self_test(base_dir) else 1

    application = CapsWriterApplication(base_dir)
    if not application.acquire_instance():
        show_already_running_message()
        return 0

    try:
        application.run()
        return 0
    except BaseException:
        with (base_dir / "crash_log.txt").open("a", encoding="utf-8") as log:
            traceback.print_exc(file=log)
        try:
            if os.name == "nt":
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0,
                    "CapsWriter 启动失败，请查看 crash_log.txt。",
                    "CapsWriter",
                    16,
                )
        except Exception:
            pass
        return 1
    finally:
        application.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
