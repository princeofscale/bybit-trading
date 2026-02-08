import asyncio
from enum import StrEnum

from pydantic import BaseModel

from utils.time_utils import utc_now_ms


class EndpointCategory(StrEnum):
    ORDER_CREATE = "order_create"
    ORDER_AMEND = "order_amend"
    ORDER_CANCEL = "order_cancel"
    ORDER_CANCEL_ALL = "order_cancel_all"
    ORDER_QUERY = "order_query"
    POSITION = "position"
    ACCOUNT = "account"
    MARKET_DATA = "market_data"


class RateLimitConfig(BaseModel):
    max_requests: int
    window_ms: int = 1000


RATE_LIMITS: dict[EndpointCategory, RateLimitConfig] = {
    EndpointCategory.ORDER_CREATE: RateLimitConfig(max_requests=10),
    EndpointCategory.ORDER_AMEND: RateLimitConfig(max_requests=10),
    EndpointCategory.ORDER_CANCEL: RateLimitConfig(max_requests=10),
    EndpointCategory.ORDER_CANCEL_ALL: RateLimitConfig(max_requests=1),
    EndpointCategory.ORDER_QUERY: RateLimitConfig(max_requests=10),
    EndpointCategory.POSITION: RateLimitConfig(max_requests=10),
    EndpointCategory.ACCOUNT: RateLimitConfig(max_requests=10),
    EndpointCategory.MARKET_DATA: RateLimitConfig(max_requests=20),
}


class TokenBucket:
    def __init__(self, max_tokens: int, refill_interval_ms: int) -> None:
        self._max_tokens = max_tokens
        self._tokens = float(max_tokens)
        self._refill_rate = max_tokens / (refill_interval_ms / 1000)
        self._last_refill = utc_now_ms()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            while self._tokens < 1:
                wait_time = (1 - self._tokens) / self._refill_rate
                await asyncio.sleep(wait_time)
                self._refill()
            self._tokens -= 1

    def _refill(self) -> None:
        now = utc_now_ms()
        elapsed_seconds = (now - self._last_refill) / 1000
        self._tokens = min(
            self._max_tokens,
            self._tokens + elapsed_seconds * self._refill_rate,
        )
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def _get_bucket(self, category: EndpointCategory, symbol: str = "") -> TokenBucket:
        key = f"{category}:{symbol}" if symbol else category.value
        if key not in self._buckets:
            config = RATE_LIMITS.get(category, RateLimitConfig(max_requests=10))
            self._buckets[key] = TokenBucket(
                max_tokens=config.max_requests,
                refill_interval_ms=config.window_ms,
            )
        return self._buckets[key]

    async def acquire(self, category: EndpointCategory, symbol: str = "") -> None:
        bucket = self._get_bucket(category, symbol)
        await bucket.acquire()

    def update_from_headers(
        self,
        category: EndpointCategory,
        remaining: int,
        reset_timestamp_ms: int,
        symbol: str = "",
    ) -> None:
        key = f"{category}:{symbol}" if symbol else category.value
        if key in self._buckets:
            bucket = self._buckets[key]
            bucket._tokens = float(remaining)
            bucket._last_refill = utc_now_ms()
