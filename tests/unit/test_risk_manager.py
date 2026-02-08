from decimal import Decimal
from unittest.mock import patch

import pytest

from config.settings import RiskSettings
from data.models import PositionSide
from exchange.models import Position
from risk.position_sizer import SizingMethod
from risk.risk_manager import RiskDecision, RiskManager
from strategies.base_strategy import Signal, SignalDirection


def _make_signal(
    direction: SignalDirection = SignalDirection.LONG,
    entry: Decimal = Decimal("100"),
    stop: Decimal = Decimal("95"),
    tp: Decimal = Decimal("110"),
    strategy: str = "test_strategy",
) -> Signal:
    return Signal(
        symbol="BTCUSDT",
        direction=direction,
        confidence=0.8,
        strategy_name=strategy,
        entry_price=entry,
        stop_loss=stop,
        take_profit=tp,
    )


def _make_position(
    symbol: str = "BTCUSDT",
    size: Decimal = Decimal("0.1"),
    entry: Decimal = Decimal("50000"),
) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        size=size,
        entry_price=entry,
    )


@pytest.fixture
def settings() -> RiskSettings:
    return RiskSettings(
        max_risk_per_trade=Decimal("0.02"),
        max_portfolio_risk=Decimal("0.10"),
        max_drawdown_pct=Decimal("0.15"),
        max_daily_loss_pct=Decimal("0.05"),
        max_leverage=Decimal("3.0"),
        max_concurrent_positions=10,
        circuit_breaker_consecutive_losses=3,
        circuit_breaker_cooldown_hours=4,
        funding_arb_max_allocation=Decimal("0.30"),
    )


@pytest.fixture
def rm(settings: RiskSettings) -> RiskManager:
    mgr = RiskManager(settings)
    mgr.initialize(Decimal("10000"))
    return mgr


class TestExitSignals:
    def test_close_long_always_approved(self, rm: RiskManager) -> None:
        signal = _make_signal(SignalDirection.CLOSE_LONG)
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is True
        assert decision.reason == "exit_signal"

    def test_close_short_always_approved(self, rm: RiskManager) -> None:
        signal = _make_signal(SignalDirection.CLOSE_SHORT)
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is True
        assert decision.reason == "exit_signal"


class TestNeutralSignal:
    def test_neutral_rejected(self, rm: RiskManager) -> None:
        signal = _make_signal(SignalDirection.NEUTRAL)
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is False
        assert decision.reason == "neutral_signal"


class TestDrawdownHalt:
    def test_rejected_when_drawdown_halted(self, rm: RiskManager) -> None:
        rm.update_equity(Decimal("8000"))
        signal = _make_signal()
        decision = rm.evaluate_signal(signal, Decimal("8000"), [])
        assert decision.approved is False
        assert "drawdown_halt" in decision.reason


class TestCircuitBreaker:
    def test_rejected_after_consecutive_losses(self, rm: RiskManager) -> None:
        rm.record_trade_result(False)
        rm.record_trade_result(False)
        rm.record_trade_result(False)
        signal = _make_signal()
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is False
        assert decision.reason == "circuit_breaker_active"


class TestStopLossRequired:
    def test_rejected_without_stop_loss(self, rm: RiskManager) -> None:
        signal = Signal(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            confidence=0.8,
            strategy_name="test",
            entry_price=Decimal("100"),
            stop_loss=None,
            take_profit=Decimal("110"),
        )
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is False
        assert decision.reason == "no_stop_loss"


class TestEntryPriceValidation:
    def test_rejected_zero_entry(self, rm: RiskManager) -> None:
        signal = _make_signal(entry=Decimal("0"))
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is False
        assert decision.reason == "invalid_entry_price"

    def test_rejected_negative_entry(self, rm: RiskManager) -> None:
        signal = _make_signal(entry=Decimal("-50"))
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is False
        assert decision.reason == "invalid_entry_price"


class TestExposureCheck:
    def test_rejected_at_max_positions(self, rm: RiskManager) -> None:
        positions = [_make_position(f"SYM{i}") for i in range(10)]
        signal = _make_signal()
        decision = rm.evaluate_signal(signal, Decimal("10000"), positions)
        assert decision.approved is False
        assert "max_positions" in decision.reason


class TestApprovedTrade:
    def test_approved_with_quantity(self, rm: RiskManager) -> None:
        signal = _make_signal()
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is True
        assert decision.quantity > Decimal("0")
        assert decision.stop_loss == Decimal("95")
        assert decision.take_profit == Decimal("110")

    def test_quantity_matches_sizer(self, rm: RiskManager) -> None:
        signal = _make_signal()
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        expected = rm.position_sizer.fixed_fractional(
            Decimal("10000"), Decimal("100"), Decimal("95"),
        )
        assert decision.quantity == expected

    def test_short_signal_approved(self, rm: RiskManager) -> None:
        signal = _make_signal(
            direction=SignalDirection.SHORT,
            entry=Decimal("100"),
            stop=Decimal("105"),
            tp=Decimal("90"),
        )
        decision = rm.evaluate_signal(signal, Decimal("10000"), [])
        assert decision.approved is True
        assert decision.quantity > Decimal("0")


class TestRecordTradeResult:
    def test_win_keeps_trading(self, rm: RiskManager) -> None:
        rm.record_trade_result(True)
        assert rm.is_trading_allowed() is True

    def test_loss_streak_disables(self, rm: RiskManager) -> None:
        rm.record_trade_result(False)
        rm.record_trade_result(False)
        rm.record_trade_result(False)
        assert rm.is_trading_allowed() is False


class TestUpdateEquity:
    def test_update_returns_true_ok(self, rm: RiskManager) -> None:
        assert rm.update_equity(Decimal("9800")) is True

    def test_update_returns_false_halted(self, rm: RiskManager) -> None:
        assert rm.update_equity(Decimal("8000")) is False


class TestIsTradingAllowed:
    def test_allowed_initially(self, rm: RiskManager) -> None:
        assert rm.is_trading_allowed() is True

    def test_not_allowed_drawdown(self, rm: RiskManager) -> None:
        rm.update_equity(Decimal("8000"))
        assert rm.is_trading_allowed() is False

    def test_not_allowed_circuit_breaker(self, rm: RiskManager) -> None:
        for _ in range(3):
            rm.record_trade_result(False)
        assert rm.is_trading_allowed() is False


class TestRiskDecision:
    def test_defaults(self) -> None:
        rd = RiskDecision(approved=False, reason="test")
        assert rd.quantity == Decimal("0")
        assert rd.stop_loss == Decimal("0")
        assert rd.take_profit == Decimal("0")

    def test_with_values(self) -> None:
        rd = RiskDecision(
            approved=True,
            quantity=Decimal("10"),
            stop_loss=Decimal("95"),
            take_profit=Decimal("110"),
        )
        assert rd.approved is True
        assert rd.quantity == Decimal("10")


class TestFundingArbSpecialHandling:
    def test_funding_arb_bypasses_position_count(self, rm: RiskManager) -> None:
        positions = [_make_position(f"SYM{i}") for i in range(10)]
        signal = _make_signal(strategy="funding_rate_arb")
        decision = rm.evaluate_signal(signal, Decimal("100000"), positions)
        assert "max_positions" not in decision.reason
