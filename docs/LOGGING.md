# NMT-Bot — Документація системи логування

## Архітектура

Система логування складається з **чотирьох незалежних таблиць**, кожна для свого типу даних. Жодне логування не блокує основний потік — всі записи відбуваються в межах тієї ж транзакції middleware і не кидають виняток назовні.

```
Подія користувача
       │
       ▼
DatabaseMiddleware (відкриває session)
       │
       ├──▶ Handler / Dialog handler
       │         │
       │         ├──▶ repo.logs.add_log()           → UserActionLog
       │         ├──▶ repo.results.save_result()     → ExamResult
       │         ├──▶ repo.events.log_event()        → UserEvent   (fire-and-forget)
       │         ├──▶ repo.audit.log_action()        → AdminAuditLog (fire-and-forget)
       │         └──▶ repo.daily_participation.*     → DailyParticipation
       │
       ▼
session.commit()  ← єдиний commit у всьому стеку
```

**Фоновий виняток:** `services/daily.py` (APScheduler) запускається поза middleware — відкриває власну сесію і самостійно робить `commit` після batch-вставки `DailyParticipation`.

---

## Таблиці

---

### 1. `useractionlogs` — Відповіді користувачів

**Модель:** `infrastructure/database/models/logs.py` → `UserActionLog`
**Репо:** `infrastructure/database/repo/logs.py` → `LogsRepo`
**Доступ:** `repo.logs`

#### Структура

| Колонка | Тип | Опис |
|---|---|---|
| `id` | BIGINT PK | Автоінкремент |
| `user_id` | BIGINT | Telegram ID користувача |
| `question_id` | BIGINT | ID питання з таблиці `questions` |
| `answer` | VARCHAR(500) | Відповідь: літера (А/Б/В), число, або пари (match) |
| `is_correct` | BOOLEAN | Чи правильна відповідь |
| `mode` | VARCHAR(50) | `"random"` або `"simulation"` |
| `session_id` | VARCHAR(100) | Лише для simulation: `"math_2024_main"` |
| `created_at` | TIMESTAMP | Час запису (server_default) |

#### Де записується

| Місце | Метод | Коли |
|---|---|---|
| `tgbot/dialogs/random_mode.py` | `repo.logs.add_log(mode="random")` | При кожній відповіді в Random-режимі |
| `tgbot/services/simulation_service.py` | `repo.logs.add_logs_batch(mode="simulation")` | При завершенні симуляції (batch insert всіх відповідей) |

#### Що рахується на основі цих даних

- **Топ-10 найскладніших питань** (`get_hardest_questions`) — GROUP BY question_id WHERE is_correct=False
- **Покинуті симуляції** (`get_abandoned_stats`) — DISTINCT (user_id, session_id) vs ExamResult
- **Кількість відповідей по предметах** (`get_daily_activity_stats`)
- **Помилки конкретного юзера** по конкретному питанню

---

### 2. `examresults` — Результати іспитів

**Модель:** `infrastructure/database/models/results.py` → `ExamResult`
**Репо:** `infrastructure/database/repo/results.py` → `ResultRepo`
**Доступ:** `repo.results`

#### Структура

| Колонка | Тип | Опис |
|---|---|---|
| `id` | UUID PK | UUID v4 |
| `user_id` | BIGINT FK → users | Telegram ID |
| `subject` | VARCHAR(50) | `math`, `mova`, `hist`, `eng`, `physics` |
| `year` | INTEGER | Рік ЗНО/НМТ |
| `session` | VARCHAR(50) | Назва сесії (`main`, `additional`, тощо) |
| `raw_score` | INTEGER | Сира сума балів |
| `nmt_score` | INTEGER | Бал за шкалою НМТ (конвертований) |
| `duration` | INTEGER | Час проходження у секундах |
| `created_at` | TIMESTAMP | Час завершення |

#### Де записується

| Місце | Коли |
|---|---|
| `tgbot/services/simulation_service.py` → `finish_simulation()` | Автоматично при завершенні симуляції (всі питання відповідані або час вийшов) |

---

### 3. `userevents` — Поведінкові події користувачів

**Модель:** `infrastructure/database/models/events.py` → `UserEvent`
**Репо:** `infrastructure/database/repo/events.py` → `EventRepo`
**Доступ:** `repo.events`

