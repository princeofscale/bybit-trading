import asyncio

import pytest

from core.shutdown import ShutdownManager, ShutdownMode, ShutdownTask


@pytest.fixture
def manager() -> ShutdownManager:
    return ShutdownManager(mode=ShutdownMode.GRACEFUL, timeout_seconds=5.0)


class TestShutdownInit:
    def test_default_mode(self, manager: ShutdownManager) -> None:
        assert manager.mode == ShutdownMode.GRACEFUL

    def test_not_requested(self, manager: ShutdownManager) -> None:
        assert manager.shutdown_requested is False

    def test_not_complete(self, manager: ShutdownManager) -> None:
        assert manager.shutdown_complete is False

    def test_timeout(self, manager: ShutdownManager) -> None:
        assert manager.timeout == 5.0

    def test_set_mode(self, manager: ShutdownManager) -> None:
        manager.mode = ShutdownMode.CLOSE_POSITIONS
        assert manager.mode == ShutdownMode.CLOSE_POSITIONS


class TestRegisterTask:
    def test_registers(self, manager: ShutdownManager) -> None:
        async def noop() -> None:
            pass

        manager.register_task("stop_ws", noop)
        assert "stop_ws" in manager.registered_tasks

    def test_multiple_tasks(self, manager: ShutdownManager) -> None:
        async def noop() -> None:
            pass

        manager.register_task("a", noop, priority=1)
        manager.register_task("b", noop, priority=2)
        assert len(manager.registered_tasks) == 2

    def test_unregister(self, manager: ShutdownManager) -> None:
        async def noop() -> None:
            pass

        manager.register_task("x", noop)
        manager.unregister_task("x")
        assert "x" not in manager.registered_tasks


class TestGracefulExecution:
    @pytest.mark.asyncio
    async def test_executes_all_tasks(self, manager: ShutdownManager) -> None:
        executed: list[str] = []

        async def task_a() -> None:
            executed.append("a")

        async def task_b() -> None:
            executed.append("b")

        manager.register_task("a", task_a, priority=1)
        manager.register_task("b", task_b, priority=2)
        results = await manager.execute()
        assert len(executed) == 2
        assert executed == ["a", "b"]
        assert manager.shutdown_complete is True

    @pytest.mark.asyncio
    async def test_priority_order(self, manager: ShutdownManager) -> None:
        order: list[str] = []

        async def first() -> None:
            order.append("first")

        async def second() -> None:
            order.append("second")

        async def third() -> None:
            order.append("third")

        manager.register_task("c", third, priority=30)
        manager.register_task("a", first, priority=10)
        manager.register_task("b", second, priority=20)
        await manager.execute()
        assert order == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_marks_completed(self, manager: ShutdownManager) -> None:
        async def ok() -> None:
            pass

        manager.register_task("ok", ok)
        results = await manager.execute()
        assert results[0].completed is True
        assert results[0].error is None

    @pytest.mark.asyncio
    async def test_captures_error(self, manager: ShutdownManager) -> None:
        async def fail() -> None:
            raise RuntimeError("boom")

        manager.register_task("fail", fail)
        results = await manager.execute()
        assert results[0].completed is False
        assert results[0].error == "boom"

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        mgr = ShutdownManager(timeout_seconds=0.1)

        async def slow() -> None:
            await asyncio.sleep(10)

        mgr.register_task("slow", slow)
        results = await mgr.execute()
        assert results[0].error == "timeout"
        assert mgr.shutdown_complete is True

    @pytest.mark.asyncio
    async def test_sets_requested_flag(self, manager: ShutdownManager) -> None:
        await manager.execute()
        assert manager.shutdown_requested is True

    @pytest.mark.asyncio
    async def test_duration_tracked(self, manager: ShutdownManager) -> None:
        async def quick() -> None:
            pass

        manager.register_task("q", quick)
        await manager.execute()
        assert manager.duration_ms >= 0


class TestImmediateMode:
    @pytest.mark.asyncio
    async def test_skips_tasks(self) -> None:
        mgr = ShutdownManager(mode=ShutdownMode.IMMEDIATE)
        executed = False

        async def should_not_run() -> None:
            nonlocal executed
            executed = True

        mgr.register_task("skip", should_not_run)
        await mgr.execute()
        assert executed is False
        assert mgr.shutdown_complete is True


class TestReport:
    @pytest.mark.asyncio
    async def test_report_structure(self, manager: ShutdownManager) -> None:
        async def ok() -> None:
            pass

        async def fail() -> None:
            raise ValueError("bad")

        manager.register_task("ok", ok, priority=1)
        manager.register_task("fail", fail, priority=2)
        await manager.execute()

        report = manager.get_report()
        assert report["mode"] == "graceful"
        assert report["total_tasks"] == 2
        assert report["completed"] == 1
        assert report["failed"] == 1
        assert len(report["failures"]) == 1
        assert report["failures"][0]["name"] == "fail"
