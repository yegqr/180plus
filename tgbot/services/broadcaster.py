import asyncio
import logging
from typing import Union

from aiogram import Bot
from aiogram import exceptions
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto

from tgbot.misc.constants import BROADCAST_SEND_DELAY

_MAX_RETRIES = 3


async def send_message(
    bot: Bot,
    user_id: Union[int, str],
    text: str,
    disable_notification: bool = False,
    reply_markup: InlineKeyboardMarkup = None,
    photo: str | list[str] | None = None,
) -> bool:
    """Safe message sender with exponential-backoff retry on rate limits (max 3 attempts)."""
    for attempt in range(_MAX_RETRIES):
        try:
            if photo:
                if isinstance(photo, list) and len(photo) > 1:
                    media = [InputMediaPhoto(type="photo", media=file_id) for file_id in photo]
                    await bot.send_media_group(
                        chat_id=user_id,
                        media=media,
                        disable_notification=disable_notification,
                    )
                    await bot.send_message(
                        user_id,
                        text,
                        disable_notification=disable_notification,
                        reply_markup=reply_markup,
                    )
                else:
                    single_photo = photo[0] if isinstance(photo, list) else photo
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=single_photo,
                        caption=text,
                        disable_notification=disable_notification,
                        reply_markup=reply_markup,
                    )
            else:
                await bot.send_message(
                    user_id,
                    text,
                    disable_notification=disable_notification,
                    reply_markup=reply_markup,
                )
            return True

        except exceptions.TelegramRetryAfter as e:
            if attempt == _MAX_RETRIES - 1:
                logging.error(
                    f"Target [ID:{user_id}]: Rate limit hit, giving up after {_MAX_RETRIES} retries."
                )
                return False
            logging.warning(
                f"Target [ID:{user_id}]: Flood limit. Sleep {e.retry_after}s "
                f"(attempt {attempt + 1}/{_MAX_RETRIES})."
            )
            await asyncio.sleep(e.retry_after)

        except exceptions.TelegramBadRequest as e:
            logging.error(f"Target [ID:{user_id}]: Bad Request {e.message}")
            if "chat not found" in e.message.lower() or "user not found" in e.message.lower():
                await _deactivate_user(bot, user_id)
            return False

        except exceptions.TelegramForbiddenError:
            logging.error(f"Target [ID:{user_id}]: User Blocked Bot")
            await _deactivate_user(bot, user_id)
            return False

        except exceptions.TelegramAPIError as e:
            logging.error(f"Target [ID:{user_id}]: Failed with API error: {e}")
            return False

        except Exception as e:
            logging.error(f"Target [ID:{user_id}]: Unexpected error: {e}")
            return False

    return False

async def _deactivate_user(bot: Bot, user_id: Union[int, str]) -> None:
    if hasattr(bot, "session_pool"):
        try:
            from sqlalchemy import update
            from infrastructure.database.models import User
            
            async with bot.session_pool() as session:
                # We need to coerce user_id to int
                uid = int(user_id)
                stmt = update(User).where(User.user_id == uid).values(active=False)
                await session.execute(stmt)
                await session.commit()
                logging.info(f"User {uid} marked as inactive in DB.")
        except Exception as e:
            logging.warning(f"Failed to deactivate user {user_id}: {e}")


async def broadcast(
    bot: Bot,
    users: list[Union[str, int]],
    text: str,
    disable_notification: bool = False,
    reply_markup: InlineKeyboardMarkup = None,
    photo: str | list[str] | None = None
) -> int:
    """
    Simple broadcaster.
    :param bot: Bot instance.
    :param users: List of users.
    :param text: Text of the message.
    :param disable_notification: Disable notification or not.
    :param reply_markup: Reply markup.
    :return: Count of messages.
    """
    count = 0
    try:
        for user_id in users:
            if await send_message(
                bot, user_id, text, disable_notification, reply_markup, photo
            ):
                count += 1
            await asyncio.sleep(BROADCAST_SEND_DELAY)  # 20 msg/s (Limit: 30 msg/s)
    finally:
        logging.info(f"{count} messages successful sent.")

    return count
