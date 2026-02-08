import numpy as np
import pandas as pd
import pytest

from strategies.base_strategy import SignalDirection
from strategies.grid_trading import GridLevel, GridTradingStrategy


def _make_ranging_df(n: int = 60) -> pd.DataFrame:
    np.random.seed(42)
    t = np.linspace(0, 4 * np.pi, n)
    close = 100 + 5 * np.sin(t) + np.random.randn(n) * 0.3
    return pd.DataFrame({
        "open": close - 0.2,
        "high": close + 1.5,
        "low": close - 1.5,
        "close": close,
        "volume": np.full(n, 1000.0),
    })


@pytest.fixture
def strategy() -> GridTradingStrategy:
    return GridTradingStrategy(
        symbols=["BTC/USDT:USDT"],
        num_grids=10,
        grid_spacing_atr=0.5,
    )


def test_min_candles(strategy: GridTradingStrategy) -> None:
    assert strategy.min_candles_required() >= 14


def test_build_grid(strategy: GridTradingStrategy) -> None:
    levels = strategy.build_grid("BTC/USDT:USDT", 100.0, 2.0)
    assert len(levels) == 10
    buy_levels = [l for l in levels if l.is_buy]
    sell_levels = [l for l in levels if not l.is_buy]
    assert len(buy_levels) == 5
    assert len(sell_levels) == 5


def test_grid_prices_ordered(strategy: GridTradingStrategy) -> None:
    levels = strategy.build_grid("BTC/USDT:USDT", 100.0, 2.0)
    buy_prices = sorted([l.price for l in levels if l.is_buy])
    sell_prices = sorted([l.price for l in levels if not l.is_buy])
    assert all(bp < 100 for bp in buy_prices)
    assert all(sp > 100 for sp in sell_prices)


def test_get_grid_empty(strategy: GridTradingStrategy) -> None:
    assert strategy.get_grid("MISSING") == []


def test_auto_builds_grid_on_first_signal(strategy: GridTradingStrategy) -> None:
    df = _make_ranging_df()
    strategy.generate_signal("BTC/USDT:USDT", df)
    grid = strategy.get_grid("BTC/USDT:USDT")
    assert len(grid) > 0


def test_reset_grid(strategy: GridTradingStrategy) -> None:
    strategy.build_grid("BTC/USDT:USDT", 100.0, 2.0)
    strategy.reset_grid("BTC/USDT:USDT")
    assert strategy.get_grid("BTC/USDT:USDT") == []


def test_grid_level_creation() -> None:
    level = GridLevel(price=99.0, is_buy=True)
    assert level.price == 99.0
    assert level.is_buy is True
    assert level.filled is False


def test_strategy_name(strategy: GridTradingStrategy) -> None:
    assert strategy.name == "grid_trading"
