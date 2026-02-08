from decimal import Decimal

import numpy as np
import pandas as pd
import structlog

from exchange.models import Candle

logger = structlog.get_logger("preprocessor")


class CandlePreprocessor:
    def __init__(self, max_gap_ratio: float = 3.0) -> None:
        self._max_gap_ratio = max_gap_ratio

    def candles_to_dataframe(self, candles: list[Candle]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame(columns=[
                "open_time", "open", "high", "low", "close", "volume", "symbol", "timeframe",
            ])

        rows = [
            {
                "open_time": pd.Timestamp(c.open_time, unit="ms", tz="UTC"),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
                "symbol": c.symbol,
                "timeframe": c.timeframe,
            }
            for c in candles
        ]
        df = pd.DataFrame(rows)
        df = df.sort_values("open_time").reset_index(drop=True)
        return df

    def validate_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        mask_high = df["high"] >= df[["open", "close"]].max(axis=1)
        mask_low = df["low"] <= df[["open", "close"]].min(axis=1)
        mask_positive_vol = df["volume"] >= 0
        mask_positive_price = (df["open"] > 0) & (df["close"] > 0)

        valid_mask = mask_high & mask_low & mask_positive_vol & mask_positive_price
        invalid_count = (~valid_mask).sum()

        if invalid_count > 0:
            logger.warning("invalid_candles_removed", count=int(invalid_count))

        return df[valid_mask].reset_index(drop=True)

    def detect_gaps(self, df: pd.DataFrame, timeframe_ms: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        if len(df) < 2:
            return []

        diffs = df["open_time"].diff().dt.total_seconds() * 1000
        threshold = timeframe_ms * self._max_gap_ratio
        gap_indices = diffs[diffs > threshold].index

        gaps = []
        for idx in gap_indices:
            gap_start = df["open_time"].iloc[idx - 1]
            gap_end = df["open_time"].iloc[idx]
            gaps.append((gap_start, gap_end))

        return gaps

    def fill_missing_candles(self, df: pd.DataFrame, timeframe_ms: int) -> pd.DataFrame:
        if len(df) < 2:
            return df

        freq = pd.Timedelta(milliseconds=timeframe_ms)
        full_range = pd.date_range(
            start=df["open_time"].iloc[0],
            end=df["open_time"].iloc[-1],
            freq=freq,
        )

        df_indexed = df.set_index("open_time")
        df_reindexed = df_indexed.reindex(full_range)
        df_reindexed.index.name = "open_time"

        for col in ["symbol", "timeframe"]:
            if col in df_reindexed.columns:
                df_reindexed[col] = df_reindexed[col].ffill()

        df_reindexed["close"] = df_reindexed["close"].ffill()
        for col in ["open", "high", "low"]:
            df_reindexed[col] = df_reindexed[col].fillna(df_reindexed["close"])
        df_reindexed["volume"] = df_reindexed["volume"].fillna(0.0)

        filled_count = len(df_reindexed) - len(df)
        if filled_count > 0:
            logger.info("candles_filled", count=filled_count)

        return df_reindexed.reset_index()

    def remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        before = len(df)
        df = df.drop_duplicates(subset=["open_time"], keep="last").reset_index(drop=True)
        removed = before - len(df)

        if removed > 0:
            logger.info("duplicates_removed", count=removed)

        return df

    def normalize_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "close" not in df.columns:
            return df

        df = df.copy()
        df["returns"] = df["close"].pct_change()
        df["log_returns"] = np.log(df["close"] / df["close"].shift(1))
        return df

    def clean_pipeline(self, candles: list[Candle], timeframe_ms: int) -> pd.DataFrame:
        df = self.candles_to_dataframe(candles)
        df = self.remove_duplicates(df)
        df = self.validate_ohlcv(df)
        df = self.fill_missing_candles(df, timeframe_ms)
        df = self.normalize_returns(df)
        return df
