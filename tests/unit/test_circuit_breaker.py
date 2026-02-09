from decimal import Decimal
from unittest.mock import patch

import pytest

from config.settings import RiskSettings
from risk.circuit_breaker import CircuitBreaker


@pytest.fixture
def settings() -> RiskSettings:
    return RiskSettings(
        circuit_breaker_consecutive_losses=3,
        circuit_breaker_cooldown_hours=4,
    )


@pytest.fixture
def breaker(settings: RiskSettings) -> CircuitBreaker:
    return CircuitBreaker(settings)


class TestRecordWinLoss:
    def test_record_loss_increments(self, breaker: CircuitBreaker) -> None:
        breaker.record_loss()
        assert breaker.consecutive_losses == 1
        breaker.record_loss()
        assert breaker.consecutive_losses == 2

    def test_record_win_resets(self, breaker: CircuitBreaker) -> None:
        breaker.record_loss()
        breaker.record_loss()
        breaker.record_win()
        assert breaker.consecutive_losses == 0

    def test_win_after_losses_prevents_trip(self, breaker: CircuitBreaker) -> None:
        breaker.record_loss()
        breaker.record_loss()
        breaker.record_win()
        breaker.record_loss()
        assert breaker.is_trading_allowed() is True


class TestTripping:
    def test_trips_after_consecutive_losses(self, breaker: CircuitBreaker) -> None:
        breaker.record_loss()
        breaker.record_loss()
        assert breaker.is_trading_allowed() is True
        breaker.record_loss()
        assert breaker.is_trading_allowed() is False
        assert breaker.is_tripped is True

    def test_total_trips_counted(self, breaker: CircuitBreaker) -> None:
        assert breaker.total_trips == 0
        for _ in range(3):
            breaker.record_loss()
        assert breaker.total_trips == 1

    def test_force_trip(self, breaker: CircuitBreaker) -> None:
        breaker.force_trip("test_reason")
        assert breaker.is_tripped is True
        assert breaker.is_trading_allowed() is False
        assert breaker.total_trips == 1


class TestCooldown:
    def test_cooldown_remaining_when_tripped(self, breaker: CircuitBreaker) -> None:
        now_ms = 1_000_000_000
        with patch("risk.circuit_breaker.utc_now_ms", return_value=now_ms):
            for _ in range(3):
                breaker.record_loss()
        cooldown_4h = 4 * 3_600_000
        with patch("risk.circuit_breaker.utc_now_ms", return_value=now_ms + 1000):
            assert breaker.cooldown_remaining_ms > 0
            assert breaker.cooldown_remaining_ms == cooldown_4h - 1000

    def test_auto_reset_after_cooldown(self, breaker: CircuitBreaker) -> None:
        now_ms = 1_000_000_000
        with patch("risk.circuit_breaker.utc_now_ms", return_value=now_ms):
            for _ in range(3):
                breaker.record_loss()

        cooldown_4h = 4 * 3_600_000
        future = now_ms + cooldown_4h + 1
        with patch("risk.circuit_breaker.utc_now_ms", return_value=future):
            assert breaker.is_tripped is False
            assert breaker.is_trading_allowed() is True

    def test_still_tripped_before_cooldown(self, breaker: CircuitBreaker) -> None:
        now_ms = 1_000_000_000
        with patch("risk.circuit_breaker.utc_now_ms", return_value=now_ms):
            for _ in range(3):
                breaker.record_loss()

        almost = now_ms + 4 * 3_600_000 - 1
        with patch("risk.circuit_breaker.utc_now_ms", return_value=almost):
            assert breaker.is_tripped is True

    def test_cooldown_zero_when_not_tripped(self, breaker: CircuitBreaker) -> None:
        assert breaker.cooldown_remaining_ms == 0


class TestReset:
    def test_manual_reset(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            breaker.record_loss()
        assert breaker.is_tripped is True
        breaker.reset()
        assert breaker.is_tripped is False
        assert breaker.consecutive_losses == 0
        assert breaker.is_trading_allowed() is True


class TestCustomSettings:
    def test_different_consecutive_threshold(self) -> None:
        settings = RiskSettings(circuit_breaker_consecutive_losses=5)
        breaker = CircuitBreaker(settings)
        for _ in range(4):
            breaker.record_loss()
        assert breaker.is_trading_allowed() is True
        breaker.record_loss()
        assert breaker.is_trading_allowed() is False

    def test_disabled_circuit_breaker_never_blocks(self) -> None:
        settings = RiskSettings(enable_circuit_breaker=False)
        breaker = CircuitBreaker(settings)
        for _ in range(10):
            breaker.record_loss()
        assert breaker.is_trading_allowed() is True
