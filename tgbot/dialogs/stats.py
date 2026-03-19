from typing import Any
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ContentType
from aiogram_dialog import Dialog, Window, DialogManager
from aiogram_dialog.widgets.kbd import Cancel, Button, Back
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.text import Const, Format, Multi

from infrastructure.database.models import User
from infrastructure.database.repo.requests import RequestsRepo

class StatsSG(StatesGroup):
    main = State()
    input_feedback = State()

async def get_stats(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    
    stats = await repo.results.get_user_stats(user.user_id)
    
    subject_map = {
        "math": "Математика 🔢",
        "mova": "Українська мова 🇺🇦", 
        "eng": "Англійська мова 🇬🇧",
        "hist": "Історія України 🇺🇦",
        "physics": "Фізика 🧲",
    }

    from tgbot.misc.nmt_scoring import get_raw_score_equivalent

    subj_lines = []
    for s in stats["subject_stats"]:
        name = subject_map.get(s["subject"], s["subject"])
        avg = s["avg"]
        median = s["median"]
        
        avg_tb = get_raw_score_equivalent(s["subject"], avg)
        avg_text = f"<b>{avg}</b> (<b>{avg_tb}</b> ТБ)"
        
        if median == "-":
            median_text = "— (робіть ще, поки даних недостатньо✨)"
        else:
            median_tb = get_raw_score_equivalent(s["subject"], median)
            median_text = f"<b>{median}</b> (<b>{median_tb}</b> ТБ)"
            
        line = (
            f"🔹 <b>{name}</b>\n"
            f"   Середній бал: {avg_text}\n"
            f"   Прогноз бала НМТ: {median_text}"
        )
        subj_lines.append(line)

    summary_text = (
        f"📊 <b>Твоя статистика з усіх предметів:</b>\n\n"
        f"📝 Пройдено симуляцій: <b>{stats['total_sims']}</b>\n"
        f"✅ Виконано завдань (у симуляціях): <b>{stats['sim_correct']}</b>\n"
        f"🎲 Виконано завдань (у рандомі): <b>{stats['rand_correct']}</b>\n\n"
        + ("\n\n".join(subj_lines) if subj_lines else "<i>Даних по предметах поки немає. Пройди першу симуляцію!</i>")
    )

    return {
        "stats_text": summary_text,
        "is_admin": user.is_admin,
        "daily_sub_emoji": "✅" if user.daily_sub else "❌",
        "daily_sub_text": "Сповіщення (Daily Challenge)"
    }

async def on_toggle_daily_sub(callback: Any, button: Button, dialog_manager: DialogManager):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    
    # Toggle
    new_status = not user.daily_sub
    await repo.users.update_daily_sub(user.user_id, new_status)
    
    # Update local user object in middleware/dialog data if needed to reflect immediately without re-fetching?
    # Middleware usually fetches user once per update. 
    # But since we are likely re-rendering, `get_stats` uses middleware user.
    # Middleware user object is persistent in SQLAlchemy session until commit?
    # Yes, `user` object is attached to session. Ideally we just update attribute.
    user.daily_sub = new_status
    # Repo update does the commit.
    
    # Optional: Answer callback
    text = "🔔 Сповіщення увімкнено!" if new_status else "🔕 Сповіщення вимкнено!"
    await callback.answer(text)

async def on_feedback_button(callback: Any, button: Button, dialog_manager: DialogManager):
    await dialog_manager.switch_to(StatsSG.input_feedback)

async def on_feedback_input(message: Message, message_input: MessageInput, dialog_manager: DialogManager):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    bot = message.bot
    config = dialog_manager.middleware_data.get("config")
    
    # Get stats for the report
    stats_data = await get_stats(dialog_manager)
    stats_text = stats_data["stats_text"]
    
    user_info = (
        f"📩 <b>Новий відгук!</b>\n"
        f"👤 Користувач: {user.full_name}\n"
        f"🔗 Тег: @{user.username if user.username else 'відсутній'}\n"
        f"🆔 ID: <code>{user.user_id}</code>\n\n"
        f"💬 <b>Текст відгуку:</b>\n{message.text or message.caption or '<i>(тільки фото)</i>'}\n\n"
        f"📊 <b>Статистика на момент відправки:</b>\n{stats_text}"
    )
    
    for admin_id in config.tg_bot.admin_ids:
        try:
            if message.photo:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=message.photo[-1].file_id,
                    caption=user_info[:1024] # Telegram caption limit
                )
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text=user_info
                )
        except Exception:
            pass

    await message.answer("✅ Дякуємо! Ваш відгук надіслано адміністрації.")
    await dialog_manager.switch_to(StatsSG.main)

stats_dialog = Dialog(
    Window(
        Format("{stats_text}"),
        Button(Format("{daily_sub_emoji} {daily_sub_text}"), id="btn_daily_sub", on_click=on_toggle_daily_sub),
        Button(Const("✍️ Зворотній зв'язок"), id="btn_feedback", on_click=on_feedback_button),
        Cancel(Const("🏠 Меню")),
        state=StatsSG.main,
        getter=get_stats,
    ),
    Window(
        Const("📝 <b>Форма для зворотного зв'язку</b>\n\n"
              "Ти можеш написати текст або надіслати фото з описом. "
              "Адміністратор отримає твоє повідомлення та надасть відповідь asap."),
        MessageInput(on_feedback_input, content_types=[ContentType.TEXT, ContentType.PHOTO]),
        Back(Const("⬅️ Назад")),
        state=StatsSG.input_feedback,
    ),
)
