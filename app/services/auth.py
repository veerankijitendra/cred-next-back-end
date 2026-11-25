from datetime import UTC, datetime, timedelta
import logging
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OTPChannel, normalize_acquisition_source
from app.core.config import settings
from app.core.exceptions import (
    AccountUnverifiedError,
    ConflictError,
    ForbiddenError,
    TooManyRequestsError,
    UnauthorizedError,
)
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
from app.repositories.acquisition_source import AcquisitionSourceRepository
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest, RegisterResponse
from app.services.notification import NotificationService
from app.services.otp import OTPService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        otp_service: OTPService | None = None,
        notification_service: NotificationService | None = None,
        acquisition_source_repository: AcquisitionSourceRepository | None = None,
    ):
        self.session = session
        self.user_repository = UserRepository(session=session)
        self.refresh_repository = RefreshSessionRepository(session=session)
        self.otp_service = otp_service or OTPService(session=session)
        self.notification_service = notification_service or NotificationService()
        self.acquisition_source_repository = acquisition_source_repository or (
            AcquisitionSourceRepository(session=session)
            if session is not None and hasattr(session, "execute")
            else None
        )

    async def register_user(self, *, data: RegisterRequest) -> RegisterResponse:
        existing_email = await self.user_repository.get_by_email(email=data.email)
        existing_phone_number = await self.user_repository.get_by_phone_number(
            phone_number=data.phone_number
        )

        otp_service = self.otp_service
        notification_service = self.notification_service

        if existing_email:
            if existing_email.is_verified:
                raise ConflictError("Email is already registered.")

            # Email exists and is unverified: user is retrying or updating registration
            if existing_phone_number and existing_phone_number.id != existing_email.id:
                if existing_phone_number.is_verified:
                    raise ConflictError("Phone number is already registered.")
                # The phone number belongs to another unverified placeholder; clean it up
                await self.user_repository.delete(user=existing_phone_number)

            phone_changed = existing_email.phone_number != data.phone_number

            channel = settings.default_otp_channel
            # Enforce cooldown on the same destination to avoid OTP spamming
            cooldown_check_needed = (channel == OTPChannel.PHONE and not phone_changed) or (channel == OTPChannel.EMAIL)
            if cooldown_check_needed:
                latest_otp = await otp_service.repository.get_latest(
                    user_id=existing_email.id, channel=channel, for_update=True
                )
                if latest_otp:
                    now = datetime.now(UTC)
                    cooldown_until = latest_otp.created_at + timedelta(
                        seconds=settings.otp_resend_cooldown_seconds
                    )
                    if now < cooldown_until:
                        remaining_seconds = int((cooldown_until - now).total_seconds())
                        raise TooManyRequestsError(
                            message=f"Please wait {remaining_seconds} seconds before requesting a new OTP"
                        )
                    await otp_service.repository.invalidate(otp_verification=latest_otp)

            existing_email.name = data.name
            existing_email.phone_number = data.phone_number
            existing_email.password_hash = hash_password(password=data.password)
            if data.source:
                existing_email.source = (
                    await self.acquisition_source_repository.resolve_source_name(
                        raw_source=data.source
                    )
                    if self.acquisition_source_repository is not None
                    else normalize_acquisition_source(data.source)
                )

            user = existing_email
            is_resume = True
        else:
            if existing_phone_number:
                if existing_phone_number.is_verified:
                    raise ConflictError("Phone number is already registered.")
                # Unverified record with different email; clean up stale record
                await self.user_repository.delete(user=existing_phone_number)

            user_id = uuid4()
            password_hash = hash_password(password=data.password)
            resolved_source = (
                await self.acquisition_source_repository.resolve_source_name(
                    raw_source=data.source
                )
                if self.acquisition_source_repository is not None
                else normalize_acquisition_source(data.source)
            )

            user = User(
                id=user_id,
                reference_id=generate_reference_id(user_id=user_id),
                name=data.name,
                email=data.email,
                phone_number=data.phone_number,
                password_hash=password_hash,
                is_verified=False,
                is_active=False,
                source=resolved_source,
            )
            is_resume = False

        try:
            if is_resume:
                await self.session.flush()
            else:
                await self.user_repository.create(user=user)

            await self.session.commit()

        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("Email or phone number is already registered.")

        except Exception:
            await self.session.rollback()
            raise

        await self.session.refresh(user)

        channel = settings.default_otp_channel
        otp = await otp_service.create_otp(user_id=user.id, channel=channel)

        await self.session.commit()

        destination = user.email if channel == OTPChannel.EMAIL else user.phone_number
        await notification_service.send_otp(
            channel=channel, destination=destination, otp=otp
        )

        return RegisterResponse(
            user_id=user.id,
            reference_id=user.reference_id,
            verification_required=True,
            verification_channel=channel,
        )

    async def login_user(self, *, email: str, password: str) -> tuple[str, str]:
        user = await self.user_repository.get_by_email(email=email)

        if not user:
            logger.warning(
                "Login failed",
                extra={"event": "auth.login_failed", "reason": "invalid_credentials"},
            )
            raise UnauthorizedError(message="Invalid email or password")

        if not user.password_hash:
            logger.warning(
                "Login failed",
                extra={"event": "auth.login_failed", "reason": "invalid_credentials"},
            )
            raise UnauthorizedError(message="Invalid email or password")

        if not verify_password(password=password, password_hash=user.password_hash):
            logger.warning(
                "Login failed",
                extra={"event": "auth.login_failed", "reason": "invalid_credentials"},
            )
            raise UnauthorizedError(message="Invalid email or password")

        if not user.is_verified:
            logger.warning(
                "Login failed",
                extra={
                    "event": "auth.login_failed",
                    "reason": "account_unverified",
                    "user_id": str(user.id),
                },
            )
            raise AccountUnverifiedError(
                message="Please verify your account before logging in.",
                user_id=str(user.id),
                channel=settings.default_otp_channel.value,
            )

        if not user.is_active:
            logger.warning(
                "Login failed",
                extra={
                    "event": "auth.login_failed",
                    "reason": "account_inactive",
                    "user_id": str(user.id),
                },
            )
            raise ForbiddenError(
                message="Your account has been deactivated. Please contact an administrator."
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

        logger.info(
            "Login succeeded",
            extra={"event": "auth.login_succeeded", "user_id": str(user.id)},
        )

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
            logger.warning(
                "Refresh token reuse detected; session revoked",
                extra={
                    "event": "auth.refresh_token_reuse",
                    "user_id": str(auth_session.user_id),
                },
            )
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
