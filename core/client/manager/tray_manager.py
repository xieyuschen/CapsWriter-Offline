# coding: utf-8
import os
import sys
import subprocess
import time
from pathlib import Path

from . import logger
from config_client import ClientConfig as Config
from core.app_status import app_info, app_status


class TrayManager:
    """
    托盘管理器：负责系统托盘图标的初始化、菜单构建及回调处理。
    """
    def __init__(self, app):
        self.app = app

    @property
    def state(self):
        return self.app.state

    def start(self):
        """初始化系统托盘图标"""
        if not Config.enable_tray:
            return

        try:
            from ..ui import enable_min_to_tray
        except ImportError as e:
            logger.warning(f"托盘模块导入失败，跳过托盘功能: {e}")
            return

        # 获取图标路径
        icon_path = os.path.join(self.app.base_dir, 'assets', 'icon.ico')
        
        # 启用托盘
        enable_min_to_tray(
            'CapsWriter',
            icon_path,
            exit_callback=getattr(self.app, "exit_callback", self.app.stop),
            more_options=[
                (self._status_text, self._noop, False),
                (self._microphone_text, self._noop, False),
                (self._client_config_text, self._open_client_config),
                (self._server_config_text, self._open_server_config),
                (self._save_directory_text, self._open_save_directory),
                ('📂 日志目录', self._open_logs),
                ('📋 复制结果', self._copy_last_result),
                ('📝 上下文', self._add_context),
                ('✨ 热词', self._add_hotword),
                ('🧹 清除记忆', self._clear_memory),
                ('♻️ 重开音频', self._restart_audio),
                ('♻️ 重启本地服务', self._restart_server),
            ],
            status_bus=app_status,
        )
        logger.info("托盘图标已启用")

    def stop(self):
        """停止托盘图标"""
        if not Config.enable_tray:
            return
            
        try:
            from ..ui import stop_tray
            stop_tray()
            logger.info("TrayManager: 托盘图标已卸载")
        except Exception as e:
            logger.debug(f"TrayManager: 卸载托盘时发生错误: {e}")

    def _restart_audio(self):
        """重启音频流回调"""
        if hasattr(self.app, 'stream') and self.app.stream:
            self.app.stream.reopen()
            logger.info("用户请求重启音频")

    def _restart_server(self):
        callback = getattr(self.app, "restart_server_callback", None)
        if callback is not None:
            callback()

    @staticmethod
    def _noop(*_args):
        return None

    @staticmethod
    def _status_text(_item) -> str:
        return f"状态：{app_status.current.title}"

    @staticmethod
    def _microphone_text(_item) -> str:
        return f"当前麦克风：{app_info.microphone}"

    @property
    def _base_dir(self) -> Path:
        return Path(self.app.base_dir).resolve()

    def _client_config_text(self, _item) -> str:
        return f"客户端配置：{self._base_dir / 'config_client.py'}"

    def _server_config_text(self, _item) -> str:
        return f"服务端配置：{self._base_dir / 'config_server.py'}"

    def _save_directory(self) -> Path:
        now = time.localtime()
        return self._base_dir / time.strftime("%Y", now) / time.strftime("%m", now)

    def _save_directory_text(self, _item) -> str:
        return f"保存目录：{self._save_directory()}"

    @staticmethod
    def _open_path(path: Path) -> None:
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _open_client_config(self):
        self._open_path(self._base_dir / "config_client.py")

    def _open_server_config(self):
        self._open_path(self._base_dir / "config_server.py")

    def _open_save_directory(self):
        path = self._save_directory()
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)

    def _open_logs(self):
        path = self._base_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)

    def _clear_memory(self):
        """清除 LLM 对话历史回调"""
        from ..ui import toast
        if self.app.llm:
            self.app.llm.clear_history()
            toast("清除成功：已清除所有角色的对话历史记录", duration=3000, bg="#075077")

    def _add_hotword(self):
        """用系统默认方式打开热词文件回调"""
        
        target = os.path.abspath('hot.txt')
        if sys.platform == 'win32':
            os.startfile(target)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', target])
        else:
            subprocess.Popen(['xdg-open', target])

    def _add_context(self):
        """打开编辑上下文界面回调"""
        try:
            from ..ui import on_edit_context
            on_edit_context()
        except ImportError as e:
            logger.warning(f"无法导入上下文菜单处理器: {e}")

    def _copy_last_result(self):
        """复制最后一次识别结果到剪贴板回调"""
        text = self.state.last_output_text
        if text:
            from ..llm.llm_clipboard import copy_to_clipboard
            copy_to_clipboard(text)

    def _request_exit(self, icon=None, item=None):
        """托盘图标引用的退出回调"""
        logger.info("托盘退出: 用户点击退出菜单，准备清理资源并退出")
        self.app.stop()
