from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)

    async def get_by_telegram_id(self, session: AsyncSession, telegram_id: int) -> User | None:
        return await self.get_by_attribute(session, "telegram_id", telegram_id)

    async def get_or_create_user(
        self, session: AsyncSession, telegram_user: dict
    ) -> tuple[User, bool]:
        """Gets or creates a user based on Telegram user info."""
        return await self.get_or_create(
            session,
            telegram_id=telegram_user["id"],
            defaults={
                "username": telegram_user.get("username"),
                "first_name": telegram_user["first_name"],
                "last_name": telegram_user.get("last_name"),
                "is_active": True,
            }
        )

user_repo = UserRepository() 