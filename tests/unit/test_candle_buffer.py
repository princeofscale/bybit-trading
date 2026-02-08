from decimal import Decimal

import pytest

from core.candle_buffer import CandleBuffer
from exchange.models import Candle


def make_candle(open_time: int, close: float = 50000.0) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="15m",
        open_time=open_time,
        open=Decimal(str(close)),
        high=Decimal(str(close + 100)),
        low=Decimal(str(close - 100)),
        close=Decimal(str(close)),
        volume=Decimal("100"),
    )


def test_initialize_buffer() -> None:
    buffer = CandleBuffer(max_candles=100)
    candles = [make_candle(i * 900000) for i in range(50)]

    buffer.initialize("BTCUSDT", candles)

    result = buffer.get_candles("BTCUSDT")
    assert len(result) == 50


def test_initialize_respects_max_limit() -> None:
    buffer = CandleBuffer(max_candles=10)
    candles = [make_candle(i * 900000) for i in range(50)]

    buffer.initialize("BTCUSDT", candles)

    result = buffer.get_candles("BTCUSDT")
    assert len(result) == 10
    assert result[0].open_time == candles[-10].open_time


def test_update_append_new_candle() -> None:
    buffer = CandleBuffer(max_candles=100)
    candles = [make_candle(i * 900000) for i in range(5)]
    buffer.initialize("BTCUSDT", candles)

    new_candle = make_candle(5 * 900000, 51000.0)
    buffer.update("BTCUSDT", new_candle)

    result = buffer.get_candles("BTCUSDT")
    assert len(result) == 6
    assert result[-1].close == Decimal("51000")


def test_update_replace_same_timestamp() -> None:
    buffer = CandleBuffer(max_candles=100)
    candles = [make_candle(i * 900000) for i in range(5)]
    buffer.initialize("BTCUSDT", candles)

    updated_candle = make_candle(4 * 900000, 51000.0)
    buffer.update("BTCUSDT", updated_candle)

    result = buffer.get_candles("BTCUSDT")
    assert len(result) == 5
    assert result[-1].close == Decimal("51000")


def test_update_respects_max_candles() -> None:
    buffer = CandleBuffer(max_candles=5)
    candles = [make_candle(i * 900000) for i in range(5)]
    buffer.initialize("BTCUSDT", candles)

    new_candle = make_candle(5 * 900000)
    buffer.update("BTCUSDT", new_candle)

    result = buffer.get_candles("BTCUSDT")
    assert len(result) == 5
    assert result[0].open_time == 1 * 900000


def test_has_enough() -> None:
    buffer = CandleBuffer(max_candles=100)
    candles = [make_candle(i * 900000) for i in range(20)]
    buffer.initialize("BTCUSDT", candles)

    assert buffer.has_enough("BTCUSDT", 10)
    assert buffer.has_enough("BTCUSDT", 20)
    assert not buffer.has_enough("BTCUSDT", 21)


def test_multiple_symbols() -> None:
    buffer = CandleBuffer(max_candles=100)

    btc_candles = [make_candle(i * 900000) for i in range(10)]
    buffer.initialize("BTCUSDT", btc_candles)

    eth_candles = [make_candle(i * 900000) for i in range(5)]
    buffer.initialize("ETHUSDT", eth_candles)

    assert len(buffer.get_candles("BTCUSDT")) == 10
    assert len(buffer.get_candles("ETHUSDT")) == 5


def test_clear_symbol() -> None:
    buffer = CandleBuffer(max_candles=100)
    candles = [make_candle(i * 900000) for i in range(10)]
    buffer.initialize("BTCUSDT", candles)

    buffer.clear("BTCUSDT")

    assert len(buffer.get_candles("BTCUSDT")) == 0


def test_clear_all() -> None:
    buffer = CandleBuffer(max_candles=100)

    btc_candles = [make_candle(i * 900000) for i in range(10)]
    buffer.initialize("BTCUSDT", btc_candles)

    eth_candles = [make_candle(i * 900000) for i in range(5)]
    buffer.initialize("ETHUSDT", eth_candles)

    buffer.clear_all()

    assert len(buffer.get_candles("BTCUSDT")) == 0
    assert len(buffer.get_candles("ETHUSDT")) == 0


def test_symbols_property() -> None:
    buffer = CandleBuffer(max_candles=100)

    buffer.initialize("BTCUSDT", [make_candle(0)])
    buffer.initialize("ETHUSDT", [make_candle(0)])

    symbols = buffer.symbols
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" in symbols
    assert len(symbols) == 2
