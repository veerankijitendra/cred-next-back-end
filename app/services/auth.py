from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OTPChannel
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest, RegisterResponse
from app.services.notification import NotificationService
from app.services.otp import OTPService


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repository = UserRepository(session=session)

    async def register_user(self, *, data: RegisterRequest) -> RegisterResponse:
        existing_email = await self.user_repository.get_by_email(email=data.email)

        if existing_email:
            raise ConflictError("Email is already registered.")

        existing_phone_number = await self.user_repository.get_by_phone_number(
            phone_number=data.phone_number
        )

        if existing_phone_number:
            raise ConflictError("Phone number is already registered.")

        password_hash = hash_password(password=data.password)

        user = User(
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

        access_token, refresh_token = self._get_access_refresh_token(
            user_id=str(user.id), role=user.role
        )

        await self._save_refresh_token(user=user, refresh_token=refresh_token)

        return access_token, refresh_token

    def _get_access_refresh_token(self, user_id: str, role: str) -> tuple[str, str]:
        access_token = create_access_token(user_id=user_id, role=role)
        refresh_token = create_access_token(user_id=user_id, role=role)

        return access_token, refresh_token

    async def _save_refresh_token(self, *, user: User, refresh_token: str):
        refresh_token_hash = hash_refresh_token(refresh_token=refresh_token)

        try:
            await self.user_repository.update_refresh_token_hash(
                user=user, refresh_token_hash=refresh_token_hash
            )
            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise

    def _get_user_uuid(self, *, user_id: str) -> UUID:
        try:
            user_uuid = UUID(user_id)
        except ValueError as exc:
            raise UnauthorizedError(message="Invalid user ID.") from exc

        return user_uuid

    async def refresh_tokens(self, user_id: str, refresh_token: str) -> tuple[str, str]:
        user_uuid = self._get_user_uuid(user_id=user_id)

        user = await self.user_repository.get_by_id(user_id=user_uuid)

        if not user:
            raise UnauthorizedError(message="Invalid refresh token.")

        if not user.refresh_token_hash:
            raise UnauthorizedError(message="Refresh token is revoked.")

        if not verify_refresh_token(
            refresh_token=refresh_token, refresh_token_hash=user.refresh_token_hash
        ):
            raise UnauthorizedError(message="Invalid refresh token.")

        access_token, new_refresh_token = self._get_access_refresh_token(
            user_id=str(user.id), role=user.role
        )

        await self._save_refresh_token(user=user, refresh_token=new_refresh_token)

        return access_token, new_refresh_token

    async def logout_user(self, user_id: str):
        user_uuid = self._get_user_uuid(user_id=user_id)

        user = await self.user_repository.get_by_id(user_id=user_uuid)

        if not user:
            raise UnauthorizedError(message="User not found.")

        user.refresh_token_hash = None

        try:
            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise
