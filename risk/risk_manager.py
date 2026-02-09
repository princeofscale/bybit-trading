from decimal import Decimal
from collections import deque

import structlog

from config.settings import RiskSettings
from data.models import PositionSide
from exchange.models import Position
from risk.circuit_breaker import CircuitBreaker
from risk.drawdown_monitor import DrawdownMonitor
from risk.exposure_manager import ExposureCheck, ExposureManager
from risk.position_sizer import PositionSizer, SizingMethod
from risk.stop_loss import StopLossManager, StopLossType
from strategies.base_strategy import Signal, SignalDirection
from utils.time_utils import utc_now_ms

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
        self._symbol_cooldowns: dict[str, int] = {}
        self._entry_side_history: deque[str] = deque(maxlen=50)

    def evaluate_signal(
        self,
        signal: Signal,
        equity: Decimal,
        positions: list[Position],
        sizing_method: SizingMethod = SizingMethod.FIXED_FRACTIONAL,
        **kwargs: Decimal,
    ) -> RiskDecision:
        if signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT):
            target_side = (
                PositionSide.LONG
                if signal.direction == SignalDirection.CLOSE_LONG
                else PositionSide.SHORT
            )
            for pos in positions:
                if pos.symbol == signal.symbol and pos.side == target_side and pos.size > 0:
                    return RiskDecision(
                        approved=True,
                        quantity=pos.size,
                        reason="exit_signal",
                    )
            return RiskDecision(approved=False, reason="no_position_to_close")

        if signal.direction == SignalDirection.NEUTRAL:
            return RiskDecision(approved=False, reason="neutral_signal")

        if self.drawdown_monitor.is_halted:
            return RiskDecision(
                approved=False,
                reason=f"drawdown_halt: {self.drawdown_monitor.halt_reason}",
            )

        if not self.circuit_breaker.is_trading_allowed():
            return RiskDecision(approved=False, reason="circuit_breaker_active")

        if self._is_symbol_on_cooldown(signal.symbol):
            return RiskDecision(approved=False, reason="symbol_cooldown_active")

        if signal.stop_loss is None:
            return RiskDecision(approved=False, reason="no_stop_loss")

        spread_bps = signal.metadata.get("spread_bps")
        if spread_bps is not None and Decimal(str(spread_bps)) > self._settings.max_spread_bps:
            return RiskDecision(
                approved=False,
                reason=f"spread_too_wide: {spread_bps:.2f}bps > {self._settings.max_spread_bps}",
            )
        liquidity_score = signal.metadata.get("liquidity_score")
        if liquidity_score is not None and liquidity_score < self._settings.min_liquidity_score:
            return RiskDecision(
                approved=False,
                reason=f"low_liquidity: {liquidity_score:.2f} < {self._settings.min_liquidity_score:.2f}",
            )

        entry_price = signal.entry_price or Decimal("0")
        stop_loss = signal.stop_loss
        take_profit = signal.take_profit or Decimal("0")

        if entry_price <= 0:
            return RiskDecision(approved=False, reason="invalid_entry_price")

        is_funding_arb = signal.strategy_name == "funding_rate_arb"

        if self.drawdown_monitor.is_soft_stopped:
            min_conf = self._settings.soft_stop_min_confidence
            if signal.confidence < min_conf:
                return RiskDecision(
                    approved=False,
                    reason=f"soft_stop_low_confidence: {signal.confidence:.2f} < {min_conf:.2f}",
                )

        quantity = self.position_sizer.calculate_size(
            sizing_method, equity, entry_price, stop_loss, **kwargs,
        )

        if quantity <= 0:
            return RiskDecision(approved=False, reason="zero_quantity")

        new_size_estimate = equity * self._settings.max_risk_per_trade

        exposure_check = self.exposure_manager.check_new_position(
            positions, signal.symbol, new_size_estimate,
            Decimal("1"), equity, is_funding_arb,
        )
        if not exposure_check.allowed:
            return RiskDecision(approved=False, reason=exposure_check.reason)

        direction_side = PositionSide.LONG if signal.direction == SignalDirection.LONG else PositionSide.SHORT
        directional_check = self.exposure_manager.check_directional_exposure(
            positions, direction_side, new_size_estimate, equity,
        )
        if not directional_check.allowed:
            return RiskDecision(approved=False, reason=directional_check.reason)

        side_balance_check = self._check_side_balancer(positions, direction_side, equity)
        if not side_balance_check.allowed:
            return RiskDecision(approved=False, reason=side_balance_check.reason)

        if self._is_portfolio_heat_exceeded(positions, equity):
            return RiskDecision(approved=False, reason="portfolio_heat_limit")

        return RiskDecision(
            approved=True,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def record_trade_result(self, is_win: bool, symbol: str = "") -> None:
        if is_win:
            self.circuit_breaker.record_win()
            if symbol:
                self._symbol_cooldowns.pop(symbol, None)
        else:
            self.circuit_breaker.record_loss()
            if symbol and self._settings.enable_symbol_cooldown:
                ttl_ms = self._settings.symbol_cooldown_minutes * 60_000
                self._symbol_cooldowns[symbol] = utc_now_ms() + ttl_ms

    def record_entry_direction(self, direction: SignalDirection) -> None:
        if direction == SignalDirection.LONG:
            self._entry_side_history.append("long")
        elif direction == SignalDirection.SHORT:
            self._entry_side_history.append("short")

    def current_side_streak(self) -> tuple[str, int]:
        if not self._entry_side_history:
            return "", 0
        last = self._entry_side_history[-1]
        streak = 0
        for side in reversed(self._entry_side_history):
            if side != last:
                break
            streak += 1
        return last, streak

    def side_balancer_snapshot(self, positions: list[Position], equity: Decimal) -> dict[str, Decimal | int | str]:
        long_exposure, short_exposure = self.exposure_manager.directional_exposure_usd(positions)
        side, streak = self.current_side_streak()
        imbalance_abs = abs(long_exposure - short_exposure)
        imbalance_pct = (imbalance_abs / equity) if equity > 0 else Decimal("0")
        verdict = "ok"
        if self._settings.enable_side_balancer and side and streak >= self._settings.max_side_streak:
            if imbalance_pct >= self._settings.side_imbalance_pct:
                verdict = f"guard_active_{side}"
        return {
            "streak_side": side or "none",
            "streak_count": streak,
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "imbalance_pct": imbalance_pct,
            "verdict": verdict,
        }

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

    def reset_daily(self) -> None:
        self.drawdown_monitor.reset_daily()

    def risk_state(self) -> str:
        if self.drawdown_monitor.is_halted:
            return "HARD_STOP"
        if self.drawdown_monitor.is_soft_stopped:
            return "SOFT_STOP"
        return "NORMAL"

    def block_reason(self) -> str:
        if self.drawdown_monitor.is_halted:
            return self.drawdown_monitor.halt_reason
        if self.drawdown_monitor.is_soft_stopped:
            return self.drawdown_monitor.soft_stop_reason
        return ""

    def symbol_cooldown_remaining_ms(self, symbol: str) -> int:
        expiry = self._symbol_cooldowns.get(symbol)
        if not expiry:
            return 0
        remaining = expiry - utc_now_ms()
        if remaining <= 0:
            self._symbol_cooldowns.pop(symbol, None)
            return 0
        return remaining

    def _is_symbol_on_cooldown(self, symbol: str) -> bool:
        if not self._settings.enable_symbol_cooldown:
            return False
        return self.symbol_cooldown_remaining_ms(symbol) > 0

    def _is_portfolio_heat_exceeded(self, positions: list[Position], equity: Decimal) -> bool:
        if equity <= 0:
            return False
        heat = self.exposure_manager.total_portfolio_risk_pct(positions, equity)
        return heat >= self._settings.portfolio_heat_limit_pct

    def _check_side_balancer(
        self,
        positions: list[Position],
        new_direction: PositionSide,
        equity: Decimal,
    ) -> ExposureCheck:
        if not self._settings.enable_side_balancer:
            return ExposureCheck(True)
        if equity <= 0:
            return ExposureCheck(False, "invalid_equity")
        last_side, streak = self.current_side_streak()
        if streak < self._settings.max_side_streak:
            return ExposureCheck(True)
        if not last_side:
            return ExposureCheck(True)
        long_exposure, short_exposure = self.exposure_manager.directional_exposure_usd(positions)
        imbalance_pct = abs(long_exposure - short_exposure) / equity
        if imbalance_pct < self._settings.side_imbalance_pct:
            return ExposureCheck(True)
        if last_side == "long" and new_direction == PositionSide.LONG:
            return ExposureCheck(False, "side_balancer_long")
        if last_side == "short" and new_direction == PositionSide.SHORT:
            return ExposureCheck(False, "side_balancer_short")
        return ExposureCheck(True)
