import asyncio
import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)

    TARGET_SUBJECT = "hist"

    async with session_pool() as session:
        stmt = select(Question).where(Question.subject == TARGET_SUBJECT)
        result = await session.execute(stmt)
        questions = result.scalars().all()

        updated_count = 0
        for q in questions:
            num = q.q_number
            options = None
            
            if 1 <= num <= 20:
                options = "4"
            elif 21 <= num <= 24:
                options = "4x5"
            elif 25 <= num <= 27:
                options = "4x4"
            elif 28 <= num <= 30:
                options = "-"
            
            if options is not None:
                # Update options in correct_answer JSONB
                new_ans = (q.correct_answer or {}).copy()
                if new_ans.get("options") != options:
                    new_ans["options"] = options
                    q.correct_answer = new_ans
                    updated_count += 1

        if updated_count > 0:
            await session.commit()
            print(f"✅ Updated 'options' for {updated_count} History questions.")
        else:
            print("📅 All History questions already have correct 'options'.")

if __name__ == "__main__":
    asyncio.run(main())
