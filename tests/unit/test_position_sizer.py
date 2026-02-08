from decimal import Decimal

import pytest

from config.settings import RiskSettings
from risk.position_sizer import PositionSizer, SizingMethod


@pytest.fixture
def risk_settings() -> RiskSettings:
    return RiskSettings(
        max_risk_per_trade=Decimal("0.02"),
        max_leverage=Decimal("3.0"),
    )


@pytest.fixture
def sizer(risk_settings: RiskSettings) -> PositionSizer:
    return PositionSizer(risk_settings)


class TestFixedFractional:
    def test_basic_calculation(self, sizer: PositionSizer) -> None:
        qty = sizer.fixed_fractional(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("95"),
        )
        expected = Decimal("10000") * Decimal("0.02") / Decimal("5")
        assert qty == expected
        assert qty == Decimal("40")

    def test_tight_stop_gives_smaller_position(self, sizer: PositionSizer) -> None:
        wide = sizer.fixed_fractional(
            Decimal("10000"), Decimal("100"), Decimal("90"),
        )
        tight = sizer.fixed_fractional(
            Decimal("10000"), Decimal("100"), Decimal("98"),
        )
        assert tight > wide

    def test_leverage_cap(self, sizer: PositionSizer) -> None:
        qty = sizer.fixed_fractional(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("99.99"),
        )
        max_leverage_qty = Decimal("10000") * Decimal("3.0") / Decimal("100")
        assert qty == max_leverage_qty
        assert qty == Decimal("300")

    def test_zero_entry_returns_zero(self, sizer: PositionSizer) -> None:
        qty = sizer.fixed_fractional(
            Decimal("10000"), Decimal("0"), Decimal("95"),
        )
        assert qty == Decimal("0")

    def test_zero_stop_returns_zero(self, sizer: PositionSizer) -> None:
        qty = sizer.fixed_fractional(
            Decimal("10000"), Decimal("100"), Decimal("0"),
        )
        assert qty == Decimal("0")

    def test_same_entry_stop_returns_zero(self, sizer: PositionSizer) -> None:
        qty = sizer.fixed_fractional(
            Decimal("10000"), Decimal("100"), Decimal("100"),
        )
        assert qty == Decimal("0")

    def test_short_position_stop_above(self, sizer: PositionSizer) -> None:
        qty = sizer.fixed_fractional(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("105"),
        )
        expected = Decimal("10000") * Decimal("0.02") / Decimal("5")
        assert qty == expected

    def test_larger_equity_larger_position(self, sizer: PositionSizer) -> None:
        small = sizer.fixed_fractional(
            Decimal("5000"), Decimal("100"), Decimal("95"),
        )
        large = sizer.fixed_fractional(
            Decimal("20000"), Decimal("100"), Decimal("95"),
        )
        assert large > small
        assert large / small == Decimal("4")


