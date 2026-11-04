import asyncio
import sys
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy.exc import ProgrammingError

from app.core.config import settings
from app.core.exception_handlers import sqlalchemy_exception_handler
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
)
from app.enums.user import UserRoleEnum
from app.models.refresh_session import RefreshCredential, RefreshSession
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.services.auth import AuthService


class _FakeDBSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _FakeUserRepository:
    def __init__(self, user: User | None = None):
        self.user = user

    async def get_by_email(self, *, email: str) -> User | None:
        if self.user and self.user.email.lower() == email.lower():
            return self.user
        return None

    async def get_by_id(self, *, user_id) -> User | None:
        if self.user and self.user.id == user_id:
            return self.user
        return None


class _FakeRefreshRepository:
    def __init__(self, auth_session: RefreshSession, credential: RefreshCredential):
        self.auth_session = auth_session
        self.credential = credential
        self.credentials_by_hash = {credential.token_hash: credential}

    async def get_credential_by_hash(self, *, token_hash: str):
        return self.credentials_by_hash.get(token_hash)

    async def get_session_by_id(self, *, session_id):
        if self.auth_session and self.auth_session.id == session_id:
            return self.auth_session
        return None

    async def revoke_session(self, *, session: RefreshSession):
        session.revoked_at = datetime.now(UTC)

    async def create_session(self, *, session):
        self.auth_session = session
        return session

    async def create_credential(self, *, credential):
        self.credentials_by_hash[credential.token_hash] = credential
        return credential


