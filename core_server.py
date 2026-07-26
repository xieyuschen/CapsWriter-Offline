import os
import asyncio
import socket
from multiprocessing import Process, Manager
from platform import system
from queue import Empty
from typing import Optional

try:
    from websockets.legacy.server import serve
except ImportError:  # websockets < 10
    from websockets import serve
from config import ServerConfig as Config
from util.server_cosmic import Cosmic, console
from util.server_check_model import check_model
from util.server_ws_recv import ws_recv
from util.server_ws_send import ws_send
from util.server_init_recognizer import init_recognizer
from util.empty_working_set import empty_current_working_set

BASE_DIR = os.path.dirname(__file__)
os.chdir(BASE_DIR)  # 确保 os.getcwd() 位置正确，用相对路径加载模型


def _report(status_queue, event_type: str, message: str) -> None:
    if status_queue is not None:
        status_queue.put({"type": event_type, "message": message})


async def _wait_for_stop(stop_event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(0.2)


def _ensure_port_available() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((Config.addr, int(Config.port)))


async def main(stop_event=None, status_queue=None):
    # 检查模型文件
    check_model(interactive=status_queue is None)
    _ensure_port_available()
    _report(status_queue, "loading", "正在加载离线语音模型，请稍候。")

    console.line(2)
    console.rule("[bold #d55252]CapsWriter Offline Server")
    console.line()
    console.print(
        "项目地址：[cyan underline]"
        "https://github.com/HaujetZhao/CapsWriter-Offline",
        end="\n\n",
    )
    console.print(f"当前基文件夹：[cyan underline]{BASE_DIR}", end="\n\n")
    console.print(
        f"绑定的服务地址：[cyan underline]{Config.addr}:{Config.port}",
        end="\n\n",
    )

    # 跨进程列表，用于保存 socket 的 id，用于让识别进程查看连接是否中断
    manager = Manager()
    recognize_process: Optional[Process] = None
    server = None
    send_task = None
    try:
        Cosmic.sockets_id = manager.list()

        # 负责识别的子进程
        recognize_process = Process(
            target=init_recognizer,
            args=(Cosmic.queue_in, Cosmic.queue_out, Cosmic.sockets_id),
            daemon=True,
        )
        recognize_process.start()

        # 等模型进程确认就绪，同时允许统一启动器在加载期间退出。
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                ready = Cosmic.queue_out.get(timeout=0.2)
            except Empty:
                if not recognize_process.is_alive():
                    raise RuntimeError("模型进程在加载完成前退出")
                continue
            if ready is True:
                break

        # 先完成端口绑定，再向托盘报告“已就绪”。
        server = await serve(
            ws_recv,
            Config.addr,
            Config.port,
            subprotocols=["binary"],
            max_size=None,
        )
        console.rule("[green3]开始服务")
        console.line()
        _report(status_queue, "ready", "本地语音服务已就绪。")

        if system() == "Windows":
            empty_current_working_set()

        send_task = asyncio.create_task(ws_send())
        if stop_event is None:
            await send_task
        else:
            await _wait_for_stop(stop_event)
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()

        # 停止发送协程和模型进程，避免统一启动器退出后留下后台进程。
        Cosmic.queue_out.put(None)
        if send_task is not None:
            try:
                await asyncio.wait_for(send_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                send_task.cancel()

        Cosmic.queue_in.put(None)
        if recognize_process is not None:
            recognize_process.join(timeout=5.0)
            if recognize_process.is_alive():
                recognize_process.terminate()
                recognize_process.join(timeout=2.0)
        manager.shutdown()


def init(stop_event=None, status_queue=None):
    try:
        asyncio.run(main(stop_event=stop_event, status_queue=status_queue))
    except KeyboardInterrupt:
        console.print("\n再见！")
    except Exception as exc:
        _report(status_queue, "error", f"服务端错误：{exc}")
        console.print(f"出错了：{exc}", style="bright_red")
        if status_queue is not None:
            raise


if __name__ == "__main__":
    init()
