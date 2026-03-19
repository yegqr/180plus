# Архітектура NMT-bot

## Загальна схема

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Telegram Platform                             │
│                    (повідомлення / callback-и)                       │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ HTTP long polling
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   aiogram Dispatcher                                 │
│              (bot.py → dp.start_polling)                            │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Middleware Pipeline (outer)                        │
│                                                                      │
│  1. ConfigMiddleware      — вставляє Config у data["config"]        │
│  2. DatabaseMiddleware    — відкриває сесію, upsert юзера,          │
│                             комітить після хендлера                  │
│  3. TopicRoutingMiddleware — визначає selected_subject за thread_id  │
│  4. MaintenanceMiddleware — блокує звичайних юзерів під час ТО      │
│                                                                      │
│                   Middleware Pipeline (inner)                        │
│  5. EnsureTopicsMiddleware — створює форум-топіки, якщо їх нема     │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
          ┌───────────┴────────────┐
          ▼                        ▼
┌──────────────────┐    ┌──────────────────────────────────────┐
│  Regular Handlers │    │     aiogram-dialog Dialogs           │
│  (tgbot/handlers) │    │   (tgbot/dialogs/*)                  │
│                   │    │                                      │
│  - user.py        │    │  SimulationSG / RandomSG             │
│  - admin.py       │    │  AdminSG / MainMenuSG                │
│  - daily.py       │    │  StatsS G / BroadcastSG              │
│  - join_request.py│    │  CalculatorSG / DailySG              │
│  - error.py       │    │  SubjectMenuSG                       │
└─────────┬─────────┘    └──────────────┬───────────────────── ┘
          │                             │
          └──────────────┬──────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Services Layer                                   │
│                                                                      │
│  scoring.py         — чиста логіка підрахунку балів                 │
│  simulation_service.py — оркестрація завершення симуляції           │
│  gemini.py          — виклики Google Gemini API                     │
│  bulk_upload.py     — обробка ZIP-архівів з питаннями               │
│  broadcaster.py     — масові Telegram-розсилки                      │
│  daily.py           — логіка daily challenge                        │
│  scheduler.py       — APScheduler (лотерея, авто-approve)          │
│  topic_manager.py   — створення Telegram форум-топіків             │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Repository Pattern                                 │
│                                                                      │
│  RequestsRepo (facade)                                               │
│    .users      → UserRepo                                           │
│    .questions  → QuestionRepo                                       │
│    .results    → ResultRepo                                         │
│    .settings   → SettingsRepo                                       │
│    .logs       → LogsRepo                                           │
│    .stats      → StatsRepo                                          │
│    .join_requests → JoinRequestsRepo                                │
│    .materials  → MaterialRepo                                       │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ SQLAlchemy AsyncSession
          ┌───────────┼───────────┐
          ▼           ▼           ▼
    PostgreSQL      Redis       Google
    (основна БД)  (FSM-сховище, (Gemini API —
                   APScheduler   пояснення)
                   jobstore)
```

---

## Middleware Pipeline

Всі мідлвари реєструються у `bot.py` → `register_global_middlewares()`. Порядок виконання фіксований і критично важливий — кожен наступний мідлвар отримує `data`, вже збагачений попереднім.

### 1. ConfigMiddleware

**Файл:** `tgbot/middlewares/config.py`

Найпростіший мідлвар. Ін'єктує об'єкт `Config` (зчитаний із `.env` при старті) у `data["config"]`. Не виконує жодних I/O операцій. Реєструється першим, бо `DatabaseMiddleware` читає `config.tg_bot.admin_ids` ще до виклику хендлера.

```python
data["config"] = self.config
return await handler(event, data)
```

### 2. DatabaseMiddleware

**Файл:** `tgbot/middlewares/database.py`

Центральний мідлвар транзакційного контексту:

1. Відкриває `AsyncSession` через `async_sessionmaker`.
2. Виконує upsert поточного юзера (`INSERT … ON CONFLICT DO UPDATE`) і записує результат у `data["user"]`.
3. Кладе `session` і `repo` (екземпляр `RequestsRepo`) у `data`.
4. Викликає хендлер у блоці `try/except`.
5. **Після успішного повернення хендлера — `await session.commit()`**.
6. При будь-якому виключенні — `await session.rollback()`.

Це єдина точка коміту в запиті (окрім фонових завдань, які мають власну сесію).

### 3. TopicRoutingMiddleware

**Файл:** `tgbot/middlewares/topic_routing.py`

Telegram супер-групи з форумами мають `message_thread_id` у кожному повідомленні. Цей мідлвар перевіряє: якщо `thread_id` збігається з одним із `user.settings["topic_ids"]`, то `user.selected_subject` оновлюється відповідним предметом (in-memory, без DB write). Це дозволяє розпізнавати контекст відповіді без явного вибору предмета.

### 4. MaintenanceMiddleware

**Файл:** `tgbot/middlewares/maintenance.py`

Блокує доступ до бота під час технічних робіт:

- Читає налаштування `maintenance_mode` з таблиці `settings` **не частіше ніж раз на 30 секунд** (TTL-кеш на основі `time.monotonic()`).
- Якщо режим активний — перевіряє, чи є поточний юзер адміном. Адміни пропускаються.
- Звичайному юзеру повертається повідомлення з `settings["maintenance_message"]` або fallback-текст.
- Для `CallbackQuery` використовується `answer(show_alert=True)`.
- Повертає `None` (зупиняє propagation) без виклику хендлера.

### 5. EnsureTopicsMiddleware

**Файл:** `tgbot/middlewares/ensure_topics.py`

Реєструється як **inner**-мідлвар (після outer-ів). Перевіряє, чи є у юзера `settings["topic_ids"]`. Якщо ні — викликає `TopicManager.ensure_topics()`, що синхронно (в рамках поточного event loop) створює форум-топіки у чаті супер-групи і записує їх ID у `user.settings`. Гарантує, що хендлер вже матиме готові топіки.

---

## Dialog Architecture (aiogram-dialog)

Бот використовує бібліотеку `aiogram-dialog` для реалізації складних багатоекранних UI.

### FSM + State Groups

Кожен діалог визначає власну `StatesGroup`:

```python
class SimulationSG(StatesGroup):
    select_year    = State()
    select_session = State()
    question       = State()
    summary        = State()
    review         = State()
    navigation     = State()
```

FSM-стан зберігається в Redis (або MemoryStorage при `USE_REDIS=False`) і прив'язаний до `(user_id, bot_id)`.

### Window + Getter

Кожен `State` відповідає одному `Window`. `Window` приймає:
- **Widgets** — `Format`, `Const`, `Button`, `Select`, `DynamicMedia`, `MessageInput`.
- **getter** — async-функція, що повертає `dict` з даними для рендерингу.

Getter викликається при кожному відображенні вікна і отримує `dialog_manager` як аргумент. Доступ до репозиторію і юзера через `dialog_manager.middleware_data`:

```python
async def get_sim_years(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    years = await repo.questions.get_unique_years(user.selected_subject)
    return {"years": [(str(y), y) for y in years]}
```

### dialog_data vs DB data

| | `dialog_manager.dialog_data` | База даних |
|---|---|---|
| Де живе | In-memory + FSM-сховище (Redis) | PostgreSQL |
| Коли зникає | При `dm.done()` або рестарті бота | Ніколи |
| Що зберігати | Тимчасовий стан сесії: `q_ids`, `answers`, `current_index`, `start_time` | Фінальні результати: `ExamResult`, `UserActionLog` |
| Приклад | `dm.dialog_data["sim_year"] = 2024` | `await repo.results.save_result(...)` |

---

## Repository Pattern

### Ієрархія

```
BaseRepo
    └── UserRepo
    └── QuestionRepo
    └── ResultRepo
    └── SettingsRepo
    └── LogsRepo
    └── StatsRepo
    └── JoinRequestsRepo
    └── MaterialRepo

RequestsRepo (dataclass-facade)
    session: AsyncSession
    .users      → UserRepo(self.session)
    .questions  → QuestionRepo(self.session)
    ...
```

`BaseRepo` — просто тримає `AsyncSession`. Всі конкретні репо успадковують від нього.

`RequestsRepo` — dataclass-facade, що lazy-ін'єктує репо через `@property`. Кожен `property` створює новий екземпляр відповідного репо з **тією самою сесією**.

### Доступ з хендлерів

З regular handlers:
```python
async def my_handler(message: Message, repo: RequestsRepo, user: User):
    result = await repo.questions.get_unique_years(user.selected_subject)
```

З aiogram-dialog getters:
```python
repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
```

---

## Transaction Boundary

**КРИТИЧНО:** Бот побудований на принципі **одна транзакція на один запит**.

### Правило

- `DatabaseMiddleware` відкриває сесію і комітить її **після повернення хендлера**.
- Жоден репо-метод не викликає `session.commit()` або `session.rollback()`.
- Хендлери та сервіси виконують INSERT/UPDATE/DELETE через сесію — всі зміни буферизуються в пам'яті SQLAlchemy.
- Коміт відбувається рівно один раз.

### Виняток: фонові завдання

Фонові задачі (`asyncio.create_task`, APScheduler jobs) **не мають доступу до сесії хендлера** — вона до того моменту вже закрита. Вони відкривають власну сесію і самостійно комітять:

```python
# BulkUploadService._gemini_task
async with self.bot.session_pool() as session:
    q_repo = QuestionRepo(session)
    await q_repo.update_explanation(target_q.id, explanation)
    await session.commit()  # <-- фонова задача комітить сама
```

### Візуалізація

```
Request →─────────────────────────────────────────────→ Response
          │                                          │
          │ DatabaseMiddleware.__call__              │
          │   async with session_pool() as session: │
          │     repo = RequestsRepo(session)         │
          │     user = await repo.users.upsert(...)  │
          │     ┌──── await handler(event, data) ────┤
          │     │   handler calls repo.xxx.yyy()     │
          │     │   service calls repo.zzz.www()     │
          │     └───────────────────────────────────┤
          │     await session.commit()  ◄── один раз│
          └──────────────────────────────────────────┘
```

---

## Simulation Flow

Повний цикл симуляції НМТ:

### Крок 1: Вибір року

- **State:** `SimulationSG.select_year`
- **Getter:** `get_sim_years()` → `repo.questions.get_unique_years(subject)`
- **Handler:** `on_year_selected()` → зберігає `dm.dialog_data["sim_year"]`, переходить до `select_session`

### Крок 2: Вибір сесії

- **State:** `SimulationSG.select_session`
- **Getter:** `get_sim_sessions()` → `repo.questions.get_unique_sessions(subject, year)` + `repo.results.get_completed_sessions(user_id, subject, year)` (для мітки ✅)
- **Handler:** `on_session_selected()`:
  - Завантажує `repo.questions.get_questions_by_criteria(subject, year, session)`
  - Зберігає `q_ids`, `start_time`, порожній `answers` dict у `dialog_data`
  - Перевіряє `repo.logs.get_failed_questions_in_last_sim(user_id, session)` — якщо є помилки з минулого разу, попереджає юзера
  - Переходить до `question`

### Крок 3: Цикл питань

- **State:** `SimulationSG.question`
- **Getter:** `get_question_data()` → `repo.questions.get_question_by_id(current_id)` + `repo.materials.get_by_subject(subject)`
- **Handlers:**
  - `on_choice_selected()` → `dm.dialog_data["answers"][str(q_id)] = "А"`
  - `on_match_num_selected()` / `on_match_letter_selected()` → накопичує пари
  - `on_answer_text()` → зберігає текстову відповідь (для short-type)
  - `on_next()` / `on_prev()` → `update_question_view(dm, idx±1)`

### Крок 4: Завершення і підрахунок балів

- **Handler:** `on_finish()`:
  1. Фіксує `end_time`
  2. Викликає `finish_simulation(repo, user, q_ids, answers, session_id, year, ...)`
  3. `finish_simulation` → `score_simulation()` (чиста функція) → повертає `SimulationScore`
  4. `repo.results.save_result(...)` — зберігає `ExamResult`
  5. `repo.logs.add_logs_batch(logs_data)` — зберігає `UserActionLog` для кожної відповіді
  6. Результати записуються у `dialog_data`, перехід до `summary`

### Крок 5: Підсумок

- **State:** `SimulationSG.summary`
- **Getter:** `get_summary_data()`:
  - Читає pre-calculated scores з `dialog_data`
  - `repo.questions.get_questions_by_ids(answered_ids)` — batch-запит
  - `repo.results.get_last_session_result(user_id, subject, session)` — попередня спроба
  - Формує список помилок через `is_answer_correct_for_display()`

### Крок 6: Перегляд відповідей (опційно)

- **State:** `SimulationSG.review`
- **Getter:** `get_review_data()` → `repo.questions.get_question_by_id(current_id)`
- Показує `question.explanation` (з кешу в БД), якщо воно є

---

## Scoring System

### Функція `check_simulation_answer()`

**Файл:** `tgbot/services/scoring.py`

Диспетчеризує за `subject`:

#### Стандартні предмети (math, mova, eng, physics тощо)

| q_type | Логіка | Макс балів |
|--------|--------|-----------|
| `choice` | Точне порівняння літер (case-insensitive) | 1 |
| `short` | `float`-порівняння або рядкове; для `mova`/`eng` — flexible digit set | 2 |
| `match` | 1 бал за кожну правильну пару `{num: letter}` | `len(pairs)` |

#### Історія (`hist`) — окрема логіка по `q_number`

| Номери питань | Тип | Логіка | Макс балів |
|---------------|-----|--------|-----------|
| 1–20 | `choice` | Точне порівняння | 1 |
| 21–24 | `match` | 1 бал за пару, макс 4 | 4 |
| 25–27 | sequence | 1 бал за цифру на правильній **позиції** | 3 |
| 28–30 | cluster | `len(set(correct) ∩ set(user))` | 3 |

### Функція `get_nmt_score()`

**Файл:** `tgbot/misc/nmt_scoring.py`

Конвертує сирий бал у шкалу 100–200 через lookup-таблиці `SCORING_TABLES`. Таблиці задані для кожного предмета (`ukr_mova`, `math`, `ukr_history`, `inozemna_mova`, `biology`, `physics`, `chemestry`, `georgraphy`, `ukr_lit`).

Алгоритм:
1. Якщо `raw_score <= 0` → повертає `0` (не склав, < прохідного мінімуму).
2. Пряма підстановка `int(raw_score)` в таблицю.
3. Якщо менше мінімуму таблиці → `0.0`.
4. Якщо більше максимуму → `200.0`.
5. `get_nmt_score()` повертає `int` якщо `>= 100`, інакше `None` (не склав).

---

## Gemini Integration

### GeminiService

**Файл:** `tgbot/services/gemini.py`

Клас-обгортка над `google-genai` SDK. Модель: `gemini-3-flash-preview`.

```python
class GeminiService:
    def __init__(self, api_key: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-3-flash-preview"
```

### Структура промпту

```
Question Text: {question_text}
Subject: {subject}

Ти — крутий викладач. Твій стиль — професіоналізм + гумор.
ТВОЄ ЗАВДАННЯ:
1. Пояснити розв'язання (Explanation).
2. Визначити категорію(ї) завдання (Categories).

[список категорій з CATEGORIES[subject]]

ВАЖЛИВО: Поверни ВІДПОВІДЬ ВИКЛЮЧНО У ФОРМАТІ JSON!
```

### Формат відповіді

```json
{
  "explanation": "🤡 TL;DR ...\n🚀 Розбір ...\n🧐 Чому інші - крінж?",
  "categories": ["math_equations", "math_text_problems"]
}
```

### Технічні деталі

- Виклик синхронного SDK виконується у `run_in_executor` (thread pool), щоб не блокувати event loop.
- Таймаут: 30 секунд (`asyncio.wait_for`).
- При помилці парсингу JSON повертається `{"explanation": raw_text, "categories": []}`.
- При таймауті або будь-якому винятку повертається `_EMPTY_RESULT`.

### Кешування

Результат (`explanation` + `categories`) зберігається у полях `Question.explanation` (Text) і `Question.categories` (JSONB) у БД. При повторному перегляді питання читається з БД — Gemini не викликається знову.

---

## Bulk Upload Pipeline

**Файл:** `tgbot/services/bulk_upload.py`

### ZIP-структура

```
archive.zip
├── questions.csv   (або questions.json)
└── images/
    ├── q1.jpg
    ├── q2.jpg
    └── ...
```

### Кроки обробки

#### 1. Читання метаданих (`_read_metadata`)

- Якщо є `questions.csv` — парсить через `csv.DictReader`.
- Якщо є `questions.json` — парсить через `json.load`.
- CSV-формат: `subject, year, session, q_number, q_type, answer, options, images` (через кому).
- Для `match`-типу парсить рядок `"1-А; 2-Б; 3-В"` у `{"pairs": {"1": "А", "2": "Б", "3": "В"}}`.

#### 2. Завантаження зображень у Telegram (`_upload_images`)

- Для кожного зображення: `bot.send_photo(admin_id, BufferedInputFile(bytes))` → отримує `file_id`.
- Повідомлення з фото відразу видаляється (`bot.delete_message`).
- Зберігається список `file_id` і бінарні дані (для Gemini).

#### 3. Upsert у БД (`_process_one`)

- `repo.questions.upsert_question(...)` — якщо питання вже є (за `subject+year+session+q_number`), то оновлює `images`, `q_type`, `correct_answer`. Якщо ні — створює нове.

#### 4. Фонова генерація пояснень

- `asyncio.create_task(self._gemini_task(...))` — запускається паралельно, не блокує основний цикл.
- Семафор `asyncio.Semaphore(3)` обмежує одночасні виклики Gemini до 3.
- Фонова задача відкриває **власну сесію** і сама комітить результат.

---

## Scheduler

**Файл:** `tgbot/services/scheduler.py`

### Ініціалізація

```python
scheduler = AsyncIOScheduler(jobstores=jobstores)
```

При `USE_REDIS=True` — APScheduler зберігає завдання в Redis (DB 1, окремо від FSM DB 0). Інакше — in-memory (завдання втрачаються при рестарті).

### Завдання 1: Авто-approve join requests

- **Trigger:** `interval`, кожні 60 секунд.
- **Логіка:** `check_and_approve_requests()` — `repo.join_requests.get_old_requests(minutes=3)`, схвалює через `bot.approve_chat_join_request`, видаляє з `pendingjoinrequests`.

### Завдання 2: Daily lottery

- **Trigger:** `cron`, о 7:00 UTC.
- **Логіка:** `schedule_daily_lottery()`:
  1. Перевіряє `settings["daily_enabled"]`.
  2. Перевіряє `settings["last_lottery_run"]` — не запускатись двічі на день.
  3. `random.random() >= 0.5` → 50% шанс не відправляти сьогодні.
  4. При виграші лотереї — вибирає випадковий час у вікні **8:00–22:00** через `_pick_send_time()`.
  5. Додає одноразове завдання `broadcast_daily_question` з `trigger="date"` на обраний час.
  6. Записує статус у `settings["daily_lottery_status"]`.

### Завдання 3: broadcast_daily_question

- **Trigger:** `date` (одноразово, в час, обраний лотереєю).
- **Логіка:** Вибирає випадковий предмет з `DAILY_CHALLENGE_SUBJECTS = ["math", "mova", "hist"]`, отримує рандомне `choice`-питання, розсилає всім підписникам (`daily_sub=True`, активним за тиждень).
- Відправлення через `broadcast` з затримкою `BROADCAST_SEND_DELAY = 0.05s` між повідомленнями.
