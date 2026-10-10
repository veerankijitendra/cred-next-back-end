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
        logger.warning("OTP delivery is not configured; no phone message was sent, phone number: %s, otp: %s", phone_number, otp)
        return False

    async def _send_email_otp(self, *, email: str, otp: str) -> bool:
        logger.warning("OTP delivery is not configured; no email message was sent, email: %s, otp: %s", email, otp)
        return False
