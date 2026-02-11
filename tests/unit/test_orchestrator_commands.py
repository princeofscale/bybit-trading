from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from config.settings import AppSettings
from config.strategy_profiles import MODERATE_PROFILE
from core.orchestrator import TradingOrchestrator
from strategies.base_strategy import Signal, SignalDirection


async def test_status_uses_journal_daily_aggregates(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None)
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._sync_for_reporting = AsyncMock()
    orch._account_manager = MagicMock()
    orch._account_manager.equity = Decimal("1000")
    orch._position_manager = MagicMock()
    orch._position_manager.open_position_count = 2
    orch._strategy_selector = MagicMock()
    orch._strategy_selector.strategies = {"ema_crossover": MagicMock()}
    orch._journal_reader = AsyncMock()
    orch._journal_reader.count_signals_since = AsyncMock(return_value=9)
    orch._journal_reader.count_trades_since = AsyncMock(return_value=4)
    orch._journal_reader.sum_realized_pnl_since = AsyncMock(return_value=Decimal("12.5"))

    text = await orch._cmd_status()
    assert "Сигналов: `9`" in text
    assert "Сделок: `4`" in text
    assert "Дневной PnL: `+12.50 USDT`" in text


async def test_get_daily_stats_falls_back_when_reader_disabled(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None)
    settings.status.use_journal_daily_agg = False
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._signals_count = 5
    orch._trades_count = 3

    stats = await orch._get_daily_stats()
    assert stats["signals"] == 5
    assert stats["trades"] == 3
    assert stats["realized_pnl"] == Decimal("0")


async def test_get_daily_stats_uses_cache(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None)
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    now = datetime.now(timezone.utc)
    orch._daily_stats_cache = (
        now,
        {"signals": 2, "trades": 1, "realized_pnl": Decimal("1.25")},
    )
    orch._journal_reader = AsyncMock()

    stats = await orch._get_daily_stats()
    assert stats["signals"] == 2
    orch._journal_reader.count_signals_since.assert_not_called()


async def test_entry_ready_includes_directional_guard_block_reason(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None)
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._symbols = ["BTC/USDT:USDT"]
    orch._rest_api = AsyncMock()
    orch._rest_api.fetch_ohlcv = AsyncMock(return_value=[{"a": 1}])
    orch._preprocessor = MagicMock()
    orch._preprocessor.candles_to_dataframe.return_value = MagicMock()
    orch._feature_engineer = MagicMock()
    orch._feature_engineer.build_features.return_value = MagicMock()
    orch._strategy_selector = MagicMock()
    orch._strategy_selector.get_best_signal.return_value = Signal(
        symbol="BTC/USDT:USDT",
        direction=SignalDirection.LONG,
        confidence=0.8,
        strategy_name="ema_crossover",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
    )
    orch._evaluate_mtf_confirm = AsyncMock(return_value=(True, "", {"mtf_ema50": 1.0, "mtf_ema200": 0.5, "mtf_adx": 25.0}))
    orch._account_manager = MagicMock()
    orch._account_manager.equity = Decimal("10000")
    orch._position_manager = MagicMock()
    orch._position_manager.get_all_positions.return_value = []
    orch._risk_manager = MagicMock()
    orch._risk_manager.evaluate_signal.return_value = MagicMock(approved=False, reason="side_balancer_long")
    orch._risk_manager.side_balancer_snapshot.return_value = {
        "verdict": "guard_active_long",
        "streak_side": "long",
        "streak_count": 4,
        "imbalance_pct": Decimal("0.24"),
    }

    text = await orch._cmd_entry_ready(["BTC/USDT:USDT"])
    assert "BLOCKED" in text
    assert "side_balancer_long" in text
    assert "Side" in text
