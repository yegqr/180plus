import json
import logging
import zipfile
import io
import asyncio
from typing import List, Dict, Any
from aiogram import Bot
from aiogram.types import BufferedInputFile
from infrastructure.database.repo.requests import RequestsRepo
from tgbot.services.gemini import GeminiService
from tgbot.config import Config

logger = logging.getLogger(__name__)

class BulkUploadService:
    def __init__(self, bot: Bot, repo: RequestsRepo, config: Config):
        self.bot = bot
        self.repo = repo
        self.config = config

    async def process_zip(self, zip_bytes: bytes, admin_id: int):
        """
        Processes a ZIP archive containing questions.json and images.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                # 1. Read metadata
                data = []
                if "questions.csv" in z.namelist():
                    import csv
                    try:
                        with z.open("questions.csv") as f:
                            # Read as text
                            content = f.read().decode("utf-8-sig") # Handle BOM from Excel
                            reader = csv.DictReader(io.StringIO(content))
                            for row in reader:
                                # Data conversion
                                item = {
                                    "subject": row["subject"].strip().lower(),
                                    "year": int(row["year"]),
                                    "session": row["session"].strip(), # Can be "main" or "17 червня"
                                    "q_number": int(row["q_number"]),
                                    "q_type": row["q_type"].strip().lower(),
                                    "images": [img.strip() for img in row["images"].split(",") if img.strip()]
                                }
                                
                                options = row.get("options", "").strip()
                                
                                # Format answer
                                raw_ans = row["answer"].strip()
                                if item["q_type"] == "match":
                                    # Format: 1А; 2Б; 3В
                                    pairs = {}
                                    for part in raw_ans.split(";"):
                                        part = part.strip()
                                        if part:
                                            # Find digits and letters
                                            import re
                                            match = re.search(r"(\d+)\s*[–-]?\s*([А-Яа-яA-Za-zЄЄіІїЇґҐ]+)", part)
                                            if match:
                                                pairs[match.group(1)] = match.group(2).upper()
                                    item["correct_answer"] = {"pairs": pairs, "options": options}
                                elif item["q_type"] == "choice":
                                    item["correct_answer"] = {"answer": raw_ans.upper(), "options": options}
                                else:
                                    item["correct_answer"] = {"answer": raw_ans}
                                
                                data.append(item)
                    except Exception as e:
                        await self.bot.send_message(admin_id, f"❌ Помилка читання CSV: {e}")
                        return
                
                elif "questions.json" in z.namelist():
                    try:
                        with z.open("questions.json") as f:
                            data = json.load(f)
                    except Exception as e:
                        await self.bot.send_message(admin_id, f"❌ Помилка читання JSON: {e}")
                        return
                else:
                    await self.bot.send_message(admin_id, "❌ Помилка: У ZIP-архіві відсутній файл <code>questions.csv</code> або <code>questions.json</code>.")
                    return

                if not isinstance(data, list):
                    await self.bot.send_message(admin_id, "❌ Помилка: JSON має бути списком об'єктів.")
                    return

                await self.bot.send_message(admin_id, f"⏳ Знайдено {len(data)} питань. Починаю завантаження...")

                success_count = 0
                for item in data:
                    try:
                        # Required fields
                        subject = item["subject"]
                        year = int(item["year"])
                        session = item["session"]
                        q_number = int(item["q_number"])
                        q_type = item["q_type"]
                        correct_answer = item["correct_answer"]
                        images = item.get("images", []) # List of filenames in ZIP

                        # 2. Upload images to Telegram to get file_ids
                        file_ids = []
                        image_data_list = []
                        for img_name in images:
                            if img_name in z.namelist():
                                with z.open(img_name) as img_file:
                                    img_bytes = img_file.read()
                                    image_data_list.append(img_bytes)
                                    
                                    # We send to admin to get file_id (Telegram requires file_id for persistent storage)
                                    # Or we send to a hidden channel/logs chat if configured.
                                    # For now, send to admin (it might be spammy but safe)
                                    sent_msg = await self.bot.send_photo(
                                        chat_id=admin_id,
                                        photo=BufferedInputFile(img_bytes, filename=img_name),
                                        caption=f"📦 Uploading {img_name} for Q#{q_number}..."
                                    )
                                    file_ids.append(sent_msg.photo[-1].file_id)
                                    # Delete the temporary upload message to keep chat clean
                                    await self.bot.delete_message(admin_id, sent_msg.message_id)

                        # 3. Save to DB
                        await self.repo.questions.upsert_question(
                            subject=subject,
                            year=year,
                            session=session,
                            q_number=q_number,
                            image_file_ids=file_ids,
                            q_type=q_type,
                            correct_answer=correct_answer,
                            weight=len(correct_answer.get("pairs", {})) if q_type == "match" else 1
                        )

                        # 4. Trigger Gemini in background
                        db_key = await self.repo.settings.get_setting("gemini_api_key")
                        api_key = db_key or self.config.misc.gemini_api_key
                        
                        if api_key and image_data_list:
                            logger.info(f"Triggering Gemini for Q#{q_number} ({subject}, {year}, {session})")
                            asyncio.create_task(self.generate_and_save_explanation(
                                api_key=api_key,
                                images=image_data_list,
                                subject=subject,
                                q_type=q_type,
                                correct_answer=correct_answer,
                                q_number=q_number,
                                year=year,
                                session_name=session,
                                admin_id=admin_id
                            ))

                        success_count += 1
                        await asyncio.sleep(0.1) # Rate limiting

                    except Exception as e:
                        logger.error(f"Error processing item: {e}")
                        await self.bot.send_message(admin_id, f"⚠️ Помилка у питанні #{item.get('q_number', '?')}: {e}")

                await self.bot.send_message(admin_id, f"✅ Масове завантаження завершено! Успішно додано: {success_count}/{len(data)}")

        except Exception as e:
            logger.error(f"Bulk upload error: {e}")
            await self.bot.send_message(admin_id, f"❌ Критична помилка під час обробки ZIP: {e}")

    async def generate_and_save_explanation(self, api_key: str, images: List[bytes], subject: str, q_type: str, correct_answer: Any, q_number: int, year: int, session_name: str, admin_id: int):
        logger.info(f"Starting background explanation generation for Q#{q_number}")
        try:
            service = GeminiService(api_key)
            context = f"Subject: {subject}, Type: {q_type}, Answer: {correct_answer}"
            result = await service.generate_explanation(images, context, subject=subject)
            
            explanation = result.get("explanation", "")
            categories = result.get("categories", [])

            # We need to use a NEW session because the one in self.repo might be closed
            from infrastructure.database.setup import create_engine, create_session_pool
            engine = create_engine(self.config.db)
            session_pool = create_session_pool(engine)
            
            async with session_pool() as session:
                from infrastructure.database.repo.questions import QuestionRepo
                q_repo = QuestionRepo(session)
                
                # Fetch question id
                questions = await q_repo.get_questions_by_criteria(subject, year, session_name)
                target_q = next((q for q in questions if q.q_number == q_number), None)
                
                if target_q:
                    await q_repo.update_explanation(target_q.id, explanation)
                    if categories:
                        await q_repo.update_categories(target_q.id, categories)
                    # Optional: notify admin? (might be too much noise if 50 questions)
                    # logger.info(f"Generated explanation for Q#{q_number}")
                
        except Exception as e:
            logger.error(f"Gemini background error for Q#{q_number}: {e}")
