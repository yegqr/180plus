import logging
from aiogram import Router, Bot
from aiogram.types import ChatJoinRequest, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram_dialog import StartMode, BgManagerFactory

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.dialogs.main_menu import MainSG

join_router = Router()

@join_router.chat_join_request()
async def handle_join_request(
    update: ChatJoinRequest, 
    bot: Bot, 
    repo: RequestsRepo, 
    dialog_bg_factory: BgManagerFactory
):
    # 1. Register or update user
    user = await repo.users.get_or_create_user(
        user_id=update.from_user.id,
        full_name=update.from_user.full_name,
        language=update.from_user.language_code or "en",
        username=update.from_user.username,
    )
    
    # Store pending request for bulk approval
    await repo.join_requests.add_request(update.from_user.id, update.chat.id)
    
    # 2. Track Statistics (UTM)
    invite_link = update.invite_link
    source = "unknown"
    if invite_link:
        # invite_link is a ChatInviteLink object. We use its name or invite_link string.
        # Ideally user wants "name" if available, or the link itself.
        source = invite_link.name or invite_link.invite_link or "unknown"
        
    await repo.stats.add_join_stat(update.from_user.id, source)
    
    # 3. Send welcome message (private chat)
    welcome_text = (
        f"👋 Вітаю, {update.from_user.full_name}!\n\n"
        "Отримали ваш запит на вступ до каналу, приймемо його за декілька хвилин.\n\n"
        "Цей телеграм-бот — як OSVITA.UA, тільки в ТГ й зі злитими НМТ! Спробуй вирішити прям зараз 👇"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Минулорічні НМТ", callback_data="start_menu")]
        ]
    )
    try:
        await bot.send_message(chat_id=update.from_user.id, text=welcome_text, reply_markup=keyboard)
        logging.info(f"Welcome message sent to user {update.from_user.id} after join request.")
        # We don't start the dialog here anymore, the button will do it.
        
    except Exception as e:
        logging.error(f"Error handling join request for {update.from_user.id}: {e}")
