from enum import StrEnum


class ExchangeErrorType(StrEnum):
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    INVALID_ORDER = "invalid_order"
    ORDER_NOT_FOUND = "order_not_found"
    NETWORK = "network"
    EXCHANGE_UNAVAILABLE = "exchange_unavailable"
    UNKNOWN = "unknown"


class ExchangeError(Exception):
    def __init__(self, error_type: ExchangeErrorType, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.raw_error = raw_error

    @property
    def is_retryable(self) -> bool:
        return self.error_type in {
            ExchangeErrorType.RATE_LIMIT,
            ExchangeErrorType.NETWORK,
            ExchangeErrorType.EXCHANGE_UNAVAILABLE,
        }


class InsufficientFundsError(ExchangeError):
    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(ExchangeErrorType.INSUFFICIENT_FUNDS, message, raw_error)


class InvalidOrderError(ExchangeError):
    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(ExchangeErrorType.INVALID_ORDER, message, raw_error)


class RateLimitError(ExchangeError):
    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(ExchangeErrorType.RATE_LIMIT, message, raw_error)


class AuthenticationError(ExchangeError):
    def __init__(self, message: str, raw_error: Exception | None = None) -> None:
        super().__init__(ExchangeErrorType.AUTHENTICATION, message, raw_error)
