import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import update
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)

    # Filter for Hist, 2026, Демоваріант
    TARGET_SUBJECT = "hist"
    TARGET_YEAR = 2026
    TARGET_SESSION = "Демоваріант"

    async with session_pool() as session:
        stmt = (
            update(Question)
            .where(
                Question.subject == TARGET_SUBJECT,
                Question.year == TARGET_YEAR,
                Question.session == TARGET_SESSION
            )
            .values(explanation=None)
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        print(f"✅ Cleared explanations for {result.rowcount} questions in '{TARGET_SUBJECT} {TARGET_YEAR} {TARGET_SESSION}'.")

if __name__ == "__main__":
    asyncio.run(main())
