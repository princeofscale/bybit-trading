import asyncio
from collections import OrderedDict
from decimal import Decimal
from typing import Any

import structlog

from exchange.models import Candle, Ticker

logger = structlog.get_logger("cache")


class LRUCache:
    def __init__(self, max_size: int = 1000) -> None:
        self._data: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Any | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self._max_size:
            self._data.popitem(last=False)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    @property
    def size(self) -> int:
        return len(self._data)


class CandleBuffer:
    def __init__(self, max_candles_per_key: int = 500) -> None:
        self._buffers: dict[str, list[Candle]] = {}
        self._max_per_key = max_candles_per_key

    def _key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol}:{timeframe}"

    def append(self, candle: Candle) -> None:
        key = self._key(candle.symbol, candle.timeframe)
        buf = self._buffers.setdefault(key, [])

        if buf and buf[-1].open_time == candle.open_time:
            buf[-1] = candle
        else:
            buf.append(candle)

        if len(buf) > self._max_per_key:
            self._buffers[key] = buf[-self._max_per_key:]

    def get_candles(self, symbol: str, timeframe: str, count: int | None = None) -> list[Candle]:
        key = self._key(symbol, timeframe)
        buf = self._buffers.get(key, [])
        if count:
            return buf[-count:]
        return list(buf)

    def get_latest(self, symbol: str, timeframe: str) -> Candle | None:
        key = self._key(symbol, timeframe)
        buf = self._buffers.get(key, [])
        return buf[-1] if buf else None

    def load_initial(self, symbol: str, timeframe: str, candles: list[Candle]) -> None:
        key = self._key(symbol, timeframe)
        self._buffers[key] = candles[-self._max_per_key:]

    @property
    def buffer_stats(self) -> dict[str, int]:
        return {key: len(buf) for key, buf in self._buffers.items()}


class TickerCache:
    def __init__(self) -> None:
        self._tickers: dict[str, Ticker] = {}

    def update(self, ticker: Ticker) -> None:
        self._tickers[ticker.symbol] = ticker

    def get(self, symbol: str) -> Ticker | None:
        return self._tickers.get(symbol)

    def get_all(self) -> dict[str, Ticker]:
        return dict(self._tickers)

    def get_funding_rate(self, symbol: str) -> Decimal:
        ticker = self._tickers.get(symbol)
        return ticker.funding_rate if ticker else Decimal("0")


class DataCache:
    def __init__(self, max_candles_per_buffer: int = 500) -> None:
        self.candles = CandleBuffer(max_candles_per_buffer)
        self.tickers = TickerCache()
        self.lru = LRUCache(max_size=5000)
