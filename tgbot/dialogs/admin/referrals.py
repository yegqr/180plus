"""
Admin referral link management: create links, view stats, assign owners.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from aiogram.types import ContentType
from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Column, Row, Select
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.repo.requests import RequestsRepo
from .states import AdminSG

logger = logging.getLogger(__name__)

_CODE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,60}$")


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

async def get_referral_list(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    items = await repo.referrals.get_all_with_stats()

    lines = []
    choices = []
    for entry in items:
        link = entry["link"]
        s = entry["stats"]
        status = "🟢" if link.is_active else "🔴"
        owner = f" | 👤{link.owner_user_id}" if link.owner_user_id else ""
        lines.append(
            f"{status} <code>{link.code}</code> — {link.name}{owner}\n"
            f"   Сьогодні: <b>{s['today']}</b> | Тиждень: <b>{s['week']}</b> | "
            f"Місяць: <b>{s['month']}</b> | Всього: <b>{s['total']}</b>"
        )
        choices.append((link.code, link.name[:30]))

    text = "\n\n".join(lines) if lines else "— Немає жодного реф-посилання —"
    return {"referral_list_text": text, "referral_choices": choices}


async def get_referral_detail(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    code = dialog_manager.dialog_data.get("selected_referral_code", "")
    link = await repo.referrals.get_by_code(code)
    if not link:
        return {
            "ref_code": code,
            "ref_name": "?",
            "ref_active": False,
            "ref_owner": "—",
            "ref_today": 0,
            "ref_week": 0,
            "ref_month": 0,
            "ref_total": 0,
        }
    s = await repo.referrals.get_stats_for_code(code)
    config = dialog_manager.middleware_data.get("config")
    bot_username = getattr(getattr(config, "tg_bot", None), "bot_username", "YOUR_BOT")
    return {
        "ref_code": link.code,
        "ref_name": link.name,
        "ref_active": link.is_active,
        "ref_owner": str(link.owner_user_id) if link.owner_user_id else "—",
        "ref_today": s["today"],
        "ref_week": s["week"],
        "ref_month": s["month"],
        "ref_total": s["total"],
        "ref_link": f"https://t.me/{bot_username}?start=ref_{link.code}",
        "active_label": "🟢 Активне" if link.is_active else "🔴 Неактивне",
    }


# ---------------------------------------------------------------------------
# Handlers — referral list
# ---------------------------------------------------------------------------

async def on_select_referral(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    dm.dialog_data["selected_referral_code"] = item_id
    await dm.switch_to(AdminSG.referral_detail)


async def on_create_referral(message: Any, widget: Any, dm: DialogManager) -> None:
    """Expects input format: code|Назва посилання"""
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor: Any = dm.middleware_data.get("user")
    text = message.text.strip()

    if "|" not in text:
        await message.reply(
            "❌ Формат: <code>код|Назва</code>\n"
            "Приклад: <code>inst_mar25|Instagram березень 2025</code>"
        )
        return

    code, _, name = text.partition("|")
    code = code.strip()
    name = name.strip()

    if not _CODE_RE.match(code):
        await message.reply(
            "❌ Код може містити лише латинські літери, цифри, <code>-</code> і <code>_</code> (макс. 60 символів)."
        )
        return

    if not name:
        await message.reply("❌ Назва не може бути порожньою.")
        return

    existing = await repo.referrals.get_by_code(code)
    if existing:
        await message.reply(f"❌ Реф-посилання з кодом <code>{code}</code> вже існує.")
        return

    await repo.referrals.create_referral(code=code, name=name, created_by=actor.user_id)
    await repo.audit.log_action(
        admin_id=actor.user_id,
        action="referral_created",
        target_id=code,
        details=name,
    )

    config = dm.middleware_data.get("config")
    bot_username = getattr(getattr(config, "tg_bot", None), "bot_username", "YOUR_BOT")
    await message.reply(
        f"✅ Реф-посилання створено!\n\n"
        f"🔗 <code>https://t.me/{bot_username}?start=ref_{code}</code>\n\n"
        f"Надішліть наступне реф-посилання або натисніть «Список» для перегляду."
    )


# ---------------------------------------------------------------------------
# Handlers — referral detail
# ---------------------------------------------------------------------------

async def on_toggle_active(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor: Any = dm.middleware_data.get("user")
    code = dm.dialog_data.get("selected_referral_code", "")
    new_state = await repo.referrals.toggle_active(code)
    await repo.audit.log_action(
        admin_id=actor.user_id,
        action="referral_toggled",
        target_id=code,
        details="active" if new_state else "inactive",
    )
    await c.answer("✅ Статус змінено!")
    await dm.switch_to(AdminSG.referral_detail)


async def on_remove_owner(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor: Any = dm.middleware_data.get("user")
    code = dm.dialog_data.get("selected_referral_code", "")
    await repo.referrals.set_owner(code, None)
    await repo.audit.log_action(
        admin_id=actor.user_id,
        action="referral_owner_removed",
        target_id=code,
    )
    await c.answer("✅ Власника прибрано!")
    await dm.switch_to(AdminSG.referral_detail)


async def on_set_owner_input(message: Any, widget: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor: Any = dm.middleware_data.get("user")
    code = dm.dialog_data.get("selected_referral_code", "")
    try:
        owner_id = int(message.text.strip())
    except ValueError:
        await message.reply("❌ Надішліть коректний Telegram ID (ціле число).")
        return

    user = await repo.users.get_user_by_id(owner_id)
    if not user:
        await message.reply("❌ Користувача не знайдено. Він має хоча б раз запустити бота.")
        return

    await repo.referrals.set_owner(code, owner_id)
    await repo.audit.log_action(
        admin_id=actor.user_id,
        action="referral_owner_set",
        target_id=code,
        details=str(owner_id),
    )
    await message.reply(f"✅ Власником реф-посилання встановлено {user.full_name} ({owner_id}).")
    await dm.switch_to(AdminSG.referral_detail)


async def on_delete_referral(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor: Any = dm.middleware_data.get("user")
    code = dm.dialog_data.get("selected_referral_code", "")
    await repo.referrals.delete(code)
    await repo.audit.log_action(
        admin_id=actor.user_id,
        action="referral_deleted",
        target_id=code,
    )
    await c.answer("🗑 Видалено!")
    await dm.switch_to(AdminSG.referral_list)


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        # ----- Referral list -----
        Window(
            Format(
                "🔗 <b>Реф-посилання</b>\n\n"
                "{referral_list_text}\n\n"
                "➕ <b>Щоб створити нове, надішліть:</b> <code>код|Назва</code>\n"
                "<i>Приклад: inst_mar25|Instagram березень 2025</i>"
            ),
            Column(
                Select(
                    Format("🔗 {item[0]} — {item[1]}"),
                    id="ref_select",
                    item_id_getter=lambda x: x[0],
                    items="referral_choices",
                    on_click=on_select_referral,
                ),
            ),
            MessageInput(on_create_referral, content_types=[ContentType.TEXT]),
            Button(
                Const("🔙 Назад"),
                id="back_ref_list",
                on_click=lambda c, b, d: d.switch_to(AdminSG.menu),
            ),
            state=AdminSG.referral_list,
            getter=get_referral_list,
        ),

        # ----- Referral detail -----
        Window(
            Format(
                "🔗 <b>{ref_name}</b>\n"
                "Код: <code>{ref_code}</code>\n"
                "Статус: {active_label}\n"
                "Власник: <b>{ref_owner}</b>\n\n"
                "📊 <b>Статистика переходів:</b>\n"
                "Сьогодні: <b>{ref_today}</b>\n"
                "Тиждень (ПН-НД): <b>{ref_week}</b>\n"
                "Місяць: <b>{ref_month}</b>\n"
                "Всього: <b>{ref_total}</b>\n\n"
                "🔗 <code>{ref_link}</code>"
            ),
            Row(
                Button(Const("🔛 Увімк/Вимк"), id="ref_toggle", on_click=on_toggle_active),
                Button(Const("🗑 Видалити"), id="ref_delete", on_click=on_delete_referral),
            ),
            Button(
                Const("👤 Встановити власника"),
                id="ref_set_owner",
                on_click=lambda c, b, d: d.switch_to(AdminSG.referral_set_owner),
            ),
            Button(
                Const("❌ Прибрати власника"),
                id="ref_remove_owner",
                on_click=on_remove_owner,
            ),
            Button(
                Const("🔙 До списку"),
                id="back_ref_detail",
                on_click=lambda c, b, d: d.switch_to(AdminSG.referral_list),
            ),
            state=AdminSG.referral_detail,
            getter=get_referral_detail,
        ),

        # ----- Set owner form -----
        Window(
            Const(
                "👤 <b>Встановити власника реф-посилання</b>\n\n"
                "Надішліть Telegram ID користувача, якому надати доступ до статистики цього реф-посилання:"
            ),
            MessageInput(on_set_owner_input, content_types=[ContentType.TEXT]),
            Button(
                Const("🔙 Назад"),
                id="back_set_owner",
                on_click=lambda c, b, d: d.switch_to(AdminSG.referral_detail),
            ),
            state=AdminSG.referral_set_owner,
        ),
    ]
