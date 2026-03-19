
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InputMediaPhoto, Message
from aiogram_dialog import DialogManager

logger = logging.getLogger(__name__)

class AlbumManager:
    """
    Helper service to manage sending and deleting media groups (albums).
    We use this because aiogram_dialog doesn't natively support albums well yet.
    """

    @staticmethod
    async def send_album(
        bot: Bot,
        chat_id: int,
        image_file_ids: list[str],
        caption: str | None = None,
    ) -> list[int]:
        """
        Sends a media group (album) and returns the list of message IDs.
        """
        if not image_file_ids:
            return []

        # If only 1 image, better to let aiogram-dialog handle it via DynamicMedia? 
        # But this service might be used to force "Album" behavior or uniformity.
        # However, for 1 image a simple photo message is better. 
        # But the caller (dialog) decides when to use this. 
        # If caller passes 1 image here, we send as MediaGroup? Telegran allows 2-10 for album.
        # If 1 image, it is NOT an album. send_media_group throws error if length < 2? 
        # Actually yes, MediaGroup must have 2-10 items.
        
        if len(image_file_ids) < 2:
            return []

        media_group = []
        for i, file_id in enumerate(image_file_ids):
            # Only the first item supports a caption in the album notification, 
            # but in the chat it shows up at the bottom.
            media_group.append(
                InputMediaPhoto(
                    media=file_id, 
                    caption=caption if i == 0 else None
                )
            )

        try:
            messages: list[Message] = await bot.send_media_group(chat_id=chat_id, media=media_group)
            return [m.message_id for m in messages]
        except Exception as e:
            logger.error(f"Failed to send album: {e}")
            return []

    @staticmethod
    async def cleanup_album(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
        """
        Deletes the album messages.
        """
        if not message_ids:
            return
        
        # We can try delete_messages (plural) if aiogram supports it (from v3.x?)
        # Or delete one by one.
        try:
            # delete_messages is available in recent Bot API.
            # Only valid for messages in the same chat.
            # aiogram 3.x 'bot.delete_messages' might exist.
            # If not, use loop.
            # Let's check if delete_messages exists dynamically or just loop for safety.
            if hasattr(bot, "delete_messages"):
                 await bot.delete_messages(chat_id, message_ids)
            else:
                 for mid in message_ids:
                     try:
                         await bot.delete_message(chat_id, mid)
                     except Exception:
                         pass
        except Exception as e:
            logger.warning(f"Failed to cleanup album {message_ids}: {e}")
