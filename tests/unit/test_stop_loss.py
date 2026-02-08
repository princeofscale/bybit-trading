from decimal import Decimal

import pytest

from risk.stop_loss import StopLossManager, StopLossTracker, StopLossType


class TestStopLossTracker:
    def test_fixed_stop_long_not_triggered(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            is_long=True,
        )
        assert not tracker.is_triggered(Decimal("100"))
        assert not tracker.is_triggered(Decimal("96"))

    def test_fixed_stop_long_triggered(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            is_long=True,
        )
        assert tracker.is_triggered(Decimal("95"))
        assert tracker.is_triggered(Decimal("90"))

    def test_fixed_stop_short_not_triggered(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("105"),
            is_long=False,
        )
        assert not tracker.is_triggered(Decimal("100"))
        assert not tracker.is_triggered(Decimal("104"))

    def test_fixed_stop_short_triggered(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("105"),
            is_long=False,
        )
        assert tracker.is_triggered(Decimal("105"))
        assert tracker.is_triggered(Decimal("110"))

    def test_trailing_stop_long_moves_up(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            is_long=True,
            sl_type=StopLossType.TRAILING,
            trailing_distance=Decimal("5"),
        )
        assert tracker.stop_price == Decimal("95")
        tracker.update(Decimal("110"))
        assert tracker.stop_price == Decimal("105")
        tracker.update(Decimal("115"))
        assert tracker.stop_price == Decimal("110")

    def test_trailing_stop_long_never_moves_down(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            is_long=True,
            sl_type=StopLossType.TRAILING,
            trailing_distance=Decimal("5"),
        )
        tracker.update(Decimal("110"))
        assert tracker.stop_price == Decimal("105")
        tracker.update(Decimal("106"))
        assert tracker.stop_price == Decimal("105")

    def test_trailing_stop_short_moves_down(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("105"),
            is_long=False,
            sl_type=StopLossType.TRAILING,
            trailing_distance=Decimal("5"),
        )
        tracker.update(Decimal("90"))
        assert tracker.stop_price == Decimal("95")

    def test_trailing_stop_short_never_moves_up(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("105"),
            is_long=False,
            sl_type=StopLossType.TRAILING,
            trailing_distance=Decimal("5"),
        )
        tracker.update(Decimal("90"))
        assert tracker.stop_price == Decimal("95")
        tracker.update(Decimal("94"))
        assert tracker.stop_price == Decimal("95")

    def test_bars_held_increments(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            is_long=True,
        )
        assert tracker.bars_held == 0
        tracker.update(Decimal("101"))
        assert tracker.bars_held == 1
        tracker.update(Decimal("102"))
        assert tracker.bars_held == 2

    def test_risk_reward_ratio(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            is_long=True,
        )
        rr = tracker.risk_reward_ratio(Decimal("110"))
        assert rr == Decimal("2")

    def test_risk_reward_zero_risk(self) -> None:
        tracker = StopLossTracker(
            entry_price=Decimal("100"),
            stop_price=Decimal("100"),
            is_long=True,
        )
        rr = tracker.risk_reward_ratio(Decimal("110"))
        assert rr == Decimal("0")


class TestStopLossManager:
    def test_add_and_get_stop(self) -> None:
        mgr = StopLossManager()
        tracker = mgr.add_stop(
            "order1", Decimal("100"), Decimal("95"), True,
        )
        assert mgr.get_stop("order1") is tracker
        assert mgr.active_count == 1

    def test_remove_stop(self) -> None:
        mgr = StopLossManager()
        mgr.add_stop("order1", Decimal("100"), Decimal("95"), True)
        mgr.remove_stop("order1")
        assert mgr.get_stop("order1") is None
        assert mgr.active_count == 0

    def test_remove_nonexistent_no_error(self) -> None:
        mgr = StopLossManager()
        mgr.remove_stop("nonexistent")

    def test_update_all_finds_triggered(self) -> None:
        mgr = StopLossManager()
        mgr.add_stop("order1", Decimal("100"), Decimal("95"), True)
        mgr.add_stop("order2", Decimal("100"), Decimal("105"), False)
        triggered = mgr.update_all({
            "order1": Decimal("90"),
            "order2": Decimal("110"),
        })
        assert "order1" in triggered
        assert "order2" in triggered

    def test_update_all_skips_not_triggered(self) -> None:
        mgr = StopLossManager()
        mgr.add_stop("order1", Decimal("100"), Decimal("95"), True)
        triggered = mgr.update_all({"order1": Decimal("99")})
        assert triggered == []

    def test_update_all_skips_missing_prices(self) -> None:
        mgr = StopLossManager()
        mgr.add_stop("order1", Decimal("100"), Decimal("95"), True)
        triggered = mgr.update_all({"other": Decimal("90")})
        assert triggered == []

    def test_remove_triggered(self) -> None:
        mgr = StopLossManager()
        mgr.add_stop("order1", Decimal("100"), Decimal("95"), True)
        mgr.add_stop("order2", Decimal("100"), Decimal("95"), True)
        mgr.remove_triggered(["order1"])
        assert mgr.get_stop("order1") is None
        assert mgr.get_stop("order2") is not None
        assert mgr.active_count == 1

    def test_create_atr_stop_long(self) -> None:
        mgr = StopLossManager()
        tracker = mgr.create_atr_stop(
            "order1", Decimal("100"), Decimal("5"), Decimal("2"), True,
        )
        assert tracker.stop_price == Decimal("90")
        assert tracker.is_long is True

    def test_create_atr_stop_short(self) -> None:
        mgr = StopLossManager()
        tracker = mgr.create_atr_stop(
            "order1", Decimal("100"), Decimal("5"), Decimal("2"), False,
        )
        assert tracker.stop_price == Decimal("110")
        assert tracker.is_long is False

    def test_create_trailing_stop_long(self) -> None:
        mgr = StopLossManager()
        tracker = mgr.create_trailing_stop(
            "order1", Decimal("100"), Decimal("5"), True,
        )
        assert tracker.stop_price == Decimal("95")
        tracker.update(Decimal("110"))
        assert tracker.stop_price == Decimal("105")

    def test_create_trailing_stop_short(self) -> None:
        mgr = StopLossManager()
        tracker = mgr.create_trailing_stop(
            "order1", Decimal("100"), Decimal("5"), False,
        )
        assert tracker.stop_price == Decimal("105")
        tracker.update(Decimal("90"))
        assert tracker.stop_price == Decimal("95")
