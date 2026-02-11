from decimal import Decimal
from datetime import datetime, timedelta, timezone

from monitoring.telegram_bot import TelegramFormatter, SEPARATOR, _fmt_usd, _fmt_pct, _pnl_emoji
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
            return f"⚠️ Менеджер позиций недоступен"
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
            state = self._risk_manager.risk_state()
            state_icon = "🟢" if state == "normal" else "🟡" if state == "caution" else "🔴"
            message += f"\n\n{state_icon} Риск: `{state}`"
            block_reason = self._risk_manager.block_reason()
            if block_reason:
                message += f"\n⛔ Блокировка: `{block_reason}`"
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
        dd_icon = "🟢" if dd < Decimal("0.05") else "🟡" if dd < Decimal("0.10") else "🔴"

        if risk_limit is not None:
            dd_status = "ОК" if dd < risk_limit else "ПРЕВЫШЕН"
            risk_line = f"{dd_icon} Просадка: `{_fmt_pct(dd)}` / лимит `{_fmt_pct(risk_limit)}` — {dd_status}"
        else:
            risk_line = f"{dd_icon} Просадка: `{_fmt_pct(dd)}`"

        total_icon = _pnl_emoji(total_today)
        realized_icon = _pnl_emoji(realized_today)
        unrealized_icon = _pnl_emoji(unrealized)

        state = self._risk_manager.risk_state() if self._risk_manager else "N/A"
        state_icon = "🟢" if state == "normal" else "🟡" if state == "caution" else "🔴"

        summary = (
            f"💰 *Сводка PnL*\n"
            f"{SEPARATOR}\n"
            f"💎 Эквити: `{_fmt_usd(equity)} USDT`\n"
            f"🏔 Пик: `{_fmt_usd(peak)} USDT`\n"
            f"{risk_line}\n"
            f"{SEPARATOR}\n"
            f"{realized_icon} Реализ. (день): `{_fmt_usd(realized_today, sign=True)} USDT`\n"
            f"{unrealized_icon} Нереализ.: `{_fmt_usd(unrealized, sign=True)} USDT` ({float(unrealized_pct):.2f}%)\n"
            f"{total_icon} Итого за день: `{_fmt_usd(total_today, sign=True)} USDT`\n"
            f"{SEPARATOR}\n"
            f"{state_icon} Риск: `{state}`\n"
            f"📡 Сигналов: `{int(daily['signals'])}` | Сделок: `{int(daily['trades'])}`"
        )

        if self._risk_manager:
            block_reason = self._risk_manager.block_reason()
            if block_reason:
                summary += f"\n⛔ Блокировка: `{block_reason}`"

        if not self._position_manager:
            return f"{summary}\n\n📋 *Позиции*\n_Нет открытых позиций_"

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
        return f"⏸ *Торговля ПРИОСТАНОВЛЕНА*\n{SEPARATOR}\nДля продолжения: /resume"

    async def _cmd_resume(self) -> str:
        self._trading_paused = False
        return f"▶️ *Торговля ВОЗОБНОВЛЕНА*\n{SEPARATOR}\nБот снова принимает сигналы"

    async def _cmd_risk(self) -> str:
        if not self._risk_manager:
            return "⚠️ Риск-менеджер недоступен"
        s = self._risk_manager._settings
        dd = self._account_manager.current_drawdown_pct if self._account_manager else Decimal(0)
        dd_icon = "🟢" if dd < Decimal("0.05") else "🟡" if dd < Decimal("0.10") else "🔴"
        state = self._risk_manager.risk_state()
        state_icon = "🟢" if state == "normal" else "🟡" if state == "caution" else "🔴"
        paused = "⏸ ДА" if self._trading_paused else "▶️ НЕТ"
        return (
            f"🛡 *Риск-параметры*\n"
            f"{SEPARATOR}\n"
            f"📊 Риск на сделку: `{_fmt_pct(s.max_risk_per_trade)}`\n"
            f"📊 Риск портфеля: `{_fmt_pct(s.max_portfolio_risk)}`\n"
            f"📉 Лимит просадки: `{_fmt_pct(s.max_drawdown_pct)}`\n"
            f"{dd_icon} Текущая просадка: `{_fmt_pct(dd)}`\n"
            f"{SEPARATOR}\n"
            f"⚡ Макс. плечо: `{s.max_leverage}x`\n"
            f"📂 Макс. позиций: `{s.max_concurrent_positions}`\n"
            f"🔌 Предохранитель: `{s.circuit_breaker_consecutive_losses} подряд → пауза {s.circuit_breaker_cooldown_hours}ч`\n"
            f"{SEPARATOR}\n"
            f"{state_icon} Риск: `{state}`\n"
            f"Торговля: {paused}"
        )

    async def _cmd_guard(self) -> str:
        if not self._risk_manager:
            return "⚠️ Risk guard недоступен"
        s = self._risk_manager._settings
        state = self._risk_manager.risk_state()
        reason = self._risk_manager.block_reason() or "нет"
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        g = self._settings.risk_guards
        tp_est = equity * g.take_profit_pct if equity > 0 else Decimal(0)
        sl_est = equity * g.stop_loss_pct if equity > 0 else Decimal(0)

        state_icon = "🟢" if state == "normal" else "🟡" if state == "caution" else "🔴"

        def _on_off(val: bool) -> str:
            return "✅" if val else "❌"

        return (
            f"🧯 *Risk Guard*\n"
            f"{SEPARATOR}\n"
            f"{state_icon} Состояние: `{state}`\n"
            f"⛔ Блокировка: `{reason}`\n"
            f"{SEPARATOR}\n"
            f"{_on_off(s.enable_circuit_breaker)} Предохранитель: "
            f"`{s.circuit_breaker_consecutive_losses} подряд / {s.circuit_breaker_cooldown_hours}ч`\n"
            f"{_on_off(s.enable_daily_loss_limit)} Дневной лимит: "
            f"`{_fmt_pct(s.max_daily_loss_pct)}`\n"
            f"{_on_off(s.enable_symbol_cooldown)} Cooldown: "
            f"`{s.symbol_cooldown_minutes} мин`\n"
            f"{SEPARATOR}\n"
            f"{_on_off(g.enable_max_hold_exit)} Max hold: `{g.max_hold_minutes} мин`\n"
            f"{_on_off(g.enable_pnl_pct_exit)} PnL exits: "
            f"TP `{_fmt_pct(g.take_profit_pct)}` (~{_fmt_usd(tp_est)}) | "
            f"SL `{_fmt_pct(g.stop_loss_pct)}` (~{_fmt_usd(sl_est)})\n"
            f"{_on_off(g.enable_trailing_stop_exit)} Trailing: "
            f"`{float(g.trailing_stop_pct * 100):.1f}%` retrace\n"
            f"{SEPARATOR}\n"
            f"🔀 Soft stop: `{_fmt_pct(s.soft_stop_threshold_pct)}` (conf {s.soft_stop_min_confidence:.2f})\n"
            f"🔥 Portfolio heat: `{_fmt_pct(s.portfolio_heat_limit_pct)}`\n"
            f"{_on_off(s.enable_directional_exposure_limit)} Direction limit: "
            f"`{_fmt_pct(s.max_directional_exposure_pct)}`\n"
            f"{_on_off(s.enable_side_balancer)} Side balancer: "
            f"streak `{s.max_side_streak}` / imbalance `{_fmt_pct(s.side_imbalance_pct)}`"
        )

    async def _cmd_close_ready(self, args: list[str]) -> str:
        if not args:
            return (
                f"🩺 *Диагностика закрытия*\n"
                f"{SEPARATOR}\n"
                f"Использование: `/close_ready <symbol>`\n"
                f"Пример: `/close_ready SOL/USDT:USDT`"
            )
        symbol_input = args[0]
        symbol = self._resolve_symbol(symbol_input)
        if not symbol:
            return f"⚠️ Символ `{symbol_input}` не найден"

        if not self._position_manager:
            return "⚠️ Менеджер позиций недоступен"
        position = self._position_manager.get_position(symbol)
        if not position or position.size <= 0:
            return f"📋 По `{symbol}` нет открытой позиции"
        if not self._rest_api or not self._preprocessor or not self._feature_engineer or not self._strategy_selector:
            return "⚠️ Рыночные компоненты не инициализированы"

        candles = await self._rest_api.fetch_ohlcv(symbol, timeframe="15m", limit=120)
        if not candles:
            return f"⚠️ Недостаточно данных по `{symbol}`"
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
                checks.append(f"  ⚪ `{strategy.name}` — нет сигнала")
                continue
            sig_icon = "🟢" if signal.direction == expected_close else "🔵"
            checks.append(f"  {sig_icon} `{strategy.name}` — {signal.direction.value} ({signal.confidence:.2f})")
            if signal.direction == expected_close:
                close_candidates.append(signal)

        checks_text = "\n".join(checks[:8]) if checks else "  _нет активных стратегий_"

        if not close_candidates:
            return (
                f"🩺 *Диагностика закрытия*\n"
                f"{SEPARATOR}\n"
                f"📍 Символ: `{symbol}`\n"
                f"📂 Позиция: `{position.side}` x `{position.size}`\n"
                f"🔴 Статус: `NOT READY`\n"
                f"Причина: нет сигнала `{expected_close.value}`\n"
                f"{SEPARATOR}\n"
                f"Стратегии:\n{checks_text}"
            )

        best = sorted(close_candidates, key=lambda s: s.confidence, reverse=True)[0]
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        positions = self._position_manager.get_all_positions()
        decision = self._risk_manager.evaluate_signal(best, equity, positions) if self._risk_manager else None
        if decision and not decision.approved:
            return (
                f"🩺 *Диагностика закрытия*\n"
                f"{SEPARATOR}\n"
                f"📍 Символ: `{symbol}`\n"
                f"🟡 Статус: `BLOCKED`\n"
                f"⛔ Причина: `{decision.reason}`\n"
                f"Совет: проверьте /guard и /risk"
            )
        qty = decision.quantity if decision else position.size
        return (
            f"🩺 *Диагностика закрытия*\n"
            f"{SEPARATOR}\n"
            f"📍 Символ: `{symbol}`\n"
            f"🟢 Статус: `READY`\n"
            f"📐 Стратегия: `{best.strategy_name}` ({best.confidence:.2f})\n"
            f"📦 Объём закрытия: `{qty}`"
        )

    async def _cmd_entry_ready(self, args: list[str]) -> str:
        if not args:
            return (
                f"🩺 *Диагностика входа*\n"
                f"{SEPARATOR}\n"
                f"Использование: `/entry_ready <symbol>`\n"
                f"Пример: `/entry_ready BTC/USDT:USDT`"
            )
        symbol_input = args[0]
        symbol = self._resolve_symbol(symbol_input)
        if not symbol:
            return f"⚠️ Символ `{symbol_input}` не найден"
        if not self._rest_api or not self._preprocessor or not self._feature_engineer or not self._strategy_selector:
            return "⚠️ Рыночные компоненты не инициализированы"

        candles = await self._rest_api.fetch_ohlcv(symbol, timeframe="15m", limit=120)
        if not candles:
            return f"⚠️ Недостаточно данных по `{symbol}`"
        df = self._preprocessor.candles_to_dataframe(candles)
        await self._refresh_funding_rate(symbol)
        df = self._apply_funding_rate_column(symbol, df)
        df = self._feature_engineer.build_features(df)

        signal = self._strategy_selector.get_best_signal(symbol, df)
        if not signal:
            return (
                f"🩺 *Диагностика входа*\n"
                f"{SEPARATOR}\n"
                f"📍 Символ: `{symbol}`\n"
                f"🔴 Статус: `NOT READY`\n"
                f"Причина: нет входного сигнала"
            )
        if signal.direction not in (SignalDirection.LONG, SignalDirection.SHORT):
            return (
                f"🩺 *Диагностика входа*\n"
                f"{SEPARATOR}\n"
                f"📍 Символ: `{symbol}`\n"
                f"🔴 Статус: `NOT READY`\n"
                f"Причина: топ-сигнал — закрытие `{signal.direction.value}`"
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

        dir_emoji = "🟢" if signal.direction == SignalDirection.LONG else "🔴"
        sig_line = f"{dir_emoji} `{signal.strategy_name}` — {signal.direction.value} ({signal.confidence:.2f})"
        mtf_ema50 = mtf_meta.get("mtf_ema50", 0.0)
        mtf_ema200 = mtf_meta.get("mtf_ema200", 0.0)
        mtf_adx = mtf_meta.get("mtf_adx", 0.0)

        if not mtf_ok:
            return (
                f"🩺 *Диагностика входа*\n"
                f"{SEPARATOR}\n"
                f"📍 Символ: `{symbol}`\n"
                f"🟡 Статус: `BLOCKED`\n"
                f"⛔ MTF: `{mtf_reason}`\n"
                f"{SEPARATOR}\n"
                f"Сигнал: {sig_line}\n"
                f"MTF: ema50 `{mtf_ema50:.4f}` | ema200 `{mtf_ema200:.4f}` | adx `{mtf_adx:.2f}`\n"
                f"🔀 Side: `{side_info['verdict']}` | streak `{side_info['streak_side']}:{side_info['streak_count']}` | imb `{float(Decimal(side_info['imbalance_pct']) * 100):.1f}%`"
            )

        if decision and not decision.approved:
            return (
                f"🩺 *Диагностика входа*\n"
                f"{SEPARATOR}\n"
                f"📍 Символ: `{symbol}`\n"
                f"🟡 Статус: `BLOCKED`\n"
                f"⛔ Риск: `{decision.reason}`\n"
                f"{SEPARATOR}\n"
                f"Сигнал: {sig_line}\n"
                f"🔀 Side: `{side_info['verdict']}` | streak `{side_info['streak_side']}:{side_info['streak_count']}` | imb `{float(Decimal(side_info['imbalance_pct']) * 100):.1f}%`"
            )
        qty = decision.quantity if decision else Decimal("0")
        return (
            f"🩺 *Диагностика входа*\n"
            f"{SEPARATOR}\n"
            f"📍 Символ: `{symbol}`\n"
            f"🟢 Статус: `READY`\n"
            f"Сигнал: {sig_line}\n"
            f"MTF: `passed` (ema50 `{mtf_ema50:.4f}` | ema200 `{mtf_ema200:.4f}` | adx `{mtf_adx:.2f}`)\n"
            f"🔀 Side: `{side_info['verdict']}` | streak `{side_info['streak_side']}:{side_info['streak_count']}` | imb `{float(Decimal(side_info['imbalance_pct']) * 100):.1f}%`\n"
            f"📦 Размер: `{qty}`"
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
        state_icon = "🟢" if state == "normal" else "🟡" if state == "caution" else "🔴"
        dd_icon = "🟢" if dd < Decimal("0.05") else "🟡" if dd < Decimal("0.10") else "🔴"
        return (
            f"🗓 *Дневной отчёт*\n"
            f"{SEPARATOR}\n"
            f"💎 Эквити: `{_fmt_usd(equity)} USDT`\n"
            f"{dd_icon} Просадка: `{_fmt_pct(dd)}`\n"
            f"💵 Нереализ.: `{_fmt_usd(unrealized, sign=True)} USDT`\n"
            f"📡 Сигналы/Сделки: `{int(daily['signals'])}` / `{int(daily['trades'])}`\n"
            f"{state_icon} Риск: `{state}`\n"
            f"⛔ Блокировка: `{reason or 'нет'}`"
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
