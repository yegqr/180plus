from __future__ import annotations

from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, Window, DialogManager
from aiogram_dialog.widgets.input import TextInput
from aiogram_dialog.widgets.kbd import Button, Row
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.repo.requests import RequestsRepo
from .main_menu import MainSG

class DailySG(StatesGroup):
    input = State()
    result = State()

async def check_answer(message: Message, widget: TextInput, dialog_manager: DialogManager, text: str) -> None:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    start_data = dialog_manager.start_data
    qid = start_data.get("qid")
    
    question = await repo.questions.get_question_by_id(qid)
    if not question:
        await message.answer("Помилка: запитання не знайдено.")
        await dialog_manager.done()
        return

    correct_val = str(question.correct_answer.get("answer")).strip().lower().replace(",", ".")
    user_ans = text.strip().lower().replace(",", ".")
    
    if user_ans == correct_val:
        dialog_manager.dialog_data["result_text"] = "✅ Правильно! Молодець! 🔥"
        dialog_manager.dialog_data["is_correct"] = True
    else:
        dialog_manager.dialog_data["result_text"] = f"❌ Неправильно. Правильна відповідь: {question.correct_answer.get('answer')}"
        dialog_manager.dialog_data["is_correct"] = False
        
    await dialog_manager.switch_to(DailySG.result)

async def to_main_menu(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.done()

daily_dialog = Dialog(
    Window(
        Const("✍️ <b>Введіть вашу відповідь:</b>"),
        TextInput(
            id="daily_input",
            type_factory=str,
            on_success=check_answer,
        ),
        Row(
            Button(Const("🏠 В меню"), id="btn_home", on_click=to_main_menu),
        ),
        state=DailySG.input,
    ),
    Window(
        Format("{result_text}"),
        Row(
            Button(Const("🏠 В меню"), id="btn_home_res", on_click=to_main_menu),
        ),
        state=DailySG.result,
    ),
)
