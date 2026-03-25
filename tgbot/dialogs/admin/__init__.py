"""
Admin dialog package — assembles all admin windows into a single Dialog.
"""

from __future__ import annotations

from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Column
from aiogram_dialog.widgets.text import Const

from tgbot.dialogs.broadcasting import BroadcastSG
from .states import AdminSG
from . import content, daily, dashboard, maintenance, materials, question_detail, referrals, settings, upload

admin_dialog = Dialog(
    Window(
        Const("🛠 <b>Адмін-панель</b>"),
        Column(
            Button(Const("📊 Статистика бота"), id="btn_stats",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.stats)),
            Button(Const("📚 Керування контентом"), id="btn_content",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.subjects)),
            Button(Const("🛡 Керування адмінами"), id="btn_admins",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.manage_admins)),
            Button(Const("📢 Розсилка"), id="btn_broadcast",
                   on_click=lambda c, b, d: d.start(BroadcastSG.target)),
            Button(Const("🔥 Daily Challenge"), id="btn_daily",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.daily_settings)),
            Button(Const("📚 Довідкові матеріали"), id="btn_materials",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.materials_subjects)),
            Button(Const("📦 Масове завантаження (ZIP)"), id="btn_bulk",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.bulk_upload)),
            Button(Const("🚧 Технічні роботи"), id="btn_maint",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.maintenance)),
            Button(Const("🔗 Реф-посилання"), id="btn_referrals",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.referral_list)),
            Button(Const("⚙️ Налаштування"), id="btn_settings",
                   on_click=lambda c, b, d: d.switch_to(AdminSG.settings)),
        ),
        Cancel(Const("🏠 Вихід")),
        state=AdminSG.menu,
    ),
    *dashboard.get_windows(),
    *content.get_windows(),
    *question_detail.get_windows(),
    *upload.get_windows(),
    *settings.get_windows(),
    *maintenance.get_windows(),
    *materials.get_windows(),
    *daily.get_windows(),
    *referrals.get_windows(),
)

__all__ = ["admin_dialog", "AdminSG"]
