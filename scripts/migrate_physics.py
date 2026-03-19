import asyncio
import os
import sys

# Add project root to sys.path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config
from sqlalchemy import update, select

async def migrate_physics():
    print("🚀 Starting Physics 2023 -> 2026 migration...")
    
    # Load config from .env
    config = load_config()
    
    # Setup DB connection
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    
    async with session_pool() as session:
        # 1. Count how many questions we are about to migrate
        count_stmt = select(Question).where(
            Question.subject == 'physics', 
            Question.year == 2023
        )
        result = await session.execute(count_stmt)
        questions = result.scalars().all()
        
        if not questions:
            print("❌ No Physics questions found for year 2023.")
            return

        print(f"📦 Found {len(questions)} questions. Transferring to 2026 'Демоваріант'...")

        # 2. Perform the update
        stmt = (
            update(Question)
            .where(
                Question.subject == 'physics', 
                Question.year == 2023
            )
            .values(
                year=2026, 
                session='Демоваріант'
            )
        )
        await session.execute(stmt)
        await session.commit()
        
        print(f"✅ Successfully migrated {len(questions)} questions to 2026.")

if __name__ == "__main__":
    asyncio.run(migrate_physics())