Загальна таблиця для всіх подій, що не вписуються в структуровані таблиці. Гнучка: `event_type` + JSON `payload`.

#### Структура

| Колонка | Тип | Опис |
|---|---|---|
| `id` | BIGINT PK | Автоінкремент |
| `user_id` | BIGINT | Telegram ID |
| `event_type` | VARCHAR(50) | Тип події (рядок) |
| `payload` | TEXT | JSON-рядок з контекстом або NULL |
| `created_at` | TIMESTAMP | Час (indexed) |

#### Повний список event_type

| event_type | Де записується | payload |
|---|---|---|
| `simulation_started` | `tgbot/dialogs/simulation.py` → `on_session_selected()` | `{subject, year, session, q_count}` |
| `calculator_opened` | `tgbot/dialogs/main_menu.py` → `on_calc()` | NULL |
| `calc_spec_selected` | `tgbot/dialogs/calculator.py` → `on_spec_selected()` | `{spec}` |
| `kse_question_sent` | `tgbot/dialogs/calculator.py` → `on_kse_question_sent()` | NULL |
| `explanation_viewed` | `tgbot/dialogs/random_mode.py` → `on_show_explanation()` | `{question_id}` |
| `subject_changed` | `tgbot/dialogs/main_menu.py` → `on_subject_selected()` | `{subject}` |
| `stats_viewed` | `tgbot/dialogs/main_menu.py` → `on_stats()` | NULL |
| `daily_answered` | `tgbot/handlers/daily.py` → `on_daily_answer()` (кнопка) | `{question_id, answer, is_correct, via: "button"}` |
| `daily_text_answered` | `tgbot/dialogs/daily.py` → `check_answer()` | `{question_id, is_correct}` |
| `daily_show_answer` | `tgbot/handlers/daily.py` → `on_daily_answer()` (SHOW_ANSWER) | `{question_id}` |
| `daily_sub_toggled` | `tgbot/dialogs/stats.py` → `on_toggle_daily_sub()` | `{new_value: bool}` |
| `feedback_submitted` | `tgbot/dialogs/stats.py` → `on_feedback_input()` | `{length: int}` |
| `user_registered` | `tgbot/handlers/join_request.py` | `{source}` |

#### Патерн запису (fire-and-forget)

```python
try:
    await repo.events.log_event(user.user_id, "event_type", {"key": "value"})
except Exception:
    pass  # ніколи не ламає основний флоу
```

В `EventRepo.log_event()` вже є внутрішній try/except — виняток не підніметься до хендлера.

---

### 4. `adminauditlogs` — Аудит дій адміністраторів

**Модель:** `infrastructure/database/models/audit.py` → `AdminAuditLog`
**Репо:** `infrastructure/database/repo/audit.py` → `AuditRepo`
**Доступ:** `repo.audit`

#### Структура

| Колонка | Тип | Опис |
|---|---|---|
| `id` | BIGINT PK | Автоінкремент |
| `admin_id` | BIGINT | Telegram ID адміна (indexed) |
| `action` | VARCHAR(100) | Код дії |
| `target_id` | VARCHAR(255) | ID об'єкта дії або NULL |
| `details` | TEXT | Деталі або NULL |
| `created_at` | TIMESTAMP | Час (indexed) |

#### Повний список action

