from decimal import Decimal

from utils.math_utils import (
    kelly_fraction,
    max_drawdown,
    pct_change,
    risk_to_quantity,
)


def test_pct_change() -> None:
    assert pct_change(Decimal("110"), Decimal("100")) == Decimal("0.1")
    assert pct_change(Decimal("90"), Decimal("100")) == Decimal("-0.1")
    assert pct_change(Decimal("100"), Decimal("0")) == Decimal("0")


def test_risk_to_quantity() -> None:
    qty = risk_to_quantity(
        capital=Decimal("10000"),
        risk_pct=Decimal("0.02"),
        entry_price=Decimal("30000"),
        stop_loss_price=Decimal("29000"),
    )
    assert qty == Decimal("0.2")


def test_risk_to_quantity_zero_distance() -> None:
    qty = risk_to_quantity(
        capital=Decimal("10000"),
        risk_pct=Decimal("0.02"),
        entry_price=Decimal("30000"),
        stop_loss_price=Decimal("30000"),
    )
    assert qty == Decimal("0")


def test_kelly_fraction() -> None:
    kelly = kelly_fraction(win_rate=Decimal("0.6"), win_loss_ratio=Decimal("1.5"))
    assert kelly > Decimal("0")
    assert kelly <= Decimal("0.25")


def test_kelly_fraction_losing_strategy() -> None:
    kelly = kelly_fraction(win_rate=Decimal("0.3"), win_loss_ratio=Decimal("0.5"))
    assert kelly == Decimal("0")


def test_kelly_fraction_capped() -> None:
    kelly = kelly_fraction(win_rate=Decimal("0.9"), win_loss_ratio=Decimal("10"))
    assert kelly == Decimal("0.25")


def test_max_drawdown_basic() -> None:
    curve = [Decimal("100"), Decimal("110"), Decimal("90"), Decimal("105")]
    dd = max_drawdown(curve)
    expected = (Decimal("110") - Decimal("90")) / Decimal("110")
    assert dd == expected


def test_max_drawdown_empty() -> None:
    assert max_drawdown([]) == Decimal("0")


def test_max_drawdown_monotonic_up() -> None:
    curve = [Decimal("100"), Decimal("110"), Decimal("120")]
    assert max_drawdown(curve) == Decimal("0")
