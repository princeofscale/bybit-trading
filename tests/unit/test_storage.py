from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from data.storage import CandleStorage, EquityStorage, TradeStorage
from exchange.models import Candle


def _make_session_factory() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.add = MagicMock()

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = ctx

    return factory, session


def _make_candle(open_time: int = 1000, close: str = "100") -> Candle:
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


class TestCandleStorage:
    async def test_save_candles_empty(self) -> None:
        factory, _ = _make_session_factory()
        storage = CandleStorage(factory)
        count = await storage.save_candles([])
        assert count == 0

    async def test_save_candles_calls_execute(self) -> None:
        factory, session = _make_session_factory()
        storage = CandleStorage(factory)
        candles = [_make_candle(1000), _make_candle(2000)]
        count = await storage.save_candles(candles)
        assert count == 2
        session.execute.assert_called_once()
        session.commit.assert_called_once()

    async def test_get_candles_calls_execute(self) -> None:
        factory, session = _make_session_factory()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        storage = CandleStorage(factory)

        result = await storage.get_candles("BTC/USDT:USDT", "15m")
        assert result == []
        session.execute.assert_called_once()

    async def test_get_candles_with_date_range(self) -> None:
        factory, session = _make_session_factory()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        storage = CandleStorage(factory)

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        until = datetime(2024, 12, 31, tzinfo=timezone.utc)
        result = await storage.get_candles("BTC/USDT:USDT", "15m", since=since, until=until)
        assert result == []

    async def test_get_latest_candle_time(self) -> None:
        factory, session = _make_session_factory()
        session.execute.return_value.scalar_one_or_none.return_value = None
        storage = CandleStorage(factory)

        result = await storage.get_latest_candle_time("BTC/USDT:USDT", "15m")
        assert result is None


class TestTradeStorage:
    async def test_save_trade(self) -> None:
        factory, session = _make_session_factory()
        storage = TradeStorage(factory)
        trade = MagicMock()
        await storage.save_trade(trade)
        session.add.assert_called_once_with(trade)
        session.commit.assert_called_once()

    async def test_get_trades(self) -> None:
        factory, session = _make_session_factory()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        storage = TradeStorage(factory)

        result = await storage.get_trades(symbol="BTC/USDT:USDT")
        assert result == []


class TestEquityStorage:
    async def test_save_snapshot(self) -> None:
        factory, session = _make_session_factory()
        storage = EquityStorage(factory)
        snapshot = MagicMock()
        await storage.save_snapshot(snapshot)
        session.add.assert_called_once_with(snapshot)
        session.commit.assert_called_once()

    async def test_get_snapshots(self) -> None:
        factory, session = _make_session_factory()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        storage = EquityStorage(factory)

        result = await storage.get_snapshots()
        assert result == []
