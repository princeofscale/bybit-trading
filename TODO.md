[x] Доделать стратегии: чтобы было несколько стратегий трейдинга, где ставки больше но риск больше, где ставки меньше и соответственно риск меньше, и умеренный.. → DONE: config/strategy_profiles.py — 3 профиля (conservative/moderate/aggressive) с разным риском, плечом, confidence
[x] Добавить больше монет (криптовалют), не только BTC, ETH, а чтобы он анализировал рынок, и сам выбирал монеты для трейдинга, если это очень сложно, просто расширим возможные криптовалюты для трейдинга. → DONE: config/trading_pairs.py расширен до 15 монет (BTC, ETH, SOL, XRP, DOGE, AVAX, ADA, LINK, DOT, MATIC, AR, SUI, APT, OP, ARB)
[x] Доделать проект, основываясь на RESEARCH_NOTES.md, CLAUDE.md. → DONE: все 11 фаз CLAUDE.md реализованы, 759 тестов, интеграционные тесты, скрипты
[x] В самом конце добавить README.md - что зачем, как запускать, функции возможноси и тд. → DONE: README.md создан (архитектура, команды, профили, скрипты)
[x] Добавить варианты как улучшить наш проект, чтобы успешность повысилась, доходность увеличилась и так далее. → DONE: секция "Как улучшить доходность" в README.md (8 пунктов)
[x] Добавить логи в telegram, не все логи, а конкретно нужные нам. Например что он закрыл такой-то лонг/шорт на такой-то монете, заработал или проиграл столько-то монет, чтобы я группу создал, и он туда отправлял уведомления, возможно, чтобы через telegram-бота было какое-либо управление чем-нибудь. → DONE: monitoring/telegram_bot.py — TelegramAlertSink (открытие/закрытие сделок, PnL, риск-алерты), TelegramCommandHandler (/status, /positions, /pnl, /pause, /resume)
[x] Доделать database/ зачем нам database/migrations/ и database/repositories/ ? в чем смысл если папки пусты? → DONE: database/repositories/candle_repo.py и trade_repo.py — полные CRUD (upsert, get_latest, get_range, count, win_rate, total_pnl)
[x] Я создал в bybit api-key, добавил в .env.example, проверишь, вот permissions: Contracts - Orders Positions  , USDC Contracts - Trade  , Unified Trading - Trade  , SPOT - Trade  , Wallet - Account Transfer Subaccount Transfer  , Exchange - Convert，Exchange History → DONE: ключи перенесены из .env.example в .env (безопасность), permissions подходят для работы бота

[ ] У нас в README написано про telegram-bot, но по сути, где он находится? его еще нет, или есть но я не нашел, куда вводить канал, куда вводить токен? нужно доделать, чтобы бот в группу определенную отправлял уведомления, что купил, что продал, и так далее, чтобы отправлял только нужные и полезные уведомления, даже если проект настроен на testnet.
[ ] Я из README увидел ограничения (rare-limit чтоль) на трейдинг: "3 подряд стоп-лосса → пауза 4 часа", зачем нам ограничение на трейдинг? сделай тоже, чтобы как с стратегиями было, мы выбирали сами ограничения на трейдинг.
[ ] По поводу постановки бота на testnet, у меня есть хостинг, подготовь проект чтобы я поставил его на хостинг (testnet).
[ ] Проверь по RESEARCH_NOTES.md, все ли у нас правильно? в том ли мы направлении идем? или что-то нужно доделать/переделать?
[ ] Обновить pyproject.toml: ccxt 4.5.36, pybit 5.14.0, fastapi 0.128.5, uvicorn 0.40.0, SQLAlchemy 2.0.46, asyncpg 0.31.0, alembic 1.18.3, pydantic 2.12.5, pydantic-settings 2.12.0, redis 7.1.0, pandas 3.0.0, ta 0.11.0, numpy 2.4.2, xgboost 3.1.3, lightgbm 4.6.0, optuna 4.7.0, scikit-learn 1.8.0, structlog 25.5.0, orjson 3.11.7, httpx 0.28.1, websockets 16.0, python-dotenv 1.2.1, pytest 9.0.2, pytest-asyncio 1.3.0, pytest-cov 7.0.0, pytest-mock 3.15.1, ruff 0.15.0, mypy 1.19.1, pre-commit 4.5.1, setuptools 81.0.0, aiosqlite 0.22.1. Это все актуальные версии библиотек, use context7. Обнови все dependencies до последних версий (я прикрепил выше все актуальные версии), если нужно будет изменить логику проекта под новые стабильные версии - меняй. Если нужна будет новая версия python - устанавливай.

## Следующие шаги
[ ] Запуск на Bybit testnet (paper trading) — минимум 7-14 дней
[ ] Сбор реальных исторических данных и бэктест на них
[ ] Обучение ML модели на реальных данных
[ ] Подключение реального Telegram бота (создать бота через @BotFather, добавить токен)
[ ] Плавный переход на mainnet (10% → 25% → 50% → 100% капитала)
