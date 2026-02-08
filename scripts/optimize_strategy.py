import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from backtesting.backtester import Backtester
from backtesting.data_loader import BacktestDataLoader
from backtesting.models import BacktestConfig
from backtesting.report_generator import ReportGenerator
from strategies.ema_crossover import EmaCrossoverStrategy


def optimize(
    data_file: str | None = None,
    n_trials: int = 20,
) -> None:
    loader = BacktestDataLoader()

    if data_file:
        df = loader.load_csv(Path(data_file))
    else:
        print("No data file, using synthetic data (500 candles)")
        df = loader.generate_synthetic(periods=500, start_price=50000.0)

    train_df, test_df = loader.train_test_split(df, train_ratio=0.7)
    print(f"Train: {len(train_df)} candles, Test: {len(test_df)} candles")
    print(f"Running {n_trials} parameter combinations...")
    print("-" * 50)

    config = BacktestConfig(
        initial_equity=Decimal("100000"),
        commission_rate=Decimal("0.0006"),
        slippage_pct=Decimal("0.0001"),
    )

    best_sharpe = float("-inf")
    best_params: dict[str, int | float] = {}
    results: list[dict] = []

    np.random.seed(42)
    for trial in range(n_trials):
        fast = np.random.choice([5, 7, 9, 12])
        slow = np.random.choice([15, 21, 26, 30, 50])
        atr_mult = np.random.choice([1.5, 2.0, 2.5, 3.0])
        tp_mult = np.random.choice([2.0, 3.0, 4.0, 5.0])

        if fast >= slow:
            continue

        strategy = EmaCrossoverStrategy(
            symbols=["BTCUSDT"],
            fast_period=int(fast),
            slow_period=int(slow),
            atr_sl_multiplier=float(atr_mult),
            atr_tp_multiplier=float(tp_mult),
            volume_confirmation=False,
            min_confidence=0.3,
        )

        backtester = Backtester(config)
        result = backtester.run(strategy, train_df)
        report = ReportGenerator()
        metrics = report.generate(result)

        sharpe = float(metrics.sharpe_ratio)
        trial_result = {
            "fast": int(fast),
            "slow": int(slow),
            "atr_sl": float(atr_mult),
            "atr_tp": float(tp_mult),
            "sharpe": sharpe,
            "return": float(result.final_equity / result.initial_equity - 1),
            "trades": metrics.total_trades,
            "win_rate": float(metrics.win_rate),
            "max_dd": float(metrics.max_drawdown_pct),
        }
        results.append(trial_result)

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = {"fast": int(fast), "slow": int(slow), "atr_sl": float(atr_mult), "atr_tp": float(tp_mult)}

    results.sort(key=lambda r: r["sharpe"], reverse=True)

    print("\nTop 5 parameter sets (by Sharpe on train data):")
    for i, r in enumerate(results[:5]):
        print(f"  #{i+1}: fast={r['fast']}, slow={r['slow']}, "
              f"sl={r['atr_sl']}, tp={r['atr_tp']} | "
              f"Sharpe={r['sharpe']:.3f}, Return={r['return']*100:.1f}%, "
              f"Trades={r['trades']}, WR={r['win_rate']*100:.0f}%")

    if best_params:
        print(f"\nValidating best params on test set...")
        best_strategy = EmaCrossoverStrategy(
            symbols=["BTCUSDT"],
            fast_period=best_params["fast"],
            slow_period=best_params["slow"],
            atr_sl_multiplier=best_params["atr_sl"],
            atr_tp_multiplier=best_params["atr_tp"],
            volume_confirmation=False,
            min_confidence=0.3,
        )
        backtester = Backtester(config)
        test_result = backtester.run(best_strategy, test_df)
        test_metrics = ReportGenerator().generate(test_result)
        print(f"  Test Sharpe: {float(test_metrics.sharpe_ratio):.3f}")
        print(f"  Test Return: {float(test_result.final_equity / test_result.initial_equity - 1) * 100:.2f}%")
        print(f"  Test Max DD: {float(test_metrics.max_drawdown_pct) * 100:.2f}%")


def main() -> None:
    data_file = sys.argv[1] if len(sys.argv) > 1 else None
    n_trials = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    optimize(data_file, n_trials)


if __name__ == "__main__":
    main()
