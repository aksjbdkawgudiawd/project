import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.fsm.storage.redis import RedisStorage

from .api import Backend
from .config import Settings
from .handlers import CustomerMiddleware, make_router
from .i18n import Messages


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # HTTP debug logs could expose bot tokens embedded in Telegram endpoint URLs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings.from_env()
    if not settings.token:
        logging.info("BOT_TOKEN is absent; Telegram polling is disabled")
        return
    settings.validate()
    messages = Messages(settings.templates_directory, settings.default_locale)
    if settings.redis_url:
        storage = RedisStorage.from_url(
            settings.redis_url,
            key_builder=DefaultKeyBuilder(prefix="arshisney:bot:fsm", with_bot_id=True),
            state_ttl=86400,
            data_ttl=86400,
        )
        await storage.redis.ping()
        isolation = storage.create_isolation(lock_kwargs={"timeout": 300, "blocking_timeout": 310})
    else:
        logging.warning("Local MemoryStorage enabled; sessions do not survive restart. Not for production.")
        storage = MemoryStorage()
        isolation = SimpleEventIsolation()
    backend = Backend(settings.api_url, settings.internal_token)
    bot = Bot(settings.token, default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True))
    dispatcher = Dispatcher(storage=storage, events_isolation=isolation)
    middleware = CustomerMiddleware(backend, messages)
    dispatcher.message.outer_middleware(middleware)
    dispatcher.callback_query.outer_middleware(middleware)
    dispatcher.include_router(make_router())
    try:
        # Long polling is intentionally single-instance; webhook scaling is not configured.
        await dispatcher.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await backend.close()
        await storage.close()
        await isolation.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
