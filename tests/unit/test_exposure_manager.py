from decimal import Decimal

import pytest

from config.settings import RiskSettings
from exchange.models import Position
from data.models import PositionSide
from risk.exposure_manager import CORRELATION_GROUPS, MAX_SAME_DIRECTION_PER_GROUP, ExposureManager


def _make_position(
    symbol: str = "BTCUSDT",
    size: Decimal = Decimal("0.1"),
    entry: Decimal = Decimal("50000"),
    leverage: Decimal = Decimal("1"),
) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        size=size,
        entry_price=entry,
        leverage=leverage,
    )


@pytest.fixture
def settings() -> RiskSettings:
    return RiskSettings(
        max_concurrent_positions=3,
        max_leverage=Decimal("3.0"),
        max_risk_per_trade=Decimal("0.02"),
        max_portfolio_risk=Decimal("0.10"),
        funding_arb_max_allocation=Decimal("0.30"),
    )


@pytest.fixture
def mgr(settings: RiskSettings) -> ExposureManager:
    return ExposureManager(settings)


class TestMaxPositions:
    def test_allows_under_limit(self, mgr: ExposureManager) -> None:
        positions = [_make_position(f"SYM{i}") for i in range(2)]
        check = mgr.check_new_position(
            positions, "NEWCOIN", Decimal("100"), Decimal("1"), Decimal("100000"),
        )
        assert check.allowed is True

    def test_blocks_at_limit(self, mgr: ExposureManager) -> None:
        positions = [_make_position(f"SYM{i}") for i in range(3)]
        check = mgr.check_new_position(
            positions, "NEWCOIN", Decimal("100"), Decimal("1"), Decimal("100000"),
        )
        assert check.allowed is False
        assert "max_positions" in check.reason

    def test_funding_arb_bypasses_position_limit(self, mgr: ExposureManager) -> None:
        positions = [_make_position(f"SYM{i}") for i in range(3)]
        check = mgr.check_new_position(
            positions, "NEWCOIN", Decimal("100"), Decimal("1"),
            Decimal("100000"), is_funding_arb=True,
        )
        assert "max_positions" not in (check.reason or "")


class TestLeverageCheck:
    def test_allows_within_leverage(self, mgr: ExposureManager) -> None:
        check = mgr.check_new_position(
            [], "BTC", Decimal("100"), Decimal("3"), Decimal("100000"),
        )
        assert check.allowed is True

    def test_blocks_excessive_leverage(self, mgr: ExposureManager) -> None:
        check = mgr.check_new_position(
            [], "BTC", Decimal("100"), Decimal("5"), Decimal("100000"),
        )
        assert check.allowed is False
        assert "max_leverage" in check.reason


class TestTotalExposure:
    def test_allows_within_total_exposure(self, mgr: ExposureManager) -> None:
        equity = Decimal("100000")
        positions = [_make_position("BTC", Decimal("1"), Decimal("50000"))]
        check = mgr.check_new_position(
            positions, "ETH", Decimal("1000"), Decimal("1"), equity,
        )
        assert check.allowed is True

    def test_blocks_over_total_exposure(self, mgr: ExposureManager) -> None:
        equity = Decimal("100000")
        max_total = equity * Decimal("3")
        positions = [_make_position("BTC", Decimal("5"), Decimal("50000"))]
        check = mgr.check_new_position(
            positions, "ETH", Decimal("100000"), Decimal("1"), equity,
        )
        assert check.allowed is False
        assert "total_exposure" in check.reason


class TestFundingArbAllocation:
    def test_blocks_over_arb_allocation(self, mgr: ExposureManager) -> None:
        equity = Decimal("100000")
        max_arb = equity * Decimal("0.30")
        check = mgr.check_new_position(
            [], "BTC", max_arb + 1, Decimal("1"), equity, is_funding_arb=True,
        )
        assert check.allowed is False
        assert "funding_arb_allocation" in check.reason

    def test_allows_within_arb_allocation(self, mgr: ExposureManager) -> None:
        equity = Decimal("100000")
        check = mgr.check_new_position(
            [], "BTC", Decimal("1500"), Decimal("1"), equity, is_funding_arb=True,
        )
        assert check.allowed is True


class TestPerTradeRisk:
    def test_blocks_excessive_per_trade_risk(self, mgr: ExposureManager) -> None:
        equity = Decimal("10000")
        check = mgr.check_new_position(
            [], "BTC", Decimal("1000"), Decimal("1"), equity,
        )
        assert check.allowed is False
        assert "per_trade_risk" in check.reason

    def test_allows_reasonable_per_trade_risk(self, mgr: ExposureManager) -> None:
        equity = Decimal("100000")
        check = mgr.check_new_position(
            [], "BTC", Decimal("1000"), Decimal("1"), equity,
        )
        assert check.allowed is True


