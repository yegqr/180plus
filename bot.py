import asyncio
import logging
import os
import signal
import warnings

# Suppress Pydantic warning about "model_" protected namespace in aiogram
warnings.filterwarnings("ignore", message='Field "model_custom_emoji_id" in UniqueGiftColors has conflict with protected namespace "model_".')

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from aiogram_dialog import setup_dialogs

from infrastructure.database.setup import create_engine, create_session_pool
from tgbot.config import load_config, Config
from tgbot.dialogs import admin_dialog, main_menu_dialog, simulation_dialog, random_dialog, stats_dialog, broadcast_dialog, referrer_stats_dialog
from tgbot.dialogs.calculator import calculator_dialog
from tgbot.handlers import routers_list
from tgbot.middlewares.config import ConfigMiddleware
from tgbot.middlewares.database import DatabaseMiddleware
from tgbot.middlewares.maintenance import MaintenanceMiddleware
from tgbot.middlewares.throttling import ThrottlingMiddleware
from tgbot.services import broadcaster


def setup_sentry(dsn: str) -> None:
    """Initialise Sentry error tracking. Called only when SENTRY_DSN is set."""
    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                AsyncioIntegration(),
                SqlalchemyIntegration(),
            ],
            # Capture 10 % of transactions for performance monitoring.
            # Set to 1.0 temporarily if you need to debug latency issues.
            traces_sample_rate=0.1,
        )
        logging.getLogger(__name__).info("Sentry initialised.")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Sentry setup failed: {e}")


def setup_prometheus(port: int) -> None:
    """Start the Prometheus metrics HTTP server in a background thread."""
    try:
        from prometheus_client import start_http_server
        start_http_server(port)
        logging.getLogger(__name__).info(f"Prometheus metrics available at :{port}/metrics")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Prometheus setup failed: {e}")


async def _run_alembic_migrations() -> None:
    """Run all pending Alembic migrations (sync API wrapped in executor)."""
    import asyncio as _asyncio
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    def _migrate() -> None:
        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_command.upgrade(alembic_cfg, "head")

    await _asyncio.get_event_loop().run_in_executor(None, _migrate)


async def on_startup(bot: Bot, admin_ids: list[int], session_pool) -> None:
    await _run_alembic_migrations()
    await broadcaster.broadcast(bot, admin_ids, "🤖 I am alive!", session_pool=session_pool)


