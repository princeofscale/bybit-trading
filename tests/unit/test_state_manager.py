import pytest

from core.state_manager import BotState, InvalidStateTransition, StateManager


@pytest.fixture
def state_manager() -> StateManager:
    return StateManager()


async def test_initial_state(state_manager: StateManager) -> None:
    assert state_manager.state == BotState.INITIALIZING


async def test_valid_transition(state_manager: StateManager) -> None:
    await state_manager.transition_to(BotState.RUNNING)
    assert state_manager.state == BotState.RUNNING


async def test_invalid_transition(state_manager: StateManager) -> None:
    with pytest.raises(InvalidStateTransition):
        await state_manager.transition_to(BotState.PAUSED)


async def test_full_lifecycle(state_manager: StateManager) -> None:
    await state_manager.transition_to(BotState.RUNNING)
    await state_manager.transition_to(BotState.STOPPING)
    await state_manager.transition_to(BotState.STOPPED)
    assert state_manager.state == BotState.STOPPED


async def test_trading_allowed_when_running(state_manager: StateManager) -> None:
    await state_manager.transition_to(BotState.RUNNING)
    assert state_manager.is_trading_allowed is True


async def test_trading_not_allowed_when_paused(state_manager: StateManager) -> None:
    await state_manager.transition_to(BotState.RUNNING)
    state_manager.add_trading_pause("circuit_breaker")
    assert state_manager.is_trading_allowed is False


async def test_trading_pause_with_duration(state_manager: StateManager) -> None:
    await state_manager.transition_to(BotState.RUNNING)
    state_manager.add_trading_pause("test_pause", duration_ms=1)
    import asyncio
    await asyncio.sleep(0.01)
    assert state_manager.is_trading_allowed is True


async def test_clear_pauses(state_manager: StateManager) -> None:
    await state_manager.transition_to(BotState.RUNNING)
    state_manager.add_trading_pause("pause_1")
    state_manager.add_trading_pause("pause_2")
    assert state_manager.is_trading_allowed is False
    state_manager.clear_trading_pauses()
    assert state_manager.is_trading_allowed is True


async def test_metadata(state_manager: StateManager) -> None:
    state_manager.set_metadata("peak_equity", 10000)
    assert state_manager.get_metadata("peak_equity") == 10000
    assert state_manager.get_metadata("nonexistent", "default") == "default"


async def test_error_recovery(state_manager: StateManager) -> None:
    await state_manager.transition_to(BotState.RUNNING)
    await state_manager.transition_to(BotState.ERROR)
    await state_manager.transition_to(BotState.INITIALIZING)
    await state_manager.transition_to(BotState.RUNNING)
    assert state_manager.state == BotState.RUNNING
