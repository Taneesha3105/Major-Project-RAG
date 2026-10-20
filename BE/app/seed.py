"""Create the initial administrator account.

Usage:  python -m app.seed
Reads ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_FULL_NAME from the environment (.env).
"""

import asyncio

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import User
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository


async def seed_admin() -> None:
    async with SessionLocal() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email(settings.admin_email)
        if existing:
            print(f"Admin '{settings.admin_email}' already exists — nothing to do.")
            return
        await repo.add(
            User(
                email=settings.admin_email.lower(),
                full_name=settings.admin_full_name,
                hashed_password=hash_password(settings.admin_password),
                role=UserRole.ADMIN,
                job_title="Administrator",
            )
        )
        await session.commit()
        print(f"Created admin '{settings.admin_email}'. Change the password after first login.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_admin())
