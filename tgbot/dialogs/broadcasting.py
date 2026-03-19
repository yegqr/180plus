from typing import Any
from aiogram import F
from aiogram.types import Message, ContentType
from aiogram_dialog import Dialog, Window, DialogManager
from aiogram_dialog.widgets.kbd import Button, Row, Column, Select, Cancel, Back
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.media import DynamicMedia
from aiogram.fsm.state import StatesGroup, State

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.services.broadcaster import broadcast

class BroadcastSG(StatesGroup):
    target = State()
    content = State()
    confirm = State()
    sending = State()

# --- Getters ---

async def get_targets(dialog_manager: DialogManager, **kwargs):
    return {
        "targets": [
            ("👥 Усі користувачі", "all"),
            ("📅 Активні сьогодні", "active_today"),
            ("📅 Активні цього тижня", "active_week"),
            ("💤 Неактивні 1-2 дні", "inactive_1_2"),
            ("💤 Неактивні 3-6 днів", "inactive_3_6"),
            ("💤 Неактивні 7-13 днів", "inactive_7_13"),
            ("💤 Неактивні 14-20 днів", "inactive_14_20"),
            ("💤 Неактивні 21-27 днів", "inactive_21_27"),
            ("☠️ Неактивні 28+ днів", "inactive_28_plus"),
        ]
    }

async def get_preview(dialog_manager: DialogManager, **kwargs):
    from aiogram_dialog.api.entities import MediaAttachment, MediaId
    
    data = dialog_manager.dialog_data
    content_type = data.get("content_type", "text")
    file_id = data.get("file_id")
    caption = data.get("text", "")
    target_name = data.get("target_name", "Unknown")
    
    media = None
    if content_type == "photo" and file_id:
        media = MediaAttachment(type=ContentType.PHOTO, file_id=MediaId(file_id))
    elif content_type == "animation" and file_id:
        media = MediaAttachment(type=ContentType.ANIMATION, file_id=MediaId(file_id))
    elif content_type == "video" and file_id:
        media = MediaAttachment(type=ContentType.VIDEO, file_id=MediaId(file_id))
        
    names = {
        "text": "Текст 📝",
        "photo": "Фото 🖼️",
        "animation": "GIF 🎞️",
        "video": "Відео 📹",
        "video_note": "Круглешко 🎥",
        "poll": "Опитування 📊",
        "other": "Файл/Інше 📁"
    }
        
    return {
        "text": caption,
        "media": media,
        "target": target_name,
        "count": data.get("count", "?"),
        "content_type_name": names.get(content_type, content_type)
    }

# --- Handlers ---

async def on_target_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    
    # Get count to show expected reach (optional, but good UX)
    users = await repo.users.get_users_for_broadcast(item_id)
    
    if not users:
        await c.answer("❌ Немає користувачів у цій категорії!", show_alert=True)
        return

    dm.dialog_data["target_type"] = item_id
    
    targets = (await get_targets(dm))["targets"]
    target_name = next((t[0] for t in targets if t[1] == item_id), item_id)
    dm.dialog_data["target_name"] = target_name
    dm.dialog_data["count"] = len(users)
    
    await dm.switch_to(BroadcastSG.content)

async def on_content_input(message: Message, widget: Any, dm: DialogManager):
    # Store the message itself for copying
    dm.dialog_data["from_chat_id"] = message.chat.id
    dm.dialog_data["message_id"] = message.message_id
    
    # Still determine type for preview purposes
    if message.photo: dm.dialog_data["content_type"] = "photo"
    elif message.animation: dm.dialog_data["content_type"] = "animation"
    elif message.video: dm.dialog_data["content_type"] = "video"
    elif message.video_note: dm.dialog_data["content_type"] = "video_note"
    elif message.poll: dm.dialog_data["content_type"] = "poll"
    elif message.text: dm.dialog_data["content_type"] = "text"
    else:
        dm.dialog_data["content_type"] = "other"

    await dm.switch_to(BroadcastSG.confirm)

async def start_broadcast(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")
    
    target = dm.dialog_data["target_type"]
    users = await repo.users.get_users_for_broadcast(target)
    
    from_chat_id = dm.dialog_data.get("from_chat_id")
    message_id = dm.dialog_data.get("message_id")
    
    await c.message.answer(f"🚀 Починаю розсилку на {len(users)} користувачів...")
    
    count = 0
    blocked_count = 0
    error_count = 0
    import asyncio
    for user_id in users:
        try:
            # Universal way to send any message
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            count += 1
            await asyncio.sleep(0.05) # Rate limit
        except (exceptions.TelegramForbiddenError, exceptions.TelegramBadRequest) as e:
            blocked_count += 1
            # Optional: deactivate user
            try:
                from tgbot.services.broadcaster import _deactivate_user
                await _deactivate_user(bot, user_id)
            except: pass
        except Exception as e:
            error_count += 1
            logger.error(f"Broadcasting error for {user_id}: {e}")
            
    await c.message.answer(
        f"✅ Розсилка завершена!\n"
        f"📊 Результати:\n"
        f"✅ Доставлено: {count}\n"
        f"🚫 Заблокували: {blocked_count}\n"
        f"❌ Помилки: {error_count}"
    )
    await dm.done()


broadcast_dialog = Dialog(
    Window(
        Const("📡 <b>Оберіть аудиторію для розсилки:</b>"),
        Column(
            Select(
                Format("{item[0]}"),
                id="target_sel",
                item_id_getter=lambda x: x[1],
                items="targets",
                on_click=on_target_selected
            )
        ),
        Cancel(Const("🔙 Назад")),
        state=BroadcastSG.target,
        getter=get_targets,
    ),
    Window(
        Format("🎯 Аудиторія: <b>{target}</b> ({count} люд.)\n\n"
               "✏️ <b>Надішліть повідомлення для розсилки.</b>\n"
               "Можна надсилати будь-що:\n"
               "- Текст, Фото, Відео, GIF\n"
               "- 🎥 <b>Відео-нотатки (\"круглешки\")</b>\n"
               "- 📊 <b>Опитування та Вікторини</b>\n"
               "- Файли, Голосові тощо"),
        MessageInput(on_content_input, content_types=[ContentType.ANY]),
        Back(Const("🔙 Назад")),
        state=BroadcastSG.content,
        getter=get_preview
    ),
    Window(
        DynamicMedia("media", when=F["media"]),
        Format("👇 <b>Попередній перегляд:</b>\n"
               "Тип контенту: <code>{content_type_name}</code>\n\n"
               "🎯 Аудиторія: <b>{target}</b> ({count} люд.)"),
        Row(
            Button(Const("🚀 Надіслати"), id="btn_send", on_click=start_broadcast),
            Back(Const("✏️ Редагувати")),
        ),
        state=BroadcastSG.confirm,
        getter=get_preview
    )
)
