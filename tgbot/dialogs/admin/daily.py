"""
Admin daily challenge settings: enable/disable, force send.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import F
from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Column
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.repo.requests import RequestsRepo
from .states import AdminSG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Getter
# ---------------------------------------------------------------------------

def _parse_lottery_status(status: str) -> str:
    """Converts a raw lottery status string from DB into a human-readable display string."""
    if status == "LOSS":
        return "❌ Програно (сьогодні розсилки не буде)"
    if status.startswith("WIN"):
        time_part = status.split("(")[1].replace(")", "")
        return f"🎯 Виграно! Заплановано на {time_part}"
    if "MISS" in status:
        return "⌛ Пропущено (запізно для розсилки)"
    return status


async def get_daily_status(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")

    is_enabled_str = await repo.settings.get_setting("daily_enabled", "true")
    is_enabled = is_enabled_str.lower() == "true"

    lottery_status = await repo.settings.get_setting("daily_lottery_status", "Ще не розіграно")

    return {
        "is_enabled":   is_enabled,
        "status_emoji": "✅" if is_enabled else "❌",
        "status_text":  "УВІМКНЕНО" if is_enabled else "ВИМКНЕНО",
        "lottery_info": _parse_lottery_status(lottery_status),
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def on_toggle_daily(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor = dm.middleware_data.get("user")
    current_str = await repo.settings.get_setting("daily_enabled", "true")
    new_val = "false" if current_str.lower() == "true" else "true"
    await repo.settings.set_setting("daily_enabled", new_val)
    await repo.audit.log_action(
        admin_id=actor.user_id, action="daily_toggled", details=f"new_value={new_val}"
    )


async def on_force_daily(c: Any, b: Any, dm: DialogManager) -> None:
    bot = dm.middleware_data.get("bot")
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor = dm.middleware_data.get("user")
    from tgbot.services.daily import broadcast_daily_question
    await c.answer("⏳ Запускаю розсилку...", show_alert=True)
    await repo.audit.log_action(admin_id=actor.user_id, action="daily_force_sent")
    asyncio.create_task(broadcast_daily_question(bot, bot.session_pool))


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        Window(
            Const("<b>📅 Daily Challenge Settings</b>\n"),
            Format("Статус розсилки: <b>{status_text} {status_emoji}</b>"),
            Format("Результат лотереї сьогодні: <b>{lottery_info}</b>\n"),
            Const("<i>Порада: розсилка відбувається з імовірністю 50% щодня у випадковий час.</i>"),
            Column(
                Button(Const("✅ Увімкнути"), id="daily_on",
                       on_click=on_toggle_daily, when=~F["is_enabled"]),
                Button(Const("❌ Вимкнути"), id="daily_off",
                       on_click=on_toggle_daily, when=F["is_enabled"]),
                Button(Const("🚀 Надіслати зараз (Force)"), id="daily_force",
                       on_click=on_force_daily),
                Button(Const("⬅️ Назад"), id="back_menu_daily",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.menu)),
            ),
            state=AdminSG.daily_settings,
            getter=get_daily_status,
        ),
    ]
