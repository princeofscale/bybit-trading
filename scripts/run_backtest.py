import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

from backtesting.backtester import Backtester
from backtesting.data_loader import BacktestDataLoader
from backtesting.models import BacktestConfig
from backtesting.report_generator import ReportGenerator
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.trend_following import TrendFollowingStrategy

STRATEGIES = {
    "ema_crossover": lambda: EmaCrossoverStrategy(["BTCUSDT"]),
    "mean_reversion": lambda: MeanReversionStrategy(["BTCUSDT"]),
    "trend_following": lambda: TrendFollowingStrategy(["BTCUSDT"]),
}

DATA_DIR = Path("data/historical")


def run(
    strategy_name: str = "ema_crossover",
    data_file: str | None = None,
    initial_equity: float = 100_000,
) -> None:
    if strategy_name not in STRATEGIES:
        print(f"Unknown strategy: {strategy_name}")
        print(f"Available: {', '.join(STRATEGIES.keys())}")
        return

    strategy = STRATEGIES[strategy_name]()
    loader = BacktestDataLoader()

    if data_file:
        df = loader.load_csv(Path(data_file))
    else:
        print("No data file specified, using synthetic data (200 candles)")
        df = loader.generate_synthetic(periods=200, start_price=50000.0)

    config = BacktestConfig(
        initial_equity=Decimal(str(initial_equity)),
        commission_rate=Decimal("0.0006"),
        slippage_pct=Decimal("0.0001"),
    )

    print(f"Running backtest: {strategy_name}")
    print(f"Data: {len(df)} candles")
    print(f"Initial equity: ${initial_equity:,.0f}")
    print("-" * 50)

    backtester = Backtester(config)
    result = backtester.run(strategy, df)

    report = ReportGenerator()
    metrics = report.generate(result)

    print(f"Final equity: ${float(result.final_equity):,.2f}")
    print(f"Total return: {float(result.final_equity / result.initial_equity - 1) * 100:.2f}%")
    print(f"Total trades: {metrics.total_trades}")
    print(f"Win rate: {float(metrics.win_rate) * 100:.1f}%")
    print(f"Sharpe ratio: {float(metrics.sharpe_ratio):.3f}")
    print(f"Max drawdown: {float(metrics.max_drawdown_pct) * 100:.2f}%")
    print(f"Profit factor: {float(metrics.profit_factor):.3f}")

    if metrics.total_trades > 0:
        print(f"Avg win: {float(metrics.avg_win) * 100:.2f}%")
        print(f"Avg loss: {float(metrics.avg_loss) * 100:.2f}%")


def main() -> None:
    strategy = sys.argv[1] if len(sys.argv) > 1 else "ema_crossover"
    data_file = sys.argv[2] if len(sys.argv) > 2 else None
    equity = float(sys.argv[3]) if len(sys.argv) > 3 else 100_000
    run(strategy, data_file, equity)


if __name__ == "__main__":
    main()
