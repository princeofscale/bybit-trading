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
    circuit_breaker_consecutive_losses: int = 3
    circuit_breaker_cooldown_hours: int = 4
    funding_arb_max_allocation: Decimal = Decimal("0.30")


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
    trading: TradingSettings = Field(default_factory=TradingSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)

    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.JSON
    data_dir: Path = Path("./data")
    environment: str = "development"


def get_settings() -> AppSettings:
    return AppSettings()
