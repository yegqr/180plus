# 🎓 NMT-Bot — Твій персональний репетитор для НМТ

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram&logoColor=white)](https://docs.aiogram.dev/)
[![Tests](https://img.shields.io/badge/tests-343%20passed-brightgreen?logo=pytest)](https://pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Telegram-бот для підготовки українських школярів до **Національного Мультипредметного Тесту (НМТ)**.
Підтримує повну симуляцію іспиту, випадковий режим, щоденні виклики з лотереєю та пояснення від штучного інтелекту на базі Google Gemini.
Адмін-панель дозволяє завантажувати питання, розсилати повідомлення та керувати матеріалами просто з Telegram.

---

## ✨ Можливості

- 📝 **Симуляція іспиту** — повноцінна симуляція НМТ з таймером, вибором предметів і детальною статистикою результатів
- 🎲 **Випадковий режим** — швидке опитування з випадковими питаннями для щоденного тренування
- 🏆 **Щоденний виклик** — унікальне питання дня з системою очок і лотереєю серед учасників
- 🤖 **AI-пояснення (Gemini)** — розгорнуте пояснення правильної відповіді від Google Gemini AI
- 📊 **Статистика** — детальна аналітика прогресу по предметах і темах
- 🧮 **Калькулятор балів** — розрахунок конкурсного балу НМТ за введеними результатами
- 📚 **Навчальні матеріали** — доступ до матеріалів, завантажених адміністратором
- 🛠️ **Адмін-панель**:
  - Завантаження питань через ZIP + CSV
  - Управління питаннями та матеріалами
  - Масова розсилка повідомлень
  - Режим технічного обслуговування
  - Панель статистики та моніторингу
- 🗂️ **Telegram-теми** — автоматичне маршрутизування повідомлень по темах групи
- 🔔 **Планувальник (APScheduler)** — автоматична публікація щоденних викликів

---

## 🏗️ Архітектура

Бот побудований на **aiogram 3** з діалогами **aiogram-dialog**, шаруватою архітектурою та чітким поділом відповідальності.

```
Telegram API
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                     Dispatcher (aiogram 3)               │
└─────────────────────────────────────────────────────────┘
     │
     ▼  Middleware Pipeline
┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  ┌─────────────┐
│   Database   │→ │    Config    │→ │  TopicRouting   │→ │ Maintenance │
│  Middleware  │  │  Middleware  │  │   Middleware    │  │  Middleware │
└──────────────┘  └──────────────┘  └─────────────────┘  └─────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│             Dialogs / Handlers / Services                │
│                                                          │
│  simulation  │  random_mode  │  daily  │  calculator    │
│  stats       │  admin panel  │  materials               │
└─────────────────────────────────────────────────────────┘
     │
     ▼  Repository Layer
┌──────────────┐  ┌──────────────┐  ┌─────────────────┐
│  PostgreSQL  │  │    Redis     │  │  Google Gemini  │
│ (SQLAlchemy  │  │  (cache /    │  │  (AI-пояснення) │
│  + Alembic)  │  │  FSM state)  │  │                 │
└──────────────┘  └──────────────┘  └─────────────────┘
```

**Ключові компоненти:**

| Шар | Технологія | Призначення |
|-----|-----------|-------------|
| Bot framework | aiogram 3 + aiogram-dialog | Обробка апдейтів, FSM, діалоги |
| Database ORM | SQLAlchemy 2 (async) + asyncpg | Асинхронна робота з PostgreSQL |
| Migrations | Alembic | Версіонування схеми БД |
| Cache / FSM | Redis 6.2 | Збереження стану діалогів |
| Scheduler | APScheduler | Щоденні виклики за розкладом |
| AI | Google Gemini (google-genai) | Пояснення відповідей |
| Deploy | Docker Compose | Контейнеризація всіх сервісів |

---

## 🚀 Швидкий старт

### Передумови

- [Docker](https://docs.docker.com/get-docker/) та [Docker Compose](https://docs.docker.com/compose/install/)
- Telegram-бот, створений через [@BotFather](https://t.me/BotFather)
- (опціонально) Google Gemini API ключ для AI-пояснень

### 1. Клонування репозиторію

```bash
git clone https://github.com/your-username/NMT-bot.git
cd NMT-bot
```

### 2. Налаштування змінних середовища

Створіть `.env` файл і заповніть значення:

```bash
cp .env.example .env
nano .env
```

Мінімальна конфігурація для запуску:

```env
BOT_TOKEN=your_telegram_bot_token
ADMINS=123456789
USE_REDIS=True

POSTGRES_USER=nmt_user
POSTGRES_PASSWORD=strongpassword
POSTGRES_DB=nmt_db
DB_HOST=pg_database
DB_PORT=5432

REDIS_HOST=redis_cache
REDIS_PORT=6389
REDIS_PASSWORD=someredispass

GEMINI_API_KEY=your_gemini_api_key
```

### 3. Запуск

```bash
docker compose up -d --build
```

Бот автоматично застосує міграції Alembic і запуститься.

Перевірити логи:

```bash
docker compose logs -f bot
```

---

## ⚙️ Конфігурація

Усі параметри передаються через `.env` файл у корені проекту.

| Змінна | Обов'язкова | Опис |
|--------|:-----------:|------|
| `BOT_TOKEN` | ✅ | Токен Telegram-бота від @BotFather |
| `ADMINS` | ✅ | Telegram ID адміністраторів через кому (напр. `123,456`) |
| `USE_REDIS` | ✅ | Використовувати Redis для FSM (`True` / `False`) |
| `POSTGRES_USER` | ✅ | Ім'я користувача PostgreSQL |
| `POSTGRES_PASSWORD` | ✅ | Пароль PostgreSQL |
| `POSTGRES_DB` | ✅ | Назва бази даних |
| `DB_HOST` | ✅ | Хост PostgreSQL (у Docker: `pg_database`) |
| `DB_PORT` | ✅ | Порт PostgreSQL (за замовчуванням `5432`) |
| `REDIS_HOST` | ✅ | Хост Redis (у Docker: `redis_cache`) |
| `REDIS_PORT` | ✅ | Порт Redis (за замовчуванням `6389`) |
| `REDIS_PASSWORD` | ✅ | Пароль Redis |
| `GEMINI_API_KEY` | ⬜ | API ключ Google Gemini для AI-пояснень |
| `ONBOARDING_VIDEO` | ⬜ | URL відео для вітального повідомлення |

> **Примітка:** У Docker Compose значення `DB_HOST` та `REDIS_HOST` автоматично перевизначаються на внутрішні імена сервісів (`pg_database`, `redis_cache`).

---

## 🧪 Тести

Проект має **343 тести** на базі `pytest` і `pytest-asyncio`. Інтеграційні тести використовують SQLite in-memory для ізольованого тестування репозиторіїв без потреби у запущеній базі даних.

### Встановлення залежностей

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Запуск тестів

```bash
# Усі тести
pytest

# З деталізованим виводом
pytest -v

# Без попереджень (як у скрипті деплою)
pytest -p no:warnings --tb=short -q

# Конкретний файл
pytest tests/test_simulation_service.py
```

### Структура тестів

```
tests/
├── conftest.py                    # Фікстури (SQLite in-memory, сесія БД)
├── test_repos.py                  # Репозиторії (інтеграційні)
├── test_simulation_service.py     # Сервіс симуляції
├── test_bulk_upload.py            # Завантаження питань через ZIP/CSV
├── test_daily.py                  # Щоденний виклик
├── test_scoring.py                # Розрахунок балів НМТ
├── test_nmt_scoring.py            # Калькулятор конкурсного балу
├── test_gemini_helpers.py         # Інтеграція з Gemini AI
└── ...                            # Інші юніт-тести
```

---

## 📦 Деплой

### Локальний (розробка)

```bash
docker compose up -d --build
```

### Продакшн на VPS (Hetzner)

Проект включає скрипт `scripts/remote_deploy.sh`, який автоматизує весь процес деплою:

1. Запускає тести — якщо є падіння, деплой скасовується
2. Робить `git commit` та `git push`
3. Синхронізує файли на сервер через `rsync` (без `.env`, `.git`, кешів)
4. Підключається по SSH і виконує `scripts/deploy.sh` на сервері

```bash
chmod +x scripts/remote_deploy.sh
./scripts/remote_deploy.sh
```

При першому запуску скрипт запитає IP сервера, SSH-користувача та цільову директорію. Ці дані зберігаються у `.deploy_config` для наступних запусків.

**Ручний деплой на сервері:**

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

---

## 📁 Структура проекту

```
NMT-bot/
│
├── bot.py                          # Точка входу, ініціалізація бота
├── docker-compose.yml              # Docker Compose (bot + postgres + redis)
├── Dockerfile                      # Образ бота
├── requirements.txt                # Python залежності
├── alembic.ini                     # Конфігурація Alembic
├── pytest.ini                      # Конфігурація pytest
│
├── tgbot/                          # Основний пакет бота
│   ├── config.py                   # Завантаження конфігурації з .env
│   ├── dialogs/                    # aiogram-dialog діалоги
│   │   ├── admin/                  # Адмін-панель (dashboard, upload, settings…)
│   │   ├── simulation.py           # Симуляція іспиту
│   │   ├── random_mode.py          # Випадковий режим
│   │   ├── daily.py                # Щоденний виклик
│   │   ├── stats.py                # Статистика
│   │   ├── calculator.py           # Калькулятор балів
│   │   └── main_menu.py            # Головне меню
│   ├── handlers/                   # Обробники подій (user, admin, error…)
│   ├── middlewares/                # Middleware (database, config, routing…)
│   ├── services/                   # Бізнес-логіка
│   │   ├── simulation_service.py   # Логіка симуляції
│   │   ├── daily.py                # Логіка щоденного виклику
│   │   ├── gemini.py               # Запити до Gemini AI
│   │   ├── bulk_upload.py          # Парсинг ZIP + CSV
│   │   ├── scoring.py              # Розрахунок балів
│   │   ├── scheduler.py            # APScheduler завдання
│   │   └── broadcaster.py          # Масова розсилка
│   ├── filters/                    # Фільтри aiogram
│   ├── keyboards/                  # Клавіатури (inline, reply)
│   └── misc/                       # Утиліти та константи
│
├── infrastructure/                 # Інфраструктурний шар
│   ├── database/
│   │   ├── models/                 # SQLAlchemy моделі
│   │   │   ├── users.py
│   │   │   ├── questions.py
│   │   │   ├── results.py
│   │   │   ├── stats.py
│   │   │   └── …
│   │   ├── repo/                   # Repository pattern (CRUD)
│   │   │   ├── users.py
│   │   │   ├── questions.py
│   │   │   ├── results.py
│   │   │   └── …
│   │   └── setup.py                # Ініціалізація engine / sessionmaker
│   └── migrations/                 # Alembic міграції
│
├── scripts/
│   ├── deploy.sh                   # Деплой на сервері (docker compose up)
│   └── remote_deploy.sh            # Автоматизований деплой з локальної машини
│
└── tests/                          # 343 тести (pytest + pytest-asyncio)
```

---

<div align="center">

Зроблено з ❤️ для українських школярів

</div>
