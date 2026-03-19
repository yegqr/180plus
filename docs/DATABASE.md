# Довідник бази даних NMT-bot

## Схема бази даних

```
┌───────────────────────────────────────────────────────────────────────┐
│                              users                                    │
│  PK user_id (BIGINT)                                                  │
│     username, full_name, active, language                             │
│     selected_subject, is_admin, daily_sub                             │
│     settings (JSONB), created_at, updated_at                          │
└────────────────┬──────────────────────────────────────────────────────┘
                 │ user_id (FK)
        ┌────────┴──────────┐
        ▼                   ▼
┌──────────────────┐  ┌──────────────────────────────────────────────┐
│  examresults     │  │  randomresults                               │
│  PK id (UUID)    │  │  PK id (UUID)                                │
│  user_id (FK)    │  │  user_id (FK)                                │
│  subject, year   │  │  subject, question_id, points                │
│  session         │  │  created_at                                  │
│  raw_score       │  └──────────────────────────────────────────────┘
│  nmt_score       │
│  duration        │
│  created_at      │
└──────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│                            questions                                   │
│  PK id (INTEGER, autoincrement)                                        │
│     subject, year, session, q_number                                   │
│     image_file_id (legacy), images (JSONB array)                       │
│     q_type, correct_answer (JSONB), weight                             │
│     explanation (TEXT), categories (JSONB array)                       │
└───────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│                          useractionlogs                                │
│  PK id (BIGINT, autoincrement)                                         │
│     user_id, question_id                                               │
│     answer (VARCHAR 500), is_correct, mode, session_id                 │
│     created_at                                                         │
└───────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌────────────────────────────────────────────┐
│      settings        │  │              joinstats                     │
│  PK key (VARCHAR 50) │  │  PK id (BIGINT)                           │
│     value (VARCHAR   │  │     user_id, source (VARCHAR 255)         │
│           512)       │  │     created_at                            │
└──────────────────────┘  └────────────────────────────────────────────┘

┌──────────────────────────────────────┐  ┌─────────────────────────────┐
│        pendingjoinrequests           │  │    subjectmaterials         │
│  PK user_id (BIGINT)                 │  │  PK subject (VARCHAR 50)    │
│  PK chat_id (BIGINT)                 │  │     images (JSONB array)    │
│     created_at                       │  └─────────────────────────────┘
└──────────────────────────────────────┘
```

---

## Моделі

### users

**Файл:** `infrastructure/database/models/users.py`
**Таблиця:** `users`

Центральна таблиця. Створюється або оновлюється при **кожному** запиті до бота через `DatabaseMiddleware` (upsert `ON CONFLICT DO UPDATE`).

| Поле | Тип | Опис |
|------|-----|------|
| `user_id` | BIGINT PK | Telegram user ID (autoincrement=False) |
| `username` | VARCHAR(128) nullable | @username без "@" |
| `full_name` | VARCHAR(128) | Повне ім'я (first_name + last_name) |
| `active` | BOOLEAN DEFAULT true | Чи активний юзер (зараз не знімається автоматично) |
| `language` | VARCHAR(10) DEFAULT 'en' | Мовний код Telegram (`uk`, `en`, тощо) |
| `selected_subject` | VARCHAR(50) DEFAULT 'math' | Поточний обраний предмет |
| `is_admin` | BOOLEAN DEFAULT false | Чи є адміном бота |
| `daily_sub` | BOOLEAN DEFAULT true | Підписка на Daily Challenge |
| `settings` | JSONB DEFAULT '{}' | Словник налаштувань, включно з `topic_ids` |
| `created_at` | TIMESTAMP | Дата першого звернення до бота |
| `updated_at` | TIMESTAMP | Дата останнього звернення (оновлюється при upsert) |

**Призначення:** Зберігає профіль юзера, налаштування топіків, підписки, роль.

