import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from time import monotonic

import structlog

from data.models import OrderSide, OrderType
from exchange.models import InFlightOrder, OrderRequest, Position
from monitoring.telegram_bot import TelegramFormatter
from strategies.base_strategy import Signal, SignalDirection, StrategyState

logger = structlog.get_logger("orchestrator_execution")


class OrchestratorExecutionMixin:
    def _update_positions_snapshot(self) -> None:
        if not self._position_manager:
            return
        self._last_positions_snapshot = {
            p.symbol: p for p in self._position_manager.get_all_positions() if p.size > 0
        }

    async def _on_positions_refreshed(self) -> None:
        if not self._position_manager:
            return
        current_positions = {
            p.symbol: p for p in self._position_manager.get_all_positions() if p.size > 0
        }
        previously_open = self._last_positions_snapshot
        closed_symbols = [sym for sym in previously_open if sym not in current_positions]
        for symbol in closed_symbols:
            prev_pos = previously_open[symbol]
            synthetic_signal = self._build_exchange_close_signal(prev_pos)
            await self._account_closed_trade(
                signal=synthetic_signal,
                close_qty=prev_pos.size,
                position_size=prev_pos.size,
                entry_price=prev_pos.entry_price,
                mark_price=prev_pos.mark_price,
                unrealized_pnl=prev_pos.unrealized_pnl,
            )
        self._last_positions_snapshot = current_positions

    def _build_exchange_close_signal(self, position: Position) -> Signal:
        side = str(position.side).lower()
        direction = (
            SignalDirection.CLOSE_LONG
            if side == "long"
            else SignalDirection.CLOSE_SHORT
        )
        return Signal(
            symbol=position.symbol,
            direction=direction,
            confidence=1.0,
            strategy_name="exchange_close",
            entry_price=position.mark_price or position.entry_price,
        )

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
        if reduce_only and self._position_manager:
            await self._position_manager.sync_positions([signal.symbol])
            existing_position = self._position_manager.get_position(signal.symbol)
            positions = self._position_manager.get_all_positions()
            decision = self._risk_manager.evaluate_signal(signal, equity, positions)
            if not decision.approved:
                await logger.ainfo("close_signal_rejected_after_resync", symbol=signal.symbol, reason=decision.reason)
                return

        request = OrderRequest(
            symbol=signal.symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            quantity=decision.quantity,
            stop_loss=None,
            take_profit=None,
            position_idx=existing_position.position_idx if (reduce_only and existing_position) else 0,
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
            if self._position_manager:
                try:
                    await self._position_manager.sync_positions([signal.symbol])
                    if not reduce_only:
                        await self._on_positions_refreshed()
                except Exception:
                    pass

            if not reduce_only and (decision.stop_loss is not None or decision.take_profit is not None):
                await self._apply_position_trading_stop(
                    symbol=signal.symbol,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                )

            await self._record_execution_quality(signal, decision.quantity, in_flight)
            self._sync_strategy_state(signal)

            if reduce_only and existing_position:
                await self._finalize_close_after_submit(
                    signal=signal,
                    expected_close_qty=decision.quantity,
                    previous_position=existing_position,
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
            if reduce_only and "110017" in str(exc):
                await self._handle_reduce_only_zero_position(signal)
                return
            await logger.aerror("order_failed", symbol=signal.symbol, error=str(exc))
            if self._telegram_sink:
                await self._telegram_sink.send_message_now(
                    f"🔴 *Order Failed*\n"
                    f"Symbol: `{signal.symbol}`\n"
                    f"Error: `{str(exc)[:200]}`"
                )

    async def _apply_position_trading_stop(
        self,
        symbol: str,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
    ) -> None:
        if not self._rest_api or not self._position_manager:
            return
        if stop_loss is None and take_profit is None:
            return

        for _ in range(5):
            try:
                await self._position_manager.sync_positions([symbol])
            except Exception:
                await asyncio.sleep(0.3)
                continue
            position = self._position_manager.get_position(symbol)
            if not position or position.size <= 0:
                await asyncio.sleep(0.3)
                continue

            try:
                await self._rest_api.set_position_trading_stop(
                    symbol=symbol,
                    position_idx=position.position_idx,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
            except Exception as exc:
                await logger.awarning(
                    "set_position_trading_stop_failed",
                    symbol=symbol,
                    position_idx=position.position_idx,
                    error=str(exc),
                )
                if self._telegram_sink:
                    await self._telegram_sink.send_message_now(
                        f"⚠️ *TP/SL не установлены*\n"
                        f"Символ: `{symbol}`\n"
                        f"Причина: `{str(exc)[:180]}`"
                    )
                return
            return

        await logger.awarning("set_position_trading_stop_skipped_no_position", symbol=symbol)

    async def _handle_reduce_only_zero_position(self, signal: Signal) -> None:
        if not self._position_manager:
            return
        await self._position_manager.sync_positions([signal.symbol])
        current_position = self._position_manager.get_position(signal.symbol)
        if not current_position or current_position.size <= 0:
            self._sync_strategy_state(
                Signal(
                    symbol=signal.symbol,
                    direction=SignalDirection.CLOSE_LONG if signal.direction == SignalDirection.CLOSE_LONG else SignalDirection.CLOSE_SHORT,
                    confidence=signal.confidence,
                    strategy_name=signal.strategy_name,
                ),
            )
            await logger.awarning("reduce_only_no_position_after_resync", symbol=signal.symbol)
            if self._telegram_sink:
                await self._telegram_sink.send_message_now(
                    f"ℹ️ *Close Sync*\\n"
                    f"Символ: `{signal.symbol}`\\n"
                    f"Позиция уже отсутствует на бирже. Состояние синхронизировано."
                )
            return
        await logger.aerror(
            "reduce_only_failed_position_exists",
            symbol=signal.symbol,
            size=str(current_position.size),
            position_idx=current_position.position_idx,
        )
        if self._telegram_sink:
            await self._telegram_sink.send_message_now(
                f"🔴 *Order Failed*\\n"
                f"Symbol: `{signal.symbol}`\\n"
                f"Причина: `reduce-only rejected (110017), позиция всё ещё открыта`\\n"
                f"Size: `{current_position.size}` | positionIdx: `{current_position.position_idx}`"
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

    async def _finalize_close_after_submit(
        self,
        signal: Signal,
        expected_close_qty: Decimal,
        previous_position: Position,
    ) -> None:
        if not self._position_manager:
            return
        prev_size = previous_position.size
        updated_position = None
        for _ in range(3):
            await self._position_manager.sync_positions([signal.symbol])
            updated_position = self._position_manager.get_position(signal.symbol)
            new_size = updated_position.size if updated_position else Decimal("0")
            if new_size < prev_size:
                break
            await asyncio.sleep(0.4)
        new_size = updated_position.size if updated_position else Decimal("0")
        if new_size >= prev_size:
            await logger.awarning(
                "close_submit_without_position_change",
                symbol=signal.symbol,
                prev_size=str(prev_size),
                new_size=str(new_size),
            )
            return

        closed_qty = min(expected_close_qty, prev_size - new_size)
        await self._account_closed_trade(
            signal=signal,
            close_qty=closed_qty,
            position_size=prev_size,
            entry_price=previous_position.entry_price,
            mark_price=updated_position.mark_price if updated_position else previous_position.mark_price,
            unrealized_pnl=previous_position.unrealized_pnl,
        )
        self._update_positions_snapshot()
