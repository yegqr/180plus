"""
Admin upload: single photo, media-group albums, and bulk ZIP upload.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import ContentType, Message
from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Cancel
from aiogram_dialog.widgets.text import Const

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.config import Config
from tgbot.misc.constants import ALBUM_WAIT_SECONDS
from tgbot.misc.utils import parse_question_caption
from .states import AdminSG

logger = logging.getLogger(__name__)

# Global buffer: {media_group_id: {"meta": dict, "images": list[str], "msg_ids": list[int], "task": Task}}
ALBUM_BUFFER: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _fetch_image_bytes(bot: Bot, file_ids: list[str]) -> list[bytes]:
    """Downloads each Telegram file_id and returns the raw bytes."""
    result = []
    for fid in file_ids:
        f = await bot.get_file(fid)
        buf = io.BytesIO()
        await bot.download_file(f.file_path, buf)
        result.append(buf.getvalue())
    return result


async def _save_gemini_result(
    repo: RequestsRepo, meta: dict, explanation: str, categories: list[str]
) -> bool:
    """Persists explanation and categories for the matching question. Returns True on success."""
    questions = await repo.questions.get_questions_by_criteria(
        meta["subject"], meta["year"], meta["session"]
    )
    target = next((q for q in questions if q.q_number == meta["q_number"]), None)
    if not target:
        return False
    await repo.questions.update_explanation(target.id, explanation)
    if categories:
        await repo.questions.update_categories(target.id, categories)
    return True


async def _trigger_gemini_explanation(
    repo: RequestsRepo,
    bot: Bot,
    active_key: str,
    meta: dict,
    file_ids: list[str],
    status_msg: Message,
    status_prefix: str,
) -> None:
    """Downloads images, calls Gemini, saves explanation + categories, updates status message."""
    from tgbot.services.gemini import GeminiService
    try:
        await status_msg.edit_text(f"{status_prefix}\n⏳ Генерую пояснення...")
        images_bytes = await _fetch_image_bytes(bot, file_ids)
        q_text = f"Subject: {meta['subject']}, Type: {meta['q_type']}, Ans: {meta['correct_answer']}"
        result_data = await GeminiService(active_key).generate_explanation(
            images_bytes, q_text, subject=meta["subject"]
        )
        saved = await _save_gemini_result(
            repo, meta, result_data.get("explanation", ""), result_data.get("categories", [])
        )
        if saved:
            await status_msg.edit_text(f"{status_prefix}\n✅ Пояснення та категорії збережено!")
        else:
            await status_msg.edit_text(
                f"{status_prefix}\n⚠️ Не вдалося зберегти пояснення (питання не знайдено)."
            )
    except Exception as ex:
        logger.error(f"Gen Error: {ex}")
        await status_msg.edit_text(f"{status_prefix}\n❌ Помилка генерації: {ex}")


async def _get_active_gemini_key(repo: RequestsRepo, config: Config) -> str | None:
    db_key = await repo.settings.get_setting("gemini_api_key")
    return db_key or config.misc.gemini_api_key


async def _delete_messages(bot: Bot, chat_id: int, msg_ids: list[int]) -> None:
    """Best-effort deletion of a list of message IDs."""
    try:
        if hasattr(bot, "delete_messages"):
            await bot.delete_messages(chat_id, msg_ids)
        else:
            for mid in msg_ids:
                try:
                    await bot.delete_message(chat_id, mid)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Failed to delete uploads: {e}")


# ---------------------------------------------------------------------------
# Album helpers
# ---------------------------------------------------------------------------

async def delayed_album_save(
    media_group_id: str, repo: RequestsRepo, message: Message, config: Config
) -> None:
    """Waits for all photos in a media group to arrive, then saves to DB + triggers Gemini."""
    await asyncio.sleep(ALBUM_WAIT_SECONDS)

    data = ALBUM_BUFFER.pop(media_group_id, None)
    if not data:
        return

    meta = data["meta"]
    images = data["images"]

    try:
        await repo.questions.upsert_question(
            subject=meta["subject"], year=meta["year"], session=meta["session"],
            q_number=meta["q_number"], image_file_ids=images,
            q_type=meta["q_type"], correct_answer=meta["correct_answer"], weight=meta["weight"],
        )
        txt = f"✅ Питання Q#{meta['q_number']} збережено! (Фото: {len(images)})"
        status_msg = await message.answer(txt)

        await _delete_messages(message.bot, message.chat.id, data["msg_ids"])

        active_key = await _get_active_gemini_key(repo, config)
        if active_key:
            asyncio.create_task(
                _trigger_gemini_explanation(repo, message.bot, active_key, meta, images, status_msg, txt)
            )

    except Exception as e:
        await message.answer(f"❌ Помилка збереження альбому: {e}")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_FMT_EXAMPLE = "math | 2024 | main | 1 | choice | 5 | А"


async def _handle_album_photo(
    message: Message, media_group_id: str, file_id: str, msg_id: int,
    repo: RequestsRepo, config: Config,
) -> None:
    """Handles one photo belonging to a media group (album upload)."""
    if media_group_id in ALBUM_BUFFER:
        ALBUM_BUFFER[media_group_id]["images"].append(file_id)
        ALBUM_BUFFER[media_group_id]["msg_ids"].append(msg_id)
        return
    if not message.caption:
        await message.reply("❌ Перше фото альбому має бути з підписом!")
        return
    try:
        meta = parse_question_caption(message.caption)
        ALBUM_BUFFER[media_group_id] = {
            "meta":    meta,
            "images":  [file_id],
            "msg_ids": [msg_id],
            "task":    asyncio.create_task(
                delayed_album_save(media_group_id, repo, message, config)
            ),
        }
    except ValueError as e:
        await message.reply(f"❌ Помилка формату: {e}\nПриклад: {_FMT_EXAMPLE}")
    except Exception as e:
        await message.reply(f"❌ Помилка парсингу: {e}")


async def _handle_single_photo(
    message: Message, file_id: str, repo: RequestsRepo, config: Config,
    actor_id: int | None = None,
) -> None:
    """Handles a standalone (non-album) photo upload."""
    if not message.caption:
        await message.reply("❌ Надішліть фото з підписом!")
        return
    try:
        meta = parse_question_caption(message.caption)
        await repo.questions.upsert_question(
            subject=meta["subject"], year=meta["year"], session=meta["session"],
            q_number=meta["q_number"], image_file_ids=[file_id],
            q_type=meta["q_type"], correct_answer=meta["correct_answer"], weight=meta["weight"],
        )
        await repo.audit.log_action(
            admin_id=actor_id, action="question_uploaded",
            target_id=f"{meta['subject']}_{meta['year']}_{meta['session']}_Q{meta['q_number']}",
            details="single",
        )
        status_prefix = f"✅ Питання Q#{meta['q_number']} збережено!"
        status_msg = await message.reply(status_prefix)
        try:
            await message.delete()
        except Exception:
            pass
        active_key = await _get_active_gemini_key(repo, config)
        if active_key:
            asyncio.create_task(
                _trigger_gemini_explanation(
                    repo, message.bot, active_key, meta, [file_id], status_msg, status_prefix
                )
            )
    except ValueError as e:
        await message.reply(f"❌ Помилка формату: {e}\nПриклад: {_FMT_EXAMPLE}")
    except Exception as e:
        await message.reply(f"❌ Помилка: {e}")


async def on_upload_photo(message: Message, widget: Any, dialog_manager: DialogManager) -> None:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    config = dialog_manager.middleware_data.get("config")
    file_id = message.photo[-1].file_id

    actor = dialog_manager.middleware_data.get("user")
    actor_id = actor.user_id if actor else None

    if message.media_group_id:
        await _handle_album_photo(
            message, message.media_group_id, file_id, message.message_id, repo, config
        )
    else:
        await _handle_single_photo(message, file_id, repo, config, actor_id=actor_id)


async def on_bulk_upload(message: Message, widget: Any, dm: DialogManager) -> None:
    bot = dm.middleware_data.get("bot")
    repo = dm.middleware_data.get("repo")
    config = dm.middleware_data.get("config")

    if not message.document or not message.document.file_name.endswith(".zip"):
        await message.reply("❌ Будь ласка, надішліть ZIP-архів.")
        return

    from tgbot.services.bulk_upload import BulkUploadService
    service = BulkUploadService(bot, repo, config)

    file_info = await bot.get_file(message.document.file_id)
    zip_bytes = await bot.download_file(file_info.file_path)

    actor = dm.middleware_data.get("user")
    asyncio.create_task(service.process_zip(zip_bytes.read(), message.from_user.id))
    await repo.audit.log_action(
        admin_id=actor.user_id if actor else None,
        action="bulk_upload_started",
        details=message.document.file_name,
    )
    await message.reply("🚀 ZIP отримано! Починаю обробку у фоновому режимі...")
    await dm.switch_to(AdminSG.menu)


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        Window(
            Const(
                "📸 <b>Надішліть фото завдання з підписом:</b>\n\n"
                "<code>subject | year | session | number | type | options | answer</code>\n\n"
                "📌 <b>Як заповнювати:</b>\n"
                "🔹 <b>Предмет:</b> math, hist, mova, eng, physics\n"
                "🔹 <b>Тип:</b> choice (вибір), match (відповідність), short (коротка)\n"
                "🔹 <b>Опції:</b> choice (кількість, 5), match (розмір, 3x5), short (-)\n"
                "🔹 <b>Відповідь (УКР літери):</b>\n"
                "   - Choice: А, Б, В...\n"
                "   - Short: 4.5 або 4,5\n"
                "   - Match: 1А 2Б 3В\n\n"
                "📋 <b>Приклади (копіюйте):</b>\n\n"
                "🔸 <b>Вибір (Choice):</b>\n"
                "<code>physics | 2024 | main | 1 | choice | 5 | А</code>\n\n"
                "🔸 <b>Відповідність (Match):</b>\n"
                "<code>physics | 2024 | main | 2 | match | 3x5 | 1А 2Б 3Д</code>\n\n"
                "🔸 <b>Коротка (Short):</b>\n"
                "<code>physics | 2024 | main | 3 | short | - | 4,5</code>"
            ),
            MessageInput(on_upload_photo, content_types=[ContentType.PHOTO]),
            Button(Const("🔙 Назад (до предметів)"), id="back_subjects",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.subjects)),
            state=AdminSG.upload_new,
        ),
        Window(
            Const(
                "📦 <b>Масове завантаження (ZIP)</b>\n\n"
                "Надішліть ZIP-архів з <code>questions.csv</code> (рекомендовано) або "
                "<code>questions.json</code> та фото.\n\n"
                "📊 <b>Порядок колонок CSV:</b>\n"
                "<code>subject, year, session, q_number, q_type, answer, images</code>\n\n"
                "✅ <b>Підтримувані предмети:</b>\n"
                "<code>math, hist, mova, eng, physics</code>\n\n"
                "📂 <b>Вимоги до ZIP:</b>\n"
                "1. Файл <code>questions.csv</code> в корені.\n"
                "2. Назви фото мають збігатися з колонкою images.\n\n"
                "👇 <b>Надішліть ZIP-файл сюди для обробки.</b>"
            ),
            MessageInput(on_bulk_upload, content_types=[ContentType.DOCUMENT]),
            Button(Const("🔙 Назад"), id="back_menu",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.menu)),
            state=AdminSG.bulk_upload,
        ),
    ]
