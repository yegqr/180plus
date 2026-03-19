from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.repo.requests import RequestsRepo

logger = logging.getLogger(__name__)


async def check_and_approve_requests(bot: Bot, session_pool: async_sessionmaker) -> None:
    """Periodic task to approve join requests older than 3 minutes."""
    async with session_pool() as session:
        repo = RequestsRepo(session)
        old_requests = await repo.join_requests.get_old_requests(minutes=3)
        if not old_requests:
            return

        approved_count = 0
        for row in old_requests:
            user_id, chat_id = row
            try:
                await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
                await repo.join_requests.delete_request(user_id, chat_id)
                approved_count += 1
            except Exception as e:
                logger.error(f"Failed to auto-approve request for user {user_id} in chat {chat_id}: {e}")

        if approved_count > 0:
            logger.info(f"Auto-approved {approved_count} join requests.")


async def setup_scheduler(bot: Bot, session_pool: async_sessionmaker) -> None:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        check_and_approve_requests,
        "interval",
        seconds=60,
        kwargs={"bot": bot, "session_pool": session_pool},
    )

    from tgbot.services.daily import schedule_daily_lottery
    scheduler.add_job(
        schedule_daily_lottery,
        "cron",
        hour=7,
        minute=0,
        kwargs={"scheduler": scheduler, "bot": bot, "session_pool": session_pool},
    )

    scheduler.start()
    logger.info("Scheduler started! Checking join requests every 60s.")

    # Run lottery on startup if not already run today
    await schedule_daily_lottery(scheduler, bot, session_pool)
