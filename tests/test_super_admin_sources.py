import unittest
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.core.auth import require_super_admin
from app.core.constants import ApplicationType, LoanType, OTPChannel
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.enums.user import UserRoleEnum
from app.models.acquisition_source import AcquisitionSourceModel
from app.models.user import User
from app.repositories.acquisition_source import compact_source_key, normalize_source_key
from app.schemas.acquisition_source import CreateAcquisitionSourceRequest
from app.schemas.auth import RegisterRequest
from app.schemas.lead import LeadRequest
from app.services.acquisition_source import AcquisitionSourceService
from app.services.auth import AuthService
from app.services.lead import LeadService
from app.services.qr_code import QRCodeService


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
        self.committed = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None

    async def refresh(self, obj, attribute_names=None):
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(UTC)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.now(UTC)


class _FakeAcquisitionSourceRepository:
    def __init__(self, initial: list[AcquisitionSourceModel] | None = None):
        self.items: list[AcquisitionSourceModel] = list(initial or [])

    async def create(self, *, source: AcquisitionSourceModel) -> AcquisitionSourceModel:
        if source.created_at is None:
            source.created_at = datetime.now(UTC)
        if source.updated_at is None:
            source.updated_at = datetime.now(UTC)
        self.items.append(source)
        return source

    async def delete(self, *, source: AcquisitionSourceModel) -> None:
        self.items = [item for item in self.items if item.id != source.id]

    async def get_by_id(self, *, source_id: UUID) -> AcquisitionSourceModel | None:
        for item in self.items:
            if item.id == source_id:
                return item
        return None

    async def get_by_key_or_compact(self, *, name: str) -> AcquisitionSourceModel | None:
        clean_key = normalize_source_key(name)
        compact = compact_source_key(name)
        for item in self.items:
            if item.normalized_key == clean_key or compact_source_key(item.name) == compact:
                return item
        return None

    async def list_all_with_counts(self) -> list[tuple[AcquisitionSourceModel, int, int]]:
        return [(item, 3, 2) for item in self.items]

    async def resolve_source_name(self, *, raw_source: str | None) -> str:
        if not raw_source or not str(raw_source).strip():
            return "Browser"
        matched = await self.get_by_key_or_compact(name=str(raw_source))
        return matched.name if matched else "Browser"


class _FakeLeadRepository:
    def __init__(self):
        self.leads = []

    async def create(self, *, lead):
        self.leads.append(lead)
        return lead


class _FakeHistoryRepository:
    async def create(self, *, history):
        return history


class _FakeUserRepository:
    def __init__(self):
        self.users = []

    async def get_by_reference_id(self, *, reference_id: str):
        return None

    async def get_by_email(self, *, email: str):
        return None

    async def get_by_phone_number(self, *, phone_number: str):
        return None

    async def create(self, *, user: User):
        self.users.append(user)
        return user


class _FakeOTPService:
    async def create_otp(self, *, user_id: UUID, channel: OTPChannel) -> str:
        return "123456"


class _FakeNotificationService:
    async def send_otp(self, *, channel: OTPChannel, destination: str, otp: str) -> bool:
        return True


