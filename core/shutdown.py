import asyncio
from enum import StrEnum
from typing import Any

import structlog

from utils.time_utils import utc_now_ms

logger = structlog.get_logger("shutdown")


class ShutdownMode(StrEnum):
    GRACEFUL = "graceful"
    IMMEDIATE = "immediate"
    CLOSE_POSITIONS = "close_positions"


class ShutdownTask:
    def __init__(self, name: str, priority: int, coro_factory: Any) -> None:
        self.name = name
        self.priority = priority
        self.coro_factory = coro_factory
        self.completed = False
        self.error: str | None = None


class ShutdownManager:
    def __init__(
        self,
        mode: ShutdownMode = ShutdownMode.GRACEFUL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._mode = mode
        self._timeout = timeout_seconds
        self._tasks: list[ShutdownTask] = []
        self._shutdown_requested = False
        self._shutdown_complete = False
        self._start_ts: int | None = None
        self._end_ts: int | None = None

    @property
    def mode(self) -> ShutdownMode:
        return self._mode

    @mode.setter
    def mode(self, value: ShutdownMode) -> None:
        self._mode = value

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    @property
    def shutdown_complete(self) -> bool:
        return self._shutdown_complete

    @property
    def registered_tasks(self) -> list[str]:
        return [t.name for t in self._tasks]

    @property
    def duration_ms(self) -> int:
        if self._start_ts and self._end_ts:
            return self._end_ts - self._start_ts
        return 0

    def register_task(
        self,
        name: str,
        coro_factory: Any,
        priority: int = 100,
    ) -> None:
        self._tasks.append(ShutdownTask(name, priority, coro_factory))

    def unregister_task(self, name: str) -> None:
        self._tasks = [t for t in self._tasks if t.name != name]

    async def execute(self) -> list[ShutdownTask]:
        self._shutdown_requested = True
        self._start_ts = utc_now_ms()

        sorted_tasks = sorted(self._tasks, key=lambda t: t.priority)

        if self._mode == ShutdownMode.IMMEDIATE:
            self._shutdown_complete = True
            self._end_ts = utc_now_ms()
            return sorted_tasks

        for task in sorted_tasks:
            try:
                await asyncio.wait_for(
                    task.coro_factory(),
                    timeout=self._timeout / max(len(sorted_tasks), 1),
                )
                task.completed = True
            except asyncio.TimeoutError:
                task.error = "timeout"
            except Exception as exc:
                task.error = str(exc)

        self._shutdown_complete = True
        self._end_ts = utc_now_ms()
        return sorted_tasks

    def get_report(self) -> dict[str, Any]:
        completed = [t for t in self._tasks if t.completed]
        failed = [t for t in self._tasks if t.error is not None]
        return {
            "mode": self._mode.value,
            "total_tasks": len(self._tasks),
            "completed": len(completed),
            "failed": len(failed),
            "duration_ms": self.duration_ms,
            "failures": [
                {"name": t.name, "error": t.error} for t in failed
            ],
        }
