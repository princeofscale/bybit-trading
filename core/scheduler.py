import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from utils.time_utils import utc_now_ms

logger = structlog.get_logger("scheduler")

ScheduledTask = Callable[[], Coroutine[Any, Any, None]]


class ScheduledJob:
    def __init__(
        self,
        name: str,
        func: ScheduledTask,
        interval_seconds: float,
        run_immediately: bool = False,
    ) -> None:
        self.name = name
        self.func = func
        self.interval_seconds = interval_seconds
        self.run_immediately = run_immediately
        self.last_run: int | None = None
        self.run_count: int = 0
        self.error_count: int = 0
        self._task: asyncio.Task[None] | None = None


class Scheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}
        self._running: bool = False

    def add_job(
        self,
        name: str,
        func: ScheduledTask,
        interval_seconds: float,
        run_immediately: bool = False,
    ) -> None:
        self._jobs[name] = ScheduledJob(
            name=name,
            func=func,
            interval_seconds=interval_seconds,
            run_immediately=run_immediately,
        )

    def remove_job(self, name: str) -> None:
        job = self._jobs.pop(name, None)
        if job and job._task:
            job._task.cancel()

    async def start(self) -> None:
        self._running = True
        for job in self._jobs.values():
            job._task = asyncio.create_task(self._run_job_loop(job))

    async def stop(self) -> None:
        self._running = False
        for job in self._jobs.values():
            if job._task:
                job._task.cancel()
                try:
                    await job._task
                except asyncio.CancelledError:
                    pass

    async def _run_job_loop(self, job: ScheduledJob) -> None:
        if not job.run_immediately:
            await asyncio.sleep(job.interval_seconds)

        while self._running:
            try:
                await job.func()
                job.last_run = utc_now_ms()
                job.run_count += 1
            except asyncio.CancelledError:
                break
            except Exception as exc:
                job.error_count += 1
                await logger.aerror(
                    "scheduled_job_error",
                    job=job.name,
                    error=str(exc),
                    error_count=job.error_count,
                )
            await asyncio.sleep(job.interval_seconds)

    @property
    def job_stats(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "last_run": job.last_run,
                "run_count": job.run_count,
                "error_count": job.error_count,
                "interval": job.interval_seconds,
            }
            for name, job in self._jobs.items()
        }
