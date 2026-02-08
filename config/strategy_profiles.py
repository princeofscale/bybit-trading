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
    circuit_breaker_consecutive_losses: int
    circuit_breaker_cooldown_hours: int
    take_profit_multiplier: float
    stop_loss_multiplier: float
    min_confidence: float
    max_portfolio_risk: Decimal


CONSERVATIVE_PROFILE = StrategyProfile(
    name=RiskProfile.CONSERVATIVE,
    risk_per_trade=Decimal("0.01"),
    max_leverage=Decimal("1.5"),
    max_drawdown_pct=Decimal("0.08"),
    max_daily_loss_pct=Decimal("0.03"),
    max_concurrent_positions=5,
    circuit_breaker_consecutive_losses=2,
    circuit_breaker_cooldown_hours=6,
    take_profit_multiplier=2.0,
    stop_loss_multiplier=1.5,
    min_confidence=0.7,
    max_portfolio_risk=Decimal("0.05"),
)


MODERATE_PROFILE = StrategyProfile(
    name=RiskProfile.MODERATE,
    risk_per_trade=Decimal("0.02"),
    max_leverage=Decimal("3.0"),
    max_drawdown_pct=Decimal("0.15"),
    max_daily_loss_pct=Decimal("0.05"),
    max_concurrent_positions=10,
    circuit_breaker_consecutive_losses=3,
    circuit_breaker_cooldown_hours=4,
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
    circuit_breaker_consecutive_losses=5,
    circuit_breaker_cooldown_hours=2,
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


def profile_to_risk_settings(profile: StrategyProfile) -> dict[str, Decimal | int]:
    return {
        "max_risk_per_trade": profile.risk_per_trade,
        "max_leverage": profile.max_leverage,
        "max_drawdown_pct": profile.max_drawdown_pct,
        "max_daily_loss_pct": profile.max_daily_loss_pct,
        "max_concurrent_positions": profile.max_concurrent_positions,
        "max_portfolio_risk": profile.max_portfolio_risk,
        "circuit_breaker_consecutive_losses": profile.circuit_breaker_consecutive_losses,
        "circuit_breaker_cooldown_hours": profile.circuit_breaker_cooldown_hours,
    }
