from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class DummyStrategy(BaseStrategy):
    def __init__(self, symbols: list[str], signal: Signal | None = None) -> None:
        super().__init__("dummy", symbols)
        self._signal = signal

    def min_candles_required(self) -> int:
        return 10

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        return self._signal


def _make_df(n: int = 50) -> pd.DataFrame:
    np.random.seed(42)
    close = np.cumsum(np.random.randn(n)) + 100
    return pd.DataFrame({
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": np.random.randint(100, 1000, n).astype(float),
    })


def test_initial_state() -> None:
    strat = DummyStrategy(["BTC/USDT:USDT"])
    assert strat.get_state("BTC/USDT:USDT") == StrategyState.IDLE
    assert strat.name == "dummy"
    assert strat.enabled is True


def test_enable_disable() -> None:
    strat = DummyStrategy(["BTC/USDT:USDT"])
    strat.disable()
    assert strat.enabled is False
    strat.enable()
    assert strat.enabled is True


def test_set_state() -> None:
    strat = DummyStrategy(["BTC/USDT:USDT"])
    strat.set_state("BTC/USDT:USDT", StrategyState.LONG)
    assert strat.get_state("BTC/USDT:USDT") == StrategyState.LONG


def test_should_enter_long_when_idle() -> None:
    signal = Signal(
        symbol="BTC/USDT:USDT", direction=SignalDirection.LONG,
        confidence=0.8, strategy_name="dummy",
    )
    strat = DummyStrategy(["BTC/USDT:USDT"], signal=signal)
    result = strat.should_enter_long("BTC/USDT:USDT", _make_df())
    assert result is not None
    assert result.direction == SignalDirection.LONG


def test_should_not_enter_long_when_in_position() -> None:
    signal = Signal(
        symbol="BTC/USDT:USDT", direction=SignalDirection.LONG,
        confidence=0.8, strategy_name="dummy",
    )
    strat = DummyStrategy(["BTC/USDT:USDT"], signal=signal)
    strat.set_state("BTC/USDT:USDT", StrategyState.LONG)
    result = strat.should_enter_long("BTC/USDT:USDT", _make_df())
    assert result is None


def test_should_enter_short_when_idle() -> None:
    signal = Signal(
        symbol="BTC/USDT:USDT", direction=SignalDirection.SHORT,
        confidence=0.8, strategy_name="dummy",
    )
    strat = DummyStrategy(["BTC/USDT:USDT"], signal=signal)
    result = strat.should_enter_short("BTC/USDT:USDT", _make_df())
    assert result is not None


def test_should_exit_long() -> None:
    signal = Signal(
        symbol="BTC/USDT:USDT", direction=SignalDirection.CLOSE_LONG,
        confidence=0.7, strategy_name="dummy",
    )
    strat = DummyStrategy(["BTC/USDT:USDT"], signal=signal)
    strat.set_state("BTC/USDT:USDT", StrategyState.LONG)
    result = strat.should_exit("BTC/USDT:USDT", _make_df())
    assert result is not None
    assert result.direction == SignalDirection.CLOSE_LONG


def test_should_not_exit_when_idle() -> None:
    signal = Signal(
        symbol="BTC/USDT:USDT", direction=SignalDirection.CLOSE_LONG,
        confidence=0.7, strategy_name="dummy",
    )
    strat = DummyStrategy(["BTC/USDT:USDT"], signal=signal)
    result = strat.should_exit("BTC/USDT:USDT", _make_df())
    assert result is None


def test_signal_model_validation() -> None:
    signal = Signal(
        symbol="BTC/USDT:USDT", direction=SignalDirection.LONG,
        confidence=0.85, strategy_name="test",
        entry_price=Decimal("30000"),
        stop_loss=Decimal("29500"),
        take_profit=Decimal("31000"),
        metadata={"rsi": 45.0},
    )
    assert signal.confidence == 0.85
    assert signal.entry_price == Decimal("30000")


def test_signal_confidence_bounds() -> None:
    with pytest.raises(Exception):
        Signal(
            symbol="BTC/USDT:USDT", direction=SignalDirection.LONG,
            confidence=1.5, strategy_name="test",
        )


def test_symbols_list() -> None:
    strat = DummyStrategy(["BTC/USDT:USDT", "ETH/USDT:USDT"])
    assert len(strat.symbols) == 2
    assert "BTC/USDT:USDT" in strat.symbols
