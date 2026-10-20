from collections.abc import Sequence

from sqlalchemy import func, or_, select

from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(func.lower(User.email) == email.lower()))

    async def search(self, query: str | None, limit: int = 100) -> Sequence[User]:
        stmt = select(User).order_by(User.full_name).limit(limit)
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(or_(func.lower(User.full_name).like(pattern), func.lower(User.email).like(pattern)))
        return await self.list(stmt)

    async def count_all(self) -> int:
        return await self.count(select(User))
