from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from exchange.account_manager import AccountManager
from exchange.models import AccountBalance


@pytest.fixture
def mock_rest_api() -> AsyncMock:
    api = AsyncMock()
    api.fetch_balance = AsyncMock(return_value=AccountBalance(
        total_equity=Decimal("10000"),
        total_wallet_balance=Decimal("10000"),
        total_available_balance=Decimal("8000"),
        total_unrealized_pnl=Decimal("200"),
    ))
    return api


@pytest.fixture
def account_manager(mock_rest_api: AsyncMock) -> AccountManager:
    return AccountManager(mock_rest_api)


async def test_sync_balance(account_manager: AccountManager) -> None:
    balance = await account_manager.sync_balance()
    assert balance.total_equity == Decimal("10000")
    assert account_manager.equity == Decimal("10000")
    assert account_manager.available_balance == Decimal("8000")


async def test_peak_equity_tracking(account_manager: AccountManager, mock_rest_api: AsyncMock) -> None:
    await account_manager.sync_balance()
    assert account_manager.peak_equity == Decimal("10000")

    mock_rest_api.fetch_balance.return_value = AccountBalance(
        total_equity=Decimal("12000"),
        total_wallet_balance=Decimal("12000"),
        total_available_balance=Decimal("10000"),
    )
    await account_manager.sync_balance()
    assert account_manager.peak_equity == Decimal("12000")

    mock_rest_api.fetch_balance.return_value = AccountBalance(
        total_equity=Decimal("11000"),
        total_wallet_balance=Decimal("11000"),
        total_available_balance=Decimal("9000"),
    )
    await account_manager.sync_balance()
    assert account_manager.peak_equity == Decimal("12000")


async def test_drawdown_calculation(account_manager: AccountManager, mock_rest_api: AsyncMock) -> None:
    await account_manager.sync_balance()

    mock_rest_api.fetch_balance.return_value = AccountBalance(
        total_equity=Decimal("9000"),
        total_wallet_balance=Decimal("9000"),
        total_available_balance=Decimal("7000"),
    )
    await account_manager.sync_balance()

    expected_dd = (Decimal("10000") - Decimal("9000")) / Decimal("10000")
    assert account_manager.current_drawdown_pct == expected_dd


async def test_has_sufficient_balance(account_manager: AccountManager) -> None:
    await account_manager.sync_balance()
    assert account_manager.has_sufficient_balance(Decimal("5000")) is True
    assert account_manager.has_sufficient_balance(Decimal("8000")) is True
    assert account_manager.has_sufficient_balance(Decimal("8001")) is False


async def test_initial_state(account_manager: AccountManager) -> None:
    assert account_manager.equity == Decimal("0")
    assert account_manager.available_balance == Decimal("0")
    assert account_manager.peak_equity == Decimal("0")
    assert account_manager.balance is None


async def test_update_balance_directly(account_manager: AccountManager) -> None:
    account_manager.update_balance(AccountBalance(
        total_equity=Decimal("15000"),
        total_wallet_balance=Decimal("15000"),
        total_available_balance=Decimal("12000"),
    ))
    assert account_manager.equity == Decimal("15000")
    assert account_manager.peak_equity == Decimal("15000")
