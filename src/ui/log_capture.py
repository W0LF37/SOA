from __future__ import annotations
import queue, sys

class LogCapture:
    def __init__(self) -> None:
        self.queue: queue.Queue[str] = queue.Queue()
        self._old: object | None = None

    def __enter__(self) -> "LogCapture":
        self._old = sys.stdout
        sys.stdout = self  # type: ignore
        return self

    def write(self, text: str) -> None:
        if text.strip():
            self.queue.put(text.rstrip())
        if self._old:
            self._old.write(text)  # type: ignore

    def flush(self) -> None:
        if self._old:
            self._old.flush()  # type: ignore

    def __exit__(self, *args: object) -> None:
        sys.stdout = self._old  # type: ignore

    def drain(self) -> list[str]:
        lines: list[str] = []
        while True:
            try:
                lines.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return lines
