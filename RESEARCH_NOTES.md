# Phase 0: Research Notes

## 1. Technology Stack Decisions

### Primary Exchange Library: ccxt (over pybit)

| Factor | ccxt | pybit |
|--------|------|-------|
| Async support | Native via `ccxt.async_support` | None (sync only) |
| WebSocket | `ccxt.pro` with async loop pattern (`watch_*`) | Callback-based |
| Rate limiting | Built-in (`enableRateLimit=True`) | Not built-in |
| Error handling | Rich hierarchy (10+ exception types) | Two types + retCode |
| Multi-exchange | 100+ exchanges | Bybit only |
| Parameters | Numeric (float/int) | Strings |

**Decision**: ccxt as primary library. pybit as fallback for Bybit-specific features not cleanly exposed through ccxt.

**Architecture implication**: Exchange layer uses adapter/interface pattern:
```
ExchangeInterface (abstract)
    +-- CcxtBybitAdapter (primary)
    +-- PybitAdapter (fallback/testing)
```

### ccxt Key Patterns
- Symbol format: `BTC/USDT:USDT` (USDT perp), `BTC/USD:BTC` (inverse), `BTC/USDT` (spot)
- Must call `await exchange.close()` in `finally` block
- `load_markets()` expensive — cache and refresh hourly
- `sandbox=True` for testnet
- SL/TP via `params` dict with `stopLoss`/`takeProfit` sub-dicts
- Hedge mode requires `positionIdx` in `params`

### Infrastructure Stack

| Component | Library | Version | Justification |
|-----------|---------|---------|---------------|
| Web framework | FastAPI | >=0.115 | Native async, WebSocket, dependency injection, Pydantic integration |
| Database ORM | SQLAlchemy 2.0 | >=2.0.30 | Async with asyncpg, type-safe Mapped[] syntax, mature ecosystem |
| DB driver | asyncpg | >=0.29 | Native async PostgreSQL driver, C implementation |
| Validation | Pydantic v2 | >=2.7 | Rust core (5-50x faster than v1), BaseSettings for config |
| Config | pydantic-settings | >=2.3 | env_prefix, .env files, SecretStr for API keys |
| Migrations | Alembic | >=1.13 | Async support via run_sync wrapper |
| Technical analysis | pandas-ta | 0.3.x | 130+ indicators, Strategy builder, DataFrame accessor |
| Backtesting | vectorbt | 0.26.x | Vectorized (fast), Portfolio.from_signals(), parameter sweeps |
| ML (primary) | XGBoost | 2.x | predict_proba for confidence, native NaN handling, regularization |
| ML (secondary) | LightGBM | 4.x | Faster training, native categorical support, leaf-wise growth |
| Hyperparameter opt | Optuna | 3.x | TPE sampler, pruning callbacks for XGB/LGBM, multi-objective |
| ML utilities | scikit-learn | >=1.4 | TimeSeriesSplit, Pipeline, ColumnTransformer, metrics |
| Server | uvicorn | >=0.30 | ASGI server for FastAPI |

### Database Strategy
- **PostgreSQL + TimescaleDB** for historical OHLCV, funding rates, open interest
- **Redis** for hot data cache (latest candles, orderbook state, positions)
- **Composite indexes** on `(symbol, timeframe, open_time)` for candle queries
- **Upsert pattern** (`ON CONFLICT DO UPDATE`) for idempotent candle ingestion
- **Table partitioning** by month for large candle tables
- **SQLAlchemy async**: `expire_on_commit=False`, `selectin` loading (no lazy loading in async)

---

## 2. Bybit API v5 Key Findings

### Base URLs

| Environment | REST | WebSocket Public | WebSocket Private |
|-------------|------|-------------------|-------------------|
| Mainnet | `https://api.bybit.com` | `wss://stream.bybit.com/v5/public/{category}` | `wss://stream.bybit.com/v5/private` |
| Testnet | `https://api-testnet.bybit.com` | `wss://stream-testnet.bybit.com/v5/public/{category}` | `wss://stream-testnet.bybit.com/v5/private` |

### Unified Trading Account (UTA)
- Single collateral pool across spot, perps, futures, options
- Cross-collateral with weights: USDT=1.0, BTC=0.95, ETH=0.95
- Portfolio margin mode available (>1000 USDT equiv) — nets hedged positions
- Use `accountType: "UNIFIED"` for all wallet queries

### Position Modes
- **One-way** (`positionIdx=0`): Single position per symbol, simpler
- **Hedge** (`positionIdx=1/2`): Simultaneous long+short, required for funding arb
- Cannot switch while positions/orders are open

