import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject, User

from infrastructure.database.repo.requests import RequestsRepo

logger = logging.getLogger(__name__)

class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        repo: RequestsRepo = data.get("repo")
        if not repo:
            # Should be handled after DatabaseMiddleware
            return await handler(event, data)

        # Check maintenance setting
        m_mode = await repo.settings.get_setting("maintenance_mode", "false")
        
        if m_mode.lower() != "true":
            return await handler(event, data)

        # Maintenance is ON
        # Check if user is admin
        user: User = data.get("event_from_user")
        if not user:
            # No user? Maybe service update. Let it pass or block.
            return await handler(event, data)

        # We can check is_admin from DB (repo.users) or config.
        # User object in data["user"] (from DB middleware?)
        # Let's check `data.get("user")` which is the DB User object if DatabaseMiddleware put it there (usually it doesn't automatically put DB user unless we custom logic).
        # But we have `repo`.
        # NOTE: DatabaseMiddleware in this bot (I saw previously) likely passes `repo` but maybe not the user object?
        # Let's assume we check ID against config admins FIRST for safety, then DB admins.
        
        config = data.get("config")
        is_admin = False
        if user.id in config.tg_bot.admin_ids:
            is_admin = True
        else:
             # Check DB
             db_user = await repo.users.get_user_by_id(user.id)
             if db_user and db_user.is_admin:
                 is_admin = True

        if is_admin:
            return await handler(event, data)

        # Block user
        m_msg = await repo.settings.get_setting("maintenance_message")
        if not m_msg:
            m_msg = "⛔️ <b>Вибачте, в нас технічні роботи в боті.</b>\nНайближчим часом запустимо бота з оновленнями!"

        # Reply if message or answer if callback
        if isinstance(event, Message):
            # To avoid spam loops, maybe check if message text is NOT the maintenance message (bot shouldn't reply to self anyway).
            # Just reply.
            await event.answer(m_msg)
        elif isinstance(event, CallbackQuery):
            await event.answer(m_msg, show_alert=True)
        
        # Stop propagation
        return
