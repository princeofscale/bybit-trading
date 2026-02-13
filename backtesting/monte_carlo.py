import math
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from backtesting.models import BacktestTrade


@dataclass
class MonteCarloResult:
    num_simulations: int
    median_final_equity: float
    ci_95_low: float
    ci_95_high: float
    median_max_drawdown: float
    dd_ci_95: float
    median_sharpe: float
    sharpe_ci_95_low: float
    sharpe_ci_95_high: float
    ruin_probability: float


def run_monte_carlo(
    trades: list[BacktestTrade],
    initial_equity: Decimal = Decimal("10000"),
    num_simulations: int = 1000,
    ruin_threshold: float = 0.5,
) -> MonteCarloResult:
    if not trades:
        return MonteCarloResult(
            num_simulations=num_simulations,
            median_final_equity=float(initial_equity),
            ci_95_low=float(initial_equity),
            ci_95_high=float(initial_equity),
            median_max_drawdown=0.0,
            dd_ci_95=0.0,
            median_sharpe=0.0,
            sharpe_ci_95_low=0.0,
            sharpe_ci_95_high=0.0,
            ruin_probability=0.0,
        )

    returns = np.array([float(t.pnl_pct) for t in trades])
    n_trades = len(returns)
    init_eq = float(initial_equity)
    rng = np.random.default_rng(42)

    final_equities = np.zeros(num_simulations)
    max_drawdowns = np.zeros(num_simulations)
    sharpes = np.zeros(num_simulations)
    ruin_count = 0

    for i in range(num_simulations):
        shuffled = rng.permutation(returns)
        equity = init_eq
        peak = equity
        max_dd = 0.0
        eq_returns = []

        for r in shuffled:
            prev_equity = equity
            equity *= (1 + r)
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
            eq_returns.append((equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0)

        final_equities[i] = equity
        max_drawdowns[i] = max_dd

        if len(eq_returns) >= 2:
            mean_r = np.mean(eq_returns)
            std_r = np.std(eq_returns, ddof=1)
            sharpes[i] = (mean_r / std_r * math.sqrt(n_trades)) if std_r > 0 else 0.0
        else:
            sharpes[i] = 0.0

        if equity < init_eq * ruin_threshold:
            ruin_count += 1

    return MonteCarloResult(
        num_simulations=num_simulations,
        median_final_equity=float(np.median(final_equities)),
        ci_95_low=float(np.percentile(final_equities, 2.5)),
        ci_95_high=float(np.percentile(final_equities, 97.5)),
        median_max_drawdown=float(np.median(max_drawdowns)),
        dd_ci_95=float(np.percentile(max_drawdowns, 95)),
        median_sharpe=float(np.median(sharpes)),
        sharpe_ci_95_low=float(np.percentile(sharpes, 2.5)),
        sharpe_ci_95_high=float(np.percentile(sharpes, 97.5)),
        ruin_probability=ruin_count / num_simulations,
    )
