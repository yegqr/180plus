import asyncio
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from infrastructure.database.models import User
from tgbot.services.topic_manager import TopicManager

class EnsureTopicsMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        user: User = data.get("user")
        
        # Check if the user obj exists and topic_ids is empty or missing
        if user and not user.settings.get("topic_ids"):
            dialog_manager = data.get("dialog_manager")
            repo = data.get("repo")
            bot = data.get("bot")
            
            # As long as aiogram-dialog is initialized, dialog_manager shouldn't be None
            if dialog_manager and repo and bot:
                # Synchronously await ensure_topics to guarantee it's created before handler executes
                await TopicManager.ensure_topics(bot, user, repo, dialog_manager)
        
        return await handler(event, data)
