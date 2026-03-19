# 🎭 Dialogs Layer

Цей пакет містить опис усіх складних UI-компонентів бота на базі `aiogram-dialog`.

## 📁 Основні діалоги

*   [`admin.py`](file:///Users/yegqr/NMT-bot/tgbot/dialogs/admin.py) — Головна панель адміністратора.
    *   Керування контентом (предмети, роки, сесії, питання).
    *   Керування списком адміністраторів.
    *   Глобальні налаштування (відео-онбординг).
    *   Масове прийняття заявок у канал.
*   [`broadcasting.py`](file:///Users/yegqr/NMT-bot/tgbot/dialogs/broadcasting.py) — Інтерфейс створення та відправки розсилок з сегментацією.
*   [`main_menu.py`](file:///Users/yegqr/NMT-bot/tgbot/dialogs/main_menu.py) — Головне меню користувача. Вибір предмета.
*   [`simulation.py`](file:///Users/yegqr/NMT-bot/tgbot/dialogs/simulation.py) — Логіка проведення тестів (симуляція НМТ). Підтримка типів питань: тест, відповідність, ввід тексту.
*   [`random_mode.py`](file:///Users/yegqr/NMT-bot/tgbot/dialogs/random_mode.py) — Режим випадкових питань.
*   [`stats.py`](file:///Users/yegqr/NMT-bot/tgbot/dialogs/stats.py) — Статистика користувача.

## 🏗️ Побудова діалогу

Кожен файл зазвичай містить:
1.  `StatesGroup` — Опис станів діалогу.
2.  `Getters` — Асинхронні функції для підготовки даних (доступ до `repo` через `dialog_manager`).
3.  `Handlers` — Логіка обробки натискань (наприклад, `on_click_...`).
4.  `Dialog` — Екземпляр класу `Dialog`, який об'єднує вікна.

Всі діалоги реєструються у [`tgbot/dialogs/__init__.py`](file:///Users/yegqr/NMT-bot/tgbot/dialogs/__init__.py).
