import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.constants import OTPChannel
from app.core.exceptions import (
    AccountUnverifiedError,
    ConflictError,
    TooManyRequestsError,
)
from app.core.security import hash_password, verify_password
from app.models.otp import OTPVerification
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.services.auth import AuthService
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
    return val


class _FakeDBSession:
    def __init__(self):
        self.deleted_objects = []
        self.added_objects = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added_objects.append(obj)

    async def delete(self, obj):
        self.deleted_objects.append(obj)

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
    def __init__(self, users: list[User] | None = None):
        self.users: dict[str, User] = {}
        for u in users or []:
            self.users[str(u.id)] = u

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

    async def create(self, *, user: User):
        self.users[str(user.id)] = user
        return user

    async def delete(self, *, user: User):
        self.users.pop(str(user.id), None)


class _FakeOTPRepository:
    def __init__(self, otps: list[OTPVerification] | None = None):
        self.otps: list[OTPVerification] = list(otps or [])

    async def get_latest(self, *, user_id, channel, for_update=False):
        matching = [
            o for o in self.otps
            if o.user_id == user_id and o.channel == channel and not o.is_used
        ]
        if not matching:
            return None
        return sorted(matching, key=lambda x: x.created_at, reverse=True)[0]

    async def create(self, *, otp_verification: OTPVerification):
        self.otps.append(otp_verification)
        return otp_verification

    async def invalidate(self, *, otp_verification: OTPVerification):
        otp_verification.is_used = True
        return otp_verification


class _FakeNotificationService:
    def __init__(self):
        self.sent_otps = []

    async def send_otp(self, *, channel, destination, otp):
        self.sent_otps.append({"channel": channel, "destination": destination, "otp": otp})
        return True


