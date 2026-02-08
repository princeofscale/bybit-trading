from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from config.settings import RiskSettings
from exchange.models import Position
from risk.risk_manager import RiskManager
from strategies.base_strategy import Signal, SignalDirection
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.trend_following import TrendFollowingStrategy


def _make_trending_df(periods: int = 50, start: float = 100.0, trend: float = 0.5) -> pd.DataFrame:
    np.random.seed(42)
    prices = [start]
    for _ in range(periods - 1):
        change = trend + np.random.normal(0, 0.5)
        prices.append(prices[-1] + change)
    close = pd.Series(prices, dtype=float)
    high = close + abs(np.random.normal(1, 0.3, periods))
    low = close - abs(np.random.normal(1, 0.3, periods))
    volume = np.random.uniform(1000, 5000, periods)
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _make_mean_reverting_df(periods: int = 50, center: float = 100.0) -> pd.DataFrame:
    np.random.seed(123)
    prices = [center]
    for _ in range(periods - 1):
        reversion = (center - prices[-1]) * 0.1
        noise = np.random.normal(0, 2)
        prices.append(prices[-1] + reversion + noise)
    prices[-1] = center - 15
    close = pd.Series(prices, dtype=float)
    high = close + abs(np.random.normal(0.5, 0.2, periods))
    low = close - abs(np.random.normal(0.5, 0.2, periods))
    volume = np.random.uniform(1000, 5000, periods)
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def risk_manager() -> RiskManager:
    rm = RiskManager(RiskSettings())
    rm.initialize(Decimal("100000"))
    return rm


class TestEmaSignalToRisk:
    def test_approved_long_signal(self, risk_manager: RiskManager) -> None:
        strategy = EmaCrossoverStrategy(
            symbols=["BTCUSDT"],
            fast_period=5,
            slow_period=15,
            volume_confirmation=False,
            min_confidence=0.3,
        )
        df = _make_trending_df(periods=50, trend=1.0)
        signal = strategy.generate_signal("BTCUSDT", df)

        if signal and signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
            decision = risk_manager.evaluate_signal(
                signal, Decimal("100000"), [],
            )
            assert decision.approved is True
            assert decision.quantity > Decimal("0")
            assert decision.stop_loss > Decimal("0")

    def test_signal_rejected_without_stop_loss(self, risk_manager: RiskManager) -> None:
        signal = Signal(
            symbol="ETHUSDT",
            direction=SignalDirection.LONG,
            confidence=0.8,
            strategy_name="test",
            entry_price=Decimal("3000"),
            stop_loss=None,
        )
        decision = risk_manager.evaluate_signal(signal, Decimal("100000"), [])
        assert decision.approved is False
        assert "no_stop_loss" in decision.reason

    def test_signal_rejected_at_max_positions(self, risk_manager: RiskManager) -> None:
        positions = [
            Position(
                symbol=f"COIN{i}USDT",
                side="Long",
                size=Decimal("1"),
                entry_price=Decimal("100"),
                leverage=Decimal("1"),
            )
            for i in range(10)
        ]
        signal = Signal(
            symbol="NEWUSDT",
            direction=SignalDirection.LONG,
            confidence=0.8,
            strategy_name="test",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
        )
        decision = risk_manager.evaluate_signal(signal, Decimal("100000"), positions)
        assert decision.approved is False

    def test_exit_signal_always_approved(self, risk_manager: RiskManager) -> None:
        signal = Signal(
            symbol="BTCUSDT",
            direction=SignalDirection.CLOSE_LONG,
            confidence=0.5,
            strategy_name="test",
        )
        decision = risk_manager.evaluate_signal(signal, Decimal("100000"), [])
        assert decision.approved is True

    def test_circuit_breaker_blocks_after_losses(self, risk_manager: RiskManager) -> None:
        for _ in range(3):
            risk_manager.record_trade_result(is_win=False)

        signal = Signal(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            confidence=0.9,
            strategy_name="test",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
        )
        decision = risk_manager.evaluate_signal(signal, Decimal("100000"), [])
        assert decision.approved is False
        assert "circuit_breaker" in decision.reason

    def test_drawdown_halt_blocks_signals(self, risk_manager: RiskManager) -> None:
        risk_manager.update_equity(Decimal("84000"))

        signal = Signal(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            confidence=0.9,
            strategy_name="test",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
        )
        decision = risk_manager.evaluate_signal(signal, Decimal("84000"), [])
        assert decision.approved is False
        assert "drawdown_halt" in decision.reason


class TestMultiStrategySignals:
    def test_different_strategies_same_risk_pipeline(self, risk_manager: RiskManager) -> None:
        signals = [
            Signal(
                symbol="BTCUSDT",
                direction=SignalDirection.LONG,
                confidence=0.8,
                strategy_name="ema_crossover",
                entry_price=Decimal("50000"),
                stop_loss=Decimal("49000"),
            ),
            Signal(
                symbol="ETHUSDT",
                direction=SignalDirection.SHORT,
                confidence=0.7,
                strategy_name="mean_reversion",
                entry_price=Decimal("3000"),
                stop_loss=Decimal("3100"),
            ),
        ]
        for signal in signals:
            decision = risk_manager.evaluate_signal(signal, Decimal("100000"), [])
            assert decision.approved is True
            assert decision.quantity > Decimal("0")

    def test_win_loss_tracking_affects_circuit_breaker(self, risk_manager: RiskManager) -> None:
        risk_manager.record_trade_result(is_win=True)
        risk_manager.record_trade_result(is_win=False)
        risk_manager.record_trade_result(is_win=False)
        assert risk_manager.is_trading_allowed() is True

        risk_manager.record_trade_result(is_win=False)
        risk_manager.record_trade_result(is_win=False)
        assert risk_manager.is_trading_allowed() is False
