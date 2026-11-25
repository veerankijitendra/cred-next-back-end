import asyncio
import logging
from typing import Any
import resend

from app.core.config import settings

logger = logging.getLogger(__name__)


class ResendEmailService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        from_email: str | None = None,
    ) -> None:
        self.api_key = api_key or (
            settings.resend_api_key.get_secret_value()
            if settings.resend_api_key
            else None
        )
        self.from_email = from_email or settings.resend_from_email

    def _render_otp_html(self, *, otp: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Your CRED HEXA Verification Code</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 40px 16px;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
    <div style="background: #1e1b4b; padding: 28px 32px; text-align: center;">
      <h1 style="color: #ffffff; font-size: 24px; font-weight: 800; letter-spacing: 1px; margin: 0;">CRED HEXA</h1>
      <p style="color: #a5b4fc; font-size: 13px; margin: 6px 0 0 0;">Financial Growth & Referral Platform</p>
    </div>
    <div style="padding: 32px 32px 24px 32px; color: #334155;">
      <h2 style="font-size: 18px; font-weight: 700; color: #0f172a; margin-top: 0;">Verify Your Email Address</h2>
      <p style="font-size: 14px; line-height: 1.6; color: #475569; margin: 12px 0 24px 0;">
        Please enter the verification code below to complete your account setup. This code is confidential and expires in <strong>{settings.otp_expire_minutes} minutes</strong>.
      </p>
      <div style="background: #f1f5f9; border-radius: 8px; border: 1px dashed #cbd5e1; padding: 18px; text-align: center; margin: 24px 0;">
        <span style="font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 800; letter-spacing: 10px; color: #312e81;">{otp}</span>
      </div>
      <p style="font-size: 13px; color: #64748b; line-height: 1.5; margin: 20px 0 0 0;">
        ⚠️ If you did not request this verification code, please ignore this email or reach out to our security team.
      </p>
    </div>
    <div style="background: #f8fafc; padding: 16px 32px; border-top: 1px solid #e2e8f0; text-align: center;">
      <p style="font-size: 12px; color: #94a3b8; margin: 0;">&copy; CRED HEXA. All rights reserved.</p>
    </div>
  </div>
</body>
</html>"""

    def _render_otp_text(self, *, otp: str) -> str:
        return (
            f"Your CRED HEXA verification code is: {otp}\n\n"
            f"This code will expire in {settings.otp_expire_minutes} minutes.\n"
            f"If you did not request this code, please ignore this message."
        )

    def _sync_send(self, params: dict[str, Any]) -> dict[str, Any]:
        """Synchronously dispatch email using Resend SDK."""
        resend.api_key = self.api_key
        return resend.Emails.send(params)

    async def send_otp_email(self, *, recipient_email: str, otp: str) -> bool:

        if not self.api_key:

            logger.info(
                "🔐 [DEV OTP DELIVERY] Channel: EMAIL | Destination: %s | OTP Code: %s (Resend API key not configured)",
                recipient_email,
                otp,
                extra={"event": "otp.dev_delivery", "channel": "email"},
            )
            return True

        params: dict[str, Any] = {
            "from": self.from_email,
            "to": [recipient_email],
            "subject": f"{otp} is your CRED HEXA verification code",
            "html": self._render_otp_html(otp=otp),
            "text": self._render_otp_text(otp=otp),
        }

        try:
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, self._sync_send, params)

            except RuntimeError:
                result = self._sync_send(params)

            email_id = (
                result.get("id")
                if isinstance(result, dict)
                else getattr(result, "id", None)
            )
            logger.info(
                "OTP email dispatched via Resend SDK",
                extra={
                    "event": "email.otp_sent",
                    "resend_id": email_id,
                    "recipient": recipient_email,
                },
            )
            return True
        except Exception as exc:
            print("jitendra=====>", exc)
            logger.error(
                "Exception occurred while sending email via Resend SDK",
                exc_info=exc,
            )
            return False
