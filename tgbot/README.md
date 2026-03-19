# 🤖 Logic Core (`tgbot/`)

This directory contains the entire application logic for the NMT Bot.

## � Directory Structure

### 1. `dialogs/` — User Interface (UI)
The bot uses `aiogram-dialog` to create interactive menus (windows).
- **`admin.py`**: The Admin Panel. CRUD for questions, broadcasting, settings.
- **`simulation.py`**: The exam simulation flow. Year -> Session -> Test -> Results -> Review.
- **`random_mode.py`**: Quick practice mode ("Random Question").
- **`main_menu.py`**: The entry point after `/start`.
- **`stats.py`**: User statistics window.

### 2. `handlers/` — Entry Points
Handles standard Telegram commands and events.
- **`admin.py`**: Handles `/admin` command.
- **`user.py`**: Handles `/start` and text inputs outside dialogs.
- **`errors.py`**: Global error handling (logging exceptions).

### 3. `services/` — Business Logic
External integrations and helper classes.
- **`gemini.py`**: Integration with Google Gemini 1.5 Pro. Generates explanations for images.
- **`broadcaster.py`**: Utility for safe mass messaging (handles blocking/rate limits).

### 4. `middlewares/` — Processing Pipeline
Middleware layers that run before every update.
- **`config.py`**: Injects `config` object into handlers.
- **`database.py`**: specific middleware.

### 5. `misc/` — Utilities
- **`nmt_scoring.py`**: Algorithm for calculating NMT score (100-200 scale).

---

## � Key Files
- **`config.py`**: Parses `.env` variables into a strongly-typed configuration object used throughout the bot.
