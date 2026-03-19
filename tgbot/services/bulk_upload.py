from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import zipfile
from typing import Any

from aiogram import Bot
from aiogram.types import BufferedInputFile

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.config import Config
from tgbot.services.gemini import GeminiService

logger = logging.getLogger(__name__)


class BulkUploadService:
    def __init__(self, bot: Bot, repo: RequestsRepo, config: Config) -> None:
        self.bot = bot
        self.repo = repo
        self.config = config
        self._gemini_sem = asyncio.Semaphore(3)  # max 3 concurrent Gemini API calls

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def process_zip(self, zip_bytes: bytes, admin_id: int) -> None:
        """Orchestrates ZIP processing: read metadata → upload images → save to DB → Gemini."""
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                data = await self._read_metadata(zf, admin_id)
                if data is None:
                    return

                await self.bot.send_message(
                    admin_id, f"⏳ Знайдено {len(data)} питань. Починаю завантаження..."
                )

                success_count = 0
                for item in data:
                    try:
                        await self._process_one(zf, item, admin_id)
                        success_count += 1
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Error processing item: {e}")
                        await self.bot.send_message(
                            admin_id,
                            f"⚠️ Помилка у питанні #{item.get('q_number', '?')}: {e}",
                        )

                await self.bot.send_message(
                    admin_id,
                    f"✅ Масове завантаження завершено! Успішно додано: {success_count}/{len(data)}",
                )

        except Exception as e:
            logger.error(f"Bulk upload error: {e}")
            await self.bot.send_message(
                admin_id, f"❌ Критична помилка під час обробки ZIP: {e}"
            )

    # ------------------------------------------------------------------
    # Step 1: read CSV or JSON metadata
    # ------------------------------------------------------------------

    async def _read_metadata(
        self, zf: zipfile.ZipFile, admin_id: int
    ) -> list[dict[str, Any]] | None:
        """Returns parsed question list or None if the ZIP is malformed."""
        names = zf.namelist()

        if "questions.csv" in names:
            try:
                return self._parse_csv(zf)
            except Exception as e:
                await self.bot.send_message(admin_id, f"❌ Помилка читання CSV: {e}")
                return None

        if "questions.json" in names:
            try:
                with zf.open("questions.json") as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    await self.bot.send_message(
                        admin_id, "❌ Помилка: JSON має бути списком об'єктів."
                    )
                    return None
                return data
            except Exception as e:
                await self.bot.send_message(admin_id, f"❌ Помилка читання JSON: {e}")
                return None

        await self.bot.send_message(
            admin_id,
            "❌ Помилка: У ZIP-архіві відсутній файл "
            "<code>questions.csv</code> або <code>questions.json</code>.",
        )
        return None

    def _parse_csv(self, zf: zipfile.ZipFile) -> list[dict[str, Any]]:
        """Parses questions.csv inside the ZIP into a list of question dicts."""
        with zf.open("questions.csv") as f:
            content = f.read().decode("utf-8-sig")  # handle Excel BOM
        reader = csv.DictReader(io.StringIO(content))
        data: list[dict[str, Any]] = []
        for row in reader:
            q_type = row["q_type"].strip().lower()
            raw_ans = row["answer"].strip()
            options = row.get("options", "").strip()

            if q_type == "match":
                pairs: dict[str, str] = {}
                for part in raw_ans.split(";"):
                    m = re.search(
                        r"(\d+)\s*[–-]?\s*([А-Яа-яA-Za-zЄЄіІїЇґҐ]+)", part.strip()
                    )
                    if m:
                        pairs[m.group(1)] = m.group(2).upper()
                correct_answer: dict = {"pairs": pairs, "options": options}
            elif q_type == "choice":
                correct_answer = {"answer": raw_ans.upper(), "options": options}
            else:
                correct_answer = {"answer": raw_ans}

            data.append(
                {
                    "subject":        row["subject"].strip().lower(),
                    "year":           int(row["year"]),
                    "session":        row["session"].strip(),
                    "q_number":       int(row["q_number"]),
                    "q_type":         q_type,
                    "correct_answer": correct_answer,
                    "images":         [
                        img.strip()
                        for img in row["images"].split(",")
                        if img.strip()
                    ],
                }
            )
        return data

    # ------------------------------------------------------------------
    # Step 2: upload images + save one question to DB
    # ------------------------------------------------------------------

    async def _process_one(
        self, zf: zipfile.ZipFile, item: dict[str, Any], admin_id: int
    ) -> None:
        """Uploads images for one question and saves it to the database."""
        subject = item["subject"]
        year = int(item["year"])
        session = item["session"]
        q_number = int(item["q_number"])
        q_type = item["q_type"]
        correct_answer = item["correct_answer"]

        file_ids, image_data_list = await self._upload_images(
            zf, item.get("images", []), admin_id, q_number
        )

        await self.repo.questions.upsert_question(
            subject=subject,
            year=year,
            session=session,
            q_number=q_number,
            image_file_ids=file_ids,
            q_type=q_type,
            correct_answer=correct_answer,
            weight=len(correct_answer.get("pairs", {})) if q_type == "match" else 1,
        )

        db_key = await self.repo.settings.get_setting("gemini_api_key")
        api_key = db_key or self.config.misc.gemini_api_key
        if api_key and image_data_list:
            asyncio.create_task(
                self._gemini_task(
                    api_key=api_key,
                    images=image_data_list,
                    subject=subject,
                    q_type=q_type,
                    correct_answer=correct_answer,
                    q_number=q_number,
                    year=year,
                    session_name=session,
                    admin_id=admin_id,
                )
            )

    async def _upload_images(
        self,
        zf: zipfile.ZipFile,
        image_names: list[str],
        admin_id: int,
        q_number: int,
    ) -> tuple[list[str], list[bytes]]:
        """Sends each image to Telegram to obtain a persistent file_id."""
        file_ids: list[str] = []
        image_data_list: list[bytes] = []
        for img_name in image_names:
            if img_name not in zf.namelist():
                continue
            with zf.open(img_name) as img_file:
                img_bytes = img_file.read()
            image_data_list.append(img_bytes)
            sent = await self.bot.send_photo(
                chat_id=admin_id,
                photo=BufferedInputFile(img_bytes, filename=img_name),
                caption=f"📦 Uploading {img_name} for Q#{q_number}...",
            )
            file_ids.append(sent.photo[-1].file_id)
            await self.bot.delete_message(admin_id, sent.message_id)
        return file_ids, image_data_list

    # ------------------------------------------------------------------
    # Background Gemini generation
    # ------------------------------------------------------------------

    async def _gemini_task(self, **kwargs: Any) -> None:
        """Wrapper that acquires the semaphore before calling Gemini."""
        async with self._gemini_sem:
            await self.generate_and_save_explanation(**kwargs)

    async def generate_and_save_explanation(
        self,
        api_key: str,
        images: list[bytes],
        subject: str,
        q_type: str,
        correct_answer: Any,
        q_number: int,
        year: int,
        session_name: str,
        admin_id: int,
    ) -> None:
        logger.info(f"Starting background explanation generation for Q#{q_number}")
        try:
            service = GeminiService(api_key)
            context = f"Subject: {subject}, Type: {q_type}, Answer: {correct_answer}"
            result = await service.generate_explanation(images, context, subject=subject)
            explanation = result.get("explanation", "")
            categories = result.get("categories", [])

            async with self.bot.session_pool() as session:
                from infrastructure.database.repo.questions import QuestionRepo
                q_repo = QuestionRepo(session)
                questions = await q_repo.get_questions_by_criteria(subject, year, session_name)
                target_q = next((q for q in questions if q.q_number == q_number), None)
                if target_q:
                    await q_repo.update_explanation(target_q.id, explanation)
                    if categories:
                        await q_repo.update_categories(target_q.id, categories)
                    await session.commit()
        except Exception as e:
            logger.error(f"Gemini background error for Q#{q_number}: {e}")
