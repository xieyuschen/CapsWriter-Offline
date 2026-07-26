import asyncio
import threading
import time

import numpy as np
import sounddevice as sd

from config import ClientConfig as Config
from util.app_info import app_info
from util.client_cosmic import Cosmic, console


def record_callback(
    indata: np.ndarray,
    frames: int,
    time_info,
    status: sd.CallbackFlags,
) -> None:
    if not Cosmic.on:
        return
    asyncio.run_coroutine_threadsafe(
        Cosmic.queue_in.put(
            {
                "type": "data",
                "time": time.time(),
                "data": indata.copy(),
            },
        ),
        Cosmic.loop,
    )


def stream_close(signum, frame):
    Cosmic.stream.close()


def stream_reopen():
    if Cosmic.stopping or not threading.main_thread().is_alive():
        return
    print("重启音频流")

    Cosmic.stream.close()

    # 重载 PortAudio，更新设备列表
    sd._terminate()
    sd._ffi.dlclose(sd._lib)
    sd._lib = sd._ffi.dlopen(sd._libname)
    sd._initialize()

    time.sleep(0.1)
    Cosmic.stream = stream_open()


def _input_devices():
    return [
        (index, device)
        for index, device in enumerate(sd.query_devices())
        if device["max_input_channels"] > 0
    ]


def _device_summary(devices) -> str:
    if not devices:
        return "无"
    return "；".join(
        f'{index}: {device["name"]} ({device["max_input_channels"]} 声道)'
        for index, device in devices
    )


def _select_input_device():
    """Return ``(stream device, device info, all inputs)`` with a fallback."""

    devices = _input_devices()
    configured = Config.mic_device
    if configured is not None and configured != "":
        if isinstance(configured, str) and not configured.isdigit():
            matches = [
                (index, device)
                for index, device in devices
                if configured.casefold() in device["name"].casefold()
            ]
            if not matches:
                raise RuntimeError(
                    f"配置的麦克风“{configured}”不存在。"
                    f"可用输入设备：{_device_summary(devices)}"
                )
            index, device = matches[0]
            return index, device, devices

        index = int(configured)
        try:
            device = sd.query_devices(index, kind="input")
        except (ValueError, sd.PortAudioError) as exc:
            raise RuntimeError(
                f"配置的麦克风编号 {index} 无法使用：{exc}。"
                f"可用输入设备：{_device_summary(devices)}"
            ) from exc
        return index, device, devices

    try:
        return None, sd.query_devices(kind="input"), devices
    except sd.PortAudioError as exc:
        # A device can be present even when PortAudio doesn't expose a default
        # input. Falling back also gives USB microphones a chance to work.
        if devices:
            index, device = devices[0]
            return index, device, devices
        raise RuntimeError(
            f"PortAudio 未枚举到输入设备：{exc}。"
            f"音频组件版本：sounddevice {sd.__version__}。"
        ) from exc


def stream_open():
    app_info.set_microphone("正在检测…")
    try:
        stream_device, device, devices = _select_input_device()
        channels = min(2, device["max_input_channels"])
        console.print(
            f'使用音频设备：[italic]{device["name"]}，声道数：{channels}',
            end="\n\n",
        )
    except UnicodeDecodeError:
        app_info.set_microphone("不可用")
        raise RuntimeError("麦克风设备名称编码异常") from None
    except Exception:
        app_info.set_microphone("不可用")
        raise

    try:
        stream = sd.InputStream(
            samplerate=48000,
            blocksize=int(0.05 * 48000),
            device=stream_device,
            dtype="float32",
            channels=channels,
            callback=record_callback,
            finished_callback=stream_reopen,
        )
        stream.start()
    except sd.PortAudioError as exc:
        app_info.set_microphone("不可用")
        raise RuntimeError(
            f'无法打开麦克风“{device["name"]}”：{exc}。'
            f"可用输入设备：{_device_summary(devices)}。"
            f"可在 config.py 的 ClientConfig.mic_device 指定设备编号或名称。"
        ) from exc

    app_info.set_microphone(device["name"])
    return stream
