from unittest.mock import patch

import pytest

from monitoring.health_check import (
    ComponentHealth,
    ComponentStatus,
    HealthChecker,
    SystemHealth,
)


@pytest.fixture
def checker() -> HealthChecker:
    return HealthChecker()


class TestRegisterComponent:
    def test_registers_with_unknown_status(self, checker: HealthChecker) -> None:
        checker.register_component("exchange")
        health = checker.get_component_health("exchange")
        assert health is not None
        assert health.status == ComponentStatus.UNKNOWN

    def test_registers_multiple(self, checker: HealthChecker) -> None:
        checker.register_component("exchange")
        checker.register_component("database")
        assert len(checker.component_names) == 2

    def test_component_names(self, checker: HealthChecker) -> None:
        checker.register_component("exchange")
        checker.register_component("websocket")
        assert "exchange" in checker.component_names
        assert "websocket" in checker.component_names


class TestUpdateStatus:
    def test_updates_existing(self, checker: HealthChecker) -> None:
        checker.register_component("exchange")
        checker.update_status("exchange", ComponentStatus.HEALTHY, "Connected")
        health = checker.get_component_health("exchange")
        assert health.status == ComponentStatus.HEALTHY
        assert health.message == "Connected"

    def test_auto_registers_on_update(self, checker: HealthChecker) -> None:
        checker.update_status("new_component", ComponentStatus.DEGRADED)
        assert "new_component" in checker.component_names

    def test_records_latency(self, checker: HealthChecker) -> None:
        checker.update_status("db", ComponentStatus.HEALTHY, latency_ms=15)
        health = checker.get_component_health("db")
        assert health.latency_ms == 15

    def test_updates_timestamp(self, checker: HealthChecker) -> None:
        checker.update_status("exchange", ComponentStatus.HEALTHY)
        health = checker.get_component_health("exchange")
        assert health.last_check_ts > 0


class TestOverallHealth:
    def test_all_healthy(self, checker: HealthChecker) -> None:
        checker.update_status("a", ComponentStatus.HEALTHY)
        checker.update_status("b", ComponentStatus.HEALTHY)
        assert checker.is_healthy() is True

    def test_one_unhealthy_makes_overall_unhealthy(self, checker: HealthChecker) -> None:
        checker.update_status("a", ComponentStatus.HEALTHY)
        checker.update_status("b", ComponentStatus.UNHEALTHY)
        assert checker.is_healthy() is False

    def test_degraded_not_healthy(self, checker: HealthChecker) -> None:
        checker.update_status("a", ComponentStatus.HEALTHY)
        checker.update_status("b", ComponentStatus.DEGRADED)
        assert checker.is_healthy() is False

    def test_empty_returns_unknown(self, checker: HealthChecker) -> None:
        health = checker.get_system_health()
        assert health.overall == ComponentStatus.UNKNOWN

    def test_unhealthy_components_list(self, checker: HealthChecker) -> None:
        checker.update_status("ok", ComponentStatus.HEALTHY)
        checker.update_status("bad", ComponentStatus.UNHEALTHY)
        checker.update_status("worse", ComponentStatus.UNHEALTHY)
        bad = checker.unhealthy_components()
        assert "bad" in bad
        assert "worse" in bad
        assert "ok" not in bad


class TestSystemHealth:
    def test_includes_all_components(self, checker: HealthChecker) -> None:
        checker.update_status("a", ComponentStatus.HEALTHY)
        checker.update_status("b", ComponentStatus.DEGRADED)
        sys_health = checker.get_system_health()
        assert "a" in sys_health.components
        assert "b" in sys_health.components

    def test_uptime_positive(self, checker: HealthChecker) -> None:
        sys_health = checker.get_system_health()
        assert sys_health.uptime_ms >= 0

    def test_timestamp_set(self, checker: HealthChecker) -> None:
        sys_health = checker.get_system_health()
        assert sys_health.timestamp > 0


class TestReset:
    def test_clears_components(self, checker: HealthChecker) -> None:
        checker.update_status("a", ComponentStatus.HEALTHY)
        checker.reset()
        assert len(checker.component_names) == 0

    def test_get_missing_returns_none(self, checker: HealthChecker) -> None:
        assert checker.get_component_health("nonexistent") is None
