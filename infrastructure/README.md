# 🗄️ Infrastructure Layer (`infrastructure/`)

This directory manages data persistence, database models, and external storage.

## 📂 Directory Structure

### 1. `database/` — Database Logic
- **`models/`**: SQLAlchemy models defining the schema.
    - `users.py`: User profile and stats.
    - `questions.py`: Exam questions (subject, year, images, correct answer, explanation).
    - `results.py`: History of passed tests.
    - `join_requests.py`: Queue for channel join requests.
- **`repo/`**: Repository Pattern implementation (CRUD operations).
    - `requests.py`: The main `RequestsRepo` wrapper that groups all repos.
    - `questions.py`: Methods to fetch/filter questions.
    - `users.py`: Methods to create/update users.
- **`setup.py`**: Database engine creation and session factory (`asyncpg`).

### 2. `migrations/` — Schema Versioning
Managed by **Alembic**.
- **`versions/`**: Python scripts describing changes to the DB schema (e.g., adding a table or column).

---

## 🛠 Usage
The bot acts as a **Repo** consumer. In any handler/dialog:
```python
repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
user = await repo.users.get_user_by_id(123)
```
