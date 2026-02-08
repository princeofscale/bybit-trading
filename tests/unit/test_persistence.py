from decimal import Decimal
from pathlib import Path

import pytest

from core.persistence import RecoveryManager, StatePersistence, StateSnapshot


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def persistence(state_dir: Path) -> StatePersistence:
    return StatePersistence(state_dir)


@pytest.fixture
def recovery(persistence: StatePersistence) -> RecoveryManager:
    return RecoveryManager(persistence)


class TestStateSnapshot:
    def test_set_and_get(self) -> None:
        snap = StateSnapshot()
        snap.set("equity", Decimal("50000"))
        assert snap.get("equity") == Decimal("50000")

    def test_get_default(self) -> None:
        snap = StateSnapshot()
        assert snap.get("missing", "default") == "default"

    def test_has_key(self) -> None:
        snap = StateSnapshot()
        snap.set("key", "value")
        assert snap.has("key") is True
        assert snap.has("other") is False

    def test_keys(self) -> None:
        snap = StateSnapshot()
        snap.set("a", 1)
        snap.set("b", 2)
        assert sorted(snap.keys()) == ["a", "b"]

    def test_version(self) -> None:
        snap = StateSnapshot()
        assert snap.version == 1

    def test_timestamp_positive(self) -> None:
        snap = StateSnapshot()
        assert snap.timestamp > 0

    def test_to_dict(self) -> None:
        snap = StateSnapshot()
        snap.set("x", "y")
        d = snap.to_dict()
        assert d["version"] == 1
        assert d["data"]["x"] == "y"
        assert "timestamp" in d

    def test_from_dict(self) -> None:
        raw = {"version": 2, "timestamp": 12345, "data": {"key": "val"}}
        snap = StateSnapshot.from_dict(raw)
        assert snap.version == 2
        assert snap.timestamp == 12345
        assert snap.get("key") == "val"

    def test_data_is_copy(self) -> None:
        snap = StateSnapshot()
        snap.set("a", 1)
        data = snap.data
        data["b"] = 2
        assert snap.has("b") is False


class TestStatePersistence:
    def test_creates_directory(self, state_dir: Path) -> None:
        StatePersistence(state_dir)
        assert state_dir.exists()

    def test_save_creates_file(self, persistence: StatePersistence) -> None:
        snap = StateSnapshot()
        snap.set("test", "data")
        path = persistence.save("engine", snap)
        assert path.exists()
        assert path.name == "engine.json"

    def test_load_returns_snapshot(self, persistence: StatePersistence) -> None:
        snap = StateSnapshot()
        snap.set("equity", "50000")
        persistence.save("account", snap)

        loaded = persistence.load("account")
        assert loaded is not None
        assert loaded.get("equity") == Decimal("50000")

    def test_load_missing_returns_none(self, persistence: StatePersistence) -> None:
        assert persistence.load("nonexistent") is None

    def test_exists(self, persistence: StatePersistence) -> None:
        snap = StateSnapshot()
        persistence.save("test", snap)
        assert persistence.exists("test") is True
        assert persistence.exists("other") is False

    def test_delete(self, persistence: StatePersistence) -> None:
        snap = StateSnapshot()
        persistence.save("temp", snap)
        assert persistence.delete("temp") is True
        assert persistence.exists("temp") is False

    def test_delete_missing(self, persistence: StatePersistence) -> None:
        assert persistence.delete("nope") is False

    def test_list_snapshots(self, persistence: StatePersistence) -> None:
        for name in ["engine", "positions", "risk"]:
            persistence.save(name, StateSnapshot())
        names = persistence.list_snapshots()
        assert sorted(names) == ["engine", "positions", "risk"]

    def test_decimal_round_trip(self, persistence: StatePersistence) -> None:
        snap = StateSnapshot()
        snap.set("price", Decimal("50123.45"))
        snap.set("size", Decimal("0.001"))
        persistence.save("decimals", snap)

        loaded = persistence.load("decimals")
        assert loaded.get("price") == Decimal("50123.45")
        assert loaded.get("size") == Decimal("0.001")

    def test_state_dir_property(self, persistence: StatePersistence, state_dir: Path) -> None:
        assert persistence.state_dir == state_dir


class TestRecoveryManager:
    def test_save_and_recover(self, recovery: RecoveryManager) -> None:
        snap = StateSnapshot()
        snap.set("balance", Decimal("10000"))
        recovery.save_state("account", snap)

        recovered = recovery.recover_state("account")
        assert recovered is not None
        assert recovered.get("balance") == Decimal("10000")

    def test_recover_missing(self, recovery: RecoveryManager) -> None:
        assert recovery.recover_state("nonexistent") is None

    def test_recover_all(self, recovery: RecoveryManager) -> None:
        for name in ["a", "b"]:
            snap = StateSnapshot()
            snap.set("name", name)
            recovery.save_state(name, snap)

        result = recovery.recover_all(["a", "b", "c"])
        assert len(result) == 2
        assert "a" in result
        assert "b" in result
        assert "c" not in result

    def test_recovered_components(self, recovery: RecoveryManager) -> None:
        snap = StateSnapshot()
        recovery.save_state("engine", snap)
        recovery.recover_state("engine")
        assert "engine" in recovery.recovered_components

    def test_clear_state(self, recovery: RecoveryManager) -> None:
        snap = StateSnapshot()
        recovery.save_state("temp", snap)
        recovery.recover_state("temp")
        recovery.clear_state("temp")
        assert recovery.has_saved_state("temp") is False
        assert "temp" not in recovery.recovered_components

    def test_has_saved_state(self, recovery: RecoveryManager) -> None:
        snap = StateSnapshot()
        recovery.save_state("x", snap)
        assert recovery.has_saved_state("x") is True
        assert recovery.has_saved_state("y") is False
