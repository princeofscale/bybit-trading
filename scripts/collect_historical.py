import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

from config.settings import ExchangeSettings
from exchange.bybit_client import BybitClient
from exchange.rest_api import RestApi
from data.collector import HistoricalCollector
from monitoring.logger import setup_logging
from config.settings import LogLevel, LogFormat

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
TIMEFRAMES = ["15m", "1h", "4h"]
DATA_DIR = Path("data/historical")


async def collect(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    days_back: int = 365,
) -> None:
    setup_logging(LogLevel.INFO, LogFormat.CONSOLE)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    settings = ExchangeSettings()
    client = BybitClient(settings)
    rest_api = RestApi(client)
    collector = HistoricalCollector(rest_api)

    target_symbols = symbols or SYMBOLS
    target_timeframes = timeframes or TIMEFRAMES

    from utils.time_utils import utc_now_ms
    now = utc_now_ms()
    since = now - (days_back * 86_400_000)

    for symbol in target_symbols:
        for tf in target_timeframes:
            safe_symbol = symbol.replace("/", "_").replace(":", "_")
            filepath = DATA_DIR / f"{safe_symbol}_{tf}.csv"

            print(f"Collecting {symbol} {tf} ({days_back} days)...")

            try:
                candles = await collector.fetch_candles(
                    symbol, tf, since=since, until=now,
                )
                if not candles:
                    print(f"  No data for {symbol} {tf}")
                    continue

                rows = [
                    {
                        "open_time": c.open_time,
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                        "volume": float(c.volume),
                    }
                    for c in candles
                ]
                df = pd.DataFrame(rows)
                df.to_csv(filepath, index=False)
                print(f"  Saved {len(candles)} candles to {filepath}")
            except Exception as e:
                print(f"  Error: {e}")

    print("Collection complete.")


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    asyncio.run(collect(days_back=days))


if __name__ == "__main__":
    main()
