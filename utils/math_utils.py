from decimal import Decimal


def pct_change(current: Decimal, previous: Decimal) -> Decimal:
    if previous == 0:
        return Decimal("0")
    return (current - previous) / previous


def risk_to_quantity(
    capital: Decimal,
    risk_pct: Decimal,
    entry_price: Decimal,
    stop_loss_price: Decimal,
) -> Decimal:
    risk_amount = capital * risk_pct
    price_distance = abs(entry_price - stop_loss_price)
    if price_distance == 0:
        return Decimal("0")
    return risk_amount / price_distance


def kelly_fraction(win_rate: Decimal, win_loss_ratio: Decimal) -> Decimal:
    if win_loss_ratio == 0:
        return Decimal("0")
    kelly = win_rate - (1 - win_rate) / win_loss_ratio
    return max(Decimal("0"), min(kelly, Decimal("0.25")))


def sharpe_ratio(
    returns: list[Decimal],
    risk_free_rate: Decimal = Decimal("0"),
    periods_per_year: int = 365,
) -> Decimal:
    if len(returns) < 2:
        return Decimal("0")
    mean_return = sum(returns) / len(returns)
    excess_returns = [r - risk_free_rate / periods_per_year for r in returns]
    variance = sum((r - mean_return) ** 2 for r in excess_returns) / (len(returns) - 1)
    std_dev = variance ** Decimal("0.5")
    if std_dev == 0:
        return Decimal("0")
    return (mean_return * periods_per_year) / (std_dev * Decimal(str(periods_per_year ** 0.5)))


def max_drawdown(equity_curve: list[Decimal]) -> Decimal:
    if not equity_curve:
        return Decimal("0")
    peak = equity_curve[0]
    max_dd = Decimal("0")
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else Decimal("0")
        if dd > max_dd:
            max_dd = dd
    return max_dd
