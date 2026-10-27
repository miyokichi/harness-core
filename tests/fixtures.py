import threading
import os
from pathlib import Path

entered = threading.Event()
release = threading.Event()
calls = 0


def identity(value):
    return value


def add(value):
    return value + 1


def fail():
    raise RuntimeError("intentional failure")


def invalid_number():
    return float("nan")


def context(_context):
    return _context


def blocked():
    global calls
    calls += 1
    entered.set()
    if not release.wait(5):
        raise TimeoutError("test synchronization failed")
    return calls


def append_marker(path):
    with Path(path).open("a", encoding="utf-8") as file:
        file.write("実行済み\n")
    return {"written": True}


def crash_after_write(path):
    append_marker(path)
    os._exit(73)
