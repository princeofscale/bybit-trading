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

Команды: `/status`, `/positions`, `/pnl`, `/pause`, `/resume`, `/risk`, `/help`

## Риск-менеджмент (не отключается)

- Все позиции обязаны иметь стоп-лосс
- Circuit breaker: 3 подряд стоп-лосса → пауза 4 часа
- Drawdown monitor: превышение лимита → полная остановка торговли
- Exposure manager: лимиты на количество позиций, плечо, общий риск

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
