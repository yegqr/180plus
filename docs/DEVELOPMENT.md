# Гайд з розробки NMT-bot

## Зміст

1. [Локальна розробка](#-локальна-розробка)
2. [Тести](#-тести)
3. [Як додати новий предмет](#-як-додати-новий-предмет)
4. [Як додати нову функцію в адмінку](#-як-додати-нову-функцію-в-адмінку)
5. [Як додати нову модель БД](#-як-додати-нову-модель-бд)
6. [Міграції Alembic](#-міграції-alembic)
7. [Деплой](#-деплой)
8. [Конвенції коду](#-конвенції-коду)

---

## 🛠 Локальна розробка

### Передумови

- Python 3.11+
- Docker та Docker Compose
- Git

### Клонування репозиторію

```bash
git clone <repo-url>
cd NMT-bot
```

### Створення віртуального середовища

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Налаштування змінних середовища

Скопіюй `.env.example` або створи `.env` вручну:

```bash
cp .env.example .env
# відредагуй .env — встав токен бота, credentials БД тощо
```

### Запуск інфраструктури (тільки БД та Redis)

```bash
docker compose up -d pg_database redis_cache
```

### Запуск бота

```bash
python bot.py
```

---

## 🧪 Тести

### Запуск тестів

```bash
python3 -m pytest -p no:warnings -q
```

Усього тестів: **343**.

### Як влаштований тестовий стек

- **pytest** + **pytest-asyncio**
- База даних: **SQLite in-memory** (замість PostgreSQL)
- `conftest.py` патчить PostgreSQL-специфічні типи (наприклад, `UUID`, `JSONB`) для сумісності з SQLite

### Коли писати unit-тест, а коли інтеграційний

| Тип | Коли використовувати | Що потрібно |
|-----|----------------------|-------------|
| **Unit** | Чиста функція без зовнішніх залежностей | Нічого, крім імпорту |
| **Integration** | Логіка, що взаємодіє з БД через репозиторій | Фікстура `repo` з `conftest.py` |

### Важливо: UUID-ключі в одній транзакції

Якщо в одному тесті вставляєш кілька об'єктів з UUID як первинним ключем в рамках однієї транзакції — роби `commit` між кожним вставленням, інакше SQLite видасть помилку конфлікту:

```python
async def test_example(repo):
    obj1 = MyModel(id=uuid4(), ...)
    repo.session.add(obj1)
    await repo.session.commit()   # <-- обов'язково між вставками

    obj2 = MyModel(id=uuid4(), ...)
    repo.session.add(obj2)
    await repo.session.commit()
```

---

## ➕ Як додати новий предмет

Підтримувані slug-и предметів: `math`, `mova`, `hist`, `eng`, `physics`.

Якщо потрібно додати новий предмет, зроби наступне по черзі:

1. **`tgbot/misc/constants.py`** — додай slug і назву до словника `SUBJECT_LABELS`:
   ```python
   SUBJECT_LABELS = {
       ...
       "new_subject": "Назва предмету",
   }
   ```

2. **`tgbot/misc/constants.py`** — якщо предмет має щоденні завдання, додай slug до `DAILY_CHALLENGE_SUBJECTS`.

3. **`tgbot/misc/nmt_scoring.py`** — додай таблицю перерахунку балів для нового предмету.

4. **`tgbot/misc/categories.py`** — додай категорії питань для нового предмету.

5. **`tgbot/services/scoring.py`** — перевір, чи не потребує предмет особливої логіки підрахунку. Для `hist` вже є спеціальний кейс — переконайся, що новий предмет не конфліктує або додай свій кейс за аналогією.

---

## ➕ Як додати нову функцію в адмінку

Адмін-діалоги знаходяться у `tgbot/dialogs/admin/`. State groups визначаються безпосередньо у файлах діалогів (не у `misc/states.py`).

1. **`tgbot/dialogs/admin/states.py`** — додай новий стан до класу `AdminSG`:
   ```python
   class AdminSG(StatesGroup):
       ...
       new_feature = State()
   ```

2. **`tgbot/dialogs/admin/*.py`** — створи або розшир відповідний файл діалогу: напиши window-функцію та хендлери з іменуванням `on_{action}`.

3. **`tgbot/dialogs/admin/__init__.py`** — додай кнопку переходу в головне меню `Window` адмінки.

4. **`tgbot/dialogs/admin/__init__.py`** — зареєструй нові вікна в `admin_dialog`.

5. Напиши тести, якщо логіка нетривіальна.

---

## ➕ Як додати нову модель БД

1. **Створи модель** у `infrastructure/database/models/new_model.py`. Успадковуй `Base` і `TableNameMixin`; за потреби додай `TimestampMixin`:
   ```python
   class NewModel(Base, TableNameMixin, TimestampMixin):
       id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
       ...
   ```

2. **Експортуй модель** з `infrastructure/database/models/__init__.py`.

3. **Створи репозиторій** `infrastructure/database/repo/new_repo.py`. Успадковуй `BaseRepo`. Ніколи не викликай `session.commit()` всередині репо:
   ```python
   class NewRepo(BaseRepo):
       async def get_by_id(self, obj_id: uuid.UUID) -> NewModel | None:
           ...
   ```

4. **Додай `@property`** до `RequestsRepo` у `infrastructure/database/repo/requests.py`:
   ```python
   @property
   def new(self) -> NewRepo:
       return NewRepo(self.session)
   ```

5. **Створи міграцію Alembic**:
   ```bash
   alembic revision --autogenerate -m "add_new_model"
   ```

6. **Застосуй міграцію**:
   ```bash
   alembic upgrade head
   ```

7. **Напиши інтеграційні тести** у `tests/test_repos.py`.

---

## 📦 Міграції Alembic

Конфігурація: `alembic.ini` → вказує на `infrastructure/migrations/`.
Файли міграцій: `infrastructure/migrations/versions/`.

| Команда | Дія |
|---------|-----|
| `alembic revision --autogenerate -m "description"` | Створити міграцію автоматично |
| `alembic upgrade head` | Застосувати всі міграції |
| `alembic downgrade -1` | Відкотити останню міграцію |
| `alembic history` | Переглянути історію міграцій |

> Перед запуском міграцій переконайся, що БД доступна і `.env` налаштовано. Завжди перевіряй згенерований файл перед `upgrade head` — `--autogenerate` може пропустити зміни у JSONB-структурах та деяких custom типах.

---

## 🚀 Деплой

### Локально (docker compose)

```bash
docker compose up -d --build
```

### Віддалений деплой на VPS

```bash
./scripts/remote_deploy.sh
```

Скрипт виконує наступні кроки:

1. Запускає всі **343 тести** — якщо хоч один не пройшов, деплой зупиняється.
2. Запитує підтвердження (`ok`) перед продовженням.
3. `git add` + `git commit` + `git push`.
4. `rsync` — синхронізує файли на VPS.
5. SSH на сервер → запускає `deploy.sh`.

### Конфігурація деплою

Файл `.deploy_config` (знаходиться в `.gitignore`) містить:

```
SERVER_IP=...
SERVER_USER=...
TARGET_DIR=...
```

---

## 📐 Конвенції коду

### Загальні правила

- **Type hints** — скрізь і завжди.
- **async/await** — для всіх операцій з БД і Telegram API.
- **Синхронні виклики БД заборонені** — завжди `await`.

### Найменування

| Що | Конвенція | Приклад |
|----|-----------|---------|
| Метод репозиторію | `дієслово_іменник` | `get_user_by_id`, `save_result`, `update_materials` |
| Getter діалогу | `get_{window}_data` | `get_stats_data` |
| Хендлер діалогу | `on_{action}` | `on_subject_selected`, `on_answer_submitted` |
| State group | `{Name}SG` (inline у файлі діалогу) | `QuizSG`, `AdminSG` |

### Транзакції — головне правило

**Тільки `DatabaseMiddleware` викликає `session.commit()`.**
Ніколи не викликай `session.commit()` у репозиторіях або хендлерах діалогів.

```python
# ПРАВИЛЬНО — репо тільки пише у сесію, без commit
async def save_result(self, ...) -> None:
    self.session.add(ExamResult(...))

# НЕПРАВИЛЬНО
async def save_result(self, ...) -> None:
    self.session.add(ExamResult(...))
    await self.session.commit()  # НЕ РОБИТИ ТАК
```

### Архітектурні обмеження

- `tgbot/services/` **не імпортує** з `tgbot/dialogs/` — тільки в одному напрямку.
- Фонові задачі (scheduler jobs) **відкривають власну сесію** через `session_pool`, а не використовують сесію з middleware.
