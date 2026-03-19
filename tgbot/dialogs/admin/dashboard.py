"""
Admin dashboard: bot stats, admin user management, CSV exports.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any

from aiogram.types import BufferedInputFile, ContentType
from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Back, Button, Column, Row, Select
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.repo.requests import RequestsRepo
from .states import AdminSG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

def _fmt_week(data: list) -> str:
    """Formats UTM source rows for weekly dashboard display."""
    if not data:
        return "— порожньо —"
    return "\n".join(f"• {row['source']}: {row['count']}" for row in data)


def _fmt_content(data: list) -> str:
    """Formats per-subject question-count rows for dashboard display."""
    if not data:
        return "— порожньо —"
    return "\n".join(f"• {row['subject']}: {row['count']}" for row in data)


def _fmt_daily(activity: dict) -> str:
    """Formats per-subject daily activity breakdown for dashboard display."""
    subjects = set(list(activity["simulations"].keys()) + list(activity["random"].keys()))
    if not subjects:
        return "— сьогодні активності не було —"
    lines = []
    for s in sorted(subjects):
        sims = activity["simulations"].get(s, 0)
        rand = activity["random"].get(s, 0)
        lines.append(f"• {s.upper()}: {sims} сим. / {rand} ранд.")
    return "\n".join(lines)


async def get_admin_dashboard(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")

    stats = await repo.users.get_active_stats()
    current_week = await repo.stats.get_weekly_stats(week_offset=0)
    last_week = await repo.stats.get_weekly_stats(week_offset=1)
    content_stats = await repo.stats.get_content_stats()
    daily_activity = await repo.stats.get_daily_activity_stats()

    return {
        "total":           stats["total"],
        "today":           stats["today"],
        "week":            stats["week"],
        "utm_current":     _fmt_week(current_week),
        "utm_last":        _fmt_week(last_week),
        "content_stats":   _fmt_content(content_stats),
        "daily_sims":      daily_activity["total_sims"],
        "daily_rand":      daily_activity["total_rand"],
        "daily_breakdown": _fmt_daily(daily_activity),
    }


async def get_admins_list(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    admins = await repo.users.get_admins()
    return {
        "admins": [(f"{a.full_name} ({a.user_id})", a.user_id) for a in admins]
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def on_add_admin(message: Any, widget: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    try:
        user_id = int(message.text.strip())
        user = await repo.users.get_user_by_id(user_id)
        if not user:
            await message.reply(
                "❌ Користувача не знайдено в базі. Він має хоча б раз запустити бота."
            )
            return
        await repo.users.promote_admin(user_id)
        await message.reply(f"✅ Користувач {user.full_name} тепер адмін!")
    except ValueError:
        await message.reply("❌ Надішліть коректний ID (число).")


async def on_demote_admin(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    curr_user = dm.middleware_data.get("user")
    if int(item_id) == curr_user.user_id:
        await c.answer("Ви не можете прибрати самого себе!", show_alert=True)
        return
    await repo.users.demote_admin(int(item_id))
    await c.message.reply(f"✅ Адміна {item_id} видалено.")


async def on_export_logs(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    logs = await repo.logs.get_all_logs()

    if not logs:
        await c.answer("Logs are empty!", show_alert=True)
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "User ID", "Question ID", "Answer", "Is Correct", "Mode", "Session", "Time"])
    for log in logs:
        writer.writerow([
            log.id, log.user_id, log.question_id, log.answer,
            log.is_correct, log.mode, log.session_id,
            log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
        ])

    output.seek(0)
    filename = f"user_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    doc = BufferedInputFile(output.getvalue().encode("utf-8"), filename=filename)
    await c.message.answer_document(doc, caption="📂 User Action Logs")


async def on_export_stats(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    results = await repo.results.get_all_results_for_export()

    if not results:
        await c.answer("❌ Немає даних для експорту.", show_alert=True)
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "Subject", "Date", "Year", "Session", "Raw Score", "NMT Score", "Duration (sec)"])
    for r in results:
        writer.writerow([
            r.user_id, r.subject,
            r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            r.year, r.session, r.raw_score, r.nmt_score, r.duration,
        ])

    output.seek(0)
    filename = f"nmt_stats_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    document = BufferedInputFile(output.getvalue().encode("utf-8"), filename=filename)
    await c.message.answer_document(document, caption="📊 Ваша статистика готова!")


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        Window(
            Format(
                "📊 <b>Статистика бота</b>\n\n"
                "👥 <b>Користувачі:</b>\n"
                "Всього: <b>{total}</b>\n"
                "Активні сьогодні: <b>{today}</b>\n"
                "Активні за тиждень: <b>{week}</b>\n\n"
                "📝 <b>Тести сьогодні:</b>\n"
                "Симуляції: <b>{daily_sims}</b>\n"
                "Рандом (питань): <b>{daily_rand}</b>\n\n"
                "📚 <b>По предметах (сьогодні):</b>\n{daily_breakdown}\n\n"
                "📈 <b>UTM (Поточний тиждень):</b>\n{utm_current}\n\n"
                "📉 <b>UTM (Минулий тиждень):</b>\n{utm_last}\n\n"
                "📚 <b>Контент (Питань):</b>\n{content_stats}"
            ),
            Row(
                Button(Const("🔄 Оновити"), id="btn_refresh_stats"),
                Button(Const("📥 Експорт CSV"), id="btn_export_stats", on_click=on_export_stats),
            ),
            Back(Const("🔙 Назад")),
            state=AdminSG.stats,
            getter=get_admin_dashboard,
        ),
        Window(
            Const("🛡 <b>Список адміністраторів:</b>\n<i>(Натисніть на ID, щоб видалити)</i>"),
            Column(
                Select(
                    Format("👤 {item[0]}"), id="rem_admin",
                    item_id_getter=lambda x: x[1], items="admins",
                    on_click=on_demote_admin,
                ),
            ),
            Const("\n➕ <b>Щоб додати адміна, надішліть його Telegram ID:</b>"),
            MessageInput(on_add_admin, content_types=[ContentType.TEXT]),
            Button(Const("🔙 Назад"), id="back_menu", on_click=lambda c, b, d: d.switch_to(AdminSG.menu)),
            state=AdminSG.manage_admins,
            getter=get_admins_list,
        ),
    ]