def register_global_middlewares(dp: Dispatcher, config: Config, session_pool=None, throttle_redis=None, user_cache_redis=None):
    """
    Register global middlewares for the given dispatcher.
    Global middlewares here are the ones that are applied to all the handlers (you specify the type of update)

    :param dp: The dispatcher instance.
    :type dp: Dispatcher
    :param config: The configuration object from the loaded configuration.
    :param session_pool: Optional session pool object for the database using SQLAlchemy.
    :param throttle_redis: Optional Redis client for distributed rate-limiting (db=3).
    :return: None
    """
    from tgbot.middlewares.topic_routing import TopicRoutingMiddleware
    from tgbot.middlewares.ensure_topics import EnsureTopicsMiddleware

    # ThrottlingMiddleware runs first (before DB session is opened) to drop
    # flood requests cheaply — no DB round-trip for throttled users.
    # admin_ids are passed at construction so the admin check works even before
    # ConfigMiddleware injects config into handler data.
    throttle_mw = ThrottlingMiddleware(
        rate_limit=0.7,
        redis=throttle_redis,
        admin_ids=config.tg_bot.admin_ids,
    )
    dp.message.outer_middleware(throttle_mw)
    dp.callback_query.outer_middleware(throttle_mw)

    middleware_types = [
        ConfigMiddleware(config),
        DatabaseMiddleware(session_pool, redis=user_cache_redis),
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
    Configure logging.

    In production (LOG_FORMAT=json env var set) emits structured JSON via
    python-json-logger so log aggregators (Loki, Datadog, ELK) can parse fields.
    Falls back to a human-readable coloured format for local development.
    """
    log_level = logging.INFO

    if os.getenv("LOG_FORMAT", "").lower() == "json":
        try:
            from pythonjsonlogger import jsonlogger

            handler = logging.StreamHandler()
            handler.setFormatter(
                jsonlogger.JsonFormatter(
                    fmt="%(asctime)s %(levelname)s %(name)s %(filename)s %(lineno)d %(message)s"
                )
            )
            logging.basicConfig(level=log_level, handlers=[handler])
        except ImportError:
            # python-json-logger not installed — fall back to plain text
            logging.basicConfig(
                level=log_level,
                format="%(filename)s:%(lineno)d #%(levelname)-8s [%(asctime)s] - %(name)s - %(message)s",
            )
    else:
        try:
            import betterlogging as bl
            bl.basic_colorized_config(level=log_level)
        except ImportError:
            pass
        logging.basicConfig(
            level=log_level,
            format="%(filename)s:%(lineno)d #%(levelname)-8s [%(asctime)s] - %(name)s - %(message)s",
        )

    logging.getLogger(__name__).info("Starting bot")


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

    # ── Sentry (optional) ────────────────────────────────────────────────────
    if config.misc.sentry_dsn:
        setup_sentry(config.misc.sentry_dsn)

    # ── Prometheus metrics server (background thread) ────────────────────────
    setup_prometheus(config.misc.metrics_port)

    storage = get_storage(config)

    bot = Bot(token=config.tg_bot.token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=storage)

    # Dialogs first (so they can intercept messages if active)
    from tgbot.dialogs.subject_menu import subject_menu_dialog

    dp.include_router(admin_dialog)
    dp.include_router(referrer_stats_dialog)
    dp.include_router(main_menu_dialog)
    dp.include_router(calculator_dialog)
    dp.include_router(simulation_dialog)
    dp.include_router(random_dialog)
    dp.include_router(stats_dialog)
    dp.include_router(broadcast_dialog)
    dp.include_router(subject_menu_dialog)

    # Then regular routers
    dp.include_routers(*routers_list)

    engine = create_engine(config.db)
    session_pool = create_session_pool(engine)

    # Redis clients — each on a separate DB to keep key spaces isolated:
    #   db=0  FSM storage
    #   db=1  APScheduler job store
    #   db=2  Distributed scheduler locks
    #   db=3  Throttling keys
    #   db=4  User object cache (ucache:*)
    throttle_redis = None
    user_cache_redis = None
    if config.tg_bot.use_redis:
        logger = logging.getLogger(__name__)
        base_dsn = config.redis.dsn()  # .../0
        for db_index, name, varname in [
            (3, "Throttling",  "throttle_redis"),
            (4, "User cache",  "user_cache_redis"),
        ]:
            try:
                import redis.asyncio as aioredis
                client = aioredis.Redis.from_url(
                    base_dsn.replace("/0", f"/{db_index}"),
                    decode_responses=True,
                )
                await client.ping()
                logger.info(f"{name}: Redis enabled (db={db_index}).")
                if varname == "throttle_redis":
                    throttle_redis = client
                else:
                    user_cache_redis = client
            except Exception as e:
                logger.warning(f"{name}: Redis unavailable ({e}), falling back to in-memory.")

    register_global_middlewares(
        dp, config,
        session_pool=session_pool,
        throttle_redis=throttle_redis,
        user_cache_redis=user_cache_redis,
    )

    setup_dialogs(dp)

    from tgbot.services.scheduler import setup_scheduler
    await setup_scheduler(bot, session_pool, config=config)

    await on_startup(bot, config.tg_bot.admin_ids, session_pool)

    # ── Health check server (always on, port 8081) ───────────────────────────
    asyncio.create_task(_run_health_server(8081))

    # ── Webhook or polling ───────────────────────────────────────────────────
    if config.webhook.use_webhook:
        await _run_webhook(bot, dp, config)
    else:
        await dp.start_polling(bot, drop_pending_updates=True)


async def _run_health_server(port: int) -> None:
    """Start a minimal HTTP server that returns 200 on GET /health."""
    from aiohttp import web

    async def health_handler(request: web.Request) -> web.Response:
        return web.Response(text='{"status":"ok"}', content_type="application/json")

    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logging.getLogger(__name__).info(f"Health endpoint: http://0.0.0.0:{port}/health")


async def _run_webhook(bot: Bot, dp: Dispatcher, config: Config) -> None:
    """Start the aiohttp webhook server and block until SIGINT/SIGTERM."""
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    logger = logging.getLogger(__name__)

    await bot.set_webhook(
        url=config.webhook.url,
        secret_token=config.webhook.secret_token,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    logger.info(f"Webhook set → {config.webhook.url}")

    app = web.Application()

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config.webhook.secret_token,
    ).register(app, path=config.webhook.path)

    # Wire aiogram's startup/shutdown signals to the aiohttp lifecycle.
    # NOTE: on_startup was already called manually above, so we skip re-running
    # it here — setup_application only needs to handle clean shutdown.
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.webhook.webapp_host, config.webhook.webapp_port)
    await site.start()

    logger.info(
        f"Webhook server listening on "
        f"{config.webhook.webapp_host}:{config.webhook.webapp_port}"
        f"{config.webhook.path}"
    )

    # Block until OS sends SIGINT or SIGTERM (e.g. docker stop / systemctl stop).
    # Using an Event + signal handlers instead of Event().wait() so SIGTERM is
    # caught gracefully and we can log the shutdown reason.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal(sig_name: str) -> None:
        logger.info(f"Received {sig_name} — shutting down webhook server.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal, sig.name)

    await stop_event.wait()

    logger.info("Cleaning up webhook server...")
    await runner.cleanup()
    await bot.delete_webhook(drop_pending_updates=False)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Бот був вимкнений!")
