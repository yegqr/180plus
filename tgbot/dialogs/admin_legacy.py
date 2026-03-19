from typing import Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from aiogram import F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ContentType
from aiogram_dialog import Dialog, Window, DialogManager, StartMode, ShowMode
from aiogram_dialog.widgets.kbd import Button, Select, Row, Column, Back, Cancel, Group
from aiogram_dialog.widgets.input import MessageInput, TextInput
from aiogram_dialog.widgets.text import Const, Format

from sqlalchemy import select
from infrastructure.database.models import Question
from infrastructure.database.repo.requests import RequestsRepo
from .broadcasting import BroadcastSG
from tgbot.services.album_manager import AlbumManager
from tgbot.misc.constants import (
    SUBJECT_LABELS,
    ALBUM_WAIT_SECONDS,
    JOIN_REQUEST_DELAY,
    TG_CAPTION_SAFE_LIMIT,
    TG_TEXT_SAFE_LIMIT,
)
from tgbot.misc.utils import get_question_images, parse_question_caption
import asyncio

# Buffer: {media_group_id: {"meta": dict, "images": list[str], "task": asyncio.Task}}
ALBUM_BUFFER = {}

class AdminSG(StatesGroup):
    menu = State()
    stats = State()
    manage_admins = State()
    subjects = State()
    years = State()
    sessions = State()
    questions = State()
    question_detail = State()
    upload_new = State()
    settings = State()
    approve_confirm_1 = State()
    approve_confirm_2 = State()
    update_video = State()
    daily_settings = State()
    maintenance = State()
    maintenance_confirm = State()
    maintenance_finish = State()
    materials_subjects = State()
    materials_subjects = State()
    materials_upload = State()
    gemini_settings = State()
    bulk_upload = State()
    delete_session_confirm = State()
    edit_session_year = State()
    edit_session_name = State()

# --- Getters ---

