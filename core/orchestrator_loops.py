import asyncio
from datetime import datetime, timezone
from pathlib import Path

import structlog

from core.event_bus import Event, EventType
from monitoring.telegram_bot import TelegramFormatter

logger = structlog.get_logger("orchestrator_loops")


class OrchestratorLoopsMixin:
    async def _candle_poll_loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                for symbol in self._symbols:
                    await self._poll_and_analyze(symbol)
                await asyncio.sleep(120)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("candle_poll_error", error=str(exc))
                await asyncio.sleep(120)

    async def _ws_kline_handler(self, event: Event) -> None:
        symbol = event.payload.get("symbol")
        if not symbol or not self._candle_buffer:
            return
        raw_data = event.payload.get("data")
        if not raw_data:
            return
        try:
            from exchange.models import Candle
            from decimal import Decimal
            for row in raw_data:
                candle = Candle(
                    symbol=symbol,
                    timeframe=event.payload.get("timeframe", "15m"),
                    open_time=int(row[0]),
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                )
                self._candle_buffer.update(symbol, candle)
            await self._poll_and_analyze(symbol)
        except Exception as exc:
            await logger.aerror("ws_kline_handler_error", symbol=symbol, error=str(exc))

    async def _balance_poll_loop(self) -> None:
        was_halted = False
        while True:
            try:
                await asyncio.sleep(120)
                now_date = datetime.now(timezone.utc).date()
                if self._account_manager and self._risk_manager:
                    if now_date > self._last_daily_reset_date:
                        self._risk_manager.reset_daily()
                        self._last_daily_reset_date = now_date
                        if self._telegram_sink:
                            await self._telegram_sink.send_message_now(
                                "🕛 *Новый торговый день*\n─────────────────────\nДневные лимиты сброшены",
                            )
                    balance = await self._account_manager.sync_balance()
                    self._risk_manager.update_equity(balance.total_equity)
                    is_halted = self._risk_manager.drawdown_monitor.is_halted
                    if is_halted and not was_halted:
                        self._trading_paused = True
                        was_halted = True
                        await logger.awarning("trading_halted_drawdown")
                        if self._telegram_sink:
                            dd = self._account_manager.current_drawdown_pct
                            await self._telegram_sink.send_message_now(
                                TelegramFormatter.format_risk_alert(
                                    reason=self._risk_manager.drawdown_monitor.halt_reason,
                                    current_drawdown=dd,
                                    max_drawdown=self._risk_manager._settings.max_drawdown_pct,
                                )
                            )
                    if now_date > self._last_digest_date and self._telegram_sink:
                        await self._telegram_sink.send_message_now(
                            await self._build_daily_digest(),
                        )
                        self._last_digest_date = now_date
                if self._position_manager:
                    await self._sync_positions_and_reconcile()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("balance_poll_error", error=str(exc))

    async def _trading_stop_worker_loop(self) -> None:
        while True:
            try:
                await self._process_pending_trading_stops()
                await asyncio.sleep(max(0.2, self._settings.trading_stop.retry_interval_sec))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("trading_stop_worker_error", error=str(exc))
                await asyncio.sleep(2)

    async def _equity_snapshot_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(300)
                if not self._account_manager or not self._journal or not self._position_manager:
                    continue
                balance = self._account_manager.balance
                if not balance:
                    continue
                await self._journal.log_equity_snapshot(
                    timestamp=datetime.now(timezone.utc),
                    total_equity=balance.total_equity,
                    available_balance=balance.total_available_balance,
                    unrealized_pnl=balance.total_unrealized_pnl,
                    open_position_count=self._position_manager.open_position_count,
                    peak_equity=self._account_manager.peak_equity,
                    drawdown_pct=self._account_manager.current_drawdown_pct,
                    session_id=self._session_id,
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("equity_snapshot_error", error=str(exc))

    async def _telegram_poll_loop(self) -> None:
        await asyncio.sleep(3)
        while True:
            try:
                await self._telegram_sink.poll_and_handle()
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("telegram_poll_error", error=str(exc))
                await asyncio.sleep(10)

    async def _dashboard_update_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(10)
                if not self._dashboard:
                    continue
                ds = self._dashboard.state
                ds.signals_count = self._signals_count
                ds.trades_count = self._trades_count
                if self._account_manager:
                    ds.equity = self._account_manager.equity
                    ds.peak_equity = self._account_manager.peak_equity
                    ds.drawdown_pct = self._account_manager.current_drawdown_pct
                if self._position_manager:
                    ds.open_positions = [
                        {
                            "symbol": p.symbol,
                            "side": str(p.side),
                            "size": float(p.size),
                            "entry_price": float(p.entry_price),
                            "mark_price": float(p.mark_price),
                            "unrealized_pnl": float(p.unrealized_pnl),
                        }
                        for p in self._position_manager.get_all_positions()
                        if p.size > 0
                    ]
                    ds.unrealized_pnl = self._position_manager.total_unrealized_pnl
                if self._risk_manager:
                    ds.risk_state = self._risk_manager.risk_state()
                ds.bot_state = "paused" if self._trading_paused else "running"
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("dashboard_update_error", error=str(exc))

    async def _rebalance_loop(self) -> None:
        await asyncio.sleep(60)
        while True:
            try:
                await asyncio.sleep(6 * 3600)
                if not self._portfolio_manager or not self._strategy_selector:
                    continue
                if self._account_manager:
                    balance = await self._account_manager.sync_balance()
                    self._portfolio_manager.update_equity(balance.total_equity)
                self._portfolio_manager.calculate_target_allocation(method="performance")
                if not self._portfolio_manager.check_rebalance_needed():
                    continue
                actions = self._portfolio_manager.execute_rebalance()
                if not actions:
                    continue
                new_allocs = self._portfolio_manager.current_allocations
                self._strategy_selector.update_strategy_weights(new_allocs)
                await logger.ainfo("portfolio_rebalanced", actions=len(actions))
                if self._telegram_sink:
                    lines = [f"  `{a.strategy_name}`: {float(a.delta_pct * 100):+.1f}%" for a in actions[:8]]
                    await self._telegram_sink.send_message_now(
                        f"📊 *Ребалансировка портфеля*\n"
                        f"─────────────────────\n" + "\n".join(lines)
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("rebalance_loop_error", error=str(exc))

    async def _ml_retrain_loop(self) -> None:
        await asyncio.sleep(60)
        while True:
            try:
                now = datetime.now(timezone.utc)
                seconds_until_3am = ((3 - now.hour) % 24) * 3600 - now.minute * 60 - now.second
                if seconds_until_3am <= 0:
                    seconds_until_3am += 86400
                await asyncio.sleep(seconds_until_3am)
                await self._run_ml_retrain()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("ml_retrain_loop_error", error=str(exc))
                await asyncio.sleep(3600)

    async def _run_ml_retrain(self) -> None:
        await logger.ainfo("ml_retrain_started")
        try:
            result = await asyncio.to_thread(self._ml_retrain_sync)
            await logger.ainfo("ml_retrain_finished", **result)
            if result.get("status") == "trained" and result.get("model_id"):
                await self._load_ml_model()
                if self._telegram_sink:
                    acc = result.get("test_accuracy", 0)
                    cv = result.get("cv_accuracy", 0)
                    n = result.get("samples", 0)
                    await self._telegram_sink.send_message_now(
                        f"🧠 *ML модель обновлена*\n"
                        f"─────────────────────\n"
                        f"📊 Сэмплов: `{n}`\n"
                        f"🎯 Accuracy: `{acc:.4f}`\n"
                        f"📈 CV Accuracy: `{cv:.4f}`\n"
                        f"🆔 Модель: `{result.get('model_id')}`"
                    )
            elif result.get("status") == "trained" and self._telegram_sink:
                acc = result.get("test_accuracy", 0)
                await self._telegram_sink.send_message_now(
                    f"🧠 *ML обучение завершено*\n"
                    f"─────────────────────\n"
                    f"⚠️ Модель НЕ сохранена (accuracy `{acc:.4f}` <= 0.52)"
                )
        except Exception as exc:
            await logger.aerror("ml_retrain_failed", error=str(exc))

    def _ml_retrain_sync(self) -> dict:
        from scripts.enrich_and_train import enrich_and_train

        db_path = self._journal_path
        data_dir = self._settings.data_dir
        model_dir = data_dir / self._settings.ml.model_dir
        return enrich_and_train(
            db_path=db_path,
            data_dir=data_dir,
            model_dir=model_dir,
            min_samples=100,
        )
