import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.exceptions import UnauthorizedError
from app.core.rate_limit import AuthRateLimiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
)
from app.models.refresh_session import RefreshCredential, RefreshSession
from app.models.user import User
from app.services.auth import AuthService


class SecurityTests(unittest.TestCase):
    def test_access_token_has_required_claims(self):
        session_id = uuid4()
        token = create_access_token(user_id=str(uuid4()), role="user", session_id=session_id)
        payload = decode_token(token)
        self.assertEqual(payload["type"], "access")
        self.assertEqual(payload["sid"], str(session_id))
        self.assertEqual(payload["iss"], settings.jwt_issuer)
        self.assertEqual(payload["aud"], settings.jwt_audience)
        self.assertTrue(payload["jti"])

    def test_expired_malformed_and_wrong_signature_tokens_rejected(self):
        now = datetime.now(UTC)
        base = {
            "sub": str(uuid4()), "role": "user", "sid": str(uuid4()),
            "iat": now - timedelta(minutes=2), "exp": now - timedelta(minutes=1),
            "jti": str(uuid4()), "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience, "type": "access",
        }
        expired = jwt.encode(base, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)
        wrong_signature = jwt.encode({**base, "exp": now + timedelta(minutes=1)}, "x" * 40, algorithm=settings.jwt_algorithm)
        for token in (expired, wrong_signature, "not-a-jwt"):
            with self.subTest(token_kind="invalid"):
                with self.assertRaises(UnauthorizedError):
                    decode_token(token)

    def test_refresh_token_is_opaque_and_hash_is_stable(self):
        token = create_refresh_token()
        self.assertEqual(len(hash_refresh_token(token)), 64)
        self.assertNotEqual(token, hash_refresh_token(token))
        with self.assertRaises(UnauthorizedError):
            decode_token(token)

    def test_settings_reject_weak_secret_and_wildcard_origins(self):
        base = {
            "database_url": "postgresql+psycopg://user:pass@localhost/db",
            "jwt_secret_key": "x" * 32,
        }
        with self.assertRaises(ValidationError):
            Settings(**{**base, "jwt_secret_key": "short"})
        with self.assertRaises(ValidationError):
            Settings(**{**base, "cors_allowed_origins": "*"}).trusted_origins

    def test_rate_limiter_enforces_window_limit(self):
        async def run():
            limiter = AuthRateLimiter()
            self.assertIsNone(await limiter.check(key="test", limit=1))
            self.assertIsNotNone(await limiter.check(key="test", limit=1))
        asyncio.run(run())

    def test_refresh_rotation_reuse_revokes_session_and_logout_blocks_refresh(self):
        async def run():
            now = datetime.now(UTC)
            user = User(
                id=uuid4(), name="Test User", email="test@example.com",
                phone_number="9876543210", reference_id="CNX-TEST",
            )
            auth_session = RefreshSession(
                user_id=user.id, expires_at=now + timedelta(days=1), revoked_at=None,
            )
            auth_session.id = uuid4()
            old_token = create_refresh_token()
            old_credential = RefreshCredential(
                session_id=auth_session.id,
                token_hash=hash_refresh_token(old_token),
                expires_at=auth_session.expires_at,
                consumed_at=None,
            )
            session = _FakeSession()
            service = AuthService.__new__(AuthService)
            service.session = session
            service.refresh_repository = _FakeRefreshRepository(auth_session, old_credential)
            service.user_repository = _FakeUserRepository(user)

            access_token, rotated_token = await service.refresh_tokens(refresh_token=old_token)
            self.assertEqual(decode_token(access_token)["type"], "access")
            self.assertNotEqual(rotated_token, old_token)
            self.assertIsNotNone(old_credential.consumed_at)

            with self.assertRaises(UnauthorizedError):
                await service.refresh_tokens(refresh_token=old_token)
            self.assertIsNotNone(auth_session.revoked_at)

            second_session = RefreshSession(
                user_id=user.id, expires_at=now + timedelta(days=1), revoked_at=None,
            )
            second_session.id = uuid4()
            logout_token = create_refresh_token()
            logout_credential = RefreshCredential(
                session_id=second_session.id,
                token_hash=hash_refresh_token(logout_token),
                expires_at=second_session.expires_at,
                consumed_at=None,
            )
            service.refresh_repository = _FakeRefreshRepository(second_session, logout_credential)
            await service.logout_user(refresh_token=logout_token)
            self.assertIsNotNone(second_session.revoked_at)
            with self.assertRaises(UnauthorizedError):
                await service.refresh_tokens(refresh_token=logout_token)

        asyncio.run(run())


class _FakeSession:
    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeRefreshRepository:
    def __init__(self, auth_session, credential):
        self.sessions = {auth_session.id: auth_session}
        self.credentials = {credential.token_hash: credential}

    async def get_credential(self, *, token_hash):
        return self.credentials.get(token_hash)

    async def get_session(self, *, session_id, for_update=False):
        return self.sessions.get(session_id)

    async def create_credential(self, *, credential):
        self.credentials[credential.token_hash] = credential
        return credential


class _FakeUserRepository:
    def __init__(self, user):
        self.user = user

    async def get_by_id(self, *, user_id):
        return self.user if self.user.id == user_id else None


if __name__ == "__main__":
    unittest.main()
