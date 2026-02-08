from pathlib import Path

import pytest
from sklearn.tree import DecisionTreeClassifier

from ml.model_registry import ModelEntry, ModelRegistry


@pytest.fixture
def registry(tmp_path: Path) -> ModelRegistry:
    return ModelRegistry(tmp_path / "models")


def _dummy_model() -> DecisionTreeClassifier:
    m = DecisionTreeClassifier(random_state=42)
    import numpy as np
    m.fit(np.array([[1, 2], [3, 4]]), np.array([0, 1]))
    return m


class TestRegister:
    def test_register_creates_entry(self, registry: ModelRegistry) -> None:
        entry = registry.register(
            model=_dummy_model(),
            model_id="test_model",
            model_type="decision_tree",
            metrics={"accuracy": 0.85},
            feature_names=["f1", "f2"],
        )
        assert entry.model_id == "test_model_v1"
        assert entry.version == 1
        assert entry.metrics["accuracy"] == 0.85

    def test_register_increments_version(self, registry: ModelRegistry) -> None:
        registry.register(
            _dummy_model(), "test_model", "dt",
            {"accuracy": 0.8}, ["f1"],
        )
        entry2 = registry.register(
            _dummy_model(), "test_model", "dt",
            {"accuracy": 0.9}, ["f1"],
        )
        assert entry2.version == 2
        assert entry2.model_id == "test_model_v2"

    def test_register_saves_file(self, registry: ModelRegistry) -> None:
        registry.register(
            _dummy_model(), "file_test", "dt", {}, [],
        )
        model_path = registry._base_dir / "file_test_v1.joblib"
        assert model_path.exists()


class TestLoadModel:
    def test_load_registered_model(self, registry: ModelRegistry) -> None:
        original = _dummy_model()
        registry.register(original, "load_test", "dt", {}, ["f1", "f2"])
        loaded = registry.load_model("load_test_v1")
        assert loaded is not None

    def test_load_nonexistent_raises(self, registry: ModelRegistry) -> None:
        with pytest.raises(FileNotFoundError, match="model_not_found"):
            registry.load_model("nonexistent_v1")


class TestGetEntry:
    def test_get_existing(self, registry: ModelRegistry) -> None:
        registry.register(_dummy_model(), "entry_test", "dt", {"a": 1.0}, [])
        entry = registry.get_entry("entry_test_v1")
        assert entry is not None
        assert entry.model_type == "dt"

    def test_get_nonexistent(self, registry: ModelRegistry) -> None:
        assert registry.get_entry("nope_v1") is None


class TestGetLatest:
    def test_latest_version(self, registry: ModelRegistry) -> None:
        registry.register(_dummy_model(), "latest_test", "dt", {"v": 1.0}, [])
        registry.register(_dummy_model(), "latest_test", "dt", {"v": 2.0}, [])
        registry.register(_dummy_model(), "latest_test", "dt", {"v": 3.0}, [])
        latest = registry.get_latest("latest_test")
        assert latest is not None
        assert latest.version == 3
        assert latest.metrics["v"] == 3.0

    def test_latest_no_match(self, registry: ModelRegistry) -> None:
        assert registry.get_latest("nothing") is None


class TestListModels:
    def test_list_all(self, registry: ModelRegistry) -> None:
        registry.register(_dummy_model(), "m1", "dt", {}, [])
        registry.register(_dummy_model(), "m2", "dt", {}, [])
        models = registry.list_models()
        assert len(models) == 2

    def test_list_empty(self, registry: ModelRegistry) -> None:
        assert registry.list_models() == []


class TestDeleteModel:
    def test_delete_removes_entry_and_file(self, registry: ModelRegistry) -> None:
        registry.register(_dummy_model(), "del_test", "dt", {}, [])
        assert registry.delete_model("del_test_v1") is True
        assert registry.get_entry("del_test_v1") is None
        model_path = registry._base_dir / "del_test_v1.joblib"
        assert not model_path.exists()

    def test_delete_nonexistent(self, registry: ModelRegistry) -> None:
        assert registry.delete_model("nope_v1") is False


class TestPersistence:
    def test_registry_persists_across_instances(self, tmp_path: Path) -> None:
        base = tmp_path / "persist_models"
        r1 = ModelRegistry(base)
        r1.register(_dummy_model(), "persist_test", "dt", {"acc": 0.9}, ["f1"])
        r2 = ModelRegistry(base)
        entry = r2.get_entry("persist_test_v1")
        assert entry is not None
        assert entry.metrics["acc"] == 0.9


class TestModelEntry:
    def test_to_dict_round_trip(self) -> None:
        entry = ModelEntry(
            model_id="test_v1", model_type="xgb", version=1,
            metrics={"acc": 0.8}, feature_names=["f1", "f2"],
            params={"n_estimators": 100},
        )
        d = entry.to_dict()
        restored = ModelEntry.from_dict(d)
        assert restored.model_id == entry.model_id
        assert restored.version == entry.version
        assert restored.metrics == entry.metrics
