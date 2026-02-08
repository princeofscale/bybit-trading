from decimal import Decimal

import structlog

from config.settings import RiskSettings

logger = structlog.get_logger("drawdown_monitor")


class DrawdownMonitor:
    def __init__(self, risk_settings: RiskSettings) -> None:
        self._settings = risk_settings
        self._peak_equity = Decimal("0")
        self._current_equity = Decimal("0")
        self._daily_start_equity = Decimal("0")
        self._weekly_start_equity = Decimal("0")
        self._halted = False
        self._halt_reason = ""

    @property
    def peak_equity(self) -> Decimal:
        return self._peak_equity

    @property
    def current_drawdown_pct(self) -> Decimal:
        if self._peak_equity <= 0:
            return Decimal("0")
        return (self._peak_equity - self._current_equity) / self._peak_equity

    @property
    def daily_pnl_pct(self) -> Decimal:
        if self._daily_start_equity <= 0:
            return Decimal("0")
        return (self._current_equity - self._daily_start_equity) / self._daily_start_equity

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def initialize(self, equity: Decimal) -> None:
        self._peak_equity = equity
        self._current_equity = equity
        self._daily_start_equity = equity
        self._weekly_start_equity = equity
        self._halted = False
        self._halt_reason = ""

    def update_equity(self, equity: Decimal) -> bool:
        self._current_equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity

        if self._check_max_drawdown():
            return False
        if self._check_daily_loss():
            return False

        return True

    def _check_max_drawdown(self) -> bool:
        if self.current_drawdown_pct >= self._settings.max_drawdown_pct:
            self._halted = True
            self._halt_reason = (
                f"max_drawdown_breached: {self.current_drawdown_pct:.4f} "
                f">= {self._settings.max_drawdown_pct}"
            )
            return True
        return False

    def _check_daily_loss(self) -> bool:
        daily_loss = -self.daily_pnl_pct
        if daily_loss >= self._settings.max_daily_loss_pct:
            self._halted = True
            self._halt_reason = (
                f"daily_loss_breached: {daily_loss:.4f} "
                f">= {self._settings.max_daily_loss_pct}"
            )
            return True
        return False

    def reset_daily(self) -> None:
        self._daily_start_equity = self._current_equity
        if self._halted and "daily" in self._halt_reason:
            self._halted = False
            self._halt_reason = ""

    def reset_weekly(self) -> None:
        self._weekly_start_equity = self._current_equity

    def resume_trading(self) -> None:
        self._halted = False
        self._halt_reason = ""
