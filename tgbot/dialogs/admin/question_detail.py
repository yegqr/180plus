"""
Admin question detail view: show question, toggle explanation/categories, Gemini regeneration.
"""

from __future__ import annotations

import html
import logging
from typing import Any

from aiogram import F
from aiogram.types import ContentType
from aiogram_dialog import DialogManager, ShowMode, Window
from aiogram_dialog.api.entities import MediaAttachment, MediaId
from aiogram_dialog.widgets.kbd import Button, Row
from aiogram_dialog.widgets.media import DynamicMedia
from aiogram_dialog.widgets.text import Const, Format
from sqlalchemy import select

from infrastructure.database.models import Question
from infrastructure.database.repo.requests import RequestsRepo
from tgbot.misc.constants import TG_CAPTION_SAFE_LIMIT, TG_TEXT_SAFE_LIMIT
from tgbot.misc.utils import get_question_images
from tgbot.services.album_manager import AlbumManager
from .states import AdminSG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure display helpers
# ---------------------------------------------------------------------------

def _format_answer_text(q_type: str, correct_answer: dict) -> str:
    """Returns a human-readable answer string for the admin question detail view."""
    if q_type == "match":
        return ", ".join(f"{k}-{v}" for k, v in correct_answer.get("pairs", {}).items())
    if q_type == "choice":
        return f"{correct_answer.get('answer')} (з {correct_answer.get('options')})"
    if q_type == "short":
        return str(correct_answer.get("answer", ""))
    return str(correct_answer)


def _resolve_categories_text(categories: list[str] | None) -> str:
    """Resolves category slugs to human-readable names. Returns '—' when empty."""
    if not categories:
        return "—"
    from tgbot.misc.categories import CATEGORIES
    flat: dict[str, str] = {}
    for subj_data in CATEGORIES.values():
        for section_cats in subj_data.values():
            for c in section_cats:
                flat[c["slug"]] = c["name"]
    return ", ".join(flat.get(slug, slug) for slug in categories)


def _truncate_explanation(
    explanation_safe: str,
    ans_text: str,
    show_image: bool,
    is_long_text: bool,
) -> str:
    """Trims explanation to fit within Telegram message limits."""
    if show_image and is_long_text:
        limit = TG_CAPTION_SAFE_LIMIT - len(ans_text)
        if len(explanation_safe) > limit:
            return (
                explanation_safe[:limit]
                + "...\n(<i>текст обрізано, натисніть '📝 Показати текст'</i>)"
            )
    elif not show_image and len(explanation_safe) > TG_TEXT_SAFE_LIMIT:
        return (
            explanation_safe[:TG_TEXT_SAFE_LIMIT]
            + "...\n(<i>текст занадто довгий для Telegram</i>)"
        )
    return explanation_safe


# ---------------------------------------------------------------------------
# Getter
# ---------------------------------------------------------------------------

async def get_question_detail(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    q_id = dialog_manager.dialog_data.get("admin_q_id")
    question = await repo.questions.get_question_by_id(q_id)

    if not question:
        return {"q": None, "image": None, "ans_text": "Питання видалено"}

    image = MediaAttachment(type=ContentType.PHOTO, file_id=MediaId(question.image_file_id))
    ans_text = _format_answer_text(question.q_type, question.correct_answer)
    categories_text = _resolve_categories_text(question.categories)

    show_expl = dialog_manager.dialog_data.get("show_expl", False)
    show_cats = dialog_manager.dialog_data.get("show_cats", False)
    raw_explanation = question.explanation

    explanation_safe = None
    is_long_text = False
    if show_expl and raw_explanation:
        explanation_safe = html.escape(raw_explanation)
        is_long_text = len(ans_text) + len(explanation_safe) + 200 > TG_CAPTION_SAFE_LIMIT

    force_image = dialog_manager.dialog_data.get("force_image", False)
    is_album = bool(dialog_manager.dialog_data.get("album_message_ids"))
    show_image = (
        image is not None
        and not is_album
        and (not show_expl or not is_long_text or force_image)
    )

    if explanation_safe:
        explanation_safe = _truncate_explanation(explanation_safe, ans_text, show_image, is_long_text)

    return {
        "q":                question,
        "image":            image,
        "ans_text":         ans_text,
        "explanation_safe": explanation_safe,
        "categories_text":  categories_text,
        "is_long_text":     is_long_text,
        "show_image":       show_image,
        "force_image":      force_image,
        "show_expl":        show_expl,
        "show_cats":        show_cats,
        "has_expl":         bool(raw_explanation),
        "has_cats":         bool(question.categories),
        "is_album":         is_album,
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def on_toggle_expl(c: Any, b: Any, dm: DialogManager) -> None:
    dm.dialog_data["show_expl"] = not dm.dialog_data.get("show_expl", False)


async def on_toggle_view(c: Any, b: Any, dm: DialogManager) -> None:
    dm.dialog_data["force_image"] = not dm.dialog_data.get("force_image", False)


async def on_toggle_cats(c: Any, b: Any, dm: DialogManager) -> None:
    dm.dialog_data["show_cats"] = not dm.dialog_data.get("show_cats", False)


async def on_back_from_detail(c: Any, b: Any, dm: DialogManager) -> None:
    bot = dm.middleware_data.get("bot")
    old_album = dm.dialog_data.get("album_message_ids")
    if old_album:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album)
        dm.dialog_data["album_message_ids"] = []
    await dm.switch_to(AdminSG.questions)


async def on_delete_q(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")

    old_album = dm.dialog_data.get("album_message_ids")
    if old_album:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album)
        dm.dialog_data["album_message_ids"] = []

    q_id = dm.dialog_data["admin_q_id"]
    actor = dm.middleware_data.get("user")
    await repo.questions.delete_question(q_id)
    await repo.audit.log_action(
        admin_id=actor.user_id, action="question_deleted", target_id=str(q_id)
    )
    await dm.switch_to(AdminSG.questions)


async def on_edit_q(c: Any, b: Any, dm: DialogManager) -> None:
    bot = dm.middleware_data.get("bot")
    old_album = dm.dialog_data.get("album_message_ids")
    if old_album:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album)
        dm.dialog_data["album_message_ids"] = []
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor = dm.middleware_data.get("user")
    await repo.audit.log_action(
        admin_id=actor.user_id, action="question_edit_started",
        target_id=str(dm.dialog_data.get("admin_q_id")),
    )
    await dm.switch_to(AdminSG.upload_new)


