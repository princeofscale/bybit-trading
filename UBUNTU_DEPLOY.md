# Деплой на Ubuntu Хостинг

## Быстрая установка (5 минут)

### 1. Подключитесь к серверу

```bash
ssh user@your-server-ip
```

### 2. Установите Docker

```bash
# Обновите систему
sudo apt update && sudo apt upgrade -y

# Установите зависимости
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

# Добавьте Docker GPG ключ
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавьте Docker репозиторий
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установите Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Добавьте текущего пользователя в группу docker
sudo usermod -aG docker $USER

# Выйдите и зайдите снова, чтобы изменения вступили в силу
exit
```

Зайдите снова:
```bash
ssh user@your-server-ip
```

### 3. Загрузите проект

```bash
# Клонируйте репозиторий (если у вас Git) или загрузите архив
git clone your-repo-url bybit-bot
cd bybit-bot

# ИЛИ загрузите через scp с локального компа:
# scp -r /Users/alextretyakov/Desktop/tests/bybit-bot user@your-server-ip:~/
```

### 4. Настройте .env

```bash
# Скопируйте шаблон
cp .env.example .env

# Отредактируйте (используйте nano или vim)
nano .env
```

Вставьте ваши настройки:

```bash
# Bybit Demo Trading API Keys
BYBIT_API_KEY=ваш_api_key
BYBIT_API_SECRET=ваш_api_secret
BYBIT_TESTNET=true
BYBIT_DEMO_TRADING=true
BYBIT_RECV_WINDOW=5000

# Risk Profile
RISK_PROFILE=conservative

# Risk guards
RISK_GUARD_ENABLE_CIRCUIT_BREAKER=true
RISK_GUARD_CIRCUIT_BREAKER_CONSECUTIVE_LOSSES=3
RISK_GUARD_CIRCUIT_BREAKER_COOLDOWN_HOURS=4
RISK_GUARD_ENABLE_DAILY_LOSS_LIMIT=true
RISK_GUARD_DAILY_LOSS_LIMIT_PCT=0.03
RISK_GUARD_ENABLE_SYMBOL_COOLDOWN=true
RISK_GUARD_SYMBOL_COOLDOWN_MINUTES=180
RISK_GUARD_SOFT_STOP_THRESHOLD_PCT=0.80
RISK_GUARD_SOFT_STOP_MIN_CONFIDENCE=0.75
RISK_GUARD_PORTFOLIO_HEAT_LIMIT_PCT=0.08

# Telegram (опционально)
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=ваш_токен
TELEGRAM_CHAT_ID=ваш_chat_id

# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=trading_bot
DB_USER=postgres
DB_PASSWORD=измените_пароль_здесь

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Environment
ENVIRONMENT=production
```

Сохраните (Ctrl+X → Y → Enter в nano)

### 5. Запустите бота

```bash
# Запуск всех сервисов
docker compose up -d

# Проверьте статус
docker compose ps

# Смотрите логи
docker compose logs -f bot
```

---

## Управление ботом

### Просмотр логов

```bash
# Все логи
docker compose logs -f

# Только бот
docker compose logs -f bot

# Последние 100 строк
docker compose logs --tail=100 bot
```

### Перезапуск

```bash
# Перезапуск после изменения кода
docker compose down
docker compose up -d --build

# Быстрый перезапуск (без пересборки)
docker compose restart bot
```

### Остановка

```bash
# Остановить всё
docker compose down

# Остановить с удалением volumes (ВНИМАНИЕ: удалит БД!)
docker compose down -v
```

### Обновление кода

```bash
# Если используете Git
git pull

# Пересобрать и перезапустить
docker compose down
docker compose up -d --build
```

---

## Мониторинг

### Проверка здоровья

```bash
# Статус контейнеров
docker compose ps

# Использование ресурсов
docker stats

# Логи за последние 5 минут
docker compose logs --since=5m bot
```

### Grafana (опционально)

Откройте в браузере: `http://your-server-ip:3000`

- Логин: admin
- Пароль: admin

### Telegram уведомления

Все торговые сигналы и сделки придут в Telegram автоматически.

---

## Автозапуск при перезагрузке сервера

Docker контейнеры настроены с `restart: unless-stopped`, поэтому автоматически запустятся после перезагрузки сервера.

Проверить:
```bash
sudo reboot
# После перезагрузки зайдите снова
docker compose ps
# Все контейнеры должны быть запущены
```

---

## Резервное копирование

### Бэкап базы данных

```bash
# Создать бэкап
docker compose exec postgres pg_dump -U postgres trading_bot > backup_$(date +%Y%m%d).sql

# Восстановить из бэкапа
docker compose exec -T postgres psql -U postgres trading_bot < backup_20260208.sql
```

### Бэкап журнала сделок

```bash
# Скопировать journal.db
docker compose cp bot:/app/journal.db journal_backup_$(date +%Y%m%d).db
```

---

## Безопасность

### Firewall

```bash
# Установите ufw
sudo apt install ufw

# Разрешите SSH
sudo ufw allow 22/tcp

# Разрешите Grafana (опционально)
sudo ufw allow 3000/tcp

# Включите firewall
sudo ufw enable
```

### Обновления системы

```bash
# Регулярно обновляйте
sudo apt update && sudo apt upgrade -y
```

---

## Устранение проблем

### Бот не запускается

```bash
# Проверьте логи
docker compose logs bot

# Проверьте .env
cat .env | grep BYBIT

# Пересоберите с нуля
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

### База данных не доступна

```bash
# Проверьте PostgreSQL
docker compose logs postgres

# Перезапустите БД
docker compose restart postgres
```

### Нет места на диске

```bash
# Проверьте место
df -h

# Очистите старые Docker образы
docker system prune -a
```

---

## Производительность

### Рекомендуемые ресурсы:

- **CPU:** 2 ядра (минимум 1)
- **RAM:** 2GB (минимум 1GB)
- **Диск:** 20GB SSD

### Оптимизация:

Для слабого сервера отключите Grafana:

```bash
# Закомментируйте Grafana в docker-compose.yml
# или остановите его:
docker compose stop grafana
```

---

## Готово! 🚀

Бот работает 24/7 на сервере. Все уведомления в Telegram.

**Что дальше:**
- Следите за Telegram для сигналов
- Держите минимум 14 дней testnet без hard-limit breach
- Переходите по этапам: conservative -> moderate -> масштабирование капитала
- Проверяйте логи раз в день
- Делайте бэкапы раз в неделю
