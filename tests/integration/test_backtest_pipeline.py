from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from backtesting.backtester import Backtester
from backtesting.data_loader import BacktestDataLoader
from backtesting.models import BacktestConfig, TradeSide
from backtesting.report_generator import ReportGenerator
from backtesting.simulator import FillSimulator
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection


class TrendStrategy(BaseStrategy):
    def __init__(self) -> None:
        super().__init__("test_trend", ["BTCUSDT"])

    def min_candles_required(self) -> int:
        return 20

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < 20:
            return None
        sma_fast = df["close"].rolling(5).mean().iloc[-1]
        sma_slow = df["close"].rolling(20).mean().iloc[-1]
        prev_fast = df["close"].rolling(5).mean().iloc[-2]
        prev_slow = df["close"].rolling(20).mean().iloc[-2]
        current_price = float(df["close"].iloc[-1])

        if prev_fast <= prev_slow and sma_fast > sma_slow:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.LONG,
                confidence=0.7,
                strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(current_price * 0.97, 2))),
                take_profit=Decimal(str(round(current_price * 1.06, 2))),
            )
        if prev_fast >= prev_slow and sma_fast < sma_slow:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.SHORT,
                confidence=0.7,
                strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(current_price * 1.03, 2))),
                take_profit=Decimal(str(round(current_price * 0.94, 2))),
            )
        return None


class TestFullBacktestPipeline:
    def test_end_to_end_backtest(self) -> None:
        loader = BacktestDataLoader()
        df = loader.generate_synthetic(n_bars=200, start_price=50000.0)
        strategy = TrendStrategy()
        config = BacktestConfig(
            initial_equity=Decimal("100000"),
            taker_fee=Decimal("0.0006"),
            slippage_pct=Decimal("0.0001"),
        )
        backtester = Backtester(config)
        result = backtester.run(strategy, "BTCUSDT", df)

        assert result.config.initial_equity == Decimal("100000")
        assert result.final_equity > Decimal("0")
        assert len(result.equity_curve) > 0

    def test_report_generation(self) -> None:
        loader = BacktestDataLoader()
        df = loader.generate_synthetic(n_bars=200, start_price=50000.0)
        strategy = TrendStrategy()
        config = BacktestConfig(
            initial_equity=Decimal("100000"),
            taker_fee=Decimal("0.0006"),
            slippage_pct=Decimal("0.0001"),
        )
        backtester = Backtester(config)
        result = backtester.run(strategy, "BTCUSDT", df)
        report = ReportGenerator()
        metrics = report.calculate_metrics(result)

        assert metrics.total_trades >= 0
        assert metrics.max_drawdown_pct >= Decimal("0")
        if metrics.total_trades > 0:
            assert metrics.win_rate >= Decimal("0")
            assert metrics.win_rate <= Decimal("1")

    def test_fill_simulator_applies_costs(self) -> None:
        config = BacktestConfig(
            taker_fee=Decimal("0.001"),
            slippage_pct=Decimal("0.0005"),
        )
        simulator = FillSimulator(config)
        fill_price, commission, slippage = simulator.simulate_entry(
            Decimal("50000"), Decimal("1"), TradeSide.LONG,
        )
        assert fill_price > Decimal("50000")
        assert commission > Decimal("0")

    def test_data_loader_synthetic(self) -> None:
        loader = BacktestDataLoader()
        df = loader.generate_synthetic(
            n_bars=100,
            start_price=50000.0,
            volatility=0.02,
        )
        assert len(df) == 100
        assert "close" in df.columns
        assert "open" in df.columns
        assert df["high"].ge(df["low"]).all()

    def test_train_test_split(self) -> None:
        loader = BacktestDataLoader()
        df = loader.generate_synthetic(n_bars=200)
        train, test = loader.split_data(df, train_pct=0.8)
        assert len(train) == 160
        assert len(test) == 40

    def test_backtest_preserves_equity(self) -> None:
        loader = BacktestDataLoader()
        df = loader.generate_synthetic(n_bars=50, start_price=50000.0)
        strategy = TrendStrategy()
        config = BacktestConfig(
            initial_equity=Decimal("100000"),
            taker_fee=Decimal("0"),
            slippage_pct=Decimal("0"),
        )
        backtester = Backtester(config)
        result = backtester.run(strategy, "BTCUSDT", df)

        assert result.final_equity > Decimal("0")
        assert len(result.equity_curve) > 0
