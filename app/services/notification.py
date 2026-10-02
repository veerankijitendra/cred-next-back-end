from app.core.constants import OTPChannel


class NotificationService:
    async def send_otp(
        self, *, channel: OTPChannel, destination: str, otp: str
    ) -> None:

        if channel == OTPChannel.PHONE:
            await self._send_phone_otp(phone_number=destination, otp=otp)
            return

        if channel == OTPChannel.EMAIL:
            await self._send_email_otp(email=destination, otp=otp)

    async def _send_phone_otp(self, *, phone_number: str, otp: str) -> None:
        print(f"[DEV] OTP for {phone_number}: {otp}")

    async def _send_email_otp(self, *, email: str, otp: str) -> None:
        print(f"[DEV] OTP for {email}: {otp}")
