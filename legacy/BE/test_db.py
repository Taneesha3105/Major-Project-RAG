import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings


async def main():
    print(
        "URL:",
        settings.database_url.render_as_string(hide_password=True)
    )

    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_recycle=300,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as conn:
            result = await conn.exec_driver_sql(
                "SELECT current_database(), current_user"
            )
            print("RESULT:", result.fetchone())
    finally:
        await engine.dispose()


asyncio.run(main())