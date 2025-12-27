"""
这个文件仅仅是为了 PyInstaller 打包用
"""

import sys
import threading
import traceback
import typer
from core_client import init_file, init_mic

# 引入我们在 handler 里写好的托盘启动函数
# 确保 util/client_shortcut_handler.py 里有 start_tray 函数
from util.client_shortcut_handler import start_tray

if __name__ == "__main__":
    # === 新增：将所有 print 和 报错 写入文件 ===
    log_file = open("debug_log.txt", "w", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file
    # 添加全局错误捕获，防止因为缺库导致静默闪退
    try:
        # 如果参数传入文件，那就转录文件
        if sys.argv[1:]:
            typer.run(init_file)
        else:
            # === 托盘模式启动 (针对无黑框版本) ===
            
            # 1. 启动业务子线程 (运行录音主逻辑)
            # daemon=True 保证主程序退出时，这个线程也会随之关闭
            t = threading.Thread(target=init_mic, daemon=True)
            t.start()

            # 2. 启动托盘 (这一步必须在主线程，且会阻塞直到退出)
            # 如果这里报错，通常是 PIL 或 pystray 问题
            start_tray()
            
    except Exception as e:
        # 如果启动失败（比如缺少 dll，或者 import 错误），记录日志
        with open('crash_log.txt', 'w', encoding='utf-8') as f:
            f.write(traceback.format_exc())
            
        # 如果是 Windows，尝试弹窗提示（可选）
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"程序启动出错，请查看 crash_log.txt", "启动失败", 16)
        except:
            pass