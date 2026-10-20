import asyncio
import logging

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.config import settings
from app.db.models import Chunk, Document  # noqa: F401
from app.db.schema import prepare_database_schema
from app.db.session import engine

logger = logging.getLogger(__name__)


async def initialize_database() -> None:
    last_error: Exception | None = None

    for attempt in range(1, settings.db_init_max_retries + 1):
        try:
            async with engine.begin() as connection:
                await prepare_database_schema(connection)

            logger.info("Database connection established and tables are ready.")
            return
        except OperationalError as exc:
            last_error = exc
            logger.warning(
                "Database not ready yet (attempt %s/%s). Retrying in %s seconds.",
                attempt,
                settings.db_init_max_retries,
                settings.db_init_retry_delay,
            )
            if attempt < settings.db_init_max_retries:
                await asyncio.sleep(settings.db_init_retry_delay)
        except SQLAlchemyError as exc:
            logger.exception("Database initialization failed.")
            raise RuntimeError("Database initialization failed.") from exc

    raise RuntimeError("Could not connect to the database after multiple attempts.") from last_error


async def close_database_engine() -> None:
    await engine.dispose()
