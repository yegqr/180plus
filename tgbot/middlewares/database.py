from __future__ import annotations

import json
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.models import User
from infrastructure.database.repo.requests import RequestsRepo

# How long (seconds) a user record is cached in Redis before a fresh DB upsert.
# At 100k DAU this reduces upsert load by ~90 % — 5 min staleness is fine for
# username/subject/settings, and activity tracking (updated_at) is only off by
# up to _USER_CACHE_TTL seconds which is well within any analytics window.
_USER_CACHE_TTL = 300


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker, redis=None) -> None:
        self.session_pool = session_pool
        self._redis = redis  # optional redis.asyncio.Redis for user-cache (db=4)

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        start = time.perf_counter()
        update_type = type(event).__name__.lower()

        try:
            from tgbot.metrics import MESSAGES_TOTAL, REQUESTS_DURATION, DB_SESSIONS_ACTIVE
            MESSAGES_TOTAL.labels(update_type=update_type).inc()
            _metrics_available = True
        except Exception:
            _metrics_available = False

        if _metrics_available:
            DB_SESSIONS_ACTIVE.inc()

        try:
            async with self.session_pool() as session:
                repo = RequestsRepo(session)

                from_user = event.from_user
                config = data.get("config")
                is_admin = config and from_user.id in config.tg_bot.admin_ids

                user = await self._get_or_create_user_cached(
                    repo,
                    user_id=from_user.id,
                    full_name=from_user.full_name,
                    language=from_user.language_code,
                    is_admin=bool(is_admin),
                    username=from_user.username,
                )

                data["session"] = session
                data["repo"] = repo
                data["user"] = user
                # Expose session_pool so downstream code (e.g. admin broadcast handlers)
                # can open their own sessions without the bot.session_pool hack.
                data["session_pool"] = self.session_pool

                try:
                    result = await handler(event, data)
                    await session.commit()
                    return result
                except Exception:
                    await session.rollback()
                    raise
        finally:
            if _metrics_available:
                DB_SESSIONS_ACTIVE.dec()
                REQUESTS_DURATION.observe(time.perf_counter() - start)

    async def _get_or_create_user_cached(
        self,
        repo: RequestsRepo,
        user_id: int,
        full_name: str,
        language: str,
        is_admin: bool,
        username: str | None,
    ) -> User:
        """
        Returns a User from Redis cache (TTL=5 min) or falls back to a DB upsert.

        Cache hit → returns a transient User instance (not attached to the session).
        This is safe: all middleware/handler access is simple attribute reads, and any
        writes go through explicit repo method calls (update_subject, etc.).
        """
        if self._redis is not None:
            cache_key = f"ucache:{user_id}"
            try:
                cached_raw = await self._redis.get(cache_key)
                if cached_raw:
                    d = json.loads(cached_raw)
                    # Reconstruct a transient User (not tracked by any session).
                    return User(
                        user_id=d["user_id"],
                        username=d["username"],
                        full_name=d["full_name"],
                        language=d["language"],
                        is_admin=d["is_admin"],
                        selected_subject=d["selected_subject"],
                        settings=d["settings"],
                        active=d["active"],
                        daily_sub=d["daily_sub"],
                    )
            except Exception:
                pass  # cache error → fall through to DB

        user = await repo.users.get_or_create_user(
            user_id, full_name, language, is_admin, username
        )

        if self._redis is not None:
            try:
                await self._redis.set(
                    f"ucache:{user_id}",
                    json.dumps({
                        "user_id": user.user_id,
                        "username": user.username,
                        "full_name": user.full_name,
                        "language": user.language,
                        "is_admin": user.is_admin,
                        "selected_subject": user.selected_subject,
                        "settings": user.settings or {},
                        "active": user.active,
                        "daily_sub": user.daily_sub,
                    }),
                    ex=_USER_CACHE_TTL,
                )
            except Exception:
                pass  # cache write failure is non-fatal

        return user
