from datetime import datetime

import structlog
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from data.models import CandleRecord, EquitySnapshot, PositionRecord, TradeRecord
from exchange.models import Candle
from utils.time_utils import ms_to_datetime

logger = structlog.get_logger("storage")


class CandleStorage:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_candles(self, candles: list[Candle]) -> int:
        if not candles:
            return 0

        records = [
            {
                "symbol": c.symbol,
                "timeframe": c.timeframe,
                "open_time": ms_to_datetime(c.open_time),
                "open_price": float(c.open),
                "high_price": float(c.high),
                "low_price": float(c.low),
                "close_price": float(c.close),
                "volume": float(c.volume),
            }
            for c in candles
        ]

        async with self._session_factory() as session:
            stmt = pg_insert(CandleRecord).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "timeframe", "open_time"],
                set_={
                    "close_price": stmt.excluded.close_price,
                    "high_price": stmt.excluded.high_price,
                    "low_price": stmt.excluded.low_price,
                    "volume": stmt.excluded.volume,
                },
            )
            await session.execute(stmt)
            await session.commit()

        await logger.ainfo("candles_saved", count=len(records), symbol=candles[0].symbol)
        return len(records)

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1000,
    ) -> list[CandleRecord]:
        async with self._session_factory() as session:
            stmt = (
                select(CandleRecord)
                .where(
                    and_(
                        CandleRecord.symbol == symbol,
                        CandleRecord.timeframe == timeframe,
                    )
                )
                .order_by(CandleRecord.open_time.asc())
                .limit(limit)
            )
            if since:
                stmt = stmt.where(CandleRecord.open_time >= since)
            if until:
                stmt = stmt.where(CandleRecord.open_time <= until)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_latest_candle_time(self, symbol: str, timeframe: str) -> datetime | None:
        async with self._session_factory() as session:
            stmt = (
                select(CandleRecord.open_time)
                .where(
                    and_(
                        CandleRecord.symbol == symbol,
                        CandleRecord.timeframe == timeframe,
                    )
                )
                .order_by(CandleRecord.open_time.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row


class TradeStorage:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_trade(self, trade: TradeRecord) -> None:
        async with self._session_factory() as session:
            session.add(trade)
            await session.commit()

    async def get_trades(
        self,
        symbol: str | None = None,
        strategy: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[TradeRecord]:
        async with self._session_factory() as session:
            stmt = select(TradeRecord).order_by(TradeRecord.created_at.desc()).limit(limit)
            if symbol:
                stmt = stmt.where(TradeRecord.symbol == symbol)
            if strategy:
                stmt = stmt.where(TradeRecord.strategy_name == strategy)
            if since:
                stmt = stmt.where(TradeRecord.created_at >= since)
            result = await session.execute(stmt)
            return list(result.scalars().all())


class EquityStorage:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_snapshot(self, snapshot: EquitySnapshot) -> None:
        async with self._session_factory() as session:
            session.add(snapshot)
            await session.commit()

    async def get_snapshots(
        self,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[EquitySnapshot]:
        async with self._session_factory() as session:
            stmt = select(EquitySnapshot).order_by(EquitySnapshot.timestamp.asc()).limit(limit)
            if since:
                stmt = stmt.where(EquitySnapshot.timestamp >= since)
            result = await session.execute(stmt)
            return list(result.scalars().all())
