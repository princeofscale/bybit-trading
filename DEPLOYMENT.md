# Deployment Guide - Bybit Trading Bot (Testnet)

Инструкция по развёртыванию бота на хостинге для тестирования на Bybit testnet.

## Предварительные требования

### 1. Bybit Testnet API Keys

1. Зарегистрируйтесь на [Bybit Testnet](https://testnet.bybit.com)
2. Пройдите в User Center → API Management
3. Создайте API ключ с правами:
   - ✅ Read/Write (для Order, Position, Account)
   - ❌ Withdraw (не нужен)
4. Сохраните API Key и API Secret (покажется только один раз!)

### 2. Хостинг требования

- **CPU**: 1+ ядро
- **RAM**: 2+ GB
- **Storage**: 10+ GB SSD
- **OS**: Ubuntu 20.04+ / Debian 11+
- **Docker**: 24.0+
- **Docker Compose**: 2.20+

## Установка на хостинг

### Шаг 1: Подготовка сервера

```bash
# Подключитесь к серверу
ssh user@your-server.com

# Обновите систему
sudo apt update && sudo apt upgrade -y

# Установите Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установите Docker Compose
sudo apt install docker-compose-plugin -y

# Выйдите и зайдите снова для применения прав
exit
ssh user@your-server.com

# Проверьте установку
docker --version
docker compose version
```

### Шаг 2: Клонирование проекта

```bash
# Клонируйте репозиторий
git clone <your-repo-url> bybit-bot
cd bybit-bot

# Или загрузите архив
scp -r ./bybit-bot user@your-server.com:~/
```

### Шаг 3: Конфигурация

```bash
# Скопируйте пример конфигурации
cp .env.example .env

# Отредактируйте .env
nano .env
```

**Обязательно измените:**

```env
# Ваши реальные API ключи от Bybit Testnet
BYBIT_API_KEY=ваш_testnet_api_key
BYBIT_API_SECRET=ваш_testnet_api_secret
BYBIT_TESTNET=true

# Выберите профиль риска
RISK_PROFILE=conservative   # или moderate, aggressive

# Telegram уведомления (рекомендуется)
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=ваш_telegram_bot_token
TELEGRAM_CHAT_ID=ваш_chat_id

# Смените пароль БД
DB_PASSWORD=надёжный_пароль_для_postgres
```

#### Настройка Telegram (опционально, но рекомендуется)

1. **Создайте бота:**
   - Откройте [@BotFather](https://t.me/BotFather) в Telegram
   - Отправьте `/newbot`
   - Следуйте инструкциям, получите токен

2. **Получите Chat ID:**
   ```bash
   # Отправьте любое сообщение вашему боту
   # Затем выполните (замените <TOKEN>):
   curl https://api.telegram.org/bot<TOKEN>/getUpdates
   # Найдите "chat":{"id":123456789} - это ваш chat_id
   ```

3. **Для группы:**
   - Добавьте бота в группу
   - Сделайте бота админом (чтобы он мог читать сообщения)
   - Chat ID группы будет отрицательным: `-1001234567890`

### Шаг 4: Запуск

```bash
# Запустите все сервисы
docker compose up -d

# Проверьте логи
docker compose logs -f bot

# Остановить: Ctrl+C, затем
docker compose down
```

### Шаг 5: Мониторинг

```bash
# Просмотр логов
docker compose logs -f bot

# Статус контейнеров
docker compose ps

# Проверка здоровья
docker compose exec bot python3 -c "from core.orchestrator import *; print('OK')"
```

## Структура Docker Compose

```yaml
services:
  postgres:  # База данных для исторических данных
  redis:     # Кэш для hot data
  bot:       # Торговый бот
```

## Анализ торговой сессии

После остановки бота (или в любой момент):

```bash
# Подключитесь к контейнеру
docker compose exec bot bash

# Запустите анализ
python scripts/analyze_session.py journal.db

# Или скопируйте журнал для анализа локально
docker compose cp bot:/app/journal.db ./journal_backup.db
```

## Обслуживание

### Обновление бота

```bash
cd bybit-bot
git pull origin main  # или загрузите новую версию
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Бэкап данных

```bash
# Бэкап PostgreSQL
docker compose exec postgres pg_dump -U postgres trading_bot > backup_$(date +%Y%m%d).sql

# Бэкап журнала
docker compose cp bot:/app/journal.db ./journal_backup_$(date +%Y%m%d).db
```

### Очистка

```bash
# Остановить и удалить контейнеры
docker compose down

# Удалить volumes (ВНИМАНИЕ: удалит все данные!)
docker compose down -v

# Полная очистка Docker
docker system prune -a
```

## Troubleshooting

### Бот не запускается

```bash
# Проверьте логи
docker compose logs bot

# Проверьте .env файл
cat .env | grep BYBIT

# Перезапустите
docker compose restart bot
```

### Ошибка подключения к Bybit

- Проверьте, что `BYBIT_TESTNET=true`
- Проверьте API ключи в .env
- Проверьте интернет на сервере: `curl https://api-testnet.bybit.com/v5/market/time`

### БД ошибки

```bash
# Проверьте статус PostgreSQL
docker compose logs postgres

# Пересоздайте БД
docker compose down
docker volume rm bybit-bot_postgres_data
docker compose up -d
```

### Telegram не работает

```bash
# Проверьте токен
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Проверьте chat_id
docker compose exec bot env | grep TELEGRAM
```

## Безопасность

### ❗ Важные меры

1. **Никогда не коммитьте .env в git**
   ```bash
   # Убедитесь, что .env в .gitignore
   grep -q "^\.env$" .gitignore || echo ".env" >> .gitignore
   ```

2. **Используйте firewall**
   ```bash
   sudo ufw enable
   sudo ufw allow 22/tcp    # SSH
   sudo ufw allow from <your-ip> to any port 5432  # PostgreSQL (только с вашего IP)
   ```

3. **Регулярные обновления**
   ```bash
   sudo apt update && sudo apt upgrade -y
   docker compose pull
   docker compose up -d
   ```

4. **Мониторинг логов**
   ```bash
   # Настройте logrotate для логов Docker
   sudo nano /etc/docker/daemon.json
   ```
   ```json
   {
     "log-driver": "json-file",
     "log-opts": {
       "max-size": "100m",
       "max-file": "3"
     }
   }
   ```

## Переход на Mainnet (когда будете готовы)

1. Смените в `.env`:
   ```env
   BYBIT_TESTNET=false
   BYBIT_API_KEY=ваш_mainnet_api_key
   BYBIT_API_SECRET=ваш_mainnet_api_secret
   ENVIRONMENT=production
   ```

2. **ВАЖНО**: Начните с минимальных позиций!
3. Используйте `conservative` профиль
4. Увеличивайте капитал постепенно

## Полезные команды

```bash
# Просмотр всех контейнеров
docker compose ps

# Перезапуск только бота
docker compose restart bot

# Просмотр использования ресурсов
docker stats

# Подключение к PostgreSQL
docker compose exec postgres psql -U postgres -d trading_bot

# Подключение к Redis
docker compose exec redis redis-cli

# Выполнение команды в контейнере бота
docker compose exec bot python3 -c "print('Hello')"
```

## Поддержка

Если возникли проблемы:
1. Проверьте логи: `docker compose logs -f bot`
2. Проверьте README.md и RESEARCH_NOTES.md
3. Запустите тесты: `docker compose exec bot python3 -m pytest tests/ -v`

---

**Удачного трейдинга! 🚀**

*Помните: всегда тестируйте на testnet перед использованием реальных средств.*
