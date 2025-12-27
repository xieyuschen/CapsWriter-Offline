# coding: utf-8

import os
import sys
import asyncio
import signal
import threading  # <--- 新增
from pathlib import Path
from platform import system
from typing import List

import typer
import colorama
import keyboard

from config import ClientConfig as Config
from util.client_cosmic import console, Cosmic
from util.client_stream import stream_open, stream_close
# <--- 修改导入，增加 start_tray
from util.client_shortcut_handler import bond_shortcut, start_tray 
from util.client_recv_result import recv_result
from util.client_show_tips import show_mic_tips, show_file_tips
from util.client_hot_update import update_hot_all, observe_hot

from util.client_transcribe import transcribe_check, transcribe_send, transcribe_recv
from util.client_adjust_srt import adjust_srt

from util.empty_working_set import empty_current_working_set

# 确保根目录位置正确，用相对路径加载模型
BASE_DIR = os.path.dirname(__file__); os.chdir(BASE_DIR)

# 确保终端能使用 ANSI 控制字符
colorama.init()

# MacOS 的权限设置
if system() == 'Darwin' and not sys.argv[1:]:
    if os.getuid() != 0:
        print('在 MacOS 上需要以管理员启动客户端才能监听键盘活动，请 sudo 启动')
        input('按回车退出'); sys.exit()
    else:
        os.umask(0o000)


async def main_mic():
    Cosmic.queue_in = asyncio.Queue()
    Cosmic.queue_out = asyncio.Queue()

    show_mic_tips()

    # 更新热词
    update_hot_all()

    # 实时更新热词
    observer = observe_hot()

    # 打开音频流
    Cosmic.stream = stream_open()

    # Ctrl-C 关闭音频流，触发自动重启
    # 托盘话，关闭没有作用了移除掉
    # signal.signal(signal.SIGINT, stream_close)

    # 绑定按键
    bond_shortcut()

    # 清空物理内存工作集
    if system() == 'Windows':
        empty_current_working_set()

    # 接收结果
    while True:
        await recv_result()


async def main_file(files: List[Path]):
    show_file_tips()

    for file in files:
        if file.suffix in ['.txt', '.json', 'srt']:
            adjust_srt(file)
        else:
            await transcribe_check(file)
            await asyncio.gather(
                transcribe_send(file),
                transcribe_recv(file)
            )

    if Cosmic.websocket:
        await Cosmic.websocket.close()
    input('\n按回车退出\n')


def init_mic():
    try:
        # 1. 为当前子线程创建唯一的循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 2. 立即赋值给全局变量，确保 handler 能找到它
        Cosmic.loop = loop
        
        # 3. 运行主逻辑（直到被关闭）
        loop.run_until_complete(main_mic())
    except Exception as e:
        with open('error_log.txt', 'a', encoding='utf-8') as f:
            import traceback
            f.write(traceback.format_exc())

def init_file(files: List[Path]):
    """
    用 CapsWriter Server 转录音视频文件，生成 srt 字幕
    """
    try:
        asyncio.run(main_file(files))
    except KeyboardInterrupt:
        console.print(f'再见！')
        sys.exit()


if __name__ == "__main__":
    # === 新增：全局错误捕获，专治无界面启动失败 ===
    try:
        # 如果参数传入文件，那就转录文件
        if sys.argv[1:]:
            typer.run(init_file)
        else:
            # === 托盘模式启动 ===
            
            # 1. 启动业务子线程 (运行 init_mic)
            t = threading.Thread(target=init_mic, daemon=True)
            t.start()
            
            # 2. 启动托盘 (阻塞主线程)
            # 这一步最容易出问题，比如 PIL 加载失败
            print("正在启动托盘...")
            start_tray()
            
    except Exception as e:
        # 无论发生什么错误（缺少依赖、图片生成失败等），都记录下来
        import traceback
        error_msg = traceback.format_exc()
        
        # 写入 crash_log.txt
        with open('crash_log.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)
            
        # 甚至可以弹窗提示 (如果 tkinter 可用)
        try:
            import tkinter.messagebox
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            tkinter.messagebox.showerror("启动失败", f"程序遇到错误：\n{e}\n请查看 crash_log.txt")
        except:
            pass