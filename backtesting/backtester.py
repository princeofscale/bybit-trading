from decimal import Decimal

import pandas as pd
import structlog

from backtesting.models import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    EquityCurvePoint,
    TradeSide,
)
from backtesting.simulator import FillSimulator
from strategies.base_strategy import BaseStrategy, SignalDirection, StrategyState

logger = structlog.get_logger("backtester")


class OpenPosition:
    def __init__(
        self,
        side: TradeSide,
        entry_price: Decimal,
        quantity: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        entry_time: int,
        entry_commission: Decimal,
        slippage: Decimal,
    ) -> None:
        self.side = side
        self.entry_price = entry_price
        self.quantity = quantity
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.entry_time = entry_time
        self.entry_commission = entry_commission
        self.slippage = slippage
        self.bars_held = 0


class Backtester:
    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        self._simulator = FillSimulator(config)

    def run(
        self, strategy: BaseStrategy, symbol: str, df: pd.DataFrame,
    ) -> BacktestResult:
        equity = self._config.initial_equity
        peak_equity = equity
        trades: list[BacktestTrade] = []
        equity_curve: list[EquityCurvePoint] = []
        position: OpenPosition | None = None
        trade_counter = 0
        min_bars = strategy.min_candles_required()

        for i in range(min_bars, len(df)):
            row = df.iloc[i]
            ts = int(row["open_time"]) if "open_time" in df.columns else i
            high = Decimal(str(row["high"]))
            low = Decimal(str(row["low"]))
            close = Decimal(str(row["close"]))

            if position is not None:
                position.bars_held += 1
                exit_price, reason = self._check_exit(
                    position, high, low, close, strategy, symbol, df.iloc[:i + 1],
                )

                if exit_price is not None:
                    trade = self._close_position(
                        position, exit_price, ts, trade_counter,
                        symbol, strategy.name,
                    )
                    trade_counter += 1
                    equity += trade.pnl
                    trades.append(trade)
                    position = None
                    strategy.set_state(symbol, StrategyState.IDLE)

            if position is None and len(df.iloc[:i + 1]) >= min_bars:
                window = df.iloc[:i + 1]
                signal = strategy.generate_signal(symbol, window)

                if signal and signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
                    if signal.stop_loss and signal.entry_price:
                        position = self._open_position(
                            signal, equity, close, ts,
                        )
                        if position is not None:
                            side_state = (
                                StrategyState.LONG
                                if signal.direction == SignalDirection.LONG
                                else StrategyState.SHORT
                            )
                            strategy.set_state(symbol, side_state)

            if equity > peak_equity:
                peak_equity = equity
            dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else Decimal("0")

            equity_curve.append(EquityCurvePoint(
                timestamp=ts, equity=equity,
                drawdown_pct=dd,
                open_positions=1 if position else 0,
            ))

        if position is not None:
            close_price = Decimal(str(df.iloc[-1]["close"]))
            final_ts = int(df.iloc[-1]["open_time"]) if "open_time" in df.columns else len(df) - 1
            trade = self._close_position(
                position, close_price, final_ts, trade_counter,
                symbol, strategy.name,
            )
            equity += trade.pnl
            trades.append(trade)

        start_ts = int(df.iloc[0]["open_time"]) if "open_time" in df.columns else 0
        end_ts = int(df.iloc[-1]["open_time"]) if "open_time" in df.columns else len(df) - 1

        return BacktestResult(
            config=self._config,
            trades=trades,
            equity_curve=equity_curve,
            final_equity=equity,
            strategy_name=strategy.name,
            symbol=symbol,
            start_time=start_ts,
            end_time=end_ts,
        )

    def _open_position(
        self, signal: "Signal", equity: Decimal, current_price: Decimal, ts: int,
    ) -> OpenPosition | None:
        entry = signal.entry_price or current_price
        stop = signal.stop_loss
        tp = signal.take_profit or Decimal("0")
        side = TradeSide.LONG if signal.direction == SignalDirection.LONG else TradeSide.SHORT

        risk_amount = equity * self._config.risk_per_trade
        distance = abs(entry - stop)
        if distance == 0:
            return None

        quantity = risk_amount / distance
        max_qty = (equity * self._config.max_leverage) / entry
        quantity = min(quantity, max_qty)

        if quantity <= 0:
            return None

        fill_price, commission, slippage = self._simulator.simulate_entry(
            entry, quantity, side,
        )

        return OpenPosition(
            side=side, entry_price=fill_price, quantity=quantity,
            stop_loss=stop, take_profit=tp, entry_time=ts,
            entry_commission=commission, slippage=slippage,
        )

    def _check_exit(
        self,
        pos: OpenPosition,
        high: Decimal,
        low: Decimal,
        close: Decimal,
        strategy: BaseStrategy,
        symbol: str,
        window: pd.DataFrame,
    ) -> tuple[Decimal | None, str]:
        if self._simulator.check_stop_loss(low, high, pos.stop_loss, pos.side):
            return pos.stop_loss, "stop_loss"

        if self._simulator.check_take_profit(low, high, pos.take_profit, pos.side):
            return pos.take_profit, "take_profit"

        signal = strategy.generate_signal(symbol, window)
        if signal:
            if pos.side == TradeSide.LONG and signal.direction == SignalDirection.CLOSE_LONG:
                return close, "signal_exit"
            if pos.side == TradeSide.SHORT and signal.direction == SignalDirection.CLOSE_SHORT:
                return close, "signal_exit"

        return None, ""

    def _close_position(
        self,
        pos: OpenPosition,
        exit_price: Decimal,
        ts: int,
        trade_id: int,
        symbol: str,
        strategy_name: str,
    ) -> BacktestTrade:
        fill_price, exit_commission, exit_slippage = self._simulator.simulate_exit(
            exit_price, pos.quantity, pos.side,
        )

        pnl = self._simulator.calculate_pnl(
            pos.entry_price, fill_price, pos.quantity, pos.side,
            pos.entry_commission, exit_commission,
        )

        notional = pos.entry_price * pos.quantity
        pnl_pct = pnl / notional if notional > 0 else Decimal("0")

        return BacktestTrade(
            trade_id=trade_id, symbol=symbol, side=pos.side,
            entry_price=pos.entry_price, exit_price=fill_price,
            quantity=pos.quantity, entry_time=pos.entry_time,
            exit_time=ts, stop_loss=pos.stop_loss,
            take_profit=pos.take_profit, pnl=pnl,
            pnl_pct=pnl_pct,
            commission=pos.entry_commission + exit_commission,
            slippage=pos.slippage + exit_slippage,
            bars_held=pos.bars_held, strategy_name=strategy_name,
        )
