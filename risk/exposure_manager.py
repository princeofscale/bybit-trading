from decimal import Decimal

import structlog

from config.settings import RiskSettings
from data.models import PositionSide
from exchange.models import Position

logger = structlog.get_logger("exposure_manager")

CORRELATION_GROUPS: dict[str, list[str]] = {
    "btc_eth": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
    "alt_l1": ["SOL/USDT:USDT", "AVAX/USDT:USDT", "SUI/USDT:USDT", "APT/USDT:USDT"],
    "alt_l2": ["OP/USDT:USDT", "ARB/USDT:USDT", "MATIC/USDT:USDT"],
    "defi": ["LINK/USDT:USDT", "DOT/USDT:USDT", "ADA/USDT:USDT"],
    "meme": ["DOGE/USDT:USDT"],
    "storage": ["AR/USDT:USDT"],
    "legacy": ["XRP/USDT:USDT"],
}
MAX_SAME_DIRECTION_PER_GROUP = 2


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

    def directional_exposure_usd(self, positions: list[Position]) -> tuple[Decimal, Decimal]:
        long_exposure = Decimal("0")
        short_exposure = Decimal("0")
        for p in positions:
            notional = abs(p.size * p.entry_price)
            if p.side == PositionSide.LONG:
                long_exposure += notional
            elif p.side == PositionSide.SHORT:
                short_exposure += notional
        return long_exposure, short_exposure

    def check_directional_exposure(
        self,
        positions: list[Position],
        new_direction: PositionSide,
        new_size_usd: Decimal,
        equity: Decimal,
    ) -> ExposureCheck:
        if not self._settings.enable_directional_exposure_limit:
            return ExposureCheck(True)
        if equity <= 0:
            return ExposureCheck(False, "invalid_equity")

        long_exposure, short_exposure = self.directional_exposure_usd(positions)
        if new_direction == PositionSide.LONG:
            long_exposure += abs(new_size_usd)
            long_pct = long_exposure / equity
            if long_pct > self._settings.max_directional_exposure_pct:
                return ExposureCheck(
                    False,
                    f"directional_exposure_limit_long: {long_pct:.4f} > {self._settings.max_directional_exposure_pct}",
                )
        elif new_direction == PositionSide.SHORT:
            short_exposure += abs(new_size_usd)
            short_pct = short_exposure / equity
            if short_pct > self._settings.max_directional_exposure_pct:
                return ExposureCheck(
                    False,
                    f"directional_exposure_limit_short: {short_pct:.4f} > {self._settings.max_directional_exposure_pct}",
                )

        return ExposureCheck(True)

    def total_portfolio_risk_pct(
        self, positions: list[Position], equity: Decimal,
    ) -> Decimal:
        if equity <= 0:
            return Decimal("0")
        exposure = self.total_exposure_usd(positions)
        return exposure / equity

    def check_correlation_group(
        self,
        positions: list[Position],
        new_symbol: str,
        new_direction: PositionSide,
    ) -> ExposureCheck:
        group_name = ""
        for name, symbols in CORRELATION_GROUPS.items():
            if new_symbol in symbols:
                group_name = name
                break
        if not group_name:
            return ExposureCheck(True)

        group_symbols = set(CORRELATION_GROUPS[group_name])
        same_dir_count = 0
        for p in positions:
            if p.symbol not in group_symbols or p.size <= 0:
                continue
            if p.side == new_direction:
                same_dir_count += 1

        if same_dir_count >= MAX_SAME_DIRECTION_PER_GROUP:
            return ExposureCheck(
                False,
                f"correlation_group_{group_name}: {same_dir_count} same-direction >= {MAX_SAME_DIRECTION_PER_GROUP}",
            )
        return ExposureCheck(True)

    def is_portfolio_risk_acceptable(
        self, positions: list[Position], equity: Decimal,
    ) -> bool:
        risk_pct = self.total_portfolio_risk_pct(positions, equity)
        return risk_pct <= self._settings.max_portfolio_risk
