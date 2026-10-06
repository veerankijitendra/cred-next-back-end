from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, *, user_id: UUID) -> User | None:
        statement = select(User).where(User.id == user_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_email(self, *, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))

        return result.scalar_one_or_none()

    async def get_by_phone_number(self, *, phone_number: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.phone_number == phone_number)
        )

        return result.scalar_one_or_none()

    async def create(self, *, user: User) -> User:
        self.session.add(user)

        await self.session.flush()

        return user

    async def update_refresh_token_hash(
        self, user: User, refresh_token_hash: str | None
    ) -> User:
        user.refresh_token_hash = refresh_token_hash

        await self.session.flush()

        return user

    async def get_by_reference_id(self, *, reference_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.reference_id == reference_id)
        )

        return result.scalar_one_or_none()
