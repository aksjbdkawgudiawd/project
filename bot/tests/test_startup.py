import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.storage.base import StorageKey

from bot.__main__ import main
from bot.config import Settings


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_absent_token_does_not_create_clients_or_storage(self):
        with patch("bot.__main__.Settings.from_env", return_value=Settings()), \
                patch("bot.__main__.Bot") as bot, \
                patch("bot.__main__.Backend") as backend, \
                patch("bot.__main__.RedisStorage.from_url") as redis:
            await main()
        bot.assert_not_called()
        backend.assert_not_called()
        redis.assert_not_called()

    async def test_production_startup_isolates_bot_keys_and_closes_clients(self):
        settings = Settings(token="synthetic-token", internal_token="x" * 32,
                            redis_url="redis://fixture.invalid/0", environment="production")
        storage = MagicMock()
        storage.redis.ping = AsyncMock()
        storage.close = AsyncMock()
        isolation = MagicMock(close=AsyncMock())
        storage.create_isolation.return_value = isolation
        bot = MagicMock()
        bot.session.close = AsyncMock()
        backend = MagicMock(close=AsyncMock())
        dispatcher = MagicMock(start_polling=AsyncMock())
        with patch("bot.__main__.Settings.from_env", return_value=settings), \
                patch("bot.__main__.RedisStorage.from_url", return_value=storage) as redis, \
                patch("bot.__main__.Bot", return_value=bot), \
                patch("bot.__main__.Backend", return_value=backend), \
                patch("bot.__main__.Dispatcher", return_value=dispatcher):
            await main()
        builder = redis.call_args.kwargs["key_builder"]
        first = StorageKey(bot_id=111, chat_id=77, user_id=77)
        second = StorageKey(bot_id=222, chat_id=77, user_id=77)
        for part in ("state", "data", "lock"):
            self.assertNotEqual(builder.build(first, part), builder.build(second, part))
        self.assertEqual(redis.call_args.kwargs["state_ttl"], 86400)
        self.assertEqual(redis.call_args.kwargs["data_ttl"], 86400)
        storage.redis.ping.assert_awaited_once()
        dispatcher.start_polling.assert_awaited_once()
        backend.close.assert_awaited_once()
        storage.close.assert_awaited_once()
        isolation.close.assert_awaited_once()
        bot.session.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
