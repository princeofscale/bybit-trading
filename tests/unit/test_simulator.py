from decimal import Decimal

import pytest

from backtesting.models import BacktestConfig, TradeSide
from backtesting.simulator import FillSimulator


@pytest.fixture
def config() -> BacktestConfig:
    return BacktestConfig(
        maker_fee=Decimal("0.0001"),
        taker_fee=Decimal("0.0006"),
        slippage_pct=Decimal("0.001"),
        use_limit_orders=False,
    )


@pytest.fixture
def sim(config: BacktestConfig) -> FillSimulator:
    return FillSimulator(config)


class TestSlippage:
    def test_long_entry_slips_up(self, sim: FillSimulator) -> None:
        price = Decimal("100")
        result = sim.apply_slippage(price, TradeSide.LONG, is_entry=True)
        assert result == Decimal("100.1")
        assert result > price

    def test_long_exit_slips_down(self, sim: FillSimulator) -> None:
        price = Decimal("100")
        result = sim.apply_slippage(price, TradeSide.LONG, is_entry=False)
        assert result == Decimal("99.9")
        assert result < price

    def test_short_entry_slips_down(self, sim: FillSimulator) -> None:
        price = Decimal("100")
        result = sim.apply_slippage(price, TradeSide.SHORT, is_entry=True)
        assert result == Decimal("99.9")
        assert result < price

    def test_short_exit_slips_up(self, sim: FillSimulator) -> None:
        price = Decimal("100")
        result = sim.apply_slippage(price, TradeSide.SHORT, is_entry=False)
        assert result == Decimal("100.1")
        assert result > price

    def test_zero_slippage(self) -> None:
        cfg = BacktestConfig(slippage_pct=Decimal("0"))
        s = FillSimulator(cfg)
        assert s.apply_slippage(Decimal("100"), TradeSide.LONG, True) == Decimal("100")


class TestCommission:
    def test_taker_fee_default(self, sim: FillSimulator) -> None:
        comm = sim.calculate_commission(Decimal("10000"))
        assert comm == Decimal("6")

    def test_maker_fee_when_limit(self) -> None:
        cfg = BacktestConfig(
            maker_fee=Decimal("0.0001"),
            use_limit_orders=True,
        )
        s = FillSimulator(cfg)
        comm = s.calculate_commission(Decimal("10000"))
        assert comm == Decimal("1")


class TestSimulateEntry:
    def test_long_entry(self, sim: FillSimulator) -> None:
        fill, comm, slip = sim.simulate_entry(
            Decimal("100"), Decimal("10"), TradeSide.LONG,
        )
        assert fill == Decimal("100.1")
        assert comm == Decimal("100.1") * 10 * Decimal("0.0006")
        assert slip == Decimal("0.1") * 10

    def test_short_entry(self, sim: FillSimulator) -> None:
        fill, comm, slip = sim.simulate_entry(
            Decimal("100"), Decimal("10"), TradeSide.SHORT,
        )
        assert fill == Decimal("99.9")
        assert slip == Decimal("0.1") * 10


class TestSimulateExit:
    def test_long_exit(self, sim: FillSimulator) -> None:
        fill, comm, slip = sim.simulate_exit(
            Decimal("110"), Decimal("10"), TradeSide.LONG,
        )
        assert fill == Decimal("109.89")
        assert fill < Decimal("110")


class TestPnl:
    def test_long_profit(self, sim: FillSimulator) -> None:
        pnl = sim.calculate_pnl(
            Decimal("100"), Decimal("110"), Decimal("10"),
            TradeSide.LONG, Decimal("0.6"), Decimal("0.66"),
        )
        gross = (Decimal("110") - Decimal("100")) * Decimal("10")
        assert pnl == gross - Decimal("0.6") - Decimal("0.66")

    def test_long_loss(self, sim: FillSimulator) -> None:
        pnl = sim.calculate_pnl(
            Decimal("100"), Decimal("95"), Decimal("10"),
            TradeSide.LONG, Decimal("0.6"), Decimal("0.57"),
        )
        assert pnl < Decimal("0")

    def test_short_profit(self, sim: FillSimulator) -> None:
        pnl = sim.calculate_pnl(
            Decimal("100"), Decimal("90"), Decimal("10"),
            TradeSide.SHORT, Decimal("0.6"), Decimal("0.54"),
        )
        gross = (Decimal("100") - Decimal("90")) * Decimal("10")
        assert pnl == gross - Decimal("0.6") - Decimal("0.54")

    def test_short_loss(self, sim: FillSimulator) -> None:
        pnl = sim.calculate_pnl(
            Decimal("100"), Decimal("105"), Decimal("10"),
            TradeSide.SHORT, Decimal("0.6"), Decimal("0.63"),
        )
        assert pnl < Decimal("0")


class TestStopAndTP:
    def test_long_stop_hit(self, sim: FillSimulator) -> None:
        assert sim.check_stop_loss(
            Decimal("94"), Decimal("101"), Decimal("95"), TradeSide.LONG,
        ) is True

    def test_long_stop_not_hit(self, sim: FillSimulator) -> None:
        assert sim.check_stop_loss(
            Decimal("96"), Decimal("101"), Decimal("95"), TradeSide.LONG,
        ) is False

    def test_short_stop_hit(self, sim: FillSimulator) -> None:
        assert sim.check_stop_loss(
            Decimal("99"), Decimal("106"), Decimal("105"), TradeSide.SHORT,
        ) is True

    def test_short_stop_not_hit(self, sim: FillSimulator) -> None:
        assert sim.check_stop_loss(
            Decimal("99"), Decimal("104"), Decimal("105"), TradeSide.SHORT,
        ) is False

    def test_long_tp_hit(self, sim: FillSimulator) -> None:
        assert sim.check_take_profit(
            Decimal("99"), Decimal("111"), Decimal("110"), TradeSide.LONG,
        ) is True

    def test_short_tp_hit(self, sim: FillSimulator) -> None:
        assert sim.check_take_profit(
            Decimal("89"), Decimal("99"), Decimal("90"), TradeSide.SHORT,
        ) is True

    def test_tp_zero_never_hits(self, sim: FillSimulator) -> None:
        assert sim.check_take_profit(
            Decimal("0"), Decimal("200"), Decimal("0"), TradeSide.LONG,
        ) is False