class TestPortfolioAnalytics:
    def test_total_exposure_usd(self, mgr: ExposureManager) -> None:
        positions = [
            _make_position("BTC", Decimal("0.1"), Decimal("50000")),
            _make_position("ETH", Decimal("2"), Decimal("3000")),
        ]
        total = mgr.total_exposure_usd(positions)
        assert total == Decimal("11000")

    def test_total_exposure_empty(self, mgr: ExposureManager) -> None:
        assert mgr.total_exposure_usd([]) == 0

    def test_portfolio_risk_pct(self, mgr: ExposureManager) -> None:
        positions = [_make_position("BTC", Decimal("0.1"), Decimal("50000"))]
        risk = mgr.total_portfolio_risk_pct(positions, Decimal("50000"))
        assert risk == Decimal("0.1")

    def test_portfolio_risk_zero_equity(self, mgr: ExposureManager) -> None:
        positions = [_make_position()]
        assert mgr.total_portfolio_risk_pct(positions, Decimal("0")) == Decimal("0")

    def test_is_portfolio_risk_acceptable(self, mgr: ExposureManager) -> None:
        positions = [_make_position("BTC", Decimal("0.01"), Decimal("50000"))]
        assert mgr.is_portfolio_risk_acceptable(positions, Decimal("50000")) is True

    def test_portfolio_risk_not_acceptable(self, mgr: ExposureManager) -> None:
        positions = [_make_position("BTC", Decimal("1"), Decimal("50000"))]
        assert mgr.is_portfolio_risk_acceptable(positions, Decimal("50000")) is False


def _make_directional_position(
    symbol: str,
    side: PositionSide,
    size: Decimal = Decimal("0.1"),
    entry: Decimal = Decimal("100"),
) -> Position:
    return Position(
        symbol=symbol,
        side=side,
        size=size,
        entry_price=entry,
    )


class TestCorrelationGroups:
    def test_all_15_pairs_covered(self) -> None:
        all_symbols = set()
        for symbols in CORRELATION_GROUPS.values():
            all_symbols.update(symbols)
        from config.trading_pairs import get_ccxt_symbols
        configured = set(get_ccxt_symbols())
        assert configured.issubset(all_symbols)

    def test_allows_first_position_in_group(self, mgr: ExposureManager) -> None:
        check = mgr.check_correlation_group(
            [], "SOL/USDT:USDT", PositionSide.LONG,
        )
        assert check.allowed is True

    def test_allows_second_same_direction_in_group(self, mgr: ExposureManager) -> None:
        positions = [
            _make_directional_position("SOL/USDT:USDT", PositionSide.LONG),
        ]
        check = mgr.check_correlation_group(
            positions, "AVAX/USDT:USDT", PositionSide.LONG,
        )
        assert check.allowed is True

    def test_blocks_third_same_direction_in_group(self, mgr: ExposureManager) -> None:
        positions = [
            _make_directional_position("SOL/USDT:USDT", PositionSide.LONG),
            _make_directional_position("AVAX/USDT:USDT", PositionSide.LONG),
        ]
        check = mgr.check_correlation_group(
            positions, "SUI/USDT:USDT", PositionSide.LONG,
        )
        assert check.allowed is False
        assert "correlation_group_alt_l1" in check.reason

    def test_allows_opposite_direction_in_group(self, mgr: ExposureManager) -> None:
        positions = [
            _make_directional_position("SOL/USDT:USDT", PositionSide.LONG),
            _make_directional_position("AVAX/USDT:USDT", PositionSide.LONG),
        ]
        check = mgr.check_correlation_group(
            positions, "SUI/USDT:USDT", PositionSide.SHORT,
        )
        assert check.allowed is True

    def test_allows_different_group(self, mgr: ExposureManager) -> None:
        positions = [
            _make_directional_position("SOL/USDT:USDT", PositionSide.LONG),
            _make_directional_position("AVAX/USDT:USDT", PositionSide.LONG),
        ]
        check = mgr.check_correlation_group(
            positions, "BTC/USDT:USDT", PositionSide.LONG,
        )
        assert check.allowed is True

    def test_unknown_symbol_always_allowed(self, mgr: ExposureManager) -> None:
        check = mgr.check_correlation_group(
            [], "UNKNOWN/USDT:USDT", PositionSide.LONG,
        )
        assert check.allowed is True

    def test_ignores_zero_size_positions(self, mgr: ExposureManager) -> None:
        positions = [
            _make_directional_position("SOL/USDT:USDT", PositionSide.LONG, size=Decimal("0")),
            _make_directional_position("AVAX/USDT:USDT", PositionSide.LONG, size=Decimal("0")),
        ]
        check = mgr.check_correlation_group(
            positions, "SUI/USDT:USDT", PositionSide.LONG,
        )
        assert check.allowed is True
