from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import OTPChannel
from app.db.base import Base
from app.db.mixins import BaseModelMixin


class OTPVerification(Base, BaseModelMixin):
    __tablename__ = "otp_verification"

    def __init__(
        self,
        *,
        user_id: UUID,
        channel: OTPChannel,
        otp_hash: str,
        expires_at: datetime,
        attempts: int = 1,
        is_used: bool = False,
    ):
        self.user_id = user_id
        self.channel = channel
        self.otp_hash = otp_hash
        self.expires_at = expires_at
        self.attempts = attempts
        self.is_used = is_used

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    channel: Mapped[OTPChannel] = mapped_column(
        Enum(
            OTPChannel,
            native_enum=False,
            values_callable=lambda channels: [channel.value for channel in channels],
        ),
        nullable=False,
    )

    otp_hash: Mapped[str] = mapped_column(String(300), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
