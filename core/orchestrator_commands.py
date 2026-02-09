from decimal import Decimal
from datetime import datetime, timedelta, timezone

from monitoring.telegram_bot import TelegramFormatter
from strategies.base_strategy import SignalDirection


class OrchestratorCommandsMixin:
    async def _cmd_status(self) -> str:
        await self._sync_for_reporting()
        daily = await self._get_daily_stats()
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        pos_count = self._position_manager.open_position_count if self._position_manager else 0
        state = "PAUSED" if self._trading_paused else "RUNNING"
        strategies = list(self._strategy_selector.strategies.keys()) if self._strategy_selector else []
        return TelegramFormatter.format_status(
            bot_state=state,
            equity=equity,
            open_positions=pos_count,
            daily_pnl=daily["realized_pnl"],
            active_strategies=strategies,
            session_id=self._session_id,
            signals_count=int(daily["signals"]),
            trades_count=int(daily["trades"]),
        )

    async def _cmd_positions(self) -> str:
        await self._sync_for_reporting()
        if not self._position_manager:
            return "Менеджер позиций недоступен."
        positions = self._position_manager.get_all_positions()
        pos_data = [
            {
                "symbol": p.symbol,
                "side": p.side.value if hasattr(p.side, "value") else str(p.side),
                "size": p.size,
                "entry": p.entry_price,
                "pnl": p.unrealized_pnl,
                "mark": p.mark_price,
                "liq": p.liquidation_price,
                "leverage": p.leverage,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "tpsl_status": self._tpsl_status_for_symbol(p.symbol, p.stop_loss, p.take_profit),
            }
            for p in positions
            if p.size > 0
        ]
        message = TelegramFormatter.format_positions(pos_data)
        if self._risk_manager:
            message = f"{message}\n\nСостояние риска: `{self._risk_manager.risk_state()}`"
            block_reason = self._risk_manager.block_reason()
            if block_reason:
                message += f"\nПричина ограничения: `{block_reason}`"
        return message

    async def _cmd_pnl(self) -> str:
        await self._sync_for_reporting()
        daily = await self._get_daily_stats()
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        peak = self._account_manager.peak_equity if self._account_manager else Decimal(0)
        dd = self._account_manager.current_drawdown_pct if self._account_manager else Decimal(0)
        unrealized = self._position_manager.total_unrealized_pnl if self._position_manager else Decimal(0)
        unrealized_pct = (unrealized / equity * 100) if equity > 0 else Decimal(0)
        realized_today = daily["realized_pnl"]
        total_today = realized_today + unrealized

        risk_limit = self._risk_manager._settings.max_drawdown_pct if self._risk_manager else None
        if risk_limit is not None:
            status = "в пределах лимита" if dd < risk_limit else "превышен лимит"
            risk_line = (
                f"Оценка: нереализованный PnL `{unrealized:.2f} USDT` "
                f"({unrealized_pct:.2f}% эквити) — {status} просадки `{risk_limit * 100:.1f}%`"
            )
        else:
            risk_line = (
                f"Оценка: нереализованный PnL `{unrealized:.2f} USDT` "
                f"({unrealized_pct:.2f}% эквити) — лимит просадки недоступен"
            )

        summary = (
            f"💰 *Сводка PnL*\n"
            f"Текущее эквити: `{equity:.2f} USDT`\n"
            f"Пиковое эквити: `{peak:.2f} USDT`\n"
            f"Просадка: `{dd * 100:.2f}%`\n"
            f"Реализованный PnL (день UTC): `{realized_today:.2f} USDT`\n"
            f"Нереализованный PnL: `{unrealized:.2f} USDT` ({unrealized_pct:.2f}% эквити)\n"
            f"Итого за день (realized+unrealized): `{total_today:.2f} USDT`\n"
            f"Risk state: `{self._risk_manager.risk_state() if self._risk_manager else 'N/A'}`\n"
            f"Сигналы: `{int(daily['signals'])}`\n"
            f"Сделки: `{int(daily['trades'])}`\n"
            f"{risk_line}"
        )

        if self._risk_manager:
            block_reason = self._risk_manager.block_reason()
            if block_reason:
                summary += f"\nПричина ограничения: `{block_reason}`"

        if not self._position_manager:
            return f"{summary}\n\n📋 *Открытые позиции*\n\nНет открытых позиций."

        positions = self._position_manager.get_all_positions()
        pos_data = [
            {
                "symbol": p.symbol,
                "side": p.side.value if hasattr(p.side, "value") else str(p.side),
                "size": p.size,
                "entry": p.entry_price,
                "pnl": p.unrealized_pnl,
                "mark": p.mark_price,
                "liq": p.liquidation_price,
                "leverage": p.leverage,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "tpsl_status": self._tpsl_status_for_symbol(p.symbol, p.stop_loss, p.take_profit),
            }
            for p in positions
            if p.size > 0
        ]
        return f"{summary}\n\n{TelegramFormatter.format_positions(pos_data)}"

    async def _cmd_pause(self) -> str:
        self._trading_paused = True
        return "⏸ Торговля *ПРИОСТАНОВЛЕНА*. Используйте /resume для продолжения."

    async def _cmd_resume(self) -> str:
        self._trading_paused = False
        return "▶️ Торговля *ВОЗОБНОВЛЕНА*."

    async def _cmd_risk(self) -> str:
        if not self._risk_manager:
            return "Риск-менеджер недоступен."
        s = self._risk_manager._settings
        dd = self._account_manager.current_drawdown_pct if self._account_manager else Decimal(0)
        return (
            f"🛡 *Риск-параметры*\n"
            f"Риск на сделку: `{s.max_risk_per_trade * 100:.1f}%`\n"
            f"Риск портфеля: `{s.max_portfolio_risk * 100:.1f}%`\n"
            f"Лимит просадки: `{s.max_drawdown_pct * 100:.1f}%`\n"
            f"Текущая просадка: `{dd * 100:.2f}%`\n"
            f"Макс. плечо: `{s.max_leverage}x`\n"
            f"Макс. позиций: `{s.max_concurrent_positions}`\n"
            f"Предохранитель: `{s.circuit_breaker_consecutive_losses} убыточных → пауза {s.circuit_breaker_cooldown_hours}ч`\n"
            f"Торговля на паузе: `{'ДА' if self._trading_paused else 'НЕТ'}`\n"
            f"Risk state: `{self._risk_manager.risk_state()}`"
        )

    async def _cmd_guard(self) -> str:
        if not self._risk_manager:
            return "Risk guard недоступен."
        s = self._risk_manager._settings
        state = self._risk_manager.risk_state()
        reason = self._risk_manager.block_reason() or "нет"
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        tp_est = equity * self._settings.risk_guards.take_profit_pct if equity > 0 else Decimal(0)
        sl_est = equity * self._settings.risk_guards.stop_loss_pct if equity > 0 else Decimal(0)
        return (
            f"🧯 *Risk Guard*\n"
            f"Состояние: `{state}`\n"
            f"Circuit breaker: `{'ON' if s.enable_circuit_breaker else 'OFF'}` "
            f"({s.circuit_breaker_consecutive_losses} / {s.circuit_breaker_cooldown_hours}ч)\n"
            f"Дневной лимит: `{'ON' if s.enable_daily_loss_limit else 'OFF'}` "
            f"({s.max_daily_loss_pct * 100:.2f}%)\n"
            f"Soft stop: `{s.soft_stop_threshold_pct * 100:.0f}%` "
            f"min confidence `{s.soft_stop_min_confidence:.2f}`\n"
            f"Cooldown symbol: `{'ON' if s.enable_symbol_cooldown else 'OFF'}` "
            f"({s.symbol_cooldown_minutes} мин)\n"
            f"Portfolio heat: `{s.portfolio_heat_limit_pct * 100:.2f}%`\n"
            f"Max hold exit: `{'ON' if self._settings.risk_guards.enable_max_hold_exit else 'OFF'}` "
            f"({self._settings.risk_guards.max_hold_minutes} мин)\n"
            f"PnL exits (% equity): `{'ON' if self._settings.risk_guards.enable_pnl_pct_exit else 'OFF'}` "
            f"(TP {self._settings.risk_guards.take_profit_pct * 100:.2f}% ~ {tp_est:.2f} USDT, "
            f"SL {self._settings.risk_guards.stop_loss_pct * 100:.2f}% ~ {sl_est:.2f} USDT)\n"
            f"Trailing exit: `{'ON' if self._settings.risk_guards.enable_trailing_stop_exit else 'OFF'}` "
            f"({self._settings.risk_guards.trailing_stop_pct * 100:.1f}% retrace)\n"
            f"Directional limit: `{'ON' if s.enable_directional_exposure_limit else 'OFF'}` "
            f"({s.max_directional_exposure_pct * 100:.1f}% на сторону)\n"
            f"Side balancer: `{'ON' if s.enable_side_balancer else 'OFF'}` "
            f"(streak {s.max_side_streak}, imbalance {s.side_imbalance_pct * 100:.1f}%)\n"
            f"Причина блокировки: `{reason}`"
        )

    async def _cmd_close_ready(self, args: list[str]) -> str:
        if not args:
            return "Использование: `/close_ready <symbol>`\nПример: `/close_ready SOL/USDT:USDT`"
        symbol_input = args[0]
        symbol = self._resolve_symbol(symbol_input)
        if not symbol:
            return f"Символ `{symbol_input}` не найден в активном списке."

        if not self._position_manager:
            return "Менеджер позиций недоступен."
        position = self._position_manager.get_position(symbol)
        if not position or position.size <= 0:
            return f"По `{symbol}` нет открытой позиции."
        if not self._rest_api or not self._preprocessor or not self._feature_engineer or not self._strategy_selector:
            return "Диагностика недоступна: не инициализированы рыночные компоненты."

        candles = await self._rest_api.fetch_ohlcv(symbol, timeframe="15m", limit=120)
        if not candles:
            return f"Недостаточно данных по `{symbol}` для диагностики."
        df = self._preprocessor.candles_to_dataframe(candles)
        await self._refresh_funding_rate(symbol)
        df = self._apply_funding_rate_column(symbol, df)
        df = self._feature_engineer.build_features(df)

        expected_close = (
            SignalDirection.CLOSE_LONG
            if str(position.side).lower() == "long"
            else SignalDirection.CLOSE_SHORT
        )
        checks: list[str] = []
        close_candidates = []

        for strategy in self._strategy_selector.select_strategies(df):
            if symbol not in strategy.symbols:
                continue
            signal = strategy.generate_signal(symbol, df)
            if not signal:
                checks.append(f"- `{strategy.name}`: сигнала нет")
                continue
            checks.append(f"- `{strategy.name}`: {signal.direction.value} (conf {signal.confidence:.2f})")
            if signal.direction == expected_close:
                close_candidates.append(signal)

        if not close_candidates:
            checks_text = "\n".join(checks[:8]) if checks else "- нет активных стратегий для символа"
            return (
                f"🩺 *Close Readiness*\n"
                f"Символ: `{symbol}`\n"
                f"Позиция: `{position.side}` size `{position.size}`\n"
                f"Статус: `NOT READY`\n"
                f"Причина: нет close-сигнала для `{expected_close.value}`\n"
                f"Проверки:\n{checks_text}"
            )

        best = sorted(close_candidates, key=lambda s: s.confidence, reverse=True)[0]
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        positions = self._position_manager.get_all_positions()
        decision = self._risk_manager.evaluate_signal(best, equity, positions) if self._risk_manager else None
        if decision and not decision.approved:
            return (
                f"🩺 *Close Readiness*\n"
                f"Символ: `{symbol}`\n"
                f"Статус: `BLOCKED`\n"
                f"Причина: `{decision.reason}`\n"
                f"Рекомендация: проверить /guard и /risk"
            )
        qty = decision.quantity if decision else position.size
        return (
            f"🩺 *Close Readiness*\n"
            f"Символ: `{symbol}`\n"
            f"Статус: `READY`\n"
            f"Close signal: `{best.strategy_name}` ({best.confidence:.2f})\n"
            f"Ожидаемый объём закрытия: `{qty}`"
        )

    async def _cmd_entry_ready(self, args: list[str]) -> str:
        if not args:
            return "Использование: `/entry_ready <symbol>`\nПример: `/entry_ready BTC/USDT:USDT`"
        symbol_input = args[0]
        symbol = self._resolve_symbol(symbol_input)
        if not symbol:
            return f"Символ `{symbol_input}` не найден в активном списке."
        if not self._rest_api or not self._preprocessor or not self._feature_engineer or not self._strategy_selector:
            return "Диагностика недоступна: не инициализированы рыночные компоненты."

        candles = await self._rest_api.fetch_ohlcv(symbol, timeframe="15m", limit=120)
        if not candles:
            return f"Недостаточно данных по `{symbol}` для диагностики."
        df = self._preprocessor.candles_to_dataframe(candles)
        await self._refresh_funding_rate(symbol)
        df = self._apply_funding_rate_column(symbol, df)
        df = self._feature_engineer.build_features(df)

        signal = self._strategy_selector.get_best_signal(symbol, df)
        if not signal:
            return (
                f"🩺 *Entry Readiness*\n"
                f"Символ: `{symbol}`\n"
                f"Статус: `NOT READY`\n"
                f"Причина: стратегии не выдали входной сигнал"
            )
        if signal.direction not in (SignalDirection.LONG, SignalDirection.SHORT):
            return (
                f"🩺 *Entry Readiness*\n"
                f"Символ: `{symbol}`\n"
                f"Статус: `NOT READY`\n"
                f"Причина: топ-сигнал является закрытием `{signal.direction.value}`"
            )

        mtf_ok, mtf_reason, mtf_meta = await self._evaluate_mtf_confirm(signal)
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        positions = self._position_manager.get_all_positions() if self._position_manager else []
        decision = self._risk_manager.evaluate_signal(signal, equity, positions) if self._risk_manager else None
        side_info = (
            self._risk_manager.side_balancer_snapshot(positions, equity)
            if self._risk_manager
            else {
                "verdict": "n/a",
                "streak_side": "none",
                "streak_count": 0,
                "imbalance_pct": Decimal("0"),
            }
        )

        if not mtf_ok:
            return (
                f"🩺 *Entry Readiness*\n"
                f"Символ: `{symbol}`\n"
                f"Статус: `BLOCKED`\n"
                f"Причина: `{mtf_reason}`\n"
                f"Signal: `{signal.strategy_name}` ({signal.direction.value}, conf {signal.confidence:.2f})\n"
                f"MTF: ema50 `{mtf_meta.get('mtf_ema50', 0.0):.4f}`, ema200 `{mtf_meta.get('mtf_ema200', 0.0):.4f}`, adx `{mtf_meta.get('mtf_adx', 0.0):.2f}`\n"
                f"Directional guard: `{side_info['verdict']}` | streak `{side_info['streak_side']}:{side_info['streak_count']}` | imbalance `{Decimal(side_info['imbalance_pct']) * 100:.2f}%`"
            )

        if decision and not decision.approved:
            return (
                f"🩺 *Entry Readiness*\n"
                f"Символ: `{symbol}`\n"
                f"Статус: `BLOCKED`\n"
                f"Причина: `{decision.reason}`\n"
                f"Signal: `{signal.strategy_name}` ({signal.direction.value}, conf {signal.confidence:.2f})\n"
                f"Directional guard: `{side_info['verdict']}` | streak `{side_info['streak_side']}:{side_info['streak_count']}` | imbalance `{Decimal(side_info['imbalance_pct']) * 100:.2f}%`"
            )
        qty = decision.quantity if decision else Decimal("0")
        return (
            f"🩺 *Entry Readiness*\n"
            f"Символ: `{symbol}`\n"
            f"Статус: `READY`\n"
            f"Signal: `{signal.strategy_name}` ({signal.direction.value}, conf {signal.confidence:.2f})\n"
            f"MTF: `passed` (ema50 {mtf_meta.get('mtf_ema50', 0.0):.4f}, "
            f"ema200 {mtf_meta.get('mtf_ema200', 0.0):.4f}, adx {mtf_meta.get('mtf_adx', 0.0):.2f})\n"
            f"Directional guard: `{side_info['verdict']}` | streak `{side_info['streak_side']}:{side_info['streak_count']}` | imbalance `{Decimal(side_info['imbalance_pct']) * 100:.2f}%`\n"
            f"Размер: `{qty}`"
        )

    def _resolve_symbol(self, symbol_input: str) -> str | None:
        norm = symbol_input.strip().upper()
        if not self._symbols:
            return None
        for symbol in self._symbols:
            s_norm = symbol.upper()
            flat = s_norm.replace("/", "").replace(":", "")
            if norm == s_norm or norm == flat:
                return symbol
        return None

    def _tpsl_status_for_symbol(
        self,
        symbol: str,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
    ) -> str:
        if stop_loss is not None or take_profit is not None:
            return "confirmed"
        if symbol in self._pending_trading_stops:
            return self._trading_stop_last_status.get(symbol, "pending")
        return self._trading_stop_last_status.get(symbol, "failed")

    async def _cmd_help(self) -> str:
        return TelegramFormatter.format_help()

    async def _build_daily_digest(self) -> str:
        await self._sync_for_reporting()
        daily = await self._get_daily_stats()
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        dd = self._account_manager.current_drawdown_pct if self._account_manager else Decimal(0)
        unrealized = self._position_manager.total_unrealized_pnl if self._position_manager else Decimal(0)
        state = self._risk_manager.risk_state() if self._risk_manager else "N/A"
        reason = self._risk_manager.block_reason() if self._risk_manager else ""
        return (
            f"🗓 *Ежедневный digest*\n"
            f"Equity: `{equity:.2f} USDT`\n"
            f"Drawdown: `{dd * 100:.2f}%`\n"
            f"Unrealized PnL: `{unrealized:.2f} USDT`\n"
            f"Signals/Trades (UTC day): `{int(daily['signals'])}/{int(daily['trades'])}`\n"
            f"Risk state: `{state}`\n"
            f"Причина блокировки: `{reason or 'нет'}`"
        )

    async def _sync_for_reporting(self) -> None:
        if self._account_manager:
            try:
                await self._account_manager.sync_balance()
            except Exception:
                pass
        if self._position_manager:
            try:
                await self._sync_positions_and_reconcile()
            except Exception:
                pass

    async def _get_daily_stats(self) -> dict[str, Decimal | int]:
        defaults: dict[str, Decimal | int] = {
            "signals": self._signals_count,
            "trades": self._trades_count,
            "realized_pnl": Decimal("0"),
        }
        if not self._settings.status.use_journal_daily_agg or not getattr(self, "_journal_reader", None):
            return defaults

        now = datetime.now(timezone.utc)
        if self._daily_stats_cache and (now - self._daily_stats_cache[0]).total_seconds() < 10:
            return self._daily_stats_cache[1]

        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        reader = self._journal_reader
        signals = await reader.count_signals_since(start, end)
        trades = await reader.count_trades_since(start, end)
        realized = await reader.sum_realized_pnl_since(start, end)
        stats = {
            "signals": int(signals),
            "trades": int(trades),
            "realized_pnl": realized,
        }
        self._daily_stats_cache = (now, stats)
        return stats
