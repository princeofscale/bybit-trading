# Bybit AI Trading Bot

Автономный торговый бот для криптобиржи Bybit. Поддерживает USDT перпетуал фьючерсы на 15 криптовалютах. Включает технический анализ, ML-предсказания, бэктестинг, риск-менеджмент и мониторинг.

## Возможности

- **9 торговых стратегий**: EMA crossover, RSI mean reversion, momentum, trend following, Bollinger breakout, grid trading, funding rate arbitrage, multi-timeframe, ML-strategy
- **3 профиля риска**: консервативный (1% на сделку, плечо 1.5x), умеренный (2%, 3x), агрессивный (4%, 5x)
- **15 криптовалют**: BTC, ETH, SOL, XRP, DOGE, AVAX, ADA, LINK, DOT, MATIC, AR, SUI, APT, OP, ARB
- **ML модели**: XGBoost/LightGBM для фильтрации сигналов, walk-forward валидация
- **Бэктестинг**: исторический симулятор с проскальзыванием и комиссиями, walk-forward оптимизация
- **Риск-менеджмент**: position sizing (Kelly/fixed fractional), стоп-лоссы (fixed/trailing/ATR), circuit breaker, drawdown monitor, exposure limits
- **Портфель**: мульти-стратегия, ребалансировка по Sharpe/risk-parity
- **Мониторинг**: метрики, health checks, Telegram-алерты, дашборд
- **Production**: Docker, docker-compose (PostgreSQL + Redis + Grafana), graceful shutdown, state persistence

## Быстрый старт

### Установка

```bash
git clone <repo-url>
cd bybit-trading-bot
pip install -e ".[dev]"
```

### Настройка

```bash
cp .env.example .env
```

Заполните `.env`:
- `BYBIT_API_KEY` и `BYBIT_API_SECRET` — ключи от Bybit (testnet для начала)
- `BYBIT_TESTNET=true` — включает тестнет

### Запуск тестов

```bash
python3 -m pytest tests/ -v
```

### Запуск бота

```bash
python main.py
```

### Docker

```bash
docker compose up -d
```

Это поднимет: бот + PostgreSQL + Redis + Grafana (localhost:3000).

## Архитектура

```
Event Bus (async)
    │
    ├── Market Data → Strategies → Signals
    │                                  │
    │                    Risk Manager ← ┘
    │                         │
    │                    Order Manager → Exchange (Bybit API)
    │                         │
    │                    Position Manager
    │                         │
    └── Portfolio Manager ← ──┘
              │
         Monitoring → Telegram / Grafana
```

### Ключевые решения
- **ccxt** — универсальная библиотека для бирж (async, rate limiting)
- **Event-driven** — компоненты общаются через события
- **Pydantic Settings** — вся конфигурация через env-переменные
- **structlog** — структурированные JSON-логи

## Структура проекта

```
config/          Конфигурация, торговые пары, профили риска
core/            Движок, event bus, state manager, shutdown, persistence
exchange/        REST API, WebSocket, order/position manager
data/            Сбор данных, хранение, кэш, препроцессинг
indicators/      Технические индикаторы (EMA, RSI, MACD, ATR, VWAP...)
strategies/      9 торговых стратегий + strategy selector
ml/              ML pipeline (features, training, prediction, registry)
risk/            Risk manager, position sizer, stop loss, circuit breaker
portfolio/       Portfolio manager, allocation, rebalancer
backtesting/     Backtester, fill simulator, report generator
monitoring/      Metrics, health checks, alerts, dashboard, Telegram
database/        SQLAlchemy async, repositories
scripts/         Утилиты (collect_historical, run_backtest, train_model)
tests/           759 тестов (unit + integration)
```

## Скрипты

```bash
# Сбор исторических данных (365 дней по умолчанию)
python scripts/collect_historical.py [days]

# Бэктест стратегии
python scripts/run_backtest.py ema_crossover [data_file] [equity]

# Обучение ML модели
python scripts/train_model.py [data_file] [xgboost|lightgbm]

# Оптимизация параметров стратегии
python scripts/optimize_strategy.py [data_file] [n_trials]
```

## Профили риска

| Параметр | Консервативный | Умеренный | Агрессивный |
|----------|---------------|-----------|-------------|
| Риск на сделку | 1% | 2% | 4% |
| Макс. плечо | 1.5x | 3x | 5x |
| Макс. просадка | 8% | 15% | 25% |
| Дневной лимит | 3% | 5% | 8% |
| Макс. позиций | 5 | 10 | 15 |
| Мин. confidence | 0.7 | 0.5 | 0.4 |

## Telegram

Бот отправляет в Telegram:
- Открытие/закрытие позиций (символ, сторона, PnL)
- Риск-алерты (просадка, circuit breaker)
- Статус бота по команде `/status`

Команды: `/status`, `/positions`, `/pnl`, `/close_ready`, `/entry_ready`, `/guard`, `/pause`, `/resume`, `/risk`, `/help`

`/close_ready <symbol>` показывает диагностику, почему символ сейчас не закрывается (или готов к закрытию).
`/entry_ready <symbol>` показывает диагностику входа: стратегия, confidence, MTF confirm, risk verdict.

