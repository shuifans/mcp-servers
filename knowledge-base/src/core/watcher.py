import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver


class DebouncedHandler(FileSystemEventHandler):
    def __init__(self, callback, delay=2):
        self.callback, self.delay, self.timer = callback, delay, None

    def on_any_event(self, event):
        if event.is_directory:
            return
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(self.delay, self.callback)
        self.timer.daemon = True
        self.timer.start()


def start_watchers(paths: list[Path], callback):
    observer = PollingObserver(timeout=2)
    handler = DebouncedHandler(callback)
    for path in paths:
        if path.exists():
            observer.schedule(handler, str(path), recursive=True)
    observer.start()
    return observer
