from decimal import Decimal
from enum import StrEnum
from typing import Any

import httpx
import structlog

from monitoring.alerts import Alert, AlertChannel, AlertSeverity

logger = structlog.get_logger("telegram_bot")


class TelegramCommand(StrEnum):
    STATUS = "/status"
    POSITIONS = "/positions"
    PNL = "/pnl"
    PAUSE = "/pause"
    RESUME = "/resume"
    RISK = "/risk"
    HELP = "/help"


class TelegramMessage:
    def __init__(self, chat_id: str, text: str) -> None:
        self.chat_id = chat_id
        self.text = text


class TelegramFormatter:
    @staticmethod
    def format_alert(alert: Alert) -> str:
        emoji = _severity_emoji(alert.severity)
        return (
            f"{emoji} *{alert.title}*\n"
            f"{alert.message}\n"
            f"Source: `{alert.source}`"
        )

    @staticmethod
    def format_trade_opened(
        symbol: str,
        side: str,
        size: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        strategy: str,
    ) -> str:
        arrow = "🟢 LONG" if side.lower() == "long" else "🔴 SHORT"
        return (
            f"{arrow} *{symbol}*\n"
            f"Entry: `{entry_price}`\n"
            f"Size: `{size}`\n"
            f"SL: `{stop_loss}` | TP: `{take_profit}`\n"
            f"Strategy: `{strategy}`"
        )

    @staticmethod
    def format_trade_closed(
        symbol: str,
        side: str,
        pnl: Decimal,
        pnl_pct: Decimal,
        entry_price: Decimal,
        exit_price: Decimal,
        strategy: str,
    ) -> str:
        result = "✅ WIN" if pnl > 0 else "❌ LOSS"
        sign = "+" if pnl > 0 else ""
        return (
            f"{result} *{symbol}* ({side})\n"
            f"PnL: `{sign}{pnl:.4f} USDT ({sign}{pnl_pct * 100:.2f}%)`\n"
            f"Entry: `{entry_price}` → Exit: `{exit_price}`\n"
            f"Strategy: `{strategy}`"
        )

    @staticmethod
    def format_status(
        bot_state: str,
        equity: Decimal,
        open_positions: int,
        daily_pnl: Decimal,
        active_strategies: list[str],
    ) -> str:
        sign = "+" if daily_pnl >= 0 else ""
        return (
            f"📊 *Bot Status*\n"
            f"State: `{bot_state}`\n"
            f"Equity: `{equity:.2f} USDT`\n"
            f"Open positions: `{open_positions}`\n"
            f"Daily PnL: `{sign}{daily_pnl:.2f} USDT`\n"
            f"Strategies: `{', '.join(active_strategies)}`"
        )

    @staticmethod
    def format_risk_alert(
        reason: str,
        current_drawdown: Decimal,
        max_drawdown: Decimal,
    ) -> str:
        return (
            f"🚨 *RISK ALERT*\n"
            f"Reason: `{reason}`\n"
            f"Current DD: `{current_drawdown * 100:.2f}%`\n"
            f"Max DD Limit: `{max_drawdown * 100:.2f}%`"
        )


class TelegramAlertSink:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._formatter = TelegramFormatter()
        self._sent_messages: list[TelegramMessage] = []
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def sent_count(self) -> int:
        return len(self._sent_messages)

    @property
    def last_message(self) -> TelegramMessage | None:
        return self._sent_messages[-1] if self._sent_messages else None

    def receive(self, alert: Alert) -> None:
        if not self._enabled:
            return
        text = self._formatter.format_alert(alert)
        self._queue_message(text)

    def send_trade_opened(
        self, symbol: str, side: str, size: Decimal,
        entry: Decimal, sl: Decimal, tp: Decimal, strategy: str,
    ) -> None:
        text = self._formatter.format_trade_opened(
            symbol, side, size, entry, sl, tp, strategy,
        )
        self._queue_message(text)

    def send_trade_closed(
        self, symbol: str, side: str, pnl: Decimal, pnl_pct: Decimal,
        entry: Decimal, exit_price: Decimal, strategy: str,
    ) -> None:
        text = self._formatter.format_trade_closed(
            symbol, side, pnl, pnl_pct, entry, exit_price, strategy,
        )
        self._queue_message(text)

    def send_status(
        self, bot_state: str, equity: Decimal, positions: int,
        daily_pnl: Decimal, strategies: list[str],
    ) -> None:
        text = self._formatter.format_status(
            bot_state, equity, positions, daily_pnl, strategies,
        )
        self._queue_message(text)

    def _queue_message(self, text: str) -> None:
        msg = TelegramMessage(self._chat_id, text)
        self._sent_messages.append(msg)

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
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                await logger.adebug("telegram_message_sent", chat_id=self._chat_id)
                return True
        except Exception as exc:
            await logger.aerror("telegram_send_failed", error=str(exc))
            return False

    def get_pending_messages(self) -> list[TelegramMessage]:
        return list(self._sent_messages)

    def clear_sent(self) -> None:
        self._sent_messages.clear()


class TelegramCommandHandler:
    def __init__(self) -> None:
        self._handlers: dict[TelegramCommand, Any] = {}

    def register(self, command: TelegramCommand, handler: Any) -> None:
        self._handlers[command] = handler

    def handle(self, command_text: str) -> str | None:
        cmd_str = command_text.strip().split()[0].lower()
        try:
            cmd = TelegramCommand(cmd_str)
        except ValueError:
            return None
        handler = self._handlers.get(cmd)
        if handler:
            return handler()
        return f"Command {cmd_str} not implemented"

    @property
    def registered_commands(self) -> list[str]:
        return [cmd.value for cmd in self._handlers.keys()]


def _severity_emoji(severity: AlertSeverity) -> str:
    mapping = {
        AlertSeverity.INFO: "ℹ️",
        AlertSeverity.WARNING: "⚠️",
        AlertSeverity.ERROR: "🔴",
        AlertSeverity.CRITICAL: "🚨",
    }
    return mapping.get(severity, "📌")
