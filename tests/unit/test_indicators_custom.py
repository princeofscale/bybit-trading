import numpy as np
import pandas as pd
import pytest

from indicators.custom import (
    bid_ask_spread,
    heikin_ashi,
    market_regime,
    orderbook_imbalance,
    price_momentum_divergence,
    support_resistance_levels,
    trade_flow_imbalance,
    weighted_orderbook_imbalance,
)


def test_orderbook_imbalance_balanced() -> None:
    bids = [(100.0, 10.0), (99.0, 10.0)]
    asks = [(101.0, 10.0), (102.0, 10.0)]
    assert orderbook_imbalance(bids, asks) == 0.0


def test_orderbook_imbalance_bid_heavy() -> None:
    bids = [(100.0, 30.0), (99.0, 20.0)]
    asks = [(101.0, 5.0), (102.0, 5.0)]
    result = orderbook_imbalance(bids, asks)
    assert result > 0


def test_orderbook_imbalance_empty() -> None:
    assert orderbook_imbalance([], []) == 0.0


def test_weighted_orderbook_imbalance() -> None:
    bids = [(99.0, 10.0), (98.0, 10.0)]
    asks = [(101.0, 10.0), (102.0, 10.0)]
    result = weighted_orderbook_imbalance(bids, asks, mid_price=100.0)
    assert isinstance(result, float)


def test_weighted_orderbook_imbalance_zero_mid() -> None:
    result = weighted_orderbook_imbalance([], [], mid_price=0.0)
    assert result == 0.0


def test_bid_ask_spread() -> None:
    result = bid_ask_spread(99.0, 101.0)
    assert result == pytest.approx(0.02, abs=0.001)


def test_bid_ask_spread_zero() -> None:
    assert bid_ask_spread(0.0, 100.0) == 0.0


def test_trade_flow_imbalance() -> None:
    np.random.seed(42)
    prices = pd.Series(np.cumsum(np.random.randn(100)) + 100)
    volumes = pd.Series(np.random.randint(100, 1000, 100).astype(float))
    result = trade_flow_imbalance(prices, volumes, window=20)
    assert len(result) == 100
    assert not result.isna().any()


def test_price_momentum_divergence() -> None:
    close = pd.Series(range(100, 150), dtype=float)
    rsi = pd.Series(np.linspace(70, 30, 50))
    result = price_momentum_divergence(close, rsi, window=10)
    assert len(result) == 50


def test_support_resistance_levels() -> None:
    np.random.seed(42)
    n = 100
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    high = close + 1
    low = close - 1
    result = support_resistance_levels(high, low, close)
    assert "support" in result
    assert "resistance" in result


def test_market_regime() -> None:
    np.random.seed(42)
    n = 100
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    adx_vals = pd.Series(np.random.uniform(10, 50, n))
    atr_vals = pd.Series(np.random.uniform(0.5, 3.0, n))
    result = market_regime(close, adx_vals, atr_vals)
    assert len(result) == n
    valid_regimes = {"low_vol_range", "high_vol_trend", "low_vol_trend", "high_vol_range"}
    assert set(result.unique()).issubset(valid_regimes)


def test_heikin_ashi() -> None:
    np.random.seed(42)
    n = 50
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    open_price = close.shift(1).fillna(100.0)
    high = pd.concat([close, open_price], axis=1).max(axis=1) + 1
    low = pd.concat([close, open_price], axis=1).min(axis=1) - 1
    result = heikin_ashi(open_price, high, low, close)
    assert "open" in result
    assert "high" in result
    assert "low" in result
    assert "close" in result
    assert len(result["close"]) == n