### Rate Limits
- Per-UID per-endpoint, not per-IP (except market data)
- Order placement: 10 req/s per symbol (linear)
- Batch orders: up to 10 orders in 1 request, counts as 1 rate limit hit
- Headers: `X-Bapi-Limit-Status` (remaining), `X-Bapi-Limit-Reset-Timestamp`
- WebSocket Trade endpoint (`/v5/trade`) for lowest latency order ops

### WebSocket Management
- Ping every 20 seconds (`{"op": "ping"}`) or connection drops after 30s
- Max ~300 topics per connection
- Orderbook: snapshot first, then deltas — validate `delta.u == prev.u + 1`
- Kline `confirm` field: `true` = candle closed, `false` = still forming

### Critical Implementation Details
- **Precision**: Query `GET /v5/market/instruments-info` on startup, cache `lotSizeFilter` and `priceFilter`
- **Idempotency**: Always use `orderLinkId` (client UUID) on every order
- **Clock sync**: Periodically call `GET /v5/market/time`, maintain offset
- **Error categorization**: Retryable (10006 rate limit, 5xx, timeout) vs non-retryable (10001 params, 110007 balance)
- **Funding rate**: Every 8h at 00:00/08:00/16:00 UTC, queryable in advance via tickers
- **PostOnly orders**: Guarantee maker fee (0.01% vs 0.06% taker on derivs)

### Key Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 10001 | Invalid parameter | Check precision |
| 10002 | Invalid timestamp | Sync clock |
| 10006 | Rate limit exceeded | Backoff + retry |
| 110007 | Insufficient balance | Check before order |
| 110013 | Position mode mismatch | Check positionIdx |
| 170131/132 | Qty/price precision error | Use instruments-info |

---

## 3. Architecture Lessons from Open-Source Bots

### Projects Studied
- **freqtrade** (~30k stars) — most popular, polling-based, DataFrame strategies
- **hummingbot** (~8k stars) — market making, full async, connector pattern
- **jesse-ai** (~6k stars) — cleanest strategy interface, PostgreSQL storage

### Key Pattern Analysis

| Aspect | freqtrade | hummingbot | jesse | Our approach |
|--------|-----------|------------|-------|-------------|
| Core pattern | Polling loop | Clock-tick + async | Event-candle hybrid | Event-driven + async |
| Strategy interface | DataFrame columns | Tick callbacks | Lifecycle methods | Lifecycle + confidence scores |
| Data storage | Feather files | In-memory | PostgreSQL | TimescaleDB + Redis |
| Risk management | Plugin system | Strategy-dependent | Mandatory SL | 5-layer system |
| Configuration | JSON + schema | YAML + CLI | .env + Python | Pydantic Settings |
| Exchange abstraction | Wraps ccxt | Per-exchange dirs | Internal simulated | Adapter pattern |

### Patterns to Adopt

**From freqtrade:**
- Protection/plugin system for risk management (StoplossGuard, CooldownPeriod, MaxDrawdown)
- Hyperopt integration with Optuna for parameter optimization
- Resolver pattern for dynamically loading strategies
- Comprehensive configuration validation

**From hummingbot:**
- `InFlightOrder` pattern — tracks orders between placement and confirmation
- `TradingRule` objects — encapsulate exchange constraints (tick size, lot size, min notional)
- Full async architecture with asyncio
- Per-exchange connector with consistent internal structure

**From jesse:**
- Strategy lifecycle: `should_long()`, `go_long()`, `update_position()`
- Mandatory stop-loss at entry (enforced by framework)
- `risk_to_qty()` utility for position sizing
- PostgreSQL for candle storage with warm-up candle loading

### Patterns to Avoid

1. **Freqtrade's DataFrame-only strategy model** — awkward for stateful strategies
2. **Hummingbot's Cython dependency** — unnecessary complexity, not doing HFT
3. **Jesse's tight coupling to internal exchange** — use abstraction from start
4. **All three: lack of portfolio-level risk management** — biggest gap to fill
5. **Freqtrade's monolithic FreqtradeBot class** — use proper event-driven decoupling
6. **Hardcoded assumptions** (one position per pair, one strategy per bot)

### Our Strategy Interface Design

```
BaseStrategy (abstract)
    generate_signal(market_data) -> Signal (with confidence 0.0-1.0)
    calculate_entry(signal) -> OrderParams (including SL/TP)
    update_position(position, market_data) -> Optional[OrderParams]
    should_exit(position, market_data) -> bool
```

