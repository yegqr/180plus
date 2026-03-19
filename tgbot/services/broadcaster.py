import asyncio
import logging
from typing import Union

from aiogram import Bot
from aiogram import exceptions
from aiogram.types import InlineKeyboardMarkup


from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto

async def send_message(
    bot: Bot,
    user_id: Union[int, str],
    text: str,
    disable_notification: bool = False,
    reply_markup: InlineKeyboardMarkup = None,
    photo: str | list[str] | None = None
) -> bool:
    """
    Safe messages sender
    """
    try:
        if photo:
            if isinstance(photo, list) and len(photo) > 1:
                # Send mediagroup first
                media = [InputMediaPhoto(type='photo', media=file_id) for file_id in photo]
                await bot.send_media_group(
                    chat_id=user_id,
                    media=media,
                    disable_notification=disable_notification
                )
                # Send caption and keyboard as a separate message
                await bot.send_message(
                    user_id,
                    text,
                    disable_notification=disable_notification,
                    reply_markup=reply_markup,
                )
            else:
                # Single photo
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
    except exceptions.TelegramBadRequest as e:
        logging.error(f"Target [ID:{user_id}]: Bad Request {e.message}")
        if "chat not found" in e.message.lower() or "user not found" in e.message.lower():
            await _deactivate_user(bot, user_id)
    except exceptions.TelegramForbiddenError:
        logging.error(f"Target [ID:{user_id}]: User Blocked Bot")
        await _deactivate_user(bot, user_id)
    except exceptions.TelegramRetryAfter as e:
        logging.error(
            f"Target [ID:{user_id}]: Flood limit exceeded. Sleep {e.retry_after}s."
        )
        await asyncio.sleep(e.retry_after)
        return await send_message(
            bot, user_id, text, disable_notification, reply_markup, photo
        )  # Recursive call
    except exceptions.TelegramAPIError as e:
        logging.error(f"Target [ID:{user_id}]: Failed with API error: {e}")
    except Exception as e:
        logging.error(f"Target [ID:{user_id}]: Unexpected error: {e}")
    else:
        # logging.info(f"Target [ID:{user_id}]: success")
        return True
    return False

async def _deactivate_user(bot: Bot, user_id: Union[int, str]):
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
            await asyncio.sleep(
                0.05
            )  # 20 messages per second (Limit: 30 messages per second)
    finally:
        logging.info(f"{count} messages successful sent.")

    return count
