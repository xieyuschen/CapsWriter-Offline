"""CapsWriter 单一桌面 App 入口。"""

from __future__ import annotations


def main() -> int:
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

    from core.app_runtime import (
        UnifiedCapsWriterApplication,
        show_already_running_message,
    )

    application = UnifiedCapsWriterApplication(base_dir)
    if not application.acquire_instance():
        show_already_running_message()
        return 0

    try:
        application.run()
        return 0
    except BaseException as exc:
        log_path = base_dir / "logs" / "crash_latest.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            traceback.print_exc(file=log_file)
        if os.name == "nt":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"CapsWriter 启动失败：{exc}\n请查看 logs 文件夹。",
                    "CapsWriter",
                    16,
                )
            except Exception:
                pass
        return 1
    finally:
        application.stop()


if __name__ == "__main__":
    raise SystemExit(main())
