from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import AppSettings
from config.strategy_profiles import MODERATE_PROFILE
from core.orchestrator import TradingOrchestrator
from data.models import PositionSide
from exchange.models import Position
from data.models import OrderSide
from risk.risk_manager import RiskDecision
from strategies.base_strategy import Signal, SignalDirection, StrategyState


@pytest.fixture
def settings() -> AppSettings:
    return AppSettings(_env_file=None)


async def test_session_id_generated(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    assert orch._session_id
    assert len(orch._session_id) > 0


async def test_request_shutdown_sets_event(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    assert not orch._shutdown_event.is_set()
    orch.request_shutdown()
    assert orch._shutdown_event.is_set()


async def test_initial_state_not_paused(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    assert orch._trading_paused is False
    assert orch._signals_count == 0
    assert orch._trades_count == 0


async def test_cmd_pause_sets_flag(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    result = await orch._cmd_pause()
    assert orch._trading_paused is True
    assert "ПРИОСТАНОВЛЕНА" in result


async def test_cmd_resume_clears_flag(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._trading_paused = True

    result = await orch._cmd_resume()
    assert orch._trading_paused is False
    assert "ВОЗОБНОВЛЕНА" in result


async def test_cmd_help_returns_commands(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    result = await orch._cmd_help()
    assert "/status" in result
    assert "/positions" in result
    assert "/pnl" in result
    assert "/guard" in result
    assert "Команды бота" in result


async def test_cmd_status_with_no_managers(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    result = await orch._cmd_status()
    assert "Статус бота" in result
    assert "RUNNING" in result


async def test_cmd_pnl_with_no_managers(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    result = await orch._cmd_pnl()
    assert "Сводка PnL" in result
    assert "0.00 USDT" in result
    assert "Открытые позиции" in result or "Нет открытых позиций" in result


async def test_cmd_guard_without_risk_manager(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    result = await orch._cmd_guard()
    assert "недоступен" in result


async def test_cmd_close_ready_without_symbol(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    result = await orch._cmd_close_ready([])
    assert "Использование" in result


async def test_cmd_close_ready_symbol_not_found(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._symbols = ["BTC/USDT:USDT"]
    result = await orch._cmd_close_ready(["SOL/USDT:USDT"])
    assert "не найден" in result


async def test_poll_and_analyze_skips_when_paused(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._trading_paused = True
    orch._rest_api = AsyncMock()
    orch._candle_buffer = MagicMock()

    await orch._poll_and_analyze("BTC/USDT:USDT")

    orch._rest_api.fetch_ohlcv.assert_not_called()


async def test_poll_and_analyze_skips_without_rest_api(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    await orch._poll_and_analyze("BTC/USDT:USDT")
    assert orch._signals_count == 0


async def test_account_closed_trade_updates_risk_and_strategy(
    settings: AppSettings,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._risk_manager = MagicMock()
    orch._strategy_selector = MagicMock()
    orch._journal = AsyncMock()
    orch._telegram_sink = AsyncMock()

    signal = Signal(
        symbol="BTC/USDT:USDT",
        direction=SignalDirection.CLOSE_LONG,
        confidence=0.9,
        strategy_name="ema_crossover",
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("51000"),
    )

    await orch._account_closed_trade(
        signal=signal,
        close_qty=Decimal("0.1"),
        position_size=Decimal("0.2"),
        entry_price=Decimal("49000"),
        mark_price=Decimal("50000"),
        unrealized_pnl=Decimal("100"),
    )

    orch._risk_manager.record_trade_result.assert_called_once()
    orch._strategy_selector.record_trade_result.assert_called_once()
    assert orch._metrics.counter("trades_closed").value == Decimal("1")


async def test_resolve_order_side_for_close_short(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    assert orch._resolve_order_side(SignalDirection.CLOSE_SHORT) == OrderSide.BUY


async def test_open_request_contains_sl_tp(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    signal = Signal(
        symbol="BTC/USDT:USDT",
        direction=SignalDirection.LONG,
        confidence=0.8,
        strategy_name="ema_crossover",
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("51000"),
    )

    orch._trading_paused = False
    orch._rest_api = AsyncMock()
    orch._rest_api.fetch_ohlcv = AsyncMock(return_value=[{"a": 1}])
    orch._candle_buffer = MagicMock()
    orch._candle_buffer.has_enough.return_value = True
    orch._candle_buffer.get_candles.return_value = []
    orch._preprocessor = MagicMock()
    orch._preprocessor.candles_to_dataframe.return_value = MagicMock()
    orch._feature_engineer = MagicMock()
    orch._feature_engineer.build_features.return_value = MagicMock()
    orch._strategy_selector = MagicMock()
    orch._strategy_selector.get_best_signal.return_value = signal
    orch._position_manager = MagicMock()
    orch._position_manager.get_all_positions.return_value = []
    orch._account_manager = MagicMock()
    orch._account_manager.equity = Decimal("10000")
    orch._risk_manager = MagicMock()
    orch._risk_manager.evaluate_signal.return_value = RiskDecision(
        approved=True,
        quantity=Decimal("0.1"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("51000"),
    )
    orch._journal = None
    orch._telegram_sink = None
    orch._order_manager = AsyncMock()
    orch._order_manager.submit_order = AsyncMock(
        return_value=MagicMock(fee=Decimal("0"), avg_fill_price=None, filled_qty=Decimal("0")),
    )

    await orch._poll_and_analyze("BTC/USDT:USDT")

    request = orch._order_manager.submit_order.call_args.args[0]
    assert request.stop_loss == Decimal("49000")
    assert request.take_profit == Decimal("51000")


async def test_restore_strategy_states_from_positions(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    strategy = MagicMock()
    strategy.symbols = ["BTC/USDT:USDT"]
    orch._strategy_selector = MagicMock()
    orch._strategy_selector.strategies = {"ema_crossover": strategy}
    orch._position_manager = MagicMock()
    orch._position_manager.get_position.return_value = Position(
        symbol="BTC/USDT:USDT",
        side=PositionSide.LONG,
        size=Decimal("0.5"),
        entry_price=Decimal("50000"),
    )

    orch._restore_strategy_states_from_positions()
    strategy.set_state.assert_called_with("BTC/USDT:USDT", StrategyState.LONG)


async def test_close_request_uses_position_idx_and_no_false_close_log(
    settings: AppSettings,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    signal = Signal(
        symbol="BTC/USDT:USDT",
        direction=SignalDirection.CLOSE_SHORT,
        confidence=0.8,
        strategy_name="momentum",
        entry_price=Decimal("69000"),
    )
    existing = Position(
        symbol="BTC/USDT:USDT",
        side=PositionSide.SHORT,
        size=Decimal("1.381"),
        entry_price=Decimal("68936.2"),
        position_idx=2,
    )

    orch._trading_paused = False
    orch._rest_api = AsyncMock()
    orch._rest_api.fetch_ohlcv = AsyncMock(return_value=[{"a": 1}])
    orch._candle_buffer = MagicMock()
    orch._candle_buffer.has_enough.return_value = True
    orch._candle_buffer.get_candles.return_value = []
    orch._preprocessor = MagicMock()
    orch._preprocessor.candles_to_dataframe.return_value = MagicMock()
    orch._feature_engineer = MagicMock()
    orch._feature_engineer.build_features.return_value = MagicMock()
    strategy = MagicMock()
    strategy.symbols = ["BTC/USDT:USDT"]
    orch._strategy_selector = MagicMock()
    orch._strategy_selector.get_best_signal.return_value = signal
    orch._strategy_selector.strategies = {"momentum": strategy}
    orch._position_manager = MagicMock()
    orch._position_manager.get_all_positions.return_value = [existing]
    orch._position_manager.get_position.return_value = existing
    orch._position_manager.sync_positions = AsyncMock()
    orch._account_manager = MagicMock()
    orch._account_manager.equity = Decimal("10000")
    orch._risk_manager = MagicMock()
    orch._risk_manager.evaluate_signal.return_value = RiskDecision(
        approved=True,
        quantity=Decimal("1.381"),
        reason="exit_signal",
    )
    orch._journal = None
    orch._telegram_sink = None
    orch._order_manager = AsyncMock()
    orch._order_manager.submit_order = AsyncMock(
        return_value=MagicMock(fee=Decimal("0"), avg_fill_price=None, filled_qty=Decimal("0")),
    )
    orch._account_closed_trade = AsyncMock()

    await orch._poll_and_analyze("BTC/USDT:USDT")

    request = orch._order_manager.submit_order.call_args.args[0]
    assert request.position_idx == 2
    assert request.reduce_only is True
    assert request.side == OrderSide.BUY
    orch._account_closed_trade.assert_not_called()


async def test_close_skips_order_when_position_missing_after_resync(
    settings: AppSettings,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    signal = Signal(
        symbol="BTC/USDT:USDT",
        direction=SignalDirection.CLOSE_SHORT,
        confidence=0.8,
        strategy_name="momentum",
        entry_price=Decimal("69000"),
    )

    orch._trading_paused = False
    orch._rest_api = AsyncMock()
    orch._rest_api.fetch_ohlcv = AsyncMock(return_value=[{"a": 1}])
    orch._candle_buffer = MagicMock()
    orch._candle_buffer.has_enough.return_value = True
    orch._candle_buffer.get_candles.return_value = []
    orch._preprocessor = MagicMock()
    orch._preprocessor.candles_to_dataframe.return_value = MagicMock()
    orch._feature_engineer = MagicMock()
    orch._feature_engineer.build_features.return_value = MagicMock()
    strategy = MagicMock()
    strategy.symbols = ["BTC/USDT:USDT"]
    orch._strategy_selector = MagicMock()
    orch._strategy_selector.get_best_signal.return_value = signal
    orch._strategy_selector.strategies = {"momentum": strategy}
    orch._position_manager = MagicMock()
    orch._position_manager.get_all_positions.return_value = []
    orch._position_manager.get_position.return_value = None
    orch._position_manager.sync_positions = AsyncMock()
    orch._account_manager = MagicMock()
    orch._account_manager.equity = Decimal("10000")
    orch._risk_manager = MagicMock()
    orch._risk_manager.evaluate_signal.side_effect = [
        RiskDecision(approved=True, quantity=Decimal("1")),
        RiskDecision(approved=False, reason="no_position_to_close"),
    ]
    orch._journal = None
    orch._telegram_sink = None
    orch._order_manager = AsyncMock()
    orch._order_manager.submit_order = AsyncMock()

    await orch._poll_and_analyze("BTC/USDT:USDT")
    orch._order_manager.submit_order.assert_not_called()


async def test_reduce_only_110017_goes_to_special_handler(
    settings: AppSettings,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    signal = Signal(
        symbol="BTC/USDT:USDT",
        direction=SignalDirection.CLOSE_SHORT,
        confidence=0.8,
        strategy_name="momentum",
        entry_price=Decimal("69000"),
    )
    existing = Position(
        symbol="BTC/USDT:USDT",
        side=PositionSide.SHORT,
        size=Decimal("1"),
        entry_price=Decimal("68000"),
        position_idx=2,
    )
    orch._trading_paused = False
    orch._rest_api = AsyncMock()
    orch._rest_api.fetch_ohlcv = AsyncMock(return_value=[{"a": 1}])
    orch._candle_buffer = MagicMock()
    orch._candle_buffer.has_enough.return_value = True
    orch._candle_buffer.get_candles.return_value = []
    orch._preprocessor = MagicMock()
    orch._preprocessor.candles_to_dataframe.return_value = MagicMock()
    orch._feature_engineer = MagicMock()
    orch._feature_engineer.build_features.return_value = MagicMock()
    strategy = MagicMock()
    strategy.symbols = ["BTC/USDT:USDT"]
    orch._strategy_selector = MagicMock()
    orch._strategy_selector.get_best_signal.return_value = signal
    orch._strategy_selector.strategies = {"momentum": strategy}
    orch._position_manager = MagicMock()
    orch._position_manager.get_all_positions.return_value = [existing]
    orch._position_manager.get_position.return_value = existing
    orch._position_manager.sync_positions = AsyncMock()
    orch._account_manager = MagicMock()
    orch._account_manager.equity = Decimal("10000")
    orch._risk_manager = MagicMock()
    orch._risk_manager.evaluate_signal.return_value = RiskDecision(approved=True, quantity=Decimal("1"))
    orch._journal = None
    orch._telegram_sink = None
    orch._order_manager = AsyncMock()
    orch._order_manager.submit_order = AsyncMock(side_effect=Exception("retCode\":110017"))
    orch._handle_reduce_only_zero_position = AsyncMock()

    await orch._poll_and_analyze("BTC/USDT:USDT")
    orch._handle_reduce_only_zero_position.assert_called_once()


async def test_on_positions_refreshed_accounts_external_close(
    settings: AppSettings,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._position_manager = MagicMock()
    previous = Position(
        symbol="XRP/USDT:USDT",
        side=PositionSide.SHORT,
        size=Decimal("100"),
        entry_price=Decimal("1.43"),
        mark_price=Decimal("1.44"),
        unrealized_pnl=Decimal("-100"),
    )
    orch._last_positions_snapshot = {"XRP/USDT:USDT": previous}
    orch._position_manager.get_all_positions.return_value = []
    orch._account_closed_trade = AsyncMock()

    await orch._on_positions_refreshed()

    orch._account_closed_trade.assert_called_once()
