import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import joblib


class ModelEntry:
    def __init__(
        self,
        model_id: str,
        model_type: str,
        version: int,
        metrics: dict[str, float],
        feature_names: list[str],
        params: dict[str, Any],
        created_at: str = "",
    ) -> None:
        self.model_id = model_id
        self.model_type = model_type
        self.version = version
        self.metrics = metrics
        self.feature_names = feature_names
        self.params = params
        self.created_at = created_at or datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type,
            "version": self.version,
            "metrics": self.metrics,
            "feature_names": self.feature_names,
            "params": self.params,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelEntry":
        return cls(**data)


class ModelRegistry:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._registry_file = base_dir / "registry.json"
        self._entries: dict[str, ModelEntry] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if self._registry_file.exists():
            data = json.loads(self._registry_file.read_text())
            for mid, entry_data in data.items():
                self._entries[mid] = ModelEntry.from_dict(entry_data)

    def _save_registry(self) -> None:
        data = {mid: e.to_dict() for mid, e in self._entries.items()}
        self._registry_file.write_text(json.dumps(data, indent=2))

    def register(
        self,
        model: Any,
        model_id: str,
        model_type: str,
        metrics: dict[str, float],
        feature_names: list[str],
        params: dict[str, Any] | None = None,
    ) -> ModelEntry:
        version = self._next_version(model_id)
        versioned_id = f"{model_id}_v{version}"

        model_path = self._base_dir / f"{versioned_id}.joblib"
        joblib.dump(model, model_path)

        entry = ModelEntry(
            model_id=versioned_id,
            model_type=model_type,
            version=version,
            metrics=metrics,
            feature_names=feature_names,
            params=params or {},
        )
        self._entries[versioned_id] = entry
        self._save_registry()
        return entry

    def load_model(self, model_id: str) -> Any:
        model_path = self._base_dir / f"{model_id}.joblib"
        if not model_path.exists():
            raise FileNotFoundError(f"model_not_found: {model_id}")
        return joblib.load(model_path)

    def get_entry(self, model_id: str) -> ModelEntry | None:
        return self._entries.get(model_id)

    def get_latest(self, base_id: str) -> ModelEntry | None:
        matching = [
            e for e in self._entries.values()
            if e.model_id.startswith(base_id + "_v")
        ]
        if not matching:
            return None
        return max(matching, key=lambda e: e.version)

    def list_models(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def delete_model(self, model_id: str) -> bool:
        if model_id not in self._entries:
            return False
        model_path = self._base_dir / f"{model_id}.joblib"
        if model_path.exists():
            model_path.unlink()
        del self._entries[model_id]
        self._save_registry()
        return True

    def _next_version(self, base_id: str) -> int:
        matching = [
            e for e in self._entries.values()
            if e.model_id.startswith(base_id + "_v")
        ]
        if not matching:
            return 1
        return max(e.version for e in matching) + 1
