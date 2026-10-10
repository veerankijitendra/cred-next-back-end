from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OTPChannel
from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.reference_id import generate_reference_id
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import User
from app.repositories.refresh_session import RefreshSessionRepository
from app.models.refresh_session import RefreshCredential, RefreshSession
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest, RegisterResponse
from app.services.notification import NotificationService
from app.services.otp import OTPService

class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repository = UserRepository(session=session)
        self.refresh_repository = RefreshSessionRepository(session=session)

    async def register_user(self, *, data: RegisterRequest) -> RegisterResponse:
        existing_email = await self.user_repository.get_by_email(email=data.email)

        if existing_email:
            raise ConflictError("Email is already registered.")

        existing_phone_number = await self.user_repository.get_by_phone_number(
            phone_number=data.phone_number
        )

        if existing_phone_number:
            raise ConflictError("Phone number is already registered.")

        user_id = uuid4()

        password_hash = hash_password(password=data.password)

        user = User(
            id=user_id,
            reference_id=generate_reference_id(user_id=user_id),
            name=data.name,
            email=data.email,
            phone_number=data.phone_number,
            password_hash=password_hash,
        )
        try:
            await self.user_repository.create(user=user)

            await self.session.commit()

        except IntegrityError:
            await self.session.rollback()

            raise ConflictError("Email or phone number is already registered.")

        except Exception:
            await self.session.rollback()
            raise

        await self.session.refresh(user)

        otp_service = OTPService(session=self.session)
        notification_service = NotificationService()

        otp = await otp_service.create_otp(user_id=user.id, channel=OTPChannel.PHONE)

        await self.session.commit()

        await notification_service.send_otp(
            channel=OTPChannel.PHONE, destination=user.phone_number, otp=otp
        )

        return RegisterResponse(
            user_id=user.id,
            reference_id=user.reference_id,
            verification_required=True,
            verification_channel=OTPChannel.PHONE,
        )

    async def login_user(self, *, email: str, password: str) -> tuple[str, str]:
        user = await self.user_repository.get_by_email(email=email)

        if not user:
            raise UnauthorizedError(message="Invalid email or password")

        if not user.password_hash:
            raise UnauthorizedError(message="Invalid email or password")

        if not verify_password(password=password, password_hash=user.password_hash):
            raise UnauthorizedError(message="Invalid email or password")

        if not user.is_verified:
            raise ForbiddenError(
                message="Please verify your account before logging in."
            )

        now = datetime.now(UTC)
        auth_session = RefreshSession(
            user_id=user.id,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
        await self.refresh_repository.create_session(auth_session=auth_session)
        refresh_token = create_refresh_token()
        await self.refresh_repository.create_credential(
            credential=RefreshCredential(
                session_id=auth_session.id,
                token_hash=hash_refresh_token(refresh_token),
                expires_at=auth_session.expires_at,
            )
        )
        access_token = create_access_token(
            user_id=str(user.id), role=str(user.role), session_id=auth_session.id
        )
        await self.session.commit()

        return access_token, refresh_token

    async def refresh_tokens(self, *, refresh_token: str) -> tuple[str, str]:
        token_hash = hash_refresh_token(refresh_token)
        credential = await self.refresh_repository.get_credential(token_hash=token_hash)
        if credential is None:
            raise UnauthorizedError(message="Invalid refresh session.")

        auth_session = await self.refresh_repository.get_session(
            session_id=credential.session_id, for_update=True
        )
        if auth_session is None:
            raise UnauthorizedError(message="Invalid refresh session.")

        # Re-read after taking the session lock so concurrent refreshes serialize.
        credential = await self.refresh_repository.get_credential(token_hash=token_hash)
        if credential is None:
            raise UnauthorizedError(message="Invalid refresh session.")

        now = datetime.now(UTC)
        if credential.consumed_at is not None:
            if auth_session.revoked_at is None:
                auth_session.revoked_at = now
                await self.session.commit()
            raise UnauthorizedError(message="Refresh token reuse detected; session revoked.")
        if auth_session.revoked_at is not None or auth_session.expires_at <= now or credential.expires_at <= now:
            raise UnauthorizedError(message="Refresh session is expired or revoked.")

        user = await self.user_repository.get_by_id(user_id=auth_session.user_id)
        if user is None:
            auth_session.revoked_at = now
            await self.session.commit()
            raise UnauthorizedError(message="Invalid refresh session.")

        new_refresh_token = create_refresh_token()
        credential.consumed_at = now
        await self.refresh_repository.create_credential(
            credential=RefreshCredential(
                session_id=auth_session.id,
                token_hash=hash_refresh_token(new_refresh_token),
                expires_at=auth_session.expires_at,
            )
        )
        access_token = create_access_token(
            user_id=str(user.id), role=str(user.role), session_id=auth_session.id
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return access_token, new_refresh_token

    async def logout_user(self, *, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        credential = await self.refresh_repository.get_credential(
            token_hash=hash_refresh_token(refresh_token)
        )
        if credential is None:
            return
        auth_session = await self.refresh_repository.get_session(
            session_id=credential.session_id, for_update=True
        )
        if auth_session is not None and auth_session.revoked_at is None:
            auth_session.revoked_at = datetime.now(UTC)
            await self.session.commit()
