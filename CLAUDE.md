# NMT-Bot — Claude Code Instructions

## Project Overview

NMT-Bot is a Telegram bot that helps Ukrainian students prepare for the National Multi-Subject Test (НМТ / NMT). It delivers exam simulations, random-question practice, a daily challenge, AI-powered answer explanations via Google Gemini, and admin tools for content management. The bot is deployed via Docker and uses PostgreSQL for persistence and Redis for FSM storage and APScheduler job persistence.

## Tech Stack

Python 3.11+, aiogram 3, aiogram-dialog 2, SQLAlchemy 2 (async, asyncpg), PostgreSQL, Redis, Alembic, APScheduler, Google Gemini API, Docker / docker-compose.

## Project Layout

```
bot.py                          Entry point
tgbot/
  config.py                     Config dataclasses (DbConfig, TgBot, RedisConfig, Miscellaneous)
  middlewares/                  Request pipeline
  dialogs/                      aiogram-dialog FSM windows
    admin/                      Admin sub-dialogs
  handlers/                     Non-dialog event handlers
  services/                     Business logic
  misc/                         Constants, utilities, NMT scoring tables
  filters/                      Custom aiogram filters
  keyboards/                    Reply keyboards
infrastructure/
  database/
    models/                     SQLAlchemy ORM models
    repo/                       Repository layer
    setup.py                    Engine / session-pool factory
  migrations/                   Alembic migration scripts
tests/                          pytest test suite
scripts/                        Deploy and maintenance scripts
```

## Architecture Layers

### 1. Middleware (`tgbot/middlewares/`)

Outer middlewares (registered on message, callback_query, chat_join_request), applied in order:

| Middleware | Purpose |
|---|---|
| `config.py` — ConfigMiddleware | Injects `config` into handler data |
| `database.py` — DatabaseMiddleware | Opens session, creates `RequestsRepo`, upserts user, **commits on success / rolls back on exception** |
| `topic_routing.py` — TopicRoutingMiddleware | Routes user to the correct forum topic based on their subject preference |
| `maintenance.py` — MaintenanceMiddleware | Blocks non-admin users when maintenance mode is on (cached 30 s) |

Inner middleware (registered after outer):

| Middleware | Purpose |
|---|---|
| `ensure_topics.py` — EnsureTopicsMiddleware | Lazily creates missing forum topics before the handler runs |

### 2. Dialogs (`tgbot/dialogs/`)

aiogram-dialog FSM windows. Each file defines a `StatesGroup` inline and exports a `Dialog` instance.

| File | Dialog | States |
|---|---|---|
| `simulation.py` | `simulation_dialog` | SimulationSG: select_year, select_session, question, summary, review, navigation |
| `random_mode.py` | `random_dialog` | RandomModeSG |
| `daily.py` | `daily_dialog` | DailySG |
| `stats.py` | `stats_dialog` | StatsSG |
| `broadcasting.py` | `broadcast_dialog` | BroadcastSG |
| `main_menu.py` | `main_menu_dialog` | MainMenuSG |
| `subject_menu.py` | `subject_menu_dialog` | SubjectMenuSG |
| `calculator.py` | `calculator_dialog` | CalculatorSG |
| `admin/` | `admin_dialog` | AdminSG and sub-states |

Dialog registration order in `bot.py` matters: dialogs are included **before** regular routers so they intercept active FSM states first.

### 3. Handlers (`tgbot/handlers/`)

Non-dialog event handlers: `user.py` (start, main menu), `admin.py` (admin commands), `daily.py` (daily challenge entry), `error.py` (global error handler), `join_request.py` (chat join requests).

### 4. Services (`tgbot/services/`)

Pure or near-pure business logic, no aiogram-dialog dependencies:

| File | Purpose |
|---|---|
| `scoring.py` | **Pure synchronous** scoring functions — single source of truth for answer evaluation |
| `simulation_service.py` | `finish_simulation()` — scores + persists a completed simulation |
| `gemini.py` | GeminiService — async AI explanations via Google Gemini API |
| `bulk_upload.py` | ZIP+CSV question import with concurrent Gemini calls |
| `broadcaster.py` | Mass-send Telegram messages — chunk-based parallel sends (25 msg/chunk, 1 s between chunks ≈ 25 msg/s) |
| `daily.py` | Daily challenge lottery and broadcast logic — uses same chunk-based pattern |
| `scheduler.py` | APScheduler setup; jobs own their own sessions via `_session_pool` |
| `topic_manager.py` | Forum topic creation/management |
| `album_manager.py` | Deduplication buffer for Telegram media groups |

