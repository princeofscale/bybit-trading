from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from monitoring.alerts import Alert, AlertSeverity
from monitoring.telegram_bot import (
    TelegramAlertSink,
    TelegramCommand,
    TelegramFormatter,
)


@pytest.fixture
def sink() -> TelegramAlertSink:
    return TelegramAlertSink(bot_token="test_token", chat_id="123456")


class TestTelegramFormatter:
    def test_format_alert(self) -> None:
        alert = Alert(
            severity=AlertSeverity.WARNING,
            title="High Drawdown",
            message="Drawdown at 12%",
            source="risk_manager",
        )
        text = TelegramFormatter.format_alert(alert)
        assert "High Drawdown" in text
        assert "risk_manager" in text
        assert "Источник" in text

    def test_format_trade_opened(self) -> None:
        text = TelegramFormatter.format_trade_opened(
            symbol="BTCUSDT", side="long", size=Decimal("0.1"),
            entry_price=Decimal("50000"), stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"), strategy="ema_crossover",
        )
        assert "ЛОНГ" in text
        assert "BTCUSDT" in text
        assert "Вход" in text

    def test_format_trade_closed_win(self) -> None:
        text = TelegramFormatter.format_trade_closed(
            symbol="ETHUSDT", side="short", pnl=Decimal("150.50"),
            pnl_pct=Decimal("0.03"), entry_price=Decimal("3100"),
            exit_price=Decimal("3000"), strategy="mean_reversion",
        )
        assert "ПРИБЫЛЬ" in text
        assert "150.50" in text

    def test_format_trade_closed_loss(self) -> None:
        text = TelegramFormatter.format_trade_closed(
            symbol="BTCUSDT", side="long", pnl=Decimal("-200"),
            pnl_pct=Decimal("-0.02"), entry_price=Decimal("50000"),
            exit_price=Decimal("49000"), strategy="trend",
        )
        assert "УБЫТОК" in text

    def test_format_status(self) -> None:
        text = TelegramFormatter.format_status(
            bot_state="running", equity=Decimal("50000"),
            open_positions=3, daily_pnl=Decimal("250"),
            active_strategies=["ema", "trend"],
        )
        assert "running" in text
        assert "50000" in text
        assert "Статус бота" in text

    def test_format_status_with_session(self) -> None:
        text = TelegramFormatter.format_status(
            bot_state="RUNNING", equity=Decimal("100000"),
            open_positions=0, daily_pnl=Decimal("0"),
            active_strategies=[], session_id="20260209_120000",
            signals_count=5, trades_count=2,
        )
        assert "20260209_120000" in text
        assert "5" in text
        assert "2" in text

    def test_format_risk_alert(self) -> None:
        text = TelegramFormatter.format_risk_alert(
            reason="max_drawdown_exceeded",
            current_drawdown=Decimal("0.16"),
            max_drawdown=Decimal("0.15"),
        )
        assert "РИСК-АЛЕРТ" in text
        assert "16.00%" in text

    def test_format_positions_empty(self) -> None:
        text = TelegramFormatter.format_positions([])
        assert "Нет открытых позиций" in text

    def test_format_positions_with_data(self) -> None:
        positions: list[dict[str, Any]] = [
            {"symbol": "BTCUSDT", "side": "long", "size": Decimal("0.5"),
             "entry": Decimal("50000"), "pnl": Decimal("100"),
             "mark": Decimal("50100"), "liq": Decimal("40000"),
             "leverage": Decimal("3"), "stop_loss": Decimal("49000"),
             "take_profit": Decimal("52000")},
        ]
        text = TelegramFormatter.format_positions(positions)
        assert "BTCUSDT" in text
        assert "LONG" in text
        assert "100" in text
        assert "Марк" in text
        assert "Ликвидация" in text
        assert "Плечо" in text
        assert "SL" in text
        assert "TP" in text

    def test_format_help(self) -> None:
        text = TelegramFormatter.format_help()
        assert "/status" in text
        assert "/positions" in text
        assert "/guard" in text
        assert "/close_ready" in text
        assert "/pause" in text
        assert "/resume" in text
        assert "Команды бота" in text

    def test_format_trade_opened_short(self) -> None:
        text = TelegramFormatter.format_trade_opened(
            symbol="ETHUSDT", side="short", size=Decimal("1"),
            entry_price=Decimal("3000"), stop_loss=Decimal("3100"),
            take_profit=Decimal("2800"), strategy="momentum",
        )
        assert "ШОРТ" in text


class TestTelegramAlertSink:
    def test_init(self, sink: TelegramAlertSink) -> None:
        assert sink._bot_token == "test_token"
        assert sink._chat_id == "123456"
        assert sink.enabled is True

    def test_disable_enable(self, sink: TelegramAlertSink) -> None:
        sink.enabled = False
        assert sink.enabled is False
        sink.enabled = True
        assert sink.enabled is True

    def test_register_command(self, sink: TelegramAlertSink) -> None:
        handler = AsyncMock(return_value="ok")
        sink.register_command("/status", handler)
        assert "/status" in sink._command_handlers

    def test_register_multiple_commands(self, sink: TelegramAlertSink) -> None:
        sink.register_command("/status", AsyncMock(return_value="status"))
        sink.register_command("/pnl", AsyncMock(return_value="pnl"))
        assert len(sink._command_handlers) == 2

    async def test_send_message_disabled_returns_false(self, sink: TelegramAlertSink) -> None:
        sink.enabled = False
        result = await sink.send_message_now("test")
        assert result is False

    async def test_send_message_no_token_returns_false(self) -> None:
        s = TelegramAlertSink(bot_token="", chat_id="123")
        result = await s.send_message_now("test")
        assert result is False

    async def test_poll_disabled_does_nothing(self, sink: TelegramAlertSink) -> None:
        sink.enabled = False
        await sink.poll_and_handle()

    async def test_poll_no_token_does_nothing(self) -> None:
        s = TelegramAlertSink(bot_token="", chat_id="123")
        await s.poll_and_handle()


class TestTelegramCommand:
    def test_command_values(self) -> None:
        assert TelegramCommand.STATUS == "/status"
        assert TelegramCommand.POSITIONS == "/positions"
        assert TelegramCommand.PNL == "/pnl"
        assert TelegramCommand.CLOSE_READY == "/close_ready"
        assert TelegramCommand.GUARD == "/guard"
        assert TelegramCommand.PAUSE == "/pause"
        assert TelegramCommand.RESUME == "/resume"
        assert TelegramCommand.RISK == "/risk"
        assert TelegramCommand.HELP == "/help"
