from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import AppSettings
from config.strategy_profiles import MODERATE_PROFILE
from core.orchestrator import TradingOrchestrator
from data.models import OrderSide
from strategies.base_strategy import Signal, SignalDirection


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
    assert "PAUSED" in result


async def test_cmd_resume_clears_flag(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)
    orch._trading_paused = True

    result = await orch._cmd_resume()
    assert orch._trading_paused is False
    assert "RESUMED" in result


async def test_cmd_help_returns_commands(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    result = await orch._cmd_help()
    assert "/status" in result
    assert "/positions" in result
    assert "/pnl" in result


async def test_cmd_status_with_no_managers(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    result = await orch._cmd_status()
    assert "Bot Status" in result
    assert "RUNNING" in result


async def test_cmd_pnl_with_no_managers(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    result = await orch._cmd_pnl()
    assert "PnL" in result
    assert "0.00 USDT" in result


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
