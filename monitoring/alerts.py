from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from utils.time_utils import utc_now_ms


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(StrEnum):
    LOG = "log"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WEBHOOK = "webhook"


class Alert(BaseModel):
    severity: AlertSeverity
    title: str
    message: str
    source: str = ""
    timestamp: int = Field(default_factory=utc_now_ms)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertRule(BaseModel):
    name: str
    severity: AlertSeverity
    channels: list[AlertChannel]
    cooldown_ms: int = 60_000
    enabled: bool = True


class AlertManager:
    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._history: list[Alert] = []
        self._last_fired: dict[str, int] = {}
        self._sinks: dict[AlertChannel, list[Any]] = {}
        self._max_history = 1000

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> None:
        self._rules.pop(name, None)

    def get_rule(self, name: str) -> AlertRule | None:
        return self._rules.get(name)

    @property
    def rule_names(self) -> list[str]:
        return list(self._rules.keys())

    def register_sink(self, channel: AlertChannel, sink: Any) -> None:
        if channel not in self._sinks:
            self._sinks[channel] = []
        self._sinks[channel].append(sink)

    def fire_alert(self, alert: Alert, rule_name: str | None = None) -> bool:
        if rule_name and rule_name in self._rules:
            rule = self._rules[rule_name]
            if not rule.enabled:
                return False
            if not self._check_cooldown(rule_name, rule.cooldown_ms):
                return False
            self._last_fired[rule_name] = utc_now_ms()

        self._history.append(alert)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        self._dispatch(alert, rule_name)
        return True

    def _check_cooldown(self, rule_name: str, cooldown_ms: int) -> bool:
        last = self._last_fired.get(rule_name, 0)
        return (utc_now_ms() - last) >= cooldown_ms

    def _dispatch(self, alert: Alert, rule_name: str | None) -> None:
        if rule_name and rule_name in self._rules:
            channels = self._rules[rule_name].channels
        else:
            channels = [AlertChannel.LOG]

        for channel in channels:
            sinks = self._sinks.get(channel, [])
            for sink in sinks:
                try:
                    sink.receive(alert)
                except Exception:
                    pass

    @property
    def history(self) -> list[Alert]:
        return list(self._history)

    def recent_alerts(self, count: int = 10) -> list[Alert]:
        return self._history[-count:]

    def alerts_by_severity(self, severity: AlertSeverity) -> list[Alert]:
        return [a for a in self._history if a.severity == severity]

    def clear_history(self) -> None:
        self._history.clear()
        self._last_fired.clear()
