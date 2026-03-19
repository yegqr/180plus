from __future__ import annotations

from typing import Any
from aiogram.types import CallbackQuery

from aiogram.fsm.state import StatesGroup, State
from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button, Group, Cancel
from aiogram_dialog.widgets.text import Const, Format

from infrastructure.database.models import User

from .simulation import SimulationSG
from .random_mode import RandomSG

class SubjectMenuSG(StatesGroup):
    menu = State()

async def get_subject_data(dialog_manager: DialogManager, **kwargs) -> dict:
    user: User = dialog_manager.middleware_data.get("user")
    
    subject_map = {
        "math": "🧮 math",
        "mova": "🇺🇦 mova", 
        "eng": "🇬🇧 eng",
        "hist": "📌 hist",
        "physics": "⚛️ phy",
    }
    
    return {
        "subject": subject_map.get(user.selected_subject, user.selected_subject),
        "is_admin": user.is_admin
    }

async def on_simulation(callback: Any, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(SimulationSG.select_year, mode=StartMode.NORMAL)

async def on_random(callback: Any, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(RandomSG.question, mode=StartMode.NORMAL)


async def on_calc(c: CallbackQuery, button: Button, manager: DialogManager) -> None:
    from .calculator import CalculatorSG
    await manager.start(CalculatorSG.main, mode=StartMode.NORMAL)

async def on_admin_panel(callback: Any, button: Button, dialog_manager: DialogManager) -> None:
    from .admin import AdminSG
    await dialog_manager.start(AdminSG.menu, mode=StartMode.NORMAL)

async def on_stats(callback: Any, button: Button, dialog_manager: DialogManager) -> None:
    from .stats import StatsSG
    await dialog_manager.start(StatsSG.main, mode=StartMode.NORMAL)

subject_menu_dialog = Dialog(
    Window(
        Format("📚 Предмет: {subject}\nОбери дію:"),
        Group(
            Button(Const("📚 Симуляція"), id="btn_simulation", on_click=on_simulation),
            Button(Const("🎲 Рандом"), id="btn_random", on_click=on_random),
            width=2,
        ),
        Group(
            Button(Const("📊 Статистика"), id="btn_stats", on_click=on_stats),
            Button(Const("🧮 Розрахунок КБ"), id="btn_calc", on_click=on_calc),
            Button(Const("🛠 Адмін-панель"), id="btn_admin", on_click=on_admin_panel, when="is_admin"),
            width=2,
        ),
        state=SubjectMenuSG.menu,
        getter=get_subject_data,
    ),
)
