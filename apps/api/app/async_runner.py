"""Run async application work on one persistent event loop per process."""

import asyncio
import os
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncRunner:
    """Own a background event loop, recreating it after a process fork."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pid: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        pid = os.getpid()
        with self._lock:
            if self._pid != pid or self._loop is None or not self._loop.is_running():
                loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=loop.run_forever, daemon=True, name="async-worker-loop"
                )
                thread.start()
                self._pid = pid
                self._loop = loop
                self._thread = thread
            return self._loop

    def run(self, coroutine: Coroutine[Any, Any, T]) -> T:
        future: Future[T] = asyncio.run_coroutine_threadsafe(coroutine, self._ensure_loop())
        return future.result()


runner = AsyncRunner()
