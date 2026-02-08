from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import AppSettings, RiskSettings
from config.strategy_profiles import MODERATE_PROFILE
from core.orchestrator import TradingOrchestrator
from core.event_bus import Event, EventType
from exchange.models import Candle
from strategies.base_strategy import Signal, SignalDirection


@pytest.fixture
def settings() -> AppSettings:
    return AppSettings(_env_file=None)


@pytest.fixture
async def orchestrator_mocked(settings: AppSettings, tmp_path: Path) -> TradingOrchestrator:
    journal_path = tmp_path / "test_journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    with patch.object(orch, "_client", AsyncMock()):
        with patch.object(orch, "_rest_api", AsyncMock()):
            with patch.object(orch, "_ws_manager", AsyncMock()):
                yield orch


async def test_session_id_generated(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    assert orch._session_id
    assert len(orch._session_id) > 0


async def test_signal_to_order_params_long(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    from data.models import OrderSide

    side, reduce = orch._signal_to_order_params(SignalDirection.LONG)
    assert side == OrderSide.BUY
    assert reduce is False


async def test_signal_to_order_params_close_long(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    from data.models import OrderSide

    side, reduce = orch._signal_to_order_params(SignalDirection.CLOSE_LONG)
    assert side == OrderSide.SELL
    assert reduce is True


async def test_parse_candle_from_list(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    data = [1704110400000, 50000.0, 50100.0, 49900.0, 50050.0, 100.0]
    candle = orch._parse_candle("BTCUSDT", data)

    assert candle.symbol == "BTCUSDT"
    assert candle.open_time == 1704110400000
    assert candle.close == Decimal("50050")


async def test_parse_candle_from_dict(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    data = {
        "timestamp": 1704110400000,
        "open": 50000.0,
        "high": 50100.0,
        "low": 49900.0,
        "close": 50050.0,
        "volume": 100.0,
    }
    candle = orch._parse_candle("BTCUSDT", data)

    assert candle.symbol == "BTCUSDT"
    assert candle.close == Decimal("50050")


async def test_request_shutdown_sets_event(settings: AppSettings, tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    orch = TradingOrchestrator(settings, MODERATE_PROFILE, journal_path)

    assert not orch._shutdown_event.is_set()
    orch.request_shutdown()
    assert orch._shutdown_event.is_set()
