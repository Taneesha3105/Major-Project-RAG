import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.main import lifespan


class MainLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_starts_local_warmup_in_background_when_configured(self):
        warmup_started = asyncio.Event()
        allow_warmup_to_finish = asyncio.Event()

        async def fake_warmup() -> None:
            warmup_started.set()
            await allow_warmup_to_finish.wait()

        initialize_database = AsyncMock()
        close_database_engine = AsyncMock()

        with (
            patch("app.main.initialize_database", initialize_database),
            patch("app.main.close_database_engine", close_database_engine),
            patch("app.main.warm_configured_embedding_provider", side_effect=fake_warmup),
            patch("app.main.settings.embedding_provider", "local"),
            patch("app.main.settings.local_embedding_warmup_enabled", True),
            patch("app.main.settings.local_embedding_warmup_mode", "background"),
        ):
            manager = lifespan(None)
            await asyncio.wait_for(manager.__aenter__(), timeout=0.1)
            await asyncio.sleep(0)

            self.assertTrue(warmup_started.is_set())
            initialize_database.assert_awaited_once()

            allow_warmup_to_finish.set()
            await manager.__aexit__(None, None, None)

        close_database_engine.assert_awaited_once()

    async def test_lifespan_blocks_until_local_warmup_finishes_when_configured(self):
        initialize_database = AsyncMock()
        close_database_engine = AsyncMock()
        warmup_finished = False

        async def fake_warmup() -> None:
            nonlocal warmup_finished
            await asyncio.sleep(0)
            warmup_finished = True

        with (
            patch("app.main.initialize_database", initialize_database),
            patch("app.main.close_database_engine", close_database_engine),
            patch("app.main.warm_configured_embedding_provider", side_effect=fake_warmup),
            patch("app.main.settings.embedding_provider", "local"),
            patch("app.main.settings.local_embedding_warmup_enabled", True),
            patch("app.main.settings.local_embedding_warmup_mode", "blocking"),
        ):
            manager = lifespan(None)
            await manager.__aenter__()
            self.assertTrue(warmup_finished)
            await manager.__aexit__(None, None, None)

        initialize_database.assert_awaited_once()
        close_database_engine.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
