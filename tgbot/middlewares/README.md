# ⚙️ Middlewares Layer

Цей пакет містить класи проміжного ПЗ (Middlewares), які виконуються до або після обробки кожної події.

## 📁 Наявні Middlewares

*   [`database.py`](file:///Users/yegqr/NMT-bot/tgbot/middlewares/database.py) — **Найважливіший middleware**.
    *   Відкриває асинхронну сесію PostgreSQL для кожного апдейта.
    *   Створює екземпляр `RequestsRepo`.
    *   Отримує/створює об'єкт `user` у базі даних.
    *   Прокидає `repo`, `user` та `session` у `data` обробника.
*   [`config.py`](file:///Users/yegqr/NMT-bot/tgbot/middlewares/config.py) — Прокидає об'єкт конфігурації (`config`) у хендлери.

## 🚀 Реєстрація

Middlewares реєструються глобально у файлі `bot.py` через функцію `register_global_middlewares`. Ми реєструємо їх для типів подій `message`, `callback_query` та `chat_join_request`.
