from enum import StrEnum

from pydantic import BaseModel, Field

from utils.time_utils import utc_now_ms


class ComponentStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentHealth(BaseModel):
    name: str
    status: ComponentStatus = ComponentStatus.UNKNOWN
    last_check_ts: int = 0
    message: str = ""
    latency_ms: int = 0


class SystemHealth(BaseModel):
    overall: ComponentStatus = ComponentStatus.UNKNOWN
    components: dict[str, ComponentHealth] = Field(default_factory=dict)
    timestamp: int = Field(default_factory=utc_now_ms)
    uptime_ms: int = 0


class HealthChecker:
    def __init__(self) -> None:
        self._components: dict[str, ComponentHealth] = {}
        self._start_ts = utc_now_ms()

    def register_component(self, name: str) -> None:
        self._components[name] = ComponentHealth(name=name)

    def update_status(
        self,
        name: str,
        status: ComponentStatus,
        message: str = "",
        latency_ms: int = 0,
    ) -> None:
        if name not in self._components:
            self.register_component(name)
        self._components[name] = ComponentHealth(
            name=name,
            status=status,
            last_check_ts=utc_now_ms(),
            message=message,
            latency_ms=latency_ms,
        )

    def get_component_health(self, name: str) -> ComponentHealth | None:
        return self._components.get(name)

    @property
    def component_names(self) -> list[str]:
        return list(self._components.keys())

    def get_system_health(self) -> SystemHealth:
        overall = self._compute_overall()
        return SystemHealth(
            overall=overall,
            components=dict(self._components),
            uptime_ms=utc_now_ms() - self._start_ts,
        )

    def _compute_overall(self) -> ComponentStatus:
        if not self._components:
            return ComponentStatus.UNKNOWN
        statuses = [c.status for c in self._components.values()]
        if any(s == ComponentStatus.UNHEALTHY for s in statuses):
            return ComponentStatus.UNHEALTHY
        if any(s == ComponentStatus.DEGRADED for s in statuses):
            return ComponentStatus.DEGRADED
        if all(s == ComponentStatus.HEALTHY for s in statuses):
            return ComponentStatus.HEALTHY
        return ComponentStatus.DEGRADED

    def is_healthy(self) -> bool:
        return self._compute_overall() == ComponentStatus.HEALTHY

    def unhealthy_components(self) -> list[str]:
        return [
            name for name, c in self._components.items()
            if c.status == ComponentStatus.UNHEALTHY
        ]

    def reset(self) -> None:
        self._components.clear()
        self._start_ts = utc_now_ms()
