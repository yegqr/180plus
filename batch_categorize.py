import asyncio
import logging
import io

from sqlalchemy import select
from infrastructure.database.setup import create_engine, create_session_pool
from infrastructure.database.models import Question, Setting
from tgbot.config import load_config
from tgbot.services.gemini import GeminiService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def process_question(sem, session_pool, bot, service, q_id, counter, total):
    async with sem:
        async with session_pool() as session:
            try:
                # Fetch question again to be safe in new session
                stmt = select(Question).where(Question.id == q_id)
                result = await session.execute(stmt)
                q = result.scalar_one_or_none()
                
                if not q:
                    return

                q_text = f"Subject: {q.subject}, Type: {q.q_type}, Ans: {q.correct_answer}. Explanation: {q.explanation or ''}"
                images_bytes = []
                
                # Image handling
                image_ids = q.images or []
                if not image_ids and q.image_file_id:
                    image_ids = [q.image_file_id]
                
                if image_ids:
                    try:
                        f = await bot.get_file(image_ids[0])
                        b = io.BytesIO()
                        await bot.download_file(f.file_path, b)
                        images_bytes.append(b.getvalue())
                    except Exception as e:
                        logger.warning(f"Failed to download image for Q#{q.q_number}: {e}")

                if not images_bytes and not q.explanation:
                     print(f"⚠️ Skipped Q#{q.q_number}: No content.")
                     return

                result_data = await service.generate_explanation(images_bytes, q_text, subject=q.subject)
                cats = result_data.get("categories", [])
                
                if cats:
                    q.categories = cats
                    # We can also update explanation if it was empty?
                    if not q.explanation and result_data.get("explanation"):
                        q.explanation = result_data.get("explanation")
                    
                    await session.commit()
                    
                    # Update counter
                    counter['success'] += 1
                    print(f"[{counter['processed']}/{total}] ✅ Q#{q.q_number} ({q.subject}) -> {cats}")
                else:
                    counter['error'] += 1
                    print(f"[{counter['processed']}/{total}] ⚠️ Q#{q.q_number} -> No categories.")

            except Exception as e:
                counter['error'] += 1
                logger.error(f"Error Q#{q_id}: {e}")
            finally:
                counter['processed'] += 1
                # 1 second delay as requested
                await asyncio.sleep(1.0)

async def main():
    config = load_config(".env")
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    
    # Fake bot
    from aiogram import Bot
    bot = Bot(token=config.tg_bot.token)

    # Validate Key
    async with session_pool() as session:
        stmt_key = select(Setting.value).where(Setting.key == "gemini_api_key")
        db_key_res = await session.execute(stmt_key)
        db_key = db_key_res.scalar_one_or_none()
        api_key = db_key or config.misc.gemini_api_key
        
        if not api_key:
            logger.error("❌ No API Key.")
            await bot.session.close()
            return

        # Fetch Uncategorized IDs
        stmt_q = select(Question.id).where(
            (Question.categories.is_(None)) | (Question.categories == [])
        ).order_by(Question.id)
        result_q = await session.execute(stmt_q)
        q_ids = list(result_q.scalars().all())

    total = len(q_ids)
    logger.info(f"🔎 Found {total} uncategorized questions.")
    
    if total == 0:
        await bot.session.close()
        return

    service = GeminiService(api_key)
    sem = asyncio.Semaphore(3) # 3 concurrent workers
    
    # Shared counter across tasks (simple dict works in asyncio because it's single threaded)
    counter = {'processed': 1, 'success': 0, 'error': 0}
    
    print(f"🚀 Starting batch categorization: 3 workers, 1s delay...")
    
    tasks = [process_question(sem, session_pool, bot, service, qid, counter, total) for qid in q_ids]
    await asyncio.gather(*tasks)

    print(f"\n🏁 Finished! Success: {counter['success']}, Errors: {counter['error']}")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
