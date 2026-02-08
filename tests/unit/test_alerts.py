from unittest.mock import MagicMock, patch

import pytest

from monitoring.alerts import (
    Alert,
    AlertChannel,
    AlertManager,
    AlertRule,
    AlertSeverity,
)


@pytest.fixture
def manager() -> AlertManager:
    return AlertManager()


def _make_alert(
    severity: AlertSeverity = AlertSeverity.WARNING,
    title: str = "Test Alert",
    message: str = "Something happened",
) -> Alert:
    return Alert(severity=severity, title=title, message=message, source="test")


class TestFireAlert:
    def test_adds_to_history(self, manager: AlertManager) -> None:
        alert = _make_alert()
        manager.fire_alert(alert)
        assert len(manager.history) == 1
        assert manager.history[0].title == "Test Alert"

    def test_multiple_alerts(self, manager: AlertManager) -> None:
        for i in range(5):
            manager.fire_alert(_make_alert(title=f"Alert {i}"))
        assert len(manager.history) == 5

    def test_returns_true_on_success(self, manager: AlertManager) -> None:
        assert manager.fire_alert(_make_alert()) is True


class TestAlertRules:
    def test_add_rule(self, manager: AlertManager) -> None:
        rule = AlertRule(
            name="drawdown",
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.TELEGRAM],
        )
        manager.add_rule(rule)
        assert "drawdown" in manager.rule_names

    def test_remove_rule(self, manager: AlertManager) -> None:
        rule = AlertRule(
            name="test",
            severity=AlertSeverity.INFO,
            channels=[AlertChannel.LOG],
        )
        manager.add_rule(rule)
        manager.remove_rule("test")
        assert "test" not in manager.rule_names

    def test_get_rule(self, manager: AlertManager) -> None:
        rule = AlertRule(
            name="circuit",
            severity=AlertSeverity.ERROR,
            channels=[AlertChannel.DISCORD],
        )
        manager.add_rule(rule)
        fetched = manager.get_rule("circuit")
        assert fetched is not None
        assert fetched.severity == AlertSeverity.ERROR

    def test_get_missing_rule_none(self, manager: AlertManager) -> None:
        assert manager.get_rule("nonexistent") is None

    def test_disabled_rule_blocks_alert(self, manager: AlertManager) -> None:
        rule = AlertRule(
            name="disabled",
            severity=AlertSeverity.INFO,
            channels=[AlertChannel.LOG],
            enabled=False,
        )
        manager.add_rule(rule)
        result = manager.fire_alert(_make_alert(), rule_name="disabled")
        assert result is False
        assert len(manager.history) == 0


class TestCooldown:
    def test_cooldown_blocks_rapid_fire(self, manager: AlertManager) -> None:
        rule = AlertRule(
            name="rate_limited",
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.LOG],
            cooldown_ms=60_000,
        )
        manager.add_rule(rule)

        first = manager.fire_alert(_make_alert(), rule_name="rate_limited")
        second = manager.fire_alert(_make_alert(), rule_name="rate_limited")
        assert first is True
        assert second is False
        assert len(manager.history) == 1

    def test_no_rule_name_bypasses_cooldown(self, manager: AlertManager) -> None:
        manager.fire_alert(_make_alert())
        manager.fire_alert(_make_alert())
        assert len(manager.history) == 2


class TestSinks:
    def test_dispatches_to_registered_sink(self, manager: AlertManager) -> None:
        sink = MagicMock()
        rule = AlertRule(
            name="with_sink",
            severity=AlertSeverity.INFO,
            channels=[AlertChannel.TELEGRAM],
        )
        manager.add_rule(rule)
        manager.register_sink(AlertChannel.TELEGRAM, sink)
        manager.fire_alert(_make_alert(), rule_name="with_sink")
        sink.receive.assert_called_once()

    def test_sink_error_does_not_crash(self, manager: AlertManager) -> None:
        sink = MagicMock()
        sink.receive.side_effect = RuntimeError("connection failed")
        rule = AlertRule(
            name="failing",
            severity=AlertSeverity.ERROR,
            channels=[AlertChannel.WEBHOOK],
        )
        manager.add_rule(rule)
        manager.register_sink(AlertChannel.WEBHOOK, sink)
        result = manager.fire_alert(_make_alert(), rule_name="failing")
        assert result is True


class TestFiltering:
    def test_recent_alerts(self, manager: AlertManager) -> None:
        for i in range(15):
            manager.fire_alert(_make_alert(title=f"A{i}"))
        recent = manager.recent_alerts(5)
        assert len(recent) == 5
        assert recent[0].title == "A10"

    def test_alerts_by_severity(self, manager: AlertManager) -> None:
        manager.fire_alert(_make_alert(severity=AlertSeverity.INFO))
        manager.fire_alert(_make_alert(severity=AlertSeverity.ERROR))
        manager.fire_alert(_make_alert(severity=AlertSeverity.INFO))
        infos = manager.alerts_by_severity(AlertSeverity.INFO)
        assert len(infos) == 2

    def test_clear_history(self, manager: AlertManager) -> None:
        manager.fire_alert(_make_alert())
        manager.clear_history()
        assert len(manager.history) == 0


class TestHistoryLimit:
    def test_trims_to_max(self, manager: AlertManager) -> None:
        manager._max_history = 10
        for i in range(20):
            manager.fire_alert(_make_alert(title=f"A{i}"))
        assert len(manager.history) == 10
        assert manager.history[0].title == "A10"
