from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticate the request using an access token.
    """

    token = credentials.credentials

    payload = decode_token(token=token)

    if payload.get("type") != "access":
        raise UnauthorizedError(message="Access token required.")

    user_id = payload.get("sub")

    if not user_id:
        raise UnauthorizedError(message="Invalid access token")

    try:
        user_uuid = UUID(user_id)

    except ValueError as exc:
        raise UnauthorizedError(message="Invalid access token") from exc

    repository = UserRepository(session=session)

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