**Ключові методи `UserRepo`:**
- `get_or_create_user()` — upsert, повертає поточний стан юзера
- `update_subject()` — зміна `selected_subject`
- `get_users_for_broadcast(filter_type)` — вибірка юзерів для розсилки за фільтром (all, daily_challenge, active_today, active_week, inactive_*)
- `update_user_settings()` — зберігає JSONB `settings` (наприклад `{"topic_ids": {"math": 123, "hist": 456}}`)

**Структура `settings` JSONB:**
```json
{
  "topic_ids": {
    "math": 100,
    "hist": 101,
    "mova": 102,
    "eng":  103
  }
}
```

---

### questions

**Файл:** `infrastructure/database/models/questions.py`
**Таблиця:** `questions`

Основний контент бота. Питання завантажуються адміном через ZIP або вручну.

| Поле | Тип | Опис |
|------|-----|------|
| `id` | INTEGER PK autoincrement | Внутрішній ID питання |
| `subject` | VARCHAR(50) | Slug предмета: `math`, `hist`, `mova`, `eng`, `physics` |
| `year` | INTEGER | Рік НМТ (наприклад, 2024) |
| `session` | VARCHAR(50) | Назва сесії (наприклад, `main`, `additional`) |
| `q_number` | INTEGER | Номер питання в тесті (1–30 для hist, 1–N для решти) |
| `image_file_id` | VARCHAR(255) nullable | Legacy: file_id першого зображення |
| `images` | JSONB nullable | Список Telegram file_id всіх зображень питання |
| `q_type` | VARCHAR(50) | Тип: `choice`, `short`, `match` |
| `correct_answer` | JSONB | Правильна відповідь (структура залежить від типу) |
| `weight` | INTEGER | Вага питання (для match — кількість пар, інакше 1) |
| `explanation` | TEXT nullable | AI-пояснення від Gemini (кешується тут) |
| `categories` | JSONB nullable | Список slugs категорій від Gemini |

**Структура `correct_answer` за типом:**

```json
// choice
{"answer": "А", "options": "5"}

// short
{"answer": "4.5"}

// match
{"pairs": {"1": "А", "2": "Б", "3": "В"}, "options": "АБВГД"}
```

**Призначення:** Весь навчальний контент. Питання ідентифікуються унікально за `(subject, year, session, q_number)`.

**Ключові методи `QuestionRepo`:**
- `upsert_question()` — insert або update за унікальним ключем
- `get_questions_by_criteria(subject, year, session)` — повертає всі питання сесії, впорядковані за `q_number`
- `get_random_question(subjects, q_type)` — для daily challenge та random mode
- `get_unique_years(subject)` / `get_unique_sessions(subject, year)` — для UI вибору
- `update_explanation()` / `update_categories()` — після генерації Gemini

---

### examresults

**Файл:** `infrastructure/database/models/results.py`
**Таблиця:** `examresults`

Зберігає результат кожного завершеного simulation-тесту.

| Поле | Тип | Опис |
|------|-----|------|
| `id` | UUID PK | Унікальний ID результату |
| `user_id` | BIGINT FK → users.user_id | Юзер |
| `subject` | VARCHAR(50) | Предмет |
| `year` | INTEGER | Рік НМТ |
| `session` | VARCHAR(50) | Назва сесії |
| `raw_score` | INTEGER | Сирий бал (сума очок за питання) |
| `nmt_score` | INTEGER | Бал за шкалою 100–200 (0 якщо не склав) |
| `duration` | INTEGER | Час виконання в секундах |
| `created_at` | TIMESTAMP | Коли завершено тест |

**Призначення:** Статистика прогресу юзера, попередні спроби, передбачення балу (bakalavr calculator).

**Ключові запити:**
- `get_completed_sessions(user_id, subject, year)` — список сесій, які юзер уже пройшов (для мітки ✅)
- `get_last_session_result(user_id, subject, session)` — попередній результат по конкретній сесії

---

### randomresults

**Файл:** `infrastructure/database/models/random_results.py`
**Таблиця:** `randomresults`

Зберігає кожну спробу відповіді в random-режимі.