### Our 5-Layer Risk System (differentiator)

1. **Order level**: Position limits, leverage limits, balance validation
2. **Position level**: Mandatory stop-loss, trailing stop optional
3. **Strategy level**: Per-strategy drawdown limits, cooldown after consecutive losses
4. **Portfolio level**: Total exposure, correlation-based risk budgeting, max drawdown circuit breaker
5. **System level**: Daily loss limit, kill switch, health monitoring

---

## 4. ML Pipeline Architecture

### Full Pipeline Flow

```
pandas-ta → scikit-learn → XGBoost/LightGBM → Optuna → vectorbt
    |              |                |              |           |
 Indicators   TimeSeriesSplit   predict_proba   Optimize   Backtest
 130+ avail   Walk-forward CV   Confidence      HPO        Sharpe/DD
 Strategy()   Pipeline          Feature imp     Prune      Equity curve
```

### Key ML Decisions

1. **Walk-forward validation is mandatory** — standard CV will leak future data
2. **Use sliding window** (not expanding) — markets change, old data may hurt
3. **predict_proba for confidence** — higher confidence = larger position size
4. **Feature engineering is 80% of the work** — technical, volume, cross-asset features
5. **Start with XGBoost/LightGBM** — not deep learning
6. **Retrain weekly/bi-weekly** — not too frequently
7. **60%+ OOS accuracy is excellent** for financial prediction
8. **Optuna + walk-forward** — objective function uses walk-forward internally

### Custom SlidingWindowSplit Required
scikit-learn's `TimeSeriesSplit` uses expanding window (growing train set). For financial data, fixed-size sliding window is preferable. Must implement custom splitter with configurable `train_size`, `test_size`, `gap`, `step`.

### Vectorbt Limitations
- Not event-driven — cannot model limit order fills, orderbook-dependent logic
- No built-in walk-forward — must implement manually
- Memory-heavy with many parameter combinations
- Good for signal-based strategy validation, not for full execution simulation

---

## 5. FastAPI Dashboard Architecture

### Real-time Data Flow

```
Event Bus → ConnectionManager → WebSocket clients (dashboard)
    |
    +-- portfolio_update → broadcast P&L, equity
    +-- order_filled → broadcast order status
    +-- risk_alert → broadcast warnings
```

### Key Patterns
- `lifespan` context manager for startup/shutdown (not deprecated `on_event`)
- `Depends()` for injecting DB sessions, trading engine, auth
- `ConnectionManager` class for WebSocket broadcast
- `BackgroundTasks` for non-critical work (alerts, logging) — NOT for trading engine loop
- `asyncio.create_task()` for the main trading engine event loop in lifespan

### Pydantic Settings as Single Source of Truth
```
AppSettings
    +-- ExchangeSettings (BYBIT_ prefix, SecretStr for keys)
    +-- DatabaseSettings (DB_ prefix, async_url property)
    +-- RiskSettings (RISK_ prefix, all non-negotiable defaults)
    +-- RedisSettings (REDIS_ prefix)
```
- Switching testnet↔mainnet: `BYBIT_TESTNET=false`
- All secrets via `SecretStr` — hidden from logs and repr
- `.env` file support built in

---

## 6. Implementation Priority

Based on all research, the optimal build order:

1. **Foundation** (config, logging, event bus, DB) — enables everything else
2. **Exchange connectivity** (REST + WebSocket with reconnection) — must be rock-solid
3. **Risk management** — capital preservation before any trading logic
4. **Simplest strategy** (EMA crossover) — validates entire pipeline end-to-end
5. **Backtesting** — validates strategy logic without risking capital
6. **Data pipeline** — historical collection, feature engineering
7. **More strategies** — RSI mean reversion, momentum, funding rate arb
8. **ML pipeline** — feature engineering, XGBoost, walk-forward
9. **Portfolio management** — multi-strategy allocation
10. **Monitoring** — FastAPI dashboard, Telegram alerts
11. **Production hardening** — Docker, CI/CD, graceful shutdown

---

## 7. Open Questions for Phase 1

- TimescaleDB extension vs plain PostgreSQL with manual partitioning?
- Redis vs in-process caching for initial development?
- Start with one-way or hedge position mode?
- pyproject.toml with Poetry vs uv vs pip?

**Recommendations:**
- Start with plain PostgreSQL, add TimescaleDB later if needed
- In-process cache (dict/LRU) for dev, Redis for production
- One-way mode first, hedge mode when implementing funding rate arb
- uv for package management (fastest, modern, growing ecosystem)
