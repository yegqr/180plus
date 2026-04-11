"""
Central location for all shared constants across the bot.
Prevents DRY violations and eliminates magic numbers scattered across files.
"""

# ---------------------------------------------------------------------------
# Subject metadata
# ---------------------------------------------------------------------------

# Subject display labels: slug → short human-readable name (used in UI)
SUBJECT_LABELS: dict[str, str] = {
    "math":    "Math 🔢",
    "hist":    "History 🇺🇦",
    "mova":    "🇺🇦 Mova",
    "eng":     "English 🇬🇧",
    "physics": "Physics 🧲",
}

# Full Ukrainian subject names (used in broadcasts, reports)
SUBJECT_FULL_NAMES: dict[str, str] = {
    "math":    "МАТЕМАТИКА",
    "mova":    "УКРАЇНСЬКА МОВА",
    "hist":    "ІСТОРІЯ УКРАЇНИ",
    "physics": "ФІЗИКА",
    "eng":     "АНГЛІЙСЬКА МОВА",
}

# Subjects available as a list (for iteration)
ALL_SUBJECTS: list[str] = list(SUBJECT_LABELS.keys())

# ---------------------------------------------------------------------------
# Answer letter alphabets
# ---------------------------------------------------------------------------

UKR_LETTERS: str = "АБВГДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
ENG_LETTERS: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ---------------------------------------------------------------------------
# Telegram rate-limiting
# ---------------------------------------------------------------------------

# Seconds between individual sends during broadcasts (stays under 30 msg/s limit)
BROADCAST_SEND_DELAY: float = 0.05

# Chunk-based broadcast settings.
# CHUNK_SIZE concurrent sends per chunk; CHUNK_DELAY seconds between chunks.
# 25 sends / 1.0 s = 25 msg/s, safely under Telegram's 30 msg/s global cap.
BROADCAST_CHUNK_SIZE: int = 25
BROADCAST_CHUNK_DELAY: float = 1.0

# Seconds between join-request approvals
JOIN_REQUEST_DELAY: float = 0.05

# ---------------------------------------------------------------------------
# Album / media group handling
# ---------------------------------------------------------------------------

# Seconds to wait for all photos in a media group to arrive before processing
ALBUM_WAIT_SECONDS: float = 4.0

# ---------------------------------------------------------------------------
# Gemini background tasks
# ---------------------------------------------------------------------------

# Maximum concurrent Gemini API calls in the bulk-upload semaphore
GEMINI_SEMAPHORE_LIMIT: int = 3

# ---------------------------------------------------------------------------
# Random-mode history
# ---------------------------------------------------------------------------

# How many past attempts to show per question
QUESTION_HISTORY_LIMIT: int = 5

# ---------------------------------------------------------------------------
# Telegram message / caption size limits
# ---------------------------------------------------------------------------

TG_CAPTION_LIMIT: int = 1024
TG_MESSAGE_LIMIT: int = 4096

# Safe thresholds used for truncation before sending
TG_CAPTION_SAFE_LIMIT: int = 900
TG_TEXT_SAFE_LIMIT: int = 3500
