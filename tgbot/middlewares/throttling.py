"""
Rate-limiting middleware for NMT-bot.

Uses Redis sliding window (SET NX PX) when a Redis client is provided —
works correctly across multiple bot instances / containers.
Falls back to an in-process dict on Redis errors or when Redis is absent.
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """
    Silently drops requests from a user if they arrive faster than
    `rate_limit` seconds apart.

    Admins (passed as admin_ids at construction) are never throttled.
    When `redis` is passed, rate-limit state is shared across all instances
    via a Redis NX key (db=3 by convention). Falls back to in-process dict
    on Redis errors.
    """

    def __init__(self, rate_limit: float = 0.7, redis=None, admin_ids: list[int] = ()) -> None:
        self._rate_limit = rate_limit
        self._redis = redis
        self._admin_ids: frozenset[int] = frozenset(admin_ids)
        # Fallback: user_id -> monotonic timestamp after which next request is allowed
        self._users: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if not from_user:
            return await handler(event, data)

        user_id: int = from_user.id

        # Never throttle admins — check at construction time, no config lookup needed
        if user_id in self._admin_ids:
            return await handler(event, data)

        if await self._is_throttled(user_id):
            try:
                from tgbot.metrics import THROTTLED_TOTAL
                THROTTLED_TOTAL.inc()
            except Exception:
                pass
            return

        return await handler(event, data)

    async def _is_throttled(self, user_id: int) -> bool:
        """Returns True if this request should be dropped."""
        if self._redis is not None:
            try:
                # SET key 1 PX <ms> NX — only sets if key does not exist.
                # Returns True (key created → not throttled) or None (key existed → throttled).
                result = await self._redis.set(
                    f"throttle:{user_id}",
                    "1",
                    px=int(self._rate_limit * 1000),
                    nx=True,
                )
                return result is None
            except Exception:
                pass  # Redis error → fall through to in-memory

        # In-memory fallback (single-instance only)
        now = time.monotonic()
        expire_at = self._users.get(user_id, 0.0)

        if now < expire_at:
            return True

        self._users[user_id] = now + self._rate_limit

        # Prevent unbounded growth: prune stale entries when large
        if len(self._users) > 100_000:
            self._users = {k: v for k, v in self._users.items() if v > now}

        return False
