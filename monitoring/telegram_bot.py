from collections.abc import Callable, Coroutine
from decimal import Decimal
from enum import StrEnum
from inspect import signature
from typing import Any

import httpx
import structlog

from monitoring.alerts import Alert, AlertSeverity

logger = structlog.get_logger("telegram_bot")


class TelegramCommand(StrEnum):
    STATUS = "/status"
    POSITIONS = "/positions"
    PNL = "/pnl"
    CLOSE_READY = "/close_ready"
    GUARD = "/guard"
    PAUSE = "/pause"
    RESUME = "/resume"
    RISK = "/risk"
    HELP = "/help"


class TelegramFormatter:
    @staticmethod
    def format_alert(alert: Alert) -> str:
        emoji = _severity_emoji(alert.severity)
        return (
            f"{emoji} *{alert.title}*\n"
            f"{alert.message}\n"
            f"Источник: `{alert.source}`"
        )

    @staticmethod
    def format_trade_opened(
        symbol: str, side: str, size: Decimal,
        entry_price: Decimal, stop_loss: Decimal,
        take_profit: Decimal, strategy: str,
    ) -> str:
        arrow = "🟢 ЛОНГ" if side.lower() == "long" else "🔴 ШОРТ"
        return (
            f"{arrow} *{symbol}*\n"
            f"Вход: `{entry_price}`\n"
            f"Размер: `{size}`\n"
            f"SL: `{stop_loss}` | TP: `{take_profit}`\n"
            f"Стратегия: `{strategy}`"
        )

    @staticmethod
    def format_trade_closed(
        symbol: str, side: str, pnl: Decimal, pnl_pct: Decimal,
        entry_price: Decimal, exit_price: Decimal, strategy: str,
    ) -> str:
        result = "✅ ПРИБЫЛЬ" if pnl > 0 else "❌ УБЫТОК"
        sign = "+" if pnl > 0 else ""
        return (
            f"{result} *{symbol}* ({side})\n"
            f"PnL: `{sign}{pnl:.4f} USDT ({sign}{pnl_pct * 100:.2f}%)`\n"
            f"Вход: `{entry_price}` → Выход: `{exit_price}`\n"
            f"Стратегия: `{strategy}`"
        )

    @staticmethod
    def format_status(
        bot_state: str, equity: Decimal, open_positions: int,
        daily_pnl: Decimal, active_strategies: list[str],
        session_id: str = "", signals_count: int = 0, trades_count: int = 0,
    ) -> str:
        sign = "+" if daily_pnl >= 0 else ""
        return (
            f"📊 *Статус бота*\n"
            f"Состояние: `{bot_state}`\n"
            f"Сессия: `{session_id}`\n"
            f"Эквити: `{equity:.2f} USDT`\n"
            f"Открытых позиций: `{open_positions}`\n"
            f"Дневной PnL: `{sign}{daily_pnl:.2f} USDT`\n"
            f"Сигналов: `{signals_count}`\n"
            f"Сделок: `{trades_count}`\n"
            f"Стратегии: `{', '.join(active_strategies)}`"
        )

    @staticmethod
    def format_risk_alert(
        reason: str, current_drawdown: Decimal, max_drawdown: Decimal,
    ) -> str:
        return (
            f"🚨 *РИСК-АЛЕРТ*\n"
            f"Причина: `{reason}`\n"
            f"Текущая просадка: `{current_drawdown * 100:.2f}%`\n"
            f"Лимит просадки: `{max_drawdown * 100:.2f}%`"
        )

    @staticmethod
    def format_positions(positions: list[dict[str, Any]]) -> str:
        if not positions:
            return "📋 *Открытые позиции*\n\nНет открытых позиций."
        lines = ["📋 *Открытые позиции*\n"]
        for p in positions:
            side = str(p.get("side", "")).lower()
            side_emoji = "🟢" if side == "long" else "🔴"
            pnl = p.get("pnl", Decimal(0))
            sign = "+" if pnl >= 0 else ""
            size = p.get("size", Decimal(0))
            entry = p.get("entry", Decimal(0))
            notional = entry * size if entry and size else Decimal("0")
            pnl_pct = (pnl / notional * 100) if notional > 0 else Decimal("0")
            mark = p.get("mark", Decimal(0))
            liq = p.get("liq")
            lev = p.get("leverage")
            sl = p.get("stop_loss")
            tp = p.get("take_profit")
            tpsl_status = p.get("tpsl_status")
            liq_str = f"{liq}" if liq is not None else "—"
            lev_str = f"{lev}" if lev is not None else "—"
            sl_str = f"{sl}" if sl is not None else "—"
            tp_str = f"{tp}" if tp is not None else "—"
            status_line = (
                f"\n  TP/SL status: `{tpsl_status}`"
                if tpsl_status in {"confirmed", "pending", "failed"}
                else ""
            )
            lines.append(
                f"{side_emoji} *{p['symbol']}* {side.upper()}\n"
                f"  Размер: `{size}` | Вход: `{entry}` | Марк: `{mark}`\n"
                f"  PnL: `{sign}{pnl:.4f} USDT ({pnl_pct:.2f}%)`\n"
                f"  Ликвидация: `{liq_str}` | Плечо: `{lev_str}`\n"
                f"  SL: `{sl_str}` | TP: `{tp_str}`{status_line}"
            )
        return "\n".join(lines)

    @staticmethod
    def format_help() -> str:
        return (
            "🤖 *Команды бота*\n\n"
            "`/status` — Статус и эквити\n"
            "`/positions` — Открытые позиции\n"
            "`/pnl` — Сводка PnL\n"
            "`/close_ready <symbol>` — Диагностика закрытия\n"
            "`/guard` — Статус risk guard\n"
            "`/pause` — Пауза торговли\n"
            "`/resume` — Возобновить торговлю\n"
            "`/risk` — Риск-метрики\n"
            "`/help` — Эта справка"
        )


