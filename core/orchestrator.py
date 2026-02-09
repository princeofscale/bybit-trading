import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import structlog

from config.settings import AppSettings, RiskSettings
from config.strategy_profiles import StrategyProfile, profile_to_risk_settings
from config.trading_pairs import get_ccxt_symbols
from core.candle_buffer import CandleBuffer
from core.event_bus import EventBus
from core.orchestrator_commands import OrchestratorCommandsMixin
from core.orchestrator_execution import OrchestratorExecutionMixin
from core.orchestrator_loops import OrchestratorLoopsMixin
from data.feature_engineer import FeatureEngineer
from data.preprocessor import CandlePreprocessor
from exchange.account_manager import AccountManager
from exchange.bybit_client import BybitClient
from exchange.order_manager import OrderManager
from exchange.position_manager import PositionManager
from exchange.rate_limiter import RateLimiter
from exchange.rest_api import RestApi
from journal.writer import JournalWriter
from monitoring.metrics import MetricsRegistry
from monitoring.telegram_bot import TelegramAlertSink
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager
from strategies.breakout_strategy import BreakoutStrategy
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.funding_rate_arb import FundingRateArbStrategy
from strategies.grid_trading import GridTradingStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum_strategy import MomentumStrategy
from strategies.strategy_selector import StrategySelector
from strategies.trend_following import TrendFollowingStrategy

logger = structlog.get_logger("orchestrator")


