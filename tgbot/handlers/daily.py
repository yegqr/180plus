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
    if call.data == "daily:menu:home":
        from tgbot.dialogs.main_menu import MainSG
        from aiogram_dialog import StartMode
        await dialog_manager.start(MainSG.menu, mode=StartMode.RESET_STACK)
        return

    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer()
        return

    qid_str, user_ans = parts[1], parts[2]
    if not qid_str.isdigit():
        await call.answer()
        return
    qid = int(qid_str)

    if user_ans == "INPUT":
        from tgbot.dialogs.daily import DailySG
        from aiogram_dialog import StartMode
        await dialog_manager.start(DailySG.input, data={"qid": qid}, mode=StartMode.RESET_STACK)
        return

    question = await repo.questions.get_question_by_id(qid)
    if not question:
        await call.answer("Питання не знайдено.", show_alert=True)
        return

    correct_val = str(question.correct_answer.get("answer"))

    if user_ans == "SHOW_ANSWER":
        await call.answer(f"✅ Правильна відповідь: {correct_val}", show_alert=True)
        try:
            await repo.events.log_event(call.from_user.id, "daily_show_answer", {"question_id": qid})
        except Exception:
            pass
        return

    if user_ans == "EXPLAIN":
        explanation = question.explanation or ""
        if not explanation:
            await call.answer("Пояснення для цього завдання недоступне.", show_alert=True)
            return
        await call.answer()
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏠 В головне меню", callback_data="daily:menu:home"),
        ]])
        expl_block = f"\n\n💡 <b>Пояснення:</b>\n{explanation}"
        try:
            if call.message.photo:
                base = call.message.caption or ""
                await call.message.edit_caption(caption=base + expl_block, reply_markup=kb)
            else:
                base = call.message.text or ""
                await call.message.edit_text(base + expl_block, reply_markup=kb)
        except Exception:
            await call.message.answer(f"💡 <b>Пояснення:</b>\n{explanation}", reply_markup=kb)
        return

    # --- Regular answer ---
    is_correct = False
    if question.q_type == "choice":
        is_correct = (str(user_ans) == correct_val)
    elif question.q_type == "short":
        is_correct = (str(user_ans).strip() == correct_val.strip())

    try:
        await repo.daily_participation.record_answer(
            user_id=call.from_user.id,
            question_id=qid,
            answer=str(user_ans),
            is_correct=is_correct,
        )
        await repo.events.log_event(
            call.from_user.id, "daily_answered",
            {"question_id": qid, "is_correct": is_correct, "via": "button"},
        )
    except Exception as e:
        logger.warning(f"Daily: failed to record participation for user {call.from_user.id}: {e}")

    if is_correct:
        alert_text = "✅ Правильно! Молодець! 🔥"
        result_line = "✅ <b>Правильно! Молодець! 🔥</b>"
    else:
        alert_text = f"❌ Неправильно.\nПравильна відповідь: {correct_val} | Ваша відповідь: {user_ans}"
        result_line = f"❌ <b>Неправильно.</b>\nПравильна відповідь: <b>{correct_val}</b> | Ваша відповідь: {user_ans}"

    result_row = [InlineKeyboardButton(text="🏠 В головне меню", callback_data="daily:menu:home")]
    if question.explanation:
        result_row.insert(0, InlineKeyboardButton(text="💡 Пояснення", callback_data=f"daily:{qid}:EXPLAIN"))
    kb = InlineKeyboardMarkup(inline_keyboard=[result_row])

    await call.answer(text=alert_text, show_alert=True)
    try:
        if call.message.photo:
            base = call.message.caption or ""
            await call.message.edit_caption(caption=f"{base}\n\n{result_line}", reply_markup=kb)
        else:
            base = call.message.text or ""
            await call.message.edit_text(f"{base}\n\n{result_line}", reply_markup=kb)
    except Exception as e:
        logger.warning(f"Daily: failed to edit message for user {call.from_user.id}: {e}")

