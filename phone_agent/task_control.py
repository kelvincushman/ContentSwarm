"""Cooperative task stops. A stop request does not release an in-flight phone."""

import threading
import time
from dataclasses import dataclass, field


class TaskCancelled(RuntimeError):
    pass


class TaskTimeout(TimeoutError):
    pass


@dataclass
class TaskControl:
    deadline: float
    cancelled: threading.Event = field(default_factory=threading.Event)

    def check(self):
        if self.cancelled.is_set():
            raise TaskCancelled(
                "Task cancelled; inspect the phone before retrying uncertain actions"
            )
        if time.monotonic() >= self.deadline:
            raise TaskTimeout(
                "Task deadline exceeded; inspect the phone before retrying uncertain actions"
            )