### 5. Repository (`infrastructure/database/repo/`)

| File | Repo class | Accessed via |
|---|---|---|
| `requests.py` | **RequestsRepo** (facade) | `middleware_data["repo"]` |
| `users.py` | UserRepo | `repo.users` |
| `questions.py` | QuestionRepo | `repo.questions` |
| `results.py` | ResultRepo | `repo.results` |
| `settings.py` | SettingsRepo | `repo.settings` |
| `stats.py` | StatsRepo | `repo.stats` |
| `logs.py` | LogsRepo | `repo.logs` |
| `materials.py` | MaterialRepo | `repo.materials` |
| `join_requests.py` | JoinRequestsRepo | `repo.join_requests` |

`RequestsRepo` exposes each sub-repo as a `@property`. New repos must be added there.

---

## Critical Rules

### Transaction Boundary (MOST IMPORTANT)

`DatabaseMiddleware` is the **sole owner of `session.commit()`** for all normal request handlers. The flow is:

```
outer middleware opens session
  → handler / dialog handler runs
  → middleware calls session.commit()   ← ONLY commit in the entire call stack
  → on exception: session.rollback()
```

- **NEVER** call `session.commit()` inside a repo method.
- **NEVER** call `session.commit()` inside a dialog handler or service function called from a dialog handler.
- **Background tasks** (scheduler jobs, broadcaster) are the only exception — they run outside the middleware stack and **must** open their own sessions via `_session_pool` and manage their own commits.

### Repository Pattern

- All DB access goes through `RequestsRepo` accessed via `data["repo"]` (injected by DatabaseMiddleware).
- Repos only issue `session.add()` and `session.execute()` — never `session.commit()`.
- Each ORM model gets its own repo class. Add it as a `@property` in `RequestsRepo`.

### Dialog Pattern

- Each dialog window has a **getter** function (named `get_{window}_data`) that returns a dict for template rendering.
- Transient dialog state (e.g., current question index, selected answers) lives in `dialog_manager.dialog_data` — stored in Redis FSM storage, not the DB.
- To persist dialog state to the DB, explicitly call repo methods inside dialog event handlers before the middleware auto-commits.
- Dialog state classes (`StatesGroup`) are defined **inline** in each dialog file, not in `tgbot/misc/states.py` (that file is currently a placeholder).

### Adding a New Feature — Checklist

1. Add the ORM model in `infrastructure/database/models/` (inherit `Base` and relevant mixins from `base.py`). Export it from `infrastructure/database/models/__init__.py`.
2. Create a migration: `alembic revision --autogenerate -m "short description"`. Review the generated file before using it.
3. Add a repo class in `infrastructure/database/repo/`. Never call `session.commit()` inside it.
4. Add a `@property` for the new repo in `infrastructure/database/repo/requests.py`.
5. Add service logic in `tgbot/services/` if the feature involves business rules or external calls.
6. If the feature needs an FSM UI, define the `StatesGroup` inline in the new dialog file in `tgbot/dialogs/`.
7. Register the new dialog in `bot.py` (before regular routers).
8. Write tests: pure functions → unit tests in a `test_*.py` file; DB interactions → integration tests using the `repo` fixture in `tests/test_repos.py` or a new `test_*.py`.

---

## Testing

```bash
python3 -m pytest -p no:warnings -q
```

**343 tests, all must pass before deploy.**

### SQLite Compatibility

Tests use in-memory SQLite via aiosqlite. `tests/conftest.py` patches the following at import time before any model import:

| PostgreSQL construct | Replacement |
|---|---|
| `postgresql.JSONB` | `sa.JSON` |
| `postgresql.insert` | `sqlite.insert` (also supports `on_conflict_do_update`) |
| `postgresql.UUID` | `_UUIDCompat` TypeDecorator (stores as `String(36)`) |
| `BIGINT` DDL | `INTEGER` (SQLite only auto-increments `INTEGER PRIMARY KEY`) |

**Do not use PostgreSQL-specific SQL features** (`DISTINCT ON`, `func.greatest`, window functions) in new code unless you add a SQLite workaround in `conftest.py`.

**UUID PK gotcha:** When inserting multiple ORM objects with UUID PKs in one test transaction, call `await session.commit()` between each `session.add()` to avoid SQLAlchemy sentinel key mismatch on SQLite.

