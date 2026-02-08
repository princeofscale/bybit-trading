from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from backtesting.data_loader import BacktestDataLoader
from exchange.models import Candle


@pytest.fixture
def loader() -> BacktestDataLoader:
    return BacktestDataLoader()


def _make_candles(n: int = 10) -> list[Candle]:
    candles = []
    for i in range(n):
        candles.append(Candle(
            symbol="BTCUSDT",
            timeframe="15m",
            open_time=1_700_000_000_000 + i * 900_000,
            open=Decimal(str(100 + i)),
            high=Decimal(str(105 + i)),
            low=Decimal(str(95 + i)),
            close=Decimal(str(102 + i)),
            volume=Decimal("1000"),
        ))
    return candles


class TestCandlesToDataframe:
    def test_correct_shape(self, loader: BacktestDataLoader) -> None:
        df = loader.candles_to_dataframe(_make_candles(10))
        assert len(df) == 10
        assert set(df.columns) == {"open_time", "open", "high", "low", "close", "volume"}

    def test_sorted_by_time(self, loader: BacktestDataLoader) -> None:
        candles = _make_candles(5)
        candles.reverse()
        df = loader.candles_to_dataframe(candles)
        times = df["open_time"].tolist()
        assert times == sorted(times)

    def test_values_converted_to_float(self, loader: BacktestDataLoader) -> None:
        df = loader.candles_to_dataframe(_make_candles(1))
        assert isinstance(df.iloc[0]["close"], float)


class TestLoadCsv:
    def test_loads_valid_csv(self, loader: BacktestDataLoader, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        df_in = pd.DataFrame({
            "open_time": [1, 2, 3],
            "open": [100, 101, 102],
            "high": [105, 106, 107],
            "low": [95, 96, 97],
            "close": [102, 103, 104],
            "volume": [1000, 1100, 1200],
        })
        df_in.to_csv(csv_path, index=False)
        df = loader.load_csv(csv_path)
        assert len(df) == 3

    def test_raises_on_missing_columns(self, loader: BacktestDataLoader, tmp_path: Path) -> None:
        csv_path = tmp_path / "bad.csv"
        pd.DataFrame({"open_time": [1], "close": [100]}).to_csv(csv_path, index=False)
        with pytest.raises(ValueError, match="missing_columns"):
            loader.load_csv(csv_path)


class TestSyntheticData:
    def test_correct_length(self, loader: BacktestDataLoader) -> None:
        df = loader.generate_synthetic(100)
        assert len(df) == 100

    def test_has_required_columns(self, loader: BacktestDataLoader) -> None:
        df = loader.generate_synthetic(10)
        required = {"open_time", "open", "high", "low", "close", "volume"}
        assert required <= set(df.columns)

    def test_high_above_low(self, loader: BacktestDataLoader) -> None:
        df = loader.generate_synthetic(50)
        assert (df["high"] >= df["low"]).all()

    def test_custom_params(self, loader: BacktestDataLoader) -> None:
        df = loader.generate_synthetic(
            n_bars=10, start_price=50000.0,
            start_time=1_000_000_000_000, interval_ms=60_000,
        )
        assert len(df) == 10
        assert df.iloc[0]["open_time"] == 1_000_000_000_000
        assert df.iloc[1]["open_time"] == 1_000_000_060_000


class TestSplitData:
    def test_train_test_split(self, loader: BacktestDataLoader) -> None:
        df = loader.generate_synthetic(100)
        train, test = loader.split_data(df, train_pct=0.7)
        assert len(train) == 70
        assert len(test) == 30

    def test_no_overlap(self, loader: BacktestDataLoader) -> None:
        df = loader.generate_synthetic(100)
        train, test = loader.split_data(df, train_pct=0.8)
        assert len(train) + len(test) == 100


class TestWalkForwardSplit:
    def test_produces_correct_folds(self, loader: BacktestDataLoader) -> None:
        df = loader.generate_synthetic(100)
        splits = loader.split_walk_forward(df, n_splits=5, train_pct=0.7)
        assert len(splits) >= 1
        for train, test in splits:
            assert len(train) > 0
            assert len(test) > 0

    def test_train_always_bigger(self, loader: BacktestDataLoader) -> None:
        df = loader.generate_synthetic(200)
        splits = loader.split_walk_forward(df, n_splits=3, train_pct=0.8)
        for train, test in splits:
            assert len(train) > len(test)
