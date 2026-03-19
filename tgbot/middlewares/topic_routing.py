from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from infrastructure.database.models import User


class TopicRoutingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,  # Can be Message or CallbackQuery depending on which stack it's registered on
        data: Dict[str, Any],
    ) -> Any:
        user: User = data.get("user")
        if not user:
            return await handler(event, data)

        # Get thread_id from event directly (Message or CallbackQuery)
        thread_id = None
        if isinstance(event, Message):
            thread_id = event.message_thread_id
        elif isinstance(event, CallbackQuery) and event.message:
            thread_id = event.message.message_thread_id

        if thread_id:
            topic_ids = user.settings.get("topic_ids", {})
            for subj, tid in topic_ids.items():
                if tid == thread_id:
                    if user.selected_subject != subj:
                        user.selected_subject = subj
                        repo = data.get("repo")
                        if repo:
                            await repo.users.update_subject(user.user_id, subj)
                    break

        return await handler(event, data)
