from decimal import Decimal

import pytest

from backtesting.models import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    EquityCurvePoint,
    TradeSide,
)
from backtesting.report_generator import ReportGenerator


def _winning_trade(pnl: str = "100") -> BacktestTrade:
    return BacktestTrade(
        pnl=Decimal(pnl), pnl_pct=Decimal("0.01"),
        commission=Decimal("1"), slippage=Decimal("0.5"),
        bars_held=5, side=TradeSide.LONG,
    )


def _losing_trade(pnl: str = "-50") -> BacktestTrade:
    return BacktestTrade(
        pnl=Decimal(pnl), pnl_pct=Decimal("-0.005"),
        commission=Decimal("1"), slippage=Decimal("0.5"),
        bars_held=3, side=TradeSide.LONG,
    )


def _equity_curve(start: float, end: float, n: int = 10) -> list[EquityCurvePoint]:
    step = (end - start) / max(n - 1, 1)
    points = []
    for i in range(n):
        eq = Decimal(str(start + step * i))
        points.append(EquityCurvePoint(
            timestamp=1000 + i, equity=eq,
        ))
    return points


def _make_result(
    trades: list[BacktestTrade] | None = None,
    curve: list[EquityCurvePoint] | None = None,
    initial: str = "10000",
    final: str = "11000",
) -> BacktestResult:
    return BacktestResult(
        config=BacktestConfig(initial_equity=Decimal(initial)),
        trades=trades or [],
        equity_curve=curve or [],
        final_equity=Decimal(final),
    )


@pytest.fixture
def gen() -> ReportGenerator:
    return ReportGenerator(annualization_factor=100)


class TestWinRate:
    def test_all_winners(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_winning_trade() for _ in range(5)],
            curve=_equity_curve(10000, 10500),
            final="10500",
        )
        m = gen.calculate_metrics(result)
        assert m.win_rate == Decimal("1")
        assert m.winning_trades == 5
        assert m.losing_trades == 0

    def test_all_losers(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_losing_trade() for _ in range(4)],
            curve=_equity_curve(10000, 9800),
            final="9800",
        )
        m = gen.calculate_metrics(result)
        assert m.win_rate == Decimal("0")
        assert m.losing_trades == 4

    def test_mixed(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_winning_trade(), _winning_trade(), _losing_trade()],
            curve=_equity_curve(10000, 10150),
            final="10150",
        )
        m = gen.calculate_metrics(result)
        expected_wr = Decimal("2") / Decimal("3")
        assert m.win_rate == expected_wr
        assert m.total_trades == 3


class TestProfitFactor:
    def test_profit_factor(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_winning_trade("200"), _losing_trade("-100")],
            curve=_equity_curve(10000, 10100),
            final="10100",
        )
        m = gen.calculate_metrics(result)
        assert m.profit_factor == Decimal("2")

    def test_no_losses_profit_factor_zero(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_winning_trade()],
            curve=_equity_curve(10000, 10100),
            final="10100",
        )
        m = gen.calculate_metrics(result)
        assert m.profit_factor == Decimal("0")


class TestAvgWinLoss:
    def test_avg_win(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_winning_trade("100"), _winning_trade("200"), _losing_trade("-50")],
            curve=_equity_curve(10000, 10250),
            final="10250",
        )
        m = gen.calculate_metrics(result)
        assert m.avg_win == Decimal("150")
        assert m.avg_loss == Decimal("50")
        assert m.avg_win_loss_ratio == Decimal("3")


class TestMaxDrawdown:
    def test_drawdown_from_curve(self, gen: ReportGenerator) -> None:
        curve = [
            EquityCurvePoint(timestamp=1, equity=Decimal("10000")),
            EquityCurvePoint(timestamp=2, equity=Decimal("11000")),
            EquityCurvePoint(timestamp=3, equity=Decimal("9900")),
            EquityCurvePoint(timestamp=4, equity=Decimal("10500")),
        ]
        result = _make_result(
            trades=[_winning_trade(), _losing_trade()],
            curve=curve,
            final="10500",
        )
        m = gen.calculate_metrics(result)
        assert m.max_drawdown_pct == Decimal("0.1")

    def test_no_drawdown(self, gen: ReportGenerator) -> None:
        curve = _equity_curve(10000, 11000, 5)
        result = _make_result(
            trades=[_winning_trade()],
            curve=curve,
            final="11000",
        )
        m = gen.calculate_metrics(result)
        assert m.max_drawdown_pct == Decimal("0")


class TestTotalReturn:
    def test_positive_return(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_winning_trade()],
            curve=_equity_curve(10000, 11000),
            final="11000",
        )
        m = gen.calculate_metrics(result)
        assert m.total_return_pct == Decimal("0.1")

    def test_negative_return(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_losing_trade()],
            curve=_equity_curve(10000, 9000),
            final="9000",
        )
        m = gen.calculate_metrics(result)
        assert m.total_return_pct == Decimal("-0.1")


class TestExpectancy:
    def test_positive_expectancy(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_winning_trade("100"), _winning_trade("100"), _losing_trade("-50")],
            curve=_equity_curve(10000, 10150),
            final="10150",
        )
        m = gen.calculate_metrics(result)
        assert m.expectancy == Decimal("50")

    def test_negative_expectancy(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[_winning_trade("20"), _losing_trade("-50"), _losing_trade("-50")],
            curve=_equity_curve(10000, 9920),
            final="9920",
        )
        m = gen.calculate_metrics(result)
        expected = (Decimal("20") + Decimal("-50") + Decimal("-50")) / Decimal("3")
        assert m.expectancy == expected


class TestCommissionAndSlippage:
    def test_totals(self, gen: ReportGenerator) -> None:
        t1 = BacktestTrade(
            pnl=Decimal("100"), commission=Decimal("2"),
            slippage=Decimal("1"), bars_held=3,
        )
        t2 = BacktestTrade(
            pnl=Decimal("-50"), commission=Decimal("3"),
            slippage=Decimal("1.5"), bars_held=2,
        )
        result = _make_result(
            trades=[t1, t2],
            curve=_equity_curve(10000, 10050),
            final="10050",
        )
        m = gen.calculate_metrics(result)
        assert m.total_commission == Decimal("5")
        assert m.total_slippage == Decimal("2.5")
        assert m.avg_bars_held == Decimal("2.5")


class TestEmptyResults:
    def test_no_trades(self, gen: ReportGenerator) -> None:
        result = _make_result(trades=[], final="10000")
        m = gen.calculate_metrics(result)
        assert m.total_trades == 0
        assert m.win_rate == Decimal("0")
        assert m.sharpe_ratio == Decimal("0")


class TestKellyPct:
    def test_positive_edge_kelly(self, gen: ReportGenerator) -> None:
        result = _make_result(
            trades=[
                _winning_trade("200"), _winning_trade("200"),
                _losing_trade("-100"),
            ],
            curve=_equity_curve(10000, 10300),
            final="10300",
        )
        m = gen.calculate_metrics(result)
        wr = Decimal("2") / Decimal("3")
        wl = Decimal("200") / Decimal("100")
        expected = wr - (1 - wr) / wl
        assert m.kelly_pct == expected
