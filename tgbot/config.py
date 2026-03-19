from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from environs import Env


@dataclass
class DbConfig:
    """
    Database configuration class.
    This class holds the settings for the database, such as host, password, port, etc.

    Attributes
    ----------
    host : str
        The host where the database server is located.
    password : str
        The password used to authenticate with the database.
    user : str
        The username used to authenticate with the database.
    database : str
        The name of the database.
    port : int
        The port where the database server is listening.
    """

    host: str
    password: str
    user: str
    database: str
    port: int = 5432

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("DB_HOST must not be empty")
        if not self.user:
            raise ValueError("POSTGRES_USER must not be empty")
        if not self.database:
            raise ValueError("POSTGRES_DB must not be empty")
        if not (1 <= self.port <= 65535):
            raise ValueError(f"DB_PORT must be 1-65535, got {self.port}")

    def construct_sqlalchemy_url(self, driver: str = "asyncpg", host: str | None = None, port: int | None = None) -> str:
        """
        Constructs and returns a SQLAlchemy URL for this database configuration.
        """
        from sqlalchemy.engine.url import URL

        if not host:
            host = self.host
        if not port:
            port = self.port
        uri = URL.create(
            drivername=f"postgresql+{driver}",
            username=self.user,
            password=self.password,
            host=host,
            port=port,
            database=self.database,
        )
        return uri.render_as_string(hide_password=False)

    @staticmethod
    def from_env(env: Env) -> DbConfig:
        """
        Creates the DbConfig object from environment variables.
        """
        host = env.str("DB_HOST")
        password = env.str("POSTGRES_PASSWORD")
        user = env.str("POSTGRES_USER")
        database = env.str("POSTGRES_DB")
        port = env.int("DB_PORT", 5432)
        return DbConfig(
            host=host, password=password, user=user, database=database, port=port
        )


@dataclass
class TgBot:
    """
    Creates the TgBot object from environment variables.
    """

    token: str
    admin_ids: list[int]
    use_redis: bool

    def __post_init__(self) -> None:
        if not self.token:
            raise ValueError("BOT_TOKEN must not be empty")
        if not self.admin_ids:
            raise ValueError("ADMINS must contain at least one admin ID")

    @staticmethod
    def from_env(env: Env) -> TgBot:
        """
        Creates the TgBot object from environment variables.
        """
        token = env.str("BOT_TOKEN")
        admin_ids = env.list("ADMINS", subcast=int)
        use_redis = env.bool("USE_REDIS")
        return TgBot(token=token, admin_ids=admin_ids, use_redis=use_redis)


@dataclass
class RedisConfig:
    """
    Redis configuration class.

    Attributes
    ----------
    redis_pass : Optional(str)
        The password used to authenticate with Redis.
    redis_port : Optional(int)
        The port where Redis server is listening.
    redis_host : Optional(str)
        The host where Redis server is located.
    """

    redis_pass: Optional[str]
    redis_port: Optional[int]
    redis_host: Optional[str]

    def dsn(self) -> str:
        """
        Constructs and returns a Redis DSN (Data Source Name) for this database configuration.
        """
        if self.redis_pass:
            return f"redis://:{self.redis_pass}@{self.redis_host}:{self.redis_port}/0"
        else:
            return f"redis://{self.redis_host}:{self.redis_port}/0"

    @staticmethod
    def from_env(env: Env) -> RedisConfig:
        """
        Creates the RedisConfig object from environment variables.
        """
        redis_pass = env.str("REDIS_PASSWORD")
        redis_port = env.int("REDIS_PORT")
        redis_host = env.str("REDIS_HOST")

        return RedisConfig(
            redis_pass=redis_pass, redis_port=redis_port, redis_host=redis_host
        )


@dataclass
class WebhookConfig:
    """
    Webhook configuration. Set USE_WEBHOOK=true to switch from polling.

    Required env vars when USE_WEBHOOK=true:
      WEBHOOK_URL   — full public URL Telegram will POST to, e.g.
                      https://bot.example.com/webhook/<TOKEN>
      WEBHOOK_PATH  — URL path component, e.g. /webhook/<TOKEN>

    Optional:
      WEBAPP_HOST   — bind host for the aiohttp server (default 0.0.0.0)
      WEBAPP_PORT   — bind port (default 8080)
      WEBHOOK_SECRET — secret token sent by Telegram in X-Telegram-Bot-Api-Secret-Token
    """

    use_webhook: bool = False
    url: str = ""
    path: str = ""
    webapp_host: str = "0.0.0.0"
    webapp_port: int = 8080
    secret_token: Optional[str] = None

    @staticmethod
    def from_env(env: "Env") -> "WebhookConfig":
        use_webhook = env.bool("USE_WEBHOOK", False)
        if not use_webhook:
            return WebhookConfig()
        return WebhookConfig(
            use_webhook=True,
            url=env.str("WEBHOOK_URL", ""),
            path=env.str("WEBHOOK_PATH", ""),
            webapp_host=env.str("WEBAPP_HOST", "0.0.0.0"),
            webapp_port=env.int("WEBAPP_PORT", 8080),
            secret_token=env.str("WEBHOOK_SECRET", None),
        )


@dataclass
class Miscellaneous:
    """
    Miscellaneous configuration class.

    This class holds settings for various other parameters.
    It merely serves as a placeholder for settings that are not part of other categories.

    Attributes
    ----------
    other_params : str, optional
        A string used to hold other various parameters as required (default is None).
    sentry_dsn : str, optional
        Sentry DSN for error tracking. Leave empty to disable Sentry.
    metrics_port : int
        Port for the Prometheus /metrics HTTP server (default 9090).
    """

    onboarding_video: Optional[str] = None
    gemini_api_key: Optional[str] = None
    sentry_dsn: Optional[str] = None
    metrics_port: int = 9090
    other_params: str = None


@dataclass
class Config:
    """
    The main configuration class that integrates all the other configuration classes.

    This class holds the other configuration classes, providing a centralized point of access for all settings.

    Attributes
    ----------
    tg_bot : TgBot
        Holds the settings related to the Telegram Bot.
    misc : Miscellaneous
        Holds the values for miscellaneous settings.
    db : Optional[DbConfig]
        Holds the settings specific to the database (default is None).
    redis : Optional[RedisConfig]
        Holds the settings specific to Redis (default is None).
    webhook : WebhookConfig
        Holds webhook settings (polling by default).
    """

    tg_bot: TgBot
    misc: Miscellaneous
    db: Optional[DbConfig] = None
    redis: Optional[RedisConfig] = None
    webhook: WebhookConfig = None

    def __post_init__(self):
        if self.webhook is None:
            self.webhook = WebhookConfig()


def load_config(path: str = None) -> Config:
    """
    This function takes an optional file path as input and returns a Config object.
    :param path: The path of env file from where to load the configuration variables.
    It reads environment variables from a .env file if provided, else from the process environment.
    :return: Config object with attributes set as per environment variables.
    """

    env = Env()
    env.read_env(path)

    return Config(
        tg_bot=TgBot.from_env(env),
        db=DbConfig.from_env(env),
        redis=RedisConfig.from_env(env),
        webhook=WebhookConfig.from_env(env),
        misc=Miscellaneous(
            onboarding_video=env.str("ONBOARDING_VIDEO", None),
            gemini_api_key=env.str("GEMINI_API_KEY", None),
            sentry_dsn=env.str("SENTRY_DSN", None),
            metrics_port=env.int("METRICS_PORT", 9090),
        ),
    )
