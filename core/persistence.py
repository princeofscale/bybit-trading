import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

from utils.time_utils import utc_now_ms

logger = structlog.get_logger("persistence")


class DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def _decimal_hook(obj: dict[str, Any]) -> dict[str, Any]:
    for key, value in obj.items():
        if isinstance(value, str):
            try:
                obj[key] = Decimal(value)
            except Exception:
                pass
    return obj


class StateSnapshot:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._timestamp = utc_now_ms()
        self._version = 1

    @property
    def data(self) -> dict[str, Any]:
        return dict(self._data)

    @property
    def timestamp(self) -> int:
        return self._timestamp

    @property
    def version(self) -> int:
        return self._version

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self._version,
            "timestamp": self._timestamp,
            "data": self._data,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StateSnapshot":
        snap = cls()
        snap._version = raw.get("version", 1)
        snap._timestamp = raw.get("timestamp", utc_now_ms())
        snap._data = raw.get("data", {})
        return snap


class StatePersistence:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    def save(self, name: str, snapshot: StateSnapshot) -> Path:
        filepath = self._state_dir / f"{name}.json"
        raw = json.dumps(snapshot.to_dict(), cls=DecimalEncoder, indent=2)
        filepath.write_text(raw, encoding="utf-8")
        return filepath

    def load(self, name: str) -> StateSnapshot | None:
        filepath = self._state_dir / f"{name}.json"
        if not filepath.exists():
            return None
        raw = filepath.read_text(encoding="utf-8")
        parsed = json.loads(raw, object_hook=_decimal_hook)
        return StateSnapshot.from_dict(parsed)

    def exists(self, name: str) -> bool:
        return (self._state_dir / f"{name}.json").exists()

    def delete(self, name: str) -> bool:
        filepath = self._state_dir / f"{name}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def list_snapshots(self) -> list[str]:
        return [
            p.stem for p in self._state_dir.glob("*.json")
        ]


class RecoveryManager:
    def __init__(self, persistence: StatePersistence) -> None:
        self._persistence = persistence
        self._recovered: dict[str, StateSnapshot] = {}

    def save_state(self, component: str, snapshot: StateSnapshot) -> None:
        self._persistence.save(component, snapshot)

    def recover_state(self, component: str) -> StateSnapshot | None:
        snapshot = self._persistence.load(component)
        if snapshot:
            self._recovered[component] = snapshot
        return snapshot

    def recover_all(self, components: list[str]) -> dict[str, StateSnapshot]:
        result: dict[str, StateSnapshot] = {}
        for name in components:
            snap = self.recover_state(name)
            if snap:
                result[name] = snap
        return result

    @property
    def recovered_components(self) -> list[str]:
        return list(self._recovered.keys())

    def clear_state(self, component: str) -> None:
        self._persistence.delete(component)
        self._recovered.pop(component, None)

    def has_saved_state(self, component: str) -> bool:
        return self._persistence.exists(component)
