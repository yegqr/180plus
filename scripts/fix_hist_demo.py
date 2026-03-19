import asyncio
import logging
import sys
import os
import io

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aiogram import Bot
from sqlalchemy import select
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config
from tgbot.services.gemini import GeminiService

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Official History Demo Keys
HIST_KEYS = {
    1: {"type": "choice", "ans": "В", "opt": "4"},
    2: {"type": "choice", "ans": "Г", "opt": "4"},
    3: {"type": "choice", "ans": "В", "opt": "4"},
    4: {"type": "choice", "ans": "А", "opt": "4"},
    5: {"type": "choice", "ans": "Б", "opt": "4"},
    6: {"type": "choice", "ans": "В", "opt": "4"},
    7: {"type": "choice", "ans": "Б", "opt": "4"},
    8: {"type": "choice", "ans": "Г", "opt": "4"},
    9: {"type": "choice", "ans": "А", "opt": "4"},
    10: {"type": "choice", "ans": "А", "opt": "4"},
    11: {"type": "choice", "ans": "А", "opt": "4"},
    12: {"type": "choice", "ans": "Б", "opt": "4"},
    13: {"type": "choice", "ans": "Г", "opt": "4"},
    14: {"type": "choice", "ans": "А", "opt": "4"},
    15: {"type": "choice", "ans": "Г", "opt": "4"},
    16: {"type": "choice", "ans": "Б", "opt": "4"},
    17: {"type": "choice", "ans": "А", "opt": "4"},
    18: {"type": "choice", "ans": "А", "opt": "4"},
    19: {"type": "choice", "ans": "Г", "opt": "4"},
    20: {"type": "choice", "ans": "Г", "opt": "4"},
    21: {"type": "match", "ans": {"1": "В", "2": "А", "3": "Б", "4": "Г"}, "opt": "4x5"},
    22: {"type": "match", "ans": {"1": "В", "2": "Г", "3": "А", "4": "Б"}, "opt": "4x5"},
    23: {"type": "match", "ans": {"1": "В", "2": "Д", "3": "А", "4": "Г"}, "opt": "4x5"},
    24: {"type": "match", "ans": {"1": "Г", "2": "Д", "3": "Б", "4": "В"}, "opt": "4x5"},
    25: {"type": "match", "ans": {"1": "А", "2": "Г", "3": "В", "4": "Б"}, "opt": "4x4"},
    26: {"type": "match", "ans": {"1": "Б", "2": "Г", "3": "В", "4": "А"}, "opt": "4x4"},
    27: {"type": "match", "ans": {"1": "Г", "2": "Б", "3": "А", "4": "В"}, "opt": "4x4"},
    28: {"type": "short", "ans": "124", "opt": "-"},
    29: {"type": "short", "ans": "357", "opt": "-"},
    30: {"type": "short", "ans": "124", "opt": "-"},
}

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    bot = Bot(token=config.tg_bot.token)
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ GEMINI_API_KEY is missing!")
        return

    gemini_svc = GeminiService(api_key)
    
    TARGET_SUBJECT = "hist"
    TARGET_SESSION = "Демоваріант"
    
    semaphore = asyncio.Semaphore(2)
    
    async def process_one(q_id, q_num, session_pool):
        async with semaphore:
            async with session_pool() as session:
                stmt = select(Question).where(Question.id == q_id)
                res = await session.execute(stmt)
                q = res.scalar_one_or_none()
                if not q: return

                key = HIST_KEYS.get(q_num)
                if not key:
                    logger.warning(f"No official key for Q#{q_num}")
                    return

                try:
                    # 1. Force explanation
                    images_data = []
                    image_ids = q.images or ([q.image_file_id] if q.image_file_id else [])
                    
                    if image_ids:
                        for img_id in image_ids:
                            file_io = io.BytesIO()
                            file_info = await bot.get_file(img_id)
                            await bot.download_file(file_info.file_path, destination=file_io)
                            images_data.append(file_io.getvalue())
                        
                        q_text = f"Subject: {q.subject}, Year: {q.year}, Session: {q.session}, Number: {q.q_number}"
                        q.explanation = await gemini_svc.generate_explanation(images_data, q_text)
                    
                    # 2. Set official answer
                    g_type = key["type"]
                    if g_type == "choice":
                        q.correct_answer = {"answer": key["ans"]}
                    elif g_type == "match":
                        q.correct_answer = {"pairs": key["ans"], "options": key["opt"]}
                    elif g_type == "short":
                        q.correct_answer = {"answer": key["ans"]}
                    
                    q.q_type = g_type
                    q.weight = 4 if g_type == "match" else 1
                    
                    await session.commit()
                    
                    # Format log
                    display_ans = key["ans"]
                    if g_type == "match":
                         display_ans = " ".join([f"{k}{v}" for k, v in sorted(key["ans"].items())])
                    
                    logger.info(f"hist | {q.year} | {TARGET_SESSION} | {q_num} | {g_type} | {key['opt']} | {display_ans} = ✅ UPDATED WITH OFFICIAL KEY")

                except Exception as e:
                    logger.error(f"❌ Error Q#{q_num}: {e}")

    async with session_pool() as session:
        stmt = select(Question).where(
            Question.subject == TARGET_SUBJECT, 
            Question.session == TARGET_SESSION
        ).order_by(Question.q_number)
        result = await session.execute(stmt)
        questions = result.scalars().all()
        
        logger.info(f"🚀 REBUILDING {len(questions)} history questions for 'Демоваріант' with OFFICIAL KEYS...")
        tasks = [process_one(q.id, q.q_number, session_pool) for q in questions]

    await asyncio.gather(*tasks)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
