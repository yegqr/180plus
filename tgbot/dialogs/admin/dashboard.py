"""
Admin dashboard: bot stats, admin user management, CSV exports, audit log, hardest questions.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import date, datetime
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
# Formatters
# ---------------------------------------------------------------------------

def _fmt_week(data: list) -> str:
    if not data:
        return "— порожньо —"
    return "\n".join(f"• {row['source']}: {row['count']}" for row in data)


def _fmt_content(data: list) -> str:
    if not data:
        return "— порожньо —"
    return "\n".join(f"• {row['subject']}: {row['count']}" for row in data)


def _fmt_daily(activity: dict) -> str:
    subjects = set(list(activity["simulations"].keys()) + list(activity["random"].keys()))
    if not subjects:
        return "— сьогодні активності не було —"
    lines = []
    for s in sorted(subjects):
        sims = activity["simulations"].get(s, 0)
        rand = activity["random"].get(s, 0)
        lines.append(f"• {s.upper()}: {sims} сим. / {rand} ранд.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

async def get_admin_dashboard(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")

    stats = await repo.users.get_active_stats()
    current_week = await repo.stats.get_weekly_stats(week_offset=0)
    last_week = await repo.stats.get_weekly_stats(week_offset=1)
    content_stats = await repo.stats.get_content_stats()
    daily_activity = await repo.stats.get_daily_activity_stats()
    abandoned = await repo.stats.get_abandoned_stats()
    daily_part = await repo.daily_participation.get_stats_for_date(date.today())
    event_counts = await repo.events.get_counts_today()

    _EV = event_counts  # shorthand
    events_text = (
        f"🧮 Калькулятор відкрито: <b>{_EV.get('calculator_opened', 0)}</b>\n"
        f"🎓 Спец. обрано: <b>{_EV.get('calc_spec_selected', 0)}</b>\n"
        f"🙋 KSE питань: <b>{_EV.get('kse_question_sent', 0)}</b>\n"
        f"💡 Пояснень переглянуто: <b>{_EV.get('explanation_viewed', 0)}</b>\n"
        f"🔄 Предмет змінено: <b>{_EV.get('subject_changed', 0)}</b>\n"
        f"📊 Статистику відкрито: <b>{_EV.get('stats_viewed', 0)}</b>\n"
        f"✍️ Daily (текст) відповідей: <b>{_EV.get('daily_text_answered', 0)}</b>"
    )

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
        "sim_started":     abandoned["started"],
        "sim_completed":   abandoned["completed"],
        "sim_abandoned":   abandoned["abandoned"],
        "daily_sent":      daily_part["sent"],
        "daily_answered":  daily_part["answered"],
        "daily_correct":   daily_part["correct"],
        "daily_rate":      daily_part["rate"],
        "events_today":    events_text,
    }


async def get_admins_list(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    admins = await repo.users.get_admins()
    return {
        "admins": [(f"{a.full_name} ({a.user_id})", a.user_id) for a in admins]
    }


async def get_audit_log(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    logs = await repo.audit.get_recent_logs(limit=20)
    if not logs:
        text = "— Аудит порожній —"
    else:
        lines = []
        for entry in logs:
            ts = entry.created_at.strftime("%m-%d %H:%M") if entry.created_at else "?"
            target = f" → {entry.target_id}" if entry.target_id else ""
            detail = f" ({entry.details[:40]})" if entry.details else ""
            lines.append(f"• [{ts}] <b>{entry.action}</b>{target}{detail}")
        text = "\n".join(lines)
    return {"audit_text": text}


async def get_hardest_questions_data(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    questions = await repo.logs.get_hardest_questions(limit=10)
    if not questions:
        text = "— Ще немає даних —"
    else:
        lines = []
        for i, q in enumerate(questions, 1):
            lines.append(
                f"{i}. Q#{q['question_id']} [{q['subject'].upper()} | {q['q_type']}]"
                f" — ❌ {q['wrong_count']} помилок"
            )
        text = "\n".join(lines)
    return {"hardest_text": text}


# ---------------------------------------------------------------------------
# Handlers — Admin management
# ---------------------------------------------------------------------------

async def on_add_admin(message: Any, widget: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor: Any = dm.middleware_data.get("user")
    try:
        user_id = int(message.text.strip())
        user = await repo.users.get_user_by_id(user_id)
        if not user:
            await message.reply(
                "❌ Користувача не знайдено в базі. Він має хоча б раз запустити бота."
            )
            return
        await repo.users.promote_admin(user_id)
        await repo.audit.log_action(
            admin_id=actor.user_id,
            action="promote_admin",
            target_id=str(user_id),
            details=user.full_name,
        )
        await message.reply(f"✅ Користувач {user.full_name} тепер адмін!")
    except ValueError:
        await message.reply("❌ Надішліть коректний ID (число).")


async def on_demote_admin(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor: Any = dm.middleware_data.get("user")
    if int(item_id) == actor.user_id:
        await c.answer("Ви не можете прибрати самого себе!", show_alert=True)
        return
    await repo.users.demote_admin(int(item_id))
    await repo.audit.log_action(
        admin_id=actor.user_id,
        action="demote_admin",
        target_id=item_id,
    )
    await c.message.reply(f"✅ Адміна {item_id} видалено.")


# ---------------------------------------------------------------------------
# Handlers — Exports
# ---------------------------------------------------------------------------

def _make_csv(rows: list[list], headers: list[str]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


async def on_export_logs(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    logs = await repo.logs.get_all_logs()
    if not logs:
        await c.answer("Logs are empty!", show_alert=True)
        return
    data = _make_csv(
        [
            [
                log.id, log.user_id, log.question_id, log.answer,
                log.is_correct, log.mode, log.session_id,
                log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
            ]
            for log in logs
        ],
        ["ID", "User ID", "Question ID", "Answer", "Is Correct", "Mode", "Session", "Time"],
    )
    filename = f"user_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    await c.message.answer_document(
        BufferedInputFile(data, filename=filename),
        caption="📂 User Action Logs",
    )


async def on_export_stats(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    results = await repo.results.get_all_results_for_export()
    if not results:
        await c.answer("❌ Немає даних для експорту.", show_alert=True)
        return
    data = _make_csv(
        [
            [
                r.user_id, r.subject,
                r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                r.year, r.session, r.raw_score, r.nmt_score, r.duration,
            ]
            for r in results
        ],
        ["User ID", "Subject", "Date", "Year", "Session", "Raw Score", "NMT Score", "Duration (sec)"],
    )
    filename = f"nmt_stats_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    await c.message.answer_document(
        BufferedInputFile(data, filename=filename),
        caption="📊 Exam Results",
    )


async def on_export_all_zip(c: Any, b: Any, dm: DialogManager) -> None:
    """One-click: ZIP archive with all available log tables as separate CSVs."""
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor: Any = dm.middleware_data.get("user")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:

        # 1. user_action_logs.csv
        logs = await repo.logs.get_all_logs()
        zf.writestr(
            "user_action_logs.csv",
            _make_csv(
                [
                    [
                        l.id, l.user_id, l.question_id, l.answer,
                        l.is_correct, l.mode, l.session_id,
                        l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else "",
                    ]
                    for l in logs
                ],
                ["ID", "User ID", "Question ID", "Answer", "Is Correct", "Mode", "Session", "Time"],
            ).decode("utf-8"),
        )

        # 2. exam_results.csv
        results = await repo.results.get_all_results_for_export()
        zf.writestr(
            "exam_results.csv",
            _make_csv(
                [
                    [
                        r.user_id, r.subject,
                        r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        r.year, r.session, r.raw_score, r.nmt_score, r.duration,
                    ]
                    for r in results
                ],
                ["User ID", "Subject", "Date", "Year", "Session", "Raw Score", "NMT Score", "Duration (sec)"],
            ).decode("utf-8"),
        )

        # 3. admin_audit_log.csv
        audit = await repo.audit.get_all_for_export()
        zf.writestr(
            "admin_audit_log.csv",
            _make_csv(
                [
                    [
                        a.id, a.admin_id, a.action, a.target_id or "", a.details or "",
                        a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
                    ]
                    for a in audit
                ],
                ["ID", "Admin ID", "Action", "Target ID", "Details", "Time"],
            ).decode("utf-8"),
        )

        # 4. user_events.csv
        user_events = await repo.events.get_all_for_export()
        zf.writestr(
            "user_events.csv",
            _make_csv(
                [
                    [
                        e.id, e.user_id, e.event_type, e.payload or "",
                        e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "",
                    ]
                    for e in user_events
                ],
                ["ID", "User ID", "Event Type", "Payload (JSON)", "Time"],
            ).decode("utf-8"),
        )

        # 5. daily_participation.csv
        daily = await repo.daily_participation.get_all_for_export()
        zf.writestr(
            "daily_participation.csv",
            _make_csv(
                [
                    [
                        d.id, d.user_id, d.question_id, d.subject, str(d.date),
                        d.sent_at.strftime("%Y-%m-%d %H:%M:%S") if d.sent_at else "",
                        d.answered_at.strftime("%Y-%m-%d %H:%M:%S") if d.answered_at else "",
                        d.answer or "",
                        d.is_correct if d.is_correct is not None else "",
                    ]
                    for d in daily
                ],
                ["ID", "User ID", "Question ID", "Subject", "Date",
                 "Sent At", "Answered At", "Answer", "Is Correct"],
            ).decode("utf-8"),
        )

    zip_buf.seek(0)
    filename = f"nmt_all_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    await c.message.answer_document(
        BufferedInputFile(zip_buf.read(), filename=filename),
        caption=(
            "📦 <b>Повний архів логів</b>\n\n"
            "• user_action_logs.csv — всі відповіді юзерів\n"
            "• exam_results.csv — результати іспитів\n"
            "• admin_audit_log.csv — дії адмінів\n"
            "• user_events.csv — події (калькулятор, пояснення, etc.)\n"
            "• daily_participation.csv — daily challenge"
        ),
    )
    await repo.audit.log_action(
        admin_id=actor.user_id,
        action="export_all_logs_zip",
    )


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        # ----- Main stats window -----
        Window(
            Format(
                "📊 <b>Статистика бота</b>\n\n"
                "👥 <b>Користувачі:</b>\n"
                "Всього: <b>{total}</b> | Сьогодні: <b>{today}</b> | Тиждень: <b>{week}</b>\n\n"
                "📝 <b>Симуляції сьогодні:</b>\n"
                "Розпочато: <b>{sim_started}</b> | Завершено: <b>{sim_completed}</b> | "
                "Покинуто: <b>{sim_abandoned}</b>\n\n"
                "🎯 <b>Рандом-режим сьогодні:</b> <b>{daily_rand}</b> питань\n\n"
                "🔥 <b>Daily Challenge сьогодні:</b>\n"
                "Надіслано: <b>{daily_sent}</b> | Відповіли: <b>{daily_answered}</b> | "
                "Правильно: <b>{daily_correct}</b> | Участь: <b>{daily_rate}%</b>\n\n"
                "📚 <b>По предметах (сьогодні):</b>\n{daily_breakdown}\n\n"
                "📈 <b>UTM (поточний тиждень):</b>\n{utm_current}\n\n"
                "📉 <b>UTM (минулий тиждень):</b>\n{utm_last}\n\n"
                "📚 <b>Контент (питань по предметах):</b>\n{content_stats}\n\n"
                "🎯 <b>Події сьогодні:</b>\n{events_today}"
            ),
            Row(
                Button(Const("🔄 Оновити"), id="btn_refresh_stats",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.stats)),
                Button(Const("📥 Результати CSV"), id="btn_export_stats", on_click=on_export_stats),
            ),
            Row(
                Button(Const("📥 Логи CSV"), id="btn_export_logs", on_click=on_export_logs),
                Button(Const("📦 Все (ZIP)"), id="btn_export_zip", on_click=on_export_all_zip),
            ),
            Row(
                Button(Const("🔴 Топ складних"), id="btn_hardest",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.hardest_questions)),
                Button(Const("🗂 Аудит"), id="btn_audit",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.audit_log)),
            ),
            Back(Const("🔙 Назад")),
            state=AdminSG.stats,
            getter=get_admin_dashboard,
        ),

        # ----- Admin management window -----
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
            Button(Const("🔙 Назад"), id="back_menu",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.menu)),
            state=AdminSG.manage_admins,
            getter=get_admins_list,
        ),

        # ----- Audit log window -----
        Window(
            Format(
                "🗂 <b>Аудит лог адмінів</b> (останні 20)\n\n"
                "{audit_text}"
            ),
            Back(Const("🔙 Назад")),
            state=AdminSG.audit_log,
            getter=get_audit_log,
        ),

        # ----- Hardest questions window -----
        Window(
            Format(
                "🔴 <b>Топ-10 найскладніших питань</b>\n"
                "<i>(по кількості неправильних відповідей)</i>\n\n"
                "{hardest_text}"
            ),
            Back(Const("🔙 Назад")),
            state=AdminSG.hardest_questions,
            getter=get_hardest_questions_data,
        ),
    ]
