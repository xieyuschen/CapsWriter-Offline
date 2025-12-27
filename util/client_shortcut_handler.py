import keyboard
from util.client_cosmic import Cosmic, console
from config import ClientConfig as Config

import time
import asyncio
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from util.client_send_audio import send_audio
from util.my_status import Status

# === 新增导入 ===
import sys
import os
from PIL import Image, ImageDraw
import pystray

task = asyncio.Future()
status = Status('开始录音', spinner='point')
pool = ThreadPoolExecutor()
pressed = False
released = True
event = Event()

# === 托盘图标相关逻辑 ===

def create_image(width, height, color_bg, color_fg):
    image = Image.new('RGB', (width, height), color_bg)
    dc = ImageDraw.Draw(image)
    # 画一个圆点
    dc.ellipse((width // 4, height // 4, 3 * width // 4, 3 * height // 4), fill=color_fg)
    return image

# 预先生成两种图标状态
icon_default = create_image(64, 64, 'black', 'white') # 待机：白点
icon_recording = create_image(64, 64, 'black', 'red') # 录音：红点

# 全局托盘变量
tray_icon = None

def on_exit(icon, item):
    """点击托盘退出菜单时的回调"""
    icon.stop()
    # 强制退出整个进程，因为还有一个子线程在跑
    os._exit(0)

def start_tray():
    """供主程序调用的启动函数"""
    global tray_icon
    menu = (pystray.MenuItem('退出', on_exit),)
    tray_icon = pystray.Icon("CapsWriter", icon_default, "CapsWriter Client", menu)
    tray_icon.run()

# =======================

def shortcut_correct(e: keyboard.KeyboardEvent):
    key_expect = keyboard.normalize_name(Config.shortcut).replace('left ', '')
    key_actual = e.name.replace('left ', '')
    if key_expect != key_actual: return False
    return True


def launch_task():
    global task

    # 记录开始时间
    t1 = time.time()

    # 将开始标志放入队列
    asyncio.run_coroutine_threadsafe(
        Cosmic.queue_in.put({'type': 'begin', 'time': t1, 'data': None}),
        Cosmic.loop
    )

    # 通知录音线程可以向队列放数据了
    Cosmic.on = t1

    # 打印动画：正在录音
    # status.start()
    
    # === 图标变红 ===
    if tray_icon: 
        tray_icon.icon = icon_recording
        time.sleep(0.1)


    # 启动识别任务
    task = asyncio.run_coroutine_threadsafe(
        send_audio(),
        Cosmic.loop,
    )


def cancel_task():
    if Cosmic.on and (time.time() - Cosmic.on < 0.3):
        return
    # 通知停止录音，关掉滚动条
    Cosmic.on = False
    # status.stop()
    
    # === 图标变白 ===
    if tray_icon:
        tray_icon.icon = icon_default
        time.sleep(0.1)

    # 取消协程任务
    task.cancel()


def finish_task():
    global task
# === 核心保护逻辑：如果录音开启到现在还不满 1 秒，拒绝关闭 ===
    # 这能防止第一次点击的“松开”动作瞬间把刚开启的录音给关了
    if Cosmic.on and (time.time() - Cosmic.on < 1):
        return
    # 通知停止录音，关掉滚动条
    Cosmic.on = False
    # status.stop()

    # === 图标变白 ===
    if tray_icon:
        tray_icon.icon = icon_default
        time.sleep(0.1)

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
    极简逻辑：只负责开关切换
    """
    # 1. 记录按下时的状态快照
    was_running = Cosmic.on

    if not was_running:
        # 如果没在录音，启动它
        launch_task()
    else:
        # 如果正在录音，停止它
        finish_task()

    # 2. 直接等待松开，不做任何超时判断，也不发送模拟按键
    e.wait()


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
    elif e.event_type == 'up':
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
        keyboard.hook_key(Config.shortcut, hold_handler, suppress=Config.suppress)
    else:
        # 单击模式，必须得阻塞快捷键
        # 收到长按时，再模拟发送按键
        keyboard.hook_key(Config.shortcut, click_handler, suppress=True)