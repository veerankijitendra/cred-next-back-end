import logging

from app.core.constants import OTPChannel

logger = logging.getLogger(__name__)


class NotificationService:
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
        # TODO: When an Email provider (e.g. SendGrid, AWS SES) is configured, dispatch via its API client here.
        logger.info(
            "🔐 [DEV OTP DELIVERY] Channel: EMAIL | Destination: %s | OTP Code: %s",
            email,
            otp,
            extra={
                "event": "otp.dev_delivery",
                "channel": OTPChannel.EMAIL.value,
            },
        )
        return True
