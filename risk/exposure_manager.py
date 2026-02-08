from decimal import Decimal

import structlog

from config.settings import RiskSettings
from exchange.models import Position

logger = structlog.get_logger("exposure_manager")


class ExposureCheck:
    def __init__(self, allowed: bool, reason: str = "") -> None:
        self.allowed = allowed
        self.reason = reason


class ExposureManager:
    def __init__(self, risk_settings: RiskSettings) -> None:
        self._settings = risk_settings

    def check_new_position(
        self,
        positions: list[Position],
        new_symbol: str,
        new_size_usd: Decimal,
        new_leverage: Decimal,
        equity: Decimal,
        is_funding_arb: bool = False,
    ) -> ExposureCheck:
        if not is_funding_arb:
            if len(positions) >= self._settings.max_concurrent_positions:
                return ExposureCheck(
                    False,
                    f"max_positions: {len(positions)} >= {self._settings.max_concurrent_positions}",
                )

        if new_leverage > self._settings.max_leverage:
            return ExposureCheck(
                False,
                f"max_leverage: {new_leverage} > {self._settings.max_leverage}",
            )

        total_exposure = sum(abs(p.size * p.entry_price) for p in positions)
        max_total = equity * self._settings.max_leverage
        if total_exposure + new_size_usd > max_total:
            return ExposureCheck(
                False,
                f"total_exposure: {total_exposure + new_size_usd} > {max_total}",
            )

        if is_funding_arb:
            arb_exposure = sum(
                abs(p.size * p.entry_price) for p in positions
            )
            max_arb = equity * self._settings.funding_arb_max_allocation
            if new_size_usd > max_arb:
                return ExposureCheck(
                    False,
                    f"funding_arb_allocation: {new_size_usd} > {max_arb}",
                )

        per_trade_risk = new_size_usd / equity if equity > 0 else Decimal("1")
        if per_trade_risk > self._settings.max_risk_per_trade * new_leverage:
            return ExposureCheck(
                False,
                f"per_trade_risk: {per_trade_risk:.4f}",
            )

        return ExposureCheck(True)

    def total_exposure_usd(self, positions: list[Position]) -> Decimal:
        return sum(abs(p.size * p.entry_price) for p in positions)

    def total_portfolio_risk_pct(
        self, positions: list[Position], equity: Decimal,
    ) -> Decimal:
        if equity <= 0:
            return Decimal("0")
        exposure = self.total_exposure_usd(positions)
        return exposure / equity

    def is_portfolio_risk_acceptable(
        self, positions: list[Position], equity: Decimal,
    ) -> bool:
        risk_pct = self.total_portfolio_risk_pct(positions, equity)
        return risk_pct <= self._settings.max_portfolio_risk
