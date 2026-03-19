"""
Admin materials management: browse subjects, upload/clear reference photos.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import ContentType, Message
from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Column, Select
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.misc.constants import SUBJECT_LABELS
from .states import AdminSG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

async def get_material_upload_data(dialog_manager: DialogManager, **kwargs) -> dict:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    subject = dialog_manager.dialog_data.get("material_subject")

    material = await repo.materials.get_by_subject(subject)
    images = list(material.images or []) if material else []

    return {
        "subject":       subject,
        "subject_label": SUBJECT_LABELS.get(subject, subject),
        "count":         len(images),
        "has_images":    len(images) > 0,
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def on_material_subject_selected(c: Any, w: Any, dm: DialogManager, item_id: str) -> None:
    dm.dialog_data["material_subject"] = item_id
    await dm.switch_to(AdminSG.materials_upload)


async def on_material_photo_upload(message: Message, widget: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    subject = dm.dialog_data.get("material_subject")

    if not message.photo:
        await message.reply("❌ Надішліть фото!")
        return

    file_id = message.photo[-1].file_id
    material = await repo.materials.get_by_subject(subject)
    images = list(material.images or []) if material else []

    if file_id not in images:
        images.append(file_id)
        await repo.materials.update_materials(subject, images)
        await message.reply(f"✅ Фото додано! Всього: {len(images)}")
    else:
        await message.reply("⚠️ Це фото вже є в матеріалах.")


async def on_clear_materials(c: Any, b: Any, dm: DialogManager) -> None:
    repo: RequestsRepo = dm.middleware_data.get("repo")
    subject = dm.dialog_data.get("material_subject")
    await repo.materials.clear_materials(subject)
    await c.answer("✅ Всі матеріали для предмету видалено.")


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def get_windows() -> list:
    subjects = [(label, slug) for slug, label in SUBJECT_LABELS.items()]

    return [
        Window(
            Const("📚 <b>Обери предмет для довідкових матеріалів</b>"),
            Column(
                Select(
                    Format("{item[0]}"), id="m_subj",
                    item_id_getter=lambda x: x[1], items="subjects",
                    on_click=on_material_subject_selected,
                ),
            ),
            Button(Const("🔙 Назад"), id="back_menu",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.menu)),
            state=AdminSG.materials_subjects,
            getter=lambda dm, **kw: {"subjects": [(label, slug) for slug, label in SUBJECT_LABELS.items()]},
        ),
        Window(
            Format(
                "📚 <b>Довідкові матеріали: {subject_label}</b>\n\n"
                "Завантажено фото: <b>{count}</b>\n\n"
                "👇 <b>Щоб додати фото, просто надішліть його сюди.</b>\n"
                "Можна надсилати по одному або декілька (як альбом)."
            ),
            Button(Const("🧹 Очистити всі матеріали"), id="clear_m",
                   on_click=on_clear_materials, when="has_images"),
            Button(Const("🔙 Назад до предметів"), id="back_m_subj",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.materials_subjects)),
            MessageInput(on_material_photo_upload, content_types=[ContentType.PHOTO]),
            state=AdminSG.materials_upload,
            getter=get_material_upload_data,
        ),
    ]
