from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.services.broadcaster import broadcast
from tgbot.misc.constants import (
    SUBJECT_FULL_NAMES,
    DAILY_CHALLENGE_SUBJECTS,
    BROADCAST_SEND_DELAY,
    DAILY_WINDOW_START_HOUR,
    DAILY_WINDOW_END_HOUR,
)
from tgbot.misc.utils import get_question_images

logger = logging.getLogger(__name__)

_HOME_BTN = InlineKeyboardButton(text="🏠 В головне меню", callback_data="daily:menu:home")


def _build_daily_keyboard(question: Any) -> InlineKeyboardMarkup:
    """Returns the answer keyboard for a daily challenge question."""
    if question.q_type == "choice":
        buttons = [
            InlineKeyboardButton(text=opt, callback_data=f"daily:{question.id}:{opt}")
            for opt in ["А", "Б", "В", "Г", "Д"]
        ]
        return InlineKeyboardMarkup(inline_keyboard=[buttons, [_HOME_BTN]])
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✍️ Написати відповідь", callback_data=f"daily:{question.id}:INPUT"),
        InlineKeyboardButton(text="👀 (Показати відповідь)", callback_data=f"daily:{question.id}:SHOW_ANSWER"),
    ], [_HOME_BTN]])


async def _send_daily_to_user(
    bot: Bot, user: Any, subject: str, images: list[str], caption: str, kb: InlineKeyboardMarkup
) -> bool:
    """Sends the daily challenge to a single user. Returns True on success."""
    thread_id = user.settings.get("topic_ids", {}).get(subject)
    send_kwargs = dict(chat_id=user.user_id, disable_notification=False, message_thread_id=thread_id)
    try:
        if images:
            if len(images) == 1:
                await bot.send_photo(photo=images[0], caption=caption, reply_markup=kb, **send_kwargs)
            else:
                media_group = [InputMediaPhoto(media=img, caption=caption if i == 0 else None) for i, img in enumerate(images)]
                await bot.send_media_group(media=media_group, **send_kwargs)
                await bot.send_message(text="👇 Оберіть варіант відповіді:", reply_markup=kb, **send_kwargs)
        else:
            await bot.send_message(text=caption, reply_markup=kb, **send_kwargs)
        return True
    except Exception as e:
        logger.warning(f"Daily: Failed to send to user {user.user_id}: {e}")
        return False


async def broadcast_daily_question(bot: Bot, session_pool: async_sessionmaker) -> None:
    """Selects a random question and broadcasts it to all subscribed users."""
    try:
        async with session_pool() as session:
            repo = RequestsRepo(session)
            selected_subject = random.choice(DAILY_CHALLENGE_SUBJECTS)
            question = await repo.questions.get_random_question([selected_subject], q_type="choice")
            if not question:
                logger.warning(f"Daily Challenge: No questions found for {selected_subject}!")
                return

            subject_name = SUBJECT_FULL_NAMES.get(question.subject, question.subject.upper())
            caption = (
                f"🚂 <b>Daily Challenge!</b>\n\n"
                f"Розминка: спробуй розв'язати це завдання!\n"
                f"Предмет: {subject_name}\n"
                f"Рік: {question.year}, Сесія: {question.session}"
            )
            kb = _build_daily_keyboard(question)
            users = await repo.users.get_users_for_broadcast("daily_challenge")
            all_users_data = await repo.users.get_users_with_settings(users)
            logger.info(f"Daily Challenge: Broadcasting Q#{question.id} ({selected_subject}) to {len(users)} users.")

        images = get_question_images(question)
        count = 0
        for user in all_users_data:
            if await _send_daily_to_user(bot, user, selected_subject, images, caption, kb):
                count += 1
            await asyncio.sleep(BROADCAST_SEND_DELAY)
        logger.info(f"Daily Challenge: {count} messages sent successfully.")

    except Exception as e:
        logger.error(f"Daily Challenge Error: {e}")

def _pick_send_time(now: datetime) -> datetime | None:
    """
    Picks a random time within the daily window for today.
    Returns None if the window has already passed.
    """
    random_hour = random.randint(DAILY_WINDOW_START_HOUR, DAILY_WINDOW_END_HOUR - 1)
    random_minute = random.randint(0, 59)
    target = now.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)

    if target >= now:
        return target

    # Slot already passed — try near-future fallback if window is still open
    if now.hour < DAILY_WINDOW_END_HOUR:
        fallback = now + timedelta(minutes=random.randint(5, 30))
        if fallback.hour >= DAILY_WINDOW_END_HOUR:
            fallback = fallback.replace(hour=DAILY_WINDOW_END_HOUR - 1, minute=59)
        return fallback

    return None  # window fully over


async def schedule_daily_lottery(scheduler: Any, bot: Bot, session_pool: async_sessionmaker) -> None:
    """Runs daily to decide IF and WHEN to send the challenge (50 % lottery)."""
    async with session_pool() as session:
        repo = RequestsRepo(session)

        enabled_str = await repo.settings.get_setting("daily_enabled", "true")
        if enabled_str.lower() != "true":
            logger.info("Daily Challenge: Disabled in settings. Skipping.")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        if await repo.settings.get_setting("last_lottery_run") == today_str:
            logger.info(f"Daily Challenge: Lottery already run for {today_str}. Skipping.")
            return

        await repo.settings.set_setting("last_lottery_run", today_str)

        if random.random() >= 0.5:
            logger.info("Daily Challenge: Lottery LOST. No challenge today.")
            await repo.settings.set_setting("daily_lottery_status", "LOSS")
            return

        logger.info("Daily Challenge: Lottery WON! Scheduling for today.")
        target_time = _pick_send_time(datetime.now())

        if target_time is None:
            logger.info("Daily Challenge: Day nearly over, skipping broadcast.")
            await repo.settings.set_setting("daily_lottery_status", "MISS (Day Over)")
            return

        logger.info(f"Daily Challenge: Scheduled for {target_time}")
        await repo.settings.set_setting("daily_lottery_status", f"WIN ({target_time:%H:%M})")
        scheduler.add_job(
            broadcast_daily_question,
            "date",
            run_date=target_time,
            kwargs={"bot": bot, "session_pool": session_pool},
        )
