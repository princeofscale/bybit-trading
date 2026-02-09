import asyncio
import json
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from time import monotonic

import structlog

from data.models import OrderSide, OrderType
from exchange.models import InFlightOrder, OrderRequest, Position
from monitoring.telegram_bot import TelegramFormatter
from strategies.base_strategy import Signal, SignalDirection, StrategyState
from utils.time_utils import utc_now_ms

logger = structlog.get_logger("orchestrator_execution")


class OrchestratorExecutionMixin:
    def _update_positions_snapshot(self) -> None:
        if not self._position_manager:
            return
        self._last_positions_snapshot = {
            p.symbol: p for p in self._position_manager.get_all_positions() if p.size > 0
        }

    async def _on_positions_refreshed(
        self,
        observed_symbols: set[str] | None = None,
        allow_exchange_fallback: bool = False,
    ) -> None:
        if not self._position_manager:
            return
        self._prune_recent_external_closes()
        current_positions = {
            p.symbol: p for p in self._position_manager.get_all_positions() if p.size > 0
        }
        previously_open = self._last_positions_snapshot
        next_snapshot = dict(current_positions)
        closed_symbols = [sym for sym in previously_open if sym not in current_positions]
        for symbol in closed_symbols:
            prev_pos = previously_open[symbol]
            if observed_symbols is not None and symbol not in observed_symbols:
                next_snapshot[symbol] = prev_pos
                continue
            if not allow_exchange_fallback:
                self._position_first_seen_ms.pop(symbol, None)
                self._position_peak_pnl.pop(symbol, None)
                self._pending_trading_stops.pop(symbol, None)
                self._trading_stop_last_status.pop(symbol, None)
                self._missing_position_counts.pop(symbol, None)
                continue
            misses = self._missing_position_counts.get(symbol, 0) + 1
            self._missing_position_counts[symbol] = misses
            if misses < max(1, self._settings.trading.close_missing_confirmations):
                next_snapshot[symbol] = prev_pos
                continue
            dedup_key = self._build_external_close_key(prev_pos)
            now_ms = utc_now_ms()
            last_sent = self._recent_external_closes.get(dedup_key, 0)
            if now_ms - last_sent < self._settings.trading.close_dedup_ttl_sec * 1000:
                continue
            self._recent_external_closes[dedup_key] = now_ms
            await logger.ainfo("close_event_source", symbol=symbol, source="exchange_fallback")
            synthetic_signal = self._build_exchange_close_signal(prev_pos)
            await self._account_closed_trade(
                signal=synthetic_signal,
                close_qty=prev_pos.size,
                position_size=prev_pos.size,
                entry_price=prev_pos.entry_price,
                mark_price=prev_pos.mark_price,
                unrealized_pnl=prev_pos.unrealized_pnl,
            )
            self._position_first_seen_ms.pop(symbol, None)
            self._position_peak_pnl.pop(symbol, None)
            self._pending_trading_stops.pop(symbol, None)
            self._trading_stop_last_status.pop(symbol, None)
            self._missing_position_counts.pop(symbol, None)
        now_ms = utc_now_ms()
        for symbol, position in current_positions.items():
            self._missing_position_counts.pop(symbol, None)
            self._position_first_seen_ms.setdefault(symbol, now_ms)
            peak = self._position_peak_pnl.get(symbol, position.unrealized_pnl)
            self._position_peak_pnl[symbol] = max(peak, position.unrealized_pnl)
        self._last_positions_snapshot = next_snapshot

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

    def _build_external_close_key(self, position: Position) -> str:
        ttl_bucket = max(1, self._settings.trading.close_dedup_ttl_sec)
        bucket = utc_now_ms() // (ttl_bucket * 1000)
        side = str(position.side).lower()
        entry = f"{position.entry_price:.4f}" if position.entry_price is not None else "0"
        size = f"{position.size:.6f}" if position.size is not None else "0"
        return f"{position.symbol}|{side}|{entry}|{size}|{bucket}"

    def _prune_recent_external_closes(self) -> None:
        if not self._recent_external_closes:
            return
        ttl_ms = max(1, self._settings.trading.close_dedup_ttl_sec) * 1000
        now_ms = utc_now_ms()
        stale = [key for key, ts in self._recent_external_closes.items() if now_ms - ts > ttl_ms]
        for key in stale:
            self._recent_external_closes.pop(key, None)

    async def _sync_positions_and_reconcile(self, symbols: list[str] | None = None) -> None:
        if not self._position_manager:
            return
        observed = set(symbols) if symbols else None
        is_full_sync = symbols is None
        allow_exchange_fallback = (
            is_full_sync and self._settings.trading.enable_exchange_close_fallback
        )
        async with self._positions_refresh_lock:
            await self._position_manager.sync_positions(symbols)
            await self._on_positions_refreshed(observed, allow_exchange_fallback=allow_exchange_fallback)

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
        if self._position_manager:
            try:
                await self._sync_positions_and_reconcile([symbol])
            except Exception:
                pass
            position = self._position_manager.get_position(symbol)
            if position and position.size > 0:
                if await self._enforce_position_exit_guards(position):
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
        await self._refresh_funding_rate(symbol)
        df = self._apply_funding_rate_column(symbol, df)
        df = self._feature_engineer.build_features(df)

        signal = self._strategy_selector.get_best_signal(symbol, df)
        if not signal:
            return

        mtf_ok, mtf_reason, mtf_meta = await self._evaluate_mtf_confirm(signal)
        if not mtf_ok:
            await logger.ainfo("signal_rejected_mtf", symbol=symbol, reason=mtf_reason, **mtf_meta)
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
                    approved=False,
                    rejection_reason=mtf_reason,
                    session_id=self._session_id,
                )
            await self._record_ml_candidate(signal, approved=False, rejection_reason=mtf_reason, features=mtf_meta)
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
        await self._record_ml_candidate(
            signal,
            approved=decision.approved,
            rejection_reason="" if decision.approved else (decision.reason or ""),
            features=mtf_meta,
        )

        if not decision.approved:
            await logger.ainfo("signal_rejected", symbol=signal.symbol, reason=decision.reason)
            return

        order_side = self._resolve_order_side(signal.direction)
        reduce_only = signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT)
        existing_position = self._position_manager.get_position(signal.symbol) if self._position_manager else None
        if reduce_only and self._position_manager:
            await self._sync_positions_and_reconcile([signal.symbol])
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
                    await self._sync_positions_and_reconcile([signal.symbol])
                except Exception:
                    pass

            if not reduce_only and (decision.stop_loss is not None or decision.take_profit is not None):
                self._queue_position_trading_stop(
                    symbol=signal.symbol,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                )
                await self._ensure_position_trading_stop(signal.symbol)

            await self._record_execution_quality(signal, decision.quantity, in_flight)
            self._sync_strategy_state(signal)
            if not reduce_only and self._risk_manager:
                self._risk_manager.record_entry_direction(signal.direction)

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

    def _queue_position_trading_stop(
        self,
        symbol: str,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
    ) -> None:
        if stop_loss is None and take_profit is None:
            return
        now_ms = utc_now_ms()
        self._pending_trading_stops[symbol] = {
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "attempts": 0,
            "first_queued_ms": now_ms,
            "next_retry_ms": now_ms,
            "last_error": "",
            "alerted_failed": False,
        }
        self._trading_stop_last_status[symbol] = "pending"

    async def _ensure_position_trading_stop(self, symbol: str) -> bool:
        if not self._rest_api or not self._position_manager:
            return False
        desired = self._pending_trading_stops.get(symbol)
        if not desired:
            return True
        now_ms = utc_now_ms()
        next_retry_ms = int(desired.get("next_retry_ms", 0))
        if now_ms < next_retry_ms:
            return False

        stop_loss = desired.get("stop_loss")
        take_profit = desired.get("take_profit")
        attempts = int(desired.get("attempts", 0))
        first_queued_ms = int(desired.get("first_queued_ms", now_ms))
        timeout_ms = self._settings.trading_stop.confirm_timeout_sec * 1000
        max_attempts = self._settings.trading_stop.retry_max_attempts
        retry_interval_ms = int(self._settings.trading_stop.retry_interval_sec * 1000)

        error_text = ""
        try:
            await self._position_manager.sync_positions([symbol])
            position = self._position_manager.get_position(symbol)
        except Exception as exc:
            position = None
            error_text = str(exc)

        if position and position.size > 0 and self._position_has_expected_stops(position, stop_loss, take_profit):
            self._pending_trading_stops.pop(symbol, None)
            self._trading_stop_last_status[symbol] = "confirmed"
            return True

        if position and position.size > 0:
            try:
                await self._rest_api.set_position_trading_stop(
                    symbol=symbol,
                    position_idx=position.position_idx,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
            except Exception as exc:
                error_text = str(exc)
                await logger.awarning(
                    "set_position_trading_stop_failed",
                    symbol=symbol,
                    position_idx=position.position_idx,
                    error=error_text,
                )

        attempts += 1
        desired["attempts"] = attempts
        desired["last_error"] = error_text

        timed_out = (now_ms - first_queued_ms) >= timeout_ms
        failed = attempts >= max_attempts or timed_out
        if failed:
            self._trading_stop_last_status[symbol] = "failed"
            desired["next_retry_ms"] = now_ms + timeout_ms
            alerted_failed = bool(desired.get("alerted_failed", False))
            if not alerted_failed and self._telegram_sink:
                await logger.awarning(
                    "set_position_trading_stop_unconfirmed",
                    symbol=symbol,
                    stop_loss=str(stop_loss) if stop_loss is not None else None,
                    take_profit=str(take_profit) if take_profit is not None else None,
                    error=error_text,
                )
                await self._telegram_sink.send_message_now(
                    f"⚠️ *TP/SL не подтверждены биржей*\n"
                    f"Символ: `{symbol}`\n"
                    f"SL: `{stop_loss if stop_loss is not None else '—'}` | TP: `{take_profit if take_profit is not None else '—'}`\n"
                    f"Причина: `{error_text[:160] if error_text else 'таймаут подтверждения'}`"
                )
                desired["alerted_failed"] = True
            return False

        self._trading_stop_last_status[symbol] = "pending"
        desired["next_retry_ms"] = now_ms + max(200, retry_interval_ms)
        return False

    async def _process_pending_trading_stops(self) -> None:
        if not self._pending_trading_stops:
            return
        for symbol in list(self._pending_trading_stops):
            try:
                await self._ensure_position_trading_stop(symbol)
            except Exception as exc:
                await logger.awarning("pending_trading_stop_process_error", symbol=symbol, error=str(exc))

    def _position_has_expected_stops(
        self,
        position: Position,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
    ) -> bool:
        return (
            self._price_matches(position.stop_loss, stop_loss)
            and self._price_matches(position.take_profit, take_profit)
        )

    def _price_matches(self, actual: Decimal | None, expected: Decimal | None) -> bool:
        if expected is None:
            return True
        if actual is None:
            return False
        tolerance = max(Decimal("0.0001"), abs(expected) * Decimal("0.001"))
        return abs(actual - expected) <= tolerance

    async def _refresh_funding_rate(self, symbol: str) -> None:
        if not self._rest_api:
            return
        try:
            rate = await self._rest_api.fetch_funding_rate(symbol)
        except Exception:
            self._funding_rate_failures[symbol] = self._funding_rate_failures.get(symbol, 0) + 1
            self._update_funding_arb_availability()
            return
        self._funding_rate_failures[symbol] = 0
        self._update_funding_arb_availability()
        self._append_funding_rate_sample(symbol, float(rate))

    def _update_funding_arb_availability(self) -> None:
        if not self._strategy_selector:
            return
        strategy = self._strategy_selector.strategies.get("funding_rate_arb")
        if not strategy:
            return
        degraded = any(v >= 3 for v in self._funding_rate_failures.values())
        if degraded and not self._funding_arb_degraded:
            strategy.disable()
            self._funding_arb_degraded = True
            logger.warning("funding_arb_temporarily_disabled", failures=self._funding_rate_failures)
            return
        if not degraded and self._funding_arb_degraded:
            strategy.enable()
            self._funding_arb_degraded = False
            logger.info("funding_arb_reenabled")

    def _append_funding_rate_sample(self, symbol: str, funding_rate: float) -> None:
        history = self._funding_rate_history.get(symbol)
        if history is None:
            history = deque(maxlen=240)
            self._funding_rate_history[symbol] = history
        history.append(funding_rate)

    def _apply_funding_rate_column(self, symbol: str, df):
        history = self._funding_rate_history.get(symbol)
        if df is None or df.empty or not history:
            return df
        rates = list(history)
        count = len(df)
        if len(rates) >= count:
            values = rates[-count:]
        else:
            values = [rates[0]] * (count - len(rates)) + rates
        out = df.copy()
        out["funding_rate"] = values
        return out

    async def _evaluate_mtf_confirm(self, signal: Signal) -> tuple[bool, str, dict[str, float]]:
        if signal.direction not in (SignalDirection.LONG, SignalDirection.SHORT):
            return True, "", {}
        if not self._settings.trading.enable_mtf_confirm:
            return True, "", {}
        if not self._rest_api or not self._preprocessor or not self._feature_engineer:
            return False, "mtf_components_unavailable", {}

        bars = max(80, int(self._settings.trading.mtf_confirm_min_bars))
        candles = await self._rest_api.fetch_ohlcv(
            signal.symbol,
            timeframe=self._settings.trading.mtf_confirm_tf,
            limit=bars,
        )
        if not candles or len(candles) < bars:
            return False, "mtf_confirm_insufficient_data", {}

        df_mtf = self._preprocessor.candles_to_dataframe(candles)
        await self._refresh_funding_rate(signal.symbol)
        df_mtf = self._apply_funding_rate_column(signal.symbol, df_mtf)
        df_mtf = self._feature_engineer.build_features(df_mtf)
        if df_mtf.empty:
            return False, "mtf_confirm_empty_frame", {}

        last = df_mtf.iloc[-1]
        ema50 = float(last.get("ema_50", 0.0))
        ema200 = float(last.get("sma_200", 0.0))
        adx_val = float(last.get("adx", 0.0))
        adx_min = float(self._settings.trading.mtf_confirm_adx_min)
        if (
            signal.direction == SignalDirection.SHORT
            and self._settings.trading.enable_short_relax_if_long_streak
            and self._risk_manager
        ):
            streak_side, streak_count = self._risk_manager.current_side_streak()
            if streak_side == "long" and streak_count >= self._settings.risk_guards.max_side_streak:
                adx_min = max(10.0, adx_min * 0.8)
        meta = {"mtf_ema50": ema50, "mtf_ema200": ema200, "mtf_adx": adx_val}

        trend_ok = ema50 > ema200 if signal.direction == SignalDirection.LONG else ema50 < ema200
        if not trend_ok:
            return False, "mtf_confirm_failed", meta
        if adx_val < adx_min:
            return False, "mtf_confirm_failed", meta
        return True, "", meta

    async def _record_ml_candidate(
        self,
        signal: Signal,
        approved: bool,
        rejection_reason: str,
        features: dict[str, float] | None = None,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "strategy": signal.strategy_name,
            "confidence": signal.confidence,
            "entry_price": str(signal.entry_price or Decimal("0")),
            "stop_loss": str(signal.stop_loss or Decimal("0")),
            "take_profit": str(signal.take_profit or Decimal("0")),
            "approved": approved,
            "rejection_reason": rejection_reason,
            "label": None,
        }
        if features:
            payload["features"] = features

        target = self._settings.data_dir / "ml_candidates.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)

        def _append() -> None:
            with target.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(payload, ensure_ascii=False) + "\n")

        await asyncio.to_thread(_append)

    async def _enforce_position_exit_guards(self, position: Position) -> bool:
        equity = self._account_manager.equity if self._account_manager else Decimal("0")
        reason = self._position_exit_reason(position, equity)
        if not reason or not self._order_manager:
            return False

        close_direction = (
            SignalDirection.CLOSE_LONG
            if str(position.side).lower() == "long"
            else SignalDirection.CLOSE_SHORT
        )
        close_side = self._resolve_order_side(close_direction)
        signal = Signal(
            symbol=position.symbol,
            direction=close_direction,
            confidence=1.0,
            strategy_name="risk_exit_guard",
            entry_price=position.mark_price or position.entry_price,
        )
        request = OrderRequest(
            symbol=position.symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=position.size,
            stop_loss=None,
            take_profit=None,
            position_idx=position.position_idx,
            reduce_only=True,
        )

        try:
            await self._order_manager.submit_order(request, signal.strategy_name)
            self._trades_count += 1
            if self._telegram_sink:
                await self._telegram_sink.send_message_now(
                    f"🛑 *Принудительное закрытие*\n"
                    f"Символ: `{position.symbol}`\n"
                    f"Причина: `{reason}`\n"
                    f"PnL: `{position.unrealized_pnl:.4f} USDT`"
                )
            await self._finalize_close_after_submit(
                signal=signal,
                expected_close_qty=position.size,
                previous_position=position,
            )
            return True
        except Exception as exc:
            await logger.aerror(
                "forced_close_failed",
                symbol=position.symbol,
                reason=reason,
                error=str(exc),
            )
            if self._telegram_sink:
                await self._telegram_sink.send_message_now(
                    f"🔴 *Order Failed*\n"
                    f"Symbol: `{position.symbol}`\n"
                    f"Причина: `{reason}`\n"
                    f"Error: `{str(exc)[:160]}`"
                )
            return False

    def _position_exit_reason(self, position: Position, equity: Decimal) -> str | None:
        guards = self._settings.risk_guards
        now_ms = utc_now_ms()
        self._position_first_seen_ms.setdefault(position.symbol, now_ms)
        peak = self._position_peak_pnl.get(position.symbol, position.unrealized_pnl)
        peak = max(peak, position.unrealized_pnl)
        self._position_peak_pnl[position.symbol] = peak

        if guards.enable_max_hold_exit and guards.max_hold_minutes > 0:
            held_ms = now_ms - self._position_first_seen_ms[position.symbol]
            if held_ms >= guards.max_hold_minutes * 60_000:
                return f"max_hold_exceeded: {held_ms // 60_000}m >= {guards.max_hold_minutes}m"

        pnl = position.unrealized_pnl
        if guards.enable_pnl_pct_exit and equity > 0:
            stop_loss_usdt = equity * guards.stop_loss_pct
            take_profit_usdt = equity * guards.take_profit_pct
            if stop_loss_usdt > 0 and pnl <= -stop_loss_usdt:
                return (
                    f"stop_loss_pct_hit: {pnl:.2f} <= -{stop_loss_usdt:.2f} "
                    f"({guards.stop_loss_pct:.2%} equity)"
                )
            if take_profit_usdt > 0 and pnl >= take_profit_usdt:
                return (
                    f"take_profit_pct_hit: {pnl:.2f} >= {take_profit_usdt:.2f} "
                    f"({guards.take_profit_pct:.2%} equity)"
                )
        elif guards.enable_pnl_usdt_exit:
            if guards.stop_loss_usdt > 0 and pnl <= -guards.stop_loss_usdt:
                return f"stop_loss_usdt_hit: {pnl:.2f} <= -{guards.stop_loss_usdt:.2f}"
            if guards.take_profit_usdt > 0 and pnl >= guards.take_profit_usdt:
                return f"take_profit_usdt_hit: {pnl:.2f} >= {guards.take_profit_usdt:.2f}"

        if guards.enable_trailing_stop_exit and guards.trailing_stop_pct > 0 and peak > 0:
            min_peak_pct = getattr(guards, "trailing_stop_min_peak_pct", Decimal("0.003"))
            min_peak_usdt = equity * min_peak_pct if equity > 0 else Decimal("0")
            if peak >= min_peak_usdt:
                retrace = peak - pnl
                threshold = peak * guards.trailing_stop_pct
                if retrace >= threshold:
                    return (
                        f"trailing_stop_hit: retrace {retrace:.2f} >= {threshold:.2f} "
                        f"(peak {peak:.2f}, pct {guards.trailing_stop_pct:.2%})"
                    )
        return None

    async def _handle_reduce_only_zero_position(self, signal: Signal) -> None:
        if not self._position_manager:
            return
        await self._sync_positions_and_reconcile([signal.symbol])
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
            await self._sync_positions_and_reconcile([signal.symbol])
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
        await logger.ainfo("close_event_source", symbol=signal.symbol, source="size_delta")
        self._missing_position_counts.pop(signal.symbol, None)
        self._update_positions_snapshot()