async def _regen_explanation_bg(
    bot: Any,
    user_id: int,
    image_ids: list[str],
    q_id: int,
    q_number: int,
    q_text: str,
    api_key: str,
    subject: str,
) -> None:
    """Background task: downloads images, calls Gemini, writes result directly to DB."""
    from tgbot.services.gemini import GeminiService
    try:
        images_data = []
        for img_id in image_ids:
            f = await bot.get_file(img_id)
            fb = await bot.download_file(f.file_path)
            images_data.append(fb.read())

        result_data = await GeminiService(api_key).generate_explanation(
            images_data, q_text, subject=subject
        )
        text = result_data.get("explanation", "")
        cats = result_data.get("categories", [])

        async with bot.session_pool() as session:
            res = await session.execute(select(Question).where(Question.id == q_id))
            q = res.scalar_one_or_none()
            if q:
                q.explanation = text
                if cats:
                    q.categories = cats
                await session.commit()

        await bot.send_message(user_id, f"✅ Пояснення та категорії оновлено для Q#{q_number}!")
    except Exception as ex:
        logger.error(f"Regen Error: {ex}")
        await bot.send_message(user_id, f"❌ Помилка генерації для Q#{q_number}")


async def on_regenerate_explanation(c: Any, b: Any, dm: DialogManager) -> None:
    import asyncio

    repo: RequestsRepo = dm.middleware_data.get("repo")
    config = dm.middleware_data.get("config")
    q_id = dm.dialog_data.get("admin_q_id")

    db_key = await repo.settings.get_setting("gemini_api_key")
    api_key = db_key or config.misc.gemini_api_key

    if not api_key:
        await c.answer("❌ API Key не знайдено!", show_alert=True)
        return

    question = await repo.questions.get_question_by_id(q_id)
    if not question or not question.image_file_id:
        await c.answer("❌ Питання не має фото.", show_alert=True)
        return

    await c.message.answer("⏳ Генерація пояснення запущена...")
    actor = dm.middleware_data.get("user")
    await repo.audit.log_action(
        admin_id=actor.user_id, action="explanation_regen_started", target_id=str(q_id)
    )
    bot = dm.middleware_data.get("bot")
    context_text = f"Subject: {question.subject}, Type: {question.q_type}"
    asyncio.create_task(
        _regen_explanation_bg(
            bot, c.from_user.id, get_question_images(question),
            q_id, question.q_number, context_text, api_key, question.subject,
        )
    )


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        Window(
            DynamicMedia("image", when="show_image"),
            Format(
                "<b>Питання #{q.q_number}</b>\nТип: {q.q_type}\nВідповідь: <code>{ans_text}</code>",
                when="q",
            ),
            Format("\n📂 <b>Категорії:</b>\n{categories_text}", when="show_cats"),
            Format("\n💡 <b>Пояснення:</b>\n{explanation_safe}", when="show_expl"),
            Button(
                Const("🖼 Показати фото (обрізати текст)"), id="tgl_img",
                on_click=on_toggle_view,
                when=F["show_expl"] & ~F["show_image"] & F["is_long_text"] & ~F["is_album"],
            ),
            Button(
                Const("📝 Показати текст (сховати фото)"), id="tgl_txt",
                on_click=on_toggle_view,
                when=F["show_expl"] & F["show_image"] & F["is_long_text"] & ~F["is_album"],
            ),
            Row(
                Button(Const("💡 Пояснення"), id="tgl_expl", on_click=on_toggle_expl, when="has_expl"),
                Button(Const("📂 Категорії"), id="tgl_cats", on_click=on_toggle_cats, when="has_cats"),
            ),
            Button(Const("🔙 Назад"), id="back_qs", on_click=on_back_from_detail),
            Row(
                Button(Const("🗑 Видалити"), id="btn_del", on_click=on_delete_q, when="q"),
                Button(Const("📝 Редагувати"), id="btn_edit", on_click=on_edit_q, when="q"),
            ),
            Button(
                Const("🔄 Згенерувати пояснення"), id="btn_regen",
                on_click=on_regenerate_explanation, when="q",
            ),
            state=AdminSG.question_detail,
            getter=get_question_detail,
        ),
    ]