class SuperAdminSourcesTests(unittest.TestCase):
    def _make_super_admin(self) -> User:
        return User(
            id=uuid4(),
            name="Super Admin",
            email="superadmin@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-SUPER1",
            role=UserRoleEnum.SUPER_ADMIN,
            is_verified=True,
        )

    def test_require_super_admin_guard(self):
        super_admin = self._make_super_admin()
        admin = User(
            id=uuid4(),
            name="Admin",
            email="admin@example.com",
            phone_number="9876543211",
            reference_id="CNX-REF-ADMIN1",
            role=UserRoleEnum.ADMIN,
            is_verified=True,
        )
        regular = User(
            id=uuid4(),
            name="User",
            email="user@example.com",
            phone_number="9876543212",
            reference_id="CNX-REF-USER1",
            role=UserRoleEnum.USER,
            is_verified=True,
        )

        self.assertEqual(run_coroutine(require_super_admin(current_user=super_admin)).id, super_admin.id)

        with self.assertRaises(ForbiddenError):
            run_coroutine(require_super_admin(current_user=admin))

        with self.assertRaises(ForbiddenError):
            run_coroutine(require_super_admin(current_user=regular))

    def test_create_source_validation_and_duplicate_rejection(self):
        with self.assertRaises(ValidationError):
            CreateAcquisitionSourceRequest(name="A")

        with self.assertRaises(ValidationError):
            CreateAcquisitionSourceRequest(name="Bad<script>")

        actor = self._make_super_admin()
        browser = AcquisitionSourceModel(
            id=uuid4(),
            name="Browser",
            normalized_key="browser",
            is_system=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo = _FakeAcquisitionSourceRepository([browser])
        service = AcquisitionSourceService(session=_FakeDBSession(), repository=repo)

        created = run_coroutine(
            service.create_source(
                payload=CreateAcquisitionSourceRequest(
                    name="GoldGym",
                    description="Gold Gym Standee QR",
                ),
                actor=actor,
            )
        )
        self.assertEqual(created.name, "GoldGym")
        self.assertFalse(created.is_system)
        self.assertIn("source=GoldGym", created.target_url)

        # Duplicate case-insensitive / compact variant rejected
        with self.assertRaises(ConflictError):
            run_coroutine(
                service.create_source(
                    payload=CreateAcquisitionSourceRequest(name="gold gym"),
                    actor=actor,
                )
            )

    def test_delete_source_protects_system_default(self):
        actor = self._make_super_admin()
        browser = AcquisitionSourceModel(
            id=uuid4(),
            name="Browser",
            normalized_key="browser",
            is_system=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        custom = AcquisitionSourceModel(
            id=uuid4(),
            name="BrightFitness",
            normalized_key="brightfitness",
            is_system=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo = _FakeAcquisitionSourceRepository([browser, custom])
        service = AcquisitionSourceService(session=_FakeDBSession(), repository=repo)

        with self.assertRaises(ConflictError):
            run_coroutine(service.delete_source(source_id=browser.id, actor=actor))

        with self.assertRaises(NotFoundError):
            run_coroutine(service.delete_source(source_id=uuid4(), actor=actor))

        run_coroutine(service.delete_source(source_id=custom.id, actor=actor))
        self.assertEqual(len(repo.items), 1)
        self.assertEqual(repo.items[0].name, "Browser")

    def test_generate_qr_code_png_and_svg(self):
        custom = AcquisitionSourceModel(
            id=uuid4(),
            name="GoldGym",
            normalized_key="goldgym",
            is_system=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo = _FakeAcquisitionSourceRepository([custom])
        service = AcquisitionSourceService(session=_FakeDBSession(), repository=repo)

        url = QRCodeService.build_target_url(
            source_name="GoldGym",
            page="apply",
            ref="cnx-ref-123",
            base_url="https://credhexa.com",
        )
        self.assertEqual(url, "https://credhexa.com/apply?source=GoldGym&ref=CNX-REF-123")

        png_bytes, png_mime, png_name = run_coroutine(
            service.generate_qr_file(source_id=custom.id, file_format="png")
        )
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(png_mime, "image/png")
        self.assertEqual(png_name, "qr-GoldGym.png")

        svg_bytes, svg_mime, svg_name = run_coroutine(
            service.generate_qr_file(source_id=custom.id, file_format="svg", page="register")
        )
        self.assertIn(b"<svg", svg_bytes)
        self.assertEqual(svg_mime, "image/svg+xml")
        self.assertEqual(svg_name, "qr-GoldGym.svg")

    def test_lead_and_auth_resolve_dynamic_db_source(self):
        gold_gym = AcquisitionSourceModel(
            id=uuid4(),
            name="GoldGym",
            normalized_key="goldgym",
            is_system=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        source_repo = _FakeAcquisitionSourceRepository([gold_gym])

        user = User(
            id=uuid4(),
            name="Applicant",
            email="applicant@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-APP1",
        )
        lead_repo = _FakeLeadRepository()
        lead_service = LeadService(
            session=_FakeDBSession(),
            lead_repository=lead_repo,
            lead_status_history_repository=_FakeHistoryRepository(),
            user_repository=_FakeUserRepository(),
            acquisition_source_repository=source_repo,
        )

        # Valid dynamic DB source (case/separator variant) resolves cleanly
        req_valid = LeadRequest(
            full_name="JOHN DOE",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            contact_number="9876543210",
            email="john@example.com",
            city="Mumbai",
            loan_amount=Decimal("500000"),
            monthly_income=Decimal("50000"),
            credit_score=750,
            source="gold gym",
        )
        lead_valid = run_coroutine(lead_service.create_lead(lead_request=req_valid, user=user))
        self.assertEqual(lead_valid.source, "GoldGym")

        # Unregistered source falls back to Browser
        req_spam = LeadRequest(
            full_name="JANE DOE",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            contact_number="9876543210",
            email="jane@example.com",
            city="Delhi",
            loan_amount=Decimal("300000"),
            monthly_income=Decimal("40000"),
            credit_score=740,
            source="unregistered-spam",
        )
        lead_spam = run_coroutine(lead_service.create_lead(lead_request=req_spam, user=user))
        self.assertEqual(lead_spam.source, "Browser")

        # AuthService registration resolves dynamic DB source
        auth_user_repo = _FakeUserRepository()
        auth_service = AuthService(
            session=_FakeDBSession(),
            otp_service=_FakeOTPService(),
            notification_service=_FakeNotificationService(),
            acquisition_source_repository=source_repo,
        )
        auth_service.user_repository = auth_user_repo
        reg = RegisterRequest(
            name="New User",
            email="newuser@example.com",
            phone_number="9876543215",
            password="Password123!",
            source="goldgym",
        )
        run_coroutine(auth_service.register_user(data=reg))
        self.assertEqual(auth_user_repo.users[0].source, "GoldGym")


if __name__ == "__main__":
    unittest.main()
