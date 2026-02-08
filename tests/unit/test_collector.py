from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from data.collector import TIMEFRAME_MS, HistoricalCollector
from exchange.models import Candle


def _make_candle(open_time: int, close: str = "100") -> Candle:
    return Candle(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        open_time=open_time,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("10"),
    )


@pytest.fixture
def mock_rest_api() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def collector(mock_rest_api: AsyncMock) -> HistoricalCollector:
    return HistoricalCollector(mock_rest_api)


async def test_fetch_candles_single_batch(collector: HistoricalCollector, mock_rest_api: AsyncMock) -> None:
    candles = [_make_candle(i * 900_000) for i in range(5)]
    mock_rest_api.fetch_ohlcv.return_value = candles

    result = await collector.fetch_candles("BTC/USDT:USDT", "15m", limit_per_request=200)

    assert len(result) == 5
    mock_rest_api.fetch_ohlcv.assert_called_once()


async def test_fetch_candles_empty(collector: HistoricalCollector, mock_rest_api: AsyncMock) -> None:
    mock_rest_api.fetch_ohlcv.return_value = []
    result = await collector.fetch_candles("BTC/USDT:USDT", "15m")
    assert len(result) == 0


async def test_fetch_candles_pagination(collector: HistoricalCollector, mock_rest_api: AsyncMock) -> None:
    batch1 = [_make_candle(i * 900_000) for i in range(3)]
    batch2 = [_make_candle((3 + i) * 900_000) for i in range(2)]

    mock_rest_api.fetch_ohlcv.side_effect = [batch1, batch2]

    result = await collector.fetch_candles(
        "BTC/USDT:USDT", "15m", limit_per_request=3,
    )

    assert len(result) == 5
    assert mock_rest_api.fetch_ohlcv.call_count == 2


async def test_fetch_candles_with_until(collector: HistoricalCollector, mock_rest_api: AsyncMock) -> None:
    candles = [_make_candle(i * 900_000) for i in range(10)]
    mock_rest_api.fetch_ohlcv.return_value = candles

    until = 4 * 900_000
    result = await collector.fetch_candles(
        "BTC/USDT:USDT", "15m", until=until, limit_per_request=200,
    )

    assert all(c.open_time <= until for c in result)


async def test_fetch_funding_rates(collector: HistoricalCollector, mock_rest_api: AsyncMock) -> None:
    mock_rest_api.fetch_funding_rate.return_value = Decimal("0.0001")
    result = await collector.fetch_funding_rates("BTC/USDT:USDT")
    assert len(result) == 1
    assert result[0]["funding_rate"] == Decimal("0.0001")


async def test_collect_multiple_symbols(collector: HistoricalCollector, mock_rest_api: AsyncMock) -> None:
    btc_candles = [_make_candle(1000)]
    eth_candle = Candle(
        symbol="ETH/USDT:USDT", timeframe="15m", open_time=1000,
        open=Decimal("2000"), high=Decimal("2000"), low=Decimal("2000"),
        close=Decimal("2000"), volume=Decimal("100"),
    )

    mock_rest_api.fetch_ohlcv.side_effect = [btc_candles, [eth_candle]]

    result = await collector.collect_multiple_symbols(
        ["BTC/USDT:USDT", "ETH/USDT:USDT"], "15m",
    )

    assert "BTC/USDT:USDT" in result
    assert "ETH/USDT:USDT" in result
    assert mock_rest_api.fetch_ohlcv.call_count == 2


def test_timeframe_ms_mapping() -> None:
    assert TIMEFRAME_MS["1m"] == 60_000
    assert TIMEFRAME_MS["15m"] == 900_000
    assert TIMEFRAME_MS["1h"] == 3_600_000
    assert TIMEFRAME_MS["1d"] == 86_400_000
