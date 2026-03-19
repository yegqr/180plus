from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from aiogram_dialog import DialogManager, StartMode

from tgbot.dialogs.admin import AdminSG
from tgbot.filters.admin import AdminFilter

admin_router = Router()
admin_router.message.filter(AdminFilter())


@admin_router.message(Command("admin_upload"))
async def admin_upload(message: Message, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(AdminSG.subjects, mode=StartMode.RESET_STACK)
