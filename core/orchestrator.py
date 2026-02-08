import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import structlog

from config.settings import AppSettings, RiskSettings
from config.strategy_profiles import StrategyProfile, profile_to_risk_settings
from config.trading_pairs import get_ccxt_symbols
from core.candle_buffer import CandleBuffer
from core.event_bus import Event, EventBus, EventType
from data.feature_engineer import FeatureEngineer
from data.preprocessor import CandlePreprocessor
from exchange.account_manager import AccountManager
from exchange.bybit_client import BybitClient
from exchange.models import Candle, OrderRequest, OrderResult, Position
from exchange.order_manager import OrderManager
from exchange.position_manager import PositionManager
from exchange.rest_api import RestApi
from exchange.rate_limiter import RateLimiter
from exchange.websocket_manager import WebSocketManager
from journal.writer import JournalWriter
from monitoring.alerts import AlertManager
from monitoring.health_check import HealthChecker
from monitoring.metrics import MetricsRegistry
from monitoring.telegram_bot import TelegramAlertSink
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
from data.models import OrderSide, OrderType, OrderStatus

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

        self._event_bus: EventBus | None = None
        self._journal: JournalWriter | None = None
        self._client: BybitClient | None = None
        self._rest_api: RestApi | None = None
        self._ws_manager: WebSocketManager | None = None
        self._order_manager: OrderManager | None = None
        self._position_manager: PositionManager | None = None
        self._account_manager: AccountManager | None = None
        self._risk_manager: RiskManager | None = None
        self._portfolio_manager: PortfolioManager | None = None
        self._strategy_selector: StrategySelector | None = None
        self._candle_buffer: CandleBuffer | None = None
        self._preprocessor: CandlePreprocessor | None = None
        self._feature_engineer: FeatureEngineer | None = None
        self._metrics: MetricsRegistry | None = None
        self._health_checker: HealthChecker | None = None
        self._alert_manager: AlertManager | None = None
        self._telegram_sink: TelegramAlertSink | None = None

        self._periodic_tasks: list[asyncio.Task[None]] = []
        self._order_signals: dict[str, dict[str, str | Decimal]] = {}

    async def start(self) -> None:
        await logger.ainfo("orchestrator_starting", session=self._session_id)

        self._journal = JournalWriter(self._journal_path)
        await self._journal.initialize()
        await self._journal.log_system_event(
            timestamp=datetime.now(timezone.utc),
            event_type="system_start",
            message="Trading bot started",
            metadata={"profile": self._profile.name.value},
            session_id=self._session_id,
        )

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

        await self._position_manager.sync_positions()

        symbols = get_ccxt_symbols()
        strategies = [
            EmaCrossoverStrategy(symbols),
            MeanReversionStrategy(symbols),
            MomentumStrategy(symbols),
            TrendFollowingStrategy(symbols),
            BreakoutStrategy(symbols),
            GridTradingStrategy(symbols),
            FundingRateArbStrategy(symbols),
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

        self._metrics = MetricsRegistry()
        self._health_checker = HealthChecker()
        self._alert_manager = AlertManager()

        if self._settings.telegram.enabled and self._settings.telegram.bot_token.get_secret_value():
            self._telegram_sink = TelegramAlertSink(
                bot_token=self._settings.telegram.bot_token.get_secret_value(),
                chat_id=self._settings.telegram.chat_id,
            )
            await logger.ainfo("telegram_notifications_enabled", chat_id=self._settings.telegram.chat_id)

        for symbol in symbols[:5]:
            candles = await self._rest_api.fetch_ohlcv(
                symbol, timeframe="15m", limit=200,
            )
            self._candle_buffer.initialize(symbol, candles)

        self._event_bus = EventBus()
        await self._event_bus.start()

        self._event_bus.subscribe(EventType.KLINE, self._on_kline)
        self._event_bus.subscribe(EventType.ORDER_FILLED, self._on_order_update)
        self._event_bus.subscribe(EventType.ORDER_PARTIALLY_FILLED, self._on_order_update)
        self._event_bus.subscribe(EventType.POSITION_UPDATED, self._on_position_update)
        self._event_bus.subscribe(EventType.PORTFOLIO_UPDATE, self._on_balance_update)

        self._ws_manager = WebSocketManager(self._client, self._event_bus)
        await self._ws_manager.start()

        for symbol in symbols[:5]:
            self._ws_manager.subscribe_ohlcv(symbol, "15m")

        self._ws_manager.subscribe_orders()
        self._ws_manager.subscribe_positions()
        self._ws_manager.subscribe_balance()

        self._periodic_tasks.append(
            asyncio.create_task(self._periodic_equity_snapshot()),
        )
        self._periodic_tasks.append(
            asyncio.create_task(self._periodic_health_check()),
        )

        await logger.ainfo("orchestrator_started")

    async def stop(self) -> None:
        await logger.ainfo("orchestrator_stopping")

        for task in self._periodic_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._ws_manager:
            await self._ws_manager.stop()

        if self._event_bus:
            await self._event_bus.stop()

        if self._client:
            await self._client.disconnect()

        if self._journal:
            await self._journal.log_system_event(
                timestamp=datetime.now(timezone.utc),
                event_type="system_stop",
                message="Trading bot stopped",
                metadata={},
                session_id=self._session_id,
            )
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

    async def _on_kline(self, event: Event) -> None:
        if self._trading_paused:
            return

        symbol = event.payload["symbol"]
        data = event.payload["data"]

        if not data or len(data) == 0:
            return

        candle_data = data[-1] if isinstance(data, list) else data
        candle = self._parse_candle(symbol, candle_data)

        if not self._candle_buffer:
            return

        self._candle_buffer.update(symbol, candle)

        if not self._candle_buffer.has_enough(symbol, 60):
            return

        candles = self._candle_buffer.get_candles(symbol)
        if not self._preprocessor or not self._feature_engineer:
            return

        df = self._preprocessor.candles_to_dataframe(candles)
        df = self._feature_engineer.build_features(df)

        if not self._strategy_selector:
            return

        signal = self._strategy_selector.get_best_signal(symbol, df)
        if not signal:
            return

        if not self._journal or not self._risk_manager or not self._order_manager:
            return

        positions = self._position_manager.get_all_positions() if self._position_manager else []
        equity = self._account_manager.equity if self._account_manager else Decimal("0")

        decision = self._risk_manager.evaluate_signal(signal, equity, positions)

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
            return

        order_side, reduce_only = self._signal_to_order_params(signal.direction)

        request = OrderRequest(
            symbol=signal.symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            quantity=decision.quantity,
            reduce_only=reduce_only,
        )

        in_flight = await self._order_manager.submit_order(request, signal.strategy_name)

        self._order_signals[in_flight.client_order_id] = {
            "strategy_name": signal.strategy_name,
            "direction": signal.direction.value,
            "entry_price": signal.entry_price or Decimal("0"),
        }

    async def _on_order_update(self, event: Event) -> None:
        if not self._order_manager or not self._journal:
            return

        data = event.payload.get("data", {})
        order_result = self._parse_order_result(data)

        self._order_manager.update_from_exchange(order_result)

        await self._journal.log_order(
            timestamp=datetime.now(timezone.utc),
            client_order_id=order_result.client_order_id,
            exchange_order_id=order_result.order_id,
            symbol=order_result.symbol,
            side=order_result.side.value,
            order_type=order_result.order_type.value,
            quantity=order_result.quantity,
            price=order_result.price,
            avg_fill_price=order_result.avg_fill_price,
            filled_qty=order_result.filled_qty,
            status=order_result.status.value,
            strategy_name=self._order_signals.get(order_result.client_order_id, {}).get("strategy_name", ""),
            fee=order_result.fee,
            session_id=self._session_id,
        )

        if order_result.status == OrderStatus.FILLED:
            signal_data = self._order_signals.get(order_result.client_order_id, {})
            if signal_data and self._portfolio_manager and self._risk_manager:
                direction = str(signal_data.get("direction", ""))
                is_opening = direction in ("long", "short")
                is_closing = direction in ("close_long", "close_short")

                if is_opening and self._telegram_sink:
                    await self._telegram_sink.send_message_now(
                        self._telegram_sink._formatter.format_trade_opened(
                            symbol=order_result.symbol,
                            side=direction,
                            size=order_result.filled_qty,
                            entry=order_result.avg_fill_price or Decimal("0"),
                            sl=Decimal("0"),
                            tp=Decimal("0"),
                            strategy=str(signal_data.get("strategy_name", "")),
                        )
                    )

                if is_closing and self._telegram_sink:
                    pnl = Decimal("100")
                    pnl_pct = Decimal("0.02")
                    is_win = pnl > 0

                    await self._telegram_sink.send_message_now(
                        self._telegram_sink._formatter.format_trade_closed(
                            symbol=order_result.symbol,
                            side="long" if direction == "close_long" else "short",
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            entry=signal_data.get("entry_price", Decimal("0")),
                            exit_price=order_result.avg_fill_price or Decimal("0"),
                            strategy=str(signal_data.get("strategy_name", "")),
                        )
                    )

                    self._portfolio_manager.record_trade(
                        str(signal_data.get("strategy_name", "")),
                        pnl_pct,
                    )
                    self._risk_manager.record_trade_result(is_win)

    async def _on_position_update(self, event: Event) -> None:
        if not self._position_manager:
            return

        data = event.payload.get("data", {})
        position = self._parse_position(data)
        self._position_manager.update_position(position)

    async def _on_balance_update(self, event: Event) -> None:
        if not self._account_manager or not self._risk_manager:
            return

        if not self._account_manager.balance:
            return

        new_equity = self._account_manager.balance.total_equity
        halt_triggered = self._risk_manager.update_equity(new_equity)

        if halt_triggered and self._journal:
            drawdown_pct = self._account_manager.current_drawdown_pct

            await self._journal.log_risk_event(
                timestamp=datetime.now(timezone.utc),
                event_type="drawdown_halt",
                reason="Max drawdown exceeded",
                equity_at_event=new_equity,
                drawdown_pct=drawdown_pct,
                session_id=self._session_id,
            )

            self._trading_paused = True
            await logger.awarning("trading_paused", reason="drawdown_halt")

            if self._telegram_sink and self._risk_manager:
                await self._telegram_sink.send_message_now(
                    self._telegram_sink._formatter.format_risk_alert(
                        reason="Max drawdown exceeded - trading halted",
                        current_drawdown=drawdown_pct,
                        max_drawdown=self._risk_manager._settings.max_drawdown_pct,
                    )
                )

    async def _periodic_equity_snapshot(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)

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

    async def _periodic_health_check(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)

                if self._health_checker:
                    health = self._health_checker.get_system_health()
                    await logger.ainfo("health_check", status=health.overall.value)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("health_check_error", error=str(exc))

    def _signal_to_order_params(self, direction: SignalDirection) -> tuple[OrderSide, bool]:
        if direction == SignalDirection.LONG:
            return OrderSide.BUY, False
        elif direction == SignalDirection.SHORT:
            return OrderSide.SELL, False
        elif direction == SignalDirection.CLOSE_LONG:
            return OrderSide.SELL, True
        elif direction == SignalDirection.CLOSE_SHORT:
            return OrderSide.BUY, True
        return OrderSide.BUY, False

    def _parse_candle(self, symbol: str, data: list[int | float] | dict[str, int | float]) -> Candle:
        if isinstance(data, list):
            return Candle(
                symbol=symbol,
                timeframe="15m",
                open_time=int(data[0]),
                open=Decimal(str(data[1])),
                high=Decimal(str(data[2])),
                low=Decimal(str(data[3])),
                close=Decimal(str(data[4])),
                volume=Decimal(str(data[5])),
            )
        return Candle(
            symbol=symbol,
            timeframe="15m",
            open_time=int(data.get("timestamp", 0)),
            open=Decimal(str(data.get("open", 0))),
            high=Decimal(str(data.get("high", 0))),
            low=Decimal(str(data.get("low", 0))),
            close=Decimal(str(data.get("close", 0))),
            volume=Decimal(str(data.get("volume", 0))),
        )

    def _parse_order_result(self, data: dict[str, str | int | float]) -> OrderResult:
        return OrderResult(
            order_id=str(data.get("id", "")),
            client_order_id=str(data.get("clientOrderId", "")),
            symbol=str(data.get("symbol", "")),
            side=OrderSide.BUY if data.get("side") == "buy" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal(str(data.get("amount", 0))),
            filled_qty=Decimal(str(data.get("filled", 0))),
            status=OrderStatus.FILLED if data.get("status") == "closed" else OrderStatus.NEW,
            fee=Decimal(str(data.get("fee", {}).get("cost", 0) if isinstance(data.get("fee"), dict) else 0)),
        )

    def _parse_position(self, data: dict[str, str | int | float]) -> Position:
        from data.models import PositionSide

        side_str = str(data.get("side", ""))
        side = PositionSide.LONG if side_str == "long" else PositionSide.SHORT if side_str == "short" else PositionSide.NONE

        return Position(
            symbol=str(data.get("symbol", "")),
            side=side,
            size=Decimal(str(data.get("contracts", 0))),
            entry_price=Decimal(str(data.get("entryPrice", 0))),
            unrealized_pnl=Decimal(str(data.get("unrealizedPnl", 0))),
        )
