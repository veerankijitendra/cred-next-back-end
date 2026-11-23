import logging

from app.core.constants import OTPChannel
from app.services.email import ResendEmailService

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, email_service: ResendEmailService | None = None) -> None:
        self.email_service = email_service or ResendEmailService()

    async def send_otp(
        self, *, channel: OTPChannel, destination: str, otp: str
    ) -> bool:

        if channel == OTPChannel.PHONE:
            return await self._send_phone_otp(phone_number=destination, otp=otp)

        if channel == OTPChannel.EMAIL:
            return await self._send_email_otp(email=destination, otp=otp)

        return False

    async def _send_phone_otp(self, *, phone_number: str, otp: str) -> bool:
        # TODO: When an SMS provider (e.g. Twilio, AWS SNS) is configured, dispatch via its API client here.
        logger.info(
            "🔐 [DEV OTP DELIVERY] Channel: PHONE | Destination: %s | OTP Code: %s",
            phone_number,
            otp,
            extra={
                "event": "otp.dev_delivery",
                "channel": OTPChannel.PHONE.value,
            },
        )
        return True

    async def _send_email_otp(self, *, email: str, otp: str) -> bool:

        return await self.email_service.send_otp_email(recipient_email=email, otp=otp)
