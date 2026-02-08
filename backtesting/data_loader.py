from decimal import Decimal
from pathlib import Path

import pandas as pd

from exchange.models import Candle


class BacktestDataLoader:
    def candles_to_dataframe(self, candles: list[Candle]) -> pd.DataFrame:
        rows = []
        for c in candles:
            rows.append({
                "open_time": c.open_time,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            })
        df = pd.DataFrame(rows)
        df.sort_values("open_time", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def load_csv(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        required = {"open_time", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"missing_columns: {missing}")
        df.sort_values("open_time", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def generate_synthetic(
        self,
        n_bars: int,
        start_price: float = 100.0,
        volatility: float = 0.02,
        trend: float = 0.0001,
        start_time: int = 1_700_000_000_000,
        interval_ms: int = 900_000,
    ) -> pd.DataFrame:
        import random

        prices = [start_price]
        for _ in range(n_bars - 1):
            change = random.gauss(trend, volatility)
            prices.append(prices[-1] * (1 + change))

        rows = []
        for i, close in enumerate(prices):
            o = close * (1 + random.gauss(0, volatility * 0.3))
            h = max(o, close) * (1 + abs(random.gauss(0, volatility * 0.5)))
            l = min(o, close) * (1 - abs(random.gauss(0, volatility * 0.5)))
            v = random.uniform(100, 10000)
            rows.append({
                "open_time": start_time + i * interval_ms,
                "open": o,
                "high": h,
                "low": l,
                "close": close,
                "volume": v,
            })
        return pd.DataFrame(rows)

    def split_data(
        self, df: pd.DataFrame, train_pct: float = 0.7,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        split_idx = int(len(df) * train_pct)
        train = df.iloc[:split_idx].copy().reset_index(drop=True)
        test = df.iloc[split_idx:].copy().reset_index(drop=True)
        return train, test

    def split_walk_forward(
        self, df: pd.DataFrame, n_splits: int = 5, train_pct: float = 0.7,
    ) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
        total = len(df)
        step = total // n_splits
        splits = []
        for i in range(n_splits):
            end = min((i + 1) * step + step, total)
            window = df.iloc[: end].copy()
            split_idx = int(len(window) * train_pct)
            train = window.iloc[:split_idx].copy().reset_index(drop=True)
            test = window.iloc[split_idx:].copy().reset_index(drop=True)
            if len(test) > 0:
                splits.append((train, test))
        return splits