async def get_admin_dashboard(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    
    # User Stats
    stats = await repo.users.get_active_stats()
    
    # UTM Stats
    current_week = await repo.stats.get_weekly_stats(week_offset=0)
    last_week = await repo.stats.get_weekly_stats(week_offset=1)
    
    # Content Stats
    content_stats = await repo.stats.get_content_stats()

    # Daily Activity Stats (New)
    daily_activity = await repo.stats.get_daily_activity_stats()
    
    # Format for display
    def fmt_week(data):
        if not data: return "— порожньо —"
        lines = [f"• {row['source']}: {row['count']}" for row in data]
        return "\n".join(lines)
        
    def fmt_content(data):
        if not data: return "— порожньо —"
        lines = [f"• {row['subject']}: {row['count']}" for row in data]
        return "\n".join(lines)

    def fmt_daily(activity):
        lines = []
        subjects = set(list(activity["simulations"].keys()) + list(activity["random"].keys()))
        if not subjects:
            return "— сьогодні активності не було —"
        
        for s in sorted(subjects):
            sims = activity["simulations"].get(s, 0)
            rand = activity["random"].get(s, 0)
            lines.append(f"• {s.upper()}: {sims} сим. / {rand} ранд.")
        return "\n".join(lines)

    return {
        "total": stats["total"],
        "today": stats["today"],
        "week": stats["week"],
        "utm_current": fmt_week(current_week),
        "utm_last": fmt_week(last_week),
        "content_stats": fmt_content(content_stats),
        "daily_sims": daily_activity["total_sims"],
        "daily_rand": daily_activity["total_rand"],
        "daily_breakdown": fmt_daily(daily_activity)
    }

async def get_admins_list(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    admins = await repo.users.get_admins()
    return {
        "admins": [(f"{a.full_name} ({a.user_id})", a.user_id) for a in admins]
    }

async def get_admin_subjects(dialog_manager: DialogManager, **kwargs):
    return {
        "subjects": [(label, slug) for slug, label in SUBJECT_LABELS.items()]
    }

async def get_admin_years(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    subject = dialog_manager.dialog_data.get("admin_subject")
    years = await repo.questions.get_unique_years(subject)
    return {"years": [(str(y), y) for y in years], "subject": subject}

async def get_admin_sessions(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    subject = dialog_manager.dialog_data.get("admin_subject")
    year = dialog_manager.dialog_data.get("admin_year")
    sessions = await repo.questions.get_unique_sessions(subject, year)
    return {"sessions": [(s, s) for s in sessions], "subject": subject, "year": year}

async def get_admin_questions(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    subject = dialog_manager.dialog_data.get("admin_subject")
    year = dialog_manager.dialog_data.get("admin_year")
    session = dialog_manager.dialog_data.get("admin_session")
    questions = await repo.questions.get_questions_by_criteria(subject, year, session)
    return {
        "questions": [(f"Q#{q.q_number}", q.id) for q in questions],
        "subject": subject, "year": year, "session": session
    }

async def get_question_detail(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    q_id = dialog_manager.dialog_data.get("admin_q_id")
    question = await repo.questions.get_question_by_id(q_id)
    
    if not question:
        return {"q": None, "image": None, "ans_text": "Питання видалено"}

    from aiogram_dialog.api.entities import MediaAttachment, MediaId
    image = MediaAttachment(type=ContentType.PHOTO, file_id=MediaId(question.image_file_id))
    
    ans_text = str(question.correct_answer)
    if question.q_type == "match":
        ans_text = ", ".join([f"{k}-{v}" for k, v in question.correct_answer.get("pairs", {}).items()])
    elif question.q_type == "choice":
        ans_text = f"{question.correct_answer.get('answer')} (з {question.correct_answer.get('options')})"
    elif question.q_type == "short":
        ans_text = str(question.correct_answer.get("answer"))

    # Toggle Explanation Logic
    show_expl = dialog_manager.dialog_data.get("show_expl", False)
    show_cats = dialog_manager.dialog_data.get("show_cats", False)
    
    import html
    raw_explanation = question.explanation
    
    explanation_safe = None
    is_long_text = False
    
    if show_expl and raw_explanation:
        explanation_safe = html.escape(raw_explanation)
        # Identify if total length exceeds caption limit
        total_len = len(str(ans_text)) + len(explanation_safe) + 200
        is_long_text = total_len > TG_CAPTION_SAFE_LIMIT
    
    # Categories Logic
    categories_text = "—"
    if question.categories:
        from tgbot.misc.categories import CATEGORIES
        # Flatten categories
        flat_cats = {}
        for subj_data in CATEGORIES.values():
            for section, cats in subj_data.items():
                for c in cats:
                    flat_cats[c['slug']] = c['name']
        
        cat_names = [flat_cats.get(slug, slug) for slug in question.categories]
        categories_text = ", ".join(cat_names)
    
    # Toggle Image Logic
    # Default: if showing explanation -> hide image if long
    force_image = dialog_manager.dialog_data.get("force_image", False)
    
    # Check album
    is_album = bool(dialog_manager.dialog_data.get("album_message_ids"))

    # Show image if: (Image exists) AND (Not Album) AND (Explanation Hidden OR Text Short OR Force Image)
    # If showing categories, we also might need space? Usually cats are short.
    show_image = (image is not None) and (not is_album) and ((not show_expl) or (not is_long_text) or force_image)
    
    
    if show_image and is_long_text and show_expl:
        limit = TG_CAPTION_SAFE_LIMIT - len(str(ans_text))
        if explanation_safe and len(explanation_safe) > limit:
            explanation_safe = explanation_safe[:limit] + "...\n(<i>текст обрізано, натисніть '📝 Показати текст'</i>)"

    if not show_image and explanation_safe and len(explanation_safe) > TG_TEXT_SAFE_LIMIT:
        explanation_safe = explanation_safe[:TG_TEXT_SAFE_LIMIT] + "...\n(<i>текст занадто довгий для Telegram</i>)"

    return {
        "q": question, 
        "image": image, 
        "ans_text": ans_text, 
        "explanation_safe": explanation_safe, 
        "categories_text": categories_text,
        "is_long_text": is_long_text,
        "show_image": show_image,
        "force_image": force_image,
        "show_expl": show_expl,
        "show_cats": show_cats,
        "has_expl": bool(raw_explanation),
        "has_cats": bool(question.categories),
        "is_album": is_album
    }

async def get_admin_settings(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    video_id = await repo.settings.get_setting("onboarding_video", "Не встановлено")
    pending_count = len(await repo.join_requests.get_all_requests())
    return {
        "video_id": video_id,
        "pending_count": pending_count
    }

async def get_daily_status(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    is_enabled_str = await repo.settings.get_setting("daily_enabled", "true")
    is_enabled = is_enabled_str.lower() == "true"
    
    lottery_status = await repo.settings.get_setting("daily_lottery_status", "Ще не розіграно")
    
    # Prettify status
    if lottery_status == "LOSS":
        status_info = "❌ Програно (сьогодні розсилки не буде)"
    elif lottery_status.startswith("WIN"):
        time_part = lottery_status.split("(")[1].replace(")", "")
        status_info = f"🎯 Виграно! Заплановано на {time_part}"
    elif "MISS" in lottery_status:
        status_info = "⌛ Пропущено (запізно для розсилки)"
    else:
        status_info = lottery_status

    return {
        "is_enabled": is_enabled,
        "status_emoji": "✅" if is_enabled else "❌",
        "status_text": "УВІМКНЕНО" if is_enabled else "ВИМКНЕНО",
        "lottery_info": status_info
    }

async def get_material_upload_data(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    subject = dialog_manager.dialog_data.get("material_subject")
    
    material = await repo.materials.get_by_subject(subject)
    images = material.images if material else []
    
    subj_label = SUBJECT_LABELS.get(subject, subject)

    return {
        "subject": subject,
        "subject_label": subj_label,
        "count": len(images),
        "has_images": len(images) > 0
    }

async def get_gemini_settings(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    config = dialog_manager.middleware_data.get("config")
    
    db_key = await repo.settings.get_setting("gemini_api_key")
    config_key = config.misc.gemini_api_key
    
    active_key = db_key or config_key
    source = "Database" if db_key else ("Config (.env)" if config_key else "None")
    
    return {
        "has_key": bool(active_key),
        "source": source,
        "key_preview": f"{active_key[:8]}...{active_key[-4:]}" if active_key else "—"
    }

# --- Handlers ---

async def on_update_video(message: Message, widget: Any, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    
    file_id = None
    if message.video:
        file_id = message.video.file_id
    elif message.animation:
        file_id = message.animation.file_id
    elif message.text:
        file_id = message.text.strip()
        
    if file_id:
        await repo.settings.set_setting("onboarding_video", file_id)
        await message.reply(f"✅ Відео-онбординг оновлено!\nID: {file_id}")
        await dm.switch_to(AdminSG.settings)
    else:
        await message.reply("❌ Будь ласка, надішліть відео, GIF або текстовий ID.")

async def on_approve_all(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")
    
    requests = await repo.join_requests.get_all_requests()
    if not requests:
        await c.answer("❌ Немає активних запитів!", show_alert=True)
        return

    await c.message.answer(f"⏳ Починаю приймати {len(requests)} запитів...")
    
    success_count = 0
    import asyncio
    for user_id, chat_id in requests:
        try:
            await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            success_count += 1
            await asyncio.sleep(JOIN_REQUEST_DELAY)
        except Exception:
            pass
            
    await repo.join_requests.clear_all()
    await c.message.answer(f"✅ Готово! Прийнято користувачів: {success_count}")
    await dm.switch_to(AdminSG.settings)

# --- Handlers ---

async def on_add_admin(message: Message, widget: Any, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    try:
        user_id = int(message.text.strip())
        user = await repo.users.get_user_by_id(user_id)
        if not user:
            await message.reply("❌ Користувача не знайдено в базі. Він має хоча б раз запустити бота.")
            return
        await repo.users.promote_admin(user_id)
        await message.reply(f"✅ Користувач {user.full_name} тепер адмін!")
    except ValueError:
        await message.reply("❌ Надішліть коректний ID (число).")

async def on_demote_admin(c: Any, w: Any, dm: DialogManager, item_id: str):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    curr_user = dm.middleware_data.get("user")
    if int(item_id) == curr_user.user_id:
        await c.answer("Ви не можете прибрати самого себе!", show_alert=True)
        return
    await repo.users.demote_admin(int(item_id))
    await c.message.reply(f"✅ Адміна {item_id} видалено.")

async def on_subject_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    dm.dialog_data["admin_subject"] = item_id
    await dm.switch_to(AdminSG.years)

async def on_year_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    dm.dialog_data["admin_year"] = int(item_id)
    await dm.switch_to(AdminSG.sessions)

async def on_session_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    dm.dialog_data["admin_session"] = item_id
    await dm.switch_to(AdminSG.questions)

async def on_question_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    q_id = int(item_id)
    dm.dialog_data["admin_q_id"] = q_id
    dm.dialog_data["show_expl"] = False # Reset on new question
    dm.dialog_data["force_image"] = False
    
    # Handle Album
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")
    
    # Cleanup any previous album (unlikely here but safe)
    old_album = dm.dialog_data.get("album_message_ids")
    if old_album:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album)
        dm.dialog_data["album_message_ids"] = []

    question = await repo.questions.get_question_by_id(q_id)
    images = question.images or []
    if not images and question.image_file_id:
        images = [question.image_file_id]
        
    if len(images) > 1:
        chat_id = dm.middleware_data.get("event_chat").id
        album_ids = await AlbumManager.send_album(bot, chat_id, images)
        dm.dialog_data["album_message_ids"] = album_ids
        dm.show_mode = ShowMode.SEND
    else:
        dm.show_mode = ShowMode.EDIT

    await dm.switch_to(AdminSG.question_detail)

async def on_confirm_delete_session(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    subject = dm.dialog_data.get("admin_subject")
    year = dm.dialog_data.get("admin_year")
    session = dm.dialog_data.get("admin_session")
    
    await repo.questions.delete_questions_by_session(subject, year, session)
    await c.answer("✅ Всі питання сесії видалено!", show_alert=True)
    await dm.switch_to(AdminSG.sessions)

async def on_change_session_year(message: Message, widget: Any, dm: DialogManager, data: Any):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    old_subject = dm.dialog_data.get("admin_subject")
    old_year = dm.dialog_data.get("admin_year")
    old_session = dm.dialog_data.get("admin_session")
    
    try:
        new_year = int(message.text.strip())
        await repo.questions.update_session_metadata(old_subject, old_year, old_session, new_year=new_year)
        await message.reply(f"✅ Рік змінено на {new_year}!")
        dm.dialog_data["admin_year"] = new_year
        await dm.switch_to(AdminSG.questions)
    except ValueError:
        await message.reply("❌ Надішліть коректний рік (число).")

async def on_change_session_name(message: Message, widget: Any, dm: DialogManager, data: Any):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    old_subject = dm.dialog_data.get("admin_subject")
    old_year = dm.dialog_data.get("admin_year")
    old_session = dm.dialog_data.get("admin_session")
    
    new_name = message.text.strip()
    if new_name:
        await repo.questions.update_session_metadata(old_subject, old_year, old_session, new_session=new_name)
        await message.reply(f"✅ Сесію перейменовано на {new_name}!")
        dm.dialog_data["admin_session"] = new_name
        await dm.switch_to(AdminSG.questions)
    else:
        await message.reply("❌ Назва не може бути порожньою.")

async def on_back_from_detail(c: Any, b: Button, dm: DialogManager):
    # Cleanup album
    bot = dm.middleware_data.get("bot")
    old_album = dm.dialog_data.get("album_message_ids")
    if old_album:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album)
        dm.dialog_data["album_message_ids"] = []
        
    await dm.switch_to(AdminSG.questions)

async def on_delete_q(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")
    
    # Cleanup album
    old_album = dm.dialog_data.get("album_message_ids")
    if old_album:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album)
        dm.dialog_data["album_message_ids"] = []

    await repo.questions.delete_question(dm.dialog_data["admin_q_id"])
    await dm.switch_to(AdminSG.questions)

async def on_edit_q(c: Any, b: Button, dm: DialogManager):
    # Cleanup album
    bot = dm.middleware_data.get("bot")
    old_album = dm.dialog_data.get("album_message_ids")
    if old_album:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album)
        dm.dialog_data["album_message_ids"] = []

    await dm.switch_to(AdminSG.upload_new)

async def delayed_album_save(media_group_id: str, repo: RequestsRepo, message: Message, config: Config):
    await asyncio.sleep(ALBUM_WAIT_SECONDS)  # Wait for all photos to arrive

    data = ALBUM_BUFFER.pop(media_group_id, None)
    if not data:
        return

    meta = data["meta"]
    images = data["images"]     # List of file_ids
    msg_ids = data["msg_ids"]   # List of message_ids to delete

    bot = message.bot
    chat_id = message.chat.id

    try:
        # 1. Save to DB
        await repo.questions.upsert_question(
            subject=meta["subject"], year=meta["year"], session=meta["session"], q_number=meta["q_number"],
            image_file_ids=images, q_type=meta["q_type"], correct_answer=meta["correct_answer"], weight=meta["weight"]
        )
        
        count = len(images)
        txt = f"✅ Питання Q#{meta['q_number']} збережено! (Фото: {count})"
        status_msg = await message.answer(txt)
        
        # 2. Auto-Delete User Uploads
        try:
             # msg_ids contains all individual messages of the album
             if hasattr(bot, "delete_messages"):
                 await bot.delete_messages(chat_id, msg_ids)
             else:
                 for mid in msg_ids:
                     try:
                         await bot.delete_message(chat_id, mid)
                     except Exception:
                         pass
        except Exception as e:
            logger.warning(f"Failed to delete uploads: {e}")

        # 3. Trigger Gemini Generation (with ALL images)
        # Check DB key
        db_key = await repo.settings.get_setting("gemini_api_key")
        active_key = db_key or config.misc.gemini_api_key

        if active_key:
            from tgbot.services.gemini import GeminiService
            import io
            
            async def generate_explanation():
                try:
                    await status_msg.edit_text(f"{txt}\n⏳ Генерую пояснення...")
                    
                    # Download all images
                    images_bytes = []
                    for file_id in images:
                        f = await bot.get_file(file_id)
                        # download file to memory
                        b = io.BytesIO()
                        await bot.download_file(f.file_path, b)
                        images_bytes.append(b.getvalue())
                        
                    service = GeminiService(active_key)
                    # Context text
                    q_text = f"Subject: {meta['subject']}, Type: {meta['q_type']}, Ans: {meta['correct_answer']}"
                    
                    # Pass subject explicitly
                    result_data = await service.generate_explanation(images_bytes, q_text, subject=meta['subject'])
                    explanation = result_data.get("explanation", "")
                    categories = result_data.get("categories", [])
                    
                    # Save explanation and categories
                    # We need q_id. Repo upsert doesn't return ID easily unless we query.
                    # Since we upserted, we can fetch by criteria.
                    questions = await repo.questions.get_questions_by_criteria(meta["subject"], meta["year"], meta["session"])
                    target_q = next((q for q in questions if q.q_number == meta["q_number"]), None)
                    
                    if target_q:
                        await repo.questions.update_explanation(target_q.id, explanation)
                        if categories:
                            await repo.questions.update_categories(target_q.id, categories)
                        await status_msg.edit_text(f"{txt}\n✅ Пояснення та категорії збережено!")
                    else:
                        await status_msg.edit_text(f"{txt}\n⚠️ Не вдалося зберегти пояснення (питання не знайдено).")

                except Exception as ex:
                    logger.error(f"Gen Error: {ex}")
                    await status_msg.edit_text(f"{txt}\n❌ Помилка генерації: {ex}")

            asyncio.create_task(generate_explanation())

    except Exception as e:
        await message.answer(f"❌ Помилка збереження альбому: {e}")


async def on_upload_photo(message: Message, widget: Any, dialog_manager: DialogManager):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    config = dialog_manager.middleware_data.get("config")
    
    media_group_id = message.media_group_id
    file_id = message.photo[-1].file_id
    msg_id = message.message_id

    if media_group_id:
        if media_group_id in ALBUM_BUFFER:
            # Append to existing group
            ALBUM_BUFFER[media_group_id]["images"].append(file_id)
            ALBUM_BUFFER[media_group_id]["msg_ids"].append(msg_id)
            return

        # New Media Group
        if not message.caption:
            await message.reply("❌ Перше фото альбому має бути з підписом!")
            # We don't return here? If user failed caption, we ignore? 
            # If we return, we might miss the rest of the album which is annoying.
            # But without caption we can't parse metadata.
            return

        # Parse Metadata
        try:
            meta = parse_question_caption(message.caption)
            ALBUM_BUFFER[media_group_id] = {
                "meta": meta,
                "images": [file_id],
                "msg_ids": [msg_id],
                "task": asyncio.create_task(delayed_album_save(media_group_id, repo, message, config))
            }
        except ValueError as e:
            await message.reply(f"❌ Помилка формату: {e}\nПриклад: math | 2024 | main | 1 | choice | 5 | А")
        except Exception as e:
            await message.reply(f"❌ Помилка парсингу: {e}")

    else:
        # Single Photo
        if not message.caption:
            await message.reply("❌ Надішліть фото з підписом!")
            return
            
        try:
            meta = parse_question_caption(message.caption)
            subject = meta["subject"]
            year = meta["year"]
            session = meta["session"]
            q_number = meta["q_number"]
            q_type = meta["q_type"]
            correct_answer = meta["correct_answer"]
            weight = meta["weight"]

            await repo.questions.upsert_question(
                subject=subject, year=year, session=session, q_number=q_number,
                image_file_ids=[file_id], q_type=q_type, correct_answer=correct_answer, weight=weight
            )
            
            msg = await message.reply(f"✅ Питання Q#{q_number} збережено!")
            
            # Auto-Delete User Upload
            try:
                await message.delete()
            except Exception:
                pass

            # Trigger Gemini
            db_key = await repo.settings.get_setting("gemini_api_key")
            active_key = db_key or config.misc.gemini_api_key

            if active_key:
                from tgbot.services.gemini import GeminiService
                import io
                
                async def generate_single():
                    try:
                        await msg.edit_text(f"{msg.text}\n⏳ Генерую пояснення...")
                        f = await message.bot.get_file(file_id)
                        b = io.BytesIO()
                        await message.bot.download_file(f.file_path, b)
                        
                        service = GeminiService(active_key)
                        q_text = f"Subject: {subject}, Type: {q_type}, Ans: {correct_answer}"
                        result_data = await service.generate_explanation([b.getvalue()], q_text, subject=subject)
                        explanation = result_data.get("explanation", "")
                        categories = result_data.get("categories", [])
                        
                        # Use update_explanation by ID... fetch first? 
                        # We know query criteria
                        questions = await repo.questions.get_questions_by_criteria(subject, year, session)
                        target_q = next((q for q in questions if q.q_number == q_number), None)
                        if target_q:
                            await repo.questions.update_explanation(target_q.id, explanation)
                            if categories:
                                await repo.questions.update_categories(target_q.id, categories)
                            await msg.edit_text(f"{msg.text}\n✅ Пояснення та категорії збережено!")
                    except Exception as ex:
                        logger.error(f"Gen Error: {ex}")
                        await msg.edit_text(f"{msg.text}\n❌ Помилка генерації: {ex}")

                asyncio.create_task(generate_single())

        except Exception as e:
            await message.reply(f"❌ Помилка: {e}")

async def on_toggle_expl(c: Any, b: Button, dm: DialogManager):
    current = dm.dialog_data.get("show_expl", False)
    dm.dialog_data["show_expl"] = not current

async def on_toggle_view(c: Any, b: Button, dm: DialogManager):
    current = dm.dialog_data.get("force_image", False)
    dm.dialog_data["force_image"] = not current

async def on_toggle_cats(c: Any, b: Button, dm: DialogManager):
    current = dm.dialog_data.get("show_cats", False)
    dm.dialog_data["show_cats"] = not current

async def on_regenerate_explanation(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    config = dm.middleware_data.get("config")
    q_id = dm.dialog_data.get("admin_q_id")
    
    # Check DB key first
    db_key = await repo.settings.get_setting("gemini_api_key")
    api_key = db_key or config.misc.gemini_api_key
    
    if not api_key:
        await c.answer("❌ API Key не знайдено!", show_alert=True)
        return

    question = await repo.questions.get_question_by_id(q_id)
    if not question or not question.image_file_id:
        await c.answer("❌ Питання не має фото.", show_alert=True)
        return

    await c.message.answer("⏳ Генерація пояснення запущена...")
    
    # Background generation (duplicate logic, could be refactored)
    from tgbot.services.gemini import GeminiService
    import asyncio
    
    async def generate_in_bg(bot, file_id, q_id, q_text):  # Changed q_text to be caption
        try:
            # We need to fetch the question again inside this scope (or assume q_id is valid)
            # Actually we need all images. 
            # We can't easily access repo inside this bg function cleanly if we don't pass it or context.
            # But we passed `repo` in outer scope? Handlers are async, `repo` variable from outer scope might be stale or session closed?
            # Actually middleware repo is per-request session. It WILL be closed when handler finishes. 
            # So we CANNOT use `repo` here. We must create new session or use what we have? 
            # In aiogram, background task should create its own session.
            # BUT for simplicity, let's download images in the main handler (before background) if possible?
            # NO, downloading takes time.
            # Better approach: Pass the list of file_ids to generate_in_bg.
            pass
        except Exception:
            pass

    # Fetch all file_ids first
    images_list = question.images or []
    if not images_list and question.image_file_id:
        images_list = [question.image_file_id]
        
    async def generate_in_bg_safe(bot, image_ids, q_id, q_text, config_key, subject):
        try:
            images_data = []
            for img_id in image_ids:
                f = await bot.get_file(img_id)
                fb = await bot.download_file(f.file_path)
                images_data.append(fb.read())

            service = GeminiService(config_key)
            result_data = await service.generate_explanation(images_data, q_text, subject=subject)
            text = result_data.get("explanation", "")
            cats = result_data.get("categories", [])

            # Use session_pool attached to the bot instance (set at startup in bot.py)
            async with bot.session_pool() as session:
                stmt = select(Question).where(Question.id == q_id)
                res = await session.execute(stmt)
                q = res.scalar_one_or_none()
                if q:
                    q.explanation = text
                    if cats:
                        q.categories = cats
                    await session.commit()

            await bot.send_message(c.from_user.id, f"✅ Пояснення та категорії оновлено для Q#{question.q_number}!")

        except Exception as ex:
            logger.error(f"Regen Error: {ex}")
            await bot.send_message(c.from_user.id, f"❌ Помилка генерації для Q#{question.q_number}")

    bot = dm.middleware_data.get("bot")
    context_text = f"Subject: {question.subject}, Type: {question.q_type}"
    # Use api_key resolved above
    asyncio.create_task(generate_in_bg_safe(bot, images_list, q_id, context_text, api_key, question.subject))


async def on_material_subject_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    dm.dialog_data["material_subject"] = item_id
    await dm.switch_to(AdminSG.materials_upload)

async def on_material_photo_upload(message: Message, widget: Any, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    subject = dm.dialog_data.get("material_subject")
    
    file_id = message.photo[-1].file_id if message.photo else None
    if not file_id:
        await message.reply("❌ Надішліть фото!")
        return

    material = await repo.materials.get_by_subject(subject)
    images = material.images if material else []
    
    if file_id not in images:
        images.append(file_id)
        await repo.materials.update_materials(subject, images)
        await message.reply(f"✅ Фото додано! Всього: {len(images)}")
    else:
        await message.reply("⚠️ Це фото вже є в матеріалах.")

async def on_clear_materials(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    subject = dm.dialog_data.get("material_subject")
    
    await repo.materials.clear_materials(subject)
    await c.answer("✅ Всі матеріали для предмету видалено.")

async def on_toggle_daily(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    current_str = await repo.settings.get_setting("daily_enabled", "true")
    new_val = "false" if current_str.lower() == "true" else "true"
    await repo.settings.set_setting("daily_enabled", new_val)
    # Refresh window
    # Auto refresh happens on state change or manually if needed? 
    # Aiogram dialog refreshes automatically on event.

async def on_force_daily(c: Any, b: Button, dm: DialogManager):
    bot = dm.middleware_data.get("bot")
    repo: RequestsRepo = dm.middleware_data.get("repo")
    
    # We need to import the service function
    from tgbot.services.daily import broadcast_daily_question
    
    # We can pass session_pool if available, but broadcast uses session_pool.
    # We can get session_pool from bot if we attached it, or config.
    # It is attached in bot.py: bot.session_pool = session_pool
    
    await c.answer("⏳ Запускаю розсилку...", show_alert=True)
    asyncio.create_task(broadcast_daily_question(bot, bot.session_pool))
    
    # Ideally should we wait? No, user wants control "Trigger Now".


async def get_maintenance_status(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    m_mode = await repo.settings.get_setting("maintenance_mode", "false")
    is_active = m_mode.lower() == "true"
    
    msg = await repo.settings.get_setting("maintenance_message")
    if not msg:
        msg = "⛔️ <b>Вибачте, в нас технічні роботи в боті.</b>\nНайближчим часом запустимо бота з оновленнями!"
        
    return {
        "is_active": is_active,
        "status_text": "АКТИВНО" if is_active else "ВИМКНЕНО",
        "status_emoji": "🚨" if is_active else "✅",
        "current_msg": msg
    }

async def on_update_gemini_key(message: Message, widget: Any, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    new_key = message.text.strip()
    if new_key:
        await repo.settings.set_setting("gemini_api_key", new_key)
        await message.reply("✅ Gemini API Key оновлено!")
    else:
        await message.reply("❌ Ключ не може бути пустим.")

async def on_delete_gemini_key(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    # Delete by setting empty or removing row?
    # SettingsRepo "set_setting" is upsert. Let's just set empty string or introduce delete method.
    # Simple way: set to ""
    await repo.settings.set_setting("gemini_api_key", "")
    await c.answer("✅ Ключ видалено з бази (використовується Config, якщо є).")

async def on_toggle_maintenance(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")
    
    # Check current status
    m_mode = await repo.settings.get_setting("maintenance_mode", "false")
    is_active = m_mode.lower() == "true"
    
    if is_active:
        # Turning OFF -> Go to Finish/Changelog input
        await dm.switch_to(AdminSG.maintenance_finish)
    else:
        # Turning ON
        await dm.switch_to(AdminSG.maintenance_confirm)

async def on_finish_maintenance(message: Message, widget: Any, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")
    
    # 1. Disable Maintenance
    await repo.settings.set_setting("maintenance_mode", "false")
    
    # 2. Prepare Broadcast
    changelog = message.text.strip() if message.text else ""
    
    text_to_send = "✅ <b>Технічні роботи завершено!</b>\n"
    if changelog:
        text_to_send += f"\n📣 <b>Що нового:</b>\n{changelog}"
    else:
        text_to_send += "\nБот повертається до роботи. Дякуємо за очікування!"

    # 3. Add Main Menu Button
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data="start_menu")]
    ])
    
    # Delete admin's input message to keep the dialog clean
    try:
        await message.delete()
    except Exception:
        pass
    
    from tgbot.services.broadcaster import broadcast
    users = await repo.users.get_users_for_broadcast("all")
    count = await broadcast(bot, users, text_to_send, reply_markup=kb)
    
    await message.answer(f"✅ Технічні роботи вимкнено! Сповіщено {count} користувачів.")
    await dm.switch_to(AdminSG.maintenance)

async def on_finish_skip(c: Any, b: Button, dm: DialogManager):
    # Same as above but without custom text
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")
    
    await repo.settings.set_setting("maintenance_mode", "false")
    
    text_to_send = "✅ <b>Технічні роботи завершено!</b>\n\nБот повертається до роботи. Дякуємо за очікування!"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data="start_menu")]
    ])
    
    await c.message.answer("✅ Роботи завершено! Розсилаю сповіщення...")
    
    from tgbot.services.broadcaster import broadcast
    users = await repo.users.get_users_for_broadcast("all")
    
    await broadcast(bot, users, text_to_send, reply_markup=kb)
    
    await c.message.answer(f"📢 Сповіщено користувачів.")
    await dm.switch_to(AdminSG.maintenance)

async def on_enable_maintenance_confirm(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    bot = dm.middleware_data.get("bot")
    
    # Get message (custom or default)
    # If custom input was provided, it should be in dialog_data or we check input?
    # Actually let's use the one in DB. If user wants custom, they edit it first.
    # OR we allow input in the confirm window?
    # Simple flow: Input message in maintenance window (optional), then click Activate.
    
    msg = await repo.settings.get_setting("maintenance_message")
    if not msg:
        msg = "⛔️ <b>Вибачте, в нас технічні роботи в боті.</b>\nНайближчим часом запустимо бота з оновленнями!"
    
    # 1. Enable Mode
    await repo.settings.set_setting("maintenance_mode", "true")
    
    # 2. Broadcast Warning
    await c.message.answer("⏳ Активую режим та розсилаю попередження...")
    
    # Import broadcast
    from tgbot.services.broadcaster import broadcast
    users = await repo.users.get_users_for_broadcast("all") # active last 7 days + active today + etc? Usually ALL for maintenance.
    # repo.users.get_users_for_broadcast("all") is now filtering 7 days.
    # Maintenance warning should probably go to EVERYONE? Or at least active. 
    # Let's stick to "all" (7 days) to avoid spamming dead users.
    
    count = await broadcast(bot, users, msg)
    
    await c.message.answer(f"🚨 Технічні роботи АКТИВОВАНО!\n📢 Сповіщено: {count} користувачів.")
    await dm.switch_to(AdminSG.maintenance)

async def on_update_maintenance_msg(message: Message, widget: Any, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    new_text = message.text or message.caption
    if new_text:
        await repo.settings.set_setting("maintenance_message", new_text)
        await message.reply("✅ Повідомлення оновлено!")
        # Stay in window
    else:
        await message.reply("❌ Надішліть текст.")

async def on_bulk_upload(message: Message, widget: Any, dm: DialogManager):
    bot = dm.middleware_data.get("bot")
    repo = dm.middleware_data.get("repo")
    config = dm.middleware_data.get("config")
    
    if not message.document or not message.document.file_name.endswith(".zip"):
        await message.reply("❌ Будь ласка, надішліть ZIP-архів.")
        return

    from tgbot.services.bulk_upload import BulkUploadService
    service = BulkUploadService(bot, repo, config)
    
    file_info = await bot.get_file(message.document.file_id)
    zip_bytes = await bot.download_file(file_info.file_path)
    
    # Run in background to avoid blocking the dialog
    asyncio.create_task(service.process_zip(zip_bytes.read(), message.from_user.id))
    await message.reply("🚀 ZIP отримано! Починаю обробку у фоновому режимі...")
    await dm.switch_to(AdminSG.menu)


# --- Windows ---

async def on_export_logs(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    
    # helper for CSV generation
    import io
    import csv
    from aiogram.types import BufferedInputFile

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
            log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else ""
        ])
    
    output.seek(0)
    file_data = output.getvalue().encode('utf-8')
    
    filename = f"user_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    doc = BufferedInputFile(file_data, filename=filename)
    
    await c.message.answer_document(doc, caption="📂 User Action Logs")

async def on_export_stats(c: Any, b: Button, dm: DialogManager):
    repo: RequestsRepo = dm.middleware_data.get("repo")
    results = await repo.results.get_all_results_for_export()
    
    if not results:
        await c.answer("❌ Немає даних для експорту.", show_alert=True)
        return

    import csv
    import io
    from aiogram.types import BufferedInputFile

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(["User ID", "Subject", "Date", "Year", "Session", "Raw Score", "NMT Score", "Duration (sec)"])
    
    # Data
    for r in results:
        writer.writerow([
            r.user_id,
            r.subject,
            r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            r.year,
            r.session,
            r.raw_score,
            r.nmt_score,
            r.duration
        ])
    
    output.seek(0)
    # Convert to bytes
    file_data = output.getvalue().encode("utf-8")
    
    filename = f"nmt_stats_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    document = BufferedInputFile(file_data, filename=filename)
    
    await c.message.answer_document(document, caption="📊 Ваша статистика готова!")


# --- Windows ---

from aiogram_dialog.widgets.media import DynamicMedia

admin_dialog = Dialog(
    Window(
        Const("🛠 <b>Адмін-панель</b>"),
        Column(
            Button(Const("📊 Статистика бота"), id="btn_stats", on_click=lambda c,b,d: d.switch_to(AdminSG.stats)),
            Button(Const("📚 Керування контентом"), id="btn_content", on_click=lambda c,b,d: d.switch_to(AdminSG.subjects)),
            Button(Const("🛡 Керування адмінами"), id="btn_admins", on_click=lambda c,b,d: d.switch_to(AdminSG.manage_admins)),
            Button(Const("📢 Розсилка"), id="btn_broadcast", on_click=lambda c,b,d: d.start(BroadcastSG.target)),
            Button(Const("🔥 Daily Challenge"), id="btn_daily", on_click=lambda c,b,d: d.switch_to(AdminSG.daily_settings)),
            Button(Const("📚 Довідкові матеріали"), id="btn_materials", on_click=lambda c,b,d: d.switch_to(AdminSG.materials_subjects)),
            Button(Const("📦 Масове завантаження (ZIP)"), id="btn_bulk", on_click=lambda c,b,d: d.switch_to(AdminSG.bulk_upload)),
            Button(Const("🚧 Технічні роботи"), id="btn_maint", on_click=lambda d,b,dm: dm.switch_to(AdminSG.maintenance)),
            Button(Const("⚙️ Налаштування"), id="btn_settings", on_click=lambda c,b,d: d.switch_to(AdminSG.settings)),
        ),
        Cancel(Const("🏠 Вихід")),
        state=AdminSG.menu,
    ),
    Window(
        Format("📊 <b>Статистика бота</b>\n\n"
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
               "📚 <b>Контент (Питань):</b>\n{content_stats}"),
        Row(
            Button(Const("🔄 Оновити"), id="btn_refresh_stats"),
            Button(Const("📥 Експорт CSV"), id="btn_export_stats", on_click=on_export_stats),
        ),
        Back(Const("🔙 Назад")),
        state=AdminSG.stats,
        getter=get_admin_dashboard
    ),
    Window(
        Const("🛡 <b>Список адміністраторів:</b>\n<i>(Натисніть на ID, щоб видалити)</i>"),
        Column(
            Select(Format("👤 {item[0]}"), id="rem_admin", item_id_getter=lambda x: x[1], items="admins", on_click=on_demote_admin),
        ),
        Const("\n➕ <b>Щоб додати адміна, надішліть його Telegram ID:</b>"),
        MessageInput(on_add_admin, content_types=[ContentType.TEXT]),
        Button(Const("🔙 Назад"), id="back_menu", on_click=lambda c,b,d: d.switch_to(AdminSG.menu)),
        state=AdminSG.manage_admins,
        getter=get_admins_list,
    ),
    Window(
        Const("🛠 <b>Обери предмет для редагування</b>"),
        Column(
            Select(Format("{item[0]}"), id="s_subj", item_id_getter=lambda x: x[1], items="subjects", on_click=on_subject_selected),
        ),
        Button(Const("➕ Додати нове питання"), id="btn_new", on_click=lambda c,b,d: d.switch_to(AdminSG.upload_new)),
        Button(Const("🔙 Назад"), id="back_menu", on_click=lambda c,b,d: d.switch_to(AdminSG.menu)),
        state=AdminSG.subjects,
        getter=get_admin_subjects,
    ),
    Window(
        Format("🛠 <b>{subject}: Обери рік</b>"),
        Group(
            Select(Format("{item[0]}"), id="s_year", item_id_getter=lambda x: x[1], items="years", on_click=on_year_selected),
            width=3
        ),
        Button(Const("🔙 Назад"), id="back_subj", on_click=lambda c,b,d: d.switch_to(AdminSG.subjects)),
        state=AdminSG.years,
        getter=get_admin_years,
    ),
    Window(
        Format("🛠 <b>{subject} {year}: Обери сесію</b>"),
        Column(
            Select(Format("{item[0]}"), id="s_sess", item_id_getter=lambda x: x[1], items="sessions", on_click=on_session_selected),
        ),
        Button(Const("🔙 Назад"), id="back_year", on_click=lambda c,b,d: d.switch_to(AdminSG.years)),
        state=AdminSG.sessions,
        getter=get_admin_sessions,
    ),
    Window(
        Format("🛠 <b>{subject} {year} {session}: Питання</b>"),
        Group(
            Select(Format("{item[0]}"), id="s_qs", item_id_getter=lambda x: x[1], items="questions", on_click=on_question_selected),
            width=4
        ),
        Group(
            Button(Const("📅 Змінити рік"), id="btn_edit_year", on_click=lambda c,b,d: d.switch_to(AdminSG.edit_session_year)),
            Button(Const("✏️ Перейменувати"), id="btn_edit_name", on_click=lambda c,b,d: d.switch_to(AdminSG.edit_session_name)),
            Button(Const("🗑 Видалити сесію"), id="btn_del_sess", on_click=lambda c,b,d: d.switch_to(AdminSG.delete_session_confirm)),
            width=2
        ),
        Button(Const("🔙 Назад"), id="back_sess", on_click=lambda c,b,d: d.switch_to(AdminSG.sessions)),
        state=AdminSG.questions,
        getter=get_admin_questions,
    ),
    Window(
        DynamicMedia("image", when="show_image"),
        Format("<b>Питання #{q.q_number}</b>\nТип: {q.q_type}\nВідповідь: <code>{ans_text}</code>", when="q"),
        
        # Categories Section
        Format("\n📂 <b>Категорії:</b>\n{categories_text}", when="show_cats"),

        # Explanation Section
        Format("\n💡 <b>Пояснення:</b>\n{explanation_safe}", when="show_expl"),
        
        Button(Const("🖼 Показати фото (обрізати текст)"), id="tgl_img", on_click=on_toggle_view, when=F["show_expl"] & ~F["show_image"] & F["is_long_text"] & ~F["is_album"]),
        Button(Const("📝 Показати текст (сховати фото)"), id="tgl_txt", on_click=on_toggle_view, when=F["show_expl"] & F["show_image"] & F["is_long_text"] & ~F["is_album"]),
        
        # Toggles Row
        Row(
            Button(Const("💡 Пояснення"), id="tgl_expl", on_click=on_toggle_expl, when="has_expl"),
            Button(Const("📂 Категорії"), id="tgl_cats", on_click=on_toggle_cats, when="has_cats"),
        ),

        Button(Const("🔙 Назад"), id="back_qs", on_click=on_back_from_detail),
        Row(
            Button(Const("🗑 Видалити"), id="btn_del", on_click=on_delete_q, when="q"),
            Button(Const("📝 Редагувати"), id="btn_edit", on_click=on_edit_q, when="q"),
        ),
        Button(Const("🔄 Згенерувати пояснення"), id="btn_regen", on_click=on_regenerate_explanation, when="q"),
        state=AdminSG.question_detail,
        getter=get_question_detail,
    ),
    Window(
        Const(
            "📸 <b>Надішліть фото завдання з підписом:</b>\n\n"
            "<code>subject | year | session | number | type | options | answer</code>\n\n"
            "📌 <b>Як заповнювати:</b>\n"
            "🔹 <b>Предмет:</b> math, hist, mova, eng, physics\n"
            "🔹 <b>Тип:</b> choice (вибір), match (відповідність), short (коротка)\n"
            "🔹 <b>Опції:</b> choice (кількість, 5), match (розмір, 3x5), short (-)\n"
            "🔹 <b>Відповідь (УКР літери):</b>\n"
            "   - Choice: А, Б, В...\n"
            "   - Short: 4.5 або 4,5\n"
            "   - Match: 1А 2Б 3В\n\n"
            "📋 <b>Приклади (копіюйте):</b>\n\n"
            "🔸 <b>Вибір (Choice):</b>\n"
            "<code>physics | 2024 | main | 1 | choice | 5 | А</code>\n\n"
            "🔸 <b>Відповідність (Match):</b>\n"
            "<code>physics | 2024 | main | 2 | match | 3x5 | 1А 2Б 3Д</code>\n\n"
            "🔸 <b>Коротка (Short):</b>\n"
            "<code>physics | 2024 | main | 3 | short | - | 4,5</code>"
        ),
        MessageInput(on_upload_photo, content_types=[ContentType.PHOTO]),
        # Since we can jump here from different places (AdminSG.subjects or AdminSG.question_detail),
        # standard Back() might not work as expected because aiogram-dialog stack logic depends on how we got here.
        # But let's try explicit Cancel to subjects if we came from there, or Back.
        # Ideally, we should know where we came from. For now, let's just route to Subjects as a safe fallback for "Back/Cancel".
        Cancel(Const("🔙 Назад (до предметів)")), 
        state=AdminSG.upload_new,
    ),
    Window(
        Format("⚙️ <b>Налаштування бота</b>\n\n"
               "🎥 <b>Відео-онбординг:</b>\n"
               "<code>{video_id}</code>\n\n"
               "👥 <b>Запитів у канал:</b> <code>{pending_count}</code>"),
        Column(
            Button(Const("🎥 Змінити відео"), id="btn_edit_vid", on_click=lambda c,b,d: d.switch_to(AdminSG.update_video)),
            Button(Format("👥 Прийняти всіх ({pending_count})"), id="btn_app_all", on_click=lambda c,b,d: d.switch_to(AdminSG.approve_confirm_1)),
            Button(Const("🔑 Gemini API Key"), id="btn_gemini", on_click=lambda c,b,d: d.switch_to(AdminSG.gemini_settings)),
        ),
        Button(Const("🔙 Назад"), id="back_menu", on_click=lambda c,b,d: d.switch_to(AdminSG.menu)),
        state=AdminSG.settings,
        getter=get_admin_settings,
    ),
    Window(
        Format("🔑 <b>Gemini API Key Settings</b>\n\n"
               "Статус: <b>{has_key}</b>\n"
               "Джерело: <b>{source}</b>\n"
               "Поточний (початок/кінець): <code>{key_preview}</code>\n\n"
               "👇 <b>Надішліть новий ключ сюди, щоб оновити/встановити.</b>"),
        Button(Const("🗑 Видалити ключ з БД"), id="del_key", on_click=on_delete_gemini_key, when="has_key"),
        Button(Const("🔙 Назад"), id="back_settings", on_click=lambda c,b,d: d.switch_to(AdminSG.settings)),
        MessageInput(on_update_gemini_key, content_types=[ContentType.TEXT]),
        state=AdminSG.gemini_settings,
        getter=get_gemini_settings,
    ),
    Window(
        Const("⚠️ <b>Ви впевнені?</b>\nВи збираєтеся прийняти ВСІХ користувачів у канал."),
        Button(Const("✅ Так, я впевнений"), id="conf_1", on_click=lambda c,b,d: d.switch_to(AdminSG.approve_confirm_2)),
        Button(Const("🔙 Скасувати"), id="back_set", on_click=lambda c,b,d: d.switch_to(AdminSG.settings)),
        state=AdminSG.approve_confirm_1,
    ),
    Window(
        Const("🛑 <b>ОСТАННЄ ПОПЕРЕДЖЕННЯ!</b>\nЦя дія незворотна. Продовжити?"),
        Button(Const("🚀 ПРИЙНЯТИ ВСІХ"), id="conf_2", on_click=on_approve_all),
        Button(Const("🔙 Скасувати"), id="back_set", on_click=lambda c,b,d: d.switch_to(AdminSG.settings)),
        state=AdminSG.approve_confirm_2,
    ),
    Window(
        Const("✏️ <b>Надішліть відео, GIF або ID для онбордингу</b>"),
        MessageInput(on_update_video, content_types=[ContentType.VIDEO, ContentType.ANIMATION, ContentType.TEXT]),
        Button(Const("🔙 Назад"), id="back_set", on_click=lambda c,b,d: d.switch_to(AdminSG.settings)),
        state=AdminSG.update_video,
    ),
    Window(
        Const("<b>📅 Daily Challenge Settings</b>\n"),
        Format("Статус розсилки: <b>{status_text} {status_emoji}</b>"),
        Format("Результат лотереї сьогодні: <b>{lottery_info}</b>\n"),
        Const("<i>Порада: розсилка відбувається з імовірністю 50% щодня у випадковий час.</i>"),
        Column(
            Button(Const("✅ Увімкнути"), id="daily_on", on_click=on_toggle_daily, when=~F["is_enabled"]),
            Button(Const("❌ Вимкнути"), id="daily_off", on_click=on_toggle_daily, when=F["is_enabled"]),
            Button(Const("🚀 Надіслати зараз (Force)"), id="daily_force", on_click=on_force_daily),
            Back(Const("⬅️ Назад")),
        ),
        state=AdminSG.daily_settings,
        getter=get_daily_status
    ),
    Window(
        Format("🚧 <b>Технічні роботи</b>\n\n"
               "Статус: {status_emoji} <b>{status_text}</b>\n\n"
               "📢 <b>Повідомлення для користувачів:</b>\n"
               "<i>{current_msg}</i>\n\n"
               "👇 Щоб змінити повідомлення, просто надішліть новий текст сюди."),
        Column(
            Button(Const("🚨 УВІМКНУТИ (Розіслати)"), id="btn_enable_m", on_click=on_toggle_maintenance, when=~F["is_active"]),
            Button(Const("✅ ВИМКНУТИ (Завершити)"), id="btn_disable_m", on_click=on_toggle_maintenance, when=F["is_active"]),
        ),
        MessageInput(on_update_maintenance_msg, content_types=[ContentType.TEXT]),
        Button(Const("🔙 Назад"), id="back_menu", on_click=lambda c,b,d: d.switch_to(AdminSG.menu)),
        state=AdminSG.maintenance,
        getter=get_maintenance_status
    ),
    Window(
        Const("⚠️ <b>Підтвердження активації</b>\n\n"
              "1. Бот перейде в режим технічних робіт.\n"
              "2. Користувачі (крім адмінів) втратять доступ.\n"
              "3. <b>Усім активним користувачам буде надіслано поточне повідомлення!</b>\n\n"
              "Ви впевнені?"),
        Button(Const("🚀 ТАК, АКТИВУВАТИ"), id="confirm_m", on_click=on_enable_maintenance_confirm),
        Button(Const("🔙 Скасувати"), id="cancel_m", on_click=lambda c,b,d: d.switch_to(AdminSG.maintenance)),
        state=AdminSG.maintenance_confirm,
    ),
    Window(
        Const("📢 <b>Завершення робіт</b>\n\n"
              "Надішліть повідомлення про оновлення (ChangeLog).\n"
              "Воно буде надіслано всім користувачам разом з кнопкою «Головне меню».\n\n"
              "<i>Або натисніть «Пропустити», щоб надіслати стандартне повідомлення.</i>"),
        MessageInput(on_finish_maintenance, content_types=[ContentType.TEXT]),
        Button(Const("⏩ Пропустити (Стандартне)"), id="skip_fin", on_click=on_finish_skip),
        Button(Const("🔙 Скасувати"), id="cancel_fin", on_click=lambda c,b,d: d.switch_to(AdminSG.maintenance)),
        state=AdminSG.maintenance_finish
    ),
    Window(
        Const("📚 <b>Обери предмет для довідкових матеріалів</b>"),
        Column(
            Select(Format("{item[0]}"), id="m_subj", item_id_getter=lambda x: x[1], items="subjects", on_click=on_material_subject_selected),
        ),
        Button(Const("🔙 Назад"), id="back_menu", on_click=lambda c,b,d: d.switch_to(AdminSG.menu)),
        state=AdminSG.materials_subjects,
        getter=get_admin_subjects,
    ),
    Window(
        Format("📚 <b>Довідкові матеріали: {subject_label}</b>\n\n"
               "Завантажено фото: <b>{count}</b>\n\n"
               "👇 <b>Щоб додати фото, просто надішліть його сюди.</b>\n"
               "Можна надсилати по одному або декілька (як альбом)."),
        Button(Const("🧹 Очистити всі матеріали"), id="clear_m", on_click=on_clear_materials, when="has_images"),
        Button(Const("🔙 Назад до предметів"), id="back_m_subj", on_click=lambda c,b,d: d.switch_to(AdminSG.materials_subjects)),
        MessageInput(on_material_photo_upload, content_types=[ContentType.PHOTO]),
        state=AdminSG.materials_upload,
        getter=get_material_upload_data,
    ),
    Window(
        Const("📦 <b>Масове завантаження (ZIP)</b>\n\n"
              "Надішліть ZIP-архів з <code>questions.csv</code> (рекомендовано) або <code>questions.json</code> та фото.\n\n"
              "📊 <b>Порядок колонок CSV:</b>\n"
              "<code>subject, year, session, q_number, q_type, answer, images</code>\n\n"
              "✅ <b>Підтримувані предмети:</b>\n"
              "<code>math, hist, mova, eng, physics</code>\n\n"
              "📂 <b>Вимоги до ZIP:</b>\n"
              "1. Файл <code>questions.csv</code> в корені.\n"
              "2. Назви фото мають збігатися з колонкою images.\n\n"
              "👇 <b>Надішліть ZIP-файл сюди для обробки.</b>"),
        MessageInput(on_bulk_upload, content_types=[ContentType.DOCUMENT]),
        Button(Const("🔙 Назад"), id="back_menu", on_click=lambda c,b,d: d.switch_to(AdminSG.menu)),
        state=AdminSG.bulk_upload,
    ),
    Window(
        Format("⚠️ <b>ВИДАЛЕННЯ СЕСІЇ</b>\n\n"
               "Ви впевнені, що хочете видалити ВСІ питання сесії:\n"
               "📚 Предмет: <code>{subject}</code>\n"
               "📅 Рік: <code>{year}</code>\n"
               "📂 Сесія: <code>{session}</code>\n\n"
               "❗ Цю дію неможливо скасувати!"),
        Row(
            Button(Const("❌ ТАК, ВИДАЛИТИ"), id="btn_confirm_del", on_click=on_confirm_delete_session),
            Button(Const("🚫 Скасувати"), id="btn_cancel_del", on_click=lambda c,b,d: d.switch_to(AdminSG.questions)),
        ),
        state=AdminSG.delete_session_confirm,
        getter=get_admin_questions, # Reusing getter to have subject/year/session labels
    ),
    Window(
        Format("📅 <b>ЗМІНА РОКУ</b>\n\n"
               "📚 Предмет: <code>{subject}</code>\n"
               "📂 Сесія: <code>{session}</code>\n\n"
               "Поточний рік: <b>{year}</b>\n\n"
               "✍️ Надішліть новий рік:"),
        TextInput(id="inp_new_year", on_success=on_change_session_year),
        Button(Const("🔙 Скасувати"), id="back_from_year", on_click=lambda c,b,d: d.switch_to(AdminSG.questions)),
        state=AdminSG.edit_session_year,
        getter=get_admin_questions,
    ),
    Window(
        Format("✏️ <b>ПЕРЕЙМЕНУВАННЯ СЕСІЇ</b>\n\n"
               "📚 Предмет: <code>{subject}</code>\n"
               "📅 Рік: <b>{year}</b>\n\n"
               "Поточна назва: <code>{session}</code>\n\n"
               "✍️ Надішліть нову назву для сесії:"),
        TextInput(id="inp_new_name", on_success=on_change_session_name),
        Button(Const("🔙 Скасувати"), id="back_from_name", on_click=lambda c,b,d: d.switch_to(AdminSG.questions)),
        state=AdminSG.edit_session_name,
        getter=get_admin_questions,
    ),
)
