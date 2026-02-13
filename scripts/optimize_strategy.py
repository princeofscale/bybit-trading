import sys
from decimal import Decimal
from pathlib import Path

import numpy as np

from backtesting.backtester import Backtester
from backtesting.data_loader import BacktestDataLoader
from backtesting.models import BacktestConfig
from backtesting.monte_carlo import run_monte_carlo
from backtesting.report_generator import ReportGenerator
from strategies.ema_crossover import EmaCrossoverStrategy


SYMBOL = "BTC/USDT:USDT"


def _build_strategy(fast: int, slow: int, atr_sl: float, atr_tp: float) -> EmaCrossoverStrategy:
    return EmaCrossoverStrategy(
        symbols=[SYMBOL],
        fast_period=fast,
        slow_period=slow,
        atr_sl_multiplier=atr_sl,
        atr_tp_multiplier=atr_tp,
        volume_confirmation=False,
        min_confidence=0.3,
    )


def optimize_optuna(
    data_file: str | None = None,
    n_trials: int = 100,
) -> None:
    try:
        import optuna
    except ImportError:
        print("optuna not installed, falling back to random search")
        optimize_random(data_file, n_trials)
        return

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    loader = BacktestDataLoader()

    if data_file:
        df = loader.load_csv(Path(data_file))
    else:
        print("No data file, using synthetic data (500 candles)")
        df = loader.generate_synthetic(periods=500, start_price=50000.0)

    train_df, test_df = loader.train_test_split(df, train_ratio=0.7)
    print(f"Train: {len(train_df)} candles, Test: {len(test_df)} candles")
    print(f"Running Optuna optimization with {n_trials} trials...")
    print("-" * 50)

    config = BacktestConfig(
        initial_equity=Decimal("100000"),
        slippage_pct=Decimal("0.0001"),
    )

    def objective(trial: optuna.Trial) -> float:
        fast = trial.suggest_int("fast", 5, 15)
        slow = trial.suggest_int("slow", 16, 60)
        atr_sl = trial.suggest_float("atr_sl", 1.0, 4.0, step=0.5)
        atr_tp = trial.suggest_float("atr_tp", 1.5, 6.0, step=0.5)

        strategy = _build_strategy(fast, slow, atr_sl, atr_tp)
        backtester = Backtester(config)
        result = backtester.run(strategy, SYMBOL, train_df)
        metrics = ReportGenerator().calculate_metrics(result)
        return float(metrics.sharpe_ratio)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)

    print(f"\nBest trial (Sharpe on train): {study.best_value:.3f}")
    bp = study.best_params
    print(f"  Params: fast={bp['fast']}, slow={bp['slow']}, "
          f"atr_sl={bp['atr_sl']}, atr_tp={bp['atr_tp']}")

    print("\nTop 5 trials:")
    for i, trial in enumerate(sorted(study.trials, key=lambda t: t.value or 0, reverse=True)[:5]):
        p = trial.params
        print(f"  #{i+1}: fast={p['fast']}, slow={p['slow']}, "
              f"sl={p['atr_sl']}, tp={p['atr_tp']} | Sharpe={trial.value:.3f}")

    print(f"\nValidating best params on test set...")
    best_strategy = _build_strategy(bp["fast"], bp["slow"], bp["atr_sl"], bp["atr_tp"])
    backtester = Backtester(config)
    test_result = backtester.run(best_strategy, SYMBOL, test_df)
    test_metrics = ReportGenerator().calculate_metrics(test_result)
    print(f"  Test Sharpe: {float(test_metrics.sharpe_ratio):.3f}")
    print(f"  Test Return: {float(test_result.final_equity / test_result.initial_equity - 1) * 100:.2f}%")
    print(f"  Test Max DD: {float(test_metrics.max_drawdown_pct) * 100:.2f}%")

    if test_result.trades:
        print(f"\nMonte Carlo simulation (1000 paths)...")
        mc = run_monte_carlo(test_result.trades, config.initial_equity, num_simulations=1000)
        print(f"  Median equity: {mc.median_final_equity:,.0f}")
        print(f"  95% CI: [{mc.ci_95_low:,.0f}, {mc.ci_95_high:,.0f}]")
        print(f"  Median max DD: {mc.median_max_drawdown * 100:.1f}%")
        print(f"  95th pct DD: {mc.dd_ci_95 * 100:.1f}%")
        print(f"  Median Sharpe: {mc.median_sharpe:.3f}")
        print(f"  Sharpe 95% CI: [{mc.sharpe_ci_95_low:.3f}, {mc.sharpe_ci_95_high:.3f}]")
        print(f"  Ruin probability (50% drawdown): {mc.ruin_probability * 100:.1f}%")


