"""
Admin maintenance mode: toggle, broadcast, message update.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F
from aiogram.types import ContentType, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Column
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.repo.requests import RequestsRepo
from .states import AdminSG

logger = logging.getLogger(__name__)

_DEFAULT_MAINTENANCE_MSG = (
    "⛔️ <b>Вибачте, в нас технічні роботи в боті.</b>\n"
    "Найближчим часом запустимо бота з оновленнями!"
)


# ---------------------------------------------------------------------------
# Getter
# ---------------------------------------------------------------------------

async def get_maintenance_status(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    m_mode = await repo.settings.get_setting("maintenance_mode", "false")
    is_active = m_mode.lower() == "true"

    msg = await repo.settings.get_setting("maintenance_message") or _DEFAULT_MAINTENANCE_MSG

    return {
        "is_active":    is_active,
        "status_text":  "АКТИВНО" if is_active else "ВИМКНЕНО",
        "status_emoji": "🚨" if is_active else "✅",
        "current_msg":  msg,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Головне меню", callback_data="start_menu")]]
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def on_toggle_maintenance(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    m_mode = await repo.settings.get_setting("maintenance_mode", "false")
    if m_mode.lower() == "true":
        await dm.switch_to(AdminSG.maintenance_finish)
    else:
        await dm.switch_to(AdminSG.maintenance_confirm)


async def on_enable_maintenance_confirm(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")

    msg = await repo.settings.get_setting("maintenance_message") or _DEFAULT_MAINTENANCE_MSG
    await repo.settings.set_setting("maintenance_mode", "true")

    await c.message.answer("⏳ Активую режим та розсилаю попередження...")

    from tgbot.services.broadcaster import broadcast
    users = await repo.users.get_users_for_broadcast("all")
    count = await broadcast(bot, users, msg)

    await c.message.answer(f"🚨 Технічні роботи АКТИВОВАНО!\n📢 Сповіщено: {count} користувачів.")
    await dm.switch_to(AdminSG.maintenance)


async def on_finish_maintenance(message: Message, widget: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")

    await repo.settings.set_setting("maintenance_mode", "false")

    changelog = message.text.strip() if message.text else ""
    text_to_send = "✅ <b>Технічні роботи завершено!</b>\n"
    if changelog:
        text_to_send += f"\n📣 <b>Що нового:</b>\n{changelog}"
    else:
        text_to_send += "\nБот повертається до роботи. Дякуємо за очікування!"

    try:
        await message.delete()
    except Exception:
        pass

    from tgbot.services.broadcaster import broadcast
    users = await repo.users.get_users_for_broadcast("all")
    count = await broadcast(bot, users, text_to_send, reply_markup=_main_menu_kb())

    await message.answer(f"✅ Технічні роботи вимкнено! Сповіщено {count} користувачів.")
    await dm.switch_to(AdminSG.maintenance)


async def on_finish_skip(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")

    await repo.settings.set_setting("maintenance_mode", "false")

    text_to_send = (
        "✅ <b>Технічні роботи завершено!</b>\n\n"
        "Бот повертається до роботи. Дякуємо за очікування!"
    )

    await c.message.answer("✅ Роботи завершено! Розсилаю сповіщення...")

    from tgbot.services.broadcaster import broadcast
    users = await repo.users.get_users_for_broadcast("all")
    await broadcast(bot, users, text_to_send, reply_markup=_main_menu_kb())

    await c.message.answer("📢 Сповіщено користувачів.")
    await dm.switch_to(AdminSG.maintenance)


async def on_update_maintenance_msg(message: Message, widget: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    new_text = message.text or message.caption
    if new_text:
        await repo.settings.set_setting("maintenance_message", new_text)
        await message.reply("✅ Повідомлення оновлено!")
    else:
        await message.reply("❌ Надішліть текст.")


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        Window(
            Format(
                "🚧 <b>Технічні роботи</b>\n\n"
                "Статус: {status_emoji} <b>{status_text}</b>\n\n"
                "📢 <b>Повідомлення для користувачів:</b>\n"
                "<i>{current_msg}</i>\n\n"
                "👇 Щоб змінити повідомлення, просто надішліть новий текст сюди."
            ),
            Column(
                Button(
                    Const("🚨 УВІМКНУТИ (Розіслати)"), id="btn_enable_m",
                    on_click=on_toggle_maintenance, when=~F["is_active"],
                ),
                Button(
                    Const("✅ ВИМКНУТИ (Завершити)"), id="btn_disable_m",
                    on_click=on_toggle_maintenance, when=F["is_active"],
                ),
            ),
            MessageInput(on_update_maintenance_msg, content_types=[ContentType.TEXT]),
            Button(Const("🔙 Назад"), id="back_menu",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.menu)),
            state=AdminSG.maintenance,
            getter=get_maintenance_status,
        ),
        Window(
            Const(
                "⚠️ <b>Підтвердження активації</b>\n\n"
                "1. Бот перейде в режим технічних робіт.\n"
                "2. Користувачі (крім адмінів) втратять доступ.\n"
                "3. <b>Усім активним користувачам буде надіслано поточне повідомлення!</b>\n\n"
                "Ви впевнені?"
            ),
            Button(Const("🚀 ТАК, АКТИВУВАТИ"), id="confirm_m",
                   on_click=on_enable_maintenance_confirm),
            Button(Const("🔙 Скасувати"), id="cancel_m",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.maintenance)),
            state=AdminSG.maintenance_confirm,
        ),
        Window(
            Const(
                "📢 <b>Завершення робіт</b>\n\n"
                "Надішліть повідомлення про оновлення (ChangeLog).\n"
                "Воно буде надіслано всім користувачам разом з кнопкою «Головне меню».\n\n"
                "<i>Або натисніть «Пропустити», щоб надіслати стандартне повідомлення.</i>"
            ),
            MessageInput(on_finish_maintenance, content_types=[ContentType.TEXT]),
            Button(Const("⏩ Пропустити (Стандартне)"), id="skip_fin", on_click=on_finish_skip),
            Button(Const("🔙 Скасувати"), id="cancel_fin",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.maintenance)),
            state=AdminSG.maintenance_finish,
        ),
    ]
