from __future__ import annotations

from typing import Any

from aiogram.fsm.state import StatesGroup, State
from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button, Group
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.models import User
from infrastructure.database.repo.requests import RequestsRepo
from .admin import AdminSG
from .simulation import SimulationSG
from .random_mode import RandomSG
from aiogram_dialog.widgets.kbd import Select
from tgbot.services.topic_manager import TopicManager

class MainSG(StatesGroup):
    menu = State()

async def get_user_data(dialog_manager: DialogManager, **kwargs) -> dict:
    user: User = dialog_manager.middleware_data.get("user")
    
    if not user:
        start_data = dialog_manager.start_data or {}
        name = start_data.get("user_name", "User")
        is_admin = start_data.get("user_is_admin", False)
    else:
        name = user.full_name
        is_admin = user.is_admin

    subjects = [{"id": k, "name": v} for k, v in TopicManager.SUBJECTS.items()]
    
    current_subject = user.selected_subject if user else "math"
    subject_label = TopicManager.SUBJECTS.get(current_subject, current_subject)

    return {
        "name": name,
        "is_admin": is_admin,
        "subjects": subjects,
        "subject_label": subject_label
    }

from tgbot.dialogs.calculator import CalculatorSG
from aiogram.types import CallbackQuery

async def on_calc(c: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await manager.start(CalculatorSG.main, mode=StartMode.NORMAL)

async def on_admin_panel(callback: Any, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(AdminSG.menu, mode=StartMode.NORMAL)

async def on_stats(callback: Any, button: Button, dialog_manager: DialogManager) -> None:
    from .stats import StatsSG
    await dialog_manager.start(StatsSG.main, mode=StartMode.NORMAL)

async def on_simulation(callback: Any, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(SimulationSG.select_year, mode=StartMode.NORMAL)

async def on_random(callback: Any, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(RandomSG.question, mode=StartMode.NORMAL)

async def on_subject_selected(c: CallbackQuery, widget: Any, manager: DialogManager, item_id: str) -> None:
    repo: RequestsRepo = manager.middleware_data.get("repo")
    user: User = manager.middleware_data.get("user")

    await repo.users.update_subject(user.user_id, item_id)
    user.selected_subject = item_id

    # Invalidate Redis user cache so the next request picks up the new subject
    # instead of serving the stale cached value for up to 5 minutes.
    redis = manager.middleware_data.get("user_cache_redis")
    if redis:
        try:
            await redis.delete(f"ucache:{user.user_id}")
        except Exception:
            pass


main_menu_dialog = Dialog(
    Window(
        Format("Вітаю, {name}!\n"
               "📚 Предмет: <b>{subject_label}</b>\n\n"
               "Обери дію:"),
        Group(
            Button(Const("📚 Симуляція"), id="btn_sim", on_click=on_simulation),
            Button(Const("🎲 Рандом"), id="btn_rand", on_click=on_random),
            width=2
        ),
        Group(
            Select(
                Format("{item[name]}"),
                id="subj_select",
                item_id_getter=lambda x: x["id"],
                items="subjects",
                on_click=on_subject_selected,
            ),
            width=3
        ),
        Group(
            Button(Const("📊 Статистика"), id="btn_stats", on_click=on_stats),
            Button(Const("🧮 Розрахунок КБ"), id="btn_calc", on_click=on_calc),
            Button(Const("🛠 Адмін-панель"), id="btn_admin", on_click=on_admin_panel, when="is_admin"),
            width=2,
        ),
        state=MainSG.menu,
        getter=get_user_data,
    ),
)
