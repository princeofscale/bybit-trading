from decimal import Decimal, ROUND_DOWN


def truncate_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError(f"Step must be positive, got {step}")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def validate_quantity(qty: Decimal, min_qty: Decimal, max_qty: Decimal, step: Decimal) -> Decimal:
    truncated = truncate_to_step(qty, step)
    if truncated < min_qty:
        raise ValueError(f"Quantity {truncated} below minimum {min_qty}")
    if truncated > max_qty:
        raise ValueError(f"Quantity {truncated} above maximum {max_qty}")
    return truncated


def validate_price(price: Decimal, tick_size: Decimal) -> Decimal:
    return truncate_to_step(price, tick_size)


def decimal_places_from_step(step: Decimal) -> int:
    step_str = str(step)
    if "." not in step_str:
        return 0
    return len(step_str.split(".")[1].rstrip("0")) or 0
