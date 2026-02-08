from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from monitoring.alerts import AlertManager
from monitoring.health_check import HealthChecker, SystemHealth
from monitoring.metrics import MetricsRegistry
from utils.time_utils import utc_now_ms


class PositionSnapshot(BaseModel):
    symbol: str
    side: str
    size: Decimal
    entry_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    leverage: Decimal = Decimal("1")


class OrderSnapshot(BaseModel):
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: Decimal
    quantity: Decimal
    status: str


class PnLSnapshot(BaseModel):
    total_equity: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl_today: Decimal = Decimal("0")
    total_realized_pnl: Decimal = Decimal("0")
    win_rate: Decimal = Decimal("0")
    total_trades: int = 0
    timestamp: int = Field(default_factory=utc_now_ms)


class DashboardState(BaseModel):
    pnl: PnLSnapshot = Field(default_factory=PnLSnapshot)
    positions: list[PositionSnapshot] = Field(default_factory=list)
    open_orders: list[OrderSnapshot] = Field(default_factory=list)
    health: SystemHealth | None = None
    bot_state: str = "unknown"
    active_strategies: list[str] = Field(default_factory=list)
    timestamp: int = Field(default_factory=utc_now_ms)


class DashboardService:
    def __init__(
        self,
        metrics_registry: MetricsRegistry,
        health_checker: HealthChecker,
        alert_manager: AlertManager,
    ) -> None:
        self._metrics = metrics_registry
        self._health = health_checker
        self._alerts = alert_manager
        self._positions: list[PositionSnapshot] = []
        self._orders: list[OrderSnapshot] = []
        self._pnl = PnLSnapshot()
        self._bot_state = "unknown"
        self._active_strategies: list[str] = []

    def update_pnl(self, pnl: PnLSnapshot) -> None:
        self._pnl = pnl

    def update_positions(self, positions: list[PositionSnapshot]) -> None:
        self._positions = positions

    def update_orders(self, orders: list[OrderSnapshot]) -> None:
        self._orders = orders

    def update_bot_state(self, state: str) -> None:
        self._bot_state = state

    def update_active_strategies(self, strategies: list[str]) -> None:
        self._active_strategies = strategies

    def get_state(self) -> DashboardState:
        return DashboardState(
            pnl=self._pnl,
            positions=list(self._positions),
            open_orders=list(self._orders),
            health=self._health.get_system_health(),
            bot_state=self._bot_state,
            active_strategies=list(self._active_strategies),
        )

    def get_metrics_summary(self) -> dict[str, Any]:
        return {
            "counters": {
                name: self._metrics.counter(name).value
                for name in self._metrics.counter_names
            },
            "gauges": {
                name: self._metrics.gauge(name).value
                for name in self._metrics.gauge_names
            },
            "histograms": {
                name: {
                    "count": self._metrics.histogram(name).count,
                    "mean": self._metrics.histogram(name).mean,
                    "p95": self._metrics.histogram(name).p95,
                }
                for name in self._metrics.histogram_names
            },
        }

    def get_recent_alerts(self, count: int = 20) -> list[dict[str, Any]]:
        alerts = self._alerts.recent_alerts(count)
        return [
            {
                "severity": a.severity.value,
                "title": a.title,
                "message": a.message,
                "timestamp": a.timestamp,
            }
            for a in alerts
        ]

    @property
    def position_count(self) -> int:
        return len(self._positions)

    @property
    def open_order_count(self) -> int:
        return len(self._orders)
