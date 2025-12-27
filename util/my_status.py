from rich.console import RenderableType
from rich.style import StyleType
from rich.status import Status as St


class Status:  # 1. 去掉继承 St，切断与 rich 的联系
    """
    重写为静默版本，不再触发任何控制台操作
    """
    def __init__(self,
                 status: RenderableType,
                 *,
                 spinner: str = "dots",
                 spinner_style: StyleType = "status.spinner",
                 speed: float = 1.0,
                 refresh_per_second: float = 12.5):
        # 只要保留这些参数名，外面调用就不会报错
        self.started = False

    def start(self) -> None:
        # 只改状态，不调 super().start()，这样就不会弹黑框
        if not self.started:
            self.started = True
            # print("DEBUG: 逻辑启动，不再显示黑框动画") 

    def stop(self) -> None:
        if self.started:
            self.started = False
            # print("DEBUG: 逻辑停止")

    def update(self, *args, **kwargs):
        # 防止其他地方调用 status.update() 报错
        pass