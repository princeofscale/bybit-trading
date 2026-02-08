from decimal import Decimal
from unittest.mock import patch

from config.settings import AppSettings, ExchangeSettings, RiskSettings


def test_default_settings() -> None:
    settings = AppSettings(_env_file=None)
    assert settings.log_level == "INFO"
    assert settings.environment == "development"


def test_risk_defaults() -> None:
    risk = RiskSettings()
    assert risk.max_risk_per_trade == Decimal("0.02")
    assert risk.max_portfolio_risk == Decimal("0.10")
    assert risk.max_drawdown_pct == Decimal("0.15")
    assert risk.max_daily_loss_pct == Decimal("0.05")
    assert risk.max_leverage == Decimal("3.0")
    assert risk.max_concurrent_positions == 10
    assert risk.circuit_breaker_consecutive_losses == 3
    assert risk.circuit_breaker_cooldown_hours == 4


def test_exchange_testnet_default() -> None:
    exchange = ExchangeSettings()
    assert exchange.testnet is True


def test_database_url() -> None:
    settings = AppSettings(_env_file=None)
    url = settings.database.async_url
    assert url.startswith("postgresql+asyncpg://")
    assert "trading_bot" in url
