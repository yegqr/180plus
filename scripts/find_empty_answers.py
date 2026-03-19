import asyncio
import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, or_
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)

    async with session_pool() as session:
        # We look for:
        # 1. correct_answer is null
        # 2. correct_answer is empty JSON {}
        # 3. correct_answer contains "None" as a string value
        stmt = select(Question).where(
            or_(
                Question.correct_answer.is_(None),
                Question.correct_answer == {},
                # Since correct_answer is JSONB, we can check for "None" string or null values inside
                Question.correct_answer["answer"].as_string().ilike("None"),
                Question.correct_answer["pairs"].as_string().ilike("None")
            )
        ).order_by(Question.subject, Question.year, Question.session, Question.q_number)

        result = await session.execute(stmt)
        questions = result.scalars().all()

        if not questions:
            print("✅ No empty or 'None-like' answers found.")
            return

        print(f"🔍 Found {len(questions)} questions with suspicious answer data:")
        print("-" * 100)
        print(f"{'Year':<6} | {'Subject':<8} | {'Session':<20} | {'Num':<4} | {'Options':<10} | {'Answer'}")
        print("-" * 100)

        for q in questions:
            ans = q.correct_answer
            ans_str = json.dumps(ans, ensure_ascii=False) if ans else "NULL"
            options = ans.get("options", "-") if isinstance(ans, dict) else "-"
            
            print(f"{q.year:<6} | {q.subject:<8} | {q.session:<20} | {q.q_number:<4} | {options:<10} | {ans_str}")

if __name__ == "__main__":
    asyncio.run(main())
