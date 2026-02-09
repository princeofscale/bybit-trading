import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import structlog

from config.settings import AppSettings, RiskSettings
from config.strategy_profiles import StrategyProfile, profile_to_risk_settings
from config.trading_pairs import get_ccxt_symbols
from core.candle_buffer import CandleBuffer
from core.event_bus import EventBus, EventType
from data.feature_engineer import FeatureEngineer
from data.preprocessor import CandlePreprocessor
from exchange.account_manager import AccountManager
from exchange.bybit_client import BybitClient
from exchange.models import OrderRequest
from exchange.order_manager import OrderManager
from exchange.position_manager import PositionManager
from exchange.rest_api import RestApi
from exchange.rate_limiter import RateLimiter
from journal.writer import JournalWriter
from monitoring.alerts import AlertManager
from monitoring.health_check import HealthChecker
from monitoring.metrics import MetricsRegistry
from monitoring.telegram_bot import TelegramAlertSink, TelegramFormatter
from portfolio.portfolio_manager import PortfolioManager
from risk.risk_manager import RiskManager
from strategies.base_strategy import SignalDirection
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum_strategy import MomentumStrategy
from strategies.trend_following import TrendFollowingStrategy
from strategies.breakout_strategy import BreakoutStrategy
from strategies.grid_trading import GridTradingStrategy
from strategies.funding_rate_arb import FundingRateArbStrategy
from strategies.strategy_selector import StrategySelector
from data.models import OrderSide, OrderType

logger = structlog.get_logger("orchestrator")


