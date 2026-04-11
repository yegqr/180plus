from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.repo.requests import RequestsRepo

logger = logging.getLogger(__name__)

# Module-level refs so job functions can access them without being pickled as kwargs
_bot: Bot | None = None
_session_pool: async_sessionmaker | None = None
_redis = None  # redis.asyncio.Redis — set in setup_scheduler when Redis is available


# ---------------------------------------------------------------------------
# Distributed locking helpers
# ---------------------------------------------------------------------------

async def _acquire_lock(key: str, ttl_seconds: int) -> bool:
    """
    Try to acquire a Redis-based distributed lock.

    Returns True if the lock was acquired (this process should proceed),
    False if another instance already holds it.

    Falls back to True (always proceed) when Redis is not configured —
    safe for single-instance deployments.
    """
    if _redis is None:
        return True
    try:
        acquired = await _redis.set(key, "1", ex=ttl_seconds, nx=True)
        return bool(acquired)
    except Exception as e:
        logger.warning(f"Scheduler: Redis lock error for '{key}': {e} — proceeding without lock.")
        return True


async def _release_lock(key: str) -> None:
    if _redis is None:
        return
    try:
        await _redis.delete(key)
    except Exception as e:
        logger.warning(f"Scheduler: failed to release lock '{key}': {e}")


def _build_jobstore(config: Any) -> dict:
    """Returns APScheduler jobstores dict. Uses Redis when configured, otherwise in-memory."""
    if config and config.tg_bot.use_redis:
        try:
            from apscheduler.jobstores.redis import RedisJobStore
            redis_cfg = config.redis
            jobstore = RedisJobStore(
                host=redis_cfg.redis_host,
                port=redis_cfg.redis_port,
                password=redis_cfg.redis_pass or None,
                db=1,  # separate DB from FSM storage (which uses db=0)
            )
            logger.info("Scheduler: using Redis job store.")
            return {"default": jobstore}
        except Exception as e:
            logger.warning(f"Scheduler: Redis job store unavailable ({e}), falling back to memory.")
    return {}


async def check_and_approve_requests() -> None:
    """
    Periodic task to approve join requests older than 3 minutes.

    Protected by a short-lived distributed lock (55 s) so that if two bot
    instances happen to run simultaneously they don't double-approve.
    """
    lock_key = "scheduler:approve_requests"
    if not await _acquire_lock(lock_key, ttl_seconds=55):
        logger.debug("Scheduler: approve_requests lock held by another instance, skipping.")
        return

    try:
        async with _session_pool() as session:
            repo = RequestsRepo(session)
            old_requests = await repo.join_requests.get_old_requests(minutes=3)
            if not old_requests:
                return

            approved_count = 0
            for row in old_requests:
                user_id, chat_id = row
                try:
                    await _bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
                    await repo.join_requests.delete_request(user_id, chat_id)
                    approved_count += 1
                except Exception as e:
                    logger.error(f"Failed to auto-approve request for user {user_id} in chat {chat_id}: {e}")

            if approved_count > 0:
                await session.commit()
                logger.info(f"Auto-approved {approved_count} join requests.")
    finally:
        await _release_lock(lock_key)


async def setup_scheduler(bot: Bot, session_pool: async_sessionmaker, config: Any = None) -> None:
    global _bot, _session_pool, _redis
    _bot = bot
    _session_pool = session_pool

    # Build Redis client for distributed locking (db=2, separate from FSM=0 and APScheduler=1)
    if config and config.tg_bot.use_redis:
        try:
            import redis.asyncio as aioredis
            _redis = aioredis.Redis.from_url(config.redis.dsn().replace("/0", "/2"))
            await _redis.ping()
            logger.info("Scheduler: Redis distributed locking enabled.")
        except Exception as e:
            logger.warning(f"Scheduler: Redis unavailable for locking ({e}), running without distributed lock.")
            _redis = None

    jobstores = _build_jobstore(config)
    scheduler = AsyncIOScheduler(jobstores=jobstores if jobstores else None)

    scheduler.add_job(
        check_and_approve_requests,
        "interval",
        seconds=60,
    )

    scheduler.start()
    logger.info("Scheduler started! Checking join requests every 60s.")
