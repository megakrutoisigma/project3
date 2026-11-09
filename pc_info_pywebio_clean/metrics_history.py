"""Последние 120 замеров в памяти. При закрытии программы они исчезают."""
from collections import deque
from threading import Lock
import time

_samples = deque(maxlen=120)
_lock = Lock()


def save(stats):
    sample = {key: stats[key] for key in (
        "cpu", "ram", "disk", "net_sent", "net_recv", "processes"
    )}
    sample["timestamp"] = time.time()
    with _lock:
        _samples.append(sample)


def history(limit=120):
    with _lock:
        return [dict(sample) for sample in list(_samples)[-max(1, min(limit, 120)):]]


def clear_history():
    with _lock:
        _samples.clear()
