import asyncio
import logging
import sys
import os

# Add parent dir to path to import modules
sys.path.append(os.getcwd())

from tgbot.config import load_config
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question
from tgbot.services.gemini import GeminiService
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    config = load_config(".env")
    if not config.misc.gemini_api_key:
        logger.error("No Gemini API Key found in .env")
        return

    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    
    service = GeminiService(config.misc.gemini_api_key)
    
    # We need a bot instance to download images?
    # Or can we just use file_ids if we are inside the bot logic?
    # GeminiService takes bytes.
    # We need to download files from Telegram.
    # We need a Bot instance.
    from aiogram import Bot
    bot = Bot(token=config.tg_bot.token)

    async with session_pool() as session:
        # Fetch all questions
        # Optional: filtered by those missing explanation?
        # User said "generate for all all". Let's do missing first or just all.
        # Let's filter for missing explanations to save tokens/time, or add a flag.
        # For now, let's just do ALL as requested, or log if skipping.
        result = await session.execute(select(Question).order_by(Question.id))
        questions = result.scalars().all()
        
        logger.info(f"Found {len(questions)} questions.")
        
        for q in questions:
            # Force overwrite as requested for regeneration
            # if q.explanation and len(q.explanation) > 10:
            #     logger.info(f"Skipping Q#{q.id} (already has explanation)")
            #     continue

            logger.info(f"Processing Q#{q.id} ({q.subject} {q.year})...")
            
            # Fetch images
            images_data = []
            image_ids = q.images or ([q.image_file_id] if q.image_file_id else [])
            
            if not image_ids:
                logger.warning(f"No images for Q#{q.id}")
                continue
                
            try:
                for img_id in image_ids:
                    # Download file from Telegram
                    f = await bot.get_file(img_id)
                    # We can download using bot.download_file
                    # ByteIO
                    from io import BytesIO
                    b = BytesIO()
                    await bot.download_file(f.file_path, b)
                    images_data.append(b.getvalue())
                
                # Context text in prompt
                q_text = f"Subject: {q.subject}, Type: {q.q_type}"
                
                # Generate
                explanation = await service.generate_explanation(images_data, q_text)
                
                # Save
                q.explanation = explanation
                await session.commit()
                logger.info(f"✅ Generated for Q#{q.id}")
                
                # Rate limit safety
                await asyncio.sleep(2) 
                
            except Exception as e:
                logger.error(f"Failed Q#{q.id}: {e}")
                # continue

    await bot.session.close()
    logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(main())
