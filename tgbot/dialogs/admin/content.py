"""
Admin content management: browse subjects / years / sessions / questions.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.input import TextInput
from aiogram_dialog.widgets.kbd import Button, Column, Group, Row, Select, Back
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.misc.constants import SUBJECT_LABELS
from tgbot.services.album_manager import AlbumManager
from .states import AdminSG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

async def get_admin_subjects(dialog_manager: DialogManager, **kwargs) -> dict:
    return {"subjects": [(label, slug) for slug, label in SUBJECT_LABELS.items()]}


async def get_admin_years(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    subject = dialog_manager.dialog_data.get("admin_subject")
    years = await repo.questions.get_unique_years(subject)
    return {"years": [(str(y), y) for y in years], "subject": subject}


async def get_admin_sessions(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    subject = dialog_manager.dialog_data.get("admin_subject")
    year = dialog_manager.dialog_data.get("admin_year")
    sessions = await repo.questions.get_unique_sessions(subject, year)
    return {"sessions": [(s, s) for s in sessions], "subject": subject, "year": year}


async def get_admin_questions(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    subject = dialog_manager.dialog_data.get("admin_subject")
    year = dialog_manager.dialog_data.get("admin_year")
    session = dialog_manager.dialog_data.get("admin_session")
    questions = await repo.questions.get_questions_by_criteria(subject, year, session)
    return {
        "questions": [(f"Q#{q.q_number}", q.id) for q in questions],
        "subject": subject,
        "year": year,
        "session": session,
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def on_subject_selected(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    dm.dialog_data["admin_subject"] = item_id
    await dm.switch_to(AdminSG.years)


async def on_year_selected(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    dm.dialog_data["admin_year"] = int(item_id)
    await dm.switch_to(AdminSG.sessions)


async def on_session_selected(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    dm.dialog_data["admin_session"] = item_id
    await dm.switch_to(AdminSG.questions)


async def on_question_selected(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    from aiogram.types import ContentType
    from aiogram_dialog import ShowMode
    from aiogram_dialog.api.entities import MediaAttachment, MediaId

    q_id = int(item_id)
    dm.dialog_data["admin_q_id"] = q_id
    dm.dialog_data["show_expl"] = False
    dm.dialog_data["force_image"] = False

    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")

    # Cleanup any previous album
    old_album = dm.dialog_data.get("album_message_ids")
    if old_album:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album)
        dm.dialog_data["album_message_ids"] = []

    question = await repo.questions.get_question_by_id(q_id)
    from tgbot.misc.utils import get_question_images
    images = get_question_images(question)

    if len(images) > 1:
        chat_id = dm.middleware_data.get("event_chat").id
        album_ids = await AlbumManager.send_album(bot, chat_id, images)
        dm.dialog_data["album_message_ids"] = album_ids
        dm.show_mode = ShowMode.SEND
    else:
        dm.show_mode = ShowMode.EDIT

    await dm.switch_to(AdminSG.question_detail)


async def on_confirm_delete_session(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    actor = dm.middleware_data.get("user")
    subj = dm.dialog_data.get("admin_subject")
    year = dm.dialog_data.get("admin_year")
    sess = dm.dialog_data.get("admin_session")
    await repo.questions.delete_questions_by_session(subj, year, sess)
    await repo.audit.log_action(
        admin_id=actor.user_id, action="session_deleted",
        target_id=f"{subj}_{year}_{sess}",
    )
    await c.answer("✅ Всі питання сесії видалено!", show_alert=True)
    await dm.switch_to(AdminSG.sessions)


async def on_change_session_year(message: Any, widget: Any, dm: DialogManager, data: Any) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    try:
        new_year = int(message.text.strip())
        await repo.questions.update_session_metadata(
            dm.dialog_data.get("admin_subject"),
            dm.dialog_data.get("admin_year"),
            dm.dialog_data.get("admin_session"),
            new_year=new_year,
        )
        actor = dm.middleware_data.get("user")
        await repo.audit.log_action(
            admin_id=actor.user_id, action="session_year_changed",
            target_id=f"{dm.dialog_data.get('admin_subject')}_{dm.dialog_data.get('admin_session')}",
            details=f"{dm.dialog_data.get('admin_year')} → {new_year}",
        )
        await message.reply(f"✅ Рік змінено на {new_year}!")
        dm.dialog_data["admin_year"] = new_year
        await dm.switch_to(AdminSG.questions)
    except ValueError:
        await message.reply("❌ Надішліть коректний рік (число).")


async def on_change_session_name(message: Any, widget: Any, dm: DialogManager, data: Any) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    new_name = message.text.strip()
    if new_name:
        await repo.questions.update_session_metadata(
            dm.dialog_data.get("admin_subject"),
            dm.dialog_data.get("admin_year"),
            dm.dialog_data.get("admin_session"),
            new_session=new_name,
        )
        actor = dm.middleware_data.get("user")
        old_name = dm.dialog_data.get("admin_session")
        await repo.audit.log_action(
            admin_id=actor.user_id, action="session_name_changed",
            target_id=f"{dm.dialog_data.get('admin_subject')}_{dm.dialog_data.get('admin_year')}",
            details=f"{old_name} → {new_name}",
        )
        await message.reply(f"✅ Сесію перейменовано на {new_name}!")
        dm.dialog_data["admin_session"] = new_name
        await dm.switch_to(AdminSG.questions)
    else:
        await message.reply("❌ Назва не може бути порожньою.")


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def get_windows() -> list:
    return [
        Window(
            Const("🛠 <b>Обери предмет для редагування</b>"),
            Column(
                Select(
                    Format("{item[0]}"), id="s_subj",
                    item_id_getter=lambda x: x[1], items="subjects",
                    on_click=on_subject_selected,
                ),
            ),
            Button(Const("➕ Додати нове питання"), id="btn_new",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.upload_new)),
            Button(Const("🔙 Назад"), id="back_menu",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.menu)),
            state=AdminSG.subjects,
            getter=get_admin_subjects,
        ),
        Window(
            Format("🛠 <b>{subject}: Обери рік</b>"),
            Group(
                Select(Format("{item[0]}"), id="s_year",
                       item_id_getter=lambda x: x[1], items="years",
                       on_click=on_year_selected),
                width=3,
            ),
            Button(Const("🔙 Назад"), id="back_subj",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.subjects)),
            state=AdminSG.years,
            getter=get_admin_years,
        ),
        Window(
            Format("🛠 <b>{subject} {year}: Обери сесію</b>"),
            Column(
                Select(Format("{item[0]}"), id="s_sess",
                       item_id_getter=lambda x: x[1], items="sessions",
                       on_click=on_session_selected),
            ),
            Button(Const("🔙 Назад"), id="back_year",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.years)),
            state=AdminSG.sessions,
            getter=get_admin_sessions,
        ),
        Window(
            Format("🛠 <b>{subject} {year} {session}: Питання</b>"),
            Group(
                Select(Format("{item[0]}"), id="s_qs",
                       item_id_getter=lambda x: x[1], items="questions",
                       on_click=on_question_selected),
                width=4,
            ),
            Group(
                Button(Const("📅 Змінити рік"), id="btn_edit_year",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.edit_session_year)),
                Button(Const("✏️ Перейменувати"), id="btn_edit_name",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.edit_session_name)),
                Button(Const("🗑 Видалити сесію"), id="btn_del_sess",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.delete_session_confirm)),
                width=2,
            ),
            Button(Const("🔙 Назад"), id="back_sess",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.sessions)),
            state=AdminSG.questions,
            getter=get_admin_questions,
        ),
        Window(
            Format(
                "⚠️ <b>ВИДАЛЕННЯ СЕСІЇ</b>\n\n"
                "Ви впевнені, що хочете видалити ВСІ питання сесії:\n"
                "📚 Предмет: <code>{subject}</code>\n"
                "📅 Рік: <code>{year}</code>\n"
                "📂 Сесія: <code>{session}</code>\n\n"
                "❗ Цю дію неможливо скасувати!"
            ),
            Row(
                Button(Const("❌ ТАК, ВИДАЛИТИ"), id="btn_confirm_del",
                       on_click=on_confirm_delete_session),
                Button(Const("🚫 Скасувати"), id="btn_cancel_del",
                       on_click=lambda c, b, d: d.switch_to(AdminSG.questions)),
            ),
            state=AdminSG.delete_session_confirm,
            getter=get_admin_questions,
        ),
        Window(
            Format(
                "📅 <b>ЗМІНА РОКУ</b>\n\n"
                "📚 Предмет: <code>{subject}</code>\n"
                "📂 Сесія: <code>{session}</code>\n\n"
                "Поточний рік: <b>{year}</b>\n\n"
                "✍️ Надішліть новий рік:"
            ),
            TextInput(id="inp_new_year", on_success=on_change_session_year),
            Button(Const("🔙 Скасувати"), id="back_from_year",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.questions)),
            state=AdminSG.edit_session_year,
            getter=get_admin_questions,
        ),
        Window(
            Format(
                "✏️ <b>ПЕРЕЙМЕНУВАННЯ СЕСІЇ</b>\n\n"
                "📚 Предмет: <code>{subject}</code>\n"
                "📅 Рік: <b>{year}</b>\n\n"
                "Поточна назва: <code>{session}</code>\n\n"
                "✍️ Надішліть нову назву для сесії:"
            ),
            TextInput(id="inp_new_name", on_success=on_change_session_name),
            Button(Const("🔙 Скасувати"), id="back_from_name",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.questions)),
            state=AdminSG.edit_session_name,
            getter=get_admin_questions,
        ),
    ]
