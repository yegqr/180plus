
import asyncio
from infrastructure.database.setup import create_engine, create_session_pool
from tgbot.config import load_config
from sqlalchemy import text

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    
    async with session_pool() as session:
        print("🔄 Adding 'categories' column to 'questions' table...")
        try:
            # PostgreSQL specific
            await session.execute(text("ALTER TABLE questions ADD COLUMN IF NOT EXISTS categories JSONB;"))
            await session.commit()
            print("✅ Column 'categories' (JSONB) added successfully.")
        except Exception as e:
            print(f"❌ Error adding column: {e}")
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(main())
