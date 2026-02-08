from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import CandleRecord


class CandleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, candle: CandleRecord) -> None:
        stmt = pg_insert(CandleRecord).values(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            open_time=candle.open_time,
            open_price=candle.open_price,
            high_price=candle.high_price,
            low_price=candle.low_price,
            close_price=candle.close_price,
            volume=candle.volume,
            turnover=candle.turnover,
        ).on_conflict_do_update(
            index_elements=["symbol", "timeframe", "open_time"],
            set_={
                "open_price": candle.open_price,
                "high_price": candle.high_price,
                "low_price": candle.low_price,
                "close_price": candle.close_price,
                "volume": candle.volume,
            },
        )
        await self._session.execute(stmt)

    async def get_latest(
        self, symbol: str, timeframe: str, limit: int = 200,
    ) -> list[CandleRecord]:
        stmt = (
            select(CandleRecord)
            .where(CandleRecord.symbol == symbol)
            .where(CandleRecord.timeframe == timeframe)
            .order_by(CandleRecord.open_time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def get_range(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[CandleRecord]:
        stmt = (
            select(CandleRecord)
            .where(CandleRecord.symbol == symbol)
            .where(CandleRecord.timeframe == timeframe)
            .where(CandleRecord.open_time >= start)
            .where(CandleRecord.open_time <= end)
            .order_by(CandleRecord.open_time)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, symbol: str, timeframe: str) -> int:
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(CandleRecord)
            .where(CandleRecord.symbol == symbol)
            .where(CandleRecord.timeframe == timeframe)
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def delete_older_than(
        self, symbol: str, timeframe: str, before: datetime,
    ) -> int:
        stmt = (
            delete(CandleRecord)
            .where(CandleRecord.symbol == symbol)
            .where(CandleRecord.timeframe == timeframe)
            .where(CandleRecord.open_time < before)
        )
        result = await self._session.execute(stmt)
        return result.rowcount
