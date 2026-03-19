import logging
from aiogram import Router
from aiogram.types import ErrorEvent
from aiogram_dialog.api.exceptions import OutdatedIntent, UnknownIntent
from aiogram_dialog import DialogManager

error_router = Router()

@error_router.error()
async def on_error(event: ErrorEvent, dialog_manager: DialogManager) -> None:
    if isinstance(event.exception, (OutdatedIntent, UnknownIntent)):
        logging.error(f"Intent error handled: {event.exception}")
        if event.update.callback_query:
            await event.update.callback_query.answer(
                "⚠️ Сесія застаріла. Будь ласка, відкрийте меню заново.",
                show_alert=True
            )
            try:
                if dialog_manager.current_stack():
                    await dialog_manager.reset_stack(remove_keyboard=True)
            except Exception:
                pass
        return True
    
    logging.exception(f"Unhandled error: {event.exception}")
