import asyncio
from datetime import datetime, timezone

import structlog

from monitoring.telegram_bot import TelegramFormatter

logger = structlog.get_logger("orchestrator_loops")


class OrchestratorLoopsMixin:
    async def _candle_poll_loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                for symbol in self._symbols:
                    await self._poll_and_analyze(symbol)
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("candle_poll_error", error=str(exc))
                await asyncio.sleep(30)

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
                                "🕛 Новый торговый день: дневные risk-ограничения сброшены.",
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
                    await self._position_manager.sync_positions()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("balance_poll_error", error=str(exc))

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
