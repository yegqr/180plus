import time

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from tgbot.config import DbConfig


def create_engine(db: DbConfig, echo=False):
    engine = create_async_engine(
        db.construct_sqlalchemy_url(),
        query_cache_size=1200,
        # PgBouncer (transaction mode) is the real connection pool.
        # SQLAlchemy keeps a small pool of connections *to PgBouncer*.
        pool_size=10,
        max_overflow=20,
        # Drop stale connections held too long by the pool
        pool_recycle=1800,
        # Validate connection health before checkout (catches dropped sockets)
        pool_pre_ping=True,
        # Disable asyncpg prepared-statement cache — required for PgBouncer
        # transaction mode (server connections are not sticky per transaction).
        connect_args={"prepared_statement_cache_size": 0},
        future=True,
        echo=echo,
    )

    # --- Per-query timing for Prometheus ---
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_qstart", []).append(time.perf_counter())

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        elapsed = time.perf_counter() - conn.info["_qstart"].pop()
        try:
            from tgbot.metrics import DB_QUERY_DURATION
            DB_QUERY_DURATION.observe(elapsed)
        except Exception:
            pass

    return engine


def create_session_pool(engine):
    session_pool = async_sessionmaker(bind=engine, expire_on_commit=False)
    return session_pool
