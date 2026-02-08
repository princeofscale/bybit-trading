from decimal import Decimal

import pytest

from monitoring.alerts import Alert, AlertSeverity
from monitoring.telegram_bot import (
    TelegramAlertSink,
    TelegramCommand,
    TelegramCommandHandler,
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

    def test_format_trade_opened(self) -> None:
        text = TelegramFormatter.format_trade_opened(
            symbol="BTCUSDT", side="long", size=Decimal("0.1"),
            entry_price=Decimal("50000"), stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"), strategy="ema_crossover",
        )
        assert "LONG" in text
        assert "BTCUSDT" in text
        assert "50000" in text

    def test_format_trade_closed_win(self) -> None:
        text = TelegramFormatter.format_trade_closed(
            symbol="ETHUSDT", side="short", pnl=Decimal("150.50"),
            pnl_pct=Decimal("0.03"), entry_price=Decimal("3100"),
            exit_price=Decimal("3000"), strategy="mean_reversion",
        )
        assert "WIN" in text
        assert "150.50" in text

    def test_format_trade_closed_loss(self) -> None:
        text = TelegramFormatter.format_trade_closed(
            symbol="BTCUSDT", side="long", pnl=Decimal("-200"),
            pnl_pct=Decimal("-0.02"), entry_price=Decimal("50000"),
            exit_price=Decimal("49000"), strategy="trend",
        )
        assert "LOSS" in text

    def test_format_status(self) -> None:
        text = TelegramFormatter.format_status(
            bot_state="running", equity=Decimal("50000"),
            open_positions=3, daily_pnl=Decimal("250"),
            active_strategies=["ema", "trend"],
        )
        assert "running" in text
        assert "50000" in text
        assert "ema" in text

    def test_format_risk_alert(self) -> None:
        text = TelegramFormatter.format_risk_alert(
            reason="max_drawdown_exceeded",
            current_drawdown=Decimal("0.16"),
            max_drawdown=Decimal("0.15"),
        )
        assert "RISK ALERT" in text
        assert "16.00%" in text


class TestTelegramAlertSink:
    def test_receive_alert(self, sink: TelegramAlertSink) -> None:
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Connection Lost",
            message="WebSocket disconnected",
            source="ws_manager",
        )
        sink.receive(alert)
        assert sink.sent_count == 1
        assert "Connection Lost" in sink.last_message.text

    def test_disabled_sink_ignores(self, sink: TelegramAlertSink) -> None:
        sink.enabled = False
        alert = Alert(severity=AlertSeverity.INFO, title="Test", message="msg")
        sink.receive(alert)
        assert sink.sent_count == 0

    def test_send_trade_opened(self, sink: TelegramAlertSink) -> None:
        sink.send_trade_opened(
            "BTCUSDT", "long", Decimal("0.5"),
            Decimal("50000"), Decimal("49000"), Decimal("52000"),
            "ema_crossover",
        )
        assert sink.sent_count == 1
        assert "BTCUSDT" in sink.last_message.text

    def test_send_trade_closed(self, sink: TelegramAlertSink) -> None:
        sink.send_trade_closed(
            "ETHUSDT", "short", Decimal("100"), Decimal("0.05"),
            Decimal("3000"), Decimal("2900"), "momentum",
        )
        assert sink.sent_count == 1
        assert "WIN" in sink.last_message.text

    def test_send_status(self, sink: TelegramAlertSink) -> None:
        sink.send_status(
            "running", Decimal("50000"), 2, Decimal("-100"),
            ["ema", "rsi"],
        )
        assert sink.sent_count == 1

    def test_clear_sent(self, sink: TelegramAlertSink) -> None:
        sink.send_status("running", Decimal("50000"), 0, Decimal("0"), [])
        sink.clear_sent()
        assert sink.sent_count == 0

    def test_chat_id_in_message(self, sink: TelegramAlertSink) -> None:
        alert = Alert(severity=AlertSeverity.INFO, title="T", message="M")
        sink.receive(alert)
        assert sink.last_message.chat_id == "123456"


class TestTelegramCommandHandler:
    def test_register_and_handle(self) -> None:
        handler = TelegramCommandHandler()
        handler.register(TelegramCommand.STATUS, lambda: "Bot is running")
        result = handler.handle("/status")
        assert result == "Bot is running"

    def test_unknown_command(self) -> None:
        handler = TelegramCommandHandler()
        result = handler.handle("/unknown_cmd")
        assert result is None

    def test_registered_commands(self) -> None:
        handler = TelegramCommandHandler()
        handler.register(TelegramCommand.STATUS, lambda: "ok")
        handler.register(TelegramCommand.PNL, lambda: "pnl")
        assert "/status" in handler.registered_commands
        assert "/pnl" in handler.registered_commands

    def test_unregistered_known_command(self) -> None:
        handler = TelegramCommandHandler()
        result = handler.handle("/pause")
        assert "not implemented" in result.lower()
