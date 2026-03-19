import asyncio
import logging
from typing import Union

from aiogram import Bot
from aiogram import exceptions
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto

from tgbot.misc.constants import BROADCAST_CHUNK_SIZE, BROADCAST_CHUNK_DELAY

_MAX_RETRIES = 3


def _inc_broadcast_metric(status: str) -> None:
    try:
        from tgbot.metrics import BROADCAST_SENT
        BROADCAST_SENT.labels(status=status).inc()
    except Exception:
        pass


async def send_message(
    bot: Bot,
    user_id: Union[int, str],
    text: str,
    disable_notification: bool = False,
    reply_markup: InlineKeyboardMarkup = None,
    photo: str | list[str] | None = None,
    session_pool=None,
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
            _inc_broadcast_metric("sent")
            return True

        except exceptions.TelegramRetryAfter as e:
            if attempt == _MAX_RETRIES - 1:
                logging.error(
                    f"Target [ID:{user_id}]: Rate limit hit, giving up after {_MAX_RETRIES} retries."
                )
                _inc_broadcast_metric("failed")
                return False
            logging.warning(
                f"Target [ID:{user_id}]: Flood limit. Sleep {e.retry_after}s "
                f"(attempt {attempt + 1}/{_MAX_RETRIES})."
            )
            await asyncio.sleep(e.retry_after)

        except exceptions.TelegramBadRequest as e:
            logging.error(f"Target [ID:{user_id}]: Bad Request {e.message}")
            if "chat not found" in e.message.lower() or "user not found" in e.message.lower():
                await _deactivate_user(user_id, session_pool)
            _inc_broadcast_metric("failed")
            return False

        except exceptions.TelegramForbiddenError:
            logging.error(f"Target [ID:{user_id}]: User Blocked Bot")
            await _deactivate_user(user_id, session_pool)
            _inc_broadcast_metric("failed")
            return False

        except exceptions.TelegramAPIError as e:
            logging.error(f"Target [ID:{user_id}]: Failed with API error: {e}")
            _inc_broadcast_metric("failed")
            return False

        except Exception as e:
            logging.error(f"Target [ID:{user_id}]: Unexpected error: {e}")
            _inc_broadcast_metric("failed")
            return False

    _inc_broadcast_metric("failed")
    return False


async def _deactivate_user(user_id: Union[int, str], session_pool) -> None:
    """Mark user as inactive in DB. session_pool must be provided explicitly."""
    if session_pool is None:
        return
    try:
        from sqlalchemy import update
        from infrastructure.database.models import User

        async with session_pool() as session:
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
    photo: str | list[str] | None = None,
    session_pool=None,
) -> int:
    """
    Chunk-based broadcaster: sends BROADCAST_CHUNK_SIZE messages concurrently,
    then sleeps BROADCAST_CHUNK_DELAY seconds before the next chunk.
    Effective rate: 25 msg/s — safely under Telegram's 30 msg/s global cap.

    Pass session_pool to enable automatic user deactivation on TelegramForbiddenError
    or 'chat not found' errors.
    """
    count = 0
    chunks = [
        users[i : i + BROADCAST_CHUNK_SIZE]
        for i in range(0, len(users), BROADCAST_CHUNK_SIZE)
    ]
    try:
        for idx, chunk in enumerate(chunks):
            results = await asyncio.gather(
                *[
                    send_message(bot, uid, text, disable_notification, reply_markup, photo, session_pool)
                    for uid in chunk
                ],
                return_exceptions=True,
            )
            count += sum(1 for r in results if r is True)
            if idx < len(chunks) - 1:
                await asyncio.sleep(BROADCAST_CHUNK_DELAY)
    finally:
        logging.info(f"{count} messages sent successfully.")

    return count
