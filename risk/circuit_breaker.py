from decimal import Decimal

import structlog

from config.settings import RiskSettings
from utils.time_utils import utc_now_ms

logger = structlog.get_logger("circuit_breaker")


class CircuitBreaker:
    def __init__(self, risk_settings: RiskSettings) -> None:
        self._max_consecutive = risk_settings.circuit_breaker_consecutive_losses
        self._cooldown_ms = risk_settings.circuit_breaker_cooldown_hours * 3_600_000
        self._consecutive_losses = 0
        self._tripped = False
        self._tripped_at: int = 0
        self._total_trips = 0

    @property
    def is_tripped(self) -> bool:
        if self._tripped:
            elapsed = utc_now_ms() - self._tripped_at
            if elapsed >= self._cooldown_ms:
                self.reset()
                return False
        return self._tripped

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    @property
    def total_trips(self) -> int:
        return self._total_trips

    @property
    def cooldown_remaining_ms(self) -> int:
        if not self._tripped:
            return 0
        elapsed = utc_now_ms() - self._tripped_at
        remaining = self._cooldown_ms - elapsed
        return max(0, remaining)

    def record_win(self) -> None:
        self._consecutive_losses = 0

    def record_loss(self) -> None:
        self._consecutive_losses += 1
        if self._consecutive_losses >= self._max_consecutive:
            self._trip()

    def _trip(self) -> None:
        self._tripped = True
        self._tripped_at = utc_now_ms()
        self._total_trips += 1
        logger.warning(
            "circuit_breaker_tripped",
            consecutive_losses=self._consecutive_losses,
            total_trips=self._total_trips,
        )

    def reset(self) -> None:
        self._tripped = False
        self._tripped_at = 0
        self._consecutive_losses = 0

    def force_trip(self, reason: str = "manual") -> None:
        self._trip()
        logger.warning("circuit_breaker_forced", reason=reason)

    def is_trading_allowed(self) -> bool:
        return not self.is_tripped
