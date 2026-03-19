# 🗄️ Database Layer

Цей пакет відповідає за роботу з персистентними даними проекту. Ми використовуємо **SQLAlchemy 2.0** з асинхронним драйвером **asyncpg**.

## 📁 Структура пакету

*   `models/` — Опис таблиць бази даних у вигляді Python-класів.
    *   `users.py` — Таблиця користувачів.
    *   `questions.py` — База питань НМТ.
    *   `results.py` — Результати симуляцій.
    *   `settings.py` — Глобальні налаштування бота.
    *   `join_requests.py` — Тимчасове сховище заявок у канал.
*   `repo/` — Імплементація патерну "Репозиторій" для ізоляції логіки запитів.
    *   `users.py`, `questions.py` тощо — Методи для конкретних сутностей.
    *   `requests.py` — Головний фасад (RequestsRepo), доступний через `dialog_manager.middleware_data['repo']`.
*   `setup.py` — Конфігурація Engine та SessionPool.

## 🚀 Як використовувати в боті

Завдяки `DatabaseMiddleware`, об'єкт `repo` автоматично прокидається в усі хендлери та діалоги.

Приклад у хендлері:
```python
async def my_handler(message: Message, repo: RequestsRepo):
    user = await repo.users.get_user_by_id(message.from_user.id)
```

Приклад у геттері діалогу:
```python
async def my_getter(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    data = await repo.questions.get_all()
    return {"items": data}
```
