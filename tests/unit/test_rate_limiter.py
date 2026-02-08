import asyncio
import time

import pytest

from exchange.rate_limiter import EndpointCategory, RateLimiter, TokenBucket


@pytest.fixture
def rate_limiter() -> RateLimiter:
    return RateLimiter()


async def test_token_bucket_acquire() -> None:
    bucket = TokenBucket(max_tokens=5, refill_interval_ms=1000)
    for _ in range(5):
        await bucket.acquire()
    assert bucket.available_tokens < 1


async def test_token_bucket_refill() -> None:
    bucket = TokenBucket(max_tokens=10, refill_interval_ms=100)
    for _ in range(10):
        await bucket.acquire()
    await asyncio.sleep(0.15)
    assert bucket.available_tokens >= 1


async def test_rate_limiter_acquire(rate_limiter: RateLimiter) -> None:
    start = time.monotonic()
    for _ in range(10):
        await rate_limiter.acquire(EndpointCategory.ORDER_CREATE, "BTCUSDT")
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


async def test_rate_limiter_separate_symbols(rate_limiter: RateLimiter) -> None:
    for _ in range(10):
        await rate_limiter.acquire(EndpointCategory.ORDER_CREATE, "BTCUSDT")
    await rate_limiter.acquire(EndpointCategory.ORDER_CREATE, "ETHUSDT")


async def test_update_from_headers(rate_limiter: RateLimiter) -> None:
    await rate_limiter.acquire(EndpointCategory.MARKET_DATA)
    rate_limiter.update_from_headers(
        EndpointCategory.MARKET_DATA,
        remaining=15,
        reset_timestamp_ms=int(time.time() * 1000) + 1000,
    )