| Поле | Тип | Опис |
|------|-----|------|
| `id` | UUID PK | Унікальний ID |
| `user_id` | BIGINT FK → users.user_id | Юзер |
| `subject` | VARCHAR(50) | Предмет |
| `question_id` | INTEGER | ID питання |
| `points` | INTEGER DEFAULT 1 | Нараховані бали |
| `created_at` | TIMESTAMP | Коли відповів |

**Призначення:** Лічильник балів у random-режимі, статистика по темах.

---

### useractionlogs

**Файл:** `infrastructure/database/models/logs.py`
**Таблиця:** `useractionlogs`

Детальний лог кожної відповіді юзера у simulation і random режимах.

| Поле | Тип | Опис |
|------|-----|------|
| `id` | BIGINT PK autoincrement | ID запису |
| `user_id` | BIGINT | Telegram user ID |
| `question_id` | BIGINT | ID питання |
| `answer` | VARCHAR(500) nullable | Текст відповіді юзера (для match — "1-А, 2-Б, 3-В") |
| `is_correct` | BOOLEAN DEFAULT false | Чи правильна відповідь |
| `mode` | VARCHAR(50) DEFAULT 'random' | `random` або `simulation` |
| `session_id` | VARCHAR(100) nullable | Ідентифікатор сесії симуляції (наприклад `main`) |
| `created_at` | TIMESTAMP | Коли відповів |

**Призначення:** Аналітика помилок, перегляд попередніх відповідей, функція "у цій сесії ти вже припускався помилок на питаннях X, Y, Z".

**Ключові запити:**
- `get_failed_questions_in_last_sim(user_id, session_id)` — для попередження перед симуляцією
- `add_logs_batch(logs_data)` — batch insert після завершення тесту

---

### settings

**Файл:** `infrastructure/database/models/settings.py`
**Таблиця:** `settings`

Таблиця типу key-value для конфігурації бота, що змінюється в рантаймі.

| Поле | Тип | Опис |
|------|-----|------|
| `key` | VARCHAR(50) PK | Унікальний ключ |
| `value` | VARCHAR(512) | Значення (завжди рядок) |

**Відомі ключі:**

| Ключ | Тип значення | Призначення |
|------|-------------|-------------|
| `maintenance_mode` | `"true"` / `"false"` | Режим ТО |
| `maintenance_message` | HTML-рядок | Повідомлення під час ТО |
| `daily_enabled` | `"true"` / `"false"` | Чи активний daily challenge |
| `last_lottery_run` | `"YYYY-MM-DD"` | Дата останнього запуску лотереї |
| `daily_lottery_status` | рядок | Статус лотереї: `WIN (HH:MM)`, `LOSS`, `MISS (Day Over)` |
| `gemini_api_key` | рядок | API ключ Gemini (пріоритет над `.env`) |

**Призначення:** Дозволяє змінювати поведінку бота без рестарту через адмінку.

---

### joinstats

**Файл:** `infrastructure/database/models/stats.py`
**Таблиця:** `joinstats`

Відслідковує джерела приходу нових юзерів (UTM-мітки).

| Поле | Тип | Опис |
|------|-----|------|
| `id` | BIGINT PK autoincrement | ID запису |
| `user_id` | BIGINT | Telegram user ID |
| `source` | VARCHAR(255) DEFAULT 'unknown' | UTM-джерело (наприклад, `instagram_bio`) |
| `created_at` | TIMESTAMP | Коли вступив |

**Призначення:** Аналітика ефективності рекламних каналів.

---

### pendingjoinrequests

**Файл:** `infrastructure/database/models/join_requests.py`
**Таблиця:** `pendingjoinrequests`

Черга заявок на вступ до каналу/групи, які очікують авто-схвалення.

| Поле | Тип | Опис |
|------|-----|------|
| `user_id` | BIGINT PK | Telegram user ID |
| `chat_id` | BIGINT PK | ID каналу/групи |
| `created_at` | TIMESTAMP | Коли надійшла заявка |

Складений первинний ключ `(user_id, chat_id)` — один юзер може подати заявку до різних чатів.

**Призначення:** APScheduler кожну хвилину перевіряє заявки старші 3 хвилин і схвалює їх через `bot.approve_chat_join_request`.

