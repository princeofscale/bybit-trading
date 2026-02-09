from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogFormat(StrEnum):
    JSON = "json"
    CONSOLE = "console"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ExchangeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BYBIT_")

    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    testnet: bool = True
    demo_trading: bool = False
    recv_window: int = Field(default=5000, ge=1000, le=10000)


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "trading_bot"
    user: str = "postgres"
    password: SecretStr = SecretStr("postgres")
    pool_size: int = Field(default=20, ge=5, le=100)
    pool_overflow: int = Field(default=10, ge=0, le=50)

    @property
    def async_url(self) -> str:
        pw = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{pw}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_url(self) -> str:
        pw = self.password.get_secret_value()
        return f"postgresql+psycopg2://{self.user}:{pw}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    db: int = 0

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


class RiskSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RISK_")

    max_risk_per_trade: Decimal = Decimal("0.02")
    max_portfolio_risk: Decimal = Decimal("0.10")
    max_drawdown_pct: Decimal = Decimal("0.15")
    max_daily_loss_pct: Decimal = Decimal("0.05")
    max_leverage: Decimal = Decimal("3.0")
    max_concurrent_positions: int = 10
    enable_circuit_breaker: bool = True
    circuit_breaker_consecutive_losses: int = 3
    circuit_breaker_cooldown_hours: int = 4
    enable_daily_loss_limit: bool = True
    enable_symbol_cooldown: bool = True
    symbol_cooldown_minutes: int = 180
    soft_stop_threshold_pct: Decimal = Decimal("0.80")
    soft_stop_min_confidence: float = 0.75
    portfolio_heat_limit_pct: Decimal = Decimal("0.08")
    max_spread_bps: Decimal = Decimal("15")
    min_liquidity_score: float = 0.30
    funding_arb_max_allocation: Decimal = Decimal("0.30")
    enable_directional_exposure_limit: bool = True
    max_directional_exposure_pct: Decimal = Decimal("0.60")


class TradingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADING_")

    default_timeframe: str = "15m"
    position_mode: str = "one_way"
    default_leverage: int = 1
    use_postonly: bool = True


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")

    bot_token: SecretStr = SecretStr("")
    chat_id: str = ""
    enabled: bool = False


class RiskGuardsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RISK_GUARD_")

    enable_circuit_breaker: bool = True
    circuit_breaker_consecutive_losses: int = 3
    circuit_breaker_cooldown_hours: int = 4
    enable_daily_loss_limit: bool = True
    daily_loss_limit_pct: Decimal = Decimal("0.03")
    enable_symbol_cooldown: bool = True
    symbol_cooldown_minutes: int = 180
    soft_stop_threshold_pct: Decimal = Decimal("0.80")
    soft_stop_min_confidence: float = 0.75
    portfolio_heat_limit_pct: Decimal = Decimal("0.08")
    enable_directional_exposure_limit: bool = True
    max_directional_exposure_pct: Decimal = Decimal("0.60")
    enable_max_hold_exit: bool = True
    max_hold_minutes: int = 90
    enable_pnl_pct_exit: bool = True
    take_profit_pct: Decimal = Decimal("0.006")
    stop_loss_pct: Decimal = Decimal("0.004")
    # Deprecated fallback for legacy envs; keep disabled by default.
    enable_pnl_usdt_exit: bool = False
    take_profit_usdt: Decimal = Decimal("0")
    stop_loss_usdt: Decimal = Decimal("0")
    enable_trailing_stop_exit: bool = True
    trailing_stop_pct: Decimal = Decimal("0.35")


class TradingStopSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADING_STOP_")

    retry_max_attempts: int = 3
    retry_interval_sec: float = 1.0
    confirm_timeout_sec: int = 30


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    exchange: ExchangeSettings = Field(default_factory=ExchangeSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    risk_guards: RiskGuardsSettings = Field(default_factory=RiskGuardsSettings)
    trading_stop: TradingStopSettings = Field(default_factory=TradingStopSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)

    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.JSON
    data_dir: Path = Path("./data")
    environment: str = "development"


def get_settings() -> AppSettings:
    return AppSettings()
