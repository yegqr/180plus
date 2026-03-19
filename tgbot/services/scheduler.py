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
    """Periodic task to approve join requests older than 3 minutes."""
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


async def setup_scheduler(bot: Bot, session_pool: async_sessionmaker, config: Any = None) -> None:
    global _bot, _session_pool
    _bot = bot
    _session_pool = session_pool

    import tgbot.services.daily as daily_module
    daily_module._bot = bot
    daily_module._session_pool = session_pool

    jobstores = _build_jobstore(config)
    scheduler = AsyncIOScheduler(jobstores=jobstores if jobstores else None)
    daily_module._scheduler = scheduler

    scheduler.add_job(
        check_and_approve_requests,
        "interval",
        seconds=60,
    )

    scheduler.add_job(
        daily_module.schedule_daily_lottery,
        "cron",
        hour=7,
        minute=0,
    )

    scheduler.start()
    logger.info("Scheduler started! Checking join requests every 60s.")

    # Run lottery on startup if not already run today
    await daily_module.schedule_daily_lottery()