---

### subjectmaterials

**Файл:** `infrastructure/database/models/materials.py`
**Таблиця:** `subjectmaterials`

Довідкові матеріали (шпаргалки) для кожного предмета — відображаються під час симуляції.

| Поле | Тип | Опис |
|------|-----|------|
| `subject` | VARCHAR(50) PK | Slug предмета |
| `images` | JSONB DEFAULT [] | Список Telegram file_id зображень |

**Призначення:** Адмін завантажує зображення-шпаргалки. Юзер може розгорнути їх під час симуляції кнопкою "Довідкові матеріали".

---

## Індекси

Всі індекси додані міграцією `b2c3d4e5f6a7` (performance indexes).

| Назва індексу | Таблиця | Колонки | Призначення |
|---------------|---------|---------|-------------|
| `ix_useractionlogs_user_question` | `useractionlogs` | `(user_id, question_id)` | Пошук помилок юзера по конкретному питанню, підрахунок кількості спроб |
| `ix_useractionlogs_session_id` | `useractionlogs` | `(session_id)` | Пошук всіх логів симуляційної сесії (наприклад, `get_failed_questions_in_last_sim`) |
| `ix_examresults_user_subject` | `examresults` | `(user_id, subject)` | Статистика юзера по предмету, відображення прогресу |
| `ix_questions_subject_year_session` | `questions` | `(subject, year, session)` | Завантаження питань сесії (`get_questions_by_criteria`) — найчастіший запит |
| `ix_randomresults_user_subject` | `randomresults` | `(user_id, subject)` | Агрегація балів юзера в random-режимі по предмету |

**Первинні ключі** (автоматично індексуються PostgreSQL):
- `users.user_id`
- `questions.id`
- `examresults.id`
- `randomresults.id`
- `useractionlogs.id`
- `settings.key`
- `joinstats.id`
- `pendingjoinrequests.(user_id, chat_id)` — складений PK
- `subjectmaterials.subject`

---

## Міграції

### Поточний ланцюжок

```
None
  ↓
343bb188ff78   Create users table
               (user_id, username, full_name, active, language, created_at)
  ↓
6de8e23ae988   Add question + result tables
               (questions, examresults, randomresults, useractionlogs,
                joinstats, pendingjoinrequests, settings, subjectmaterials)
  ↓
7f3e1a2b3c4d   Add images column
               questions.images (JSONB) — список file_id замість одного
  ↓
8a4b2c3d4e5f   Add explanation column
               questions.explanation (TEXT) + questions.categories (JSONB)
  ↓
9b5c3d4e5f6a   Add daily_sub column
               users.daily_sub (BOOLEAN DEFAULT true)
               users.selected_subject (VARCHAR DEFAULT 'math')
               users.is_admin (BOOLEAN DEFAULT false)
               users.updated_at (TIMESTAMP)
  ↓
a1b2c3d4e5f6   Add user settings
               users.settings (JSONB DEFAULT '{}')
  ↓
b2c3d4e5f6a7   Add performance indexes  ← HEAD
               5 індексів (описані в розділі "Індекси")
```

### Створення нової міграції

```bash
# Autogenerate (порівнює Python-моделі зі станом БД)
alembic revision --autogenerate -m "add_new_column"

# Вручну (порожній шаблон)
alembic revision -m "custom_migration"
```

Файли зберігаються у `infrastructure/migrations/versions/`.

### Застосування

```bash
# До останньої ревізії
alembic upgrade head

# До конкретної ревізії
alembic upgrade b2c3d4e5f6a7
```

### Відкат

```bash
# Один крок назад
alembic downgrade -1

# До конкретної ревізії
alembic downgrade 343bb188ff78
```

### У продакшені (через Docker)

```bash
docker compose run --rm bot alembic upgrade head
```

`deploy.sh` виконує це автоматично при кожному деплої. Якщо міграція падає, скрипт намагається `alembic stamp 6de8e23ae988 && upgrade head` (виправлення desync стану).
