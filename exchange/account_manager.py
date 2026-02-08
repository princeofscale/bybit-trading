from decimal import Decimal

import structlog

from exchange.models import AccountBalance
from exchange.rest_api import RestApi

logger = structlog.get_logger("account_manager")


class AccountManager:
    def __init__(self, rest_api: RestApi) -> None:
        self._rest_api = rest_api
        self._balance: AccountBalance | None = None
        self._peak_equity: Decimal = Decimal("0")

    async def sync_balance(self) -> AccountBalance:
        self._balance = await self._rest_api.fetch_balance()
        if self._balance.total_equity > self._peak_equity:
            self._peak_equity = self._balance.total_equity
        await logger.ainfo(
            "balance_synced",
            equity=str(self._balance.total_equity),
            available=str(self._balance.total_available_balance),
        )
        return self._balance

    def update_balance(self, balance: AccountBalance) -> None:
        self._balance = balance
        if balance.total_equity > self._peak_equity:
            self._peak_equity = balance.total_equity

    @property
    def balance(self) -> AccountBalance | None:
        return self._balance

    @property
    def equity(self) -> Decimal:
        return self._balance.total_equity if self._balance else Decimal("0")

    @property
    def available_balance(self) -> Decimal:
        return self._balance.total_available_balance if self._balance else Decimal("0")

    @property
    def peak_equity(self) -> Decimal:
        return self._peak_equity

    @property
    def current_drawdown_pct(self) -> Decimal:
        if self._peak_equity == 0:
            return Decimal("0")
        return (self._peak_equity - self.equity) / self._peak_equity

    def has_sufficient_balance(self, required_usd: Decimal) -> bool:
        return self.available_balance >= required_usd
