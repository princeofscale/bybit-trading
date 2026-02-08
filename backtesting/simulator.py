from decimal import Decimal

from backtesting.models import BacktestConfig, TradeSide


class FillSimulator:
    def __init__(self, config: BacktestConfig) -> None:
        self._maker_fee = config.maker_fee
        self._taker_fee = config.taker_fee
        self._slippage_pct = config.slippage_pct
        self._use_limit = config.use_limit_orders

    def apply_slippage(self, price: Decimal, side: TradeSide, is_entry: bool) -> Decimal:
        if self._slippage_pct == 0:
            return price

        if (side == TradeSide.LONG and is_entry) or (side == TradeSide.SHORT and not is_entry):
            return price * (1 + self._slippage_pct)

        return price * (1 - self._slippage_pct)

    def calculate_commission(self, notional: Decimal) -> Decimal:
        fee_rate = self._maker_fee if self._use_limit else self._taker_fee
        return notional * fee_rate

    def simulate_entry(
        self, price: Decimal, quantity: Decimal, side: TradeSide,
    ) -> tuple[Decimal, Decimal, Decimal]:
        fill_price = self.apply_slippage(price, side, is_entry=True)
        notional = fill_price * quantity
        commission = self.calculate_commission(notional)
        slippage_cost = abs(fill_price - price) * quantity
        return fill_price, commission, slippage_cost

    def simulate_exit(
        self, price: Decimal, quantity: Decimal, side: TradeSide,
    ) -> tuple[Decimal, Decimal, Decimal]:
        fill_price = self.apply_slippage(price, side, is_entry=False)
        notional = fill_price * quantity
        commission = self.calculate_commission(notional)
        slippage_cost = abs(fill_price - price) * quantity
        return fill_price, commission, slippage_cost

    def calculate_pnl(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        side: TradeSide,
        entry_commission: Decimal,
        exit_commission: Decimal,
    ) -> Decimal:
        if side == TradeSide.LONG:
            gross_pnl = (exit_price - entry_price) * quantity
        else:
            gross_pnl = (entry_price - exit_price) * quantity
        return gross_pnl - entry_commission - exit_commission

    def check_stop_loss(
        self, low: Decimal, high: Decimal, stop: Decimal, side: TradeSide,
    ) -> bool:
        if side == TradeSide.LONG:
            return low <= stop
        return high >= stop

    def check_take_profit(
        self, low: Decimal, high: Decimal, tp: Decimal, side: TradeSide,
    ) -> bool:
        if tp <= 0:
            return False
        if side == TradeSide.LONG:
            return high >= tp
        return low <= tp
