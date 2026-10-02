from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

password_hasher = PasswordHasher()


def hash_password(*, password: str) -> str:
    """Hash a plain-text password using Argon2id."""
    return password_hasher.hash(password)


def verify_password(*, password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError, VerifyMismatchError):
        return False


def create_access_token(user_id: str, role: str) -> str:
    """Create a short-lived access token."""

    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": expires_at,
        "type": "access",
    }

    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_refresh_token(user_id: str, role: str) -> str:
    """Create a long-lived refresh token."""

    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)

    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": expires_at,
        "type": "refresh",
        "jti": str(uuid4()),
    }

    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def hash_refresh_token(refresh_token: str) -> str:
    """Hash a refresh token before storing it."""
    return password_hasher.hash(refresh_token)


def verify_refresh_token(*, refresh_token: str, refresh_token_hash: str):
    try:
        return password_hasher.verify(refresh_token_hash, refresh_token)
    except (VerificationError, InvalidHashError):
        return False


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT."""

    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError(message="Invalid or expired token.") from exc


def hash_otp(otp: str) -> str:
    return password_hasher.hash(otp)


def verify_otp(otp: str, otp_hash: str) -> bool:
    try:
        return password_hasher.verify(otp_hash, otp)

    except (VerificationError, InvalidHashError, VerifyMismatchError):
        return False
