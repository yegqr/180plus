import asyncio
import logging
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    
    async with session_pool() as session:
        # Fetch generic match for Q23 History
        # We look for "Demo" session or similar year
        stmt = select(Question).where(
            Question.subject == "hist",
            Question.q_number == 23
        ).order_by(Question.year.desc()).limit(5)
        
        result = await session.execute(stmt)
        questions = result.scalars().all()
        
        for q in questions:
            print(f"ID: {q.id} | Year: {q.year} | Session: {q.session}")
            print(f"Type: {q.q_type}")
            print(f"Correct Answer RAW: {q.correct_answer}")
            print("-" * 30)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