class TradingOrchestrator:
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

        self._periodic_tasks: list[asyncio.Task[None]] = []
        self._symbols: list[str] = []

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

        risk_params = profile_to_risk_settings(self._profile)
        risk_settings = RiskSettings(**risk_params)
        self._risk_manager = RiskManager(risk_settings)

        balance = await self._account_manager.sync_balance()
        self._risk_manager.initialize(balance.total_equity)
        await logger.ainfo("balance_synced", equity=str(balance.total_equity), available=str(balance.total_available_balance))

        await self._position_manager.sync_positions()
        await logger.ainfo("positions_synced", count=self._position_manager.open_position_count)

        self._symbols = get_ccxt_symbols()[:5]
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

        strategy_names = [s.name for s in strategies]
        self._portfolio_manager = PortfolioManager(
            strategy_names=strategy_names,
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

        self._periodic_tasks.append(asyncio.create_task(self._candle_poll_loop()))
        self._periodic_tasks.append(asyncio.create_task(self._balance_poll_loop()))
        self._periodic_tasks.append(asyncio.create_task(self._equity_snapshot_loop()))

        if self._telegram_sink:
            self._periodic_tasks.append(asyncio.create_task(self._telegram_poll_loop()))

        await logger.ainfo("orchestrator_started")

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
        self._telegram_sink.register_command("/pause", self._cmd_pause)
        self._telegram_sink.register_command("/resume", self._cmd_resume)
        self._telegram_sink.register_command("/risk", self._cmd_risk)
        self._telegram_sink.register_command("/help", self._cmd_help)

        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        pos_count = self._position_manager.open_position_count if self._position_manager else 0
        startup_msg = (
            f"🤖 *Bot Started*\n"
            f"Session: `{self._session_id}`\n"
            f"Profile: `{self._profile.name.value}`\n"
            f"Equity: `{equity:.2f} USDT`\n"
            f"Positions: `{pos_count}`\n"
            f"Symbols: `{', '.join(self._symbols)}`\n\n"
            f"Type /help for commands"
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
                f"🛑 *Bot Stopped*\n"
                f"Session: `{self._session_id}`\n"
                f"Final equity: `{equity:.2f} USDT`\n"
                f"Signals: `{self._signals_count}` | Trades: `{self._trades_count}`"
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

    async def _candle_poll_loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                for symbol in self._symbols:
                    await self._poll_and_analyze(symbol)
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("candle_poll_error", error=str(exc))
                await asyncio.sleep(30)

    async def _poll_and_analyze(self, symbol: str) -> None:
        if self._trading_paused or not self._rest_api or not self._candle_buffer:
            return

        candles = await self._rest_api.fetch_ohlcv(symbol, timeframe="15m", limit=5)
        if not candles:
            return

        for candle in candles:
            self._candle_buffer.update(symbol, candle)

        if not self._candle_buffer.has_enough(symbol, 60):
            return

        all_candles = self._candle_buffer.get_candles(symbol)
        df = self._preprocessor.candles_to_dataframe(all_candles)
        df = self._feature_engineer.build_features(df)

        signal = self._strategy_selector.get_best_signal(symbol, df)
        if not signal:
            return

        self._signals_count += 1
        await logger.ainfo(
            "signal_generated",
            symbol=signal.symbol,
            direction=signal.direction.value,
            strategy=signal.strategy_name,
            confidence=signal.confidence,
        )

        positions = self._position_manager.get_all_positions() if self._position_manager else []
        equity = self._account_manager.equity if self._account_manager else Decimal(0)

        decision = self._risk_manager.evaluate_signal(signal, equity, positions)

        if self._journal:
            await self._journal.log_signal(
                timestamp=datetime.now(timezone.utc),
                symbol=signal.symbol,
                direction=signal.direction.value,
                confidence=signal.confidence,
                strategy_name=signal.strategy_name,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                approved=decision.approved,
                rejection_reason=decision.reason if not decision.approved else "",
                session_id=self._session_id,
            )

        if not decision.approved:
            await logger.ainfo("signal_rejected", symbol=signal.symbol, reason=decision.reason)
            return

        order_side = OrderSide.BUY if signal.direction == SignalDirection.LONG else OrderSide.SELL
        reduce_only = signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT)

        request = OrderRequest(
            symbol=signal.symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            quantity=decision.quantity,
            reduce_only=reduce_only,
        )

        try:
            in_flight = await self._order_manager.submit_order(request, signal.strategy_name)
            self._trades_count += 1

            await logger.ainfo(
                "order_submitted",
                symbol=signal.symbol,
                side=order_side.value,
                quantity=str(decision.quantity),
                strategy=signal.strategy_name,
            )

            if self._telegram_sink:
                await self._telegram_sink.send_message_now(
                    TelegramFormatter.format_trade_opened(
                        symbol=signal.symbol,
                        side=signal.direction.value,
                        size=decision.quantity,
                        entry_price=signal.entry_price or Decimal(0),
                        stop_loss=signal.stop_loss or Decimal(0),
                        take_profit=signal.take_profit or Decimal(0),
                        strategy=signal.strategy_name,
                    )
                )
        except Exception as exc:
            await logger.aerror("order_failed", symbol=signal.symbol, error=str(exc))
            if self._telegram_sink:
                await self._telegram_sink.send_message_now(
                    f"🔴 *Order Failed*\n"
                    f"Symbol: `{signal.symbol}`\n"
                    f"Error: `{str(exc)[:200]}`"
                )

    async def _balance_poll_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(120)
                if self._account_manager and self._risk_manager:
                    balance = await self._account_manager.sync_balance()
                    halt = self._risk_manager.update_equity(balance.total_equity)
                    if halt:
                        self._trading_paused = True
                        await logger.awarning("trading_halted_drawdown")
                        if self._telegram_sink:
                            dd = self._account_manager.current_drawdown_pct
                            await self._telegram_sink.send_message_now(
                                TelegramFormatter.format_risk_alert(
                                    reason="Max drawdown exceeded",
                                    current_drawdown=dd,
                                    max_drawdown=self._risk_manager._settings.max_drawdown_pct,
                                )
                            )
                if self._position_manager:
                    await self._position_manager.sync_positions()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("balance_poll_error", error=str(exc))

    async def _equity_snapshot_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(300)
                if not self._account_manager or not self._journal or not self._position_manager:
                    continue
                balance = self._account_manager.balance
                if not balance:
                    continue
                await self._journal.log_equity_snapshot(
                    timestamp=datetime.now(timezone.utc),
                    total_equity=balance.total_equity,
                    available_balance=balance.total_available_balance,
                    unrealized_pnl=balance.total_unrealized_pnl,
                    open_position_count=self._position_manager.open_position_count,
                    peak_equity=self._account_manager.peak_equity,
                    drawdown_pct=self._account_manager.current_drawdown_pct,
                    session_id=self._session_id,
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("equity_snapshot_error", error=str(exc))

    async def _telegram_poll_loop(self) -> None:
        await asyncio.sleep(3)
        while True:
            try:
                await self._telegram_sink.poll_and_handle()
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("telegram_poll_error", error=str(exc))
                await asyncio.sleep(10)

    async def _cmd_status(self) -> str:
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        pos_count = self._position_manager.open_position_count if self._position_manager else 0
        state = "PAUSED" if self._trading_paused else "RUNNING"
        strategies = list(self._strategy_selector.strategies.keys()) if self._strategy_selector else []
        return TelegramFormatter.format_status(
            bot_state=state,
            equity=equity,
            open_positions=pos_count,
            daily_pnl=Decimal(0),
            active_strategies=strategies,
            session_id=self._session_id,
            signals_count=self._signals_count,
            trades_count=self._trades_count,
        )

    async def _cmd_positions(self) -> str:
        if not self._position_manager:
            return "No position manager available."
        positions = self._position_manager.get_all_positions()
        pos_data = [
            {
                "symbol": p.symbol,
                "side": p.side.value if hasattr(p.side, 'value') else str(p.side),
                "size": p.size,
                "entry": p.entry_price,
                "pnl": p.unrealized_pnl,
            }
            for p in positions if p.size > 0
        ]
        return TelegramFormatter.format_positions(pos_data)

    async def _cmd_pnl(self) -> str:
        equity = self._account_manager.equity if self._account_manager else Decimal(0)
        peak = self._account_manager.peak_equity if self._account_manager else Decimal(0)
        dd = self._account_manager.current_drawdown_pct if self._account_manager else Decimal(0)
        return (
            f"💰 *PnL Summary*\n"
            f"Current equity: `{equity:.2f} USDT`\n"
            f"Peak equity: `{peak:.2f} USDT`\n"
            f"Drawdown: `{dd * 100:.2f}%`\n"
            f"Signals: `{self._signals_count}`\n"
            f"Trades: `{self._trades_count}`"
        )

    async def _cmd_pause(self) -> str:
        self._trading_paused = True
        return "⏸ Trading *PAUSED*. Use /resume to continue."

    async def _cmd_resume(self) -> str:
        self._trading_paused = False
        return "▶️ Trading *RESUMED*."

    async def _cmd_risk(self) -> str:
        if not self._risk_manager:
            return "Risk manager not available."
        s = self._risk_manager._settings
        dd = self._account_manager.current_drawdown_pct if self._account_manager else Decimal(0)
        return (
            f"🛡 *Risk Settings*\n"
            f"Max risk/trade: `{s.max_risk_per_trade * 100:.1f}%`\n"
            f"Max portfolio risk: `{s.max_portfolio_risk * 100:.1f}%`\n"
            f"Max drawdown: `{s.max_drawdown_pct * 100:.1f}%`\n"
            f"Current drawdown: `{dd * 100:.2f}%`\n"
            f"Max leverage: `{s.max_leverage}x`\n"
            f"Max positions: `{s.max_concurrent_positions}`\n"
            f"Circuit breaker: `{s.circuit_breaker_consecutive_losses} losses → {s.circuit_breaker_cooldown_hours}h pause`\n"
            f"Trading paused: `{'YES' if self._trading_paused else 'NO'}`"
        )

    async def _cmd_help(self) -> str:
        return TelegramFormatter.format_help()
