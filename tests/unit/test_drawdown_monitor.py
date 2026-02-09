from decimal import Decimal

import pytest

from config.settings import RiskSettings
from risk.drawdown_monitor import DrawdownMonitor


@pytest.fixture
def settings() -> RiskSettings:
    return RiskSettings(
        max_drawdown_pct=Decimal("0.15"),
        max_daily_loss_pct=Decimal("0.05"),
    )


@pytest.fixture
def monitor(settings: RiskSettings) -> DrawdownMonitor:
    mon = DrawdownMonitor(settings)
    mon.initialize(Decimal("10000"))
    return mon


class TestInitialize:
    def test_sets_peak_equity(self, monitor: DrawdownMonitor) -> None:
        assert monitor.peak_equity == Decimal("10000")

    def test_drawdown_is_zero(self, monitor: DrawdownMonitor) -> None:
        assert monitor.current_drawdown_pct == Decimal("0")

    def test_daily_pnl_is_zero(self, monitor: DrawdownMonitor) -> None:
        assert monitor.daily_pnl_pct == Decimal("0")

    def test_not_halted(self, monitor: DrawdownMonitor) -> None:
        assert not monitor.is_halted


class TestUpdateEquity:
    def test_equity_increase_updates_peak(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("11000"))
        assert monitor.peak_equity == Decimal("11000")

    def test_equity_decrease_no_peak_change(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("9500"))
        assert monitor.peak_equity == Decimal("10000")

    def test_drawdown_calculation(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("9000"))
        assert monitor.current_drawdown_pct == Decimal("0.1")

    def test_returns_true_when_ok(self, monitor: DrawdownMonitor) -> None:
        result = monitor.update_equity(Decimal("9600"))
        assert result is True

    def test_daily_pnl_tracks_change(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("10500"))
        assert monitor.daily_pnl_pct == Decimal("0.05")


class TestMaxDrawdownHalt:
    def test_halts_at_15pct_drawdown(self, monitor: DrawdownMonitor) -> None:
        result = monitor.update_equity(Decimal("8500"))
        assert result is False
        assert monitor.is_halted is True
        assert "max_drawdown_breached" in monitor.halt_reason

    def test_exactly_at_threshold(self, monitor: DrawdownMonitor) -> None:
        result = monitor.update_equity(Decimal("8500"))
        assert result is False
        assert monitor.is_halted is True

    def test_just_above_drawdown_threshold_but_daily_triggers(
        self, monitor: DrawdownMonitor,
    ) -> None:
        result = monitor.update_equity(Decimal("8501"))
        assert result is False
        assert "daily_loss" in monitor.halt_reason

    def test_under_both_thresholds_ok(self, monitor: DrawdownMonitor) -> None:
        result = monitor.update_equity(Decimal("9600"))
        assert result is True
        assert monitor.is_halted is False

    def test_halts_after_peak_increases(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("12000"))
        result = monitor.update_equity(Decimal("10200"))
        assert result is False
        assert monitor.is_halted is True


class TestDailyLossHalt:
    def test_halts_at_5pct_daily_loss(self, monitor: DrawdownMonitor) -> None:
        result = monitor.update_equity(Decimal("9500"))
        assert result is False
        assert monitor.is_halted is True
        assert "daily_loss_breached" in monitor.halt_reason

    def test_just_under_threshold_ok(self, monitor: DrawdownMonitor) -> None:
        result = monitor.update_equity(Decimal("9501"))
        assert result is True
        assert monitor.is_halted is False

    def test_soft_stop_before_daily_hard_limit(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("9600"))
        assert monitor.is_halted is False
        assert monitor.is_soft_stopped is True
        assert "soft_daily_loss" in monitor.soft_stop_reason


class TestResets:
    def test_reset_daily_clears_daily_halt(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("9500"))
        assert monitor.is_halted is True
        assert "daily" in monitor.halt_reason
        monitor.reset_daily()
        assert monitor.is_halted is False

    def test_reset_daily_does_not_clear_max_drawdown_halt(
        self, monitor: DrawdownMonitor,
    ) -> None:
        monitor.update_equity(Decimal("8400"))
        assert monitor.is_halted is True
        assert "max_drawdown" in monitor.halt_reason
        monitor.reset_daily()
        assert monitor.is_halted is True

    def test_resume_trading_clears_any_halt(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("8400"))
        assert monitor.is_halted is True
        monitor.resume_trading()
        assert monitor.is_halted is False
        assert monitor.halt_reason == ""

    def test_reset_daily_updates_baseline(self, monitor: DrawdownMonitor) -> None:
        monitor.update_equity(Decimal("9600"))
        monitor.reset_daily()
        monitor.update_equity(Decimal("9200"))
        assert monitor.daily_pnl_pct < Decimal("0")
        pct = (Decimal("9200") - Decimal("9600")) / Decimal("9600")
        assert monitor.daily_pnl_pct == pct


class TestEdgeCases:
    def test_zero_peak_drawdown_is_zero(self, settings: RiskSettings) -> None:
        mon = DrawdownMonitor(settings)
        assert mon.current_drawdown_pct == Decimal("0")

    def test_zero_daily_start_pnl_is_zero(self, settings: RiskSettings) -> None:
        mon = DrawdownMonitor(settings)
        assert mon.daily_pnl_pct == Decimal("0")

    def test_daily_limit_can_be_disabled(self, settings: RiskSettings) -> None:
        mon = DrawdownMonitor(settings.model_copy(update={"enable_daily_loss_limit": False}))
        mon.initialize(Decimal("10000"))
        result = mon.update_equity(Decimal("9000"))
        assert result is True
        assert mon.is_halted is False
