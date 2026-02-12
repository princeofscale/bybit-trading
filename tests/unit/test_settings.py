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
    assert risk.circuit_breaker_consecutive_losses == 5
    assert risk.circuit_breaker_cooldown_hours == 2
    assert risk.enable_circuit_breaker is True
    assert risk.enable_daily_loss_limit is True
    assert risk.enable_symbol_cooldown is True
    assert risk.symbol_cooldown_minutes == 30
    assert risk.soft_stop_threshold_pct == Decimal("0.80")
    assert risk.portfolio_heat_limit_pct == Decimal("0.08")
    assert risk.enable_directional_exposure_limit is True
    assert risk.max_directional_exposure_pct == Decimal("0.60")


def test_exchange_testnet_default() -> None:
    exchange = ExchangeSettings()
    assert exchange.testnet is True


def test_exchange_testnet_accepts_flase_typo() -> None:
    with patch.dict("os.environ", {"BYBIT_TESTNET": "flase"}):
        exchange = ExchangeSettings()
    assert exchange.testnet is False


def test_risk_guards_partial_tp_defaults() -> None:
    from config.settings import RiskGuardsSettings
    guards = RiskGuardsSettings()
    assert guards.enable_partial_tp is True
    assert guards.partial_tp_ratio == Decimal("0.6")
    assert guards.partial_tp_close_pct == Decimal("0.5")


def test_risk_guards_dca_defaults() -> None:
    from config.settings import RiskGuardsSettings
    guards = RiskGuardsSettings()
    assert guards.enable_dca is True
    assert guards.dca_trigger_loss_pct == Decimal("1.5")
    assert guards.dca_add_size_pct == Decimal("0.5")
    assert guards.dca_max_adds == 1
    assert guards.dca_max_hold_minutes == 240


def test_trading_effective_mtf_tf() -> None:
    from config.settings import TradingSettings
    ts = TradingSettings()
    assert ts.effective_mtf_tf == "1h"
    ts5 = TradingSettings(default_timeframe="5m")
    assert ts5.effective_mtf_tf == "15m"


def test_ml_settings_defaults() -> None:
    from config.settings import MLSettings
    ml = MLSettings()
    assert ml.enabled is False
    assert ml.model_dir == "models"
    assert ml.confidence_threshold == 0.6
    assert ml.boost_agreement == 0.2
    assert ml.penalize_disagreement == 0.3


def test_ml_settings_in_app_settings() -> None:
    settings = AppSettings(_env_file=None)
    assert settings.ml.enabled is False
    assert settings.ml.model_dir == "models"


def test_database_url() -> None:
    settings = AppSettings(_env_file=None)
    url = settings.database.async_url
    assert url.startswith("postgresql+asyncpg://")
    assert "trading_bot" in url
    assert settings.risk_guards.enable_circuit_breaker is True
    assert settings.trading_stop.retry_max_attempts == 3
