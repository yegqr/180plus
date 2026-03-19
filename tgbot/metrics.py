"""
Prometheus metrics definitions for the NMT-bot.
Import these counters/histograms from middlewares and services.
"""
from prometheus_client import Counter, Histogram, Gauge

MESSAGES_TOTAL = Counter(
    "bot_messages_total",
    "Total incoming updates processed",
    ["update_type"],
)

REQUESTS_DURATION = Histogram(
    "bot_request_duration_seconds",
    "End-to-end request processing time (middleware → handler)",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

THROTTLED_TOTAL = Counter(
    "bot_throttled_requests_total",
    "Requests silently dropped by the throttling middleware",
)

BROADCAST_SENT = Counter(
    "bot_broadcast_sent_total",
    "Broadcast messages outcome",
    ["status"],  # "sent" | "failed"
)

ERRORS_TOTAL = Counter(
    "bot_errors_total",
    "Unhandled exceptions caught by the global error handler",
    ["exc_type"],
)

DB_SESSIONS_ACTIVE = Gauge(
    "bot_db_sessions_active",
    "Currently open SQLAlchemy sessions (inside DatabaseMiddleware)",
)

DB_QUERY_DURATION = Histogram(
    "bot_db_query_duration_seconds",
    "Individual SQLAlchemy query execution time",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)