| action | Де записується | target_id | details |
|---|---|---|---|
| `promote_admin` | `dashboard.py` → `on_add_admin()` | user_id | full_name |
| `demote_admin` | `dashboard.py` → `on_demote_admin()` | user_id | NULL |
| `export_all_logs_zip` | `dashboard.py` → `on_export_all_zip()` | NULL | NULL |
| `question_uploaded` | `upload.py` → `_handle_single_photo()` | `"math_2024_main_Q5"` | `"single"` |
| `bulk_upload_started` | `upload.py` → `on_bulk_upload()` | NULL | filename.zip |
| `question_deleted` | `question_detail.py` → `on_delete_q()` | question_id | NULL |
| `question_edit_started` | `question_detail.py` → `on_edit_q()` | question_id | NULL |
| `explanation_regen_started` | `question_detail.py` → `on_regenerate_explanation()` | question_id | NULL |
| `session_deleted` | `content.py` → `on_confirm_delete_session()` | `"math_2024_main"` | NULL |
| `session_year_changed` | `content.py` → `on_change_session_year()` | `"math_main"` | `"2024 → 2023"` |
| `session_name_changed` | `content.py` → `on_change_session_name()` | `"math_2024"` | `"old → new"` |
| `onboarding_video_updated` | `settings.py` → `on_update_video()` | NULL | NULL |
| `join_requests_approved` | `settings.py` → `on_approve_all()` | NULL | `"approved=50 of 52"` |
| `gemini_key_updated` | `settings.py` → `on_update_gemini_key()` | NULL | NULL |
| `gemini_key_deleted` | `settings.py` → `on_delete_gemini_key()` | NULL | NULL |
| `daily_toggled` | `daily.py` → `on_toggle_daily()` | NULL | `"new_value=true"` |
| `daily_force_sent` | `daily.py` → `on_force_daily()` | NULL | NULL |
| `broadcast_sent` | `broadcasting.py` → `start_broadcast()` | target_type | `"sent=5000,blocked=120,errors=3"` |

---

### 5. `dailyparticipations` — Daily Challenge

**Модель:** `infrastructure/database/models/daily_participation.py` → `DailyParticipation`
**Репо:** `infrastructure/database/repo/daily_participation.py` → `DailyParticipationRepo`
**Доступ:** `repo.daily_participation`

#### Структура

| Колонка | Тип | Опис |
|---|---|---|
| `id` | BIGINT PK | Автоінкремент |
| `user_id` | BIGINT | Telegram ID (indexed) |
| `question_id` | BIGINT | ID питання |
| `subject` | VARCHAR(50) | Предмет (`math`, `mova`, `hist`) |
| `date` | DATE | Дата розсилки (indexed) |
| `sent_at` | TIMESTAMP | Час доставки |
| `answered_at` | TIMESTAMP | Час відповіді або NULL |
| `answer` | VARCHAR(500) | Відповідь або NULL |
| `is_correct` | BOOLEAN | NULL якщо не відповів |

**Unique constraint:** `(user_id, date)` — один запис на юзера на день (idempotent re-send).

#### Де записується

| Подія | Метод | Де |
|---|---|---|
| Розсилка відбулась | `record_sent()` (batch) | `tgbot/services/daily.py` → `broadcast_daily_question()` — у фоновій задачі зі своєю сесією |
| Відповідь через кнопку | `record_answer()` | `tgbot/handlers/daily.py` → `on_daily_answer()` |
| Відповідь текстом | `record_answer()` | `tgbot/dialogs/daily.py` → `check_answer()` |

---

## Де переглядати дані

### В адмінці (реалтайм)

| Розділ | Шлях | Що показує |
|---|---|---|
| Статистика бота | Адмінка → 📊 Статистика | Всі агреговані метрики за сьогодні |
| Аудит лог | Статистика → 🗂 Аудит | Останні 20 дій адмінів |
| Топ складних | Статистика → 🔴 Топ складних | Топ-10 питань за кількістю помилок |

### ZIP-експорт (одна кнопка)

**Статистика → 📦 Все (ZIP)** — завантажує архів з 5 CSV:

```
nmt_all_logs_YYYYMMDD_HHMM.zip
├── user_action_logs.csv       ← UserActionLog
├── exam_results.csv           ← ExamResult
├── admin_audit_log.csv        ← AdminAuditLog
├── user_events.csv            ← UserEvent
└── daily_participation.csv    ← DailyParticipation
```

---

## Важливі правила

1. **Жодне логування не робить `session.commit()`** — це виключне право `DatabaseMiddleware`.
2. **`log_event()` і `log_action()` — fire-and-forget**: внутрішній try/except гарантує, що помилка в логуванні ніколи не зламає основний флоу.
3. **`DailyParticipation.record_sent()`** — єдиний виняток з правила: викликається у фоновій задачі `broadcast_daily_question()`, яка сама керує сесією і робить `commit`.
4. **`ON CONFLICT DO NOTHING`** на `(user_id, date)` в `DailyParticipation` — повторна розсилка того ж дня не дублює запис.
