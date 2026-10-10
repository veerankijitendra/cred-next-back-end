import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

password_hasher = PasswordHasher()


def hash_password(*, password: str) -> str:
    return password_hasher.hash(password)


def verify_password(*, password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError, VerifyMismatchError):
        return False


def create_access_token(*, user_id: str, role: str, session_id: UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "sid": str(session_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "jti": str(uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


def create_refresh_token() -> str:
    """Create an opaque, high-entropy refresh credential for cookie transport."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(refresh_token: str) -> str:
    # Refresh credentials have 384 bits of entropy, so a fast cryptographic digest
    # avoids Argon2's unnecessary CPU cost while remaining infeasible to brute force.
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def verify_refresh_token(*, refresh_token: str, refresh_token_hash: str) -> bool:
    return hmac.compare_digest(hash_refresh_token(refresh_token), refresh_token_hash)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "role", "sid", "iat", "exp", "jti", "iss", "aud", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError(message="Invalid or expired access token.") from exc


def hash_otp(otp: str) -> str:
    return password_hasher.hash(otp)


def verify_otp(otp: str, otp_hash: str) -> bool:
    try:
        return password_hasher.verify(otp_hash, otp)
    except (VerificationError, InvalidHashError, VerifyMismatchError):
        return False