class AuthRegressionTests(unittest.TestCase):
    def setUp(self):
        self.password = "ValidSecretPass123!"
        self.password_hash = hash_password(password=self.password)
        self.user = User(
            id=uuid4(),
            name="Test User",
            email="testuser@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-AUTH01",
            role=UserRoleEnum.USER,
            password_hash=self.password_hash,
            is_verified=True,
            is_active=True,
        )

    # 1. Login with valid credentials
    def test_01_login_with_valid_credentials(self):
        async def run():
            session = _FakeDBSession()
            service = AuthService.__new__(AuthService)
            service.session = session
            service.user_repository = _FakeUserRepository(self.user)
            service.refresh_repository = _FakeRefreshRepository(None, None)

            access_token, refresh_token = await service.login_user(
                email=self.user.email,
                password=self.password,
            )
            self.assertTrue(access_token)
            self.assertTrue(refresh_token)
            payload = decode_token(access_token)
            self.assertEqual(payload["sub"], str(self.user.id))
            self.assertEqual(payload["role"], self.user.role.value)
            self.assertEqual(payload["type"], "access")

        asyncio.run(run())

    # 2. Login with incorrect password
    def test_02_login_with_incorrect_password(self):
        async def run():
            session = _FakeDBSession()
            service = AuthService.__new__(AuthService)
            service.session = session
            service.user_repository = _FakeUserRepository(self.user)

            with self.assertRaises(UnauthorizedError) as ctx:
                await service.login_user(
                    email=self.user.email,
                    password="WrongPassword999!",
                )
            self.assertEqual(ctx.exception.message, "Invalid email or password")

        asyncio.run(run())

    # 3. Login with an unregistered email/phone
    def test_03_login_with_unregistered_email(self):
        async def run():
            session = _FakeDBSession()
            service = AuthService.__new__(AuthService)
            service.session = session
            service.user_repository = _FakeUserRepository(None)

            with self.assertRaises(UnauthorizedError) as ctx:
                await service.login_user(
                    email="nonexistent@example.com",
                    password=self.password,
                )
            self.assertEqual(ctx.exception.message, "Invalid email or password")

        asyncio.run(run())

    # 4. Login with an inactive user
    def test_04_login_with_inactive_user(self):
        async def run():
            self.user.is_active = False
            session = _FakeDBSession()
            service = AuthService.__new__(AuthService)
            service.session = session
            service.user_repository = _FakeUserRepository(self.user)

            with self.assertRaises(UnauthorizedError) as ctx:
                await service.login_user(
                    email=self.user.email,
                    password=self.password,
                )
            self.assertEqual(ctx.exception.message, "Account is inactive. Please contact support.")

        asyncio.run(run())

    # 5. Login with missing required fields
    def test_05_login_with_missing_required_fields(self):
        with self.assertRaises(ValidationError):
            LoginRequest.model_validate({"email": "test@example.com"})

        with self.assertRaises(ValidationError):
            LoginRequest.model_validate({"password": "password123"})

        with self.assertRaises(ValidationError):
            LoginRequest.model_validate({})

    # 6. Login with malformed input
    def test_06_login_with_malformed_input(self):
        with self.assertRaises(ValidationError):
            LoginRequest.model_validate({"email": "not-a-valid-email", "password": "pass"})

    # 7. Access token generation
    def test_07_access_token_generation(self):
        session_id = uuid4()
        token = create_access_token(
            user_id=str(self.user.id),
            role=self.user.role.value,
            session_id=session_id,
        )
        claims = decode_token(token)
        self.assertEqual(claims["sub"], str(self.user.id))
        self.assertEqual(claims["role"], self.user.role.value)
        self.assertEqual(claims["sid"], str(session_id))
        self.assertEqual(claims["type"], "access")
        self.assertEqual(claims["iss"], settings.jwt_issuer)
        self.assertEqual(claims["aud"], settings.jwt_audience)
        self.assertTrue(claims["jti"])

    # 8. Refresh token generation
    def test_08_refresh_token_generation(self):
        token = create_refresh_token()
        self.assertTrue(isinstance(token, str))
        self.assertGreaterEqual(len(token), 32)
        hashed = hash_refresh_token(token)
        self.assertEqual(len(hashed), 64)
        # Opaque refresh token must NOT be decodable as JWT
        with self.assertRaises(UnauthorizedError):
            decode_token(token)

    # 9. Refresh token rotation
    def test_09_refresh_token_rotation(self):
        async def run():
            now = datetime.now(UTC)
            auth_session = RefreshSession(
                user_id=self.user.id,
                expires_at=now + timedelta(days=7),
                revoked_at=None,
            )
            auth_session.id = uuid4()

            token_1 = create_refresh_token()
            cred_1 = RefreshCredential(
                session_id=auth_session.id,
                token_hash=hash_refresh_token(token_1),
                expires_at=auth_session.expires_at,
                consumed_at=None,
            )

            session = _FakeDBSession()
            service = AuthService.__new__(AuthService)
            service.session = session
            service.refresh_repository = _FakeRefreshRepository(auth_session, cred_1)
            service.user_repository = _FakeUserRepository(self.user)

            # Rotate once
            new_access, token_2 = await service.refresh_tokens(refresh_token=token_1)
            self.assertTrue(new_access)
            self.assertNotEqual(token_1, token_2)
            self.assertIsNotNone(cred_1.consumed_at)

            # Reusing already-consumed token_1 must trigger revocation
            with self.assertRaises(UnauthorizedError):
                await service.refresh_tokens(refresh_token=token_1)
            self.assertIsNotNone(auth_session.revoked_at)

        asyncio.run(run())

    # 10. Logout and session revocation
    def test_10_logout_and_session_revocation(self):
        async def run():
            now = datetime.now(UTC)
            auth_session = RefreshSession(
                user_id=self.user.id,
                expires_at=now + timedelta(days=7),
                revoked_at=now,  # already revoked upon logout
            )
            auth_session.id = uuid4()

            token = create_refresh_token()
            cred = RefreshCredential(
                session_id=auth_session.id,
                token_hash=hash_refresh_token(token),
                expires_at=auth_session.expires_at,
                consumed_at=None,
            )

            session = _FakeDBSession()
            service = AuthService.__new__(AuthService)
            service.session = session
            service.refresh_repository = _FakeRefreshRepository(auth_session, cred)
            service.user_repository = _FakeUserRepository(self.user)

            with self.assertRaises(UnauthorizedError) as ctx:
                await service.refresh_tokens(refresh_token=token)
            self.assertEqual(ctx.exception.message, "Session has been revoked.")

        asyncio.run(run())

    # 11. Database errors handled correctly
    def test_11_database_errors_handled_correctly(self):
        async def run():
            class DummyRequest:
                method = "POST"
                url = type("URL", (), {"path": "/api/v1/auth/login"})()

            exc = ProgrammingError(
                statement="SELECT users.id FROM users WHERE users.email = :email",
                params={"email": "sensitive@example.com"},
                orig=Exception("column users.updated_by_user_id does not exist"),
            )

            response = await sqlalchemy_exception_handler(DummyRequest(), exc)
            self.assertEqual(response.status_code, 500)
            data = getattr(response, "body", None)
            import json
            body = json.loads(data.decode()) if data else {}
            self.assertFalse(body["success"])
            self.assertEqual(body["error_code"], "DATABASE_ERROR")
            self.assertEqual(body["message"], "A database error occurred")
            # Client response must NEVER leak table names, query strings, or sensitive params
            self.assertNotIn("updated_by_user_id", str(body))
            self.assertNotIn("sensitive@example.com", str(body))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

