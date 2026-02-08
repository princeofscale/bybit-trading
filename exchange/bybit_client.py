import ccxt.async_support as ccxt
import structlog

from config.settings import ExchangeSettings
from exchange.errors import (
    AuthenticationError,
    ExchangeError,
    ExchangeErrorType,
    InsufficientFundsError,
    InvalidOrderError,
    RateLimitError,
)

logger = structlog.get_logger("bybit_client")


class BybitClient:
    def __init__(self, settings: ExchangeSettings) -> None:
        self._settings = settings
        self._exchange: ccxt.bybit | None = None

    async def connect(self) -> None:
        config = {
            "apiKey": self._settings.api_key.get_secret_value(),
            "secret": self._settings.api_secret.get_secret_value(),
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
                "recvWindow": self._settings.recv_window,
            },
        }

        if self._settings.demo_trading:
            config["urls"] = {
                "api": {
                    "public": "https://api-demo.bybit.com",
                    "private": "https://api-demo.bybit.com",
                },
            }
        else:
            config["sandbox"] = self._settings.testnet

        self._exchange = ccxt.bybit(config)

        if self._settings.demo_trading:
            markets = await self._exchange.fetch_markets()
            self._exchange.markets = self._exchange.index_by(markets, 'symbol')
            self._exchange.markets_by_id = self._exchange.index_by(markets, 'id')
        else:
            await self._exchange.load_markets()

        await logger.ainfo(
            "exchange_connected",
            testnet=self._settings.testnet,
            demo_trading=self._settings.demo_trading,
            markets_count=len(self._exchange.markets),
        )

    async def disconnect(self) -> None:
        if self._exchange:
            await self._exchange.close()
            await logger.ainfo("exchange_disconnected")

    @property
    def exchange(self) -> ccxt.bybit:
        if not self._exchange:
            raise RuntimeError("Exchange not connected")
        return self._exchange

    async def reload_markets(self) -> None:
        await self.exchange.load_markets(reload=True)


def map_ccxt_error(error: Exception) -> ExchangeError:
    if isinstance(error, ccxt.InsufficientFunds):
        return InsufficientFundsError(str(error), error)
    if isinstance(error, ccxt.OrderNotFound):
        return ExchangeError(ExchangeErrorType.ORDER_NOT_FOUND, str(error), error)
    if isinstance(error, ccxt.InvalidOrder):
        return InvalidOrderError(str(error), error)
    if isinstance(error, ccxt.RateLimitExceeded):
        return RateLimitError(str(error), error)
    if isinstance(error, ccxt.AuthenticationError):
        return AuthenticationError(str(error), error)
    if isinstance(error, ccxt.ExchangeNotAvailable):
        return ExchangeError(ExchangeErrorType.EXCHANGE_UNAVAILABLE, str(error), error)
    if isinstance(error, ccxt.NetworkError):
        return ExchangeError(ExchangeErrorType.NETWORK, str(error), error)
    return ExchangeError(ExchangeErrorType.UNKNOWN, str(error), error)
