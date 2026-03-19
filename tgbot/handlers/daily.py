from datetime import datetime, timedelta
import random
import logging
import asyncio

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram_dialog import DialogManager
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.repo.requests import RequestsRepo

logger = logging.getLogger(__name__)

daily_router = Router()

# Callback factory or simple split
# format: daily:qid:answer_val

@daily_router.callback_query(F.data.startswith("daily:"))
async def on_daily_answer(call: CallbackQuery, bot: Bot, repo: RequestsRepo, dialog_manager: DialogManager = None) -> None:
    # Check for Home button first
    if call.data == "daily:menu:home":
        # Start main menu if possible
        # We need to import main menu state
        from tgbot.dialogs.main_menu import MainSG
        from aiogram_dialog import StartMode
        # If dialog_manager is available (via middleware), use it. 
        # But wait, this is a plain handler, dialog middleware IS running because we use Dispatcher.
        # But we need to accept `dialog_manager`. Added to signature.
        await dialog_manager.start(MainSG.menu, mode=StartMode.RESET_STACK)
        # Maybe delete the daily message to clean up? Or just leave it. User can answer later.
        # Let's feedback
        # await call.answer("🏠 Переходимо в меню...")
        return

    # Data: daily:qid:answer
    parts = call.data.split(":")
    if len(parts) != 3:
        return
    
    qid = int(parts[1])
    user_ans = parts[2]
    
    # Handle Input Request
    if user_ans == "INPUT":
        from tgbot.dialogs.daily import DailySG
        from aiogram_dialog import StartMode
        await dialog_manager.start(DailySG.input, data={"qid": qid}, mode=StartMode.RESET_STACK)
        return

    question = await repo.questions.get_question_by_id(qid)
    if not question:
        await call.answer("Questions not found.", show_alert=True)
        return

    correct_val = str(question.correct_answer.get("answer"))

    # Handle "SHOW_ANSWER"
    if user_ans == "SHOW_ANSWER":
        await call.answer(f"✅ Правильна відповідь: {correct_val}", show_alert=True)
        return

    # Check correctness
    is_correct = False
    
    if question.q_type == "choice":
        is_correct = (str(user_ans) == correct_val)
    elif question.q_type == "short":
        # Simplified for short, though buttons usually imply choice
        is_correct = (str(user_ans).strip() == correct_val.strip())
        
    if is_correct:
        await call.answer("✅ Правильно! Молодець! 🔥", show_alert=True)
        # Optional: Edit message to show success state?
    else:
        await call.answer(f"❌ Неправильно. Правильна відповідь: {correct_val}", show_alert=True)

