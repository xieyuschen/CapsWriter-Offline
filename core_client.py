# coding: utf-8

import os
import sys
import asyncio
import threading
from pathlib import Path
from platform import system
from typing import List

import colorama

from util.client_cosmic import console, Cosmic
from util.client_stream import stream_open
from util.client_shortcut_handler import bond_shortcut, unbond_shortcut
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


async def main_mic(stop_event=None):
    if stop_event is None:
        stop_event = threading.Event()

    Cosmic.queue_in = asyncio.Queue()
    Cosmic.queue_out = asyncio.Queue()
    Cosmic.stopping = False
    observer = None
    shortcut_handler = None

    try:
        show_mic_tips()

        # 更新并持续观察热词文件。
        update_hot_all()
        observer = observe_hot()

        Cosmic.stream = stream_open()
        shortcut_handler = bond_shortcut()

        if system() == "Windows":
            empty_current_working_set()

        # recv_result returns when the server is unavailable. Retry with a
        # bounded delay so a local server restart recovers automatically.
        while not stop_event.is_set():
            await recv_result(stop_event=stop_event)
            if not stop_event.is_set():
                await asyncio.sleep(0.8)
    finally:
        Cosmic.stopping = True
        unbond_shortcut(shortcut_handler)
        if observer is not None:
            observer.stop()
            observer.join(timeout=2)
        if Cosmic.stream is not None:
            try:
                Cosmic.stream.stop()
                Cosmic.stream.close()
            except Exception:
                pass
            Cosmic.stream = None
        if Cosmic.websocket is not None:
            try:
                await Cosmic.websocket.close()
            except Exception:
                pass
            Cosmic.websocket = None


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


def init_mic(stop_event=None):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        Cosmic.loop = loop
        loop.run_until_complete(main_mic(stop_event=stop_event))
    except Exception:
        with open("client_log.txt", "a", encoding="utf-8") as log_file:
            import traceback

            traceback.print_exc(file=log_file)
        raise
    finally:
        Cosmic.loop = None
        loop.close()


def request_stop() -> None:
    """Close the websocket so the client event loop can observe its stop event."""

    loop = Cosmic.loop
    websocket = Cosmic.websocket
    if loop is None or websocket is None or not loop.is_running():
        return

    async def close_websocket():
        try:
            await websocket.close()
        except Exception:
            pass

    asyncio.run_coroutine_threadsafe(close_websocket(), loop)

def init_file(files: List[Path]):
    """
    用 CapsWriter Server 转录音视频文件，生成 srt 字幕
    """
    try:
        asyncio.run(main_file(files))
    except KeyboardInterrupt:
        console.print('再见！')
        sys.exit()


if __name__ == "__main__":
    from start_client import main

    raise SystemExit(main())