## Риск-менеджмент (конфигурируемые guards)

- Все позиции обязаны иметь стоп-лосс
- Circuit breaker: N подряд убытков -> пауза на M часов
- Daily loss guard:
- soft stop на 80% дневного лимита (только high-confidence сигналы)
- hard stop при 100% дневного лимита (пауза до нового дня)
- Symbol cooldown после убыточного закрытия (по инструменту)
- Portfolio heat limit: блок новых входов при перегреве риска
- Drawdown monitor: превышение лимита просадки -> полная остановка торговли
- Exposure manager: лимиты на количество позиций, плечо, общий риск

Основные env-переменные:
- `RISK_GUARD_ENABLE_CIRCUIT_BREAKER`
- `RISK_GUARD_CIRCUIT_BREAKER_CONSECUTIVE_LOSSES`
- `RISK_GUARD_CIRCUIT_BREAKER_COOLDOWN_HOURS`
- `RISK_GUARD_ENABLE_DAILY_LOSS_LIMIT`
- `RISK_GUARD_DAILY_LOSS_LIMIT_PCT`
- `RISK_GUARD_ENABLE_SYMBOL_COOLDOWN`
- `RISK_GUARD_SYMBOL_COOLDOWN_MINUTES`
- `RISK_GUARD_SOFT_STOP_THRESHOLD_PCT`
- `RISK_GUARD_SOFT_STOP_MIN_CONFIDENCE`
- `RISK_GUARD_PORTFOLIO_HEAT_LIMIT_PCT`
- `RISK_GUARD_ENABLE_DIRECTIONAL_EXPOSURE_LIMIT`
- `RISK_GUARD_MAX_DIRECTIONAL_EXPOSURE_PCT`
- `RISK_GUARD_ENABLE_SIDE_BALANCER`
- `RISK_GUARD_MAX_SIDE_STREAK`
- `RISK_GUARD_SIDE_IMBALANCE_PCT`
- `RISK_GUARD_ENABLE_MAX_HOLD_EXIT`
- `RISK_GUARD_MAX_HOLD_MINUTES`
- `RISK_GUARD_ENABLE_PNL_PCT_EXIT`
- `RISK_GUARD_TAKE_PROFIT_PCT`
- `RISK_GUARD_STOP_LOSS_PCT`
- `RISK_GUARD_ENABLE_TRAILING_STOP_EXIT`
- `RISK_GUARD_TRAILING_STOP_PCT`
- `TRADING_STOP_RETRY_MAX_ATTEMPTS`
- `TRADING_STOP_RETRY_INTERVAL_SEC`
- `TRADING_STOP_CONFIRM_TIMEOUT_SEC`
- `TRADING_MAX_SYMBOLS`
- `TRADING_ENABLE_MTF_CONFIRM`
- `TRADING_MTF_CONFIRM_TF`
- `TRADING_MTF_CONFIRM_MIN_BARS`
- `TRADING_MTF_CONFIRM_ADX_MIN`
- `TRADING_CLOSE_MISSING_CONFIRMATIONS`
- `TRADING_CLOSE_DEDUP_TTL_SEC`
- `TRADING_ENABLE_EXCHANGE_CLOSE_FALLBACK`
- `TRADING_ENABLE_SHORT_RELAX_IF_LONG_STREAK`
- `STATUS_USE_JOURNAL_DAILY_AGG`

## Операционный регламент

1. Минимум 14 дней на `testnet` без breach hard-limit перед масштабированием.
2. Порядок профилей: `conservative -> moderate -> увеличение капитала`.
3. Переход на следующий этап только при стабильных `DD`, `PF`, `Sharpe`.

При перезапуске бот синхронизирует открытые позиции с биржей, восстанавливает strategy state и делает reconcile на старте.

## Безопасность ключей

- Никогда не коммитьте рабочие `.env` с реальными ключами.
- Используйте `BYBIT_TESTNET=true`/`BYBIT_DEMO_TRADING=true` на этапе отладки.
- При любом подозрении утечки немедленно ротируйте `BYBIT_API_KEY` и `TELEGRAM_BOT_TOKEN`.

## Как улучшить доходность

1. **Реальные данные**: скачать 1-2 года свечей через `collect_historical.py`, прогнать бэктест на реальных данных
2. **ML фильтр**: обучить XGBoost на исторических сигналах — отсеивает слабые сигналы, повышает win rate на 5-10%
3. **Multi-timeframe**: совмещать сигналы с 15m, 1h, 4h — фильтрует шум
4. **Funding rate arb**: стабильный доход 10-30% годовых при боковом рынке
5. **Оптимизация параметров**: walk-forward оптимизация через `optimize_strategy.py`
6. **Больше монет**: диверсификация снижает просадки, повышает Sharpe ratio
7. **Корреляционный фильтр**: не открывать сильно коррелированные позиции
8. **Адаптивные стоп-лоссы**: ATR-based стопы адаптируются к волатильности

## Требования

- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Bybit API ключ (testnet для начала)

## Лицензия

Private. Not for redistribution.
