from collections import deque

import structlog

from exchange.models import Candle

logger = structlog.get_logger("candle_buffer")


class CandleBuffer:
    def __init__(self, max_candles: int = 500) -> None:
        self._max_candles = max_candles
        self._buffers: dict[str, deque[Candle]] = {}

    def initialize(self, symbol: str, candles: list[Candle]) -> None:
        if symbol not in self._buffers:
            self._buffers[symbol] = deque(maxlen=self._max_candles)

        sorted_candles = sorted(candles, key=lambda c: c.open_time)
        self._buffers[symbol].clear()
        for candle in sorted_candles[-self._max_candles:]:
            self._buffers[symbol].append(candle)

        logger.info("candle_buffer_initialized", symbol=symbol, count=len(self._buffers[symbol]))

    def update(self, symbol: str, candle: Candle) -> None:
        if symbol not in self._buffers:
            self._buffers[symbol] = deque(maxlen=self._max_candles)

        buffer = self._buffers[symbol]

        if buffer and buffer[-1].open_time == candle.open_time:
            buffer[-1] = candle
        else:
            buffer.append(candle)

    def get_candles(self, symbol: str) -> list[Candle]:
        return list(self._buffers.get(symbol, []))

    def has_enough(self, symbol: str, min_count: int) -> bool:
        return len(self._buffers.get(symbol, [])) >= min_count

    def clear(self, symbol: str) -> None:
        if symbol in self._buffers:
            self._buffers[symbol].clear()

    def clear_all(self) -> None:
        self._buffers.clear()

    @property
    def symbols(self) -> list[str]:
        return list(self._buffers.keys())
