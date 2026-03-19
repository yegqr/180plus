from __future__ import annotations

import random
from typing import Any

from aiogram import F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ContentType, Message
from aiogram_dialog import Dialog, Window, DialogManager, ShowMode, StartMode
from aiogram_dialog.api.entities import MediaAttachment, MediaId
from aiogram_dialog.widgets.kbd import Button, Row, Select, Group, Column
from aiogram_dialog.widgets.media import DynamicMedia
from aiogram_dialog.widgets.text import Const, Format, Case
from aiogram_dialog.widgets.input import MessageInput

from tgbot.services.album_manager import AlbumManager

from infrastructure.database.models import User, Question
from infrastructure.database.repo.requests import RequestsRepo

from tgbot.misc.constants import UKR_LETTERS, ENG_LETTERS
from tgbot.misc.utils import build_answer_ui, build_hint_text, build_wrong_answer_status, get_question_images
from tgbot.services.scoring import check_random_answer

class RandomSG(StatesGroup):
    question = State()

# --- Getters ---

async def get_random_question(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    
    # If no question picked yet (should be handled by on_start/on_next, but safety fallback)
    q_id = dialog_manager.dialog_data.get("current_q_id")
    if not q_id:
        return {"has_questions": False}

    # Album Logic
    is_album = bool(dialog_manager.dialog_data.get("album_message_ids"))
    
    question: Question = await repo.questions.get_question_by_id(q_id)
    dialog_manager.dialog_data["current_explanation"] = question.explanation
    
    image = None
    if not is_album:
        images = get_question_images(question)
        if images:
            image = MediaAttachment(type=ContentType.PHOTO, file_id=MediaId(images[0]))
    
    letters_source = ENG_LETTERS if user.selected_subject == "eng" else UKR_LETTERS
    choice_variants, match_nums, match_letters = build_answer_ui(
        question.q_type, question.correct_answer, letters_source
    )

    user_ans = dialog_manager.dialog_data.get("user_answer")
    is_correct = dialog_manager.dialog_data.get("is_correct")
    
    status_text = ""
    if is_correct is True:
        status_text = "✅ <b>Правильно!</b>"
    elif is_correct is False:
        status_text = build_wrong_answer_status(question.q_type, question.correct_answer, user_ans)

    active_num = dialog_manager.dialog_data.get("active_match_num")
    hint = build_hint_text(question.q_type, active_num, user.selected_subject)

    show_explanation = dialog_manager.dialog_data.get("show_explanation", False)
    import html
    expl_text = html.escape(question.explanation or "") if show_explanation else ""

    # History Logic
    history_warning = ""
    previous_answers_fmt = ""
    
    # 1. Check failures if not answered yet (Tricky warning)
    if not is_correct and not user_ans:
        failures = await repo.logs.get_question_failures_count(user.user_id, q_id)
        if failures > 0:
            history_warning = "⚠️ <b>Це завдання підступне!</b> Ти його вже вирішував/ла неправильно. Be careful :)"

    # 2. Show history if answered (or if user just wants to see?)
    # User said: "After he did the test" -> Show history
    if is_correct is not None:
        # Fetch history (excluding current attempt ideally, or including?)
        # Current attempt is not in DB yet (saved async). 
        # Actually check_answer saves it. so if we fetch now we might see it?
        # Let's fetch last 5.
        history = await repo.logs.get_question_history(user.user_id, q_id, limit=5)
        if history:
             # Filter out current answer if it's the top one?
             # Or just show all.
             previous_answers_fmt = "\n\n📜 <b>Минулі відповіді:</b> " + "; ".join(history)

    material = await repo.materials.get_by_subject(user.selected_subject)
    has_materials = bool(material and material.images)
    show_materials = dialog_manager.dialog_data.get("show_materials", False)
    
    materials_label = "📚 Довідкові матеріали (Приховати)" if show_materials else "📚 Довідкові матеріали (Показати)"

    return {
        "has_questions": True,
        "question_image": image,
        "is_album": is_album,
        "q_type": question.q_type,
        "choice_variants": choice_variants,
        "match_nums": match_nums,
        "match_letters": match_letters,
        "active_num": active_num,
        "status_text": status_text,
        "hint": hint,
        "answered": is_correct is not None,
        "has_explanation": bool(question.explanation),
        "show_explanation": show_explanation,
        "explanation_text": expl_text,
        "history_warning": history_warning,
        "history_text": previous_answers_fmt,
        "has_materials": has_materials,
        "materials_label": materials_label,
    }

# --- Handlers ---

async def update_question_view(dm: DialogManager, q_id: int | None = None, pick_new: bool = False) -> None:
    """
    Handles switching questions, sending new albums, and cleaning old ones in Random Mode.
    """
    bot = dm.middleware_data.get("bot")
    repo: RequestsRepo = dm.middleware_data.get("repo")
    user: User = dm.middleware_data.get("user")

    # 1. Cleanup Old Album
    old_album_ids = dm.dialog_data.get("album_message_ids")
    if old_album_ids:
        # random mode user_id is chat_id
        chat_id = user.user_id
        await AlbumManager.cleanup_album(bot, chat_id, old_album_ids)
        dm.dialog_data["album_message_ids"] = []

    # 2. Pick/Update Question
    if q_id is not None:
        dm.dialog_data["current_q_id"] = q_id
        dm.dialog_data["user_answer"] = None
        dm.dialog_data["is_correct"] = None
        dm.dialog_data["active_match_num"] = None
        dm.dialog_data["show_explanation"] = False
    elif pick_new:
        q_ids = await repo.questions.get_questions_ids_by_subject(user.selected_subject)
        if not q_ids:
            dm.dialog_data["current_q_id"] = None
            return
        q_id = random.choice(q_ids)
        dm.dialog_data["current_q_id"] = q_id
        dm.dialog_data["user_answer"] = None
        dm.dialog_data["is_correct"] = None
        dm.dialog_data["active_match_num"] = None
        dm.dialog_data["show_explanation"] = False
    
    current_id = dm.dialog_data.get("current_q_id")
    if not current_id: return

    question = await repo.questions.get_question_by_id(current_id)
    
    # 3. Check for Album (including materials)
    images = get_question_images(question)

    if dm.dialog_data.get("show_materials"):
        material = await repo.materials.get_by_subject(user.selected_subject)
        if material and material.images:
            images = images + material.images

    if len(images) > 1:
        chat_id = user.user_id
        
        # Bug Fix: try to delete previous dialog message
        try:
            stack = dm.current_stack()
            if stack and stack.last_message_id:
                await bot.delete_message(chat_id, stack.last_message_id)
        except Exception:
            pass  # fire-and-forget cleanup

        album_ids = await AlbumManager.send_album(bot, chat_id, images, caption=None)
        dm.dialog_data["album_message_ids"] = album_ids
        dm.show_mode = ShowMode.SEND
    else:
        dm.show_mode = ShowMode.EDIT

async def check_answer(dm: DialogManager, user_ans: Any) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    user: User = dm.middleware_data.get("user")
    q_id = dm.dialog_data.get("current_q_id")
    question = await repo.questions.get_question_by_id(q_id)

    result = check_random_answer(
        q_type=question.q_type,
        correct_answer=question.correct_answer,
        user_answer=user_ans,
        subject=user.selected_subject,
    )

    dm.dialog_data["user_answer"] = user_ans
    dm.dialog_data["is_correct"] = result.is_correct

    if result.points_earned > 0:
        await repo.results.save_random_result(
            user.user_id, user.selected_subject, q_id, points=result.points_earned
        )

    log_ans = (
        ", ".join(f"{k}-{v}" for k, v in sorted(user_ans.items()))
        if isinstance(user_ans, dict)
        else str(user_ans)
    )
    await repo.logs.add_log(
        user_id=user.user_id,
        question_id=q_id,
        answer=log_ans,
        is_correct=result.is_correct,
        mode="random",
    )

async def on_choice_selected(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    if dm.dialog_data.get("is_correct") is not None: return
    await check_answer(dm, item_id)

async def on_match_num_selected(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    if dm.dialog_data.get("is_correct") is not None: return
    dm.dialog_data["active_match_num"] = item_id

async def on_match_letter_selected(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    active_num = dm.dialog_data.get("active_match_num")
    if not active_num: return

    ans_data = dm.dialog_data.get("user_answer", {})
    if not isinstance(ans_data, dict): ans_data = {}
    ans_data[active_num] = item_id
    dm.dialog_data["user_answer"] = ans_data
    dm.dialog_data["active_match_num"] = None

    # Check if all pairs filled
    repo: RequestsRepo = dm.middleware_data.get("repo")
    q_id = dm.dialog_data.get("current_q_id")
    question = await repo.questions.get_question_by_id(q_id)
    target_count = len(question.correct_answer.get("pairs", {}))

    if len(ans_data) >= target_count:
        await check_answer(dm, ans_data)

async def on_answer_text(m: Message, w: MessageInput, dm: DialogManager) -> None:
    if dm.dialog_data.get("is_correct") is not None:
        await m.delete()
        return
    dm.show_mode = ShowMode.EDIT
    await check_answer(dm, m.text)
    await m.delete()

async def on_show_explanation(c: Any, b: Button, dm: DialogManager) -> None:
    current = dm.dialog_data.get("show_explanation", False)
    dm.dialog_data["show_explanation"] = not current

async def on_show_materials(c: Any, b: Button, dm: DialogManager) -> None:
    current = dm.dialog_data.get("show_materials", False)
    dm.dialog_data["show_materials"] = not current

    # Refresh view with new image set
    await update_question_view(dm)

async def on_next_random(c: Any, b: Button, dm: DialogManager) -> None:
    await update_question_view(dm, pick_new=True)

async def on_random_start(data: Any, dm: DialogManager) -> None:
    await update_question_view(dm, pick_new=True)


# --- Dialog ---

random_dialog = Dialog(
    Window(
        DynamicMedia("question_image", when=F["has_questions"] & ~F["show_explanation"] & ~F["is_album"]),
        Format("{history_warning}", when="history_warning"), # Warning at top
        Format("{status_text}{history_text}", when="has_questions"), # Status + History
        Format("\n<i>{hint}</i>", when=F["has_questions"] & ~F["show_explanation"]),
        Const("Задач з цього предмета поки немає.", when=~F["has_questions"]),
        
        # Choice UI
        Group(
            Select(Format("{item[0]}"), id="ans_choice", item_id_getter=lambda x: x[1], items="choice_variants", on_click=on_choice_selected),
            width=5, when=F["has_questions"] & (F["q_type"] == "choice") & ~F["answered"]
        ),
        
        # Match UI
        Row(
            Select(
                Format("·{item[0]}·" if F["active_num"] == F["item"][0] else "{item[0]}"),
                id="match_n", item_id_getter=lambda x: x[1], items="match_nums", on_click=on_match_num_selected
            ),
            when=F["has_questions"] & (F["q_type"] == "match") & ~F["active_num"] & ~F["answered"]
        ),
        Row(
            Select(Format("{item[0]}"), id="match_l", item_id_getter=lambda x: x[1], items="match_letters", on_click=on_match_letter_selected),
            when=F["has_questions"] & (F["q_type"] == "match") & F["active_num"] & ~F["answered"]
        ),
        Button(
            Format("{materials_label}"), 
            id="btn_materials", 
            on_click=on_show_materials, 
            when=F["has_questions"] & F["has_materials"] & ~F["answered"]
        ),
        
        # Text input (only for short)
        MessageInput(on_answer_text, content_types=[ContentType.TEXT]),
        
        # Explanation Text
        Format("\n💡 <b>Пояснення:</b>\n{explanation_text}", when="show_explanation"),

        # Controls
        Column(
            Button(Const("💡 Показати пояснення"), id="expl_show", on_click=on_show_explanation, when=F["answered"] & F["has_explanation"] & ~F["show_explanation"]),
            Button(Const("🙈 Сховати пояснення"), id="expl_hide", on_click=on_show_explanation, when=F["answered"] & F["show_explanation"]),
            
            Button(Const("🎲 Наступне"), id="next", on_click=on_next_random, when="answered"),
            Button(Const("🏠 Меню"), id="to_menu", on_click=lambda c, b, d: d.done()),
        ),
        state=RandomSG.question,
        getter=get_random_question,
    ),
    on_start=on_random_start
)