class UnverifiedRegistrationTests(unittest.TestCase):
    def test_fresh_user_registration(self):
        session = _FakeDBSession()
        user_repo = _FakeUserRepository([])
        otp_repo = _FakeOTPRepository([])
        otp_service = OTPService(session=session, repository=otp_repo)
        notif_service = _FakeNotificationService()

        service = AuthService(session=session, otp_service=otp_service, notification_service=notif_service)
        service.user_repository = user_repo

        reg_request = RegisterRequest(
            name="Vikram Seth",
            email="vikram@example.com",
            phone_number="9876543210",
            password="SecurePassword123!",
        )

        response = run_coroutine(service.register_user(data=reg_request))
        self.assertTrue(response.verification_required)
        self.assertEqual(response.verification_channel, OTPChannel.PHONE)

        created_user = run_coroutine(user_repo.get_by_email(email="vikram@example.com"))
        self.assertIsNotNone(created_user)
        self.assertFalse(created_user.is_verified)
        self.assertEqual(created_user.name, "Vikram Seth")
        self.assertTrue(verify_password(password="SecurePassword123!", password_hash=created_user.password_hash))
        self.assertEqual(len(notif_service.sent_otps), 1)

    def test_verified_user_registration_conflict(self):
        verified_user = User(
            id=uuid4(),
            name="Existing Verified",
            email="verified@example.com",
            phone_number="9123456789",
            reference_id="CNX-VERIFIED",
            password_hash=hash_password(password="OldPassword123!"),
            is_verified=True,
        )
        session = _FakeDBSession()
        user_repo = _FakeUserRepository([verified_user])
        otp_repo = _FakeOTPRepository([])
        otp_service = OTPService(session=session, repository=otp_repo)
        notif_service = _FakeNotificationService()

        service = AuthService(session=session, otp_service=otp_service, notification_service=notif_service)
        service.user_repository = user_repo

        reg_request = RegisterRequest(
            name="Existing Verified Retry",
            email="verified@example.com",
            phone_number="9123456789",
            password="NewPassword123!",
        )

        with self.assertRaises(ConflictError) as ctx:
            run_coroutine(service.register_user(data=reg_request))
        self.assertIn("Email is already registered", str(ctx.exception))

    def test_unverified_user_re_registration_resumes_and_updates(self):
        old_user_id = uuid4()
        unverified_user = User(
            id=old_user_id,
            name="Rahul Old",
            email="rahul@example.com",
            phone_number="9876500000",
            reference_id="CNX-RAHUL01",
            password_hash=hash_password(password="OldPassword123!"),
            is_verified=False,
        )
        old_otp = OTPVerification(
            user_id=old_user_id,
            channel=OTPChannel.PHONE,
            otp_hash="old_hash",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        old_otp.created_at = datetime.now(UTC) - timedelta(minutes=5)

        session = _FakeDBSession()
        user_repo = _FakeUserRepository([unverified_user])
        otp_repo = _FakeOTPRepository([old_otp])
        otp_service = OTPService(session=session, repository=otp_repo)
        notif_service = _FakeNotificationService()

        service = AuthService(session=session, otp_service=otp_service, notification_service=notif_service)
        service.user_repository = user_repo

        reg_request = RegisterRequest(
            name="Rahul Sharma",
            email="rahul@example.com",
            phone_number="9876511111",
            password="BrandNewPassword123!",
        )

        response = run_coroutine(service.register_user(data=reg_request))

        self.assertEqual(response.user_id, old_user_id)
        self.assertEqual(response.reference_id, "CNX-RAHUL01")
        self.assertTrue(response.verification_required)

        updated = run_coroutine(user_repo.get_by_email(email="rahul@example.com"))
        self.assertEqual(updated.name, "Rahul Sharma")
        self.assertEqual(updated.phone_number, "9876511111")
        self.assertTrue(verify_password(password="BrandNewPassword123!", password_hash=updated.password_hash))
        self.assertFalse(updated.is_verified)
        self.assertEqual(len(notif_service.sent_otps), 1)
        self.assertEqual(notif_service.sent_otps[0]["destination"], "9876511111")

    def test_unverified_user_phone_conflict_with_verified_user(self):
        verified_user = User(
            id=uuid4(),
            name="Verified Owner",
            email="owner@example.com",
            phone_number="9998887776",
            reference_id="CNX-OWNER",
            is_verified=True,
        )
        unverified_user = User(
            id=uuid4(),
            name="Unverified User",
            email="unverified@example.com",
            phone_number="9876543210",
            reference_id="CNX-UNVERIFIED",
            is_verified=False,
        )

        session = _FakeDBSession()
        user_repo = _FakeUserRepository([verified_user, unverified_user])
        otp_repo = _FakeOTPRepository([])
        otp_service = OTPService(session=session, repository=otp_repo)
        notif_service = _FakeNotificationService()

        service = AuthService(session=session, otp_service=otp_service, notification_service=notif_service)
        service.user_repository = user_repo

        reg_request = RegisterRequest(
            name="Unverified User",
            email="unverified@example.com",
            phone_number="9998887776",
            password="Password123!",
        )

        with self.assertRaises(ConflictError) as ctx:
            run_coroutine(service.register_user(data=reg_request))
        self.assertIn("Phone number is already registered", str(ctx.exception))

    def test_unverified_user_cooldown_enforcement(self):
        user_id = uuid4()
        unverified_user = User(
            id=user_id,
            name="Rapid User",
            email="rapid@example.com",
            phone_number="9811122233",
            reference_id="CNX-RAPID",
            is_verified=False,
        )
        recent_otp = OTPVerification(
            user_id=user_id,
            channel=OTPChannel.PHONE,
            otp_hash="recent_hash",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        recent_otp.created_at = datetime.now(UTC) - timedelta(seconds=10)

        session = _FakeDBSession()
        user_repo = _FakeUserRepository([unverified_user])
        otp_repo = _FakeOTPRepository([recent_otp])
        otp_service = OTPService(session=session, repository=otp_repo)
        notif_service = _FakeNotificationService()

        service = AuthService(session=session, otp_service=otp_service, notification_service=notif_service)
        service.user_repository = user_repo

        reg_request = RegisterRequest(
            name="Rapid User",
            email="rapid@example.com",
            phone_number="9811122233",
            password="Password123!",
        )

        with self.assertRaises(TooManyRequestsError) as ctx:
            run_coroutine(service.register_user(data=reg_request))
        self.assertIn("Please wait", str(ctx.exception))

    def test_unverified_user_login_raises_account_unverified_error(self):
        user_id = uuid4()
        unverified_user = User(
            id=user_id,
            name="Login Test",
            email="logintest@example.com",
            phone_number="9800011122",
            reference_id="CNX-LOGIN",
            password_hash=hash_password(password="ValidPassword123!"),
            is_verified=False,
            is_active=True,
        )
        session = _FakeDBSession()
        user_repo = _FakeUserRepository([unverified_user])
        service = AuthService(session=session)
        service.user_repository = user_repo

        with self.assertRaises(AccountUnverifiedError) as ctx:
            run_coroutine(service.login_user(email="logintest@example.com", password="ValidPassword123!"))

        self.assertEqual(ctx.exception.error_code, "ACCOUNT_UNVERIFIED")
        self.assertEqual(ctx.exception.user_id, str(user_id))
        self.assertEqual(ctx.exception.channel, "phone")

    def test_notification_service_dev_logging(self):
        notif_service = NotificationService()
        phone_delivered = run_coroutine(
            notif_service.send_otp(channel=OTPChannel.PHONE, destination="9876543210", otp="123456")
        )
        self.assertTrue(phone_delivered)

        email_delivered = run_coroutine(
            notif_service.send_otp(channel=OTPChannel.EMAIL, destination="test@example.com", otp="654321")
        )
        self.assertTrue(email_delivered)


if __name__ == "__main__":
    unittest.main()
