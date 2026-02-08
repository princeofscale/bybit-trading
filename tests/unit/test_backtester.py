from decimal import Decimal

import pandas as pd
import pytest

from backtesting.backtester import Backtester
from backtesting.models import BacktestConfig
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class AlwaysLongStrategy(BaseStrategy):
    def __init__(self) -> None:
        super().__init__("always_long", ["TEST"])
        self._entered = False

    def min_candles_required(self) -> int:
        return 2

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        close = Decimal(str(df.iloc[-1]["close"]))
        if self.get_state(symbol) == StrategyState.IDLE and not self._entered:
            self._entered = True
            return Signal(
                symbol=symbol,
                direction=SignalDirection.LONG,
                confidence=0.9,
                strategy_name=self.name,
                entry_price=close,
                stop_loss=close * Decimal("0.95"),
                take_profit=close * Decimal("1.10"),
            )
        return None


class AlwaysShortStrategy(BaseStrategy):
    def __init__(self) -> None:
        super().__init__("always_short", ["TEST"])
        self._entered = False

    def min_candles_required(self) -> int:
        return 2

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        close = Decimal(str(df.iloc[-1]["close"]))
        if self.get_state(symbol) == StrategyState.IDLE and not self._entered:
            self._entered = True
            return Signal(
                symbol=symbol,
                direction=SignalDirection.SHORT,
                confidence=0.9,
                strategy_name=self.name,
                entry_price=close,
                stop_loss=close * Decimal("1.05"),
                take_profit=close * Decimal("0.90"),
            )
        return None


def _make_uptrend_df(n: int = 20, start: float = 100.0) -> pd.DataFrame:
    rows = []
    for i in range(n):
        p = start + i * 2
        rows.append({
            "open_time": 1_700_000_000_000 + i * 900_000,
            "open": p - 0.5,
            "high": p + 3,
            "low": p - 1,
            "close": p,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


def _make_downtrend_df(n: int = 20, start: float = 200.0) -> pd.DataFrame:
    rows = []
    for i in range(n):
        p = start - i * 2
        rows.append({
            "open_time": 1_700_000_000_000 + i * 900_000,
            "open": p + 0.5,
            "high": p + 1,
            "low": p - 3,
            "close": p,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


def _make_flat_df(n: int = 20, price: float = 100.0) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "open_time": 1_700_000_000_000 + i * 900_000,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def config() -> BacktestConfig:
    return BacktestConfig(
        initial_equity=Decimal("10000"),
        slippage_pct=Decimal("0"),
        taker_fee=Decimal("0"),
        maker_fee=Decimal("0"),
        risk_per_trade=Decimal("0.02"),
        max_leverage=Decimal("3.0"),
    )


class TestBacktesterLong:
    def test_produces_trades(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        result = bt.run(AlwaysLongStrategy(), "TEST", _make_uptrend_df())
        assert len(result.trades) >= 1

    def test_long_uptrend_profitable(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        result = bt.run(AlwaysLongStrategy(), "TEST", _make_uptrend_df())
        total_pnl = sum(t.pnl for t in result.trades)
        assert total_pnl > Decimal("0")
        assert result.final_equity > config.initial_equity

    def test_trade_has_correct_side(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        result = bt.run(AlwaysLongStrategy(), "TEST", _make_uptrend_df())
        for trade in result.trades:
            assert trade.side == "long"

    def test_trade_quantity_positive(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        result = bt.run(AlwaysLongStrategy(), "TEST", _make_uptrend_df())
        for trade in result.trades:
            assert trade.quantity > Decimal("0")

    def test_equity_curve_populated(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        result = bt.run(AlwaysLongStrategy(), "TEST", _make_uptrend_df())
        assert len(result.equity_curve) > 0


class TestBacktesterShort:
    def test_short_downtrend_profitable(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        result = bt.run(AlwaysShortStrategy(), "TEST", _make_downtrend_df())
        total_pnl = sum(t.pnl for t in result.trades)
        assert total_pnl > Decimal("0")

    def test_short_trade_side(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        result = bt.run(AlwaysShortStrategy(), "TEST", _make_downtrend_df())
        for trade in result.trades:
            assert trade.side == "short"


class TestStopLossExecution:
    def test_stop_loss_closes_at_stop(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        df = _make_downtrend_df(n=30, start=100.0)
        result = bt.run(AlwaysLongStrategy(), "TEST", df)
        assert len(result.trades) >= 1
        trade = result.trades[0]
        assert trade.pnl < Decimal("0")

    def test_stop_loss_limits_loss(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        df = _make_downtrend_df(n=30, start=100.0)
        result = bt.run(AlwaysLongStrategy(), "TEST", df)
        for trade in result.trades:
            max_expected_loss = config.initial_equity * config.risk_per_trade * Decimal("1.5")
            assert abs(trade.pnl) < max_expected_loss


class TestCommissionsAndSlippage:
    def test_commissions_reduce_pnl(self) -> None:
        no_fee = BacktestConfig(
            initial_equity=Decimal("10000"),
            slippage_pct=Decimal("0"),
            taker_fee=Decimal("0"),
        )
        with_fee = BacktestConfig(
            initial_equity=Decimal("10000"),
            slippage_pct=Decimal("0"),
            taker_fee=Decimal("0.001"),
        )
        df = _make_uptrend_df()
        r1 = Backtester(no_fee).run(AlwaysLongStrategy(), "TEST", df)
        r2 = Backtester(with_fee).run(AlwaysLongStrategy(), "TEST", df)
        assert r1.final_equity > r2.final_equity

    def test_slippage_reduces_pnl(self) -> None:
        no_slip = BacktestConfig(
            initial_equity=Decimal("10000"),
            slippage_pct=Decimal("0"),
            taker_fee=Decimal("0"),
        )
        with_slip = BacktestConfig(
            initial_equity=Decimal("10000"),
            slippage_pct=Decimal("0.005"),
            taker_fee=Decimal("0"),
        )
        df = _make_uptrend_df()
        r1 = Backtester(no_slip).run(AlwaysLongStrategy(), "TEST", df)
        r2 = Backtester(with_slip).run(AlwaysLongStrategy(), "TEST", df)
        assert r1.final_equity > r2.final_equity


class TestEdgeCases:
    def test_no_trades_flat_market(self, config: BacktestConfig) -> None:
        bt = Backtester(config)

        class NeverTradeStrategy(BaseStrategy):
            def __init__(self) -> None:
                super().__init__("never", ["TEST"])

            def min_candles_required(self) -> int:
                return 2

            def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
                return None

        result = bt.run(NeverTradeStrategy(), "TEST", _make_flat_df())
        assert len(result.trades) == 0
        assert result.final_equity == config.initial_equity

    def test_metadata_correct(self, config: BacktestConfig) -> None:
        bt = Backtester(config)
        result = bt.run(AlwaysLongStrategy(), "TEST", _make_uptrend_df())
        assert result.strategy_name == "always_long"
        assert result.symbol == "TEST"
        assert result.start_time > 0
        assert result.end_time > result.start_time
