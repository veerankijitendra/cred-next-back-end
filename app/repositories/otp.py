from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OTPChannel
from app.models.otp import OTPVerification


class OTPRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session

    async def get_latest(
        self, *, user_id: UUID, channel: OTPChannel, for_update: bool = False
    ) -> OTPVerification | None:
        statement = (
            select(OTPVerification)
            .where(
                OTPVerification.user_id == user_id,
                OTPVerification.channel == channel.value,
                OTPVerification.is_used.is_(False),
            )
            .order_by(OTPVerification.created_at.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def create(self, *, otp_verification: OTPVerification) -> OTPVerification:
        self.session.add(otp_verification)
        await self.session.flush()

        return otp_verification

    async def mark_used(self, *, otp_verification: OTPVerification) -> OTPVerification:
        otp_verification.is_used = True

        await self.session.flush()

        return otp_verification

    async def increment_attempts(
        self, *, otp_verification: OTPVerification
    ) -> OTPVerification:
        otp_verification.attempts += 1

        await self.session.flush()

        return otp_verification

    async def invalidate(self, *, otp_verification: OTPVerification) -> OTPVerification:
        otp_verification.is_used = True

        await self.session.flush()

        return otp_verification

    async def get_by_id(self, *, user_id: UUID) -> OTPVerification | None:
        result = await self.session.execute(
            select(OTPVerification).where(OTPVerification.user_id == user_id)
        )
        return result.scalar_one_or_none()
