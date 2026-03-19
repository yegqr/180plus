from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

if TYPE_CHECKING:
    from aiogram_dialog import DialogManager
    from infrastructure.database.models import User
    from infrastructure.database.repo.requests import RequestsRepo

logger = logging.getLogger(__name__)


class TopicManager:
    SUBJECTS = {
        "math":    "🧮 math",
        "mova":    "🇺🇦 mova",
        "eng":     "🇬🇧 eng",
        "hist":    "📌 hist",
        "physics": "⚛️ phy",
    }

    @classmethod
    async def create_subject_topics(cls, bot: Bot, user_id: int) -> dict[str, int]:
        """Creates 5 subject topics for the user. Returns subject_id → thread_id mapping."""
        topic_ids: dict[str, int] = {}
        for subject_id, name in cls.SUBJECTS.items():
            try:
                topic = await bot.create_forum_topic(chat_id=user_id, name=name)
                topic_ids[subject_id] = topic.message_thread_id
                logger.info(f"Created topic '{name}' (ID: {topic.message_thread_id}) for user {user_id}")
            except TelegramBadRequest as e:
                logger.error(f"Failed to create topic '{name}' for user {user_id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error creating topic for user {user_id}: {e}")
        return topic_ids

    @classmethod
    async def rename_subject_topics(
        cls, bot: Bot, user_id: int, topic_ids: dict[str, int]
    ) -> None:
        """Renames existing topics to match the current SUBJECTS names."""
        for subject_id, thread_id in topic_ids.items():
            new_name = cls.SUBJECTS.get(subject_id)
            if not new_name:
                continue
            try:
                await bot.edit_forum_topic(
                    chat_id=user_id, message_thread_id=thread_id, name=new_name
                )
                logger.info(f"Renamed topic '{subject_id}' -> '{new_name}' for user {user_id}")
            except Exception as e:
                logger.warning(f"Could not rename topic '{subject_id}' for user {user_id}: {e}")

    @classmethod
    async def ensure_topics(
        cls,
        bot: Bot,
        user: User,
        repo: RequestsRepo,
        dialog_manager: DialogManager,
        rename_if_exists: bool = False,
    ) -> bool:
        """Ensures all subject topics exist. Returns True if new topics were created."""
        topic_ids = user.settings.get("topic_ids")

        if not topic_ids:
            return await cls._do_create_topics(bot, user, repo, dialog_manager)

        if rename_if_exists:
            first_subject = list(cls.SUBJECTS.keys())[0]
            first_thread_id = topic_ids.get(first_subject)
            try:
                await bot.edit_forum_topic(
                    chat_id=user.user_id,
                    message_thread_id=first_thread_id,
                    name=cls.SUBJECTS[first_subject],
                )
                await cls.rename_subject_topics(bot, user.user_id, topic_ids)
            except TelegramBadRequest as e:
                if "message thread not found" in e.message.lower() or "not found" in e.message.lower():
                    logger.warning(
                        f"Topics in DB but missing in Telegram for user {user.user_id}. Recreating..."
                    )
                    user.settings.pop("topic_ids", None)
                    return await cls._do_create_topics(bot, user, repo, dialog_manager)

        return False

    @classmethod
    async def _do_create_topics(
        cls,
        bot: Bot,
        user: User,
        repo: RequestsRepo,
        dialog_manager: DialogManager,
    ) -> bool:
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
                        thread_id=thread_id,
                    )
                    await bg.start(SubjectMenuSG.menu, mode=StartMode.RESET_STACK)
                    logger.info(f"Started dialog for {subject} in thread {thread_id}")
                except Exception as e:
                    logger.error(f"Failed to start dialog in thread {thread_id}: {e}")
            return True
        return False

    @classmethod
    def get_subject_by_thread_id(
        cls, topic_ids: dict[str, int], thread_id: int | None
    ) -> str | None:
        """Finds the subject ID matching a message_thread_id."""
        if not thread_id:
            return None
        for subj, tid in topic_ids.items():
            if tid == thread_id:
                return subj
        return None
