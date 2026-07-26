import keyboard
from util.client_cosmic import Cosmic, websocket_is_open
from config import ClientConfig as Config

import time
import asyncio
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from util.client_send_audio import send_audio
from util.my_status import Status
from util.app_status import AppState, app_status

task = None
status = Status('开始录音', spinner='point')
pool = ThreadPoolExecutor()
pressed = False
released = True
event = Event()


def shortcut_instruction() -> str:
    shortcut = Config.shortcut.title()
    if Config.hold_mode:
        return f"按住 {shortcut} 开始说话，松开后识别。"
    return f"按一下 {shortcut} 开始说话，再按一下结束。"


def recording_instruction() -> str:
    shortcut = Config.shortcut.title()
    if Config.hold_mode:
        return f"正在录音，松开 {shortcut} 后开始识别。"
    return f"正在录音，再按一下 {shortcut} 后开始识别。"


def shortcut_correct(e: keyboard.KeyboardEvent):
    key_expect = keyboard.normalize_name(Config.shortcut).replace('left ', '')
    key_actual = e.name.replace('left ', '')
    if key_expect != key_actual: return False
    return True


def launch_task():
    global task

    if not Cosmic.loop or not websocket_is_open():
        app_status.set(AppState.DISCONNECTED)
        return False

    # 记录开始时间
    t1 = time.time()

    # 将开始标志放入队列
    asyncio.run_coroutine_threadsafe(
        Cosmic.queue_in.put({'type': 'begin', 'time': t1, 'data': None}),
        Cosmic.loop
    )

    # 通知录音线程可以向队列放数据了
    Cosmic.on = t1

    status.start()
    app_status.set(AppState.RECORDING, recording_instruction())

    # 启动识别任务
    task = asyncio.run_coroutine_threadsafe(
        send_audio(),
        Cosmic.loop,
    )
    return True


def cancel_task():
    # 通知停止录音，关掉滚动条
    Cosmic.on = False
    status.stop()
    app_status.set(AppState.READY, "录音时间太短，已取消。")

    # 取消协程任务
    if task is not None:
        task.cancel()


def finish_task():
    global task
    if not Cosmic.on:
        return
    # 通知停止录音，关掉滚动条
    Cosmic.on = False
    status.stop()
    app_status.set(AppState.PROCESSING)

    # 通知结束任务
    asyncio.run_coroutine_threadsafe(
        Cosmic.queue_in.put(
            {'type': 'finish',
             'time': time.time(),
             'data': None
             },
        ),
        Cosmic.loop
    )


# =================单击模式======================


def count_down(e: Event):
    """按下后，开始倒数"""
    time.sleep(Config.threshold)
    e.set()


def manage_task(e: Event):
    """
    通过按键持续时间区分单击切换和原始按键功能。
    """
    on = Cosmic.on

    if not on:
        launch_task()

    if e.wait(timeout=Config.threshold * 0.8):
        if Cosmic.on and on:
            finish_task()
    else:
        if not on and Cosmic.on:
            cancel_task()
        keyboard.send(Config.shortcut)


def click_mode(e: keyboard.KeyboardEvent):
    global pressed, released, event

    if e.event_type == 'down' and released:
        pressed, released = True, False
        event = Event()
        pool.submit(count_down, event)
        pool.submit(manage_task, event)

    elif e.event_type == 'up' and pressed:
        pressed, released = False, True
        event.set()



# ======================长按模式==================================


def hold_mode(e: keyboard.KeyboardEvent):
    """像对讲机一样，按下录音，松开停止"""
    global task

    if e.event_type == 'down' and not Cosmic.on:
        # 记录开始时间
        launch_task()
    elif e.event_type == 'up' and Cosmic.on:
        # 记录持续时间，并标识录音线程停止向队列放数据
        duration = time.time() - Cosmic.on

        # 取消或停止任务
        if duration < Config.threshold:
            cancel_task()
        else:
            finish_task()

            # 松开快捷键后，再按一次，恢复 CapsLock 或 Shift 等按键的状态
            if Config.restore_key:
                time.sleep(0.01)
                keyboard.send(Config.shortcut)





# ==================== 绑定 handler ===============================


def hold_handler(e: keyboard.KeyboardEvent) -> None:

    # 验证按键名正确
    if not shortcut_correct(e):
        return

    # 长按模式
    hold_mode(e)


def click_handler(e: keyboard.KeyboardEvent) -> None:

    # 验证按键名正确
    if not shortcut_correct(e):
        return

    # 单击模式
    click_mode(e)


def bond_shortcut():
    if Config.hold_mode:
        return keyboard.hook_key(
            Config.shortcut, hold_handler, suppress=Config.suppress
        )
    else:
        # 单击模式，必须得阻塞快捷键
        # 收到长按时，再模拟发送按键
        return keyboard.hook_key(Config.shortcut, click_handler, suppress=True)


def unbond_shortcut(handler) -> None:
    global task
    Cosmic.on = False
    status.stop()
    if task is not None and not task.done():
        task.cancel()
    task = None
    if handler is not None:
        keyboard.unhook(handler)
