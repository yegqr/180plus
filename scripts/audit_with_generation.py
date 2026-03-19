import asyncio
import logging
import sys
import os
import io

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aiogram import Bot
from sqlalchemy import select
from google import genai
from google.genai import types

from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config
from tgbot.services.gemini import GeminiService

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
    gemini_svc = GeminiService(api_key)

    # 3. Fetch Questions to Audit
    target_subject = "hist"
    
    # Limit concurrency strictly to 2 workers
    semaphore = asyncio.Semaphore(2)
    
    async def process_one(q_id, subject, q_num, year, session_name, session_pool):
        async with semaphore:
            async with session_pool() as session:
                stmt = select(Question).where(Question.id == q_id)
                res = await session.execute(stmt)
                q = res.scalar_one_or_none()
                if not q: return

                try:
                    # STEP 1: Ensure Explanation Exists
                    if not q.explanation or len(q.explanation.strip()) < 10:
                        # logger.info(f"⚡ Generating explanation for Q#{q_num}...")
                        
                        # Fetch images
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
                            await session.commit()
                        else:
                            logger.warning(f"⚠️ No images for Q#{q_num}, cannot generate explanation.")

                    # STEP 2: Audit from Explanation
                    if not q.explanation or "⚠️" in q.explanation:
                        return

                    prompt = (
                        "Analyze NMT exam question explanation.\n"
                        "Extract the correct answer and dimensions from the explanation text.\n"
                        "Output ONLY one line in this format:\n"
                        "subject | year | session | number | type | options | answer\n\n"
                        "Rules for answer field:\n"
                        "- choice: ONE Ukrainian letter (А, Б, В, Г or Д)\n"
                        "- match: Pairs separated by SPACE like '1А 2Б 3В 4Г'.\n"
                        "- short: Digit sequence (e.g. 123) or single number. No spaces, no commas unless decimal.\n\n"
                        "Rules for options field:\n"
                        "- choice: Number of variants (usually 5 or 4)\n"
                        "- match: Grid size (usually 4x5 or 3x5)\n"
                        "- short: -\n\n"
                        f"Context: Subject={subject}, Year={year}, Session={session_name}, Number={q_num}\n"
                        f"Explanation: {q.explanation}\n"
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
                                    parts=[types.Part.from_text(text=prompt)]
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
                    if "match" in g_type or "sequence" in g_type or "order" in g_type: 
                        g_type = "match"
                    elif "choice" in g_type: 
                        g_type = "choice"
                    elif "short" in g_type: 
                        g_type = "short"
                    
                    g_options = parts[5].strip()
                    g_answer_str = parts[6].strip()
                    
                    new_answer_payload = {}
                    if g_type == "choice":
                        ans = g_answer_str.upper().replace(" ", "")[:1]
                        new_answer_payload = {"answer": ans}
                    elif g_type == "match":
                        pairs = {}
                        clean_ans = g_answer_str.upper().replace(" ", "")
                        
                        if clean_ans.isalpha() and len(clean_ans) >= 3:
                            # It's a sequence string like БАВГ
                            for i, char in enumerate(clean_ans):
                                pairs[str(i+1)] = char
                        elif any(c.isdigit() for c in clean_ans) and any(c.isalpha() for c in clean_ans):
                            # It's something like 1А2Б3В4Г or 1А 2Б...
                            import re
                            # Find all digit+letter groups
                            found = re.findall(r'(\d+)([А-ЯA-Z])', g_answer_str.upper())
                            if found:
                                for k, v in found:
                                    pairs[k] = v
                            else:
                                # Fallback to tokens
                                tokens = g_answer_str.upper().split()
                                for t in tokens:
                                    if len(t) >= 2:
                                         k = "".join([c for c in t if c.isdigit()])
                                         v = "".join([c for c in t if not c.isdigit()])
                                         if k and v: pairs[k] = v
                        
                        if "x" not in g_options:
                            # Sequence is usually 4x4, match is 4x5
                            g_options = "4x4" if len(pairs) == 4 and "sequence" in parts[4].lower() else "4x5"
                        
                        new_answer_payload = {"pairs": pairs, "options": g_options}
                    elif g_type == "short":
                        ans = g_answer_str.replace(",", ".")
                        new_answer_payload = {"answer": ans}
                    
                    # 6. Compare & Update
                    is_changed = False
                    old_ans = q.correct_answer
                    
                    if not old_ans:
                        is_changed = True
                    elif q.q_type != g_type:
                        is_changed = True
                    elif g_type == "match":
                         if old_ans.get("pairs") != new_answer_payload.get("pairs") or old_ans.get("options") != new_answer_payload.get("options"):
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
                    
                    # Standardized log string for both match/seq
                    display_ans = g_answer_str
                    if g_type == "match":
                        # Sort and format as 1А 2Б 3В
                        sorted_pairs = sorted(new_answer_payload.get("pairs", {}).items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
                        display_ans = " ".join([f"{k}{v}" for k, v in sorted_pairs])

                    # Log result
                    logger.info(f"{subject} | {year} | {session_name} | {q_num} | {g_type} | {g_options} | {display_ans} = {status}")

                except Exception as e:
                    logger.error(f"❌ Error Q#{q_num}: {e}")

    async with session_pool() as session:
        stmt = select(Question).where(Question.subject == target_subject).order_by(Question.year, Question.session, Question.q_number)
        result = await session.execute(stmt)
        questions = result.scalars().all()
        
        logger.info(f"🔍 Generating missing explanations & auditing {len(questions)} history questions (2 workers)...")
        tasks_data = [(q.id, q.subject, q.q_number, q.year, q.session) for q in questions]

    tasks = [process_one(*d, session_pool) for d in tasks_data]
    await asyncio.gather(*tasks)
    
    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
