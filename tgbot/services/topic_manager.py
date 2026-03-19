import logging
from typing import Dict, Optional
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

class TopicManager:
    SUBJECTS = {
        "math": "🧮 math",
        "mova": "🇺🇦 mova",
        "eng": "🇬🇧 eng",
        "hist": "📌 hist",
        "physics": "⚛️ phy",
    }

    @classmethod
    async def create_subject_topics(cls, bot: Bot, user_id: int) -> Dict[str, int]:
        """
        Creates 5 topics for the user in their private chat.
        Returns a mapping of subject_id -> message_thread_id.
        """
        topic_ids = {}
        for subject_id, name in cls.SUBJECTS.items():
            try:
                topic = await bot.create_forum_topic(chat_id=user_id, name=name)
                topic_ids[subject_id] = topic.message_thread_id
                logger.info(f"Created topic '{name}' (ID: {topic.message_thread_id}) for user {user_id}")
            except TelegramBadRequest as e:
                logger.error(f"Failed to create topic '{name}' for user {user_id}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error creating topic for user {user_id}: {e}")
                continue
        return topic_ids

    @classmethod
    async def rename_subject_topics(cls, bot: Bot, user_id: int, topic_ids: Dict[str, int]) -> None:
        """
        Renames existing topics to match the current SUBJECTS names.
        Useful when names have been updated in code but topics already exist.
        """
        for subject_id, thread_id in topic_ids.items():
            new_name = cls.SUBJECTS.get(subject_id)
            if not new_name:
                continue
            try:
                await bot.edit_forum_topic(
                    chat_id=user_id,
                    message_thread_id=thread_id,
                    name=new_name,
                )
                logger.info(f"Renamed topic '{subject_id}' -> '{new_name}' for user {user_id}")
            except Exception as e:
                logger.warning(f"Could not rename topic '{subject_id}' for user {user_id}: {e}")

    @classmethod
    async def ensure_topics(cls, bot: Bot, user, repo, dialog_manager, rename_if_exists: bool = False) -> bool:
        """
        Ensures all subject topics exist and have an active menu dialog.
        Returns True if new topics were created.
        """
        from tgbot.dialogs.subject_menu import SubjectMenuSG
        from aiogram_dialog import StartMode

        topic_ids = user.settings.get("topic_ids")
        
        # 1. If no topics in DB -> Create
        if not topic_ids:
            return await cls._do_create_topics(bot, user, repo, dialog_manager)

        # 2. If topics in DB, occasionally or on-demand check if they still exist in Telegram
        # (Telegram doesn't notify bot when user deletes topics)
        if rename_if_exists:
            # Try to rename first one to check existence
            first_subject = list(cls.SUBJECTS.keys())[0]
            first_thread_id = topic_ids.get(first_subject)
            
            try:
                await bot.edit_forum_topic(
                    chat_id=user.user_id,
                    message_thread_id=first_thread_id,
                    name=cls.SUBJECTS[first_subject]
                )
                # If worked, proceed with the rest of renames
                await cls.rename_subject_topics(bot, user.user_id, topic_ids)
            except TelegramBadRequest as e:
                if "message thread not found" in e.message.lower() or "not found" in e.message.lower():
                    # Topics deleted in Telegram! 
                    logger.warning(f"Topics found in DB but missing in Telegram for user {user.user_id}. Recreating...")
                    user.settings.pop("topic_ids", None)
                    return await cls._do_create_topics(bot, user, repo, dialog_manager)
        
        return False

    @classmethod
    async def _do_create_topics(cls, bot, user, repo, dialog_manager) -> bool:
        from tgbot.dialogs.subject_menu import SubjectMenuSG
        from aiogram_dialog import StartMode

        topic_ids = await cls.create_subject_topics(bot, user.user_id)
        if topic_ids:
            user.settings["topic_ids"] = topic_ids
            await repo.users.update_user_settings(user.user_id, user.settings)
            
            for subject, thread_id in topic_ids.items():
                try:
                    bg = dialog_manager.bg(
                        user_id=user.user_id, 
                        chat_id=user.user_id, 
                        stack_id=subject, 
                        thread_id=thread_id
                    )
                    await bg.start(SubjectMenuSG.menu, mode=StartMode.RESET_STACK)
                    logger.info(f"Started dialog for {subject} in thread {thread_id}")
                except Exception as e:
                    logger.error(f"Failed to start dialog in thread {thread_id}: {e}")
            return True
        return False

    @classmethod
    def get_subject_by_thread_id(cls, topic_ids: Dict[str, int], thread_id: Optional[int]) -> Optional[str]:
        """
        Finds the subject ID by the message_thread_id.
        """
        if not thread_id:
            return None
        for subj, tid in topic_ids.items():
            if tid == thread_id:
                return subj
        return None
