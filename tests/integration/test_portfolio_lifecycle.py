from decimal import Decimal

import pytest

from config.settings import RiskSettings
from monitoring.alerts import Alert, AlertManager, AlertSeverity
from monitoring.health_check import ComponentStatus, HealthChecker
from monitoring.metrics import MetricsRegistry
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager
from strategies.base_strategy import Signal, SignalDirection


@pytest.fixture
def risk_manager() -> RiskManager:
    rm = RiskManager(RiskSettings())
    rm.initialize(Decimal("100000"))
    return rm


@pytest.fixture
def portfolio() -> PortfolioManager:
    return PortfolioManager(
        strategy_names=["ema_crossover", "mean_reversion", "trend_following"],
        total_equity=Decimal("100000"),
    )


@pytest.fixture
def metrics() -> MetricsRegistry:
    return MetricsRegistry()


@pytest.fixture
def health() -> HealthChecker:
    return HealthChecker()


@pytest.fixture
def alerts() -> AlertManager:
    return AlertManager()


class TestStrategyLifecycle:
    def test_portfolio_tracks_strategy_pnl(self, portfolio: PortfolioManager) -> None:
        portfolio.record_trade("ema_crossover", Decimal("0.05"))
        portfolio.record_trade("ema_crossover", Decimal("-0.02"))
        portfolio.record_trade("mean_reversion", Decimal("0.03"))

        summary = portfolio.get_performance_summary()
        assert summary["ema_crossover"]["total_trades"] == Decimal("2")
        assert summary["mean_reversion"]["total_trades"] == Decimal("1")

    def test_equity_update_changes_budgets(self, portfolio: PortfolioManager) -> None:
        budget_before = portfolio.get_strategy_budget("ema_crossover")
        portfolio.update_equity(Decimal("150000"))
        budget_after = portfolio.get_strategy_budget("ema_crossover")
        assert budget_after > budget_before

    def test_rebalance_after_performance_divergence(self, portfolio: PortfolioManager) -> None:
        for _ in range(10):
            portfolio.record_trade("ema_crossover", Decimal("0.05"))
            portfolio.record_trade("mean_reversion", Decimal("-0.02"))
            portfolio.record_trade("trend_following", Decimal("0.01"))

        target = portfolio.calculate_target_allocation("performance")
        assert target.get("ema_crossover") > target.get("mean_reversion")

    def test_add_and_remove_strategy(self, portfolio: PortfolioManager) -> None:
        portfolio.add_strategy("grid_trading")
        assert "grid_trading" in portfolio.strategy_names
        assert portfolio.get_strategy_budget("grid_trading") == Decimal("0")

        portfolio.remove_strategy("grid_trading")
        assert "grid_trading" not in portfolio.strategy_names

        allocs = portfolio.current_allocations
        total = sum(allocs.values())
        assert abs(total - Decimal("1")) < Decimal("0.001")


class TestRiskAndPortfolioIntegration:
    def test_risk_loss_updates_portfolio(
        self, risk_manager: RiskManager, portfolio: PortfolioManager,
    ) -> None:
        risk_manager.record_trade_result(is_win=False)
        portfolio.record_trade("ema_crossover", Decimal("-0.02"))
        portfolio.update_equity(Decimal("98000"))

        assert portfolio.total_equity == Decimal("98000")
        summary = portfolio.get_performance_summary()
        assert summary["ema_crossover"]["total_trades"] == Decimal("1")

    def test_drawdown_halt_and_portfolio_state(
        self, risk_manager: RiskManager, portfolio: PortfolioManager,
    ) -> None:
        risk_manager.update_equity(Decimal("84000"))
        assert risk_manager.is_trading_allowed() is False

        portfolio.update_equity(Decimal("84000"))
        assert portfolio.total_equity == Decimal("84000")


class TestMonitoringIntegration:
    def test_metrics_track_trade_flow(self, metrics: MetricsRegistry) -> None:
        orders_counter = metrics.counter("orders_placed")
        fills_counter = metrics.counter("orders_filled")
        pnl_gauge = metrics.gauge("total_pnl")
        latency = metrics.histogram("order_latency_ms")

        orders_counter.increment()
        orders_counter.increment()
        fills_counter.increment()
        pnl_gauge.set(Decimal("1500.50"))
        latency.observe(Decimal("15.3"))
        latency.observe(Decimal("22.1"))

        points = metrics.get_all_points()
        assert len(points) == 3
        assert orders_counter.value == Decimal("2")
        assert fills_counter.value == Decimal("1")
        assert latency.mean > Decimal("0")

    def test_health_check_reflects_system_state(self, health: HealthChecker) -> None:
        health.update_status("exchange_rest", ComponentStatus.HEALTHY)
        health.update_status("exchange_ws", ComponentStatus.HEALTHY)
        health.update_status("database", ComponentStatus.HEALTHY)
        health.update_status("redis", ComponentStatus.HEALTHY)
        assert health.is_healthy() is True

        health.update_status("exchange_ws", ComponentStatus.UNHEALTHY, "Connection lost")
        assert health.is_healthy() is False
        assert "exchange_ws" in health.unhealthy_components()

    def test_alerts_fire_on_risk_events(self, alerts: AlertManager) -> None:
        from monitoring.alerts import AlertChannel, AlertRule

        alerts.add_rule(AlertRule(
            name="drawdown_alert",
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.LOG],
            cooldown_ms=1000,
        ))

        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            title="Max Drawdown Hit",
            message="Portfolio drawdown exceeded 15%",
            source="risk_manager",
        )
        fired = alerts.fire_alert(alert, rule_name="drawdown_alert")
        assert fired is True
        assert len(alerts.history) == 1
        assert alerts.history[0].severity == AlertSeverity.CRITICAL


class TestFullTradeLifecycle:
    def test_signal_risk_portfolio_monitoring_flow(
        self,
        risk_manager: RiskManager,
        portfolio: PortfolioManager,
        metrics: MetricsRegistry,
        alerts: AlertManager,
    ) -> None:
        signal = Signal(
            symbol="BTCUSDT",
            direction=SignalDirection.LONG,
            confidence=0.8,
            strategy_name="ema_crossover",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"),
        )

        decision = risk_manager.evaluate_signal(signal, Decimal("100000"), [])
        assert decision.approved is True

        metrics.counter("signals_generated").increment()
        metrics.counter("signals_approved").increment()

        portfolio.record_trade("ema_crossover", Decimal("0.04"))
        risk_manager.record_trade_result(is_win=True)
        metrics.counter("trades_won").increment()

        portfolio.update_equity(Decimal("104000"))
        risk_manager.update_equity(Decimal("104000"))

        assert portfolio.total_equity == Decimal("104000")
        assert risk_manager.is_trading_allowed() is True
        assert metrics.counter("trades_won").value == Decimal("1")

        summary = portfolio.get_performance_summary()
        assert summary["ema_crossover"]["total_trades"] == Decimal("1")
