import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import settings
from app.core.constants import OTPChannel
from app.schemas.auth import RegisterRequest
from app.services.auth import AuthService
from app.services.email import ResendEmailService
from app.services.notification import NotificationService
from app.services.otp import OTPService


def run_coroutine(coro):
    stack = [coro]
    val = None
    while stack:
        try:
            res = stack[-1].send(val)
            stack.append(res)
            val = None
        except StopIteration as e:
            stack.pop()
            val = e.value
        except Exception:
            raise
    return val


class _FakeDBSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        pass

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True
        return None

    async def rollback(self):
        self.rolled_back = True
        return None

    async def refresh(self, obj):
        return None


class _FakeUserRepository:
    def __init__(self, users=None):
        self.users = {str(u.id): u for u in users or []}

    async def get_by_id(self, *, user_id):
        return self.users.get(str(user_id))

    async def get_by_email(self, *, email: str):
        for u in self.users.values():
            if u.email.lower() == email.lower():
                return u
        return None

    async def get_by_phone_number(self, *, phone_number: str):
        for u in self.users.values():
            if u.phone_number == phone_number:
                return u
        return None

    async def create(self, *, user):
        self.users[str(user.id)] = user
        return user


class _FakeOTPRepository:
    def __init__(self, otps=None):
        self.otps = list(otps or [])

    async def get_latest(self, *, user_id, channel, for_update=False):
        matching = [
            o for o in self.otps
            if o.user_id == user_id and o.channel == channel and not o.is_used
        ]
        if not matching:
            return None
        return sorted(matching, key=lambda x: x.created_at, reverse=True)[0]

    async def create(self, *, otp_verification):
        self.otps.append(otp_verification)
        return otp_verification

    async def invalidate(self, *, otp_verification):
        otp_verification.is_used = True
        return otp_verification


class EmailOTPTests(unittest.TestCase):
    def test_render_otp_html_and_text(self):
        service = ResendEmailService(api_key="re_test_123")
        html = service._render_otp_html(otp="482915")
        text = service._render_otp_text(otp="482915")

        self.assertIn("482915", html)
        self.assertIn("CRED HEXA", html)
        self.assertIn("5 minutes", html)

        self.assertIn("482915", text)
        self.assertIn("CRED HEXA", text)
        self.assertIn("5 minutes", text)

    @patch.object(settings, "resend_api_key", None)
    def test_send_otp_email_without_api_key_falls_back_to_dev(self):
        service = ResendEmailService(api_key=None)
        delivered = run_coroutine(
            service.send_otp_email(recipient_email="test@example.com", otp="123456")
        )
        self.assertTrue(delivered)

    @patch("resend.Emails.send")
    def test_send_otp_email_with_resend_sdk_success(self, mock_send):
        mock_send.return_value = {"id": "re_msg_test_abc123"}

        service = ResendEmailService(
            api_key="re_valid_api_key_123",
            from_email="CRED NEXT <onboarding@resend.dev>",
        )

        delivered = run_coroutine(
            service.send_otp_email(
                recipient_email="user@crednext.com", otp="987654"
            )
        )

        self.assertTrue(delivered)
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0][0]
        self.assertEqual(call_args["from"], "CRED NEXT <onboarding@resend.dev>")
        self.assertEqual(call_args["to"], ["user@crednext.com"])
        self.assertIn("987654", call_args["subject"])
        self.assertIn("987654", call_args["html"])
        self.assertIn("987654", call_args["text"])

    @patch("resend.Emails.send")
    def test_send_otp_email_with_resend_sdk_error(self, mock_send):
        mock_send.side_effect = RuntimeError("Resend API network timeout")

        service = ResendEmailService(
            api_key="re_test_key",
            from_email="CRED NEXT <onboarding@resend.dev>",
        )

        delivered = run_coroutine(
            service.send_otp_email(
                recipient_email="user@crednext.com", otp="112233"
            )
        )

        self.assertFalse(delivered)

    def test_notification_service_dispatches_email(self):
        mock_email_service = MagicMock(spec=ResendEmailService)
        async def fake_send(recipient_email, otp):
            return True
        mock_email_service.send_otp_email = MagicMock(side_effect=fake_send)

        notif_service = NotificationService(email_service=mock_email_service)

        delivered = run_coroutine(
            notif_service.send_otp(
                channel=OTPChannel.EMAIL, destination="partner@example.com", otp="554433"
            )
        )

        self.assertTrue(delivered)
        mock_email_service.send_otp_email.assert_called_once_with(
            recipient_email="partner@example.com", otp="554433"
        )

    def test_registration_defaults_to_email_otp(self):
        session = _FakeDBSession()
        user_repo = _FakeUserRepository([])
        otp_repo = _FakeOTPRepository([])
        otp_service = OTPService(session=session, repository=otp_repo)

        mock_email_service = MagicMock(spec=ResendEmailService)
        async def fake_send(recipient_email, otp):
            return True
        mock_email_service.send_otp_email = MagicMock(side_effect=fake_send)

        notif_service = NotificationService(email_service=mock_email_service)

        auth_service = AuthService(
            session=session,
            otp_service=otp_service,
            notification_service=notif_service,
        )
        auth_service.user_repository = user_repo

        reg_data = RegisterRequest(
            name="Aarav Patel",
            email="aarav.patel@example.com",
            phone_number="9876543210",
            password="SecurePassword123!",
        )

        res = run_coroutine(auth_service.register_user(data=reg_data))

        self.assertTrue(res.verification_required)
        self.assertEqual(res.verification_channel, OTPChannel.EMAIL)
        mock_email_service.send_otp_email.assert_called_once()
        call_kwargs = mock_email_service.send_otp_email.call_args[1]
        self.assertEqual(call_kwargs["recipient_email"], "aarav.patel@example.com")
        self.assertEqual(len(call_kwargs["otp"]), 6)


if __name__ == "__main__":
    unittest.main()
