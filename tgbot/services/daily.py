import logging
import random
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.services.broadcaster import broadcast

logger = logging.getLogger(__name__)

async def broadcast_daily_question(bot: Bot, session_pool: async_sessionmaker):
    """
    Selects a random question and broadcasts it to all subscribed users,
    sending the message into the user's subject-specific topic thread.
    """
    try:
        async with session_pool() as session:
            repo = RequestsRepo(session)
            
            # 1. Pick random subject — only math, mova, hist
            subjects_pool = ["math", "mova", "hist"]
            selected_subject = random.choice(subjects_pool)
            
            # Fetch random question for that subject (only CHOICE type)
            question = await repo.questions.get_random_question([selected_subject], q_type="choice")
            
            if not question:
                logger.warning(f"Daily Challenge: No questions found for {selected_subject}!")
                return

            # Subject display map
            subject_map = {
                "math": "МАТЕМАТИКА",
                "mova": "УКРАЇНСЬКА МОВА",
                "hist": "ІСТОРІЯ УКРАЇНИ",
                "physics": "ФІЗИКА"
            }
            subject_name = subject_map.get(question.subject, question.subject.upper())

            # 2. Prepare content
            caption = (
                f"🚂 <b>Daily Challenge!</b>\n\n"
                f"Розминка: спробуй розв'язати це завдання!\n"
                f"Предмет: {subject_name}\n"
                f"Рік: {question.year}, Сесія: {question.session}"
            )
            
            # Keyboard
            kb = None
            if question.q_type == "choice":
                options = ["А", "Б", "В", "Г", "Д"]
                buttons = [InlineKeyboardButton(text=opt, callback_data=f"daily:{question.id}:{opt}") for opt in options]
                kb = InlineKeyboardMarkup(inline_keyboard=[buttons, [InlineKeyboardButton(text="🏠 В головне меню", callback_data="daily:menu:home")]])
            else:
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✍️ Написати відповідь", callback_data=f"daily:{question.id}:INPUT"),
                    InlineKeyboardButton(text="👀 (Показати відповідь)", callback_data=f"daily:{question.id}:SHOW_ANSWER")
                ], [
                    InlineKeyboardButton(text="🏠 В головне меню", callback_data="daily:menu:home")
                ]])
            
            # 3. Get all users with their settings
            users = await repo.users.get_users_for_broadcast("daily_challenge")
            all_users_data = await repo.users.get_users_with_settings(users)
            
            logger.info(f"Daily Challenge: Broadcasting Q#{question.id} ({selected_subject}) to {len(users)} users.")

        # 4. Broadcast per-user into the correct topic thread
        # 4. Broadcast per-user into the correct topic thread
        images = []
        if question.image_file_id:
            images.append(question.image_file_id)
        if question.images:
            for img in question.images:
                if img not in images:
                    images.append(img)

        count = 0
        from aiogram.types import InputMediaPhoto
        
        for user in all_users_data:
            # Find thread_id for this subject in user's settings
            topic_ids = user.settings.get("topic_ids", {})
            thread_id = topic_ids.get(selected_subject)  # may be None if topics not created

            try:
                send_kwargs = dict(
                    chat_id=user.user_id,
                    disable_notification=False,
                    message_thread_id=thread_id,  # None = General chat
                )
                if images:
                    if len(images) == 1:
                        await bot.send_photo(
                            photo=images[0],
                            caption=caption,
                            reply_markup=kb,
                            **send_kwargs,
                        )
                    else:
                        media_group = [InputMediaPhoto(media=img, caption=caption if i == 0 else None) for i, img in enumerate(images)]
                        await bot.send_media_group(media=media_group, **send_kwargs)
                        await bot.send_message(text="👇 Оберіть варіант відповіді:", reply_markup=kb, **send_kwargs)
                else:
                    await bot.send_message(text=caption, reply_markup=kb, **send_kwargs)
                count += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning(f"Daily: Failed to send to user {user.user_id}: {e}")

        logger.info(f"Daily Challenge: {count} messages sent successfully.")

    except Exception as e:
        logger.error(f"Daily Challenge Error: {e}")

async def schedule_daily_lottery(scheduler, bot: Bot, session_pool: async_sessionmaker):
    """
    Runs daily (e.g. 7 AM) to decide IF and WHEN to send a challenge.
    """
    async with session_pool() as session:
        repo = RequestsRepo(session)
        
        # 1. Check global setting first
        enabled_str = await repo.settings.get_setting("daily_enabled", "true")
        if enabled_str.lower() != "true":
            logger.info("Daily Challenge: Disabled in settings. Skipping.")
            return

        # 2. Check if already run today
        today_str = datetime.now().strftime("%Y-%m-%d")
        last_run = await repo.settings.get_setting("last_lottery_run")
        if last_run == today_str:
            logger.info(f"Daily Challenge: Lottery already run for {today_str}. Skipping.")
            return

        # 3. Mark as run for today (to prevent re-runs on restarts)
        await repo.settings.set_setting("last_lottery_run", today_str)

        # 4. 50% chance
        lottery_won = random.random() < 0.5
        if lottery_won:
            logger.info("Daily Challenge: Lottery WON! Scheduling for today.")
            
            # Random time 8:00 - 22:00
            start_hour = 8
            end_hour = 22
            
            now = datetime.now()
            
            # Pick random slot
            random_hour = random.randint(start_hour, end_hour - 1)
            random_minute = random.randint(0, 59)
            
            target_time = now.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)
            
            # Determine wait time / validity
            if target_time < now:
                # If we missed the slot (e.g. bot started at 15:00 and lottery won now)
                if now.hour < end_hour:
                    # Reschedule for near future
                    target_time = now + timedelta(minutes=random.randint(5, 30))
                    if target_time.hour >= end_hour:
                         target_time = target_time.replace(hour=end_hour-1, minute=59)
                else:
                    logger.info("Daily Challenge: Day nearly over, skipping broadcast.")
                    await repo.settings.set_setting("daily_lottery_status", f"MISS (Day Over)")
                    return

            logger.info(f"Daily Challenge: Scheduled for {target_time}")
            
            # Persist status for admin panel
            time_str = target_time.strftime("%H:%M")
            await repo.settings.set_setting("daily_lottery_status", f"WIN ({time_str})")

            scheduler.add_job(
                broadcast_daily_question,
                "date",
                run_date=target_time,
                kwargs={"bot": bot, "session_pool": session_pool}
            )
        else:
            logger.info("Daily Challenge: Lottery LOST. No challenge today.")
            await repo.settings.set_setting("daily_lottery_status", "LOSS")
