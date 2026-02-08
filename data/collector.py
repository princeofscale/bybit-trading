import asyncio
from decimal import Decimal

import structlog

from exchange.models import Candle
from exchange.rest_api import RestApi

logger = structlog.get_logger("collector")

TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


class HistoricalCollector:
    def __init__(self, rest_api: RestApi) -> None:
        self._rest_api = rest_api

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "15m",
        since: int | None = None,
        until: int | None = None,
        limit_per_request: int = 200,
    ) -> list[Candle]:
        all_candles: list[Candle] = []
        current_since = since

        while True:
            batch = await self._rest_api.fetch_ohlcv(
                symbol, timeframe, since=current_since, limit=limit_per_request,
            )
            if not batch:
                break

            all_candles.extend(batch)

            if until and batch[-1].open_time >= until:
                all_candles = [c for c in all_candles if c.open_time <= until]
                break

            if len(batch) < limit_per_request:
                break

            tf_ms = TIMEFRAME_MS.get(timeframe, 900_000)
            current_since = batch[-1].open_time + tf_ms
            await asyncio.sleep(0.1)

        await logger.ainfo(
            "candles_fetched",
            symbol=symbol,
            timeframe=timeframe,
            count=len(all_candles),
        )
        return all_candles

    async def fetch_funding_rates(
        self,
        symbol: str,
        since: int | None = None,
        limit: int = 200,
    ) -> list[dict[str, Decimal | int | str]]:
        rate = await self._rest_api.fetch_funding_rate(symbol)
        return [{"symbol": symbol, "funding_rate": rate}]

    async def collect_multiple_symbols(
        self,
        symbols: list[str],
        timeframe: str = "15m",
        since: int | None = None,
    ) -> dict[str, list[Candle]]:
        result: dict[str, list[Candle]] = {}
        for symbol in symbols:
            candles = await self.fetch_candles(symbol, timeframe, since=since)
            result[symbol] = candles
            await asyncio.sleep(0.2)
        return result