class TestKellyCriterion:
    def test_positive_edge(self, sizer: PositionSizer) -> None:
        qty = sizer.kelly_criterion(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("95"),
            win_rate=Decimal("0.6"),
            avg_win=Decimal("2"),
            avg_loss=Decimal("1"),
        )
        assert qty > Decimal("0")

    def test_no_edge_returns_zero(self, sizer: PositionSizer) -> None:
        qty = sizer.kelly_criterion(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("95"),
            win_rate=Decimal("0.3"),
            avg_win=Decimal("1"),
            avg_loss=Decimal("1"),
        )
        assert qty == Decimal("0")

    def test_kelly_capped_at_25pct(self, sizer: PositionSizer) -> None:
        qty = sizer.kelly_criterion(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("95"),
            win_rate=Decimal("0.95"),
            avg_win=Decimal("10"),
            avg_loss=Decimal("1"),
        )
        kelly_raw = Decimal("0.95") - Decimal("0.05") / Decimal("10")
        assert kelly_raw > Decimal("0.25")
        capped_kelly = Decimal("0.25")
        half_kelly_risk = Decimal("10000") * capped_kelly / 2
        expected_from_risk = half_kelly_risk / Decimal("5")
        max_lev = Decimal("10000") * Decimal("3") / Decimal("100")
        expected = min(expected_from_risk, max_lev)
        assert qty == expected

    def test_half_kelly_used(self, sizer: PositionSizer) -> None:
        qty = sizer.kelly_criterion(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("95"),
            win_rate=Decimal("0.6"),
            avg_win=Decimal("1.5"),
            avg_loss=Decimal("1"),
        )
        kelly_raw = Decimal("0.6") - Decimal("0.4") / Decimal("1.5")
        assert kelly_raw > Decimal("0.25")
        capped = Decimal("0.25")
        half = capped / 2
        risk_amount = Decimal("10000") * half
        expected = risk_amount / Decimal("5")
        assert qty == expected
        assert qty == Decimal("250")

    def test_zero_avg_loss_returns_zero(self, sizer: PositionSizer) -> None:
        qty = sizer.kelly_criterion(
            Decimal("10000"), Decimal("100"), Decimal("95"),
            Decimal("0.6"), Decimal("2"), Decimal("0"),
        )
        assert qty == Decimal("0")


class TestVolatilityBased:
    def test_basic_volatility_sizing(self, sizer: PositionSizer) -> None:
        qty = sizer.volatility_based(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            atr_value=Decimal("5"),
            atr_multiplier=Decimal("2"),
        )
        expected = Decimal("10000") * Decimal("0.02") / (Decimal("5") * Decimal("2"))
        assert qty == expected
        assert qty == Decimal("20")

    def test_higher_atr_smaller_position(self, sizer: PositionSizer) -> None:
        low_vol = sizer.volatility_based(
            Decimal("10000"), Decimal("100"), Decimal("2"), Decimal("2"),
        )
        high_vol = sizer.volatility_based(
            Decimal("10000"), Decimal("100"), Decimal("10"), Decimal("2"),
        )
        assert low_vol > high_vol

    def test_zero_atr_returns_zero(self, sizer: PositionSizer) -> None:
        qty = sizer.volatility_based(
            Decimal("10000"), Decimal("100"), Decimal("0"),
        )
        assert qty == Decimal("0")

    def test_leverage_cap_applies(self, sizer: PositionSizer) -> None:
        qty = sizer.volatility_based(
            equity=Decimal("10000"),
            entry_price=Decimal("100"),
            atr_value=Decimal("0.01"),
            atr_multiplier=Decimal("1"),
        )
        max_lev = Decimal("10000") * Decimal("3") / Decimal("100")
        assert qty == max_lev


class TestCalculateSize:
    def test_dispatch_fixed_fractional(self, sizer: PositionSizer) -> None:
        qty = sizer.calculate_size(
            SizingMethod.FIXED_FRACTIONAL,
            Decimal("10000"), Decimal("100"), Decimal("95"),
        )
        direct = sizer.fixed_fractional(
            Decimal("10000"), Decimal("100"), Decimal("95"),
        )
        assert qty == direct

    def test_dispatch_kelly(self, sizer: PositionSizer) -> None:
        qty = sizer.calculate_size(
            SizingMethod.KELLY,
            Decimal("10000"), Decimal("100"), Decimal("95"),
            win_rate=Decimal("0.6"),
            avg_win=Decimal("2"),
            avg_loss=Decimal("1"),
        )
        assert qty > Decimal("0")

    def test_dispatch_volatility(self, sizer: PositionSizer) -> None:
        qty = sizer.calculate_size(
            SizingMethod.VOLATILITY,
            Decimal("10000"), Decimal("100"), Decimal("95"),
            atr_value=Decimal("5"),
            atr_multiplier=Decimal("2"),
        )
        direct = sizer.volatility_based(
            Decimal("10000"), Decimal("100"), Decimal("5"), Decimal("2"),
        )
        assert qty == direct
