import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import OTPChannel
from app.core.exceptions import TooManyRequestsError, UnauthorizedError
from app.core.security import hash_otp, verify_otp
from app.models.otp import OTPVerification
from app.repositories.otp import OTPRepository


class OTPService:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session
        self.repository = OTPRepository(session=session)

    def _generate_otp(self) -> str:
        minimum = 10 ** (settings.otp_length - 1)
        maximum = (10**settings.otp_length) - 1

        return str(secrets.randbelow(maximum - minimum + 1) + minimum)

    async def create_otp(self, *, user_id: UUID, channel: OTPChannel) -> str:
        otp = self._generate_otp()
        otp_hash = hash_otp(otp=otp)

        expires_at = datetime.now(UTC) + timedelta(minutes=settings.otp_expire_minutes)

        otp_verification = OTPVerification(
            user_id=user_id, channel=channel, otp_hash=otp_hash, expires_at=expires_at
        )
        await self.repository.create(otp_verification=otp_verification)

        return otp

    async def verify(self, user_id: UUID, channel: OTPChannel, otp: str) -> bool:
        verification = await self.repository.get_latest(
            user_id=user_id, channel=channel
        )

        if not verification:
            raise UnauthorizedError(message="OTP is invalid or expired")

        if verification.expires_at < datetime.now(UTC):
            raise UnauthorizedError(message="OTP is invalid or expired")

        if verification.attempts >= settings.otp_max_attempts:
            raise UnauthorizedError(message="Maximum OTP attempts exceeded")

        if not verify_otp(otp=otp, otp_hash=verification.otp_hash):
            await self.repository.increment_attempts(otp_verification=verification)

            raise UnauthorizedError(message="Invalid OTP")

        await self.repository.mark_used(otp_verification=verification)

        return True

    async def resend(self, user_id: UUID, channel: OTPChannel) -> str:

        latest_otp = await self.repository.get_latest(user_id=user_id, channel=channel)

        now = datetime.now(UTC)

        if latest_otp:
            cooldown_until = latest_otp.created_at + timedelta(
                seconds=settings.otp_resend_cooldown_seconds
            )

            if now < cooldown_until:
                remaining_seconds = int((cooldown_until - now).total_seconds())

                raise TooManyRequestsError(
                    message=f"Please wait {remaining_seconds} seconds before requesting a new OTP"
                )
            await self.repository.invalidate(otp_verification=latest_otp)

        return await self.create_otp(user_id=user_id, channel=channel)
