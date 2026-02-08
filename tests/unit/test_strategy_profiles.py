from decimal import Decimal

import pytest

from config.strategy_profiles import (
    AGGRESSIVE_PROFILE,
    ALL_PROFILES,
    CONSERVATIVE_PROFILE,
    MODERATE_PROFILE,
    RiskProfile,
    StrategyProfile,
    get_profile,
    profile_to_risk_settings,
)


class TestProfiles:
    def test_conservative_lower_risk(self) -> None:
        assert CONSERVATIVE_PROFILE.risk_per_trade == Decimal("0.01")
        assert CONSERVATIVE_PROFILE.max_leverage == Decimal("1.5")
        assert CONSERVATIVE_PROFILE.max_concurrent_positions == 5

    def test_moderate_default(self) -> None:
        assert MODERATE_PROFILE.risk_per_trade == Decimal("0.02")
        assert MODERATE_PROFILE.max_leverage == Decimal("3.0")
        assert MODERATE_PROFILE.max_concurrent_positions == 10

    def test_aggressive_higher_risk(self) -> None:
        assert AGGRESSIVE_PROFILE.risk_per_trade == Decimal("0.04")
        assert AGGRESSIVE_PROFILE.max_leverage == Decimal("5.0")
        assert AGGRESSIVE_PROFILE.max_concurrent_positions == 15

    def test_risk_ordering(self) -> None:
        assert CONSERVATIVE_PROFILE.risk_per_trade < MODERATE_PROFILE.risk_per_trade
        assert MODERATE_PROFILE.risk_per_trade < AGGRESSIVE_PROFILE.risk_per_trade

    def test_leverage_ordering(self) -> None:
        assert CONSERVATIVE_PROFILE.max_leverage < MODERATE_PROFILE.max_leverage
        assert MODERATE_PROFILE.max_leverage < AGGRESSIVE_PROFILE.max_leverage

    def test_drawdown_ordering(self) -> None:
        assert CONSERVATIVE_PROFILE.max_drawdown_pct < MODERATE_PROFILE.max_drawdown_pct
        assert MODERATE_PROFILE.max_drawdown_pct < AGGRESSIVE_PROFILE.max_drawdown_pct

    def test_confidence_ordering(self) -> None:
        assert CONSERVATIVE_PROFILE.min_confidence > MODERATE_PROFILE.min_confidence
        assert MODERATE_PROFILE.min_confidence > AGGRESSIVE_PROFILE.min_confidence

    def test_all_profiles_in_dict(self) -> None:
        assert len(ALL_PROFILES) == 3
        assert RiskProfile.CONSERVATIVE in ALL_PROFILES
        assert RiskProfile.MODERATE in ALL_PROFILES
        assert RiskProfile.AGGRESSIVE in ALL_PROFILES


class TestGetProfile:
    def test_get_conservative(self) -> None:
        p = get_profile(RiskProfile.CONSERVATIVE)
        assert p.name == RiskProfile.CONSERVATIVE

    def test_get_moderate(self) -> None:
        p = get_profile(RiskProfile.MODERATE)
        assert p.name == RiskProfile.MODERATE

    def test_get_aggressive(self) -> None:
        p = get_profile(RiskProfile.AGGRESSIVE)
        assert p.name == RiskProfile.AGGRESSIVE


class TestProfileToSettings:
    def test_converts_to_dict(self) -> None:
        settings = profile_to_risk_settings(MODERATE_PROFILE)
        assert settings["max_risk_per_trade"] == Decimal("0.02")
        assert settings["max_leverage"] == Decimal("3.0")
        assert settings["max_drawdown_pct"] == Decimal("0.15")
        assert settings["max_concurrent_positions"] == 10

    def test_conservative_settings(self) -> None:
        settings = profile_to_risk_settings(CONSERVATIVE_PROFILE)
        assert settings["max_risk_per_trade"] == Decimal("0.01")
        assert settings["max_daily_loss_pct"] == Decimal("0.03")

    def test_aggressive_settings(self) -> None:
        settings = profile_to_risk_settings(AGGRESSIVE_PROFILE)
        assert settings["max_portfolio_risk"] == Decimal("0.20")
