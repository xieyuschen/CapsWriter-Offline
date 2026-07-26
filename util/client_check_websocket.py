
try:
    from websockets.legacy.client import connect
except ImportError:  # websockets < 10
    from websockets import connect

from util.client_cosmic import Cosmic, websocket_is_open
from config import ClientConfig as Config


async def check_websocket() -> bool:
    if websocket_is_open():
        return True
    for _ in range(3):
        try:
            Cosmic.websocket = await connect(
                f"ws://{Config.addr}:{Config.port}",
                max_size=None,
                open_timeout=1,
            )
            return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            continue
        except Exception:
            continue
    return False
