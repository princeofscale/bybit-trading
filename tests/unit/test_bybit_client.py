import ccxt

from exchange.bybit_client import map_ccxt_error
from exchange.errors import (
    AuthenticationError,
    ExchangeError,
    ExchangeErrorType,
    InsufficientFundsError,
    InvalidOrderError,
    RateLimitError,
)


def test_map_insufficient_funds() -> None:
    err = map_ccxt_error(ccxt.InsufficientFunds("no money"))
    assert isinstance(err, InsufficientFundsError)
    assert err.is_retryable is False


def test_map_invalid_order() -> None:
    err = map_ccxt_error(ccxt.InvalidOrder("bad order"))
    assert isinstance(err, InvalidOrderError)


def test_map_rate_limit() -> None:
    err = map_ccxt_error(ccxt.RateLimitExceeded("slow down"))
    assert isinstance(err, RateLimitError)
    assert err.is_retryable is True


def test_map_authentication() -> None:
    err = map_ccxt_error(ccxt.AuthenticationError("bad key"))
    assert isinstance(err, AuthenticationError)
    assert err.is_retryable is False


def test_map_network_error() -> None:
    err = map_ccxt_error(ccxt.NetworkError("timeout"))
    assert err.error_type == ExchangeErrorType.NETWORK
    assert err.is_retryable is True


def test_map_exchange_unavailable() -> None:
    err = map_ccxt_error(ccxt.ExchangeNotAvailable("maintenance"))
    assert err.error_type == ExchangeErrorType.EXCHANGE_UNAVAILABLE
    assert err.is_retryable is True


def test_map_order_not_found() -> None:
    err = map_ccxt_error(ccxt.OrderNotFound("not found"))
    assert err.error_type == ExchangeErrorType.ORDER_NOT_FOUND


def test_map_unknown_error() -> None:
    err = map_ccxt_error(ccxt.ExchangeError("something weird"))
    assert err.error_type == ExchangeErrorType.UNKNOWN
