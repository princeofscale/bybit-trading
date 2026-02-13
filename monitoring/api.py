import asyncio
from decimal import Decimal
from typing import Any

import structlog

logger = structlog.get_logger("dashboard_api")


class DashboardState:
    def __init__(self) -> None:
        self.bot_state: str = "starting"
        self.equity: Decimal = Decimal("0")
        self.peak_equity: Decimal = Decimal("0")
        self.drawdown_pct: Decimal = Decimal("0")
        self.open_positions: list[dict[str, Any]] = []
        self.signals_count: int = 0
        self.trades_count: int = 0
        self.session_id: str = ""
        self.strategies: list[str] = []
        self.risk_state: str = "NORMAL"
        self.daily_pnl: Decimal = Decimal("0")
        self.unrealized_pnl: Decimal = Decimal("0")

    def to_status(self) -> dict[str, Any]:
        return {
            "bot_state": self.bot_state,
            "session_id": self.session_id,
            "equity": float(self.equity),
            "peak_equity": float(self.peak_equity),
            "drawdown_pct": float(self.drawdown_pct),
            "open_positions": len(self.open_positions),
            "signals_count": self.signals_count,
            "trades_count": self.trades_count,
            "strategies": self.strategies,
            "risk_state": self.risk_state,
        }

    def to_pnl(self) -> dict[str, Any]:
        return {
            "equity": float(self.equity),
            "peak_equity": float(self.peak_equity),
            "drawdown_pct": float(self.drawdown_pct),
            "daily_pnl": float(self.daily_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
        }


class DashboardService:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        self._host = host
        self._port = port
        self._state = DashboardState()
        self._metrics_registry: Any = None
        self._server_task: asyncio.Task[None] | None = None
        self._app: Any = None

    @property
    def state(self) -> DashboardState:
        return self._state

    def set_metrics_registry(self, registry: Any) -> None:
        self._metrics_registry = registry

    async def start(self) -> None:
        try:
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse, PlainTextResponse
            from starlette.routing import Route
        except ImportError:
            await logger.awarning("dashboard_disabled_no_starlette")
            return

        async def health(_request: Any) -> JSONResponse:
            return JSONResponse({"status": "ok", "session_id": self._state.session_id})

        async def status(_request: Any) -> JSONResponse:
            return JSONResponse(self._state.to_status())

        async def positions(_request: Any) -> JSONResponse:
            return JSONResponse({"positions": self._state.open_positions})

        async def metrics(_request: Any) -> JSONResponse:
            if not self._metrics_registry:
                return JSONResponse({"metrics": []})
            points = self._metrics_registry.get_all_points()
            return JSONResponse({
                "metrics": [
                    {"name": p.name, "value": float(p.value), "type": p.metric_type}
                    for p in points
                ]
            })

        async def pnl(_request: Any) -> JSONResponse:
            return JSONResponse(self._state.to_pnl())

        async def metrics_prometheus(_request: Any) -> PlainTextResponse:
            if not self._metrics_registry:
                return PlainTextResponse("")
            from monitoring.metrics_export import to_prometheus_text
            text = to_prometheus_text(self._metrics_registry)
            return PlainTextResponse(text, media_type="text/plain; version=0.0.4; charset=utf-8")

        routes = [
            Route("/health", health),
            Route("/status", status),
            Route("/positions", positions),
            Route("/metrics", metrics),
            Route("/pnl", pnl),
            Route("/metrics/prometheus", metrics_prometheus),
        ]
        self._app = Starlette(routes=routes)
        self._server_task = asyncio.create_task(self._run_server())
        await logger.ainfo("dashboard_started", host=self._host, port=self._port)

    async def _run_server(self) -> None:
        try:
            import uvicorn
            config = uvicorn.Config(
                app=self._app,
                host=self._host,
                port=self._port,
                log_level="warning",
            )
            server = uvicorn.Server(config)
            await server.serve()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            await logger.aerror("dashboard_server_error", error=str(exc))

    async def stop(self) -> None:
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
        await logger.ainfo("dashboard_stopped")
