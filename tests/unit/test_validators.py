from decimal import Decimal

import pytest

from utils.validators import (
    decimal_places_from_step,
    truncate_to_step,
    validate_price,
    validate_quantity,
)


def test_truncate_to_step() -> None:
    assert truncate_to_step(Decimal("0.12345"), Decimal("0.001")) == Decimal("0.123")
    assert truncate_to_step(Decimal("100.99"), Decimal("0.01")) == Decimal("100.99")
    assert truncate_to_step(Decimal("0.5"), Decimal("1")) == Decimal("0")
    assert truncate_to_step(Decimal("1.5"), Decimal("1")) == Decimal("1")


def test_truncate_to_step_invalid() -> None:
    with pytest.raises(ValueError):
        truncate_to_step(Decimal("1.0"), Decimal("0"))


def test_validate_quantity_valid() -> None:
    result = validate_quantity(
        qty=Decimal("0.015"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("100"),
        step=Decimal("0.001"),
    )
    assert result == Decimal("0.015")


def test_validate_quantity_truncated() -> None:
    result = validate_quantity(
        qty=Decimal("0.0159"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("100"),
        step=Decimal("0.001"),
    )
    assert result == Decimal("0.015")


def test_validate_quantity_below_minimum() -> None:
    with pytest.raises(ValueError, match="below minimum"):
        validate_quantity(
            qty=Decimal("0.0001"),
            min_qty=Decimal("0.001"),
            max_qty=Decimal("100"),
            step=Decimal("0.001"),
        )


def test_validate_quantity_above_maximum() -> None:
    with pytest.raises(ValueError, match="above maximum"):
        validate_quantity(
            qty=Decimal("200"),
            min_qty=Decimal("0.001"),
            max_qty=Decimal("100"),
            step=Decimal("0.001"),
        )


def test_validate_price() -> None:
    result = validate_price(Decimal("30000.567"), Decimal("0.01"))
    assert result == Decimal("30000.56")


def test_decimal_places_from_step() -> None:
    assert decimal_places_from_step(Decimal("0.001")) == 3
    assert decimal_places_from_step(Decimal("0.01")) == 2
    assert decimal_places_from_step(Decimal("1")) == 0
    assert decimal_places_from_step(Decimal("0.10")) == 1
