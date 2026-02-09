from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class RiskProfile(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class StrategyProfile(BaseModel):
    name: RiskProfile
    risk_per_trade: Decimal
    max_leverage: Decimal
    max_drawdown_pct: Decimal
    max_daily_loss_pct: Decimal
    max_concurrent_positions: int
    enable_circuit_breaker: bool
    circuit_breaker_consecutive_losses: int
    circuit_breaker_cooldown_hours: int
    enable_daily_loss_limit: bool
    daily_loss_limit_pct: Decimal
    enable_symbol_cooldown: bool
    symbol_cooldown_minutes: int
    soft_stop_threshold_pct: Decimal
    soft_stop_min_confidence: float
    portfolio_heat_limit_pct: Decimal
    max_spread_bps: Decimal
    min_liquidity_score: float
    take_profit_multiplier: float
    stop_loss_multiplier: float
    min_confidence: float
    max_portfolio_risk: Decimal


CONSERVATIVE_PROFILE = StrategyProfile(
    name=RiskProfile.CONSERVATIVE,
    risk_per_trade=Decimal("0.01"),
    max_leverage=Decimal("2.0"),
    max_drawdown_pct=Decimal("0.10"),
    max_daily_loss_pct=Decimal("0.03"),
    max_concurrent_positions=6,
    enable_circuit_breaker=True,
    circuit_breaker_consecutive_losses=3,
    circuit_breaker_cooldown_hours=2,
    enable_daily_loss_limit=True,
    daily_loss_limit_pct=Decimal("0.03"),
    enable_symbol_cooldown=True,
    symbol_cooldown_minutes=60,
    soft_stop_threshold_pct=Decimal("0.80"),
    soft_stop_min_confidence=0.75,
    portfolio_heat_limit_pct=Decimal("0.08"),
    max_spread_bps=Decimal("15"),
    min_liquidity_score=0.35,
    take_profit_multiplier=2.5,
    stop_loss_multiplier=1.5,
    min_confidence=0.6,
    max_portfolio_risk=Decimal("0.08"),
)


MODERATE_PROFILE = StrategyProfile(
    name=RiskProfile.MODERATE,
    risk_per_trade=Decimal("0.02"),
    max_leverage=Decimal("3.0"),
    max_drawdown_pct=Decimal("0.15"),
    max_daily_loss_pct=Decimal("0.05"),
    max_concurrent_positions=10,
    enable_circuit_breaker=True,
    circuit_breaker_consecutive_losses=3,
    circuit_breaker_cooldown_hours=4,
    enable_daily_loss_limit=True,
    daily_loss_limit_pct=Decimal("0.05"),
    enable_symbol_cooldown=True,
    symbol_cooldown_minutes=180,
    soft_stop_threshold_pct=Decimal("0.80"),
    soft_stop_min_confidence=0.75,
    portfolio_heat_limit_pct=Decimal("0.08"),
    max_spread_bps=Decimal("15"),
    min_liquidity_score=0.35,
    take_profit_multiplier=3.0,
    stop_loss_multiplier=2.0,
    min_confidence=0.5,
    max_portfolio_risk=Decimal("0.10"),
)


AGGRESSIVE_PROFILE = StrategyProfile(
    name=RiskProfile.AGGRESSIVE,
    risk_per_trade=Decimal("0.04"),
    max_leverage=Decimal("5.0"),
    max_drawdown_pct=Decimal("0.25"),
    max_daily_loss_pct=Decimal("0.08"),
    max_concurrent_positions=15,
    enable_circuit_breaker=True,
    circuit_breaker_consecutive_losses=5,
    circuit_breaker_cooldown_hours=2,
    enable_daily_loss_limit=True,
    daily_loss_limit_pct=Decimal("0.08"),
    enable_symbol_cooldown=True,
    symbol_cooldown_minutes=90,
    soft_stop_threshold_pct=Decimal("0.80"),
    soft_stop_min_confidence=0.70,
    portfolio_heat_limit_pct=Decimal("0.12"),
    max_spread_bps=Decimal("22"),
    min_liquidity_score=0.25,
    take_profit_multiplier=4.0,
    stop_loss_multiplier=2.5,
    min_confidence=0.4,
    max_portfolio_risk=Decimal("0.20"),
)


ALL_PROFILES: dict[RiskProfile, StrategyProfile] = {
    RiskProfile.CONSERVATIVE: CONSERVATIVE_PROFILE,
    RiskProfile.MODERATE: MODERATE_PROFILE,
    RiskProfile.AGGRESSIVE: AGGRESSIVE_PROFILE,
}


def get_profile(name: RiskProfile) -> StrategyProfile:
    return ALL_PROFILES[name]


def profile_to_risk_settings(
    profile: StrategyProfile,
) -> dict[str, Decimal | int | float | bool]:
    return {
        "max_risk_per_trade": profile.risk_per_trade,
        "max_leverage": profile.max_leverage,
        "max_drawdown_pct": profile.max_drawdown_pct,
        "max_daily_loss_pct": profile.daily_loss_limit_pct,
        "max_concurrent_positions": profile.max_concurrent_positions,
        "max_portfolio_risk": profile.max_portfolio_risk,
        "enable_circuit_breaker": profile.enable_circuit_breaker,
        "circuit_breaker_consecutive_losses": profile.circuit_breaker_consecutive_losses,
        "circuit_breaker_cooldown_hours": profile.circuit_breaker_cooldown_hours,
        "enable_daily_loss_limit": profile.enable_daily_loss_limit,
        "enable_symbol_cooldown": profile.enable_symbol_cooldown,
        "symbol_cooldown_minutes": profile.symbol_cooldown_minutes,
        "soft_stop_threshold_pct": profile.soft_stop_threshold_pct,
        "soft_stop_min_confidence": profile.soft_stop_min_confidence,
        "portfolio_heat_limit_pct": profile.portfolio_heat_limit_pct,
        "max_spread_bps": profile.max_spread_bps,
        "min_liquidity_score": profile.min_liquidity_score,
    }