CommandHandler = Callable[..., Coroutine[Any, Any, str]]


class TelegramAlertSink:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._formatter = TelegramFormatter()
        self._enabled = True
        self._last_update_id = 0
        self._command_handlers: dict[str, CommandHandler] = {}
        self._http_client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def register_command(self, command: str, handler: CommandHandler) -> None:
        self._command_handlers[command] = handler

    async def send_message_now(self, text: str) -> bool:
        if not self._enabled or not self._bot_token or not self._chat_id:
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return True
        except Exception as exc:
            await logger.aerror("telegram_send_failed", error=str(exc))
            return False

    async def poll_and_handle(self) -> None:
        if not self._enabled or not self._bot_token:
            return

        url = f"https://api.telegram.org/bot{self._bot_token}/getUpdates"
        params = {"offset": self._last_update_id + 1, "timeout": 5, "limit": 10}

        try:
            client = self._http_client or httpx.AsyncClient(timeout=15.0)
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                return

            for update in data.get("result", []):
                self._last_update_id = update["update_id"]
                message = update.get("message", {})
                text = message.get("text", "").strip()
                chat_id = str(message.get("chat", {}).get("id", ""))

                if not text.startswith("/"):
                    continue

                cmd = text.split()[0].split("@")[0].lower()
                args = text.split()[1:]
                handler = self._command_handlers.get(cmd)

                if handler:
                    params_count = len(signature(handler).parameters)
                    if params_count == 0:
                        reply = await handler()
                    else:
                        reply = await handler(args)
                    await self._reply_to(chat_id, reply)
                elif cmd == "/help":
                    await self._reply_to(chat_id, self._formatter.format_help())
                else:
                    await self._reply_to(chat_id, f"Неизвестная команда: {cmd}\nПопробуйте /help")

        except httpx.TimeoutException:
            pass
        except Exception as exc:
            await logger.aerror("telegram_poll_error", error=str(exc))

    async def _reply_to(self, chat_id: str, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            await client.post(url, json=payload)
        except Exception as exc:
            await logger.aerror("telegram_reply_failed", error=str(exc))


def _severity_emoji(severity: AlertSeverity) -> str:
    mapping = {
        AlertSeverity.INFO: "ℹ️",
        AlertSeverity.WARNING: "⚠️",
        AlertSeverity.ERROR: "🔴",
        AlertSeverity.CRITICAL: "🚨",
    }
    return mapping.get(severity, "📌")
