from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.models.refresh_session import RefreshSession
from app.repositories.user import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticate the request using an access token.
    """

    if credentials is None:
        raise UnauthorizedError(message="Authentication credentials are required.")
    token = credentials.credentials

    payload = decode_token(token=token)

    if payload.get("type") != "access":
        raise UnauthorizedError(message="Access token required.")

    user_id = payload.get("sub")

    if not user_id:
        raise UnauthorizedError(message="Invalid access token")

    try:
        user_uuid = UUID(user_id)
        session_uuid = UUID(payload.get("sid", ""))

    except (ValueError, TypeError, AttributeError) as exc:
        raise UnauthorizedError(message="Invalid access token") from exc

    repository = UserRepository(session=session)

    auth_session = await session.scalar(
        select(RefreshSession).where(RefreshSession.id == session_uuid)
    )
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.user_id != user_uuid
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
    ):
        raise UnauthorizedError(message="Authentication session is expired or revoked.")

    user = await repository.get_by_id(user_id=user_uuid)

    if not user:
        raise UnauthorizedError(message="User no longer exists")

    return user


def require_role(required_role: str) -> Callable[..., Coroutine[Any, Any, User]]:
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role:
            raise ForbiddenError(
                message="You don't have permission to access this resource"
            )
        return current_user

    return role_checker
