from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class TradeSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class BacktestTrade(BaseModel):
    trade_id: int = 0
    symbol: str = ""
    side: TradeSide = TradeSide.LONG
    entry_price: Decimal = Decimal("0")
    exit_price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    entry_time: int = 0
    exit_time: int = 0
    stop_loss: Decimal = Decimal("0")
    take_profit: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    pnl_pct: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    bars_held: int = 0
    strategy_name: str = ""


class BacktestConfig(BaseModel):
    initial_equity: Decimal = Decimal("10000")
    maker_fee: Decimal = Decimal("0.0001")
    taker_fee: Decimal = Decimal("0.0006")
    slippage_pct: Decimal = Decimal("0.0005")
    use_limit_orders: bool = False
    risk_per_trade: Decimal = Decimal("0.02")
    max_leverage: Decimal = Decimal("3.0")
    max_positions: int = 1
    timeframe: str = "15m"


class EquityCurvePoint(BaseModel):
    timestamp: int = 0
    equity: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")
    open_positions: int = 0


class PerformanceMetrics(BaseModel):
    total_return_pct: Decimal = Decimal("0")
    annualized_return_pct: Decimal = Decimal("0")
    sharpe_ratio: Decimal = Decimal("0")
    sortino_ratio: Decimal = Decimal("0")
    calmar_ratio: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    max_drawdown_duration_bars: int = 0
    win_rate: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    avg_win_loss_ratio: Decimal = Decimal("0")
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_bars_held: Decimal = Decimal("0")
    total_commission: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    expectancy: Decimal = Decimal("0")
    kelly_pct: Decimal = Decimal("0")


class BacktestResult(BaseModel):
    config: BacktestConfig = Field(default_factory=BacktestConfig)
    metrics: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    trades: list[BacktestTrade] = Field(default_factory=list)
    equity_curve: list[EquityCurvePoint] = Field(default_factory=list)
    final_equity: Decimal = Decimal("0")
    strategy_name: str = ""
    symbol: str = ""
    start_time: int = 0
    end_time: int = 0
