# 🎮 Handlers Layer

Цей пакет містить обробники стандартних подій Telegram (повідомлення, команди, запити на вступ тощо).

## 📁 Типи хендлерів

*   [`user.py`](file:///Users/yegqr/NMT-bot/tgbot/handlers/user.py) — Обробка команди `/start`. Реєстрація користувача та запуск головного меню. Також містить обробник `callback_data="start_menu"` для переходу з онбордингу.
*   [`admin.py`](file:///Users/yegqr/NMT-bot/tgbot/handlers/admin.py) — Обробка команди `/admin`. Перевірка прав доступу та запуск адмін-панелі.
*   [`join_request.py`](file:///Users/yegqr/NMT-bot/tgbot/handlers/join_request.py) — Обробка `ChatJoinRequest`. Реєстрація користувача, відправка вітального повідомлення з кнопкою онбордингу.
*   [`error.py`](file:///Users/yegqr/NMT-bot/tgbot/handlers/error.py) — Глобальна обробка винятків у боті.

## 🚀 Реєстрація

Всі роутери збираються у список `routers_list` у файлі [`tgbot/handlers/__init__.py`](file:///Users/yegqr/NMT-bot/tgbot/handlers/__init__.py). Цей список потім імпортується в `bot.py` для підключення до Диспетчера.
