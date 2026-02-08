import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import structlog

T = TypeVar("T")

logger = structlog.get_logger("retry")


async def retry_async(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as exc:
            last_exception = exc
            if attempt == max_retries:
                break
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            await logger.awarning(
                "retry_attempt",
                func=func.__name__,
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)

    raise last_exception  # type: ignore[misc]
