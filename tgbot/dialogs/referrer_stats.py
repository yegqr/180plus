from __future__ import annotations

from aiogram.fsm.state import StatesGroup, State
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.models import User
from infrastructure.database.repo.requests import RequestsRepo


class ReferrerStatsSG(StatesGroup):
    main = State()


async def get_referrer_stats(dialog_manager: DialogManager, **kwargs) -> dict:
    user: User = dialog_manager.middleware_data.get("user")
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")

    items = await repo.referrals.get_owner_links_with_stats(user.user_id)

    if not items:
        return {"stats_text": "— У вас немає реф-посилань —"}

    lines = []
    for entry in items:
        link = entry["link"]
        s = entry["stats"]
        status = "🟢" if link.is_active else "🔴"
        config = dialog_manager.middleware_data.get("config")
        bot_username = getattr(getattr(config, "tg_bot", None), "bot_username", "YOUR_BOT")
        lines.append(
            f"{status} <b>{link.name}</b>\n"
            f"🔗 <code>https://t.me/{bot_username}?start=ref_{link.code}</code>\n"
            f"Сьогодні: <b>{s['today']}</b>\n"
            f"Тиждень ПН-НД: <b>{s['week']}</b>\n"
            f"Місяць: <b>{s['month']}</b>\n"
            f"За весь час: <b>{s['total']}</b>"
        )

    return {"stats_text": "\n\n".join(lines)}


referrer_stats_dialog = Dialog(
    Window(
        Format(
            "📈 <b>Моя статистика рефералів</b>\n\n"
            "{stats_text}"
        ),
        Button(
            Const("🔄 Оновити"),
            id="ref_refresh",
            on_click=lambda c, b, d: d.switch_to(ReferrerStatsSG.main),
        ),
        Button(
            Const("🔙 Назад"),
            id="ref_back",
            on_click=lambda c, b, d: d.back(),
        ),
        state=ReferrerStatsSG.main,
        getter=get_referrer_stats,
    ),
)
