"""
Admin settings: onboarding video, join-request approval, Gemini API key.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import F
from aiogram.types import ContentType, Message
from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Column
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.misc.constants import JOIN_REQUEST_DELAY
from .states import AdminSG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

async def get_admin_settings(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    video_id = await repo.settings.get_setting("onboarding_video", "Не встановлено")
    pending_count = len(await repo.join_requests.get_all_requests())
    return {"video_id": video_id, "pending_count": pending_count}


def _key_preview(key: str | None) -> str:
    """Returns a masked preview of an API key, e.g. 'AIzaSyAB...xYzW'. Returns '—' if no key."""
    if not key:
        return "—"
    return f"{key[:8]}...{key[-4:]}"


def _key_source(db_key: str | None, config_key: str | None) -> str:
    """Returns a human-readable label for where the active API key came from."""
    if db_key:
        return "Database"
    if config_key:
        return "Config (.env)"
    return "None"


async def get_gemini_settings(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    config = dialog_manager.middleware_data.get("config")

    db_key = await repo.settings.get_setting("gemini_api_key")
    config_key = config.misc.gemini_api_key

    active_key = db_key or config_key

    return {
        "has_key":     bool(active_key),
        "source":      _key_source(db_key, config_key),
        "key_preview": _key_preview(active_key),
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def on_update_video(message: Message, widget: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")

    if message.video:
        file_id = message.video.file_id
    elif message.animation:
        file_id = message.animation.file_id
    elif message.text:
        file_id = message.text.strip()
    else:
        await message.reply("❌ Будь ласка, надішліть відео, GIF або текстовий ID.")
        return

    await repo.settings.set_setting("onboarding_video", file_id)
    await message.reply(f"✅ Відео-онбординг оновлено!\nID: {file_id}")
    await dm.switch_to(AdminSG.settings)


async def on_approve_all(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")

    requests = await repo.join_requests.get_all_requests()
    if not requests:
        await c.answer("❌ Немає активних запитів!", show_alert=True)
        return

    await c.message.answer(f"⏳ Починаю приймати {len(requests)} запитів...")

    success_count = 0
    for user_id, chat_id in requests:
        try:
            await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            success_count += 1
            await asyncio.sleep(JOIN_REQUEST_DELAY)
        except Exception:
            pass

    await repo.join_requests.clear_all()
    await c.message.answer(f"✅ Готово! Прийнято користувачів: {success_count}")
    await dm.switch_to(AdminSG.settings)


async def on_update_gemini_key(message: Message, widget: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    new_key = message.text.strip()
    if new_key:
        await repo.settings.set_setting("gemini_api_key", new_key)
        await message.reply("✅ Gemini API Key оновлено!")
    else:
        await message.reply("❌ Ключ не може бути пустим.")


async def on_delete_gemini_key(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    await repo.settings.set_setting("gemini_api_key", "")
    await c.answer("✅ Ключ видалено з бази (використовується Config, якщо є).")


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        Window(
            Format(
                "⚙️ <b>Налаштування бота</b>\n\n"
                "🎥 <b>Відео-онбординг:</b>\n"
                "<code>{video_id}</code>\n\n"
                "👥 <b>Запитів у канал:</b> <code>{pending_count}</code>"
            ),
            Column(
                Button(Const("🎥 Змінити відео"), id="btn_edit_vid",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.update_video)),
                Button(Format("👥 Прийняти всіх ({pending_count})"), id="btn_app_all",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.approve_confirm_1)),
                Button(Const("🔑 Gemini API Key"), id="btn_gemini",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.gemini_settings)),
            ),
            Button(Const("🔙 Назад"), id="back_menu",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.menu)),
            state=AdminSG.settings,
            getter=get_admin_settings,
        ),
        Window(
            Format(
                "🔑 <b>Gemini API Key Settings</b>\n\n"
                "Статус: <b>{has_key}</b>\n"
                "Джерело: <b>{source}</b>\n"
                "Поточний (початок/кінець): <code>{key_preview}</code>\n\n"
                "👇 <b>Надішліть новий ключ сюди, щоб оновити/встановити.</b>"
            ),
            Button(Const("🗑 Видалити ключ з БД"), id="del_key",
                   on_click=on_delete_gemini_key, when="has_key"),
            Button(Const("🔙 Назад"), id="back_settings",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.settings)),
            MessageInput(on_update_gemini_key, content_types=[ContentType.TEXT]),
            state=AdminSG.gemini_settings,
            getter=get_gemini_settings,
        ),
        Window(
            Const("⚠️ <b>Ви впевнені?</b>\nВи збираєтеся прийняти ВСІХ користувачів у канал."),
            Button(Const("✅ Так, я впевнений"), id="conf_1",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.approve_confirm_2)),
            Button(Const("🔙 Скасувати"), id="back_set",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.settings)),
            state=AdminSG.approve_confirm_1,
        ),
        Window(
            Const("🛑 <b>ОСТАННЄ ПОПЕРЕДЖЕННЯ!</b>\nЦя дія незворотна. Продовжити?"),
            Button(Const("🚀 ПРИЙНЯТИ ВСІХ"), id="conf_2", on_click=on_approve_all),
            Button(Const("🔙 Скасувати"), id="back_set",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.settings)),
            state=AdminSG.approve_confirm_2,
        ),
        Window(
            Const("✏️ <b>Надішліть відео, GIF або ID для онбордингу</b>"),
            MessageInput(
                on_update_video,
                content_types=[ContentType.VIDEO, ContentType.ANIMATION, ContentType.TEXT],
            ),
            Button(Const("🔙 Назад"), id="back_set",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.settings)),
            state=AdminSG.update_video,
        ),
    ]
