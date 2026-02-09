from datetime import datetime, timezone
from decimal import Decimal
from time import monotonic

import structlog

from data.models import OrderSide, OrderType
from exchange.models import InFlightOrder, OrderRequest
from monitoring.telegram_bot import TelegramFormatter
from strategies.base_strategy import Signal, SignalDirection, StrategyState

logger = structlog.get_logger("orchestrator_execution")


class OrchestratorExecutionMixin:
    def _restore_strategy_states_from_positions(self) -> None:
        if not self._strategy_selector or not self._position_manager:
            return
        for strategy in self._strategy_selector.strategies.values():
            for symbol in strategy.symbols:
                position = self._position_manager.get_position(symbol)
                if not position or position.size <= 0:
                    strategy.set_state(symbol, StrategyState.IDLE)
                    continue
                side = str(position.side).lower()
                if side == "long":
                    strategy.set_state(symbol, StrategyState.LONG)
                elif side == "short":
                    strategy.set_state(symbol, StrategyState.SHORT)
                else:
                    strategy.set_state(symbol, StrategyState.IDLE)

    async def _reconcile_recovered_positions(self) -> None:
        if not self._position_manager:
            return
        recovered = [p for p in self._position_manager.get_all_positions() if p.size > 0]
        if not recovered:
            return
        await logger.ainfo("reconcile_recovered_positions_start", count=len(recovered))
        for position in recovered:
            await self._poll_and_analyze(position.symbol)
        await logger.ainfo("reconcile_recovered_positions_done")

    async def _poll_and_analyze(self, symbol: str) -> None:
        if self._trading_paused or not self._rest_api or not self._candle_buffer:
            return

        candles = await self._rest_api.fetch_ohlcv(symbol, timeframe="15m", limit=5)
        if not candles:
            return

        for candle in candles:
            self._candle_buffer.update(symbol, candle)

        if not self._candle_buffer.has_enough(symbol, 60):
            return

        all_candles = self._candle_buffer.get_candles(symbol)
        df = self._preprocessor.candles_to_dataframe(all_candles)
        df = self._feature_engineer.build_features(df)

        signal = self._strategy_selector.get_best_signal(symbol, df)
        if not signal:
            return

        self._signals_count += 1
        await logger.ainfo(
            "signal_generated",
            symbol=signal.symbol,
            direction=signal.direction.value,
            strategy=signal.strategy_name,
            confidence=signal.confidence,
        )

        positions = self._position_manager.get_all_positions() if self._position_manager else []
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        decision = self._risk_manager.evaluate_signal(signal, equity, positions)

        if self._journal:
            await self._journal.log_signal(
                timestamp=datetime.now(timezone.utc),
                symbol=signal.symbol,
                direction=signal.direction.value,
                confidence=signal.confidence,
                strategy_name=signal.strategy_name,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                approved=decision.approved,
                rejection_reason=decision.reason if not decision.approved else "",
                session_id=self._session_id,
            )

        if not decision.approved:
            await logger.ainfo("signal_rejected", symbol=signal.symbol, reason=decision.reason)
            return

        order_side = self._resolve_order_side(signal.direction)
        reduce_only = signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT)
        existing_position = self._position_manager.get_position(signal.symbol) if self._position_manager else None

        request = OrderRequest(
            symbol=signal.symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            quantity=decision.quantity,
            stop_loss=None if reduce_only else decision.stop_loss,
            take_profit=None if reduce_only else decision.take_profit,
            reduce_only=reduce_only,
        )

        try:
            submit_started = monotonic()
            in_flight = await self._order_manager.submit_order(request, signal.strategy_name)
            ack_latency_ms = Decimal(str(round((monotonic() - submit_started) * 1000, 3)))
            self._trades_count += 1
            self._metrics.counter("orders_placed").increment()
            self._metrics.histogram("order_ack_latency_ms").observe(ack_latency_ms)

            await logger.ainfo(
                "order_submitted",
                symbol=signal.symbol,
                side=order_side.value,
                quantity=str(decision.quantity),
                strategy=signal.strategy_name,
                reduce_only=reduce_only,
            )

            await self._record_execution_quality(signal, decision.quantity, in_flight)
            self._sync_strategy_state(signal)

            if reduce_only and existing_position:
                await self._account_closed_trade(
                    signal=signal,
                    close_qty=decision.quantity,
                    position_size=existing_position.size,
                    entry_price=existing_position.entry_price,
                    mark_price=existing_position.mark_price,
                    unrealized_pnl=existing_position.unrealized_pnl,
                )

            if self._telegram_sink and not reduce_only:
                await self._telegram_sink.send_message_now(
                    TelegramFormatter.format_trade_opened(
                        symbol=signal.symbol,
                        side=signal.direction.value,
                        size=decision.quantity,
                        entry_price=signal.entry_price or Decimal(0),
                        stop_loss=signal.stop_loss or Decimal(0),
                        take_profit=signal.take_profit or Decimal(0),
                        strategy=signal.strategy_name,
                    )
                )
        except Exception as exc:
            self._metrics.counter("missed_fills").increment()
            await logger.aerror("order_failed", symbol=signal.symbol, error=str(exc))
            if self._telegram_sink:
                await self._telegram_sink.send_message_now(
                    f"🔴 *Order Failed*\n"
                    f"Symbol: `{signal.symbol}`\n"
                    f"Error: `{str(exc)[:200]}`"
                )

    def _resolve_order_side(self, direction: SignalDirection) -> OrderSide:
        if direction in (SignalDirection.LONG, SignalDirection.CLOSE_SHORT):
            return OrderSide.BUY
        return OrderSide.SELL

    def _sync_strategy_state(self, signal: Signal) -> None:
        if not self._strategy_selector:
            return
        strategy = self._strategy_selector.strategies.get(signal.strategy_name)
        if not strategy:
            return
        if signal.direction == SignalDirection.LONG:
            strategy.set_state(signal.symbol, StrategyState.LONG)
        elif signal.direction == SignalDirection.SHORT:
            strategy.set_state(signal.symbol, StrategyState.SHORT)
        elif signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT):
            strategy.set_state(signal.symbol, StrategyState.IDLE)

    async def _record_execution_quality(
        self,
        signal: Signal,
        quantity: Decimal,
        in_flight: InFlightOrder,
    ) -> None:
        fee = in_flight.fee or Decimal("0")
        if fee > 0:
            self._metrics.counter("fee_impact_usdt").increment(fee)

        fill_price = in_flight.avg_fill_price
        ref_price = signal.entry_price
        if fill_price and ref_price and ref_price > 0:
            slippage_bps = abs(fill_price - ref_price) / ref_price * Decimal("10000")
            self._metrics.histogram("slippage_bps").observe(slippage_bps)
            slippage_cost = abs(fill_price - ref_price) * quantity
            self._metrics.counter("slippage_cost_usdt").increment(slippage_cost)

        if in_flight.filled_qty <= 0:
            self._metrics.counter("missed_fills").increment()

    async def _account_closed_trade(
        self,
        signal: Signal,
        close_qty: Decimal,
        position_size: Decimal,
        entry_price: Decimal,
        mark_price: Decimal,
        unrealized_pnl: Decimal,
    ) -> None:
        if position_size <= 0:
            return
        closed_qty = min(close_qty, position_size)
        if closed_qty <= 0:
            return

        fraction = closed_qty / position_size
        realized_pnl = unrealized_pnl * fraction
        exit_price = signal.entry_price or mark_price or entry_price
        notional = entry_price * closed_qty
        pnl_pct = realized_pnl / notional if notional > 0 else Decimal("0")
        is_win = realized_pnl > 0

        self._metrics.counter("trades_closed").increment()
        if is_win:
            self._metrics.counter("trades_won").increment()
        else:
            self._metrics.counter("trades_lost").increment()

        if self._risk_manager:
            self._risk_manager.record_trade_result(is_win=is_win, symbol=signal.symbol)
        if self._strategy_selector:
            self._strategy_selector.record_trade_result(signal.strategy_name, realized_pnl)

        side = "long" if signal.direction == SignalDirection.CLOSE_LONG else "short"

        if self._journal:
            await self._journal.log_trade(
                timestamp=datetime.now(timezone.utc),
                symbol=signal.symbol,
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=closed_qty,
                realized_pnl=realized_pnl,
                pnl_pct=pnl_pct,
                strategy_name=signal.strategy_name,
                hold_duration_ms=0,
                session_id=self._session_id,
            )

        if self._telegram_sink:
            await self._telegram_sink.send_message_now(
                TelegramFormatter.format_trade_closed(
                    symbol=signal.symbol,
                    side=side,
                    pnl=realized_pnl,
                    pnl_pct=pnl_pct,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    strategy=signal.strategy_name,
                )
            )
