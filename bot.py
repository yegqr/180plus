import asyncio
import logging
import warnings

# Suppress Pydantic warning about "model_" protected namespace in aiogram
warnings.filterwarnings("ignore", message='Field "model_custom_emoji_id" in UniqueGiftColors has conflict with protected namespace "model_".')

import betterlogging as bl
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from aiogram_dialog import setup_dialogs

from infrastructure.database.models import Base
from infrastructure.database.setup import create_engine, create_session_pool
from tgbot.config import load_config, Config
from tgbot.dialogs import admin_dialog, main_menu_dialog, simulation_dialog, random_dialog, stats_dialog, broadcast_dialog
from tgbot.dialogs.calculator import calculator_dialog
from tgbot.handlers import routers_list
from tgbot.middlewares.config import ConfigMiddleware
from tgbot.middlewares.database import DatabaseMiddleware
from tgbot.middlewares.maintenance import MaintenanceMiddleware
from tgbot.services import broadcaster

async def on_startup(bot: Bot, admin_ids: list[int], engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await broadcaster.broadcast(bot, admin_ids, "🤖 I am alive!")


def register_global_middlewares(dp: Dispatcher, config: Config, session_pool=None):
    """
    Register global middlewares for the given dispatcher.
    Global middlewares here are the ones that are applied to all the handlers (you specify the type of update)

    :param dp: The dispatcher instance.
    :type dp: Dispatcher
    :param config: The configuration object from the loaded configuration.
    :param session_pool: Optional session pool object for the database using SQLAlchemy.
    :return: None
    """
    from tgbot.middlewares.topic_routing import TopicRoutingMiddleware
    from tgbot.middlewares.ensure_topics import EnsureTopicsMiddleware
    
    middleware_types = [
        ConfigMiddleware(config),
        DatabaseMiddleware(session_pool),
        TopicRoutingMiddleware(),
        MaintenanceMiddleware(),
    ]

    for middleware_type in middleware_types:
        dp.message.outer_middleware(middleware_type)
        dp.callback_query.outer_middleware(middleware_type)
        dp.chat_join_request.outer_middleware(middleware_type)
        
    # Inner middleware to ensure topics exist before hitting endpoints
    ensure_topics_mw = EnsureTopicsMiddleware()
    dp.message.middleware(ensure_topics_mw)
    dp.callback_query.middleware(ensure_topics_mw)


def setup_logging():
    """
    Set up logging configuration for the application.

    This method initializes the logging configuration for the application.
    It sets the log level to INFO and configures a basic colorized log for
    output. The log format includes the filename, line number, log level,
    timestamp, logger name, and log message.

    Returns:
        None

    Example usage:
        setup_logging()
    """
    log_level = logging.INFO
    bl.basic_colorized_config(level=log_level)

    logging.basicConfig(
        level=logging.INFO,
        format="%(filename)s:%(lineno)d #%(levelname)-8s [%(asctime)s] - %(name)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting bot")


def get_storage(config):
    """
    Return storage based on the provided configuration.

    Args:
        config (Config): The configuration object.

    Returns:
        Storage: The storage object based on the configuration.

    """
    if config.tg_bot.use_redis:
        return RedisStorage.from_url(
            config.redis.dsn(),
            key_builder=DefaultKeyBuilder(with_bot_id=True, with_destiny=True),
        )
    else:
        return MemoryStorage()


async def main():
    setup_logging()

    config = load_config(".env")
    storage = get_storage(config)

    bot = Bot(token=config.tg_bot.token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage)

    # Dialogs first (so they can intercept messages if active)
    from tgbot.dialogs.subject_menu import subject_menu_dialog
    from tgbot.dialogs.daily import daily_dialog
    
    dp.include_router(admin_dialog)
    dp.include_router(main_menu_dialog)
    dp.include_router(calculator_dialog)
    dp.include_router(simulation_dialog)
    dp.include_router(random_dialog)
    dp.include_router(stats_dialog)
    dp.include_router(broadcast_dialog)
    dp.include_router(subject_menu_dialog)
    dp.include_router(daily_dialog)
    
    # Then regular routers
    from tgbot.handlers.daily import daily_router
    dp.include_router(daily_router)
    dp.include_routers(*routers_list)
    
    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)
    bot.session_pool = session_pool

    register_global_middlewares(dp, config, session_pool=session_pool)
    
    setup_dialogs(dp)

    from tgbot.services.scheduler import setup_scheduler
    await setup_scheduler(bot, session_pool)

    await on_startup(bot, config.tg_bot.admin_ids, engine)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Бот був вимкнений!")