### Fixture Reference

| Fixture | Scope | What it provides |
|---|---|---|
| `db_engine` | function | Fresh in-memory SQLite engine with schema created |
| `db_session` | function | `AsyncSession` bound to that engine |
| `repo` | function | `RequestsRepo` backed by the test session |

---

## Key Files Quick Reference

| File | Purpose |
|---|---|
| `bot.py` | Entry point: Dispatcher setup, middleware registration, dialog/router registration order |
| `tgbot/config.py` | Config dataclasses; reads from `.env` via `environs` |
| `tgbot/middlewares/database.py` | Session lifecycle, auto-commit, user upsert |
| `tgbot/dialogs/simulation.py` | Full exam simulation FSM (SimulationSG) |
| `tgbot/dialogs/random_mode.py` | Random question practice mode |
| `tgbot/services/scoring.py` | Pure scoring functions (sync, no DB, no aiogram) |
| `tgbot/services/simulation_service.py` | `finish_simulation()` — score + persist results |
| `tgbot/services/gemini.py` | GeminiService — AI answer explanations |
| `tgbot/services/bulk_upload.py` | ZIP+CSV question import |
| `tgbot/misc/constants.py` | SUBJECT_LABELS, DAILY_CHALLENGE_SUBJECTS, BROADCAST_CHUNK_SIZE/DELAY, all shared constants |
| `tgbot/misc/nmt_scoring.py` | NMT score conversion tables |
| `infrastructure/database/repo/requests.py` | RequestsRepo facade |
| `infrastructure/database/setup.py` | `create_engine()`, `create_session_pool()` |
| `tests/conftest.py` | SQLite compatibility patches + shared fixtures |

---

## Domain Reference

### Subject Slugs

Used as keys throughout the codebase (DB, constants, dialogs):

`math`, `mova`, `hist`, `eng`, `physics`

Daily challenge subjects (subset): `math`, `mova`, `hist`

### Question Types

| Type | Answer format | Points |
|---|---|---|
| `choice` | Single letter (А/Б/В/Г/Д) | 1 point |
| `short` | Numeric or text string | 2 points |
| `match` | Dict of pair mappings | 1 point per correct pair |
| `sequence` | Ordered list | 1 point per correct position |

### Naming Conventions

- **Repo methods:** `verb_noun` — `get_user_by_id`, `save_result`, `update_materials`
- **Dialog getters:** `get_{window_name}_data`
- **Dialog handlers:** `on_{action}` — `on_subject_selected`, `on_answer_submitted`
- **State classes:** `{DialogName}SG` with states named after what the window shows — `SimulationSG.question`, `AdminSG.menu`

---

## Broadcast Rate Limiting

`broadcaster.py` and `daily.py` use **chunk-based parallel sends** instead of sequential:

- `BROADCAST_CHUNK_SIZE = 25` — concurrent sends per chunk
- `BROADCAST_CHUNK_DELAY = 1.0 s` — sleep between chunks
- Effective rate: ~25 msg/s (safely under Telegram's 30 msg/s global cap)
- `asyncio.gather(..., return_exceptions=True)` — one failed send does not block the chunk

Do **not** revert to a sequential loop — it blocks the event loop for the entire broadcast duration.

## Logging

Structured JSON logging is opt-in via env var:

```bash
LOG_FORMAT=json  # set in .env on the server
```

When set, all log output is emitted as JSON (via `python-json-logger`) for aggregators such as Loki, Datadog, or ELK. Without the var, `betterlogging` colourised output is used for local dev.

## Database — statement timeout

PostgreSQL is configured with `statement_timeout = 10 000 ms` (10 s) at the server level (`docker-compose.yml`). Any query running longer than 10 s is automatically killed. This protects handlers from hanging indefinitely on slow or missing indexes.

## Graceful Shutdown (webhook mode)

In webhook mode `_run_webhook()` installs `signal.SIGTERM` / `signal.SIGINT` handlers on the event loop. On shutdown:

1. `runner.cleanup()` — drains in-flight aiohttp requests
2. `bot.delete_webhook()` — tells Telegram to stop delivering updates

`docker stop` sends SIGTERM, so containers shut down cleanly without corrupting in-flight handler state.

## Deploy

```bash
./scripts/remote_deploy.sh
```

This script: runs the full test suite → prompts for confirmation → `git push` → `rsync` files to server → SSH deploy via `./scripts/deploy.sh`.

**Never push without passing all 343 tests.**
