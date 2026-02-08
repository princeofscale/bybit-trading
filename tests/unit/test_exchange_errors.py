from exchange.errors import (
    AuthenticationError,
    ExchangeErrorType,
    InsufficientFundsError,
    InvalidOrderError,
    RateLimitError,
)


def test_retryable_rate_limit() -> None:
    err = RateLimitError("rate limit hit")
    assert err.is_retryable is True
    assert err.error_type == ExchangeErrorType.RATE_LIMIT


def test_non_retryable_auth_error() -> None:
    err = AuthenticationError("bad key")
    assert err.is_retryable is False
    assert err.error_type == ExchangeErrorType.AUTHENTICATION


def test_non_retryable_insufficient_funds() -> None:
    err = InsufficientFundsError("no money")
    assert err.is_retryable is False


def test_non_retryable_invalid_order() -> None:
    err = InvalidOrderError("bad qty")
    assert err.is_retryable is False
    assert err.error_type == ExchangeErrorType.INVALID_ORDER
