from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_session import RefreshCredential, RefreshSession


class RefreshSessionRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session

    async def get_session(self, *, session_id: UUID, for_update: bool = False) -> RefreshSession | None:
        statement = select(RefreshSession).where(RefreshSession.id == session_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_credential(self, *, token_hash: str) -> RefreshCredential | None:
        result = await self.session.execute(
            select(RefreshCredential)
            .where(RefreshCredential.token_hash == token_hash)
            # Refresh reads the credential before taking the family lock. Force
            # the post-lock read to overwrite identity-map state after a waiter
            # resumes, so it sees the first transaction's consumed_at update.
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def create_session(self, *, auth_session: RefreshSession) -> RefreshSession:
        self.session.add(auth_session)
        await self.session.flush()
        return auth_session

    async def create_credential(self, *, credential: RefreshCredential) -> RefreshCredential:
        self.session.add(credential)
        await self.session.flush()
        return credential
