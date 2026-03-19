import asyncio
import logging
import sys
import os
import io

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aiogram import Bot
from sqlalchemy import select, update
from google import genai
from google.genai import types

from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Silence SDK noise
logging.getLogger("google.genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

async def main():
    config = load_config(".env")
    
    # 1. Setup Infrastructure
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    bot = Bot(token=config.tg_bot.token)
    
    # 2. Setup Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ GEMINI_API_KEY is missing in environment variables!")
        return

    client = genai.Client(api_key=api_key)

    # 3. Fetch Questions to Audit
    target_subject = "hist"
    
    # Limit concurrency strictly to 2 workers
    semaphore = asyncio.Semaphore(2)
    
    async def process_one(q_id, subject, q_num, img_id, year, session_name, session_pool):
        async with semaphore:
            async with session_pool() as session:
                stmt = select(Question).where(Question.id == q_id)
                res = await session.execute(stmt)
                q = res.scalar_one_or_none()
                if not q: return

                try:
                    # 4. Download Image
                    file_io = io.BytesIO()
                    try:
                        file_info = await bot.get_file(img_id)
                        await bot.download_file(file_info.file_path, destination=file_io)
                        file_bytes = file_io.getvalue()
                    except Exception as e:
                        logger.error(f"❌ Failed to download image for Q#{q_num}: {e}")
                        return

                    # 5. Ask Gemini
                    prompt = (
                        "Analyze NMT History exam question.\n"
                        "Output ONLY one line in this format:\n"
                        "subject | year | session | number | type | options | answer\n\n"
                        "Rules for answer field:\n"
                        "- choice: ONE Ukrainian letter (А, Б, В, Г or Д)\n"
                        "- match: Pairs separated by SPACE like '1А 2Б 3В 4Г'.\n"
                        "- short: Digit sequence (e.g. 123) or single number. No spaces, no commas unless decimal.\n"
                        f"Context: Subject={subject}, Year={year}, Session={session_name}, Number={q_num}\n"
                    )
                    
                    def call_gemini():
                        generate_content_config = types.GenerateContentConfig(
                            thinking_config=types.ThinkingConfig(
                                thinking_level="HIGH",
                            ),
                        )
                        
                        return client.models.generate_content(
                            model="gemini-3-flash-preview",
                            contents=[
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part.from_bytes(data=file_bytes, mime_type="image/jpeg"),
                                        types.Part.from_text(text=prompt)
                                    ]
                                )
                            ],
                            config=generate_content_config
                        )
                    
                    response = await asyncio.to_thread(call_gemini)
                    
                    if not response.text:
                        return
                        
                    line = response.text.strip().replace("```", "").split("\n")[-1].strip()
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) < 7:
                        return
                    
                    g_type = parts[4].lower()
                    if "match" in g_type: g_type = "match"
                    elif "choice" in g_type: g_type = "choice"
                    elif "short" in g_type: g_type = "short"
                    
                    g_options = parts[5].strip()
                    g_answer_str = parts[6].strip().replace(" ", "") if g_type != "match" else parts[6].strip()
                    
                    new_answer_payload = {}
                    if g_type == "choice":
                        ans = g_answer_str.upper()[:1]
                        new_answer_payload = {"answer": ans}
                    elif g_type == "match":
                        pairs = {}
                        tokens = g_answer_str.upper().split()
                        for t in tokens:
                            if len(t) >= 2:
                                 k = "".join([c for c in t if c.isdigit()])
                                 v = "".join([c for c in t if not c.isdigit()])
                                 if k and v: pairs[k] = v
                        if "x" not in g_options:
                            g_options = "4x5"
                        new_answer_payload = {"pairs": pairs, "options": g_options}
                    elif g_type == "short":
                        ans = g_answer_str.replace(",", ".")
                        new_answer_payload = {"answer": ans}
                    
                    # 6. Compare & Update
                    is_changed = False
                    old_ans = q.correct_answer
                    
                    if q.q_type == "match" and g_type == "match":
                         if old_ans.get("pairs") != new_answer_payload.get("pairs"):
                             is_changed = True
                    else:
                        old_val = str(old_ans.get("answer", "")).strip().lower().replace(",", ".")
                        new_val = str(new_answer_payload.get("answer", "")).strip().lower().replace(",", ".")
                        if old_val != new_val:
                            is_changed = True
                            
                    status = "✅ MATCH"
                    if is_changed:
                        q.correct_answer = new_answer_payload
                        q.q_type = g_type
                        if g_type == "match": q.weight = 4
                        else: q.weight = 1
                        
                        await session.commit()
                        status = "🔄 UPDATED"
                    
                    # Log row result
                    logger.info(f"{subject} | {year} | {session_name} | {q_num} | {g_type} | {g_options} | {g_answer_str} = {status}")

                except Exception as e:
                    logger.error(f"❌ Error Q#{q_num}: {e}")

    async with session_pool() as session:
        stmt = select(Question).where(Question.subject == target_subject).order_by(Question.year, Question.session, Question.q_number)
        result = await session.execute(stmt)
        questions = result.scalars().all()
        
        logger.info(f"🔍 Auditing {len(questions)} history questions (2 workers)...")
        tasks_data = [(q.id, q.subject, q.q_number, q.image_file_id, q.year, q.session) for q in questions if q.image_file_id]

    tasks = [process_one(*d, session_pool) for d in tasks_data]
    await asyncio.gather(*tasks)
    
    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
