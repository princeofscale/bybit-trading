from decimal import Decimal
from enum import StrEnum

from config.settings import RiskSettings


class SizingMethod(StrEnum):
    FIXED_FRACTIONAL = "fixed_fractional"
    KELLY = "kelly"
    VOLATILITY = "volatility"


class PositionSizer:
    def __init__(self, risk_settings: RiskSettings) -> None:
        self._settings = risk_settings

    def fixed_fractional(
        self,
        equity: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> Decimal:
        if entry_price <= 0 or stop_loss_price <= 0:
            return Decimal("0")

        risk_amount = equity * self._settings.max_risk_per_trade
        price_distance = abs(entry_price - stop_loss_price)

        if price_distance == 0:
            return Decimal("0")

        quantity = risk_amount / price_distance
        max_by_leverage = (equity * self._settings.max_leverage) / entry_price

        return min(quantity, max_by_leverage)

    def kelly_criterion(
        self,
        equity: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        win_rate: Decimal,
        avg_win: Decimal,
        avg_loss: Decimal,
    ) -> Decimal:
        if avg_loss == 0 or entry_price <= 0:
            return Decimal("0")

        win_loss_ratio = avg_win / avg_loss
        kelly = win_rate - (1 - win_rate) / win_loss_ratio
        kelly = max(Decimal("0"), min(kelly, Decimal("0.25")))

        half_kelly = kelly / 2

        risk_amount = equity * half_kelly
        price_distance = abs(entry_price - stop_loss_price)

        if price_distance == 0:
            return Decimal("0")

        quantity = risk_amount / price_distance
        max_by_leverage = (equity * self._settings.max_leverage) / entry_price

        return min(quantity, max_by_leverage)

    def volatility_based(
        self,
        equity: Decimal,
        entry_price: Decimal,
        atr_value: Decimal,
        atr_multiplier: Decimal = Decimal("2"),
    ) -> Decimal:
        if entry_price <= 0 or atr_value <= 0:
            return Decimal("0")

        risk_amount = equity * self._settings.max_risk_per_trade
        stop_distance = atr_value * atr_multiplier

        if stop_distance == 0:
            return Decimal("0")

        quantity = risk_amount / stop_distance
        max_by_leverage = (equity * self._settings.max_leverage) / entry_price

        return min(quantity, max_by_leverage)

    def calculate_size(
        self,
        method: SizingMethod,
        equity: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        **kwargs: Decimal,
    ) -> Decimal:
        if method == SizingMethod.FIXED_FRACTIONAL:
            return self.fixed_fractional(equity, entry_price, stop_loss_price)

        if method == SizingMethod.KELLY:
            return self.kelly_criterion(
                equity, entry_price, stop_loss_price,
                kwargs.get("win_rate", Decimal("0.5")),
                kwargs.get("avg_win", Decimal("1")),
                kwargs.get("avg_loss", Decimal("1")),
            )

        if method == SizingMethod.VOLATILITY:
            return self.volatility_based(
                equity, entry_price,
                kwargs.get("atr_value", Decimal("0")),
                kwargs.get("atr_multiplier", Decimal("2")),
            )

        return Decimal("0")
