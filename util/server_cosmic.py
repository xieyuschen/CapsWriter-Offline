from multiprocessing import Queue
from typing import Any, Dict, List
from rich.console import Console 
console = Console(highlight=False)





class Cosmic:
    sockets: Dict[str, Any] = {}
    sockets_id: List
    queue_in = Queue()
    queue_out = Queue()
