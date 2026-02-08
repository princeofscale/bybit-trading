from decimal import Decimal

import pytest

from monitoring.alerts import Alert, AlertManager, AlertSeverity
from monitoring.dashboard import (
    DashboardService,
    DashboardState,
    OrderSnapshot,
    PnLSnapshot,
    PositionSnapshot,
)
from monitoring.health_check import ComponentStatus, HealthChecker
from monitoring.metrics import MetricsRegistry


@pytest.fixture
def service() -> DashboardService:
    return DashboardService(
        metrics_registry=MetricsRegistry(),
        health_checker=HealthChecker(),
        alert_manager=AlertManager(),
    )


class TestDashboardState:
    def test_initial_state(self, service: DashboardService) -> None:
        state = service.get_state()
        assert state.bot_state == "unknown"
        assert state.pnl.total_equity == Decimal("0")
        assert len(state.positions) == 0
        assert len(state.open_orders) == 0

    def test_update_pnl(self, service: DashboardService) -> None:
        pnl = PnLSnapshot(
            total_equity=Decimal("50000"),
            unrealized_pnl=Decimal("150"),
            realized_pnl_today=Decimal("300"),
            total_trades=25,
            win_rate=Decimal("0.56"),
        )
        service.update_pnl(pnl)
        state = service.get_state()
        assert state.pnl.total_equity == Decimal("50000")
        assert state.pnl.unrealized_pnl == Decimal("150")
        assert state.pnl.total_trades == 25

    def test_update_positions(self, service: DashboardService) -> None:
        positions = [
            PositionSnapshot(
                symbol="BTCUSDT",
                side="long",
                size=Decimal("0.5"),
                entry_price=Decimal("50000"),
                unrealized_pnl=Decimal("250"),
                leverage=Decimal("2"),
            ),
            PositionSnapshot(
                symbol="ETHUSDT",
                side="short",
                size=Decimal("10"),
                entry_price=Decimal("3000"),
                unrealized_pnl=Decimal("-50"),
            ),
        ]
        service.update_positions(positions)
        state = service.get_state()
        assert len(state.positions) == 2
        assert state.positions[0].symbol == "BTCUSDT"
        assert service.position_count == 2

    def test_update_orders(self, service: DashboardService) -> None:
        orders = [
            OrderSnapshot(
                order_id="o1",
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                price=Decimal("49000"),
                quantity=Decimal("0.1"),
                status="open",
            ),
        ]
        service.update_orders(orders)
        state = service.get_state()
        assert len(state.open_orders) == 1
        assert service.open_order_count == 1

    def test_update_bot_state(self, service: DashboardService) -> None:
        service.update_bot_state("running")
        state = service.get_state()
        assert state.bot_state == "running"

    def test_update_active_strategies(self, service: DashboardService) -> None:
        service.update_active_strategies(["trend", "mean_reversion"])
        state = service.get_state()
        assert state.active_strategies == ["trend", "mean_reversion"]


class TestMetricsSummary:
    def test_includes_counters(self, service: DashboardService) -> None:
        service._metrics.counter("orders_placed").increment(Decimal("10"))
        summary = service.get_metrics_summary()
        assert summary["counters"]["orders_placed"] == Decimal("10")

    def test_includes_gauges(self, service: DashboardService) -> None:
        service._metrics.gauge("equity").set(Decimal("50000"))
        summary = service.get_metrics_summary()
        assert summary["gauges"]["equity"] == Decimal("50000")

    def test_includes_histograms(self, service: DashboardService) -> None:
        h = service._metrics.histogram("latency")
        h.observe(Decimal("10"))
        h.observe(Decimal("20"))
        summary = service.get_metrics_summary()
        assert summary["histograms"]["latency"]["count"] == 2
        assert summary["histograms"]["latency"]["mean"] == Decimal("15")

    def test_empty_summary(self, service: DashboardService) -> None:
        summary = service.get_metrics_summary()
        assert summary["counters"] == {}
        assert summary["gauges"] == {}
        assert summary["histograms"] == {}


class TestHealthInDashboard:
    def test_includes_health(self, service: DashboardService) -> None:
        service._health.update_status("exchange", ComponentStatus.HEALTHY)
        state = service.get_state()
        assert state.health is not None
        assert state.health.overall == ComponentStatus.HEALTHY

    def test_unhealthy_reflected(self, service: DashboardService) -> None:
        service._health.update_status("db", ComponentStatus.UNHEALTHY)
        state = service.get_state()
        assert state.health.overall == ComponentStatus.UNHEALTHY


class TestRecentAlerts:
    def test_returns_recent(self, service: DashboardService) -> None:
        for i in range(5):
            service._alerts.fire_alert(
                Alert(
                    severity=AlertSeverity.WARNING,
                    title=f"Alert {i}",
                    message="test",
                )
            )
        recent = service.get_recent_alerts(3)
        assert len(recent) == 3
        assert recent[0]["title"] == "Alert 2"

    def test_empty_alerts(self, service: DashboardService) -> None:
        recent = service.get_recent_alerts()
        assert len(recent) == 0

    def test_alert_format(self, service: DashboardService) -> None:
        service._alerts.fire_alert(
            Alert(
                severity=AlertSeverity.CRITICAL,
                title="DD Limit",
                message="Max drawdown hit",
            )
        )
        recent = service.get_recent_alerts(1)
        assert recent[0]["severity"] == "critical"
        assert recent[0]["title"] == "DD Limit"
        assert "timestamp" in recent[0]
