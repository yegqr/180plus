import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, update
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.config import load_config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)

    # Questions to fix: Subject 'hist', Numbers 21-24
    # They should be q_type 'match' and weight 4.
    
    target_subject = "hist"
    target_numbers = [21, 22, 23, 24]
    
    async with session_pool() as session:
        # 1. Fetch relevant questions
        stmt = select(Question).where(
            Question.subject == target_subject,
            Question.q_number.in_(target_numbers)
        )
        result = await session.execute(stmt)
        questions = result.scalars().all()
        
        updated_count = 0
        
        for q in questions:
            original_type = q.q_type
            original_weight = q.weight
            
            # Need to update type and weight
            q.q_type = "match"
            q.weight = 4
            
            # Update options in correct_answer to "4x5"
            # We must create a new dict to ensure SQLAlchemy detects the change on JSONB
            new_answer = dict(q.correct_answer)
            new_answer["options"] = "4x5" 
            q.correct_answer = new_answer
            
            # Helper to debug what we are changing
            logger.info(f"Fixed Q#{q.q_number} ({q.session} {q.year}): "
                        f"Type {original_type}->match, Weight {original_weight}->4, Options->4x5")
            
            updated_count += 1

        if updated_count > 0:
            await session.commit()
            logger.info(f"✅ Successfully updated {updated_count} questions.")
        else:
            logger.info("🎉 No questions needed fixing (none found).")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