def optimize_random(
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
        slippage_pct=Decimal("0.0001"),
    )

    best_sharpe = float("-inf")
    best_params: dict[str, int | float] = {}
    results: list[dict] = []

    np.random.seed(42)
    for trial in range(n_trials):
        fast = int(np.random.choice([5, 7, 9, 12]))
        slow = int(np.random.choice([15, 21, 26, 30, 50]))
        atr_mult = float(np.random.choice([1.5, 2.0, 2.5, 3.0]))
        tp_mult = float(np.random.choice([2.0, 3.0, 4.0, 5.0]))

        if fast >= slow:
            continue

        strategy = _build_strategy(fast, slow, atr_mult, tp_mult)
        backtester = Backtester(config)
        result = backtester.run(strategy, SYMBOL, train_df)
        report = ReportGenerator()
        metrics = report.calculate_metrics(result)

        sharpe = float(metrics.sharpe_ratio)
        trial_result = {
            "fast": fast, "slow": slow,
            "atr_sl": atr_mult, "atr_tp": tp_mult,
            "sharpe": sharpe,
            "return": float(result.final_equity / result.initial_equity - 1),
            "trades": metrics.total_trades,
            "win_rate": float(metrics.win_rate),
            "max_dd": float(metrics.max_drawdown_pct),
        }
        results.append(trial_result)

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = {"fast": fast, "slow": slow, "atr_sl": atr_mult, "atr_tp": tp_mult}

    results.sort(key=lambda r: r["sharpe"], reverse=True)

    print("\nTop 5 parameter sets (by Sharpe on train data):")
    for i, r in enumerate(results[:5]):
        print(f"  #{i+1}: fast={r['fast']}, slow={r['slow']}, "
              f"sl={r['atr_sl']}, tp={r['atr_tp']} | "
              f"Sharpe={r['sharpe']:.3f}, Return={r['return']*100:.1f}%, "
              f"Trades={r['trades']}, WR={r['win_rate']*100:.0f}%")

    if best_params:
        print(f"\nValidating best params on test set...")
        best_strategy = _build_strategy(
            int(best_params["fast"]), int(best_params["slow"]),
            best_params["atr_sl"], best_params["atr_tp"],
        )
        backtester = Backtester(config)
        test_result = backtester.run(best_strategy, SYMBOL, test_df)
        test_metrics = ReportGenerator().calculate_metrics(test_result)
        print(f"  Test Sharpe: {float(test_metrics.sharpe_ratio):.3f}")
        print(f"  Test Return: {float(test_result.final_equity / test_result.initial_equity - 1) * 100:.2f}%")
        print(f"  Test Max DD: {float(test_metrics.max_drawdown_pct) * 100:.2f}%")

        if test_result.trades:
            print(f"\nMonte Carlo simulation (1000 paths)...")
            mc = run_monte_carlo(test_result.trades, config.initial_equity, num_simulations=1000)
            print(f"  Median equity: {mc.median_final_equity:,.0f}")
            print(f"  95% CI: [{mc.ci_95_low:,.0f}, {mc.ci_95_high:,.0f}]")
            print(f"  Median max DD: {mc.median_max_drawdown * 100:.1f}%")
            print(f"  Ruin probability: {mc.ruin_probability * 100:.1f}%")


def main() -> None:
    data_file = sys.argv[1] if len(sys.argv) > 1 else None
    n_trials = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    use_optuna = "--optuna" in sys.argv or "--no-optuna" not in sys.argv
    if use_optuna:
        optimize_optuna(data_file, n_trials)
    else:
        optimize_random(data_file, n_trials)


if __name__ == "__main__":
    main()
