from decimal import Decimal

import structlog

from config.settings import RiskSettings
from exchange.models import Position
from risk.circuit_breaker import CircuitBreaker
from risk.drawdown_monitor import DrawdownMonitor
from risk.exposure_manager import ExposureCheck, ExposureManager
from risk.position_sizer import PositionSizer, SizingMethod
from risk.stop_loss import StopLossManager, StopLossType
from strategies.base_strategy import Signal, SignalDirection

logger = structlog.get_logger("risk_manager")


class RiskDecision:
    def __init__(
        self,
        approved: bool,
        quantity: Decimal = Decimal("0"),
        stop_loss: Decimal = Decimal("0"),
        take_profit: Decimal = Decimal("0"),
        reason: str = "",
    ) -> None:
        self.approved = approved
        self.quantity = quantity
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.reason = reason


class RiskManager:
    def __init__(self, risk_settings: RiskSettings) -> None:
        self._settings = risk_settings
        self.position_sizer = PositionSizer(risk_settings)
        self.stop_loss_manager = StopLossManager()
        self.drawdown_monitor = DrawdownMonitor(risk_settings)
        self.circuit_breaker = CircuitBreaker(risk_settings)
        self.exposure_manager = ExposureManager(risk_settings)

    def evaluate_signal(
        self,
        signal: Signal,
        equity: Decimal,
        positions: list[Position],
        sizing_method: SizingMethod = SizingMethod.FIXED_FRACTIONAL,
        **kwargs: Decimal,
    ) -> RiskDecision:
        if signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT):
            return RiskDecision(approved=True, reason="exit_signal")

        if signal.direction == SignalDirection.NEUTRAL:
            return RiskDecision(approved=False, reason="neutral_signal")

        if self.drawdown_monitor.is_halted:
            return RiskDecision(
                approved=False,
                reason=f"drawdown_halt: {self.drawdown_monitor.halt_reason}",
            )

        if not self.circuit_breaker.is_trading_allowed():
            return RiskDecision(approved=False, reason="circuit_breaker_active")

        if signal.stop_loss is None:
            return RiskDecision(approved=False, reason="no_stop_loss")

        entry_price = signal.entry_price or Decimal("0")
        stop_loss = signal.stop_loss
        take_profit = signal.take_profit or Decimal("0")

        if entry_price <= 0:
            return RiskDecision(approved=False, reason="invalid_entry_price")

        is_funding_arb = signal.strategy_name == "funding_rate_arb"
        new_size_estimate = equity * self._settings.max_risk_per_trade

        exposure_check = self.exposure_manager.check_new_position(
            positions, signal.symbol, new_size_estimate,
            Decimal("1"), equity, is_funding_arb,
        )
        if not exposure_check.allowed:
            return RiskDecision(approved=False, reason=exposure_check.reason)

        quantity = self.position_sizer.calculate_size(
            sizing_method, equity, entry_price, stop_loss, **kwargs,
        )

        if quantity <= 0:
            return RiskDecision(approved=False, reason="zero_quantity")

        return RiskDecision(
            approved=True,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def record_trade_result(self, is_win: bool) -> None:
        if is_win:
            self.circuit_breaker.record_win()
        else:
            self.circuit_breaker.record_loss()

    def update_equity(self, equity: Decimal) -> bool:
        return self.drawdown_monitor.update_equity(equity)

    def initialize(self, equity: Decimal) -> None:
        self.drawdown_monitor.initialize(equity)

    def is_trading_allowed(self) -> bool:
        if self.drawdown_monitor.is_halted:
            return False
        if not self.circuit_breaker.is_trading_allowed():
            return False
        return True
