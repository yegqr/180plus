
import asyncio
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.repo.requests import RequestsRepo
from tgbot.config import load_config
from sqlalchemy import select
from infrastructure.database.models import Question

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    
    async with session_pool() as session:
        # Fetch History Q1-20
        stmt = select(Question).where(
            Question.subject == "hist",
            Question.q_number >= 1,
            Question.q_number <= 20
        )
        result = await session.execute(stmt)
        questions = result.scalars().all()
        
        updated_count = 0
        for q in questions:
            # Ensure correct_answer is a dict copy to trigger update
            current_data = dict(q.correct_answer)
            current_options = str(current_data.get("options", ""))
            
            # Only update if incorrect
            if current_options != "4":
                current_data["options"] = "4"
                q.correct_answer = current_data
                updated_count += 1
        
        if updated_count > 0:
            await session.commit()
            print(f"✅ Successfully updated {updated_count} History questions to have 4 options.")
        else:
            print("✅ All History Q1-20 already have 4 options. No changes needed.")

if __name__ == "__main__":
    asyncio.run(main())