class TradingOrchestrator(
    OrchestratorExecutionMixin,
    OrchestratorLoopsMixin,
    OrchestratorCommandsMixin,
):
    def __init__(
        self,
        settings: AppSettings,
        profile: StrategyProfile,
        journal_path: Path | None = None,
    ) -> None:
        self._settings = settings
        self._profile = profile
        self._journal_path = journal_path or Path("journal.db")
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        self._shutdown_event = asyncio.Event()
        self._trading_paused = False
        self._signals_count = 0
        self._trades_count = 0

        self._event_bus: EventBus | None = None
        self._journal: JournalWriter | None = None
        self._client: BybitClient | None = None
        self._rest_api: RestApi | None = None
        self._order_manager: OrderManager | None = None
        self._position_manager: PositionManager | None = None
        self._account_manager: AccountManager | None = None
        self._risk_manager: RiskManager | None = None
        self._portfolio_manager: PortfolioManager | None = None
        self._strategy_selector: StrategySelector | None = None
        self._candle_buffer: CandleBuffer | None = None
        self._preprocessor: CandlePreprocessor | None = None
        self._feature_engineer: FeatureEngineer | None = None
        self._telegram_sink: TelegramAlertSink | None = None
        self._metrics = MetricsRegistry()

        self._periodic_tasks: list[asyncio.Task[None]] = []
        self._symbols: list[str] = []
        today = datetime.now(timezone.utc).date()
        self._last_daily_reset_date = today
        self._last_digest_date = today

    async def start(self) -> None:
        await logger.ainfo("orchestrator_starting", session=self._session_id)

        self._journal = JournalWriter(self._journal_path)
        await self._journal.initialize()

        self._client = BybitClient(self._settings.exchange)
        await self._client.connect()

        rate_limiter = RateLimiter()
        self._rest_api = RestApi(self._client, rate_limiter)
        self._order_manager = OrderManager(self._rest_api)
        self._position_manager = PositionManager(self._rest_api)
        self._account_manager = AccountManager(self._rest_api)

        risk_settings = self._build_risk_settings()
        self._risk_manager = RiskManager(risk_settings)

        balance = await self._account_manager.sync_balance()
        self._risk_manager.initialize(balance.total_equity)
        await logger.ainfo(
            "balance_synced",
            equity=str(balance.total_equity),
            available=str(balance.total_available_balance),
        )

        try:
            await self._position_manager.sync_positions()
            await logger.ainfo("positions_synced", count=self._position_manager.open_position_count)
        except Exception as exc:
            await logger.awarning("positions_sync_failed", error=str(exc))

        self._symbols = get_ccxt_symbols()[:5]
        recovered_symbols = [p.symbol for p in self._position_manager.get_all_positions() if p.size > 0]
        for symbol in recovered_symbols:
            if symbol not in self._symbols:
                self._symbols.append(symbol)
        strategies = [
            EmaCrossoverStrategy(self._symbols),
            MeanReversionStrategy(self._symbols),
            MomentumStrategy(self._symbols),
            TrendFollowingStrategy(self._symbols),
            BreakoutStrategy(self._symbols),
            GridTradingStrategy(self._symbols),
            FundingRateArbStrategy(self._symbols),
        ]
        self._strategy_selector = StrategySelector(strategies)

        self._portfolio_manager = PortfolioManager(
            strategy_names=[s.name for s in strategies],
            total_equity=balance.total_equity,
        )

        self._candle_buffer = CandleBuffer(max_candles=500)
        self._preprocessor = CandlePreprocessor()
        self._feature_engineer = FeatureEngineer()

        for symbol in self._symbols:
            candles = await self._rest_api.fetch_ohlcv(symbol, timeframe="15m", limit=200)
            self._candle_buffer.initialize(symbol, candles)
            await logger.ainfo("candle_buffer_initialized", symbol=symbol, count=len(candles))

        self._event_bus = EventBus()
        await self._event_bus.start()

        await self._setup_telegram()
        self._restore_strategy_states_from_positions()
        await self._reconcile_recovered_positions()

        self._periodic_tasks.append(asyncio.create_task(self._candle_poll_loop()))
        self._periodic_tasks.append(asyncio.create_task(self._balance_poll_loop()))
        self._periodic_tasks.append(asyncio.create_task(self._equity_snapshot_loop()))

        if self._telegram_sink:
            self._periodic_tasks.append(asyncio.create_task(self._telegram_poll_loop()))

        await logger.ainfo("orchestrator_started")

    def _build_risk_settings(self) -> RiskSettings:
        risk_params = profile_to_risk_settings(self._profile)
        guards = self._settings.risk_guards
        risk_params.update(
            {
                "enable_circuit_breaker": guards.enable_circuit_breaker,
                "circuit_breaker_consecutive_losses": guards.circuit_breaker_consecutive_losses,
                "circuit_breaker_cooldown_hours": guards.circuit_breaker_cooldown_hours,
                "enable_daily_loss_limit": guards.enable_daily_loss_limit,
                "max_daily_loss_pct": guards.daily_loss_limit_pct,
                "enable_symbol_cooldown": guards.enable_symbol_cooldown,
                "symbol_cooldown_minutes": guards.symbol_cooldown_minutes,
                "soft_stop_threshold_pct": guards.soft_stop_threshold_pct,
                "soft_stop_min_confidence": guards.soft_stop_min_confidence,
                "portfolio_heat_limit_pct": guards.portfolio_heat_limit_pct,
            }
        )
        return RiskSettings(**risk_params)

    async def _setup_telegram(self) -> None:
        if not self._settings.telegram.enabled:
            return
        token = self._settings.telegram.bot_token.get_secret_value()
        if not token:
            return

        self._telegram_sink = TelegramAlertSink(
            bot_token=token,
            chat_id=self._settings.telegram.chat_id,
        )
        await self._telegram_sink.start()

        self._telegram_sink.register_command("/status", self._cmd_status)
        self._telegram_sink.register_command("/positions", self._cmd_positions)
        self._telegram_sink.register_command("/pnl", self._cmd_pnl)
        self._telegram_sink.register_command("/close_ready", self._cmd_close_ready)
        self._telegram_sink.register_command("/guard", self._cmd_guard)
        self._telegram_sink.register_command("/pause", self._cmd_pause)
        self._telegram_sink.register_command("/resume", self._cmd_resume)
        self._telegram_sink.register_command("/risk", self._cmd_risk)
        self._telegram_sink.register_command("/help", self._cmd_help)

        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        pos_count = self._position_manager.open_position_count if self._position_manager else 0
        startup_msg = (
            f"🤖 *Бот запущен*\n"
            f"Сессия: `{self._session_id}`\n"
            f"Профиль: `{self._profile.name.value}`\n"
            f"Эквити: `{equity:.2f} USDT`\n"
            f"Позиций: `{pos_count}`\n"
            f"Символы: `{', '.join(self._symbols)}`\n\n"
            f"Команды: /help"
        )
        await self._telegram_sink.send_message_now(startup_msg)
        await logger.ainfo("telegram_enabled", chat_id=self._settings.telegram.chat_id)

    async def stop(self) -> None:
        await logger.ainfo("orchestrator_stopping")

        for task in self._periodic_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._telegram_sink:
            equity = self._account_manager.equity if self._account_manager else Decimal(0)
            await self._telegram_sink.send_message_now(
                f"🛑 *Бот остановлен*\n"
                f"Сессия: `{self._session_id}`\n"
                f"Итоговое эквити: `{equity:.2f} USDT`\n"
                f"Сигналы: `{self._signals_count}` | Сделки: `{self._trades_count}`"
            )
            await self._telegram_sink.close()

        if self._event_bus:
            await self._event_bus.stop()

        if self._client:
            await self._client.disconnect()

        if self._journal:
            await self._journal.close()

        await logger.ainfo("orchestrator_stopped")

    async def run(self) -> None:
        await self.start()
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()
