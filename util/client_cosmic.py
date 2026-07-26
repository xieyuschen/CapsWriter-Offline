from asyncio import AbstractEventLoop, Queue
import sounddevice as sd
from io import StringIO
from typing import Any, List, Union

from rich.console import Console 
from rich.theme import Theme
my_theme = Theme({'markdown.code':'cyan', 'markdown.item.number':'yellow'})
# console = Console(highlight=False, soft_wrap=False, theme=my_theme)
# hide console when press key under tray mode
console = Console(file=StringIO(), force_terminal=False)


class Cosmic:
    """
    用一个 class 存储需要跨模块访问的变量值，命名为 Cosmic
    """
    on = False
    queue_in: Queue
    queue_out: Queue
    loop: Union[None, AbstractEventLoop] = None
    websocket: Any = None
    audio_files = {}
    stream: Union[None, sd.InputStream] = None
    kwd_list: List[str] = []
    stopping = False


def websocket_is_open(websocket=None) -> bool:
    websocket = Cosmic.websocket if websocket is None else websocket
    if websocket is None:
        return False
    # The project deliberately uses websockets' legacy asyncio API because it
    # supports the Python versions used by the existing Windows builds.
    return not bool(getattr(websocket, "closed", True))
